"""
psi/add_classification_columns.py

Adds LOS_BUCKET, COMPLEXITY_TIER, and LOS_SOURCE to psi/outputs/psi_balanced_cases_v1.csv.

Uses the same formulas as omny/feasibility/eval/meta_complexity_comparison.py
and the same classification logic as omny/feasibility/eval/select_eval_cases.py.

PROTEGE_SCORE (max ~20 pts):
  HAS_ANY_ICU * 3  + HAS_VASOPRESSOR * 3  + HAS_CRITICAL_DX * 3  + HAS_VENTILATOR * 3
  + LOS bonus (>=21 days → 3, >=14 days → 2)
  + DX count bonus (>=10 → 2, >=15 → 2)
  + HAS_UNSPECIFIED_DX
  + provider bonus (>=5 → 2, >=3 → 1)
  + HAS_IMAGING
  + N_LAB_RESULTS >= 20 → 1
  + N_ABNORMAL_LABS >= 10 → 1
  + N_VITAL_MEASUREMENTS >= 20 → 1
  + N_DISTINCT_MEDS >= 5 → 1

META_BROAD_2D: age 20-60 AND any ICU AND >= 2 distinct ICU calendar days.

COMPLEXITY_TIER terciles computed from this PSI pool (same approach as
select_eval_cases.py, which computes terciles from its own pool).

LOS_BUCKET:
  short  — 3-4 days (LOS in [3, 4])
  medium — 5-6 days (LOS in [5, 6])
  long   — 7+ days

LOS_SOURCE:
  en_los      — LOS from CUSTOM.ENCOUNTERS.EN_LOS (primary, same as OMNY eval)
  note_dates  — fallback: DATEDIFF(min, max) across all notes for the encounter
                (noisier; late addenda can inflate; same caveat as qa_los_validation.py)
  none        — EN_LOS null and no notes found

ICU is detected from three sources (OR logic, same as meta_complexity_comparison.py):
  1. PRESCRIPTION_ADMINISTRATIONS.AD_DEPT — dept keyword match
  2. CLAIMS_PROCEDURE.REVENUE_CODE — UB-04 codes 0200-0219
  3. PROCEDURES.PX_CODE — CPT 99291/99292 critical care billing

Run from repo root:
    python3 psi/add_classification_columns.py
"""

from pathlib import Path

import pandas as pd
import snowflake.connector

PSI_CSV = Path("psi/outputs/aggregated/psi_inpatient_cases.csv")

SNOWFLAKE_CONFIG = {
    "account": "APHHHWO-PROTEGE_PARTNER",
    "user": "ALLISON.FOX@WITHPROTEGE.AI",
    "authenticator": "externalbrowser",
    "role": "READ_ONLY",
    "warehouse": "READ_ONLY_2XL_WH",
}


