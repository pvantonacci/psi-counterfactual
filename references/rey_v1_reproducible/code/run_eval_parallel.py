"""
Parallel eval runner for Project Bayes — Wednesday deliverable build.

Supports:
  - Multiple MUTs (Opus 4.7 + GPT-5.5) per (case, prompt)
  - 3-judge stack (Sonnet 4.6 + GPT-5.4-mini + Gemini 3.5 Flash) per MUT response
  - Concurrent execution via ThreadPoolExecutor (per-task = one (case, prompt, mut))
  - Resumable — skips already-completed (case, prompt, mut) tuples

Per-task work (sequential within a task):
  1. Render input + extract GT
  2. Call MUT
  3. For each judge: for each criterion: call → record yes/no + rationale
  4. Write one row per (case, prompt, mut) to per_case_scores.csv
  5. Write per-criterion rows to criteria_long.csv

Parallelism: N concurrent tasks (default 10). 300 cases × 5 prompts × 2 MUTs = 3,000 tasks.
At ~30s/task with N=10 → ~2.5 hours wall-clock.

Usage:
  python3 run_eval_parallel.py --cases eval_cases_v2.csv --prompts S1,S5,C1,C8,P7 --concurrency 10
"""

from __future__ import annotations

import argparse
import csv
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional

import pandas as pd

from renderer import (
    EncounterDataLoader,
    extract_ground_truth,
    render,
    render_p7,
    render_single_note,
    select_target_note,
    TruncationSpec,
)
from judge import call_llm, parse_judge_json
from criteria import (
    criteria_for,
    score_from_results,
    UNIVERSAL_CRITERIA,
)
from judge_routing import (
    family_for,
    judges_for,
    models_under_test,
    DEFAULT_MUTS,
    DEFAULT_JUDGES,
)


OUT_DIR = Path(__file__).parent / "eval_output_v2"
PER_CASE_CSV = OUT_DIR / "per_case_scores.csv"
CRITERIA_LONG_CSV = OUT_DIR / "criteria_long.csv"
RUN_LOG = OUT_DIR / "run_log.jsonl"

# Thread-safe writes
_WRITE_LOCK = threading.Lock()


# Default prompt set for the Wednesday deliverable
DEFAULT_PROMPTS = ["S1", "S5", "C1", "C8", "P7"]


PROMPT_TEXT = {
    "S1": "Extract the chief complaint (or reason for admission) from the clinical note(s) below. Return only the chief complaint text.",
    "S5": "Extract the Assessment and Plan section from the clinical note below. Return the A&P text verbatim or as closely as possible.",
    "C1": ("Summarize the Assessment and Plan from the admission H&P below. Cover all problems "
           "and their plans. Specify the date of the note. Limit your summary to that note only."),
    "C8": ("Summarize the lab results below. Identify which values are abnormal and, for each "
           "abnormal result, describe what clinical action or follow-up order would be appropriate."),
    "P7": ("A lab panel has been ordered for this patient. Based on the clinical context (notes, prior "
           "labs, vitals, meds), predict the values of the next lab panel. For each lab predicted, "
           "give name, value, units, and whether you expect it to be high / low / within reference."),
}


MUT_SYSTEM = "You are a clinical AI assistant. Answer the question concisely based on the clinical record provided."

JUDGE_SYSTEM = """You are a clinical evaluator scoring a medical AI model's response against a rubric.
The model was given a specific clinical task and produced a response. You must judge
whether the response meets a specific criterion.

Be strict but fair. Base your judgment ONLY on the source material and the response
provided. Do not penalize for stylistic choices unless the criterion explicitly
addresses style. If the criterion is ambiguous in this case, default to "no".

Return your answer as JSON in this exact format:
{"answer": "yes" | "no", "rationale": "<one sentence>"}"""


# ---------------------------------------------------------------------------
# Result row schema
# ---------------------------------------------------------------------------


