#!/usr/bin/env python3
"""
Loop the PSI counterfactual pipeline over every PSI type found in the metadata.

Each type runs in its own output directory:
    outputs/<PSI_TYPE>/cases.csv
    outputs/<PSI_TYPE>/matched_sets.parquet
    outputs/<PSI_TYPE>/propensity_scores.csv
    outputs/<PSI_TYPE>/logs/pipeline_<RUN_ID>.log
    ...

Usage:
    source PSI/bin/activate
    python src/03_run_all_psi_types.py

Results summary written to: results/tables/all_psi_types_summary.md
"""

import subprocess, sys, time
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd

PYTHON      = sys.executable
PSI_META    = "data/raw/psi_inpatient_cases.csv"
OUTPUT_ROOT = "outputs"
SUMMARY_MD  = Path("results/tables") / "all_psi_types_summary.md"

# ── Discover all PSI types ────────────────────────────────────────────────────
psi_meta   = pd.read_csv(PSI_META, low_memory=False)
psi_types  = sorted(psi_meta["PSI_CODE"].dropna().unique().tolist())
n_total    = len(psi_types)

print(f"PSI types to run: {n_total}")
for pt in psi_types:
    n = (psi_meta["PSI_CODE"] == pt).sum()
    print(f"  {pt}: {n} encounters")
print()

# ── Run each type sequentially ────────────────────────────────────────────────
results = []
start_all = time.time()

for i, psi_type in enumerate(psi_types, 1):
    print(f"\n{'='*70}")
    print(f"[{i}/{n_total}] Running: {psi_type}")
    print(f"{'='*70}")
    t0 = time.time()

    result = subprocess.run(
        [PYTHON, "src/02_counterfactual_pipeline.py",
         "--psi-type", psi_type,
         "--output-root", OUTPUT_ROOT],
        capture_output=False,   # let stdout/stderr flow to terminal
    )

    elapsed = time.time() - t0
    # A run is considered successful if matched_sets.parquet was written,
    # regardless of exit code (Python Tee cleanup can emit non-zero on some systems).
    ms_check = Path(OUTPUT_ROOT) / psi_type / "matched_sets.parquet"
    if ms_check.exists():
        status = "PASS"
    elif result.returncode == 0:
        status = "PASS (no matched_sets)"
    else:
        status = f"FAIL (exit {result.returncode})"
    print(f"\n→ {psi_type}: {status} in {elapsed:.0f}s")

    # Collect matched-sets count if output exists
    ms_path = Path(OUTPUT_ROOT) / psi_type / "matched_sets.parquet"
    n_pairs = None
    if ms_path.exists():
        try:
            n_pairs = len(pd.read_parquet(ms_path))
        except Exception:
            pass

    cases_path = Path(OUTPUT_ROOT) / psi_type / "cases.csv"
    n_cases = None
    if cases_path.exists():
        try:
            n_cases = len(pd.read_csv(cases_path))
        except Exception:
            pass

    results.append({
        "psi_type":    psi_type,
        "status":      status,
        "n_cases":     n_cases,
        "n_pairs":     n_pairs,
        "elapsed_s":   round(elapsed),
    })

total_elapsed = time.time() - start_all

# ── Write summary markdown ────────────────────────────────────────────────────
Path("results/tables").mkdir(parents=True, exist_ok=True)
ts = datetime.now(timezone.utc).isoformat()

lines = [
    "# PSI Counterfactual Pipeline — All PSI Types Summary",
    "",
    f"**Run completed:** {ts}  ",
    f"**Total wall time:** {total_elapsed/60:.1f} minutes  ",
    f"**PSI types attempted:** {n_total}  ",
    "",
    "| PSI Type | Status | Cases | Matched Pairs | Time (s) |",
    "|---|---|---|---|---|",
]
for r in results:
    lines.append(
        f"| {r['psi_type']} | {r['status']} "
        f"| {r['n_cases'] if r['n_cases'] is not None else '—'} "
        f"| {r['n_pairs']  if r['n_pairs']  is not None else '—'} "
        f"| {r['elapsed_s']} |"
    )

n_pass = sum(1 for r in results if r["status"] == "PASS")
n_fail = n_total - n_pass
total_pairs = sum(r["n_pairs"] or 0 for r in results)

lines += [
    "",
    f"**Passed:** {n_pass} / {n_total}  ",
    f"**Failed:** {n_fail}  ",
    f"**Total matched pairs across all types:** {total_pairs}  ",
    "",
    "Per-type outputs are in `outputs/<PSI_TYPE>/`.  ",
    "Logs: `outputs/<PSI_TYPE>/logs/pipeline_*.log`",
]

SUMMARY_MD.write_text("\n".join(lines))

# ── Rebuild all_matched_pairs.csv from per-type parquet outputs ───────────────
pairs_frames = []
for r in results:
    ms_path = Path(OUTPUT_ROOT) / r["psi_type"] / "matched_sets.parquet"
    if ms_path.exists():
        try:
            df = pd.read_parquet(ms_path)
            df["psi_type"] = r["psi_type"]
            pairs_frames.append(df)
        except Exception as e:
            print(f"  WARNING: could not read {ms_path}: {e}")

PAIRS_CSV = Path("results/tables/all_matched_pairs.csv")
if pairs_frames:
    all_pairs = pd.concat(pairs_frames, ignore_index=True)
    PAIRS_CSV.write_text("")   # truncate first
    all_pairs.to_csv(PAIRS_CSV, index=False)
    n_unique_cases  = all_pairs["case_enc"].nunique()
    n_unique_donors = all_pairs["donor_enc"].nunique()
    n_r1            = (all_pairs["match_rank"] == 1).sum()
    print(f"Matched pairs CSV written: {PAIRS_CSV}")
    print(f"  Total rows    : {len(all_pairs):,}")
    print(f"  Unique cases  : {n_unique_cases}")
    print(f"  Rank-1 pairs  : {n_r1}")
    print(f"  Unique donors : {n_unique_donors:,}")
else:
    print("WARNING: no matched_sets.parquet files found — all_matched_pairs.csv not updated")

print(f"\n{'='*70}")
print(f"All done. {n_pass}/{n_total} passed. {total_pairs} total matched pairs.")
print(f"Summary written to: {SUMMARY_MD}")
print(f"{'='*70}")
