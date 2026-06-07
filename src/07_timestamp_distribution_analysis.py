#!/usr/bin/env python3
"""
Timestamp distribution analysis — Cases vs Counterfactuals.

For each rank-1 matched pair, sets t0 = admission time and computes elapsed
hours for every clinical event across diagnoses, labs, vitals, procedures,
prescription orders/administrations, clinical scores, and medical devices.

Outputs
-------
results/figures/ts_*.png          — one PNG per plot
results/reports/timestamp_distribution_analysis.md  — markdown report
"""

import warnings
warnings.filterwarnings("ignore")

import sys
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.lines as mlines

ROOT    = Path(__file__).resolve().parents[1]
RAW     = ROOT / "data/raw/psi_tables"
FIG_DIR = ROOT / "results/figures"
OUT_MD  = ROOT / "results/reports/timestamp_distribution_analysis.md"

FIG_DIR.mkdir(parents=True, exist_ok=True)

CASE_COLOR = "#e05c4b"   # coral-red  — PSI cases
BEST_COLOR = "#4b8ec8"   # steel-blue — best match (rank 1)
ALL_COLOR  = "#5aaa6e"   # sage-green — full matched pool (all ranks)
ALPHA      = 0.40
BW_ADJUST  = 0.8

GROUPS = ["Case", "Best Match (rank 1)", "All Matches (rank 2+)"]

saved_figures: list[dict] = []   # {filename, title, caption}
summary_rows:  list[dict] = []


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def parse_dt(date_series: pd.Series, time_series: pd.Series,
             default_time: str = "12:00:00") -> pd.Series:
    time_filled = time_series.fillna(default_time).astype(str)
    combined = date_series.astype(str) + " " + time_filled
    return pd.to_datetime(combined, errors="coerce")


def elapsed_hours(event_ts: pd.Series, t0_map: dict,
                  enc_col: pd.Series) -> pd.Series:
    t0 = enc_col.map(t0_map)
    return (event_ts - t0).dt.total_seconds() / 3600


def save_fig(fig: plt.Figure, name: str, title: str, caption: str) -> str:
    path = FIG_DIR / name
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    saved_figures.append({"filename": name, "title": title, "caption": caption})
    print(f"  saved → {path.relative_to(ROOT)}")
    return name


def plot_domain(df_elapsed: pd.DataFrame, title: str,
                xlabel: str = "Hours from admission",
                xlim: tuple = (-12, 240), bins: int = 60,
                ax: plt.Axes = None) -> plt.Axes:
    """Histogram + KDE for up to three groups on a single axes."""
    if ax is None:
        _, ax = plt.subplots(figsize=(9, 4))

    if CASES_ONLY:
        palette = [("Case", CASE_COLOR)]
    else:
        palette = [
            ("Case",                   CASE_COLOR),
            ("Best Match (rank 1)",    BEST_COLOR),
            ("All Matches (rank 2+)",  ALL_COLOR),
        ]

    for role_label, color in palette:
        data = df_elapsed.loc[df_elapsed["role"] == role_label, "elapsed_h"].dropna()
        data = data[(data >= xlim[0]) & (data <= xlim[1])]
        if data.empty:
            continue
        ax.hist(data, bins=bins, range=xlim, alpha=ALPHA, color=color,
                label=f"{role_label} (n={len(data):,})", density=True)
        if len(data) > 5 and data.nunique() > 1:
            try:
                data.plot.kde(ax=ax, color=color, linewidth=2,
                              bw_method=BW_ADJUST, label="_nolegend_")
            except Exception:
                pass

    ax.axvline(0, color="black", linestyle="--", linewidth=1,
               alpha=0.6, label="Admission (t₀)")
    ax.set_title(title, fontweight="bold", pad=8)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Density")
    ax.set_xlim(xlim)
    ax.legend(fontsize=8)
    return ax


def collect_summary(name: str, df: pd.DataFrame) -> None:
    valid = df[df["elapsed_h"].notna()]
    groups = ["Case"] if CASES_ONLY else GROUPS
    for role_label in groups:
        sub = valid.loc[valid["role"] == role_label, "elapsed_h"]
        early = sub[sub.between(0, 4)]
        summary_rows.append({
            "Domain":            name,
            "Group":             role_label,
            "N events":          len(sub),
            "N events (0–4 h)":  len(early),
            "Median (h)":        round(sub.median(), 1) if len(sub) else None,
            "P25 (h)":           round(sub.quantile(0.25), 1) if len(sub) else None,
            "P75 (h)":           round(sub.quantile(0.75), 1) if len(sub) else None,
        })


# ─────────────────────────────────────────────────────────────────────────────
# Load matched pairs + encounters
# ─────────────────────────────────────────────────────────────────────────────

