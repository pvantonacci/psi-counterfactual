# Prompt Selection Rationale — why these 5 of 31

Reference doc explaining why the v1 PSI eval ran 5 prompts (S1, S5, C1, C8, P7) out of Meta's full 31-prompt SOW.

Companion data file: [`code/engy_data_export/engy_prompt_selection_data.csv`](code/engy_data_export/engy_prompt_selection_data.csv) — one row per SOW prompt with all 4 readiness booleans + blocker count + observed scores for the 5 we ran.

---

## TL;DR

The SOW has 31 prompts. We ran 5. The 26 we didn't run aren't *rejected on quality grounds* — each is missing at least one piece of infrastructure that's required to score it end-to-end. **All gaps are engineering-time issues, not fundamental research problems.** The pilot was time-boxed; we built infrastructure for the 5 highest-priority prompts and the rest are scoped for v2.

---

## The 4 infrastructure pieces every prompt needs

To score a prompt end-to-end, four things must exist:

| Piece | What it does |
|---|---|
| **Rubric in `criteria.py`** | List of yes/no criteria with signed point values that judges grade against |
| **Renderer input support** | Code that assembles the right chart slice into the model's input |
| **Look-ahead truncation** | Hard-cut filtering so prediction prompts can't see the answer |
| **Ground-truth extraction** | Function that pulls the *right answer* from the chart for the judge to compare against |

The 5 v1 prompts have all 4 pieces built and validated. The 26 others are missing at least one.

---

## Where the gaps are — empirical readiness state

From introspecting `code/criteria.py` and `code/renderer.py`:

| Tier | Count | Prompts | What's missing |
|---|---|---|---|
| **A — Fully ready (ran in v1)** | 5 | S1, S5, C1, C8, P7 | Nothing |
| **B — Template rubric only (needs validation)** | 8 | S2, S3, S4, S6, S7, S8, S9, S10 | Per-section rubric calibration, look-ahead validation, GT extraction |
| **C — No rubric at all (un-scoreable)** | 18 | C2–C7, P1–P6, P8–P10, AE1–AE3 | Rubric + GT extraction + look-ahead truncation |

**Empirical signal**: of 31 SOW prompts, **18 raise `NotImplementedError` when you call `criteria.criteria_for(prompt_id)`**. They literally have no rubric to grade against.

---

## Why missing rubrics — gap-by-gap

A rubric requires three design decisions: (1) what counts as "correct"; (2) point values per criterion; (3) judge-validation that criteria are unambiguous. Each rubric is ~1–3 hours of work, more if domain expertise is needed.

### Missing rubrics — specific reasons per prompt

| Prompt | Why no rubric |
|---|---|
| **C2** (clinical annotation) | Needs decision on annotation scheme (span-level? entity-level?). Different schemes have different rubric shapes. |
| **C3** (differential diagnosis) | Open-ended output — multiple valid differentials exist. Needs a *plausibility* rubric, not an *exact-match* one. Much harder to design. |
| **C4** (drug interactions) | Needs a reference interaction database to grade against. Building the verifier is half the work. |
| **C5/C6/C7** (cardiology/oncology/nephrology) | Specialty-specific clinical knowledge required. Needs a specialist (or specialist-validated reference) to define correct specialty reasoning. |
| **P1** (next note type) | Structured outcome but requires defining "next" precisely — same calendar day? Same encounter? |
| **P2** (next medication) | Needs disambiguation: order vs administration vs prescribed-but-not-given. |
| **P3** (discharge diagnoses) | Multi-code output — rubric needs to handle "partial match" sensibly. |
| **P4** (30-day mortality) | Binary outcome, easy rubric — but requires joining encounter to outcome data we'd need to pull. |
| **P5** (readmission), **P6** (LOS) | Outcome-based, similar to P4. |
| **P8/P9/P10** | Each has prompt-specific definitional issues. |
| **AE1/AE2/AE3** (adverse events) | The rubric is essentially "did the model identify the PSI label correctly?" Re-uses Allison's label but needs prompt-shaping to make it scoreable as text generation (not classification). |

### S-family (S2–S4, S6–S10): template rubric exists but not validated

All 10 S-family prompts share a generic `s_a_criteria(section_name)` template — 6 criteria like "Does the response include ≥80% of the ground-truth section content?" The template *works mechanically* but has never been:

- Calibrated for the specific section (HPI vs PMH vs ROS — different content shapes)
- Pilot-tested to know if judges agree on it for that section
- Adjusted for section-specific failure modes (e.g., PMH lists where order matters; allergies where missing one is critical)

S1 and S5 are exceptions because we **validated the template on those specific sections** through the pilot. The other 8 would produce scores but with unknown reliability.

---

## Why missing ground-truth extraction — gap-by-gap

GT extraction is the function that pulls the *right answer* from the chart so the judge can compare the model's response against it. For each prompt, this means writing prompt-specific logic against the OMNY tables.

### What GT extraction looks like for the 5 we have

| Prompt | GT extraction logic | Code complexity |
|---|---|---|
| **S1** | Pull chief complaint from H&P CC section; fall back to HPI first sentence + reason-for-admission | ~100 lines |
| **S5** | Pull A&P section from H&P, parse section boundaries | ~50 lines |
| **C1** | Same as S5 plus structural mapping of problems → plans | ~80 lines |
| **C8** | Pull labs table for encounter, annotate reference ranges | ~30 lines |
| **P7** | Pull actual lab values at target specimen timestamp | ~50 lines |

### Why it doesn't exist for the others

