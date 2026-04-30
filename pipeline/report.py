"""Report generator — Markdown reports per project + combined summary."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from models.schemas import (
    EvaluationResult, ExtractionRun, ProjectManifest, ReviewSession, TakeoffItem,
)


def _table(items: list[TakeoffItem], max_rows: int = 40) -> str:
    if not items:
        return "_No items._\n"
    hdr = "| # | Description | Category | Qty | Unit | Sheet | Conf |\n"
    sep = "|---|-------------|----------|-----|------|-------|------|\n"
    rows = []
    for i, it in enumerate(items[:max_rows], 1):
        qty = f"{it.quantity:,.1f}" if it.quantity is not None else "—"
        rows.append(f"| {i} | {it.description[:55]} | {it.category} | {qty} | {it.unit} | {it.source_sheet[:25]} | {it.confidence.value} |")
    out = hdr + sep + "\n".join(rows)
    if len(items) > max_rows:
        out += f"\n\n_...{len(items) - max_rows} more — see JSON output._"
    return out


def generate_project_report(
    manifest: ProjectManifest,
    run: ExtractionRun,
    eval_result: Optional[EvaluationResult],
    review_session: Optional[ReviewSession],
    output_dir: Path,
) -> Path:
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    L = []
    L.append(f"# Takeoff Report — {manifest.project_id}: {manifest.project_name}")
    L.append(f"_Generated: {ts}_\n")

    L.append("## Project Overview")
    L.append(f"- **Type**: {manifest.project_type.value}")
    L.append(f"- **Input files**: {len(manifest.input_files)}")
    L.append(f"- **Gold files**: {len(manifest.gold_files)}")
    for note in manifest.notes:
        L.append(f"- ⚠ {note}")
    L.append("")

    L.append("## Extraction")
    L.append(f"- **Model**: {run.model} ({run.provider})")
    L.append(f"- **Pages processed**: {run.pages_processed}")
    L.append(f"- **Items extracted**: {run.items_extracted}")
    L.append(f"- **Duration**: {run.duration_seconds}s")
    if run.is_mock:
        L.append("- ⚠ **MOCK RUN** — set `ANTHROPIC_API_KEY` in `.env` for real extraction")
    for e in run.errors[:5]:
        L.append(f"- ✗ {e}")
    L.append("")

    items = review_session.final_items if review_session else run.items
    L.append(f"## Takeoff Line Items ({len(items)} total)")
    L.append(_table(items))
    L.append("")

    if eval_result and eval_result.gold_item_count > 0:
        L.append("## Evaluation vs Gold")
        L.append("| Metric | Value |")
        L.append("|--------|-------|")
        for label, val in [
            ("Gold items", eval_result.gold_item_count),
            ("Predicted items", eval_result.predicted_item_count),
            ("Matched", len(eval_result.matched)),
            ("Missed (in gold, not predicted)", len(eval_result.missed)),
            ("Extras (predicted, not in gold)", len(eval_result.extras)),
            ("**Precision**", f"**{eval_result.precision:.1%}**"),
            ("**Recall**", f"**{eval_result.recall:.1%}**"),
            ("**F1**", f"**{eval_result.f1:.1%}**"),
            ("Quantity accuracy (≤10% diff)", f"{eval_result.quantity_accuracy:.1%}"),
        ]:
            L.append(f"| {label} | {val} |")
        L.append("")
        if eval_result.missed:
            L.append("### Missed Items")
            L.append(_table(eval_result.missed, 20))
            L.append("")
        if eval_result.extras:
            L.append("### Extra Items (not in gold)")
            L.append(_table(eval_result.extras, 20))
            L.append("")
    elif eval_result:
        for note in eval_result.notes:
            L.append(f"> {note}")
        L.append("")

    if review_session:
        L.append("## Human Review")
        L.append(f"- Status: {review_session.status}")
        L.append(f"- Corrections applied: {len(review_session.corrections)}")
        L.append(f"- Final item count: {len(review_session.final_items)}")
        L.append("")

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{manifest.project_id}_report.md"
    path.write_text("\n".join(L))
    return path


def generate_summary(
    results: list[tuple[ProjectManifest, ExtractionRun, Optional[EvaluationResult]]],
    output_dir: Path,
) -> Path:
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    L = [f"# AI Takeoff System — Summary Report", f"_Generated: {ts}_\n",
         f"**Projects processed**: {len(results)}\n"]
    L.append("| Project | Name | Type | Pages | Items | P | R | F1 | AI |")
    L.append("|---------|------|------|-------|-------|---|---|----|----|")
    for manifest, run, ev in results:
        p = f"{ev.precision:.0%}" if ev and ev.gold_item_count else "—"
        r = f"{ev.recall:.0%}" if ev and ev.gold_item_count else "—"
        f1 = f"{ev.f1:.0%}" if ev and ev.gold_item_count else "—"
        ai = "⚠ mock" if run.is_mock else run.model.split("/")[-1][:15]
        items = str(run.items_extracted) if run.items_extracted > 0 else "⚠ 0"
        L.append(f"| {manifest.project_id} | {manifest.project_name[:25]} | {manifest.project_type.value} | {run.pages_processed} | {items} | {p} | {r} | {f1} | {ai} |")
    L.append("\n> P/R/F1 only shown for sample projects with gold outputs.")
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "SUMMARY_REPORT.md"
    path.write_text("\n".join(L))
    print(f"[report] Summary → {path}")
    return path
