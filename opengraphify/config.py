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


def load_config(root: Path) -> Config:
    """Load config from the first opengraphify.toml found, then apply env overrides.

    Search order:
      1. <root>/opengraphify.toml          (repo-specific)
      2. <cwd>/opengraphify.toml           (working-directory)
      3. ~/.opengraphify/config.toml       (user global)
    """
    config = Config()

    candidates = [
        root / "opengraphify.toml",
        Path.cwd() / "opengraphify.toml",
        Path.home() / ".opengraphify" / "config.toml",
    ]

    data: dict = {}
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
                break
            except Exception as exc:
                print(f"[opengraphify] WARNING: could not read {path}: {exc}", file=sys.stderr)

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

    return config
