"""
AI extraction pipeline.

DETERMINISTIC: file → image conversion, JSON parsing, file I/O.
AI/MODEL: sending rendered blueprint images to Claude or GPT-4o vision,
          receiving structured JSON takeoff line items back.
FALLBACK: if no API key is set, produces clearly-labelled MOCK items so the
          rest of the pipeline (evaluate, report) can still run end-to-end.
"""
from __future__ import annotations

import base64
import json
import os
import re
import time
from io import BytesIO
from pathlib import Path

from models.schemas import (
    ConfidenceLevel, ExtractionRun, ProjectManifest, TakeoffItem,
)

AI_PROVIDER = os.getenv("AI_PROVIDER", "anthropic").lower()
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-opus-4-5")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-exp:free")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
MAX_PAGES_PER_FILE = int(os.getenv("MAX_PAGES_PER_FILE", "6"))
MAX_FILES_PER_PROJECT = int(os.getenv("MAX_FILES_PER_PROJECT", "999"))
RENDER_DPI = 150

SYSTEM_PROMPT = """You are a senior construction takeoff specialist reviewing construction drawings.
Extract every measurable construction item from the provided drawing page.

Return ONLY a JSON array. Each element must have exactly these fields:
{
  "description": "clear item name e.g. 'Ceramic floor tile - Room 101'",
  "category": "trade e.g. Flooring / Drywall / Painting / Electrical / Plumbing / Structural / Roofing / Doors & Windows / Ceilings / Mechanical / Other",
  "quantity": numeric value or null,
  "unit": "SF | LF | EA | CY | SY | LS | TON | GAL etc.",
  "unit_notes": "clarification if non-standard",
  "source_sheet": "sheet/page reference from title block",
  "assumptions": ["list assumptions"],
  "warnings": ["flag ambiguity, missing scale, overlap risk"],
  "confidence": "high | medium | low",
  "raw_text": "verbatim text from drawing that led to this item"
}

Rules:
- Read quantities from dimensions, schedules, and room tags.
- Use null for quantity if you cannot read it; note it in warnings.
- Flag missing scale bars in warnings.
- One item per distinct material/location.
- Return [] for title pages or legends with no measurable items."""

USER_PROMPT = "Extract all takeoff line items from this drawing. Sheet reference: {sheet_ref}"


# ---------------------------------------------------------------------------
# Image conversion (deterministic)
# ---------------------------------------------------------------------------

def _pdf_page_to_b64(path: Path, page_num: int) -> str:
    import fitz
    doc = fitz.open(str(path))
    page = doc[page_num]
    mat = fitz.Matrix(RENDER_DPI / 72, RENDER_DPI / 72)
    pix = page.get_pixmap(matrix=mat)
    data = pix.tobytes("png")
    doc.close()
    return base64.b64encode(data).decode()


def _tif_to_b64(path: Path) -> str:
    from PIL import Image
    img = Image.open(str(path))
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    if max(img.size) > 2400:
        ratio = 2400 / max(img.size)
        img = img.resize((int(img.width * ratio), int(img.height * ratio)), Image.LANCZOS)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


def _image_to_b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode()


def _file_to_images(path: Path) -> list[tuple[str, str, str]]:
    """Returns list of (b64, sheet_ref, media_type)."""
    ext = path.suffix.lower()
    results = []
    if ext == ".pdf":
        try:
            import fitz
            doc = fitz.open(str(path))
            total = doc.page_count
            doc.close()
            for i in range(min(MAX_PAGES_PER_FILE, total)):
                b64 = _pdf_page_to_b64(path, i)
                results.append((b64, f"{path.name} p{i+1}/{total}", "image/png"))
        except Exception as e:
            print(f"    PDF render error {path.name}: {e}")
    elif ext in (".tif", ".tiff"):
        try:
            results.append((_tif_to_b64(path), path.name, "image/jpeg"))
        except Exception as e:
            print(f"    TIF error {path.name}: {e}")
    elif ext in (".jpg", ".jpeg"):
        results.append((_image_to_b64(path), path.name, "image/jpeg"))
    elif ext == ".png":
        results.append((_image_to_b64(path), path.name, "image/png"))
    return results


