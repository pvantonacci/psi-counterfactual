# Project Bayes — Pipeline, Experiments, and Results (Handoff for Rey)

Hey Rey — this bundle contains the **complete v1 pipeline + cohort + experiment results** so you can reproduce everything Matt + Engy have run on Project Bayes so far.

The headline: we built a 145-case healthcare LLM benchmark anchored on AHRQ Patient Safety Indicators (PSIs), ran 5 prompts × 2 models × 3 judges on it, and produced a clean per-case score CSV with criterion-level granularity.

---

## TL;DR — what's in this folder

```
rey_v1_reproducible/
├── README.md                              ← this file
├── code/                                  Python that runs the pipeline
├── data/                                  the 145-case cohort + OMNY EHR tables
├── notebooks/                             3 Jupyter notebooks with the results
├── results/                               per_case_scores.csv + criteria_long.csv from the run
└── docs/                                  reference markdown (renderer design, truncation rules, prompt-selection rationale, etc.)
```

To reproduce the run: `cd code && python3 run_eval_parallel.py --cases ../data/eval_cases_psi.csv --tables-dir ../data/tables --out-dir my_rerun`

To browse the existing results: open one of the notebooks in `notebooks/`.

---

## 1. The project in one paragraph

**Goal:** build a healthcare LLM benchmark that lives in the "hard problem, easy to verify" quadrant — clinical cases where the model has to reason about messy real-world EHR context, but whether it got the answer right is unambiguous and doesn't require physician adjudication. We use AHRQ Patient Safety Indicators (PSIs) as the anchor because PSI events are non-deferrable, well-defined adverse events with a structured curation pipeline behind them.

**Why it matters:** existing healthcare benchmarks either (a) test easy memorization (HealthBench / MedQA / USMLE-style) or (b) require human physician judges to score, which is expensive and noisy. PSIs let us thread the needle.

For the longer strategic framing, see `docs/PROJECT_GOAL.md`.

---

## 2. The pipeline

```
                 ┌────────────────────────────────────────────────────────────────┐
                 │  Allison's PSI labeler (upstream, not in this bundle)           │
                 │  Stage 1: ICD-10 regex on claims                               │
                 │  Stage 2: regex on note text                                   │
                 │  Stage 3: Claude chart review with HIGH-confidence curation    │
                 └────────────────────────────────────────────────────────────────┘
                                            │
                                            ▼
                  data/psi_inpatient_cases_downsampled.csv   (163 labeled rows)
                                            │
                                            ▼
                  data/eval_cases_psi.csv                    (145 inpatient cases — the cohort we eval on)
                                            │
                                            ▼
                  ┌──────────────────────────────────┐
                  │  code/renderer.py                │   reads OMNY tables in data/tables/,
                  │   • EncounterDataLoader           │   filters to the encounter, applies
                  │   • render(encounter, prompt)     │   prompt-specific truncation, returns text
                  └──────────────────────────────────┘
                                            │
                                            ▼
                  ┌──────────────────────────────────┐
                  │  code/run_eval_parallel.py       │   for each (case × prompt × MUT):
                  │   • ThreadPoolExecutor (conc 12) │     1. render + extract ground truth
                  │                                  │     2. call MUT (Opus / GPT-5.5)
                  │                                  │     3. for each judge, for each criterion:
                  │                                  │          binary yes/no + rationale
                  │                                  │     4. write per_case + criteria_long rows
                  └──────────────────────────────────┘
                                            │
                                            ▼
                  results/per_case_scores.csv            (1 row per case×prompt×MUT, with per-judge scores)
                  results/criteria_long.csv              (1 row per case×prompt×MUT×judge×criterion)
                                            │
                                            ▼
                  notebooks/*.ipynb                      (plots, deep dives, examples)
```

### Components in detail

**Cohort (145 cases) — `data/eval_cases_psi.csv`.** Curated from Allison's downsampled PSI labels. Filtered to inpatient encounters (the original 163 had 18 non-inpatient that were dropped). 73 negative + 72 positive PSI labels across 16 PSI codes (PSI_03 / PSI_04 / PSI_05 / PSI_06 / PSI_07 / PSI_08 / PSI_09 / PSI_10 / PSI_11 / PSI_12 / PSI_13 / PSI_14 / PSI_15 / PSI_17 / PSI_18 / PSI_19). Stratifiers: `COMPLEXITY_TIER` (continuous Protege Complexity Score bucketed), `LOS_BUCKET` (length-of-stay bin), `PROTEGE_SCORE` (raw score).

