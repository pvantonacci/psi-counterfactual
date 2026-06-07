# Project Bayes — Prompts & Rubrics (v1)

All 5 prompts run in v1, with full rubrics and scoring logic.

---

## 0. The data

### Cohort

**145 real inpatient encounters**, drawn from three health systems:

| Health system |
|---|
| Northwell | 
| Ochsner | 
| St. Luke's |


**PSI labels:** 73 negative / 72 positive, across 16 PSI codes:
PSI-03, 04, 05, 06, 07, 08, 09, 10, 11, 12, 13, 14, 15, 17, 18, 19

**Case stratifiers:**

| Stratifier | Values |
|---|---|
| `COMPLEXITY_TIER` | easy / medium / hard / meta-hard (bucketed from Protege Complexity Score) |
| `LOS_BUCKET` | short (3–4d) / medium (4–6d) / long (7+d) |
| `PROTEGE_SCORE` | raw continuous complexity score |

### How cases were labeled (Allison's PSI pipeline)

Three-stage pipeline upstream of this bundle:

1. **ICD-10 regex on claims** — flags encounters with PSI-relevant codes
2. **Regex on note text** — secondary signal from clinical narrative
3. **Claude chart review** — high-confidence curation pass to resolve ambiguous cases

Output: `data/psi_inpatient_cases_downsampled.csv` (163 rows) → filtered to `data/eval_cases_psi.csv` (145 rows).

### Source tables

Nine tables feed the renderer:

| Table | Contents |
|---|---|
| `encounters.csv` | Admission/discharge dates, LOS, health system |
| `notes_concatenated.csv` | Clinical notes (H&P, progress, consult, discharge, etc.) |
| `labs.csv` | Lab results with reference ranges and abnormal flags |
| `vitals.csv` | Vital signs |
| `diagnoses.csv` | ICD-10 diagnoses |
| `procedures.csv` | Procedure codes |
| `prescription_orders.csv` | Medication orders |
| `prescription_administrations.csv` | Medication administrations |
| `problem_lists.csv` | Active problem lists |

### Known data quality issues (mitigated in renderer)

| Issue | Mitigation |
|---|---|
| Multi-supplier duplicate rows (same note 3–5×) | Row-level dedup in renderer |
| Duplicate paragraphs within a single note cell | Line-level dedup |
| Sentinel/placeholder dates (Jan 1 timestamps) | Filter notes dated before `EN_START_DATE`; exclude discharge note types regardless of date |
| "Reason for Admission" field often contains process items, not true CC | S1 GT uses HPI primary sentence as primary source + REASON FOR ADMISSION as secondary |
| ~25% of H&P notes have no labeled CC section | HPI-first-sentence fallback (regex on "presents/complains/admitted/age-sex" patterns) |
| Pediatric/NICU notes use different NOTE_TYPE prefixes | Fallback chain: H&P adult → pediatric → NICU → generic H&P → admission note |
| Narrative A&P written in ATTENDING COMMENTS (not A&P section) | Regex redaction on plan-language patterns when within-note masking is active |

---

## How scoring works

Every `(case, prompt)` pair produces two scores:

- **Prompt-specific score** — rubric below for each prompt  
- **Universal score** — 5 cross-cutting criteria applied to every response (section 7)

```
score_prompt   = clip(sum_of_signed_points / max_positive_points, 0, 1)
score_universal = clip(sum_of_signed_points / 7, 0, 1)
score_combined  = 0.8 × score_prompt + 0.2 × score_universal
```

Judges: **Claude Sonnet 4.6** and **GPT-5.4-mini**, independent calls per criterion.  
Final score = mean across judges.

---

## Judge preamble (sent before every criterion)

```
You are a clinical evaluator scoring a medical AI model's response against a rubric.
The model was given a specific clinical task and produced a response. You must judge whether the response meets a specific criterion.

Be strict but fair. Base your judgment ONLY on the source material and the response provided. Do not penalize for stylistic choices unless the criterion explicitly
addresses style. If the criterion is ambiguous in this case, default to "no".

Return your answer as JSON in this exact format:
{"answer": "yes" | "no", "rationale": "<one sentence>"}
```

---

## 1. S1 — Chief Complaint Extraction

### Model prompt

```
System: You are a clinical AI assistant. Answer the question concisely based on the clinical record provided.

User:
Extract the chief complaint (or reason for admission) from the clinical note(s) below.
Return only the chief complaint text.

---

[CLINICAL RECORD — single admission H&P note]
```

### Input to model
Single admission H&P note. No truncation needed (extraction only, answer is in the note).

### Rubric (S-A variant, section = "Chief Complaint") — max 10 pts

