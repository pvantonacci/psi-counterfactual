"""
08_comorbidity_prevalence.py

Charlson and Elixhauser comorbidity prevalence analysis for the PSI cohort.

Inputs  : data/raw/psi_tables/{diagnoses,encounters,problem_lists}.csv
          results/tables/all_matched_pairs.csv
Outputs : results/reports/comorbidity_prevalence.md
          results/figures/cs_charlson_distribution.png
          results/figures/cs_elixhauser_heatmap.png
          results/figures/cs_charlson_by_psi_type.png

Pre-existing diagnosis classification (priority order):
  1. DX_CHRONIC == 'YES'                             → pre-existing
  2. DX_DATE < EN_START_DATE (by ≥ 1 day)            → pre-existing
  3. PL_CHRONIC == 'YES' + PL_NOTED_DATE < EN_START  → pre-existing
  4. DX_STATUS contains 'POA' or 'BEFORE'            → pre-existing
  Default                                            → encounter-driven

Run from project root:
    source '/home/pvam/projects/PROTEGE - HealthBenck/PSI/bin/activate'
    python src/08_comorbidity_prevalence.py
"""

from __future__ import annotations

import re
import sys
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

# ─── Paths ────────────────────────────────────────────────────────────────────
RAW_DIR     = Path("data/raw/psi_tables")
PAIRS_CSV   = Path("results/tables/all_matched_pairs.csv")
FIG_DIR     = Path("results/figures")
REPORT_PATH = Path("results/reports/comorbidity_prevalence.md")
FIG_DIR.mkdir(parents=True, exist_ok=True)
REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

# ─── Group colours (shared with 07) ───────────────────────────────────────────
CASE_COLOR = "#e05c4b"
BEST_COLOR = "#4b8ec8"
ALL_COLOR  = "#5aaa6e"
GROUP_ORDER = ["Case", "Best Match (rank 1)", "All Matches (rank 2+)"]


# ══════════════════════════════════════════════════════════════════════════════
# ICD-10 → Charlson category mapping  (Quan et al. 2005, ICD-10-CM prefixes)
# ══════════════════════════════════════════════════════════════════════════════

CHARLSON_MAP: dict[str, tuple[int, list[str]]] = {
    # (weight, [ICD-10-CM prefix list])
    "Myocardial infarction":              (1, ["I21", "I22"]),
    "Congestive heart failure":           (1, ["I09.9","I11.0","I13.0","I13.2","I25.5",
                                               "I42.0","I42.5","I42.6","I42.7","I42.8",
                                               "I42.9","I43","I50","P29.0"]),
    "Peripheral vascular disease":        (1, ["I70","I71","I73.1","I73.8","I73.9",
                                               "I77.1","I79.0","I79.2","K55.1","K55.8",
                                               "K55.9","Z95.8","Z95.9"]),
    "Cerebrovascular disease":            (1, ["G45","G46","H34.0","I60","I61","I62",
                                               "I63","I64","I65","I66","I67","I68","I69"]),
    "Dementia":                           (1, ["F00","F01","F02","F03","F05.1",
                                               "G30","G31.1"]),
    "Chronic pulmonary disease":          (1, ["J40","J41","J42","J43","J44","J45",
                                               "J46","J47","J60","J61","J62","J63",
                                               "J64","J65","J66","J67","J68.4",
                                               "J70.1","J70.3"]),
    "Rheumatic disease":                  (1, ["M05","M06","M09.0","M32","M34",
                                               "M35.1","M35.2","M35.3","M36.0"]),
    "Peptic ulcer disease":               (1, ["K25","K26","K27","K28"]),
    "Mild liver disease":                 (1, ["B18","K70.0","K70.1","K70.2","K70.3",
                                               "K70.9","K71.3","K71.4","K71.5","K71.7",
                                               "K73","K74","K76.0","K76.2","K76.3",
                                               "K76.4","K76.8","K76.9","Z94.4"]),
    "Diabetes (uncomplicated)":           (1, ["E10.0","E10.6","E10.8","E10.9",
                                               "E11.0","E11.6","E11.8","E11.9",
                                               "E12.0","E12.6","E12.9",
                                               "E13.0","E13.6","E13.8","E13.9",
                                               "E14.0","E14.6","E14.8","E14.9"]),
    "Diabetes (complicated)":             (2, ["E10.2","E10.3","E10.4","E10.5","E10.7",
                                               "E11.2","E11.3","E11.4","E11.5","E11.7",
                                               "E12.2","E12.3","E12.4","E12.5","E12.7",
                                               "E13.2","E13.3","E13.4","E13.5","E13.7",
                                               "E14.2","E14.3","E14.4","E14.5","E14.7"]),
    "Hemiplegia / paraplegia":            (2, ["G04.1","G11.4","G80.1","G80.2",
                                               "G81","G82","G83.0","G83.1","G83.2",
                                               "G83.3","G83.4","G83.9"]),
    "Renal disease":                      (2, ["I12.0","I13.1","N03.2","N03.3","N03.4",
                                               "N03.5","N03.6","N03.7",
                                               "N05.2","N05.3","N05.4","N05.5","N05.6",
                                               "N05.7","N18","N19","N25.0",
                                               "Z49.0","Z49.1","Z49.2","Z94.0","Z99.2"]),
    "Malignancy (no metastasis)":         (2, ["C00","C01","C02","C03","C04","C05",
                                               "C06","C07","C08","C09","C10","C11",
                                               "C12","C13","C14","C15","C16","C17",
                                               "C18","C19","C20","C21","C22","C23",
                                               "C24","C25","C26","C30","C31","C32",
                                               "C33","C34","C37","C38","C39","C40",
                                               "C41","C43","C45","C46","C47","C48",
                                               "C49","C50","C51","C52","C53","C54",
                                               "C55","C56","C57","C58","C60","C61",
                                               "C62","C63","C64","C65","C66","C67",
                                               "C68","C69","C70","C71","C72","C73",
                                               "C74","C75","C76","C81","C82","C83",
                                               "C84","C85","C88","C90","C91","C92",
                                               "C93","C94","C95","C96","C97"]),
    "Moderate/severe liver disease":      (3, ["I85.0","I85.9","I86.4","I98.2",
                                               "K70.4","K71.1","K72.1","K72.9",
                                               "K76.5","K76.6","K76.7"]),
    "Metastatic solid tumor":             (6, ["C77","C78","C79","C80"]),
    "AIDS/HIV":                           (6, ["B20","B21","B22","B24"]),
}

