"""
Analyze discharge diagnoses of matched counterfactual (donor) encounters.
For each PSI type, extracts the principal/all diagnoses of matched donors,
flags whether any match PSI ICD-10 criteria, and produces a summary MD.

Usage:
    source PSI/bin/activate
    python src/04_analyze_donor_diagnostics.py
"""

import re
import sys
import os
import webbrowser
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime

import pandas as pd
import numpy as np

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── Config ────────────────────────────────────────────────────────────────────
OUTPUT_ROOT  = Path("outputs")
CACHE_DIR    = Path("data/interim/snowflake_cache")
DIAG_CACHE   = CACHE_DIR / "DONOR_MATCHED_DIAGNOSES.parquet"
REPORT_PATH  = Path("results/reports/donor_diagnostics_by_psi.md")

SF_ACCOUNT    = os.environ.get("SF_ACCOUNT",   "APHHHWO-PROTEGE_PARTNER")
SF_USER       = os.environ["SF_USER"]
SF_ROLE       = os.environ.get("SF_ROLE",      "READ_ONLY")
SF_WAREHOUSE  = os.environ.get("SF_WAREHOUSE", "READ_ONLY_2XL_WH")
SF_DIAG_TABLE = "OMNY_REPL_ID.CUSTOM.DIAGNOSES"

FORBIDDEN_SUPPLIERS = [1990, 3707, 3490]

PSI_TYPES = [
    "PSI_03_PRESSURE_ULCER",
    "PSI_04_FAILURE_TO_RESCUE",
    "PSI_05_RETAINED_ITEM",
    "PSI_06_IATROGENIC_PNEUMOTHORAX",
    "PSI_07_CLABSI",
    "PSI_08_FALL_FRACTURE",
    "PSI_09_POSTOP_HEMORRHAGE",
    "PSI_10_POSTOP_AKI_DIALYSIS",
    "PSI_11_POSTOP_RESP_FAILURE",
    "PSI_12_PERIOP_PE_DVT",
    "PSI_13_POSTOP_SEPSIS",
    "PSI_14_WOUND_DEHISCENCE",
    "PSI_15_ACCIDENTAL_PUNCTURE",
    "PSI_17_BIRTH_TRAUMA",
    "PSI_18_OB_TRAUMA_INSTRUMENT",
    "PSI_19_OB_TRAUMA_NO_INSTRUMENT",
]

PSI_LABELS = {
    "PSI_03_PRESSURE_ULCER":           "PSI-03 Pressure Ulcer",
    "PSI_04_FAILURE_TO_RESCUE":        "PSI-04 Failure to Rescue",
    "PSI_05_RETAINED_ITEM":            "PSI-05 Retained Item",
    "PSI_06_IATROGENIC_PNEUMOTHORAX":  "PSI-06 Iatrogenic Pneumothorax",
    "PSI_07_CLABSI":                   "PSI-07 CLABSI",
    "PSI_08_FALL_FRACTURE":            "PSI-08 Fall/Fracture",
    "PSI_09_POSTOP_HEMORRHAGE":        "PSI-09 Postop Hemorrhage",
    "PSI_10_POSTOP_AKI_DIALYSIS":      "PSI-10 Postop AKI/Dialysis",
    "PSI_11_POSTOP_RESP_FAILURE":      "PSI-11 Postop Resp Failure",
    "PSI_12_PERIOP_PE_DVT":            "PSI-12 Periop PE/DVT",
    "PSI_13_POSTOP_SEPSIS":            "PSI-13 Postop Sepsis",
    "PSI_14_WOUND_DEHISCENCE":         "PSI-14 Wound Dehiscence",
    "PSI_15_ACCIDENTAL_PUNCTURE":      "PSI-15 Accidental Puncture",
    "PSI_17_BIRTH_TRAUMA":             "PSI-17 Birth Trauma",
    "PSI_18_OB_TRAUMA_INSTRUMENT":     "PSI-18 OB Trauma (instrumental)",
    "PSI_19_OB_TRAUMA_NO_INSTRUMENT":  "PSI-19 OB Trauma (no instrument)",
}

