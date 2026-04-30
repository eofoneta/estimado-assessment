# Candidate Review Packet
**Assessment:** AI Takeoff Builder Challenge — Assessment 1.0  
**Candidate:** Emmanuel Ofoneta  
**Date:** 2026-04-30  

---

## 1. Plain-English Summary

I built a backend Python pipeline that automates construction takeoff extraction. When given a folder of construction blueprint PDFs, the system:

1. Scans and indexes every file, separating AI-visible blueprints from human reference outputs
2. Sends blueprint pages to GPT-4o (via OpenRouter) which reads each page and extracts a structured list of materials, quantities, and units
3. Compares the AI's extracted items against the human expert's reference output (where available) and produces a precision/recall score
4. Flags uncertain or unmatched items in a human review queue where a reviewer can accept, reject, or correct each item
5. Generates a structured JSON output per project (matching the provided output template) and a Markdown report

The goal is not to perfectly solve blueprint reading — it is to build the repeatable system that a real takeoff AI would run on: ingest → extract → evaluate → correct → improve.

---

## 2. How To Run It

**Requirements:** Python 3.9+, an OpenRouter API key (free tier available at openrouter.ai)

```bash
# 1. Clone or unzip the project
cd assesment

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env — set OPENROUTER_API_KEY and DATASET_ROOT

# 5. Run full pipeline
python run.py all

# Or step by step:
python run.py ingest              # index all project files
python run.py extract             # AI extraction
python run.py evaluate            # score vs gold outputs
python run.py review queue        # generate human review files
python run.py report              # generate Markdown reports
python run.py export              # export official template JSON outputs

# Single project:
python run.py all --project TAKEOFF-28
```

**Outputs:**
- `outputs/manifests/`   — project index JSONs
- `outputs/predictions/` — raw AI extraction JSONs
- `outputs/evaluations/` — scores + review queues
- `outputs/reports/`     — Markdown reports + SUMMARY_REPORT.md
- `outputs/exports/`     — official template format JSONs

**Dataset location:** The system auto-detects the dataset at `../AI Takeoff Builder Challenge - Assessment 1.0/` or `~/Downloads/`. Override with `DATASET_ROOT` in `.env`.

---

## 3. Projects Processed

The provided Drive folder contained 2 sample projects and 7 challenge projects (TAKEOFF-50 and 18 challenge projects from the manifest were not present in the shared folder).

| Set | Takeoff ID | Project Name | Files Used | Output Created? | Scored? |
| --- | --- | --- | --- | --- | --- |
| Sample | TAKEOFF-28 | Maryland Vision Institute | 1 (gold markup PDF) | yes | N/A — no separate input blueprint |
| Sample | TAKEOFF-56 | Jack & Jones Staten Island NY | 5 of 42 TIF/PDF | yes | no hidden gold available in download |
| Challenge | TAKEOFF-31 | Walmart 1783 | 5 of 98 PDFs | yes | no hidden gold available |
| Challenge | TAKEOFF-32 | APU Military and Veterans Azusa | 1 PDF | yes | no hidden gold available |
| Challenge | TAKEOFF-36 | Gucci Perm Cherry Creek | 5 of 50 PDFs | yes | no hidden gold available |
| Challenge | TAKEOFF-37 | Take 5 Oil Change Sheffield OH | 1 PDF | yes | no hidden gold available |
| Challenge | TAKEOFF-39 | Nuuvi Modern Med Spa Wayne PA | 5 of 46 PDFs | yes | no hidden gold available |
| Challenge | TAKEOFF-45 | Ground Up Maverik Fuel Center | 3 of 3 PDFs | yes | no hidden gold available |
| Challenge | TAKEOFF-47 | Woof Gang | 5 of 26 PDFs | yes | no hidden gold available |

**Note on TAKEOFF-28:** This project only contained a "Markups" PDF in the Expected Manual Output folder — no separate input blueprint files were in the shared Drive. The system correctly classified the markup PDF as a gold reference file and extracted items from it to understand the expected output format. A full evaluation (P/R/F1) requires both the raw input blueprints and the markup output.

---

## 4. System Pipeline

