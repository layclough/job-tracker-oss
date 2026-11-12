import os
from pathlib import Path
from typing import Iterator

import anthropic
from openai import OpenAI

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

# Maximum characters of JD text sent to any LLM to prevent runaway token costs
MAX_JD_CHARS = 30000

# Claude models think before answering and thinking counts toward max_tokens,
# so the Anthropic path uses a fixed generous ceiling instead of the caller's value.
ANTHROPIC_MAX_TOKENS = 16000

PROVIDERS = {
    "lm_studio": {
        "label": "Local (LM Studio)",
        "short_label": "LM Studio (Local)",
        "default_base_url": "http://127.0.0.1:1234/v1",
        "default_model": "google/gemma-4-31b",
        "requires_key": False,
        "env_key_name": "LM_STUDIO_API_KEY",
        "default_key": "lm-studio",
        "is_local": True,
        "model_suggestions": ["google/gemma-4-31b", "google/gemma-3-27b-it", "qwen2.5-14b-instruct"],
    },
    "ollama": {
        "label": "Local (Ollama)",
        "short_label": "Ollama (Local)",
        "default_base_url": "http://127.0.0.1:11434/v1",
        "default_model": "gemma4:31b",
        "requires_key": False,
        "env_key_name": "OLLAMA_API_KEY",
        "default_key": "ollama",
        "is_local": True,
        "model_suggestions": ["gemma4:31b", "gemma4:27b", "qwen3:32b"],
    },
    "gemini": {
        "label": "Google Gemini API",
        "short_label": "Google Gemini",
        "default_base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "default_model": "gemini-3.8-flash",
        "requires_key": True,
        "env_key_name": "GEMINI_API_KEY",
        "default_key": "",
        "is_local": False,
        "model_suggestions": ["gemini-3.8-flash", "gemini-3.1-pro-preview", "gemini-3.7-flash"],
    },
    "openai": {
        "label": "OpenAI API",
        "short_label": "OpenAI",
        "default_base_url": "https://api.openai.com/v1",
        "default_model": "gpt-5.4",
        "requires_key": True,
        "env_key_name": "OPENAI_API_KEY",
        "default_key": "",
        "is_local": False,
        "model_suggestions": ["gpt-5.4", "gpt-5.4-nano", "gpt-4.1", "o3"],
    },
    "anthropic": {
        "label": "Anthropic Claude API",
        "short_label": "Anthropic Claude",
        "default_base_url": "https://api.anthropic.com",
        "default_model": "claude-haiku-5-5",
        "requires_key": True,
        "env_key_name": "ANTHROPIC_API_KEY",
        "default_key": "",
        "is_local": False,
        "model_suggestions": ["claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"],
    },
    "custom": {
        "label": "Custom (OpenAI-Compatible)",
        "short_label": "Custom API",
        "default_base_url": "https://openrouter.ai/api/v1",
        "default_model": "anthropic/claude-sonnet-5-5",
        "requires_key": True,
        "env_key_name": "CUSTOM_LLM_API_KEY",
        "default_key": "",
        "is_local": False,
        "model_suggestions": ["anthropic/claude-sonnet-5-5", "anthropic/claude-opus-5-5", "google/gemini-3.8-flash"],
    },
}

# Automatically upgrade retired default model IDs if previously saved in .env
DEPRECATED_MODEL_MIGRATIONS = {
    "gemini-2.5-flash": "gemini-3.8-flash",
    "gemini-2.5-pro": "gemini-3.1-pro-preview",
    "gemini-2.5-flash-lite": "gemini-3.7-flash",
    "gpt-4o": "gpt-5.4",
    "gpt-4o-mini": "gpt-5.4-nano",
    "gemma3:27b": "gemma4:31b",
    "anthropic/claude-3.7-sonnet": "anthropic/claude-sonnet-5-5",
}


def _parse_env_file(env_path: Path = ENV_PATH) -> dict[str, str]:
    """Reads key-value pairs from the local .env file without exposing them to logs."""
    values: dict[str, str] = {}
    if not env_path.exists():
        return values

    try:
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip()
            if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                val = val[1:-1]
            values[key] = val
    except Exception:
        pass
    return values


def _write_env_file(updates: dict[str, str | None], env_path: Path = ENV_PATH) -> None:
    """Updates keys in .env and enforces 0600 (owner read/write only) permissions."""
    current = _parse_env_file(env_path)
    for k, v in updates.items():
        if v is None:
            current.pop(k, None)
            os.environ.pop(k, None)
        else:
            current[k] = v
            os.environ[k] = v

    lines = [
        "# Local AI Model & API Configuration (Git-Ignored - Do Not Commit)",
    ]
    for k, v in current.items():
        safe_val = str(v).replace("\n", "").replace("\r", "")
        lines.append(f'{k}="{safe_val}"')

    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        os.chmod(env_path, 0o600)
    except Exception:
        pass


