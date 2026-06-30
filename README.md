# Messy Candidate Data Transformer Pipeline

A robust, production-ready Python pipeline designed to ingest candidate data from 4 messy real-world sources (CSV, ATS JSON, Resume, and GitHub), merge them into a single clean canonical JSON profile per candidate, track provenance and confidence, and output a runtime-configurable shape.

Includes a premium Streamlit UI (`app.py`) for interactive file uploads and real-time visualization of the transformation process.

---

## Setup

1. **Clone the repository** (or navigate to the workspace directory).
2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

---

## How to Run

### 1. Web Application (Streamlit UI)
To launch the interactive web interface:
```bash
streamlit run app.py
```

### 2. CLI Run (Default Configuration)
Runs the pipeline using all available sample inputs and projects the full canonical schema with metadata:
```bash
python transform.py \
  --csv data/candidates.csv \
  --ats data/ats_export.json \
  --github https://github.com/vishhneww \
  --resume data/resume.docx \
  --config config/default.json \
  --output output/
```

### 3. CLI Run (Minimal Configuration)
Runs the pipeline and outputs only the candidate's name, primary email, and flat skills list, with no confidence or provenance metadata:
```bash
python transform.py \
  --csv data/candidates.csv \
  --config config/minimal.json \
  --output output/
```

---

## Run Tests
Run the full test suite using `pytest`:
```bash
pytest tests/ -v
```

---

## Design Decisions

- **Stable UUID5 Generation**: Candidates are assigned a stable `candidate_id` derived using `uuid.uuid5(uuid.NAMESPACE_DNS, email)`. This guarantees that reprocessing the same candidate's data always results in the same identifier, preventing duplicates in downstream systems.
- **Fuzzy Skill and Name Matching**: Name matching uses a fuzzy threshold (`rapidfuzz.fuzz.token_sort_ratio > 90`) to link profiles across messy sources. Skills are matched against a canonical list (e.g. "JS" -> "JavaScript", "ML" -> "Machine Learning") using a threshold of 85, allowing robust de-duplication while preserving niche skills.
- **Confidence Scoring & Provenance**: 
  - Base confidence is determined by the source trust level.
  - A `+0.10` bonus is applied when a field value is confirmed by 2+ sources.
  - A `-0.15` penalty is applied for cross-source value conflicts.
  - A `-0.10` penalty is applied for values extracted via regex or heuristics (e.g. from resume).
  - Provenance tracks every single field in the canonical schema. If a field is null, it records a `not_found` method.

---

## Assumptions & Descoped Items
- **LinkedIn Scraping**: LinkedIn profile scraping is descoped because LinkedIn lacks a public profile API, enforces strict rate limits/IP blocks, and actively prosecutes automated scraping. LinkedIn URLs are still captured and merged from candidate records when provided in the ATS JSON or other sources.
- **Scanned Resumes**: If a PDF contains no text layer (e.g., scanned image), the parser gracefully logs the warning and returns null fields. The candidate's profile is still merged using other available sources.
- **Date Standardization**: Experience and education dates are normalized to `YYYY-MM` or `null` (never "Present" or "Current"), ensuring clean date arithmetic and consistency.
