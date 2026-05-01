# Candidate Review Packet

**Candidate:** Emmanuel Ofoneta | **Date:** 2026-04-30

---

## 1. Summary

I built a Python backend pipeline that automates construction takeoff extraction. It:

1. Scans the dataset folder and indexes every file, separating input blueprints from gold reference outputs
2. Sends blueprint pages to GPT-4o which reads each page and extracts materials, quantities, and units
3. Compares AI output against human reference data and scores it (Precision / Recall / F1)
4. Flags uncertain items in a human review queue for correction
5. Outputs structured JSON per project in the official template format

---

## 2. How To Run It

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # add OPENROUTER_API_KEY
python run.py all           # runs full pipeline
```

Single project: `python run.py all --project TAKEOFF-28`

---

## 3. Projects Processed


| Set       | Takeoff ID | Project Name                  | Files Used | Output? | Scored?  |
| --------- | ---------- | ----------------------------- | ---------- | ------- | -------- |
| Sample    | TAKEOFF-28 | Maryland Vision Institute     | 1 gold PDF | yes     | partial* |
| Sample    | TAKEOFF-56 | Jack & Jones Staten Island    | 5 of 42    | yes     | no gold  |
| Challenge | TAKEOFF-31 | Walmart 1783                  | 5 of 98    | yes     | no gold  |
| Challenge | TAKEOFF-32 | APU Military & Veterans Azusa | 1          | yes     | no gold  |
| Challenge | TAKEOFF-36 | Gucci Perm Cherry Creek       | 5 of 50    | yes     | no gold  |
| Challenge | TAKEOFF-37 | Take 5 Oil Change Sheffield   | 1          | yes     | no gold  |
| Challenge | TAKEOFF-39 | Nuuvi Modern Med Spa Wayne PA | 5 of 46    | yes     | no gold  |
| Challenge | TAKEOFF-45 | Ground Up Maverik Fuel Center | 3 of 3     | yes     | no gold  |
| Challenge | TAKEOFF-47 | Woof Gang                     | 5 of 26    | yes     | no gold  |


*TAKEOFF-28 only had the markup PDF in the shared folder — no separate input blueprints. Full P/R/F1 scoring requires both.

*TAKEOFF-50 and 18 challenge projects were not present in the shared Drive link.*

---

## 4. System Pipeline


| Step                                          | Module                                     | Type          |
| --------------------------------------------- | ------------------------------------------ | ------------- |
| Index files, separate input vs gold           | `pipeline/ingest.py`                       | Deterministic |
| Render PDF/TIF pages to images                | `pipeline/extract.py`                      | Deterministic |
| Send images to GPT-4o, parse JSON response    | `pipeline/extract.py`                      | AI            |
| Match predicted vs gold items, compute P/R/F1 | `pipeline/evaluate.py`                     | Deterministic |
| Flag items for human review                   | `pipeline/human_review.py`                 | Deterministic |
| Generate reports + official template JSON     | `pipeline/report.py`, `pipeline/export.py` | Deterministic |


---

## 5. Output Summary

Sample from TAKEOFF-28 (Maryland Vision Institute):


| Description          | Qty    | Unit | Confidence |
| -------------------- | ------ | ---- | ---------- |
| PNT-01 9'-0" High    | 62.8   | FT   | high       |
| PNT-01 9'-6" High    | 1502.2 | FT   | high       |
| PNT-02 9'-6" High    | 234.0  | FT   | high       |
| Existing fan         | 3.0    | EA   | medium     |
| Existing fire damper | 1.0    | EA   | medium     |


Full structured outputs in `outputs/exports/` (official template format).

---

## 6. Evaluation / Scoring Results

Full P/R/F1 scoring was not possible for TAKEOFF-28 because the shared Drive only contained the markup PDF (gold), not the raw input blueprints. The system correctly separated them and extracted 11 gold items.

For all challenge projects: no gold outputs available — scoring not applicable.

**Scoring method:** Jaccard token overlap on normalised descriptions (threshold 0.40). Quantity match = ±10% tolerance. Metrics: Precision, Recall, F1, Quantity Accuracy.

---

## 7. Automation vs Manual


| Task                     | Status                       |
| ------------------------ | ---------------------------- |
| File indexing            | Automated                    |
| PDF/TIF → image          | Automated                    |
| AI extraction            | Automated (GPT-4o)           |
| Scoring                  | Automated (deterministic)    |
| Review queue generation  | Automated                    |
| Correcting flagged items | Manual (reviewer edits JSON) |
| Loom recording           | Manual                       |


---

## 8. AI / Tools Used


| Tool                  | Purpose                     |
| --------------------- | --------------------------- |
| GPT-4o via OpenRouter | Blueprint vision extraction |
| PyMuPDF               | PDF page rendering          |
| Pillow                | TIF/image processing        |
| Pydantic v2           | Data models                 |
| Cursor IDE            | Development                 |


---

## 9. Limitations and Risks

- Only 5 files and 2 pages per file processed per project (API rate limits + personal budget)
- TAKEOFF-28 missing input blueprints in shared folder — no full evaluation possible
- TAKEOFF-32 and TAKEOFF-37 returned 0 items — first pages were admin/cover sheets
- Quantities depend on visible text annotations — unlabelled geometry returns null
- Human review currently file-based (JSON), not a web UI

---

## 10. 30-Day Plan If Hired

**Week 1:** Supabase schema + replace file JSON with database. Full coverage on all projects.

**Week 2:** Next.js review dashboard (blueprint viewer + item table + accept/reject/edit). Collect corrections, inject as few-shot examples, re-run and measure F1 delta.

**Week 3:** Geometry measurement engine (pdfplumber), trade-specific prompts, retry/cost tracking, regression tests.

**Week 4:** Deploy on Vercel, multi-user Supabase Auth, comparison dashboard, internal docs.

**Target:** F1 ≥ 0.70 on TAKEOFF-28, new project processed in under 30 minutes.

---

## 11. Reviewer Notes

- Run `python run.py all` to regenerate all outputs fresh — nothing is hardcoded
- Official template JSONs in `outputs/exports/`
- Dataset auto-detected if placed next to the project folder
- I personally funded API costs during development and testing

