"""CLI entry point: python -m opengraphify [options] [path]"""
from __future__ import annotations

import argparse
import atexit
import json
import os
import sys
from pathlib import Path


def _arm_hang_watchdog() -> None:
    """Opt-in stack dumper for diagnosing a stuck run.

    Set OPENGRAPHIFY_DEBUG_HANG=1 (or to a number of seconds) and, if any phase
    blocks longer than that window, faulthandler prints the full traceback of
    every thread to stderr — repeatedly — so a hang shows exactly which frame is
    stuck (e.g. a blocking HTTP read against the Ollama backend) instead of a
    silent frozen cursor. No effect unless the env var is set.
    """
    raw = os.environ.get("OPENGRAPHIFY_DEBUG_HANG", "").strip()
    if not raw or raw.lower() in ("0", "false", "no"):
        return
    try:
        secs = float(raw) if raw.lower() not in ("1", "true", "yes") else 120.0
    except ValueError:
        secs = 120.0
    import faulthandler
    faulthandler.dump_traceback_later(secs, repeat=True, file=sys.stderr)
    print(
        f"[opengraphify] hang watchdog armed: dumping stacks every {secs:g}s "
        "while a phase is blocked (OPENGRAPHIFY_DEBUG_HANG)",
        file=sys.stderr,
    )


def _fast_exit(code: int = 0) -> None:
    """Flush output, run atexit handlers, then hard-exit the process.

    A one-shot run writes every artifact (graph.json/html, manifest, caches) to
    disk synchronously inside run(), so once it returns there is nothing left to
    do. Returning through the interpreter's normal shutdown, however, can stall
    for minutes: an unclosed openai/httpx client keeps a keep-alive socket to the
    (often remote) Ollama backend, and finalizing it at teardown is what leaves
    the cursor hanging after "done". We run atexit handlers explicitly first so
    graphify's stat-index cache is still flushed (keeps next run's change
    detection fast), then os._exit past the teardown phase entirely.

    Escape hatch: OPENGRAPHIFY_NO_FAST_EXIT=1 restores the normal sys.exit path.
    """
    if os.environ.get("OPENGRAPHIFY_NO_FAST_EXIT", "").strip() in ("1", "true", "yes"):
        sys.exit(code)
    try:
        sys.stdout.flush()
        sys.stderr.flush()
        atexit._run_exitfuncs()
    except Exception:
        pass
    os._exit(code)


