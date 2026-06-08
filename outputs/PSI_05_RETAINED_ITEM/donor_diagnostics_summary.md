# Counterfactual Donor Diagnostics — PSI_05_RETAINED_ITEM

**Run:** 20260607_223355
**Source:** OMNY DIAGNOSES table, via `dx_df_ft` (Stage 2a pull)
**Scope:** K:1 matched donor encounters only (control arm)
**Principal diagnosis:** `DX_PRIMARY = 'YES'` or `DX_LINE = 1`

## Summary

| Metric | Value |
|---|---|
| Matched donor encounters | 355 |
| Donors with OMNY diagnosis data | 2 (1%) |
| Donors without diagnosis data | 353 |
| Total diagnosis rows | 48 |
| Donors with a PSI-type ICD code | 2 (100% of those with dx) |

> PSI-type codes in donor records may reflect events occurring *after* the landmark window t\* — not violations of the event-free selection criterion.

## Diagnosis category breakdown

Unique donor encounters per ICD-10 chapter:

| ICD-10 Chapter | Donor Encounters |
|---|---|
| Circulatory System | 2 |
| Endocrine, Nutritional & Metabolic | 2 |
| Factors Influencing Health Status (Z-codes) | 2 |
| Genitourinary System | 2 |
| Symptoms, Signs & Abnormal Findings | 2 |
| Neoplasms / Blood & Immune | 2 |
| Skin & Subcutaneous Tissue | 2 |
| Nervous System | 2 |
| Digestive System | 1 |
| Infectious & Parasitic Diseases | 1 |
| Musculoskeletal & Connective Tissue | 1 |
| Respiratory System | 1 |

## PSI-type codes found in donor records

**2** donor encounter(s) contain an ICD-10 code matching the PSI_05_RETAINED_ITEM PSI criterion:

- `L89.153` — 2 occurrence(s)
- `A41.9` — 1 occurrence(s)
- `N17.9` — 1 occurrence(s)
- `J15.1` — 1 occurrence(s)
- `R65.21` — 1 occurrence(s)
