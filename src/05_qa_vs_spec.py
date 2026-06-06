#!/usr/bin/env python3
"""
QA script: compare PSI_counterfactual_pipeline.py against PROTEGE___Evaluating_LLMs.pdf

Each check is a standalone function returning (passed: bool, detail: str).
Run with:
    python src/05_qa_vs_spec.py
"""

import ast, re, sys, textwrap
from pathlib import Path

PIPELINE = Path("src/02_counterfactual_pipeline.py")
assert PIPELINE.exists(), f"Cannot find {PIPELINE}"

src = PIPELINE.read_text()
PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"   # deviation that is intentional / pre-approved

results = []

def check(name, status, detail):
    results.append((name, status, detail))
    marker = {"PASS": "✓", "FAIL": "✗", "WARN": "△"}[status]
    print(f"  {marker} [{status}] {name}")
    if status != "PASS":
        for line in textwrap.wrap(detail, width=90, initial_indent="      ", subsequent_indent="      "):
            print(line)

print("=" * 70)
print("PSI Pipeline QA — spec: PROTEGE___Evaluating_LLMs.pdf")
print("=" * 70)
print()

# ─────────────────────────────────────────────────────────────────────────────
print("STAGE 0 — Governance & Temporal Structure")
# ─────────────────────────────────────────────────────────────────────────────

# 0a. Forbidden supplier 1990 (Advocate Aurora)
ok = "1990" in src and "FORBIDDEN_SUPPLIERS" in src
check(
    "Forbidden supplier 1990 (Advocate Aurora) excluded",
    PASS if ok else FAIL,
    "FORBIDDEN_SUPPLIERS list must include 1990 per spec §0"
)

# 0b. Forbidden suppliers 3707 and 3490
ok = "3707" in src and "3490" in src
check(
    "Forbidden suppliers 3707 and 3490 excluded",
    PASS if ok else FAIL,
    "Spec §0: remove 3707 (Jan-1 placeholder dates) and 3490 (partial lab corruption)"
)

# 0c. Grid spacing Δ = 4 hours
m = re.search(r'"GRID_HOURS"\s*:\s*(\d+)', src)
grid_h = int(m.group(1)) if m else None
ok = grid_h == 4
check(
    f"Temporal grid spacing Δ = 4 hours (found {grid_h}h)",
    PASS if ok else FAIL,
    "Spec §Temporal: stay clock t ∈ {0,1,2,...} with Δ = 4 hours"
)

# 0d. Blanking window b = 6 grid steps (24h)
m = re.search(r'"B_GRID"\s*:\s*(\d+)', src)
b_grid = int(m.group(1)) if m else None
ok = b_grid == 6
check(
    f"Blanking window b = 6 grid steps = 24h (found {b_grid})",
    PASS if ok else FAIL,
    "Spec §Temporal: b = 6 grid steps; sweep sensitivity at b ∈ {3,6,9}"
)

# 0e. Landmark t* = E_i − B_GRID
ok = "E_i" in src and "B_GRID" in src and 't_star' in src and "E_i - CONFIG" in src or 'E_i"] - CONFIG' in src
ok = bool(re.search(r'E_i.*-.*B_GRID|t_star.*=.*E_i\s*-', src))
check(
    "Landmark t* = E_i − B_GRID",
    PASS if ok else FAIL,
    "Spec §Temporal: t*ᵢ = Eᵢ − b"
)

# 0f. Risk set uses donors still admitted at t*
ok = "grid_LOS" in src and "risk_set" in src
check(
    "Risk set R(t*): donors still admitted at landmark t*",
    PASS if ok else FAIL,
    "Spec Assumption 1: donor j eligible only if j ∈ R(t*ᵢ) — still admitted and event-free"
)

# 0g. Donors with negative LOS dropped
ok = "grid_LOS >= 0" in src or "grid_LOS < 0" in src
check(
    "Negative LOS donors dropped (data quality filter)",
    PASS if ok else FAIL,
    "Spec §0: non-null EN_START_DATE and sensible LOS required"
)

