"""
10a_pull_donor_clinical_data.py

Pull labs, vitals, procedures, and Rx from Snowflake for the unique
rank-1 matched-donor encounter IDs. Saves to a dedicated parquet cache
that is NOT overwritten by subsequent pipeline runs.

Run ONCE before 10_temporal_propensity_analysis.py.

Usage (from project root):
    source '/home/pvam/projects/PROTEGE - HealthBenck/PSI/bin/activate'
    python src/10a_pull_donor_clinical_data.py

Output:
    data/interim/snowflake_cache/donor_temporal/
        labs.parquet
        vitals.parquet
        procedures.parquet
        rx_orders.parquet
        meta.json          ← pull timestamp + donor count
"""

from __future__ import annotations

import json
import os
import sys
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

ROOT      = Path(__file__).resolve().parents[1]
OUT_DIR   = ROOT / "data/interim/snowflake_cache/donor_temporal"
OUT_DIR.mkdir(parents=True, exist_ok=True)

load_dotenv(ROOT / ".env")

# ── Config ────────────────────────────────────────────────────────────────────
SF_ACCOUNT   = os.environ.get("SF_ACCOUNT",   "APHHHWO-PROTEGE_PARTNER")
SF_USER      = os.environ["SF_USER"]
SF_ROLE      = os.environ.get("SF_ROLE",      "READ_ONLY")
SF_WAREHOUSE = os.environ.get("SF_WAREHOUSE", "READ_ONLY_2XL_WH")
FORBIDDEN    = [1990, 3707, 3490]
BATCH_SIZE   = 8_000    # stay safely below Snowflake ~16K IN-clause limit

TBL = {
    "LABS":               "OMNY_REPL_ID.CUSTOM.LABS",
    "VITALS":             "OMNY_REPL_ID.CUSTOM.VITALS",
    "PROCEDURES":         "OMNY_REPL_ID.CUSTOM.PROCEDURES",
    "PRESCRIPTION_ORDERS":"OMNY_REPL_ID.CUSTOM.PRESCRIPTION_ORDERS",
}

# ── Load donor IDs ────────────────────────────────────────────────────────────
pairs = pd.read_csv(ROOT / "results/tables/all_matched_pairs.csv")
r1    = pairs[pairs["match_rank"] == 1]
donor_ids = r1["donor_enc"].astype(str).unique().tolist()
print(f"Unique rank-1 donor IDs: {len(donor_ids)}")

# ── Snowflake connection ──────────────────────────────────────────────────────
def get_conn():
    try:
        import snowflake.connector
    except ImportError:
        sys.exit("snowflake-connector-python not installed — run: pip install snowflake-connector-python")

    for browser_path in [
        "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe",
        "/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
    ]:
        if os.path.exists(browser_path):
            webbrowser.register("wsl-browser", None,
                                webbrowser.BackgroundBrowser(browser_path),
                                preferred=True)
            print(f"  WSL2 browser: {browser_path}")
            break

    print("Opening Snowflake — Okta browser will open in Windows …")
    conn = snowflake.connector.connect(
        account       = SF_ACCOUNT,
        user          = SF_USER,
        authenticator = "externalbrowser",
        role          = SF_ROLE,
        warehouse     = SF_WAREHOUSE,
    )
    print("  Connected.")
    return conn


def batch_pull(conn, table: str, enc_ids: list[str]) -> pd.DataFrame:
    """Pull all rows for enc_ids from table, batched to avoid IN-clause limit."""
    forbidden_sql = ", ".join(str(s) for s in FORBIDDEN)
    pieces = []
    n_batches = (len(enc_ids) + BATCH_SIZE - 1) // BATCH_SIZE
    for i, start in enumerate(range(0, len(enc_ids), BATCH_SIZE), 1):
        batch = enc_ids[start : start + BATCH_SIZE]
        ids_sql = ", ".join(f"'{e}'" for e in batch)
        sql = (
            f"SELECT * FROM {table} "
            f"WHERE ENCOUNTER_ID IN ({ids_sql}) "
            f"AND DATA_SUPPLIER_ID NOT IN ({forbidden_sql})"
        )
        cur = conn.cursor()
        cur.execute(sql)
        df = cur.fetch_pandas_all()
        cur.close()
        pieces.append(df)
        print(f"    batch {i}/{n_batches}: {len(df):,} rows")
    return pd.concat(pieces, ignore_index=True) if pieces else pd.DataFrame()


# ── Main pull ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    conn = get_conn()

    table_map = {
        "labs":      TBL["LABS"],
        "vitals":    TBL["VITALS"],
        "procedures":TBL["PROCEDURES"],
        "rx_orders": TBL["PRESCRIPTION_ORDERS"],
    }

    summary = {}
    for name, tbl_fqn in table_map.items():
        out_path = OUT_DIR / f"{name}.parquet"
        if out_path.exists():
            existing = pd.read_parquet(out_path)
            print(f"[{name}] already cached ({len(existing):,} rows) — skipping."
                  "  Delete to re-pull.")
            summary[name] = len(existing)
            continue

        print(f"\n[{name}] pulling from {tbl_fqn} …")
        df = batch_pull(conn, tbl_fqn, donor_ids)
        # Cast LB_REF_HIGH to str if present (avoids mixed-type parquet issue)
        if "LB_REF_HIGH" in df.columns:
            df["LB_REF_HIGH"] = df["LB_REF_HIGH"].astype(str)
        df.to_parquet(out_path, index=False)
        summary[name] = len(df)
        print(f"  → saved {len(df):,} rows to {out_path.relative_to(ROOT)}")

    conn.close()

    meta = {
        "pulled_at":   datetime.now(timezone.utc).isoformat(),
        "n_donors":    len(donor_ids),
        "row_counts":  summary,
    }
    (OUT_DIR / "meta.json").write_text(json.dumps(meta, indent=2))
    print(f"\nDone. Meta written to {(OUT_DIR/'meta.json').relative_to(ROOT)}")
    for name, n in summary.items():
        print(f"  {name}: {n:,} rows")