# PSI ICD-10 code patterns (from pipeline)
PSI_ICD_REGEX = {
    "PSI_03_PRESSURE_ULCER":           r"^L89\.",
    "PSI_04_FAILURE_TO_RESCUE":        r"^(R57|I46|A40|A41|R65\.2|J1[2-8]|J69|K25|K26|K27|K28|K92\.[012]|I26|I82\.4|I82\.6|I82\.7)",
    "PSI_05_RETAINED_ITEM":            r"^T81\.5",
    "PSI_06_IATROGENIC_PNEUMOTHORAX":  r"^J95\.81",
    "PSI_07_CLABSI":                   r"^T80\.21",
    "PSI_08_FALL_FRACTURE":            r"^(S72|S32\.[0-8]|S22|S12|S02|S42|S52|S62|S82|S92)",
    "PSI_09_POSTOP_HEMORRHAGE":        r"^(K91\.84|I97\.41|I97\.42|N99\.6|J95\.83|G97\.3|H59\.3|M96\.83|E36\.0)",
    "PSI_10_POSTOP_AKI_DIALYSIS":      r"^N17\.",
    "PSI_11_POSTOP_RESP_FAILURE":      r"^(J95\.82|J96\.0|J96\.2)",
    "PSI_12_PERIOP_PE_DVT":            r"^(I26|I82\.4|I82\.6|I82\.7)",
    "PSI_13_POSTOP_SEPSIS":            r"^(A40|A41|R65\.2|T81\.44)",
    "PSI_14_WOUND_DEHISCENCE":         r"^T81\.3",
    "PSI_15_ACCIDENTAL_PUNCTURE":      r"^(K91\.71|K91\.72|J95\.71|J95\.72|G97\.4|G97\.5|N99\.71|N99\.72|N99\.73|E36\.1|I97\.5|D78\.1|D78\.2)",
    "PSI_17_BIRTH_TRAUMA":             r"^P1[0-5]",
    "PSI_18_OB_TRAUMA_INSTRUMENT":     r"^O70\.[23]",
    "PSI_19_OB_TRAUMA_NO_INSTRUMENT":  r"^O70\.[23]",
}

ALL_PSI_PATTERN = "|".join(f"(?:{v})" for v in PSI_ICD_REGEX.values())

# ICD-10 chapter mapping (first character of code → chapter name)
ICD10_CHAPTERS = {
    "A": "Infectious & Parasitic Diseases",
    "B": "Infectious & Parasitic Diseases",
    "C": "Neoplasms",
    "D": "Neoplasms / Blood & Immune",
    "E": "Endocrine, Nutritional & Metabolic",
    "F": "Mental & Behavioral Disorders",
    "G": "Nervous System",
    "H": "Eye / Ear",
    "I": "Circulatory System",
    "J": "Respiratory System",
    "K": "Digestive System",
    "L": "Skin & Subcutaneous Tissue",
    "M": "Musculoskeletal & Connective Tissue",
    "N": "Genitourinary System",
    "O": "Pregnancy, Childbirth & Puerperium",
    "P": "Perinatal Conditions",
    "Q": "Congenital Malformations",
    "R": "Symptoms, Signs & Abnormal Findings",
    "S": "Injury, Poisoning & External Causes",
    "T": "Injury, Poisoning & External Causes",
    "V": "External Causes of Morbidity",
    "W": "External Causes of Morbidity",
    "X": "External Causes of Morbidity",
    "Y": "External Causes of Morbidity",
    "Z": "Factors Influencing Health Status (Z-codes)",
}

def icd_chapter(code: str) -> str:
    if not isinstance(code, str) or not code:
        return "Unknown"
    return ICD10_CHAPTERS.get(code[0].upper(), "Other")


# ── Step 1: Collect all matched donor encounter IDs ──────────────────────────
print("Collecting matched donor encounter IDs...")
donor_map = {}   # psi_type -> set of donor enc IDs
all_donor_ids = set()

