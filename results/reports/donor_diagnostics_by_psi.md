# Counterfactual Donor Diagnostics — by PSI Type

**Generated:** 2026-06-05 20:50
**Source:** `OMNY_REPL_ID.CUSTOM.DIAGNOSES` (Snowflake) for all K:1 matched donor encounters
**Principal diagnosis:** `DX_PRIMARY = 'YES'` or `DX_LINE = 1`

---

## Purpose

For each PSI type, this document answers: **What were the most common reasons for hospitalization
among the matched counterfactual (control) donors — patients who were admitted under similar
circumstances but did NOT experience the adverse event at the landmark time?**

This helps validate that the control group captures a realistic mix of comparable admissions,
and reveals the clinical contexts where each PSI type could plausibly develop but didn't.

A secondary check flags donors whose diagnosis list contains a PSI-type ICD-10 code —
which could indicate the event occurred after the landmark window, or that the matching
captured patients who eventually did experience an adverse outcome.

---

## Overall summary

| Metric | Value |
|---|---|
| Total matched pairs (all types) | 3,626 |
| Unique donor encounters | 2,801 |
| Donors with diagnoses retrieved | 2,527 (90%) |
| Diagnosis rows pulled | 32,739 |
| Donors with any PSI-type ICD code | 907 (32%) |

> **Coverage note:** Diagnoses are only available for donors whose encounters appear in the OMNY
> DIAGNOSES table. Encounters with no diagnosis rows (e.g., encounters at suppliers that do not
> submit diagnostic billing data to OMNY) are counted but excluded from the diagnostic tables.

---

## Results by PSI type

### PSI-03 Pressure Ulcer

| | |
|---|---|
| Matched donor encounters | 150 |
| Donors with diagnoses in OMNY | 146 (97%) |
| Donors without diagnosis data | 4 |
| Donors with a PSI-type ICD code in record | 5 (3% of those with dx) |

**Diagnosis category breakdown** (unique encounters per chapter):

| ICD-10 Chapter | Donor Encounters |
|---|---|
| Factors Influencing Health Status (Z-codes) | 134 |
| Circulatory System | 127 |
| Endocrine, Nutritional & Metabolic | 125 |
| Symptoms, Signs & Abnormal Findings | 100 |
| Genitourinary System | 82 |
| Mental & Behavioral Disorders | 67 |
| Digestive System | 67 |
| Nervous System | 63 |
| Neoplasms / Blood & Immune | 62 |
| Respiratory System | 62 |
| Musculoskeletal & Connective Tissue | 58 |
| Injury, Poisoning & External Causes | 35 |
| Infectious & Parasitic Diseases | 34 |
| Neoplasms | 21 |
| Skin & Subcutaneous Tissue | 18 |
| Eye / Ear | 17 |
| External Causes of Morbidity | 11 |
| Congenital Malformations | 5 |
| Other | 5 |

> **PSI flag detail:** 5 donor encounter(s) carry an ICD-10 code
> matching the PSI-03 Pressure Ulcer PSI criterion. Top codes: `L89.312` (n=2), `L89.152` (n=2), `L89.153` (n=1), `L89.612` (n=1), `L89.611` (n=1)
> This may reflect events occurring *after* the landmark window t\*, not violations of
> the event-free selection criterion (which only applies up to t\*).

---

### PSI-04 Failure to Rescue

| | |
|---|---|
| Matched donor encounters | 99 |
| Donors with diagnoses in OMNY | 91 (92%) |
| Donors without diagnosis data | 8 |
| Donors with a PSI-type ICD code in record | 16 (18% of those with dx) |

**Diagnosis category breakdown** (unique encounters per chapter):

| ICD-10 Chapter | Donor Encounters |
|---|---|
| Symptoms, Signs & Abnormal Findings | 48 |
| Circulatory System | 32 |
| Digestive System | 20 |
| Genitourinary System | 19 |
| Endocrine, Nutritional & Metabolic | 16 |
| Respiratory System | 16 |
| Nervous System | 14 |
| Factors Influencing Health Status (Z-codes) | 14 |
| Neoplasms / Blood & Immune | 11 |
| Infectious & Parasitic Diseases | 10 |
| Injury, Poisoning & External Causes | 9 |
| Mental & Behavioral Disorders | 7 |
| Musculoskeletal & Connective Tissue | 6 |
| Neoplasms | 5 |
| Other | 2 |
| Skin & Subcutaneous Tissue | 2 |
| Eye / Ear | 1 |

**Top 15 principal diagnoses** (by ICD-10 code):

| ICD-10 Code | Description | Chapter | Encounters |
|---|---|---|---|
| `K56.609` | SMALL BOWEL OBSTRUCTION (HCC) | Digestive System | 3 |
| `I50.9` | ACUTE ON CHRONIC CONGESTIVE HEART FAILURE, UNSPECIFIED HEART FAILURE T | Circulatory System | 3 |
| `R07.9` | CHEST PAIN, UNSPECIFIED TYPE | Symptoms, Signs & Abnormal Findings | 3 |
| `R41.82` | ALTERED MENTAL STATUS, UNSPECIFIED ALTERED MENTAL STATUS TYPE | Symptoms, Signs & Abnormal Findings | 3 |
| `I21.4` | NSTEMI (NON-ST ELEVATED MYOCARDIAL INFARCTION) (HCC) | Circulatory System | 2 |
| `G89.18` | POST-OP PAIN | Nervous System | 2 |
| `J18.9` | PNEUMONIA DUE TO INFECTIOUS ORGANISM, UNSPECIFIED LATERALITY, UNSPECIF ⚠️ PSI | Respiratory System | 2 |
| `K92.2` | GASTROINTESTINAL HEMORRHAGE, UNSPECIFIED GASTROINTESTINAL HEMORRHAGE T ⚠️ PSI | Digestive System | 2 |
| `R10.32` | LEFT LOWER QUADRANT ABDOMINAL PAIN | Symptoms, Signs & Abnormal Findings | 2 |
| `R07.9` | CHEST PAIN | Symptoms, Signs & Abnormal Findings | 2 |
| `G89.18` | ACUTE POSTOPERATIVE ABDOMINAL PAIN | Nervous System | 1 |
| `G89.18` | POSTOPERATIVE PAIN | Nervous System | 1 |
| `G93.89` | BRAIN MASS | Nervous System | 1 |
| `E87.1` | HYPONATREMIA | Endocrine, Nutritional & Metabolic | 1 |
| `D70.9` | NEUTROPENIC FEVER (HCC) | Neoplasms / Blood & Immune | 1 |

> **PSI flag detail:** 16 donor encounter(s) carry an ICD-10 code
> matching the PSI-04 Failure to Rescue PSI criterion. Top codes: `A41.9` (n=8), `J18.9` (n=7), `K92.2` (n=4), `R65.21` (n=1), `I26.99` (n=1)
> This may reflect events occurring *after* the landmark window t\*, not violations of
> the event-free selection criterion (which only applies up to t\*).

---

### PSI-05 Retained Item

| | |
|---|---|
| Matched donor encounters | 402 |
| Donors with diagnoses in OMNY | 323 (80%) |
| Donors without diagnosis data | 79 |
| Donors with a PSI-type ICD code in record | 0 (0% of those with dx) |

**Diagnosis category breakdown** (unique encounters per chapter):