# 0h. Information set append-only (no future data in features)
# Check that feature window uses cutoff (upper bound) without look-ahead
ok = "cutoff" in src and "<= cutoff" in src
check(
    "Feature window is append-only (records ≤ cutoff only)",
    PASS if ok else FAIL,
    "Spec Definition 1: information set is append-only — each datum time-stamped by availability"
)

print()

# ─────────────────────────────────────────────────────────────────────────────
print("STAGE 1 — CEM Key & Coarsening")
# ─────────────────────────────────────────────────────────────────────────────

# 1a. Sex in CEM key
ok = bool(re.search(r'GENDER.*CEM|make_cem_key.*GENDER|GENDER.*cem', src, re.I))
ok = 'row["GENDER"]' in src or "GENDER" in src and "make_cem_key" in src
check(
    "Sex (GENDER) in CEM key",
    PASS if ok else FAIL,
    "Spec Stage 1: sex is one of the 5 required CEM key variables"
)

# 1b. Age band in CEM key
ok = "age_bin" in src and "AGE_BIN" in src
check(
    "Age band (AGE_BIN) in CEM key",
    PASS if ok else FAIL,
    "Spec Stage 1: broad age band in CEM key"
)

# 1c. Age bins match spec (0-17, 18-44, 45-64, 65-79, 80+)
has_bins = all(x in src for x in ["18", "45", "65", "80"])
check(
    "Age bins: 0-17, 18-44, 45-64, 65-79, 80+",
    PASS if has_bins else FAIL,
    "Spec Stage 1: clinically meaningful age intervals"
)

# 1d. Facility type in CEM key
ok = "FAC_TYPE" in src and "EN_FACILITY_TYPE" in src
check(
    "Facility type (EN_FACILITY_TYPE) in CEM key",
    PASS if ok else FAIL,
    "Spec Stage 1: facility type is a required CEM key variable"
)

# 1e. Urban/rural in CEM key
ok = "URBAN_BIN" in src and "EN_URBAN_RURAL" in src
check(
    "Urban/rural (EN_URBAN_RURAL) in CEM key",
    PASS if ok else FAIL,
    "Spec Stage 1: urban/rural designation is a required CEM key variable"
)

# 1f. Admission department in CEM key
ok = "ADM_DEPT_GRP" in src and "EN_ADM_DEPT" in src
check(
    "Admission department (EN_ADM_DEPT) in CEM key",
    PASS if ok else FAIL,
    "Spec Stage 1: admission department is a required CEM key variable"
)

# 1g. Spec says ONLY 5 variables in CEM key; check whether extra vars added
cem_key_vars = re.findall(r'row\.get\("([^"]+)"', src[src.find("make_cem_key"):src.find("make_cem_key")+800])
extra = [v for v in cem_key_vars if v not in ("AGE_BIN","FAC_TYPE","URBAN_BIN","ADM_DEPT_GRP")]
spec_5 = {"GENDER (via row[\"GENDER\"])": True}
n_cem_vars = len(cem_key_vars) + 1  # +1 for GENDER which uses row["GENDER"]
ok = n_cem_vars == 5
check(
    f"CEM key has exactly 5 variables per spec (found {n_cem_vars}: {cem_key_vars + ['GENDER']})",
    WARN if not ok else PASS,
    "Spec Stage 1: exact-match key = sex, age band, facility type, urban/rural, admission dept. "
    "Code adds RACE_GRP, ETHNICITY_BIN, EMPLOY_BIN, FAC_SIZE, DEPT_GRP (5 extras). "
    "This is an intentional extension — see deviations doc."
)

# 1h. Missingness-as-information: explicit MISSING category
ok = "__MISSING__" in src or '"MISSING"' in src
check(
    "Missingness-as-information: explicit MISSING category in coarsening",
    PASS if ok else FAIL,
    "Spec Remark 2: add explicit missing category to each coarsened variable"
)