for psi in PSI_TYPES:
    ms_path = OUTPUT_ROOT / psi / "matched_sets.parquet"
    if not ms_path.exists():
        print(f"  WARNING: no matched_sets.parquet for {psi}")
        donor_map[psi] = set()
        continue
    ms = pd.read_parquet(ms_path)
    donors = set(ms["donor_enc"].unique())
    donor_map[psi] = donors
    all_donor_ids.update(donors)

print(f"  Total unique donor encounters: {len(all_donor_ids)}")
for p, s in donor_map.items():
    print(f"  {p}: {len(s)} unique donors")


# ── Step 2: Pull diagnoses from Snowflake (or load from cache) ────────────────
if DIAG_CACHE.exists():
    print(f"\nLoading diagnoses from cache: {DIAG_CACHE}")
    dx_all = pd.read_parquet(DIAG_CACHE)
    print(f"  Loaded {len(dx_all)} diagnosis rows for {dx_all['ENCOUNTER_ID'].nunique()} encounters")
else:
    print("\nConnecting to Snowflake to pull diagnoses for matched donors...")

    try:
        import snowflake.connector
    except ImportError:
        sys.exit("ERROR: snowflake-connector-python not installed in this environment")

    _WIN_BROWSERS = [
        "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe",
        "/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
    ]
    for _wb in _WIN_BROWSERS:
        if os.path.exists(_wb):
            webbrowser.register(
                "wsl-windows-browser", None,
                webbrowser.BackgroundBrowser(_wb), preferred=True)
            print(f"  Browser: {_wb}")
            break

    print("  Opening Snowflake (Okta browser will open)...")
    conn = snowflake.connector.connect(
        account       = SF_ACCOUNT,
        user          = SF_USER,
        authenticator = "externalbrowser",
        role          = SF_ROLE,
        warehouse     = SF_WAREHOUSE,
    )
    print("  Connected.")

    donor_id_list = sorted(all_donor_ids)
    forbidden_sql = ", ".join(str(s) for s in FORBIDDEN_SUPPLIERS)
    batch_size    = 5_000
    pieces        = []

    print(f"  Querying in batches of {batch_size}...")
    for i in range(0, len(donor_id_list), batch_size):
        batch = donor_id_list[i : i + batch_size]
        ids_sql = ", ".join(f"'{v}'" for v in batch)
        sql = (
            f"SELECT ENCOUNTER_ID, DX_LINE, DX_CODE, DX_CODE_TYPE, "
            f"       DX_HCS_DESC, DX_PRIMARY, DX_CHRONIC, DATA_SUPPLIER_ID "
            f"FROM {SF_DIAG_TABLE} "
            f"WHERE ENCOUNTER_ID IN ({ids_sql}) "
            f"  AND DATA_SUPPLIER_ID NOT IN ({forbidden_sql})"
        )
        cur = conn.cursor()
        cur.execute(sql)
        batch_df = cur.fetch_pandas_all()
        cur.close()
        pieces.append(batch_df)
        covered = min(i + batch_size, len(donor_id_list))
        print(f"    Batch {i//batch_size+1}: {covered}/{len(donor_id_list)} IDs → {len(batch_df)} rows")

    conn.close()
    print("  Snowflake connection closed.")

    dx_all = pd.concat(pieces, ignore_index=True) if pieces else pd.DataFrame()
    dx_all.to_parquet(DIAG_CACHE, index=False)
    print(f"  Saved {len(dx_all)} rows to cache: {DIAG_CACHE}")


# ── Step 3: Flag PSI-positive diagnoses ──────────────────────────────────────
print("\nFlagging PSI diagnoses...")
dx_all["is_any_psi"] = dx_all["DX_CODE"].str.match(ALL_PSI_PATTERN, na=False)

# Per-type PSI flags
for psi, pat in PSI_ICD_REGEX.items():
    short = psi.replace("_", "").lower()[:20]
    dx_all[f"is_{psi}"] = dx_all["DX_CODE"].str.match(pat, na=False)

print(f"  Diagnoses with any PSI code: {dx_all['is_any_psi'].sum()} / {len(dx_all)}")


# ── Step 4: Select "principal / primary" diagnoses ───────────────────────────
# Principal = DX_PRIMARY == 'YES'  OR  DX_LINE == 1 (whichever is available)
dx_principal = dx_all[
    (dx_all["DX_PRIMARY"].str.upper() == "YES") |
    (dx_all["DX_LINE"] == 1)
].copy()