# ---------------------------------------------------------------------------
# AI calls
# ---------------------------------------------------------------------------

def _call_anthropic(b64: str, sheet_ref: str, media_type: str) -> list[dict]:
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    resp = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
                {"type": "text", "text": USER_PROMPT.format(sheet_ref=sheet_ref)},
            ],
        }],
    )
    return _parse_json(resp.content[0].text)


def _call_openai(b64: str, sheet_ref: str, media_type: str) -> list[dict]:
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        max_tokens=4096,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{b64}"}},
                {"type": "text", "text": USER_PROMPT.format(sheet_ref=sheet_ref)},
            ]},
        ],
    )
    return _parse_json(resp.choices[0].message.content)


OPENROUTER_USER_PROMPT = """You are reading a construction drawing. List every construction material, item, or quantity visible.
Return ONLY a valid JSON array. Each object must have:
- "description": item name (string)
- "quantity": numeric value only, or null
- "unit": unit of measurement (SF, LF, EA, SY, etc.)
- "source_sheet": "{sheet_ref}"
- "category": trade category (Flooring, Drywall, Painting, Electrical, Plumbing, Roofing, Structural, Other)
- "confidence": "high", "medium", or "low"
- "assumptions": []
- "warnings": []
- "raw_text": exact text from the drawing

Return [] if nothing measurable is visible. No explanation outside the JSON array."""


def _call_openrouter(b64: str, sheet_ref: str, media_type: str) -> list[dict]:
    from openai import OpenAI
    client = OpenAI(
        api_key=os.environ["OPENROUTER_API_KEY"],
        base_url=OPENROUTER_BASE_URL,
    )
    resp = client.chat.completions.create(
        model=OPENROUTER_MODEL,
        max_tokens=4096,
        messages=[
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{b64}"}},
                {"type": "text", "text": OPENROUTER_USER_PROMPT.format(sheet_ref=sheet_ref)},
            ]},
        ],
    )
    content = resp.choices[0].message.content if resp.choices else None
    if not content:
        return []
    return _parse_json(content)


