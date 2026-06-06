"""
00_pull_psi_tables.py

Pull all OMNY_REPL_ID.CUSTOM tables filtered to the encounters in
data/raw/psi_inpatient_cases.csv, one CSV per table, into data/raw/psi_tables/.

Filter strategy (auto-detected per table from INFORMATION_SCHEMA):
  - Table has OMNY_ID + ENCOUNTER_ID  → filter by encounter pair
  - Table has OMNY_ID only            → filter by patient (OMNY_IDs looked up
                                         from encounter IDs at startup)
  - Table has neither                 → skip (reference / lookup table)

Also pulls OMNY_PROTEGE.PUBLIC.OMNY_NOTES_CONCATENATED filtered to the
same encounter pairs.

Run from project root:
    source PSI/bin/activate
    python src/00_pull_psi_tables.py
"""

import os
import time
import webbrowser
from pathlib import Path

import pandas as pd
import snowflake.connector

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

CASES_CSV  = Path("data/raw/psi_inpatient_cases.csv")
OUTPUT_DIR = Path("data/raw/psi_tables")

SNOWFLAKE_CONFIG = {
    "account":       os.environ.get("SF_ACCOUNT",   "APHHHWO-PROTEGE_PARTNER"),
    "user":          os.environ["SF_USER"],
    "authenticator": "externalbrowser",
    "role":          os.environ.get("SF_ROLE",      "READ_ONLY"),
    "warehouse":     os.environ.get("SF_WAREHOUSE", "READ_ONLY_2XL_WH"),
}

CUSTOM_DB     = "OMNY_REPL_ID"
CUSTOM_SCHEMA = "CUSTOM"

EXTRA_TABLES = [
    ("OMNY_PROTEGE", "PUBLIC", "OMNY_NOTES_CONCATENATED"),
]

BATCH_SIZE  = 10_000
MAX_RETRIES = 5


def connect() -> snowflake.connector.SnowflakeConnection:
    for _wb in [
        "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe",
        "/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
    ]:
        if os.path.exists(_wb):
            webbrowser.register("wsl-windows-browser", None,
                                webbrowser.BackgroundBrowser(_wb), preferred=True)
            break
    print("Opening browser for SSO authentication...")
    conn = snowflake.connector.connect(**SNOWFLAKE_CONFIG)
    print("Connected.\n")
    return conn


def list_custom_tables(conn: snowflake.connector.SnowflakeConnection) -> list[str]:
    cur = conn.cursor()
    cur.execute(
        f"SELECT TABLE_NAME FROM {CUSTOM_DB}.INFORMATION_SCHEMA.TABLES "
        f"WHERE TABLE_SCHEMA = '{CUSTOM_SCHEMA}' "
        f"AND TABLE_TYPE IN ('BASE TABLE', 'VIEW') "
        f"ORDER BY TABLE_NAME"
    )
    tables = [row[0] for row in cur.fetchall()]
    cur.close()
    return tables


def table_columns(
    conn: snowflake.connector.SnowflakeConnection,
    db: str, schema: str, table: str,
) -> set[str]:
    cur = conn.cursor()
    cur.execute(
        f"SELECT COLUMN_NAME FROM {db}.INFORMATION_SCHEMA.COLUMNS "
        f"WHERE TABLE_SCHEMA = '{schema}' AND TABLE_NAME = '{table}'"
    )
    cols = {row[0].upper() for row in cur.fetchall()}
    cur.close()
    return cols


def lookup_omny_ids(
    conn: snowflake.connector.SnowflakeConnection,
    enc_id_sql: str,
    custom_tables: list[str],
) -> list[str]:
    """Find OMNY_IDs for the given encounters using the first CUSTOM table
    that has both ENCOUNTER_ID and OMNY_ID columns."""
    for table in custom_tables:
        cols = table_columns(conn, CUSTOM_DB, CUSTOM_SCHEMA, table)
        if "ENCOUNTER_ID" in cols and "OMNY_ID" in cols:
            fq = f"{CUSTOM_DB}.{CUSTOM_SCHEMA}.{table}"
            cur = conn.cursor()
            cur.execute(
                f"SELECT DISTINCT OMNY_ID FROM {fq} "
                f"WHERE ENCOUNTER_ID IN ({enc_id_sql})"
            )
            omny_ids = [row[0] for row in cur.fetchall()]
            cur.close()
            print(f"Looked up {len(omny_ids)} unique OMNY_IDs via {table}\n")
            return omny_ids
    print("Warning: no table with both ENCOUNTER_ID and OMNY_ID found; "
          "patient-level tables will be skipped.\n")
    return []


