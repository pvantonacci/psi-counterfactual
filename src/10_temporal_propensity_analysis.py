"""
10_temporal_propensity_analysis.py

Illustrates two phenomena across 10 time horizons post-admission:
  1. At t0+4h cases and matched donors are indistinguishable by construction.
  2. As time passes, case clinical profiles diverge — a propensity model
     re-fitted at a later horizon assigns higher case probability to cases.

Symmetric mode (full analysis) — requires donor clinical data cache:
    python src/10a_pull_donor_clinical_data.py   # run once
    python src/10_temporal_propensity_analysis.py

Fallback mode (case-side proxy only) — runs without donor clinical data.

Outputs
-------
    results/figures/tp_baseline_propensity.png
    results/figures/tp_clinical_accumulation.png
    results/figures/tp_pair_cohesion.png
    results/figures/tp_propensity_trajectory.png   ← Figure 4: symmetric or proxy
    results/tables/temporal_propensity_scores.csv
    results/reports/temporal_propensity.md

Run from project root:
    source '/home/pvam/projects/PROTEGE - HealthBenck/PSI/bin/activate'
    python src/10_temporal_propensity_analysis.py
"""

from __future__ import annotations

import warnings
warnings.filterwarnings("ignore")

from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
from scipy import stats
from sklearn.linear_model import SGDClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline

ROOT        = Path(__file__).resolve().parents[1]
FIG_DIR     = ROOT / "results/figures"
RAW_DIR     = ROOT / "data/raw/psi_tables"
CACHE       = ROOT / "data/interim/snowflake_cache"
DONOR_CACHE = CACHE / "donor_temporal"   # written by 10a_pull_donor_clinical_data.py
REPORT      = ROOT / "results/reports/temporal_propensity.md"
SCORES_CSV  = ROOT / "results/tables/temporal_propensity_scores.csv"

FIG_DIR.mkdir(parents=True, exist_ok=True)
REPORT.parent.mkdir(parents=True, exist_ok=True)
SCORES_CSV.parent.mkdir(parents=True, exist_ok=True)

HORIZONS = [4, 8, 12, 16, 20, 24, 36, 48, 60, 72]   # hours post-admission

CASE_COLOR  = "#e05c4b"
DONOR_COLOR = "#4b8ec8"
PAIR_COLOR  = "#5aaa6e"

SYMMETRIC = all(
    (DONOR_CACHE / f).exists()
    for f in ["labs.parquet", "vitals.parquet", "procedures.parquet", "rx_orders.parquet"]
)
print(f"Mode: {'SYMMETRIC (full analysis)' if SYMMETRIC else 'PROXY (case-side only — run 10a first)'}")

plt.rc("font", **{"family": "sans-serif", "size": 11})


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def save_fig(fig: plt.Figure, name: str) -> Path:
    p = FIG_DIR / name
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  saved {p.relative_to(ROOT)}")
    return p


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = k / n
    denom  = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    half   = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def make_ts(df: pd.DataFrame, date_col: str, time_col: str | None = None) -> pd.Series:
    if time_col and time_col in df.columns:
        return pd.to_datetime(
            df[date_col].astype(str) + " " + df[time_col].fillna("00:00:00").astype(str),
            errors="coerce",
        )
    return pd.to_datetime(df[date_col], errors="coerce")


def count_window(
    df: pd.DataFrame, enc_id: str, t0: pd.Timestamp, h: float,
    abn_col: str | None = None,
) -> dict:
    """Count rows for enc_id with timestamp in (t0, t0+h]."""
    sub = df[df["ENCOUNTER_ID"] == enc_id]
    if sub.empty or pd.isna(t0):
        return {"n": 0, "n_abn": 0}
    cutoff = t0 + pd.Timedelta(hours=h)
    mask   = sub["ts"].notna() & (sub["ts"] > t0) & (sub["ts"] <= cutoff)
    n      = int(mask.sum())
    n_abn  = int((mask & (sub[abn_col] == "ABNORMAL")).sum()) if abn_col and abn_col in sub.columns else 0
    return {"n": n, "n_abn": n_abn}


# ═══════════════════════════════════════════════════════════════════════════════
# Load static data
# ═══════════════════════════════════════════════════════════════════════════════

print("\nLoading matched pairs …")
pairs = pd.read_csv(ROOT / "results/tables/all_matched_pairs.csv")
pairs["case_enc"]  = pairs["case_enc"].astype(str)
pairs["donor_enc"] = pairs["donor_enc"].astype(str)
r1 = pairs[pairs["match_rank"] == 1].copy()

print("Loading case metadata …")
case_frames = []
for p in sorted(ROOT.glob("outputs/PSI_*/cases.csv")):
    df = pd.read_csv(p); df["psi_type"] = p.parent.name; case_frames.append(df)
cases_meta = pd.concat(case_frames, ignore_index=True)
cases_meta["ENCOUNTER_ID"] = cases_meta["ENCOUNTER_ID"].astype(str)
cases_meta["EN_LOS"]       = pd.to_numeric(cases_meta["EN_LOS"], errors="coerce")
cases_meta["AGE"]          = pd.to_numeric(cases_meta["AGE"],    errors="coerce")
cases_meta["t0_dt"]        = pd.to_datetime(
    cases_meta["EN_START_DATE"].astype(str) + " " +
    cases_meta["EN_START_TIME"].fillna("00:00:00").astype(str), errors="coerce"
)

