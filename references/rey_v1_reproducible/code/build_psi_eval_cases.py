"""
Build eval_cases_psi.csv — a runner-ready case list from Allison's PSI dataset.

Sources (all in /psi/outputs/aggregated):
  - psi_inpatient_cases_downsampled.csv  (163 rows, the case list)
  - tables/encounters.csv                (LOS, AGE, dept)
  - tables/diagnoses.csv                 (PRIMARY_DX_CODE)

Output (in code/):
  - eval_cases_psi.csv with all columns run_eval_parallel.py expects, plus
    the PSI metadata (PSI_CODE, LABEL, CONFIDENCE) preserved.

Run:
  python3 build_psi_eval_cases.py
"""

from __future__ import annotations

from pathlib import Path
import pandas as pd


BASE = Path("/Users/mturk/Projects/agentic-task-discovery/project-bayes")
PSI_DIR = BASE / "psi" / "outputs" / "aggregated"
OUT = BASE / "code" / "eval_cases_psi.csv"


def _bucket_los(los: float) -> str:
    if pd.isna(los):
        return "unknown"
    if los < 3:
        return "short"  # technically <3 should be excluded but bucket here anyway
    if los <= 4:
        return "short"
    if los <= 6:
        return "medium"
    return "long"


def main():
    cases = pd.read_csv(PSI_DIR / "psi_inpatient_cases_downsampled.csv")
    encs = pd.read_csv(PSI_DIR / "tables" / "encounters.csv")
    dx = pd.read_csv(PSI_DIR / "tables" / "diagnoses.csv")

    print(f"Loaded:")
    print(f"  cases (downsampled): {len(cases)} rows, {cases['ENCOUNTER_ID'].nunique()} distinct encounters")
    print(f"  encounters.csv:       {len(encs)} rows")
    print(f"  diagnoses.csv:        {len(dx)} rows")

    # Encounter-level LOS + age + OMNY_ID (needed by the renderer)
    enc_features = encs[[
        "OMNY_ID", "ENCOUNTER_ID", "EN_START_DATE", "EN_END_DATE", "EN_LOS",
        "AGE", "GENDER", "EN_DEPT", "EN_FACILITY"
    ]].drop_duplicates(subset=["ENCOUNTER_ID"])
    enc_features = enc_features.rename(columns={"EN_LOS": "LOS_DAYS_RAW", "AGE": "AGE_INT",
                                                  "EN_FACILITY": "INSTITUTION_NAME"})

    # Primary diagnosis
    primary = dx[dx["DX_PRIMARY"].astype(str).str.upper().isin(["Y", "YES", "1", "TRUE"])].copy()
    primary = primary.sort_values(["ENCOUNTER_ID", "DX_LINE"]).drop_duplicates(
        subset=["ENCOUNTER_ID"], keep="first"
    )
    primary = primary[["ENCOUNTER_ID", "DX_CODE", "DX_HCS_DESC"]].rename(
        columns={"DX_CODE": "PRIMARY_DX_CODE", "DX_HCS_DESC": "PRIMARY_DX_DESC"}
    )

    # Fallback: when no primary, take first diagnosis by line number
    no_primary_encs = set(enc_features["ENCOUNTER_ID"]) - set(primary["ENCOUNTER_ID"])
    if no_primary_encs:
        first_dx = dx[dx["ENCOUNTER_ID"].isin(no_primary_encs)].sort_values(
            ["ENCOUNTER_ID", "DX_LINE"]
        ).drop_duplicates(subset=["ENCOUNTER_ID"], keep="first")
        first_dx = first_dx[["ENCOUNTER_ID", "DX_CODE", "DX_HCS_DESC"]].rename(
            columns={"DX_CODE": "PRIMARY_DX_CODE", "DX_HCS_DESC": "PRIMARY_DX_DESC"}
        )
        primary = pd.concat([primary, first_dx], ignore_index=True)

    # Join
    merged = cases.merge(enc_features, on="ENCOUNTER_ID", how="left")
    merged = merged.merge(primary, on="ENCOUNTER_ID", how="left")

    # Backfill LOS_BUCKET from raw LOS where missing
    merged["LOS_DAYS"] = merged["LOS_DAYS_RAW"].fillna(0).astype(int)
    los_unknown = merged["LOS_BUCKET"].isna()
    if los_unknown.any():
        merged.loc[los_unknown, "LOS_BUCKET"] = merged.loc[los_unknown, "LOS_DAYS"].apply(_bucket_los)

    # Synth PROTEGE_SCORE — Allison's classification used age + ICU days for COMPLEXITY_TIER.
    # We don't have the original Protege score column, so derive a proxy from
    # COMPLEXITY_TIER for the runner's column requirement.
    tier_to_score = {"easy": 5, "medium": 10, "hard": 17, "meta_hard": 20, "unknown": 0}
    merged["PROTEGE_SCORE"] = merged["COMPLEXITY_TIER"].fillna("unknown").map(tier_to_score).fillna(0).astype(int)

    # Stable column order
    ordered = [
        "OMNY_ID", "ENCOUNTER_ID",
        "PSI_CODE", "PSI_TITLE", "LABEL", "CONFIDENCE",
        "PRIMARY_DX_CODE", "PRIMARY_DX_DESC",
        "LOS_BUCKET", "COMPLEXITY_TIER",
        "LOS_DAYS", "AGE_INT", "GENDER", "EN_DEPT", "INSTITUTION_NAME",
        "PROTEGE_SCORE",
        "EN_START_DATE", "EN_END_DATE",
        "NOTE_ID", "MATCHED_DX_CODES", "EVIDENCE_SPAN", "RATIONALE",
        "HOSPITAL_ACQUIRED_NOT_POA", "IS_EXCLUSION", "PSI_EVENT_PRESENT",
    ]
    for col in ordered:
        if col not in merged.columns:
            merged[col] = ""
    merged = merged[ordered]

    # Drop rows without OMNY_ID — they're not renderable (no encounter data pulled)
    n_before = len(merged)
    merged = merged[merged["OMNY_ID"].notna()].copy()
    n_dropped = n_before - len(merged)
    if n_dropped:
        print()
        print(f"⚠ Dropped {n_dropped} rows missing OMNY_ID (not in encounters.csv — not renderable)")

    print()
    print(f"Output: {OUT}")
    merged.to_csv(OUT, index=False)
    print(f"  rows: {len(merged)}")
    print()
    print(f"PSI_CODE × LABEL distribution:")
    print(merged.groupby(["PSI_CODE", "LABEL"]).size().unstack(fill_value=0).to_string())
    print()
    print(f"LOS_BUCKET × COMPLEXITY_TIER distribution:")
    print(merged.groupby(["LOS_BUCKET", "COMPLEXITY_TIER"]).size().unstack(fill_value=0).to_string())
    print()
    n_missing_dx = merged["PRIMARY_DX_CODE"].isna().sum()
    n_missing_los = (merged["LOS_DAYS"] == 0).sum()
    print(f"Coverage:")
    print(f"  rows with primary Dx:  {len(merged) - n_missing_dx}/{len(merged)}")
    print(f"  rows with LOS_DAYS>0:  {len(merged) - n_missing_los}/{len(merged)}")


if __name__ == "__main__":
    main()