print("Loading matched pairs …")
pairs    = pd.read_csv(ROOT / "results/tables/all_matched_pairs.csv")
pairs_r1 = pairs[pairs["match_rank"] == 1].copy()

# Three non-overlapping groups (priority: Case > Best Match > All Matches)
case_encs      = set(pairs["case_enc"].unique())
donor_encs_r1  = set(pairs_r1["donor_enc"].unique()) - case_encs
donor_encs_all = set(pairs["donor_enc"].unique()) - case_encs - donor_encs_r1
all_encs       = case_encs | donor_encs_r1 | donor_encs_all

# Single role label per encounter (used to colour every event row)
role: dict[str, str] = {}
for e in donor_encs_all:
    role[e] = "All Matches (rank 2+)"
for e in donor_encs_r1:
    role[e] = "Best Match (rank 1)"
for e in case_encs:
    role[e] = "Case"

print(f"  {len(pairs_r1)} rank-1 pairs  |  {len(case_encs)} cases  |  "
      f"{len(donor_encs_r1)} best-match donors  |  "
      f"{len(donor_encs_all)} extended-pool donors  |  "
      f"{pairs['psi_type'].nunique()} PSI types")

print("Loading encounters …")
enc = pd.read_csv(RAW / "encounters.csv",
                  usecols=["ENCOUNTER_ID", "EN_START_DATE", "EN_START_TIME", "EN_LOS"])
enc = enc[enc["ENCOUNTER_ID"].isin(all_encs)].copy()
enc["t0"] = parse_dt(enc["EN_START_DATE"], enc["EN_START_TIME"])
t0_map    = enc.set_index("ENCOUNTER_ID")["t0"].to_dict()

# Detect whether any donor clinical data exists in raw tables.
any_donors_in_raw = len((donor_encs_r1 | donor_encs_all) & set(enc["ENCOUNTER_ID"]))
CASES_ONLY = any_donors_in_raw == 0
if CASES_ONLY:
    print("  *** No donor data found in raw tables — running in CASES-ONLY mode ***")
    print("  *** Re-run 00_pull_psi_tables.py then re-run this script for full comparison ***\n")
    all_encs = case_encs
else:
    print(f"  Best-match donors in raw tables  : "
          f"{len(donor_encs_r1 & set(enc['ENCOUNTER_ID']))} / {len(donor_encs_r1)}")
    print(f"  Extended-pool donors in raw tables: "
          f"{len(donor_encs_all & set(enc['ENCOUNTER_ID']))} / {len(donor_encs_all)}\n")


# ─────────────────────────────────────────────────────────────────────────────
# 1. Diagnoses
# ─────────────────────────────────────────────────────────────────────────────

print("\n[1/7] Diagnoses …")
dx = pd.read_csv(RAW / "diagnoses.csv",
                 usecols=["ENCOUNTER_ID", "DX_DATE", "DX_TIME",
                          "DX_CODE", "DX_HCS_DESC"])
dx = dx[dx["ENCOUNTER_ID"].isin(all_encs)].copy()
dx["event_ts"]  = parse_dt(dx["DX_DATE"], dx["DX_TIME"])
dx["elapsed_h"] = elapsed_hours(dx["event_ts"], t0_map, dx["ENCOUNTER_ID"])
dx["role"]      = dx["ENCOUNTER_ID"].map(role)
collect_summary("Diagnoses", dx)

fig, ax = plt.subplots(figsize=(10, 4))
plot_domain(dx, "Diagnoses — Time from Admission", xlim=(-24, 480), ax=ax)
plt.tight_layout()
save_fig(fig, "ts_diagnoses.png", "Diagnoses",
         "Distribution of diagnosis timestamps relative to admission (t₀). "
         "Negative values indicate diagnoses recorded before the encounter start time.")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Labs
# ─────────────────────────────────────────────────────────────────────────────

print("[2/7] Labs …")
labs = pd.read_csv(RAW / "labs.csv",
                   usecols=["ENCOUNTER_ID", "LB_ORDER_DATE", "LB_ORDER_TIME",
                             "LB_SPECIMEN_DATE", "LB_SPECIMEN_TIME",
                             "LB_RESULT_DATE", "LB_RESULT_TIME",
                             "LB_SHORT_NAME", "LB_LOINC_LEVEL2_CAT"])
