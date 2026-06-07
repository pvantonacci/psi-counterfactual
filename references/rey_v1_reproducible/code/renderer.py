"""
Renderer — Project Bayes Inpatient EHR Benchmark.

Converts filtered OMNY CSV tables into clinician-readable text prompts for the
model under test. Handles within-note truncation (mask sections) and time-based
truncation (filter all rows to <= cutoff_ts) per prompt requirements.

See TRUNCATION.md and RENDERER_DESIGN.md for design rationale.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd


# Default to bundle-relative ../data/tables (sibling of code/ in this handoff).
# Override with the --tables-dir flag when invoking run_eval_parallel.py.
TABLES_DIR = (Path(__file__).resolve().parent.parent / "data" / "tables")
CACHE_DIR = TABLES_DIR.parent / "cache"


# ---------------------------------------------------------------------------
# Specs
# ---------------------------------------------------------------------------


@dataclass
class TruncationSpec:
    """Defines what content to keep / mask for a given prompt."""
    cutoff_ts: Optional[datetime] = None
    # Section masks operate on note text. Substring match, case-insensitive.
    section_mask: list[str] = field(default_factory=list)
    # Keep-only is the inverse: drop all sections except these.
    section_keep_only: list[str] = field(default_factory=list)
    # Specific NOTE_IDs / lab rows to exclude as ground truth.
    exclude_note_ids: list[str] = field(default_factory=list)
    exclude_lab_specimen_dates: list[str] = field(default_factory=list)
    # For P3: take only the admission H&P, no time filter.
    keep_only_note_type: Optional[str] = None


@dataclass
class AblationSpec:
    drop: list[str] = field(default_factory=list)
    keep_only: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Encounter data loader
# ---------------------------------------------------------------------------


class EncounterDataLoader:
    """Loads the encounter-scoped slices of OMNY tables.

    Lazily caches per-encounter dataframes so repeated render() calls on the
    same case don't re-read the CSVs.

    Args:
        tables_dir: directory containing the OMNY CSVs (encounters.csv, notes.csv, etc.)
        cases_csv: optional path to a custom case-list CSV (must contain OMNY_ID + ENCOUNTER_ID).
                   If None, falls back to <tables_dir>/eval_cases.csv.
        cache_dir: optional parquet cache directory. If None, defaults to <tables_dir>.parent/cache.
                   Set to a non-existent path (or any path) — the loader checks per file.
    """

    def __init__(
        self,
        tables_dir: Path = TABLES_DIR,
        cases_csv: Optional[Path] = None,
        cache_dir: Optional[Path] = None,
    ):
        self.tables_dir = Path(tables_dir)
        self.cases_csv = Path(cases_csv) if cases_csv else self.tables_dir / "eval_cases.csv"
        self.cache_dir = Path(cache_dir) if cache_dir else (self.tables_dir.parent / "cache")
        self._cache: dict[str, dict[str, pd.DataFrame]] = {}
        self._cases: Optional[pd.DataFrame] = None

    @property
    def cases(self) -> pd.DataFrame:
        if self._cases is None:
            self._cases = pd.read_csv(self.cases_csv)
        return self._cases

    def get_case(self, encounter_id: str) -> pd.Series:
        df = self.cases
        row = df[df["ENCOUNTER_ID"] == encounter_id]
        if row.empty:
            raise KeyError(f"Encounter {encounter_id} not found in eval_cases.csv")
        return row.iloc[0]

    def load(self, encounter_id: str) -> dict[str, pd.DataFrame]:
        if encounter_id in self._cache:
            return self._cache[encounter_id]

        case = self.get_case(encounter_id)
        omny_id = case["OMNY_ID"]

        # Prefer parquet cache if present (built by code/build_cache.py).
        table_specs = [
            ("encounters.csv", "encounters"),
            ("diagnoses.csv", "diagnoses"),
            ("vitals.csv", "vitals"),
            ("labs.csv", "labs"),
            ("procedures.csv", "procedures"),
            ("prescription_orders.csv", "meds"),
            ("omny_notes_concatenated.csv", "notes"),
            ("prescription_administrations.csv", "admins"),
        ]
        slices: dict[str, pd.DataFrame] = {}
        for fname, table_key in table_specs:
            cache_path = self.cache_dir / f"{encounter_id}_{table_key}.parquet"
            if cache_path.exists():
                slices[table_key] = pd.read_parquet(cache_path)
            else:
                csv_path = self.tables_dir / fname
                if csv_path.exists():
                    slices[table_key] = _load_filtered(csv_path, encounter_id, omny_id)
                else:
                    slices[table_key] = pd.DataFrame()

        self._cache[encounter_id] = slices
        return slices


def _load_filtered(path: Path, encounter_id: str, omny_id: str) -> pd.DataFrame:
    """Read a CSV in chunks and return only rows matching this encounter."""
    chunks: list[pd.DataFrame] = []
    for chunk in pd.read_csv(path, chunksize=200_000, low_memory=False):
        mask = (chunk["ENCOUNTER_ID"] == encounter_id) & (chunk["OMNY_ID"] == omny_id)
        if mask.any():
            chunks.append(chunk[mask].copy())
    if not chunks:
        return pd.DataFrame()
    return pd.concat(chunks, ignore_index=True)


# ---------------------------------------------------------------------------
# Timestamp utilities
# ---------------------------------------------------------------------------


def _combine_date_time(df: pd.DataFrame, date_col: str, time_col: str) -> pd.Series:
    """Combine a DATE and TIME column into a single datetime Series."""
    if df.empty:
        return pd.Series([], dtype="datetime64[ns]")
    date = pd.to_datetime(df[date_col], errors="coerce")
    time = df[time_col].fillna("00:00:00").astype(str) if time_col in df.columns else "00:00:00"
    if isinstance(time, pd.Series):
        time = time.str.replace(r"^(\d{2}):(\d{2})$", r"\1:\2:00", regex=True)
        combined = pd.to_datetime(
            date.dt.strftime("%Y-%m-%d") + " " + time, errors="coerce"
        )
    else:
        combined = date
    return combined


# ---------------------------------------------------------------------------
# Section parsing for notes
# ---------------------------------------------------------------------------


# OMNY encodes sections in NOTE_TYPE as "<NOTE_KIND> - <SECTION_LABEL>".
# These section keyword groups identify which rows belong to each canonical section.
# Patterns use \b word boundaries so substring noise like "NSHPLAN..." doesn't
# match PLAN. OMNY also uses "REASON FOR ADMISSION" in lieu of "CHIEF COMPLAINT".
SECTION_PATTERNS = {
    "CC": [r"\bCHIEF COMPLAINT\b", r"\bREASON FOR ADMISSION\b"],
    "HPI": [r"\bHPI\b", r"\bHISTORY OF PRESENT ILLNESS\b", r"\bPRESENT ILLNESS\b"],
    "PE": [r"\bPHYSICAL EXAM\b", r"NSHPPHYSICALEXAM", r"^EXAM\b", r"\b- EXAM\b"],
    "ROS": [r"\bREVIEW OF SYSTEMS\b", r"\bROS\b"],
    "LABS": [r"\bLAB(?:S|ORATORY|RESULTS)\b", r"NSHPLABSRESULTS"],
    "IMAGING": [r"\bIMAGING\b", r"\bRADIOLOGY\b"],
    "ASSESSMENT": [r"\bASSESSMENT\b"],
    "PLAN": [r"(?<![A-Z])PLAN(?![A-Z])", r"\bCARE PLAN\b", r"\bTREATMENT PLAN\b"],
    "AP": [r"\bASSESSMENT AND PLAN\b", r"\bA&P\b", r"\bA/P\b"],
    "SUBJECTIVE": [r"\bSUBJECTIVE\b"],
    "OBJECTIVE": [r"\bOBJECTIVE\b"],
    "SUBJ_OBJ": [r"\bSUBJECTIVE AND OBJECTIVE\b"],
}


def _classify_section(note_type: str) -> set[str]:
    """Return the set of canonical section labels that a NOTE_TYPE belongs to."""
    if not isinstance(note_type, str):
        return set()
    upper = note_type.upper()
    # Take the part after the last " - " if present (the section label, not note kind)
    section_part = upper.split(" - ", 1)[1] if " - " in upper else upper
    labels: set[str] = set()
    for canonical, patterns in SECTION_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, section_part):
                labels.add(canonical)
                break
    return labels


def _normalize_section_filter(filter_list: list[str]) -> set[str]:
    """Expand user-provided section labels to all relevant canonical sections."""
    normalized: set[str] = set()
    for raw in filter_list:
        u = raw.upper().strip()
        if u in ("A&P", "AP", "ASSESSMENT AND PLAN", "ASSESSMENT & PLAN"):
            normalized.update({"AP", "ASSESSMENT", "PLAN"})
        elif u in ("A",):
            normalized.update({"ASSESSMENT", "AP"})
        elif u in ("P",):
            normalized.update({"PLAN", "AP"})
        else:
            normalized.add(u)
    return normalized


def _filter_note_rows_by_section(
    df: pd.DataFrame,
    section_mask: list[str],
    section_keep_only: list[str],
) -> pd.DataFrame:
    """Drop or keep note rows based on the section encoded in NOTE_TYPE."""
    if not section_mask and not section_keep_only:
        return df
    if df.empty:
        return df
    classified = df["NOTE_TYPE"].apply(_classify_section)
    if section_keep_only:
        keep_set = _normalize_section_filter(section_keep_only)
        mask = classified.apply(lambda labels: bool(labels & keep_set))
    else:
        drop_set = _normalize_section_filter(section_mask)
        mask = classified.apply(lambda labels: not (labels & drop_set))
    return df[mask].copy()


# ---------------------------------------------------------------------------
# Narrative-form A&P leakage redaction
# ---------------------------------------------------------------------------

# OMNY notes are typically one long run-on paragraph (no real newlines),
# so patterns must be position-tolerant rather than line-anchored.
# Catches narrative plan markers: "Impression - ...", "Plan: ...", "A/P ...",
# numbered plan items, bullet plan items.
NARRATIVE_PLAN_PATTERNS = [
    # "Impression - <stuff>" or "Imp: <stuff>" (until next double-space or end)
    re.compile(r"(?i)(?:^|(?<=\s))(?:impression|imp\.?|assessment|a/p|a\s*&\s*p|plan)\s*[-:]\s*[^\n]{1,400}?(?=\s{2,}|\n|$)"),
    # Standalone "P  <plan-verb>" or numbered plan items like "1) admit"
    re.compile(r"(?i)(?:^|(?<=\s{2}))P\s+(?:admit|start|continue|consult|will|plan|begin|initiate|hold|d/c).{1,400}?(?=\s{2,}|\n|$)"),
    re.compile(r"(?i)(?:^|(?<=\s))\d+[\.)]\s*(?:admit|start|continue|consult|will|plan to|begin|initiate|d/c|hold)[^\n]{1,400}?(?=\s{2,}|\n|$)"),
    # "Disposition - admit", "Disposition: home"
    re.compile(r"(?i)(?:^|(?<=\s))disposition\s*[-:]\s*[^\n]{1,200}?(?=\s{2,}|\n|$)"),
    # Standalone plan verbs at start of a double-space-delimited segment.
    # E.g., "  Continue IVAbx - ID guidance appreciated  Podiatry to perform ..."
    re.compile(
        r"(?i)(?:^|(?<=\s{2}))"
        r"(?:continue|start|stop|hold|initiate|discontinue|d/c|begin|consult|admit\s+to)\s+"
        r"[^\n]{1,300}?(?=\s{2,}|\n|$)"
    ),
]


def _redact_narrative_plan(text: str) -> str:
    """Replace spans that look like narrative-form A&P with a redaction marker.

    Applied to non-A&P-labeled sections when within-note A&P masking is active
    (e.g., the ATTENDING COMMENTS section frequently mirrors the A&P).
    """
    if not isinstance(text, str):
        return text
    redacted = text
    for pattern in NARRATIVE_PLAN_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


# ---------------------------------------------------------------------------
# Section renderers (per data type)
# ---------------------------------------------------------------------------


def _render_encounter_header(case: pd.Series, encounters: pd.DataFrame) -> str:
    enc = encounters.iloc[0] if not encounters.empty else {}
    return (
        "=== Encounter ===\n"
        f"Hospital: {case['INSTITUTION_NAME']}\n"
        f"Admission: {enc.get('EN_START_DATE', case['EN_START_DATE'])}\n"
        f"Discharge: {enc.get('EN_END_DATE', 'N/A')}\n"
        f"LOS: {case['LOS_DAYS']} days\n"
        f"Patient: {int(case['AGE_INT'])}yo {case.get('GENDER', 'UNKNOWN')}, {case.get('RACE', 'UNKNOWN')}\n"
    )


def _render_notes(
    notes: pd.DataFrame,
    truncation: TruncationSpec,
    admit_ts: Optional[datetime] = None,
) -> str:
    if notes.empty:
        return ""

    df = notes.copy()
    df["TS"] = pd.to_datetime(df["NOTE_DATE"], errors="coerce")

    # BUG FIX: filter out notes with sentinel/placeholder dates that fall before
    # the actual admission. These otherwise leak into time-truncated prompts.
    if admit_ts is not None:
        df = df[df["TS"] >= admit_ts - timedelta(days=1)]

    if truncation.cutoff_ts is not None:
        df = df[df["TS"] <= truncation.cutoff_ts]
        # Per Allison: when time-truncation is active, also exclude any
        # discharge-type notes regardless of their timestamp. OMNY's date-
        # shift / placeholder dates make timestamp-based filtering insufficient
        # for discharge notes specifically — they often have sentinel dates
        # that fall pre-admission and slip past the cutoff.
        # Broadened regex: catches DISCHARGE SUMMARY / DISCHARGE INSTRUCTIONS /
        # DISCHARGE PLANNING in addition to DISCHARGE NOTE. Earlier version
        # leaked discharge summaries in ~7.6% of P7 cases.
        discharge_pattern = r"\bDISCHARGE\b|DEATH NOTE|EXPIRED PATIENT|DECEASED|DISPOSITION"
        df = df[~df["NOTE_TYPE"].fillna("").str.upper().str.contains(discharge_pattern, regex=True)]
        # Belt-and-suspenders sentinel-date filter: drop notes timestamped at
        # exactly midnight on Jan 1 (a common placeholder pattern in OMNY).
        sentinel_mask = (
            df["TS"].dt.month.eq(1) &
            df["TS"].dt.day.eq(1) &
            df["TS"].dt.hour.eq(0) &
            df["TS"].dt.minute.eq(0) &
            df["TS"].dt.second.eq(0)
        )
        df = df[~sentinel_mask]
    if truncation.exclude_note_ids:
        df = df[~df["NOTE_ID"].isin(truncation.exclude_note_ids)]
    if truncation.keep_only_note_type:
        target = truncation.keep_only_note_type.lower()
        df = df[df["NOTE_TYPE"].fillna("").str.lower().str.contains(target)]

    # Apply section-level filtering (OMNY stores sections in NOTE_TYPE).
    df = _filter_note_rows_by_section(
        df, truncation.section_mask, truncation.section_keep_only
    )

    # BUG FIX: dedupe rows that repeat the same content across data suppliers.
    # Same (NOTE_ID, NOTE_TYPE, NOTE_TEXT) can appear 3-5x. Keep first only.
    df = df.drop_duplicates(subset=["NOTE_ID", "NOTE_TYPE", "NOTE_TEXT"])

    # BUG FIX: also dedupe duplicate paragraphs WITHIN each NOTE_TEXT cell.
    # OMNY sometimes concatenates the same content 3-5x inside a single cell.
    def _dedupe_text(text):
        if not isinstance(text, str):
            return text
        seen = set()
        out = []
        for line in text.split("\n"):
            key = line.strip()
            if not key or key not in seen:
                seen.add(key)
                out.append(line)
        return "\n".join(out)
    df = df.copy()
    df["NOTE_TEXT"] = df["NOTE_TEXT"].apply(_dedupe_text)

    df = df.sort_values(["TS", "NOTE_ID"])

    if df.empty:
        return ""

    # Apply narrative-plan redaction in remaining sections when A&P is being masked.
    apply_redaction = bool(truncation.section_mask) and bool(
        _normalize_section_filter(truncation.section_mask) & {"ASSESSMENT", "PLAN", "AP"}
    )

    # Group rows by NOTE_ID — each NOTE_ID is one logical clinical document.
    blocks: list[str] = []
    for note_id, group in df.groupby("NOTE_ID", sort=False):
        group = group.sort_values("NOTE_TYPE")
        ts = group["TS"].iloc[0]
        ts_str = ts.strftime("%Y-%m-%d %H:%M") if pd.notna(ts) else "unknown"

        # Derive the note kind (the prefix before " - " in NOTE_TYPE).
        first_type = str(group["NOTE_TYPE"].iloc[0])
        note_kind = first_type.split(" - ", 1)[0] if " - " in first_type else first_type

        section_lines: list[str] = []
        for _, row in group.iterrows():
            ntype = str(row.get("NOTE_TYPE", ""))
            section_label = ntype.split(" - ", 1)[1] if " - " in ntype else ntype
            text = row.get("NOTE_TEXT", "")
            if not isinstance(text, str) or not text.strip():
                continue
            if apply_redaction:
                text = _redact_narrative_plan(text)
            section_lines.append(f"  [{section_label}] {text.strip()}")
        if not section_lines:
            continue
        blocks.append(f"--- {note_kind} — {ts_str} ---\n" + "\n".join(section_lines) + "\n")
    if not blocks:
        return ""
    return "=== Notes ===\n\n" + "\n".join(blocks)


def _render_labs(labs: pd.DataFrame, truncation: TruncationSpec) -> str:
    if labs.empty:
        return ""
    df = labs.copy()
    df["TS"] = _combine_date_time(df, "LB_SPECIMEN_DATE", "LB_SPECIMEN_TIME")
    if truncation.cutoff_ts is not None:
        df = df[df["TS"] <= truncation.cutoff_ts]
    if truncation.exclude_lab_specimen_dates:
        df = df[~df["LB_SPECIMEN_DATE"].isin(truncation.exclude_lab_specimen_dates)]
    if df.empty:
        return ""
    # Dedupe identical lab measurements from multi-supplier ingestion
    df = df.drop_duplicates(subset=["TS", "LB_SHORT_NAME", "LB_RESULT_VALUE"])
    df = df.sort_values("TS")
    rows = ["| Time | Test | Value | Units | Ref Low | Ref High | Flag |",
            "|------|------|-------|-------|---------|----------|------|"]
    # Compact: drop duplicate (test, value, time) rows if any
    for _, row in df.iterrows():
        ts = row["TS"].strftime("%Y-%m-%d %H:%M") if pd.notna(row["TS"]) else ""
        rows.append(
            f"| {ts} | {row.get('LB_SHORT_NAME', '')} | "
            f"{row.get('LB_RESULT_VALUE', '')} | {row.get('LB_REF_UNIT', '')} | "
            f"{row.get('LB_REF_LOW', '')} | {row.get('LB_REF_HIGH', '')} | "
            f"{row.get('LB_ABN_RESULT', '')} |"
        )
    return "=== Labs ===\n" + "\n".join(rows)


def _render_vitals(vitals: pd.DataFrame, truncation: TruncationSpec) -> str:
    if vitals.empty:
        return ""
    df = vitals.copy()
    df["TS"] = _combine_date_time(df, "VS_DATE", "VS_TIME")
    if truncation.cutoff_ts is not None:
        df = df[df["TS"] <= truncation.cutoff_ts]
    if df.empty:
        return ""
    df = df.drop_duplicates(subset=["TS", "VS_DESC", "VS_VALUE"])
    df = df.sort_values("TS")
    rows = ["| Time | Vital | Value | Units |", "|------|-------|-------|-------|"]
    for _, row in df.iterrows():
        ts = row["TS"].strftime("%Y-%m-%d %H:%M") if pd.notna(row["TS"]) else ""
        rows.append(
            f"| {ts} | {row.get('VS_DESC', '')} | "
            f"{row.get('VS_VALUE', '')} | {row.get('VS_UNIT', '')} |"
        )
    return "=== Vitals ===\n" + "\n".join(rows)


def _render_meds(meds: pd.DataFrame, truncation: TruncationSpec) -> str:
    if meds.empty:
        return ""
    df = meds.copy()
    df["TS"] = _combine_date_time(df, "RX_ORDER_DATE", "RX_ORDER_TIME")
    if truncation.cutoff_ts is not None:
        df = df[df["TS"] <= truncation.cutoff_ts]
    if df.empty:
        return ""
    df = df.drop_duplicates(subset=["TS", "RX_GENERIC_NAME", "RX_DOSE", "RX_FREQ"])
    df = df.sort_values("TS")
    lines: list[str] = []
    for _, row in df.iterrows():
        ts = row["TS"].strftime("%Y-%m-%d %H:%M") if pd.notna(row["TS"]) else ""
        name = row.get("RX_GENERIC_NAME") or row.get("RX_BRAND_NAME") or ""
        dose = row.get("RX_DOSE", "")
        unit = row.get("RX_UNIT", "")
        route = row.get("RX_ROUTE", "")
        freq = row.get("RX_FREQ", "")
        lines.append(f"- {ts}  {name} {dose}{unit} {route} {freq}".strip())
    return "=== Medication Orders ===\n" + "\n".join(lines)


def _render_diagnoses(diagnoses: pd.DataFrame, truncation: TruncationSpec) -> str:
    if diagnoses.empty:
        return ""
    df = diagnoses.copy()
    if "DX_DATE" in df.columns:
        df["TS"] = pd.to_datetime(df["DX_DATE"], errors="coerce")
        if truncation.cutoff_ts is not None:
            df = df[df["TS"] <= truncation.cutoff_ts]
    df = df.drop_duplicates(subset=["DX_CODE"])
    if df.empty:
        return ""
    lines: list[str] = []
    for _, row in df.iterrows():
        primary = " (primary)" if str(row.get("DX_PRIMARY", "")).upper() in ("Y", "YES", "1", "TRUE") else ""
        lines.append(f"- {row.get('DX_CODE', '')}  {row.get('DX_HCS_DESC', '')}{primary}")
    return "=== Diagnoses (ICD-10) ===\n" + "\n".join(lines)


# ---------------------------------------------------------------------------
# Main render entry point
# ---------------------------------------------------------------------------


def render(
    encounter_id: str,
    prompt_id: str,
    loader: Optional[EncounterDataLoader] = None,
    truncation: Optional[TruncationSpec] = None,
    ablation: Optional[AblationSpec] = None,
) -> str:
    """Render the input context for one (case, prompt) combination.

    `prompt_id` controls section composition (e.g., S1 returns only one note;
    P10 returns full record). `truncation` overrides default behavior.
    """
    loader = loader or EncounterDataLoader()
    truncation = truncation or _default_truncation_for(prompt_id, encounter_id, loader)
    ablation = ablation or AblationSpec()

    case = loader.get_case(encounter_id)
    data = loader.load(encounter_id)

    drop = set(ablation.drop)
    keep_only = set(ablation.keep_only)

    # BUG FIX: P3 / P4 predict discharge Dx — the diagnoses table contains
    # the discharge Dx itself. Auto-drop diagnoses unless caller explicitly
    # asks to keep it.
    if prompt_id in ("P3", "P4") and "dx_codes" not in keep_only:
        drop.add("dx_codes")

    def include(table_key: str) -> bool:
        if keep_only:
            return table_key in keep_only
        return table_key not in drop

    blocks: list[str] = [_render_encounter_header(case, data["encounters"])]

    if include("notes"):
        admit_ts = pd.to_datetime(case["EN_START_DATE"], errors="coerce")
        block = _render_notes(data["notes"], truncation, admit_ts=admit_ts)
        if block:
            blocks.append(block)
    if include("dx_codes"):
        block = _render_diagnoses(data["diagnoses"], truncation)
        if block:
            blocks.append(block)
    if include("labs"):
        block = _render_labs(data["labs"], truncation)
        if block:
            blocks.append(block)
    if include("vitals"):
        block = _render_vitals(data["vitals"], truncation)
        if block:
            blocks.append(block)
    if include("meds"):
        block = _render_meds(data["meds"], truncation)
        if block:
            blocks.append(block)

    return "\n\n".join(blocks)


def _default_truncation_for(
    prompt_id: str, encounter_id: str, loader: EncounterDataLoader
) -> TruncationSpec:
    """Return the default truncation spec for a given prompt.

    Most prompts have a fixed default; prompts that anchor on patient-specific
    events (P5/P6/P7/P8, AE1/AE2/AE3) use the loader to identify the anchor.
    """
    if prompt_id in ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9", "S10"):
        return TruncationSpec()
    if prompt_id in ("C1", "C5", "C6", "C7", "C8"):
        return TruncationSpec()
    if prompt_id == "C2":
        return TruncationSpec(section_keep_only=["CC", "HPI"])
    if prompt_id in ("C3", "C4"):
        return TruncationSpec()
    if prompt_id == "P1":
        return TruncationSpec(
            keep_only_note_type="h&p adult",
            section_mask=["A&P", "ASSESSMENT", "PLAN", "AP"],
        )
    if prompt_id == "P2":
        return TruncationSpec(
            keep_only_note_type="progress note adult",
            section_mask=["A", "P", "ASSESSMENT", "PLAN", "AP"],
        )
    if prompt_id == "P3":
        return TruncationSpec(keep_only_note_type="h&p adult")
    if prompt_id == "P10":
        case = loader.get_case(encounter_id)
        start = pd.to_datetime(case["EN_START_DATE"])
        mid = start + timedelta(days=max(2, int(case["LOS_DAYS"]) // 2))
        return TruncationSpec(cutoff_ts=mid)
    # P4, P5-P8, AE1-3 need encounter-specific cutoffs the caller should provide.
    return TruncationSpec()


def cutoff_for_day(encounter_id: str, day: int, loader: EncounterDataLoader) -> datetime:
    """Helper: compute the end-of-day-N cutoff for an encounter (used by P4)."""
    case = loader.get_case(encounter_id)
    start = pd.to_datetime(case["EN_START_DATE"])
    return start + timedelta(days=day, hours=23, minutes=59, seconds=59)


def _select_p7_target_specimen(
    encounter_id: str,
    loader: EncounterDataLoader,
    min_panel_size: int = 10,
    skip_hours: int = 6,
) -> Optional[tuple[datetime, pd.DataFrame]]:
    """Pick the first post-admission lab draw whose panel has >= min_panel_size labs.

    Returns (specimen_ts, panel_rows_df) or None if no qualifying panel exists.
    Per Allison: skip thin draws like single-lab fingerstick glucose — we want
    a real venipuncture panel.
    """
    case = loader.get_case(encounter_id)
    data = loader.load(encounter_id)
    labs = data["labs"]
    if labs.empty:
        return None
    labs = labs.copy()
    labs["TS"] = _combine_date_time(labs, "LB_SPECIMEN_DATE", "LB_SPECIMEN_TIME")
    labs = labs.dropna(subset=["TS"]).sort_values("TS")
    admit_ts = pd.to_datetime(case["EN_START_DATE"])
    after = labs[labs["TS"] >= admit_ts + timedelta(hours=skip_hours)]
    if after.empty:
        return None
    # Group by specimen timestamp, find the first with enough labs
    grouped = after.groupby("TS")
    for ts, panel in grouped:
        if len(panel) >= min_panel_size:
            return (ts, panel)
    return None


def render_p7(
    encounter_id: str,
    loader: EncounterDataLoader,
    min_panel_size: int = 10,
) -> tuple[str, Optional[datetime]]:
    """Render the P7 context with a hard cutoff at the target specimen timestamp.

    Per Allison: the cutoff must apply to ALL context types (notes, diagnoses,
    labs, vitals, med orders). Otherwise lab values drawn later in the
    encounter can leak into the input. Returns (rendered_text, cutoff_ts).
    """
    target = _select_p7_target_specimen(encounter_id, loader, min_panel_size=min_panel_size)
    if target is None:
        return "", None
    specimen_ts, _ = target
    # Cutoff = specimen_ts - 1 second to ensure the target panel itself is NOT
    # included in the rendered context (renderer uses <= comparison; we want
    # strict "before the draw").
    cutoff_ts = specimen_ts - timedelta(seconds=1)
    truncation = TruncationSpec(cutoff_ts=cutoff_ts)
    rendered = render(encounter_id, "P7", loader=loader, truncation=truncation)
    return rendered, specimen_ts


# ---------------------------------------------------------------------------
# Lightweight self-check
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Single-note selection and ground-truth extraction
# ---------------------------------------------------------------------------


_NOTE_KIND_FALLBACKS = {
    # Comprehensive admission documents in order of preference. Long-stay or
    # transferred patients may have no H&P at all — fall back to earliest
    # progress note as the closest comprehensive document available.
    # Includes both long-form OMNY note kinds ("H&P ADULT", "PROGRESS NOTE ADULT")
    # and short-form codes used in some pulled datasets ("HP", "PN", "ED", "DS").
    "h&p adult": [
        "h&p adult",
        "h&p pediatric",
        "h & p adult",
        "h&p nicu",
        "h&p",
        "admission h&p",
        "admission note",
        "ed provider note",
        "consult note adult",
        "progress note adult",
        "progress note peds",
        "progress notes",
        "progress note",
        # Short codes used in some OMNY pulls (e.g. Allison's PSI dataset)
        "hp",
        "ed",
        "pn",
        "ds",
    ],
    "progress note adult": [
        "progress note adult",
        "progress note peds",
        "progress notes",
        "progress note",
        "pn",
    ],
}


def select_target_note(
    encounter_id: str,
    note_kind: str,
    loader: EncounterDataLoader,
) -> Optional[str]:
    """Return the NOTE_ID of the earliest note matching `note_kind`, or None.

    Tries fallback patterns if the primary pattern doesn't match (e.g.,
    pediatric encounters use "H&P PEDIATRIC" not "H&P ADULT").

    Pattern matching:
      - Short patterns (≤ 4 chars, e.g. "hp", "pn", "ed") use exact match on
        the NOTE_TYPE prefix (before any " - " section separator). This avoids
        false positives like "hp" matching "happen" or "PHP".
      - Long patterns (≥ 5 chars) use case-insensitive substring match.
    """
    data = loader.load(encounter_id)
    notes = data["notes"]
    if notes.empty:
        return None
    patterns = _NOTE_KIND_FALLBACKS.get(note_kind.lower(), [note_kind.lower()])
    types_raw = notes["NOTE_TYPE"].fillna("")
    types_lower = types_raw.str.lower()
    # For exact-match: the prefix before " - " (if present), lowercased
    types_prefix = types_lower.str.split(" - ").str[0].str.strip()

    for pattern in patterns:
        if len(pattern) <= 4:
            # Exact match on the NOTE_TYPE prefix
            mask = types_prefix == pattern
        else:
            # Substring match
            mask = types_lower.str.contains(pattern, regex=False)
        matching = notes[mask]
        if matching.empty:
            continue
        matching = matching.copy()
        matching["TS"] = pd.to_datetime(matching["NOTE_DATE"], errors="coerce")
        matching = matching.sort_values("TS")
        return matching.iloc[0]["NOTE_ID"]
    return None


def render_single_note(
    encounter_id: str,
    note_id: str,
    loader: EncounterDataLoader,
    truncation: Optional[TruncationSpec] = None,
) -> str:
    """Render a single note (all its sections) as readable text."""
    data = loader.load(encounter_id)
    notes = data["notes"]
    note_rows = notes[notes["NOTE_ID"] == note_id].copy()
    if note_rows.empty:
        return ""
    truncation = truncation or TruncationSpec()
    note_rows = _filter_note_rows_by_section(
        note_rows, truncation.section_mask, truncation.section_keep_only
    )
    # BUG FIX: dedupe identical section rows from multi-supplier ingestion.
    note_rows = note_rows.drop_duplicates(subset=["NOTE_ID", "NOTE_TYPE", "NOTE_TEXT"])
    # Also dedupe duplicate lines within each NOTE_TEXT cell.
    def _dedupe_text(text):
        if not isinstance(text, str):
            return text
        seen, out = set(), []
        for line in text.split("\n"):
            key = line.strip()
            if not key or key not in seen:
                seen.add(key)
                out.append(line)
        return "\n".join(out)
    note_rows = note_rows.copy()
    note_rows["NOTE_TEXT"] = note_rows["NOTE_TEXT"].apply(_dedupe_text)
    if note_rows.empty:
        return ""
    note_rows["TS"] = pd.to_datetime(note_rows["NOTE_DATE"], errors="coerce")
    note_rows = note_rows.sort_values("NOTE_TYPE")
    first_type = str(note_rows["NOTE_TYPE"].iloc[0])
    note_kind = first_type.split(" - ", 1)[0] if " - " in first_type else first_type
    ts = note_rows["TS"].iloc[0]
    ts_str = ts.strftime("%Y-%m-%d %H:%M") if pd.notna(ts) else "unknown"
    apply_redaction = bool(truncation.section_mask) and bool(
        _normalize_section_filter(truncation.section_mask) & {"ASSESSMENT", "PLAN", "AP"}
    )
    section_lines: list[str] = []
    for _, row in note_rows.iterrows():
        ntype = str(row.get("NOTE_TYPE", ""))
        section_label = ntype.split(" - ", 1)[1] if " - " in ntype else ntype
        text = row.get("NOTE_TEXT", "")
        if not isinstance(text, str) or not text.strip():
            continue
        if apply_redaction:
            text = _redact_narrative_plan(text)
        section_lines.append(f"  [{section_label}] {text.strip()}")
    if not section_lines:
        return ""
    return f"--- {note_kind} — {ts_str} ---\n" + "\n".join(section_lines)


def _extract_hpi_cc_sentence(hpi_text: str) -> str:
    """Extract the chief-complaint-like sentence from HPI text.

    OMNY's H&P notes often have templated preambles (Trauma Service header,
    Mechanism of Injury checkboxes, etc.) before the actual HPI narrative.
    We look for the "HPI:" marker first, then for a sentence containing
    presentation language ("presents", "complains", "admitted") or an
    age+sex pattern that signals the start of the actual story.
    """
    if not hpi_text:
        return ""
    # Strip leading [SECTION] label
    text = re.sub(r"^\[[^\]]+\]\s*", "", hpi_text.strip())
    # If there's an explicit "HPI:" marker, take what follows (most notes have this)
    m = re.search(r"\bHPI\s*:\s*(.+)", text, re.DOTALL | re.IGNORECASE)
    if m:
        text = m.group(1).strip()
    # Split into candidate sentences
    sentences = re.split(r"\.\s+|\?\s+|\n\s*\n", text)
    # Look for first sentence with CC-like signal
    for s in sentences[:8]:
        s = s.strip()
        if not s or len(s) < 8:
            continue
        if re.search(r"\b(presents?|presenting|complains?|admitted with|admit\w* for|brought in|BIBEMS|brought by EMS|s/p)\b", s, re.IGNORECASE):
            return s[:300]
        # Age+sex pattern: "33M", "55y/o female", "70-year-old male", etc.
        if re.match(r"^\s*\d{1,3}\s*(?:[ymdwo]+|-?year-?old|M|F|male|female)\b", s, re.IGNORECASE):
            return s[:300]
    # Fallback: first non-trivial sentence
    for s in sentences:
        s = s.strip()
        if s and len(s) > 20:
            return s[:300]
    return ""


# Text-based section header patterns (used as fallback when NOTE_TYPE has no
# section sub-label, e.g., PSI dataset stores whole notes per row).
# Order matters: more specific patterns first.
_TEXT_SECTION_HEADERS = {
    # Canonical section -> list of header regex variants (case-insensitive)
    "CC": [
        r"\bChief\s+Complaint\b\s*[:\-]?",
        r"\bCC\s*:",
        r"\bReason\s+for\s+Admission\b\s*[:\-]?",
        r"\bPresenting\s+Complaint\b\s*[:\-]?",
    ],
    "HPI": [
        r"\bHistory\s+of\s+Present\s+Illness\b\s*[:\-]?",
        r"\bHPI\b\s*[:\-]?",
        r"\bSubjective\b\s*[:\-]",
        r"@SUBJNOHEADERBEGIN@",
    ],
    "AP": [
        r"\bAssessment\s+and\s+Plan\b\s*[:\-]?",
        r"\bAssessment\s*&\s*Plan\b\s*[:\-]?",
        r"\bAssessment\s*/\s*Plan\b\s*[:\-]?",
        r"\bA\s*&\s*P\b\s*[:\-]?",
        r"\bA/P\b\s*[:\-]?",
        r"\bImpression\s*and\s+Plan\b\s*[:\-]?",
    ],
    "ASSESSMENT": [
        r"\bAssessment\b\s*[:\-]",
        r"\bImpression\b\s*[:\-]",
    ],
    "PLAN": [
        r"\bPlan\b\s*[:\-]",
        r"\bDisposition\b\s*[:\-]",
    ],
}

# Generic end-of-section markers — any of these signals the next section starts.
# Built once at module load time.
_END_OF_SECTION_PATTERNS = [
    r"\bChief\s+Complaint\b\s*[:\-]?",
    r"\bCC\s*:",
    r"\bReason\s+for\s+Admission\b\s*[:\-]?",
    r"\bPresenting\s+Complaint\b\s*[:\-]?",
    r"\bHistory\s+of\s+Present\s+Illness\b\s*[:\-]?",
    r"\bHPI\b\s*[:\-]?",
    r"\bSubjective\b\s*[:\-]",
    r"@SUBJNOHEADERBEGIN@",
    r"\bPast\s+Medical\s+History\b\s*[:\-]?",
    r"\bPMH\b\s*[:\-]?",
    r"\bPast\s+Surgical\s+History\b\s*[:\-]?",
    r"\bPSH\b\s*[:\-]?",
    r"\bFamily\s+History\b\s*[:\-]?",
    r"\bSocial\s+History\b\s*[:\-]?",
    r"\bAllergies\b\s*[:\-]?",
    r"\bMedications\b\s*[:\-]?",
    r"\bMeds\b\s*[:\-]?",
    r"\bReview\s+of\s+Systems\b\s*[:\-]?",
    r"\bROS\b\s*[:\-]?",
    r"\bPhysical\s+Exam(?:ination)?\b\s*[:\-]?",
    r"\bObjective\b\s*[:\-]?",
    r"\bAssessment\s+and\s+Plan\b\s*[:\-]?",
    r"\bAssessment\b\s*[:\-]?",
    r"\bImpression\b\s*[:\-]?",
    r"\bPlan\b\s*[:\-]?",
    r"\bDisposition\b\s*[:\-]?",
    r"\bDischarge\b\s*[:\-]?",
    r"\bElectronically\s+signed\b",
]
_END_OF_SECTION_RE = re.compile("|".join(_END_OF_SECTION_PATTERNS), re.IGNORECASE)


def _extract_section_from_text(note_text: str, section: str) -> str:
    """Parse a target section out of a single NOTE_TEXT blob using text-based
    section headers. Returns the text between the section header and the next
    section header (or end of note)."""
    if not isinstance(note_text, str) or not note_text.strip():
        return ""

    # Map the requested section to one or more canonical labels
    canonical_targets = _normalize_section_filter([section])
    # Pick header patterns that map to any of the requested canonical labels
    target_patterns = []
    for canonical, patterns in _TEXT_SECTION_HEADERS.items():
        if canonical in canonical_targets:
            target_patterns.extend(patterns)
    if not target_patterns:
        return ""

    target_re = re.compile("|".join(target_patterns), re.IGNORECASE)
    target_match = target_re.search(note_text)
    if not target_match:
        return ""

    # Find the start (just after the matched header) and the end (next section header).
    start = target_match.end()
    rest = note_text[start:]
    # Find the next ANY section header after `start`
    next_match = _END_OF_SECTION_RE.search(rest)
    end_local = next_match.start() if next_match else len(rest)
    chunk = rest[:end_local].strip()
    return chunk


def extract_section_text(
    encounter_id: str,
    note_id: str,
    section: str,
    loader: EncounterDataLoader,
) -> str:
    """Return concatenated text of all rows in `note_id` belonging to `section`.

    Dedupes identical (NOTE_TYPE, NOTE_TEXT) rows (OMNY multi-supplier ingestion)
    and also dedupes identical text within a single row's NOTE_TEXT field
    (sometimes the same paragraph is concatenated 3-5x).

    NOTE_TYPE-based path: when NOTE_TYPE contains a section sub-label (e.g.,
    "H&P ADULT - ASSESSMENT"), the matching rows are returned. Used when OMNY
    sends sections as separate rows.

    Text-parse fallback: when no row matches the section via NOTE_TYPE (e.g.,
    PSI dataset stores whole-note rows with sections embedded in NOTE_TEXT),
    parse the section out of the NOTE_TEXT directly using header regexes.
    """
    data = loader.load(encounter_id)
    notes = data["notes"]
    note_rows = notes[notes["NOTE_ID"] == note_id].copy()
    if note_rows.empty:
        return ""

    # === Primary path: NOTE_TYPE-based row filtering ===
    keep = _filter_note_rows_by_section(note_rows, [], [section])
    if not keep.empty:
        # Dedupe at the row level (multi-supplier repeats)
        keep = keep.drop_duplicates(subset=["NOTE_TYPE", "NOTE_TEXT"])
        parts: list[str] = []
        seen_text: set[str] = set()
        for _, r in keep.iterrows():
            text = r.get("NOTE_TEXT")
            if not isinstance(text, str) or not text.strip():
                continue
            deduped_lines: list[str] = []
            for line in text.split("\n"):
                ls = line.strip()
                if ls and ls not in seen_text:
                    seen_text.add(ls)
                    deduped_lines.append(line)
            deduped = "\n".join(deduped_lines).strip()
            if deduped:
                label = str(r["NOTE_TYPE"]).split(" - ", 1)[-1]
                parts.append(f"[{label}] {deduped}")
        if parts:
            return "\n".join(parts)

    # === Fallback: parse the section out of each row's NOTE_TEXT ===
    # Dedupe rows first (multi-supplier repeats produce the same NOTE_TEXT)
    deduped_rows = note_rows.drop_duplicates(subset=["NOTE_TYPE", "NOTE_TEXT"])
    text_parts: list[str] = []
    seen: set[str] = set()
    for _, r in deduped_rows.iterrows():
        text = r.get("NOTE_TEXT")
        if not isinstance(text, str) or not text.strip():
            continue
        chunk = _extract_section_from_text(text, section)
        if chunk and chunk not in seen:
            seen.add(chunk)
            text_parts.append(chunk)
    return "\n".join(text_parts)


def extract_ground_truth(
    encounter_id: str,
    prompt_id: str,
    loader: EncounterDataLoader,
    target_note_id: Optional[str] = None,
) -> dict:
    """Extract ground truth for a specific (case, prompt) combination.

    Returns a dict with at least: {"label": <string>, "metadata": {...}}.
    """
    case = loader.get_case(encounter_id)
    data = loader.load(encounter_id)

    if prompt_id == "S1":
        # Chief complaint — extract from BOTH "Reason for Admission" and HPI first
        # CC-like sentence. OMNY's REASON FOR ADMISSION field is unreliable: it often
        # contains admission orders ("serial abdominal exams") or process items
        # rather than the actual chief complaint. The real CC is usually in the
        # HPI's opening sentence (e.g., "33M presents following motorcycle crash").
        if target_note_id is None:
            target_note_id = select_target_note(encounter_id, "h&p adult", loader)
        cc_section = extract_section_text(encounter_id, target_note_id or "", "CC", loader)
        hpi = extract_section_text(encounter_id, target_note_id or "", "HPI", loader)
        hpi_cc = _extract_hpi_cc_sentence(hpi)
        parts = []
        if hpi_cc:
            parts.append(f"[HPI primary presenting sentence] {hpi_cc}")
        if cc_section.strip():
            parts.append(cc_section.strip())
        gt = "\n".join(parts)
        return {"label": gt, "metadata": {"note_id": target_note_id, "section": "CC",
                                          "sources": ["HPI" if hpi_cc else None,
                                                      "REASON_FOR_ADMISSION" if cc_section else None]}}

    if prompt_id == "S5":
        # A&P from admission H&P
        if target_note_id is None:
            target_note_id = select_target_note(encounter_id, "h&p adult", loader)
        gt = extract_section_text(encounter_id, target_note_id or "", "AP", loader)
        if not gt:
            gt = extract_section_text(encounter_id, target_note_id or "", "ASSESSMENT", loader)
        return {"label": gt, "metadata": {"note_id": target_note_id, "section": "AP"}}

    if prompt_id == "C1":
        # A&P summary — target note's A&P content
        if target_note_id is None:
            target_note_id = select_target_note(encounter_id, "h&p adult", loader)
        gt = extract_section_text(encounter_id, target_note_id or "", "AP", loader)
        if not gt:
            gt = extract_section_text(encounter_id, target_note_id or "", "ASSESSMENT", loader)
        return {"label": gt, "metadata": {"note_id": target_note_id}}

    if prompt_id in ("P3", "P4"):
        # Primary discharge diagnosis
        dx = data["diagnoses"]
        if dx.empty:
            return {"label": "", "metadata": {}}
        primary = dx[dx["DX_PRIMARY"].astype(str).str.upper().isin(["Y", "YES", "1", "TRUE"])]
        if primary.empty:
            primary = dx
        row = primary.iloc[0]
        return {
            "label": f"{row['DX_CODE']} — {row['DX_HCS_DESC']}",
            "metadata": {"code": row["DX_CODE"], "desc": row["DX_HCS_DESC"]},
        }

    if prompt_id == "P7":
        # Per Allison's feedback: pick first post-admission lab draw with >= 10 labs at
        # the same timestamp (a real venipuncture panel, not a fingerstick).
        target = _select_p7_target_specimen(encounter_id, loader, min_panel_size=10)
        if target is None:
            return {"label": "", "metadata": {"note": "no qualifying lab panel found"}}
        target_ts, target_panel = target
        rows = [
            f"{r['LB_SHORT_NAME']}: {r['LB_RESULT_VALUE']} {r['LB_REF_UNIT']} (ref {r['LB_REF_LOW']}-{r['LB_REF_HIGH']})"
            for _, r in target_panel.iterrows()
        ]
        return {
            "label": "\n".join(rows),
            "metadata": {
                "specimen_ts": target_ts.isoformat() if pd.notna(target_ts) else None,
                "n_values": len(rows),
                "panel_threshold": 10,
            },
        }

    if prompt_id == "P1":
        # A&P of the admission H&P (same content as C1, different prompt framing)
        if target_note_id is None:
            target_note_id = select_target_note(encounter_id, "h&p adult", loader)
        gt = extract_section_text(encounter_id, target_note_id or "", "AP", loader)
        if not gt:
            gt = extract_section_text(encounter_id, target_note_id or "", "ASSESSMENT", loader)
        return {"label": gt, "metadata": {"note_id": target_note_id, "section": "A&P"}}

    if prompt_id == "P2":
        # A&P of a progress note (use the first progress note)
        if target_note_id is None:
            target_note_id = select_target_note(encounter_id, "progress note adult", loader)
        gt = extract_section_text(encounter_id, target_note_id or "", "AP", loader)
        if not gt:
            gt = extract_section_text(encounter_id, target_note_id or "", "ASSESSMENT", loader)
        return {"label": gt, "metadata": {"note_id": target_note_id, "section": "A&P"}}

    if prompt_id == "P5":
        # Predict imaging finding: select an imaging study, GT is its report text
        procs = data["procedures"]
        if procs.empty:
            return {"label": "", "metadata": {"note": "no procedures"}}
        # Imaging CPT range 70000-79999
        codes = procs["PX_CODE"].astype(str)
        imaging = procs[codes.str.match(r"^7\d{4}$", na=False)]
        if imaging.empty:
            return {"label": "", "metadata": {"note": "no imaging procedures"}}
        imaging = imaging.copy()
        imaging["TS"] = _combine_date_time(imaging, "PX_SERVICE_DATE", "PX_SERVICE_TIME")
        imaging = imaging.sort_values("TS")
        row = imaging.iloc[0]
        # GT = imaging report note text closest to the procedure timestamp
        notes = data["notes"]
        radio = notes[notes["NOTE_TYPE"].fillna("").str.contains("RADIOLOGY|IMAGING|CT |MRI|XRAY|X-RAY",
                                                                  case=False, regex=True)]
        gt_text = ""
        if not radio.empty:
            radio = radio.copy()
            radio["TS"] = pd.to_datetime(radio["NOTE_DATE"], errors="coerce")
            target_ts = row["TS"]
            radio["DELTA"] = (radio["TS"] - target_ts).abs()
            closest = radio.nsmallest(1, "DELTA")
            if not closest.empty:
                rid = closest.iloc[0]["NOTE_ID"]
                gt_rows = notes[notes["NOTE_ID"] == rid]
                gt_text = "\n".join(
                    f"[{str(r['NOTE_TYPE']).split(' - ', 1)[-1]}] {r['NOTE_TEXT']}"
                    for _, r in gt_rows.iterrows()
                    if isinstance(r.get("NOTE_TEXT"), str)
                )
        return {
            "label": gt_text or f"Imaging procedure: {row.get('PX_HCS_DESC', '')}",
            "metadata": {
                "imaging_ts": row["TS"].isoformat() if pd.notna(row["TS"]) else None,
                "code": row.get("PX_CODE"),
                "desc": row.get("PX_HCS_DESC"),
            },
        }

    if prompt_id == "P6":
        # Predict procedure result. Look for non-imaging procedures with notes.
        procs = data["procedures"]
        if procs.empty:
            return {"label": "", "metadata": {}}
        codes = procs["PX_CODE"].astype(str)
        non_imaging = procs[~codes.str.match(r"^7\d{4}$", na=False)]
        if non_imaging.empty:
            return {"label": "", "metadata": {}}
        non_imaging = non_imaging.copy()
        non_imaging["TS"] = _combine_date_time(non_imaging, "PX_SERVICE_DATE", "PX_SERVICE_TIME")
        non_imaging = non_imaging.sort_values("TS")
        row = non_imaging.iloc[0]
        return {
            "label": f"{row.get('PX_HCS_DESC', '')} on {row['TS']}",
            "metadata": {
                "procedure_ts": row["TS"].isoformat() if pd.notna(row["TS"]) else None,
                "code": row.get("PX_CODE"),
                "desc": row.get("PX_HCS_DESC"),
            },
        }

    if prompt_id == "P10":
        # Predict next 24-48h and full course. GT = subsequent notes + discharge.
        # FIX: also include sentinel-dated notes (NOTE_DATE before EN_START_DATE)
        # — these are typically discharge/summary notes with placeholder dates
        # in OMNY. They're excluded from the model's INPUT (correct) but should
        # be INCLUDED in GT (they ARE the answer).
        encs = data["encounters"]
        notes = data["notes"]
        admit_ts = pd.to_datetime(case["EN_START_DATE"])
        mid = admit_ts + timedelta(days=max(2, int(case["LOS_DAYS"]) // 2))
        future_notes = notes.copy()
        future_notes["TS"] = pd.to_datetime(future_notes["NOTE_DATE"], errors="coerce")
        # Include notes after mid OR sentinel-dated (before admit) — both reflect
        # end-of-encounter / discharge activity.
        in_future = future_notes["TS"] > mid
        sentinel = future_notes["TS"] < admit_ts - timedelta(days=1)
        future_notes = future_notes[in_future | sentinel].head(50)
        future_notes = future_notes.drop_duplicates(subset=["NOTE_ID", "NOTE_TYPE", "NOTE_TEXT"])
        dispo = encs.iloc[0].get("EN_DC_DIS") if not encs.empty else None
        gt_snippets = [
            f"[{r['NOTE_TYPE']}] {str(r['NOTE_TEXT'])[:200]}"
            for _, r in future_notes.iterrows()
            if isinstance(r.get("NOTE_TEXT"), str)
        ][:30]
        return {
            "label": (f"Discharge disposition: {dispo}\n\n" if dispo else "") + "\n".join(gt_snippets),
            "metadata": {"cutoff_ts": mid.isoformat(), "discharge_disposition": dispo,
                         "n_sentinel_notes_included": int(sentinel.sum())},
        }

    if prompt_id == "P4":
        # Same GT as P3 (discharge Dx); the prompt is run multiple times at varying N.
        return extract_ground_truth(encounter_id, "P3", loader)

    if prompt_id == "C8":
        # Lab interpretation: GT is the list of abnormal lab values (for rubric grading).
        labs = data["labs"]
        if labs.empty:
            return {"label": "", "metadata": {}}
        abn = labs[labs["LB_ABN_RESULT"].fillna("").astype(str).str.upper().isin(
            ["H", "L", "HH", "LL", "CRITICAL", "ABNORMAL", "A"]
        )]
        if abn.empty:
            return {"label": "", "metadata": {"n_abnormal": 0}}
        lines = [
            f"{r['LB_SHORT_NAME']}: {r['LB_RESULT_VALUE']} {r['LB_REF_UNIT']} "
            f"(ref {r['LB_REF_LOW']}-{r['LB_REF_HIGH']}) [{r['LB_ABN_RESULT']}]"
            for _, r in abn.iterrows()
        ]
        return {
            "label": "\n".join(lines),
            "metadata": {"n_abnormal": len(lines), "n_total_labs": len(labs)},
        }

    if prompt_id == "C2":
        # Generate DDx from HPI — GT is the actual A&P from the H&P
        if target_note_id is None:
            target_note_id = select_target_note(encounter_id, "h&p adult", loader)
        gt = extract_section_text(encounter_id, target_note_id or "", "AP", loader)
        if not gt:
            gt = extract_section_text(encounter_id, target_note_id or "", "ASSESSMENT", loader)
        return {"label": gt, "metadata": {"note_id": target_note_id, "note": "actual A&P as reference"}}

    if prompt_id in ("C3", "C4", "C7"):
        # No clean ground truth — judges score per the rubric without a reference answer.
        return {"label": "", "metadata": {"note": f"{prompt_id} graded by rubric without GT reference"}}

    if prompt_id == "C5":
        # Expected orders — GT is the actual orders placed after the plan documented
        meds = data["meds"]
        procs = data["procedures"]
        ordered_meds = []
        if not meds.empty:
            ordered_meds = meds["RX_GENERIC_NAME"].dropna().unique().tolist()[:30]
        ordered_procs = []
        if not procs.empty:
            ordered_procs = procs["PX_HCS_DESC"].dropna().unique().tolist()[:30]
        return {
            "label": (
                "Medications ordered: " + ", ".join(ordered_meds) + "\n"
                "Procedures ordered: " + ", ".join(ordered_procs)
            ),
            "metadata": {"n_meds": len(ordered_meds), "n_procs": len(ordered_procs)},
        }

    if prompt_id == "C6":
        # Imaging summary — GT is the actual imaging report
        notes = data["notes"]
        if notes.empty:
            return {"label": "", "metadata": {}}
        radio = notes[notes["NOTE_TYPE"].fillna("").str.contains(
            "RADIOLOGY|IMAGING|CT |MRI|X-RAY|XRAY|ULTRASOUND",
            case=False, regex=True
        )]
        if radio.empty:
            return {"label": "", "metadata": {"note": "no imaging report"}}
        rid = radio.iloc[0]["NOTE_ID"]
        gt_rows = notes[notes["NOTE_ID"] == rid]
        gt_text = "\n".join(
            f"[{str(r['NOTE_TYPE']).split(' - ', 1)[-1]}] {r['NOTE_TEXT']}"
            for _, r in gt_rows.iterrows()
            if isinstance(r.get("NOTE_TEXT"), str)
        )
        return {"label": gt_text, "metadata": {"note_id": rid}}

    if prompt_id in ("AE1", "AE2", "AE3"):
        # Defer to code/ae_events.py — caller should pass T from sidecar table.
        return {"label": None, "metadata": {"note": f"Call ae_events.detect_ae_events() for {prompt_id} T"}}

    if prompt_id in ("P8", "P9"):
        # Pathology / raw image — OMNY has limited pathology data; placeholder
        return {"label": "", "metadata": {"note": f"{prompt_id} requires pathology / DICOM data not in OMNY"}}

    return {"label": "", "metadata": {"note": f"No extractor for {prompt_id}"}}


# ---------------------------------------------------------------------------
# Self-check
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    loader = EncounterDataLoader()
    sample_enc = loader.cases.iloc[0]["ENCOUNTER_ID"]
    print(f"Rendering sample encounter {sample_enc} (S1):\n")
    print(render(sample_enc, "S1", loader=loader)[:1500])
    print("\n\n=== Same encounter, P1 (H&P only, A&P masked) ===\n")
    print(render(sample_enc, "P1", loader=loader)[:1500])
    print("\n\n=== Ground truths ===")
    for pid in ("S1", "S5", "C1", "P3", "P7"):
        gt = extract_ground_truth(sample_enc, pid, loader)
        label = gt["label"][:300] if gt["label"] else "(empty)"
        print(f"\n{pid}: {label}")
        print(f"  metadata: {gt['metadata']}")