def build_scores_query(encounter_ids: list[str]) -> str:
    enc_list = ", ".join(f"'{e}'" for e in encounter_ids)
    return f"""
WITH
t_enc AS (
    SELECT
        e.OMNY_ID,
        e.ENCOUNTER_ID,
        TRY_CAST(e.EN_LOS AS FLOAT)::INTEGER AS LOS_DAYS,
        TRY_CAST(e.AGE AS INTEGER)            AS AGE_INT,
        e.EN_START_DATE,
        e.EN_PCP_PROV_ID, e.EN_PR_PROV_ID, e.EN_ADM_PROV_ID,
        e.EN_ATT_PROV_ID, e.EN_DC_PROV_ID
    FROM OMNY_REPL_ID.CUSTOM.ENCOUNTERS e
    WHERE e.ENCOUNTER_ID IN ({enc_list})
      AND e.ENCOUNTER_ID IS NOT NULL
),
prov_all AS (
    SELECT OMNY_ID, ENCOUNTER_ID, EN_PCP_PROV_ID AS PROV_ID FROM t_enc WHERE EN_PCP_PROV_ID IS NOT NULL
    UNION ALL SELECT OMNY_ID, ENCOUNTER_ID, EN_PR_PROV_ID  FROM t_enc WHERE EN_PR_PROV_ID  IS NOT NULL
    UNION ALL SELECT OMNY_ID, ENCOUNTER_ID, EN_ADM_PROV_ID FROM t_enc WHERE EN_ADM_PROV_ID IS NOT NULL
    UNION ALL SELECT OMNY_ID, ENCOUNTER_ID, EN_ATT_PROV_ID FROM t_enc WHERE EN_ATT_PROV_ID IS NOT NULL
    UNION ALL SELECT OMNY_ID, ENCOUNTER_ID, EN_DC_PROV_ID  FROM t_enc WHERE EN_DC_PROV_ID  IS NOT NULL
    UNION ALL
    SELECT p.OMNY_ID, p.ENCOUNTER_ID, p.PX_PERF_PROV_ID
    FROM OMNY_REPL_ID.CUSTOM.PROCEDURES p
    INNER JOIN t_enc a ON p.OMNY_ID = a.OMNY_ID AND p.ENCOUNTER_ID = a.ENCOUNTER_ID
    WHERE p.PX_PERF_PROV_ID IS NOT NULL
    UNION ALL
    SELECT l.OMNY_ID, l.ENCOUNTER_ID, l.LB_PROV_ID
    FROM OMNY_REPL_ID.CUSTOM.LABS l
    INNER JOIN t_enc a ON l.OMNY_ID = a.OMNY_ID AND l.ENCOUNTER_ID = a.ENCOUNTER_ID
    WHERE l.LB_PROV_ID IS NOT NULL
    UNION ALL
    SELECT r.OMNY_ID, r.ENCOUNTER_ID, r.RX_PROV_ID
    FROM OMNY_REPL_ID.CUSTOM.PRESCRIPTION_ORDERS r
    INNER JOIN t_enc a ON r.OMNY_ID = a.OMNY_ID AND r.ENCOUNTER_ID = a.ENCOUNTER_ID
    WHERE r.RX_PROV_ID IS NOT NULL
),
t_providers AS (
    SELECT OMNY_ID, ENCOUNTER_ID, COUNT(DISTINCT PROV_ID) AS N_DISTINCT_PROVIDERS
    FROM prov_all GROUP BY OMNY_ID, ENCOUNTER_ID
),
t_labs AS (
    SELECT l.OMNY_ID, l.ENCOUNTER_ID,
        COUNT(*) AS N_LAB_RESULTS,
        SUM(IFF(l.LB_ABN_RESULT IS NOT NULL
                AND UPPER(l.LB_ABN_RESULT) NOT IN ('N', 'NORMAL', ''), 1, 0)) AS N_ABNORMAL_LABS
    FROM OMNY_REPL_ID.CUSTOM.LABS l
    INNER JOIN t_enc a ON l.OMNY_ID = a.OMNY_ID AND l.ENCOUNTER_ID = a.ENCOUNTER_ID
    GROUP BY l.OMNY_ID, l.ENCOUNTER_ID
),
t_vitals AS (
    SELECT v.OMNY_ID, v.ENCOUNTER_ID, COUNT(*) AS N_VITAL_MEASUREMENTS
    FROM OMNY_REPL_ID.CUSTOM.VITALS v
    INNER JOIN t_enc a ON v.OMNY_ID = a.OMNY_ID AND v.ENCOUNTER_ID = a.ENCOUNTER_ID
    GROUP BY v.OMNY_ID, v.ENCOUNTER_ID
),
t_procedures AS (
    SELECT p.OMNY_ID, p.ENCOUNTER_ID,
        MAX(IFF(
            (p.PX_CODE BETWEEN '70000' AND '79999')
            OR p.PX_TYPE    ILIKE '%RADIOLOGY%'           OR p.PX_TYPE    ILIKE '%IMAGING%'
            OR p.PX_HCS_DESC ILIKE '% CT %'               OR p.PX_HCS_DESC ILIKE '%MRI%'
            OR p.PX_HCS_DESC ILIKE '%X-RAY%'              OR p.PX_HCS_DESC ILIKE '%ULTRASOUND%'
            OR p.PX_LONG_DESC ILIKE '%computed tomography%'
            OR p.PX_LONG_DESC ILIKE '%magnetic resonance%',
            1, 0
        )) AS HAS_IMAGING,
        MAX(IFF(
            p.PX_CODE IN ('94002', '94003', '94004', '31500')
            OR p.PX_HCS_DESC ILIKE '%MECHANIC%VENTIL%'
            OR p.PX_HCS_DESC ILIKE '%INTUBAT%',
            1, 0
        )) AS HAS_VENTILATOR
    FROM OMNY_REPL_ID.CUSTOM.PROCEDURES p
    INNER JOIN t_enc a ON p.OMNY_ID = a.OMNY_ID AND p.ENCOUNTER_ID = a.ENCOUNTER_ID
    GROUP BY p.OMNY_ID, p.ENCOUNTER_ID
),
t_meds AS (
    SELECT r.OMNY_ID, r.ENCOUNTER_ID,
        COUNT(DISTINCT r.RX_GENERIC_NAME) AS N_DISTINCT_MEDS,
        MAX(IFF(
            r.RX_GENERIC_NAME ILIKE '%NOREPINEPHRINE%' OR r.RX_GENERIC_NAME ILIKE '%EPINEPHRINE%'
            OR r.RX_GENERIC_NAME ILIKE '%DOPAMINE%'    OR r.RX_GENERIC_NAME ILIKE '%DOBUTAMINE%'
            OR r.RX_GENERIC_NAME ILIKE '%VASOPRESSIN%' OR r.RX_GENERIC_NAME ILIKE '%PHENYLEPHRINE%',
            1, 0
        )) AS HAS_VASOPRESSOR
    FROM OMNY_REPL_ID.CUSTOM.PRESCRIPTION_ORDERS r
    INNER JOIN t_enc a ON r.OMNY_ID = a.OMNY_ID AND r.ENCOUNTER_ID = a.ENCOUNTER_ID
    GROUP BY r.OMNY_ID, r.ENCOUNTER_ID
),
t_diagnoses AS (
    SELECT d.OMNY_ID, d.ENCOUNTER_ID,
        COUNT(DISTINCT d.DX_CODE) AS N_DISTINCT_DX_CODES,
        MAX(IFF(
            d.DX_CODE LIKE 'A41%' OR d.DX_CODE LIKE 'R65%' OR d.DX_CODE LIKE 'R57%'
            OR d.DX_CODE LIKE 'J96%' OR d.DX_CODE LIKE 'J80%' OR d.DX_CODE LIKE 'N17%'
            OR d.DX_CODE LIKE 'K72%' OR d.DX_CODE LIKE 'I21%' OR d.DX_CODE LIKE 'I63%'
            OR d.DX_CODE LIKE 'G93%' OR d.DX_CODE LIKE 'D65%' OR d.DX_CODE LIKE 'C%',
            1, 0
        )) AS HAS_CRITICAL_DX,
        MAX(IFF(
            d.DX_HCS_DESC ILIKE '%UNSPECIFIED%'
            OR d.DX_HCS_DESC ILIKE '%NOT ELSEWHERE CLASSIFIED%'
            OR d.DX_HCS_DESC ILIKE '%UNCERTAIN%'
            OR d.DX_CODE LIKE '%.9',
            1, 0
        )) AS HAS_UNSPECIFIED_DX
    FROM OMNY_REPL_ID.CUSTOM.DIAGNOSES d
    INNER JOIN t_enc a ON d.OMNY_ID = a.OMNY_ID AND d.ENCOUNTER_ID = a.ENCOUNTER_ID
    GROUP BY d.OMNY_ID, d.ENCOUNTER_ID
),
-- Source 1: ICU from prescription administration dept labels
t_icu_admins AS (
    SELECT
        a.OMNY_ID,
        a.ENCOUNTER_ID,
        COUNT(DISTINCT a.AD_ADMIN_DATE) AS N_DISTINCT_ICU_DATES
    FROM OMNY_REPL_ID.CUSTOM.PRESCRIPTION_ADMINISTRATIONS a
    INNER JOIN t_enc ip ON a.OMNY_ID = ip.OMNY_ID AND a.ENCOUNTER_ID = ip.ENCOUNTER_ID
    WHERE a.AD_DEPT ILIKE '%ICU%'
       OR a.AD_DEPT ILIKE '%INTENSIVE CARE%'
       OR a.AD_DEPT ILIKE '%CCU%'
       OR a.AD_DEPT ILIKE '%CORONARY CARE%'
    GROUP BY a.OMNY_ID, a.ENCOUNTER_ID
),
-- Source 2: ICU from UB-04 revenue codes (0200-0219) in claims
t_icu_claims AS (
    SELECT
        ip.OMNY_ID,
        ip.ENCOUNTER_ID,
        COUNT(DISTINCT TRY_TO_DATE(cp.SERVICE_FROM)) AS N_DISTINCT_ICU_CLAIM_DATES
    FROM OMNY_REPL_ID.CUSTOM.CLAIMS_PROCEDURE cp
    INNER JOIN t_enc ip
        ON  cp.OMNY_ID = ip.OMNY_ID
        AND TRY_TO_DATE(cp.SERVICE_FROM) >= TRY_TO_DATE(ip.EN_START_DATE)
        AND TRY_TO_DATE(cp.SERVICE_FROM) < DATEADD('day',
                COALESCE(ip.LOS_DAYS, 30) + 2, TRY_TO_DATE(ip.EN_START_DATE))
    WHERE cp.REVENUE_CODE BETWEEN '0200' AND '0219'
      AND TRY_TO_DATE(cp.SERVICE_FROM) >= '2010-01-01'
    GROUP BY ip.OMNY_ID, ip.ENCOUNTER_ID
),
-- Source 3: ICU from CPT 99291/99292 critical care billing
t_icu_cpt AS (
    SELECT
        p.OMNY_ID,
        p.ENCOUNTER_ID,
        COUNT(DISTINCT TRY_TO_DATE(p.PX_SERVICE_DATE)) AS N_DISTINCT_ICU_CPT_DATES
    FROM OMNY_REPL_ID.CUSTOM.PROCEDURES p
    INNER JOIN t_enc ip ON p.OMNY_ID = ip.OMNY_ID AND p.ENCOUNTER_ID = ip.ENCOUNTER_ID
    WHERE p.PX_CODE IN ('99291', '99292')
    GROUP BY p.OMNY_ID, p.ENCOUNTER_ID
),
t_icu_combined AS (
    SELECT
        ip.OMNY_ID,
        ip.ENCOUNTER_ID,
        IFF(adm.OMNY_ID IS NOT NULL
            OR clm.OMNY_ID IS NOT NULL
            OR cpt.OMNY_ID IS NOT NULL, 1, 0)                  AS HAS_ANY_ICU,
        GREATEST(
            COALESCE(adm.N_DISTINCT_ICU_DATES, 0),
            COALESCE(clm.N_DISTINCT_ICU_CLAIM_DATES, 0),
            COALESCE(cpt.N_DISTINCT_ICU_CPT_DATES, 0)
        )                                                       AS N_ICU_DATES
    FROM t_enc ip
    LEFT JOIN t_icu_admins adm ON ip.OMNY_ID = adm.OMNY_ID AND ip.ENCOUNTER_ID = adm.ENCOUNTER_ID
    LEFT JOIN t_icu_claims  clm ON ip.OMNY_ID = clm.OMNY_ID AND ip.ENCOUNTER_ID = clm.ENCOUNTER_ID
    LEFT JOIN t_icu_cpt     cpt ON ip.OMNY_ID = cpt.OMNY_ID AND ip.ENCOUNTER_ID = cpt.ENCOUNTER_ID
),
-- Fallback LOS: note date span for encounters where EN_LOS is null
-- Same caveat as omny/feasibility/eval/qa_los_validation.py — late addenda inflate span.
t_note_span AS (
    SELECT
        ENCOUNTER_ID,
        DATEDIFF('day',
            MIN(NOTE_DATE::DATE),
            MAX(NOTE_DATE::DATE)
        ) AS NOTE_SPAN_DAYS
    FROM OMNY_PROTEGE.PUBLIC.OMNY_NOTES_CONCATENATED
    WHERE ENCOUNTER_ID IN ({enc_list})
      AND NOTE_DATE IS NOT NULL
    GROUP BY ENCOUNTER_ID
),
scored AS (
    SELECT
        a.ENCOUNTER_ID,
        -- Primary LOS from EN_LOS; fall back to note date span if null
        COALESCE(a.LOS_DAYS, ns.NOTE_SPAN_DAYS)                AS LOS_DAYS,
        CASE
            WHEN a.LOS_DAYS IS NOT NULL THEN 'en_los'
            WHEN ns.NOTE_SPAN_DAYS IS NOT NULL THEN 'note_dates'
            ELSE 'none'
        END                                                     AS LOS_SOURCE,
        a.AGE_INT,
        COALESCE(icu.HAS_ANY_ICU, 0) AS HAS_ANY_ICU,
        COALESCE(icu.N_ICU_DATES, 0) AS N_ICU_DATES,
        (
            COALESCE(icu.HAS_ANY_ICU, 0) * 3
            + COALESCE(md.HAS_VASOPRESSOR, 0) * 3
            + COALESCE(dx.HAS_CRITICAL_DX, 0) * 3
            + COALESCE(pr.HAS_VENTILATOR, 0) * 3
            + IFF(COALESCE(a.LOS_DAYS, ns.NOTE_SPAN_DAYS) >= 21, 3,
                  IFF(COALESCE(a.LOS_DAYS, ns.NOTE_SPAN_DAYS) >= 14, 2, 0))
            + IFF(COALESCE(dx.N_DISTINCT_DX_CODES, 0) >= 10, 2, 0)
            + IFF(COALESCE(dx.N_DISTINCT_DX_CODES, 0) >= 15, 2, 0)
            + COALESCE(dx.HAS_UNSPECIFIED_DX, 0)
            + IFF(COALESCE(pv.N_DISTINCT_PROVIDERS, 0) >= 5, 2,
                  IFF(COALESCE(pv.N_DISTINCT_PROVIDERS, 0) >= 3, 1, 0))
            + COALESCE(pr.HAS_IMAGING, 0)
            + IFF(COALESCE(lb.N_LAB_RESULTS, 0) >= 20, 1, 0)
            + IFF(COALESCE(lb.N_ABNORMAL_LABS, 0) >= 10, 1, 0)
            + IFF(COALESCE(vt.N_VITAL_MEASUREMENTS, 0) >= 20, 1, 0)
            + IFF(COALESCE(md.N_DISTINCT_MEDS, 0) >= 5, 1, 0)
        ) AS PROTEGE_SCORE,
        IFF(
            a.AGE_INT BETWEEN 20 AND 60
            AND COALESCE(icu.HAS_ANY_ICU, 0) = 1
            AND COALESCE(icu.N_ICU_DATES, 0) >= 2,
            1, 0
        ) AS META_BROAD_2D
    FROM t_enc a
    LEFT JOIN t_note_span    ns  ON a.ENCOUNTER_ID = ns.ENCOUNTER_ID
    LEFT JOIN t_icu_combined icu ON a.OMNY_ID = icu.OMNY_ID AND a.ENCOUNTER_ID = icu.ENCOUNTER_ID
    LEFT JOIN t_providers    pv  ON a.OMNY_ID = pv.OMNY_ID  AND a.ENCOUNTER_ID = pv.ENCOUNTER_ID
    LEFT JOIN t_labs         lb  ON a.OMNY_ID = lb.OMNY_ID  AND a.ENCOUNTER_ID = lb.ENCOUNTER_ID
    LEFT JOIN t_vitals       vt  ON a.OMNY_ID = vt.OMNY_ID  AND a.ENCOUNTER_ID = vt.ENCOUNTER_ID
    LEFT JOIN t_procedures   pr  ON a.OMNY_ID = pr.OMNY_ID  AND a.ENCOUNTER_ID = pr.ENCOUNTER_ID
    LEFT JOIN t_meds         md  ON a.OMNY_ID = md.OMNY_ID  AND a.ENCOUNTER_ID = md.ENCOUNTER_ID
    LEFT JOIN t_diagnoses    dx  ON a.OMNY_ID = dx.OMNY_ID  AND a.ENCOUNTER_ID = dx.ENCOUNTER_ID
)
SELECT ENCOUNTER_ID, LOS_DAYS, LOS_SOURCE, AGE_INT, PROTEGE_SCORE, META_BROAD_2D, HAS_ANY_ICU, N_ICU_DATES
FROM scored
"""