CHARLSON_NAMES = list(CHARLSON_MAP.keys())


# ══════════════════════════════════════════════════════════════════════════════
# ICD-10 → Elixhauser category mapping  (HCUP; 31 conditions; prefix matching)
# ══════════════════════════════════════════════════════════════════════════════

ELIXHAUSER_MAP: dict[str, list[str]] = {
    "Congestive heart failure":       ["I09.9","I11.0","I13.0","I13.2","I25.5",
                                       "I42.0","I42.5","I42.6","I42.7","I42.8","I42.9",
                                       "I43","I50","P29.0"],
    "Cardiac arrhythmias":            ["I44.1","I44.2","I44.3","I45.6","I45.9",
                                       "I47","I48","I49","R00.0","R00.1","R00.8","T82.1","Z45.0","Z95.0"],
    "Valvular disease":               ["A52.0","I05","I06","I07","I08","I09.1","I09.8",
                                       "I34","I35","I36","I37","I38","I39","Q23.0","Q23.1",
                                       "Q23.2","Q23.3","Z95.2","Z95.3","Z95.4"],
    "Pulmonary circulation disorders":["I26","I27","I28.0","I28.8","I28.9"],
    "Peripheral vascular disorders":  ["I70","I71","I73.1","I73.8","I73.9","I77.1",
                                       "I79.0","I79.2","K55.1","K55.8","K55.9",
                                       "Z95.8","Z95.9"],
    "Hypertension (uncomplicated)":   ["I10"],
    "Hypertension (complicated)":     ["I11","I12","I13","I15"],
    "Paralysis":                      ["G04.1","G11.4","G80.1","G80.2","G81","G82",
                                       "G83.0","G83.1","G83.2","G83.3","G83.4","G83.9"],
    "Other neurological disorders":   ["G10","G11","G12","G13","G20","G21","G22",
                                       "G25.4","G25.5","G31.2","G31.8","G31.9",
                                       "G32","G35","G36","G37","G40","G41",
                                       "G93.1","G93.4","R47.0","R56"],
    "Chronic pulmonary disease":      ["I27.8","I27.9","J40","J41","J42","J43","J44",
                                       "J45","J46","J47","J60","J61","J62","J63",
                                       "J64","J65","J66","J67","J68.0","J68.1",
                                       "J68.2","J68.3","J68.4","J70.1","J70.3"],
    "Diabetes (uncomplicated)":       ["E10.0","E10.6","E10.8","E10.9",
                                       "E11.0","E11.6","E11.8","E11.9",
                                       "E12.0","E12.6","E12.9",
                                       "E13.0","E13.6","E13.8","E13.9",
                                       "E14.0","E14.6","E14.8","E14.9"],
    "Diabetes (complicated)":         ["E10.2","E10.3","E10.4","E10.5","E10.7",
                                       "E11.2","E11.3","E11.4","E11.5","E11.7",
                                       "E12.2","E12.3","E12.4","E12.5","E12.7",
                                       "E13.2","E13.3","E13.4","E13.5","E13.7",
                                       "E14.2","E14.3","E14.4","E14.5","E14.7"],
    "Hypothyroidism":                 ["E00","E01","E02","E03","E89.0"],
    "Renal failure":                  ["I12.0","I13.1","N18","N19","N25.0",
                                       "Z49.0","Z49.1","Z49.2","Z94.0","Z99.2"],
    "Liver disease":                  ["B18","I85","I86.4","I98.2",
                                       "K70","K71.1","K71.3","K71.4","K71.5","K71.7",
                                       "K72","K73","K74","K76","Z94.4"],
    "Peptic ulcer disease":           ["K25","K26","K27","K28"],
    "AIDS/HIV":                       ["B20","B21","B22","B24"],
    "Lymphoma":                       ["C81","C82","C83","C84","C85","C88","C96","C90.0","C90.2"],
    "Metastatic cancer":              ["C77","C78","C79","C80"],
    "Solid tumor (no metastasis)":    ["C00","C01","C02","C03","C04","C05","C06","C07",
                                       "C08","C09","C10","C11","C12","C13","C14","C15",
                                       "C16","C17","C18","C19","C20","C21","C22","C23",
                                       "C24","C25","C26","C30","C31","C32","C33","C34",
                                       "C37","C38","C39","C40","C41","C43","C45","C46",
                                       "C47","C48","C49","C50","C51","C52","C53","C54",
                                       "C55","C56","C57","C58","C60","C61","C62","C63",
                                       "C64","C65","C66","C67","C68","C69","C70","C71",
                                       "C72","C73","C74","C75","C76"],
    "Rheumatoid arthritis/collagen":  ["L94.0","L94.1","L94.3","M05","M06","M08",
                                       "M09.0","M30","M31.0","M31.1","M31.2","M31.3",
                                       "M32","M33","M34","M35","M36.0","M45","M46.1","M46.8"],
    "Coagulopathy":                   ["D65","D66","D67","D68","D69.1","D69.3","D69.4",
                                       "D69.5","D69.6"],
    "Obesity":                        ["E66"],
    "Weight loss":                    ["E40","E41","E42","E43","E44","E45","E46","R63.4","R64"],
    "Fluid/electrolyte disorders":    ["E22.2","E86","E87"],
    "Blood loss anemia":              ["D50.0"],
    "Deficiency anemia":              ["D50.8","D50.9","D51","D52","D53"],
    "Alcohol abuse":                  ["F10","E52","G62.1","I42.6","K29.2","K70.0",
                                       "K70.3","K70.9","T51","Z50.2","Z71.4","Z72.1"],
    "Drug abuse":                     ["F11","F12","F13","F14","F15","F16","F18","F19",
                                       "Z71.5","Z72.2"],
    "Psychoses":                      ["F20","F22","F23","F24","F25","F28","F29",
                                       "F30.2","F31.2","F31.5"],
    "Depression":                     ["F20.4","F31.3","F31.4","F31.5","F32","F33",
                                       "F34.1","F41.2","F43.2"],
}