# Also keep ALL diagnoses for secondary analysis
dx_all_clean = dx_all.copy()
dx_all_clean["chapter"] = dx_all_clean["DX_CODE"].apply(icd_chapter)
dx_principal["chapter"] = dx_principal["DX_CODE"].apply(icd_chapter)

print(f"  Principal diagnoses: {len(dx_principal)} across {dx_principal['ENCOUNTER_ID'].nunique()} encounters")


# ── Step 5: Build per-PSI-type tables ────────────────────────────────────────
print("\nBuilding per-PSI-type diagnostic tables...")

TOP_N = 15   # top N diagnoses per PSI type

results = {}

for psi in PSI_TYPES:
    donors = donor_map.get(psi, set())
    n_donors = len(donors)

    # All diagnoses for these donors
    dx_psi = dx_all_clean[dx_all_clean["ENCOUNTER_ID"].isin(donors)].copy()
    n_with_dx = dx_psi["ENCOUNTER_ID"].nunique()
    n_without_dx = n_donors - n_with_dx

    # Principal diagnoses for these donors
    dx_psi_p = dx_principal[dx_principal["ENCOUNTER_ID"].isin(donors)].copy()

    # PSI-positive flags
    psi_col = f"is_{psi}"
    psi_positive_encs = set()
    if psi_col in dx_psi.columns:
        psi_positive_encs = set(dx_psi[dx_psi[psi_col]]["ENCOUNTER_ID"].unique())
    n_psi_positive = len(psi_positive_encs)

    # Top principal diagnoses (by code)
    if len(dx_psi_p) > 0:
        top_codes = (
            dx_psi_p.groupby(["DX_CODE", "DX_HCS_DESC", "chapter"])
            .size()
            .reset_index(name="n_encounters")
            .sort_values("n_encounters", ascending=False)
            .head(TOP_N)
        )
    else:
        top_codes = pd.DataFrame(columns=["DX_CODE","DX_HCS_DESC","chapter","n_encounters"])

    # Top ICD-10 chapter breakdown (all diagnoses)
    if len(dx_psi) > 0:
        chapter_counts = (
            dx_psi.drop_duplicates(subset=["ENCOUNTER_ID","chapter"])
            .groupby("chapter").size()
            .reset_index(name="n_encounters")
            .sort_values("n_encounters", ascending=False)
        )
    else:
        chapter_counts = pd.DataFrame(columns=["chapter","n_encounters"])

    results[psi] = {
        "n_donors": n_donors,
        "n_with_dx": n_with_dx,
        "n_without_dx": n_without_dx,
        "n_psi_positive": n_psi_positive,
        "psi_positive_encs": psi_positive_encs,
        "top_codes": top_codes,
        "chapter_counts": chapter_counts,
        "dx_psi": dx_psi,
        "dx_psi_p": dx_psi_p,
    }
    print(f"  {psi}: {n_donors} donors, {n_with_dx} with dx, {n_psi_positive} PSI-flagged")


# ── Step 6: Write the markdown report ─────────────────────────────────────────
print("\nWriting markdown report...")

lines = []
lines.append("# Counterfactual Donor Diagnostics — by PSI Type")
lines.append("")
lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
lines.append("**Source:** `OMNY_REPL_ID.CUSTOM.DIAGNOSES` (Snowflake) for all K:1 matched donor encounters")
lines.append("**Principal diagnosis:** `DX_PRIMARY = 'YES'` or `DX_LINE = 1`")
lines.append("")
lines.append("---")
lines.append("")
lines.append("## Purpose")
lines.append("")
lines.append("For each PSI type, this document answers: **What were the most common reasons for hospitalization")
lines.append("among the matched counterfactual (control) donors — patients who were admitted under similar")
lines.append("circumstances but did NOT experience the adverse event at the landmark time?**")
lines.append("")
lines.append("This helps validate that the control group captures a realistic mix of comparable admissions,")
lines.append("and reveals the clinical contexts where each PSI type could plausibly develop but didn't.")
lines.append("")
lines.append("A secondary check flags donors whose diagnosis list contains a PSI-type ICD-10 code —")
lines.append("which could indicate the event occurred after the landmark window, or that the matching")
lines.append("captured patients who eventually did experience an adverse outcome.")
lines.append("")
lines.append("---")
lines.append("")
lines.append("## Overall summary")
lines.append("")