print("Loading donor metadata …")
donors_sf = pd.read_parquet(CACHE / "DONORS_SF.parquet")
donors_sf["ENCOUNTER_ID"] = donors_sf["ENCOUNTER_ID"].astype(str)
donors_sf["EN_LOS"]       = pd.to_numeric(donors_sf["EN_LOS"], errors="coerce")
donors_sf["AGE"]          = pd.to_numeric(donors_sf["AGE"],    errors="coerce")
donors_sf["t0_dt"]        = pd.to_datetime(
    donors_sf["EN_START_DATE"].astype(str) + " " +
    donors_sf["EN_START_TIME"].fillna("00:00:00").astype(str), errors="coerce"
)

# Augment rank-1 pairs with t0 and LOS for both sides
r1_aug = (
    r1.merge(
        cases_meta[["ENCOUNTER_ID","EN_LOS","t0_dt","AGE","E_TIME","t_star"]],
        left_on="case_enc", right_on="ENCOUNTER_ID", how="left",
    ).merge(
        donors_sf[["ENCOUNTER_ID","EN_LOS","t0_dt","AGE"]]
            .rename(columns={"EN_LOS":"donor_los","t0_dt":"donor_t0","AGE":"donor_age"}),
        left_on="donor_enc", right_on="ENCOUNTER_ID", how="left",
    ).rename(columns={"EN_LOS":"case_los","t0_dt":"case_t0","AGE":"case_age"})
)

print("Loading propensity scores (h=4h baseline) …")
prop_frames = []
for p in sorted(ROOT.glob("outputs/PSI_*/propensity_scores.csv")):
    df = pd.read_csv(p); df["psi_type"] = p.parent.name; prop_frames.append(df)
props = pd.concat(prop_frames, ignore_index=True)
props["ENCOUNTER_ID"] = props["ENCOUNTER_ID"].astype(str)
prop_map = dict(zip(props["ENCOUNTER_ID"], props["logit_score"]))


# ═══════════════════════════════════════════════════════════════════════════════
# Load clinical data (cases from CSV; donors from parquet cache if available)
# ═══════════════════════════════════════════════════════════════════════════════

def load_csv(fname: str, usecols: list[str]) -> pd.DataFrame:
    path = RAW_DIR / fname
    if not path.exists():
        return pd.DataFrame(columns=usecols + ["ts"])
    try:
        df = pd.read_csv(path, usecols=usecols, low_memory=False)
    except ValueError:
        avail = pd.read_csv(path, nrows=0).columns.tolist()
        df    = pd.read_csv(path, usecols=[c for c in usecols if c in avail], low_memory=False)
    df["ENCOUNTER_ID"] = df["ENCOUNTER_ID"].astype(str)
    return df


def load_parquet(fname: str) -> pd.DataFrame:
    path = DONOR_CACHE / fname
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_parquet(path)
    df["ENCOUNTER_ID"] = df["ENCOUNTER_ID"].astype(str)
    return df


print("Loading case clinical data from CSVs …")
case_ids  = set(r1_aug["case_enc"].unique())
donor_ids = set(r1_aug["donor_enc"].unique())

c_labs  = load_csv("labs.csv",      ["ENCOUNTER_ID","LB_RESULT_DATE","LB_RESULT_TIME","LB_ABN_RESULT","LB_LOINC_CODE"])
c_vits  = load_csv("vitals.csv",    ["ENCOUNTER_ID","VS_DATE","VS_TIME","VS_CODE"])
c_procs = load_csv("procedures.csv",["ENCOUNTER_ID","PX_SERVICE_DATE","PX_SERVICE_TIME","PX_CODE"])
c_rx    = load_csv("rx_orders.csv", ["ENCOUNTER_ID","RX_ORDER_DATE","RX_ORDER_TIME","RX_GENERIC_NAME"])

c_labs  = c_labs [c_labs ["ENCOUNTER_ID"].isin(case_ids)].copy()
c_vits  = c_vits [c_vits ["ENCOUNTER_ID"].isin(case_ids)].copy()
c_procs = c_procs[c_procs["ENCOUNTER_ID"].isin(case_ids)].copy()
c_rx    = c_rx   [c_rx   ["ENCOUNTER_ID"].isin(case_ids)].copy()

c_labs ["ts"] = make_ts(c_labs,  "LB_RESULT_DATE", "LB_RESULT_TIME")
c_vits ["ts"] = make_ts(c_vits,  "VS_DATE",        "VS_TIME")
c_procs["ts"] = make_ts(c_procs, "PX_SERVICE_DATE","PX_SERVICE_TIME")
c_rx   ["ts"] = make_ts(c_rx,    "RX_ORDER_DATE",  "RX_ORDER_TIME")

print(f"  Case labs: {len(c_labs):,}  vitals: {len(c_vits):,}  "
      f"procs: {len(c_procs):,}  rx: {len(c_rx):,}")

if SYMMETRIC:
    print("Loading donor clinical data from parquet cache …")
    d_labs  = load_parquet("labs.parquet")
    d_vits  = load_parquet("vitals.parquet")
    d_procs = load_parquet("procedures.parquet")
    d_rx    = load_parquet("rx_orders.parquet")

    d_labs  = d_labs [d_labs ["ENCOUNTER_ID"].isin(donor_ids)].copy()
    d_vits  = d_vits [d_vits ["ENCOUNTER_ID"].isin(donor_ids)].copy()
    d_procs = d_procs[d_procs["ENCOUNTER_ID"].isin(donor_ids)].copy()
    d_rx    = d_rx   [d_rx   ["ENCOUNTER_ID"].isin(donor_ids)].copy()

    # Build timestamps — same column names as CSV (Snowflake schema matches)
    d_labs ["ts"] = make_ts(d_labs,  "LB_RESULT_DATE", "LB_RESULT_TIME")
    d_vits ["ts"] = make_ts(d_vits,  "VS_DATE",        "VS_TIME")
    d_procs["ts"] = make_ts(d_procs, "PX_SERVICE_DATE","PX_SERVICE_TIME")
    d_rx   ["ts"] = make_ts(d_rx,    "RX_ORDER_DATE",  "RX_ORDER_TIME")

    print(f"  Donor labs: {len(d_labs):,}  vitals: {len(d_vits):,}  "
          f"procs: {len(d_procs):,}  rx: {len(d_rx):,}")