# 1i. SDOH not used as primary matching variable (spec says description only)
# The spec says SDOH should not be in the exact key. EMPLOY and RACE could be considered SDOH.
# We flag this for review.
has_employ_in_cem = "EMPLOY_BIN" in src and "make_cem_key" in src
check(
    "SDOH variables (EMPLOY, RACE, ETHNICITY) not in CEM exact-match key",
    WARN,
    "Spec Stage 1: 'Do NOT include SDOH in exact key (present for negligible fraction of admissions, "
    "would empty strata)'. Code includes RACE_GRP, ETHNICITY_BIN, EMPLOY_BIN in the key. "
    "These are intentional additions (see deviations doc). Monitor for stratum sparsity."
)

print()

# ─────────────────────────────────────────────────────────────────────────────
print("STAGE 2a — Feature Engineering (Clinical History)")
# ─────────────────────────────────────────────────────────────────────────────

# 2a-i. Lab observation indicator R (presence feature)
ok = "lab_" in src and "_R" in src and "feats[f\"lab_" in src
check(
    "Lab observation indicator R^lab_itk (presence feature)",
    PASS if ok else FAIL,
    "Spec §2a: L^lab_it = R^lab_it ⊙ M^lab_it; R indicator must be included"
)

# 2a-ii. Lab last value
ok = "lab_" in src and "_last" in src
check(
    "Lab last value within window",
    PASS if ok else FAIL,
    "Spec §2a: summarize lab trajectory by last value"
)

# 2a-iii. Lab min/max
ok = "_min" in src and "_max" in src and "lab_" in src
check(
    "Lab min/max within window",
    PASS if ok else FAIL,
    "Spec §2a: summarize lab trajectory by min/max"
)

# 2a-iv. Lab abnormal count
ok = "_n_abn" in src or "ABN_RESULT" in src
check(
    "Lab abnormal-flag count",
    PASS if ok else FAIL,
    "Spec §2a: count of abnormal flags per analyte"
)

# 2a-v. Lab slope — SPEC REQUIRES, check implementation
ok = "_slope" in src and "lab_" in src
check(
    "Lab slope (trend) within window",
    FAIL if not ok else PASS,
    "Spec §2a: slope is an explicit required lab summary feature. NOT implemented — "
    "code has last/min/max/count but no slope calculation."
)

# 2a-vi. Lab time-since-last-result — SPEC REQUIRES
ok = "time_since" in src or "_tsl" in src
check(
    "Lab time-since-last result within window",
    FAIL if not ok else PASS,
    "Spec §2a: time-since-last result is an explicit required lab summary feature. NOT implemented."
)

# 2a-vii. Vitals: last value
ok = "vit_" in src and "_last" in src
check(
    "Vital sign last value within window",
    PASS if ok else FAIL,
    "Spec §2a: vitals summarized same as labs: last value"
)

# 2a-viii. Vitals: slope — SPEC REQUIRES
ok = "vit_" in src and "_slope" in src
check(
    "Vital sign slope within window",
    FAIL if not ok else PASS,
    "Spec §2a: vitals slope is required (same summarization as labs). NOT implemented."
)

# 2a-ix. Vitals: abnormal counts — SPEC REQUIRES
# Must appear specifically for vitals (VS_), not just any _abn elsewhere
ok = bool(re.search(r'vit_.*_abn|VS_.*ABN|vs.*abnorm', src, re.I)) and "feats[f\"vit_" in src and "abn" in src[src.find("# ── Vitals"):src.find("# ── Vitals")+500]
check(
    "Vital sign abnormal count",
    FAIL if not ok else PASS,
    "Spec §2a: vitals abnormal counts required. NOT implemented — code has last/min/max only."
)

# 2a-x. Procedures: presence (sparse code set)
ok = "px_" in src and "PX_CODE" in src
check(
    "Procedures: sparse presence features (hdPS/LSPS setting)",
    PASS if ok else FAIL,
    "Spec §2a: procedures treated as high-dimensional sparse code set; presence feature per code"
)

