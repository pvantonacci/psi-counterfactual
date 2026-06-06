# Pipeline vs. Spec — Deviations & Gaps

**Reference document:** `PROTEGE___Evaluating_LLMs.pdf`  
**Implementation:** `PSI_counterfactual_pipeline.py`  
**QA script:** `qa_pipeline_vs_spec.py`  
**QA result:** 37/60 PASS · 12 FAIL · 11 WARN  
**Date:** 2026-06-05

This document explains every place where the code deviates from the design specification, organised by whether the gap should be fixed, was intentional, or is a known data limitation.

---

## Summary table

| # | Item | Category | Status |
|---|---|---|---|
| 1 | Lab slope feature | Missing feature | **Must implement** |
| 2 | Lab time-since-last result | Missing feature | **Must implement** |
| 3 | Vitals slope feature | Missing feature | **Must implement** |
| 4 | Vitals abnormal-count feature | Missing feature | **Must implement** |
| 5 | Procedures recurrence feature | Missing feature | **Must implement** |
| 6 | Prognostic score ψt (double-score) | Missing component | **Must implement** |
| 7 | K:1 matching with replacement | Wrong algorithm | **Must implement** |
| 8 | Abadie-Imbens bias correction | Missing component | **Must implement** |
| 9 | Stage 3 heterogeneity test | Incomplete verification | **Must implement** |
| 10 | Stage 3 placebo panel (p-value distribution) | Incomplete verification | **Must implement** |
| 11 | Negative controls (systematic calibration) | Missing validation layer | **Must implement** |
| 12 | Multiple imputation robustness for CEM | Missing sensitivity check | **Must implement** |
| 13 | CEM key extended to 10 variables | Intentional extension | WARN — monitor strata |
| 14 | Feature window fixed at 4h vs full history to t* | Intentional (user instruction) | WARN — document clearly |
| 15 | Caliper width fixed at 0.2×SD | Pragmatic default | WARN — add sweep |
| 16 | Blanking sweep counts pairs only (no re-matching) | Incomplete implementation | WARN |
| 17 | Baseline anthropometry (height/weight/BMI) absent | Data availability | WARN — investigate OMNY |
| 18 | Stage 3 runs per-type not pooled | Pragmatic simplification | WARN |
| 19 | Caliper 3× relaxation fallback | Extra (not in spec) | WARN |
| 20 | Clinical concept embeddings | Optional per spec | Low priority |

---

## FAIL items — gaps that should be closed

### 1. Lab slope (trend) not computed
**Spec §2a:** "Summarize each analyte's within-window trajectory by: last value, **slope**, min/max, count of abnormal flags, time-since-last result."

**Current code:** computes `last`, `min`, `max`, `n` (count), `n_abn` — but no slope.

**Why it matters:** Slope captures whether a lab value is rising or falling, which is often more discriminating than the level. A sodium of 135 trending downward carries different risk than the same value trending upward.

**Fix:** For each analyte with ≥2 results in the window, fit `numpy.polyfit(relative_times, values, 1)` and store the slope coefficient as `lab_{code}_slope`. Set to 0 (not NaN) when only one result exists.

---

### 2. Lab time-since-last result not computed
**Spec §2a:** "time-since-last result" is an explicit required feature.

**Current code:** no `_tsl` or time-since-last feature for any modality.

**Why it matters:** Under informative missingness, the time since a lab was last checked is itself a clinical signal (e.g., a creatinine checked 30 minutes ago vs. 8 hours ago carries different information).

**Fix:** For each analyte, compute `(cutoff - last_timestamp).total_seconds() / 3600` and store as `lab_{code}_hours_since`. Where no result exists in the window, set to a sentinel (e.g., 999h) and add a separate "never observed" indicator.

---

### 3 & 4. Vitals slope and abnormal count not computed
**Spec §2a:** "Vitals: summarize as for labs: last value, slope, abnormal counts."