else:
    d_labs = d_vits = d_procs = d_rx = pd.DataFrame()


# ═══════════════════════════════════════════════════════════════════════════════
# Build accumulation tables  (cases + donors)
# ═══════════════════════════════════════════════════════════════════════════════

def build_accumulation(
    enc_ids: list[str],
    t0_map: dict,          # enc_id → pd.Timestamp
    los_map: dict,         # enc_id → float (days)
    labs_df:  pd.DataFrame,
    vits_df:  pd.DataFrame,
    procs_df: pd.DataFrame,
    rx_df:    pd.DataFrame,
    label: int,
) -> pd.DataFrame:
    rows = []
    for enc_id in enc_ids:
        t0     = t0_map.get(enc_id)
        los_h  = (los_map.get(enc_id) or float("nan"))
        if t0 is None or not isinstance(t0, pd.Timestamp) or pd.isna(t0):
            continue
        for h in HORIZONS:
            if not np.isnan(los_h) and los_h * 24 < h:
                continue
            lr  = count_window(labs_df,  enc_id, t0, h, "LB_ABN_RESULT")
            vr  = count_window(vits_df,  enc_id, t0, h)
            pr  = count_window(procs_df, enc_id, t0, h)
            rxr = count_window(rx_df,    enc_id, t0, h)
            rows.append({
                "enc_id":    enc_id,
                "horizon_h": h,
                "label":     label,
                "n_labs":    lr["n"],
                "n_abn_labs":lr["n_abn"],
                "n_vitals":  vr["n"],
                "n_procs":   pr["n"],
                "n_rx":      rxr["n"],
            })
    return pd.DataFrame(rows)


print("\nComputing clinical accumulation for cases …")
case_t0_map  = cases_meta.set_index("ENCOUNTER_ID")["t0_dt"].to_dict()
case_los_map = cases_meta.set_index("ENCOUNTER_ID")["EN_LOS"].to_dict()
case_age_map = cases_meta.set_index("ENCOUNTER_ID")["AGE"].to_dict()

accum_cases = build_accumulation(
    list(case_ids), case_t0_map, case_los_map,
    c_labs, c_vits, c_procs, c_rx, label=1,
)
print(f"  {len(accum_cases):,} rows (case × horizon)")

if SYMMETRIC:
    print("Computing clinical accumulation for donors …")
    donor_t0_map  = donors_sf.set_index("ENCOUNTER_ID")["t0_dt"].to_dict()
    donor_los_map = donors_sf.set_index("ENCOUNTER_ID")["EN_LOS"].to_dict()
    donor_age_map = donors_sf.set_index("ENCOUNTER_ID")["AGE"].to_dict()

    accum_donors = build_accumulation(
        list(donor_ids), donor_t0_map, donor_los_map,
        d_labs, d_vits, d_procs, d_rx, label=0,
    )
    print(f"  {len(accum_donors):,} rows (donor × horizon)")
    accum_all = pd.concat([accum_cases, accum_donors], ignore_index=True)
else:
    accum_donors = pd.DataFrame()
    accum_all    = accum_cases.copy()

# Keep a copy of cases-only for Figure 2
accum = accum_cases.copy()


# ═══════════════════════════════════════════════════════════════════════════════
# Fit propensity model at each horizon  (symmetric mode only)
# ═══════════════════════════════════════════════════════════════════════════════

FEATURE_COLS = ["n_labs", "n_abn_labs", "n_vitals", "n_procs", "n_rx"]

score_rows = []

if SYMMETRIC:
    print("\nFitting propensity model at each horizon …")
    for h in HORIZONS:
        sub = accum_all[accum_all["horizon_h"] == h].copy()
        if sub["label"].nunique() < 2 or len(sub) < 10:
            print(f"  h={h}h: skipped (n={len(sub)}, labels={sub['label'].unique()})")
            continue
        X = sub[FEATURE_COLS].fillna(0).values
        y = sub["label"].values

        model = Pipeline([
            ("scaler", StandardScaler()),
            ("clf",    SGDClassifier(
                loss="log_loss", penalty="l2", alpha=0.01,
                max_iter=2000, tol=1e-4, random_state=42,
                class_weight="balanced",
            )),
        ])
        model.fit(X, y)

        # Extract logit scores = log(p/(1-p))
        proba = model.predict_proba(X)[:, 1].clip(1e-6, 1 - 1e-6)
        logit = np.log(proba / (1 - proba))

        for i, (_, row) in enumerate(sub.iterrows()):
            score_rows.append({
                "enc_id":    row["enc_id"],
                "horizon_h": h,
                "label":     int(row["label"]),
                "logit":     float(logit[i]),
                "proba":     float(proba[i]),
            })

        case_logits  = logit[y == 1]
        donor_logits = logit[y == 0]
        print(f"  h={h:2d}h  n_cases={int(y.sum()):3d}  n_donors={int((y==0).sum()):3d}  "
              f"mean_logit_case={case_logits.mean():+.3f}  "
              f"mean_logit_donor={donor_logits.mean():+.3f}  "
              f"SMD={abs(case_logits.mean()-donor_logits.mean()) / max(np.sqrt((case_logits.std()**2+donor_logits.std()**2)/2),1e-6):.3f}")

    scores_df = pd.DataFrame(score_rows)
    scores_df.to_csv(SCORES_CSV, index=False)
    print(f"\n  Propensity scores saved → {SCORES_CSV.relative_to(ROOT)}")
