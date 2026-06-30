# Candidate Data Transformer — Design Document

## 1. Pipeline Architecture Diagram

The candidate transformation pipeline executes in 8 sequential stages, ensuring clean separation of concerns and high fault tolerance:

```mermaid
graph LR
    INGEST[1. INGEST] --> PARSE[2. PARSE]
    PARSE --> NORMALIZE[3. NORMALIZE]
    NORMALIZE --> MERGE[4. MERGE]
    MERGE --> CONFIDENCE[5. CONFIDENCE]
    CONFIDENCE --> PROVENANCE[6. PROVENANCE]
    PROVENANCE --> PROJECT[7. PROJECT]
    PROJECT --> VALIDATE_OUT[8. VALIDATE & OUTPUT]
```

- **INGEST**: Loads sources (CSV, ATS, GitHub, Resume) independently. Catches and logs errors; never crashes on a single bad source.
- **PARSE**: Extracts fields from raw inputs into intermediate dictionaries.
- **NORMALIZE**: Standardizes names, emails, phones, dates, countries, and skills.
- **MERGE**: Matches candidate records using email (priority 1) and name (priority 2), resolving conflicts using a trust hierarchy.
- **CONFIDENCE**: Computes field and overall confidence scores based on source trust, confirmations, and conflicts.
- **PROVENANCE**: Tracks the source and extraction method (`direct_extract`, `regex`, `api`, `fuzzy_match`, `heuristic`, `inferred`) for every field.
- **PROJECT**: Separates core logic from presentation; filters and reshapes profiles at runtime based on a JSON config.
- **VALIDATE & OUTPUT**: Validates the output with Pydantic v2 and writes candidate profiles and a run summary.

---

## 2. Schema Decisions

- **Phone Numbers (E.164)**: Standardized to `+<country_code><number>` format (e.g., `+919014746514`) using the Google `phonenumbers` library. Invalid/unparseable numbers default to `None` to prevent polluting the data.
- **Dates (YYYY-MM)**: Normalizing dates to `YYYY-MM` (using `dateparser`) handles varying inputs (e.g., "Jan 2020", "2020-01-15", "06/2021") and enables precise experience duration calculation. If a date is `"Present"` or `"Current"`, it is normalized to `None` to maintain strict compliance.
- **Skill Canonicalization**: Standardizes raw skill inputs (e.g., "JS" -> "JavaScript", "ML" -> "Machine Learning") using `rapidfuzz` (threshold >= 85) against a pre-defined dictionary of technology synonyms. Non-matching skills are preserved in Title Case, preventing loss of niche skills.

---

## 3. Merge Strategy

- **Candidate Matching**:
  - **Priority 1**: Exact matching on normalized emails (any overlapping email).
  - **Priority 2**: Fuzzy matching on normalized names (`rapidfuzz.fuzz.token_sort_ratio > 90`).
  - **Priority 3**: If no match, a new candidate record is created.
- **Stable UUID5 Generation**: Candidates are assigned a stable `candidate_id` derived using `uuid.uuid5(uuid.NAMESPACE_DNS, email)` (or name as a fallback). This guarantees that reprocessing the same candidate's data always results in the same identifier.
- **Conflict Resolution**:
  - **Single-Value Fields**: Resolved using a source trust hierarchy: `CSV (0.85) > ATS (0.80) > GitHub (0.65) > Resume (0.60)`. If trust is equal, the most recent contribution (ingestion timestamp) is selected. Conflicts are logged.
  - **List-Value Fields**: Emails, phones, and links are union-merged and deduplicated.
  - **Experience & Education**: Deduplicated by matching companies/titles and institutions/degrees using fuzzy matching (> 85 score), merging details from the higher-trust source.

---

## 4. Configuration & Projection Layer

The **Projection Layer** (`core/projector.py`) is decoupled from the core merge and normalizer logic. The pipeline first builds a complete, rich canonical profile (`schemas/canonical.py`). 

At runtime, the projector reads a JSON configuration (`schemas/config_schema.py`) and dynamically maps, renames (via the `from` key), and filters the canonical profile. The configuration supports dot-notation path traversal (e.g., `location.city`), array indexing (e.g., `emails[0]`), and array projection (e.g., `skills[].name`). This enables different consumers (e.g., a search index needing a flat structure vs. a UI needing a nested structure) to receive custom shapes without code modifications.

---

## 5. Edge Cases & Descoped Items

- **Fuzzy Name Spellings**: Handled via `rapidfuzz` name matching (score > 90), resolving to the highest-trust spelling (e.g., CSV name over Resume name) while flagging the conflict.
- **Wrong/Missing Country Codes**: Phone parsing defaults to region `"IN"` if no country code is present.
- **Scanned Resumes / Empty PDFs**: If `pdfplumber` extracts no text, the parser logs a warning and returns null fields, allowing the pipeline to continue.
- **GitHub Rate Limits / 404s**: Caught gracefully via `requests` exception handling, returning `None` for the GitHub source while other sources merge successfully.
- **Descoped - LinkedIn Scraping**: Excluded due to LinkedIn's strict anti-scraping policies, lack of a public profile API, and legal/IP block risks.
