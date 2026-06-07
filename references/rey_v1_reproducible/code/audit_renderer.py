"""
Audit the renderer + ground-truth extractors across a sample of cases.

For each (case, prompt) combination tested, records:
  - rendered input length (chars and approximate tokens)
  - ground truth length
  - flags for: empty GT, extremely-short GT, duplicate text in render,
    duplicate text in GT, large render size, common-but-questionable patterns

Output: a CSV of anomalies + a small JSON sample of the most interesting cases
for Allison's review.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

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


OUT = Path(__file__).parent / "renderer_audit"
OUT.mkdir(exist_ok=True)


PROMPTS_TO_AUDIT = ["S1", "S5", "C1", "C8", "P3", "P7", "P10"]


def _render_input(enc, pid, loader):
    """Match run_eval._render_for_prompt behavior."""
    if pid in ("S1", "S5", "C1"):
        nid = select_target_note(enc, "h&p adult", loader)
        if nid is None:
            return "", None
        return render_single_note(enc, nid, loader), nid
    if pid == "P7":
        rendered, cutoff = render_p7(enc, loader)
        return rendered, None
    return render(enc, pid, loader=loader), None


def _count_duplicate_lines(text: str) -> int:
    """How many duplicate lines exist (informally)."""
    if not text:
        return 0
    lines = [l.strip() for l in text.split("\n") if l.strip() and len(l.strip()) > 30]
    return len(lines) - len(set(lines))


def audit_one(case, pid, loader):
    enc = case["ENCOUNTER_ID"]
    try:
        rendered, target_note_id = _render_input(enc, pid, loader)
        gt = extract_ground_truth(enc, pid, loader, target_note_id=target_note_id)
    except Exception as e:
        return {"flags": [f"error: {type(e).__name__}: {str(e)[:60]}"], "render_chars": 0, "gt_chars": 0,
                "render_dup_lines": 0, "gt_dup_lines": 0, "gt_label": ""}

    gt_label = gt.get("label") or ""
    flags = []
    if not rendered.strip():
        flags.append("empty_render")
    if not gt_label.strip():
        flags.append("empty_gt")
    elif len(gt_label) < 20:
        flags.append("very_short_gt")
    render_dup = _count_duplicate_lines(rendered)
    if render_dup > 5:
        flags.append(f"render_dup_lines={render_dup}")
    gt_dup = _count_duplicate_lines(gt_label)
    if gt_dup > 0:
        flags.append(f"gt_dup_lines={gt_dup}")
    if len(rendered) > 500_000:
        flags.append("very_large_render")
    # Check for suspicious patterns
    if "[REDACTED]" in rendered:
        flags.append("has_redactions")
    if "Patient was compassionately extubated" in rendered or "expired" in rendered.lower()[:500]:
        flags.append("suspicious_eol_content_in_input")
    return {
        "flags": flags,
        "render_chars": len(rendered),
        "gt_chars": len(gt_label),
        "render_dup_lines": render_dup,
        "gt_dup_lines": gt_dup,
        "gt_label_excerpt": gt_label[:80],
    }


def main(n_per_cell: int = 3, n_cells_max: int = 12):
    loader = EncounterDataLoader()
    cases = loader.cases
    audit_rows = []
    samples_by_flag = defaultdict(list)

    print(f"Auditing {n_per_cell} cases per cell × {n_cells_max} cells × {len(PROMPTS_TO_AUDIT)} prompts...")
    cell_count = 0
    for (tier, los), grp in cases.groupby(["COMPLEXITY_TIER", "LOS_BUCKET"]):
        cell_count += 1
        if cell_count > n_cells_max:
            break
        sample = grp.head(n_per_cell)
        print(f"\nCell {tier}/{los} ({len(sample)} cases):")
        for _, case in sample.iterrows():
            enc = case["ENCOUNTER_ID"]
            for pid in PROMPTS_TO_AUDIT:
                result = audit_one(case, pid, loader)
                row = {
                    "encounter_id": enc,
                    "tier": tier,
                    "los_bucket": los,
                    "prompt_id": pid,
                    "render_chars": result["render_chars"],
                    "gt_chars": result["gt_chars"],
                    "render_dup_lines": result["render_dup_lines"],
                    "gt_dup_lines": result["gt_dup_lines"],
                    "flags": ",".join(result["flags"]),
                    "gt_label_excerpt": result["gt_label_excerpt"],
                }
                audit_rows.append(row)
                # Track samples per flag type
                for f in result["flags"]:
                    base_flag = f.split("=")[0] if "=" in f else f
                    if len(samples_by_flag[base_flag]) < 5:
                        samples_by_flag[base_flag].append((enc[:8], pid, f, result["gt_label_excerpt"]))
            print(f"  {enc[:8]}: rendered+graded {len(PROMPTS_TO_AUDIT)} prompts")

    # Save audit CSV
    audit_df = pd.DataFrame(audit_rows)
    audit_path = OUT / "audit.csv"
    audit_df.to_csv(audit_path, index=False)

    # Summary stats
    print(f"\n{'='*70}")
    print(f"AUDIT COMPLETE — {len(audit_df)} (case, prompt) combinations checked")
    print(f"{'='*70}\n")

    print("Flag frequency:")
    flag_counts = defaultdict(int)
    for row in audit_rows:
        for f in row["flags"].split(",") if row["flags"] else []:
            base = f.split("=")[0] if "=" in f else f
            flag_counts[base] += 1
    for flag, n in sorted(flag_counts.items(), key=lambda x: -x[1]):
        print(f"  {flag:30s}  {n:4d} occurrences")

    print(f"\nExample affected cases per flag:")
    for flag, samples in samples_by_flag.items():
        print(f"\n  [{flag}]")
        for s in samples:
            print(f"    {s[0]} / {s[1]}: {s[2]} | gt_excerpt={s[3]!r}")

    # Per-prompt summary
    print(f"\n\nPer-prompt anomaly rate:")
    for pid in PROMPTS_TO_AUDIT:
        sub = audit_df[audit_df.prompt_id == pid]
        n_total = len(sub)
        flags_col = sub["flags"].fillna("").astype(str)
        n_flagged = (flags_col != "").sum()
        n_empty_gt = flags_col.str.contains("empty_gt", na=False).sum()
        n_short_gt = flags_col.str.contains("very_short_gt", na=False).sum()
        n_render_dup = flags_col.str.contains("render_dup", na=False).sum()
        print(f"  {pid}: {n_flagged}/{n_total} flagged (empty_gt={n_empty_gt}, short_gt={n_short_gt}, render_dups={n_render_dup})")

    print(f"\nFull audit at {audit_path}")
    return audit_df


if __name__ == "__main__":
    main()