# 2a-xi. Procedures: recurrence — SPEC REQUIRES
ok = bool(re.search(r"px_.*_count|px_.*_n\b|recurrence.*px|px.*recur", src))
check(
    "Procedures: recurrence feature per code",
    FAIL if not ok else PASS,
    "Spec §2a: generate presence AND recurrence for procedure codes. Only presence implemented."
)

# 2a-xii. Rx: presence
ok = "rx_" in src and "RX_ORDER" in src
check(
    "Rx orders: sparse presence features",
    PASS if ok else FAIL,
    "Spec §2a: prescription orders as sparse code set"
)

# 2a-xiii. Diagnoses: truncated at t* (no post-event data)
ok = "_dx_ts <= cutoff" in src or "DX_DATE.*cutoff" in src or "dx.*cutoff" in src.lower()
ok = bool(re.search(r'_dx_ts.*cutoff|cutoff.*dx', src, re.I))
check(
    "Diagnoses: only codes recorded at t ≤ t* (no pre-event cascade)",
    PASS if ok else FAIL,
    "Spec §2a critical temporal rule: only DX entries at t ≤ t*ᵢ enter feature vector"
)

# 2a-xiv. Feature window per spec is [t0, t*·Δ] (full trajectory to landmark)
# Code uses [t0, t0+4h] regardless of t* — intentional deviation (user instruction)
ok = "t0 + pd.Timedelta" in src and "GRID_HOURS" in src
check(
    "Feature window uses full trajectory to t* (spec) vs fixed 4h window (implementation)",
    WARN,
    "Spec §2a: information set Ī_it* covers full history from t=0 to t=t*. "
    "Code uses fixed window [t0, t0+4h] regardless of t* — intentional per user instruction: "
    "'include all data in the first 4 hours of admission'. This limits features for long stays."
)

print()

# ─────────────────────────────────────────────────────────────────────────────
print("STAGE 2b — Propensity Score Model")
# ─────────────────────────────────────────────────────────────────────────────

# 2b-i. L1-regularized logistic model
ok = 'penalty="l1"' in src or "penalty='l1'" in src
check(
    "LSPS model: L1-regularized (LASSO) logistic regression",
    PASS if ok else FAIL,
    "Spec §2b: L1-regularized (LASSO) logistic model required"
)

# 2b-ii. Score is P(i ∈ C | history, R(t*)) — case vs risk-set membership
ok = "y_vec" in src and "is_case" in src and "y_all" in src
check(
    "LSPS outcome: case vs donor (risk-set membership)",
    PASS if ok else FAIL,
    "Spec §2b: e_t(Ī_it) = P(i ∈ C | Ī_it, R(t))"
)

# 2b-iii. Caliper on logit scale
ok = "caliper_logit_sd" in src and "logit" in src
check(
    "Caliper applied on logit scale",
    PASS if ok else FAIL,
    "Spec §2c: nearest neighbor on e_t*_i (logit scale), within caliper"
)

# 2b-iv. Caliper = 0.2 × logit SD (hardcoded; spec says empirically determined)
m = re.search(r'"caliper_logit_sd"\s*:\s*([\d.]+)', src)
caliper_val = float(m.group(1)) if m else None
ok = caliper_val is not None
check(
    f"Caliper width: spec says empirically determined; code uses fixed {caliper_val}×SD",
    WARN,
    "Spec §2c: caliper width 'not explicitly specified — to be determined empirically'. "
    f"Code uses 0.2×logit_SD (Rosenbaum-Rubin standard). Consider sweeping caliper width."
)