**Renderer — `code/renderer.py`.** Reads 9 OMNY tables (encounters, notes, labs, vitals, diagnoses, procedures, prescription_orders, prescription_administrations, problem_lists), filters to the target encounter, and emits clinician-readable text. Handles within-note section masking and time-based truncation per prompt. The `TruncationSpec` dataclass parameterizes what to keep / drop. See `docs/RENDERER_DESIGN.md` and `docs/TRUNCATION_BY_PROMPT.md` for the full spec.

**Criteria / rubrics — `code/criteria.py`.** Each prompt has a HealthBench-style signed-point rubric (positive points for desirable behaviors, negative for hallucinations / unsafe actions). All prompts share five universal criteria (factual support, safety, on-task, terminology, uncertainty acknowledgment). The judge sees the prompt + ground truth + model response and answers yes/no per criterion.

**Runner — `code/run_eval_parallel.py`.** Parallel orchestrator. Concurrency 12. Resumable — skips any `(encounter, prompt, mut)` tuple already in `per_case_scores.csv`. Writes streaming CSVs under a `--lock`.

**Judge stack — `code/judge.py` + `code/judge_routing.py`.** Three judges per response: Claude Sonnet 4.6, GPT-5.4-mini, Gemini 3.5 Flash. The GPT judge is deliberately smaller than the GPT MUT to avoid self-grading bias. Judges run all rubric criteria independently, then a Cohen's κ tracks pairwise agreement.

---

## 3. What we've run (the experiment)

| Parameter | Value |
|---|---|
| Cases | 145 (the full `eval_cases_psi.csv` cohort) |
| Prompts | 5 — `S1`, `S5`, `C1`, `C8`, `P7` |
| Models under test (MUTs) | Claude Opus 4.7, GPT-5.5 |
| Judges | Claude Sonnet 4.6 + GPT-5.4-mini + Gemini 3.5 Flash |
| Total tasks | 145 × 5 × 2 = 1,450 |
| Total criterion-level rows | ~78k (5–9 criteria × 5 universals × 3 judges per task) |
| Concurrency | 12 |
| Resumable | yes |
| Cost (approx) | ~$200 across the run |
| Wall-clock | ~2 hours |

### The 5 prompts

| ID | Family | What the model is asked to do | Truncation |
|---|---|---|---|
| `S1` | Structure (extract) | Extract the chief complaint from the admission H&P note | Single H&P note only |
| `S5` | Structure (extract) | Extract the Assessment and Plan section verbatim | Single H&P note only |
| `C1` | Content (summarize) | Summarize the A&P from the admission H&P, covering all problems and plans | Single H&P note only |
| `C8` | Content (interpret) | Summarize lab results, flag abnormals, suggest follow-up actions | All labs, no time cutoff |
| `P7` | Prediction (numerical) | Given the chart up to time T, predict the next lab panel's values | Strict `< specimen_ts` cutoff applied to ALL tables (6-layer look-ahead protection) |

Why these 5? See `docs/PROMPT_SELECTION_RATIONALE.md` — they were chosen from a 31-prompt SOW based on coverage (one prompt per task family), having well-defined ground truth, and resolving rubric-design questions.

### The rubrics

- **S1 / S5 (S-A family):** ≥80% / ≥50% fact recall, single most-important fact, source traceability, hallucination penalty, critical-fact omission penalty.
- **C1:** identifies all problems, primary problem, has plan for each problem, preserves reasoning, names meds, includes disposition, hallucination penalty, omission penalty, padding penalty.
- **C8:** flags ≥80% / ≥50% of abnormals, correct context per flagged abnormal, appropriate follow-up, identifies critical/panic values, false-positive penalty, missed-critical penalty, unsafe-action penalty.
- **P7:** direction match (high/low/normal) for >50% of labs, value within ±25% for >50%, hallucinated-lab penalty.
- **Universal (all prompts):** factual support, safety, on-task, terminology, uncertainty acknowledgment.

See `docs/JUDGE_PROMPTS.md` for the exact criterion text sent to judges.

### Look-ahead bias protection (P7-specific)

P7 is the only prediction prompt; it's also the only one that needs aggressive time-based truncation. The 6-layer protection stack:
1. Target specimen = first ≥10-lab panel ≥6h post-admission (skips thin draws like single-lab fingerstick glucose)
2. Cutoff = `specimen_ts − 1 second` (strict before)
3. Cutoff applied to **all** tables (notes, labs, vitals, meds, diagnoses, procedures, admins)
4. Sentinel-date filter: drops rows with the OMNY "Jan 1 at midnight" placeholder timestamps
5. Discharge-note exclusion: regex on note title/type catches `DISCHARGE` / `DEATH NOTE` / `DISPOSITION`
6. Admit-date floor: anything before `EN_START_DATE` is also dropped

