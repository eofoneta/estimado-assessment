# AI Takeoff Builder System

A backend pipeline that reads construction blueprint PDFs, extracts takeoff line items using AI, and evaluates results against human reference outputs.

---

## Prerequisites

- Python 3.9+
- An [OpenRouter](https://openrouter.ai) API key (free signup)
- The dataset folder: `AI Takeoff Builder Challenge - Assessment 1.0`

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Add your OPENROUTER_API_KEY to .env
```

## Run

```bash
python run.py all
```

That's it. Outputs go to `outputs/`.

## Step by step

```bash
python run.py ingest              # index project files
python run.py extract             # AI extraction
python run.py evaluate            # score vs gold outputs
python run.py report              # generate Markdown reports
python run.py export              # generate official template JSONs
```

## Single project

```bash
python run.py all --project TAKEOFF-28
```

## Dataset

Place the dataset folder next to this project folder — it will be auto-detected. Or set `DATASET_ROOT` in `.env`.

## Models used

- **GPT-4o** via OpenRouter — blueprint vision extraction
- **PyMuPDF** — PDF rendering
- **Pillow** — image processing

## Outputs

| Folder | Contents |
|--------|---------|
| `outputs/manifests/` | Project file index |
| `outputs/predictions/` | Raw AI extraction JSON |
| `outputs/evaluations/` | Scores + review queues |
| `outputs/reports/` | Markdown reports |
| `outputs/exports/` | Official template format JSONs |

See `CANDIDATE_REVIEW_PACKET.md` for full details.
