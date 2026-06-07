# Truncation & Look-Ahead Bias — by Prompt

Reference doc explaining how each of the 5 v1 prompts handles look-ahead bias and input truncation. **The risk per prompt depends on whether the prompt is predicting something** (P7 = high risk; C8 = no risk; S1/S5/C1 = within-note risk).

For each prompt: what it asks, what's in the input, what protections are applied, and why.

---

## S1 — Extract Chief Complaint

> *Extract the chief complaint (or reason for admission) from the clinical note(s) below. Return only the chief complaint text.*

### What's in the input
- **One single note**: the encounter's H&P (or fallback to earliest progress note if no H&P exists)
- No labs, vitals, meds, or diagnoses tables — just that one note's text

### Truncation applied
- **`render_single_note(encounter_id, target_note_id, loader)`** — pulls only the rows for the selected `NOTE_ID`
- **`select_target_note(encounter_id, "h&p adult", loader)`** — picks the earliest note matching the H&P pattern (with fallbacks: `H&P`, `Admission Note`, `Progress Note`, short codes `HP/PN/ED/DS`)
- No time-cutoff applied — the H&P typically contains the CC right at the top, so within-note structure is the only relevant boundary

### Look-ahead bias risk
**Low.** S1 is asking the model to *find* something already documented in the H&P, not predict anything. The ground truth (chief complaint text) is *supposed* to be visible in the input — that's the task. The judges grade whether the model correctly identified the right span.

### Ground truth source
- Parsed from the H&P's `CC` section + HPI's first sentence + `Reason for Admission` field
- Uses the **text-based section parser** (regex on `NOTE_TEXT` for headers like "Chief Complaint:", "Reason for Admission:", "@SUBJNOHEADERBEGIN@")

---

## S5 — Extract Assessment & Plan

> *Extract the Assessment and Plan section from the clinical note below. Return the A&P text verbatim or as closely as possible.*

