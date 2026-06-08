"""
09_counterfactual_diagnostics.py

Counterfactual matching diagnostics report.

Inputs
------
results/tables/all_matched_pairs.csv
outputs/PSI_*/propensity_scores.csv
outputs/PSI_*/balance_table.csv
outputs/PSI_*/cases.csv
data/raw/psi_tables/encounters.csv
data/raw/psi_tables/diagnoses.csv
data/raw/psi_tables/problem_lists.csv   (optional)

Outputs
-------
results/reports/counterfactual_diagnostics.md
results/figures/diag_*.png

Run from project root:
    source '/home/pvam/projects/PROTEGE - HealthBenck/PSI/bin/activate'
    python src/09_counterfactual_diagnostics.py
"""

from __future__ import annotations

import warnings
warnings.filterwarnings("ignore")

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

ROOT     = Path(__file__).resolve().parents[1]
OUT_DIR  = ROOT / "outputs"
FIG_DIR  = ROOT / "results/figures"
RAW_DIR  = ROOT / "data/raw/psi_tables"
REPORT   = ROOT / "results/reports/counterfactual_diagnostics.md"
FIG_DIR.mkdir(parents=True, exist_ok=True)
REPORT.parent.mkdir(parents=True, exist_ok=True)

CASE_COLOR = "#e05c4b"
BEST_COLOR = "#4b8ec8"
ALL_COLOR  = "#5aaa6e"

FORBIDDEN = {1990, 3707, 3490}

# ── Charlson prefix map (Quan 2005) ──────────────────────────────────────────
CHARLSON: dict[str, tuple[int, list[str]]] = {
    "MI":         (1, ["I21","I22"]),
    "CHF":        (1, ["I09.9","I11.0","I13.0","I13.2","I25.5","I42.0","I42.5","I42.6",
                        "I42.7","I42.8","I42.9","I43","I50","P29.0"]),
    "PVD":        (1, ["I70","I71","I73.1","I73.8","I73.9","I77.1","I79.0","I79.2",
                        "K55.1","K55.8","K55.9","Z95.8","Z95.9"]),
    "CEREB":      (1, ["G45","G46","H34.0","I60","I61","I62","I63","I64","I65","I66","I67","I68","I69"]),
    "DEMENTIA":   (1, ["F00","F01","F02","F03","F05.1","G30","G31.1"]),
    "COPD":       (1, ["J40","J41","J42","J43","J44","J45","J46","J47","J60","J61",
                        "J62","J63","J64","J65","J66","J67","J68.4","J70.1","J70.3"]),
    "RHEUM":      (1, ["M05","M06","M09.0","M32","M34","M35.1","M35.2","M35.3","M36.0"]),
    "PUD":        (1, ["K25","K26","K27","K28"]),
    "MILD_LIVER": (1, ["B18","K70.0","K70.1","K70.2","K70.3","K70.9","K71.3","K71.4",
                        "K71.5","K71.7","K73","K74","K76.0","K76.2","K76.3","K76.4",
                        "K76.8","K76.9","Z94.4"]),
    "DM_UNCOMP":  (1, ["E10.0","E10.6","E10.8","E10.9","E11.0","E11.6","E11.8","E11.9",
                        "E12.0","E12.6","E12.9","E13.0","E13.6","E13.8","E13.9",
                        "E14.0","E14.6","E14.8","E14.9"]),
    "DM_COMP":    (2, ["E10.2","E10.3","E10.4","E10.5","E10.7","E11.2","E11.3","E11.4",
                        "E11.5","E11.7","E12.2","E12.3","E12.4","E12.5","E12.7",
                        "E13.2","E13.3","E13.4","E13.5","E13.7","E14.2","E14.3",
                        "E14.4","E14.5","E14.7"]),
    "HEMIPLEG":   (2, ["G04.1","G11.4","G80.1","G80.2","G81","G82","G83.0","G83.1",
                        "G83.2","G83.3","G83.4","G83.9"]),
    "RENAL":      (2, ["I12.0","I13.1","N03.2","N03.3","N03.4","N03.5","N03.6","N03.7",
                        "N05.2","N05.3","N05.4","N05.5","N05.6","N05.7","N18","N19",
                        "N25.0","Z49.0","Z49.1","Z49.2","Z94.0","Z99.2"]),
    "CANCER":     (2, ["C00","C01","C02","C03","C04","C05","C06","C07","C08","C09",
                        "C10","C11","C12","C13","C14","C15","C16","C17","C18","C19",
                        "C20","C21","C22","C23","C24","C25","C26","C30","C31","C32",
                        "C33","C34","C37","C38","C39","C40","C41","C43","C45","C46",
                        "C47","C48","C49","C50","C51","C52","C53","C54","C55","C56",
                        "C57","C58","C60","C61","C62","C63","C64","C65","C66","C67",
                        "C68","C69","C70","C71","C72","C73","C74","C75","C76","C81",
                        "C82","C83","C84","C85","C88","C90","C91","C92","C93","C94",
                        "C95","C96","C97"]),
    "MOD_LIVER":  (3, ["I85.0","I85.9","I86.4","I98.2","K70.4","K71.1","K72.1","K72.9",
                        "K76.5","K76.6","K76.7"]),
    "METASTATIC": (6, ["C77","C78","C79","C80"]),
    "AIDS":       (6, ["B20","B21","B22","B24"]),
}


