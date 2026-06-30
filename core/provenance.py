from typing import List, Dict, Any, Optional

def generate_provenance(
    resolved_fields: Dict[str, Any],
    contributions: Dict[str, List[Dict[str, Any]]],
    skills_contributions: Dict[str, List[Dict[str, Any]]],
    experience_entries: List[Dict[str, Any]],
    education_entries: List[Dict[str, Any]],
    project_entries: Optional[List[Dict[str, Any]]] = None
) -> List[Dict[str, str]]:
    """
    Generates the provenance list for a candidate profile.
    Each entry tracks: { field, source, method }
    Guarantees that every single field in the canonical schema has at least one provenance entry.
    If a field is null or empty, it uses method "not_found" and source "none".
    """
    provenance = []
    seen_entries = set()

    def add_entry(field: str, source: str, method: str):
        key = (field, source, method)
        if key not in seen_entries:
            seen_entries.add(key)
            provenance.append({
                "field": field,
                "source": source,
                "method": method
            })

    # All canonical fields to track
    canonical_fields = [
        "full_name",
        "headline",
        "years_experience",
        "location.city",
        "location.region",
        "location.country",
        "links.linkedin",
        "links.github",
        "links.portfolio",
        "links.other",
        "emails",
        "phones",
        "skills",
        "experience",
        "education",
        "projects"
    ]

    for field in canonical_fields:
        # 1. Handle single-value fields
        if field in ["full_name", "headline", "years_experience"] or field.startswith("location.") or field.startswith("links."):
            if field.startswith("location."):
                sub_key = field.split(".")[1]
                val = resolved_fields.get("location", {}).get(sub_key)
            elif field.startswith("links."):
                sub_key = field.split(".")[1]
                val = resolved_fields.get("links", {}).get(sub_key)
            else:
                val = resolved_fields.get(field)

            contribs = contributions.get(field) or []
            if val is not None and contribs:
                # Find matching contribution
                matching_contrib = None
                for c in contribs:
                    if c["value"] == val:
                        matching_contrib = c
                        break
                if not matching_contrib:
                    matching_contrib = contribs[0]
                
                # Ensure method is one of the allowed types
                method = matching_contrib.get("method", "inferred")
                if method not in ["direct_extract", "regex", "api", "fuzzy_match", "heuristic", "inferred", "not_found", "hyperlink_extract"]:
                    method = "inferred"
                add_entry(field, matching_contrib["source"], method)
            else:
                add_entry(field, "none", "not_found")

        # 2. Handle emails and phones
        elif field in ["emails", "phones"]:
            items = resolved_fields.get(field) or []
            if not items:
                add_entry(field, "none", "not_found")
            else:
                contribs = contributions.get(field) or []
                for item in items:
                    matched = False
                    for c in contribs:
                        if c["value"] == item:
                            add_entry(field, c["source"], c.get("method", "direct_extract"))
                            matched = True
                            break
                    if not matched and contribs:
                        add_entry(field, contribs[0]["source"], contribs[0].get("method", "direct_extract"))

        # 3. Handle skills
        elif field == "skills":
            skills = resolved_fields.get("skills") or []
            if not skills:
                add_entry("skills", "none", "not_found")
            else:
                for skill in skills:
                    skill_name = skill["name"]
                    contribs = skills_contributions.get(skill_name) or []
                    for c in contribs:
                        add_entry("skills", c["source"], c.get("method", "heuristic"))

        # 4. Handle experience
        elif field == "experience":
            if not experience_entries:
                add_entry("experience", "none", "not_found")
            else:
                for exp in experience_entries:
                    add_entry("experience", exp.get("source", "unknown"), exp.get("method", "heuristic"))

        # 5. Handle education
        elif field == "education":
            if not education_entries:
                add_entry("education", "none", "not_found")
            else:
                for edu in education_entries:
                    add_entry("education", edu.get("source", "unknown"), edu.get("method", "heuristic"))

        # 6. Handle projects
        elif field == "projects":
            proj_list = project_entries or resolved_fields.get("projects") or []
            if not proj_list:
                add_entry("projects", "none", "not_found")
            else:
                for proj in proj_list:
                    add_entry("projects", proj.get("source", "resume"), proj.get("method", "heuristic"))

    return provenance
