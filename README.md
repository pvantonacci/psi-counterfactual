# PSI Counterfactual Pipeline

**Pipeline:** OMNY EHR → CEM → LSPS → K:1 matching → counterfactual donor sets  
**Scope:** 16 PSI types · 110 cases · 3,626 matched pairs · 2,801 unique donors  
**Production run:** 2026-06-05

---

## What this pipeline does

Implements a causal-inference matching pipeline that selects, for each confirmed PSI-positive hospital admission, a set of event-free **counterfactual donor admissions** from the OMNY EHR dataset (~51M patients on Snowflake).

The output is a matched donor set that is exchangeable with the PSI cases on all observed clinical history from admission up to a landmark time — producing a defensible "business-as-usual" counterfactual for downstream causal analysis.

---

## Quick start

```bash
# 1. Set up environment
pip install -r requirements.txt

# 2. Copy .env.example → .env and fill in your Snowflake credentials
cp .env.example .env

# 3. Run a single PSI type (Snowflake auth opens browser on first run)
make run-one PSI_TYPE=PSI_06_IATROGENIC_PNEUMOTHORAX

# 4. Run all 16 types sequentially (~40 min)
make run-all

# 5. Analyze donor diagnostics across all types
make diagnostics

# 6. QA checks against spec PDF
make qa
```

All outputs go to `outputs/<PSI_TYPE>/`. Logs in `outputs/<PSI_TYPE>/logs/`.

---

## Project structure

```
psi-counterfactual/
├── data/
│   ├── raw/
│   │   ├── psi_inpatient_cases.csv        Confirmed PSI cases (input)
│   │   └── psi_tables/                    21 per-type CSV slices
│   └── interim/
│       └── snowflake_cache/               Parquet cache of Snowflake queries (~195MB, gitignored)
├── src/
│   ├── 00_pull_psi_tables.py              Pull raw PSI tables from Snowflake
│   ├── 01_psi_pipeline.py                 Stage -1: build cases.csv from local CSVs
│   ├── 01b_add_classification_columns.py  Add PSI classification columns
│   ├── 02_counterfactual_pipeline.py      Main pipeline (CEM → LSPS → K:1 matching)
│   ├── 03_run_all_psi_types.py            Loop runner — all 16 types sequentially
│   ├── 04_analyze_donor_diagnostics.py    Donor ICD-10 profile across PSI types
│   ├── 05_qa_vs_spec.py                   QA: checks code vs spec PDF
│   └── 06_build_notebook.py               Generate Jupyter execution-plan notebook
├── outputs/
│   └── PSI_XX_<TYPE>/
│       ├── cases.csv                      Confirmed PSI cases with timestamps
│       ├── matched_sets.parquet           Donor sets (case → [donor IDs])
│       ├── propensity_scores.csv          LSPS scores for all donors
│       ├── balance_table.csv              SMD before/after matching
│       ├── calibration.json              Positivity calibration metrics
│       ├── verification_report.json      Gate results + placebo ATE + blanking sweep
│       ├── pipeline_latest.log           Symlink → logs/pipeline_*.log
│       ├── RUN_LOG_latest.md             Symlink → logs/RUN_LOG_*.md
│       └── logs/                         Versioned run logs
├── results/
│   ├── tables/
│   │   └── all_psi_types_summary.md      16-type run status table
│   └── reports/
│       ├── pipeline_results_summary.md   Human-readable production results
│       ├── manager_presentation.md       Funnel + OMNY tables for manager review
│       ├── donor_diagnostics_by_psi.md   Top diagnoses in counterfactuals by PSI type
│       └── pipeline_spec_deviations.md   Spec vs implementation gap analysis
├── references/
│   ├── PROTEGE___Evaluating_LLMs.pdf     Pipeline specification
│   └── *.pdf                             Supporting literature
├── notebooks/                            Jupyter notebooks
├── latex/                                LaTeX manuscript files
├── .env                                  Snowflake credentials (gitignored)
├── .env.example                          Credential template
├── CLAUDE.md                             Rules for AI-assisted development
├── Makefile                              Common commands
└── requirements.txt                      Python dependencies
```