@dataclass
class RunResult:
    encounter_id: str
    prompt_id: str
    mut_model: str
    los_bucket: str
    complexity_tier: str
    primary_dx: str
    protege_score: int
    los_days: int
    prompt_class: str
    # Per-judge rubric scores
    score_sonnet: Optional[float] = None
    score_gpt_mini: Optional[float] = None
    score_gemini: Optional[float] = None
    score_mean: Optional[float] = None
    # Per-judge universal scores
    score_universal_sonnet: Optional[float] = None
    score_universal_gpt_mini: Optional[float] = None
    score_universal_gemini: Optional[float] = None
    # Pairwise judge deltas
    delta_sonnet_gpt: Optional[float] = None
    delta_sonnet_gemini: Optional[float] = None
    delta_gpt_gemini: Optional[float] = None
    judge_delta_max: Optional[float] = None
    # Costs
    mut_cost_usd: float = 0.0
    judge_cost_usd: float = 0.0
    total_cost_usd: float = 0.0
    # Token counts
    n_input_tokens: int = 0
    n_output_tokens: int = 0
    # Excerpts
    model_response_excerpt: str = ""
    ground_truth_excerpt: str = ""
    # Status
    error: Optional[str] = None
    runtime_s: float = 0.0


# ---------------------------------------------------------------------------
# Render + GT (same as run_eval.py)
# ---------------------------------------------------------------------------


def _render_for_prompt(encounter_id: str, prompt_id: str, loader: EncounterDataLoader) -> tuple[str, dict]:
    if prompt_id in ("S1", "S5", "C1"):
        note_id = select_target_note(encounter_id, "h&p adult", loader)
        if note_id is None:
            return "", {"label": "", "metadata": {"note": "no H&P found"}}
        rendered = render_single_note(encounter_id, note_id, loader)
        gt = extract_ground_truth(encounter_id, prompt_id, loader, target_note_id=note_id)
        return rendered, gt
    if prompt_id == "P7":
        rendered, cutoff = render_p7(encounter_id, loader)
        gt = extract_ground_truth(encounter_id, prompt_id, loader)
        if cutoff and gt.get("metadata"):
            gt["metadata"]["context_cutoff_ts"] = cutoff.isoformat()
        return rendered, gt
    rendered = render(encounter_id, prompt_id, loader=loader)
    gt = extract_ground_truth(encounter_id, prompt_id, loader)
    return rendered, gt


def _call_judge_criterion(judge_model, criterion, full_prompt, ground_truth, model_response):
    context = f"""PROMPT GIVEN TO MODEL:
{full_prompt[:2000]}{'...' if len(full_prompt) > 2000 else ''}

GROUND TRUTH (NOT shown to the model):
{ground_truth[:1500]}{'...' if len(ground_truth) > 1500 else ''}

MODEL RESPONSE:
{model_response[:3000]}{'...' if len(model_response) > 3000 else ''}

CRITERION TO EVALUATE:
{criterion['question']}"""
    resp = call_llm(
        model=judge_model,
        system=JUDGE_SYSTEM,
        user=context,
        max_tokens=600,  # increased from 300 — Gemini was getting cut off mid-JSON
        temperature=0.0,
    )
    parsed = parse_judge_json(resp.text)
    answer = parsed.get("answer")
    if isinstance(answer, bool):
        answer = "yes" if answer else "no"
    elif isinstance(answer, str):
        answer = answer.lower().strip()
    elif isinstance(answer, int):
        answer = str(answer)
    else:
        answer = "no"
    return answer, str(parsed.get("rationale", ""))[:400], resp


# ---------------------------------------------------------------------------
# Per-task worker
# ---------------------------------------------------------------------------