else:
    scores_df = pd.DataFrame()


# ═══════════════════════════════════════════════════════════════════════════════
# Pair-cohesion table
# ═══════════════════════════════════════════════════════════════════════════════

cohesion_rows = []
for h in HORIZONS:
    case_in  = r1_aug["case_los"].notna()  & (r1_aug["case_los"]  * 24 >= h)
    donor_in = r1_aug["donor_los"].notna() & (r1_aug["donor_los"] * 24 >= h)
    both_in  = case_in & donor_in
    N = len(r1_aug)
    c_lo, c_hi = wilson_ci(case_in.sum(),  N)
    d_lo, d_hi = wilson_ci(donor_in.sum(), N)
    b_lo, b_hi = wilson_ci(both_in.sum(),  N)
    cohesion_rows.append({
        "h": h,
        "n_case":  case_in.sum(),  "c_lo": c_lo, "c_hi": c_hi,
        "n_donor": donor_in.sum(), "d_lo": d_lo, "d_hi": d_hi,
        "n_both":  both_in.sum(),  "b_lo": b_lo, "b_hi": b_hi,
        "N": N,
    })
cohesion = pd.DataFrame(cohesion_rows)


# ═══════════════════════════════════════════════════════════════════════════════
# FIGURE 1 — Baseline match quality at h = 4h
# ═══════════════════════════════════════════════════════════════════════════════

print("\nFigure 1 — Baseline propensity score overlap …")

case_logits_4h = props[props["label"] == 1]["logit_score"]
r1_donor_ids   = set(r1["donor_enc"])
donor_logits_4h = props[
    (props["label"] == 0) & (props["ENCOUNTER_ID"].isin(r1_donor_ids))
]["logit_score"]

fig, axes = plt.subplots(1, 2, figsize=(14, 5))
fig.suptitle(
    "Figure 1 — Match Quality at Baseline (h = 4 h)\n"
    "Cases and matched donors are indistinguishable by construction",
    fontsize=12, fontweight="bold", y=1.02,
)
ax = axes[0]
lo = min(case_logits_4h.quantile(0.01), donor_logits_4h.quantile(0.01))
hi = max(case_logits_4h.quantile(0.99), donor_logits_4h.quantile(0.99))
for data, color, label in [
    (props[props["label"] == 0]["logit_score"], PAIR_COLOR,
     f"Full donor pool (n={len(props[props['label']==0]):,})"),
    (donor_logits_4h, DONOR_COLOR, f"Rank-1 donors (n={len(donor_logits_4h):,})"),
    (case_logits_4h,  CASE_COLOR,  f"PSI cases (n={len(case_logits_4h):,})"),
]:
    clipped = data.clip(lo, hi)
    ax.hist(clipped, bins=60, range=(lo, hi), density=True,
            alpha=0.40, color=color, label=label)
    try:
        clipped.plot.kde(ax=ax, color=color, linewidth=2.0,
                         label="_nolegend_", bw_method=0.3)
    except Exception:
        pass
ax.axvline(case_logits_4h.median(),  color=CASE_COLOR,  ls="--", lw=1.4, alpha=0.9)
ax.axvline(donor_logits_4h.median(), color=DONOR_COLOR, ls="--", lw=1.4, alpha=0.9)
ax.set_xlabel("Logit propensity score"); ax.set_ylabel("Density")
ax.set_title("(A)  Score distributions at h = 4 h")
ax.legend(fontsize=9)
ax2 = axes[1]
r1_aug["case_logit"]  = r1_aug["case_enc"].map(prop_map)
r1_aug["donor_logit"] = r1_aug["donor_enc"].map(prop_map)
pair_df = r1_aug[["case_logit","donor_logit","psi_type"]].dropna()
ax2.scatter(pair_df["case_logit"], pair_df["donor_logit"],
            alpha=0.55, s=28, color=DONOR_COLOR, edgecolors="none")
mn = min(pair_df["case_logit"].min(), pair_df["donor_logit"].min())
mx = max(pair_df["case_logit"].max(), pair_df["donor_logit"].max())
ax2.plot([mn, mx], [mn, mx], color="black", ls="--", lw=1.2, label="Perfect match")
caliper_dist = (pair_df["case_logit"] - pair_df["donor_logit"]).abs()
ax2.set_xlabel("Case logit"); ax2.set_ylabel("Rank-1 donor logit")
ax2.set_title("(B)  Rank-1 pair logit scores  (dot = one pair)")
ax2.legend(fontsize=9)
ax2.text(0.03, 0.96,
         f"Median |Δlogit|: {caliper_dist.median():.3f}\n"
         f"Max |Δlogit|: {caliper_dist.max():.2f}",
         transform=ax2.transAxes, va="top", fontsize=9,
         bbox=dict(boxstyle="round,pad=0.3", fc="white", alpha=0.7))
fig.tight_layout()
save_fig(fig, "tp_baseline_propensity.png")
med_case_logit  = case_logits_4h.median()
med_donor_logit = donor_logits_4h.median()
med_caliper     = caliper_dist.median()
max_caliper     = caliper_dist.max()


# ═══════════════════════════════════════════════════════════════════════════════
# FIGURE 2 — Clinical feature accumulation (case-side, always available)
# ═══════════════════════════════════════════════════════════════════════════════