| ICD-10 Chapter | Donor Encounters |
|---|---|
| Factors Influencing Health Status (Z-codes) | 144 |
| Symptoms, Signs & Abnormal Findings | 133 |
| Endocrine, Nutritional & Metabolic | 113 |
| Circulatory System | 95 |
| Digestive System | 76 |
| Neoplasms / Blood & Immune | 69 |
| Genitourinary System | 68 |
| Nervous System | 63 |
| Respiratory System | 59 |
| Musculoskeletal & Connective Tissue | 56 |
| Mental & Behavioral Disorders | 55 |
| Infectious & Parasitic Diseases | 41 |
| Injury, Poisoning & External Causes | 41 |
| Skin & Subcutaneous Tissue | 37 |
| Neoplasms | 22 |
| External Causes of Morbidity | 21 |
| Pregnancy, Childbirth & Puerperium | 19 |
| Eye / Ear | 7 |
| Other | 7 |
| Congenital Malformations | 4 |

**Top 15 principal diagnoses** (by ICD-10 code):

| ICD-10 Code | Description | Chapter | Encounters |
|---|---|---|---|
| `G89.18` | POST-OPERATIVE PAIN | Nervous System | 5 |
| `E87.1` | HYPONATREMIA | Endocrine, Nutritional & Metabolic | 3 |
| `G89.18` | POST-OP PAIN | Nervous System | 3 |
| `J18.9` | MULTIFOCAL PNEUMONIA | Respiratory System | 3 |
| `J44.1` | COPD WITH ACUTE EXACERBATION (HCC) | Respiratory System | 3 |
| `L03.115` | CELLULITIS OF RIGHT LOWER EXTREMITY | Skin & Subcutaneous Tissue | 3 |
| `K57.92` | ACUTE DIVERTICULITIS | Digestive System | 3 |
| `R11.2` | NAUSEA AND VOMITING, UNSPECIFIED VOMITING TYPE | Symptoms, Signs & Abnormal Findings | 3 |
| `N17.9` | AKI (ACUTE KIDNEY INJURY) (HCC) | Genitourinary System | 3 |
| `R52` | POSTPARTUM PAIN | Symptoms, Signs & Abnormal Findings | 3 |
| `G89.18` | POSTOPERATIVE PAIN | Nervous System | 2 |
| `J44.1` | COPD EXACERBATION (HCC) | Respiratory System | 2 |
| `F32.2` | CURRENT SEVERE EPISODE OF MAJOR DEPRESSIVE DISORDER WITHOUT PSYCHOTIC  | Mental & Behavioral Disorders | 2 |
| `R09.02` | HYPOXIA | Symptoms, Signs & Abnormal Findings | 2 |
| `R06.02` | SHORTNESS OF BREATH | Symptoms, Signs & Abnormal Findings | 2 |

---

### PSI-06 Iatrogenic Pneumothorax

| | |
|---|---|
| Matched donor encounters | 223 |
| Donors with diagnoses in OMNY | 194 (87%) |
| Donors without diagnosis data | 29 |
| Donors with a PSI-type ICD code in record | 0 (0% of those with dx) |

**Diagnosis category breakdown** (unique encounters per chapter):

| ICD-10 Chapter | Donor Encounters |
|---|---|
| Symptoms, Signs & Abnormal Findings | 106 |
| Circulatory System | 84 |
| Endocrine, Nutritional & Metabolic | 66 |
| Factors Influencing Health Status (Z-codes) | 50 |
| Respiratory System | 43 |
| Genitourinary System | 41 |
| Mental & Behavioral Disorders | 38 |
| Nervous System | 36 |
| Injury, Poisoning & External Causes | 35 |
| Musculoskeletal & Connective Tissue | 32 |
| Neoplasms / Blood & Immune | 28 |
| Digestive System | 27 |
| Infectious & Parasitic Diseases | 20 |
| Skin & Subcutaneous Tissue | 20 |
| External Causes of Morbidity | 14 |
| Neoplasms | 10 |
| Other | 8 |
| Eye / Ear | 7 |

**Top 15 principal diagnoses** (by ICD-10 code):

| ICD-10 Code | Description | Chapter | Encounters |
|---|---|---|---|
| `R06.02` | SHORTNESS OF BREATH | Symptoms, Signs & Abnormal Findings | 6 |
| `R07.9` | CHEST PAIN, UNSPECIFIED TYPE | Symptoms, Signs & Abnormal Findings | 5 |
| `Z98.890` | OTHER SPECIFIED POSTPROCEDURAL STATES | Factors Influencing Health Status (Z-codes) | 5 |
| `J96.01` | ACUTE RESPIRATORY FAILURE WITH HYPOXIA (HCC) | Respiratory System | 4 |
| `R41.82` | ALTERED MENTAL STATUS, UNSPECIFIED ALTERED MENTAL STATUS TYPE | Symptoms, Signs & Abnormal Findings | 4 |
| `W19.XXXA` | FALL, INITIAL ENCOUNTER | External Causes of Morbidity | 4 |
| `R45.851` | SUICIDAL IDEATION | Symptoms, Signs & Abnormal Findings | 3 |
| `I50.9` | ACUTE ON CHRONIC CONGESTIVE HEART FAILURE, UNSPECIFIED HEART FAILURE T | Circulatory System | 3 |
| `N30.01` | ACUTE CYSTITIS WITH HEMATURIA | Genitourinary System | 3 |
| `I16.1` | HYPERTENSIVE EMERGENCY | Circulatory System | 2 |
| `I63.9` | CEREBROVASCULAR ACCIDENT (CVA), UNSPECIFIED MECHANISM (HCC) | Circulatory System | 2 |
| `J18.9` | PNEUMONIA OF BOTH LOWER LOBES DUE TO INFECTIOUS ORGANISM | Respiratory System | 2 |
| `I50.9` | ACUTE ON CHRONIC CONGESTIVE HEART FAILURE, UNSPECIFIED HEART FAILURE T | Circulatory System | 2 |
| `F10.939` | ALCOHOL WITHDRAWAL SYNDROME WITH COMPLICATION (HCC) | Mental & Behavioral Disorders | 2 |
| `I48.91` | ATRIAL FIBRILLATION WITH RVR (HCC) | Circulatory System | 2 |

---

### PSI-07 CLABSI

| | |
|---|---|
| Matched donor encounters | 159 |
| Donors with diagnoses in OMNY | 150 (94%) |
| Donors without diagnosis data | 9 |
| Donors with a PSI-type ICD code in record | 0 (0% of those with dx) |

**Diagnosis category breakdown** (unique encounters per chapter):

| ICD-10 Chapter | Donor Encounters |
|---|---|
| Circulatory System | 120 |
| Factors Influencing Health Status (Z-codes) | 113 |
| Endocrine, Nutritional & Metabolic | 106 |
| Symptoms, Signs & Abnormal Findings | 95 |
| Digestive System | 68 |
| Genitourinary System | 67 |
| Mental & Behavioral Disorders | 67 |
| Nervous System | 63 |
| Respiratory System | 61 |
| Musculoskeletal & Connective Tissue | 52 |
| Neoplasms / Blood & Immune | 51 |
| Infectious & Parasitic Diseases | 31 |
| Injury, Poisoning & External Causes | 27 |
| Skin & Subcutaneous Tissue | 16 |
| External Causes of Morbidity | 13 |
| Other | 8 |
| Eye / Ear | 7 |
| Neoplasms | 5 |
| Congenital Malformations | 2 |

**Top 15 principal diagnoses** (by ICD-10 code):