def los_bucket(los_days) -> str | None:
    if los_days is None or (hasattr(los_days, "__float__") and pd.isna(los_days)):
        return None
    d = int(los_days)
    if d >= 7:
        return "long"
    elif d >= 5:
        return "medium"
    elif d >= 3:
        return "short"
    else:
        return None  # LOS < 3 doesn't fit any bucket


def assign_complexity_tiers(scores: pd.DataFrame) -> pd.Series:
    meta_mask = scores["META_BROAD_2D"] == 1
    non_meta_scores = scores.loc[~meta_mask, "PROTEGE_SCORE"]

    if non_meta_scores.empty:
        q33 = q67 = 0.0
    else:
        q33 = non_meta_scores.quantile(1 / 3)
        q67 = non_meta_scores.quantile(2 / 3)

    print(f"  Non-meta score terciles: easy ≤{q33:.0f}  |  medium {q33:.0f}–{q67:.0f}  |  hard >{q67:.0f}")
    print(f"  Meta hard: {meta_mask.sum()}  |  Non-meta: {(~meta_mask).sum()}")

    tier = pd.Series("meta_hard", index=scores.index, dtype=str)
    tier[~meta_mask & (scores["PROTEGE_SCORE"] <= q33)] = "easy"
    tier[
        ~meta_mask
        & (scores["PROTEGE_SCORE"] > q33)
        & (scores["PROTEGE_SCORE"] <= q67)
    ] = "medium"
    tier[~meta_mask & (scores["PROTEGE_SCORE"] > q67)] = "hard"
    return tier