# 2b-v. Prognostic score ψt (double-score matching) — SPEC REQUIRES
# Must actually fit a second model on event-free donors, not just mention the word
ok = bool(re.search(r'prognostic_score|psi_t\b|control_arm_risk|fit.*donor.*only|donors_only.*fit|second.*model', src, re.I))
check(
    "Prognostic score ψt (predicted control-arm risk) for double-score matching",
    FAIL if not ok else PASS,
    "Spec §2b: 'parallel score ψt = predicted control-arm risk — fit on event-free donors. "
    "Double-score logic: additionally balancing on ψt buys bias-robustness.' NOT implemented."
)

# 2b-vi. Clinical concept embeddings (optional per spec)
ok = "embed" in src.lower() or "pretrain" in src.lower()
check(
    "Clinical concept embeddings for code representation (optional per spec)",
    WARN if not ok else PASS,
    "Spec §2b optional: 'enrich code representation with pretrained clinical-concept embeddings'. "
    "Not implemented — this is listed as optional."
)

print()

# ─────────────────────────────────────────────────────────────────────────────
print("STAGE 2c — K:1 Nearest-Neighbour Matching")
# ─────────────────────────────────────────────────────────────────────────────

# 2c-i. Nearest neighbor on logit score
ok = "candidates_with_dist.sort" in src and "dist = abs(case_logit - d_logit)" in src
check(
    "Nearest-neighbor matching on logit score",
    PASS if ok else FAIL,
    "Spec §2c: nearest neighbor on e_t*_i (logit scale)"
)

# 2c-ii. Matching within CEM stratum
ok = "case_cem_key" in src and "stratum_donors" in src
check(
    "Matching within Stage 1 CEM stratum",
    PASS if ok else FAIL,
    "Spec §2c: 'select Mi(t*) ⊂ R(t*) within Stage-1 stratum'"
)

# 2c-iii. With replacement — SPEC REQUIRES k:1 with replacement
ok = bool(re.search(r"with.replacement|replace=True|sample.*replace", src, re.I))
check(
    "K:1 matching with replacement",
    FAIL if not ok else PASS,
    "Spec §2c: 'k:1 with replacement to lower bias given large donor pool'. "
    "Code does NOT implement with-replacement — it takes top-k unique donors per case, "
    "so a donor can appear in at most one case's matched set (effectively without replacement)."
)

# 2c-iv. Abadie-Imbens bias correction — SPEC REQUIRES
ok = "abadie" in src.lower() or "bias_correction" in src.lower() or "bias_correct" in src.lower()
check(
    "Abadie-Imbens bias correction after matching",
    FAIL if not ok else PASS,
    "Spec §2c: 'apply Abadie-Imbens bias correction; use matching-based variance estimate'. NOT implemented."
)

# 2c-v. Alternative estimators (overlap weights / fine stratification) — SPEC RECOMMENDS
ok = "overlap_weight" in src.lower() or "fine_strat" in src.lower() or "ow_weight" in src.lower()
check(
    "Alternative estimators: overlap weights or fine stratification",
    WARN if not ok else PASS,
    "Spec §2c alternative: 'parallel analysis with overlap weights (bounded, minimum asymptotic variance) "
    "or fine stratification'. Not implemented — recommended for rare outcomes."
)

# 2c-vi. Caliper relaxation (extra, not in spec)
ok = "relaxed_caliper" in src
check(
    "Caliper relaxation (3× fallback when no donors found)",
    WARN,
    "Not in spec. Code relaxes caliper by 3× when no donors found within original caliper. "
    "This is pragmatic but introduces a non-trivial deviation from fixed-caliper semantics."
)

print()

# ─────────────────────────────────────────────────────────────────────────────
print("STAGE 3 — Placebo Falsification")
# ─────────────────────────────────────────────────────────────────────────────

# 3a. Causal forest / DR learner used
ok = "CausalForestDML" in src or "causal_forest" in src.lower() or "bootstrap_ate" in src
check(
    "Stage 3: causal forest / DR estimator used",
    PASS if ok else FAIL,
    "Spec §3: fit causal_forest(X, Y^pl, W) on matched set"
)

