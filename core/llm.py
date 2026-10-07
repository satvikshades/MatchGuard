"""Optional LLM add-on. Everything in MatchGuard works without it.

Provider is picked from the environment (.env is loaded if python-dotenv is installed):
  ANTHROPIC_API_KEY -> Claude (pip install anthropic)
  GEMINI_API_KEY    -> Gemini (pip install google-genai)
  MATCHGUARD_OFFLINE=1 forces offline mode even if a key is set.
SDKs are imported lazily so a missing package just means offline mode.
"""
from __future__ import annotations

import os
from typing import Callable, Optional

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # optional
    pass

ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-opus-5-5")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


class LLMError(RuntimeError):
    pass


def provider() -> Optional[str]:
    if os.getenv("MATCHGUARD_OFFLINE", "").strip() in ("1", "true", "yes"):
        return None
    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            import anthropic  # noqa: F401
            return "anthropic"
        except ImportError:
            pass
    if os.getenv("GEMINI_API_KEY"):
        try:
            from google import genai  # noqa: F401
            return "gemini"
        except ImportError:
            pass
    return None


def status_message() -> str:
    p = provider()
    if p == "anthropic":
        return f"LLM: Claude ({ANTHROPIC_MODEL})"
    if p == "gemini":
        return f"LLM: Gemini ({GEMINI_MODEL})"
    if os.getenv("ANTHROPIC_API_KEY") or os.getenv("GEMINI_API_KEY"):
        return "Running in offline mode (keyword tagger) - API key found but SDK not installed"
    return "Running in offline mode (keyword tagger)"


def _anthropic(system: str, user: str, schema: Optional[dict], max_tokens: int) -> str:
    import anthropic

    client = anthropic.Anthropic(timeout=60, max_retries=1)
    output_config: dict = {"effort": "low"}
    if schema:
        output_config["format"] = {"type": "json_schema", "schema": schema}
    try:
        resp = client.beta.messages.create(
            model=ANTHROPIC_MODEL, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": user}],
            betas=["server-side-fallback-2026-07-01"],
            extra_body={"output_config": output_config, "fallbacks": "default"},
        )
    except anthropic.APIError as e:
        raise LLMError(str(e)) from e
    if resp.stop_reason == "refusal":
        raise LLMError("model declined the request")
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    if not text:
        raise LLMError("empty response")
    return text


def _gemini(system: str, user: str, schema: Optional[dict], max_tokens: int) -> str:
    from google import genai

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    config = {"system_instruction": system, "max_output_tokens": max_tokens}
    if schema:
        config["response_mime_type"] = "application/json"
    try:
        resp = client.models.generate_content(model=GEMINI_MODEL, contents=user, config=config)
    except Exception as e:  # google-genai raises several error types
        raise LLMError(str(e)) from e
    if not resp.text:
        raise LLMError("empty response")
    return resp.text


def get_json_caller() -> Optional[Callable[[str, str, dict], str]]:
    """Returns fn(system, user, schema) -> raw JSON text, or None in offline mode."""
    p = provider()
    if p == "anthropic":
        return lambda s, u, schema: _anthropic(s, u, schema, 4000)
    if p == "gemini":
        return lambda s, u, schema: _gemini(s, u, schema, 2000)
    return None


def get_text_caller() -> Optional[Callable[[str, str], str]]:
    p = provider()
    if p == "anthropic":
        return lambda s, u: _anthropic(s, u, None, 4000)
    if p == "gemini":
        return lambda s, u: _gemini(s, u, None, 1000)
    return None


__all__ = ["provider", "status_message", "get_json_caller", "get_text_caller", "LLMError"]