ELIXHAUSER_NAMES = list(ELIXHAUSER_MAP.keys())


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _icd_prefix_match(code: str, prefixes: list[str]) -> bool:
    """True if code starts with any prefix in the list (case-insensitive, dot-stripped)."""
    c = str(code).upper().replace(".", "").replace(" ", "")
    for p in prefixes:
        p2 = p.upper().replace(".", "").replace(" ", "")
        if c.startswith(p2):
            return True
    return False


def charlson_categories(codes: list[str]) -> dict[str, bool]:
    """Map a list of ICD-10 codes to a dict of Charlson category → present."""
    result = {}
    for cat, (_, prefixes) in CHARLSON_MAP.items():
        result[cat] = any(_icd_prefix_match(c, prefixes) for c in codes)
    return result


def charlson_score(codes: list[str]) -> int:
    """Compute Charlson Comorbidity Index score from a list of ICD-10 codes."""
    cats = charlson_categories(codes)
    # Hierarchy: if diabetes complicated, don't double-count uncomplicated
    if cats.get("Diabetes (complicated)", False):
        cats["Diabetes (uncomplicated)"] = False
    # If mod/severe liver, don't double-count mild liver
    if cats.get("Moderate/severe liver disease", False):
        cats["Mild liver disease"] = False
    # If metastatic, don't double-count non-metastatic malignancy
    if cats.get("Metastatic solid tumor", False):
        cats["Malignancy (no metastasis)"] = False
    score = 0
    for cat, present in cats.items():
        if present:
            score += CHARLSON_MAP[cat][0]
    return score


def elixhauser_categories(codes: list[str]) -> dict[str, bool]:
    """Map ICD-10 codes to Elixhauser condition flags."""
    result = {}
    for cat, prefixes in ELIXHAUSER_MAP.items():
        result[cat] = any(_icd_prefix_match(c, prefixes) for c in codes)
    return result