def load_llm_settings() -> dict:
    """Loads active LLM configuration from .env (seeding .env with defaults if it does not exist yet)."""
    if not ENV_PATH.exists():
        _write_env_file({
            "LLM_PROVIDER": "lm_studio",
            "LLM_MODEL": PROVIDERS["lm_studio"]["default_model"],
            "LLM_BASE_URL": PROVIDERS["lm_studio"]["default_base_url"],
            "GEMINI_API_KEY": "",
            "OPENAI_API_KEY": "",
            "CUSTOM_LLM_API_KEY": "",
        })
    env_vals = _parse_env_file()

    provider_id = env_vals.get("LLM_PROVIDER") or os.environ.get("LLM_PROVIDER") or "lm_studio"
    if provider_id not in PROVIDERS:
        provider_id = "lm_studio"

    preset = PROVIDERS[provider_id]
    raw_model = (
        env_vals.get(f"LLM_MODEL_{provider_id.upper()}")
        or env_vals.get("LLM_MODEL")
        or os.environ.get("LLM_MODEL")
        or preset["default_model"]
    ).strip()
    model = DEPRECATED_MODEL_MIGRATIONS.get(raw_model, raw_model)
    base_url = (
        env_vals.get(f"LLM_BASE_URL_{provider_id.upper()}")
        or env_vals.get("LLM_BASE_URL")
        or os.environ.get("LLM_BASE_URL")
        or preset["default_base_url"]
    )

    key_name = preset["env_key_name"]
    api_key = env_vals.get(key_name) or os.environ.get(key_name) or preset["default_key"]

    return {
        "provider": provider_id,
        "provider_label": preset["label"],
        "short_label": preset["short_label"],
        "is_local": preset["is_local"],
        "requires_key": preset["requires_key"],
        "model": model,
        "base_url": base_url.strip(),
        "api_key": api_key.strip(),
        "env_key_name": key_name,
    }


def get_provider_saved_settings(provider_id: str) -> dict:
    """Returns saved model, base_url, and whether an API key exists for a given provider."""
    if provider_id not in PROVIDERS:
        provider_id = "lm_studio"
    preset = PROVIDERS[provider_id]
    env_vals = _parse_env_file()

    raw_model = (env_vals.get(f"LLM_MODEL_{provider_id.upper()}") or preset["default_model"]).strip()
    model = DEPRECATED_MODEL_MIGRATIONS.get(raw_model, raw_model)
    base_url = env_vals.get(f"LLM_BASE_URL_{provider_id.upper()}") or preset["default_base_url"]
    key_name = preset["env_key_name"]
    saved_key = env_vals.get(key_name) or os.environ.get(key_name) or ""

    return {
        "model": model,
        "base_url": base_url,
        "has_key": bool(saved_key and saved_key != preset["default_key"]),
        "masked_key": mask_api_key(saved_key) if saved_key else "",
    }


def save_llm_settings(
    provider_id: str,
    model: str,
    base_url: str,
    new_api_key: str | None = None,
    clear_key: bool = False,
) -> None:
    """Persists LLM configuration to git-ignored .env with 0600 file permissions."""
    if provider_id not in PROVIDERS:
        provider_id = "lm_studio"
    preset = PROVIDERS[provider_id]

    clean_model = model.strip() or preset["default_model"]
    clean_url = base_url.strip() or preset["default_base_url"]

    updates: dict[str, str | None] = {
        "LLM_PROVIDER": provider_id,
        "LLM_MODEL": clean_model,
        "LLM_BASE_URL": clean_url,
        f"LLM_MODEL_{provider_id.upper()}": clean_model,
        f"LLM_BASE_URL_{provider_id.upper()}": clean_url,
    }

    key_name = preset["env_key_name"]
    if clear_key:
        updates[key_name] = None
    elif new_api_key is not None and new_api_key.strip():
        updates[key_name] = new_api_key.strip()

    _write_env_file(updates)


def mask_api_key(key: str) -> str:
    """Masks an API key for safe display in the UI (never exposes full secret)."""
    if not key:
        return ""
    k = key.strip()
    if len(k) <= 8:
        return "•" * len(k)
    return f"{k[:4]}{'•' * 8}{k[-4:]}"


def _require_api_key(cfg: dict) -> None:
    """Raises ValueError when the active provider needs an API key and none is configured."""
    if cfg["requires_key"] and not cfg["api_key"]:
        raise ValueError(
            f"Missing API Key for {cfg['provider_label']}. Please click 'Settings' in the sidebar to configure your key."
        )


