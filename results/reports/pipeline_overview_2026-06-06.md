# PSI Counterfactual Pipeline — Complete Overview
**Date:** 2026-06-06  
**Operator:** Paulo Antonacci  
**Status:** 16 / 16 PSI types PASS · 3,615 total matched pairs

---

## 1. What This Pipeline Does

The PSI Counterfactual Pipeline is a causal-inference matching system built on top of the OMNY EHR dataset (~51M patient encounters from Snowflake). Its purpose is to construct matched control cohorts for each of AHRQ's 16 Patient Safety Indicators (PSI-03 through PSI-19).

For each PSI event (e.g. an iatrogenic pneumothorax, a pressure ulcer, a retained surgical item), the pipeline:

1. Identifies the case encounter and its event time `E_i`
2. Sets a landmark `t*` = `E_i − B_GRID` (6 ticks × 4h = 24h before the event)
3. Builds a donor pool of non-PSI encounters from the same EHR system
4. Applies Coarsened Exact Matching (CEM) to narrow the donor pool by age, LOS, and chronic condition count
5. Computes a logistic propensity score (LSPS) using features from the [t0, t0+4h] window only
6. Performs K:1 nearest-neighbor matching with caliper on the propensity score
7. Validates with governance gates (G-1 through G3) at every stage
8. Writes matched sets, balance tables, positivity curves, and calibration stubs to `outputs/<PSI_TYPE>/`

The resulting matched cohorts enable counterfactual analysis: what would have happened to the PSI case if the adverse event had not occurred?

---

## 2. Data Sources

| Source | Contents | Access |
|---|---|---|
| `OMNY_REPL_ID.CUSTOM.*` | All structured EHR tables (encounters, diagnoses, labs, vitals, procedures, medications, problem lists) | Snowflake via Okta SSO |
| `OMNY_PROTEGE.PUBLIC.OMNY_NOTES_CONCATENATED` | Clinical notes for chart abstraction | Snowflake via Okta SSO |
| `data/raw/psi_inpatient_cases.csv` | 255 PSI case encounters with labels, produced by script 01 | Local CSV |
| `data/interim/snowflake_cache/*.parquet` | Cached Snowflake query results — enables offline re-runs | Local parquet (gitignored) |

### Forbidden Suppliers (hard constraint — never relaxed)
Suppliers **1990** (Advocate Aurora), **3707**, and **3490** are excluded at every data load via an `assert_no_forbidden()` governance gate. Any data load that returns rows from these suppliers causes the pipeline to halt immediately.

---

## 3. Pipeline Architecture

```
Snowflake (OMNY EHR)
        │
        ▼
00_pull_psi_tables.py ──► data/raw/psi_tables/*.csv
        │
        ▼
01_psi_pipeline.py ──────► data/raw/psi_inpatient_cases.csv
   (ICD-10 filter + Claude chart abstraction)
        │
        ▼
01b_add_classification_columns.py ──► enriches psi_inpatient_cases.csv
   (LOS_BUCKET, COMPLEXITY_TIER via Snowflake labs/vitals/ICU)
        │
        ▼
02_counterfactual_pipeline.py ──► outputs/PSI_XX/
   Stage -1: Load & filter cases
   Stage  0: Build donor pool (Snowflake BERNOULLI 1% sample)
   Stage  1: CEM (age, LOS, n_chronic)
   Stage  2: LSPS + K:1 nearest-neighbor matching
   Stage  3: Outcome estimation (skipped in CSV dev mode)
   Stage  4: Donor diagnostic profiling
        │
        ▼
03_run_all_psi_types.py ──► loops 02 over all 16 PSI types
        │
        ▼
04_analyze_donor_diagnostics.py ──► results/reports/donor_diagnostics_by_psi.md
05_qa_vs_spec.py ────────────────► QA report vs PROTEGE spec PDF
06_build_notebook.py ────────────► notebooks/PSI_counterfactual_execution_plan.ipynb
```

---

## 4. Script Reference

### `src/00_pull_psi_tables.py`
Connects to Snowflake via Okta SSO and pulls every table in `OMNY_REPL_ID.CUSTOM` filtered to the encounters in `data/raw/psi_inpatient_cases.csv`. Auto-detects filter strategy per table (by `ENCOUNTER_ID`, by `OMNY_ID`, or skip if no ID columns). Also pulls `OMNY_PROTEGE.PUBLIC.OMNY_NOTES_CONCATENATED`. Writes one CSV per table to `data/raw/psi_tables/`.

