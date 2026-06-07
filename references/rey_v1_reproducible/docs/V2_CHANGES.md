# V2 Changes — Criteria and Code

Documents all changes introduced in the v2 files relative to v1. Supersedes `CRITERIA_V2_CHANGES.md`.

**Score comparability**: all criterion IDs and point weights are unchanged from v1. Max points per rubric are identical. V2 scores are directly comparable to v1 pilot results.

---

## Files changed

| v1 file | v2 file | What changed |
|---|---|---|
| `criteria.py` | `criteria_v2.py` | Full rubric rewrite for objectivity — see below |
| `run_eval_parallel.py` | `run_eval_parallel_v2.py` | Criteria import, C8 prompt, judge system prompt |
| `smoke_test.py` | `smoke_test_v2.py` | PROMPT_TEXT synced to match runner |

---

## Code changes (`run_eval_parallel_v2.py`)

### 1. Criteria import

```python
# v1
from criteria import (criteria_for, score_from_results, UNIVERSAL_CRITERIA)

# v2
from criteria_v2 import (criteria_for, score_from_results, UNIVERSAL_CRITERIA)
```

The runner was still importing from the v1 rubric. Any run using `run_eval_parallel_v2.py` now uses the updated criteria.

### 2. C8 model prompt — "appropriate" removed

```
# v1
"Summarize the lab results below. Identify which values are abnormal and, for each
abnormal result, describe what clinical action or follow-up order would be appropriate."

# v2
"Summarize the lab results below. Identify which values are abnormal, flagging each
as elevated or decreased. For each abnormal result, state a specific follow-up
action: name the test to repeat or add, the medication to adjust or hold, or the
specialist or service to notify."
```

The v1 prompt asked for what's "appropriate," which invited vague responses. The v2 criteria (C8.3, C8.4) score for direction accuracy and named specific actions — the prompt now asks for exactly those things. Also adds the elevated/decreased instruction, which aligns the model's output format with C8.3's direction-accuracy check.

### 3. Judge system prompt — clinical judgment removed

```
# v1
"Be strict but fair. Base your judgment ONLY on the source material and the response
provided. Do not penalize for stylistic choices unless the criterion explicitly
addresses style. If the criterion is ambiguous in this case, default to 'no'."

# v2
"Base your judgment ONLY on the source material and the model response provided.
Do not apply outside clinical knowledge — score only what is stated in the text,
not what would be clinically ideal or expected.
If the criterion cannot be determined from the provided text alone, default to 'no'."
```

Three specific changes:
- **"Be strict but fair" removed** — "fair" is an evaluative instruction with no defined meaning; it implicitly invites leniency
- **"Do not penalize for stylistic choices" removed** — judges must decide what counts as stylistic vs. substantive, which is itself a subjective call
- **"Do not apply outside clinical knowledge" added** — the most important addition. Without this, judges with clinical training may credit implied actions or inferred diagnoses that aren't stated in the response, producing inconsistent scores relative to non-expert judges

---

## Code changes (`smoke_test_v2.py`)

### PROMPT_TEXT synced to runner

The smoke test had its own `PROMPT_TEXT` dict that had drifted from `run_eval_parallel.py`. Three prompts differed:

| Prompt | v1 smoke test | v2 (corrected) |
|---|---|---|
| S1 | "...from the admission H&P below." | "...from the clinical note(s) below. Return only the chief complaint text." |
| C1 | Missing "Cover all problems and their plans." | Full prompt matching runner |
| P7 | Missing "meds" from context list; missing direction instruction | Full prompt matching runner |

`smoke_test_v2.py` now has a comment marking the dict as requiring sync with `run_eval_parallel_v2.py`.

---

## Criteria changes (`criteria_v2.py`)

### What drove the rewrite

The v1 rubric contained several categories of vague language that caused inter-judge variance:

- **Evaluative phrases** with no decision rule: "clinically correct", "appropriate", "key clinical reasoning", "clinically critical"
- **Undefined counting tasks**: "key facts" with no enumerable definition; percentage estimation done holistically rather than by explicit count
- **Subjective thresholds**: "25% off-task" (unmeasurable), "consistently replaces" (undefined frequency), "significantly abnormal" (not a defined category)
- **Escape clauses**: "or equivalent constructions" in criterion lists, "unambiguous paraphrase" with no rule for what makes a paraphrase valid

### Structural changes (apply across rubrics)

**Enumeration scaffold on S-A.1 / S-A.2**
V1 asked judges to estimate whether ≥80%/50% of "key facts" were present holistically. V2 adds an explicit three-step scaffold:
1. List each discrete clinical data point from the ground truth as a numbered list
2. Mark each P (present) or A (absent)
3. Calculate P/total and compare against threshold

**Paraphrase rule (all recall criteria)**
> A paraphrase is valid if it refers to the same clinical entity without changing its magnitude, direction, or anatomic location.
> e.g. "crackles bilaterally" → valid paraphrase of "bilateral rales"; "severe dyspnea" → NOT a valid paraphrase of "mild shortness of breath"

**Severity-upgrade rule (S-A.4, U.1)**
- Labelling a value as elevated because it exceeds the stated reference range → supported
- Applying a standard clinical label to a numeric value (e.g. calling glucose 280 "hyperglycemia") → supported
- Upgrading a qualifier the source doesn't use (e.g. calling a result "critically low" when source flags it only as L) → NOT supported
- Inferring a new diagnosis not mentioned in the source → NOT supported

**Multi-diagnosis tie-breaker (C1.1, C1.8)**
> When a single A&P item contains multiple diagnoses separated by commas, "and", or "/" (e.g. "Sepsis / bacteremia"), count each named diagnosis as a separate problem.

**Abnormality word list (C8.1, C8.2)**
V1 said "mentioned as out of range or abnormal" with no definition of what words count. V2 requires a term from an explicit list: abnormal, elevated, increased, decreased, low, high, out of range, flagged, critical, or any direct synonym.

### Per-criterion changes

#### S-A family (S1–S10)

| Criterion | V1 | V2 |
|---|---|---|
| **S-A.1** | "key fact" undefined; holistic % estimate | "discrete clinical data point" explicitly defined; three-step enumeration scaffold |
| **S-A.2** | Same issues as S-A.1 | References S-A.1 enumeration; same counting rule |
| **S-A.3** | "single most important fact" — highly subjective | Rule-based priority: (1) item labeled primary/active/principal/chief; (2) first discrete data point listed. Auto-passes if GT is empty or has one item |
| **S-A.4** | "traceable" / "clear paraphrase" — vague | Two-tier support rule with severity-upgrade examples |
| **S-A.6** | Reasonably clear | Added: direct logical inferences from source data explicitly excluded from hallucination |
| **S-A.7** | "clinically critical" — undefined | Explicit checklist: (1) CRITICAL/PANIC flag or panic thresholds; (2) first-listed or primary-labeled diagnosis; (3) EMERGENT/URGENT/STAT procedure; (4) medication in active orders |

#### C1 family

| Criterion | V1 | V2 |
|---|---|---|
| **C1.1** | "ALL problems" — "problem" undefined | Counting rule; multi-diagnosis tie-breaker; paraphrase rule |
| **C1.2** | "primary or most-active problem" — subjective | Rule-based: explicitly labeled primary/active/principal, else first problem listed |
| **C1.3** | "documented treatment plan" — vague | At least one named specific action per problem (named medication, test, service, procedure, or disposition); vague phrases explicitly excluded |
| **C1.4** | "key clinical reasoning (not just a bullet list)" — no decision boundary | Causal-connective check: response must include a phrase from the qualifying list (due to, secondary to, in the setting of, consistent with, because, given, likely from, attributed to, thought to be, or any phrase grammatically signalling causation/attribution) that also appears in the source A&P |
| **C1.5** | "where the source mentions them" — implied scope | Explicit: every medication name in the source A&P must appear in response |
| **C1.6** | "where the source documents it" — implied null case | Explicit null-case rule: auto-passes if source A&P contains no disposition and no explicit next steps |
| **C1.7** | "active medical issue" — catches PMH mentions | Changed to "presented as part of the current assessment or plan"; PMH background mentions explicitly excluded unless linked to a current problem or plan step |
| **C1.8** | Counting ambiguity | References C1.1 counting rule; multi-diagnosis tie-breaker |
| **C1.9** | "general medical teaching, padding" — vague | Explicit list: (1) pathophysiology/background sentences; (2) definition-style sentences; (3) management recommendations for conditions not in source A&P |

