# Counterfactual Donor Diagnostics — PSI_06_IATROGENIC_PNEUMOTHORAX

**Run:** 20260607_223540
**Source:** OMNY DIAGNOSES table, via `dx_df_ft` (Stage 2a pull)
**Scope:** K:1 matched donor encounters only (control arm)
**Principal diagnosis:** `DX_PRIMARY = 'YES'` or `DX_LINE = 1`

## Summary

| Metric | Value |
|---|---|
| Matched donor encounters | 222 |
| Donors with OMNY diagnosis data | 2 (1%) |
| Donors without diagnosis data | 220 |
| Total diagnosis rows | 9 |
| Donors with a PSI-type ICD code | 0 (0% of those with dx) |

> PSI-type codes in donor records may reflect events occurring *after* the landmark window t\* — not violations of the event-free selection criterion.

## Diagnosis category breakdown

Unique donor encounters per ICD-10 chapter:

| ICD-10 Chapter | Donor Encounters |
|---|---|
| Symptoms, Signs & Abnormal Findings | 2 |
| Circulatory System | 1 |
| Digestive System | 1 |
| Neoplasms / Blood & Immune | 1 |

## Top principal diagnoses

Most common ICD-10 codes among matched donors (principal diagnosis only):

| ICD-10 Code | Description | Chapter | Encounters |
|---|---|---|---|
| `I21.4` | NSTEMI (NON-ST ELEVATED MYOCARDIAL INFARCTION) (BOTH/HCC) | Circulatory System | 1 |
| `K62.5` | BRBPR (BRIGHT RED BLOOD PER RECTUM) | Digestive System | 1 |
| `R07.9` | CHEST PAIN | Symptoms, Signs & Abnormal Findings | 1 |
| `R53.1` | WEAKNESS | Symptoms, Signs & Abnormal Findings | 1 |
