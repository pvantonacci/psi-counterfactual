# Renderer Design — Project Bayes (Updated)

How patient data flows from filtered OMNY CSV tables into prompts the model under test sees. This doc is the current state of the implementation in `code/renderer.py` — replaces the original design speculation.

Companion docs:
- `EVAL_SOW.md` — case grid + prompt taxonomy
- `TRUNCATION.md` — per-prompt truncation specs
- `JUDGE_PROMPTS.md` — rubric criteria + judge prompt templates
- `RENDERER_STATUS.md` — what changed and verification snippets

---

## Philosophy

CSV is the source of truth. The renderer converts CSV slices into clinician-readable text per prompt. Three principles:

1. **Never feed structured CSV to the model.** Render to natural-language text matching what a clinician would read.
2. **The renderer is the only place truncation lives.** All "hide the answer" logic — section masking and time cutoffs — flows through one `render()` entry point.
3. **Ground-truth extraction is a separate function.** What the model sees and what the judges grade against come from the same source data but produce different artifacts.

---

## Architecture

```
┌─────────────────────────────────┐
│  tables/   (filtered OMNY CSV)  │   526MB labs.csv, 685MB notes.csv, etc.
│  - encounters.csv               │
│  - notes.csv                    │
│  - omny_notes_concatenated.csv  │
│  - labs.csv                     │
│  - vitals.csv                   │
│  - procedures.csv               │
│  - prescription_orders.csv      │
│  - prescription_administrations │
│  - diagnoses.csv                │
│  - eval_cases.csv  (360 cases)  │
└──────────────┬──────────────────┘
               │
               ▼  (one-time pre-filter)
┌─────────────────────────────────┐
│  cache/   (per-encounter parquet)│
│  <enc_id>_notes.parquet         │   2,876 files total
│  <enc_id>_labs.parquet          │   load time: ~0.1s per encounter
│  ...                            │   (vs ~30s scanning CSV)
└──────────────┬──────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────┐
│  EncounterDataLoader.load(enc_id)                       │
│    → dict of pd.DataFrames, one per table               │
│    Caches in memory; multiple render() calls            │
│    on the same case hit RAM, not disk                   │
└──────────────┬──────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────┐
│  render(encounter_id, prompt_id, truncation, ablation)  │
│                                                          │
│  1. Look up the prompt's default truncation             │
│  2. Apply within-note + time-based filters to each table │
│  3. Render each table to text per its formatter:        │
│     - Encounter header (LOS, demographics)              │
│     - Notes (grouped by NOTE_ID, sections labeled)      │
│     - Labs (markdown table)                             │
│     - Vitals (markdown table)                           │
│     - Medications (bulleted list)                       │
│     - Diagnoses (ICD-10 list)                           │
│  4. Concatenate → single text string                    │
└──────────────┬──────────────────────────────────────────┘
               │
               ▼
       Text passed to MUT
```

And in parallel:

```
extract_ground_truth(encounter_id, prompt_id, loader)
    → {"label": "...", "metadata": {...}}

Reads the same per-encounter data but extracts the answer artifact:
- S1 → CC text from the H&P
- S5 / C1 / P1 → A&P text from the H&P
- P3 / P4 → primary discharge diagnosis from diagnoses.csv
- P7 → the actual values of the held-out lab panel
- AE1/2/3 → the event timestamp + binary indicator
- ...etc
```

---

## OMNY data structure quirks (the things that surprised us)

These shaped most of the implementation. Worth documenting because anyone touching the renderer needs to know.

### 1. Sections live in `NOTE_TYPE`, not `NOTE_TEXT`

OMNY's `omny_notes_concatenated.csv` is one row per **(NOTE_ID, section)**, with the section name encoded in `NOTE_TYPE` after a `" - "` separator:

```
NOTE_TYPE                                    NOTE_TEXT
H&P ADULT - HISTORY OF PRESENT ILLNESS       "64yo M with HTN..."
H&P ADULT - ASSESSMENT                       "1. CAP — ceftriaxone..."
H&P ADULT - PHYSICAL EXAM                    "BP 152/88, HR 96..."
PROGRESS NOTE ADULT - SUBJECTIVE AND OBJECTIVE BOX  "Patient reports chest..."
PROGRESS NOTE ADULT - ASSESSMENT             "Continued NSTEMI..."
```

