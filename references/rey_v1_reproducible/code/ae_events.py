"""
Adverse Event detection — Project Bayes.

For each Hard or Meta-Hard encounter, identifies the timestamps T of qualifying
adverse events:
  AE1 — ICU transfer (any of 3 sources)
  AE2 — Intubation / mechanical ventilation
  AE3 — Acute dialysis initiation

Returns sidecar table `ae_events.csv` with one row per (encounter_id, ae_type)
where the event occurred ≥ 24h after admission start.

See TRUNCATION.md §6 for the event-detection logic.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pandas as pd

from renderer import EncounterDataLoader, _combine_date_time, TABLES_DIR


ICU_DEPT_PATTERN = r"\b(?:ICU|CCU|INTENSIVE\s*CARE|CORONARY\s*CARE)\b"
ICU_CRITCARE_CPTS = {"99291", "99292"}
ICU_REVENUE_CODE_RANGE = ("0200", "0219")

INTUBATION_CPTS = {"94002", "94003", "94004", "31500"}
INTUBATION_DESC_PATTERN = r"MECHANIC.*VENTIL|INTUBAT"

DIALYSIS_RX_PATTERN = r"DIALYSIS|HEMODIALYSIS"
DIALYSIS_CPTS = {"90935", "90937", "90945"}


def detect_ae_events(encounter_id: str, loader: EncounterDataLoader) -> dict:
    """Return AE timing dict: {ae_type: {"T": datetime, "source": str} | None}."""
    case = loader.get_case(encounter_id)
    admit_ts = pd.to_datetime(case["EN_START_DATE"])
    data = loader.load(encounter_id)

    results: dict[str, dict | None] = {"AE1": None, "AE2": None, "AE3": None}

    # AE1 — ICU transfer (3 sources)
    icu_candidates: list[tuple[pd.Timestamp, str]] = []

    # Source 1: prescription_administrations.AD_DEPT (we use prescription_orders.RX_DEPT as proxy)
    meds = data["meds"]
    if not meds.empty and "RX_DEPT" in meds.columns:
        icu_rx = meds[meds["RX_DEPT"].fillna("").str.contains(ICU_DEPT_PATTERN, case=False, regex=True)]
        if not icu_rx.empty:
            icu_rx = icu_rx.copy()
            icu_rx["TS"] = _combine_date_time(icu_rx, "RX_ORDER_DATE", "RX_ORDER_TIME")
            ts = icu_rx["TS"].min()
            if pd.notna(ts):
                icu_candidates.append((ts, "prescription_orders.RX_DEPT"))

    # Source 2: encounters.EN_DEPT — admission/transfer department
    encs = data["encounters"]
    if not encs.empty and "EN_DEPT" in encs.columns:
        icu_enc = encs[encs["EN_DEPT"].fillna("").str.contains(ICU_DEPT_PATTERN, case=False, regex=True)]
        if not icu_enc.empty:
            icu_enc = icu_enc.copy()
            icu_enc["TS"] = _combine_date_time(icu_enc, "EN_START_DATE", "EN_START_TIME")
            ts = icu_enc["TS"].min()
            if pd.notna(ts):
                icu_candidates.append((ts, "encounters.EN_DEPT"))

    # Source 3: procedures.PX_CODE — critical care CPTs
    procs = data["procedures"]
    if not procs.empty:
        critcare = procs[procs["PX_CODE"].astype(str).isin(ICU_CRITCARE_CPTS)]
        if not critcare.empty:
            critcare = critcare.copy()
            critcare["TS"] = _combine_date_time(critcare, "PX_SERVICE_DATE", "PX_SERVICE_TIME")
            ts = critcare["TS"].min()
            if pd.notna(ts):
                icu_candidates.append((ts, "procedures.PX_CODE.99291_99292"))

    if icu_candidates:
        ts, source = min(icu_candidates, key=lambda x: x[0])
        if ts >= admit_ts + timedelta(hours=24):
            results["AE1"] = {"T": ts, "source": source, "T_minus_24h": ts - timedelta(hours=24)}

    # AE2 — Intubation / ventilation
    if not procs.empty:
        intub_by_code = procs[procs["PX_CODE"].astype(str).isin(INTUBATION_CPTS)]
        intub_by_desc = procs[procs.get("PX_HCS_DESC", pd.Series(dtype=str)).fillna("").str.contains(
            INTUBATION_DESC_PATTERN, case=False, regex=True
        )]
        intub = pd.concat([intub_by_code, intub_by_desc]).drop_duplicates()
        if not intub.empty:
            intub = intub.copy()
            intub["TS"] = _combine_date_time(intub, "PX_SERVICE_DATE", "PX_SERVICE_TIME")
            ts = intub["TS"].min()
            if pd.notna(ts) and ts >= admit_ts + timedelta(hours=24):
                results["AE2"] = {"T": ts, "source": "procedures.intubation",
                                  "T_minus_24h": ts - timedelta(hours=24)}

    # AE3 — Acute dialysis initiation
    dialysis_candidates: list[tuple[pd.Timestamp, str]] = []
    if not meds.empty:
        dial_rx = meds[meds["RX_GENERIC_NAME"].fillna("").str.contains(
            DIALYSIS_RX_PATTERN, case=False, regex=True
        )]
        if not dial_rx.empty:
            dial_rx = dial_rx.copy()
            dial_rx["TS"] = _combine_date_time(dial_rx, "RX_ORDER_DATE", "RX_ORDER_TIME")
            ts = dial_rx["TS"].min()
            if pd.notna(ts):
                dialysis_candidates.append((ts, "prescription_orders.dialysis"))
    if not procs.empty:
        dial_cpt = procs[procs["PX_CODE"].astype(str).isin(DIALYSIS_CPTS)]
        if not dial_cpt.empty:
            dial_cpt = dial_cpt.copy()
            dial_cpt["TS"] = _combine_date_time(dial_cpt, "PX_SERVICE_DATE", "PX_SERVICE_TIME")
            ts = dial_cpt["TS"].min()
            if pd.notna(ts):
                dialysis_candidates.append((ts, "procedures.dialysis_CPT"))
    if dialysis_candidates:
        ts, source = min(dialysis_candidates, key=lambda x: x[0])
        if ts >= admit_ts + timedelta(hours=24):
            results["AE3"] = {"T": ts, "source": source, "T_minus_24h": ts - timedelta(hours=24)}

    return results


def build_ae_events_sidecar(
    output_path: Path = TABLES_DIR.parent / "ae_events.csv",
    only_tiers: tuple[str, ...] = ("hard", "meta_hard"),
) -> pd.DataFrame:
    """Compute AE events for all Hard + Meta-Hard cases. Write sidecar CSV."""
    loader = EncounterDataLoader()
    cases = loader.cases
    target = cases[cases["COMPLEXITY_TIER"].isin(only_tiers)]
    rows: list[dict] = []
    for i, (_, case) in enumerate(target.iterrows(), start=1):
        if i % 10 == 0:
            print(f"  processed {i}/{len(target)} encounters")
        try:
            events = detect_ae_events(case["ENCOUNTER_ID"], loader)
        except Exception as e:
            print(f"  encounter {case['ENCOUNTER_ID']}: {e}")
            continue
        for ae_type, info in events.items():
            if info is None:
                continue
            rows.append({
                "ENCOUNTER_ID": case["ENCOUNTER_ID"],
                "COMPLEXITY_TIER": case["COMPLEXITY_TIER"],
                "LOS_BUCKET": case["LOS_BUCKET"],
                "AE_TYPE": ae_type,
                "T_EVENT": info["T"],
                "T_MINUS_24H": info["T_minus_24h"],
                "SOURCE": info["source"],
            })
    df = pd.DataFrame(rows)
    df.to_csv(output_path, index=False)
    print(f"\n✓ Wrote {len(df)} AE events to {output_path}")
    print(f"  Encounters with ≥1 event: {df['ENCOUNTER_ID'].nunique() if not df.empty else 0}")
    if not df.empty:
        print("  By event type:")
        print(df["AE_TYPE"].value_counts().to_string(header=False))
    return df


if __name__ == "__main__":
    build_ae_events_sidecar()
