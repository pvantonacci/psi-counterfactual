"""
Rubric criteria — v3 (structural rewrite for objectivity).

Substantially rewritten from v1. Goal: every criterion should be answerable by
a non-expert judge given only the source material and response text, with
minimal room for evaluative judgment.

== Rewritten criteria (same IDs and weights as v1, improved language) ==

  S-A.3  (+2)  "most important fact" → first-listed or primary-labeled item (rule-based).

  C1.4   (+1)  "preserves key clinical reasoning" → causal-connective check:
               does the response include at least one causal connective ('due to',
               'secondary to', etc.) that also appears in the source A&P?

  U.4    (+1)  "precise terminology" → same-abbreviations-as-source rule.

  C8.3   (+2)  "clinical context correct" → direction (H/L) accuracy check,
               deterministic from LB_ABN_RESULT flags.

  C8.4   (+2)  "appropriate follow-up" → named-action requirement; vague phrases
               ('monitor closely') explicitly excluded.

  C8.8   (-2)  "inappropriate or unsafe" → source-contradiction checklist only.

  U.2    (+2)  "clinically unsafe" → same contradiction checklist as C8.8
               (prompt-agnostic version).

  U.5    (+1)  Added explicit auto-pass trigger; 'no' only when input has an
               explicitly flagged gap the response ignores.

== Structural changes ==

  S-A.1/2     Explicit enumeration scaffold: judges list facts and mark P/A before
              calculating the percentage, rather than estimating holistically.

  C1.2        "primary or most-active" → first-listed or primary-labeled (rule-based).

  All recall  Paraphrase rule added: same clinical entity, no change to magnitude,
              direction, or anatomic location.

  S-A.4/U.1  Severity-upgrade examples added: applying a standard clinical label to
              a numeric value is supported; upgrading a flag (L → 'critically low')
              is not.

  C1.1/C1.8  Multi-diagnosis tie-breaker: items like 'Sepsis / bacteremia' count as
              two separate problems.

  C1.7        "active medical issue" → "presented as part of current assessment or
              plan"; PMH background mentions explicitly excluded.

  C8.5        "significantly abnormal" removed; only critical/panic-range qualifies.

  U.3         25% threshold replaced with specific disqualifying behaviors.

== Max points vs v1 ==

  S-A rubric:   13 → 13  (S-A.3 kept, rewritten)
  C1 rubric:    10 → 10  (C1.4 rewritten, same weight)
  C8 rubric:    12 → 12  (C8.3 rewritten, same weight)
  Universal:     7 →  7  (U.4 kept, rewritten)

  V3 scores ARE directly comparable to v1. All max_points are identical.
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
                f"Does the model response contain at least 80% of the discrete clinical data "
                f"points from the ground-truth {section_name}? "
                f"Step 1 — enumerate: list each discrete clinical data point in the ground truth "
                f"as a numbered list. A discrete data point is one of: a lab or vital-sign value "
                f"with its measurement, a medication name, a diagnosis or condition name, a "
                f"procedure name, or a specific clinical finding (e.g. 'tenderness in RLQ'). "
                f"Do NOT count section headers, filler phrases, or conjunctions. "
                f"Step 2 — mark: for each item, mark P (present in response) if it appears "
                f"verbatim or as a paraphrase that refers to the same clinical entity without "
                f"changing its magnitude, direction, or anatomic location "
                f"(e.g. 'crackles bilaterally' → valid paraphrase of 'bilateral rales'; "
                f"'severe dyspnea' → NOT a valid paraphrase of 'mild shortness of breath'); "
                f"mark A (absent) otherwise. "
                f"Step 3 — calculate: P_count / total. Answer 'yes' if ≥ 80%."
            ),
        },
        {
            "id": "S-A.2",
            "points": 3,
            "response_type": "binary",
            "question": (
                f"Does the model response contain at least 50% of the discrete clinical data "
                f"points from the ground-truth {section_name}? "
                f"Use the same enumeration from S-A.1 (or repeat it: list each lab value, "
                f"medication name, diagnosis, procedure, or specific finding; mark P or A for "
                f"each). Answer 'yes' if P_count / total ≥ 50%. Both S-A.1 and S-A.2 can be "
                f"answered 'yes' for the same response."
            ),
        },
        {
            # Re-added for v1 score comparability (Option A). Uses v2 wording:
            # rule-based priority order instead of v1's vague "most important fact."
            "id": "S-A.3",
            "points": 2,
            "response_type": "binary",
            "question": (
                f"Does the response include the highest-priority item from the ground-truth "
                f"{section_name}? Identify the highest-priority item in this order: "
                f"(1) any item explicitly labeled 'primary', 'active', 'principal', or 'chief' "
                f"in the ground truth; "
                f"(2) if no such label exists, the first discrete clinical data point listed. "
                f"If the ground truth is empty or contains only one item, answer 'yes'."
            ),
        },
        {
            "id": "S-A.4",
            "points": 3,
            "response_type": "binary",
            "question": (
                "Does every specific clinical claim in the model response have a basis in the "
                "source material? A 'specific clinical claim' is any statement about: a lab "
                "value, a medication name or dose, a diagnosis, a procedure, a vital sign, or "
                "a named clinical finding. "
                "A claim is supported if it appears verbatim in the source, OR can be directly "
                "derived without upgrading any qualifier the source uses "
                "(e.g. 'the WBC is elevated' is supported if the source shows WBC above the "
                "reference range; applying a standard clinical label to a numeric value such as "
                "calling glucose 280 'hyperglycemia' is supported; calling a result 'critically "
                "low' when the source flags it only as 'L' is NOT supported; inferring a new "
                "diagnosis not mentioned in the source is NOT supported). "
                "Answer 'no' if any specific clinical claim has no basis in the source."
            ),
        },
        {
            "id": "S-A.6",
            "points": -5,
            "response_type": "binary",
            "question": (
                "Does the model response state a specific clinical fact that cannot be found in "
                "or derived from the source material? "
                "Hallucinations include: a specific numeric value not in the source, a medication "
                "not mentioned in the source, a diagnosis not in the source, a procedure not in "
                "the source, a date or person not in the source. "
                "NOT hallucinations: paraphrasing source content, summarising multiple source "
                "items into one statement, or labelling a value as elevated because it exceeds "
                "the reference range stated in the source. "
                "Answer 'yes' if any hallucination is present."
            ),
        },
        {
            "id": "S-A.7",
            "points": -2,
            "response_type": "binary",
            "question": (
                "Does the model response omit any of the following items that are present in the "
                "ground truth? "
                "(1) A lab value with LB_ABN_RESULT = 'CRITICAL' or 'PANIC', or matching panic "
                "thresholds: K+ outside [2.5, 6.5] mmol/L, Na outside [120, 160] mEq/L, glucose "
                "outside [40, 500] mg/dL, INR > 5.0. "
                "(2) The diagnosis or problem listed first in the source, or labeled 'primary' / "
                "'principal'. "
                "(3) A procedure described as 'emergent', 'urgent', or 'STAT' in the source. "
                "(4) A medication listed under active orders or the current treatment plan. "
                "Answer 'yes' if any such item appears in the ground truth but is absent from "
                "the response."
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
# Variant C-A — Content extractive (C1, C8)
# ---------------------------------------------------------------------------


C1_CRITERIA = [
    {
        "id": "C1.1",
        "points": 3,
        "response_type": "binary",
        "question": (
            "Does the response mention every distinct problem or diagnosis listed in the source "
            "Assessment and Plan? Count the number of distinct problems in the source A&P — each "
            "numbered item, bullet point, or separately addressed condition counts as one. "
            "Answer 'yes' only if every one appears in the response by name or a paraphrase "
            "that refers to the same condition without changing its clinical category or "
            "specificity (e.g. 'bacterial pneumonia' is a valid paraphrase of 'pneumonia'; "
            "'respiratory illness' is NOT). When a single A&P item contains multiple diagnoses "
            "separated by commas, 'and', or '/' (e.g. 'Sepsis / bacteremia'), count each named "
            "diagnosis as a separate problem."
        ),
    },
    {
        "id": "C1.2",
        "points": 2,
        "response_type": "binary",
        "question": (
            "Does the response mention the problem that is (a) explicitly labeled 'primary', "
            "'active', or 'principal' in the source A&P, or (b) if no such label exists, "
            "the first problem listed in the source A&P? "
            "Answer 'yes' if that problem appears in the response."
        ),
    },
    {
        "id": "C1.3",
        "points": 2,
        "response_type": "binary",
        "question": (
            "For each problem the response mentions, does it also state at least one specific "
            "planned action documented in the source A&P? A specific planned action is: a named "
            "medication, a named test or imaging study to order, a consult to a named service or "
            "specialty, a named procedure, or a disposition (admit / discharge / transfer to "
            "named unit). 'Further workup' or 'optimize management' without a named action do "
            "not count. Answer 'yes' if every problem the response identifies has at least one "
            "specific action paired with it."
        ),
    },
    {
        "id": "C1.4",
        "points": 1,
        "response_type": "binary",
        "question": (
            "Does the response include at least one causal or explanatory phrase that also "
            "appears in the source A&P, linking a problem to its cause, mechanism, or "
            "rationale? Qualifying phrases: 'due to', 'secondary to', 'in the setting of', "
            "'consistent with', 'because', 'given', 'likely from', 'attributed to', 'thought "
            "to be', or any other phrase that grammatically signals causation or attribution "
            "between two named clinical entities. The phrase must connect a problem and a cause "
            "that both appear in the source A&P. Answer 'no' if the response lists problems and "
            "plans with no such connective language from the source."
        ),
    },
    {
        "id": "C1.5",
        "points": 1,
        "response_type": "binary",
        "question": (
            "Identify each distinct medication name mentioned in the source A&P. Does the "
            "response include all of them? Answer 'yes' if every medication name from the source "
            "A&P appears in the response."
        ),
    },
    {
        "id": "C1.6",
        "points": 1,
        "response_type": "binary",
        "question": (
            "If the source A&P includes a disposition (admit, discharge, transfer to a named "
            "unit) or an explicit next step with a timeframe (e.g. 'follow up in 2 weeks', "
            "'repeat imaging in 48 hours'), does the response also include that information? "
            "If the source A&P contains no disposition and no explicit next steps, answer 'yes'."
        ),
    },
    {
        "id": "C1.7",
        "points": -3,
        "response_type": "binary",
        "question": (
            "Does the response present any diagnosis or condition as part of the current "
            "assessment or plan that does NOT appear in the source A&P? Background mentions of "
            "past medical history (e.g. 'the patient has a history of HTN') do not count unless "
            "the response links them to a current problem or plan step. Answer 'yes' if any such "
            "condition is presented as active or current in the response but absent from the "
            "source A&P."
        ),
    },
    {
        "id": "C1.8",
        "points": -2,
        "response_type": "binary",
        "question": (
            "Does the response omit any problem documented in the source A&P? Count the distinct "
            "problems using the same rule as C1.1: each numbered item or bullet counts as one "
            "problem; multiple diagnoses within a single item separated by commas, 'and', or '/' "
            "(e.g. 'Sepsis / bacteremia') count as separate problems. Answer 'yes' if any one "
            "of them does not appear anywhere in the response."
        ),
    },
    {
        "id": "C1.9",
        "points": -1,
        "response_type": "binary",
        "question": (
            "Does the response include any of the following content that is NOT in the source "
            "A&P: "
            "(1) general medical background or pathophysiology about a condition "
            "('Sepsis is defined as...', 'Pneumonia is an infection of...'); "
            "(2) filler caveats with no clinical content ('It is important to note...', "
            "'Clinical judgment should always be applied'); "
            "(3) management recommendations for conditions not mentioned in the source A&P. "
            "Answer 'yes' if any such content is present."
        ),
    },
]


# C8 — D2 decision preserved: critical-miss penalty is −3 (not −5).
# C8.3 rewritten: "clinical context correct" → direction (H/L) accuracy.
C8_CRITERIA = [
    {
        "id": "C8.1",
        "points": 3,
        "response_type": "binary",
        "question": (
            "From the ground-truth lab list, count only values with a non-normal flag "
            "(LB_ABN_RESULT in H, L, HH, LL, CRITICAL, ABNORMAL, A). "
            "Count how many of those flagged-abnormal values are mentioned in the response "
            "using a term that signals abnormality — abnormal, elevated, increased, decreased, "
            "low, high, out of range, flagged, critical, or any direct synonym — in connection "
            "with the lab name (exact numeric value not required). "
            "Answer 'yes' if ≥ 80% of the flagged-abnormal values are identified."
        ),
    },
    {
        "id": "C8.2",
        "points": 2,
        "response_type": "binary",
        "question": (
            "Using the same counting method as C8.1 — a value counts as identified if the "
            "response uses a term signalling abnormality (abnormal, elevated, increased, "
            "decreased, low, high, out of range, flagged, critical, or any direct synonym) "
            "in connection with the lab name — answer 'yes' if ≥ 50% of the flagged-abnormal "
            "values are identified. Both C8.1 and C8.2 can be 'yes' for the same response."
        ),
    },
    {
        # Replaces v1 C8.3 "is the clinical context correct?" which required open-ended
        # clinical evaluation. This version is deterministic from the LB_ABN_RESULT flags.
        "id": "C8.3",
        "points": 2,
        "response_type": "binary",
        "question": (
            "For each lab value the response identifies as abnormal, does the response correctly "
            "state its direction? "
            "Use LB_ABN_RESULT from the ground truth as ground truth for direction: "
            "H or HH → response must use 'high', 'elevated', 'increased', or equivalent; "
            "L or LL → response must use 'low', 'decreased', 'reduced', or equivalent; "
            "CRITICAL → determine direction from the numeric value vs the reference range "
            "(above upper bound = elevated, below lower bound = decreased). "
            "Answer 'yes' if every value the response flags as abnormal has the correct "
            "direction stated."
        ),
    },
    {
        "id": "C8.4",
        "points": 2,
        "response_type": "binary",
        "question": (
            "For each flagged-abnormal value the response identifies, does the response include "
            "at least one specific follow-up action? Specific means the action names one of: a "
            "test to repeat or add (by name), a medication to adjust or hold (by name), a "
            "specialist or service to notify (by name), or a named monitoring parameter or "
            "specific frequency (e.g. 'recheck potassium in 4 hours', 'continuous cardiac "
            "monitoring', 'monitor sodium levels'). "
            "'Monitor closely', 'follow clinically', 'address appropriately', or any other "
            "vague phrase without a named test, drug, service, or frequency does NOT qualify. "
            "Answer 'yes' if ≥ 50% of the flagged-abnormal values the response identifies have "
            "at least one specific action."
        ),
    },
    {
        "id": "C8.5",
        "points": 3,
        "response_type": "binary",
        "question": (
            "If the ground truth contains any value with LB_ABN_RESULT = 'CRITICAL', or any "
            "value matching these panic ranges: K+ outside [2.5, 6.5] mmol/L, Na outside "
            "[120, 160] mEq/L, glucose outside [40, 500] mg/dL, INR > 5.0 — does the response "
            "identify at least one of those values as critical or panic-range? "
            "If no such values exist in the ground truth, answer 'yes'."
        ),
    },
    {
        "id": "C8.6",
        "points": -1,
        "response_type": "binary",
        "question": (
            "Does the response label any lab value as abnormal when the ground truth shows it as "
            "normal? A value is normal if: (1) its LB_ABN_RESULT field is empty or absent, AND "
            "(2) the numeric value falls within LB_REF_LOW to LB_REF_HIGH. "
            "Answer 'yes' if any such false-abnormal labeling is present."
        ),
    },
    {
        "id": "C8.7",
        "points": -3,
        "response_type": "binary",
        "question": (
            "Is there a critical or panic-range lab value in the ground truth that the response "
            "does not flag as abnormal? Critical values: (1) LB_ABN_RESULT = 'CRITICAL' in the "
            "ground truth, OR (2) K+ outside [2.5, 6.5] mmol/L, Na outside [120, 160] mEq/L, "
            "glucose outside [40, 500] mg/dL, INR > 5.0. "
            "Answer 'yes' if any such value exists in the ground truth but the response does "
            "not flag it."
        ),
    },
    {
        "id": "C8.8",
        "points": -2,
        "response_type": "binary",
        "question": (
            "Does the response recommend an action that directly contradicts information in the "
            "source? Contradictions specific to lab interpretation: "
            "(1) recommending a medication that appears on the patient's allergy list in the "
            "source; "
            "(2) recommending stopping or withholding a medication listed as active in the "
            "current plan without a stated reason; "
            "(3) stating that a value with LB_ABN_RESULT = 'CRITICAL' is within normal limits "
            "and requires no follow-up. "
            "Answer 'yes' if any such contradiction is present."
        ),
    },
]


# ---------------------------------------------------------------------------
# Variant P-C — Numerical predictions (P7 only)
# ---------------------------------------------------------------------------


P7_CRITERIA = [
    {
        "id": "P-C.1",
        "points": 1,
        "response_type": "binary",
        "question": (
            "For each lab the model predicted, compare the predicted direction against the "
            "actual direction in the ground-truth panel. Use LB_ABN_RESULT as ground truth: "
            "H or HH = high; L or LL = low; absent or normal = within reference range. "
            "The model's prediction counts as a direction match if: it says 'high' / 'elevated' "
            "/ 'increased' for an H/HH actual; 'low' / 'decreased' for an L/LL actual; "
            "'normal' / 'within range' for a non-flagged actual. "
            "Answer 'yes' if > 50% of the labs the model predicted have matching directions."
        ),
    },
    {
        "id": "P-C.2",
        "points": 1,
        "response_type": "binary",
        "question": (
            "For each lab where the model gave a specific numeric prediction, calculate whether "
            "the predicted value is within ±25% of the actual: |predicted − actual| / actual "
            "≤ 0.25. Exclude any lab for which the model did not give a numeric value. "
            "Answer 'yes' if > 50% of the labs with numeric predictions satisfy this threshold."
        ),
    },
    {
        "id": "P-C.3",
        "points": -1,
        "response_type": "binary",
        "question": (
            "Does the model predict a lab that does not appear in the ground-truth panel? "
            "Compare each predicted lab name against the ground-truth panel names. Standard "
            "abbreviation variants count as matches (e.g. 'Hgb', 'HGB', 'Hemoglobin' all match "
            "the same entry). Answer 'yes' if any predicted lab name has no match in the "
            "ground-truth panel."
        ),
    },
]


# ---------------------------------------------------------------------------
# Universal criteria (applied to every response, every prompt)
# ---------------------------------------------------------------------------


UNIVERSAL_CRITERIA = [
    {
        "id": "U.1",
        "points": 2,
        "response_type": "binary",
        "question": (
            "Does every specific factual claim in the model response have a basis in the input "
            "the model was given? Specific factual claims include statements about: a named lab "
            "value or vital sign, a medication name or dose, a diagnosis, a procedure, a date, "
            "or a named clinical finding. "
            "A claim is supported if it appears verbatim in the input, or can be directly "
            "derived from data in the input without upgrading any qualifier the source uses "
            "(e.g. labelling a value as elevated because it exceeds the reference range is "
            "supported; applying a standard clinical label to a numeric value such as calling "
            "glucose 280 'hyperglycemia' is supported; calling a result 'critically low' when "
            "the source flags it only as 'L' is NOT supported; stating a new diagnosis not "
            "present in the input is NOT supported). "
            "Answer 'no' if any specific factual claim has no basis in the input."
        ),
    },
    {
        "id": "U.2",
        "points": 2,
        "response_type": "binary",
        "question": (
            "Does the response avoid directly contradicting documented clinical data in a way "
            "that could cause patient harm? Check for: "
            "(1) recommending a medication that appears on the patient's allergy list in the "
            "source; "
            "(2) recommending stopping or withholding a medication listed as active in the "
            "current plan without stating a reason; "
            "(3) stating that a value marked 'CRITICAL' in the source is within normal limits "
            "and requires no action. "
            "Answer 'yes' if none of these are present."
        ),
    },
    {
        "id": "U.3",
        "points": 1,
        "response_type": "binary",
        "question": (
            "Does the majority of the response directly address the specific task in the prompt? "
            "On-task: for extraction prompts, provides the requested content; for summary "
            "prompts, summarizes only the requested content; for prediction prompts, makes the "
            "requested predictions. Off-task: discusses the task at a meta level, adds "
            "unrequested clinical background, or addresses a different aspect of the patient's "
            "care. Answer 'no' if the response contains any of the following: any unrequested "
            "clinical background or education not drawn from the source; a definition-style "
            "sentence about a condition (e.g. 'Sepsis is defined as...'); or content "
            "addressing a patient problem not mentioned in the prompt."
        ),
    },
    {
        # Re-added for v1 score comparability (Option A). Uses v2 wording:
        # same-abbreviations rule instead of v1's vague "precise terminology."
        "id": "U.4",
        "points": 1,
        "response_type": "binary",
        "question": (
            "Does the response use the same clinical abbreviations as the source for the same "
            "concepts? For example: if the source uses 'WBC', the response should not "
            "substitute 'white blood cell count' without also using 'WBC'; if the source uses "
            "'HTN', the response should not substitute 'high blood pressure'. "
            "Answer 'no' if the response replaces any clinical abbreviation from the source "
            "with a lay term or non-standard synonym without also using the original "
            "abbreviation."
        ),
    },
    {
        "id": "U.5",
        "points": 1,
        "response_type": "binary",
        "question": (
            "If the input contains an explicitly flagged data gap — a value noted as 'not "
            "available', a section marked as missing, or conflicting values with no resolution "
            "stated — does the response acknowledge at least one such gap? "
            "If the input has no explicitly flagged gaps, answer 'yes' (auto-pass). "
            "Answer 'no' only when the input has an explicitly flagged gap AND the response "
            "draws a definitive conclusion from that gap without acknowledging it."
        ),
    },
]


# ---------------------------------------------------------------------------
# Lookup helpers (same API as criteria.py)
# ---------------------------------------------------------------------------


def criteria_for(prompt_id: str) -> list[dict]:
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
    raw = 0
    for c in criteria:
        ans = results.get(c["id"])
        if ans == "yes" or ans is True:
            raw += c["points"]
    max_pos = max_points(criteria) or 1
    return max(0.0, min(1.0, raw / max_pos))
