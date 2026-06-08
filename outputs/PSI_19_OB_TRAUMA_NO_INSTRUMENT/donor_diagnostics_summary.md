# Counterfactual Donor Diagnostics — PSI_19_OB_TRAUMA_NO_INSTRUMENT

**Run:** 20260607_225608
**Source:** OMNY DIAGNOSES table, via `dx_df_ft` (Stage 2a pull)
**Scope:** K:1 matched donor encounters only (control arm)
**Principal diagnosis:** `DX_PRIMARY = 'YES'` or `DX_LINE = 1`

## Summary

| Metric | Value |
|---|---|
| Matched donor encounters | 403 |
| Donors with OMNY diagnosis data | 2 (0%) |
| Donors without diagnosis data | 401 |
| Total diagnosis rows | 8 |
| Donors with a PSI-type ICD code | 0 (0% of those with dx) |

> PSI-type codes in donor records may reflect events occurring *after* the landmark window t\* — not violations of the event-free selection criterion.

## Diagnosis category breakdown

Unique donor encounters per ICD-10 chapter:

| ICD-10 Chapter | Donor Encounters |
|---|---|
| Factors Influencing Health Status (Z-codes) | 1 |
| Mental & Behavioral Disorders | 1 |
| Neoplasms / Blood & Immune | 1 |
| Pregnancy, Childbirth & Puerperium | 1 |
| Respiratory System | 1 |
