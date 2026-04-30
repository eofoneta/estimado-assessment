"""
Evaluation / scoring — fully deterministic. No LLM in the scoring loop.

Matching: token-overlap (Jaccard) on normalised descriptions.
Scoring: Precision, Recall, F1, quantity accuracy (≤10% tolerance).
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Optional

from models.schemas import (
    EvaluationResult, ExtractionRun, MatchedItem, TakeoffItem,
)

MATCH_THRESHOLD = 0.40
QTY_TOLERANCE = 0.10

UNIT_ALIASES = {
    "sqft": "SF", "sq ft": "SF", "sq. ft.": "SF", "sf": "SF", "s.f.": "SF",
    "lf": "LF", "lin ft": "LF", "linear ft": "LF", "l.f.": "LF",
    "ea": "EA", "each": "EA", "pc": "EA", "pcs": "EA",
    "cy": "CY", "cu yd": "CY", "sy": "SY", "sq yd": "SY",
    "ls": "LS", "lump sum": "LS",
    "ton": "TON", "tons": "TON",
}

TRADE_SYNONYMS = {
    "ceramic": "tile", "porcelain": "tile", "vct": "tile",
    "gyp": "drywall", "gypsum": "drywall", "gwb": "drywall",
    "pt": "paint", "painted": "paint",
    "susp": "suspended", "ceil": "ceiling", "clg": "ceiling",
    "corr": "corridor", "rm": "room",
}

_PUNCT = re.compile(r"[^\w\s]")


def _norm(text: str) -> set[str]:
    text = unicodedata.normalize("NFKD", text.lower())
    text = _PUNCT.sub(" ", text)
    return {TRADE_SYNONYMS.get(t, t) for t in text.split()}


def _unit(u: str) -> str:
    return UNIT_ALIASES.get(u.strip().lower(), u.upper())


def _sim(a: str, b: str) -> float:
    ta, tb = _norm(a), _norm(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def match_items(predicted: list[TakeoffItem], gold: list[TakeoffItem]):
    scores = []
    for pi, pred in enumerate(predicted):
        for gi, g in enumerate(gold):
            s = _sim(pred.description, g.description)
            if s >= MATCH_THRESHOLD:
                scores.append((s, pi, gi))
    scores.sort(key=lambda x: -x[0])

    used_pred, used_gold = set(), set()
    matched, missed, extras = [], [], []

    for s, pi, gi in scores:
        if pi in used_pred or gi in used_gold:
            continue
        pred, g = predicted[pi], gold[gi]
        qty_match, qty_diff = False, None
        if pred.quantity is not None and g.quantity is not None and g.quantity != 0:
            diff = abs(pred.quantity - g.quantity) / abs(g.quantity)
            qty_diff = round(diff * 100, 1)
            qty_match = diff <= QTY_TOLERANCE
        elif pred.quantity is None and g.quantity is None:
            qty_match = True
        matched.append(MatchedItem(
            predicted=pred, gold=g,
            description_similarity=round(s, 3),
            quantity_match=qty_match,
            quantity_diff_pct=qty_diff,
            unit_match=_unit(pred.unit) == _unit(g.unit),
        ))
        used_pred.add(pi)
        used_gold.add(gi)

    missed = [gold[i] for i in range(len(gold)) if i not in used_gold]
    extras = [predicted[i] for i in range(len(predicted)) if i not in used_pred]
    return matched, missed, extras


def evaluate_project(
    project_id: str,
    predicted_run: ExtractionRun,
    gold_run_path: Optional[Path],
    output_dir: Path,
) -> EvaluationResult:
    gold_items: list[TakeoffItem] = []
    if gold_run_path and gold_run_path.exists():
        gold_run = ExtractionRun(**json.loads(gold_run_path.read_text()))
        gold_items = gold_run.items

    matched, missed, extras = match_items(predicted_run.items, gold_items)
    tp = len(matched)
    pc = len(predicted_run.items)
    gc = len(gold_items)

    precision = tp / pc if pc > 0 else 0.0
    recall = tp / gc if gc > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    qty_acc = sum(1 for m in matched if m.quantity_match) / tp if tp > 0 else 0.0

    result = EvaluationResult(
        project_id=project_id,
        run_id=predicted_run.run_id,
        gold_item_count=gc,
        predicted_item_count=pc,
        matched=matched,
        missed=missed,
        extras=extras,
        precision=round(precision, 3),
        recall=round(recall, 3),
        f1=round(f1, 3),
        quantity_accuracy=round(qty_acc, 3),
    )
    if not gold_items:
        result.notes.append("No gold data — scoring not applicable for this project.")

    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / f"{project_id}_evaluation.json"
    out.write_text(result.model_dump_json(indent=2))
    print(f"  [{project_id}] P={precision:.2f} R={recall:.2f} F1={f1:.2f} QtyAcc={qty_acc:.2f} "
          f"| {tp} matched, {len(missed)} missed, {len(extras)} extras → {out.name}")
    return result
