"""
Smoke test for Project Bayes — renders 3 cases × 3 prompts and dumps prompts +
ground truth side-by-side. Does NOT call any LLMs. Validates the renderer
end-to-end against real OMNY data before we spend a dollar on judge calls.

Run:
    python3 smoke_test.py

Outputs:
    smoke_test_output/
      case_<n>/
        <prompt_id>_input.txt
        <prompt_id>_ground_truth.txt
        case_summary.json
"""

from __future__ import annotations

import json
from pathlib import Path

from renderer import (
    EncounterDataLoader,
    extract_ground_truth,
    render,
    select_target_note,
    render_single_note,
)

OUT_DIR = Path(__file__).parent / "smoke_test_output"
PROMPTS_TO_TEST = ["S1", "C1", "P7"]
N_CASES = 3
CELL_TIER = "easy"
CELL_LOS = "short"


PROMPT_TEXT = {
    "S1": "Extract the chief complaint (or reason for admission) from the admission H&P below.",
    "C1": "Summarize the Assessment and Plan from the admission H&P below. Specify the date of the note. Limit your summary to that note only.",
    "P7": "A lab panel has been ordered for this patient. Based on the clinical context (notes, prior labs, vitals), predict the values of the next lab panel. For each lab predicted, give value and units.",
}


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    loader = EncounterDataLoader()
    cases = loader.cases
    cell = cases[(cases["COMPLEXITY_TIER"] == CELL_TIER) & (cases["LOS_BUCKET"] == CELL_LOS)]
    if cell.empty:
        raise RuntimeError(f"No cases in cell {CELL_TIER}/{CELL_LOS}")
    selected = cell.head(N_CASES)

    summary = {
        "cell": f"{CELL_TIER}/{CELL_LOS}",
        "n_cases": N_CASES,
        "prompts": PROMPTS_TO_TEST,
        "cases": [],
    }

    for i, (_, case) in enumerate(selected.iterrows(), start=1):
        enc_id = case["ENCOUNTER_ID"]
        case_dir = OUT_DIR / f"case_{i}_{enc_id[:8]}"
        case_dir.mkdir(exist_ok=True)

        case_record = {
            "case_index": i,
            "encounter_id": enc_id,
            "institution": case["INSTITUTION_NAME"],
            "protege_score": int(case["PROTEGE_SCORE"]),
            "los_days": int(case["LOS_DAYS"]),
            "primary_dx": case["PRIMARY_DX_CODE"],
            "n_notes": int(case["N_NOTES"]),
            "n_labs": int(case["N_LAB_RESULTS"]),
            "prompts": {},
        }

        print(f"\n=== Case {i}: {enc_id} ({case['INSTITUTION_NAME']}) ===")
        print(f"  LOS={case['LOS_DAYS']}d, score={case['PROTEGE_SCORE']}, "
              f"notes={case['N_NOTES']}, labs={case['N_LAB_RESULTS']}")

        for pid in PROMPTS_TO_TEST:
            # For single-note prompts (S1, C1) we render only the target note.
            if pid in ("S1", "C1"):
                note_id = select_target_note(enc_id, "h&p adult", loader)
                if note_id is None:
                    rendered = "(no admission H&P found)"
                else:
                    from renderer import TruncationSpec
                    truncation = TruncationSpec()
                    if pid == "C1":
                        # No truncation — we want the full note for the model to summarize
                        pass
                    rendered = render_single_note(enc_id, note_id, loader, truncation=truncation)
                gt = extract_ground_truth(enc_id, pid, loader, target_note_id=note_id)
            else:
                rendered = render(enc_id, pid, loader=loader)
                gt = extract_ground_truth(enc_id, pid, loader)

            input_path = case_dir / f"{pid}_input.txt"
            gt_path = case_dir / f"{pid}_ground_truth.txt"
            full_prompt = f"{PROMPT_TEXT[pid]}\n\n---\n\n{rendered}"

            input_path.write_text(full_prompt)
            gt_path.write_text(
                f"PROMPT: {pid}\nMETADATA: {gt.get('metadata', {})}\n\n"
                f"GROUND TRUTH:\n{gt.get('label', '')}\n"
            )

            case_record["prompts"][pid] = {
                "input_chars": len(full_prompt),
                "input_tokens_est": len(full_prompt) // 4,
                "gt_chars": len(gt.get("label", "") or ""),
                "gt_metadata": gt.get("metadata", {}),
            }

            print(f"  [{pid}] input={len(full_prompt)} chars (~{len(full_prompt)//4} tok), "
                  f"gt={len(gt.get('label','') or '')} chars")

        summary["cases"].append(case_record)

    summary_path = OUT_DIR / "case_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, default=str))

    print(f"\n✓ Smoke test artifacts written to {OUT_DIR}")
    print(f"  Cases: {N_CASES}")
    print(f"  Prompts per case: {len(PROMPTS_TO_TEST)}")
    print(f"  Inputs total: {sum(p['input_chars'] for c in summary['cases'] for p in c['prompts'].values())} chars")
    print(f"  GT total: {sum(p['gt_chars'] for c in summary['cases'] for p in c['prompts'].values())} chars")
    print(f"  Estimated total input tokens: ~{sum(p['input_tokens_est'] for c in summary['cases'] for p in c['prompts'].values())}")


if __name__ == "__main__":
    main()