# 3b. Raw vs matched comparison (power contrast)
ok = "raw" in src and "matched" in src and ("ate_raw" in src or "Y_raw" in src)
check(
    "Stage 3: raw donor pool vs matched set comparison",
    PASS if ok else FAIL,
    "Spec §3c: run on raw pool (should show pseudo-effect) AND matched set (should collapse to 0)"
)

# 3c. CI brackets zero check
ok = "ci_raw" in src or "ci_matched" in src
check(
    "Stage 3: confidence interval brackets zero check",
    PASS if ok else FAIL,
    "Spec §3b criterion (i): doubly-robust average effect CI brackets zero"
)

# 3d. Heterogeneity test (causal forest heterogeneity test) — SPEC REQUIRES
ok = bool(re.search(r"heterogene|best.linear.project|calibration.test|chernozhukov|differential.pred", src, re.I))
check(
    "Stage 3: heterogeneity test (best-linear projection or calibration test)",
    FAIL if not ok else PASS,
    "Spec §3b criterion (ii): test for heterogeneity must be non-significant. "
    "Code only checks CI brackets zero; no heterogeneity test implemented."
)

# 3e. P-value distribution ~U(0,1) across placebo panel — SPEC REQUIRES
ok = bool(re.search(r"p_val.*uniform|uniform.*p_val|placebo.*panel|p_dist", src, re.I))
check(
    "Stage 3: p-value distribution ~U(0,1) across placebo panel",
    FAIL if not ok else PASS,
    "Spec §3b criterion (iii): p-value distribution across placebo panel ≈ Uniform(0,1). "
    "Only one placebo outcome (AGE) is used; no panel of placebos implemented."
)

# 3f. Pooling across PSI types with type as covariate — SPEC RECOMMENDS
ok = bool(re.search(r"pool.*type|psi_type.*covar|cross.type", src, re.I))
check(
    "Stage 3: pool across PSI types with condition type as covariate",
    WARN if not ok else PASS,
    "Spec §3 power note: 'pool across types, enter condition type as covariate — forest borrows strength'. "
    "Code runs Stage 3 per-type independently."
)

print()

# ─────────────────────────────────────────────────────────────────────────────
print("DIAGNOSTICS & SENSITIVITY")
# ─────────────────────────────────────────────────────────────────────────────

# D1. SMD table reported
ok = "smd" in src.lower() and "balance_table" in src
check(
    "SMD balance table reported (before and after matching)",
    PASS if ok else FAIL,
    "Spec §Diagnostics: report SMD for all baseline and time-t features before and after selection"
)

# D2. Blanking window sweep b ∈ {3, 6, 9}
ok = "for b in [3, 6, 9]" in src or "for b in [3,6,9]" in src
check(
    "Blanking window sweep b ∈ {3, 6, 9}",
    PASS if ok else FAIL,
    "Spec §Diagnostics: re-estimate with b ∈ {3,6,9} grid steps to verify results not driven by prodrome"
)

# D3. Blanking sweep actually re-matches (not just counts potential pairs)
# Check what the sweep does
sweep_block = src[src.find("for b in [3, 6, 9]"):src.find("for b in [3, 6, 9]")+400] if "for b in [3, 6, 9]" in src else ""
reruns_matching = "SGD" in sweep_block or "lsps" in sweep_block.lower() or "matched_sets" in sweep_block
check(
    "Blanking sweep re-runs matching (not just counting potential pairs)",
    WARN if not reruns_matching else PASS,
    "Spec §Diagnostics: 're-estimate with shifted landmarks'. Code only counts potential pairs at "
    "each b value — it does not re-run LSPS + matching for each b. Sensitivity analysis is incomplete."
)

# D4. E-value (sensitivity to unmeasured confounding)
ok = "e_value" in src.lower() or "evalue" in src.lower() or "E-value" in src
check(
    "E-value (sensitivity to unmeasured confounding)",
    PASS if ok else FAIL,
    "Spec §Diagnostics: report E-value and/or Rosenbaum bounds for headline contrast"
)

