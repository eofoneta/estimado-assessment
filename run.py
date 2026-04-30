#!/usr/bin/env python3
"""
AI Takeoff System — main entrypoint.

Usage:
  python run.py all                          # full pipeline
  python run.py ingest                       # index files only
  python run.py extract                      # extract all projects
  python run.py extract --project TAKEOFF-28 # single project
  python run.py evaluate
  python run.py review queue
  python run.py review apply
  python run.py report

Requires: copy .env.example to .env and set ANTHROPIC_API_KEY or OPENAI_API_KEY.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

sys.path.insert(0, str(Path(__file__).parent))

from pipeline.ingest import ingest_dataset, save_manifests
from pipeline.extract import extract_project
from pipeline.evaluate import evaluate_project
from pipeline.human_review import build_review_queue, apply_corrections
from pipeline.report import generate_project_report, generate_summary
from pipeline.export import export_all
from models.schemas import ExtractionRun, EvaluationResult, ProjectManifest, ProjectType, ReviewSession

DATASET_ROOT = Path(os.getenv("DATASET_ROOT", "")).expanduser()
if not DATASET_ROOT or not DATASET_ROOT.exists():
    # Auto-detect: look for the dataset folder relative to this file
    _candidates = [
        Path(__file__).parent.parent / "AI Takeoff Builder Challenge - Assessment 1.0",
        Path(__file__).parent / "dataset",
        Path.home() / "Downloads" / "AI Takeoff Builder Challenge - Assessment 1.0",
    ]
    for _c in _candidates:
        if _c.exists():
            DATASET_ROOT = _c
            break
    else:
        raise SystemExit(
            "\n❌ Dataset not found. Set DATASET_ROOT in your .env file:\n"
            "   DATASET_ROOT=/path/to/AI Takeoff Builder Challenge - Assessment 1.0\n"
        )
BASE = Path(__file__).parent
MANIFESTS = BASE / "outputs" / "manifests"
PREDICTIONS = BASE / "outputs" / "predictions"
EVALUATIONS = BASE / "outputs" / "evaluations"
REPORTS = BASE / "outputs" / "reports"
EXPORTS = BASE / "outputs" / "exports"


def _load_manifests(project_filter: str | None = None) -> list[ProjectManifest]:
    if not MANIFESTS.exists() or not list(MANIFESTS.glob("*.json")):
        manifests = ingest_dataset(DATASET_ROOT)
        save_manifests(manifests, MANIFESTS)
    else:
        manifests = [ProjectManifest(**json.loads(p.read_text())) for p in sorted(MANIFESTS.glob("*_manifest.json"))]
    if project_filter:
        manifests = [m for m in manifests if m.project_id.upper() == project_filter.upper()]
    return manifests


def step_ingest(pf=None):
    print("\n=== INGEST ===")
    manifests = ingest_dataset(DATASET_ROOT)
    for m in manifests:
        print(f"  {m.project_id} ({m.project_type.value}) — {len(m.input_files)} input, {len(m.gold_files)} gold")
        for n in m.notes:
            print(f"    ⚠ {n}")
    save_manifests(manifests, MANIFESTS)


def step_extract(pf=None):
    print("\n=== EXTRACT ===")
    manifests = _load_manifests(pf)
    for m in manifests:
        # Extract gold files for sample projects
        if m.project_type == ProjectType.SAMPLE and m.gold_files:
            extract_project(m, PREDICTIONS, is_gold=True)
        # Extract input files
        if m.input_files:
            extract_project(m, PREDICTIONS, is_gold=False)
        else:
            print(f"  [{m.project_id}] No input files — skipping input extraction")


def step_evaluate(pf=None):
    print("\n=== EVALUATE ===")
    for m in _load_manifests(pf):
        pred_path = PREDICTIONS / f"{m.project_id}_extraction.json"
        gold_path = PREDICTIONS / f"{m.project_id}_gold_extraction.json"

        # TAKEOFF-28 style: only gold extraction exists, no separate input extraction
        if not pred_path.exists() and gold_path.exists():
            print(f"  [{m.project_id}] No input extraction — showing gold items as reference only")
            run = ExtractionRun(**json.loads(gold_path.read_text()))
            evaluate_project(m.project_id, run, None, EVALUATIONS)
            continue

        if not pred_path.exists():
            print(f"  [{m.project_id}] No extraction found — run extract first")
            continue

        run = ExtractionRun(**json.loads(pred_path.read_text()))
        evaluate_project(m.project_id, run, gold_path if gold_path.exists() else None, EVALUATIONS)


def step_review_queue(pf=None):
    print("\n=== REVIEW QUEUE ===")
    for m in _load_manifests(pf):
        pred_path = PREDICTIONS / f"{m.project_id}_extraction.json"
        if not pred_path.exists():
            continue
        run = ExtractionRun(**json.loads(pred_path.read_text()))
        eval_path = EVALUATIONS / f"{m.project_id}_evaluation.json"
        ev = EvaluationResult(**json.loads(eval_path.read_text())) if eval_path.exists() else None
        build_review_queue(run, ev, EVALUATIONS)


def step_review_apply(pf=None):
    print("\n=== APPLY CORRECTIONS ===")
    for m in _load_manifests(pf):
        pred_path = PREDICTIONS / f"{m.project_id}_extraction.json"
        queue_path = EVALUATIONS / f"{m.project_id}_review_queue.json"
        if not pred_path.exists() or not queue_path.exists():
            continue
        run = ExtractionRun(**json.loads(pred_path.read_text()))
        apply_corrections(run, queue_path, EVALUATIONS)


def step_report(pf=None):
    print("\n=== REPORTS ===")
    summary_data = []
    for m in _load_manifests(pf):
        # For projects with only gold files (e.g. TAKEOFF-28), report on gold extraction
        pred_path = PREDICTIONS / f"{m.project_id}_extraction.json"
        gold_pred_path = PREDICTIONS / f"{m.project_id}_gold_extraction.json"
        if not pred_path.exists():
            if gold_pred_path.exists():
                pred_path = gold_pred_path
            else:
                continue
        run = ExtractionRun(**json.loads(pred_path.read_text()))
        eval_path = EVALUATIONS / f"{m.project_id}_evaluation.json"
        ev = EvaluationResult(**json.loads(eval_path.read_text())) if eval_path.exists() else None
        session_path = EVALUATIONS / f"{m.project_id}_review_session.json"
        session = ReviewSession(**json.loads(session_path.read_text())) if session_path.exists() else None
        p = generate_project_report(m, run, ev, session, REPORTS)
        print(f"  [{m.project_id}] → {p.name}")
        summary_data.append((m, run, ev))
    if summary_data:
        generate_summary(summary_data, REPORTS)


def step_export(pf=None):
    manifests = _load_manifests(pf)
    export_all(manifests, PREDICTIONS, EVALUATIONS, EXPORTS)


def run_all(pf=None):
    step_ingest(pf)
    step_extract(pf)
    step_evaluate(pf)
    step_review_queue(pf)
    step_report(pf)
    step_export(pf)
    print("\n✅ Done. See outputs/reports/ and outputs/exports/ for results.")


def main():
    args = sys.argv[1:]
    pf = None
    if "--project" in args:
        i = args.index("--project")
        pf = args[i + 1] if i + 1 < len(args) else None
        args = [a for j, a in enumerate(args) if j not in (i, i + 1)]

    cmd = args[0] if args else "all"
    sub = args[1] if len(args) > 1 else ""

    cmds = {
        "ingest": step_ingest,
        "extract": step_extract,
        "evaluate": step_evaluate,
        "review": lambda pf: step_review_queue(pf) if sub != "apply" else step_review_apply(pf),
        "report": step_report,
        "export": step_export,
        "all": run_all,
    }
    if cmd not in cmds:
        print(f"Unknown command '{cmd}'. Available: {', '.join(cmds)}")
        sys.exit(1)
    cmds[cmd](pf)


if __name__ == "__main__":
    main()
