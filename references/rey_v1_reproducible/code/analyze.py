"""
Analysis + statistical power for Project Bayes eval results.

Reads:
  - eval_output/per_case_scores.csv
  - eval_output/criteria_long.csv

Produces:
  - eval_output/analysis/cell_summary.csv       — per (tier, los, prompt) means + CIs
  - eval_output/analysis/judge_agreement.csv    — per-cell Cohen's κ on criterion answers
  - eval_output/analysis/power.csv              — MDE per cell comparison
  - eval_output/analysis/*.png                  — heatmap, bars, distributions
  - eval_output/analysis/RESULTS.md             — narrative summary

Run after the pilot (or full run) completes:
    python3 analyze.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


EVAL_OUT = Path(__file__).parent / "eval_output"
PER_CASE = EVAL_OUT / "per_case_scores.csv"
CRIT_LONG = EVAL_OUT / "criteria_long.csv"
ANALYSIS_DIR = EVAL_OUT / "analysis"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def bootstrap_ci(values: np.ndarray, n_boot: int = 1000, ci: float = 0.95) -> tuple[float, float]:
    """Bootstrap confidence interval for the mean."""
    if len(values) == 0:
        return (np.nan, np.nan)
    rng = np.random.default_rng(42)
    boots = [rng.choice(values, size=len(values), replace=True).mean() for _ in range(n_boot)]
    lower = float(np.percentile(boots, (1 - ci) / 2 * 100))
    upper = float(np.percentile(boots, (1 + ci) / 2 * 100))
    return (lower, upper)


def cohens_kappa_binary(a: list, b: list) -> float:
    """Cohen's κ for two raters with binary labels (yes/no)."""
    if len(a) != len(b) or len(a) == 0:
        return np.nan
    a = ["yes" if str(x).lower().startswith("y") else "no" for x in a]
    b = ["yes" if str(x).lower().startswith("y") else "no" for x in b]
    n = len(a)
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    pa_y = sum(1 for x in a if x == "yes") / n
    pb_y = sum(1 for x in b if x == "yes") / n
    pe = pa_y * pb_y + (1 - pa_y) * (1 - pb_y)
    if pe >= 1.0:
        return np.nan
    return (po - pe) / (1 - pe)


def cohens_d(a: np.ndarray, b: np.ndarray) -> float:
    """Cohen's d effect size between two groups."""
    if len(a) < 2 or len(b) < 2:
        return np.nan
    sa, sb = a.std(ddof=1), b.std(ddof=1)
    pooled = np.sqrt(((len(a) - 1) * sa**2 + (len(b) - 1) * sb**2) / (len(a) + len(b) - 2))
    if pooled == 0:
        return np.nan
    return (a.mean() - b.mean()) / pooled


def mde_for_n(n: int, alpha: float = 0.05, power: float = 0.8) -> float:
    """Minimum detectable effect size (Cohen's d) for a two-sample test with equal n."""
    # Standard approximation: d_min ≈ (z_alpha/2 + z_beta) * sqrt(2/n)
    from math import sqrt
    z_alpha = 1.96  # alpha=0.05 two-sided
    z_beta = 0.84   # power=0.80
    return (z_alpha + z_beta) * sqrt(2 / n)


# ---------------------------------------------------------------------------
# Per-cell summary
# ---------------------------------------------------------------------------