def run_one_task(
    case: pd.Series,
    prompt_id: str,
    mut_model: str,
    loader: EncounterDataLoader,
) -> tuple[RunResult, list[dict]]:
    """Run one (case, prompt, mut) task. Returns (result, criteria_rows)."""
    t_start = time.time()
    encounter_id = case["ENCOUNTER_ID"]
    los_bucket = case["LOS_BUCKET"]
    family = family_for(prompt_id)

    result = RunResult(
        encounter_id=encounter_id,
        prompt_id=prompt_id,
        mut_model=mut_model,
        los_bucket=los_bucket,
        complexity_tier=case["COMPLEXITY_TIER"],
        primary_dx=str(case.get("PRIMARY_DX_CODE", "")),
        protege_score=int(case["PROTEGE_SCORE"]),
        los_days=int(case["LOS_DAYS"]),
        prompt_class=family,
    )
    criteria_rows: list[dict] = []

    try:
        rendered, gt = _render_for_prompt(encounter_id, prompt_id, loader)
        ground_truth = gt.get("label") or ""

        if not rendered.strip():
            result.error = "empty render"
            result.runtime_s = time.time() - t_start
            return result, criteria_rows

        full_prompt = f"{PROMPT_TEXT[prompt_id]}\n\n---\n\n{rendered}"

        # MUT call
        mut_resp = call_llm(
            model=mut_model,
            system=MUT_SYSTEM,
            user=full_prompt,
            max_tokens=2048,
            temperature=0.0,
        )
        model_response = mut_resp.text
        result.mut_cost_usd = mut_resp.cost_usd
        result.n_input_tokens = mut_resp.input_tokens
        result.n_output_tokens = mut_resp.output_tokens
        result.model_response_excerpt = model_response[:400]
        result.ground_truth_excerpt = ground_truth[:200]

        # Judges
        judges = judges_for(prompt_id, los_bucket)
        rubric = criteria_for(prompt_id)
        per_judge_rubric: dict[str, float] = {}
        per_judge_universal: dict[str, float] = {}
        judge_cost_total = 0.0

        for judge_model in judges:
            # Rubric criteria
            results_rubric: dict[str, str] = {}
            for criterion in rubric:
                try:
                    answer, rationale, resp = _call_judge_criterion(
                        judge_model, criterion, full_prompt, ground_truth, model_response,
                    )
                except Exception as e:
                    answer, rationale = "no", f"judge_error: {e}"
                    resp = None
                results_rubric[criterion["id"]] = answer
                if resp is not None:
                    judge_cost_total += resp.cost_usd
                criteria_rows.append({
                    "encounter_id": encounter_id,
                    "prompt_id": prompt_id,
                    "mut_model": mut_model,
                    "judge": judge_model,
                    "criterion_id": criterion["id"],
                    "criterion_question": criterion["question"][:200],
                    "criterion_points": criterion["points"],
                    "answer": answer,
                    "rationale": rationale,
                    "scope": "rubric",
                })
            per_judge_rubric[judge_model] = score_from_results(rubric, results_rubric)

            # Universal criteria
            results_univ: dict[str, str] = {}
            for u in UNIVERSAL_CRITERIA:
                try:
                    answer, rationale, resp = _call_judge_criterion(
                        judge_model, u, full_prompt, ground_truth, model_response,
                    )
                except Exception as e:
                    answer, rationale = "no", f"judge_error: {e}"
                    resp = None
                results_univ[u["id"]] = answer
                if resp is not None:
                    judge_cost_total += resp.cost_usd
                criteria_rows.append({
                    "encounter_id": encounter_id,
                    "prompt_id": prompt_id,
                    "mut_model": mut_model,
                    "judge": judge_model,
                    "criterion_id": u["id"],
                    "criterion_question": u["question"][:200],
                    "criterion_points": u["points"],
                    "answer": answer,
                    "rationale": rationale,
                    "scope": "universal",
                })
            per_judge_universal[judge_model] = score_from_results(UNIVERSAL_CRITERIA, results_univ)

        # Aggregate
        from judge_routing import SONNET, GPT_MINI, GEMINI_FLASH
        result.score_sonnet = per_judge_rubric.get(SONNET)
        result.score_gpt_mini = per_judge_rubric.get(GPT_MINI)
        result.score_gemini = per_judge_rubric.get(GEMINI_FLASH)
        result.score_universal_sonnet = per_judge_universal.get(SONNET)
        result.score_universal_gpt_mini = per_judge_universal.get(GPT_MINI)
        result.score_universal_gemini = per_judge_universal.get(GEMINI_FLASH)

        rubric_scores = [s for s in (result.score_sonnet, result.score_gpt_mini, result.score_gemini) if s is not None]
        if rubric_scores:
            result.score_mean = sum(rubric_scores) / len(rubric_scores)

        # Pairwise deltas (only if both values present)
        def _delta(a, b):
            return abs(a - b) if (a is not None and b is not None) else None
        result.delta_sonnet_gpt = _delta(result.score_sonnet, result.score_gpt_mini)
        result.delta_sonnet_gemini = _delta(result.score_sonnet, result.score_gemini)
        result.delta_gpt_gemini = _delta(result.score_gpt_mini, result.score_gemini)
        deltas = [d for d in (result.delta_sonnet_gpt, result.delta_sonnet_gemini, result.delta_gpt_gemini) if d is not None]
        if deltas:
            result.judge_delta_max = max(deltas)

        result.judge_cost_usd = judge_cost_total
        result.total_cost_usd = result.mut_cost_usd + judge_cost_total

    except Exception as e:
        result.error = f"{type(e).__name__}: {str(e)[:200]}"

    result.runtime_s = time.time() - t_start
    return result, criteria_rows


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def already_done(encounter_id: str, prompt_id: str, mut_model: str) -> bool:
    if not PER_CASE_CSV.exists() or PER_CASE_CSV.stat().st_size == 0:
        return False
    try:
        df = pd.read_csv(PER_CASE_CSV)
    except (pd.errors.EmptyDataError, pd.errors.ParserError):
        return False
    if df.empty or "mut_model" not in df.columns:
        return False
    return (
        (df["encounter_id"] == encounter_id)
        & (df["prompt_id"] == prompt_id)
        & (df["mut_model"] == mut_model)
    ).any()