def _parse_json(text: str) -> list[dict]:
    text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            # Handle {"items": [...]} wrapper some models return
            for key in ("items", "line_items", "takeoff_items", "results"):
                if key in data and isinstance(data[key], list):
                    return data[key]
            return [data]
    except json.JSONDecodeError:
        m = re.search(r"\[.*\]", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except Exception:
                pass
    return []


def _has_key() -> bool:
    if AI_PROVIDER == "anthropic":
        return bool(os.getenv("ANTHROPIC_API_KEY"))
    if AI_PROVIDER == "openrouter":
        return bool(os.getenv("OPENROUTER_API_KEY"))
    return bool(os.getenv("OPENAI_API_KEY"))


def _call_ai(b64: str, sheet_ref: str, media_type: str) -> list[dict]:
    if AI_PROVIDER == "anthropic":
        return _call_anthropic(b64, sheet_ref, media_type)
    if AI_PROVIDER == "openrouter":
        return _call_openrouter(b64, sheet_ref, media_type)
    return _call_openai(b64, sheet_ref, media_type)


def _raw_to_item(raw: dict, run_id: str, project_id: str) -> TakeoffItem:
    conf_map = {"high": ConfidenceLevel.HIGH, "medium": ConfidenceLevel.MEDIUM, "low": ConfidenceLevel.LOW}
    qty = raw.get("quantity")
    if qty is not None:
        try:
            qty = float(qty)
        except (TypeError, ValueError):
            qty = None
    return TakeoffItem(
        run_id=run_id,
        project_id=project_id,
        description=str(raw.get("description", "")).strip(),
        category=str(raw.get("category", "")).strip(),
        quantity=qty,
        unit=str(raw.get("unit", "")).strip(),
        unit_notes=str(raw.get("unit_notes", "")).strip(),
        source_sheet=str(raw.get("source_sheet", "")).strip(),
        assumptions=raw.get("assumptions") or [],
        warnings=raw.get("warnings") or [],
        confidence=conf_map.get(str(raw.get("confidence", "medium")).lower(), ConfidenceLevel.MEDIUM),
        raw_text=str(raw.get("raw_text", "")).strip(),
    )


MOCK_ITEMS = [
    {"description": "Floor tile — area TBD (MOCK: no API key)", "category": "Flooring",
     "quantity": None, "unit": "SF", "unit_notes": "", "source_sheet": "MOCK",
     "assumptions": [], "warnings": ["MOCK DATA — add API key to .env for real extraction"], "confidence": "low", "raw_text": ""},
    {"description": "Painted drywall partition (MOCK: no API key)", "category": "Drywall",
     "quantity": None, "unit": "SF", "unit_notes": "", "source_sheet": "MOCK",
     "assumptions": [], "warnings": ["MOCK DATA — add API key to .env for real extraction"], "confidence": "low", "raw_text": ""},
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_project(manifest: ProjectManifest, output_dir: Path, is_gold: bool = False) -> ExtractionRun:
    """
    Extract takeoff items from a project's files.
    is_gold=True processes gold files instead of input files (for sample projects).
    """
    import time as _time
    start = _time.time()
    use_mock = not _has_key()
    model = (ANTHROPIC_MODEL if AI_PROVIDER == "anthropic" else OPENAI_MODEL) if not use_mock else "mock"

    run = ExtractionRun(
        project_id=manifest.project_id,
        model=model,
        provider=AI_PROVIDER if not use_mock else "mock",
        is_mock=use_mock,
    )

    files = manifest.gold_files if is_gold else manifest.input_files
    files = [f for f in files if f.extension.lower() in (".pdf", ".tif", ".tiff", ".jpg", ".jpeg", ".png")]
    files.sort(key=lambda f: {".pdf": 0, ".tif": 1, ".tiff": 1}.get(f.extension.lower(), 2))
    files = files[:MAX_FILES_PER_PROJECT]

    label = "gold" if is_gold else "input"
    print(f"  [{manifest.project_id}] Extracting {label} files ({len(files)} files) ...")

    for project_file in files:
        path = Path(project_file.path)
        if use_mock:
            for raw in MOCK_ITEMS:
                run.items.append(_raw_to_item(raw, run.run_id, manifest.project_id))
            run.pages_processed += 1
            continue

        images = _file_to_images(path)
        for b64, sheet_ref, media_type in images:
            for attempt in range(3):
                try:
                    raw_items = _call_ai(b64, sheet_ref, media_type)
                    for raw in raw_items:
                        run.items.append(_raw_to_item(raw, run.run_id, manifest.project_id))
                    run.pages_processed += 1
                    time.sleep(1.0)
                    break
                except Exception as e:
                    if "429" in str(e) and attempt < 2:
                        wait = 15 * (attempt + 1)
                        print(f"    ⏳ Rate limited, waiting {wait}s...")
                        time.sleep(wait)
                    else:
                        err = f"{sheet_ref}: {e}"
                        print(f"    ✗ {err}")
                        run.errors.append(err)
                        break

    run.items_extracted = len(run.items)
    run.duration_seconds = round(_time.time() - start, 2)

    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = "_gold_extraction.json" if is_gold else "_extraction.json"
    out = output_dir / f"{manifest.project_id}{suffix}"
    out.write_text(run.model_dump_json(indent=2))
    print(f"  [{manifest.project_id}] {run.items_extracted} items, {run.pages_processed} pages, {run.duration_seconds}s → {out.name}")
    return run