def _status(root: Path, config) -> None:
    graphify_out = root / config.out_dir
    manifest_path = graphify_out / "manifest.json"
    graph_json_path = graphify_out / "graph.json"
    analysis_path = graphify_out / ".graphify_analysis.json"

    print(f"[opengraphify] status for {root}")
    print(f"  backend : {config.provider} / {config.model}")
    print(f"  base_url: {config.base_url}")
    print(f"  out_dir : {graphify_out}")

    if not graph_json_path.exists():
        print("  graph   : not built yet")
    else:
        try:
            data = json.loads(graph_json_path.read_text(encoding="utf-8"))
            n_nodes = len(data.get("nodes", []))
            links_key = "links" if "links" in data else "edges"
            n_edges = len(data.get(links_key, []))
            mtime = graph_json_path.stat().st_mtime
            from datetime import datetime
            mtime_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
            print(f"  graph   : {n_nodes} nodes, {n_edges} edges (last update: {mtime_str})")
        except Exception:
            print(f"  graph   : exists at {graph_json_path}")

    if analysis_path.exists():
        try:
            analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
            communities = analysis.get("communities", {})
            print(f"  communities: {len(communities)}")
        except Exception:
            pass

    if not manifest_path.exists():
        print("  manifest: not found — next run will do a full extraction")
    else:
        # Show changed-file count without touching LLM
        try:
            from graphify.detect import detect_incremental as _detect_inc
            detection = _detect_inc(root, manifest_path=str(manifest_path))
            new_by_type = detection.get("new_files", {})
            changed = sum(len(v) for v in new_by_type.values())
            deleted = len(detection.get("deleted_files", []))
            unchanged = sum(len(v) for v in detection.get("unchanged_files", {}).values())
            print(f"  changes : {changed} changed, {deleted} deleted, {unchanged} unchanged")
        except Exception as exc:
            print(f"  manifest: exists ({exc})")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="opengraphify",
        description="Update a graphify knowledge graph using a local/cheap LLM backend.",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Root directory to scan (default: current directory)",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Run in daemon mode, updating the graph every --interval minutes",
    )
    parser.add_argument(
        "--interval",
        type=int,
        metavar="MINUTES",
        help="Polling interval in minutes for --watch mode (overrides config)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force full re-extraction, ignoring the manifest cache",
    )
    parser.add_argument(
        "--max",
        type=int,
        metavar="N",
        dest="max_files",
        help="Process at most N uncached semantic files this run, then stop. "
        "Lets you chip away at a large repo in bounded batches (each run caches "
        "its progress, so the next run resumes where this one left off).",
    )
    parser.add_argument(
        "--code-only",
        action="store_true",
        dest="code_only",
        help="Only extract code (AST) — skip the semantic step entirely: no LLM / "
        "Ollama calls, fast and offline. Preserves any already-extracted semantic "
        "data in the manifest. Combine with --watch to keep the code graph fresh "
        "continuously without heat or tokens.",
    )
    parser.add_argument(
        "--code-only-1",
        action="store_true",
        dest="code_only_1",
        help="Like --code-only (no semantic inference), but still runs the final "
        "LLM pass that names the clusters (~1 call per 100 communities). "
        "'code-only minus 1': offline extraction, one cheap labeling burst at the end.",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show graph status (node/edge count, pending changes) and exit",
    )
    parser.add_argument(
        "--config",
        metavar="FILE",
        help="Path to an opengraphify.toml config file",
    )
    parser.add_argument(
        "--backend",
        metavar="PROVIDER",
        help="Backend provider override (e.g. ollama, openrouter)",
    )
    parser.add_argument(
        "--model",
        metavar="MODEL",
        help="Model name override (e.g. qwen2.5-coder:3b)",
    )
    parser.add_argument(
        "--base-url",
        metavar="URL",
        help="API base URL override (e.g. http://localhost:11434/v1)",
    )

    args = parser.parse_args()
    root = Path(args.path).resolve()

    if not root.exists():
        print(f"error: path does not exist: {root}", file=sys.stderr)
        sys.exit(1)

    # Load config — before any graphify imports so env vars are ready
    from opengraphify.config import load_config
    config = load_config(root, getattr(args, "config", None))

    # Apply CLI overrides
    if args.backend:
        config.provider = args.backend
    if args.model:
        config.model = args.model
    if getattr(args, "base_url", None):
        config.base_url = args.base_url
    if args.interval is not None:
        config.interval_minutes = args.interval

    # Set env vars so graphify.llm reads the right backend on first import
    config.apply_env()

    if args.status:
        _status(root, config)
        return

    _arm_hang_watchdog()

    # --code-only and --code-only-1 both skip semantic inference; --code-only-1
    # additionally keeps the LLM cluster-labeling pass at the end.
    _code_only = args.code_only or args.code_only_1
    _label_clusters = (not _code_only) or args.code_only_1

    if args.watch:
        from opengraphify.scheduler import watch
        watch(
            root, config, force_first=args.force,
            code_only=_code_only, label_clusters=_label_clusters,
        )
    else:
        from opengraphify.runner import run
        run(
            root, config, force=args.force, max_files=args.max_files,
            code_only=_code_only, label_clusters=_label_clusters,
        )
        # All outputs are on disk; skip the slow interpreter teardown that
        # otherwise hangs on a lingering keep-alive socket to Ollama.
        _fast_exit(0)


if __name__ == "__main__":
    main()