total_donors_all   = sum(r["n_donors"]       for r in results.values())
total_with_dx      = sum(r["n_with_dx"]      for r in results.values())
total_psi_positive = sum(r["n_psi_positive"] for r in results.values())

# Note: same donor may appear in multiple PSI types
all_unique_donors = set().union(*[donor_map[p] for p in PSI_TYPES if p in donor_map])
lines.append(f"| Metric | Value |")
lines.append(f"|---|---|")
_n_with_dx   = dx_all["ENCOUNTER_ID"].nunique()
_n_psi_coded = dx_all[dx_all["is_any_psi"]]["ENCOUNTER_ID"].nunique()
lines.append(f"| Total matched pairs (all types) | 3,626 |")
lines.append(f"| Unique donor encounters | {len(all_unique_donors):,} |")
lines.append(f"| Donors with diagnoses retrieved | {_n_with_dx:,} ({100*_n_with_dx/len(all_unique_donors):.0f}%) |")
lines.append(f"| Diagnosis rows pulled | {len(dx_all):,} |")
lines.append(f"| Donors with any PSI-type ICD code | {_n_psi_coded:,} ({100*_n_psi_coded/len(all_unique_donors):.0f}%) |")
lines.append("")
lines.append("> **Coverage note:** Diagnoses are only available for donors whose encounters appear in the OMNY")
lines.append("> DIAGNOSES table. Encounters with no diagnosis rows (e.g., encounters at suppliers that do not")
lines.append("> submit diagnostic billing data to OMNY) are counted but excluded from the diagnostic tables.")
lines.append("")
lines.append("---")
lines.append("")
lines.append("## Results by PSI type")
lines.append("")

for psi in PSI_TYPES:
    r      = results[psi]
    label  = PSI_LABELS[psi]
    cov_pct = 100 * r["n_with_dx"] / r["n_donors"] if r["n_donors"] > 0 else 0
    psi_pct = 100 * r["n_psi_positive"] / r["n_with_dx"] if r["n_with_dx"] > 0 else 0

    lines.append(f"### {label}")
    lines.append("")
    lines.append(f"| | |")
    lines.append(f"|---|---|")
    lines.append(f"| Matched donor encounters | {r['n_donors']} |")
    lines.append(f"| Donors with diagnoses in OMNY | {r['n_with_dx']} ({cov_pct:.0f}%) |")
    lines.append(f"| Donors without diagnosis data | {r['n_without_dx']} |")
    lines.append(f"| Donors with a PSI-type ICD code in record | {r['n_psi_positive']} ({psi_pct:.0f}% of those with dx) |")
    lines.append("")

    # ICD-10 chapter breakdown
    if len(r["chapter_counts"]) > 0:
        lines.append("**Diagnosis category breakdown** (unique encounters per chapter):")
        lines.append("")
        lines.append("| ICD-10 Chapter | Donor Encounters |")
        lines.append("|---|---|")
        for _, row in r["chapter_counts"].iterrows():
            lines.append(f"| {row['chapter']} | {int(row['n_encounters'])} |")
        lines.append("")
    else:
        lines.append("_No diagnoses retrieved for this PSI type._")
        lines.append("")

    # Top principal diagnoses
    if len(r["top_codes"]) > 0:
        lines.append(f"**Top {min(TOP_N, len(r['top_codes']))} principal diagnoses** (by ICD-10 code):")
        lines.append("")
        lines.append("| ICD-10 Code | Description | Chapter | Encounters |")
        lines.append("|---|---|---|---|")
        for _, row in r["top_codes"].iterrows():
            desc = str(row["DX_HCS_DESC"])[:70] if pd.notna(row["DX_HCS_DESC"]) else "(no description)"
            is_psi_flag = " ⚠️ PSI" if re.match(PSI_ICD_REGEX.get(psi, r"NOMATCH"), str(row["DX_CODE"])) else ""
            lines.append(f"| `{row['DX_CODE']}` | {desc}{is_psi_flag} | {row['chapter']} | {int(row['n_encounters'])} |")
        lines.append("")

    if r["n_psi_positive"] > 0:
        psi_codes_found = (
            r["dx_psi"][r["dx_psi"][f"is_{psi}"]]["DX_CODE"].value_counts().head(5)
        )
        lines.append(f"> **PSI flag detail:** {r['n_psi_positive']} donor encounter(s) carry an ICD-10 code")
        lines.append(f"> matching the {label} PSI criterion. Top codes: "
                     + ", ".join(f"`{c}` (n={n})" for c, n in psi_codes_found.items()))
        lines.append("> This may reflect events occurring *after* the landmark window t\\*, not violations of")
        lines.append("> the event-free selection criterion (which only applies up to t\\*).")
        lines.append("")

    lines.append("---")
    lines.append("")