labs = labs[labs["ENCOUNTER_ID"].isin(all_encs)].copy()
labs["specimen_ts"] = parse_dt(labs["LB_SPECIMEN_DATE"], labs["LB_SPECIMEN_TIME"])
labs["order_ts"]    = parse_dt(labs["LB_ORDER_DATE"],    labs["LB_ORDER_TIME"])
labs["result_ts"]   = parse_dt(labs["LB_RESULT_DATE"],   labs["LB_RESULT_TIME"])
labs["event_ts"]    = labs["specimen_ts"].fillna(labs["order_ts"])
labs["elapsed_h"]   = elapsed_hours(labs["event_ts"], t0_map, labs["ENCOUNTER_ID"])
labs["result_lag"]  = (labs["result_ts"] - labs["event_ts"]).dt.total_seconds() / 3600
labs["role"]        = labs["ENCOUNTER_ID"].map(role)
collect_summary("Labs", labs)

fig, axes = plt.subplots(1, 2, figsize=(14, 4))
plot_domain(labs, "Labs — Specimen/Order Time from Admission",
            xlim=(-12, 240), ax=axes[0])
lag_df = labs[["result_lag", "role"]].rename(columns={"result_lag": "elapsed_h"})
plot_domain(lag_df, "Labs — Result Turnaround (Specimen → Result)",
            xlabel="Hours (specimen to result)", xlim=(0, 48), ax=axes[1])
axes[1].lines[0].set_visible(False)
plt.tight_layout()
save_fig(fig, "ts_labs.png", "Labs",
         "Left: lab order/specimen time from admission. "
         "Right: turnaround time from specimen collection to result.")

# Lab breakdown by category
top_cats = labs["LB_LOINC_LEVEL2_CAT"].value_counts().head(6).index.tolist()
ncols = 3
nrows = (len(top_cats) + ncols - 1) // ncols
fig, axes = plt.subplots(nrows, ncols, figsize=(14, nrows * 4))
axes = axes.flatten()
for i, cat in enumerate(top_cats):
    subset = labs[labs["LB_LOINC_LEVEL2_CAT"] == cat][["elapsed_h", "role"]]
    plot_domain(subset, f"Labs: {cat}", xlim=(-12, 240), ax=axes[i])
for j in range(len(top_cats), len(axes)):
    axes[j].set_visible(False)
fig.suptitle("Lab Distributions by Category", fontsize=14,
             fontweight="bold", y=1.01)
plt.tight_layout()
save_fig(fig, "ts_labs_by_category.png", "Labs by Category",
         "Lab timestamp distributions split by LOINC Level-2 category "
         "(top 6 categories by event count).")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Vitals
# ─────────────────────────────────────────────────────────────────────────────

print("[3/7] Vitals …")
vs = pd.read_csv(RAW / "vitals.csv",
                 usecols=["ENCOUNTER_ID", "VS_DATE", "VS_TIME",
                          "VS_CODE", "VS_DESC"])
vs = vs[vs["ENCOUNTER_ID"].isin(all_encs)].copy()
vs["event_ts"]  = parse_dt(vs["VS_DATE"], vs["VS_TIME"])
vs["elapsed_h"] = elapsed_hours(vs["event_ts"], t0_map, vs["ENCOUNTER_ID"])
vs["role"]      = vs["ENCOUNTER_ID"].map(role)
collect_summary("Vitals", vs)

fig, ax = plt.subplots(figsize=(10, 4))
plot_domain(vs, "Vitals — Time from Admission", xlim=(-12, 240), ax=ax)
plt.tight_layout()
save_fig(fig, "ts_vitals.png", "Vitals",
         "Distribution of vital sign recording times relative to admission.")

# Vitals by type
top_vs = vs["VS_DESC"].value_counts().head(6).index.tolist()
nrows  = (len(top_vs) + ncols - 1) // ncols
fig, axes = plt.subplots(nrows, ncols, figsize=(14, nrows * 4))
axes = axes.flatten()
for i, vtype in enumerate(top_vs):
    subset = vs[vs["VS_DESC"] == vtype][["elapsed_h", "role"]]
    plot_domain(subset, f"Vital: {vtype}", xlim=(-12, 240), ax=axes[i])
for j in range(len(top_vs), len(axes)):
    axes[j].set_visible(False)
fig.suptitle("Vital Sign Distributions by Type", fontsize=14,
             fontweight="bold", y=1.01)
plt.tight_layout()
save_fig(fig, "ts_vitals_by_type.png", "Vitals by Type",
         "Vital sign timestamp distributions for the top 6 vital types.")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Procedures
# ─────────────────────────────────────────────────────────────────────────────

print("[4/7] Procedures …")
px = pd.read_csv(RAW / "procedures.csv",
                 usecols=["ENCOUNTER_ID", "PX_ORDER_DATE", "PX_ORDER_TIME",
                          "PX_SERVICE_DATE", "PX_SERVICE_TIME",
                          "PX_CODE", "PX_SHORT_DESC", "PX_TYPE"])