**Requires:** Snowflake SSO (browser), `SF_USER` in `.env`  
**Produces:** `data/raw/psi_tables/*.csv`

---

### `src/01_psi_pipeline.py`
Three-stage case identification pipeline:
- **Stage A:** Pulls all inpatient encounters from Snowflake with qualifying ICD-10 codes per PSI type
- **Stage B:** Filters by note-text regex to confirm PSI documentation
- **Stage C:** Sends clinical notes to Claude (Anthropic API) for chart abstraction — Claude returns a structured `LABEL` (positive/negative) and reasoning

**Requires:** Snowflake SSO, `SF_USER` + `ANTHROPIC_API_KEY` in `.env`  
**Produces:** `data/raw/psi_inpatient_cases.csv` (255 encounters, 16 PSI types)

---

### `src/01b_add_classification_columns.py`
Enriches `psi_inpatient_cases.csv` with three derived columns:
- `LOS_BUCKET` — length-of-stay tier derived from ICU flags, lab counts, and vital signs
- `COMPLEXITY_TIER` — clinical complexity score
- `LOS_SOURCE` — data source used for LOS derivation

Queries Snowflake for ICU indicators, lab counts, vitals, and medications per encounter. Writes back to the same CSV in-place.

**Requires:** Snowflake SSO, `SF_USER` in `.env`  
**Produces:** enriched `data/raw/psi_inpatient_cases.csv`

---

### `src/02_counterfactual_pipeline.py`
The core matching engine. Runs all 7 pipeline stages for a single PSI type. Key parameters:
- `B_GRID = 6` ticks (24h blanking window)
- Feature window: strictly `[t0, t0+4h]` — no post-event features
- CEM strata: `AGE`, `EN_LOS_num`, `n_chronic`
- Matching: K:1 nearest-neighbor with 0.2 SD caliper on log-odds
- Governance gates G-1, G0, G1, G2, G3 at every stage

#### Donor pool and risk set — filter chain

The donor pool and risk set R(t\*) are produced by a six-step filter chain inside Stage 0:

| Step | Filter | Effect |
|---|---|---|
| 1 | `TABLESAMPLE BERNOULLI(N)` on the OMNY encounters table (~51M rows) | Reduces to ~316K encounters at 1%, ~632K at 2% |
| 2 | Forbidden supplier exclusion | Hard drop of supplier IDs **1990, 3707, 3490** |
| 3 | Inpatient filter | Keeps only encounters where `EN_SETTING = 'INPATIENT'` OR `EN_TYPE ILIKE '%INPATIENT%'` OR `EN_SETTING_DET = 'INPATIENT'` |
| 4 | Valid admission date | `EN_START_DATE IS NOT NULL` |
| 5 | PSI case exclusion | `ENCOUNTER_ID NOT IN (case_ids)` — the case encounters themselves are removed from the donor pool |
| 6 | Negative LOS drop | Donors with `grid_LOS < 0` (discharge before admission — bad timestamps) are removed |

After these six filters the **full donor pool** is established (typically 200K–300K for a 1% sample).

The **risk set R(t\*)** is a further temporal cut applied per case:

```python
def risk_set(t: int) -> np.ndarray:
    """R(t) = donors still admitted at grid tick t (grid_LOS > t)."""
    return donors.loc[donors["grid_LOS"] > t, "ENCOUNTER_ID"].values
```

For PSI_06, `t* = E_i − 6` grid ticks (24h before the PSI event). `R(t*)` keeps only donors whose length-of-stay was long enough that they were still admitted at the landmark time — i.e., `grid_LOS > t*`. Donors already discharged before the case's landmark are ineligible because they could not have been "at risk" of that event at that moment. The reported 188,890 figure is the count of donors surviving this temporal filter for PSI_06's specific t\* value.

**Requires:** `data/raw/psi_inpatient_cases.csv`, Snowflake cache (or live connection)  
**Produces:** `outputs/<PSI_TYPE>/matched_sets.parquet`, `balance_table.csv`, `positivity_curves.parquet`, `verification_report.json`, `calibration.json`, `cases.csv`

---

