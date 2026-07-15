"""Core pipeline: detect → AST extract → semantic extract → build → cluster → export."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from opengraphify.config import Config


# HTTP status codes worth retrying: request timeout / conflict / too-early,
# rate limit, and the 5xx family — including Cloudflare's own 52x origin
# errors (524 = origin response timeout, the case that prompted this).
_RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504, 520, 521, 522, 523, 524, 525, 527, 529}
# openai SDK errors that carry no status_code but are still transient.
_RETRYABLE_EXC_NAMES = {"APITimeoutError", "APIConnectionError"}


def _retryable_wait(exc: BaseException, default_wait: float) -> float | None:
    """Seconds to wait before retrying `exc`, or None if it is not retryable.

    Honours a server-supplied `Retry-After` header or a `retry_after` field in
    the error body (e.g. Cloudflare 524) when present; otherwise falls back to
    `default_wait`. Non-transient errors (auth failures, HTTP 400 context
    overflow, etc.) return None so they propagate unchanged — graphify's own
    bisect retry still handles context-overflow.
    """
    status = getattr(exc, "status_code", None)
    if status not in _RETRYABLE_STATUS and type(exc).__name__ not in _RETRYABLE_EXC_NAMES:
        return None
    wait: float | None = None
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        raw = body.get("retry_after", body.get("retry-after"))
        try:
            wait = float(raw) if raw is not None else None
        except (TypeError, ValueError):
            wait = None
    if wait is None:
        headers = getattr(getattr(exc, "response", None), "headers", None)
        if headers is not None:
            try:
                raw = headers.get("retry-after")
                wait = float(raw) if raw is not None else None
            except (TypeError, ValueError):
                wait = None
    if wait is None:
        wait = default_wait
    return max(1.0, min(wait, 300.0))


def _install_http_retry(config: Config) -> None:
    """Wrap graphify's LLM-call functions with retry-on-retryable-HTTP-error.

    graphify is re-cloned on every update (actualiza-librerias.bat), so this
    fix lives here and is applied at runtime — mirroring how opengraphify
    already patches `graphify.llm.BACKENDS`. graphify's adaptive retry only
    bisects truncation/context-overflow and re-raises transient HTTP errors
    (Cloudflare 524, 429, 5xx, connection resets), dropping the whole chunk for
    the run. Wrapping the single-call functions lets a retryable error wait +
    retry in-run, recovering the chunk instead of deferring it to the next run.
    Idempotent: the `_og_retry_wrapped` guard keeps --watch loops from stacking
    wrappers.
    """
    if config.chunk_retries <= 0:
        return
    try:
        from graphify import llm as _llm
    except Exception as exc:  # noqa: BLE001
        print(f"[opengraphify] WARNING: could not install HTTP retry: {exc}", file=sys.stderr)
        return

    import functools

    def _wrap(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            attempt = 0
            while True:
                try:
                    return func(*args, **kwargs)
                except Exception as exc:  # noqa: BLE001
                    wait = _retryable_wait(exc, config.retry_wait_seconds)
                    if wait is None or attempt >= config.chunk_retries:
                        raise
                    attempt += 1
                    print(
                        f"[opengraphify] retryable backend error ({type(exc).__name__}): "
                        f"retry {attempt}/{config.chunk_retries} in {wait:g}s...",
                        file=sys.stderr,
                        flush=True,
                    )
                    time.sleep(wait)
        wrapper._og_retry_wrapped = True  # type: ignore[attr-defined]
        return wrapper

    for fname in ("_call_openai_compat", "_call_llm"):
        fn = getattr(_llm, fname, None)
        if fn is None or getattr(fn, "_og_retry_wrapped", False):
            continue
        setattr(_llm, fname, _wrap(fn))


def _provider_routing_extra_body(config: Config) -> dict:
    """extra_body fragment for OpenRouter's provider routing (nitro mode).

    ``sort: "throughput"`` overrides OpenRouter's default price-based load
    balancing so it always tries the fastest provider for the model first,
    trading cost for speed. Returns {} when config.nitro is off. Harmless to
    send unconditionally to any backend: a literal Ollama server (or any other
    OpenAI-compatible endpoint) just ignores an unrecognized top-level field.
    """
    return {"provider": {"sort": "throughput"}} if config.nitro else {}


def _reasoning_effort_none() -> dict:
    """OpenRouter's own reasoning-control field.

    NOT graphify's ``{"thinking": {"type": "disabled"}}`` convention — that one
    is aimed at Moonshot/DeepSeek's *native* APIs and is a silent no-op when the
    request actually goes through OpenRouter's gateway (OpenRouter normalizes
    reasoning control across providers via its own ``reasoning`` field instead).
    ``effort: "none"`` asks it to skip the model's chain-of-thought entirely. A
    provider with mandatory reasoning may reject this outright — callers here
    already fall back gracefully (placeholder labels / a logged warning) so
    that's a no-worse-than-today outcome, not a new failure mode.
    """
    return {"reasoning": {"effort": "none"}}


def _cap_chunk_file_count(chunks: "list[list]", max_files: int) -> "list[list]":
    """Re-split any chunk longer than max_files into smaller chunks, in order.

    graphify's own chunk packer (_pack_chunks_by_tokens) only bounds chunks by
    token budget, not by how many separate documents they contain. A chunk can
    fit the token budget easily while still holding more discrete files than a
    small model can reliably track in one completion (#reenvio — see the
    coverage-retry loop in run()). This is the second, file-count dimension on
    top of that packing.
    """
    capped: "list[list]" = []
    for chunk in chunks:
        if len(chunk) <= max_files:
            capped.append(chunk)
        else:
            capped.extend(chunk[i:i + max_files] for i in range(0, len(chunk), max_files))
    return capped


def _disable_thinking_via_env() -> bool:
    """Opt-in: GRAPHIFY_DISABLE_THINKING=1 also turns off reasoning for the
    *extraction* call when routed through OpenRouter (see _reasoning_effort_none).
    graphify itself only honours this env var for its own native-API `thinking`
    convention, which does nothing over OpenRouter — this re-reads the same var
    so the documented opt-in still has an effect on this backend. Unlike
    labeling, extraction does NOT get this by default: graphify's own docs note
    disabling reasoning trades rare empty-content failures for more frequent
    (benign) truncation and measurably lower extraction coverage, so it stays a
    deliberate user choice, not a forced default.
    """
    return os.environ.get("GRAPHIFY_DISABLE_THINKING", "").strip().lower() in ("1", "true", "yes", "on")


def _scan_counter():
    """Monkeypatch graphify.detect.classify_file to count files as they are
    scanned. Returns ``(counter, restore)`` where ``counter["n"]`` climbs during
    detect()/detect_incremental() (both call classify_file once per file).

    graphify is re-cloned on update, so this lives here. Best-effort: if the
    symbol can't be patched, returns a counter that stays at 0 and the heartbeat
    simply falls back to showing elapsed time.
    """
    counter = {"n": 0}
    try:
        from graphify import detect as _d
        orig = _d.classify_file
    except Exception:
        return counter, (lambda: None)
    import functools

    @functools.wraps(orig)
    def _counting(path):
        counter["n"] += 1
        return orig(path)

    _d.classify_file = _counting

    def _restore():
        try:
            _d.classify_file = orig
        except Exception:
            pass

    return counter, _restore


def _with_heartbeat(label: str, fn, *, every: float = 8.0, counter: dict | None = None):
    """Run blocking ``fn()`` in a thread, printing a progress heartbeat.

    graphify's detect()/detect_incremental() are single blocking calls with no
    progress callback. On a huge tree (e.g. the Linux kernel, ~80k files) the
    initial full walk can take 15-20 min, and with nothing printed between
    "ready" and "found N files" it looks frozen. This prints a heartbeat every
    ``every`` seconds — including the live file count from ``counter`` when
    given — so a long scan is visibly alive. Small repos finish before the first
    tick, so there's no noise.
    """
    import threading

    box: dict = {}
    done = threading.Event()

    def _worker():
        try:
            box["value"] = fn()
        except BaseException as exc:  # noqa: BLE001 — re-raised on the main thread
            box["error"] = exc
        finally:
            done.set()

    th = threading.Thread(target=_worker, daemon=True)
    t0 = time.time()
    th.start()
    while not done.wait(timeout=every):
        elapsed = int(time.time() - t0)
        if counter is not None:
            print(
                f"[opengraphify] {label}... {counter['n']:,} files scanned ({elapsed}s)",
                flush=True,
            )
        else:
            print(
                f"[opengraphify] {label}... {elapsed}s elapsed (working, not frozen)",
                flush=True,
            )
    if "error" in box:
        raise box["error"]
    return box.get("value")


def run(
    root: Path,
    config: Config,
    *,
    force: bool = False,
    max_files: int | None = None,
    code_only: bool = False,
    label_clusters: bool = True,
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

    code_only: skip the entire semantic step — no LLM/Ollama calls at all. Only
    the AST (code) extraction runs, plus clustering/export, so the pass is fast
    and offline. Change detection and the manifest use the AST hash (kind="ast"),
    which *preserves* the semantic_hash of already-extracted docs — so a
    code-only pass never forgets prior semantic work or forces a re-extraction.
    Ideal with --watch to keep the code graph continuously fresh without heat/
    tokens. Community labeling is skipped too (existing labels are reused).

    label_clusters: whether to name communities via the LLM at the end. Always
    True on a normal run. Set False (the plain `--code-only`) for a fully offline
    pass. Setting it True together with code_only=True is the `--code-only-1`
    variant: no semantic inference, but the final ~1-call-per-100-communities
    labeling pass still runs so the clusters get real names.
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
        print(f"[opengraphify] incremental scan of {root}" + (" (code-only)" if code_only else ""))
        # code-only detects changes by AST/content hash; the normal pass detects
        # by semantic_hash so files touched by an AST-only run get re-extracted.
        _scan_ctr, _scan_restore = _scan_counter()
        try:
            detection = _with_heartbeat(
                "scanning (incremental)",
                lambda: _detect_incremental(
                    root, manifest_path=str(manifest_path),
                    kind="ast" if code_only else "semantic",
                ),
                counter=_scan_ctr,
            )
        finally:
            _scan_restore()
        files_by_type = detection.get("files", {})
        new_by_type = detection.get("new_files", {})
        code_files = [Path(p) for p in new_by_type.get("code", [])]
        doc_files = [Path(p) for p in new_by_type.get("document", [])]
        paper_files = [Path(p) for p in new_by_type.get("paper", [])]
        image_files = [Path(p) for p in new_by_type.get("image", [])]
        if code_only:
            # Ignore every semantic (LLM) input this pass.
            doc_files = paper_files = image_files = []
        deleted_files = list(detection.get("deleted_files", []))
        unchanged_total = sum(len(v) for v in detection.get("unchanged_files", {}).values())

        total_changed = len(code_files) + len(doc_files) + len(paper_files) + len(image_files)
        if total_changed == 0 and not deleted_files:
            _scope = "code files" if code_only else "files"
            print(f"[opengraphify] graph is up to date ({unchanged_total} {_scope} unchanged)")
            return False

        print(
            f"[opengraphify] {len(code_files)} code, {len(doc_files)} docs, "
            f"{len(paper_files)} papers, {len(image_files)} images changed; "
            f"{unchanged_total} unchanged; {len(deleted_files)} deleted"
        )
    else:
        print(f"[opengraphify] full scan of {root}" + (" (code-only)" if code_only else ""))
        _scan_ctr, _scan_restore = _scan_counter()
        try:
            detection = _with_heartbeat(
                "scanning files", lambda: _detect(root), counter=_scan_ctr,
            )
        finally:
            _scan_restore()
        files_by_type = detection.get("files", {})
        code_files = [Path(p) for p in files_by_type.get("code", [])]
        doc_files = [Path(p) for p in files_by_type.get("document", [])]
        paper_files = [Path(p) for p in files_by_type.get("paper", [])]
        image_files = [Path(p) for p in files_by_type.get("image", [])]
        if code_only:
            doc_files = paper_files = image_files = []
        deleted_files = []
        unchanged_total = 0
        print(
            f"[opengraphify] found {len(code_files)} code, "
            f"{len(doc_files)} docs, {len(paper_files)} papers, {len(image_files)} images"
        )

    # Install in-run retry for transient backend HTTP errors before any LLM work.
    # Needed whenever an LLM call can happen this run: semantic extraction
    # (normal run) or cluster labeling (normal run and the --code-only-1 variant).
    # Plain --code-only never touches the LLM, so it's skipped there.
    if (not code_only) or label_clusters:
        _install_http_retry(config)

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

            # Files are LLM-processed in chunks packed by token budget + directory.
            # token_budget alone doesn't cap how many *separate documents* land in
            # one chunk, though — see the coverage-retry loop below.
            _TOKEN_BUDGET = config.token_budget
            progress = {"done": 0}

            # Force valid JSON output for small local models (they otherwise
            # reply in prose, which graphify can't parse). This goes through the
            # backend's extra_body, which also bypasses graphify's auto num_ctx —
            # so we pin a fixed num_ctx sized to our budgets. Scoped to the
            # extraction call and restored afterwards so community labeling later
            # keeps graphify's own num_ctx handling.
            _prev_extra = _BACKENDS["ollama"].get("extra_body")
            _extraction_extra: dict = dict(_provider_routing_extra_body(config))
            if config.force_json:
                _num_ctx = max(8192, config.token_budget + config.max_output_tokens + 2000)
                _extraction_extra.update({
                    "options": {"num_ctx": _num_ctx},
                    "keep_alive": "10m",
                    "response_format": {"type": "json_object"},
                })
                print(
                    f"[opengraphify] forcing JSON output (num_ctx={_num_ctx:,}, "
                    f"max_retry_depth={config.max_retry_depth})"
                )
            if config.provider == "openrouter" and _disable_thinking_via_env():
                _extraction_extra.update(_reasoning_effort_none())
                print(
                    "[opengraphify] GRAPHIFY_DISABLE_THINKING: asking OpenRouter to skip "
                    "reasoning for extraction (trades away some coverage/quality)"
                )
            if config.nitro:
                print(
                    "[opengraphify] nitro: routing to the fastest OpenRouter provider "
                    "for this model, cost over price"
                )
            if _extraction_extra:
                _BACKENDS["ollama"]["extra_body"] = _extraction_extra
            fresh: dict = {
                "nodes": [], "edges": [], "hyperedges": [],
                "input_tokens": 0, "output_tokens": 0,
            }
            try:
                # Coverage-retry loop (#reenvio): a chunk can come back with a
                # clean, valid response that simply omits some of the files it was
                # given — graphify's own extract_corpus_parallel already detects
                # this (fresh["uncovered_files"], #1890) but still leaves those
                # files unprocessed for the run. If a chunk of N files came back
                # with nodes for only n < N of them, that's the model's demonstrated
                # per-call attention ceiling: shrink the chunk plan to at most n
                # files and resend just the dropped ones. Repeats (capped at 4
                # rounds) since a smaller chunk can still overflow a weak model.
                # A *single*-file chunk with no coverage isn't an attention
                # problem — it's a genuinely content-less file — so it's left
                # dropped for the next run exactly like today, not requeued here.
                worklist: list = uncached_pathobjs
                max_files_per_chunk: int | None = None
                for _round in range(4):
                    if not worklist:
                        break
                    round_chunks = [worklist]
                    if _pack_chunks is not None:
                        try:
                            round_chunks = _pack_chunks(worklist, token_budget=_TOKEN_BUDGET)
                        except Exception:
                            round_chunks = [worklist]
                    if max_files_per_chunk is not None:
                        round_chunks = _cap_chunk_file_count(round_chunks, max_files_per_chunk)

                    round_uncovered: list = []
                    worst_n: int | None = None
                    # One _extract_corpus_parallel call per chunk here (rather than
                    # one call for the whole round) so our file-count cap actually
                    # sticks — passed the full worklist, it would just re-pack by
                    # token budget alone internally and undo the cap. opengraphify
                    # always dispatches through the "ollama" backend slot, which
                    # extract_corpus_parallel already forces serial (max_concurrency
                    # = 1), so this loses no parallelism it wasn't already forgoing.
                    for chunk_files in round_chunks:
                        def _on_chunk(
                            idx: int, total: int, _r: dict,
                            _chunk_files=chunk_files, _r_idx=_round,
                        ) -> None:
                            # Persist immediately: crash-recoverable, same reasoning
                            # as before (#cache).
                            try:
                                _save_cache(
                                    _r.get("nodes", []),
                                    _r.get("edges", []),
                                    _r.get("hyperedges", []),
                                    root=root,
                                )
                            except Exception as exc:
                                print(
                                    f"[opengraphify] WARNING: could not cache chunk: {exc}",
                                    file=sys.stderr,
                                )
                            for f in _chunk_files:
                                if _r_idx == 0:
                                    # First pass: keep today's exact "(i/n_total)" format.
                                    progress["done"] += 1
                                    print(
                                        f"[opengraphify] semantic extraction on {Path(f).name} "
                                        f"({progress['done']}/{n_total})",
                                        flush=True,
                                    )
                                else:
                                    # A retry re-sends a file already counted once in
                                    # round 0 — labeling it "(i/n_total)" again would
                                    # make the running count exceed n_total.
                                    print(
                                        f"[opengraphify] retrying semantic extraction on "
                                        f"{Path(f).name} (round {_r_idx + 1})",
                                        flush=True,
                                    )

                        chunk_result = _extract_corpus_parallel(
                            chunk_files,
                            backend=backend,
                            api_key=api_key,
                            model=config.model,
                            root=root,
                            token_budget=_TOKEN_BUDGET,
                            max_retry_depth=config.max_retry_depth,
                            on_chunk_done=_on_chunk,
                        )
                        fresh["nodes"].extend(chunk_result.get("nodes", []))
                        fresh["edges"].extend(chunk_result.get("edges", []))
                        fresh["hyperedges"].extend(chunk_result.get("hyperedges", []))
                        fresh["input_tokens"] += chunk_result.get("input_tokens", 0)
                        fresh["output_tokens"] += chunk_result.get("output_tokens", 0)

                        uncovered_str = chunk_result.get("uncovered_files") or []
                        if uncovered_str and len(chunk_files) > 1:
                            _uncovered_resolved = {Path(p).resolve() for p in uncovered_str}
                            _dropped = [f for f in chunk_files if Path(f).resolve() in _uncovered_resolved]
                            if _dropped:
                                n_covered = len(chunk_files) - len(_dropped)
                                worst_n = n_covered if worst_n is None else min(worst_n, n_covered)
                                round_uncovered.extend(_dropped)

                    if not round_uncovered:
                        break
                    max_files_per_chunk = (
                        max(1, worst_n) if max_files_per_chunk is None
                        else min(max_files_per_chunk, max(1, worst_n))
                    )
                    print(
                        f"[opengraphify] {len(round_uncovered)} file(s) came back with no "
                        f"nodes this round — the model only completed {max_files_per_chunk} "
                        "of a larger batch, so that's now the max files per chunk; "
                        "retrying the rest"
                    )
                    worklist = round_uncovered

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
    if not label_clusters:
        # LLM labeling disabled (plain --code-only): reuse existing community
        # labels when present (IDs that still match keep their names), else keep
        # placeholders. The labels file is left untouched so a prior semantic
        # run's names survive.
        if labels_path.exists():
            try:
                _raw = json.loads(labels_path.read_text(encoding="utf-8"))
                for cid in communities:
                    if str(cid) in _raw:
                        community_labels[cid] = _raw[str(cid)]
            except Exception:
                pass
        print(f"[opengraphify] code-only: skipping LLM labeling ({len(communities)} communities)")
    else:
        try:
            from graphify.llm import (
                BACKENDS as _LBL_BACKENDS,
                generate_community_labels as _gen_labels,
            )
            # Point the labeling backend at the configured endpoint/model too.
            _LBL_BACKENDS["ollama"]["base_url"] = config.base_url
            _LBL_BACKENDS["ollama"]["default_model"] = config.model
            # graphify's _resolve_max_tokens() treats GRAPHIFY_MAX_OUTPUT_TOKENS as an
            # unconditional override rather than a ceiling, so the huge budget we set
            # for extraction (config.max_output_tokens — meant for large doc chunks)
            # leaks into label_communities' own small per-batch cap (normally a few
            # thousand, capped at 8192) and inflates it to whatever extraction uses.
            # On a reasoning-capable model that's free to spend that whole budget on
            # hidden thinking tokens for a trivial "name these communities" prompt,
            # turning a few-second call into a 20+ minute one that outlasts
            # api_timeout (the connection keeps producing bytes, so nothing ever
            # raises to trigger a retry/skip). Unset it for the labeling call so
            # graphify's own small per-batch cap applies, then restore it after in
            # case anything later in this process still wants the extraction value.
            _prev_max_out = os.environ.pop("GRAPHIFY_MAX_OUTPUT_TOKENS", None)
            # _call_openai_compat (extraction) zeroes the SDK's own retry count for
            # backend "ollama" on purpose: 6 silent SDK-level retries x api_timeout
            # can turn one wedged call into a ~21min block before anything raises
            # for graphify's/opengraphify's own retry-or-skip logic to see (graphify
            # calls this out explicitly, #1686). _call_llm (labeling) has no such
            # guard, so it's still exposed to that. Apply the same zero-retry
            # default here — scoped, and only when the user hasn't explicitly set
            # GRAPHIFY_MAX_RETRIES themselves (their choice always wins).
            _prev_max_retries = os.environ.get("GRAPHIFY_MAX_RETRIES")
            if not (_prev_max_retries or "").strip():
                os.environ["GRAPHIFY_MAX_RETRIES"] = "0"
            # Labeling gets the same nitro routing hint as extraction — it's a
            # separate BACKENDS["ollama"]["extra_body"] scope (restored below),
            # not the one extraction just put back to _prev_extra above.
            _prev_lbl_extra = _LBL_BACKENDS["ollama"].get("extra_body")
            _lbl_extra = dict(_provider_routing_extra_body(config))
            if config.provider == "openrouter":
                # Unconditional (unlike extraction's opt-in): a reasoning model
                # can spend the whole small per-batch budget on hidden thinking
                # and return empty content, failing the entire batch to
                # placeholders (observed on nemotron-3-nano-30b-a3b). Naming a
                # cluster in 2-5 words has no accuracy upside from reasoning, so
                # there's no coverage/quality tradeoff to weigh here the way
                # there is for extraction — mirrors graphify's own unconditional
                # thinking-disable for kimi-k2.6, same rationale.
                _lbl_extra.update(_reasoning_effort_none())
            if _lbl_extra:
                _LBL_BACKENDS["ollama"]["extra_body"] = _lbl_extra
            try:
                community_labels, _lbl_src = _gen_labels(
                    G, communities, backend=config.graphify_backend(), gods=gods
                )
            finally:
                if _prev_max_out is not None:
                    os.environ["GRAPHIFY_MAX_OUTPUT_TOKENS"] = _prev_max_out
                if _prev_max_retries is None:
                    os.environ.pop("GRAPHIFY_MAX_RETRIES", None)
                elif not _prev_max_retries.strip():
                    os.environ["GRAPHIFY_MAX_RETRIES"] = _prev_max_retries
                if _lbl_extra:
                    _LBL_BACKENDS["ollama"]["extra_body"] = _prev_lbl_extra
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
    if code_only:
        # Re-stamp only the AST hash of code files. save_manifest(kind="ast")
        # preserves each file's existing semantic_hash (when its content is
        # unchanged) and seeds untouched entries from the current manifest, so a
        # code-only pass never drops already-extracted docs — no accidental full
        # re-extraction on the next semantic run.
        manifest_files = {ft: flist for ft, flist in files_by_type.items() if ft == "code"}
        _manifest_kind = "ast"
    else:
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
        _manifest_kind = "both"
    try:
        _save_manifest(manifest_files, manifest_path=str(manifest_path), kind=_manifest_kind, root=root)
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
