# AI Takeoff Builder System

Backend prototype for an AI-powered construction takeoff pipeline.

---

## Setup

```bash
cd /Users/emmanuelofoneta/Projects/work/assesment

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt

cp .env.example .env
# Edit .env — add ANTHROPIC_API_KEY or OPENAI_API_KEY
```

---

## Run

```bash
# Full pipeline (recommended first run)
python run.py all

# Individual steps
python run.py ingest                        # index dataset files
python run.py extract                       # AI extraction (all projects)
python run.py extract --project TAKEOFF-28  # single project
python run.py evaluate                      # score vs gold outputs
python run.py review queue                  # generate human review files
python run.py review apply                  # apply saved corrections
python run.py report                        # write Markdown reports
```

Outputs go to `outputs/`:
- `outputs/manifests/`   — project index JSONs
- `outputs/predictions/` — AI-generated takeoff JSONs
- `outputs/evaluations/` — scores + review queues
- `outputs/reports/`     — Markdown reports + SUMMARY_REPORT.md

---

## No API Key?

The pipeline runs in **mock mode** without a key — all steps work but extraction
items are labelled MOCK with no real quantities. This lets you verify the full
pipeline flow before adding a real key.

---

## Dataset Location

The system auto-detects the dataset in these locations (in order):
1. Sibling folder: `../AI Takeoff Builder Challenge - Assessment 1.0/`
2. `~/Downloads/AI Takeoff Builder Challenge - Assessment 1.0/`
3. Custom path set via `DATASET_ROOT` in `.env`

If your dataset is somewhere else, add this to `.env`:
```
DATASET_ROOT=/your/path/to/AI Takeoff Builder Challenge - Assessment 1.0
```

---

## What is Automated vs Manual

| Step | Type |
|------|------|
| File indexing & classification | Automated (deterministic) |
| PDF/TIF → image conversion | Automated (deterministic) |
| Takeoff item extraction | Automated (AI — Claude/GPT-4o vision) |
| Gold item extraction from markup PDFs | Automated (AI) |
| Description matching & scoring | Automated (deterministic) |
| Human review queue generation | Automated (deterministic) |
| Correcting flagged items | Manual — edit `_review_queue.json` |
| Applying corrections | Automated (deterministic) |

---

## Tools Used

- **Claude claude-opus-4-5** / **GPT-4o** — blueprint vision extraction
- **PyMuPDF** — PDF page rendering
- **Pillow** — TIF/image processing
- **Pydantic v2** — data models
- **python-dotenv** — config

---

## Known Limitations

1. Quantities depend on readable labels in the drawing — unlabelled geometry is flagged as null.
2. Old TIF scans (TAKEOFF-56) have lower quality than clean PDFs.
3. Human review is file-based (JSON); production would use a web UI + database.
4. MAX_PAGES_PER_FILE defaults to 6 to control API cost.

See `CANDIDATE_REVIEW_PACKET.md` for full architecture and 30-day plan.