def classify_preexisting(
    dx_rows: pd.DataFrame,
    enc_start: pd.Timestamp,
    pl_rows: pd.DataFrame | None = None,
) -> pd.Series:
    """
    Return a boolean Series aligned with dx_rows indicating pre-existing diagnoses.

    Priority rules (first match wins):
      1. DX_CHRONIC == 'YES'
      2. DX_DATE < enc_start - 1 day
      3. cross-ref problem list: PL_CHRONIC=='YES' and PL_NOTED_DATE < enc_start - 30 days
      4. DX_STATUS contains 'POA' or 'BEFORE'
    """
    dx = dx_rows.copy()
    n = len(dx)
    flags = pd.Series([False] * n, index=dx.index)

    # Rule 1 — DX_CHRONIC
    if "DX_CHRONIC" in dx.columns:
        flags |= dx["DX_CHRONIC"].astype(str).str.upper() == "YES"

    # Rule 2 — DX_DATE before encounter start
    if "DX_DATE" in dx.columns and not pd.isna(enc_start):
        dx_dates = pd.to_datetime(dx["DX_DATE"], errors="coerce")
        cutoff = enc_start - pd.Timedelta(days=1)
        flags |= dx_dates < cutoff

    # Rule 4 — DX_STATUS POA / BEFORE ADMISSION
    if "DX_STATUS" in dx.columns:
        status_upper = dx["DX_STATUS"].fillna("").astype(str).str.upper()
        flags |= status_upper.str.contains("POA|BEFORE", regex=True, na=False)

    # Rule 3 — problem list cross-reference (codes present before admission)
    if pl_rows is not None and len(pl_rows) > 0 and "PL_CODE" in pl_rows.columns:
        pre_pl_cutoff = enc_start - pd.Timedelta(days=30)
        pl_dates = pd.to_datetime(pl_rows.get("PL_NOTED_DATE", pd.Series(dtype="object")),
                                  errors="coerce")
        pl_chronic = pl_rows.get("PL_CHRONIC", pd.Series(dtype="object"))
        pre_pl_codes = set(
            pl_rows[
                ((pl_chronic.astype(str).str.upper() == "YES") |
                 (pl_dates < pre_pl_cutoff))
            ]["PL_CODE"].dropna().astype(str).str.upper()
        )
        if "DX_CODE" in dx.columns and pre_pl_codes:
            dx_codes_upper = dx["DX_CODE"].fillna("").astype(str).str.upper()
            flags |= dx_codes_upper.isin(pre_pl_codes)

    return flags


# ══════════════════════════════════════════════════════════════════════════════
# Data loading
# ══════════════════════════════════════════════════════════════════════════════

def load_csv(name: str) -> pd.DataFrame:
    p = RAW_DIR / f"{name}.csv"
    if not p.exists():
        print(f"  WARNING: {p} not found — returning empty frame", flush=True)
        return pd.DataFrame()
    df = pd.read_csv(p, low_memory=False)
    print(f"  Loaded {name}: {len(df):,} rows", flush=True)
    return df


def load_data() -> tuple[pd.DataFrame, ...]:
    print("Loading raw tables …", flush=True)
    enc = load_csv("encounters")
    dx  = load_csv("diagnoses")
    pl  = load_csv("problem_lists")
    pairs = pd.read_csv(PAIRS_CSV) if PAIRS_CSV.exists() else pd.DataFrame()
    print(f"  Matched pairs: {len(pairs)} rows\n", flush=True)
    return enc, dx, pl, pairs


# ══════════════════════════════════════════════════════════════════════════════
# Group assignment
# ══════════════════════════════════════════════════════════════════════════════

def assign_groups(
    enc: pd.DataFrame, pairs: pd.DataFrame
) -> dict[str, str]:
    """Return enc_id → group label dict (priority: Case > Best Match > All Matches)."""
    role: dict[str, str] = {}
    if len(pairs) > 0:
        all_donors = pairs[pairs["match_rank"] >= 2]["donor_enc"].dropna().unique()
        r1_donors  = pairs[pairs["match_rank"] == 1]["donor_enc"].dropna().unique()
        case_encs  = pairs["case_enc"].dropna().unique()
        for e in all_donors: role[str(e)] = "All Matches (rank 2+)"
        for e in r1_donors:  role[str(e)] = "Best Match (rank 1)"
        for e in case_encs:  role[str(e)] = "Case"
    return role


# ══════════════════════════════════════════════════════════════════════════════
# Comorbidity computation
# ══════════════════════════════════════════════════════════════════════════════

