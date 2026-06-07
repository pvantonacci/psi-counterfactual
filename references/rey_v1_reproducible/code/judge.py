"""
LLM client wrappers for the Project Bayes evaluation pipeline.

Provides a uniform `call_llm(...)` interface over Anthropic, OpenAI, and
Google Gen AI (Gemini) APIs. Used by both the model-under-test runner and
the judge runner.

Requires environment variables:
  - ANTHROPIC_API_KEY
  - OPENAI_API_KEY
  - GOOGLE_API_KEY (or GEMINI_API_KEY — either works with the genai SDK)
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from typing import Optional

import anthropic
import openai
from google import genai as google_genai
from google.genai import types as google_genai_types


# Default API model identifiers. Override per-call if needed.
ANTHROPIC_MODEL_ALIASES = {
    "claude-sonnet-4-6": "claude-sonnet-4-6",
    "claude-sonnet-4-6[1m]": "claude-sonnet-4-6[1m]",
    "claude-haiku-4-5": "claude-haiku-4-5",
    "claude-opus-4-7": "claude-opus-4-7",
}

OPENAI_MODEL_ALIASES = {
    "gpt-5.4-mini": "gpt-5.4-mini",
    "gpt-5.4": "gpt-5.4",
    "gpt-5.5": "gpt-5.5",
}

GEMINI_MODEL_ALIASES = {
    "gemini-3.5-flash": "gemini-3.5-flash",
    "gemini-3-flash": "gemini-3-flash",
    "gemini-2.5-flash": "gemini-2.5-flash",
}

# Approximate USD per 1M tokens (input, output). Used for cost estimation only.
PRICING = {
    "claude-sonnet-4-6":      {"in": 3.00, "out": 15.00, "cache_hit": 0.30, "cache_write": 3.75},
    "claude-sonnet-4-6[1m]":  {"in": 3.00, "out": 15.00, "cache_hit": 0.30, "cache_write": 3.75},
    "claude-haiku-4-5":       {"in": 1.00, "out": 5.00,  "cache_hit": 0.10, "cache_write": 1.25},
    "claude-opus-4-7":        {"in": 5.00, "out": 25.00, "cache_hit": 0.50, "cache_write": 6.25},
    "gpt-5.4-mini":           {"in": 0.75, "out": 4.50,  "cache_hit": 0.075},
    "gpt-5.4":                {"in": 2.50, "out": 15.00, "cache_hit": 0.25},
    "gpt-5.5":                {"in": 5.00, "out": 30.00, "cache_hit": 0.50},
    # Gemini 3.5 Flash — estimated (refine with actual Google pricing)
    "gemini-3.5-flash":       {"in": 0.50, "out": 3.50,  "cache_hit": 0.05},
    "gemini-3-flash":         {"in": 0.40, "out": 2.50,  "cache_hit": 0.04},
    "gemini-2.5-flash":       {"in": 0.30, "out": 2.50,  "cache_hit": 0.03},
}


@dataclass
class LLMResponse:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    cached_tokens: int = 0
    cost_usd: float = 0.0
    raw: Optional[dict] = None


_anthropic_client: Optional[anthropic.Anthropic] = None
_openai_client: Optional[openai.OpenAI] = None
_gemini_client: Optional["google_genai.Client"] = None


# Per-request timeout (seconds). Without this, a single hung request can stall
# the runner for hours — observed a 9-hour hang in the pilot.
REQUEST_TIMEOUT = 180.0


def _get_anthropic() -> anthropic.Anthropic:
    global _anthropic_client
    if _anthropic_client is None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY not set in environment")
        _anthropic_client = anthropic.Anthropic(timeout=REQUEST_TIMEOUT)
    return _anthropic_client


def _get_openai() -> openai.OpenAI:
    global _openai_client
    if _openai_client is None:
        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY not set in environment")
        _openai_client = openai.OpenAI(timeout=REQUEST_TIMEOUT)
    return _openai_client


def _get_gemini() -> "google_genai.Client":
    global _gemini_client
    if _gemini_client is None:
        api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GOOGLE_API_KEY (or GEMINI_API_KEY) not set in environment")
        _gemini_client = google_genai.Client(api_key=api_key)
    return _gemini_client


def _estimate_cost(model: str, input_tokens: int, output_tokens: int, cached_tokens: int = 0) -> float:
    p = PRICING.get(model, {"in": 0, "out": 0, "cache_hit": 0})
    # Some providers (Gemini) return None for missing token counts
    input_tokens = input_tokens or 0
    output_tokens = output_tokens or 0
    cached_tokens = cached_tokens or 0
    non_cached_in = max(0, input_tokens - cached_tokens)
    return (
        non_cached_in * p["in"] / 1_000_000
        + cached_tokens * p.get("cache_hit", p["in"]) / 1_000_000
        + output_tokens * p["out"] / 1_000_000
    )


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------


def call_anthropic(
    model: str,
    system: str,
    user: str,
    max_tokens: int = 2048,
    temperature: float = 0.0,
) -> LLMResponse:
    client = _get_anthropic()
    api_model = ANTHROPIC_MODEL_ALIASES.get(model, model)
    last_err = None
    # Opus 4.7+ deprecates the temperature parameter; older Sonnet/Haiku models
    # still accept it.
    drops_temperature = model.startswith("claude-opus-4-7") or model.startswith("claude-opus-5")
    for attempt in range(3):
        try:
            kwargs: dict = dict(
                model=api_model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            if not drops_temperature:
                kwargs["temperature"] = temperature
            resp = client.messages.create(**kwargs)
            text = "".join(b.text for b in resp.content if hasattr(b, "text"))
            in_tok = resp.usage.input_tokens
            out_tok = resp.usage.output_tokens
            cached = getattr(resp.usage, "cache_read_input_tokens", 0) or 0
            cost = _estimate_cost(model, in_tok, out_tok, cached)
            return LLMResponse(
                text=text,
                model=model,
                input_tokens=in_tok,
                output_tokens=out_tok,
                cached_tokens=cached,
                cost_usd=cost,
            )
        except Exception as e:
            last_err = e
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Anthropic call failed after retries: {last_err}")


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------


def call_openai(
    model: str,
    system: str,
    user: str,
    max_tokens: int = 2048,
    temperature: float = 0.0,
) -> LLMResponse:
    client = _get_openai()
    api_model = OPENAI_MODEL_ALIASES.get(model, model)
    last_err = None
    # GPT-5.x models use 'max_completion_tokens' and don't accept 'temperature'
    is_gpt5x = model.startswith("gpt-5")
    for attempt in range(3):
        try:
            kwargs: dict = dict(
                model=api_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            if is_gpt5x:
                kwargs["max_completion_tokens"] = max_tokens
            else:
                kwargs["max_tokens"] = max_tokens
                kwargs["temperature"] = temperature
            resp = client.chat.completions.create(**kwargs)
            text = resp.choices[0].message.content or ""
            in_tok = resp.usage.prompt_tokens
            out_tok = resp.usage.completion_tokens
            cached = getattr(resp.usage, "prompt_tokens_details", None)
            cached_n = getattr(cached, "cached_tokens", 0) if cached else 0
            cost = _estimate_cost(model, in_tok, out_tok, cached_n)
            return LLMResponse(
                text=text,
                model=model,
                input_tokens=in_tok,
                output_tokens=out_tok,
                cached_tokens=cached_n,
                cost_usd=cost,
            )
        except Exception as e:
            last_err = e
            time.sleep(2 ** attempt)
    raise RuntimeError(f"OpenAI call failed after retries: {last_err}")


# ---------------------------------------------------------------------------
# Google Gemini
# ---------------------------------------------------------------------------


def call_gemini(
    model: str,
    system: str,
    user: str,
    max_tokens: int = 2048,
    temperature: float = 0.0,
) -> LLMResponse:
    client = _get_gemini()
    api_model = GEMINI_MODEL_ALIASES.get(model, model)
    last_err = None
    for attempt in range(3):
        try:
            config = google_genai_types.GenerateContentConfig(
                system_instruction=system,
                max_output_tokens=max_tokens,
                temperature=temperature,
                # Disable "thinking" tokens — Gemini 3.5 Flash uses internal
                # reasoning that counts against max_output_tokens. For judge
                # tasks (yes/no JSON output) we don't need it, and it can
                # eat the entire token budget on short responses.
                thinking_config=google_genai_types.ThinkingConfig(thinking_budget=0),
                # Disable safety filters that can refuse clinical content
                safety_settings=[
                    google_genai_types.SafetySetting(
                        category=cat,
                        threshold=google_genai_types.HarmBlockThreshold.BLOCK_NONE,
                    )
                    for cat in (
                        "HARM_CATEGORY_HARASSMENT",
                        "HARM_CATEGORY_HATE_SPEECH",
                        "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                        "HARM_CATEGORY_DANGEROUS_CONTENT",
                    )
                ],
            )
            resp = client.models.generate_content(
                model=api_model,
                contents=user,
                config=config,
            )
            text = resp.text or ""
            usage = getattr(resp, "usage_metadata", None)
            in_tok = getattr(usage, "prompt_token_count", 0) if usage else 0
            out_tok = getattr(usage, "candidates_token_count", 0) if usage else 0
            cached_n = getattr(usage, "cached_content_token_count", 0) if usage else 0
            cost = _estimate_cost(model, in_tok, out_tok, cached_n)
            return LLMResponse(
                text=text,
                model=model,
                input_tokens=in_tok,
                output_tokens=out_tok,
                cached_tokens=cached_n,
                cost_usd=cost,
            )
        except Exception as e:
            last_err = e
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Gemini call failed after retries: {last_err}")


# ---------------------------------------------------------------------------
# Unified entry point
# ---------------------------------------------------------------------------


def call_llm(
    model: str,
    system: str,
    user: str,
    max_tokens: int = 2048,
    temperature: float = 0.0,
) -> LLMResponse:
    """Route by model name prefix to the right provider."""
    if model.startswith("claude-"):
        return call_anthropic(model, system, user, max_tokens, temperature)
    if model.startswith("gpt-"):
        return call_openai(model, system, user, max_tokens, temperature)
    if model.startswith("gemini-"):
        return call_gemini(model, system, user, max_tokens, temperature)
    raise ValueError(f"Unknown model provider for: {model}")


# ---------------------------------------------------------------------------
# JSON response parsing (judges return structured output)
# ---------------------------------------------------------------------------


def parse_judge_json(text: str) -> dict:
    """Parse a judge response that should be JSON of the form
    {"answer": "yes"|"no" or int, "rationale": "..."}.

    Tolerates models that wrap JSON in backticks or include surrounding text.
    Returns {"answer": None, "rationale": "<parse error>"} on failure.

    Robust to incomplete JSON (when the model's response was truncated mid-rationale):
    finds `"answer": "yes"` or `"answer": "no"` patterns even without a closing brace.
    """
    if not text:
        return {"answer": None, "rationale": "empty response"}
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Strip code fences
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    # Fallback: extract just the answer field via regex (works on truncated/partial JSON).
    # Matches: "answer": "yes" / "answer":"no" / "answer" : "Yes" / 'answer': 'no' etc.
    answer_match = re.search(
        r"""['"]?\banswer\b['"]?\s*:\s*['"]?(yes|no|true|false|\d+)['"]?""",
        text,
        re.IGNORECASE,
    )
    if answer_match:
        # Also try to grab a rationale fragment if present (everything after "rationale": "...)
        rat_match = re.search(
            r"""['"]?\brationale\b['"]?\s*:\s*['"]?(.*?)(?:['"]?\s*[,}]|$)""",
            text,
            re.DOTALL | re.IGNORECASE,
        )
        rationale = rat_match.group(1).strip()[:400] if rat_match else "(parsed from partial JSON)"
        return {"answer": answer_match.group(1).lower(), "rationale": rationale}
    # Find first balanced JSON object
    match = re.search(r"\{[^{}]*\"answer\"[^{}]*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return {"answer": None, "rationale": f"could not parse: {text[:120]}"}


if __name__ == "__main__":
    # Tiny health check
    print("Anthropic test:")
    resp = call_llm(
        "claude-sonnet-4-6",
        system="You are a terse assistant. Respond with exactly: PONG",
        user="ping",
        max_tokens=20,
    )
    print(f"  response: {resp.text!r}")
    print(f"  tokens: in={resp.input_tokens}, out={resp.output_tokens}, cost=${resp.cost_usd:.6f}")

    print("\nOpenAI test:")
    resp = call_llm(
        "gpt-5.4-mini",
        system="You are a terse assistant. Respond with exactly: PONG",
        user="ping",
        max_tokens=20,
    )
    print(f"  response: {resp.text!r}")
    print(f"  tokens: in={resp.input_tokens}, out={resp.output_tokens}, cost=${resp.cost_usd:.6f}")