def get_llm_client_and_model(timeout: float = 120.0) -> tuple[OpenAI, str]:
    """Returns an initialized OpenAI-compatible client and target model name based on active settings."""
    cfg = load_llm_settings()
    if cfg["provider"] == "anthropic":
        raise ValueError(
            "The Anthropic provider does not use an OpenAI-compatible client. Use complete_chat or stream_chat."
        )
    _require_api_key(cfg)

    client = OpenAI(
        base_url=cfg["base_url"],
        api_key=cfg["api_key"] or "not-needed",
        timeout=timeout,
    )
    return client, cfg["model"]


def _anthropic_client(cfg: dict, timeout: float) -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=cfg["api_key"], base_url=cfg["base_url"], timeout=timeout)


def _text_from_blocks(content) -> str:
    """Concatenates the text blocks of an Anthropic response, ignoring thinking blocks."""
    return "".join(block.text for block in content if block.type == "text")


def complete_chat(system: str, user: str, *, max_tokens: int, temperature: float, timeout: float = 120.0) -> str:
    """Runs one non-streaming completion on the active provider and returns the reply text."""
    cfg = load_llm_settings()
    _require_api_key(cfg)

    if cfg["provider"] == "anthropic":
        client = _anthropic_client(cfg, timeout)
        response = client.messages.create(
            model=cfg["model"],
            max_tokens=ANTHROPIC_MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        if response.stop_reason == "refusal":
            raise RuntimeError("The model declined this request.")
        return _text_from_blocks(response.content)

    client, model_name = get_llm_client_and_model(timeout=timeout)
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content


def stream_chat(
    system: str, user: str, *, max_tokens: int, temperature: float, timeout: float = 120.0
) -> Iterator[tuple[str, str]]:
    """Streams a completion on the active provider, yielding ("reasoning" | "content", text) pieces."""
    cfg = load_llm_settings()
    _require_api_key(cfg)

    if cfg["provider"] == "anthropic":
        client = _anthropic_client(cfg, timeout)
        with client.messages.stream(
            model=cfg["model"],
            max_tokens=ANTHROPIC_MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user}],
        ) as stream:
            for event in stream:
                if event.type == "content_block_delta":
                    if event.delta.type == "thinking_delta" and event.delta.thinking:
                        yield ("reasoning", event.delta.thinking)
                    elif event.delta.type == "text_delta" and event.delta.text:
                        yield ("content", event.delta.text)
            if stream.get_final_message().stop_reason == "refusal":
                raise RuntimeError("The model declined this request.")
        return

    client, model_name = get_llm_client_and_model(timeout=timeout)
    stream = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
    )
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        r_piece = getattr(delta, "reasoning_content", None)
        if r_piece:
            yield ("reasoning", r_piece)
        piece = getattr(delta, "content", None)
        if piece:
            yield ("content", piece)


def test_llm_connection(provider_id: str, model: str, base_url: str, api_key_override: str = "") -> tuple[bool, str]:
    """Tests connectivity and credentials against the selected LLM endpoint with a minimal request."""
    if provider_id not in PROVIDERS:
        return False, "Invalid provider selected."

    preset = PROVIDERS[provider_id]
    env_vals = _parse_env_file()
    key_name = preset["env_key_name"]
    effective_key = (
        api_key_override.strip()
        or env_vals.get(key_name)
        or os.environ.get(key_name)
        or preset["default_key"]
    )

    if preset["requires_key"] and not effective_key:
        return False, f"Please enter a valid API key for {preset['label']}."

    try:
        if provider_id == "anthropic":
            a_client = anthropic.Anthropic(
                api_key=effective_key,
                base_url=base_url.strip() or preset["default_base_url"],
                timeout=20.0,
            )
            a_resp = a_client.messages.create(
                model=model.strip() or preset["default_model"],
                max_tokens=1024,
                messages=[{"role": "user", "content": "Reply with OK"}],
            )
            a_reply = _text_from_blocks(a_resp.content).strip()
            return True, f"Connected to {model} ({a_reply or 'OK'})"

        client = OpenAI(
            base_url=base_url.strip() or preset["default_base_url"],
            api_key=effective_key or "not-needed",
            timeout=20.0,
        )
        resp = client.chat.completions.create(
            model=model.strip() or preset["default_model"],
            messages=[{"role": "user", "content": "Reply with OK"}],
            max_tokens=64,
        )
        reply = (resp.choices[0].message.content or "").strip()
        return True, f"Connected to {model} ({reply or 'OK'})"
    except Exception as exc:
        err_msg = str(exc)
        # Never echo any key material in error messages
        if effective_key and len(effective_key) > 4:
            err_msg = err_msg.replace(effective_key, "***")
        return False, f"Connection failed: {err_msg}"

