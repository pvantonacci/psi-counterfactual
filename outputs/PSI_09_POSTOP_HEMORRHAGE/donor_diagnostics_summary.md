# Counterfactual Donor Diagnostics — PSI_09_POSTOP_HEMORRHAGE

**Run:** 20260607_223930
**Source:** OMNY DIAGNOSES table, via `dx_df_ft` (Stage 2a pull)
**Scope:** K:1 matched donor encounters only (control arm)
**Principal diagnosis:** `DX_PRIMARY = 'YES'` or `DX_LINE = 1`

## Summary

| Metric | Value |
|---|---|
| Matched donor encounters | 579 |
| Donors with OMNY diagnosis data | 1 (0%) |
| Donors without diagnosis data | 578 |
| Total diagnosis rows | 5 |
| Donors with a PSI-type ICD code | 0 (0% of those with dx) |

> PSI-type codes in donor records may reflect events occurring *after* the landmark window t\* — not violations of the event-free selection criterion.

## Diagnosis category breakdown

Unique donor encounters per ICD-10 chapter:

| ICD-10 Chapter | Donor Encounters |
|---|---|
| Mental & Behavioral Disorders | 1 |
| Neoplasms / Blood & Immune | 1 |
| Respiratory System | 1 |