px = px[px["ENCOUNTER_ID"].isin(all_encs)].copy()
px["service_ts"] = parse_dt(px["PX_SERVICE_DATE"], px["PX_SERVICE_TIME"])
px["order_ts"]   = parse_dt(px["PX_ORDER_DATE"],   px["PX_ORDER_TIME"])
px["event_ts"]   = px["service_ts"].fillna(px["order_ts"])
px["elapsed_h"]  = elapsed_hours(px["event_ts"], t0_map, px["ENCOUNTER_ID"])
px["order_lag"]  = (px["service_ts"] - px["order_ts"]).dt.total_seconds() / 3600
px["role"]       = px["ENCOUNTER_ID"].map(role)
collect_summary("Procedures", px)

fig, axes = plt.subplots(1, 2, figsize=(14, 4))
plot_domain(px, "Procedures — Service Time from Admission",
            xlim=(-24, 480), ax=axes[0])
lag_df = px[px["order_lag"].between(0, 72)][["order_lag", "role"]].rename(
    columns={"order_lag": "elapsed_h"})
plot_domain(lag_df, "Procedures — Order-to-Service Lag",
            xlabel="Hours (order to service)", xlim=(0, 72), ax=axes[1])
axes[1].lines[0].set_visible(False)
plt.tight_layout()
save_fig(fig, "ts_procedures.png", "Procedures",
         "Left: procedure service time from admission. "
         "Right: order-to-service lag (0–72 h).")


# ─────────────────────────────────────────────────────────────────────────────
# 5. Prescription Orders
# ─────────────────────────────────────────────────────────────────────────────

print("[5/7] Prescription orders …")
rx = pd.read_csv(RAW / "prescription_orders.csv",
                 usecols=["ENCOUNTER_ID", "RX_ORDER_DATE", "RX_ORDER_TIME",
                          "RX_START_DATE", "RX_START_TIME",
                          "RX_END_DATE",   "RX_END_TIME",
                          "RX_GENERIC_NAME", "RX_ORDER_CATEGORY", "RX_STATUS"])
rx = rx[rx["ENCOUNTER_ID"].isin(all_encs)].copy()
rx["event_ts"]  = parse_dt(rx["RX_ORDER_DATE"], rx["RX_ORDER_TIME"])
rx["start_ts"]  = parse_dt(rx["RX_START_DATE"], rx["RX_START_TIME"])
rx["end_ts"]    = parse_dt(rx["RX_END_DATE"],   rx["RX_END_TIME"])
rx["elapsed_h"] = elapsed_hours(rx["event_ts"], t0_map, rx["ENCOUNTER_ID"])
rx["duration_h"]= (rx["end_ts"] - rx["start_ts"]).dt.total_seconds() / 3600
rx["role"]      = rx["ENCOUNTER_ID"].map(role)
collect_summary("Rx Orders", rx)

fig, axes = plt.subplots(1, 2, figsize=(14, 4))
plot_domain(rx, "Prescription Orders — Time from Admission",
            xlim=(-12, 240), ax=axes[0])
dur_df = rx[rx["duration_h"].between(0, 240)][["duration_h", "role"]].rename(
    columns={"duration_h": "elapsed_h"})
plot_domain(dur_df, "Prescription Orders — Order Duration",
            xlabel="Duration (hours)", xlim=(0, 240), ax=axes[1])
axes[1].lines[0].set_visible(False)
plt.tight_layout()
save_fig(fig, "ts_rx_orders.png", "Prescription Orders",
         "Left: prescription order time from admission. "
         "Right: order duration (start to end, capped at 240 h).")


# ─────────────────────────────────────────────────────────────────────────────
# 6. Prescription Administrations
# ─────────────────────────────────────────────────────────────────────────────

print("[6/7] Prescription administrations …")
adm = pd.read_csv(RAW / "prescription_administrations.csv",
                  usecols=["ENCOUNTER_ID", "AD_ADMIN_DATE", "AD_ADMIN_TIME",
                            "AD_GENERIC_NAME", "AD_HCS_ADMIN_ROUTE"])
adm = adm[adm["ENCOUNTER_ID"].isin(all_encs)].copy()
adm["event_ts"]  = parse_dt(adm["AD_ADMIN_DATE"], adm["AD_ADMIN_TIME"])
adm["elapsed_h"] = elapsed_hours(adm["event_ts"], t0_map, adm["ENCOUNTER_ID"])
adm["role"]      = adm["ENCOUNTER_ID"].map(role)
collect_summary("Rx Administrations", adm)

fig, ax = plt.subplots(figsize=(10, 4))
plot_domain(adm, "Medication Administrations — Time from Admission",
            xlim=(-12, 240), ax=ax)
