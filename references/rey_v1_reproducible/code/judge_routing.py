"""
Judge routing — which judge models to call for each (case, prompt) combination.

UPDATED for the May 25 Meta deliverable (Wednesday 2pm PT):

  MUTs (Models Under Test):
    - claude-opus-4-7    (strongest Anthropic)
    - gpt-5.5            (strongest OpenAI)

  Judges (3-judge stack — cross-provider, mostly lighter-tier):
    - claude-sonnet-4-6     (primary, all families)
    - gpt-5.4-mini          (cross-provider, cheap)
    - gemini-3.5-flash      (cross-provider, "stable + most intelligent flash")

  Long cells: keep all 3 judges (Gemini and GPT-mini can both handle 128K+
  via their respective long-context paths; long cells that exceed ~200K still
  may overflow GPT-mini — handle per-case at run time, not via routing).

Returned judge names map to client calls in code/judge.py.
"""

from __future__ import annotations

from typing import Iterable


# Prompt families (matches JUDGE_PROMPTS.md and criteria.py)
STRUCTURE_PROMPTS = {"S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9", "S10"}
CONTENT_EXTRACTIVE_PROMPTS = {"C1", "C5", "C6", "C8"}
CONTENT_GENERATIVE_PROMPTS = {"C2", "C3", "C4", "C7"}
PREDICTION_PROMPTS = {"P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8", "P9", "P10"}
AE_PROMPTS = {"AE1", "AE2", "AE3"}


# Model identifiers
# MUTs
OPUS = "claude-opus-4-7"
GPT5_5 = "gpt-5.5"

# Judges
SONNET = "claude-sonnet-4-6"
GPT_MINI = "gpt-5.4-mini"
GEMINI_FLASH = "gemini-3.5-flash"

# Legacy / fallbacks (kept for backward compatibility)
SONNET_1M = "claude-sonnet-4-6"
GPT_FULL = "gpt-5.4"
HAIKU = "claude-haiku-4-5"


# The default MUT and judge stacks for the Wednesday run
DEFAULT_MUTS = [OPUS, GPT5_5]
DEFAULT_JUDGES = [SONNET, GPT_MINI, GEMINI_FLASH]


def family_for(prompt_id: str) -> str:
    if prompt_id in STRUCTURE_PROMPTS:
        return "structure"
    if prompt_id in CONTENT_EXTRACTIVE_PROMPTS:
        return "content_extractive"
    if prompt_id in CONTENT_GENERATIVE_PROMPTS:
        return "content_generative"
    if prompt_id in PREDICTION_PROMPTS:
        return "prediction"
    if prompt_id in AE_PROMPTS:
        return "adverse_event"
    raise ValueError(f"Unknown prompt {prompt_id}")


def judges_for(prompt_id: str, los_bucket: str) -> list[str]:
    """Return the list of judge identifiers to call for this (prompt, cell).

    Current policy: all 3 judges (Sonnet 4.6 + GPT-5.4-mini + Gemini 3.5 Flash)
    on every (prompt, cell). The runner may downgrade per-case if the rendered
    context exceeds GPT-mini's 128K window — that's a runtime decision, not a
    routing decision.

    `prompt_id` and `los_bucket` are kept in the signature for backward
    compatibility but are not currently used to differentiate routing.
    """
    return list(DEFAULT_JUDGES)


def models_under_test() -> list[str]:
    """The list of MUTs to evaluate every (case, prompt) against."""
    return list(DEFAULT_MUTS)


def model_under_test_for(los_bucket: str) -> str:
    """Legacy single-MUT selector. Returns Opus 4.7 (primary MUT).

    Use models_under_test() for the full pair.
    """
    return OPUS


def cell_uses_gpt(los_bucket: str) -> bool:
    """Quick check used by the runner. With the new 3-judge stack, GPT is always
    in the mix so this returns True. Kept for backward compatibility.
    """
    return True


def summarize_policy() -> str:
    """Human-readable summary for logging / docs."""
    lines = [
        "Judge routing policy (Wednesday-deliverable build):",
        "",
        f"  MUTs (run twice, once per model):",
        f"    1. {OPUS}",
        f"    2. {GPT5_5}",
        "",
        f"  Judges (run on each MUT response, all 3 always):",
        f"    1. {SONNET}",
        f"    2. {GPT_MINI}",
        f"    3. {GEMINI_FLASH}",
        "",
        "Per (case, prompt) we make 2 MUT calls and 2 * (3 judges * N criteria) judge calls.",
    ]
    return "\n".join(lines)


def assert_routing_consistent(cells: Iterable[tuple[str, str]]) -> None:
    """Sanity check: every (tier, los_bucket) returns at least one judge."""
    for tier, los in cells:
        for pid in ("S1", "C2", "P3", "AE1"):
            try:
                judges = judges_for(pid, los)
            except ValueError:
                continue
            assert judges, f"No judges for ({tier}, {los}, {pid})"
    assert models_under_test(), "No MUTs configured"


if __name__ == "__main__":
    print(summarize_policy())
    print()
    print("Example routing decisions:")
    examples = [
        ("S1", "short"),
        ("C2", "medium"),
        ("P3", "long"),
        ("AE1", "short"),
        ("P7", "long"),
    ]
    for pid, los in examples:
        print(f"  prompt={pid:5s} los={los:6s} → judges = {judges_for(pid, los)}")
    print(f"\nMUTs: {models_under_test()}")
