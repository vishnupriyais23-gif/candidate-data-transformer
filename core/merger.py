import uuid
from typing import List, Dict, Any, Optional, Tuple
from rapidfuzz import fuzz
from core.normalizer import (
    normalize_name, normalize_email, normalize_phone,
    normalize_date, normalize_country, normalize_skill
)

# Source trust levels
TRUST_LEVELS = {
    "csv": 0.85,
    "ats": 0.80,
    "github": 0.65,
    "resume": 0.60
}

class MergedCandidate:
    def __init__(self):
        self.candidate_id = str(uuid.uuid4())
        # Store raw contributions for each field: {field_name: [ {value, source, trust, timestamp, method} ]}
        self.contributions: Dict[str, List[Dict[str, Any]]] = {}
        # Special handling for list and nested fields
        self.skills_contributions: Dict[str, List[Dict[str, Any]]] = {} # {normalized_skill: [contributions]}
        self.experience_contributions: List[Dict[str, Any]] = []
        self.education_contributions: List[Dict[str, Any]] = []
        self.projects_contributions: List[Dict[str, Any]] = []

    def add_contribution(self, source: str, data: Dict[str, Any], timestamp: float):
        trust = TRUST_LEVELS.get(source, 0.50)
        
        # Determine extraction method based on source and field
        def get_method(field_name: str) -> str:
            if source in ["csv", "ats"]:
                return "direct_extract"
            elif source == "github":
                return "api"
            elif source == "resume":
                if field_name == "location.city" and data.get("_inferred_location_city"):
                    return "inferred"
                elif field_name == "links.github" and data.get("_hyperlink_github"):
                    return "hyperlink_extract"
                elif field_name == "links.linkedin" and data.get("_hyperlink_linkedin"):
                    return "hyperlink_extract"
                elif field_name == "links.leetcode" and data.get("_hyperlink_leetcode"):
                    return "hyperlink_extract"
                elif field_name == "links.hackerrank" and data.get("_hyperlink_hackerrank"):
                    return "hyperlink_extract"
                elif field_name == "links.portfolio" and data.get("_hyperlink_portfolio"):
                    return "hyperlink_extract"
                elif field_name in ["emails", "phones"] or field_name in ["links.linkedin", "links.github", "links.leetcode", "links.hackerrank"]:
                    return "regex"
                else:
                    return "heuristic"
            return "inferred"

        # Helper to add single value contribution
        def add_single(field_name: str, val: Any):
            if val is not None:
                self.contributions.setdefault(field_name, []).append({
                    "value": val,
                    "source": source,
                    "trust": trust,
                    "timestamp": timestamp,
                    "method": get_method(field_name)
                })

        # Add single fields
        add_single("full_name", normalize_name(data.get("full_name")))
        add_single("headline", data.get("headline"))
        add_single("years_experience", data.get("years_experience"))
        
        # Location fields
        loc = data.get("location") or {}
        city = loc.get("city")
        country = normalize_country(loc.get("country"))
        
        if city and not country:
            indian_cities = {"bangalore", "bengaluru", "hyderabad", "chennai", "pune", "mumbai", "delhi", "kolkata", "gwalior", "jhansi", "nagpur", "noida", "gurgaon"}
            if city.lower() in indian_cities:
                country = "IN"
                self.contributions.setdefault("location.country", []).append({
                    "value": "IN",
                    "source": source,
                    "trust": trust,
                    "timestamp": timestamp,
                    "method": "inferred"
                })
                
        add_single("location.city", city)
        add_single("location.region", loc.get("region"))
        if country and not (city and not loc.get("country") and country == "IN"):
            add_single("location.country", country)

        # Links fields
        links = data.get("links") or {}
        add_single("links.linkedin", links.get("linkedin"))
        add_single("links.github", links.get("github"))
        add_single("links.leetcode", links.get("leetcode"))
        add_single("links.hackerrank", links.get("hackerrank"))
        add_single("links.portfolio", links.get("portfolio"))

        # Array fields: emails, phones, other links
        for email in data.get("emails") or []:
            norm_email = normalize_email(email)
            if norm_email:
                self.contributions.setdefault("emails", []).append({
                    "value": norm_email,
                    "source": source,
                    "trust": trust,
                    "timestamp": timestamp,
                    "method": get_method("emails")
                })

        for phone in data.get("phones") or []:
            norm_phone = normalize_phone(phone)
            if norm_phone:
                self.contributions.setdefault("phones", []).append({
                    "value": norm_phone,
                    "source": source,
                    "trust": trust,
                    "timestamp": timestamp,
                    "method": get_method("phones")
                })

        for other_link in links.get("other") or []:
            self.contributions.setdefault("links.other", []).append({
                "value": other_link,
                "source": source,
                "trust": trust,
                "timestamp": timestamp,
                "method": get_method("links.other")
            })

        # Skills
        for skill in data.get("skills") or []:
            skill_name = skill
            skill_conf = None
            if isinstance(skill, dict):
                skill_name = skill.get("name")
                skill_conf = skill.get("confidence")
                
            norm_skill = normalize_skill(skill_name)
            if norm_skill:
                self.skills_contributions.setdefault(norm_skill, []).append({
                    "source": source,
                    "trust": trust,
                    "timestamp": timestamp,
                    "method": get_method("skills"),
                    "confidence": skill_conf
                })

        # Experience
        for exp in data.get("experience") or []:
            self.experience_contributions.append({
                "company": exp.get("company") or "Unknown",
                "title": exp.get("title") or "Unknown",
                "start": normalize_date(exp.get("start")),
                "end": normalize_date(exp.get("end")),
                "summary": exp.get("summary"),
                "source": source,
                "trust": trust,
                "timestamp": timestamp,
                "method": get_method("experience")
            })

        # Education
        for edu in data.get("education") or []:
            self.education_contributions.append({
                "institution": edu.get("institution") or "Unknown",
                "degree": edu.get("degree"),
                "field": edu.get("field"),
                "end_year": edu.get("end_year"),
                "source": source,
                "trust": trust,
                "timestamp": timestamp,
                "method": get_method("education")
            })

        # Projects
        for proj in data.get("projects") or []:
            self.projects_contributions.append({
                "name": proj.get("name") or "Unknown",
                "description": proj.get("description"),
                "tech_stack": proj.get("tech_stack") or [],
                "duration": proj.get("duration"),
                "source": source,
                "trust": trust,
                "timestamp": timestamp,
                "method": get_method("projects")
            })

    def get_emails(self) -> List[str]:
        contribs = self.contributions.get("emails") or []
        return list(set(c["value"] for c in contribs))

    def get_name(self) -> Optional[str]:
        # Temporarily resolve name to use for fuzzy matching
        contribs = self.contributions.get("full_name") or []
        if not contribs:
            return None
        # Sort by trust desc, timestamp desc
        sorted_contribs = sorted(contribs, key=lambda c: (c["trust"], c["timestamp"]), reverse=True)
        return sorted_contribs[0]["value"]


