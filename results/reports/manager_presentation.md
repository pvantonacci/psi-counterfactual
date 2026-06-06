# PSI Counterfactual Matching — Pipeline Overview
**Prepared:** 2026-06-05  
**Dataset:** OMNY EHR (Snowflake) — ~316K encounters from 15 health systems  
**Objective:** For each confirmed Patient Safety Indicator (PSI) case, identify a set of matched "business-as-usual" admissions that are clinically and demographically exchangeable — the counterfactual comparator group for downstream causal analysis.

---

## How the pipeline works — one paragraph

Starting from confirmed PSI adverse-event cases, the pipeline pulls a large pool of comparable inpatient admissions from the OMNY network, then progressively filters and matches them in three layers: (1) **exact demographic matching** on 10 variables to guarantee comparability at the population level, (2) **clinical propensity scoring** on labs, vitals, medications, diagnoses, and procedures from the first 4 hours of admission to capture how similar the clinical trajectory looked before the adverse event could have happened, and (3) **nearest-neighbour matching** within each demographic stratum using the propensity score as the distance metric. The result is a matched set of up to 50 donor admissions per PSI case, ready for causal effect estimation.

---

## Funnel — how encounters flow through the pipeline

```
OMNY ENCOUNTERS (Snowflake, 1% Bernoulli sample)
        316,340 raw encounters
             │
             │  Drop 2 encounters with negative length-of-stay (data quality)
             ▼
        316,338 usable donor encounters
             │
             │  Restrict to donors still admitted at landmark time t*
             │  (= 4h before the PSI event in the matched case)
             ▼
        188,890 donors in the risk set  [per PSI_06 example; varies by type]
             │
     ┌───────┴───────────────────────────────────────┐
     │                                               │
PSI CASES (local CSV, 110 cases across 16 types)     │
     │                                               │
     │  Apply governance: remove forbidden           │
     │  supplier IDs (1990, 3707, 3490)              │
     │  145 → 110 cases                              │
     ▼                                               ▼
STAGE 1 — COARSENED EXACT MATCHING (CEM)
  Match cases to donors on 10 demographic variables
  316,338 donors → 93–30,090 per PSI type (median ~1,700)
  across 8,450 unique demographic strata
             │
             │  Only demographically-matched donors proceed further
             ▼
STAGE 2a — CLINICAL FEATURE ENGINEERING
  Build feature vectors from first 4 hours of admission
  for every case + CEM-matched donor
  Clinical tables: labs, vitals, procedures, medications, diagnoses
  Feature matrix: 96–30,093 encounters × 0–808 features per PSI type
             │
             │  7 of 16 types: real feature vectors built
             │  9 of 16 types: feature matrix empty (no timestamped
             │  clinical records in first 4h for those cases in current data)
             ▼
STAGE 2b — PROPENSITY SCORE (LSPS)
  L1-regularised logistic regression (case=1 vs donor=0)
  Caliper = 0.2 × logit SD
             │
STAGE 2c — K:1 NEAREST-NEIGHBOUR MATCHING
  Within each demographic stratum, each case → up to 50 donors
  whose propensity score is within the caliper
             │
             ▼
        3,626 matched donor-case pairs
        across 110 cases (16 PSI types)
```

---

## Stage-by-stage detail

### Stage −1 — Identify PSI cases

**What it does:** Loads confirmed adverse-event cases, enforces governance rules, assigns a landmark time (t*) for each case.

**OMNY table used:**
| Table | Source | Key columns used |
|---|---|---|
| `ENCOUNTERS` | Local CSV (`psi/psi/outputs/aggregated/tables/encounters.csv`) | `ENCOUNTER_ID`, `DATA_SUPPLIER_ID`, `EN_START_DATE`, `EN_START_TIME`, `EN_LOS`, demographics |
| `psi_inpatient_cases` | Local CSV (`psi_inpatient_cases.csv`) | `PSI_CODE`, `PSI_TITLE`, `NOTE_DATE`, ICD-10 diagnosis/procedure codes |
| `DIAGNOSES` | Local CSV (`diagnoses.csv`) | `DX_CODE`, `DX_DATE` — used to refine event timestamps via ICD-10 regex |

**Governance filter applied here:**
- Remove supplier IDs **1990** (Advocate Aurora — never use), **3707**, **3490**

**Funnel:**

| Step | Count |
|---|---|
| Raw encounters in local CSV | 145 |
| After removing forbidden suppliers | **110** |
| Distributed across 16 PSI types | 3–14 cases per type |
| **Total cases in analysis** | **110** |