#### C8 family

| Criterion | V1 | V2 |
|---|---|---|
| **C8.1** | "correctly flag" — undefined | Counts values with LB_ABN_RESULT in {H, L, HH, LL, CRITICAL, ABNORMAL, A}; "identified" defined by word list |
| **C8.2** | Same | Same improvement; references C8.1 word list |
| **C8.3** | **"is the clinical context correct?"** — most subjective criterion in v1 | **Replaced entirely** with direction-accuracy check: response direction (high/elevated/increased or low/decreased/reduced) checked against LB_ABN_RESULT flag. Fully deterministic |
| **C8.4** | "is the suggested follow-up action appropriate?" — required clinical judgment | Named-action requirement: must name a test, medication, specialist/service, or monitoring parameter/frequency. Vague phrases explicitly excluded. Passes if ≥50% of identified abnormals have a specific action |
| **C8.5** | No null-case rule; "significantly abnormal" was vague | Auto-pass when no critical values in GT; "significantly abnormal" removed — only CRITICAL flag or explicit panic-range thresholds qualify |
| **C8.6** | "normal" not precisely defined | Normal = LB_ABN_RESULT empty/absent AND numeric value within LB_REF_LOW–LB_REF_HIGH |
| **C8.7** | Already had explicit thresholds | Minor cleanup |
| **C8.8** | "inappropriate or unsafe" — required clinical judgment | Source-contradiction checklist: (1) medication on allergy list; (2) stopping active medication without stated reason; (3) stating a CRITICAL-flagged value is normal |

#### P7 family

| Criterion | V1 | V2 |
|---|---|---|
| **P-C.1** | "predicted direction matches" — vague on what signals direction | Explicit mapping: H/HH → high/elevated/increased; L/LL → low/decreased; absent → normal/within range |
| **P-C.2** | Clear already | Formula added explicitly: \|predicted − actual\| / actual ≤ 0.25 |
| **P-C.3** | "predicts a lab that does not appear" | Abbreviation-matching rule added: Hgb / HGB / Hemoglobin all match same entry |

#### Universal criteria

| Criterion | V1 | V2 |
|---|---|---|
| **U.1** | "supported by content in the input" — vague | "Specific factual claim" explicitly defined; severity-upgrade examples added |
| **U.2** | "clinically unsafe action" — requires clinical knowledge | Source-contradiction checklist: allergy violation, stopping active med without reason, dismissing CRITICAL value |
| **U.3** | "no off-task tangents" | Specific disqualifying behaviors listed; unmeasurable 25% threshold removed |
| **U.4** | "precise clinical terminology" — subjective | Narrowed to same-abbreviations rule: fails if response replaces any clinical abbreviation from source without also using the original |
| **U.5** | Vague trigger | Auto-pass if input has no flagged gaps; fires only when input has an explicitly flagged gap that the response ignores |

### What was not changed

- All criterion IDs (S-A.1 through U.5)
- All point weights (positive and negative)
- The C8 D2 decision: critical-miss penalty stays at −3 (not −5)
- The scoring formula: `clip(sum_of_signed_points / max_positive_points, 0, 1)`
- The combined score weighting: 80% prompt-specific, 20% universal
- The judge stack and routing logic