| ICD-10 Code | Description | Chapter | Encounters |
|---|---|---|---|
| `I16.0` | HYPERTENSIVE URGENCY | Circulatory System | 1 |
| `I26.99` | ACUTE PULMONARY EMBOLISM, UNSPECIFIED PULMONARY EMBOLISM TYPE, UNSPECI | Circulatory System | 1 |
| `I50.23` | ACUTE ON CHRONIC SYSTOLIC CHF (CONGESTIVE HEART FAILURE) (HCC) | Circulatory System | 1 |
| `J96.00` | ACUTE RESPIRATORY FAILURE, UNSPECIFIED WHETHER WITH HYPOXIA OR HYPERCA | Respiratory System | 1 |
| `J96.21` | ACUTE ON CHRONIC RESPIRATORY FAILURE WITH HYPOXIA AND HYPERCAPNIA | Respiratory System | 1 |
| `J96.22` | ACUTE ON CHRONIC RESPIRATORY FAILURE WITH HYPOXIA AND HYPERCAPNIA | Respiratory System | 1 |
| `K70.31` | ASCITES DUE TO ALCOHOLIC CIRRHOSIS (HCC) | Digestive System | 1 |
| `L89.520` | PRESSURE ULCER OF ANKLE, LEFT, UNSTAGEABLE (HCC) | Skin & Subcutaneous Tissue | 1 |
| `M86.172` | ACUTE OSTEOMYELITIS OF LEFT FOOT (HCC) | Musculoskeletal & Connective Tissue | 1 |
| `N12` | PYELONEPHRITIS | Genitourinary System | 1 |
| `R07.2` | PRECORDIAL CHEST PAIN | Symptoms, Signs & Abnormal Findings | 1 |
| `R10.9` | ABDOMINAL PAIN, UNSPECIFIED ABDOMINAL LOCATION | Symptoms, Signs & Abnormal Findings | 1 |
| `R41.82` | ALTERED MENTAL STATUS | Symptoms, Signs & Abnormal Findings | 1 |
| `R53.1` | GENERAL WEAKNESS | Symptoms, Signs & Abnormal Findings | 1 |
| `R56.9` | SEIZURE | Symptoms, Signs & Abnormal Findings | 1 |

---

### PSI-08 Fall/Fracture

| | |
|---|---|
| Matched donor encounters | 73 |
| Donors with diagnoses in OMNY | 70 (96%) |
| Donors without diagnosis data | 3 |
| Donors with a PSI-type ICD code in record | 3 (4% of those with dx) |

**Diagnosis category breakdown** (unique encounters per chapter):

| ICD-10 Chapter | Donor Encounters |
|---|---|
| Circulatory System | 55 |
| Factors Influencing Health Status (Z-codes) | 47 |
| Endocrine, Nutritional & Metabolic | 43 |
| Symptoms, Signs & Abnormal Findings | 40 |
| Respiratory System | 29 |
| Mental & Behavioral Disorders | 28 |
| Genitourinary System | 25 |
| Nervous System | 25 |
| Digestive System | 24 |
| Musculoskeletal & Connective Tissue | 24 |
| Neoplasms / Blood & Immune | 24 |
| Injury, Poisoning & External Causes | 14 |
| Infectious & Parasitic Diseases | 13 |
| Skin & Subcutaneous Tissue | 13 |
| External Causes of Morbidity | 11 |
| Eye / Ear | 6 |
| Other | 3 |
| Neoplasms | 2 |

**Top 15 principal diagnoses** (by ICD-10 code):

| ICD-10 Code | Description | Chapter | Encounters |
|---|---|---|---|
| `I48.0` | PAROXYSMAL ATRIAL FIBRILLATION | Circulatory System | 2 |
| `F10.930` | ALCOHOL WITHDRAWAL SYNDROME WITHOUT COMPLICATION (CMS/HCC) | Mental & Behavioral Disorders | 1 |
| `I48.91` | ATRIAL FIBRILLATION BY ELECTROCARDIOGRAM (MULTI) | Circulatory System | 1 |
| `I48.91` | ATRIAL FIBRILLATION WITH RVR | Circulatory System | 1 |
| `I50.41` | ACUTE COMBINED SYSTOLIC AND DIASTOLIC HEART FAILURE | Circulatory System | 1 |
| `I50.9` | ACUTE DECOMPENSATED HEART FAILURE (MULTI) | Circulatory System | 1 |
| `I50.9` | CONGESTIVE HEART FAILURE, UNSPECIFIED HF CHRONICITY, UNSPECIFIED HEART | Circulatory System | 1 |
| `I61.9` | NONTRAUMATIC THALAMIC HEMORRHAGE | Circulatory System | 1 |
| `I62.9` | INTRACRANIAL BLEED | Circulatory System | 1 |
| `J18.9` | PNEUMONIA OF RIGHT LOWER LOBE DUE TO INFECTIOUS ORGANISM | Respiratory System | 1 |
| `J90` | PLEURAL EFFUSION | Respiratory System | 1 |
| `K92.2` | GASTROINTESTINAL HEMORRHAGE, UNSPECIFIED GASTROINTESTINAL HEMORRHAGE T | Digestive System | 1 |
| `L02.419` | LEG ABSCESS | Skin & Subcutaneous Tissue | 1 |
| `L03.115` | CELLULITIS OF RIGHT LOWER EXTREMITY | Skin & Subcutaneous Tissue | 1 |
| `M54.9` | BACK PAIN, UNSPECIFIED BACK LOCATION, UNSPECIFIED BACK PAIN LATERALITY | Musculoskeletal & Connective Tissue | 1 |

> **PSI flag detail:** 3 donor encounter(s) carry an ICD-10 code
> matching the PSI-08 Fall/Fracture PSI criterion. Top codes: `S72.011A` (n=1), `S42.292A` (n=1), `S72.141A` (n=1)
> This may reflect events occurring *after* the landmark window t\*, not violations of
> the event-free selection criterion (which only applies up to t\*).

---

### PSI-09 Postop Hemorrhage

| | |
|---|---|
| Matched donor encounters | 419 |
| Donors with diagnoses in OMNY | 356 (85%) |
| Donors without diagnosis data | 63 |
| Donors with a PSI-type ICD code in record | 0 (0% of those with dx) |

**Diagnosis category breakdown** (unique encounters per chapter):

| ICD-10 Chapter | Donor Encounters |
|---|---|
| Factors Influencing Health Status (Z-codes) | 191 |
| Circulatory System | 172 |
| Symptoms, Signs & Abnormal Findings | 155 |
| Endocrine, Nutritional & Metabolic | 153 |
| Mental & Behavioral Disorders | 115 |
| Digestive System | 108 |
| Genitourinary System | 98 |
| Respiratory System | 81 |
| Nervous System | 80 |
| Injury, Poisoning & External Causes | 68 |
| Neoplasms / Blood & Immune | 61 |
| Musculoskeletal & Connective Tissue | 60 |
| Infectious & Parasitic Diseases | 37 |
| External Causes of Morbidity | 37 |
| Skin & Subcutaneous Tissue | 33 |
| Neoplasms | 22 |
| Pregnancy, Childbirth & Puerperium | 17 |
| Other | 7 |
| Eye / Ear | 6 |
| Congenital Malformations | 3 |

**Top 15 principal diagnoses** (by ICD-10 code):