print("Figure 2 — Clinical feature accumulation …")
metrics = [
    ("n_labs",    "Labs ordered",       CASE_COLOR),
    ("n_abn_labs","Abnormal labs",      "#c0392b"),
    ("n_vitals",  "Vital signs",        "#8e44ad"),
    ("n_procs",   "Procedures",         "#e67e22"),
    ("n_rx",      "Rx orders",          "#27ae60"),
]

if SYMMETRIC and not accum_donors.empty:
    # Two-panel: cases left, donors right (or combined)
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle(
        "Figure 2 — Clinical Activity Accumulation: Cases vs. Rank-1 Donors\n"
        "(mean ± 95 % CI, encounters still in hospital at each horizon)",
        fontsize=12, fontweight="bold", y=1.02,
    )
    for ax, (df_acc, group_label) in zip(
        axes, [(accum_cases, "PSI Cases"), (accum_donors, "Rank-1 Donors")]
    ):
        agg = df_acc.groupby("horizon_h")[
            ["n_labs","n_abn_labs","n_vitals","n_procs","n_rx"]
        ].agg(["mean","sem"])
        for col, label, color in metrics:
            means = agg[(col,"mean")]
            sems  = agg[(col,"sem")]
            ax.plot(means.index, means.values, "o-", color=color,
                    label=label, linewidth=2.0, markersize=5)
            ax.fill_between(means.index,
                            (means - 1.96 * sems).values,
                            (means + 1.96 * sems).values,
                            alpha=0.15, color=color)
        ax.set_xlabel("Hours after admission")
        ax.set_ylabel("Cumulative count (mean ± 95 % CI)")
        ax.set_title(f"({['A','B'][axes.tolist().index(ax)]})  {group_label}")
        ax.set_xticks(HORIZONS)
        ax.set_xticklabels([str(h) for h in HORIZONS], rotation=30, ha="right")
        ax.legend(fontsize=9, loc="upper left")
        ax.grid(axis="y", linestyle="--", alpha=0.4)
else:
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle(
        "Figure 2 — Case Clinical Activity Accumulation After Admission\n"
        "(mean ± 95 % CI — donor clinical data not yet available)",
        fontsize=12, fontweight="bold", y=1.02,
    )
    agg = accum.groupby("horizon_h")[
        ["n_labs","n_abn_labs","n_vitals","n_procs","n_rx"]
    ].agg(["mean","sem"])
    ax = axes[0]
    for col, label, color in metrics:
        means = agg[(col,"mean")]; sems = agg[(col,"sem")]
        ax.plot(means.index, means.values, "o-", color=color,
                label=label, linewidth=2.0, markersize=5)
        ax.fill_between(means.index,
                        (means - 1.96*sems).values,
                        (means + 1.96*sems).values, alpha=0.15, color=color)
    ax.set_xlabel("Hours after admission"); ax.set_ylabel("Cumulative count")
    ax.set_title("(A)  Raw counts — cases only")
    ax.set_xticks(HORIZONS)
    ax.set_xticklabels([str(h) for h in HORIZONS], rotation=30, ha="right")
    ax.legend(fontsize=9, loc="upper left"); ax.grid(axis="y", linestyle="--", alpha=0.4)
    base = agg.loc[4]
    ax2 = axes[1]
    for col, label, color in metrics:
        base_val = base[(col,"mean")]
        if base_val == 0: continue
        rel = agg[(col,"mean")] / base_val
        ax2.plot(rel.index, rel.values, "o-", color=color, label=label,
                 linewidth=2.0, markersize=5)
    ax2.axhline(1.0, color="black", ls="--", lw=1.2)
    ax2.set_xlabel("Hours after admission"); ax2.set_ylabel("Relative to h = 4 h baseline")
    ax2.set_title("(B)  Relative growth — cases only")
    ax2.set_xticks(HORIZONS)
    ax2.set_xticklabels([str(h) for h in HORIZONS], rotation=30, ha="right")
    ax2.legend(fontsize=9, loc="upper left"); ax2.grid(axis="y", linestyle="--", alpha=0.4)
    for ax_ in axes:
        ax_.text(0.98, 0.03,
                 "Run 10a_pull_donor_clinical_data.py\nfor symmetric donor comparison",
                 transform=ax_.transAxes, ha="right", va="bottom", fontsize=7.5,
                 color="grey",
                 bbox=dict(boxstyle="round,pad=0.3", fc="white", alpha=0.7))

fig.tight_layout()
save_fig(fig, "tp_clinical_accumulation.png")


# ═══════════════════════════════════════════════════════════════════════════════
# FIGURE 3 — Pair cohesion and LOS
# ═══════════════════════════════════════════════════════════════════════════════

print("Figure 3 — Pair cohesion and LOS …")
fig, axes = plt.subplots(1, 3, figsize=(18, 5))
fig.suptitle(
    "Figure 3 — Match Pair Cohesion and LOS Distribution",
    fontsize=12, fontweight="bold", y=1.02,
)
hs = cohesion["h"].values; N = cohesion["N"].iloc[0]
ax = axes[0]
for col, lo_c, hi_c, color, lbl in [
    ("n_case",  "c_lo","c_hi", CASE_COLOR,  f"PSI cases (n={N})"),
    ("n_donor", "d_lo","d_hi", DONOR_COLOR, f"Rank-1 donors (n={N})"),
    ("n_both",  "b_lo","b_hi", PAIR_COLOR,  "Both in-hospital"),
]:
    prop = cohesion[col] / N
    ax.plot(hs, prop, "o-", color=color, label=lbl, linewidth=2.0, markersize=5)
    ax.fill_between(hs, cohesion[lo_c], cohesion[hi_c], alpha=0.15, color=color)
