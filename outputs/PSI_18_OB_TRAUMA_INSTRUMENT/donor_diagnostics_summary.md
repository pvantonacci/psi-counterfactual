# Counterfactual Donor Diagnostics — PSI_18_OB_TRAUMA_INSTRUMENT

**Run:** 20260606_192643
**Source:** OMNY DIAGNOSES table, via `dx_df_ft` (Stage 2a pull)
**Scope:** K:1 matched donor encounters only (control arm)
**Principal diagnosis:** `DX_PRIMARY = 'YES'` or `DX_LINE = 1`

## Summary

| Metric | Value |
|---|---|
| Matched donor encounters | 273 |
| Donors with OMNY diagnosis data | 1 (0%) |
| Donors without diagnosis data | 272 |
| Total diagnosis rows | 2 |
| Donors with a PSI-type ICD code | 0 (0% of those with dx) |

> PSI-type codes in donor records may reflect events occurring *after* the landmark window t\* — not violations of the event-free selection criterion.

## Diagnosis category breakdown

Unique donor encounters per ICD-10 chapter:

| ICD-10 Chapter | Donor Encounters |
|---|---|
| Factors Influencing Health Status (Z-codes) | 1 |
