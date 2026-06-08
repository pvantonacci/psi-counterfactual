# Counterfactual Donor Diagnostics — PSI_11_POSTOP_RESP_FAILURE

**Run:** 20260607_224300
**Source:** OMNY DIAGNOSES table, via `dx_df_ft` (Stage 2a pull)
**Scope:** K:1 matched donor encounters only (control arm)
**Principal diagnosis:** `DX_PRIMARY = 'YES'` or `DX_LINE = 1`

## Summary

| Metric | Value |
|---|---|
| Matched donor encounters | 357 |
| Donors with OMNY diagnosis data | 2 (1%) |
| Donors without diagnosis data | 355 |
| Total diagnosis rows | 10 |
| Donors with a PSI-type ICD code | 0 (0% of those with dx) |

> PSI-type codes in donor records may reflect events occurring *after* the landmark window t\* — not violations of the event-free selection criterion.

## Diagnosis category breakdown

Unique donor encounters per ICD-10 chapter:

| ICD-10 Chapter | Donor Encounters |
|---|---|
| Digestive System | 1 |
| Endocrine, Nutritional & Metabolic | 1 |
| Genitourinary System | 1 |
| Injury, Poisoning & External Causes | 1 |
| Musculoskeletal & Connective Tissue | 1 |
| Nervous System | 1 |
| Symptoms, Signs & Abnormal Findings | 1 |

## Top principal diagnoses

Most common ICD-10 codes among matched donors (principal diagnosis only):

| ICD-10 Code | Description | Chapter | Encounters |
|---|---|---|---|
| `K56.609` | SMALL BOWEL OBSTRUCTION | Digestive System | 1 |
| `K57.20` | DIVERTICULITIS OF LARGE INTESTINE WITH PERFORATION AND ABSCESS, UNSPEC | Digestive System | 1 |
| `N18.6` | ESRD (END STAGE RENAL DISEASE) | Genitourinary System | 1 |
| `R78.81` | BACTEREMIA | Symptoms, Signs & Abnormal Findings | 1 |
