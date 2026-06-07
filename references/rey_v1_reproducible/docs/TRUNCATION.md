# Truncation — Project Bayes Inpatient EHR Benchmark

How we prevent the answer from leaking into the model's input. Companion to `EVAL_SOW.md`, `RENDERER_DESIGN.md`, and `PROMPT_FRAMEWORK.md`.

---

## The core principle

A benchmark only measures what the model can *infer*. If the answer is sitting in the input — directly, indirectly, or buried in a downstream note that references it — we are measuring retrieval, not reasoning. **The job of truncation is to remove the answer from the input while preserving everything the model would have legitimately had access to at prediction time.**

In real clinical workflow, a clinician at hour T does not have access to:
- Notes written after T
- Lab results that haven't been collected yet
- Imaging reports for studies that haven't been performed yet
- Diagnoses entered later in the chart
- Sections of the current note the clinician hasn't written yet (e.g., the A&P when they're still on HPI)

Truncation simulates this temporal information boundary. There are two distinct mechanisms, because the "answer" can leak from two distinct places.

---

## Why two types of truncation

The answer to a benchmark prompt can be hidden in two different places in the EHR:

1. **In another section of the same note.** A note has internal structure (CC → HPI → PE → Labs → A&P). If we're testing "predict the plan given the story," we cannot show the model the section that contains the plan.

2. **In a later note or result.** A hospitalization unfolds over days. The discharge diagnosis, the imaging finding, the lab result, the adverse event — all are documented in the record *after* they happen. If we're testing "predict what will happen," we cannot show the model anything written after the prediction point.

These leakage modes operate on different axes — one within a single document, the other across the timeline — and they require **two different code paths** in the renderer.

| | Within-note truncation | Time-based truncation |
|---|---|---|
| Scope | One note | All notes + structured data |
| Key column(s) | `NOTE_TEXT` content within a single `NOTE_ID` (or section metadata) | `NOTE_DATE`, `LB_SPECIMEN_DATE`, `PX_SERVICE_DATE`, `RX_ORDER_DATE`, `AD_ADMIN_DATE` |
| Used by | P1, P2, C2 | P4, P5, P6, P7, P8, P10, AE1–AE3 |
| Failure mode if skipped | Model copies the A&P verbatim from the input | Model "predicts" using future evidence |

A prompt may need **both** — e.g., a P4 that has a time cutoff *and* a progress note straddling the cutoff that needs its A&P section trimmed.

---

## Within-note truncation

### When it is necessary

A clinical note follows a standard structure with a strong information gradient: the early sections describe the patient's story, the late sections record the clinician's interpretation and plan. If the task is "given the story, infer the plan," the plan section has to come out.

In OMNY's `notes.csv`, each note is split into **section rows** — one row per section, all sharing a `NOTE_ID`. The text of the section lives in `NOTE_TEXT`. To do within-note truncation, the renderer:

1. Loads all `notes.csv` rows for the relevant `NOTE_ID`.
2. Drops the rows whose section header matches the masked sections.
3. Reassembles the surviving rows into a single text block in the original section order.

### Per-prompt truncation specs

#### P1 — Predict A&P from admission H&P

The admission H&P contains:

```
CC          → "Chest pain, 3 hours, radiating to left arm."
HPI         → "65yo M with HTN, T2DM, prior CABG presents with..."
ROS         → "Negative except as in HPI."
PE          → "BP 152/88, HR 96, lungs clear..."
Labs        → "Troponin I 0.08 (peak 0.34)..."
Imaging     → "ECG shows ST depression V4–V6..."
A&P         → "1. NSTEMI — start heparin gtt, ASA + clopidogrel..."
```

The model under test sees: **CC + HPI + ROS + PE + Labs + Imaging**.
The model under test does NOT see: **A&P**.
Ground truth for grading: the actual A&P from the same `NOTE_ID`.

Render output to model:

```
=== Admission H&P — 2024-03-14 08:30 ===

CHIEF COMPLAINT
Chest pain, 3 hours, radiating to left arm.

HISTORY OF PRESENT ILLNESS
65yo M with HTN, T2DM, prior CABG presents with...

REVIEW OF SYSTEMS
Negative except as in HPI.

PHYSICAL EXAM
BP 152/88, HR 96, lungs clear...

LABS
Troponin I 0.08 (peak 0.34)...

IMAGING
ECG shows ST depression V4–V6...

[Assessment and Plan: PREDICT]
```

Truncation spec: `{"section_mask": ["A&P", "ASSESSMENT", "ASSESSMENT AND PLAN", "PLAN"]}`. The mask must include every variant header used in OMNY notes — we will need to enumerate these from `notes.csv` once at startup.

#### P2 — Predict A&P from progress note S+O

Progress notes follow a SOAP structure: **Subjective → Objective → Assessment → Plan**. P2 strips A and P, leaves S and O.

Render output to model:

```
=== Progress Note — Hospital Day 3 — 2024-03-17 07:15 ===

SUBJECTIVE
Patient reports chest discomfort improving overnight. Tolerating diet.

OBJECTIVE
Vitals stable. Telemetry: NSR, occasional PACs. Lungs CTA. Cardiac exam unchanged.
Labs: troponin trending down (0.21 → 0.14 → 0.09). BMP WNL.

[Assessment and Plan: PREDICT]
```

Truncation spec: `{"section_mask": ["A", "P", "ASSESSMENT", "PLAN", "A&P", "ASSESSMENT AND PLAN"]}`.

**Watch out**: some notes use combined "A/P" or "Assessment & Plan" headers — these must all be in the mask. A single missed variant leaks the answer.

#### C2 — Generate DDx + A&P from HPI only

C2 is stricter than P1. P1 lets the model see CC + HPI + PE + Labs + Imaging (everything that came before the A&P). C2 asks the model to generate a differential from the HPI *alone*, simulating the bedside reasoning a clinician does before completing the physical exam.

Render output to model:

```
=== Admission H&P (HPI only) — 2024-03-14 08:30 ===

CHIEF COMPLAINT
Chest pain, 3 hours, radiating to left arm.

HISTORY OF PRESENT ILLNESS
65yo M with HTN, T2DM, prior CABG presents with...

[Build a differential, assessment, and plan from the above.]
```

Truncation spec: `{"section_keep_only": ["CC", "HPI"]}` (or equivalently, mask everything else).

### Edge cases

1. **Combined section headers.** Some clinicians write "HPI/ROS:" or "A&P:" as a single combined header. Section-mask must use substring matching, not exact match.
2. **Sections without an explicit header.** Some notes embed the assessment in narrative text without a clean header. The renderer must skip those notes (or fall back to a heuristic last-paragraph drop) — flag these at run time so we can review.
3. **References to other sections.** A PE section that says "see HPI for further history" is fine. A Labs section that says "see A&P for interpretation" leaks intent. Build a redaction pass on cross-references during pilot.
4. **Free-text leakage of the diagnosis.** Even with A&P removed, the HPI may say "patient with known NSTEMI presents for further management." This is *not* a truncation problem — it's a fundamentally too-easy case. Flag it during sampling, not during render.

---

## Time-based truncation

### When it is necessary

If the prediction target is something that happens later in the hospitalization — a discharge diagnosis, an imaging result, a lab value, an adverse event — then everything documented after the prediction point is contamination.

In OMNY, every encounter-level table has a timestamp:

| Table | Timestamp column | What it records |
|---|---|---|
| `notes.csv` | `NOTE_DATE` | When the note was written |
| `labs.csv` | `LB_SPECIMEN_DATE` | When the specimen was collected |
| `vitals.csv` | `VITAL_DATE` (or similar) | When the measurement was taken |
| `prescription_orders.csv` | `RX_ORDER_DATE` | When the order was placed |
| `prescription_administrations.csv` | `AD_ADMIN_DATE` | When the med was administered |
| `procedures.csv` | `PX_SERVICE_DATE` | When the procedure was performed |
| `diagnoses.csv` | (no direct ts; tied to encounter window) | — |
| `encounters.csv` | `EN_START_DATE`, `EN_DC_DIS` | Admission and discharge |

The renderer's time-truncation filter is a simple predicate: `row.timestamp <= cutoff_ts`. Applied to every encounter-scoped table before any text is rendered.

### Per-prompt truncation specs

#### P4 — Predict discharge Dx from H&P + progress notes through day N

The signature use case for time-based truncation. For a patient admitted on `EN_START_DATE = 2024-03-14`:

| N | Cutoff timestamp | Notes included | Labs included | Procedures included |
|---|---|---|---|---|
| Day 2 | 2024-03-15 23:59:59 | H&P + day-1 + day-2 progress | All draws through day 2 | All procs through day 2 |
| Day 3 | 2024-03-16 23:59:59 | + day-3 progress | + day-3 draws | + day-3 procs |
| Day 4 | 2024-03-17 23:59:59 | + day-4 progress | + day-4 draws | + day-4 procs |

Each N is a separate render — the renderer is called once per `(case, N)`. Output: a discharge Dx prediction. Ground truth: `diagnoses.csv` row where `DX_PRIMARY` is true, taken from the final/discharge record.

Truncation spec: `{"cutoff_ts": "2024-03-15 23:59:59"}` (varying per N).

**Open question for the next sync**: do we evaluate at every N, or fixed points? Each N is one model call + 2 judge calls (~$0.30–0.80). For a 7-day stay that's 7 × 3 calls × 360 cases × (well, P4 only applies to M/H/MH). Adds up quickly. Recommendation: N ∈ {2, 3, 5, 7} for short stays, plus mid-stay and pre-discharge points for long stays.

#### P5 — Predict imaging finding from clinical context

For each imaging study in the patient's record, identify the order timestamp and truncate to just before the study.

Step 1 — Find imaging studies in `procedures.csv`:

```python
imaging = procedures[
    (procedures["PX_CODE"].between("70000", "79999"))
    & (procedures["ENCOUNTER_ID"] == case.ENCOUNTER_ID)
]
```

Step 2 — For each imaging study, set cutoff to `PX_SERVICE_DATE` minus 1 second.

Step 3 — Render everything ≤ cutoff. Hold out the radiology note that interprets this study (ground truth).

Render output to model (truncated to T_study − 1s):

```
=== Encounter ===
Hospital: Northwell Health
Admission: 2024-03-14 07:45
LOS so far: 2 days

=== Notes ===
[H&P + day-1 + day-2 progress notes up to 2024-03-16 14:00]

=== Labs ===
[Tabular labs up to 2024-03-16 14:00]

=== Imaging order ===
2024-03-16 14:00 — CT chest with contrast — clinical indication: rule out PE
```

The model predicts the report finding. Ground truth: the actual radiology note for that study.

Truncation spec: `{"cutoff_ts": <PX_SERVICE_DATE>, "exclude_ground_truth_note_id": <radiology_note_id>}`.

#### P6 — Predict procedure result

Same shape as P5 but anchored to procedure timestamp instead of imaging timestamp.

Identify candidate procedures:

```python
notable_procs = procedures[
    procedures["PX_HCS_DESC"].str.contains(
        "BIOPSY|CATHETER|ENDOSCOPY|BRONCHOSCOPY|TAP",
        case=False, regex=True
    )
]
```

Truncation spec: `{"cutoff_ts": <PX_SERVICE_DATE> - 1s, "exclude_ground_truth_note_id": <procedure_note_id>}`.

#### P7 — Predict lab results

Anchored to `LB_SPECIMEN_DATE`. Hold out the lab values themselves (not the order) — the order is part of the input.