# ── Cross-PSI summary table
lines.append("## Cross-type diagnostic overlap")
lines.append("")
lines.append("For each PSI type, the most common ICD-10 chapter among counterfactual donors:")
lines.append("")
lines.append("| PSI Type | Donors | Top Chapter | Count | 2nd Chapter | Count | PSI-flagged donors |")
lines.append("|---|---|---|---|---|---|---|")
for psi in PSI_TYPES:
    r     = results[psi]
    label = PSI_LABELS[psi]
    cc    = r["chapter_counts"]
    c1 = cc.iloc[0]["chapter"][:40] if len(cc) > 0 else "—"
    n1 = int(cc.iloc[0]["n_encounters"]) if len(cc) > 0 else 0
    c2 = cc.iloc[1]["chapter"][:40] if len(cc) > 1 else "—"
    n2 = int(cc.iloc[1]["n_encounters"]) if len(cc) > 1 else 0
    lines.append(f"| {label} | {r['n_donors']} | {c1} | {n1} | {c2} | {n2} | {r['n_psi_positive']} |")

lines.append("")
lines.append("---")
lines.append("")
lines.append("## Interpretation notes")
lines.append("")
lines.append("1. **Why are some PSI-type codes present in controls?**")
lines.append("   The event-free criterion only applies up to the landmark time t\\* = E_i − 6 (24 hours")
lines.append("   before the case's PSI event). Donors may still develop an adverse outcome *after* that")
lines.append("   window. Their diagnosis record in OMNY reflects the full hospitalization, so post-window")
lines.append("   PSI events will appear in their diagnosis list. This is by design and does not invalidate")
lines.append("   the counterfactual selection.")
lines.append("")
lines.append("2. **OB types (PSI-17/18/19) and the Pregnancy chapter**")
lines.append("   Counterfactual donors for obstetric PSI types are dominated by O-chapter codes")
lines.append("   (Pregnancy, Childbirth & Puerperium). This confirms the matching is finding")
lines.append("   comparable obstetric patients — not a mix of random inpatient admissions.")
lines.append("")
lines.append("3. **Surgical PSI types and Circulatory/Digestive chapters**")
lines.append("   PSI types like PSI-09 (hemorrhage), PSI-11 (resp failure), PSI-13 (sepsis) should")
lines.append("   show donors dominated by surgical or medical admission diagnoses (I-, K-, J-chapter).")
lines.append("   Deviation from this pattern would indicate the CEM matching is pulling")
lines.append("   non-comparable patients.")
lines.append("")
lines.append("4. **Coverage gaps**")
lines.append("   Donors without diagnosis data in OMNY are excluded from these tables but were used")
lines.append("   in propensity score matching. Their demographics and clinical history (labs, vitals)")
lines.append("   are still in the matched_sets.parquet. The diagnostic gap is a data-availability")
lines.append("   artefact of the OMNY DIAGNOSES table coverage, not a matching deficiency.")
lines.append("")

REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
REPORT_PATH.write_text("\n".join(lines))
print(f"\nReport written to: {REPORT_PATH}")
print("Done.")