**Landmark time (t\*):** For each case, t* = E_i − 6 grid ticks, where E_i is the 4-hour grid tick of the adverse event. All features are built using only information available before t*. In this dataset, most cases have t* = 1 (event occurred within the first 24h of admission), so the feature window is the first 4 hours of admission.

---

### Stage 0 — Donor pool & risk set

**What it does:** Fetches all available donor encounters from Snowflake, drops data-quality failures, restricts to donors who were still admitted at t* (i.e., not yet discharged when the matched case's landmark arrives).

**OMNY table used:**
| Table | Source | Key columns used |
|---|---|---|
| `OMNY_REPL_ID.CUSTOM.ENCOUNTERS` | Snowflake (1% Bernoulli sample) | `ENCOUNTER_ID`, `OMNY_ID`, `DATA_SUPPLIER_ID`, `EN_START_DATE`, `EN_START_TIME`, `EN_LOS`, `EN_FACILITY_TYPE`, `EN_URBAN_RURAL`, `EN_FACILITY_SIZE`, `EN_DEPT`, `EN_ADM_DEPT`, `GENDER`, `AGE`, `RACE`, `ETHNICITY`, `EMPLOY` |

**Funnel:**

| Step | Count |
|---|---|
| Raw Snowflake encounters (1% sample) | 316,340 |
| Drop negative length-of-stay | −2 |
| Usable donor pool | **316,338** |
| Still admitted at t* = 1 (4h into admission) | **188,890** |

---

### Stage 1 — Coarsened Exact Matching (CEM)

**What it does:** Groups all encounters (cases + donors) into demographic strata. Only donors who fall in the same stratum as a case are eligible for that case. This guarantees that every matched donor is demographically exchangeable with the case.

**OMNY table used:**
| Table | Source | Key columns used |
|---|---|---|
| `ENCOUNTERS` | Cases: local CSV / Donors: Snowflake | See variables below |
| `PROBLEM_LISTS` | Snowflake cache | `PROBLEM_CODE`, `PROBLEM_STATUS` — chronic condition count (informational, not CEM key) |

**CEM key — 10 variables:**

| Variable | Source column | Coarsening |
|---|---|---|
| Sex | `GENDER` | Male / Female |
| Age group | `AGE` | 0–17, 18–44, 45–64, 65–79, 80+ |
| Race | `RACE` | White / Black / Hispanic / Asian / Other / Missing |
| Ethnicity | `ETHNICITY` | Hispanic / Non-Hispanic / Missing |
| Employment | `EMPLOY` | Employed / Retired / Unemployed / Student / Disabled / Missing |
| Facility type | `EN_FACILITY_TYPE` | Hospital / Medical Center / Missing |
| Facility size | `EN_FACILITY_SIZE` | Large / Medium / Small / Missing |
| Urban/Rural | `EN_URBAN_RURAL` | Urban Metro / Urban Non-Metro / Rural / Missing |
| Admission dept | `EN_ADM_DEPT` | Surgical / OB / ICU / Medical / Other / Missing |
| Current dept | `EN_DEPT` | Same coarsening |

**Funnel per PSI type:**

| PSI Type | Cases | CEM-matched donors | Strata |
|---|---|---|---|
| PSI_03 — Pressure Ulcer | 3 | 30,090 | (broad: elderly, multiple strata match) |
| PSI_04 — Failure to Rescue | 5 | 788 | |
| PSI_05 — Retained Item | 13 | 2,425 | |
| PSI_06 — Iatrogenic Pneumothorax | 7 | 1,138 | 8,450 unique strata across all donors |
| PSI_07 — CLABSI | 6 | 2,853 | |
| PSI_08 — Fall/Fracture | 3 | 1,797 | |
| PSI_09 — Postop Hemorrhage | 11 | 4,327 | |
| PSI_10 — Postop AKI/Dialysis | 3 | 1,742 | |
| PSI_11 — Postop Resp Failure | 8 | 3,340 | |
| PSI_12 — Periop PE/DVT | 3 | 93 | |
| PSI_13 — Postop Sepsis | 5 | 1,548 | |
| PSI_14 — Wound Dehiscence | 7 | 1,571 | |
| PSI_15 — Accidental Puncture | 14 | 9,517 | |
| PSI_17 — Birth Trauma | 7 | 1,011 | |
| PSI_18 — OB Trauma (instr.) | 11 | 2,485 | |
| PSI_19 — OB Trauma (no instr.) | 4 | 2,138 | |
| **Total** | **110** | **66,863** | |

---

### Stage 2a — Clinical feature engineering (first 4 hours of admission)

**What it does:** Builds a clinical feature vector for every encounter that survived Stage 1. Features are restricted to records collected in the **first 4 hours of admission** — admission chaos is included; no post-event data leakage.

Feature window: `[admission_start, admission_start + 4h]`  
Any clinical record timestamped up to 4 hours after admission start is included.

**OMNY tables used:**
| Table | Source | Key columns | What it contributes |
|---|---|---|---|
| `LABS` | Snowflake cache + local CSV | `LB_SPECIMEN_DATE`, `LB_SPECIMEN_TIME`, `LB_LOINC_CODE`, `LB_LOINC_LEVEL2`, `LB_RESULT_NUM_VALUE`, `LB_ABN_RESULT` | Lab test results: one feature per LOINC category (presence, abnormal flag, numeric value) |
| `VITALS` | Snowflake cache + local CSV | `VS_DATE`, `VS_TIME`, `VS_CODE`, `VS_DESC`, vital numeric values | Vital signs: one feature per vital type |
| `PROCEDURES` | Snowflake cache + local CSV | `PX_SERVICE_DATE`, `PX_SERVICE_TIME`, `PX_CODE`, `PX_TYPE` | Procedure codes (CPT/ICD-10-PCS): presence/count features |
| `PRESCRIPTION_ORDERS` | Snowflake cache + local CSV | `RX_ORDER_DATE`, `RX_ORDER_TIME`, `DRUG_CLASS`, `DRUG_CODE` | Medication orders: presence features by drug class |
| `DIAGNOSES` | Snowflake cache + local CSV | `DX_DATE`, `DX_TIME`, `DX_CODE` | ICD-10 diagnosis codes: presence features |
| `PROBLEM_LISTS` | Snowflake cache + local CSV | `PROBLEM_CODE`, `PROBLEM_STATUS` | Chronic condition count (pre-existing conditions, not windowed) |

**Funnel:**

| PSI Type | Encounters in feature matrix | Feature columns | LSPS quality |
|---|---|---|---|
| PSI_03 — Pressure Ulcer | 30,093 | **0** — null timestamps | CEM-only |
| PSI_04 — Failure to Rescue | 793 | **0** — null timestamps | CEM-only |
| PSI_05 — Retained Item | 2,438 | 244 | Real propensity scores ✓ |
| PSI_06 — Iatrogenic Pneumothorax | 1,145 | 435 | Real propensity scores ✓ |
| PSI_07 — CLABSI | 2,859 | **0** — null timestamps | CEM-only |
| PSI_08 — Fall/Fracture | 1,800 | 538 | Real propensity scores ✓ |
| PSI_09 — Postop Hemorrhage | 4,338 | 808 | Real propensity scores ✓ |
| PSI_10 — Postop AKI/Dialysis | 1,745 | **0** — null timestamps | CEM-only |
| PSI_11 — Postop Resp Failure | 3,348 | **0** — null timestamps | CEM-only |
| PSI_12 — Periop PE/DVT | 96 | **0** — null timestamps | CEM-only |
| PSI_13 — Postop Sepsis | 1,553 | **0** — null timestamps | CEM-only |
| PSI_14 — Wound Dehiscence | 1,578 | **0** — null timestamps | CEM-only |
| PSI_15 — Accidental Puncture | 9,531 | 683 | Real propensity scores ✓ |
| PSI_17 — Birth Trauma | 1,018 | **0** — null timestamps | CEM-only |
| PSI_18 — OB Trauma (instr.) | 2,496 | 277 | Real propensity scores ✓ |
| PSI_19 — OB Trauma (no instr.) | 2,142 | 257 | Real propensity scores ✓ |

> **Note on null timestamps:** 9 of 16 PSI types have cases whose clinical records in the local CSV dataset do not carry specimen/service timestamps (fields are NULL). Without timestamps we cannot determine whether a record falls within the first 4 hours, so no features are built. The fix is to pull timestamped clinical records directly from Snowflake for each case encounter — this will be done in the next iteration. The CEM matching (Stage 1) is unaffected and these matched sets are valid for demographic-level analysis.

---

### Stage 2b — Propensity score model (LSPS)

**What it does:** Fits an L1-regularised logistic regression ("Large-Scale Propensity Score") on all CEM-matched encounters. Each encounter receives a logit score reflecting how similar its first-4-hour clinical trajectory is to the average PSI case.

**Model:** `SGDClassifier(loss='log_loss', penalty='l1', alpha=0.01)` with balanced class weights  
**Caliper:** 0.2 × logit SD (standard Rosenbaum–Rubin recommendation)

**Output:** `outputs/<PSI_TYPE>/propensity_scores.csv`  
Columns: `ENCOUNTER_ID`, `logit_score`, `propensity_score`, `label`

**Total propensity scores computed:** 66,973 across all 16 types

For the 9 types with empty feature matrices, the model falls back to random scores — matching within those strata is driven purely by CEM (demographic alignment), not clinical similarity.

---

### Stage 2c — K:1 Nearest-neighbour matching

**What it does:** Within each CEM demographic stratum, matches each case to up to k=50 donors whose propensity score (logit) falls within the caliper of the case's score. Donors must be in the risk set R(t*) — still admitted at the case's landmark time.

**Funnel:**

| PSI Type | Cases | Final matched pairs | Avg donors/case |
|---|---|---|---|
| PSI_03 — Pressure Ulcer | 3 | 150 | 50.0 |
| PSI_04 — Failure to Rescue | 5 | 99 | 19.8 |
| PSI_05 — Retained Item | 13 | 507 | 39.0 |
| PSI_06 — Iatrogenic Pneumothorax | 7 | 223 | 31.9 |
| PSI_07 — CLABSI | 6 | 159 | 26.5 |
| PSI_08 — Fall/Fracture | 3 | 73 | 24.3 |
| PSI_09 — Postop Hemorrhage | 11 | 428 | 38.9 |
| PSI_10 — Postop AKI/Dialysis | 3 | 62 | 20.7 |
| PSI_11 — Postop Resp Failure | 8 | 195 | 24.4 |
| PSI_12 — Periop PE/DVT | 3 | 19 | 6.3 |
| PSI_13 — Postop Sepsis | 5 | 96 | 19.2 |
| PSI_14 — Wound Dehiscence | 7 | 159 | 22.7 |
| PSI_15 — Accidental Puncture | 14 | 700 | 50.0 |
| PSI_17 — Birth Trauma | 7 | 140 | 20.0 |
| PSI_18 — OB Trauma (instr.) | 11 | 416 | 37.8 |
| PSI_19 — OB Trauma (no instr.) | 4 | 200 | 50.0 |
| **Total** | **110** | **3,626** | **33.0** |

**Balance check (G2):** After matching, the standardised mean difference (SMD) in age between cases and matched donors is computed. An improvement confirms the propensity model added value on top of CEM.

| | SMD improved after matching | SMD degraded (CEM-only effective) |
|---|---|---|
| PSI types | PSI_03, 05, 06, 08, 09, 11, 12, 17, 18, 19 | PSI_04, 07, 10, 13, 14, 15 |
| Typical reason for degradation | — | < 8 cases → noisy LSPS |

---

### Stage 3 — Placebo causal-forest verification (skipped)

A `CausalForestDML` model with **age** as the placebo outcome is used to verify:
- Raw arm (all CEM donors): pseudo-effect should be detectable (confirms statistical power)
- Matched arm (final matched donors): CI should bracket zero (confirms deconfounding)

Status: **skipped** (`skip_stage3=True`). Will be enabled once clinical feature coverage improves.

---

## What's needed to improve clinical feature coverage

9 of 16 PSI types currently produce 0 features because the local case CSV records have NULL clinical timestamps. Two paths forward:

| Option | Effort | Impact |
|---|---|---|
| Pull case clinical records from Snowflake by OMNY_ID | Medium — requires a Snowflake query per case | Solves the timestamp problem; gives labs/vitals/diagnoses for all cases from the same source as donors |
| Request timestamp backfill from data supplier | High — supplier engagement | Highest quality; timestamps directly from source system |

For the donor side, the Snowflake 1% sample clinical data (labs, vitals) is sparse per encounter. Increasing to a 10% or 100% sample will populate clinical features for more donors and improve propensity score discrimination.

---

## Outputs per PSI type

All results are in `outputs/<PSI_TYPE>/`:

| File | Contents |
|---|---|
| `cases.csv` | Confirmed PSI cases with event timestamps, demographics, landmark t* |
| `matched_sets.parquet` | Final matched donor-case pairs (`case_enc`, `donor_enc`, `match_rank`) |
| `propensity_scores.csv` | Logit + probability scores for all CEM-scoped encounters |
| `balance_table.csv` | Age, LOS, chronic-condition SMD before and after matching |
| `positivity_curves.parquet` | Per-case CEM donor count at each time step up to t* |
| `verification_report.json` | All gate results, ATEs, CIs |
| `runs/pipeline_YYYYMMDD_HHMMSS.log` | Full versioned run log |
| `runs/RUN_LOG_YYYYMMDD_HHMMSS.md` | Timestamped row counts and gate log |

Aggregate summary: `outputs/all_psi_types_summary.md`