This is cleaner than parsing free-text headers — but it meant rewriting the original section classifier that assumed sections were embedded in note text.

### 2. "REASON FOR ADMISSION" replaces "CHIEF COMPLAINT"

Northwell H&Ps don't have a CC section. They have `H&P ADULT - REASON FOR ADMISSION` instead. The S1 rubric and section classifier both map this to the canonical "CC" label.

### 3. Notes are run-on paragraphs (no real newlines)

Section text inside `NOTE_TEXT` is one long stream with double-space separators, not line-broken text. Patterns that anchor to line start (`^`) or line end (`$`) miss most of the content. We use double-space lookarounds (`(?<=\s{2})...(?=\s{2,}|$)`) instead.

### 4. False-positive substring matching

Examples like `NSHPLANGLIMITEDENGLISH_GEN_A_CORE` (a language interpreter field) used to match "PLAN" via substring. The classifier now uses regex word boundaries and explicit pattern lists per section.

### 5. Pediatric and ASU-transfer cases lack a fresh H&P

- Pediatric admissions: `H&P PEDIATRIC` (no `ADULT` suffix)
- NICU: `H&P NICU.` (with trailing period)
- Long-stay transfers from ambulatory surgery: no H&P at all, only progress notes

`select_target_note()` walks a fallback chain: H&P Adult → Pediatric → NICU → generic H&P → admission note → ED provider note → consult note → earliest progress note.

### 6. Mixed types in lab columns

`LB_REF_HIGH` and similar columns mix strings ("5.4000") with numerics. Pyarrow can't write these as numeric — `build_cache.py` coerces object columns to string before writing parquet.

### 7. Sentinel timestamp dates

Some discharge notes have placeholder dates like `2023-01-01` instead of the actual encounter dates. **This is a known leakage source** for time-truncated prompts (AE1–3, P5, P7, P10) — a discharge note dated before the cutoff will leak into the input even though it actually describes events after the cutoff. Open issue, see "Known limitations" below.

### 8. Duplicate text from multi-supplier ingestion

Notes occasionally appear with the same `(NOTE_ID, NOTE_TYPE)` repeated 3–5 times because OMNY ingests the same record across multiple data suppliers. Not leakage but token-wasteful. Open issue.

---

## Section classification

Each `NOTE_TYPE` is classified into 0+ canonical section labels via regex patterns in `SECTION_PATTERNS`:

| Canonical | Patterns (regex) |
|---|---|
| CC | `\bCHIEF COMPLAINT\b`, `\bREASON FOR ADMISSION\b` |
| HPI | `\bHPI\b`, `\bHISTORY OF PRESENT ILLNESS\b`, `\bPRESENT ILLNESS\b` |
| PE | `\bPHYSICAL EXAM\b`, `NSHPPHYSICALEXAM`, `^EXAM\b` |
| ROS | `\bREVIEW OF SYSTEMS\b`, `\bROS\b` |
| LABS | `\bLAB(?:S\|ORATORY\|RESULTS)\b`, `NSHPLABSRESULTS` |
| IMAGING | `\bIMAGING\b`, `\bRADIOLOGY\b` |
| ASSESSMENT | `\bASSESSMENT\b` |
| PLAN | `(?<![A-Z])PLAN(?![A-Z])`, `\bCARE PLAN\b`, `\bTREATMENT PLAN\b` |
| AP | `\bASSESSMENT AND PLAN\b`, `\bA&P\b`, `\bA/P\b` |
| SUBJECTIVE | `\bSUBJECTIVE\b` |
| OBJECTIVE | `\bOBJECTIVE\b` |
| SUBJ_OBJ | `\bSUBJECTIVE AND OBJECTIVE\b` |

`_normalize_section_filter()` handles user-friendly aliases — when a caller asks to mask "A&P", we expand to `{ASSESSMENT, PLAN, AP}`.

---

## Truncation modes (two distinct code paths)

### Within-note truncation

When a prompt withholds a section from a single note (P1, P2, C2). Implemented by filtering `notes` rows whose `NOTE_TYPE` classifies into the masked sections.

```python
TruncationSpec(section_mask=["A&P", "ASSESSMENT", "PLAN", "AP"])
```

