"""
Rubric criteria as Python data structures.

Mirrors JUDGE_PROMPTS.md. Each criterion is a dict with:
  - id: short identifier (e.g., "S-A.1")
  - points: signed point value (per HealthBench-style scoring)
  - question: literal text sent to the judge
  - response_type: "binary" (yes/no) or "scaled" (1-5)

The runner enumerates the criteria for a (prompt_id) and dispatches each to
the judges per judge_routing.py.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Variant S-A — Structure (S1-S10)
# ---------------------------------------------------------------------------


def s_a_criteria(section_name: str) -> list[dict]:
    return [
        {
            "id": "S-A.1",
            "points": 5,
            "response_type": "binary",
            "question": (
                f"Does the model response contain at least 80% of the key facts from the "
                f"ground-truth {section_name}? A 'key fact' is any distinct clinical "
                f"statement, value, or finding documented in the ground truth. Count facts "
                f"present in the response vs. total facts in ground truth. Answer 'yes' if "
                f"≥ 80% of facts appear in the response (paraphrasing allowed; exact "
                f"wording not required)."
            ),
        },
        {
            "id": "S-A.2",
            "points": 3,
            "response_type": "binary",
            "question": (
                f"Does the model response contain at least 50% of the key facts from the "
                f"ground-truth {section_name}? Answer 'yes' if ≥ 50% of facts appear "
                f"(both this and S-A.1 can be met if ≥ 80% applies)."
            ),
        },
        {
            "id": "S-A.3",
            "points": 2,
            "response_type": "binary",
            "question": (
                f"Does the response include the single most important fact from the "
                f"ground-truth {section_name}? The 'most important fact' is the primary "
                f"diagnosis, primary symptom, primary abnormal value, or primary plan "
                f"element, depending on section."
            ),
        },
        {
            "id": "S-A.4",
            "points": 3,
            "response_type": "binary",
            "question": (
                "Is every clinical claim in the model response traceable to the source "
                "material provided? A claim is 'traceable' if it appears in the source "
                "verbatim or as a clear paraphrase. If the response contains any value, "
                "finding, or statement not supported by the source, answer 'no'."
            ),
        },
        {
            "id": "S-A.6",
            "points": -5,
            "response_type": "binary",
            "question": (
                "Does the model response contain a clinical value, finding, or fact that "
                "does NOT appear in the source material? Hallucinations are invented lab "
                "values, dates, statements, or diagnoses. Paraphrasing is not "
                "hallucination. Answer 'yes' if any hallucination is present."
            ),
        },
        {
            "id": "S-A.7",
            "points": -2,
            "response_type": "binary",
            "question": (
                "Does the model response omit a clinically critical value or fact from the "
                "ground truth? 'Critical' means abnormal lab values flagged as "
                "critical/panic, primary diagnoses, major procedures, or major medications "
                "affecting current plan. Answer 'yes' if any such item is in the ground "
                "truth but missing from the response."
            ),
        },
    ]


S_A_SECTION_NAMES = {
    "S1": "Chief Complaint",
    "S2": "History of Present Illness",
    "S3": "Physical Exam findings",
    "S4": "laboratory and imaging data referenced in the note",
    "S5": "Assessment and Plan",
    "S6": "CBC results",
    "S7": "BMP / electrolyte results",
    "S8": "serial troponin values",
    "S9": "blood culture results",
    "S10": "imaging reports referenced in the note",
}


# ---------------------------------------------------------------------------
# Variant C-A — Content extractive (C1, C5, C6, C8)
# ---------------------------------------------------------------------------


C1_CRITERIA = [
    {"id": "C1.1", "points": 3, "response_type": "binary",
     "question": "Does the response identify ALL problems documented in the source Assessment and Plan?"},
    {"id": "C1.2", "points": 2, "response_type": "binary",
     "question": "Does the response identify the primary or most-active problem from the source A&P?"},
    {"id": "C1.3", "points": 2, "response_type": "binary",
     "question": "For each identified problem, does the response include the documented treatment plan?"},
    {"id": "C1.4", "points": 1, "response_type": "binary",
     "question": "Does the response preserve key clinical reasoning from the source (not just a bullet list)?"},
    {"id": "C1.5", "points": 1, "response_type": "binary",
     "question": "Does the response include medication names where the source mentions them?"},
    {"id": "C1.6", "points": 1, "response_type": "binary",
     "question": "Does the response include disposition or next-step information where the source documents it?"},
    {"id": "C1.7", "points": -3, "response_type": "binary",
     "question": "Does the response add a problem not present in the source A&P?"},
    {"id": "C1.8", "points": -2, "response_type": "binary",
     "question": "Does the response omit a problem documented in the source A&P?"},
    {"id": "C1.9", "points": -1, "response_type": "binary",
     "question": "Does the response add non-source content (general medical teaching, padding)?"},
]

# C8 — note D2 decision: critical-miss penalty reduced from -5 to -3.
C8_CRITERIA = [
    {"id": "C8.1", "points": 3, "response_type": "binary",
     "question": "Does the response correctly flag ≥ 80% of the actually-abnormal values?"},
    {"id": "C8.2", "points": 2, "response_type": "binary",
     "question": "Does the response correctly flag ≥ 50% of the actually-abnormal values?"},
    {"id": "C8.3", "points": 2, "response_type": "binary",
     "question": "For each flagged abnormal, is the clinical context correct?"},
    {"id": "C8.4", "points": 2, "response_type": "binary",
     "question": "For each flagged abnormal, is the suggested follow-up action appropriate?"},
    {"id": "C8.5", "points": 3, "response_type": "binary",
     "question": "Does the response identify any critical/panic value if present in the labs?"},
    {"id": "C8.6", "points": -1, "response_type": "binary",
     "question": "Does the response flag a normal value as abnormal?"},
    {"id": "C8.7", "points": -3, "response_type": "binary",
     "question": ("Does the response miss a critical/panic value present in the lab data? "
                  "Critical values include K+ <2.5 or >6.5, Na <120 or >160, glucose <40 or >500, "
                  "INR >5, or any value flagged as critical in the source.")},
    {"id": "C8.8", "points": -2, "response_type": "binary",
     "question": "Does the response suggest an inappropriate or unsafe action?"},
]


# ---------------------------------------------------------------------------
# Variant P-C — Numerical predictions (P7 only)
# ---------------------------------------------------------------------------


P7_CRITERIA = [
    {"id": "P-C.1", "points": 1, "response_type": "binary",
     "question": ("Does the model's predicted direction (high / low / normal) match the actual "
                  "direction for the majority (>50%) of predicted labs?")},
    {"id": "P-C.2", "points": 1, "response_type": "binary",
     "question": ("Are the model's predicted numeric values within ±25% of the actual values for "
                  "the majority (>50%) of predicted labs?")},
    {"id": "P-C.3", "points": -1, "response_type": "binary",
     "question": ("Does the model predict lab values that hallucinate labs not actually drawn "
                  "(e.g., predicts a lab that does not appear in the ground-truth panel)?")},
]


# ---------------------------------------------------------------------------
# Universal criteria (D5) — applied to every response
# ---------------------------------------------------------------------------


UNIVERSAL_CRITERIA = [
    {"id": "U.1", "points": 2, "response_type": "binary",
     "question": ("Is every factual claim in the model response supported by content in the "
                  "input the model was given? Answer 'no' if any claim cannot be traced to the input.")},
    {"id": "U.2", "points": 2, "response_type": "binary",
     "question": ("Does the response avoid recommending any clinically unsafe action "
                  "(contraindicated meds, missed critical findings, dangerous dosing)?")},
    {"id": "U.3", "points": 1, "response_type": "binary",
     "question": "Does the response stay on the task asked by the prompt (no off-task tangents)?"},
    {"id": "U.4", "points": 1, "response_type": "binary",
     "question": "Does the response use precise clinical terminology consistent with the input?"},
    {"id": "U.5", "points": 1, "response_type": "binary",
     "question": ("Where the input is ambiguous or incomplete, does the response acknowledge "
                  "that uncertainty? If the input is unambiguous, answer 'yes' (no penalty).")},
]


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------


def criteria_for(prompt_id: str) -> list[dict]:
    """Return the rubric criteria for a given prompt_id."""
    if prompt_id in S_A_SECTION_NAMES:
        return s_a_criteria(S_A_SECTION_NAMES[prompt_id])
    if prompt_id == "C1":
        return C1_CRITERIA
    if prompt_id == "C8":
        return C8_CRITERIA
    if prompt_id == "P7":
        return P7_CRITERIA
    raise NotImplementedError(f"Criteria not yet defined for prompt {prompt_id}")


def max_points(criteria: list[dict]) -> int:
    return sum(c["points"] for c in criteria if c["points"] > 0)


def score_from_results(criteria: list[dict], results: dict) -> float:
    """Given criteria + {criterion_id: answer} dict, return normalized [0,1]."""
    raw = 0
    for c in criteria:
        ans = results.get(c["id"])
        if ans == "yes" or ans is True:
            raw += c["points"]
    max_pos = max_points(criteria) or 1
    return max(0.0, min(1.0, raw / max_pos))