**1. File/folder ingestion (`pipeline/ingest.py`)**  
Walks the dataset folder structure. Classifies each file by role (input vs gold) based on folder name (`Expected Manual Output` → gold, `Project Files` → input) and by kind (blueprint, markup, photo, specification) based on filename patterns and extension. Writes a `ProjectManifest` JSON per project. Fully deterministic — no AI.

**2. AI-visible input separation**  
Files in gold-labelled folders are tagged `role: gold` and never passed to the extraction AI. Only `role: input` files are sent to the model. This prevents data leakage where the AI sees the answer before predicting.

**3. Takeoff extraction (`pipeline/extract.py`)**  
Each input file is rendered page-by-page to PNG images (PyMuPDF for PDFs, Pillow for TIFs). Each image is sent to GPT-4o via OpenRouter with a structured prompt requesting a JSON array of line items (description, quantity, unit, category, confidence, assumptions, warnings, source reference). Responses are parsed and stored as `TakeoffItem` objects.

**4. Structured output creation (`pipeline/export.py`)**  
Converts internal extraction data to the official output template format with `trade_scope`, `input_files_used`, `ai_run`, and `line_items` fields. Written to `outputs/exports/{project_id}_output.json`.

**5. Scoring/evaluation (`pipeline/evaluate.py`)**  
For projects with gold data: normalises descriptions (lowercase, trade synonym expansion), computes Jaccard token overlap between predicted and gold items, greedily matches best pairs above a 0.40 similarity threshold. Calculates Precision, Recall, F1, and quantity accuracy (±10% tolerance). Fully deterministic — no AI in scoring loop.

**6. Human review/correction loop (`pipeline/human_review.py`)**  
Generates `_review_queue.json` files flagging low-confidence items, unmatched predictions, and quantity discrepancies. Reviewer edits `_action` field to `accept`, `reject`, or `edit` per item. Running `python run.py review apply` merges corrections into a final item list. Each correction is stored as a `HumanCorrection` record — the foundation for future prompt improvement and fine-tuning.

---

## 5. Output Summary

**TAKEOFF-28 — Maryland Vision Institute (gold extraction)**

| Description | Qty | Unit | Sheet | Confidence |
|-------------|-----|------|-------|-----------|
| PNT-01 9'-0" High | 62.8 | FT | Markups p.1 | high |
| PNT-01 10'-0" High | 37.3 | FT | Markups p.1 | high |
| PNT-01 10'-6" High | 247.3 | FT | Markups p.1 | high |
| PNT-01 9'-6" High | 1502.2 | FT | Markups p.1 | high |
| PNT-02 9'-6" High | 234.0 | FT | Markups p.1 | high |
| PNT-04 9'-0" High | 176.5 | FT | Markups p.1 | high |
| Existing fan | 3.0 | EA | Markups p.2 | medium |
| Existing fire damper | 1.0 | EA | Markups p.2 | medium |

These are painting items (PNT-01/02/04 = paint type codes) with linear footage measurements, plus mechanical items — consistent with the project's trade scope (Electrical, Painting, HVAC per the manifest).

**Challenge projects:** See `outputs/exports/` for full structured JSON per project.

---

## 6. Evaluation / Scoring Results

**TAKEOFF-28:** Full P/R/F1 scoring was not possible because the shared Drive folder contained only the markup PDF (gold output) with no separate input blueprint files. The system correctly ingested the markup as gold and extracted 11 items from it. To produce a real score, the raw input blueprints would need to be provided alongside the markup.

**TAKEOFF-56 and all challenge projects:** No gold outputs available — scoring not applicable. The system outputs predicted items and flags them for human review.

**Scoring method (deterministic):**
- Match threshold: Jaccard similarity ≥ 0.40 on normalised description tokens
- Quantity tolerance: ±10% considered a match
- Metrics: Precision = matched/predicted, Recall = matched/gold, F1 = harmonic mean

---

## 7. Automation vs Manual Work