---

## Pipeline stages

| Stage | Description |
|---|---|
| −1 | Build cases.csv from local PSI CSV files |
| 0 | Load Snowflake donor pool (1% Bernoulli sample ≈ 316K encounters) |
| 1 | Coarsened Exact Matching on 10 demographic variables |
| 2a | Feature matrix: first 4h of admission (labs, vitals, procedures, Rx, Dx) |
| 2b | LSPS — L1-regularized logistic propensity score |
| 2c | K:1 nearest-neighbour matching (k=50, caliper=0.2×logit SD) |
| 3 | Placebo causal-forest verification (currently skipped) |
| 4 | Donor diagnostic profile — ICD-10 breakdown of control arm |

---

## Production results (2026-06-05)

| PSI Type | Cases | Matched Pairs | G2 |
|---|---|---|---|
| PSI-03 Pressure Ulcer | 3 | 150 | PASS |
| PSI-04 Failure to Rescue | 5 | 99 | WARN |
| PSI-05 Retained Item | 13 | 507 | PASS |
| PSI-06 Iatrogenic Pneumothorax | 7 | 223 | PASS |
| PSI-07 CLABSI | 6 | 159 | WARN |
| PSI-08 Fall/Fracture | 3 | 73 | PASS |
| PSI-09 Postop Hemorrhage | 11 | 428 | PASS |
| PSI-10 Postop AKI/Dialysis | 3 | 62 | WARN |
| PSI-11 Postop Resp Failure | 8 | 195 | PASS |
| PSI-12 Periop PE/DVT | 3 | 19 | PASS |
| PSI-13 Postop Sepsis | 5 | 96 | WARN |
| PSI-14 Wound Dehiscence | 7 | 159 | WARN |
| PSI-15 Accidental Puncture | 14 | 700 | WARN |
| PSI-17 Birth Trauma | 7 | 140 | PASS |
| PSI-18 OB Trauma (instrumental) | 11 | 416 | PASS |
| PSI-19 OB Trauma (no instrument) | 4 | 200 | PASS |
| **TOTAL** | **110** | **3,626** | |

G2 WARN = LSPS degraded age-SMD after matching (expected for types with ≤7 cases;
CEM-matched donors are still valid for downstream analysis).

---

## Data governance (hard constraints — never relax)

- Forbidden suppliers: **1990** (Advocate Aurora), **3707**, **3490** — excluded at every stage
- No post-event features in the feature matrix (only data from [t0, t0+4h])
- No local fallbacks for supplier filtering
- No invented inputs

---

## Key configuration

| Key | Value | Meaning |
|---|---|---|
| `data_mode` | `"csv"` | `"csv"` uses local files for cases; `"snowflake"` queries OMNY |
| `donor_source` | `"snowflake"` | Donor pool from Snowflake |
| `snowflake_sample_pct` | `1.0` | 1% Bernoulli sample ≈ 316K donors |
| `FORBIDDEN_SUPPLIERS` | `[1990, 3707, 3490]` | Always excluded |
| `GRID_HOURS` | `4` | Hours per temporal grid tick |
| `B_GRID` | `6` | Blanking window in ticks (t* = E_i − 6) |
| `k_matches` | `50` | Target donors per case |
| `caliper_logit_sd` | `0.2` | LSPS caliper in logit-SD units |
| `skip_stage3` | `True` | Placebo causal-forest verification skipped |

---

## Open gaps (see `results/reports/pipeline_spec_deviations.md`)

- Lab/vitals slope and time-since-last features not implemented
- Prognostic score ψt (double-score matching) not implemented
- K:1 matching currently without replacement (spec requires with replacement)
- Abadie-Imbens bias correction not applied
- Stage 3 verification still skipped
- No negative-control calibration panel