| ICD-10 Code | Description | Chapter | Encounters |
|---|---|---|---|
| `I21.4` | NSTEMI (NON-ST ELEVATED MYOCARDIAL INFARCTION) (HCC) | Circulatory System | 3 |
| `F32.A` | DEPRESSION WITH SUICIDAL IDEATION | Mental & Behavioral Disorders | 3 |
| `R45.851` | DEPRESSION WITH SUICIDAL IDEATION | Symptoms, Signs & Abnormal Findings | 3 |
| `R07.9` | CHEST PAIN | Symptoms, Signs & Abnormal Findings | 3 |
| `R45.851` | SUICIDAL IDEATION | Symptoms, Signs & Abnormal Findings | 3 |
| `F29` | PSYCHOSIS, UNSPECIFIED PSYCHOSIS TYPE (HCC) | Mental & Behavioral Disorders | 2 |
| `E87.6` | HYPOKALEMIA | Endocrine, Nutritional & Metabolic | 2 |
| `I21.4` | NSTEMI (NON-ST ELEVATED MYOCARDIAL INFARCTION) | Circulatory System | 2 |
| `I46.9` | CARDIAC ARREST (HCC) | Circulatory System | 2 |
| `I21.4` | NSTEMI (NON-ST ELEVATED MYOCARDIAL INFARCTION) (CMS/HCC) | Circulatory System | 2 |
| `L03.116` | CELLULITIS OF LEFT LOWER EXTREMITY | Skin & Subcutaneous Tissue | 2 |
| `L02.91` | ABSCESS | Skin & Subcutaneous Tissue | 2 |
| `J96.01` | ACUTE RESPIRATORY FAILURE WITH HYPOXIA (HCC) | Respiratory System | 2 |
| `N17.9` | ACUTE RENAL FAILURE, UNSPECIFIED ACUTE RENAL FAILURE TYPE (HCC) | Genitourinary System | 2 |
| `K52.9` | ACUTE COLITIS | Digestive System | 2 |

---

### PSI-10 Postop AKI/Dialysis

| | |
|---|---|
| Matched donor encounters | 62 |
| Donors with diagnoses in OMNY | 61 (98%) |
| Donors without diagnosis data | 1 |
| Donors with a PSI-type ICD code in record | 11 (18% of those with dx) |

**Diagnosis category breakdown** (unique encounters per chapter):

| ICD-10 Chapter | Donor Encounters |
|---|---|
| Factors Influencing Health Status (Z-codes) | 50 |
| Endocrine, Nutritional & Metabolic | 41 |
| Circulatory System | 35 |
| Mental & Behavioral Disorders | 27 |
| Digestive System | 26 |
| Respiratory System | 25 |
| Symptoms, Signs & Abnormal Findings | 25 |
| Neoplasms / Blood & Immune | 24 |
| Nervous System | 24 |
| Genitourinary System | 20 |
| Injury, Poisoning & External Causes | 18 |
| Musculoskeletal & Connective Tissue | 18 |
| Infectious & Parasitic Diseases | 16 |
| Skin & Subcutaneous Tissue | 9 |
| External Causes of Morbidity | 7 |
| Neoplasms | 3 |
| Other | 3 |
| Congenital Malformations | 1 |

**Top 14 principal diagnoses** (by ICD-10 code):