### What's in the input
- Same as S1: **one single note** (the encounter's H&P)
- No labs, vitals, meds, or diagnoses

### Truncation applied
- Same single-note selection as S1
- **No A&P section redaction** — the A&P stays visible in the input (the task is to *extract* it, so showing it is the input)

### Look-ahead bias risk
**Low.** Same reasoning as S1 — this is an extraction task, not a prediction task. The A&P section *should* be visible; the model's job is to identify and return it cleanly.

### Ground truth source
- Parsed from the H&P's `A&P`, `Assessment`, or `Plan` section
- Text-based section parser handles variations: "Assessment and Plan", "A&P:", "A/P:", "Assessment/Plan", `@SUBJNOHEADERBEGIN@` markers
- For S1/S5/C1, the GT extraction uses the same parser as `extract_section_text()` — but pulls from the note's text directly

---

## C1 — Summarize Assessment & Plan

> *Summarize the Assessment and Plan from the admission H&P below. Cover all problems and their plans. Specify the date of the note. Limit your summary to that note only.*

### What's in the input
- **One single note**: the encounter's H&P
- No labs, vitals, meds, or diagnoses (same as S1/S5)

### Truncation applied
- Same single-note selection as S1/S5
- **No section masking** — the A&P stays visible (the task is to summarize what's there, not extract verbatim)

### Look-ahead bias risk
**Low.** Summarization of explicitly-documented content, not prediction. The judges grade for:
- All problems from the A&P covered
- Primary problem identified correctly
- Plans aligned with problems
- No hallucinated problems
- Note date specified

### Ground truth source
- Same as S5: the H&P's A&P section, parsed via the text-based section parser

---

## C8 — Lab Interpretation

> *Summarize the lab results below. Identify which values are abnormal and, for each abnormal result, describe what clinical action or follow-up order would be appropriate.*

### What's in the input
The **full encounter dump** — every table flows through:

| Table | What's included |
|---|---|
| Encounter header | Demographics, admission/discharge timestamps |
| `notes` | All notes, all sections, all timestamps |
| `diagnoses` | All ICD-10 codes for the encounter |
| **`labs`** | **All lab specimens, all values, all reference ranges** (this is the focus) |
| `vitals` | All vital signs |
| `meds` | All medication orders |

### Truncation applied
- **`TruncationSpec()`** — default/empty spec
- **No time cutoff** — labs from any point in the encounter are visible
- **No section masking** — full chart visible
- **No note-type exclusion** — discharge summaries, death notes, etc. all included (they're useful context for retrospective lab interpretation)

The only filtering inside each table is **deduplication** (multi-supplier repeats, within-cell paragraph repeats) — not bias-prevention truncation.

### Look-ahead bias risk
**None.** C8 is a *retrospective interpretation* task, not a prediction. The model is asked to read what's already documented and identify what's clinically significant. There's no "answer" to hide — the abnormal labs the model is supposed to flag are *the same labs visible in the input*.

### Ground truth source
- `extract_ground_truth("C8")` queries the `labs.csv` `LB_ABN_RESULT` column for rows flagged: `["H", "L", "HH", "LL", "CRITICAL", "ABNORMAL", "A"]`
- The GT is the structured list of all-flagged-abnormal labs (with values + reference ranges)
- This is what the rubric grades the model's response against — did it correctly flag the same labs the lab system already flagged?

### Why C8 has the largest inputs in the run
Because C8 is the only prompt that dumps the entire chart (notes + labs + vitals + meds + diagnoses + encounter header) with no time filtering. For complex multi-day inpatient stays, this can mean 100K+ input tokens (e.g., Case #1 D6C0514E: 240K tokens).

---

## P7 — Predict Next Lab Panel

> *A lab panel has been ordered for this patient. Based on the clinical context (notes, prior labs, vitals, meds), predict the values of the next lab panel.*

### What's in the input
Same full encounter dump as C8 — **but with everything hard-cut at the target specimen timestamp**.

### Look-ahead bias risk
**Highest of the 5 prompts.** P7 is the only true prediction task. If anything in the input shows what the next lab panel will be, the task collapses to copy-paste.

### Multi-layer protection — six filters stacked

#### Filter 1 — Target specimen selection (eligibility)

`_select_p7_target_specimen()` picks the lab panel to predict:

```
admit_ts = encounter EN_START_DATE
candidates = labs WHERE specimen_ts >= admit_ts + 6 hours      ← skip immediate post-admit draws
grouped = group by specimen timestamp
target = first panel WHERE len(panel) >= 10 labs                ← real venipuncture only, no fingersticks
```

Two constraints:
- **`skip_hours = 6`** — at least 6 hours after admission. Avoids predicting admit-time bloodwork (clinicians order standard panels at admit, so it's trivially predictable).
- **`min_panel_size = 10`** — must be a real venipuncture panel with ≥ 10 distinct labs at the same timestamp. Per Allison's feedback — no scoring against single fingersticks or BG checks.

If no qualifying panel exists for the encounter, P7 returns `""` → recorded as `error="empty render"`. About **18% of P7 attempts** error this way.

#### Filter 2 — Hard timestamp cutoff (the core protection)

```python
cutoff_ts = target_specimen_ts - timedelta(seconds=1)
```

Strict-before-the-draw: subtracting 1 second guarantees the target specimen *itself* never appears in the input.

#### Filter 3 — Apply cutoff to EVERY encounter table

Inside `_render_notes`, `_render_labs`, `_render_vitals`, `_render_meds`, `_render_diagnoses`:

```python
if truncation.cutoff_ts is not None:
    df = df[df["TS"] <= truncation.cutoff_ts]
```

Per Allison's design note: *"the cutoff must apply to ALL context types — otherwise lab values drawn later in the encounter can leak into the input."*

#### Filter 4 — Sentinel-date filter (belt-and-suspenders)

OMNY uses **Jan-1-at-midnight as a placeholder timestamp** for ~4% of notes (when the real time isn't known). Without this filter, a discharge summary with sentinel date `2022-01-01 00:00:00` would pass `cutoff_ts <= 2022-XX-XX` for any later target specimen.

```python
sentinel_mask = (
    df["TS"].dt.month.eq(1) & df["TS"].dt.day.eq(1) &
    df["TS"].dt.hour.eq(0) & df["TS"].dt.minute.eq(0) & df["TS"].dt.second.eq(0)
)
df = df[~sentinel_mask]
```

#### Filter 5 — Discharge-note pattern exclusion

Even when timestamps fail, the *type* of note is a clue. Discharge summaries, death notes, etc. shouldn't be in the input regardless of when they're dated:

```python
discharge_pattern = r"\bDISCHARGE\b|DEATH NOTE|EXPIRED PATIENT|DECEASED|DISPOSITION"
df = df[~df["NOTE_TYPE"].fillna("").str.upper().str.contains(discharge_pattern)]
```

Catches: `DISCHARGE NOTE`, `DISCHARGE SUMMARY`, `DISCHARGE INSTRUCTIONS`, `DISCHARGE PLANNING`, `DEATH NOTE`, `EXPIRED PATIENT`, `DECEASED`, `DISPOSITION`. (Broadened during the audit — original regex missed `SUMMARY/INSTRUCTIONS/PLANNING` variants.)

#### Filter 6 — Admit-date filter (catches pre-admission sentinel dates)

```python
df = df[df["TS"] >= admit_ts - timedelta(days=1)]
```

Drops notes timestamped before admission (sentinel dates that fall in earlier years are silently dropped).

### Ground truth source

`extract_ground_truth("P7")` returns the **actual lab values at the target specimen timestamp** — the panel rows the model is being asked to predict.

### How we validated zero leakage

Picked 5 distinctive `(lab_name, value)` combos from the GT panel and grep'd the rendered input for them:

**Result: 0 of 5 GT values appeared in the rendered input.**

After patching filters 4 + 5 during the audit, we re-verified on the 10 previously-leaking cases — **0 of 10 had any discharge section headers** in their rendered output post-patch.

### Honest residual concern

For *stable physiology* (sodium at admission = sodium at target = 138), the model can copy the most-recent prior value and trivially predict. That's not a "leak" — it's the lab's actual trajectory — but it means P7 scores aren't a perfect frontier test on every case. v2 P7 should pick target specimens where the predicted values *differ* from the most recent prior values, specifically to test trajectory prediction.

---

## Summary table

| Prompt | What's in input | Time cutoff | Section masking | Look-ahead risk | GT source |
|---|---|---|---|---|---|
| **S1** | 1 note (H&P) | None | None | Low — extraction task | H&P CC + HPI first sentence + Reason for Admission |
| **S5** | 1 note (H&P) | None | None | Low — extraction task | H&P A&P section (text-parsed) |
| **C1** | 1 note (H&P) | None | None | Low — summarization task | H&P A&P section (text-parsed) |
| **C8** | Full encounter (all tables) | None | None | None — retrospective interpretation | Abnormal labs from `LB_ABN_RESULT` column |
| **P7** | Full encounter, **hard-cut at target specimen** | `target_specimen_ts - 1s` | None | **High — prediction task** | Actual lab values at target specimen |

## Key insight on the design

**Look-ahead truncation is only needed for prediction prompts.** Extraction (S1, S5) and interpretation (C1, C8) tasks ask the model to identify or summarize what's already documented — the "answer" is supposed to be visible in the input. The judges grade *how well* the model found it, not whether the model can predict the unknown.

P7 is the only prompt in the v1 set that requires the look-ahead protection stack. The 6-layer filtering reflects how many ways a lab value could leak through a chart that wasn't designed for prediction-eval rigor.