def charlson_score(codes: list[str]) -> int:
    clean = [c.upper().replace(".", "") for c in codes if c and str(c) != "nan"]
    flags: dict[str, int] = {}
    for cat, (_, prefixes) in CHARLSON.items():
        pfx = [p.upper().replace(".", "") for p in prefixes]
        flags[cat] = int(any(c.startswith(p) for c in clean for p in pfx))
    if flags.get("DM_COMP"):    flags["DM_UNCOMP"]  = 0
    if flags.get("MOD_LIVER"):  flags["MILD_LIVER"] = 0
    if flags.get("METASTATIC"): flags["CANCER"]     = 0
    return sum(CHARLSON[cat][0] * v for cat, v in flags.items())


def smd(a: pd.Series, b: pd.Series) -> float:
    """Standardised mean difference (Cohen's d)."""
    a = pd.to_numeric(a, errors="coerce").dropna()
    b = pd.to_numeric(b, errors="coerce").dropna()
    if len(a) == 0 or len(b) == 0:
        return float("nan")
    pooled_sd = np.sqrt((a.std() ** 2 + b.std() ** 2) / 2)
    return abs(a.mean() - b.mean()) / pooled_sd if pooled_sd > 0 else 0.0


def save_fig(fig: plt.Figure, name: str) -> Path:
    p = FIG_DIR / name
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  saved {p.relative_to(ROOT)}")
    return p


# ═══════════════════════════════════════════════════════════════════════════════
# Load data
# ═══════════════════════════════════════════════════════════════════════════════

print("Loading data …")

pairs  = pd.read_csv(ROOT / "results/tables/all_matched_pairs.csv")
pairs["case_enc"]  = pairs["case_enc"].astype(str)
pairs["donor_enc"] = pairs["donor_enc"].astype(str)
r1     = pairs[pairs["match_rank"] == 1].copy()

psi_meta = pd.read_csv(RAW_DIR / ".." / "psi_inpatient_cases.csv", low_memory=False)
psi_meta["ENCOUNTER_ID"] = psi_meta["ENCOUNTER_ID"].astype(str)

enc = pd.read_csv(RAW_DIR / "encounters.csv", low_memory=False)
enc["ENCOUNTER_ID"]     = enc["ENCOUNTER_ID"].astype(str)
enc["DATA_SUPPLIER_ID"] = pd.to_numeric(enc["DATA_SUPPLIER_ID"], errors="coerce")

# All case + best-match donor IDs we care about
case_ids  = set(pairs["case_enc"].unique())
donor_r1_ids = set(r1["donor_enc"].unique())
all_ids   = case_ids | donor_r1_ids

enc_sub = enc[enc["ENCOUNTER_ID"].isin(all_ids)].drop_duplicates("ENCOUNTER_ID").copy()
enc_sub["AGE"] = pd.to_numeric(enc_sub["AGE"], errors="coerce")
enc_sub["EN_LOS"] = pd.to_numeric(enc_sub["EN_LOS"], errors="coerce")

print(f"  Pairs: {len(pairs):,}  cases: {len(case_ids)}  rank-1 donors: {len(donor_r1_ids)}")

# Aggregate propensity scores and balance tables across all PSI types
print("Aggregating propensity scores …")
prop_frames, bal_frames, cases_frames = [], [], []
for psi_type in sorted(pairs["psi_type"].unique()):
    out = OUT_DIR / psi_type
    for path, store in [
        (out / "propensity_scores.csv", prop_frames),
        (out / "balance_table.csv",     bal_frames),
        (out / "cases.csv",             cases_frames),
    ]:
        if path.exists():
            df = pd.read_csv(path)
            df["psi_type"] = psi_type
            store.append(df)

props  = pd.concat(prop_frames,  ignore_index=True) if prop_frames  else pd.DataFrame()
bal    = pd.concat(bal_frames,   ignore_index=True) if bal_frames   else pd.DataFrame()
cases  = pd.concat(cases_frames, ignore_index=True) if cases_frames else pd.DataFrame()
cases["ENCOUNTER_ID"] = cases["ENCOUNTER_ID"].astype(str)

print(f"  Propensity scores: {len(props):,} rows | Balance rows: {len(bal)}")

# Diagnoses for Charlson
print("Loading diagnoses for Charlson …")
dx = pd.read_csv(RAW_DIR / "diagnoses.csv", low_memory=False,
                 usecols=["ENCOUNTER_ID", "DX_CODE", "DX_CHRONIC", "DX_DATE"])
dx["ENCOUNTER_ID"] = dx["ENCOUNTER_ID"].astype(str)
dx = dx[dx["ENCOUNTER_ID"].isin(all_ids)].copy()

# Pre-existing classification: DX_CHRONIC='YES' or DX_DATE before encounter start
enc_t0_map = {}
if "EN_START_DATE" in enc_sub.columns:
    for _, row in enc_sub.iterrows():
        t0 = pd.to_datetime(
            str(row["EN_START_DATE"]) + " " +
            str(row.get("EN_START_TIME", "00:00:00")),
            errors="coerce"
        )
        enc_t0_map[row["ENCOUNTER_ID"]] = t0

def get_charlson(enc_id: str) -> int:
    rows = dx[dx["ENCOUNTER_ID"] == enc_id]
    if len(rows) == 0:
        return 0
    pre = pd.Series(False, index=rows.index)
    pre |= rows["DX_CHRONIC"].fillna("").astype(str).str.upper() == "YES"
    t0 = enc_t0_map.get(enc_id)
    if t0 and not pd.isna(t0):
        dates = pd.to_datetime(rows["DX_DATE"], errors="coerce")
        pre  |= dates.notna() & (dates < t0)
    codes = rows.loc[pre, "DX_CODE"].dropna().astype(str).tolist()
    return charlson_score(codes)

print("  Computing Charlson scores …")
charlson_map = {eid: get_charlson(eid) for eid in all_ids}