One look-ahead leak was caught during the run and re-evaluated: the discharge regex originally missed `DISCHARGE SUMMARY/INSTRUCTIONS/PLANNING`, and combined with sentinel timestamps had ~11/145 P7 cases with discharge content visible. After the patch + re-run, GPT-5.5 P7 scores dropped from 0.30 → 0.08 on affected cases (the leak was inflating scores).

For the full per-prompt truncation spec see `docs/TRUNCATION_BY_PROMPT.md`.

---

## 4. Results

The actual CSVs are in `results/`. Here are the headline numbers — verify by running the notebooks.

### Mean score by (prompt, MUT) — post-patch, full cohort

| Prompt | Claude Opus 4.7 | GPT-5.5 | Effective n |
|---|---|---|---|
| `S1` (chief complaint) | 0.437 | 0.466 | 116 |
| `S5` (A&P extraction)  | 0.292 | 0.316 | 116 |
| `C1` (A&P summary)     | 0.260 | 0.279 | 116 |
| `C8` (lab interp)      | 0.454 | 0.422 | 144 |
| `P7` (next lab panel)  | 0.165 | 0.190 |  77 |

Notes:
- `Effective n` is below 145 for cases where the renderer couldn't produce non-empty content (missing H&P note for S1/S5/C1; no qualifying ≥10-lab panel ≥6h post-admit for P7).
- Scores are mean across the 3 judges, mean across cases, in `[0, 1]`.
- S1 and S5/C1 ground truths were re-extracted late in the run (the original `NOTE_TYPE`-based section parser missed most cases; a text-based fallback now handles section headers). The numbers above are post-fix.

### Three findings that survive scrutiny

1. **The benchmark discriminates.** Mean scores span 0.17 → 0.47 across the 5 prompts. P7 (prediction) is genuinely hard; S1 (extract chief complaint) is moderate; C8 (lab interpretation) is the easiest of the five.
2. **Complexity is a small headwind, not a large one.** Per-case Pearson r between `PROTEGE_SCORE` and `score_mean` is around −0.1 to −0.2 across prompts — higher-complexity cases score slightly worse, but the dominant variance is prompt × case, not complexity × case. See the complexity scatter in `notebooks/proj_bayes_main_plots_v2.ipynb`.
3. **Judges agree.** Cohen's κ on criterion-level yes/no answers between Sonnet 4.6 ↔ GPT-5.4-mini is **0.51** (moderate agreement) — well above the κ ≥ 0.4 acceptability bar. Gemini 3.5 Flash saturated on S1/S5/C1 (gave "no" to nearly all criteria after a parser change), so its κ collapsed for those prompts. Sonnet ↔ GPT-mini is the reliable backbone.

### Notebooks — what's in each

| Notebook | What's in it |
|---|---|
| `notebooks/proj_bayes_main_plots_v2.ipynb` | The main headline notebook. Cell-by-cell: cohort summary → main scatter (score vs case) → complexity × score scatter → LOS × score scatter → judge agreement heatmap → 10 hard-case deep dives with full model responses + judge rationales. This is the one to walk Engy through. |
| `notebooks/proj_bayes_deep_analysis.ipynb` | Per-prompt analytics — score distributions, per-PSI breakdowns, per-criterion pass rates, judge disagreement audits. Reference / supplement to the main notebook. |
| `notebooks/proj_bayes_3_examples.ipynb` | Three case walkthroughs at the model-response level: the chart the model saw, the prompts it answered, the model's response, ground truth, and judge scoring. Useful for understanding what the eval feels like end-to-end. |

---

## 5. Known limitations + open issues from the v1 run

These are the things to flag in any external writeup or follow-up work — don't paper over them.

1. **Gemini judge saturated on S1/S5/C1 post-patch** — answers "no" to all rubric criteria. Likely a parser issue in `judge.py`. κ collapsed to ~0 for those prompts. Sonnet ↔ GPT-mini still works fine. Worth root-causing.
2. **P7 specimen-type mismatch** — ~30–40% of P7 cases had the target panel be a urinalysis dipstick; models predicted serum chemistry. Prediction was reasonable, but scored 0 because the labs didn't match. Truncation logic is correct, but the panel-selection heuristic could be smarter.
3. **OMNY sentinel timestamps** — many rows carry Jan-1-at-midnight placeholder timestamps. The renderer filters these (in P7 specifically), but they're a footgun for anyone adding new time-anchored prompts.
4. **Empty render rate on P7** — ~18% of P7 cases have no qualifying ≥10-lab panel ≥6h post-admit. Renderer returns empty, runner records `error="empty render"` and skips judging. That's why P7 `n=77` vs 145.
5. **S1 → S5/C1 ground truth fragility** — extracting the A&P section from a single H&P note depends on either `NOTE_TYPE` sub-labels (sparse — 0.3% of rows have them) or text-based section header regex (now the fallback). The text regex misses unusual section header formats. ~20% of cases have empty extracted GT.