plt.tight_layout()
save_fig(fig, "ts_rx_admin.png", "Medication Administrations",
         "Distribution of medication administration times relative to admission.")


# ─────────────────────────────────────────────────────────────────────────────
# 7. Clinical Scores + Medical Devices
# ─────────────────────────────────────────────────────────────────────────────

print("[7/7] Clinical scores & medical devices …")
scores = pd.read_csv(RAW / "scores.csv",
                     usecols=["ENCOUNTER_ID", "QS_DATE", "QS_TIME",
                               "QS_NAME", "QS_MEASURE_NAME"])
scores = scores[scores["ENCOUNTER_ID"].isin(all_encs)].copy()
scores["event_ts"]  = parse_dt(scores["QS_DATE"], scores["QS_TIME"])
scores["elapsed_h"] = elapsed_hours(scores["event_ts"], t0_map,
                                    scores["ENCOUNTER_ID"])
scores["role"] = scores["ENCOUNTER_ID"].map(role)
collect_summary("Clinical Scores", scores)

devs = pd.read_csv(RAW / "medical_devices.csv",
                   usecols=["ENCOUNTER_ID", "DV_IMPLANT_DATE",
                             "DV_REMOVAL_DATE", "DV_DEVICE_TYPE",
                             "DV_HCS_DEVICE_NAME"])
devs = devs[devs["ENCOUNTER_ID"].isin(all_encs)].copy()
devs["implant_ts"]  = pd.to_datetime(devs["DV_IMPLANT_DATE"], errors="coerce")
devs["removal_ts"]  = pd.to_datetime(devs["DV_REMOVAL_DATE"], errors="coerce")
devs["elapsed_h"]   = elapsed_hours(devs["implant_ts"], t0_map,
                                    devs["ENCOUNTER_ID"])
devs["duration_h"]  = (devs["removal_ts"] - devs["implant_ts"]).dt.total_seconds() / 3600
devs["role"]        = devs["ENCOUNTER_ID"].map(role)
collect_summary("Medical Devices", devs)

misc_panels = [
    ("Clinical Scores",   scores, (-12, 240)),
    ("Medical Devices",   devs,   (-24, 480)),
]
fig, axes = plt.subplots(1, 2, figsize=(14, 4))
for ax, (name, df, xlim) in zip(axes, misc_panels):
    if df["elapsed_h"].notna().sum() > 5:
        plot_domain(df[["elapsed_h", "role"]], f"{name} — Time from Admission",
                    xlim=xlim, ax=ax)
    else:
        ax.text(0.5, 0.5, f"Insufficient events\n({name})",
                ha="center", va="center", transform=ax.transAxes)
        ax.set_title(name)
plt.tight_layout()
save_fig(fig, "ts_scores_devices.png", "Clinical Scores & Medical Devices",
         "Timestamp distributions for clinical scores and medical device implants.")


# ─────────────────────────────────────────────────────────────────────────────
# Summary dashboard
# ─────────────────────────────────────────────────────────────────────────────

print("\nBuilding summary dashboard …")
all_domain_data = [
    ("Diagnoses",         dx,     (-24, 480)),
    ("Labs",              labs,   (-12, 240)),
    ("Vitals",            vs,     (-12, 240)),
    ("Procedures",        px,     (-24, 480)),
    ("Rx Orders",         rx,     (-12, 240)),
    ("Rx Administrations",adm,    (-12, 240)),
    ("Clinical Scores",   scores, (-12, 240)),
]
active = [(n, d, xl) for n, d, xl in all_domain_data
          if d["elapsed_h"].notna().sum() > 5]

ncols_dash = 2
nrows_dash = (len(active) + 1) // ncols_dash
fig, axes = plt.subplots(nrows_dash, ncols_dash,
                         figsize=(16, nrows_dash * 4))
axes = axes.flatten()

for i, (name, df, xlim) in enumerate(active):
    plot_domain(df[["elapsed_h", "role"]], name, xlim=xlim,
                bins=50, ax=axes[i])

for j in range(len(active), len(axes)):
    axes[j].set_visible(False)

legend_elements = [mpatches.Patch(facecolor=CASE_COLOR, alpha=0.6, label="Case")]
if not CASES_ONLY:
    legend_elements += [
        mpatches.Patch(facecolor=BEST_COLOR, alpha=0.6, label="Best Match (rank 1)"),
        mpatches.Patch(facecolor=ALL_COLOR,  alpha=0.6, label="All Matches (rank 2+)"),
    ]
legend_elements.append(mlines.Line2D([], [], color="black", linestyle="--",
                                     linewidth=1.5, label="Admission (t₀)"))
fig.legend(handles=legend_elements, loc="lower center", ncol=3,
           fontsize=11, bbox_to_anchor=(0.5, -0.02), frameon=True)