def compute_comorbidities(
    enc: pd.DataFrame,
    dx: pd.DataFrame,
    pl: pd.DataFrame,
    role: dict[str, str],
) -> pd.DataFrame:
    """
    For each encounter in `role`, classify pre-existing diagnoses, then
    compute Charlson score, Elixhauser flags, and category presence.
    Returns one row per encounter with group, charlson_score, elixhauser_n,
    and individual category flags.
    """
    print("Computing comorbidities …", flush=True)

    # Ensure ENCOUNTER_ID is string in all tables
    for df in (enc, dx, pl):
        if "ENCOUNTER_ID" in df.columns:
            df["ENCOUNTER_ID"] = df["ENCOUNTER_ID"].astype(str)

    # Build lookup structures
    enc_start_map: dict[str, pd.Timestamp] = {}
    if "ENCOUNTER_ID" in enc.columns and "EN_START_DATE" in enc.columns:
        for _, row in enc.iterrows():
            ts = pd.to_datetime(
                str(row.get("EN_START_DATE", "")) + " " +
                str(row.get("EN_START_TIME", "00:00:00")),
                errors="coerce"
            )
            enc_start_map[str(row["ENCOUNTER_ID"])] = ts

    dx_by_enc: dict[str, pd.DataFrame] = {}
    if "ENCOUNTER_ID" in dx.columns:
        for eid, grp in dx.groupby("ENCOUNTER_ID"):
            dx_by_enc[str(eid)] = grp

    # For pl, group by OMNY_ID; we need to map enc → OMNY_ID
    omny_map: dict[str, str] = {}
    if "ENCOUNTER_ID" in enc.columns and "OMNY_ID" in enc.columns:
        for _, row in enc.iterrows():
            omny_map[str(row["ENCOUNTER_ID"])] = str(row.get("OMNY_ID", ""))

    pl_by_omny: dict[str, pd.DataFrame] = {}
    if "OMNY_ID" in pl.columns:
        for omny, grp in pl.groupby("OMNY_ID"):
            pl_by_omny[str(omny)] = grp

    records = []
    all_enc_ids = list(role.keys())

    for enc_id in all_enc_ids:
        group = role[enc_id]
        enc_start = enc_start_map.get(enc_id, pd.NaT)
        dx_enc = dx_by_enc.get(enc_id, pd.DataFrame())
        omny_id = omny_map.get(enc_id, "")
        pl_enc = pl_by_omny.get(omny_id, pd.DataFrame()) if omny_id else pd.DataFrame()

        # Classify diagnoses
        if len(dx_enc) > 0:
            preexisting = classify_preexisting(dx_enc, enc_start, pl_enc)
            pre_dx_rows = dx_enc[preexisting]
            codes_pre = pre_dx_rows["DX_CODE"].dropna().astype(str).str.upper().tolist() \
                        if "DX_CODE" in pre_dx_rows.columns else []
        else:
            codes_pre = []

        # Charlson
        c_cats = charlson_categories(codes_pre)
        # Apply Charlson hierarchies
        if c_cats.get("Diabetes (complicated)", False):
            c_cats["Diabetes (uncomplicated)"] = False
        if c_cats.get("Moderate/severe liver disease", False):
            c_cats["Mild liver disease"] = False
        if c_cats.get("Metastatic solid tumor", False):
            c_cats["Malignancy (no metastasis)"] = False
        cs = sum(CHARLSON_MAP[cat][0] for cat, present in c_cats.items() if present)

        # Elixhauser
        e_cats = elixhauser_categories(codes_pre)
        eli_n = sum(e_cats.values())

        # Merge everything into one record
        row: dict = {
            "ENCOUNTER_ID":   enc_id,
            "group":          group,
            "charlson_score": cs,
            "elixhauser_n":   eli_n,
            "n_preexisting_dx": len(codes_pre),
        }
        for cat, present in c_cats.items():
            row[f"cs_{cat}"] = int(present)
        for cat, present in e_cats.items():
            row[f"eli_{cat}"] = int(present)
        records.append(row)

    result = pd.DataFrame(records)
    print(f"  Computed comorbidities for {len(result)} encounters", flush=True)
    return result


# ══════════════════════════════════════════════════════════════════════════════
# PSI type join
# ══════════════════════════════════════════════════════════════════════════════

def add_psi_type(df: pd.DataFrame, pairs: pd.DataFrame) -> pd.DataFrame:
    """Add PSI_TYPE column (from matched pairs case_enc → psi_type mapping)."""
    if len(pairs) == 0 or "psi_type" not in pairs.columns:
        df["PSI_TYPE"] = "UNKNOWN"
        return df
    psi_map: dict[str, str] = dict(zip(
        pairs["case_enc"].astype(str),
        pairs["psi_type"].astype(str)
    ))
    # donors: look up via donor_enc → case_enc → psi_type (use first rank match)
    donor_psi_map: dict[str, str] = {}
    for _, row in pairs.drop_duplicates("donor_enc").iterrows():
        donor_psi_map[str(row["donor_enc"])] = str(row["psi_type"])

    def lookup(enc_id: str) -> str:
        return psi_map.get(enc_id, donor_psi_map.get(enc_id, "UNKNOWN"))

    df["PSI_TYPE"] = df["ENCOUNTER_ID"].apply(lookup)
    return df