| ID | Points | Question |
|---|---|---|
| S-A.1 | +5 | Does the response contain ≥ 80% of the key facts from the ground-truth Chief Complaint? (paraphrasing allowed) |
| S-A.2 | +3 | Does the response contain ≥ 50% of the key facts from the ground-truth Chief Complaint? |
| S-A.3 | +2 | Does the response include the single most important fact from the Chief Complaint? |
| S-A.4 | +3 | Is every clinical claim traceable to the source material? |
| S-A.6 | **−5** | Does the response contain a clinical fact NOT in the source? (hallucination) |
| S-A.7 | **−2** | Does the response omit a clinically critical fact from the ground truth? |

### v1 mean scores
| Claude Opus 4.7 | GPT-5.5 | n |
|---|---|---|
| 0.437 | 0.466 | 116 |

---

## 2. S5 — Assessment & Plan Extraction

### Model prompt

```
System: You are a clinical AI assistant. Answer the question concisely based on the clinical record provided.

User:
Extract the Assessment and Plan section from the clinical note below.
Return the A&P text verbatim or as closely as possible.

---

[CLINICAL RECORD — single admission H&P note]
```

### Input to model
Single admission H&P note. No truncation.

### Rubric (S-A variant, section = "Assessment and Plan") — max 10 pts

| ID | Points | Question |
|---|---|---|
| S-A.1 | +5 | Does the response contain ≥ 80% of the key facts from the ground-truth Assessment and Plan? |
| S-A.2 | +3 | Does the response contain ≥ 50% of the key facts from the ground-truth Assessment and Plan? |
| S-A.3 | +2 | Does the response include the single most important fact from the A&P? |
| S-A.4 | +3 | Is every clinical claim traceable to the source material? |
| S-A.6 | **−5** | Does the response contain a clinical fact NOT in the source? (hallucination) |
| S-A.7 | **−2** | Does the response omit a clinically critical fact from the ground truth? |

### v1 mean scores
| Claude Opus 4.7 | GPT-5.5 | n |
|---|---|---|
| 0.292 | 0.316 | 116 |

---

## 3. C1 — Assessment & Plan Summary

### Model prompt

```
System: You are a clinical AI assistant. Answer the question concisely based on the clinical record provided.

User:
Summarize the Assessment and Plan from the admission H&P below. Cover all problems
and their plans. Specify the date of the note. Limit your summary to that note only.

---

[CLINICAL RECORD — single admission H&P note]
```

### Input to model
Single admission H&P note. No truncation.

### Rubric (C-A variant) — max 10 pts

| ID | Points | Question |
|---|---|---|
| C1.1 | +3 | Does the response identify ALL problems documented in the source A&P? |
| C1.2 | +2 | Does the response identify the primary or most-active problem from the source A&P? |
| C1.3 | +2 | For each identified problem, does the response include the documented treatment plan? |
| C1.4 | +1 | Does the response preserve key clinical reasoning from the source (not just a bullet list)? |
| C1.5 | +1 | Does the response include medication names where the source mentions them? |
| C1.6 | +1 | Does the response include disposition or next-step information where the source documents it? |
| C1.7 | **−3** | Does the response add a problem NOT present in the source A&P? |
| C1.8 | **−2** | Does the response omit a problem documented in the source A&P? |
| C1.9 | **−1** | Does the response add non-source content (general medical teaching, padding)? |

### v1 mean scores
| Claude Opus 4.7 | GPT-5.5 | n |
|---|---|---|
| 0.260 | 0.279 | 116 |

---

## 4. C8 — Lab Interpretation

### Model prompt

```
System: You are a clinical AI assistant. Answer the question concisely based on the clinical record provided.

User:
Summarize the lab results below. Identify which values are abnormal and, for each
abnormal result, describe what clinical action or follow-up order would be appropriate.

---

[LAB RESULTS — all labs for the encounter, no time cutoff]
```

### Input to model
All labs for the encounter (no time truncation). Labs only — notes not included.

### Rubric (C-A variant) — max 12 pts

| ID | Points | Question |
|---|---|---|
| C8.1 | +3 | Does the response correctly flag ≥ 80% of the actually-abnormal values? |
| C8.2 | +2 | Does the response correctly flag ≥ 50% of the actually-abnormal values? |
| C8.3 | +2 | For each flagged abnormal, is the clinical context correct? |
| C8.4 | +2 | For each flagged abnormal, is the suggested follow-up action appropriate? |
| C8.5 | +3 | Does the response identify any critical/panic value if present in the labs? |
| C8.6 | **−1** | Does the response flag a normal value as abnormal? |
| C8.7 | **−3** | Does the response miss a critical/panic value? (K+ <2.5 or >6.5, Na <120 or >160, glucose <40 or >500, INR >5, or source-flagged critical) |
| C8.8 | **−2** | Does the response suggest an inappropriate or unsafe action? |

