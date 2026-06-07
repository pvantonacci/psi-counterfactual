# PSI Aggregated Dataset

This folder contains the final curated PSI case dataset, combining inpatient-confirmed cases across two pipeline runs.

---

## Files

### `psi_inpatient_cases.csv` — 255 rows

The full combined dataset: all inpatient-confirmed positives from both pipeline runs, plus 5 inpatient-confirmed negatives per PSI measure.

**How it was produced:**

Positives were drawn from two sources and merged (de-duplicated by ENCOUNTER_ID + PSI_CODE):

1. **`outputs/psi_cases_final.csv`** — the pre-inpatient-filter pipeline run. Contains 93 positives total; 51 of those had `ENCOUNTER_TYPE = 'HOSPITAL ENCOUNTER'` and were kept.

2. **`outputs/inpatient/psi_all_classified.csv`** — the inpatient-filtered pipeline run (2,467 candidates, Stage A filtered to inpatient encounters via `OMNY_REPL_ID.CUSTOM.ENCOUNTERS` join). Positives selected with: `PSI_EVENT_PRESENT=YES`, `HOSPITAL_ACQUIRED_NOT_POA` in (YES, UNCERTAIN), `IS_EXCLUSION=NO`, `CONFIDENCE=HIGH`.

Where the same encounter appeared in both sources, the `psi_cases_final.csv` version was kept (it carries the enriched `LOS_BUCKET`, `COMPLEXITY_TIER`, `LOS_SOURCE` columns added by `add_classification_columns.py`).

Negatives were taken from `outputs/inpatient/psi_all_classified.csv` with `PSI_EVENT_PRESENT=NO`, `CONFIDENCE=HIGH`, up to 5 per measure, excluding any encounter already in the positive set.

**Positive case counts by measure:**

| PSI | Positives | Negatives |
|-----|-----------|-----------|
| PSI_17 Birth Trauma | 42 | 5 |
| PSI_19 OB Trauma (No Instrument) | 38 | 3 |
| PSI_15 Accidental Puncture | 29 | 5 |
| PSI_09 Postop Hemorrhage | 18 | 5 |
| PSI_18 OB Trauma (Instrument) | 14 | 5 |
| PSI_05 Retained Item | 11 | 5 |
| PSI_06 Iatrogenic Pneumothorax | 8 | 5 |
| PSI_07 CLABSI | 4 | 5 |
| PSI_11 Postop Resp Failure | 4 | 5 |
| PSI_14 Wound Dehiscence | 4 | 5 |
| PSI_04 Failure to Rescue | 3 | 5 |
| PSI_03 Pressure Ulcer | 1 | 5 |
| PSI_13 Postop Sepsis | 1 | 5 |
| PSI_08 Fall Fracture | 0 | 5 |
| PSI_10 Postop AKI/Dialysis | 0 | 5 |
| PSI_12 Periop PE/DVT | 0 | 5 |

PSI_08, PSI_10, and PSI_12 have zero positives — across all candidate encounters Claude consistently classifies the relevant ICD codes as present on admission rather than hospital-acquired.

---

### `psi_inpatient_cases_downsampled.csv` — 163 rows

A downsampled version of `psi_inpatient_cases.csv` with positives capped at 10 per measure, and the LOS/complexity enrichment columns added via `add_classification_columns.py`.

Additional columns vs `psi_inpatient_cases.csv`:
- `LOS_BUCKET`: `short` (3–4d), `medium` (5–6d), `long` (7+d)
- `COMPLEXITY_TIER`: `easy`, `medium`, `hard`, or `meta_hard` (age 20–60 with ≥2 ICU days)
- `LOS_SOURCE`: whether LOS came from `EN_LOS` or was imputed from note date span

---

### `tables/`

Structured EHR tables pulled from Snowflake for the encounters in this dataset via `pull_psi_tables.py`. Each file is one table from `OMNY_REPL_ID.CUSTOM`, filtered to the relevant encounters.