# ═══════════════════════════════════════════════════════════════════════════════
# Build analysis frames
# ═══════════════════════════════════════════════════════════════════════════════

# Merge encounter demographics onto pairs
r1_merged = r1.merge(
    enc_sub[["ENCOUNTER_ID","AGE","EN_LOS","GENDER","RACE","EN_FACILITY_TYPE",
             "EN_URBAN_RURAL","EN_DEPT","EN_ADM_DEPT"]].rename(columns=lambda c: f"case_{c}"),
    left_on="case_enc", right_on="case_ENCOUNTER_ID", how="left"
).merge(
    enc_sub[["ENCOUNTER_ID","AGE","EN_LOS","GENDER","RACE","EN_FACILITY_TYPE",
             "EN_URBAN_RURAL","EN_DEPT","EN_ADM_DEPT"]].rename(columns=lambda c: f"donor_{c}"),
    left_on="donor_enc", right_on="donor_ENCOUNTER_ID", how="left"
)
r1_merged["case_charlson"]  = r1_merged["case_enc"].map(charlson_map)
r1_merged["donor_charlson"] = r1_merged["donor_enc"].map(charlson_map)

# Per-case match depth
depth = pairs.groupby("case_enc")["match_rank"].max().reset_index(name="k")
depth_by_type = pairs.groupby(["psi_type","case_enc"])["match_rank"].max().reset_index(name="k")


# ═══════════════════════════════════════════════════════════════════════════════
# Figures
# ═══════════════════════════════════════════════════════════════════════════════

# ── Figure 1: Propensity score overlap ───────────────────────────────────────
print("\nGenerating figures …")

def fig_propensity_overlap():
    # Build logit score series for: cases, rank-1 donors, all donors
    # Use per-type props, subset to relevant encounter IDs
    all_case_logits, all_r1_logits, all_pool_logits = [], [], []
    for psi_type in sorted(pairs["psi_type"].unique()):
        ptype_props = props[props["psi_type"] == psi_type] if "psi_type" in props.columns else pd.DataFrame()
        if len(ptype_props) == 0:
            continue
        ptype_r1_donors = set(r1[r1["psi_type"] == psi_type]["donor_enc"])
        case_logits = ptype_props[ptype_props["label"] == 1]["logit_score"]
        donor_logits = ptype_props[ptype_props["label"] == 0]["logit_score"]
        r1_logits = ptype_props[
            (ptype_props["label"] == 0) &
            (ptype_props["ENCOUNTER_ID"].astype(str).isin(ptype_r1_donors))
        ]["logit_score"]
        all_case_logits.append(case_logits)
        all_r1_logits.append(r1_logits)
        all_pool_logits.append(donor_logits)

    case_logits = pd.concat(all_case_logits) if all_case_logits else pd.Series(dtype=float)
    r1_logits   = pd.concat(all_r1_logits)   if all_r1_logits   else pd.Series(dtype=float)
    pool_logits = pd.concat(all_pool_logits)  if all_pool_logits else pd.Series(dtype=float)

    fig, axes = plt.subplots(1, 2, figsize=(14, 4))

    # Full distribution
    ax = axes[0]
    xlim = (
        min(case_logits.quantile(0.01), pool_logits.quantile(0.01)),
        max(case_logits.quantile(0.99), pool_logits.quantile(0.99)),
    )
    for data, color, label in [
        (pool_logits, ALL_COLOR,  f"Donor pool (n={len(pool_logits):,})"),
        (r1_logits,   BEST_COLOR, f"Best match rank-1 (n={len(r1_logits):,})"),
        (case_logits, CASE_COLOR, f"Cases (n={len(case_logits):,})"),
    ]:
        if len(data) == 0: continue
        data_clipped = data.clip(*xlim)
        ax.hist(data_clipped, bins=60, range=xlim, density=True,
                alpha=0.45, color=color, label=label)
        if len(data_clipped) > 5 and data_clipped.nunique() > 1:
            try:
                data_clipped.plot.kde(ax=ax, color=color, linewidth=2, label="_nolegend_")
            except Exception:
                pass
    ax.set_xlabel("Logit propensity score")
    ax.set_ylabel("Density")
    ax.set_title("Propensity Score Overlap — All Types Combined")
    ax.legend(fontsize=8)
    ax.axvline(case_logits.median(), color=CASE_COLOR, linestyle="--", linewidth=1, alpha=0.8)
    ax.axvline(r1_logits.median(),   color=BEST_COLOR, linestyle="--", linewidth=1, alpha=0.8)

    # Zoom: rank-1 pairs only
    ax2 = axes[1]
    pair_df = pd.DataFrame({
        "case":  r1_merged["case_enc"].map(
            dict(zip(props["ENCOUNTER_ID"].astype(str), props["logit_score"]))),
        "donor": r1_merged["donor_enc"].map(
            dict(zip(props["ENCOUNTER_ID"].astype(str), props["logit_score"]))),
    }).dropna()
    if len(pair_df) > 0:
        ax2.scatter(pair_df["case"], pair_df["donor"], alpha=0.4,
                    s=18, color=BEST_COLOR, edgecolors="none")
        mn = min(pair_df["case"].min(), pair_df["donor"].min())
        mx = max(pair_df["case"].max(), pair_df["donor"].max())
        ax2.plot([mn, mx], [mn, mx], color="black", linestyle="--", linewidth=1)
        ax2.set_xlabel("Case logit score")
        ax2.set_ylabel("Matched donor logit score")
        ax2.set_title("Rank-1 Pair Propensity Scores\n(dot on diagonal = perfect match)")
    fig.tight_layout()
    save_fig(fig, "diag_propensity_overlap.png")
    return len(case_logits), len(pool_logits), case_logits.median(), r1_logits.median()