| Prompt | GT extraction challenge |
|---|---|
| **S2** (HPI) | Free-text section — how strict? Exact match? Key-fact match? Each interpretation requires different extraction logic. |
| **S3** (PMH), **S4** (meds), **S6–S10** | Each is a different section with different structure, needs section-specific extraction. |
| **C3** (differential) | GT is **subjective** — the differential the clinician *should* have considered. Hard to extract from a chart that only documents the final diagnosis. |
| **P3** (discharge dx) | GT extraction needs to find the discharge ICD codes BUT ensure they don't leak into the input. Requires careful join logic. |
| **P4** (mortality), **P5** (readmission), **P6** (LOS) | Requires linking encounter to follow-up data (alive at 30 days? readmitted? actual LOS?). OMNY may not have this in scope; might need external mortality / readmission data joins. |
| **AE1** (identify event) | GT is the PSI label from Allison's pipeline — easiest of the unsolved, but requires re-shaping it from a binary label to a text-grading target. |

Effort per prompt: 30 minutes to several hours depending on join complexity.

---

## Why missing look-ahead bias protection

For prediction prompts, the input must contain *only* what was available before the prediction point. Anything later leaks the answer.

### What look-ahead protection looks like for P7

```python
cutoff_ts = target_specimen_ts - 1  # second
notes  = notes[notes['note_date'] < cutoff_ts]
labs   = labs[labs['specimen_ts'] < cutoff_ts]
vitals = vitals[vitals['vital_ts'] < cutoff_ts]
meds   = meds[meds['med_ts']   < cutoff_ts]
dx     = dx[dx['dx_date']      < cutoff_ts]
```

Validated by checking that none of 5 distinctive GT lab values appear in the rendered input — **result: 0/5 in context, clean.**

### Why the others need per-prompt work

Each prediction prompt needs its own cutoff rule + validation:

| Prompt | Truncation challenge |
|---|---|
| **P1** (next note type) | Cutoff at the time of the next note — but the *cutoff time itself* is information the model shouldn't have. Needs careful handling. |
| **P2** (next medication) | Cutoff at the next med order, plus exclude pre-orders or scheduled future orders in the prescription tables. |
| **P3** (discharge dx) | Cutoff at admission OR at a fixed time before discharge. Must remove the entire diagnoses table from the input (otherwise the answer is literally there). |
| **P4** (mortality) | Cutoff at admission or earlier; must remove death-related notes (e.g., expired notes, ICU EOL discussions) which sometimes have placeholder timestamps. |
| **P5–P10** | Each needs its own cutoff rule + leakage validation. |

### S-family: within-note truncation (different challenge)

S1/S5/C1 don't have a *time* truncation issue — instead they have a *section* truncation issue. For "extract A&P" prompts, the model is shown the H&P with the A&P section **redacted** so it has to identify it from context. This works for S1/S5/C1 (validated patterns) but for S2 (extract HPI) we'd need to mask the HPI specifically + decide what stays visible.

---

## Effort estimate to close the gaps

| Gap type | Effort per prompt |
|---|---|
| Missing specific rubric (S-family beyond S1/S5) | ~1 hour (template exists, needs section-specific calibration + validation) |
| Missing rubric for outcome-based prompts (P3/P4/P5/P6) | ~2 hours (clean structured verifier, just needs encoding) |
| Missing rubric for open-ended C-prompts (C3, C5/C6/C7) | ~4–8 hours (needs clinician input on what counts as correct) |
| Missing ground-truth extraction | ~1–3 hours per prompt (depends on whether GT exists in OMNY or needs external join) |
| Missing look-ahead truncation | ~2 hours per prompt (define cutoff + validate no leakage) |
| AE family (needs rubric + GT + truncation) | ~5–8 hours total per AE prompt |

**v2 timeline**: closing all 26 gaps end-to-end is roughly **50–80 hours of focused engineering + clinician consultation** for the specialty rubrics. Realistic 2–3 week project if prioritized.

---

## v2 priority order

If we had to rank the 26 by "v2 value per hour of work":

| Priority | Prompts | Rationale |
|---|---|---|
| **1 (highest)** | AE1–AE3 | Closes the verifier's-rule loop most directly — the PSI label IS the answer. Re-uses Allison's labeling work. |
| 2 | P3, P4 | Clean structured outcomes (discharge dx, mortality) — easy GT extraction, easy rubric, well-defined truncation. |
| 3 | P1 | Easy verifier (note type), low value but cheap. |
| 4 | C3 | Differential diagnosis is the most clinically interesting C-prompt; requires open-ended rubric design. |
| 5 | S2–S10 (batch) | Generic S-family template applies; batch-validate all together. |
| 6 (lowest) | C2, C4, C5/C6/C7 | Specialty-specific reasoning — highest domain-expertise lift, lowest overlap with PSI verification. |

---

## The honest summary for the meeting

> "We have 31 prompts in the SOW. Five of them (S1, S5, C1, C8, P7) had all 4 infrastructure pieces — rubric, renderer, look-ahead truncation, ground-truth extraction — built and validated through the pilot. The other 26 are missing at least one piece: 18 have no rubric at all, 8 share an unvalidated template rubric, and most prediction prompts need per-prompt truncation logic. None are rejected on quality grounds. The selection was an engineering-readiness decision, not a scientific one, and v2 is roughly 50–80 hours of focused work to close the remaining gaps."

---

## Where to find the supporting data

- **`code/engy_data_export/engy_prompt_selection_data.csv`** — one row per SOW prompt × 18 columns of readiness state and observed scores
- **`code/criteria.py`** — the rubric source (try `criteria.criteria_for("C3")` — it raises NotImplementedError, that's the evidence)
- **`code/renderer.py`** — the input + truncation source
- **`code/eval_output/analysis/RESULTS.md`** — the pilot's own results doc, confirming "Prompts tested: ['C1', 'C8', 'P7', 'S1', 'S5']"
- **`code/proj_bayes_prompt_selection.ipynb`** — interactive notebook with the same readiness analysis + heatmap visualization