Truncation spec: `{"cutoff_ts": <LB_SPECIMEN_DATE> - 1s, "exclude_lab_ids": [<lab_row_ids>]}`.

For multi-component panels (CBC, BMP), hold out all components drawn at the same specimen time.

#### P8 — Predict pathology

Anchored to specimen collection or order date for pathology. Same pattern as P6/P7.

#### P10 — Predict next 24–48h + full course

Open-ended forecast. Pick a cutoff (typically mid-stay), truncate everything past it, ask the model to describe what happens next.

Truncation spec: `{"cutoff_ts": <mid_stay_ts>}`.

Selection of cutoff: for cases with LOS ≤ 7d, use end of day 2 or 3. For longer cases, use end of day 5–7 (early enough that there's something to predict, late enough that there's enough context).

#### AE1–AE3 — Adverse event prediction

The hardest truncation to get right. Each AE has an event time T. The model sees everything up to **T − 24 hours** and must predict whether the event occurs in the next 24 hours.

Event detection (per the table README):

**AE1 (ICU transfer)** — three-source detection:
```python
icu_admin = prescription_administrations[
    prescription_administrations["AD_DEPT"].str.contains(
        "ICU|INTENSIVE CARE|CCU", case=False, regex=True
    )
]
icu_claims = claims_procedure[claims_procedure["REVENUE_CODE"].between("0200", "0219")]
icu_critcare = procedures[procedures["PX_CODE"].isin(["99291", "99292"])]
T_icu = min(icu_admin["AD_ADMIN_DATE"].min(),
            icu_claims["SERVICE_FROM"].min(),
            icu_critcare["PX_SERVICE_DATE"].min())
```

**AE2 (intubation)** — `procedures.PX_CODE` in `(94002, 94003, 94004, 31500)` or `PX_HCS_DESC` matching `MECHANIC.*VENTIL|INTUBAT`.

**AE3 (acute dialysis initiation)** — `prescription_orders.RX_GENERIC_NAME` matching `DIALYSIS|HEMODIALYSIS` or dialysis CPTs `(90935, 90937, 90945)`.

For each event, validate that `T - EN_START_DATE >= 24h`. Events at admission are excluded (the SOW calls these "not unexpected from the clinical record").

Truncation spec: `{"cutoff_ts": T - 24 hours}`.

The strict cutoff matters: a single nursing note at T − 12h saying *"patient deteriorating, rapid response called"* would invalidate the prediction. The renderer must filter on `timestamp <= T - 24h`, not `timestamp < T` or `date < T.date()`.

### Edge cases

1. **Time grain.** OMNY timestamps appear at day or finer resolution depending on table. If a lab was drawn at 08:00 and resulted at 10:00 on day 3, both rows have `LB_SPECIMEN_DATE = 2024-03-16` (date-level). Day-level truncation will leak the result if cutoff is "end of day 3." Use timestamp-level when available; explicitly note when falling back to date-level.

2. **Order-result pairs straddling the cutoff.** A CT ordered at T−2h with the report finalized at T+4h: the order is legitimately in the input (clinician ordered it before the cutoff), the report is not. The renderer must filter each row independently by its own timestamp, not by the parent order's timestamp.

3. **Retrospective addenda.** A note dated 2024-03-14 may have been addended on 2024-03-18 with text like "patient went on to develop septic shock." If OMNY records this as additional rows on `NOTE_ID = N4471` with later `NOTE_DATE`, time-truncation handles it correctly. If the addendum is appended to the original text in-place (no later timestamp), we have a leak. Audit notes table for this pattern during pilot.

4. **Notes that straddle the cutoff.** A progress note written at the very end of day 3 may contain a "Plan for day 4" section. The note's timestamp is day 3 (passes the cutoff), but the content references day 4. This is rare but real — recommend not handling it in v1, but flag cases during pilot review.

