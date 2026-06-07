# Judge Prompts — Project Bayes (Locked)

Literal judge prompt templates for the 31 prompt-specific rubrics + 5 universal criteria. Reflects locked decisions:

- D2: Critical-value penalty in C8 set to **−3** (was −5)
- D3: P-A "same ICD chapter" tier kept at **0.8**
- D4: Literal judge prompts included here
- D5: 5 universal criteria added, applied to every case

Judges: **Claude Sonnet 4.6** (all families) + **GPT-5.4-mini** (Structure + AE) / **GPT-5.4 full** (Content-generative + Prediction).

---

## How a judge call is constructed

Each criterion is a single LLM call. The call has three parts:

1. **System preamble** — defines the judge's role
2. **Context block** — the prompt the model was given + source/ground truth + the model's response
3. **Criterion question** — the specific yes/no (or scaled) question to answer

For each `(case, prompt, criterion)` triple we run one judge call. Two judges = two calls per criterion. The judge returns structured JSON (one or two tokens) which we parse and score.

### System preamble (used for every judge call)

```
You are a clinical evaluator scoring a medical AI model's response against a rubric.
The model was given a specific clinical task and produced a response. You must judge
whether the response meets a specific criterion.

Be strict but fair. Base your judgment ONLY on the source material and the response
provided. Do not penalize for stylistic choices unless the criterion explicitly
addresses style. If the criterion is ambiguous in this case, default to "no".

Return your answer as JSON in this exact format:
{"answer": "yes" | "no", "rationale": "<one sentence>"}
For scaled criteria, use:
{"answer": <integer>, "rationale": "<one sentence>"}
```

### Context block (template, filled per case)

```
PROMPT GIVEN TO MODEL:
{prompt_text}

SOURCE MATERIAL PROVIDED TO MODEL:
{rendered_source}

GROUND TRUTH (NOT shown to the model):
{ground_truth}

MODEL RESPONSE:
{model_response}
```

For prompts with no separate ground truth (e.g., C2 which asks the model to generate a DDx), the `GROUND TRUTH` block is omitted.

---

## Variant S-A — Structure prompts (S1–S10)

**Applies to**: S1, S2, S3, S4, S5, S6, S7, S8, S9, S10
**Customization per prompt**: the `{section_name}` and the ground-truth content vary.

### Criterion S-A.1 (+5) — High recall

```
Question: Does the model response contain at least 80% of the key facts from the
ground-truth {section_name}?

A "key fact" is any distinct clinical statement, value, or finding documented in
the ground truth. Count facts present in the response vs. total facts in ground
truth. Answer "yes" if ≥ 80% of facts appear in the response (paraphrasing
allowed; exact wording not required).
```

### Criterion S-A.2 (+3) — Moderate recall

```
Question: Does the model response contain at least 50% of the key facts from the
ground-truth {section_name}?

Apply the same fact-counting approach as the previous criterion. Answer "yes" if
≥ 50% but < 80% of facts appear. If ≥ 80%, also answer "yes" to this criterion
(both criteria can be met).
```

### Criterion S-A.3 (+2) — Primary fact present

```
Question: Does the response include the single most important fact from the
ground-truth {section_name}?

The "most important fact" is the primary diagnosis, primary symptom, primary
abnormal value, or primary plan element, depending on section. If you cannot
identify a single most-important fact, answer "yes".
```

### Criterion S-A.4 (+3) — Faithful (no hallucination)

```
Question: Is every clinical claim in the model response traceable to the source
material provided?

A claim is "traceable" if it appears in the source verbatim or as a clear
paraphrase. If the response contains any value, finding, or statement not
supported by the source, answer "no".
```

### Criterion S-A.5 (+1) — Timestamps where required

```
Question: For prompts requiring timestamps (S6–S9): does the response include
collection date/time for each reported lab value?

If the prompt does not require timestamps, mark this criterion N/A and exclude
from scoring.
```

### Criterion S-A.6 (−5) — Hallucination

```
Question: Does the model response contain a clinical value, finding, or fact
that does NOT appear in the source material provided?

Hallucinations are: invented lab values, invented dates, statements not in source,
diagnoses not documented. Paraphrasing is not hallucination. Answer "yes" if any
hallucination is present.
```

### Criterion S-A.7 (−2) — Critical omission