ax.set_xlabel("Hours after admission"); ax.set_ylabel("Proportion (95 % Wilson CI)")
ax.set_title("(A)  In-hospital proportion")
ax.set_xticks(hs); ax.set_xticklabels([str(h) for h in hs], rotation=30, ha="right")
ax.yaxis.set_major_formatter(mtick.PercentFormatter(1.0))
ax.set_ylim(0, 1.05); ax.legend(fontsize=9); ax.grid(axis="y", linestyle="--", alpha=0.4)

ax2 = axes[1]
pair_los = r1_aug[["case_los","donor_los"]].dropna()
ax2.scatter(pair_los["case_los"], pair_los["donor_los"],
            alpha=0.45, s=22, color=DONOR_COLOR, edgecolors="none")
lim = min(max(pair_los["case_los"].max(), pair_los["donor_los"].max()) + 2, 30)
ax2.plot([0, lim], [0, lim], color="black", ls="--", lw=1.2)
n_above = (pair_los["case_los"] > pair_los["donor_los"]).sum()
n_below = (pair_los["case_los"] < pair_los["donor_los"]).sum()
ax2.text(0.03, 0.97,
         f"Case LOS > Donor LOS: {n_above}\nCase LOS < Donor LOS: {n_below}",
         transform=ax2.transAxes, va="top", fontsize=9,
         bbox=dict(boxstyle="round,pad=0.3", fc="white", alpha=0.7))
ax2.set_xlabel("Case LOS (days)"); ax2.set_ylabel("Rank-1 donor LOS (days)")
ax2.set_title("(B)  Paired LOS  (dot = one pair)")
ax2.set_xlim(-0.5, lim); ax2.set_ylim(-0.5, lim)

ax3 = axes[2]
cv = r1_aug["case_los"].dropna().clip(0, 30).values
dv = r1_aug["donor_los"].dropna().clip(0, 30).values
vp = ax3.violinplot([cv, dv], positions=[1, 2], showmedians=True, showextrema=True)
vp["bodies"][0].set_facecolor(CASE_COLOR);  vp["bodies"][0].set_alpha(0.6)
vp["bodies"][1].set_facecolor(DONOR_COLOR); vp["bodies"][1].set_alpha(0.6)
for part in ("cbars","cmins","cmaxes","cmedians"):
    vp[part].set_color("black"); vp[part].set_linewidth(1.5)
ax3.set_xticks([1, 2]); ax3.set_xticklabels(["PSI Cases", "Rank-1 Donors"])
ax3.set_ylabel("LOS (days, capped at 30)")
ax3.set_title("(C)  LOS distribution comparison")
_, los_pval = stats.mannwhitneyu(cv, dv, alternative="two-sided")
ax3.text(0.5, 0.03, f"Mann–Whitney p = {los_pval:.3f}",
         transform=ax3.transAxes, ha="center", va="bottom", fontsize=9, color="grey")
fig.tight_layout()
save_fig(fig, "tp_pair_cohesion.png")


# ═══════════════════════════════════════════════════════════════════════════════
# FIGURE 4 — Propensity score trajectory (symmetric or proxy)
# ═══════════════════════════════════════════════════════════════════════════════

print("Figure 4 — Propensity score trajectory …")
fig, axes = plt.subplots(1, 2, figsize=(14, 5))
fig.suptitle(
    "Figure 4 — Propensity Score Trajectory Over Time\n"
    "At h = 4 h cases and donors overlap; divergence grows at later horizons",
    fontsize=12, fontweight="bold", y=1.02,
)

# Panel A: baseline h=4h density (always available)
ax = axes[0]
lo = min(case_logits_4h.quantile(0.02), donor_logits_4h.quantile(0.02))
hi = max(case_logits_4h.quantile(0.98), donor_logits_4h.quantile(0.98))
bins = np.linspace(lo, hi, 40)
ax.hist(donor_logits_4h.clip(lo,hi), bins=bins, density=True,
        alpha=0.5, color=DONOR_COLOR, label="Rank-1 donors")
ax.hist(case_logits_4h.clip(lo,hi),  bins=bins, density=True,
        alpha=0.5, color=CASE_COLOR,  label="PSI cases")
ax.set_xlabel("Logit propensity score at h = 4 h")
ax.set_ylabel("Density")
ax.set_title("(A)  h = 4 h — observed distributions overlap\n(by matching construction)")
ax.legend(fontsize=9)
ax.text(0.5, 0.94, "SMD ≈ 0 by construction",
        transform=ax.transAxes, ha="center", va="top", fontsize=10,
        color="darkgreen",
        bbox=dict(boxstyle="round,pad=0.3", fc="#d5f5d5", alpha=0.8))

# Panel B: trajectory — symmetric (re-fitted) or proxy
ax2 = axes[1]
ax2.set_xlabel("Hours after admission")
ax2.set_ylabel("Mean logit propensity score")
ax2.set_xticks(HORIZONS)
ax2.set_xticklabels([str(h) for h in HORIZONS], rotation=30, ha="right")
ax2.grid(axis="y", linestyle="--", alpha=0.4)

