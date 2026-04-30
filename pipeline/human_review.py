"""
Human review / correction loop.

Workflow:
  1. System writes outputs/evaluations/{project_id}_review_queue.json
     flagging low-confidence, unmatched, and quantity-mismatched items.
  2. Reviewer opens the file, sets "_action" to accept/reject/edit per item,
     and updates _corrected_* fields when editing.
  3. `python run.py review apply` reads corrections and writes a final item list.

Production upgrade path: replace JSON file editing with a Supabase-backed
Next.js review dashboard where reviewers click through items on a split-screen
(blueprint on left, item list on right).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from models.schemas import (
    CorrectionAction, EvaluationResult, ExtractionRun,
    HumanCorrection, ReviewSession, TakeoffItem,
)


def build_review_queue(
    run: ExtractionRun,
    eval_result: Optional[EvaluationResult],
    output_dir: Path,
) -> Path:
    extras_ids = {item.item_id for item in eval_result.extras} if eval_result else set()
    qty_diff_map = {
        m.predicted.item_id: m.quantity_diff_pct
        for m in (eval_result.matched if eval_result else [])
        if m.quantity_diff_pct and m.quantity_diff_pct > 10
    }

    queue = []
    for item in run.items:
        is_extra = item.item_id in extras_ids
        qty_diff = qty_diff_map.get(item.item_id)
        needs_review = (
            item.confidence.value == "low"
            or is_extra
            or qty_diff is not None
            or item.quantity is None
        )
        if not needs_review:
            continue

        flags = []
        if item.confidence.value == "low":
            flags.append("low-confidence")
        if is_extra:
            flags.append("no gold match")
        if qty_diff:
            flags.append(f"qty diff {qty_diff:.1f}%")
        if item.quantity is None:
            flags.append("quantity missing")

        queue.append({
            "_review_flag": "; ".join(flags),
            "_action": "accept",   # reviewer changes to: accept | reject | edit
            "_corrected_description": item.description,
            "_corrected_quantity": item.quantity,
            "_corrected_unit": item.unit,
            "_reviewer_note": "",
            "item_id": item.item_id,
            "description": item.description,
            "category": item.category,
            "quantity": item.quantity,
            "unit": item.unit,
            "source_sheet": item.source_sheet,
            "confidence": item.confidence.value,
            "warnings": item.warnings,
            "assumptions": item.assumptions,
        })

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{run.project_id}_review_queue.json"
    path.write_text(json.dumps(queue, indent=2))
    print(f"  [{run.project_id}] {len(queue)} items queued for review → {path.name}")
    return path


def apply_corrections(run: ExtractionRun, queue_path: Path, output_dir: Path) -> ReviewSession:
    queue = json.loads(queue_path.read_text())
    item_map = {item.item_id: item for item in run.items}

    session = ReviewSession(project_id=run.project_id, run_id=run.run_id, status="complete")
    correction_map: dict[str, HumanCorrection] = {}

    for entry in queue:
        item_id = entry["item_id"]
        action = CorrectionAction(entry.get("_action", "accept").lower().strip())
        original = item_map.get(item_id)
        if not original:
            continue

        corrected = None
        if action == CorrectionAction.EDIT:
            corrected = original.model_copy(update={
                "description": entry.get("_corrected_description", original.description),
                "quantity": entry.get("_corrected_quantity", original.quantity),
                "unit": entry.get("_corrected_unit", original.unit),
            })

        correction_map[item_id] = HumanCorrection(
            project_id=run.project_id,
            run_id=run.run_id,
            item_id=item_id,
            action=action,
            original=original,
            corrected=corrected,
            reviewer_note=entry.get("_reviewer_note", ""),
        )
        session.corrections.append(correction_map[item_id])

    final: list[TakeoffItem] = []
    for item in run.items:
        corr = correction_map.get(item.item_id)
        if corr is None:
            final.append(item)
        elif corr.action == CorrectionAction.REJECT:
            continue
        elif corr.action == CorrectionAction.EDIT and corr.corrected:
            final.append(corr.corrected)
        else:
            final.append(item)

    session.final_items = final
    out = output_dir / f"{run.project_id}_review_session.json"
    out.write_text(session.model_dump_json(indent=2))
    print(f"  [{run.project_id}] {len(session.corrections)} corrections applied, {len(final)} final items → {out.name}")
    return session