```
Question: Does the model response omit a clinically critical value or fact from
the ground truth?

"Critical" means: abnormal lab values flagged as critical/panic; primary
diagnoses; major procedures; major medications affecting current plan. Answer
"yes" if any such item is in the ground truth but missing from the response.
```

**Max points (S-A)**: 14
**Prompt-specific section_name values**:

| Prompt | `{section_name}` |
|---|---|
| S1 | "Chief Complaint" |
| S2 | "History of Present Illness" |
| S3 | "Physical Exam findings" |
| S4 | "laboratory and imaging data referenced in the note" |
| S5 | "Assessment and Plan" |
| S6 | "CBC results" |
| S7 | "BMP / electrolyte results" |
| S8 | "serial troponin values" |
| S9 | "blood culture results" |
| S10 | "imaging reports referenced in the note" |

---

## Variant C-A — Content extractive (C1, C5, C6, C8)

Per-prompt criteria. Each prompt has its own checklist.

### Prompt C1 — Summarize the A&P

| # | Question | Points |
|---|---|---|
| C1.1 | Does the response identify ALL problems documented in the source A&P? | +3 |
| C1.2 | Does the response identify the primary or most-active problem from the source A&P? | +2 |
| C1.3 | For each identified problem, does the response include the documented treatment plan? | +2 |
| C1.4 | Does the response preserve key clinical reasoning from the source (not just a bullet list)? | +1 |
| C1.5 | Does the response include medication names where the source mentions them? | +1 |
| C1.6 | Does the response include disposition or next-step information where the source documents it? | +1 |
| C1.7 | Does the response add a problem not present in the source A&P? | −3 |
| C1.8 | Does the response omit a problem that is documented in the source A&P? | −2 |
| C1.9 | Does the response add non-source content (general medical teaching, padding)? | −1 |

**Max points**: 10

Literal prompt for C1.1:

```
Question: Does the model response identify ALL problems documented in the source
Assessment and Plan?

Count distinct problems in the source A&P. The response must mention each one
(by name or close paraphrase). Order does not matter. Answer "yes" only if every
problem appears in the response.
```

(Same template form for C1.2–C1.9 with the criterion text substituted.)

### Prompt C5 — Predict expected orders from documented plan

| # | Question | Points |
|---|---|---|
| C5.1 | Does the response list ≥ 80% of the actual orders placed (from prescription_orders + procedures)? | +3 |
| C5.2 | Does the response list ≥ 50% of the actual orders placed? | +2 |
| C5.3 | Are all listed orders supported by content in the documented Plan? | +3 |
| C5.4 | Does the response include order frequency/dose where the Plan specifies it? | +1 |
| C5.5 | Does the response invent orders not supported by the Plan? | −3 |
| C5.6 | Does the response omit an order explicitly named in the Plan? | −2 |

**Max points**: 9

### Prompt C6 — Summarize imaging study findings

| # | Question | Points |
|---|---|---|
| C6.1 | Does the response capture the primary finding from the imaging report? | +3 |
| C6.2 | Does the response capture all major findings (≥ 80%) from the imaging report? | +3 |
| C6.3 | Does the response correctly identify any urgent/actionable finding? | +2 |
| C6.4 | Does the response include the imaging modality and body region? | +1 |
| C6.5 | Does the response invent a finding not in the imaging report? | −3 |
| C6.6 | Does the response miss an urgent/actionable finding documented in the report? | −3 |

**Max points**: 9

### Prompt C8 — Lab interpretation (D2: penalty softened to −3)

| # | Question | Points |
|---|---|---|
| C8.1 | Does the response correctly flag ≥ 80% of the actually-abnormal values? | +3 |
| C8.2 | Does the response correctly flag ≥ 50% of the actually-abnormal values? | +2 |
| C8.3 | For each flagged abnormal, is the clinical context correct? | +2 |
| C8.4 | For each flagged abnormal, is the suggested follow-up action appropriate? | +2 |
| C8.5 | Does the response identify any critical/panic value if present in the labs? | +3 |
| C8.6 | Does the response flag a normal value as abnormal? | −1 |
| C8.7 | Does the response miss a critical/panic value? | −3 |
| C8.8 | Does the response suggest an inappropriate or unsafe action? | −2 |

**Max points**: 12

Literal prompt for C8.7:

```
Question: Does the model response miss a critical/panic value present in the lab data?

A critical/panic value is any lab value flagged in the source data as "critical"
or "panic", OR any value in commonly recognized critical ranges (e.g., K+ < 2.5
or > 6.5, glucose < 40 or > 500, INR > 5, sodium < 120 or > 160). Answer "yes"
if any such value is in the source but not flagged in the response.
```

---

## Variant C-B — Content generative (C2, C3, C4, C7)

Same 3 Likert dimensions for all 4 prompts; the prompt context varies.

### Dimension C-B.1 — Accuracy (1–5)

```
Question: Rate the factual accuracy of the model response on a 1–5 scale.

Scale:
  5 — All clinical claims are factually correct and clinically sound.
  4 — Mostly correct; one minor factual issue that does not change clinical meaning.
  3 — Mixed accuracy; one significant factual error or several minor errors.
  2 — Multiple significant factual errors; clinical reasoning compromised.
  1 — Largely inaccurate; would mislead a clinician.

Base your rating on the source material provided. Do not penalize for omissions
(that is scored separately under Completeness).
```

### Dimension C-B.2 — Completeness (1–5)

```
Question: Rate the completeness of the model response on a 1–5 scale.

Scale:
  5 — Covers all clinically relevant aspects required by the prompt.
  4 — Covers most relevant aspects; one minor gap.
  3 — Covers some aspects but with notable gaps.
  2 — Major gaps; misses important clinical content.
  1 — Substantially incomplete; would be inadequate clinically.
```

### Dimension C-B.3 — Clinical coherence (1–5)

```
Question: Rate the clinical coherence (reasoning quality) of the model response on a 1–5 scale.

Scale:
  5 — Reasoning is clinically sound, internally consistent, and well-organized.
  4 — Mostly coherent; one minor logical inconsistency.
  3 — Coherent in parts but with reasoning gaps.
  2 — Reasoning is inconsistent or poorly supported.
  1 — Incoherent or clinically nonsensical reasoning.
```

**Max points**: 15 (5 × 3 dimensions)

Per-prompt context for C-B:

| Prompt | Context for judge |
|---|---|
| C2 | "The model was given only the HPI and asked to generate a differential diagnosis, assessment, and plan." |
| C3 | "The model was given its prior DDx output and asked to provide supporting clinical references." |
| C4 | "The model was given ≥ 2 consult notes and asked to compare recommendations." |
| C7 | "The model was given an imaging report and asked to identify new diagnoses or incidental findings." |

---

## Variant P-A — Prediction discharge Dx (P3, P4)

Single tiered judgment, not a checklist.

```
Question: Compare the model's predicted discharge diagnosis to the actual discharge diagnosis. Choose the closest tier.

GROUND TRUTH discharge diagnosis (ICD-10): {actual_dx_code} — {actual_dx_text}
MODEL prediction: {model_response}

Tiers (return the tier number):
  5 — Exact match: predicted code/name matches actual at full specificity
       (e.g., "J18.9 pneumonia, unspecified" predicted as "pneumonia, unspecified")
  4 — Same 3-character ICD-10 chapter and same condition family
       (e.g., "J18 pneumonia" when actual is "J18.9 pneumonia, unspecified")
  3 — Same organ system and same broad condition family
       (e.g., "lower respiratory tract infection" when actual is "pneumonia")
  2 — Same organ system, different condition
       (e.g., "respiratory failure" when actual is "pneumonia")
  1 — Plausible alternative, different system
       (e.g., "heart failure" when actual is "pneumonia")
  0 — Wrong, implausible, or nonsense

Return: {"answer": <0-5>, "rationale": "<one sentence>"}
```

Tier-to-score mapping: 5 → 1.0, 4 → 0.8, 3 → 0.6, 2 → 0.3, 1 → 0.1, 0 → 0.0

**For P4 (rolling N)**: same prompt at each value of N. We report per-N score and the smallest N where score reaches ≥ 0.6 (called "convergence day").

---

## Variant P-B — Prediction free-text (P1, P2, P5, P6, P8, P9, P10)

Same 7 criteria template, customized per prompt for what counts as "actual" and "predicted."

### Generic P-B criteria