5. **AE event time identification disagreements.** The three ICU detection sources can disagree by hours. Use the earliest plausible timestamp as T. Sanity check: the patient should still be in the inpatient stay at T (i.e., `EN_START_DATE <= T <= EN_DC_DIS`).

6. **Encounters with multiple eligible AE events.** A patient who is intubated on day 3 and starts dialysis on day 5 has both AE2 and AE3 eligible. Render each independently with its own T.

---

## Per-prompt truncation reference

The SOW defines 31 prompts total (S1–S10, C1–C8, P1–P10, AE1–AE3). The benchmark runs 11 of these per case — selection varies by tier per the eligibility matrix in `EVAL_SOW.md`. This reference table covers the truncation spec for every prompt in the SOW, whether or not it's in the 11-prompt subset for any given case.

| Prompt | Truncation type | Spec (renderer arg) |
|---|---|---|
| S1–S10 | none | `truncation=None` |
| C1, C5, C6, C7, C8 | none | `truncation=None` |
| C2 | within-note | `{"section_keep_only": ["CC", "HPI"]}` |
| C3 | none (follows C2 output) | — |
| C4 | none | — |
| P1 | within-note | `{"section_mask": ["A&P", "ASSESSMENT", "PLAN", ...]}` |
| P2 | within-note | `{"section_mask": ["A", "P", "ASSESSMENT", "PLAN", "A&P", ...]}` |
| P3 | within-note | `{"section_keep_only_note_type": "Admission H&P"}` (no time cutoff; just take the H&P only) |
| P4 | time-based, rolling N | `{"cutoff_ts": <EN_START_DATE + N days>}` |
| P5 | time-based | `{"cutoff_ts": <PX_SERVICE_DATE - 1s>, "exclude": [radiology_note_id]}` |
| P6 | time-based | `{"cutoff_ts": <PX_SERVICE_DATE - 1s>, "exclude": [procedure_note_id]}` |
| P7 | time-based | `{"cutoff_ts": <LB_SPECIMEN_DATE - 1s>, "exclude": [<lab_ids>]}` |
| P8 | time-based | `{"cutoff_ts": <pathology_specimen_ts - 1s>, "exclude": [<path_note_id>]}` |
| P9 | none (raw image input only) | — (bypasses renderer entirely) |
| P10 | time-based | `{"cutoff_ts": <mid_stay_ts>}` |
| AE1 | time-based | `{"cutoff_ts": <T_icu - 24h>}` |
| AE2 | time-based | `{"cutoff_ts": <T_intubation - 24h>}` |
| AE3 | time-based | `{"cutoff_ts": <T_dialysis - 24h>}` |

---

## Implementation checklist

Before running any LLM calls, the renderer must:

1. ✅ Load all timestamp columns as actual datetime types (not strings).
2. ✅ Enumerate every section header variant in `notes.csv` (one-time scan of `NOTE_TEXT` headers) so the section_mask is comprehensive.
3. ✅ For AE prompts, compute T for every Hard / Meta Hard case and store as a sidecar table (`ae_events.csv` with columns `ENCOUNTER_ID, AE_TYPE, T_EVENT, T_MINUS_24H`).
4. ✅ Unit test: for each P-family prompt, assert the rendered output contains zero text from the ground-truth source.
5. ✅ Unit test: for each AE prompt, assert no row in the rendered output has timestamp > `T − 24h`.
6. ✅ Spot check 5 cases per prompt by hand before scaling to 360.

---

## Why this matters

The single biggest way a clinical benchmark fails is silent answer leakage. Once a benchmark is published, leakage shows up as "the model is brilliant on this benchmark and useless in deployment" — a credibility-destroying outcome. The two leakage modes covered here — within-note and time-based — are the two we know about up front. There are almost certainly more we'll find during pilot review. The discipline of forcing every prediction prompt through a renderer with an explicit truncation spec is what gives us a fighting chance of catching them before the benchmark goes out the door.