After section filtering, a redaction pass (`_redact_narrative_plan`) catches narrative-form plan content in non-A&P-labeled sections like `[ATTENDING COMMENTS]` — patterns include `Impression - <stuff>`, `Plan: <stuff>`, `Continue X`, `Hold Y`, `D/C Z`, numbered plan items, `Disposition - ...`. Redaction triggers only when within-note A&P masking is active.

### Time-based truncation

When the answer lies in the future of the patient's timeline (P4, P5, P6, P7, P8, P10, AE1–3). Implemented as `df[df.TS <= cutoff_ts]` applied to every encounter-scoped table.

```python
TruncationSpec(cutoff_ts=specimen_ts - timedelta(seconds=1))
```

Timestamps are reconstructed from OMNY's split DATE/TIME columns via `_combine_date_time()`:
- `labs`: `LB_SPECIMEN_DATE` + `LB_SPECIMEN_TIME`
- `vitals`: `VS_DATE` + `VS_TIME`
- `procedures`: `PX_SERVICE_DATE` + `PX_SERVICE_TIME`
- `meds`: `RX_ORDER_DATE` + `RX_ORDER_TIME`
- `notes`: `NOTE_DATE` (single column)
- `diagnoses`: `DX_DATE` (single column)

Strict-less-than semantics: we use `cutoff_ts - 1 second` as the comparison value to ensure rows at exactly the cutoff timestamp (e.g., the target P7 lab panel) are excluded.

---

## Per-prompt render paths

Most prompts use `render(encounter_id, prompt_id, loader)` which dispatches to `_default_truncation_for(prompt_id)`. Some prompts need special-case handling.

| Prompt | Render function | Notes |
|---|---|---|
| S1, S5, S6, C1, C2, C5, P1 | `render_single_note(enc_id, note_id, loader, truncation)` | Picks H&P via `select_target_note()`, applies within-note truncation if any |
| P2 | `render(enc_id, "P2", loader)` | Default truncation = keep_only progress note + mask A&P sections |
| P3 | `render(enc_id, "P3", loader)` | Default truncation = `keep_only_note_type="h&p adult"` |
| P4 | `render(enc_id, "P4", loader, truncation=TruncationSpec(cutoff_ts=cutoff_for_day(...)))` | Rolling — caller passes cutoff per N |
| P5 | `render(enc_id, "P5", loader, truncation=TruncationSpec(cutoff_ts=imaging_ts - 1s))` | Caller selects imaging study from `procedures` |
| P6 | similar to P5, anchored to procedure timestamp | — |
| P7 | `render_p7(enc_id, loader)` | Dedicated function. Picks first lab panel with ≥10 labs, returns rendered context + cutoff timestamp |
| P8 | similar to P5/P6, anchored to pathology specimen | — |
| P9 | bypasses renderer (raw image input only) | — |
| P10 | `render(enc_id, "P10", loader)` | Default truncation = mid-stay date |
| AE1, AE2, AE3 | `render(enc_id, ae_id, loader, truncation=TruncationSpec(cutoff_ts=T-24h))` | T from `ae_events.csv` sidecar |

