"""
Export pipeline — converts internal extraction/evaluation data to the official
output template format defined in 03_Output_Template/03_Output_Template.json.

This is a deterministic post-processing step with no AI calls.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from models.schemas import EvaluationResult, ExtractionRun, ProjectManifest


def _confidence_to_float(conf: str) -> float:
    return {"high": 0.9, "medium": 0.6, "low": 0.3}.get(conf, 0.5)


def export_project(
    manifest: ProjectManifest,
    run: ExtractionRun,
    eval_result: Optional[EvaluationResult],
    output_dir: Path,
) -> Path:
    """
    Write one JSON file per project in the official output template format.
    """
    # Determine trade scope from extracted categories
    categories = list({item.category for item in run.items if item.category})
    trade_scope = " | ".join(sorted(categories)) if categories else "unknown"

    input_files_used = [f.filename for f in manifest.input_files[:20]]

    line_items = []
    items_source = run.items
    for item in items_source:
        line_items.append({
            "description": item.description,
            "quantity": item.quantity,
            "unit": item.unit,
            "confidence": _confidence_to_float(item.confidence.value),
            "source_reference": item.source_sheet,
            "category": item.category,
            "assumptions": item.assumptions,
            "warnings": item.warnings,
        })

    # Evaluation block
    if eval_result and eval_result.gold_item_count > 0:
        evaluation = {
            "matched_items": len(eval_result.matched),
            "missing_items": [
                {"description": i.description, "quantity": i.quantity, "unit": i.unit}
                for i in eval_result.missed[:20]
            ],
            "extra_items": [
                {"description": i.description, "quantity": i.quantity, "unit": i.unit}
                for i in eval_result.extras[:20]
            ],
            "quantity_differences": [
                {
                    "description": m.predicted.description,
                    "predicted": m.predicted.quantity,
                    "gold": m.gold.quantity,
                    "diff_pct": m.quantity_diff_pct,
                }
                for m in eval_result.matched
                if m.quantity_diff_pct and m.quantity_diff_pct > 0
            ][:20],
            "precision": eval_result.precision,
            "recall": eval_result.recall,
            "f1": eval_result.f1,
            "quantity_accuracy": eval_result.quantity_accuracy,
            "overall_notes": (
                f"P={eval_result.precision:.0%} R={eval_result.recall:.0%} "
                f"F1={eval_result.f1:.0%}. "
                f"{len(eval_result.matched)} matched, {len(eval_result.missed)} missed, "
                f"{len(eval_result.extras)} extras."
            ),
        }
    else:
        evaluation = {
            "matched_items": 0,
            "missing_items": [],
            "extra_items": [],
            "quantity_differences": [],
            "overall_notes": "No gold output available for this project (challenge project).",
        }

    output = {
        "project_id": manifest.project_id,
        "project_name": manifest.project_name,
        "project_type": manifest.project_type.value,
        "trade_scope": trade_scope,
        "input_files_used": input_files_used,
        "ai_run": {
            "run_id": run.run_id,
            "model": run.model,
            "provider": run.provider,
            "pages_processed": run.pages_processed,
            "is_mock": run.is_mock,
            "tools_or_models_used": [f"{run.provider}/{run.model}"],
            "assumptions": [
                "Quantities read from visible annotations and schedules only.",
                f"Max {run.pages_processed} pages processed per file.",
                "Items with null quantity could not be measured from available pages.",
            ],
            "warnings": run.errors[:10] + (
                ["Some pages may not have been processed due to file/page limits."]
                if run.pages_processed < len(manifest.input_files) else []
            ),
        },
        "line_items": line_items,
        "evaluation_when_gold_available": evaluation,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{manifest.project_id}_output.json"
    out_path.write_text(json.dumps(output, indent=2))
    return out_path


def export_all(
    manifests: list[ProjectManifest],
    predictions_dir: Path,
    evaluations_dir: Path,
    output_dir: Path,
) -> None:
    """Export all projects to official template format."""
    print("\n=== EXPORT (official template format) ===")
    for manifest in manifests:
        pred_path = predictions_dir / f"{manifest.project_id}_extraction.json"
        gold_path = predictions_dir / f"{manifest.project_id}_gold_extraction.json"

        if not pred_path.exists() and gold_path.exists():
            pred_path = gold_path
        if not pred_path.exists():
            print(f"  [{manifest.project_id}] No extraction — skipping")
            continue

        run = ExtractionRun(**json.loads(pred_path.read_text()))
        eval_path = evaluations_dir / f"{manifest.project_id}_evaluation.json"
        eval_result = EvaluationResult(**json.loads(eval_path.read_text())) if eval_path.exists() else None

        out_path = export_project(manifest, run, eval_result, output_dir)
        print(f"  [{manifest.project_id}] → {out_path.name} ({len(run.items)} items)")