suptitle = (
    "Clinical Event Timing — Cases Only (Hours from Admission)\n"
    "⚠ Counterfactual data pending Snowflake re-pull"
    if CASES_ONLY else
    "Clinical Event Timing — Cases vs Best Match vs Full Pool (Hours from Admission)"
)
fig.suptitle(suptitle, fontsize=14, fontweight="bold", y=1.01)
plt.tight_layout()
save_fig(fig, "ts_summary_dashboard.png", "Summary Dashboard",
         "All clinical domains in a single view. "
         "X-axis is hours from admission (t₀ = 0). "
         "Filled histogram = density; smooth curve = KDE.")


# ─────────────────────────────────────────────────────────────────────────────
# Early window (0–4 h)
# ─────────────────────────────────────────────────────────────────────────────

print("Building early-window plot (0–4 h) …")
early_domains = [
    ("Diagnoses",         dx),
    ("Labs",              labs),
    ("Vitals",            vs),
    ("Procedures",        px),
    ("Rx Orders",         rx),
    ("Rx Administrations",adm),
]
ncols_e = 3
nrows_e = (len(early_domains) + ncols_e - 1) // ncols_e
fig, axes = plt.subplots(nrows_e, ncols_e, figsize=(16, nrows_e * 4))
axes = axes.flatten()

for i, (name, df) in enumerate(early_domains):
    subset = df[df["elapsed_h"].between(0, 4)][["elapsed_h", "role"]]
    n_case = (subset["role"] == "Case").sum()
    n_ctrl = (subset["role"] == "Counterfactual").sum()
    if len(subset) < 5:
        axes[i].set_title(f"{name}\n(no events in first 4 h)", fontsize=10)
        axes[i].axis("off")
        continue
    plot_domain(subset, f"{name}\n(cases: {n_case}, controls: {n_ctrl})",
                xlabel="Hours from admission", xlim=(0, 4), bins=24, ax=axes[i])
    axes[i].lines[0].set_visible(False)

for j in range(len(early_domains), len(axes)):
    axes[j].set_visible(False)

fig.suptitle("Clinical Events in First 4 h of Admission (Feature Extraction Window)",
             fontsize=14, fontweight="bold", y=1.01)
plt.tight_layout()
save_fig(fig, "ts_early_window.png", "First 4 Hours (Feature Window)",
         "Zoomed view of the [t₀, t₀+4 h] window used by the propensity model "
         "to build the feature matrix.")


# ─────────────────────────────────────────────────────────────────────────────
# Summary table
# ─────────────────────────────────────────────────────────────────────────────

summary = pd.DataFrame(summary_rows)


# ─────────────────────────────────────────────────────────────────────────────
# Write markdown report
# ─────────────────────────────────────────────────────────────────────────────

print(f"\nWriting report → {OUT_MD.relative_to(ROOT)}")

REL_FIG = Path("../figures")  # relative path from results/reports/

def md_table(df: pd.DataFrame) -> str:
    lines = ["| " + " | ".join(str(c) for c in df.columns) + " |",
             "| " + " | ".join("---" for _ in df.columns) + " |"]
    for _, row in df.iterrows():
        lines.append("| " + " | ".join(
            "" if pd.isna(v) else str(v) for v in row) + " |")
    return "\n".join(lines)


mode_note = (
    "> **Cases-only run.** Counterfactual clinical data is not present in "
    "`data/raw/psi_tables/` — re-run `src/00_pull_psi_tables.py` (now includes "
    "donor encounter IDs) then re-run this script for the full comparison.\n\n"
    if CASES_ONLY else ""
)