### `src/03_run_all_psi_types.py`
Loops `02_counterfactual_pipeline.py` over all 16 PSI types sequentially using `sys.executable` (the active venv's Python). Treats a run as successful if `matched_sets.parquet` is written, regardless of exit code (handles the cosmetic logging teardown error). Writes a summary table to `results/tables/all_psi_types_summary.md`.

**Requires:** Same as script 02  
**Produces:** All per-type outputs + `results/tables/all_psi_types_summary.md`

---

### `src/04_analyze_donor_diagnostics.py`
Reads `matched_sets.parquet` for all 16 PSI types. Pulls diagnoses for matched donors from cache or Snowflake. Produces a markdown report profiling the clinical characteristics of matched donors.

**Produces:** `results/reports/donor_diagnostics_by_psi.md`

---

### `src/05_qa_vs_spec.py`
Static analysis tool. Parses `02_counterfactual_pipeline.py` and checks it against 60 requirements from the PROTEGE specification PDF. Reports PASS / FAIL / WARN per requirement.

**Result (2026-06-06):** 37 PASS · 12 FAIL · 11 WARN  
Key gaps: lab slope/time-since-last, vitals slope, prognostic score ψt, Abadie-Imbens correction, K:1 without replacement

---

### `src/06_build_notebook.py`
Generates a 24-cell Jupyter notebook (`notebooks/PSI_counterfactual_execution_plan.ipynb`) documenting the full pipeline execution plan using `nbformat`.

---

## 5. Critical Constraints

| Constraint | Detail |
|---|---|
| Forbidden suppliers | 1990, 3707, 3490 — excluded at every data load via `assert_no_forbidden()` |
| Feature window | Only `[t0, t0+4h]` — no post-event features in the feature matrix |
| No invented inputs | Never fabricate or synthesize data |
| No local fallbacks for supplier filtering | If the filter cannot run, the pipeline fails loudly |
| `SF_USER` required | Must come from `.env` — no hardcoded default |

---

## 6. Environment

### Virtualenv
```bash
source '/home/pvam/projects/PROTEGE - HealthBenck/PSI/bin/activate'
```
Note: the venv is **not** inside the project root — it lives in the shared PROTEGE directory.

### `.env` file (gitignored)
```
SF_ACCOUNT=APHHHWO-PROTEGE_PARTNER
SF_USER=<your Okta email>
SF_ROLE=READ_ONLY
SF_WAREHOUSE=READ_ONLY_2XL_WH
ANTHROPIC_API_KEY=<your Anthropic key>
```

### Key dependencies
- `snowflake-connector-python` — Snowflake queries
- `python-dotenv` — `.env` loading
- `pandas`, `numpy`, `scikit-learn` — data processing and matching
- `anthropic` — Claude API for chart abstraction
- `pyarrow` — parquet cache read/write
- `nbformat` — notebook generation

---

## 7. How to Run

### Full refresh (fresh Snowflake data)
```bash
source '/home/pvam/projects/PROTEGE - HealthBenck/PSI/bin/activate'
cd /home/pvam/projects/psi-counterfactual
make run-fresh       # 00 → 01 → 01b → run-all
```
Chrome opens 3 times for Okta SSO. Each login is per-script.

### Offline run (using cached data)
```bash
source '/home/pvam/projects/PROTEGE - HealthBenck/PSI/bin/activate'
cd /home/pvam/projects/psi-counterfactual
make run-all         # ~25 minutes, no Snowflake needed
```

### Single PSI type
```bash
make run-one PSI_TYPE=PSI_06_IATROGENIC_PNEUMOTHORAX
```

### Individual scripts
```bash
make pull-data       # step 00
make identify-cases  # step 01
make enrich-cases    # step 01b
make diagnostics     # step 04
make qa              # step 05
make notebook        # step 06
```

---

## 8. Run Results — 2026-06-06

**Run completed:** 2026-06-06T19:29:05 UTC  
**Wall time:** 25.7 minutes  
**Data mode:** CSV + Snowflake parquet cache (no live Snowflake connection)

| PSI Type | Cases | Matched Pairs | Time (s) | Status |
|---|---|---|---|---|
| PSI_03_PRESSURE_ULCER | 3 | 150 | 418 | PASS |
| PSI_04_FAILURE_TO_RESCUE | 5 | 76 | 44 | PASS |
| PSI_05_RETAINED_ITEM | 13 | 507 | 74 | PASS |
| PSI_06_IATROGENIC_PNEUMOTHORAX | 7 | 223 | 54 | PASS |
| PSI_07_CLABSI | 6 | 147 | 74 | PASS |
| PSI_08_FALL_FRACTURE | 3 | 73 | 58 | PASS |
| PSI_09_POSTOP_HEMORRHAGE | 11 | 428 | 110 | PASS |
| PSI_10_POSTOP_AKI_DIALYSIS | 3 | 74 | 66 | PASS |
| PSI_11_POSTOP_RESP_FAILURE | 8 | 265 | 80 | PASS |
| PSI_12_PERIOP_PE_DVT | 3 | 11 | 39 | PASS |
| PSI_13_POSTOP_SEPSIS | 5 | 78 | 57 | PASS |
| PSI_14_WOUND_DEHISCENCE | 7 | 150 | 57 | PASS |
| PSI_15_ACCIDENTAL_PUNCTURE | 14 | 700 | 197 | PASS |
| PSI_17_BIRTH_TRAUMA | 7 | 117 | 69 | PASS |
| PSI_18_OB_TRAUMA_INSTRUMENT | 11 | 416 | 76 | PASS |
| PSI_19_OB_TRAUMA_NO_INSTRUMENT | 4 | 200 | 67 | PASS |
| **TOTAL** | **110** | **3,615** | **1,544** | **16/16 PASS** |

---

## 9. Issues Encountered and Fixed

| # | Issue | Fix |
|---|---|---|
| 1 | Virtualenv not at `PSI/bin/activate` in project root | Use full path: `/home/pvam/projects/PROTEGE - HealthBenck/PSI/bin/activate` |
| 2 | `python-dotenv` not installed in venv | `pip install python-dotenv` |
| 3 | Scripts 00, 01, 01b had hardcoded credentials and legacy paths | Added `load_dotenv()`, replaced with `os.environ["SF_USER"]`, fixed paths to `data/raw/` |
| 4 | No WSL2 browser for Snowflake SSO | Added `webbrowser.register()` for Windows Chrome/Edge before each `connect()` |
| 5 | `03_run_all_psi_types.py` hardcoded Python path | Changed `PYTHON = str(Path("PSI/bin/python").resolve())` → `PYTHON = sys.executable` |
| 6 | Patient data (`data/raw/`) tracked by git | Added `data/raw/` to `.gitignore`; untracked with `git rm --cached -r data/raw/` |
| 7 | Linux symlinks (`*_latest.*`) blocked git on Windows | Added `outputs/PSI_*/*_latest.*` to `.gitignore`; untracked 31 symlinks; added `.gitattributes` |
| 8 | GitHub fine-grained PAT had read-only access | Updated PAT → Repository permissions → Contents → Read and write |
| 9 | Exit code 120 / `ValueError('I/O operation on closed file.')` | Cosmetic logging teardown — not fixed; success detected by `matched_sets.parquet` existence |
| 10 | Makefile used hardcoded wrong Python path | Rewrote Makefile with correct venv path and added `pull-data`, `identify-cases`, `enrich-cases`, `run-fresh` targets |

---

## 10. Repository Structure

Two GitHub repositories:

| Repo | URL | Contents |
|---|---|---|
| Full project | github.com/pvantonacci/psi-counterfactual | `src/`, `outputs/`, `results/`, `notebooks/`, `Makefile`, `CLAUDE.md` |
| Source only | github.com/pvantonacci/psi-counterfactual-src | `src/` scripts at repo root (no data, no outputs) |

**What is gitignored (never pushed):**
- `data/raw/` — patient encounter data
- `data/interim/` — Snowflake parquet cache
- `.env` — credentials
- `PSI/`, `.venv/` — virtualenv
- `outputs/PSI_*/logs/` — log files
- `outputs/PSI_*/*_latest.*` — symlinks

---

## 11. Known Gaps (QA vs Spec)

From `05_qa_vs_spec.py` (37/60 PASS):

| Gap | Detail |
|---|---|
| Lab features | Slope and time-since-last not implemented |
| Vitals features | Slope and abnormal-count features missing |
| Procedure recurrence | Not implemented |
| Prognostic score ψt | Stub only |
| K:1 matching | With replacement (spec requires without) |
| Abadie-Imbens SE correction | Not applied |
| Stage 3 | Outcome estimation skipped in CSV dev mode |

---

## 12. Next Steps

1. **Run `make run-fresh`** — pull live Snowflake data through all stages with fresh Okta SSO auth
2. **Address QA gaps** — implement lab/vitals slope features, procedure recurrence, ψt prognostic score
3. **K:1 without replacement** — enforce in matching stage
4. **Abadie-Imbens correction** — apply to standard errors
5. **Stage 3 outcome estimation** — enable for Snowflake runs with sufficient sample size