**Current code:** vitals have `last`, `min`, `max`, and presence (`_R`), but no slope and no abnormal-count feature.

**Fix:** Same logic as labs — add slope via `polyfit` for vitals with ≥2 readings, and flag abnormal via VS_ABN_FLAG or threshold comparison (e.g., HR > 100 = tachycardia).

---

### 5. Procedures recurrence feature not implemented
**Spec §2a:** "Generate candidate covariates from each code 'dimension' over the window: **presence, recurrence**."

**Current code:** only presence (`feats[f"px_{safe}"] = 1`). No recurrence count.

**Why it matters:** A procedure ordered twice in the first 4 hours (e.g., two chest X-rays) carries different signal than one ordered once.

**Fix:** Replace the presence indicator with both a presence flag (`px_{code}_any`) and a count (`px_{code}_n`). Apply the same logic to Rx orders.

---

### 6. Prognostic score ψt (double-score matching) not implemented
**Spec §2b:** "Parallel score ψt = predicted control-arm risk. Fit on event-free donors. Empirical counterpart of hazard λ(·). **Double-score logic: additionally balancing on ψt buys bias-robustness.**"

**Current code:** one model only — the propensity score e(t) = P(case | history). No prognostic score.

**Why it matters:** Double-score matching (also called "prognostic score matching" or "two-score matching") provides an additional hedge against unmeasured confounders that predict the outcome but not case-membership. It is particularly valuable for rare outcomes like PSI events.

**Fix:** After fitting LSPS, fit a second `SGDClassifier` on event-free donors only to predict a proxy outcome (e.g., any adverse event, long ICU stay). Use the combined (e_score, psi_score) distance metric during K:1 nearest-neighbour matching.

---

### 7. K:1 matching without replacement
**Spec §2c:** "k:1 **with replacement** to lower bias given large donor pool (recommendation: k:1 rather than 1:1 because nC = 145 is rare)."

**Current code:** each case takes its top-k nearest donors independently, but a given donor encounter ID cannot appear in two cases' matched sets — this is effectively matching *without* replacement across cases.

**Why it matters:** With replacement allows the best-matched donors to be reused across multiple cases, which reduces bias at the cost of some variance inflation. Without replacement forces suboptimal matches for later-processed cases when the best donors are already "used up."

**Fix:** Remove the uniqueness constraint across cases. Allow the same donor ENCOUNTER_ID to appear in multiple cases' matched sets. Apply Abadie-Imbens variance adjustment to account for reuse.

---

### 8. Abadie-Imbens bias correction not applied
**Spec §2c:** "Apply Abadie-Imbens bias correction; use matching-based variance estimate."

**Current code:** no bias correction after matching.

**Why it matters:** When matching is inexact (donors are close but not identical to the case), estimates are biased by the covariate imbalance within matched pairs. Abadie-Imbens correction removes this first-order bias using a regression adjustment within matched pairs.

**Fix:** After matching, compute the Abadie-Imbens correction term for each matched pair: fit a within-stratum OLS model for the outcome on the covariates using donors only, and subtract the predicted value from the donor outcome. Available in Python via `econml.inference` or manual implementation with `sklearn.linear_model.Ridge` within each CEM stratum.

---

### 9. Stage 3 heterogeneity test not implemented
**Spec §3b criterion (ii):** "Test for heterogeneity using best-linear projection of conditional effect, or differential-prediction/calibration test (Chernozhukov et al. generic-ML inference). Must be non-significant."

**Current code:** Stage 3 only checks whether the CI brackets zero (criterion i). No heterogeneity test.

**Why it matters:** A CI that brackets zero only rules out an average effect. Residual imbalance could manifest as heterogeneous effects (some subgroups diverge) that average to zero — the heterogeneity test catches this.

**Fix:** After fitting `CausalForestDML`, run `forest.test_calibration()` (available in `econml`) and log the p-value. Flag if p < 0.05 (indicates heterogeneous pseudo-effect, which means residual confounding).