# ══════════════════════════════════════════════════════════════════════════════
# Figures
# ══════════════════════════════════════════════════════════════════════════════

GROUP_COLOR_MAP = {
    "Case":                 CASE_COLOR,
    "Best Match (rank 1)": BEST_COLOR,
    "All Matches (rank 2+)": ALL_COLOR,
}


def fig_charlson_distribution(comob: pd.DataFrame) -> None:
    """Stacked bar of Charlson score distribution by group."""
    groups_present = [g for g in GROUP_ORDER if g in comob["group"].values]
    max_score = min(int(comob["charlson_score"].max()) + 1, 20)
    bins = list(range(0, max_score + 1))

    fig, axes = plt.subplots(1, len(groups_present), figsize=(5 * len(groups_present), 4),
                              sharey=False, squeeze=False)
    for ax, grp in zip(axes[0], groups_present):
        subset = comob[comob["group"] == grp]["charlson_score"]
        counts = subset.value_counts().reindex(bins, fill_value=0)
        ax.bar(counts.index, counts.values, color=GROUP_COLOR_MAP[grp],
               edgecolor="white", linewidth=0.5)
        ax.set_title(grp, fontsize=10, color=GROUP_COLOR_MAP[grp])
        ax.set_xlabel("Charlson Score")
        ax.set_ylabel("Encounters")
        med = subset.median()
        ax.axvline(med, color="black", linestyle="--", linewidth=1, label=f"Median={med:.1f}")
        ax.legend(fontsize=8)

    fig.suptitle("Charlson Comorbidity Index Distribution by Group", fontsize=12)
    fig.tight_layout()
    out = FIG_DIR / "cs_charlson_distribution.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved {out}", flush=True)


def fig_elixhauser_heatmap(comob: pd.DataFrame) -> None:
    """Heatmap of Elixhauser condition prevalence (%) by group."""
    groups_present = [g for g in GROUP_ORDER if g in comob["group"].values]
    eli_cols = [c for c in comob.columns if c.startswith("eli_")]
    if not eli_cols:
        print("  WARNING: no Elixhauser columns found; skipping heatmap", flush=True)
        return

    condition_labels = [c[4:] for c in eli_cols]   # strip "eli_"

    matrix = []
    for grp in groups_present:
        subset = comob[comob["group"] == grp]
        if len(subset) == 0:
            matrix.append([0.0] * len(eli_cols))
            continue
        matrix.append([100.0 * subset[c].mean() for c in eli_cols])
    mat_arr = np.array(matrix)  # shape (n_groups, n_conditions)

    # Sort conditions by prevalence across all groups
    sort_idx = np.argsort(-mat_arr.mean(axis=0))
    mat_arr = mat_arr[:, sort_idx]
    sorted_labels = [condition_labels[i] for i in sort_idx]

    fig, ax = plt.subplots(figsize=(max(14, len(sorted_labels) * 0.45), 3 + len(groups_present)))
    im = ax.imshow(mat_arr, aspect="auto", cmap="YlOrRd", vmin=0, vmax=mat_arr.max() or 1)
    plt.colorbar(im, ax=ax, label="Prevalence (%)")
    ax.set_xticks(range(len(sorted_labels)))
    ax.set_xticklabels(sorted_labels, rotation=60, ha="right", fontsize=8)
    ax.set_yticks(range(len(groups_present)))
    ax.set_yticklabels(groups_present, fontsize=10)
    for i, grp in enumerate(groups_present):
        for j in range(len(sorted_labels)):
            ax.text(j, i, f"{mat_arr[i,j]:.1f}", ha="center", va="center",
                    fontsize=6, color="black" if mat_arr[i,j] < mat_arr.max() * 0.6 else "white")
    ax.set_title("Elixhauser Condition Prevalence (%) — Pre-existing Diagnoses", fontsize=12)
    fig.tight_layout()
    out = FIG_DIR / "cs_elixhauser_heatmap.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved {out}", flush=True)