def clean_github_username(url_or_username: str) -> str:
    """Helper to clean/extract GitHub username from URLs or strings."""
    if not url_or_username:
        return ""
    val = url_or_username.strip()
    
    # Split on "github.com/" if present
    if "github.com/" in val:
        parts = val.split("github.com/", 1)
        val = parts[1]
    
    # Strip any leading slashes
    val = val.lstrip("/")
    
    # Strip query params or fragments
    if "?" in val:
        val = val.split("?", 1)[0]
    if "#" in val:
        val = val.split("#", 1)[0]
        
    # Strip trailing slash
    val = val.rstrip("/")
    
    # Take the first path segment in case of any sub-paths
    if "/" in val:
        val = val.split("/", 1)[0]
        
    return val.strip().lower()

def find_matching_candidate(
    parsed_candidate: Dict[str, Any],
    merged_candidates: List[MergedCandidate]
) -> Optional[MergedCandidate]:
    """
    Matches candidate against existing merged candidates.
    Priority 1: Exact email match.
    Priority 1.5: Match by github link already in candidate links.github.
    Priority 2: Fuzzy name match (score > 90).
    """
    parsed_emails = [normalize_email(e) for e in parsed_candidate.get("emails") or [] if normalize_email(e)]
    parsed_name = normalize_name(parsed_candidate.get("full_name"))
    parsed_github_url = parsed_candidate.get("links", {}).get("github")

    # 1. Exact email match
    if parsed_emails:
        for mc in merged_candidates:
            mc_emails = mc.get_emails()
            if any(email in mc_emails for email in parsed_emails):
                # Skip merge if there is a clear full name conflict
                mc_name = mc.get_name()
                if mc_name and parsed_name:
                    if mc_name.lower() != "unknown candidate" and parsed_name.lower() != "unknown candidate":
                        if fuzz.token_sort_ratio(parsed_name, mc_name) < 50:
                            continue
                return mc

    # 1.5. Match by github URL
    if parsed_github_url:
        parsed_gh_username = clean_github_username(parsed_github_url)
        if parsed_gh_username:
            for mc in merged_candidates:
                gh_contribs = mc.contributions.get("links.github") or []
                for c in gh_contribs:
                    if clean_github_username(c["value"]) == parsed_gh_username:
                        return mc

    # 2. Fuzzy name match
    if parsed_name and parsed_name.lower() != "unknown candidate":
        for mc in merged_candidates:
            mc_name = mc.get_name()
            if mc_name and mc_name.lower() != "unknown candidate":
                score = fuzz.token_sort_ratio(parsed_name, mc_name)
                if score > 90:
                    return mc

    return None


def merge_sources(
    parsed_sources: List[Tuple[str, List[Dict[str, Any]], float]],
    errors_dict: Optional[Dict[str, str]] = None
) -> List[MergedCandidate]:
    """
    Merges candidates across multiple sources.
    Each item in parsed_sources is a tuple of (source_name, candidate_list, ingestion_timestamp).
    """
    import sys
    # Sort parsed_sources so that "github" is processed last!
    # All other sources keep their relative order.
    sorted_sources = sorted(parsed_sources, key=lambda x: 1 if x[0] == "github" else 0)
    
    merged_candidates: List[MergedCandidate] = []

    for source_name, candidates, timestamp in sorted_sources:
        for candidate_data in candidates:
            matched_mc = find_matching_candidate(candidate_data, merged_candidates)
            if not matched_mc:
                # If GitHub data cannot be matched to any existing candidate, discard it entirely.
                if source_name == "github":
                    gh_url = candidate_data.get("links", {}).get("github")
                    username = clean_github_username(gh_url) if gh_url else "unknown"
                    err_msg = f"GitHub data for '{username}' could not be matched to any candidate and was discarded."
                    if errors_dict is not None:
                        errors_dict["github"] = err_msg
                    print(f"[INFO] {err_msg}", file=sys.stderr)
                    continue
                else:
                    matched_mc = MergedCandidate()
                    merged_candidates.append(matched_mc)
            
            matched_mc.add_contribution(source_name, candidate_data, timestamp)

    return merged_candidates