---

### 10. Stage 3 uses a single placebo outcome, not a panel
**Spec §3b criterion (iii):** "P-value distribution across placebo panel ≈ Uniform(0,1)."

**Current code:** AGE is the only placebo outcome. One p-value cannot form a distribution.

**Why it matters:** A single non-significant p-value could reflect low power rather than genuine exchangeability. A panel of 10+ null placebos with a ~Uniform p-value distribution is much stronger evidence.

**Fix:** Identify 5–10 baseline variables that are (a) not used in matching, (b) known to have zero causal relationship with PSI occurrence (e.g., LOS on a previous unrelated admission, an incidental lab from 6 months prior). Run Stage 3 for each; plot the p-value distribution and apply a KS test against Uniform(0,1).

---

### 11. No negative-control systematic calibration
**Spec §Diagnostics:** "Run full pipeline on dozens of exposure/outcome pairs with no plausible relationship. Estimate residual systematic-error distribution. Calibrate p-values and confidence intervals."

**Current code:** not implemented.

**Why it matters:** Negative-control calibration (Schuemie et al. / OHDSI approach) allows the analyst to quantify the empirical null distribution — how often the pipeline produces a false-positive finding by chance. Without this, all p-values and CIs from Stage 3 are uncalibrated.

**Fix:** Select ~20–50 negative-control exposure/outcome pairs (e.g., "appendectomy vs. PSI_17") where no causal link is plausible. Run the full pipeline for each pair, collect the naive estimate. Fit a systematic error model and use it to recalibrate the primary estimates.

---

### 12. Multiple imputation robustness check for CEM not implemented
**Spec Stage 1 §3:** "Robustness check: Repeat Stage 1 under multiple imputation. Apply MI to baseline variables. Match within each imputed dataset. Pool results. Compare resulting strata to missingness-as-information solution."

**Current code:** uses missingness-as-information (explicit `__MISSING__` category) but never runs the MI comparison.

**Why it matters:** The `__MISSING__` category assumes the reason a value is missing is itself informative (e.g., a supplier not recording employment status may serve a systematically different population). MI provides a robustness check: do the matched strata change substantially when we impute vs. when we treat missing as a category?

**Fix:** Apply `sklearn.impute.IterativeImputer` (MICE) to baseline variables before CEM. Run CEM on the imputed dataset. Compare matched pair sets and stratum sizes. If strata are substantially different, the missingness mechanism assumption needs to be documented.

---

## WARN items — intentional deviations or partial implementations

### 13. CEM key extended from 5 to 10 variables
**Spec:** exact-match key = sex, age band, facility type, urban/rural, admission department.  
**Code:** adds RACE_GRP, ETHNICITY_BIN, EMPLOY_BIN, EN_FACILITY_SIZE, EN_DEPT (current department, in addition to admission department).

**Rationale for extension:** The spec's 5-variable key was designed for the full 51M donor pool where strata would still be well-populated. With a 1% sample (~316K donors), adding more variables still leaves most strata adequately populated. The additions (race, ethnicity, employment, facility size, current department) improve demographic comparability for the causal question.

**Risk:** Sparsity. Some PSI types (PSI_12: 19 pairs from 3 cases) show signs of stratum emptying due to the tighter key. The spec explicitly warned: "SDOH should not be in the exact key — present for negligible fraction of admissions, would empty strata." Monitor strata counts per type; consider a tiered key (5-variable key first, expand only for well-powered types).

---

### 14. Feature window fixed at [t0, t0+4h] instead of [t0, t*·Δ]
**Spec:** information set Ī_it* covers the **full trajectory from t=0 to t=t***. For most cases where the PSI event occurs at day 3, this would be 3 days of history.

**Code:** fixed window [admission_start, admission_start + 4h] regardless of t*.

**Rationale:** User instruction: "Include all the information available in the first 4 hours of the admission. Admission chaos is acceptable." This is a deliberate design choice to focus on early triage signals.