> **Design note (D2):** C8.7 critical-miss penalty was set to −3 (not −5). Rationale: −5 caused floor effects on cases with multiple critical labs where the model missed one; −3 preserves the strong signal without collapsing the score distribution.

### v1 mean scores
| Claude Opus 4.7 | GPT-5.5 | n |
|---|---|---|
| **0.454** | 0.422 | 144 |

*Opus outperforms GPT-5.5 on this prompt — the only reversal across the 5.*

---

## 5. P7 — Predict Next Lab Panel

### Model prompt

```
System: You are a clinical AI assistant. Answer the question concisely based on the clinical record provided.

User:
A lab panel has been ordered for this patient. Based on the clinical context (notes,
prior labs, vitals, meds), predict the values of the next lab panel. For each lab
predicted, give name, value, units, and whether you expect it to be high / low /
within reference.

---

[CLINICAL RECORD — all tables truncated to strictly before target specimen timestamp]
```

### Input to model
All tables (notes, labs, vitals, meds, diagnoses, procedures) cut off at `specimen_ts − 1 second`. Six-layer look-ahead protection:
1. Target = first ≥10-lab panel ≥6h post-admission
2. Hard cutoff at `specimen_ts − 1s` across all 6 tables
3. Sentinel-date filter (drops Jan-1 placeholder timestamps)
4. Discharge note exclusion (regex on note title)
5. Admit-date floor (drops anything before `EN_START_DATE`)
6. Post-patch: extended discharge regex catches DISCHARGE SUMMARY / INSTRUCTIONS / PLANNING

### Rubric (P-C variant) — max 2 pts

| ID | Points | Question |
|---|---|---|
| P-C.1 | +1 | Does the model's predicted direction (H/L/normal) match actual direction for >50% of predicted labs? |
| P-C.2 | +1 | Are the model's predicted numeric values within ±25% of actual for >50% of predicted labs? |
| P-C.3 | **−1** | Does the model predict (hallucinate) labs not actually drawn in the ground-truth panel? |

### v1 mean scores
| Claude Opus 4.7 | GPT-5.5 | n |
|---|---|---|
| 0.165 | 0.190 | 77 |

*n=77 (not 145): ~18% of cases had no qualifying ≥10-lab panel ≥6h post-admit.*  
*Known issue: ~30–40% of target panels were urinalysis; models predicted serum chemistry → direction-match scored 0.*

---

## 6. Score comparison across prompts

| Prompt | Task type | Opus 4.7 | GPT-5.5 | Max pts |
|---|---|---|---|---|
| S1 | Extract CC | 0.437 | 0.466 | 10 |
| S5 | Extract A&P | 0.292 | 0.316 | 10 |
| C1 | Summarize A&P | 0.260 | 0.279 | 10 |
| C8 | Interpret labs | **0.454** | 0.422 | 12 |
| P7 | Predict lab panel | 0.165 | 0.190 | 2 |

Scores are mean across 3 judges, mean across cases, clipped to [0, 1].  
Inter-judge Cohen's κ (Sonnet 4.6 ↔ GPT-5.4-mini): **0.51** (moderate agreement, above 0.4 bar).

---

## 7. Universal criteria (applied to every response, every prompt)

Max 7 pts. Reported separately as `score_universal`. Weight in combined score: 20%.

| ID | Points | Question |
|---|---|---|
| U.1 | +2 | Is every factual claim supported by content in the model's input? |
| U.2 | +2 | Does the response avoid recommending any clinically unsafe action? |
| U.3 | +1 | Does the response stay on the task asked by the prompt? |
| U.4 | +1 | Does the response use precise clinical terminology consistent with the input? |
| U.5 | +1 | Where the input is ambiguous, does the response acknowledge uncertainty? (auto-pass if input is unambiguous) |

---

## 8. Why these 5 prompts (of 31)

Every prompt needs 4 infrastructure pieces to be scoreable:

| Piece | Description |
|---|---|
| Rubric | Criteria with signed point values |
| Renderer input | Code that assembles the right chart slice |
| Look-ahead truncation | Hard-cut filtering for prediction prompts |
| Ground-truth extraction | Function that pulls the right answer from the chart |

These 5 have all 4 built and validated. The remaining 26 are missing at least one — 18 raise `NotImplementedError` in the codebase. All gaps are engineering-time issues, not fundamental research problems. V2 closes the gaps in ~50–80 hours.

**V2 priority order:** AE1–AE3 (PSI label IS the answer) → P3/P4 (discharge Dx, mortality) → C3 (differential Dx) → S2–S10 batch → C-family specialty prompts.