def fig_charlson_by_psi_type(comob: pd.DataFrame) -> None:
    """Box/strip plot of Charlson score by PSI type (cases only)."""
    cases_only = comob[comob["group"] == "Case"].copy()
    if len(cases_only) == 0:
        print("  WARNING: no Case group data for PSI-type plot", flush=True)
        return

    psi_types = sorted(cases_only["PSI_TYPE"].dropna().unique())
    if not psi_types:
        print("  WARNING: no PSI_TYPE column in comorbidity frame", flush=True)
        return

    # Short labels
    def short_label(t: str) -> str:
        return t.replace("PSI_", "PSI-").replace("_", " ").replace("PSI- ", "")

    fig, ax = plt.subplots(figsize=(max(10, len(psi_types) * 0.8), 5))
    data_by_type = [cases_only[cases_only["PSI_TYPE"] == t]["charlson_score"].values
                    for t in psi_types]
    bp = ax.boxplot(data_by_type, patch_artist=True, notch=False,
                    showfliers=True, flierprops=dict(marker="o", markersize=3, alpha=0.5))
    for patch in bp["boxes"]:
        patch.set_facecolor(CASE_COLOR)
        patch.set_alpha(0.7)
    ax.set_xticks(range(1, len(psi_types) + 1))
    ax.set_xticklabels([short_label(t) for t in psi_types],
                       rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("Charlson Score")
    ax.set_title("Charlson Score by PSI Type (Cases only)", fontsize=12)
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    fig.tight_layout()
    out = FIG_DIR / "cs_charlson_by_psi_type.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved {out}", flush=True)


# ══════════════════════════════════════════════════════════════════════════════
# Report
# ══════════════════════════════════════════════════════════════════════════════

