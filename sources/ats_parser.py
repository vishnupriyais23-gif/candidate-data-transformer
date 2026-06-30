import json
from typing import List, Dict, Any, Union

DEFAULT_FIELD_MAP = {
    "applicant_name": "full_name",
    "contact_email": "emails",
    "contact_phone": "phones",
    "city": "location.city",
    "state": "location.region",
    "country": "location.country",
    "linkedin_url": "links.linkedin",
    "github_url": "links.github",
    "portfolio_url": "links.portfolio",
    "role_headline": "headline",
    "years_of_experience": "years_experience",
    "skills_list": "skills",
    "work_history": "experience",
    "education_history": "education"
}

def set_nested_value(d: Dict[str, Any], path: str, value: Any):
    """Sets a value in a nested dictionary using dot notation (e.g., 'location.city')."""
    parts = path.split(".")
    for part in parts[:-1]:
        d = d.setdefault(part, {})
    d[parts[-1]] = value

def parse_ats_json(file_path: str, field_map: Dict[str, str] = None) -> List[Dict[str, Any]]:
    """
    Parses ATS JSON export.
    Applies field mapping layer to rename keys to canonical names.
    Supports dot-notation for nested fields.
    """
    if field_map is None:
        field_map = DEFAULT_FIELD_MAP

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        raise ValueError(f"Failed to read ATS JSON file {file_path}: {str(e)}")

    if isinstance(data, dict):
        records = [data]
    elif isinstance(data, list):
        records = data
    else:
        raise ValueError("ATS JSON must be a dictionary or a list of dictionaries.")

    candidates = []
    for record in records:
        candidate = {
            "full_name": None,
            "emails": [],
            "phones": [],
            "location": {"city": None, "region": None, "country": None},
            "links": {"linkedin": None, "github": None, "portfolio": None, "other": []},
            "headline": None,
            "years_experience": None,
            "skills": [],
            "experience": [],
            "education": []
        }

        for src_key, dest_path in field_map.items():
            if src_key in record:
                val = record[src_key]
                if val is None:
                    continue

                # If the destination is emails or phones, ensure it's a list
                if dest_path in ["emails", "phones"]:
                    if isinstance(val, str):
                        candidate[dest_path] = [val.strip()]
                    elif isinstance(val, list):
                        candidate[dest_path] = [v.strip() for v in val if isinstance(v, str)]
                elif dest_path == "skills":
                    if isinstance(val, str):
                        candidate["skills"] = [s.strip() for s in val.split(",") if s.strip()]
                    elif isinstance(val, list):
                        candidate["skills"] = [s.strip() for s in val if isinstance(s, str)]
                elif dest_path == "experience":
                    # Experience needs to be mapped to company, title, start, end, summary
                    exp_list = []
                    if isinstance(val, list):
                        for exp in val:
                            if isinstance(exp, dict):
                                exp_list.append({
                                    "company": exp.get("company") or exp.get("employer") or "Unknown",
                                    "title": exp.get("title") or exp.get("role") or "Unknown",
                                    "start": exp.get("start") or exp.get("start_date"),
                                    "end": exp.get("end") or exp.get("end_date"),
                                    "summary": exp.get("summary") or exp.get("description")
                                })
                    candidate["experience"] = exp_list
                elif dest_path == "education":
                    edu_list = []
                    if isinstance(val, list):
                        for edu in val:
                            if isinstance(edu, dict):
                                edu_list.append({
                                    "institution": edu.get("institution") or edu.get("school") or "Unknown",
                                    "degree": edu.get("degree"),
                                    "field": edu.get("field") or edu.get("major"),
                                    "end_year": edu.get("end_year") or edu.get("year")
                                })
                    candidate["education"] = edu_list
                elif "." in dest_path:
                    set_nested_value(candidate, dest_path, val)
                else:
                    candidate[dest_path] = val

        candidates.append(candidate)

    return candidates