with OUT_MD.open("w") as f:
    f.write(f"# Timestamp Distribution Analysis\n\n")
    if mode_note:
        f.write(mode_note)
    f.write(f"**Date:** 2026-06-07  \n")
    cohort_str = (
        f"{len(case_encs)} PSI cases (counterfactuals pending Snowflake re-pull)"
        if CASES_ONLY else
        f"{len(case_encs)} cases  |  "
        f"{len(donor_encs_r1)} best-match donors (rank 1)  |  "
        f"{len(donor_encs_all)} extended-pool donors (rank 2+)"
    )
    f.write(f"**Cohort:** {cohort_str} across {pairs_r1['psi_type'].nunique()} PSI types  \n")
    f.write(f"**Time zero (t₀):** encounter admission (`EN_START_DATE + EN_START_TIME`)  \n")
    f.write(f"**Units:** hours elapsed from t₀  \n\n")
    f.write("---\n\n")

    # ── Group definitions ─────────────────────────────────────────────────────
    n_best_in_raw = len(donor_encs_r1 & set(enc["ENCOUNTER_ID"])) if not CASES_ONLY else 0
    n_all_in_raw  = len(donor_encs_all & set(enc["ENCOUNTER_ID"])) if not CASES_ONLY else 0

    f.write("## Groups\n\n")
    f.write(
        "Each plot shows up to three non-overlapping groups drawn from "
        "`results/tables/all_matched_pairs.csv`:\n\n"
    )
    f.write(
        f"| Group | Color | Encounters | In raw tables | Description |\n"
        f"|---|---|---|---|---|\n"
        f"| **Case** | 🟥 Coral | {len(case_encs)} | {len(case_encs)} | "
        f"Inpatient encounters where a PSI adverse event was confirmed by Claude chart review. "
        f"These are the observations of interest. |\n"
    )
    if not CASES_ONLY:
        f.write(
            f"| **Best Match (rank 1)** | 🟦 Blue | {len(donor_encs_r1)} | {n_best_in_raw} | "
            f"The single closest-matching control encounter per case, selected by the "
            f"propensity-score nearest-neighbour matching in Stage 2c. One donor per case "
            f"(`match_rank = 1` in `all_matched_pairs.csv`). |\n"
            f"| **All Matches (rank 2+)** | 🟩 Green | {len(donor_encs_all)} | {n_all_in_raw} | "
            f"The remaining matched controls for each case (`match_rank ≥ 2`), up to k = 50 "
            f"donors per case. Together with **Best Match**, these form the complete "
            f"counterfactual pool from `all_matched_pairs.csv` "
            f"({len(donor_encs_r1) + len(donor_encs_all):,} unique donor encounters total). |\n"
        )
    f.write(
        "\n**Design note:** the three groups are non-overlapping by construction. "
        "Rank-1 donors appear only in *Best Match*; rank 2–50 donors appear only in "
        "*All Matches (rank 2+)*. An encounter that is a case is never used as a donor "
        "in the same analysis. "
        "Combining *Best Match* + *All Matches* recovers the full counterfactual pool.\n\n"
    )
    f.write("---\n\n")

    # ── Pipeline description ──────────────────────────────────────────────────
    n_unmatched = pairs_r1["psi_type"].nunique()  # rough proxy; recalc below
    # Actual unmatched: cases in psi_inpatient_cases that have no rank-1 entry
    # 110 = cases that enter the matching pipeline after governance filtering
    # (forbidden suppliers 1990, 3707, 3490 removed from the 177 Claude-confirmed positives)
    n_pipeline_cases = 110
    n_unmatched = max(0, n_pipeline_cases - len(case_encs))

    f.write("## What are the 106 counterfactuals?\n\n")
    f.write(
        f"The **{len(pairs_r1)}** is the number of **rank-1 matched pairs** from "
        f"`results/tables/all_matched_pairs.csv` — one best-matched counterfactual "
        f"encounter per PSI case. Each pair is a case (a patient who experienced a PSI "
        f"adverse event) linked to its single closest control encounter (a patient who did "
        f"not experience that event but was otherwise similar). Script "
        f"`07_timestamp_distribution_analysis.py` uses only rank-1 pairs for its plots.\n\n"
    )
    if n_unmatched > 0:
        f.write(
            f"Why {len(pairs_r1)} and not {n_pipeline_cases}? The run-all summary reports "
            f"{n_pipeline_cases} total cases across the 16 PSI types after governance "
            f"filtering (forbidden suppliers 1990, 3707, 3490 removed from the 177 "
            f"Claude-confirmed positives in `psi_inpatient_cases.csv`). "
            f"{n_unmatched} of those {n_pipeline_cases} cases found zero matching donors "
            f"and therefore have no entry in `all_matched_pairs.csv`. "
            f"{n_pipeline_cases} − {n_unmatched} = **{len(pairs_r1)}**.\n\n"
        )

    f.write("### How were these observations selected — full pipeline\n\n")
    f.write(
        "**`src/00_pull_psi_tables.py`** — Pulls inpatient encounter data for PSI-flagged "
        "patients from Snowflake into `data/raw/psi_tables/`. Re-run after matching to also "
        "include donor encounter IDs so that counterfactual clinical records are available.\n\n"

        "**`src/01_psi_pipeline.py`** — PSI detection in three stages:\n"
        "- **Stage A+B (SQL):** For each of the 16 AHRQ Part-1 PSI definitions, encounters "
        "are filtered by ICD-10 regex against `OMNY_DIAGNOSES_ENCOUNTERS`, then the linked "
        "clinical note must match a secondary keyword regex. Up to 200 candidates per PSI "
        "type are sampled.\n"
        "- **Stage C (Claude chart review):** Each candidate note is sent to "
        "`claude-sonnet-4-6`, which returns structured JSON. A candidate is **confirmed "
        "positive** if Claude answers `psi_event_present=YES`, "
        "`hospital_acquired_not_poa=YES/UNCERTAIN`, `is_exclusion=NO`, "
        "`confidence=HIGH`. Negatives require HIGH confidence + `psi_event_present=NO`.\n"
        "- **Balanced selection:** Up to 5 positives + 5 negatives per PSI type are retained "
        "→ `data/raw/psi_inpatient_cases.csv` (255 rows: 177 positive, 78 negative).\n\n"

        "**`src/02_counterfactual_pipeline.py`** — Matching pipeline, run once per PSI type "
        "by `src/03_run_all_psi_types.py`:\n"
        "- **Stage −1 (cases.csv):** The 145 raw encounters are governance-filtered "
        "(forbidden suppliers 1990, 3707, 3490 removed) → 110 encounters. PSI metadata is "
        "joined, `t0` (admission) and `E_time` (PSI event, from ICD-10 diagnosis date or "
        "note date fallback) are parsed, and the event landmark `t_star = E_i − 6` is "
        "computed (where `E_i` is the 4-hour grid tick of the event, and 6 ticks = 24-hour "
        "lookback window).\n"
        "- **Stage 0 (donor pool):** Snowflake is queried for all inpatient encounters not "
        "in the case list using 1% Bernoulli sampling of the ~51M-row "
        "`OMNY_REPL_ID.CUSTOM.ENCOUNTERS` table, with forbidden suppliers excluded.\n"
        "- **Stage 1 (Coarsened Exact Matching — CEM):** Each encounter is binned on 10 "
        "dimensions (sex, age, race, ethnicity, employment, facility type, facility size, "
        "urban/rural, admission department, current department) to form a CEM stratum key. "
        "Donors are only eligible to match a case if they share the same stratum.\n"
        "- **Stage 2a (feature matrix):** Clinical records in the **[t₀, t₀+4 h]** window "
        "are extracted for cases and matched-strata donors (labs, vitals, procedures, Rx "
        "orders, diagnoses). Each encounter becomes a sparse feature vector. The 4-hour "
        "cutoff enforces the no-post-event-leakage rule.\n"
        "- **Stage 2b (LSPS — propensity score):** An L1 logistic regression "
        "(`SGDClassifier`) is trained on the feature matrix (label: 1=case / 0=donor). "
        "The logit-scale score is the matching distance metric.\n"
        "- **Stage 2c (K:1 nearest-neighbor matching):** For each case a **risk set** is "
        "formed from donors still admitted at `t_star` (`grid_LOS > t_star`), restricted "
        "to the case's CEM stratum. The caliper is `0.2 × SD(logit scores)` (relaxed 3× "
        "if needed). The top k=50 closest donors within the caliper are selected and saved "
        "as ranked matched pairs.\n\n"

        "**`src/03_run_all_psi_types.py`** — Invokes `02` for all 16 PSI types and "
        "aggregates results into `results/tables/all_matched_pairs.csv` "
        f"(3,615 rows: up to 50 donors per case × {len(pairs_r1)} matched cases).\n\n"

        "**`src/07_timestamp_distribution_analysis.py`** — Reads `all_matched_pairs.csv`, "
        f"keeps only **rank-1** pairs (the single best-matched donor per case) → "
        f"**{len(pairs_r1)} case–counterfactual pairs** across "
        f"{pairs_r1['psi_type'].nunique()} PSI types, then plots clinical event timestamps "
        "relative to `t₀` for both groups.\n\n"
    )
    f.write("---\n\n")

    f.write("## Summary Dashboard\n\n")
    f.write(f"![]({REL_FIG}/ts_summary_dashboard.png)\n\n")
    f.write("All clinical domains. X-axis = hours from admission. "
            "Coral = cases, blue = counterfactuals. "
            "Dashed line = admission (t₀ = 0).\n\n")

    for fig_meta in saved_figures:
        if fig_meta["filename"] == "ts_summary_dashboard.png":
            continue
        f.write(f"## {fig_meta['title']}\n\n")
        f.write(f"![]({REL_FIG}/{fig_meta['filename']})\n\n")
        f.write(f"{fig_meta['caption']}\n\n")

    f.write("---\n\n")
    f.write("## Event Count Summary\n\n")
    f.write(md_table(summary))
    f.write("\n\n")
    f.write("*N events (0–4 h): events within the propensity model feature "
            "extraction window.*\n")

print("\nDone.")
print(f"  Report : {OUT_MD.relative_to(ROOT)}")
print(f"  Figures: {len(saved_figures)} PNGs in {FIG_DIR.relative_to(ROOT)}/")