| ICD-10 Code | Description | Chapter | Encounters |
|---|---|---|---|
| `A41.9` | SEPSIS WITHOUT ACUTE ORGAN DYSFUNCTION, DUE TO UNSPECIFIED ORGANISM (H | Infectious & Parasitic Diseases | 1 |
| `G89.18` | POST-OP PAIN | Nervous System | 1 |
| `J12.82` | PNEUMONIA DUE TO COVID-19 VIRUS | Respiratory System | 1 |
| `J96.01` | ACUTE HYPOXEMIC RESPIRATORY FAILURE DUE TO COVID-19 (HCC) | Respiratory System | 1 |
| `K11.3` | PAROTID ABSCESS | Digestive System | 1 |
| `K56.600` | SMALL BOWEL OBSTRUCTION, PARTIAL (HCC) | Digestive System | 1 |
| `L03.116` | CELLULITIS OF LEFT LOWER EXTREMITY | Skin & Subcutaneous Tissue | 1 |
| `M79.89` | LEG SWELLING | Musculoskeletal & Connective Tissue | 1 |
| `N39.0` | ACUTE UTI | Genitourinary System | 1 |
| `R65.10` | SIRS (SYSTEMIC INFLAMMATORY RESPONSE SYNDROME) (HCC) | Symptoms, Signs & Abnormal Findings | 1 |
| `S22.42XA` | CLOSED FRACTURE OF MULTIPLE RIBS OF LEFT SIDE, INITIAL ENCOUNTER | Injury, Poisoning & External Causes | 1 |
| `T18.198A` | OTHER FOREIGN OBJECT IN ESOPHAGUS CAUSING OTHER INJURY, INITIAL ENCOUN | Injury, Poisoning & External Causes | 1 |
| `U07.1` | ACUTE HYPOXEMIC RESPIRATORY FAILURE DUE TO COVID-19 (HCC) | Other | 1 |
| `U07.1` | PNEUMONIA DUE TO COVID-19 VIRUS | Other | 1 |

> **PSI flag detail:** 11 donor encounter(s) carry an ICD-10 code
> matching the PSI-10 Postop AKI/Dialysis PSI criterion. Top codes: `N17.9` (n=11)
> This may reflect events occurring *after* the landmark window t\*, not violations of
> the event-free selection criterion (which only applies up to t\*).

---

### PSI-11 Postop Resp Failure

| | |
|---|---|
| Matched donor encounters | 195 |
| Donors with diagnoses in OMNY | 188 (96%) |
| Donors without diagnosis data | 7 |
| Donors with a PSI-type ICD code in record | 24 (13% of those with dx) |

**Diagnosis category breakdown** (unique encounters per chapter):

| ICD-10 Chapter | Donor Encounters |
|---|---|
| Symptoms, Signs & Abnormal Findings | 112 |
| Circulatory System | 110 |
| Endocrine, Nutritional & Metabolic | 87 |
| Factors Influencing Health Status (Z-codes) | 87 |
| Genitourinary System | 65 |
| Respiratory System | 61 |
| Digestive System | 48 |
| Musculoskeletal & Connective Tissue | 40 |
| Neoplasms / Blood & Immune | 37 |
| Nervous System | 35 |
| Mental & Behavioral Disorders | 31 |
| Injury, Poisoning & External Causes | 28 |
| Infectious & Parasitic Diseases | 23 |
| Neoplasms | 20 |
| Skin & Subcutaneous Tissue | 14 |
| External Causes of Morbidity | 14 |
| Eye / Ear | 10 |
| Other | 4 |
| Congenital Malformations | 1 |

**Top 15 principal diagnoses** (by ICD-10 code):

| ICD-10 Code | Description | Chapter | Encounters |
|---|---|---|---|
| `R07.9` | CHEST PAIN | Symptoms, Signs & Abnormal Findings | 10 |
| `R06.02` | SHORTNESS OF BREATH | Symptoms, Signs & Abnormal Findings | 4 |
| `D64.9` | ANEMIA, UNSPECIFIED TYPE | Neoplasms / Blood & Immune | 3 |
| `R06.02` | SOB (SHORTNESS OF BREATH) | Symptoms, Signs & Abnormal Findings | 3 |
| `N17.9` | AKI (ACUTE KIDNEY INJURY) | Genitourinary System | 3 |
| `R42` | POSTURAL DIZZINESS WITH NEAR SYNCOPE | Symptoms, Signs & Abnormal Findings | 2 |
| `R55` | POSTURAL DIZZINESS WITH NEAR SYNCOPE | Symptoms, Signs & Abnormal Findings | 2 |
| `R53.1` | WEAKNESS | Symptoms, Signs & Abnormal Findings | 2 |
| `I95.9` | HYPOTENSION | Circulatory System | 2 |
| `R00.0` | TACHYCARDIA | Symptoms, Signs & Abnormal Findings | 2 |
| `R53.1` | GENERALIZED WEAKNESS | Symptoms, Signs & Abnormal Findings | 2 |
| `R41.82` | ALTERED MENTAL STATUS, UNSPECIFIED ALTERED MENTAL STATUS TYPE | Symptoms, Signs & Abnormal Findings | 2 |
| `R06.03` | RESPIRATORY DISTRESS | Symptoms, Signs & Abnormal Findings | 2 |
| `J44.1` | COPD EXACERBATION | Respiratory System | 2 |
| `J96.01` | ACUTE RESPIRATORY FAILURE WITH HYPOXIA (HCC) ⚠️ PSI | Respiratory System | 2 |

> **PSI flag detail:** 24 donor encounter(s) carry an ICD-10 code
> matching the PSI-11 Postop Resp Failure PSI criterion. Top codes: `J96.01` (n=17), `J96.21` (n=8), `J96.22` (n=4), `J96.02` (n=3), `J96.20` (n=1)
> This may reflect events occurring *after* the landmark window t\*, not violations of
> the event-free selection criterion (which only applies up to t\*).

---

### PSI-12 Periop PE/DVT

| | |
|---|---|
| Matched donor encounters | 19 |
| Donors with diagnoses in OMNY | 18 (95%) |
| Donors without diagnosis data | 1 |
| Donors with a PSI-type ICD code in record | 0 (0% of those with dx) |

**Diagnosis category breakdown** (unique encounters per chapter):

| ICD-10 Chapter | Donor Encounters |
|---|---|
| Circulatory System | 11 |
| Symptoms, Signs & Abnormal Findings | 9 |
| Respiratory System | 7 |
| Endocrine, Nutritional & Metabolic | 7 |
| Factors Influencing Health Status (Z-codes) | 6 |
| Neoplasms / Blood & Immune | 6 |
| Genitourinary System | 5 |
| Infectious & Parasitic Diseases | 3 |
| Digestive System | 2 |
| Mental & Behavioral Disorders | 2 |
| Nervous System | 2 |
| Skin & Subcutaneous Tissue | 2 |
| Musculoskeletal & Connective Tissue | 1 |
| Injury, Poisoning & External Causes | 1 |

**Top 15 principal diagnoses** (by ICD-10 code):

| ICD-10 Code | Description | Chapter | Encounters |
|---|---|---|---|
| `R06.02` | SHORTNESS OF BREATH | Symptoms, Signs & Abnormal Findings | 2 |
| `E87.70` | HYPERVOLEMIA, UNSPECIFIED HYPERVOLEMIA TYPE | Endocrine, Nutritional & Metabolic | 1 |
| `G45.9` | TIA (TRANSIENT ISCHEMIC ATTACK) | Nervous System | 1 |
| `I15.0` | RENOVASCULAR HYPERTENSION | Circulatory System | 1 |
| `A04.72` | CLOSTRIDIUM DIFFICILE DIARRHEA | Infectious & Parasitic Diseases | 1 |
| `I48.91` | ATRIAL FIBRILLATION WITH RVR (HCC) | Circulatory System | 1 |
| `I50.9` | ACUTE EXACERBATION OF CHF (CONGESTIVE HEART FAILURE) | Circulatory System | 1 |
| `I63.9` | CEREBROVASCULAR ACCIDENT (CVA), UNSPECIFIED MECHANISM (HCC) | Circulatory System | 1 |
| `I50.9` | CHF (CONGESTIVE HEART FAILURE) (HCC) | Circulatory System | 1 |
| `K52.9` | COLITIS | Digestive System | 1 |
| `L97.519` | ULCER OF RIGHT FOOT, UNSPECIFIED ULCER STAGE (CMS/HCC) | Skin & Subcutaneous Tissue | 1 |
| `N12` | PYELONEPHRITIS | Genitourinary System | 1 |
| `J44.1` | COPD EXACERBATION (HCC) | Respiratory System | 1 |
| `N17.9` | AKI (ACUTE KIDNEY INJURY) | Genitourinary System | 1 |
| `N39.0` | UTI (URINARY TRACT INFECTION) | Genitourinary System | 1 |

---

### PSI-13 Postop Sepsis

| | |
|---|---|
| Matched donor encounters | 96 |
| Donors with diagnoses in OMNY | 87 (91%) |
| Donors without diagnosis data | 9 |
| Donors with a PSI-type ICD code in record | 11 (13% of those with dx) |

**Diagnosis category breakdown** (unique encounters per chapter):

| ICD-10 Chapter | Donor Encounters |
|---|---|
| Symptoms, Signs & Abnormal Findings | 56 |
| Circulatory System | 51 |
| Factors Influencing Health Status (Z-codes) | 44 |
| Endocrine, Nutritional & Metabolic | 41 |
| Genitourinary System | 26 |
| Nervous System | 23 |
| Respiratory System | 23 |
| Neoplasms / Blood & Immune | 21 |
| Digestive System | 20 |
| Mental & Behavioral Disorders | 17 |
| Musculoskeletal & Connective Tissue | 15 |
| Injury, Poisoning & External Causes | 15 |
| External Causes of Morbidity | 14 |
| Infectious & Parasitic Diseases | 14 |
| Skin & Subcutaneous Tissue | 5 |
| Neoplasms | 5 |
| Eye / Ear | 4 |
| Other | 3 |
| Congenital Malformations | 1 |

**Top 15 principal diagnoses** (by ICD-10 code):

| ICD-10 Code | Description | Chapter | Encounters |
|---|---|---|---|
| `R41.82` | ALTERED MENTAL STATUS, UNSPECIFIED ALTERED MENTAL STATUS TYPE | Symptoms, Signs & Abnormal Findings | 4 |
| `I50.9` | ACUTE ON CHRONIC CONGESTIVE HEART FAILURE, UNSPECIFIED HEART FAILURE T | Circulatory System | 2 |
| `W19.XXXA` | FALL, INITIAL ENCOUNTER | External Causes of Morbidity | 2 |
| `R29.90` | STROKE-LIKE SYMPTOMS | Symptoms, Signs & Abnormal Findings | 2 |
| `A41.9` | SEPTIC SHOCK (HCC) ⚠️ PSI | Infectious & Parasitic Diseases | 2 |
| `R65.21` | SEPTIC SHOCK (HCC) ⚠️ PSI | Symptoms, Signs & Abnormal Findings | 2 |
| `I20.0` | UNSTABLE ANGINA (HCC) | Circulatory System | 1 |
| `I26.99` | ACUTE PULMONARY EMBOLISM WITHOUT ACUTE COR PULMONALE, UNSPECIFIED PULM | Circulatory System | 1 |
| `I21.4` | NSTEMI (NON-ST ELEVATED MYOCARDIAL INFARCTION) (HCC) | Circulatory System | 1 |
| `E87.6` | HYPOKALEMIA | Endocrine, Nutritional & Metabolic | 1 |
| `I47.1` | PSVT (PAROXYSMAL SUPRAVENTRICULAR TACHYCARDIA) (HCC) | Circulatory System | 1 |
| `I47.20` | SUSTAINED VENTRICULAR TACHYCARDIA | Circulatory System | 1 |
| `I60.9` | SUBARACHNOID HEMORRHAGE (HCC) | Circulatory System | 1 |
| `I63.9` | CEREBROVASCULAR ACCIDENT (CVA), UNSPECIFIED MECHANISM (HCC) | Circulatory System | 1 |
| `I65.22` | LEFT-SIDED EXTRACRANIAL CAROTID ARTERY STENOSIS | Circulatory System | 1 |

> **PSI flag detail:** 11 donor encounter(s) carry an ICD-10 code
> matching the PSI-13 Postop Sepsis PSI criterion. Top codes: `A41.9` (n=8), `R65.21` (n=3), `R65.20` (n=2), `A40.3` (n=1), `A41.51` (n=1)
> This may reflect events occurring *after* the landmark window t\*, not violations of
> the event-free selection criterion (which only applies up to t\*).

---

### PSI-14 Wound Dehiscence

| | |
|---|---|
| Matched donor encounters | 153 |
| Donors with diagnoses in OMNY | 140 (92%) |
| Donors without diagnosis data | 13 |
| Donors with a PSI-type ICD code in record | 0 (0% of those with dx) |

**Diagnosis category breakdown** (unique encounters per chapter):

| ICD-10 Chapter | Donor Encounters |
|---|---|
| Factors Influencing Health Status (Z-codes) | 84 |
| Circulatory System | 81 |
| Symptoms, Signs & Abnormal Findings | 78 |
| Endocrine, Nutritional & Metabolic | 74 |
| Respiratory System | 54 |
| Genitourinary System | 54 |
| Digestive System | 47 |
| Mental & Behavioral Disorders | 45 |
| Nervous System | 41 |
| Neoplasms / Blood & Immune | 37 |
| Musculoskeletal & Connective Tissue | 37 |
| Infectious & Parasitic Diseases | 17 |
| Injury, Poisoning & External Causes | 14 |
| External Causes of Morbidity | 10 |
| Skin & Subcutaneous Tissue | 8 |
| Eye / Ear | 5 |
| Other | 5 |
| Neoplasms | 3 |
| Congenital Malformations | 2 |
| Pregnancy, Childbirth & Puerperium | 1 |

**Top 15 principal diagnoses** (by ICD-10 code):

| ICD-10 Code | Description | Chapter | Encounters |
|---|---|---|---|
| `J18.9` | PNEUMONIA OF RIGHT LOWER LOBE DUE TO INFECTIOUS ORGANISM | Respiratory System | 2 |
| `K92.2` | UPPER GI BLEED | Digestive System | 2 |
| `R41.82` | ALTERED MENTAL STATUS, UNSPECIFIED ALTERED MENTAL STATUS TYPE | Symptoms, Signs & Abnormal Findings | 2 |
| `B02.23` | SHINGLES (HERPES ZOSTER) POLYNEUROPATHY | Infectious & Parasitic Diseases | 1 |
| `E87.5` | HYPERKALEMIA | Endocrine, Nutritional & Metabolic | 1 |
| `F25.9` | SCHIZOAFFECTIVE DISORDER, UNSPECIFIED TYPE (HCC) | Mental & Behavioral Disorders | 1 |
| `H91.90` | HARD OF HEARING | Eye / Ear | 1 |
| `I10` | UNCONTROLLED HYPERTENSION | Circulatory System | 1 |
| `I21.3` | ST ELEVATION MYOCARDIAL INFARCTION (STEMI), UNSPECIFIED ARTERY (HCC) | Circulatory System | 1 |
| `I21.3` | STEMI (ST ELEVATION MYOCARDIAL INFARCTION) (HCC) | Circulatory System | 1 |
| `D69.3` | IDIOPATHIC THROMBOCYTOPENIC PURPURA (CMS/HCC) | Neoplasms / Blood & Immune | 1 |
| `D66` | HEMOPHILIA (MULTI) | Neoplasms / Blood & Immune | 1 |
| `I44.2` | COMPLETE HEART BLOCK    (CMD) | Circulatory System | 1 |
| `I46.9` | CARDIAC ARREST (HCC) | Circulatory System | 1 |
| `I48.91` | ATRIAL FIBRILLATION (MULTI) | Circulatory System | 1 |

---

### PSI-15 Accidental Puncture

| | |
|---|---|
| Matched donor encounters | 647 |
| Donors with diagnoses in OMNY | 640 (99%) |
| Donors without diagnosis data | 7 |
| Donors with a PSI-type ICD code in record | 1 (0% of those with dx) |

**Diagnosis category breakdown** (unique encounters per chapter):

| ICD-10 Chapter | Donor Encounters |
|---|---|
| Factors Influencing Health Status (Z-codes) | 555 |
| Endocrine, Nutritional & Metabolic | 427 |
| Circulatory System | 419 |
| Mental & Behavioral Disorders | 327 |
| Symptoms, Signs & Abnormal Findings | 271 |
| Genitourinary System | 249 |
| Digestive System | 241 |
| Nervous System | 240 |
| Respiratory System | 231 |
| Neoplasms / Blood & Immune | 222 |
| Musculoskeletal & Connective Tissue | 180 |
| Infectious & Parasitic Diseases | 142 |
| Injury, Poisoning & External Causes | 118 |
| External Causes of Morbidity | 102 |
| Skin & Subcutaneous Tissue | 81 |
| Eye / Ear | 45 |
| Pregnancy, Childbirth & Puerperium | 29 |
| Neoplasms | 28 |
| Other | 26 |
| Congenital Malformations | 5 |

**Top 15 principal diagnoses** (by ICD-10 code):

| ICD-10 Code | Description | Chapter | Encounters |
|---|---|---|---|
| `Z3A.39` | 39 WEEKS GESTATION OF PREGNANCY | Factors Influencing Health Status (Z-codes) | 11 |
| `Z3A.38` | 38 WEEKS GESTATION OF PREGNANCY | Factors Influencing Health Status (Z-codes) | 8 |
| `Z3A.40` | 40 WEEKS GESTATION OF PREGNANCY | Factors Influencing Health Status (Z-codes) | 7 |
| `Z3A.37` | 37 WEEKS GESTATION OF PREGNANCY | Factors Influencing Health Status (Z-codes) | 3 |
| `Z3A.36` | 36 WEEKS GESTATION OF PREGNANCY | Factors Influencing Health Status (Z-codes) | 2 |
| `Z98.891` | STATUS POST PRIMARY LOW TRANSVERSE CESAREAN SECTION | Factors Influencing Health Status (Z-codes) | 2 |
| `O11.9` | CHRONIC HYPERTENSION WITH SUPERIMPOSED PREECLAMPSIA | Pregnancy, Childbirth & Puerperium | 1 |
| `O14.13` | PREECLAMPSIA, SEVERE, THIRD TRIMESTER | Pregnancy, Childbirth & Puerperium | 1 |
| `E10.10` | DIABETIC KETOACIDOSIS WITHOUT COMA ASSOCIATED WITH TYPE 1 DIABETES MEL | Endocrine, Nutritional & Metabolic | 1 |
| `J10.1` | INFLUENZA A | Respiratory System | 1 |
| `O42.919` | PRETERM PREMATURE RUPTURE OF MEMBRANES (PPROM) WITH UNKNOWN ONSET OF L | Pregnancy, Childbirth & Puerperium | 1 |
| `O34.219` | HISTORY OF CESAREAN DELIVERY, ANTEPARTUM | Pregnancy, Childbirth & Puerperium | 1 |
| `O34.211` | MATERNAL CARE DUE TO LOW TRANSVERSE UTERINE SCAR FROM PREVIOUS CESAREA | Pregnancy, Childbirth & Puerperium | 1 |
| `O28.8` | NST (NON-STRESS TEST) NONREACTIVE | Pregnancy, Childbirth & Puerperium | 1 |
| `O26.00` | EXCESSIVE WEIGHT GAIN AFFECTING PREGNANCY | Pregnancy, Childbirth & Puerperium | 1 |

> **PSI flag detail:** 1 donor encounter(s) carry an ICD-10 code
> matching the PSI-15 Accidental Puncture PSI criterion. Top codes: `I97.52` (n=1)
> This may reflect events occurring *after* the landmark window t\*, not violations of
> the event-free selection criterion (which only applies up to t\*).

---

### PSI-17 Birth Trauma

| | |
|---|---|
| Matched donor encounters | 105 |
| Donors with diagnoses in OMNY | 89 (85%) |
| Donors without diagnosis data | 16 |
| Donors with a PSI-type ICD code in record | 0 (0% of those with dx) |

**Diagnosis category breakdown** (unique encounters per chapter):

| ICD-10 Chapter | Donor Encounters |
|---|---|
| Factors Influencing Health Status (Z-codes) | 63 |
| Symptoms, Signs & Abnormal Findings | 38 |
| Endocrine, Nutritional & Metabolic | 29 |
| Nervous System | 27 |
| Circulatory System | 26 |
| Mental & Behavioral Disorders | 25 |
| Respiratory System | 23 |
| Digestive System | 22 |
| Neoplasms / Blood & Immune | 18 |
| Genitourinary System | 17 |
| Musculoskeletal & Connective Tissue | 15 |
| Injury, Poisoning & External Causes | 13 |
| Skin & Subcutaneous Tissue | 13 |
| Infectious & Parasitic Diseases | 13 |
| Congenital Malformations | 11 |
| Eye / Ear | 10 |
| External Causes of Morbidity | 6 |
| Neoplasms | 1 |
| Other | 1 |

**Top 15 principal diagnoses** (by ICD-10 code):

| ICD-10 Code | Description | Chapter | Encounters |
|---|---|---|---|
| `Z11.59` | SPECIAL SCREENING EXAMINATION FOR VIRAL DISEASE | Factors Influencing Health Status (Z-codes) | 2 |
| `R56.9` | SEIZURE    (CMD) | Symptoms, Signs & Abnormal Findings | 2 |
| `C31.0` | MAXILLARY SINUS CANCER (H) | Neoplasms | 1 |
| `D75.829` | HIT (HEPARIN-INDUCED THROMBOCYTOPENIA) | Neoplasms / Blood & Immune | 1 |
| `D50.8` | OTHER IRON DEFICIENCY ANEMIA | Neoplasms / Blood & Immune | 1 |
| `E87.6` | HYPOKALEMIA | Endocrine, Nutritional & Metabolic | 1 |
| `F02.818` | LEWY BODY DEMENTIA WITH BEHAVIORAL DISTURBANCE (CMD) | Mental & Behavioral Disorders | 1 |
| `F31.9` | BIPOLAR 1 DISORDER, DEPRESSED (HCC) | Mental & Behavioral Disorders | 1 |
| `F33.9` | MAJOR DEPRESSIVE DISORDER, RECURRENT, UNSPECIFIED | Mental & Behavioral Disorders | 1 |
| `F20.9` | SCHIZOPHRENIA, UNSPECIFIED | Mental & Behavioral Disorders | 1 |
| `F22` | PARANOIA (HCC) | Mental & Behavioral Disorders | 1 |
| `G93.40` | ACUTE ENCEPHALOPATHY | Nervous System | 1 |
| `H35.123` | ROP (RETINOPATHY OF PREMATURITY), STAGE 1, BILATERAL | Eye / Ear | 1 |
| `I10` | HYPERTENSION | Circulatory System | 1 |
| `I10` | HYPERTENSION, UNSPECIFIED TYPE | Circulatory System | 1 |

---

### PSI-18 OB Trauma (instrumental)

| | |
|---|---|
| Matched donor encounters | 273 |
| Donors with diagnoses in OMNY | 265 (97%) |
| Donors without diagnosis data | 8 |
| Donors with a PSI-type ICD code in record | 0 (0% of those with dx) |

**Diagnosis category breakdown** (unique encounters per chapter):

| ICD-10 Chapter | Donor Encounters |
|---|---|
| Factors Influencing Health Status (Z-codes) | 229 |
| Pregnancy, Childbirth & Puerperium | 77 |
| Mental & Behavioral Disorders | 54 |
| Endocrine, Nutritional & Metabolic | 52 |
| Symptoms, Signs & Abnormal Findings | 43 |
| Neoplasms / Blood & Immune | 37 |
| Digestive System | 36 |
| Genitourinary System | 30 |
| Respiratory System | 25 |
| Nervous System | 22 |
| Injury, Poisoning & External Causes | 19 |
| Circulatory System | 19 |
| External Causes of Morbidity | 17 |
| Infectious & Parasitic Diseases | 14 |
| Musculoskeletal & Connective Tissue | 8 |
| Skin & Subcutaneous Tissue | 7 |
| Other | 5 |
| Congenital Malformations | 1 |

**Top 15 principal diagnoses** (by ICD-10 code):

| ICD-10 Code | Description | Chapter | Encounters |
|---|---|---|---|
| `Z3A.39` | 39 WEEKS GESTATION OF PREGNANCY | Factors Influencing Health Status (Z-codes) | 15 |
| `Z3A.40` | 40 WEEKS GESTATION OF PREGNANCY | Factors Influencing Health Status (Z-codes) | 12 |
| `Z3A.38` | 38 WEEKS GESTATION OF PREGNANCY | Factors Influencing Health Status (Z-codes) | 11 |
| `Z3A.37` | 37 WEEKS GESTATION OF PREGNANCY | Factors Influencing Health Status (Z-codes) | 4 |
| `Z3A.36` | 36 WEEKS GESTATION OF PREGNANCY | Factors Influencing Health Status (Z-codes) | 2 |
| `Z98.891` | STATUS POST PRIMARY LOW TRANSVERSE CESAREAN SECTION | Factors Influencing Health Status (Z-codes) | 2 |
| `F32.A` | DEPRESSION, UNSPECIFIED DEPRESSION TYPE | Mental & Behavioral Disorders | 1 |
| `E10.10` | DIABETIC KETOACIDOSIS WITHOUT COMA ASSOCIATED WITH TYPE 1 DIABETES MEL | Endocrine, Nutritional & Metabolic | 1 |
| `K57.80` | PERFORATED DIVERTICULUM | Digestive System | 1 |
| `J10.1` | INFLUENZA A | Respiratory System | 1 |
| `N30.00` | ACUTE CYSTITIS WITHOUT HEMATURIA | Genitourinary System | 1 |
| `O11.9` | CHRONIC HYPERTENSION WITH SUPERIMPOSED PREECLAMPSIA | Pregnancy, Childbirth & Puerperium | 1 |
| `O34.219` | HISTORY OF CESAREAN DELIVERY, ANTEPARTUM | Pregnancy, Childbirth & Puerperium | 1 |
| `O34.219` | VBAC (VAGINAL BIRTH AFTER CESAREAN) | Pregnancy, Childbirth & Puerperium | 1 |
| `O14.13` | PREECLAMPSIA, SEVERE, THIRD TRIMESTER | Pregnancy, Childbirth & Puerperium | 1 |

---

### PSI-19 OB Trauma (no instrument)

| | |
|---|---|
| Matched donor encounters | 200 |
| Donors with diagnoses in OMNY | 175 (88%) |
| Donors without diagnosis data | 25 |
| Donors with a PSI-type ICD code in record | 0 (0% of those with dx) |

**Diagnosis category breakdown** (unique encounters per chapter):

| ICD-10 Chapter | Donor Encounters |
|---|---|
| Factors Influencing Health Status (Z-codes) | 152 |
| Pregnancy, Childbirth & Puerperium | 64 |
| Mental & Behavioral Disorders | 33 |
| Endocrine, Nutritional & Metabolic | 28 |
| Neoplasms / Blood & Immune | 19 |
| Genitourinary System | 19 |
| Symptoms, Signs & Abnormal Findings | 18 |
| Digestive System | 16 |
| Circulatory System | 12 |
| Injury, Poisoning & External Causes | 11 |
| Respiratory System | 11 |
| Nervous System | 10 |
| External Causes of Morbidity | 10 |
| Infectious & Parasitic Diseases | 8 |
| Musculoskeletal & Connective Tissue | 4 |
| Skin & Subcutaneous Tissue | 4 |
| Other | 2 |
| Neoplasms | 1 |

**Top 15 principal diagnoses** (by ICD-10 code):

| ICD-10 Code | Description | Chapter | Encounters |
|---|---|---|---|
| `Z34.90` | ENCOUNTER FOR INDUCTION OF LABOR | Factors Influencing Health Status (Z-codes) | 3 |
| `Z34.90` | ENCOUNTER FOR ELECTIVE INDUCTION OF LABOR | Factors Influencing Health Status (Z-codes) | 3 |
| `B95.1` | GROUP BETA STREP POSITIVE | Infectious & Parasitic Diseases | 1 |
| `B96.5` | PSEUDOMONAS URINARY TRACT INFECTION | Infectious & Parasitic Diseases | 1 |
| `L05.01` | PILONIDAL CYST WITH ABSCESS | Skin & Subcutaneous Tissue | 1 |
| `N39.0` | PSEUDOMONAS URINARY TRACT INFECTION | Genitourinary System | 1 |
| `N70.92` | OVARIAN ABSCESS | Genitourinary System | 1 |
| `O09.213` | SUPERVISION OF PREGNANCY WITH HISTORY OF PRE-TERM LABOR IN THIRD TRIME | Pregnancy, Childbirth & Puerperium | 1 |
| `O09.523` | MULTIGRAVIDA OF ADVANCED MATERNAL AGE IN THIRD TRIMESTER | Pregnancy, Childbirth & Puerperium | 1 |
| `O13.9` | GESTATIONAL HYPERTENSION | Pregnancy, Childbirth & Puerperium | 1 |
| `D50.9` | IRON DEFICIENCY ANEMIA, UNSPECIFIED IRON DEFICIENCY ANEMIA TYPE | Neoplasms / Blood & Immune | 1 |
| `J90` | PLEURAL EFFUSION, LEFT | Respiratory System | 1 |
| `O34.219` | VAGINAL DELIVERY FOLLOWING PREVIOUS CESAREAN SECTION, DELIVERED | Pregnancy, Childbirth & Puerperium | 1 |
| `O33.4XX0` | CEPHALOPELVIC DISPROPORTION DUE TO MIXED MATERNAL AND FETAL FACTORS, S | Pregnancy, Childbirth & Puerperium | 1 |
| `O46.93` | VAGINAL BLEEDING IN PREGNANCY, THIRD TRIMESTER | Pregnancy, Childbirth & Puerperium | 1 |

---

## Cross-type diagnostic overlap

For each PSI type, the most common ICD-10 chapter among counterfactual donors:

| PSI Type | Donors | Top Chapter | Count | 2nd Chapter | Count | PSI-flagged donors |
|---|---|---|---|---|---|---|
| PSI-03 Pressure Ulcer | 150 | Factors Influencing Health Status (Z-cod | 134 | Circulatory System | 127 | 5 |
| PSI-04 Failure to Rescue | 99 | Symptoms, Signs & Abnormal Findings | 48 | Circulatory System | 32 | 16 |
| PSI-05 Retained Item | 402 | Factors Influencing Health Status (Z-cod | 144 | Symptoms, Signs & Abnormal Findings | 133 | 0 |
| PSI-06 Iatrogenic Pneumothorax | 223 | Symptoms, Signs & Abnormal Findings | 106 | Circulatory System | 84 | 0 |
| PSI-07 CLABSI | 159 | Circulatory System | 120 | Factors Influencing Health Status (Z-cod | 113 | 0 |
| PSI-08 Fall/Fracture | 73 | Circulatory System | 55 | Factors Influencing Health Status (Z-cod | 47 | 3 |
| PSI-09 Postop Hemorrhage | 419 | Factors Influencing Health Status (Z-cod | 191 | Circulatory System | 172 | 0 |
| PSI-10 Postop AKI/Dialysis | 62 | Factors Influencing Health Status (Z-cod | 50 | Endocrine, Nutritional & Metabolic | 41 | 11 |
| PSI-11 Postop Resp Failure | 195 | Symptoms, Signs & Abnormal Findings | 112 | Circulatory System | 110 | 24 |
| PSI-12 Periop PE/DVT | 19 | Circulatory System | 11 | Symptoms, Signs & Abnormal Findings | 9 | 0 |
| PSI-13 Postop Sepsis | 96 | Symptoms, Signs & Abnormal Findings | 56 | Circulatory System | 51 | 11 |
| PSI-14 Wound Dehiscence | 153 | Factors Influencing Health Status (Z-cod | 84 | Circulatory System | 81 | 0 |
| PSI-15 Accidental Puncture | 647 | Factors Influencing Health Status (Z-cod | 555 | Endocrine, Nutritional & Metabolic | 427 | 1 |
| PSI-17 Birth Trauma | 105 | Factors Influencing Health Status (Z-cod | 63 | Symptoms, Signs & Abnormal Findings | 38 | 0 |
| PSI-18 OB Trauma (instrumental) | 273 | Factors Influencing Health Status (Z-cod | 229 | Pregnancy, Childbirth & Puerperium | 77 | 0 |
| PSI-19 OB Trauma (no instrument) | 200 | Factors Influencing Health Status (Z-cod | 152 | Pregnancy, Childbirth & Puerperium | 64 | 0 |

---

## Interpretation notes

1. **Why are some PSI-type codes present in controls?**
   The event-free criterion only applies up to the landmark time t\* = E_i − 6 (24 hours
   before the case's PSI event). Donors may still develop an adverse outcome *after* that
   window. Their diagnosis record in OMNY reflects the full hospitalization, so post-window
   PSI events will appear in their diagnosis list. This is by design and does not invalidate
   the counterfactual selection.

2. **OB types (PSI-17/18/19) and the Pregnancy chapter**
   Counterfactual donors for obstetric PSI types are dominated by O-chapter codes
   (Pregnancy, Childbirth & Puerperium). This confirms the matching is finding
   comparable obstetric patients — not a mix of random inpatient admissions.

3. **Surgical PSI types and Circulatory/Digestive chapters**
   PSI types like PSI-09 (hemorrhage), PSI-11 (resp failure), PSI-13 (sepsis) should
   show donors dominated by surgical or medical admission diagnoses (I-, K-, J-chapter).
   Deviation from this pattern would indicate the CEM matching is pulling
   non-comparable patients.

4. **Coverage gaps**
   Donors without diagnosis data in OMNY are excluded from these tables but were used
   in propensity score matching. Their demographics and clinical history (labs, vitals)
   are still in the matched_sets.parquet. The diagnostic gap is a data-availability
   artefact of the OMNY DIAGNOSES table coverage, not a matching deficiency.