def build_report(comob: pd.DataFrame) -> str:
    lines: list[str] = []
    a = lines.append

    a("# Comorbidity Prevalence Analysis")
    a("")
    a("**Date:** 2026-06-07  ")
    a("**Cohort:** PSI cases (106), Best Match rank-1 donors (91), All Matches rank 2+ donors (2695)  ")
    a("**Index:** Charlson Comorbidity Index (Quan et al. 2005) and Elixhauser Comorbidity Index (HCUP)  ")
    a("**Source diagnoses:** pre-existing only (classified by DX_CHRONIC, temporal date comparison,")
    a("problem list cross-reference, and DX_STATUS POA flag)  ")
    a("")
    a("---")
    a("")
    a("## Charlson Score Distribution")
    a("")
    a("![](../figures/cs_charlson_distribution.png)")
    a("")
    a("Charlson Comorbidity Index computed from pre-existing ICD-10 diagnoses per encounter.")
    a("Score uses Quan et al. (2005) ICD-10 coding algorithm with standard weights and hierarchical")
    a("deduplication (e.g., complicated diabetes suppresses uncomplicated diabetes).")
    a("")

    groups_present = [g for g in GROUP_ORDER if g in comob["group"].values]

    # Summary table
    a("### Summary Statistics")
    a("")
    a("| Group | N | Median Charlson | Mean Charlson | % Score = 0 | % Score ≥ 3 |")
    a("|---|--:|--:|--:|--:|--:|")
    for grp in groups_present:
        subset = comob[comob["group"] == grp]["charlson_score"]
        if len(subset) == 0:
            continue
        pct0   = 100 * (subset == 0).mean()
        pct3p  = 100 * (subset >= 3).mean()
        a(f"| {grp} | {len(subset)} | {subset.median():.1f} | {subset.mean():.2f} "
          f"| {pct0:.1f}% | {pct3p:.1f}% |")
    a("")

    a("---")
    a("")
    a("## Charlson Score by PSI Type (Cases)")
    a("")
    a("![](../figures/cs_charlson_by_psi_type.png)")
    a("")
    a("Charlson scores for the 106 cases, faceted by PSI type. OB-related types")
    a("(PSI_17/18/19) are expected to have lower scores. Surgical/medical types")
    a("(e.g., PSI_04, PSI_07, PSI_13) should show higher baseline comorbidity.")
    a("")

    # Per-type table
    cases_df = comob[comob["group"] == "Case"]
    if len(cases_df) > 0 and "PSI_TYPE" in cases_df.columns:
        a("| PSI Type | N cases | Median Charlson | % Score = 0 | % Score ≥ 3 |")
        a("|---|--:|--:|--:|--:|")
        for pt in sorted(cases_df["PSI_TYPE"].dropna().unique()):
            subset = cases_df[cases_df["PSI_TYPE"] == pt]["charlson_score"]
            pct0  = 100 * (subset == 0).mean()
            pct3p = 100 * (subset >= 3).mean()
            a(f"| {pt} | {len(subset)} | {subset.median():.1f} | {pct0:.1f}% | {pct3p:.1f}% |")
        a("")

    a("---")
    a("")
    a("## Elixhauser Condition Prevalence")
    a("")
    a("![](../figures/cs_elixhauser_heatmap.png)")
    a("")
    a("Prevalence (%) of each of the 31 Elixhauser conditions across groups,")
    a("computed from pre-existing diagnoses. Conditions sorted by mean prevalence (descending).")
    a("")

    # Top-10 Elixhauser conditions
    eli_cols = [c for c in comob.columns if c.startswith("eli_")]
    if eli_cols and len(cases_df) > 0:
        prevalences = {c[4:]: 100 * cases_df[c].mean() for c in eli_cols}
        top10 = sorted(prevalences.items(), key=lambda x: -x[1])[:10]
        a("### Top 10 Elixhauser Conditions (Cases)")
        a("")
        a("| Condition | Prevalence (%) |")
        a("|---|--:|")
        for cond, prev in top10:
            a(f"| {cond} | {prev:.1f}% |")
        a("")

    a("---")
    a("")
    a("## Top Charlson Categories (Cases)")
    a("")
    cs_cols = [c for c in comob.columns if c.startswith("cs_")]
    if cs_cols and len(cases_df) > 0:
        cs_prev = {c[3:]: 100 * cases_df[c].mean() for c in cs_cols}
        cs_sorted = sorted(cs_prev.items(), key=lambda x: -x[1])
        a("| Category | Weight | Prevalence in Cases (%) |")
        a("|---|--:|--:|")
        for cond, prev in cs_sorted:
            if prev > 0:
                weight = CHARLSON_MAP.get(cond, (0,))[0] if cond in CHARLSON_MAP else "—"
                a(f"| {cond} | {weight} | {prev:.1f}% |")
        a("")

    a("---")
    a("")
    a("## Methodology Notes")
    a("")
    a("### Pre-existing Diagnosis Classification")
    a("")
    a("A diagnosis is classified as **pre-existing** (present before the encounter) if any of")
    a("the following rules is satisfied (evaluated in priority order, first match wins):")
    a("")
    a("1. **DX_CHRONIC = 'YES'** — the EHR explicitly flags the diagnosis as a chronic condition")
    a("2. **DX_DATE < EN_START_DATE − 1 day** — diagnosis date is before the encounter admission date")
    a("3. **Problem list cross-reference** — the code appears on the patient's problem list")
    a("   (PL_CHRONIC='YES' or PL_NOTED_DATE < EN_START_DATE − 30 days)")
    a("4. **DX_STATUS contains 'POA' or 'BEFORE'** — ICD Present-on-Admission flag")
    a("")
    a("All other diagnoses are classified as **encounter-driven** (potentially caused by or")
    a("arising during the encounter).")
    a("")
    a("### Charlson Score Computation")
    a("")
    a("ICD-10-CM codes are mapped to 17 Charlson categories using prefix matching per")
    a("Quan et al. (2005). Standard hierarchical deduplication is applied: complicated")
    a("diabetes suppresses uncomplicated diabetes; moderate/severe liver disease suppresses")
    a("mild liver disease; metastatic solid tumor suppresses non-metastatic malignancy.")
    a("Category weights: most = 1, hemiplegia/paraplegia/renal/diabetes-complicated/malignancy = 2,")
    a("moderate liver = 3, metastatic tumor/AIDS = 6.")
    a("")
    a("### Elixhauser Comorbidity Index")
    a("")
    a("31 binary condition flags per the HCUP Elixhauser Comorbidity Software using ICD-10-CM")
    a("prefix matching. The summary metric reported here is the count of present conditions;")
    a("individual condition flags are available in the analysis output for multivariate adjustment.")

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    enc, dx, pl, pairs = load_data()

    if enc.empty or dx.empty:
        print("ERROR: encounters or diagnoses table missing — cannot proceed.")
        sys.exit(1)

    role = assign_groups(enc, pairs)
    if not role:
        # Fallback: treat all encounters as Case
        print("  WARNING: no matched pairs found — treating all encounters as Case")
        enc_ids = enc["ENCOUNTER_ID"].astype(str).unique() if "ENCOUNTER_ID" in enc.columns else []
        role = {str(e): "Case" for e in enc_ids}

    print(f"\nGroup sizes: " +
          " | ".join(f"{g}={sum(1 for v in role.values() if v==g)}"
                     for g in GROUP_ORDER) + "\n")

    comob = compute_comorbidities(enc, dx, pl, role)
    comob = add_psi_type(comob, pairs)

    print("\nGenerating figures …", flush=True)
    fig_charlson_distribution(comob)
    fig_elixhauser_heatmap(comob)
    fig_charlson_by_psi_type(comob)

    print("\nWriting report …", flush=True)
    report = build_report(comob)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"  Saved {REPORT_PATH}", flush=True)

    # Save raw scores for downstream use
    score_out = Path("results/tables/comorbidity_scores.csv")
    score_cols = ["ENCOUNTER_ID", "group", "PSI_TYPE",
                  "charlson_score", "elixhauser_n", "n_preexisting_dx"]
    comob[score_cols].to_csv(score_out, index=False)
    print(f"  Saved {score_out}", flush=True)

    print("\nDone.", flush=True)


if __name__ == "__main__":
    main()