def fetch_all(cur: snowflake.connector.cursor.SnowflakeCursor) -> list:
    rows: list = []
    attempt = 0
    while True:
        try:
            batch = cur.fetchmany(BATCH_SIZE)
            if not batch:
                break
            rows.extend(batch)
            if len(rows) % 100_000 == 0:
                print(f"    ... {len(rows):,} rows", flush=True)
        except Exception as e:
            attempt += 1
            if attempt > MAX_RETRIES:
                raise
            wait = 15 * attempt
            print(f"    fetch error (attempt {attempt}/{MAX_RETRIES}), retry in {wait}s: {e}", flush=True)
            time.sleep(wait)
    return rows


def pull_table(
    conn: snowflake.connector.SnowflakeConnection,
    db: str, schema: str, table: str,
    enc_id_sql: str, omny_id_sql: str | None,
) -> pd.DataFrame | None:
    cols = table_columns(conn, db, schema, table)
    has_enc  = "ENCOUNTER_ID" in cols
    has_omny = "OMNY_ID" in cols

    if not has_omny and not has_enc:
        print(f"  {table:<50s} SKIP (no ID columns)")
        return None

    fq = f"{db}.{schema}.{table}"

    if has_omny and has_enc:
        sql  = f"SELECT * FROM {fq} WHERE ENCOUNTER_ID IN ({enc_id_sql})"
        if omny_id_sql:
            sql += f" AND OMNY_ID IN ({omny_id_sql})"
        kind = "encounter"
    elif has_omny:
        if not omny_id_sql:
            print(f"  {table:<50s} SKIP (OMNY_ID only, no patient IDs available)")
            return None
        sql  = f"SELECT * FROM {fq} WHERE OMNY_ID IN ({omny_id_sql})"
        kind = "patient"
    else:
        sql  = f"SELECT * FROM {fq} WHERE ENCOUNTER_ID IN ({enc_id_sql})"
        kind = "encounter"

    cur = conn.cursor()
    cur.execute(sql)
    col_names = [d[0] for d in cur.description]
    rows = fetch_all(cur)
    cur.close()

    df = pd.DataFrame(rows, columns=col_names)
    print(f"  {table:<50s} {kind:<10s}  {len(df):>8,} rows")
    return df


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    cases   = pd.read_csv(CASES_CSV)
    enc_ids = cases["ENCOUNTER_ID"].dropna().unique().tolist()

    enc_id_sql = ", ".join(f"'{v}'" for v in enc_ids)

    print(f"PSI cases: {len(cases)} rows, {len(enc_ids)} unique encounters\n")

    conn = connect()
    try:
        custom_tables = list_custom_tables(conn)
        print(f"Found {len(custom_tables)} table(s) in {CUSTOM_DB}.{CUSTOM_SCHEMA}\n")

        omny_ids   = lookup_omny_ids(conn, enc_id_sql, custom_tables)
        omny_id_sql = ", ".join(f"'{v}'" for v in omny_ids) if omny_ids else None

        # ── OMNY_REPL_ID.CUSTOM tables ────────────────────────────────────────
        for table in custom_tables:
            df = pull_table(conn, CUSTOM_DB, CUSTOM_SCHEMA, table, enc_id_sql, omny_id_sql)
            if df is not None:
                out = OUTPUT_DIR / f"{table.lower()}.csv"
                df.to_csv(out, index=False)

        # ── Extra tables from other schemas ───────────────────────────────────
        print()
        for db, schema, table in EXTRA_TABLES:
            df = pull_table(conn, db, schema, table, enc_id_sql, omny_id_sql)
            if df is not None:
                out = OUTPUT_DIR / f"{table.lower()}.csv"
                df.to_csv(out, index=False)

    finally:
        conn.close()
        print("\nConnection closed.")

    saved      = sorted(OUTPUT_DIR.glob("*.csv"))
    total_rows = sum(sum(1 for _ in open(f)) - 1 for f in saved)
    print(f"\nSaved {len(saved)} CSV(s) to {OUTPUT_DIR}")
    print(f"Total rows across all tables: {total_rows:,}")


if __name__ == "__main__":
    main()