# D5. Negative controls (dozens of E/O pairs) — SPEC REQUIRES
ok = "negative_control" in src.lower() or "negative control" in src.lower()
check(
    "Negative controls (dozens of exposure/outcome pairs)",
    FAIL if not ok else PASS,
    "Spec §Diagnostics: 'run full pipeline on dozens of exposure/outcome pairs with no plausible "
    "relationship; estimate residual systematic-error distribution; calibrate p-values'. NOT implemented."
)

# D6. Multiple imputation sensitivity for CEM — SPEC REQUIRES
ok = bool(re.search(r"multiple.imputation|MI.*stage|imputation.*CEM", src, re.I))
check(
    "Multiple imputation robustness check for Stage 1 CEM",
    FAIL if not ok else PASS,
    "Spec Stage 1 §3 sensitivity: 'Repeat Stage 1 under multiple imputation; pool results; "
    "compare to missingness-as-information solution'. NOT implemented."
)

# D7. Positivity curves (CEM donor count over time)
ok = "positivity_curves" in src
check(
    "Positivity curves: CEM donor count across grid ticks",
    PASS if ok else FAIL,
    "Spec §Positivity: monotone donor shrinkage Mᵢ(t+1) ⊆ Mᵢ(t) — curves visualize this"
)

print()

# ─────────────────────────────────────────────────────────────────────────────
print("ADDITIONAL SPEC VARIABLES")
# ─────────────────────────────────────────────────────────────────────────────

# S1. Height / Weight / BMI in covariates — SPEC LISTS as time-invariant
# Must appear as actual column references (EN_HEIGHT, EN_WEIGHT, etc.) not just in comments
ok = bool(re.search(r'EN_HEIGHT|EN_WEIGHT|EN_BMI|"HEIGHT"|"WEIGHT"|"BMI"', src))
check(
    "Baseline anthropometry (height, weight, BMI) as covariates",
    WARN if not ok else PASS,
    "Spec §Variables: 'baseline anthropometry: height, weight, BMI' listed as time-invariant Xᵢ. "
    "Not in code — not available as structured columns in OMNY ENCOUNTERS for most suppliers."
)

# S2. SDOH variables in dataset
ok = "SDOH" in src or "scores_sdoh" in src.lower() or "sdoh" in src.lower()
check(
    "SDOH variables available in dataset (description only per spec)",
    PASS if ok else WARN,
    "Spec §Variables: SDOH available for description; should NOT be in CEM exact-match key"
)

# S3. Problem lists used for chronic conditions
ok = "problem_list" in src.lower() or "PROBLEM_LIST" in src
check(
    "Problem lists used for baseline comorbidity burden",
    PASS if ok else FAIL,
    "Spec §Variables: 'baseline comorbidity burden: from problem list' is a time-invariant covariate"
)

# S4. Chronic condition count included
ok = "n_chronic" in src or "chronic_bin" in src
check(
    "Chronic condition count (from problem list) in covariates",
    PASS if ok else FAIL,
    "Spec §Variables: comorbidity burden from problem list"
)

print()

# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
print("=" * 70)
n_pass = sum(1 for _, s, _ in results if s == PASS)
n_fail = sum(1 for _, s, _ in results if s == FAIL)
n_warn = sum(1 for _, s, _ in results if s == WARN)
total  = len(results)
print(f"SUMMARY: {n_pass}/{total} PASS  |  {n_fail} FAIL  |  {n_warn} WARN")
print()

if n_fail:
    print("FAILURES (must fix to match spec):")
    for name, status, detail in results:
        if status == FAIL:
            print(f"  ✗ {name}")
            print(f"    {detail[:120]}")
    print()

if n_warn:
    print("WARNINGS (intentional deviations or optional items):")
    for name, status, detail in results:
        if status == WARN:
            print(f"  △ {name}")
    print()

print("=" * 70)
sys.exit(0 if n_fail == 0 else 1)
