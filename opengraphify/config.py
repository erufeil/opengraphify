from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            tomllib = None  # type: ignore[assignment]


@dataclass
class Config:
    provider: str = "ollama"
    model: str = "qwen2.5-coder:3b"
    base_url: str = "http://localhost:11434/v1"
    api_key: str = ""
    interval_minutes: int = 15
    out_dir: str = "graphify-out"
    generate_html: bool = True
    generate_report: bool = True
    # Tokens packed per semantic-extraction chunk. graphify's own default is
    # 60k, tuned for large hosted models (Claude). Small local models choke on
    # chunks that big: Ollama auto-sizes num_ctx to match, and generation over a
    # huge context window is so slow it exceeds the request timeout (and pins the
    # CPU for hours, overheating the machine). 4k input + a small output cap
    # keeps num_ctx near its 8k floor — fast per chunk and cool. Raise it if you
    # run a larger/faster model or have a real GPU.
    token_budget: int = 4000
    # Hard cap on tokens the model may generate per chunk. graphify reserves this
    # in Ollama's num_ctx, so a big value inflates the context window (and the
    # work per chunk) even when the input is small. 2k is plenty for one chunk's
    # JSON and keeps num_ctx at the floor. Exported as GRAPHIFY_MAX_OUTPUT_TOKENS.
    max_output_tokens: int = 2048
    # When a chunk yields no nodes/edges (a small model rambling, or a genuinely
    # content-less file), graphify treats it as a truncation and recursively
    # bisects+retries — up to 2**max_retry_depth calls per chunk. graphify's
    # default is 3 (8×), which on trivial files (e.g. .github/*) becomes a retry
    # storm that wastes time and heats the CPU. 1 caps it at one split.
    max_retry_depth: int = 1
    # Force the model to emit valid JSON (Ollama `response_format=json_object`).
    # Small local models otherwise reply in prose ("The provided content appears
    # to be...") which graphify can't parse. When on, opengraphify also pins a
    # fixed num_ctx (token_budget + max_output_tokens + headroom) for the
    # extraction call. Set false to fall back to graphify's auto num_ctx.
    force_json: bool = True

    def apply_env(self) -> None:
        """Set env vars consumed by graphify.llm BEFORE those modules are imported.

        graphify.llm reads OLLAMA_BASE_URL / OLLAMA_MODEL at module-import time
        to populate its BACKENDS dict. We also patch BACKENDS at runtime in
        runner.py, but setting env vars here covers any secondary import path.
        """
        os.environ["OLLAMA_BASE_URL"] = self.base_url
        os.environ["OLLAMA_MODEL"] = self.model
        # Ollama ignores auth; graphify warns if the var is unset, so set a
        # non-empty placeholder unless the user already provided a real key.
        key = self.api_key or os.environ.get("OPENGRAPHIFY_API_KEY", "") or "opengraphify"
        os.environ["OLLAMA_API_KEY"] = key
        # Cap the model's per-chunk output. graphify reads GRAPHIFY_MAX_OUTPUT_TOKENS
        # directly; setdefault so an explicit env var from the user always wins.
        os.environ.setdefault("GRAPHIFY_MAX_OUTPUT_TOKENS", str(self.max_output_tokens))

    def graphify_backend(self) -> str:
        """Return the graphify backend name. All providers use the ollama slot."""
        return "ollama"


def load_config(root: Path, config_path: str | None = None) -> Config:
    """Load config from a toml file, then apply env overrides.

    If config_path is given (CLI --config), only that file is read. Otherwise the
    first existing file in this search order wins:
      1. <root>/opengraphify.toml          (the repo being scanned)
      2. <cwd>/opengraphify.toml           (current working directory)
      3. ~/.opengraphify/config.toml       (user global)

    The chosen file (or "defaults") is printed so it's obvious which config is
    actually in effect — a frequent source of "it's ignoring my toml" confusion
    when the toml lives somewhere outside this search path.
    """
    config = Config()

    if config_path:
        candidates = [Path(config_path)]
    else:
        candidates = [
            root / "opengraphify.toml",
            Path.cwd() / "opengraphify.toml",
            Path.home() / ".opengraphify" / "config.toml",
        ]

    data: dict = {}
    loaded_from: Path | None = None
    for path in candidates:
        if path.exists():
            if tomllib is None:
                print(
                    f"[opengraphify] WARNING: tomllib unavailable, cannot read {path}. "
                    "Run: pip install tomli",
                    file=sys.stderr,
                )
                break
            try:
                with open(path, "rb") as fh:
                    data = tomllib.load(fh)
                loaded_from = path
                break
            except Exception as exc:
                print(f"[opengraphify] WARNING: could not read {path}: {exc}", file=sys.stderr)

    if config_path and loaded_from is None:
        print(
            f"[opengraphify] WARNING: --config {config_path} not found; using defaults + env",
            file=sys.stderr,
        )
    if loaded_from is not None:
        print(f"[opengraphify] config: {loaded_from}")
    else:
        print("[opengraphify] config: defaults (no opengraphify.toml found in search path)")

    backend = data.get("backend", {})
    config.provider = os.environ.get("OPENGRAPHIFY_PROVIDER", backend.get("provider", config.provider))
    config.model = os.environ.get("OPENGRAPHIFY_MODEL", backend.get("model", config.model))
    config.base_url = os.environ.get("OPENGRAPHIFY_BASE_URL", backend.get("base_url", config.base_url))
    config.api_key = os.environ.get("OPENGRAPHIFY_API_KEY", backend.get("api_key", config.api_key))

    schedule = data.get("schedule", {})
    try:
        config.interval_minutes = int(
            os.environ.get("OPENGRAPHIFY_INTERVAL", schedule.get("interval_minutes", config.interval_minutes))
        )
    except (ValueError, TypeError):
        pass

    output = data.get("output", {})
    config.out_dir = output.get("out_dir", config.out_dir)
    config.generate_html = bool(output.get("generate_html", config.generate_html))
    config.generate_report = bool(output.get("generate_report", config.generate_report))

    extraction = data.get("extraction", {})
    try:
        config.token_budget = int(
            os.environ.get(
                "OPENGRAPHIFY_TOKEN_BUDGET",
                extraction.get("token_budget", config.token_budget),
            )
        )
    except (ValueError, TypeError):
        pass
    try:
        config.max_output_tokens = int(
            os.environ.get(
                "GRAPHIFY_MAX_OUTPUT_TOKENS",
                extraction.get("max_output_tokens", config.max_output_tokens),
            )
        )
    except (ValueError, TypeError):
        pass
    try:
        config.max_retry_depth = int(
            os.environ.get(
                "OPENGRAPHIFY_MAX_RETRY_DEPTH",
                extraction.get("max_retry_depth", config.max_retry_depth),
            )
        )
    except (ValueError, TypeError):
        pass
    _fj = os.environ.get("OPENGRAPHIFY_FORCE_JSON")
    if _fj is not None:
        config.force_json = _fj.strip().lower() not in ("0", "false", "no", "")
    else:
        config.force_json = bool(extraction.get("force_json", config.force_json))

    return config