`render_p7()` is the only purpose-built render function (added in response to Allison's feedback on the P7 ground-truth design). The others use the general `render()` with a prompt-specific `TruncationSpec`.

---

## Rendering output format

A typical render produces text blocks separated by `=== Section ===` headers. Example skeleton:

```
=== Encounter ===
Hospital: Northwell Health
Admission: 2021-06-20
Discharge: 2021-06-25
LOS: 4 days
Patient: 51yo MALE, OTHER


=== Notes ===

--- H&P ADULT — 2021-06-20 09:41 ---
  [REASON FOR ADMISSION] sepsis / hyperglycemia / l foot wound
  [HISTORY OF PRESENT ILLNESS] 51M hx dm, htn, esrd s/p renal transplant...
  [PHYSICAL EXAM] ...
  (A&P sections masked under P1/P2/C2)

--- PROGRESS NOTE ADULT — 2021-06-21 06:30 ---
  [SUBJECTIVE AND OBJECTIVE BOX] ...
  ...


=== Diagnoses (ICD-10) ===
- E11.65  Type 2 diabetes mellitus with hyperglycemia (primary)
- L97.529  Non-pressure chronic ulcer of left foot
- ...


=== Labs ===
| Time              | Test                    | Value | Units | Ref Low | Ref High | Flag |
|-------------------|-------------------------|-------|-------|---------|----------|------|
| 2021-06-20 12:57  | GLUCOSE BLDC GLUCOMTR   | 346   | MG/DL | 70.0    | 99.0     | H    |
| ...


=== Vitals ===
| Time              | Vital | Value | Units |
| ...


=== Medication Orders ===
- 2021-06-20 10:15  Ceftriaxone 1g IV q24h
- 2021-06-20 10:15  Azithromycin 500mg IV q24h
- ...
```

Note grouping: rows sharing a `NOTE_ID` are collapsed into one `--- <note_kind> — <ts> ---` block with `[SECTION] text` lines, in section-alphabetical order. Original section labels (verbatim from `NOTE_TYPE` after " - ") are preserved.

---

## Ground-truth extractors

`extract_ground_truth(encounter_id, prompt_id, loader, target_note_id=None)` returns:

```python
{
    "label": "<text or empty>",
    "metadata": {"note_id": ..., "code": ..., "specimen_ts": ..., ...}
}
```

Per-prompt logic:

| Prompt | What the GT is | How we find it |
|---|---|---|
| S1 | Chief Complaint text | CC section of the admission H&P |
| S5 | A&P section text | AP/ASSESSMENT section of the admission H&P |
| S6 | (graded against source labs in input) | n/a — judges compare model output to provided labs |
| C1 | Same as S5 | — |
| C2 | A&P from same H&P (reference for DDx generation) | — |
| C3, C4, C7 | empty — graded against rubric, no reference | — |
| C5 | List of actual orders placed (meds + procedures) | `prescription_orders.RX_GENERIC_NAME` + `procedures.PX_HCS_DESC` |
| C6 | Imaging report text | First radiology note |
| C8 | List of abnormal lab values with units + ref ranges | `labs[LB_ABN_RESULT in {H, L, HH, LL, CRITICAL, ABNORMAL, A}]` |
| P1 | Same as S5 | — |
| P2 | A&P from progress note | — |
| P3, P4 | Primary discharge ICD-10 + description | `diagnoses[DX_PRIMARY in {Y, YES, 1, TRUE}]` |
| P5 | Radiology report text closest in time to imaging procedure | — |
| P6 | First non-imaging procedure description + timestamp | — |
| P7 | Values of the ≥10-lab panel at the cutoff specimen ts | — |
| P8, P9 | empty (OMNY doesn't have pathology/DICOM commonly) | — |
| P10 | Discharge disposition + up to 30 subsequent note snippets | `encounters.EN_DC_DIS` + `notes` after cutoff |
| AE1, AE2, AE3 | Event timestamp + source + binary `True` label | From `ae_events.csv` sidecar (built by `code/ae_events.py`) |

---

## Pre-caching

`code/build_cache.py` reads each large CSV once, filters to the 360 encounter IDs, and writes one parquet file per `(encounter_id, table)` to `cache/`. Two effects:

1. **Speed**: cold-load drops from ~30s to ~0.1s per encounter
2. **Type stability**: object columns coerced to string at cache-build time, avoiding pyarrow conversion errors at runtime

Output: 2,876 parquet files (360 encounters × 8 tables, minus empties).

The loader (`EncounterDataLoader.load()`) checks `cache/<enc_id>_<table>.parquet` first, falls back to CSV scanning if cache is missing. Cache is optional — the renderer works without it, just slower.

---

## AE event detection (sidecar)

`code/ae_events.py` computes the timestamp T of qualifying adverse events for each Hard / Meta-Hard encounter. Output: `ae_events.csv` (76 unique encounters, 106 events as of latest run).

Detection logic per event:

**AE1 (ICU transfer)** — minimum of:
- `prescription_orders.RX_DEPT` matching `ICU|CCU|INTENSIVE`
- `encounters.EN_DEPT` matching same pattern
- `procedures.PX_CODE` in {99291, 99292}

**AE2 (Intubation)** —
- `procedures.PX_CODE` in {94002, 94003, 94004, 31500}
- `procedures.PX_HCS_DESC` matching `MECHANIC.*VENTIL|INTUBAT`

**AE3 (Dialysis init)** —
- `prescription_orders.RX_GENERIC_NAME` matching `DIALYSIS|HEMODIALYSIS`
- `procedures.PX_CODE` in {90935, 90937, 90945}

Each event must occur ≥ 24h post-admission to qualify. The runner reads `ae_events.csv` and passes `cutoff_ts = T - 24h` to `render()` for AE prompts.

---

## Known limitations (as of current pilot)

1. **Sentinel-date leakage in time-truncated prompts.** Some discharge notes have placeholder `2023-01-01` or similar dates that fall before the actual encounter window. These pass the `note.timestamp <= cutoff_ts` filter even though their content describes events after the cutoff. **Fix**: filter notes whose `NOTE_DATE` is earlier than `encounters.EN_START_DATE`. Not yet implemented.

2. **Duplicate text from multi-supplier ingestion.** Same `(NOTE_ID, NOTE_TYPE)` rows occasionally repeat with identical text. Wastes tokens; doesn't directly leak. **Fix**: dedupe by `(NOTE_ID, NOTE_TYPE, NOTE_TEXT)` after section filter. Not yet implemented.

3. **`*_long` cell context overflow.** Some Hard/long and Meta-Hard/long encounters render to >1M tokens — exceeds even the 1M API cap. Affects P10 and any prompt that needs the full record. In the pilot, 4 of 10 medium/long C8 cases failed with "prompt too long". **Fix options**: recency truncation (last N days), summarization pre-pass, or skip those prompts for *_long cells.

4. **Noun-headed plan content survives ATTENDING COMMENTS redaction.** Patterns like "Podiatry to perform left 5th ray amputation" aren't caught by the verb-prefix regex. Accepted limitation — adding more aggressive patterns risks false positives in HPI text.

5. **Section classifier brittleness.** OMNY uses ~660 distinct `NOTE_TYPE` values for one encounter. Our 12-pattern classifier covers the common cases but misses long-tail labels. New cases occasionally surface uncovered patterns (we've added 4–5 fallbacks during pilot). **Fix**: per-supplier classifier audit when scaling to full 360.

6. **Lab cutoff uses specimen time, not order time.** Allison's original suggestion was order time. We're using `specimen_ts - 1s` which is slightly more permissive (orders placed within the same second as the specimen leak). In practice this is rare since orders precede specimens by minutes-to-hours. **Optional improvement**: switch to `LB_ORDER_DATE/TIME` as the cutoff anchor.

7. **Single-thread runner.** `render()` is fast enough; the bottleneck is sequential LLM calls. Full 360 × 11 × 2 judges = ~4,000 model calls at 60s/task ≈ 65 hours single-threaded. **Fix**: async batching across cases. Not implemented.

---

## API reference

### Renderer entry points

```python
from renderer import (
    EncounterDataLoader,           # data access + caching
    render,                        # main entry: (enc_id, prompt_id, ...) → text
    render_single_note,            # for S1/S5/C1/C2/C5/P1
    render_p7,                     # for P7 (returns text + cutoff_ts)
    select_target_note,            # H&P selector with fallback chain
    extract_ground_truth,          # GT artifact extractor
    cutoff_for_day,                # helper for P4 rolling cutoffs
    TruncationSpec, AblationSpec,
)

# Typical use
loader = EncounterDataLoader()
text = render(encounter_id, "S1", loader=loader)
gt   = extract_ground_truth(encounter_id, "S1", loader)
```

### Key dataclasses

```python
@dataclass
class TruncationSpec:
    cutoff_ts: Optional[datetime] = None       # time-based filter
    section_mask: list[str] = []               # mask these sections from notes
    section_keep_only: list[str] = []          # invert mask
    exclude_note_ids: list[str] = []
    exclude_lab_specimen_dates: list[str] = []
    keep_only_note_type: Optional[str] = None  # filter to one note kind

@dataclass
class AblationSpec:
    drop: list[str] = []                       # tables to drop (notes, labs, ...)
    keep_only: list[str] = []                  # invert
```

### Code layout

```
code/
├── renderer.py            ~700 lines — main module
├── ae_events.py           AE event detection
├── build_cache.py         CSV → parquet pre-cache
├── criteria.py            Rubric criteria as Python data structures
├── judge.py               LLM client wrappers (Anthropic + OpenAI)
├── judge_routing.py       Which judges per (prompt, cell)
├── run_eval.py            Orchestration (renderer → MUT → judges → CSV)
├── analyze.py             Stats + plots + RESULTS.md
└── smoke_test.py          Pre-LLM render verification (no API calls)
```