| Step | Status |
|------|--------|
| File indexing and classification | Fully automated |
| PDF/TIF → image conversion | Fully automated |
| Takeoff item extraction | Fully automated (GPT-4o via OpenRouter) |
| Gold item extraction from markup PDFs | Fully automated (same AI pipeline) |
| Description matching and scoring | Fully automated (deterministic) |
| Review queue generation | Fully automated |
| Reviewing and correcting flagged items | Manual — reviewer edits JSON file |
| Applying corrections | Fully automated |
| Loom recording | Manual |

Nothing was hardcoded or mocked in the final submission. All outputs are generated fresh by running `python run.py all`.

---

## 8. AI / Tools Used

| Tool | Purpose |
|------|---------|
| GPT-4o (via OpenRouter) | Blueprint vision extraction — reads page images, outputs structured JSON line items |
| PyMuPDF (fitz) | PDF page rendering to PNG — deterministic |
| Pillow | TIF/image processing and resizing — deterministic |
| Pydantic v2 | Data models and JSON serialization |
| python-dotenv | Environment config |
| Cursor IDE | Code generation and development |

**Provider:** OpenRouter (`openrouter.ai`) — used as a unified API gateway supporting multiple models. Primary model: `openai/gpt-4o`.

---

## 9. Limitations and Risks

1. **Partial file coverage:** Due to API rate limits and cost, only the first 5 files and 2 pages per file were processed for each project. Large projects like TAKEOFF-31 (98 files) had significant coverage gaps.

2. **TAKEOFF-28 has no input blueprints in the shared folder:** Only the markup PDF was present, preventing a full input→output→evaluation cycle for this sample project.

3. **TAKEOFF-32 and TAKEOFF-37 returned 0 items:** The first pages of these PDFs contained administrative/cover content with no measurable construction items.

4. **Quantity geometry not validated:** The AI reads quantities from text annotations and schedules only. It cannot independently measure room areas or wall lengths from unlabelled drawings.

5. **OCR accuracy on old TIF scans:** TAKEOFF-56's blueprint TIFs are old pen-and-ink drawings — GPT-4o's text recognition is less reliable than on modern PDF drawings.

6. **Human review is file-based:** The current review loop uses edited JSON files. A production system would use a database + web UI.

7. **TAKEOFF-50 missing:** The third sample project from the manifest was not present in the shared Drive folder.

---

## 10. 30-Day Plan If Hired

**Week 1 — Foundation**
- Set up Supabase schema: projects, files, runs, takeoff_items, corrections, eval_scores tables
- Replace file-based JSON with Supabase throughout the pipeline
- Push to GitHub with CI (lint + test on every commit)
- Process all available projects with full page coverage, document baseline quality per trade

**Week 2 — Evaluation Loop**
- Build Next.js review dashboard: project list → item table → blueprint viewer → accept/reject/edit
- Wire dashboard to Supabase real-time
- Collect human corrections on TAKEOFF-28 and TAKEOFF-56
- Inject corrections as few-shot examples into extraction prompt, measure delta in F1

**Week 3 — Scale & Robustness**
- Add coordinate-based geometry measurement (pdfplumber) to cross-validate AI quantities
- Trade-category routing: separate optimised prompts for flooring, MEP, drywall, structural
- Rate limiting, retry logic, cost tracking per run
- Regression test suite: re-running sample projects must not degrade F1

**Week 4 — Production Readiness**
- Deploy pipeline as Vercel background functions
- Supabase Auth for multi-reviewer access
- Run comparison dashboard (run A vs run B vs gold)
- Internal documentation for non-technical team members
- Plan fine-tuning data collection strategy for month 2

**Target metric by day 30:** F1 ≥ 0.70 on TAKEOFF-28 (once input blueprints are available), full pipeline on a new project in under 30 minutes.

---

## 11. Reviewer Notes

- All outputs in `outputs/exports/` follow the official `03_Output_Template.json` format exactly.
- The system runs end-to-end with a single command: `python run.py all`
- No outputs are committed to the repo — reviewers generate them fresh by running the pipeline.
- Dataset auto-detection means no path configuration is needed if the dataset folder is placed next to the project folder.
- TAKEOFF-50 and 18 challenge projects were absent from the provided Drive link — all available projects were processed.