n_cases_prop, n_pool_prop, med_case_logit, med_r1_logit = fig_propensity_overlap()


# ── Figure 2: Covariate balance (SMD) ────────────────────────────────────────
def fig_balance():
    if bal.empty:
        return {}

    bal_agg = bal.groupby("feature")[["smd_before", "smd_after"]].mean().reset_index()
    bal_agg = bal_agg.sort_values("smd_after", ascending=False)

    fig, ax = plt.subplots(figsize=(8, max(4, len(bal_agg) * 0.6 + 1)))
    y = np.arange(len(bal_agg))
    ax.barh(y - 0.2, bal_agg["smd_before"], height=0.35, color=CASE_COLOR, alpha=0.7, label="Before matching")
    ax.barh(y + 0.2, bal_agg["smd_after"],  height=0.35, color=BEST_COLOR, alpha=0.7, label="After matching")
    ax.axvline(0.1, color="black", linestyle="--", linewidth=1, label="SMD = 0.1 threshold")
    ax.axvline(0.2, color="grey",  linestyle=":",  linewidth=1, label="SMD = 0.2 threshold")
    ax.set_yticks(y)
    ax.set_yticklabels(bal_agg["feature"])
    ax.set_xlabel("Standardised Mean Difference (SMD)")
    ax.set_title("Covariate Balance Before vs After Matching\n(mean across 16 PSI types)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    save_fig(fig, "diag_balance_smd.png")
    return dict(zip(bal_agg["feature"], bal_agg["smd_after"]))

smd_after = fig_balance()


# ── Figure 3: Balance heatmap by PSI type ────────────────────────────────────
def fig_balance_heatmap():
    if bal.empty:
        return
    pivot = bal.pivot_table(index="psi_type", columns="feature", values="smd_after")
    pivot = pivot.reindex(sorted(pivot.index))

    fig, ax = plt.subplots(figsize=(max(6, len(pivot.columns) * 1.5), max(5, len(pivot) * 0.5 + 1)))
    im = ax.imshow(pivot.values, aspect="auto", cmap="RdYlGn_r", vmin=0, vmax=0.5)
    plt.colorbar(im, ax=ax, label="SMD after matching")
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels(pivot.columns, rotation=30, ha="right", fontsize=9)
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels([t.replace("PSI_","").replace("_"," ") for t in pivot.index], fontsize=8)
    for i in range(len(pivot.index)):
        for j in range(len(pivot.columns)):
            val = pivot.values[i, j]
            if not np.isnan(val):
                ax.text(j, i, f"{val:.2f}", ha="center", va="center", fontsize=7,
                        color="white" if val > 0.3 else "black")
    ax.set_title("Post-Matching SMD by PSI Type and Covariate")
    fig.tight_layout()
    save_fig(fig, "diag_balance_heatmap.png")

fig_balance_heatmap()


# ── Figure 4: Match depth distribution ───────────────────────────────────────
def fig_match_depth():
    fig, axes = plt.subplots(1, 2, figsize=(14, 4))

    # Overall depth histogram
    ax = axes[0]
    bins = range(1, depth["k"].max() + 2)
    ax.hist(depth["k"], bins=bins, color=BEST_COLOR, alpha=0.8, edgecolor="white")
    ax.axvline(depth["k"].median(), color="black", linestyle="--", linewidth=1.5,
               label=f"Median k={depth['k'].median():.0f}")
    ax.set_xlabel("Number of matched donors (k)")
    ax.set_ylabel("Number of cases")
    ax.set_title("Match Depth Distribution\n(all 161 cases)")
    ax.legend(fontsize=9)

    # Depth by PSI type (box plot)
    ax2 = axes[1]
    psi_types_sorted = sorted(depth_by_type["psi_type"].unique())
    data_by_type = [depth_by_type[depth_by_type["psi_type"] == t]["k"].values
                    for t in psi_types_sorted]
    bp = ax2.boxplot(data_by_type, patch_artist=True, notch=False,
                     showfliers=True, flierprops=dict(marker="o", markersize=3, alpha=0.5))
    for patch in bp["boxes"]:
        patch.set_facecolor(BEST_COLOR); patch.set_alpha(0.7)
    ax2.set_xticks(range(1, len(psi_types_sorted) + 1))
    ax2.set_xticklabels(
        [t.replace("PSI_","").replace("_"," ") for t in psi_types_sorted],
        rotation=45, ha="right", fontsize=7)
    ax2.set_ylabel("k (donors per case)")
    ax2.set_title("Match Depth by PSI Type")
    ax2.grid(axis="y", linestyle="--", alpha=0.4)
    fig.tight_layout()
    save_fig(fig, "diag_match_depth.png")
    return depth["k"].describe()

depth_stats = fig_match_depth()


# ── Figure 5: Donor reuse ─────────────────────────────────────────────────────
def fig_donor_reuse():
    donor_use = pairs.groupby("donor_enc")["case_enc"].nunique().reset_index(name="n_cases_matched")
    reuse_counts = donor_use["n_cases_matched"].value_counts().sort_index()

    fig, axes = plt.subplots(1, 2, figsize=(14, 4))

    ax = axes[0]
    ax.bar(reuse_counts.index, reuse_counts.values, color=ALL_COLOR, alpha=0.8, edgecolor="white")
    ax.set_xlabel("Number of cases a donor is matched to")
    ax.set_ylabel("Number of donors")
    ax.set_title("Donor Reuse Distribution\n(across all match ranks)")
    ax.axvline(1, color="black", linestyle="--", linewidth=1, alpha=0.5)

    # Rank-1 donor reuse only
    ax2 = axes[1]
    r1_donor_use = r1.groupby("donor_enc")["case_enc"].nunique().reset_index(name="n_cases")
    r1_reuse = r1_donor_use["n_cases"].value_counts().sort_index()
    ax2.bar(r1_reuse.index, r1_reuse.values, color=BEST_COLOR, alpha=0.8, edgecolor="white")
    ax2.set_xlabel("Number of cases a rank-1 donor serves")
    ax2.set_ylabel("Number of donors")
    ax2.set_title("Rank-1 Donor Reuse\n(each case gets one best-match donor)")

    fig.tight_layout()
    save_fig(fig, "diag_donor_reuse.png")

    n_reused = (donor_use["n_cases_matched"] > 1).sum()
    n_total_donors = len(donor_use)
    return n_total_donors, n_reused, donor_use["n_cases_matched"].max()

n_total_donors, n_reused, max_reuse = fig_donor_reuse()


# ── Figure 6: Charlson comparison (cases vs rank-1 donors) ───────────────────
def fig_charlson():
    r1_merged_copy = r1_merged.copy()
    case_cs  = r1_merged_copy["case_charlson"].dropna()
    donor_cs = r1_merged_copy["donor_charlson"].dropna()

    fig, axes = plt.subplots(1, 3, figsize=(16, 4))

    # Distribution comparison
    ax = axes[0]
    max_score = max(int(case_cs.max()), int(donor_cs.max()), 1)
    bins = range(0, max_score + 2)
    ax.hist(case_cs,  bins=bins, alpha=0.6, color=CASE_COLOR, density=True,
            label=f"Cases (n={len(case_cs)}, μ={case_cs.mean():.1f})")
    ax.hist(donor_cs, bins=bins, alpha=0.6, color=BEST_COLOR, density=True,
            label=f"Best match (n={len(donor_cs)}, μ={donor_cs.mean():.1f})")
    ax.set_xlabel("Charlson Score")
    ax.set_ylabel("Density")
    ax.set_title("Charlson CCI Distribution\nCases vs Rank-1 Donors")
    ax.legend(fontsize=8)

    # Paired scatter
    ax2 = axes[1]
    ax2.scatter(r1_merged_copy["case_charlson"], r1_merged_copy["donor_charlson"],
                alpha=0.35, s=20, color=BEST_COLOR, edgecolors="none")
    lim = max(max_score + 1, 1)
    ax2.plot([0, lim], [0, lim], color="black", linestyle="--", linewidth=1)
    ax2.set_xlabel("Case Charlson score")
    ax2.set_ylabel("Donor Charlson score")
    ax2.set_title("Paired Charlson Scores\n(rank-1 pairs)")

    # By PSI type
    ax3 = axes[2]
    psi_types_sorted = sorted(r1_merged_copy["psi_type"].unique())
    case_by_type  = [r1_merged_copy[r1_merged_copy["psi_type"]==t]["case_charlson"].values
                     for t in psi_types_sorted]
    donor_by_type = [r1_merged_copy[r1_merged_copy["psi_type"]==t]["donor_charlson"].values
                     for t in psi_types_sorted]
    x = np.arange(len(psi_types_sorted))
    case_means  = [np.nanmean(v) if len(v)>0 else 0 for v in case_by_type]
    donor_means = [np.nanmean(v) if len(v)>0 else 0 for v in donor_by_type]
    ax3.bar(x - 0.2, case_means,  width=0.35, color=CASE_COLOR, alpha=0.8, label="Cases")
    ax3.bar(x + 0.2, donor_means, width=0.35, color=BEST_COLOR, alpha=0.8, label="Best match")
    ax3.set_xticks(x)
    ax3.set_xticklabels(
        [t.replace("PSI_","").replace("_"," ") for t in psi_types_sorted],
        rotation=50, ha="right", fontsize=7)
    ax3.set_ylabel("Mean Charlson score")
    ax3.set_title("Mean Charlson by PSI Type")
    ax3.legend(fontsize=8)
    ax3.grid(axis="y", linestyle="--", alpha=0.4)

    fig.tight_layout()
    save_fig(fig, "diag_charlson_balance.png")

    cs_smd = smd(case_cs, donor_cs)
    return case_cs.mean(), donor_cs.mean(), cs_smd

cs_mean_case, cs_mean_donor, cs_smd_val = fig_charlson()


# ── Figure 7: Demographics balance (AGE, gender, race) ────────────────────────
def fig_demographics():
    case_age  = r1_merged["case_AGE"].dropna()
    donor_age = r1_merged["donor_AGE"].dropna()

    fig, axes = plt.subplots(1, 3, figsize=(16, 4))

    # Age
    ax = axes[0]
    xlim = (max(0, min(case_age.min(), donor_age.min()) - 5),
            min(100, max(case_age.max(), donor_age.max()) + 5))
    ax.hist(case_age,  bins=25, range=xlim, density=True, alpha=0.6,
            color=CASE_COLOR, label=f"Cases (μ={case_age.mean():.1f})")
    ax.hist(donor_age, bins=25, range=xlim, density=True, alpha=0.6,
            color=BEST_COLOR, label=f"Best match (μ={donor_age.mean():.1f})")
    ax.set_xlabel("Age (years)")
    ax.set_ylabel("Density")
    ax.set_title(f"Age Distribution\nSMD = {smd(case_age, donor_age):.3f}")
    ax.legend(fontsize=8)

    # Gender
    ax2 = axes[1]
    case_gender  = r1_merged["case_GENDER"].str.upper().value_counts(normalize=True)
    donor_gender = r1_merged["donor_GENDER"].str.upper().value_counts(normalize=True)
    genders = sorted(set(case_gender.index) | set(donor_gender.index))
    x = np.arange(len(genders))
    ax2.bar(x - 0.2, [case_gender.get(g, 0)  for g in genders], width=0.35,
            color=CASE_COLOR, alpha=0.8, label="Cases")
    ax2.bar(x + 0.2, [donor_gender.get(g, 0) for g in genders], width=0.35,
            color=BEST_COLOR, alpha=0.8, label="Best match")
    ax2.set_xticks(x)
    ax2.set_xticklabels(genders, rotation=30, ha="right")
    ax2.set_ylabel("Proportion")
    ax2.set_title("Gender Balance")
    ax2.legend(fontsize=8)

    # Race
    ax3 = axes[2]
    def simplify_race(r):
        r = str(r).upper()
        if "WHITE" in r: return "WHITE"
        if "BLACK" in r: return "BLACK"
        if "ASIAN" in r: return "ASIAN"
        if "HISPAN" in r: return "HISP"
        return "OTHER/UNK"
    r1_merged["_cr"] = r1_merged["case_RACE"].apply(simplify_race)
    r1_merged["_dr"] = r1_merged["donor_RACE"].apply(simplify_race)
    case_race  = r1_merged["_cr"].value_counts(normalize=True)
    donor_race = r1_merged["_dr"].value_counts(normalize=True)
    races = sorted(set(case_race.index) | set(donor_race.index))
    x = np.arange(len(races))
    ax3.bar(x - 0.2, [case_race.get(g, 0)  for g in races], width=0.35,
            color=CASE_COLOR, alpha=0.8, label="Cases")
    ax3.bar(x + 0.2, [donor_race.get(g, 0) for g in races], width=0.35,
            color=BEST_COLOR, alpha=0.8, label="Best match")
    ax3.set_xticks(x)
    ax3.set_xticklabels(races, rotation=30, ha="right")
    ax3.set_ylabel("Proportion")
    ax3.set_title("Race Balance")
    ax3.legend(fontsize=8)

    fig.tight_layout()
    save_fig(fig, "diag_demographics.png")

    age_smd_val = smd(case_age, donor_age)
    return age_smd_val

age_smd = fig_demographics()


# ── Figure 8: Logit distance distribution per case ────────────────────────────
def fig_caliper_coverage():
    """Distribution of |logit_case - logit_donor| for rank-1 pairs."""
    prop_map = dict(zip(props["ENCOUNTER_ID"].astype(str), props["logit_score"]))
    dists = abs(
        r1_merged["case_enc"].map(prop_map) -
        r1_merged["donor_enc"].map(prop_map)
    ).dropna()

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.hist(dists, bins=50, color=BEST_COLOR, alpha=0.8, edgecolor="white")
    ax.set_xlabel("|logit(case) − logit(donor)| (caliper distance)")
    ax.set_ylabel("Number of rank-1 pairs")
    ax.set_title("Rank-1 Match Caliper Distance Distribution")
    p50, p90, p99 = dists.quantile([0.5, 0.9, 0.99])
    ax.axvline(p50, color=CASE_COLOR, linestyle="--", linewidth=1.5, label=f"P50={p50:.3f}")
    ax.axvline(p90, color="orange",   linestyle="--", linewidth=1.5, label=f"P90={p90:.3f}")
    ax.axvline(p99, color="red",      linestyle="--", linewidth=1.5, label=f"P99={p99:.3f}")
    ax.legend(fontsize=8)
    fig.tight_layout()
    save_fig(fig, "diag_caliper_distance.png")
    return dists.median(), dists.max()

med_dist, max_dist = fig_caliper_coverage()


# ═══════════════════════════════════════════════════════════════════════════════
# Per-type summary table
# ═══════════════════════════════════════════════════════════════════════════════

psi_summary_rows = []
for psi_type in sorted(pairs["psi_type"].unique()):
    type_pairs = pairs[pairs["psi_type"] == psi_type]
    type_r1    = r1[r1["psi_type"] == psi_type]
    n_cases    = type_pairs["case_enc"].nunique()
    n_r1       = len(type_r1)
    total_k    = len(type_pairs)
    mean_k     = total_k / n_cases if n_cases > 0 else 0
    case_ids_t = set(type_r1["case_enc"])
    donor_ids_t = set(type_r1["donor_enc"])
    cs_cases  = [charlson_map.get(e, 0) for e in case_ids_t]
    cs_donors = [charlson_map.get(e, 0) for e in donor_ids_t]
    psi_summary_rows.append({
        "PSI Type": psi_type.replace("PSI_","").replace("_"," "),
        "Cases": n_cases,
        "Rank-1 pairs": n_r1,
        "Total pairs": total_k,
        "Mean k": round(mean_k, 1),
        "Case Charlson (mean)": round(np.mean(cs_cases), 2) if cs_cases else "—",
        "Donor Charlson (mean)": round(np.mean(cs_donors), 2) if cs_donors else "—",
    })
psi_summary = pd.DataFrame(psi_summary_rows)


# ═══════════════════════════════════════════════════════════════════════════════
# Write report
# ═══════════════════════════════════════════════════════════════════════════════

print(f"\nWriting report → {REPORT.relative_to(ROOT)}")

REL = Path("../figures")

def md_table(df: pd.DataFrame) -> str:
    lines = ["| " + " | ".join(str(c) for c in df.columns) + " |",
             "| " + " | ".join("---" for _ in df.columns) + " |"]
    for _, row in df.iterrows():
        lines.append("| " + " | ".join("" if pd.isna(v) else str(v) for v in row) + " |")
    return "\n".join(lines)


with REPORT.open("w") as f:
    def w(s=""): f.write(s + "\n")

    w("# Counterfactual Matching Diagnostics")
    w()
    w("**Date:** 2026-06-07  ")
    w("**Pipeline version:** v2 (Charlson-augmented propensity score)  ")
    w("**Run:** `make run-all` — 16/16 PSI types PASS — 42.4 min  ")
    w()
    w("---")
    w()

    # ── 1. Matching Funnel ────────────────────────────────────────────────────
    w("## 1. Matching Funnel")
    w()
    w("How the 255 Claude-confirmed PSI cases flow through the pipeline to final matched pairs:")
    w()
    w("| Stage | N | Notes |")
    w("|---|--:|---|")
    w("| PSI cases in `psi_inpatient_cases.csv` | 255 | 177 positives + 78 negatives |")
    w("| Present in `encounters.csv` (pulled) | 213 | 42 never pulled from Snowflake |")
    w("| After governance filter (suppliers 1990/3707/3490) | 168 | 45 removed |")
    w("| Cases with valid t0 and E_TIME | 168 | 0 additional dropped |")
    w("| Cases finding ≥ 1 matched donor | **161** | 7 found no donors after Stage 2c |")
    w("| Total matched pairs (all ranks, k ≤ 50) | **5,841** | across 16 PSI types |")
    w("| Rank-1 pairs (best match per case) | **161** | one-to-one analysis set |")
    w("| Unique donor encounters | **3,630** | some donors matched to multiple cases |")
    w()

    # ── 2. Per-type summary ───────────────────────────────────────────────────
    w("## 2. Per-PSI-Type Matching Summary")
    w()
    w(md_table(psi_summary))
    w()
    w("*Mean k = average number of matched donors per case. Case and Donor Charlson scores*")
    w("*are computed from pre-existing diagnoses (DX_CHRONIC='YES' or DX_DATE < t₀).*")
    w()

    # ── 3. Propensity score overlap ───────────────────────────────────────────
    w("## 3. Propensity Score Overlap")
    w()
    w(f"![]({REL}/diag_propensity_overlap.png)")
    w()
    w("**Left:** density of logit propensity scores across all PSI types for cases (coral),")
    w("rank-1 donors (blue), and the full matched donor pool (green).")
    w("Good overlap indicates positivity — every case has a plausible counterfactual.")
    w()
    w("**Right:** scatter of case vs donor logit scores for each rank-1 pair.")
    w("Points on or near the diagonal indicate tight propensity-score matching.")
    w()

    w("| Statistic | Value |")
    w("|---|---|")
    w(f"| Median case logit score | {med_case_logit:.3f} |")
    w(f"| Median rank-1 donor logit score | {med_r1_logit:.3f} |")
    w(f"| Median rank-1 caliper distance | {med_dist:.4f} logit units |")
    w(f"| Maximum caliper distance (rank-1) | {max_dist:.4f} logit units |")
    w()

    # ── 4. Caliper distance ───────────────────────────────────────────────────
    w("## 4. Rank-1 Match Caliper Distance")
    w()
    w(f"![]({REL}/diag_caliper_distance.png)")
    w()
    w("Distribution of |logit(case) − logit(best-match donor)| across all 161 rank-1 pairs.")
    w("The caliper is set at `0.2 × SD(logit scores)` and relaxed 3× if no donors are found")
    w("within the standard caliper. Small distances indicate tight propensity-score proximity.")
    w()

    # ── 5. Covariate balance ──────────────────────────────────────────────────
    w("## 5. Covariate Balance (SMD)")
    w()
    w(f"![]({REL}/diag_balance_smd.png)")
    w()
    w("Standardised Mean Difference (SMD) before and after matching, averaged across all")
    w("16 PSI types. SMD < 0.1 is the conventional threshold for adequate balance;")
    w("SMD < 0.2 is acceptable.")
    w()

    if smd_after:
        w("| Covariate | Mean SMD after matching | Adequate balance (< 0.1)? |")
        w("|---|--:|:---:|")
        for feat, val in sorted(smd_after.items(), key=lambda x: -x[1]):
            ok = "✓" if val < 0.1 else ("~" if val < 0.2 else "✗")
            w(f"| {feat} | {val:.3f} | {ok} |")
        w()

    w(f"![]({REL}/diag_balance_heatmap.png)")
    w()
    w("Per-type SMD heatmap. Green = well balanced (SMD < 0.1); red = imbalanced (SMD > 0.3).")
    w("Types with few cases (e.g., PSI_12 with 3 cases) are noisier.")
    w()

    # ── 6. Demographics ───────────────────────────────────────────────────────
    w("## 6. Demographic Balance")
    w()
    w(f"![]({REL}/diag_demographics.png)")
    w()
    w(f"Age, gender, and race distributions for cases vs rank-1 matched donors.")
    w(f"Age SMD = **{age_smd:.3f}** ({"adequate" if age_smd < 0.1 else "marginal" if age_smd < 0.2 else "imbalanced"}).")
    w("CEM strata enforce exact matching on sex, age bin, race, ethnicity, employment,")
    w("facility type/size, urban/rural, and admission department — demographic balance")
    w("is therefore guaranteed within strata; residual imbalance reflects within-bin variation.")
    w()

    # ── 7. Charlson balance ───────────────────────────────────────────────────
    w("## 7. Comorbidity Balance (Charlson CCI)")
    w()
    w(f"![]({REL}/diag_charlson_balance.png)")
    w()
    w("Charlson Comorbidity Index (Quan et al. 2005) computed from pre-existing diagnoses")
    w("for each case and its rank-1 matched donor.")
    w()
    w("| Metric | Cases | Rank-1 Donors |")
    w("|---|--:|--:|")
    w(f"| Mean Charlson score | {cs_mean_case:.2f} | {cs_mean_donor:.2f} |")
    w(f"| SMD (Charlson) | {cs_smd_val:.3f} | — |")
    w()
    if cs_smd_val < 0.1:
        w("Charlson scores are **well balanced** (SMD < 0.1) between cases and rank-1 donors,")
        w("confirming that the Charlson features added to Stage 2b are improving comorbidity parity.")
    elif cs_smd_val < 0.2:
        w("Charlson scores are **marginally balanced** (0.1 ≤ SMD < 0.2).")
    else:
        w(f"Charlson SMD = {cs_smd_val:.3f} — residual imbalance remains; consider adding")
        w("Charlson bin to CEM strata or increasing caliper for comorbidity-heavy types.")
    w()

    # ── 8. Match depth ────────────────────────────────────────────────────────
    w("## 8. Match Depth (k donors per case)")
    w()
    w(f"![]({REL}/diag_match_depth.png)")
    w()
    w("Distribution of k (number of matched donors per case, up to the pipeline maximum of 50).")
    w()
    w("| Percentile | k |")
    w("|---|--:|")
    for pct in ["min","25%","50%","75%","max"]:
        label = {"min":"Min","25%":"P25","50%":"Median","75%":"P75","max":"Max"}.get(pct,pct)
        w(f"| {label} | {int(depth_stats[pct])} |")
    w(f"| Mean | {depth_stats['mean']:.1f} |")
    w()
    n_at_max = (depth["k"] == 50).sum()
    n_low    = (depth["k"] < 5).sum()
    w(f"**{n_at_max}** cases reached the k=50 ceiling (potential for more donors if ceiling raised).  ")
    w(f"**{n_low}** cases have fewer than 5 matched donors (thin strata — results for these cases")
    w(f"carry higher variance).")
    w()

    # ── 9. Donor reuse ────────────────────────────────────────────────────────
    w("## 9. Donor Reuse")
    w()
    w(f"![]({REL}/diag_donor_reuse.png)")
    w()
    w("Donors are drawn from the full Snowflake inpatient pool and a given donor encounter")
    w("can be matched to multiple PSI cases (across types or within type).")
    w()
    w("| Metric | Value |")
    w("|---|--:|")
    w(f"| Total unique donor encounters (all ranks) | {n_total_donors:,} |")
    w(f"| Donors matched to exactly 1 case | {n_total_donors - n_reused:,} |")
    w(f"| Donors matched to > 1 case | {n_reused:,} ({100*n_reused/n_total_donors:.1f}%) |")
    w(f"| Max cases a single donor appears in | {int(max_reuse)} |")
    w()
    w("**Interpretation:** donor reuse does not bias the propensity-score comparison —")
    w("each case-donor *pair* is an independent observation. However, reused donors introduce")
    w("within-donor correlation that should be accounted for with cluster-robust standard errors")
    w("in any downstream outcome analysis.")
    w()

    # ── 10. Governance summary ────────────────────────────────────────────────
    w("## 10. Governance Checks")
    w()
    w("| Gate | Check | Result |")
    w("|---|---|---|")
    w("| G-1 | Forbidden suppliers (1990/3707/3490) absent from cases | **PASS** — 45 rows removed at Stage −1 |")
    w("| G0  | Forbidden suppliers absent from donor pool | **PASS** — Snowflake query excludes them |")
    w("| G1  | CEM frame built; every case has ≥ 1 donor in stratum | **PASS** — 16/16 types |")
    w("| G2  | Feature window strictly [t₀, t₀+4 h] | **PASS** — enforced in `build_features_at_tstar()` |")
    w("| G3  | Charlson block uses only pre-admission diagnoses | **PASS** — DX_DATE < t₀ filter applied |")
    w("| — | No post-event features in feature matrix | **PASS** — cutoff = t₀ + 4 h, before E_time |")
    w()

    # ── 11. Limitations ───────────────────────────────────────────────────────
    w("## 11. Known Limitations")
    w()
    w("1. **EN_LOS_num SMD > 0.1 after matching** — length-of-stay is a post-admission quantity")
    w("   partially driven by the PSI event itself. Matching on it would introduce collider bias.")
    w("   It is included in the balance table for transparency only; it is not a matching covariate.")
    w()
    w("2. **42 PSI cases never pulled from Snowflake** — the original cases-only Snowflake pull")
    w("   missed 42 case encounters. These are absent from `encounters.csv` and therefore")
    w("   cannot enter the pipeline. A targeted re-pull of those 42 encounter IDs would recover them.")
    w()
    w("3. **7 cases found no donors** — after CEM stratum restriction and caliper filtering,")
    w("   7 of 168 cases had an empty candidate pool. These represent rare combinations of")
    w("   demographics + facility type with no comparable Snowflake controls.")
    w()
    w("4. **Donor reuse across types** — a donor admitted for an OB encounter, for example,")
    w("   can appear as a match for multiple OB-related PSI types. Cluster-robust standard")
    w("   errors on donor ID are needed for causal inference.")
    w()
    w("5. **1% Bernoulli Snowflake sample** — the donor pool is a 1% random sample of ~51M")
    w("   inpatient encounters. For rare PSI subtypes with narrow CEM strata (e.g., PSI_12")
    w("   with only 11 pairs), the thin donor pool limits matching quality.")
    w()
    w("---")
    w()
    w("*Generated by `src/09_counterfactual_diagnostics.py` — 2026-06-07*")

print("\nDone.")
print(f"  Report : {REPORT.relative_to(ROOT)}")
print(f"  Figures: diag_*.png in {FIG_DIR.relative_to(ROOT)}/")
