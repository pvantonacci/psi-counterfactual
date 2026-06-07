"""
Pre-build per-encounter parquet caches for the 360 eval cases.

Each large OMNY CSV (notes, labs, procedures, ...) is scanned ONCE and split
into per-encounter parquet files. The renderer's EncounterDataLoader checks
the cache first and only falls back to CSV scanning if a cache file is
missing.

Cuts per-encounter load time from ~30s to ~0.1s.

Run:
    python3 build_cache.py
"""

from __future__ import annotations

import time
from pathlib import Path

import pandas as pd

from renderer import TABLES_DIR


CACHE_DIR = TABLES_DIR.parent / "cache"


# Tables to cache. Each is filtered to the 360 selected encounters.
TABLES = {
    "encounters": "encounters.csv",
    "diagnoses": "diagnoses.csv",
    "vitals": "vitals.csv",
    "labs": "labs.csv",
    "procedures": "procedures.csv",
    "meds": "prescription_orders.csv",
    "admins": "prescription_administrations.csv",
    "notes": "omny_notes_concatenated.csv",
}


def build_cache() -> None:
    CACHE_DIR.mkdir(exist_ok=True)
    cases = pd.read_csv(TABLES_DIR / "eval_cases.csv")
    target_encounter_ids = set(cases["ENCOUNTER_ID"])
    target_omny_ids = set(cases["OMNY_ID"])
    print(f"Building cache for {len(target_encounter_ids)} encounters...")

    for table_key, fname in TABLES.items():
        csv_path = TABLES_DIR / fname
        if not csv_path.exists():
            print(f"  skipping {table_key}: {csv_path} not found")
            continue

        start = time.time()
        print(f"\n  [{table_key}] scanning {csv_path.name}...")

        per_encounter_chunks: dict[str, list[pd.DataFrame]] = {
            eid: [] for eid in target_encounter_ids
        }

        rows_seen = 0
        rows_kept = 0
        for chunk in pd.read_csv(csv_path, chunksize=200_000, low_memory=False):
            rows_seen += len(chunk)
            if "ENCOUNTER_ID" not in chunk.columns:
                # Patient-level table (claims_*) — index by OMNY_ID instead
                mask = chunk["OMNY_ID"].isin(target_omny_ids)
                if mask.any():
                    sub = chunk[mask]
                    rows_kept += len(sub)
                    # Patient-level — write one shared parquet for now
                    out_path = CACHE_DIR / f"_patient_{table_key}.parquet"
                    if out_path.exists():
                        existing = pd.read_parquet(out_path)
                        sub = pd.concat([existing, sub], ignore_index=True)
                    sub.to_parquet(out_path, index=False)
                continue
            mask = chunk["ENCOUNTER_ID"].isin(target_encounter_ids)
            if not mask.any():
                continue
            kept = chunk[mask]
            rows_kept += len(kept)
            for eid, grp in kept.groupby("ENCOUNTER_ID"):
                per_encounter_chunks[eid].append(grp.copy())

        # Write one parquet per encounter for this table.
        # OMNY tables have dirty mixed-type columns (e.g., LB_REF_HIGH has both
        # strings like "5.4000" and numerics). Force all object columns to str
        # to avoid pyarrow conversion errors.
        n_written = 0
        for eid, chunks in per_encounter_chunks.items():
            if not chunks:
                continue
            df = pd.concat(chunks, ignore_index=True)
            for col in df.select_dtypes(include="object").columns:
                df[col] = df[col].astype(str)
            df.to_parquet(CACHE_DIR / f"{eid}_{table_key}.parquet", index=False)
            n_written += 1

        elapsed = time.time() - start
        print(f"    rows scanned: {rows_seen:,}  kept: {rows_kept:,}  "
              f"encounters written: {n_written}  ({elapsed:.1f}s)")

    print(f"\n✓ Cache built at {CACHE_DIR}")
    print(f"  Total parquet files: {len(list(CACHE_DIR.glob('*.parquet')))}")


if __name__ == "__main__":
    build_cache()