For more on data-quality issues see `docs/DATA_QUALITY_ISSUES.md`.

---

## 6. How to reproduce

### Setup (one-time)

```bash
# 1. Unzip + cd in
unzip rey_v1_reproducible.zip && cd rey_v1_reproducible

# 2. Python env (Matt uses ~/Projects/mturk-main-env)
python3 -m venv .venv && source .venv/bin/activate
pip install pandas numpy anthropic openai google-genai pyarrow tqdm

# 3. API keys (your own)
export ANTHROPIC_API_KEY=sk-ant-...
export OPENAI_API_KEY=sk-...
export GOOGLE_API_KEY=...    # or GEMINI_API_KEY
```

### Run a 5-case smoke test (~$2, ~2 min)

```bash
cd code
# Build a 5-case sample
python3 - <<'PY'
import pandas as pd
df = pd.read_csv('../data/eval_cases_psi.csv').head(5)
df.to_csv('../data/eval_cases_psi_smoke.csv', index=False)
PY

python3 run_eval_parallel.py \
  --cases ../data/eval_cases_psi_smoke.csv \
  --tables-dir ../data/tables \
  --prompts S1,S5,C1,C8,P7 \
  --out-dir eval_output_smoke \
  --concurrency 5
```

Output: `code/eval_output_smoke/per_case_scores.csv` + `criteria_long.csv`. Should have ~25 rows (5 cases × 5 prompts × 1 row per case-prompt, but written per-MUT so really 5×5×2 = 50 — minus any empty renders).

### Run the full thing (~$200, ~2 hr)

```bash
cd code
python3 run_eval_parallel.py \
  --cases ../data/eval_cases_psi.csv \
  --tables-dir ../data/tables \
  --prompts S1,S5,C1,C8,P7 \
  --out-dir my_full_rerun \
  --concurrency 12
```

The runner is resumable — safe to ctrl-C and restart; it skips completed `(encounter, prompt, mut)` tuples.

### Browse the existing results without rerunning

```bash
cd notebooks
jupyter lab proj_bayes_main_plots_v2.ipynb
```

The notebooks read from `../results/per_case_scores.csv` and `../results/criteria_long.csv`. If you re-run and want to re-render the notebooks against new results, point the `RESULTS_DIR` constant at the top of each notebook to your rerun output.

---

## 7. Reading order

1. **This README** — the overview you're reading.
2. **`docs/PIPELINE_OVERVIEW.md`** — short companion to this README; the high-level pipeline diagram.
3. **`docs/PROJECT_GOAL.md`** — strategic positioning of the project.
4. **`docs/RENDERER_DESIGN.md`** — the renderer's internals.
5. **`docs/TRUNCATION_BY_PROMPT.md`** — per-prompt truncation spec (especially the P7 6-layer protection).
6. **`docs/JUDGE_PROMPTS.md`** — the exact criterion text sent to the judges.
7. **`docs/PROMPT_SELECTION_RATIONALE.md`** — why these 5 prompts out of 31.
8. **`docs/DATA_QUALITY_ISSUES.md`** — the footguns we've already discovered in the OMNY data.

Then **open the notebooks** to see the results in their natural habitat.

---

## 8. Next ideas (placeholder — Matt will brief you on what to actually pick up)

This is intentionally short — Matt has a separate handoff with the specific experiments he wants you to run next. Don't start any of these without talking to him first.

- Extend the prompt set into prediction tasks (predict next adverse event vs predict next lab values)
- Tighten rubrics into multiple-choice forms to eliminate judge variance
- Per-PSI accuracy heatmap (which adverse events are easier / harder)
- Root-cause the Gemini saturation issue
- EHRshot leakage analysis

Matt's the source of truth on priorities here.

---

## Contact

- Matt — Slack DM. Slow response 6/2–6/16 (wedding/honeymoon). For urgent things he'll share his SMS number.
- Engy — fallback for anything blocking while Matt is away.
- The shared Slack channel for the project (Matt will set this up before leaving).

---

*Bundle prepared 2026-05-31. All numbers cited are from `results/per_case_scores.csv` in this bundle (the post-patch v1 run).*