def _write_result(result: RunResult, criteria_rows: list[dict],
                  case_writer: csv.DictWriter, crit_writer: csv.DictWriter,
                  case_fh, crit_fh) -> None:
    with _WRITE_LOCK:
        case_writer.writerow(asdict(result))
        case_fh.flush()
        for row in criteria_rows:
            crit_writer.writerow(row)
        crit_fh.flush()


def main() -> None:
    global OUT_DIR, PER_CASE_CSV, CRITERIA_LONG_CSV, RUN_LOG

    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=str, required=True,
                        help="CSV file with the case list (must have ENCOUNTER_ID, OMNY_ID, COMPLEXITY_TIER, LOS_BUCKET, PROTEGE_SCORE, LOS_DAYS, PRIMARY_DX_CODE)")
    parser.add_argument("--tables-dir", type=str, default=None,
                        help="Directory containing OMNY CSVs (encounters.csv, notes.csv, etc.). "
                             "Defaults to project-bayes/tables. For the PSI dataset use psi/outputs/aggregated/tables.")
    parser.add_argument("--cache-dir", type=str, default=None,
                        help="Optional parquet cache dir. Defaults to project-bayes/cache.")
    parser.add_argument("--out-dir", type=str, default=None,
                        help=f"Output directory for per_case_scores + criteria_long CSVs. "
                             f"Defaults to {OUT_DIR}")
    parser.add_argument("--prompts", type=str, default=",".join(DEFAULT_PROMPTS),
                        help=f"Comma-separated prompt IDs (default: {','.join(DEFAULT_PROMPTS)})")
    parser.add_argument("--muts", type=str, default=",".join(DEFAULT_MUTS),
                        help=f"Comma-separated MUT model IDs (default: {','.join(DEFAULT_MUTS)})")
    parser.add_argument("--concurrency", type=int, default=10,
                        help="Number of concurrent (case, prompt, mut) tasks (default 10)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Optional cap on number of tasks (for testing)")
    args = parser.parse_args()

    if args.out_dir:
        OUT_DIR = Path(args.out_dir)
        PER_CASE_CSV = OUT_DIR / "per_case_scores.csv"
        CRITERIA_LONG_CSV = OUT_DIR / "criteria_long.csv"
        RUN_LOG = OUT_DIR / "run_log.jsonl"

    OUT_DIR.mkdir(exist_ok=True, parents=True)
    cases = pd.read_csv(args.cases)
    prompts = args.prompts.split(",")
    muts = args.muts.split(",")

    # Build task list
    tasks = []
    for _, case in cases.iterrows():
        for pid in prompts:
            for mut in muts:
                if already_done(case["ENCOUNTER_ID"], pid, mut):
                    continue
                tasks.append((case, pid, mut))
    if args.limit:
        tasks = tasks[:args.limit]

    print(f"Parallel eval run")
    print(f"  Cases:       {len(cases)}")
    print(f"  Prompts:     {prompts}")
    print(f"  MUTs:        {muts}")
    print(f"  Tasks total: {len(cases) * len(prompts) * len(muts)}")
    print(f"  Pending:     {len(tasks)} (already-completed tasks skipped)")
    print(f"  Concurrency: {args.concurrency}")
    print(f"  Output:      {OUT_DIR}")
    print()

    if not tasks:
        print("Nothing to do.")
        return

    loader_kwargs = {"cases_csv": Path(args.cases)}
    if args.tables_dir:
        loader_kwargs["tables_dir"] = Path(args.tables_dir)
    if args.cache_dir:
        loader_kwargs["cache_dir"] = Path(args.cache_dir)
    loader = EncounterDataLoader(**loader_kwargs)

    # Open CSVs
    case_is_new = not PER_CASE_CSV.exists()
    case_fh = PER_CASE_CSV.open("a", newline="")
    case_writer = csv.DictWriter(case_fh, fieldnames=list(RunResult.__dataclass_fields__.keys()))
    if case_is_new:
        case_writer.writeheader()
        case_fh.flush()

    crit_is_new = not CRITERIA_LONG_CSV.exists()
    crit_fh = CRITERIA_LONG_CSV.open("a", newline="")
    crit_writer = csv.DictWriter(crit_fh, fieldnames=[
        "encounter_id", "prompt_id", "mut_model", "judge", "criterion_id", "criterion_question",
        "criterion_points", "answer", "rationale", "scope",
    ])
    if crit_is_new:
        crit_writer.writeheader()
        crit_fh.flush()

    t_start = time.time()
    n_done = 0
    n_errors = 0
    total_cost = 0.0

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = {
            pool.submit(run_one_task, case, pid, mut, loader): (case["ENCOUNTER_ID"], pid, mut)
            for (case, pid, mut) in tasks
        }
        for fut in as_completed(futures):
            enc, pid, mut = futures[fut]
            try:
                result, criteria_rows = fut.result()
                _write_result(result, criteria_rows, case_writer, crit_writer, case_fh, crit_fh)
                n_done += 1
                total_cost += result.total_cost_usd
                if result.error:
                    n_errors += 1
                    print(f"  [{n_done}/{len(tasks)}] {enc[:8]}/{pid}/{mut[:14]} ERROR: {result.error}")
                else:
                    score = result.score_mean if result.score_mean is not None else 0.0
                    print(f"  [{n_done}/{len(tasks)}] {enc[:8]}/{pid}/{mut[:14]} "
                          f"score={score:.2f} cost=${result.total_cost_usd:.3f} "
                          f"runtime={result.runtime_s:.1f}s")
            except Exception as e:
                n_errors += 1
                with RUN_LOG.open("a") as log:
                    log.write(json.dumps({"encounter_id": enc, "prompt_id": pid, "mut": mut,
                                          "error": str(e)}) + "\n")

    case_fh.close()
    crit_fh.close()

    elapsed = time.time() - t_start
    print(f"\n{'='*70}")
    print(f"Done. {n_done}/{len(tasks)} tasks, {n_errors} errors.")
    print(f"  Total cost: ${total_cost:.2f}")
    print(f"  Total time: {elapsed/60:.1f} min ({elapsed/max(n_done,1):.1f}s/task avg)")
    print(f"  Output: {PER_CASE_CSV}")


if __name__ == "__main__":
    main()
