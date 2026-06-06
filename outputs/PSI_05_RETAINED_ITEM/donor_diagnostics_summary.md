# Counterfactual Donor Diagnostics — PSI_05_RETAINED_ITEM

**Run:** 20260606_191109
**Source:** OMNY DIAGNOSES table, via `dx_df_ft` (Stage 2a pull)
**Scope:** K:1 matched donor encounters only (control arm)
**Principal diagnosis:** `DX_PRIMARY = 'YES'` or `DX_LINE = 1`

## Summary

| Metric | Value |
|---|---|
| Matched donor encounters | 394 |
| Donors with OMNY diagnosis data | 1 (0%) |
| Donors without diagnosis data | 393 |
| Total diagnosis rows | 27 |
| Donors with a PSI-type ICD code | 1 (100% of those with dx) |

> PSI-type codes in donor records may reflect events occurring *after* the landmark window t\* — not violations of the event-free selection criterion.

## Diagnosis category breakdown

Unique donor encounters per ICD-10 chapter:

| ICD-10 Chapter | Donor Encounters |
|---|---|
| Circulatory System | 1 |
| Endocrine, Nutritional & Metabolic | 1 |
| Eye / Ear | 1 |
| Factors Influencing Health Status (Z-codes) | 1 |
| Genitourinary System | 1 |
| Neoplasms / Blood & Immune | 1 |
| Respiratory System | 1 |
| Symptoms, Signs & Abnormal Findings | 1 |

## PSI-type codes found in donor records

**1** donor encounter(s) contain an ICD-10 code matching the PSI_05_RETAINED_ITEM PSI criterion:

- `J96.01` — 1 occurrence(s)
- `I46.8` — 1 occurrence(s)