def main() -> None:
    df = pd.read_csv(PSI_CSV)
    encounter_ids = df["ENCOUNTER_ID"].dropna().unique().tolist()
    print(f"PSI file: {len(df)} rows, {len(encounter_ids)} unique encounters\n")

    print("Opening browser for SSO authentication...")
    conn = snowflake.connector.connect(**SNOWFLAKE_CONFIG)
    print("Connected.\n")

    try:
        print("Querying Snowflake for encounter scores ...")
        query = build_scores_query(encounter_ids)
        cur = conn.cursor()
        cur.execute(query)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()
        print("Snowflake connection closed.\n")

    scores = pd.DataFrame(rows, columns=cols)
    print(f"Encounters returned: {len(scores)}")

    missing = set(encounter_ids) - set(scores["ENCOUNTER_ID"].tolist())
    if missing:
        print(f"  Warning: {len(missing)} encounter(s) not found in Snowflake: {missing}")

    scores = scores.drop_duplicates(subset=["ENCOUNTER_ID"])

    scores["LOS_BUCKET"] = scores["LOS_DAYS"].apply(los_bucket)

    n_en_los = (scores["LOS_SOURCE"] == "en_los").sum()
    n_notes  = (scores["LOS_SOURCE"] == "note_dates").sum()
    n_none   = (scores["LOS_SOURCE"] == "none").sum()
    print(f"  LOS source: en_los={n_en_los}, note_dates={n_notes}, none={n_none}")

    print("\nAssigning complexity tiers ...")
    scores["COMPLEXITY_TIER"] = assign_complexity_tiers(scores)

    for col in ("LOS_BUCKET", "COMPLEXITY_TIER", "LOS_SOURCE"):
        if col in df.columns:
            df = df.drop(columns=[col])

    df = df.merge(
        scores[["ENCOUNTER_ID", "LOS_BUCKET", "COMPLEXITY_TIER", "LOS_SOURCE"]],
        on="ENCOUNTER_ID",
        how="left",
    )

    print("\n── LOS_BUCKET ──────────────────")
    print(df["LOS_BUCKET"].value_counts(dropna=False).to_string())
    print("\n── LOS_SOURCE ──────────────────")
    print(df["LOS_SOURCE"].value_counts(dropna=False).to_string())
    print("\n── COMPLEXITY_TIER ─────────────")
    print(df["COMPLEXITY_TIER"].value_counts(dropna=False).to_string())

    null_los = df["LOS_BUCKET"].isna().sum()
    null_tier = df["COMPLEXITY_TIER"].isna().sum()
    if null_los or null_tier:
        print(f"\n  Warning: {null_los} rows missing LOS_BUCKET, {null_tier} missing COMPLEXITY_TIER")

    df.to_csv(PSI_CSV, index=False)
    print(f"\nSaved → {PSI_CSV}  ({len(df)} rows)")


if __name__ == "__main__":
    main()