| # | Question | Points |
|---|---|---|
| P-B.1 | Does the response's primary prediction overlap meaningfully with the ground-truth outcome? | +3 |
| P-B.2 | Does the response recommend or anticipate the actual first-line clinical action documented in ground truth? | +3 |
| P-B.3 | Does the response cover the same major categories (workup, diagnosis, treatment) as the actual outcome? | +2 |
| P-B.4 | Is the response's reasoning consistent with the input material the model was given? | +1 |
| P-B.5 | Is the response's prediction clinically appropriate for the presentation, regardless of whether it matches the actual outcome? | +1 |
| P-B.6 | Does the response recommend something clinically inappropriate or contraindicated? | −3 |
| P-B.7 | Does the response correctly identify something clinically important that the actual record missed? (counts in model's favor) | +2 |

**Max points**: ~12

Literal prompt for P-B.1 (with prompt-specific substitution):

```
Question: Does the model's primary prediction overlap meaningfully with the
ground-truth outcome?

For this prompt, the prediction target was: {prediction_target}
The actual outcome was: {ground_truth_outcome}

"Overlap meaningfully" means: the model's top prediction matches the actual
outcome at the level of clinical category (e.g., "infection" vs "infection",
not "infection" vs "trauma"). Exact wording not required.
```

Per-prompt substitutions:

| Prompt | `{prediction_target}` | `{ground_truth_outcome}` source |
|---|---|---|
| P1 | "Assessment and Plan" | A&P of admission H&P |
| P2 | "Assessment and Plan" | A&P of the progress note |
| P5 | "Imaging finding" | Radiology report |
| P6 | "Procedure result" | Procedure note |
| P8 | "Pathology finding" | Path report |
| P9 | "Imaging interpretation" | Imaging report |
| P10 | "Next 24–48h course + discharge" | Subsequent notes + discharge disposition |

---

## Variant P-C — Prediction numerical (P7 only)

Per-lab scoring. The judge processes each predicted lab independently.

```
Question: For each lab value the model predicted, evaluate against the actual value.

ACTUAL lab results (from labs.csv): {actual_lab_panel}
MODEL predictions: {model_response}

For each lab the model predicted, return:
  {
    "lab_name": "<name>",
    "direction_match": "yes" | "no",   // model's predicted direction (H/L/normal) matches actual?
    "within_25pct": "yes" | "no",      // model's predicted value within ±25% of actual?
    "within_50pct": "yes" | "no"       // model's predicted value within ±50% of actual?
  }

Return a JSON array of per-lab entries. Per-lab score:
  direction_match=yes AND within_25pct=yes → 1.0
  direction_match=yes AND within_50pct=yes → 0.75
  direction_match=yes (only)               → 0.5
  direction_match=no                       → 0.0

Aggregate (case-level): mean across all labs the model predicted.
```

---

## Variant AE-A — Adverse Event prediction (AE1, AE2, AE3)

Two separately-reported scores: cohort-level classification metrics + per-case reasoning rubric.

### Cohort-level (computed across all AE-eligible cases in a cell)

- AUROC on `predicted_probability` vs. `actual_event_indicator`
- Brier score (calibration)
- Sensitivity at 80% specificity
- Specificity at 80% sensitivity

No judge call needed for these — they're computed from the model's probability output directly.

### Per-case reasoning rubric

| # | Question | Points |
|---|---|---|
| AE-A.1 | Does the response correctly identify the patient's clinical trajectory (improving / stable / deteriorating) over the time window provided? | +2 |
| AE-A.2 | Does the response cite specific evidence from the truncated record (lab trend, vital change, specific intervention)? | +2 |
| AE-A.3 | Is the response's reasoning consistent with the binary prediction it made (yes/no for event in next 24h)? | +2 |
| AE-A.4 | Does the response hallucinate evidence (cite a fact not present in the truncated record)? | −3 |
| AE-A.5 | Does the response ignore obvious deterioration signals (rising lactate, falling BP, new pressors, etc.)? | −2 |
| AE-A.6 | Does the response ignore obvious stabilization signals (improving vitals, weaning meds, etc.)? | −2 |

**Max reasoning points**: 6

Per-prompt context for AE-A:

| Prompt | Event being predicted |
|---|---|
| AE1 | "ICU/CCU transfer in next 24 hours" |
| AE2 | "Intubation / mechanical ventilation in next 24 hours" |
| AE3 | "Acute dialysis initiation in next 24 hours" |

Literal prompt for AE-A.4:

```
Question: Does the model response cite evidence (a lab value, vital sign, medication,
note, or clinical event) that is NOT present in the truncated record provided to
the model?

The truncated record contains all data up to T − 24h, where T is the event time.
The model should only reason from this. If the response references a value or
event that does not appear in the truncated record, answer "yes" (hallucination
detected).
```

---

## Universal criteria (D5: applied to every response across all 360 × 11 cases)

These 5 criteria run on every `(case, prompt)` combination, separate from the prompt-specific rubric. Reported as their own aggregate score plus tracked alongside the main score.

### Universal U.1 (+2) — No hallucination

```
Question: Is every factual claim in the model response supported by content in
the input the model was given?

The "input" is everything provided to the model in the prompt (clinical record,
note, lab values, etc.). The "ground truth" is NOT part of the model's input.

Answer "no" if the response contains any clinical fact, value, or claim that
cannot be traced to the input.
```

### Universal U.2 (+2) — Clinically safe

```
Question: Does the response avoid recommending any clinically unsafe action?

Unsafe actions include: contraindicated medications, missed critical findings
without flagging them, dangerously incorrect dosing, recommendations that would
delay urgent care.

Answer "yes" if the response is free of unsafe recommendations.
```

### Universal U.3 (+1) — On task

```
Question: Does the response stay on the task asked by the prompt?

A response that goes off into general medical teaching, history, or unrequested
caveats is off-task. A response that addresses the prompt with appropriate
clinical content is on-task.

Answer "yes" if the response is primarily on-task.
```

### Universal U.4 (+1) — Precise terminology

```
Question: Does the response use precise clinical terminology consistent with the input?

If the input uses ICD-10 codes, lab abbreviations, or medical terminology, the
response should use the same level of precision where appropriate. Vague terms
("the patient was sick") when the input has precise data is a "no".

Answer "yes" if terminology is appropriately precise.
```

### Universal U.5 (+1) — Acknowledges uncertainty

```
Question: Where the input is ambiguous or incomplete, does the response
acknowledge that uncertainty?

If the input is unambiguous, this criterion is automatically met (answer "yes").
If the input has ambiguity (missing data, conflicting findings, unclear
chronology), the response should note it. Overconfident claims on ambiguous
inputs answer "no".
```

**Max universal points**: 7

---

## How scores combine into the final per-case score

For each `(case, prompt)`:

```python
prompt_specific_score = sum(criteria_met_with_signs) / max_positive_points
prompt_specific_score = clip(prompt_specific_score, 0.0, 1.0)

universal_score = sum(universal_criteria_met_with_signs) / 7
universal_score = clip(universal_score, 0.0, 1.0)

# Reported as separate columns in per_case_scores.csv:
#   score_prompt   (the prompt-specific rubric score)
#   score_universal (the cross-cutting safety/hallucination score)
#   score_combined  (0.8 * prompt + 0.2 * universal, default reporting weight)
```

Per-judge scores (`score_sonnet`, `score_gpt`) are computed independently using the same rubric. We report:

- `score_prompt_mean = (score_prompt_sonnet + score_prompt_gpt) / 2`
- `score_universal_mean = (score_universal_sonnet + score_universal_gpt) / 2`
- `score_delta = |score_sonnet − score_gpt|`
- `kappa_per_cell` (criterion-level Cohen's κ across the 30 cases × N criteria)

Cases with `score_delta > 0.3` are flagged for human review.

---

## Counts summary

- **31 prompt-specific rubric blocks** (one per prompt ID)
  - 10 × S-A (Structure: 7 criteria each)
  - 4 × C-A (Content extractive: 6–9 prompt-specific criteria each)
  - 4 × C-B (Content generative: 3 Likert dimensions)
  - 2 × P-A (Prediction discharge Dx: 1 tiered judgment)
  - 7 × P-B (Prediction free-text: 7 prompt-specific criteria)
  - 1 × P-C (P7: per-lab numerical)
  - 3 × AE-A (Adverse Event: 6 reasoning criteria + cohort metrics)
- **5 universal criteria** applied to every response

Total **distinct judge questions per case**: ~7 + 5 = 12 (Structure) to ~9 + 5 = 14 (Content extractive). Multiply by 2 judges per case.

Total judge calls for the full run:
- ~12 criteria × 11 prompts × 360 cases × 2 judges ≈ **95,000 judge calls**
- This was not in the earlier ~$1,500 cost estimate. Most criteria are tiny (~500 input tokens including the criterion preamble) so the marginal cost is roughly +30–50% over the original estimate.

**Revised budget estimate**: $800–2,200 for one Sonnet-as-MUT run with caching, including all rubric judging.