def cell_summary(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (tier, los, prompt), grp in df.groupby(["complexity_tier", "los_bucket", "prompt_id"]):
        scores = grp["score_mean"].dropna().to_numpy()
        if len(scores) == 0:
            continue
        ci_lo, ci_hi = bootstrap_ci(scores)
        rows.append({
            "complexity_tier": tier,
            "los_bucket": los,
            "prompt_id": prompt,
            "n": len(scores),
            "mean_score": scores.mean(),
            "median_score": float(np.median(scores)),
            "std_score": scores.std(ddof=1) if len(scores) > 1 else np.nan,
            "ci_lo": ci_lo,
            "ci_hi": ci_hi,
            "sonnet_mean": grp["score_sonnet"].dropna().mean(),
            "gpt_mean": grp["score_gpt"].dropna().mean(),
            "delta_mean": grp["judge_delta"].dropna().mean(),
            "universal_mean": grp["score_universal_sonnet"].dropna().mean(),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Judge agreement
# ---------------------------------------------------------------------------


def judge_agreement(crit: pd.DataFrame, case_scores: pd.DataFrame) -> pd.DataFrame:
    """For each (cell, prompt), compute Cohen's κ between judges on criterion answers."""
    crit = crit.merge(
        case_scores[["encounter_id", "prompt_id", "complexity_tier", "los_bucket"]],
        on=["encounter_id", "prompt_id"], how="left"
    )
    rows = []
    for (tier, los, prompt), grp in crit.groupby(["complexity_tier", "los_bucket", "prompt_id"]):
        # Pivot to (case, criterion) × judge
        pivoted = grp.pivot_table(
            index=["encounter_id", "criterion_id"],
            columns="judge",
            values="answer",
            aggfunc="first",
        )
        judges = pivoted.columns.tolist()
        if len(judges) < 2:
            rows.append({
                "complexity_tier": tier, "los_bucket": los, "prompt_id": prompt,
                "n_pairs": len(pivoted), "kappa": np.nan,
                "judges": ",".join(judges) if judges else "",
            })
            continue
        # Sort judge names for stability
        j1, j2 = sorted(judges)[:2]
        a, b = pivoted[j1].dropna().tolist(), pivoted[j2].dropna().tolist()
        kappa = cohens_kappa_binary(a, b)
        rows.append({
            "complexity_tier": tier, "los_bucket": los, "prompt_id": prompt,
            "n_pairs": len(pivoted), "kappa": kappa,
            "judges": f"{j1} vs {j2}",
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Power analysis
# ---------------------------------------------------------------------------


def power_table(case_scores: pd.DataFrame) -> pd.DataFrame:
    """For each cell × prompt, report MDE at the actual n."""
    rows = []
    cells = case_scores.groupby(["complexity_tier", "los_bucket", "prompt_id"]).size().reset_index(name="n")
    for _, row in cells.iterrows():
        n = int(row["n"])
        mde_d = mde_for_n(n)
        # Approximate MDE on the [0,1] score scale assuming sd ≈ 0.3 (will refine after run)
        scores = case_scores[
            (case_scores["complexity_tier"] == row["complexity_tier"]) &
            (case_scores["los_bucket"] == row["los_bucket"]) &
            (case_scores["prompt_id"] == row["prompt_id"])
        ]["score_mean"].dropna()
        sd = scores.std(ddof=1) if len(scores) > 1 else 0.3
        mde_score = mde_d * sd if not np.isnan(sd) else np.nan
        rows.append({
            "complexity_tier": row["complexity_tier"],
            "los_bucket": row["los_bucket"],
            "prompt_id": row["prompt_id"],
            "n": n,
            "observed_sd": round(sd, 3) if not np.isnan(sd) else None,
            "mde_cohens_d": round(mde_d, 3),
            "mde_score_units": round(mde_score, 3) if not np.isnan(mde_score) else None,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Visualization
# ---------------------------------------------------------------------------


def make_plots(case_scores: pd.DataFrame, cell_df: pd.DataFrame) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed — skipping plots")
        return

    ANALYSIS_DIR.mkdir(exist_ok=True, parents=True)

    # 1) Cell heatmap: mean score per (tier, los, prompt) — one heatmap per prompt
    for prompt_id in case_scores["prompt_id"].unique():
        sub = case_scores[case_scores["prompt_id"] == prompt_id]
        pivot = sub.groupby(["complexity_tier", "los_bucket"])["score_mean"].mean().unstack()
        if pivot.empty:
            continue
        fig, ax = plt.subplots(figsize=(6, 4))
        im = ax.imshow(pivot.values, vmin=0, vmax=1, cmap="RdYlGn", aspect="auto")
        ax.set_xticks(range(len(pivot.columns)))
        ax.set_xticklabels(pivot.columns)
        ax.set_yticks(range(len(pivot.index)))
        ax.set_yticklabels(pivot.index)
        ax.set_xlabel("LOS bucket")
        ax.set_ylabel("Complexity tier")
        ax.set_title(f"{prompt_id} mean score by cell")
        for i in range(len(pivot.index)):
            for j in range(len(pivot.columns)):
                v = pivot.values[i, j]
                if not np.isnan(v):
                    ax.text(j, i, f"{v:.2f}", ha="center", va="center",
                            color="white" if v < 0.4 else "black")
        plt.colorbar(im, ax=ax)
        plt.tight_layout()
        plt.savefig(ANALYSIS_DIR / f"heatmap_{prompt_id}.png", dpi=120)
        plt.close()

    # 2) Per-prompt bar chart of mean scores across cells
    fig, ax = plt.subplots(figsize=(10, 5))
    cells = case_scores.groupby(["complexity_tier", "los_bucket", "prompt_id"])["score_mean"].mean().reset_index()
    cells["cell"] = cells["complexity_tier"] + "/" + cells["los_bucket"]
    for prompt_id in cells["prompt_id"].unique():
        sub = cells[cells["prompt_id"] == prompt_id]
        ax.bar(sub["cell"] + f" / {prompt_id}", sub["score_mean"], label=prompt_id)
    ax.set_ylabel("Mean score")
    ax.set_ylim(0, 1)
    ax.set_xticklabels([], rotation=45, ha="right")
    ax.set_title("Per-cell mean score by prompt")
    ax.legend()
    plt.tight_layout()
    plt.savefig(ANALYSIS_DIR / "bars_by_cell_prompt.png", dpi=120)
    plt.close()

    # 3) Score distribution histograms per prompt
    prompts = case_scores["prompt_id"].unique()
    fig, axes = plt.subplots(1, len(prompts), figsize=(4 * len(prompts), 3.5), sharey=True)
    if len(prompts) == 1:
        axes = [axes]
    for ax, pid in zip(axes, prompts):
        ax.hist(case_scores[case_scores["prompt_id"] == pid]["score_mean"].dropna(),
                bins=10, range=(0, 1), edgecolor="black")
        ax.set_title(pid)
        ax.set_xlabel("score_mean")
    axes[0].set_ylabel("count")
    plt.tight_layout()
    plt.savefig(ANALYSIS_DIR / "score_distributions.png", dpi=120)
    plt.close()

    # 4) Judge agreement scatter (sonnet vs gpt per case)
    has_both = case_scores.dropna(subset=["score_sonnet", "score_gpt"])
    if not has_both.empty:
        fig, ax = plt.subplots(figsize=(5, 5))
        ax.scatter(has_both["score_sonnet"], has_both["score_gpt"], alpha=0.5)
        ax.plot([0, 1], [0, 1], "k--", alpha=0.3)
        ax.set_xlabel("Sonnet score")
        ax.set_ylabel("GPT score")
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.set_title(f"Judge agreement (n={len(has_both)})")
        plt.tight_layout()
        plt.savefig(ANALYSIS_DIR / "judge_agreement_scatter.png", dpi=120)
        plt.close()


# ---------------------------------------------------------------------------
# Summary markdown
# ---------------------------------------------------------------------------


def write_results_md(case_scores: pd.DataFrame, cell_df: pd.DataFrame,
                     kappa_df: pd.DataFrame, power_df: pd.DataFrame,
                     total_cost: float) -> None:
    md = []
    md.append("# Project Bayes — Eval Results")
    md.append("")
    md.append(f"**Cases evaluated**: {case_scores['encounter_id'].nunique()}")
    md.append(f"**Prompts tested**: {sorted(case_scores['prompt_id'].unique())}")
    md.append(f"**Cells covered**: {sorted(set(zip(case_scores['complexity_tier'], case_scores['los_bucket'])))}")
    md.append(f"**Total LLM cost**: ${total_cost:.2f}")
    md.append("")

    md.append("## Per-cell mean score by prompt")
    md.append("")
    pivot = case_scores.pivot_table(
        index=["complexity_tier", "los_bucket"],
        columns="prompt_id",
        values="score_mean",
        aggfunc="mean",
    ).round(3)
    md.append(pivot.to_markdown())
    md.append("")

    md.append("## Cell × prompt detail (n, mean, 95% CI, judge disagreement)")
    md.append("")
    md.append(cell_df.round(3).to_markdown(index=False))
    md.append("")

    md.append("## Judge agreement (Cohen's κ on criterion-level answers)")
    md.append("")
    md.append("Interpretation: κ < 0.4 weak, 0.4–0.6 moderate, 0.6–0.8 substantial, > 0.8 strong.")
    md.append("")
    md.append(kappa_df.round(3).to_markdown(index=False))
    md.append("")

    md.append("## Statistical power per cell × prompt")
    md.append("")
    md.append("MDE = minimum detectable effect (Cohen's d) at α=0.05, power=0.80.")
    md.append("With n=10 per cell, MDE ≈ 1.32 d (large effect required).")
    md.append("With n=30 per cell, MDE ≈ 0.74 d (medium effect detectable).")
    md.append("")
    md.append(power_df.round(3).to_markdown(index=False))
    md.append("")

    md.append("## Universal criteria across all responses")
    md.append("")
    univ_summary = case_scores.groupby("prompt_id")[
        ["score_universal_sonnet", "score_universal_gpt"]
    ].mean().round(3)
    md.append(univ_summary.to_markdown())
    md.append("")

    md.append("## Files produced")
    md.append("")
    md.append("- `per_case_scores.csv` — wide format, one row per (case, prompt)")
    md.append("- `criteria_long.csv` — long format, one row per (case, prompt, judge, criterion)")
    md.append("- `analysis/cell_summary.csv`")
    md.append("- `analysis/judge_agreement.csv`")
    md.append("- `analysis/power.csv`")
    md.append("- `analysis/heatmap_*.png` (one per prompt)")
    md.append("- `analysis/bars_by_cell_prompt.png`")
    md.append("- `analysis/score_distributions.png`")
    md.append("- `analysis/judge_agreement_scatter.png`")

    (ANALYSIS_DIR / "RESULTS.md").write_text("\n".join(md))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    if not PER_CASE.exists():
        print(f"per_case_scores.csv not found at {PER_CASE}. Run run_eval.py first.")
        return
    case_scores = pd.read_csv(PER_CASE)
    crit = pd.read_csv(CRIT_LONG) if CRIT_LONG.exists() else pd.DataFrame()
    total_cost = float(case_scores["total_cost_usd"].sum()) if "total_cost_usd" in case_scores else 0.0

    ANALYSIS_DIR.mkdir(exist_ok=True, parents=True)

    print(f"Loaded {len(case_scores)} per-case rows, {len(crit)} criterion rows")
    print(f"Total cost: ${total_cost:.2f}\n")

    cell_df = cell_summary(case_scores)
    cell_df.to_csv(ANALYSIS_DIR / "cell_summary.csv", index=False)

    if not crit.empty:
        kappa_df = judge_agreement(crit, case_scores)
        kappa_df.to_csv(ANALYSIS_DIR / "judge_agreement.csv", index=False)
    else:
        kappa_df = pd.DataFrame()

    power_df = power_table(case_scores)
    power_df.to_csv(ANALYSIS_DIR / "power.csv", index=False)

    make_plots(case_scores, cell_df)
    write_results_md(case_scores, cell_df, kappa_df, power_df, total_cost)

    print("Analysis complete. See:")
    print(f"  {ANALYSIS_DIR / 'RESULTS.md'}")
    print(f"  {ANALYSIS_DIR} (CSVs + PNG plots)")


if __name__ == "__main__":
    main()