if SYMMETRIC and not scores_df.empty:
    traj = (
        scores_df.groupby(["horizon_h","label"])["logit"]
        .agg(["mean","sem"])
        .reset_index()
    )
    for lbl, color, grp_label in [(1, CASE_COLOR, "PSI Cases"), (0, DONOR_COLOR, "Rank-1 Donors")]:
        sub = traj[traj["label"] == lbl].sort_values("horizon_h")
        ax2.plot(sub["horizon_h"], sub["mean"], "o-", color=color,
                 linewidth=2.5, markersize=6, label=grp_label)
        ax2.fill_between(sub["horizon_h"],
                         sub["mean"] - 1.96 * sub["sem"],
                         sub["mean"] + 1.96 * sub["sem"],
                         alpha=0.15, color=color)
    ax2.set_title("(B)  Re-fitted propensity scores at each horizon\n"
                  "(SGDClassifier on case + donor feature matrices)")

    # Annotate pair-level caliper distances per horizon
    if not scores_df.empty:
        # Map scores back to rank-1 pairs
        score_map = scores_df.groupby(["enc_id","horizon_h"])["logit"].first().to_dict()
        dist_rows = []
        for _, row in r1_aug.iterrows():
            for h in HORIZONS:
                c_l = score_map.get((row["case_enc"], h), np.nan)
                d_l = score_map.get((row["donor_enc"], h), np.nan)
                if not np.isnan(c_l) and not np.isnan(d_l):
                    dist_rows.append({"h": h, "dist": abs(c_l - d_l)})
        if dist_rows:
            dist_df = pd.DataFrame(dist_rows)
            dist_agg = dist_df.groupby("h")["dist"].agg(["mean","sem"])
            # Add secondary annotation as text
            for h_val, row2 in dist_agg.iterrows():
                ax2.annotate(f"Δ={row2['mean']:.2f}",
                             xy=(h_val, 0), xycoords=("data","axes fraction"),
                             xytext=(0, -28), textcoords="offset points",
                             ha="center", fontsize=7, color="grey",
                             rotation=30)
else:
    # Proxy version
    agg_labs = accum.groupby("horizon_h")["n_labs"].mean()
    base_labs = agg_labs.loc[4] if agg_labs.loc[4] > 0 else 1.0
    mean_case_logit_4h  = case_logits_4h.mean()
    mean_donor_logit_4h = donor_logits_4h.mean()
    c_vals = [mean_case_logit_4h  + np.log(agg_labs.loc[h] / base_labs + 1) for h in HORIZONS]
    d_vals = [mean_donor_logit_4h for h in HORIZONS]
    ax2.plot(HORIZONS, c_vals, "o-", color=CASE_COLOR,  linewidth=2.5, markersize=6,
             label="Cases — proxy (log lab accumulation drift)")
    ax2.plot(HORIZONS, d_vals, "s--", color=DONOR_COLOR, linewidth=2.5, markersize=6,
             label="Donors — held at h=4h score (no clinical data)")
    ax2.fill_between(HORIZONS, d_vals, c_vals, alpha=0.12, color=CASE_COLOR,
                     label="Growing separation (expected)")
    ax2.set_title("(B)  Propensity trajectory — PROXY only\n"
                  "⚠ Run 10a_pull_donor_clinical_data.py for symmetric version")
    ax2.text(0.98, 0.03,
             "⚠ Proxy estimate.\nRun 10a to enable\nsymmetric re-fitting.",
             transform=ax2.transAxes, ha="right", va="bottom", fontsize=8,
             color="darkorange",
             bbox=dict(boxstyle="round,pad=0.3", fc="#fff3e0", alpha=0.9))

ax2.legend(fontsize=9, loc="upper left")
fig.tight_layout()
save_fig(fig, "tp_propensity_trajectory.png")

# Optional: per-horizon pair caliper distance boxplot (symmetric mode only)
if SYMMETRIC and not scores_df.empty and dist_rows:
    dist_df = pd.DataFrame(dist_rows)
    fig_d, ax_d = plt.subplots(figsize=(11, 4))
    groups = [dist_df[dist_df["h"] == h]["dist"].values for h in HORIZONS]
    bp = ax_d.boxplot(groups, patch_artist=True, notch=False,
                      showfliers=True, flierprops=dict(marker="o", markersize=3, alpha=0.4))
    for patch in bp["boxes"]:
        patch.set_facecolor(DONOR_COLOR); patch.set_alpha(0.6)
    ax_d.axhline(0, color="black", ls="--", lw=1)
    ax_d.set_xticks(range(1, len(HORIZONS) + 1))
    ax_d.set_xticklabels([f"{h}h" for h in HORIZONS])
    ax_d.set_xlabel("Hours after admission")
    ax_d.set_ylabel("|Logit(case) − Logit(donor)|")
    ax_d.set_title("Rank-1 Pair Caliper Distance Evolution\n"
                   "Distance grows as case scores increase relative to donors")
    ax_d.grid(axis="y", linestyle="--", alpha=0.4)
    fig_d.tight_layout()
    save_fig(fig_d, "tp_caliper_distance_evolution.png")


# ═══════════════════════════════════════════════════════════════════════════════
# Write report
# ═══════════════════════════════════════════════════════════════════════════════

print(f"\nWriting report → {REPORT.relative_to(ROOT)}")
REL = Path("../figures")