**Consequence:** For cases where t* is large (e.g., pressure ulcer developing on day 10), only the first 4 hours of a 10-day stay are used for feature matching. Most of the clinical trajectory that differentiates cases from donors is discarded. The propensity score will underperform for long-stay PSI types.

**Recommended action:** Consider a hybrid — use [t0, t0+4h] as a minimum, but extend to [t0, min(t0+24h, t*·Δ)] for cases with t* > 6. This preserves the admission-chaos inclusion while capturing more signal for long-stay types.

---

### 15. Caliper fixed at 0.2×logit SD (not empirically determined)
**Spec:** "caliper width not explicitly specified in document — to be determined empirically."

**Code:** `caliper_logit_sd = 0.2` (the Rosenbaum-Rubin recommendation for general use).

**Consequence:** 0.2×SD may be too wide for types with many donors (too many matches, noisy) or too tight for rare types (too few matches). The 3× caliper relaxation fallback masks this problem rather than solving it.

**Recommended action:** Add a calibration pass — run Stage 2c at caliper ∈ {0.1, 0.2, 0.4} SD and report the number of unmatched cases and SMD improvement for each. Let the analyst choose.

---

### 16. Blanking window sweep counts potential pairs only (does not re-match)
**Spec:** "re-estimate with b ∈ {3, 6, 9} grid steps" — meaning re-run full Stage 2b + 2c at each b.

**Code:** The sweep loop only counts how many donor-case pairs would be *eligible* (in risk set) at each b value. LSPS is not re-fit and matching is not re-run for b=3 or b=9.

**Consequence:** The sensitivity analysis appears in the verification report but doesn't actually test whether results change with different blanking windows.

---

### 17. Baseline anthropometry (height, weight, BMI) absent
**Spec:** lists height, weight, BMI as time-invariant covariates Xᵢ.

**Code:** not present — these columns are not in `OMNY_REPL_ID.CUSTOM.ENCOUNTERS`.

**Status:** Data availability issue. Check whether OMNY VITALS table has baseline height/weight on admission day. If so, pull as static covariates for CEM. OMNY's SCORES table may also contain BMI.

---

### 18, 19. Stage 3 per-type, not pooled; caliper 3× relaxation
These are minor pragmatic choices. The per-type Stage 3 is acceptable as long as each type's results are interpreted with appropriate uncertainty (wide CIs). The 3× caliper relaxation should be logged clearly in the output (it already is) so analysts can flag cases where the final match relied on a relaxed caliper.

---

## What the code gets right
Despite the gaps above, the following core components match the spec precisely:

| Component | Spec requirement | Code status |
|---|---|---|
| Governance: suppliers 1990, 3707, 3490 | Hard exclusion | ✓ Exactly implemented |
| Temporal grid Δ = 4h | Grid spacing | ✓ |
| Blanking window b = 6 (24h) | Landmark placement | ✓ |
| t* = E_i − B_GRID | Landmark formula | ✓ |
| Risk set R(t*): donors still admitted | Eligibility | ✓ |
| Missingness-as-information (`__MISSING__`) | CEM coarsening | ✓ |
| L1-regularized logistic (LASSO) for LSPS | Model type | ✓ |
| Nearest-neighbour on logit scale | Matching metric | ✓ |
| Matching within CEM stratum | Matching scope | ✓ |
| Lab presence + last + min/max + abnormal count | Lab features (partial) | ✓ partial |
| Diagnoses truncated at t* | No outcome-descendant leakage | ✓ |
| SMD table before/after | Balance diagnostics | ✓ |
| E-value | Sensitivity to unmeasured confounding | ✓ |
| Positivity curves | Monotone shrinkage visualization | ✓ |
| Blanking window sweep b ∈ {3,6,9} | Sensitivity parameter | ✓ partial |
| Problem lists for comorbidity burden | Baseline covariates | ✓ |
