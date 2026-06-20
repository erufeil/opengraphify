"""Core pipeline: detect → AST extract → semantic extract → build → cluster → export."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from opengraphify.config import Config


def run(
    root: Path,
    config: Config,
    *,
    force: bool = False,
    max_files: int | None = None,
) -> bool:
    """Execute one graph-update pass.

    Returns True when the graph was updated, False when already current.
    All graphify imports are deferred until after config.apply_env() so
    that env vars (OLLAMA_BASE_URL etc.) are set before graphify.llm
    populates its BACKENDS dict.

    max_files: if set, cap the number of *uncached* semantic files processed
    this run (the slow, LLM-driven step). Lets you chip away at a large repo in
    bounded batches — e.g. `--max 50` — instead of one marathon pass that pins
    the CPU for hours. Already-cached files don't count against the cap, so each
    run makes `max_files` files of fresh progress.
    """
    root = Path(root).resolve()
    graphify_out = root / config.out_dir
    manifest_path = graphify_out / "manifest.json"
    graph_json_path = graphify_out / "graph.json"

    t0 = time.time()

    # ------------------------------------------------------------------ #
    # 1. Detect changed files
    # ------------------------------------------------------------------ #
    print(f"[opengraphify] loading graphify.detect ...", flush=True)
    from graphify.detect import (
        detect as _detect,
        detect_incremental as _detect_incremental,
        save_manifest as _save_manifest,
    )
    print(f"[opengraphify] ready", flush=True)

    incremental = not force and manifest_path.exists() and graph_json_path.exists()

    if incremental:
        print(f"[opengraphify] incremental scan of {root}")
        detection = _detect_incremental(root, manifest_path=str(manifest_path))
        files_by_type = detection.get("files", {})
        new_by_type = detection.get("new_files", {})
        code_files = [Path(p) for p in new_by_type.get("code", [])]
        doc_files = [Path(p) for p in new_by_type.get("document", [])]
        paper_files = [Path(p) for p in new_by_type.get("paper", [])]
        image_files = [Path(p) for p in new_by_type.get("image", [])]
        deleted_files = list(detection.get("deleted_files", []))
        unchanged_total = sum(len(v) for v in detection.get("unchanged_files", {}).values())

        total_changed = len(code_files) + len(doc_files) + len(paper_files) + len(image_files)
        if total_changed == 0 and not deleted_files:
            print(f"[opengraphify] graph is up to date ({unchanged_total} files unchanged)")
            return False

        print(
            f"[opengraphify] {len(code_files)} code, {len(doc_files)} docs, "
            f"{len(paper_files)} papers, {len(image_files)} images changed; "
            f"{unchanged_total} unchanged; {len(deleted_files)} deleted"
        )
    else:
        print(f"[opengraphify] full scan of {root}")
        detection = _detect(root)
        files_by_type = detection.get("files", {})
        code_files = [Path(p) for p in files_by_type.get("code", [])]
        doc_files = [Path(p) for p in files_by_type.get("document", [])]
        paper_files = [Path(p) for p in files_by_type.get("paper", [])]
        image_files = [Path(p) for p in files_by_type.get("image", [])]
        deleted_files = []
        unchanged_total = 0
        print(
            f"[opengraphify] found {len(code_files)} code, "
            f"{len(doc_files)} docs, {len(paper_files)} papers, {len(image_files)} images"
        )

    # ------------------------------------------------------------------ #
    # 2. AST extraction on code files (no LLM)
    # ------------------------------------------------------------------ #
    ast_result: dict = {"nodes": [], "edges": [], "input_tokens": 0, "output_tokens": 0}
    if code_files:
        from graphify.extract import extract as _ast_extract
        print(f"[opengraphify] AST extraction on {len(code_files)} code files...")
        try:
            ast_result = _ast_extract(code_files, cache_root=root)
            print(
                f"[opengraphify] AST: {len(ast_result.get('nodes', []))} nodes, "
                f"{len(ast_result.get('edges', []))} edges"
            )
        except Exception as exc:
            print(f"[opengraphify] AST extraction failed: {exc}", file=sys.stderr)

    # ------------------------------------------------------------------ #
    # 3. Semantic extraction on docs / papers / images (uses LLM)
    # ------------------------------------------------------------------ #
    semantic_files = doc_files + paper_files + image_files
    sem_result: dict = {
        "nodes": [], "edges": [], "hyperedges": [],
        "input_tokens": 0, "output_tokens": 0,
    }

    if semantic_files:
        from graphify.llm import (
            BACKENDS as _BACKENDS,
            extract_corpus_parallel as _extract_corpus_parallel,
        )
        try:
            from graphify.llm import _pack_chunks_by_tokens as _pack_chunks
        except Exception:
            _pack_chunks = None
        # Patch BACKENDS at runtime so the configured endpoint is used even if
        # the env var was set after graphify.llm was first imported.
        _BACKENDS["ollama"]["base_url"] = config.base_url
        _BACKENDS["ollama"]["default_model"] = config.model

        backend = config.graphify_backend()
        api_key = config.api_key or "opengraphify"

        from graphify.cache import (
            check_semantic_cache as _check_cache,
            save_semantic_cache as _save_cache,
        )
        cached_nodes, cached_edges, cached_hyperedges, uncached_paths = _check_cache(
            [str(p) for p in semantic_files], root=root
        )
        sem_result["nodes"].extend(cached_nodes)
        sem_result["edges"].extend(cached_edges)
        sem_result["hyperedges"].extend(cached_hyperedges)
        cache_hits = len(semantic_files) - len(uncached_paths)
        if cache_hits:
            print(f"[opengraphify] semantic cache: {cache_hits} hit / {len(uncached_paths)} miss")

        # --max: process only the first N uncached files this run. The rest stay
        # uncached and are picked up by the next run (they're left out of the
        # manifest below, so an incremental scan re-detects them). Combined with
        # per-chunk caching, this turns a huge repo into resumable batches.
        if max_files is not None and max_files > 0 and len(uncached_paths) > max_files:
            print(
                f"[opengraphify] --max {max_files}: processing {max_files} of "
                f"{len(uncached_paths)} uncached files this run "
                f"({len(uncached_paths) - max_files} deferred to a later run)"
            )
            uncached_paths = uncached_paths[:max_files]

        if uncached_paths:
            uncached_pathobjs = [Path(p) for p in uncached_paths]
            n_total = len(uncached_pathobjs)
            print(
                f"[opengraphify] semantic extraction on {n_total} files "
                f"via {backend} ({config.model}), token_budget={config.token_budget:,}..."
            )

            # Files are LLM-processed in parallel chunks (one request per chunk,
            # packed by token budget + directory). Pre-compute the same chunk plan
            # graphify uses so we can report which files each chunk covers; per-file
            # lines therefore appear in bursts as each chunk completes.
            _TOKEN_BUDGET = config.token_budget
            chunks = [uncached_pathobjs]
            if _pack_chunks is not None:
                try:
                    chunks = _pack_chunks(uncached_pathobjs, token_budget=_TOKEN_BUDGET)
                except Exception:
                    chunks = [uncached_pathobjs]

            progress = {"done": 0}

            def _on_chunk(idx: int, total: int, _r: dict) -> None:
                # Persist this chunk's results to the semantic cache immediately.
                # save_semantic_cache is keyed per source_file, so writing a chunk
                # at a time is correct and makes the run crash-recoverable: if the
                # machine dies (e.g. a thermal shutdown) mid-corpus, every chunk
                # completed so far is already cached and the next run resumes from
                # where it stopped instead of re-processing everything (#cache).
                try:
                    _save_cache(
                        _r.get("nodes", []),
                        _r.get("edges", []),
                        _r.get("hyperedges", []),
                        root=root,
                    )
                except Exception as exc:
                    print(
                        f"[opengraphify] WARNING: could not cache chunk {idx + 1}/{total}: {exc}",
                        file=sys.stderr,
                    )
                chunk_files = chunks[idx] if idx < len(chunks) else []
                for f in chunk_files:
                    progress["done"] += 1
                    print(
                        f"[opengraphify] semantic extraction on {Path(f).name} "
                        f"({progress['done']}/{n_total})",
                        flush=True,
                    )

            # Force valid JSON output for small local models (they otherwise
            # reply in prose, which graphify can't parse). This goes through the
            # backend's extra_body, which also bypasses graphify's auto num_ctx —
            # so we pin a fixed num_ctx sized to our budgets. Scoped to the
            # extraction call and restored afterwards so community labeling later
            # keeps graphify's own num_ctx handling.
            _prev_extra = _BACKENDS["ollama"].get("extra_body")
            if config.force_json:
                _num_ctx = max(8192, config.token_budget + config.max_output_tokens + 2000)
                _BACKENDS["ollama"]["extra_body"] = {
                    "options": {"num_ctx": _num_ctx},
                    "keep_alive": "10m",
                    "response_format": {"type": "json_object"},
                }
                print(
                    f"[opengraphify] forcing JSON output (num_ctx={_num_ctx:,}, "
                    f"max_retry_depth={config.max_retry_depth})"
                )
            try:
                fresh = _extract_corpus_parallel(
                    uncached_pathobjs,
                    backend=backend,
                    api_key=api_key,
                    model=config.model,
                    root=root,
                    token_budget=_TOKEN_BUDGET,
                    max_retry_depth=config.max_retry_depth,
                    on_chunk_done=_on_chunk,
                )
                try:
                    _save_cache(
                        fresh.get("nodes", []),
                        fresh.get("edges", []),
                        fresh.get("hyperedges", []),
                        root=root,
                    )
                except Exception as exc:
                    print(f"[opengraphify] WARNING: could not write semantic cache: {exc}", file=sys.stderr)

                sem_result["nodes"].extend(fresh.get("nodes", []))
                sem_result["edges"].extend(fresh.get("edges", []))
                sem_result["hyperedges"].extend(fresh.get("hyperedges", []))
                sem_result["input_tokens"] += fresh.get("input_tokens", 0)
                sem_result["output_tokens"] += fresh.get("output_tokens", 0)
            except Exception as exc:
                print(f"[opengraphify] semantic extraction failed: {exc}", file=sys.stderr)
            finally:
                _BACKENDS["ollama"]["extra_body"] = _prev_extra

    # ------------------------------------------------------------------ #
    # 4. Merge AST + semantic results
    # ------------------------------------------------------------------ #
    merged: dict = {
        "nodes": list(ast_result.get("nodes", [])) + list(sem_result.get("nodes", [])),
        "edges": list(ast_result.get("edges", [])) + list(sem_result.get("edges", [])),
        "hyperedges": list(sem_result.get("hyperedges", [])),
        "input_tokens": ast_result.get("input_tokens", 0) + sem_result.get("input_tokens", 0),
        "output_tokens": ast_result.get("output_tokens", 0) + sem_result.get("output_tokens", 0),
    }

    if not merged["nodes"] and not merged["edges"]:
        print("[opengraphify] WARNING: extraction produced no nodes — skipping export", file=sys.stderr)
        return False

    # ------------------------------------------------------------------ #
    # 5. Build graph (incremental merge or fresh build)
    # ------------------------------------------------------------------ #
    from graphify.build import build as _build, build_merge as _build_merge
    from graphify.cluster import cluster as _cluster, score_all as _score_all

    graphify_out.mkdir(parents=True, exist_ok=True)

    if incremental:
        G = _build_merge(
            [merged],
            graph_path=graph_json_path,
            prune_sources=deleted_files or None,
            dedup=True,
            root=root,
        )
    else:
        G = _build([merged], dedup=True, root=root)

    if G.number_of_nodes() == 0:
        print("[opengraphify] WARNING: resulting graph is empty", file=sys.stderr)
        return False

    # ------------------------------------------------------------------ #
    # 6. Community detection + scoring
    # ------------------------------------------------------------------ #
    communities = _cluster(G)
    cohesion = _score_all(G, communities)

    from graphify.analyze import god_nodes as _god_nodes, surprising_connections as _surprising
    try:
        gods = _god_nodes(G)
    except Exception:
        gods = []
    try:
        surprises = _surprising(G, communities)
    except Exception:
        surprises = []

    # ------------------------------------------------------------------ #
    # 6b. Community labeling — name each community via the configured LLM.
    # Without this the HTML meta-graph (built when the node count exceeds the
    # viz limit) and the report fall back to "Community N" placeholders, so
    # every aggregated node appears unnamed. Mirrors graphify's standalone CLI.
    # ------------------------------------------------------------------ #
    labels_path = graphify_out / ".graphify_labels.json"
    community_labels: dict = {cid: f"Community {cid}" for cid in communities}
    try:
        from graphify.llm import (
            BACKENDS as _LBL_BACKENDS,
            generate_community_labels as _gen_labels,
        )
        # Point the labeling backend at the configured endpoint/model too.
        _LBL_BACKENDS["ollama"]["base_url"] = config.base_url
        _LBL_BACKENDS["ollama"]["default_model"] = config.model
        community_labels, _lbl_src = _gen_labels(
            G, communities, backend=config.graphify_backend(), gods=gods
        )
        print(
            f"[opengraphify] community labels: {_lbl_src} "
            f"({len(community_labels)} communities)"
        )
    except Exception as exc:
        print(f"[opengraphify] WARNING: community labeling failed: {exc}", file=sys.stderr)
    try:
        labels_path.write_text(
            json.dumps({str(k): v for k, v in community_labels.items()}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as exc:
        print(f"[opengraphify] WARNING: could not write labels: {exc}", file=sys.stderr)

    # ------------------------------------------------------------------ #
    # 7. Export
    # ------------------------------------------------------------------ #
    from graphify.export import backup_if_protected as _backup, to_json as _to_json

    _backup(graphify_out)
    _to_json(G, communities, str(graph_json_path), force=True)

    if sem_result.get("output_tokens", 0) > 0:
        (graphify_out / ".graphify_semantic_marker").write_text(
            json.dumps({"output_tokens": sem_result["output_tokens"]}), encoding="utf-8"
        )

    if config.generate_html:
        from graphify.export import to_html as _to_html
        try:
            _to_html(
                G, communities, str(graphify_out / "graph.html"),
                community_labels=community_labels or None, node_limit=5000,
            )
        except Exception as exc:
            print(f"[opengraphify] WARNING: could not generate HTML: {exc}", file=sys.stderr)

    if config.generate_report:
        from graphify.report import generate as _gen_report
        token_cost = {
            "input": merged["input_tokens"],
            "output": merged["output_tokens"],
            "cost_usd": 0.0,
        }
        try:
            report_md = _gen_report(
                G, communities, cohesion, community_labels, gods, surprises,
                detection, token_cost, str(root),
            )
            (graphify_out / "GRAPH_REPORT.md").write_text(report_md, encoding="utf-8")
        except Exception as exc:
            print(f"[opengraphify] WARNING: could not generate report: {exc}", file=sys.stderr)

    # Write analysis sidecar (read by graphify's label/query commands)
    analysis = {
        "communities": {str(k): v for k, v in communities.items()},
        "cohesion": {str(k): v for k, v in cohesion.items()},
        "gods": gods,
        "surprises": surprises,
        "tokens": {"input": merged["input_tokens"], "output": merged["output_tokens"]},
    }
    (graphify_out / ".graphify_analysis.json").write_text(
        json.dumps(analysis, indent=2), encoding="utf-8"
    )

    # ------------------------------------------------------------------ #
    # 8. Save manifest — graphify's --update will see the graph as current
    # ------------------------------------------------------------------ #
    _sem_extracted: set[str] = {
        n.get("source_file", "") for n in sem_result.get("nodes", [])
    } | {e.get("source_file", "") for e in sem_result.get("edges", [])}
    _sem_extracted.discard("")
    _sem_types = {"document", "paper", "image"}
    manifest_files = {
        ftype: [
            f for f in flist
            if ftype not in _sem_types or f in _sem_extracted
        ]
        for ftype, flist in files_by_type.items()
    }
    try:
        _save_manifest(manifest_files, manifest_path=str(manifest_path), kind="both", root=root)
    except Exception as exc:
        print(f"[opengraphify] WARNING: could not write manifest: {exc}", file=sys.stderr)

    elapsed = round(time.time() - t0, 1)
    print(
        f"[opengraphify] done in {elapsed}s — "
        f"{G.number_of_nodes()} nodes, {G.number_of_edges()} edges "
        f"({len(communities)} communities)"
    )
    if merged["input_tokens"] or merged["output_tokens"]:
        print(
            f"[opengraphify] tokens: {merged['input_tokens']:,} in / "
            f"{merged['output_tokens']:,} out"
        )
    return True