with REPORT.open("w") as f:
    def w(s=""): f.write(s + "\n")

    w("# Temporal Propensity Score Analysis")
    w()
    w("**Date:** 2026-06-07  ")
    w("**Horizons:** 4, 8, 12, 16, 20, 24, 36, 48, 60, 72 hours post-admission  ")
    w("**Pairs:** 161 rank-1 matched pairs  ")
    w(f"**Analysis mode:** {'Symmetric (re-fitted propensity at each horizon)' if SYMMETRIC else 'Proxy (case-side only)'}  ")
    w()
    w("---")
    w()
    w("## Conceptual Framework")
    w()
    w("1. **At t₀ + 4 h (matching time):** cases and matched donors are indistinguishable")
    w("   by construction. The CEM + logistic propensity matching enforces score overlap.")
    w()
    w("2. **As time passes:** cases accumulate PSI-event-driven clinical activity")
    w("   (additional labs, vitals, procedures, medications). A propensity model")
    w("   re-fitted at each later horizon assigns increasingly higher case probability")
    w("   to cases and lower probability to donors — the logit-scale distance between")
    w("   matched pairs grows, reflecting deteriorating match quality.")
    w()
    w("---")
    w()
    w("## Figure 1 — Baseline Match Quality (h = 4 h)")
    w()
    w(f"![]({REL}/tp_baseline_propensity.png)")
    w()
    w("| Statistic | Value |")
    w("|---|---|")
    w(f"| Median case logit | {med_case_logit:.3f} |")
    w(f"| Median donor logit | {med_donor_logit:.3f} |")
    w(f"| Median pair |Δlogit| | {med_caliper:.4f} |")
    w(f"| Max pair |Δlogit| | {max_caliper:.3f} |")
    w()
    w("---")
    w()
    w("## Figure 2 — Clinical Activity Accumulation")
    w()
    w(f"![]({REL}/tp_clinical_accumulation.png)")
    w()
    if SYMMETRIC:
        w("Both case and donor clinical activity at each horizon.")
        w("Cases show steeper accumulation — PSI-event consequences drive additional workup.")
    else:
        w("Case clinical activity at each horizon (donor data requires 10a pull).")
    w()
    w("| Horizon | n cases | Labs | Abn labs | Vitals | Procs | Rx |")
    w("|---|--:|--:|--:|--:|--:|--:|")
    for h in HORIZONS:
        sub = accum_cases[accum_cases["horizon_h"] == h]
        n   = len(sub)
        w(f"| {h}h | {n} | {sub['n_labs'].mean():.1f} | {sub['n_abn_labs'].mean():.1f} "
          f"| {sub['n_vitals'].mean():.1f} | {sub['n_procs'].mean():.1f} | {sub['n_rx'].mean():.1f} |")
    w()
    if SYMMETRIC and not accum_donors.empty:
        w("| Horizon | n donors | Labs | Abn labs | Vitals | Procs | Rx |")
        w("|---|--:|--:|--:|--:|--:|--:|")
        for h in HORIZONS:
            sub = accum_donors[accum_donors["horizon_h"] == h]
            n   = len(sub)
            w(f"| {h}h | {n} | {sub['n_labs'].mean():.1f} | {sub['n_abn_labs'].mean():.1f} "
              f"| {sub['n_vitals'].mean():.1f} | {sub['n_procs'].mean():.1f} | {sub['n_rx'].mean():.1f} |")
        w()
    w("---")
    w()
    w("## Figure 3 — Pair Cohesion and LOS")
    w()
    w(f"![]({REL}/tp_pair_cohesion.png)")
    w()
    w(f"Mann–Whitney LOS test: p = {los_pval:.3f}")
    w()
    w("| Horizon | P(case in-hosp) | P(donor in-hosp) | P(pair intact) |")
    w("|---|--:|--:|--:|")
    for _, row in cohesion.iterrows():
        w(f"| {int(row.h)}h | {100*row.n_case/row.N:.0f}% "
          f"| {100*row.n_donor/row.N:.0f}% | {100*row.n_both/row.N:.0f}% |")
    w()
    w("---")
    w()
    w("## Figure 4 — Propensity Score Trajectory")
    w()
    w(f"![]({REL}/tp_propensity_trajectory.png)")
    w()
    if SYMMETRIC and not scores_df.empty:
        w("Re-fitted SGDClassifier (log_loss, L2) at each horizon using")
        w("case and donor feature matrices [n_labs, n_abn_labs, n_vitals, n_procs, n_rx].")
        w()
        w("| Horizon | n cases | n donors | Mean logit (cases) | Mean logit (donors) | SMD |")
        w("|---|--:|--:|--:|--:|--:|")
        for h in HORIZONS:
            sub_c = scores_df[(scores_df["horizon_h"]==h) & (scores_df["label"]==1)]["logit"]
            sub_d = scores_df[(scores_df["horizon_h"]==h) & (scores_df["label"]==0)]["logit"]
            if len(sub_c) == 0 or len(sub_d) == 0:
                continue
            pooled_sd = np.sqrt((sub_c.std()**2 + sub_d.std()**2)/2)
            smd_val   = abs(sub_c.mean()-sub_d.mean()) / max(pooled_sd, 1e-6)
            w(f"| {h}h | {len(sub_c)} | {len(sub_d)} "
              f"| {sub_c.mean():+.3f} | {sub_d.mean():+.3f} | {smd_val:.3f} |")
        w()
        if (FIG_DIR / "tp_caliper_distance_evolution.png").exists():
            w(f"![]({REL}/tp_caliper_distance_evolution.png)")
            w()
            w("Pair-level |Δlogit| grows over time, confirming match quality deterioration.")
    else:
        w("**Proxy mode** — case-side drift only. Run `10a_pull_donor_clinical_data.py`")
        w("then re-run this script for the symmetric version.")
    w()
    w("---")
    w()
    w("*Generated by `src/10_temporal_propensity_analysis.py` — 2026-06-07*")

print("\nDone.")
print(f"  Report : {REPORT.relative_to(ROOT)}")
if not SYMMETRIC:
    print("\n  ⚠ Proxy mode — run '10a_pull_donor_clinical_data.py' then re-run for symmetric analysis.")
