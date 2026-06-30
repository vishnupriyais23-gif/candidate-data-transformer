import os
import sys
import json
import time
import argparse
import uuid
import glob
from typing import List, Dict, Any, Tuple, Optional
from pydantic import ValidationError

# Import schemas
from schemas.canonical import CandidateProfile, Skill, Experience, Education, ProvenanceEntry
from schemas.config_schema import ProjectionConfig

# Import sources/parsers
from sources.csv_parser import parse_csv
from sources.ats_parser import parse_ats_json
from sources.github_fetcher import fetch_github_profile
from sources.pdf_parser import parse_resume, parse_resumes
# Import core modules
from core.normalizer import normalize_phone
from core.merger import merge_sources, MergedCandidate
from core.confidence import (
    calculate_field_confidence, calculate_skill_confidence,
    calculate_overall_confidence
)
from core.provenance import generate_provenance
from core.projector import project_candidate

from rapidfuzz import fuzz

def resolve_file_paths(paths_input: Any) -> List[str]:
    """Resolves single path, list of paths, directory, or glob pattern into a list of file paths."""
    if not paths_input:
        return []
    
    # If it is a list of paths
    if isinstance(paths_input, list):
        resolved = []
        for p in paths_input:
            resolved.extend(resolve_file_paths(p))
        return resolved
        
    # If it is a string
    if isinstance(paths_input, str):
        # Glob pattern matching
        if "*" in paths_input or "?" in paths_input:
            return [f for f in glob.glob(paths_input) if os.path.isfile(f)]
        # Directory path
        if os.path.isdir(paths_input):
            files = []
            for root, _, filenames in os.walk(paths_input):
                for filename in filenames:
                    ext = os.path.splitext(filename)[1].lower()
                    if ext in [".pdf", ".docx", ".doc"]:
                        files.append(os.path.join(root, filename))
            return files
        # Single file path
        if os.path.isfile(paths_input):
            return [paths_input]
            
    return []

def get_date_precision(date_str: Optional[str]) -> int:
    if not date_str or date_str.lower() in ["current role", "unknown", "none"]:
        return 0
    if date_str.lower() in ["present", "current"]:
        return 1
    import re
    if re.search(r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|January|February|March|April|May|June|July|August|September|October|November|December)\b', date_str, re.IGNORECASE):
        return 2
    if re.search(r'^\d{4}-\d{2}$', date_str):
        return 2
    if re.search(r'^\d{4}$', date_str):
        return 1
    return 0

def date_ranges_overlap(start1_str: Optional[str], end1_str: Optional[str], start2_str: Optional[str], end2_str: Optional[str]) -> bool:
    from sources.pdf_parser import parse_year_month
    s1 = parse_year_month(start1_str)
    s2 = parse_year_month(start2_str)
    
    if s1 and s2:
        diff_months = abs((s1[0] - s2[0]) * 12 + (s1[1] - s2[1]))
        if diff_months <= 6:
            return True
            
    e1 = parse_year_month(end1_str) if end1_str != "Present" else (9999, 12)
    e2 = parse_year_month(end2_str) if end2_str != "Present" else (9999, 12)
    
    if s1 and s2:
        m_s1 = s1[0] * 12 + s1[1]
        m_s2 = s2[0] * 12 + s2[1]
        m_e1 = (e1[0] * 12 + e1[1]) if e1 else 999999
        m_e2 = (e2[0] * 12 + e2[1]) if e2 else 999999
        
        if m_s1 <= m_e2 and m_s2 <= m_e1:
            return True
            
    if not s1 or not s2:
        return True
        
    return False

def resolve_candidate_profile(mc: MergedCandidate) -> Dict[str, Any]:
    """
    Resolves a MergedCandidate into a flat dictionary matching the canonical schema.
    Applies field conflict resolution and deduplication.
    """
    resolved = {
        "candidate_id": mc.candidate_id,
        "full_name": None,
        "emails": [],
        "phones": [],
        "location": {"city": None, "region": None, "country": None},
        "links": {"linkedin": None, "github": None, "leetcode": None, "hackerrank": None, "portfolio": None, "other": []},
        "headline": None,
        "years_experience": None,
        "skills": [],
        "experience": [],
        "education": [],
        "projects": [],
        "provenance": [],
        "overall_confidence": 0.0
    }

    # Helper to resolve single value field using trust and timestamp
    def resolve_single_field(field_name: str) -> Any:
        contribs = mc.contributions.get(field_name) or []
        if not contribs:
            return None
        sorted_contribs = sorted(contribs, key=lambda c: (c["trust"], c["timestamp"]), reverse=True)
        return sorted_contribs[0]["value"]

    # Resolve single fields
    resolved["full_name"] = resolve_single_field("full_name") or "Unknown Candidate"
    
    # Custom headline resolution: Resume Summary/Objective > GitHub Bio
    headline_contribs = mc.contributions.get("headline") or []
    resume_hl = None
    github_hl = None
    for c in headline_contribs:
        if c["source"] == "resume" and c["value"]:
            resume_hl = c["value"]
        elif c["source"] == "github" and c["value"]:
            github_hl = c["value"]
    resolved["headline"] = resume_hl if resume_hl else github_hl
    
    resolved["years_experience"] = resolve_single_field("years_experience")
    
    # Resolve location
    resolved["location"]["city"] = resolve_single_field("location.city")
    resolved["location"]["region"] = resolve_single_field("location.region")
    resolved["location"]["country"] = resolve_single_field("location.country")
    
    # Auto-infer region/country for common Indian cities if missing or generic
    if resolved["location"]["city"]:
        city_clean = resolved["location"]["city"].strip().lower()
        INDIAN_CITIES = {
            "bangalore": ("Karnataka", "IN"),
            "bengaluru": ("Karnataka", "IN"),
            "mumbai": ("Maharashtra", "IN"),
            "pune": ("Maharashtra", "IN"),
            "delhi": ("Delhi", "IN"),
            "new delhi": ("Delhi", "IN"),
            "chennai": ("Tamil Nadu", "IN"),
            "hyderabad": ("Telangana", "IN"),
            "kolkata": ("West Bengal", "IN"),
            "gurgaon": ("Haryana", "IN"),
            "gurugram": ("Haryana", "IN"),
            "noida": ("Uttar Pradesh", "IN"),
            "ahmedabad": ("Gujarat", "IN"),
            "jaipur": ("Rajasthan", "IN")
        }
        if city_clean in INDIAN_CITIES:
            if not resolved["location"]["region"]:
                resolved["location"]["region"] = INDIAN_CITIES[city_clean][0]
            if not resolved["location"]["country"] or resolved["location"]["country"].lower() in ["india", "ind"]:
                resolved["location"]["country"] = INDIAN_CITIES[city_clean][1]

    # Resolve links
    resolved["links"]["linkedin"] = resolve_single_field("links.linkedin")
    resolved["links"]["github"] = resolve_single_field("links.github")
    resolved["links"]["leetcode"] = resolve_single_field("links.leetcode")
    resolved["links"]["hackerrank"] = resolve_single_field("links.hackerrank")
    resolved["links"]["portfolio"] = resolve_single_field("links.portfolio")

    # Resolve list fields: emails, phones, other links
    email_contribs = mc.contributions.get("emails") or []
    resolved["emails"] = sorted(list(set(c["value"] for c in email_contribs)))

    # Set stable candidate_id (UUID5) derived from primary email, fallback to full name
    primary_email = resolved["emails"][0] if resolved["emails"] else None
    if primary_email:
        resolved["candidate_id"] = str(uuid.uuid5(uuid.NAMESPACE_DNS, primary_email))
    else:
        resolved["candidate_id"] = str(uuid.uuid5(uuid.NAMESPACE_DNS, resolved["full_name"]))

    phone_contribs = mc.contributions.get("phones") or []
    resolved["phones"] = sorted(list(set(c["value"] for c in phone_contribs)))

    other_link_contribs = mc.contributions.get("links.other") or []
    resolved["links"]["other"] = sorted(list(set(c["value"] for c in other_link_contribs)))

    # Resolve skills
    resolved_skills = []
    for skill_name, contribs in mc.skills_contributions.items():
        conf = calculate_skill_confidence(contribs)
        sources = sorted(list(set(c["source"] for c in contribs)))
        resolved_skills.append({
            "name": skill_name,
            "confidence": conf,
            "sources": sources
        })
    # Deduplicate and sort skills alphabetically by name
    resolved["skills"] = sorted(resolved_skills, key=lambda s: s["name"])

    # Deduplicate Experience entries
    unique_exp = []
    for exp in mc.experience_contributions:
        matched = False
        for u in unique_exp:
            if (fuzz.token_sort_ratio(exp["company"], u["company"]) > 85 and
                date_ranges_overlap(exp["start"], exp["end"], u["start"], u["end"])):
                matched = True
                
                # Merge title (most complete)
                if len(exp["title"] or "") > len(u["title"] or ""):
                    u["title"] = exp["title"]
                
                # Merge dates (most precise)
                if get_date_precision(exp["start"]) > get_date_precision(u["start"]):
                    u["start"] = exp["start"]
                if get_date_precision(exp["end"]) > get_date_precision(u["end"]):
                    u["end"] = exp["end"]
                
                # Merge summaries
                if exp["summary"] and u["summary"]:
                    if exp["summary"] not in u["summary"] and u["summary"] not in exp["summary"]:
                        u["summary"] = u["summary"] + "\n" + exp["summary"]
                    elif len(exp["summary"]) > len(u["summary"]):
                        u["summary"] = exp["summary"]
                elif exp["summary"]:
                    u["summary"] = exp["summary"]
                
                if exp["trust"] > u["trust"]:
                    u["trust"] = exp["trust"]
                    u["source"] = exp["source"]
                    u["method"] = exp["method"]
                break
        if not matched:
            unique_exp.append(exp.copy())

    # Format experience entries for schema
    resolved["experience"] = [
        {
            "company": e["company"],
            "title": e["title"],
            "start": e["start"],
            "end": e["end"],
            "summary": e["summary"]
        } for e in unique_exp
    ]

    # Calculate years of experience dynamically from earliest merged start date to today
    earliest_ym = None
    for exp in unique_exp:
        start_str = exp.get("start")
        if start_str and len(start_str) == 7 and "-" in start_str:
            try:
                parts = start_str.split("-")
                ym = (int(parts[0]), int(parts[1]))
                if earliest_ym is None or ym < earliest_ym:
                    earliest_ym = ym
            except Exception:
                pass
                
    if earliest_ym:
        import datetime
        today = datetime.date.today()
        current_year = today.year
        current_month = today.month
        start_year, start_month = earliest_ym
        diff_months = (current_year - start_year) * 12 + (current_month - start_month)
        years_exp = round(max(0.0, diff_months / 12.0), 1)
        resolved["years_experience"] = years_exp
        
        # Log/Print calculations for verification
        print(f"[DEBUG] Unified Years of Experience Calculation for {resolved['full_name']}:", file=sys.stderr)
        print(f"[DEBUG]   Earliest Start Date: {start_year}-{start_month:02d}", file=sys.stderr)
        print(f"[DEBUG]   Current Date:        {today.strftime('%Y-%m-%d')}", file=sys.stderr)
        print(f"[DEBUG]   Calculated Years:    {years_exp} years", file=sys.stderr)

    # Deduplicate Education entries
    unique_edu = []
    for edu in mc.education_contributions:
        matched = False
        for u in unique_edu:
            if (fuzz.token_sort_ratio(edu["institution"], u["institution"]) > 85 and
                (edu["degree"] == u["degree"] or fuzz.token_sort_ratio(edu["degree"] or "", u["degree"] or "") > 85)):
                matched = True
                # Merge fields: pick non-null values; if both non-null, pick higher trust
                for field in ["field", "end_year"]:
                    val_u = u[field]
                    val_edu = edu[field]
                    if val_u is None and val_edu is not None:
                        u[field] = val_edu
                    elif val_u is not None and val_edu is not None:
                        if edu["trust"] > u["trust"]:
                            u[field] = val_edu

                if edu["trust"] > u["trust"]:
                    u["trust"] = edu["trust"]
                    u["source"] = edu["source"]
                    u["method"] = edu["method"]
                break
        if not matched:
            unique_edu.append(edu.copy())

    # Format education entries for schema
    resolved["education"] = [
        {
            "institution": e["institution"],
            "degree": e["degree"],
            "field": e["field"],
            "end_year": e["end_year"]
        } for e in unique_edu
    ]

    # Deduplicate Projects entries
    unique_proj = []
    for proj in mc.projects_contributions:
        matched = False
        for u in unique_proj:
            if fuzz.token_sort_ratio(proj["name"], u["name"]) > 85:
                matched = True
                combined_tech = set(proj["tech_stack"] + u["tech_stack"])
                u["tech_stack"] = sorted(list(combined_tech))
                if proj["description"] and u["description"]:
                    if len(proj["description"]) > len(u["description"]):
                        u["description"] = proj["description"]
                elif proj["description"]:
                    u["description"] = proj["description"]
                if not u["duration"] and proj["duration"]:
                    u["duration"] = proj["duration"]
                break
        if not matched:
            unique_proj.append(proj.copy())

    resolved["projects"] = [
        {
            "name": p["name"],
            "description": p["description"],
            "tech_stack": p["tech_stack"],
            "duration": p["duration"],
            "source": p["source"]
        } for p in unique_proj
    ]

    # Calculate field confidences for overall confidence
    field_confidences = {}
    field_confidences["full_name"] = calculate_field_confidence(mc.contributions.get("full_name") or [], resolved["full_name"])
    field_confidences["emails"] = calculate_field_confidence(mc.contributions.get("emails") or [], resolved["emails"][0] if resolved["emails"] else None)
    field_confidences["phones"] = calculate_field_confidence(mc.contributions.get("phones") or [], resolved["phones"][0] if resolved["phones"] else None)
    
    field_confidences["location"] = (
        calculate_field_confidence(mc.contributions.get("location.city") or [], resolved["location"]["city"]) +
        calculate_field_confidence(mc.contributions.get("location.region") or [], resolved["location"]["region"]) +
        calculate_field_confidence(mc.contributions.get("location.country") or [], resolved["location"]["country"])
    ) / 3.0
    
    field_confidences["links"] = (
        calculate_field_confidence(mc.contributions.get("links.linkedin") or [], resolved["links"]["linkedin"]) +
        calculate_field_confidence(mc.contributions.get("links.github") or [], resolved["links"]["github"]) +
        calculate_field_confidence(mc.contributions.get("links.portfolio") or [], resolved["links"]["portfolio"])
    ) / 3.0
    
    field_confidences["headline"] = calculate_field_confidence(mc.contributions.get("headline") or [], resolved["headline"])
    field_confidences["years_experience"] = calculate_field_confidence(mc.contributions.get("years_experience") or [], resolved["years_experience"])
    
    field_confidences["skills"] = sum(s["confidence"] for s in resolved["skills"]) / len(resolved["skills"]) if resolved["skills"] else 0.0
    field_confidences["experience"] = max((e["trust"] for e in unique_exp), default=0.0)
    field_confidences["education"] = max((e["trust"] for e in unique_edu), default=0.0)

    resolved["overall_confidence"] = calculate_overall_confidence(field_confidences)
    
    resolved["confidence_breakdown"] = {
        "full_name": round(field_confidences.get("full_name", 0.0), 3),
        "email": round(field_confidences.get("emails", 0.0), 3),
        "phone": round(field_confidences.get("phones", 0.0), 3),
        "skills": round(field_confidences.get("skills", 0.0), 3),
        "education": round(field_confidences.get("education", 0.0), 3),
        "experience": round(field_confidences.get("experience", 0.0), 3)
    }

    # Generate provenance entries (which now covers all fields)
    resolved["provenance"] = generate_provenance(
        resolved, mc.contributions, mc.skills_contributions, unique_exp, unique_edu, unique_proj
    )

    return resolved


def run_pipeline(
    csv_path: Optional[str] = None,
    ats_path: Optional[str] = None,
    github_source: Optional[str] = None,
    resume_path: Optional[str] = None,
    config_path: str = "config/default.json",
    output_dir: str = "output/"
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Executes the candidate data transformer pipeline.
    Returns a tuple of (run_summary_dict, list_of_projected_profiles).
    """
    os.makedirs(output_dir, exist_ok=True)

    sources_used = []
    errors_logged = {}
    parsed_sources: List[Tuple[str, List[Dict[str, Any]], float]] = []

    start_time = time.time()
    ingest_time = start_time

    # CSV Source
    if csv_path:
        if not os.path.exists(csv_path):
            errors_logged["csv"] = f"File not found: {csv_path}"
            print(f"[WARNING] CSV Source file not found: {csv_path}", file=sys.stderr)
        else:
            try:
                candidates = parse_csv(csv_path)
                parsed_sources.append(("csv", candidates, ingest_time))
                sources_used.append("csv")
            except Exception as e:
                errors_logged["csv"] = f"Parse failed: {str(e)}"
                print(f"[WARNING] CSV Parser failed: {str(e)}", file=sys.stderr)

    # ATS Source
    if ats_path:
        if not os.path.exists(ats_path):
            errors_logged["ats"] = f"File not found: {ats_path}"
            print(f"[WARNING] ATS Source file not found: {ats_path}", file=sys.stderr)
        else:
            try:
                candidates = parse_ats_json(ats_path)
                parsed_sources.append(("ats", candidates, ingest_time))
                sources_used.append("ats")
            except Exception as e:
                errors_logged["ats"] = f"Parse failed: {str(e)}"
                print(f"[WARNING] ATS Parser failed: {str(e)}", file=sys.stderr)

    # GitHub Source
    if github_source and github_source.strip():
        parts = [p.strip() for p in github_source.split(",") if p.strip()]
        github_candidates = []
        for part in parts:
            username = part
            assoc_email = None
            if "@" in part and ":" in part:
                username, assoc_email = [item.strip() for item in part.rsplit(":", 1)]
            try:
                github_data = fetch_github_profile(username, errors_logged)
                if assoc_email:
                    github_data["emails"] = [assoc_email]
                github_candidates.append(github_data)
                if "github" not in sources_used:
                    sources_used.append("github")
            except Exception as e:
                errors_logged[f"github_{username}"] = f"Fetch failed: {str(e)}"
                print(f"[WARNING] GitHub Fetcher failed for {username}: {str(e)}", file=sys.stderr)
        if github_candidates:
            parsed_sources.append(("github", github_candidates, ingest_time))

    # Resume Source
    if resume_path:
        resolved_resumes = resolve_file_paths(resume_path)
        if not resolved_resumes:
            errors_logged["resume"] = f"No resume files found matching: {resume_path}"
            print(f"[WARNING] No resume files found matching: {resume_path}", file=sys.stderr)
        else:
            try:
                resume_candidates = parse_resumes(resolved_resumes)
                if resume_candidates:
                    parsed_sources.append(("resume", resume_candidates, ingest_time))
                    sources_used.append("resume")
            except Exception as e:
                errors_logged["resume"] = f"Parse failed: {str(e)}"
                print(f"[WARNING] Resume Parser failed: {str(e)}", file=sys.stderr)

    if not parsed_sources:
        raise ValueError("No sources were successfully ingested or parsed.")

    # Print/log the parsed output of EACH source parser individually before merge
    print("\n=== DEBUG: Ingested Source Parsing Output (Pre-Merge) ===", file=sys.stderr)
    for s_idx, (source, candidates, ts) in enumerate(parsed_sources, start=1):
        print(f"Source {s_idx}: {source.upper()} (ingestion timestamp: {ts})", file=sys.stderr)
        print(f"  Total Candidates Extracted: {len(candidates)}", file=sys.stderr)
        for idx, c in enumerate(candidates):
            print(f"  Candidate {idx + 1}:", file=sys.stderr)
            print(f"    Name:   {c.get('full_name')}", file=sys.stderr)
            print(f"    Emails: {c.get('emails')}", file=sys.stderr)
            print(f"    Phones: {c.get('phones')}", file=sys.stderr)
            print(f"    Skills: {c.get('skills')}", file=sys.stderr)
            exp_list = [f"{e.get('company')} - {e.get('title')}" for e in c.get('experience') or []]
            print(f"    Jobs:   {exp_list}", file=sys.stderr)
    print("========================================================\n", file=sys.stderr)

    # Merge Candidates
    merged_candidates = merge_sources(parsed_sources, errors_logged)

    # Load runtime projection configuration
    with open(config_path, "r", encoding="utf-8") as f:
        config_data = json.load(f)
    proj_config = ProjectionConfig(**config_data)

    processed_profiles = []
    confidences = []

    total_extracted = 0
    total_missing = 0
    total_conflicts = 0

    for mc in merged_candidates:
        # Check standard fields for conflicts
        for field, contribs in mc.contributions.items():
            if contribs:
                unique_vals = set(str(c["value"]).lower().strip() for c in contribs if c.get("value") is not None)
                if len(unique_vals) > 1:
                    total_conflicts += len(unique_vals) - 1

        profile_dict = resolve_candidate_profile(mc)

        # Validate against canonical schema
        try:
            validated_profile = CandidateProfile(**profile_dict)
            validated_dict = validated_profile.model_dump()
        except ValidationError as ve:
            print(f"[WARNING] Canonical validation failed for candidate {mc.candidate_id}: {str(ve)}", file=sys.stderr)
            validated_dict = profile_dict

        # Count populated and missing fields on the canonical profile
        for k, v in validated_dict.items():
            if k in ["candidate_id", "provenance", "overall_confidence", "confidence_breakdown"]:
                continue
            if v is not None and v != [] and v != {}:
                if isinstance(v, dict):
                    for sub_k, sub_v in v.items():
                        if sub_v is not None and sub_v != [] and sub_v != {}:
                            total_extracted += 1
                        else:
                            total_missing += 1
                else:
                    total_extracted += 1
            else:
                if isinstance(v, dict):
                    total_missing += len(v)
                else:
                    total_missing += 1

        # Calculate experience/education deduplications resolved
        unique_exp_len = len(validated_dict.get("experience") or [])
        raw_exp_len = len(mc.experience_contributions)
        total_conflicts += max(0, raw_exp_len - unique_exp_len)

        unique_edu_len = len(validated_dict.get("education") or [])
        raw_edu_len = len(mc.education_contributions)
        total_conflicts += max(0, raw_edu_len - unique_edu_len)

        # Apply projection
        projected_profile = project_candidate(validated_dict, proj_config)
        processed_profiles.append(projected_profile)
        confidences.append(validated_dict.get("overall_confidence", 0.0))

        # Write canonical and projected to output file
        canonical_file = os.path.join(output_dir, f"canonical_{projected_profile['candidate_id']}.json")
        with open(canonical_file, "w", encoding="utf-8") as can_f:
            json.dump(validated_dict, can_f, indent=2)
            
        output_file = os.path.join(output_dir, f"{projected_profile['candidate_id']}.json")
        with open(output_file, "w", encoding="utf-8") as out_f:
            json.dump(projected_profile, out_f, indent=2)

    # Compute execution time
    execution_time_seconds = round(time.time() - start_time, 3)

    # Skill deduplication count
    raw_skills_count = 0
    for source, candidates, ts in parsed_sources:
        for c in candidates:
            raw_skills_count += len(c.get("skills") or [])
            
    resolved_skills_count = 0
    for mc in merged_candidates:
        resolved_skills_count += len(mc.skills_contributions)
        
    duplicate_skills_removed = max(0, raw_skills_count - resolved_skills_count)

    # Write run summary
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    summary = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "sources_requested": {
            "csv": bool(csv_path),
            "ats": bool(ats_path),
            "github": bool(github_source),
            "resume": bool(resume_path)
        },
        "sources_successfully_used": sources_used,
        "errors": errors_logged,
        "candidates_processed": len(processed_profiles),
        "profiles_generated": len(processed_profiles),
        "execution_time_seconds": execution_time_seconds,
        "fields_extracted": total_extracted,
        "fields_missing": total_missing,
        "conflicts_resolved": total_conflicts,
        "duplicate_skills_removed": duplicate_skills_removed,
        "average_overall_confidence": round(avg_confidence, 3)
    }

    summary_file = os.path.join(output_dir, "run_summary.json")
    with open(summary_file, "w", encoding="utf-8") as sum_f:
        json.dump(summary, sum_f, indent=2)

    return summary, processed_profiles


def main():
    parser = argparse.ArgumentParser(description="Messy Candidate Data Transformer Pipeline")
    parser.add_argument("--csv", help="Path to Recruiter CSV file")
    parser.add_argument("--ats", help="Path to ATS JSON file")
    parser.add_argument("--github", help="GitHub username or profile URL")
    parser.add_argument("--resume", nargs="*", help="Path to Resume PDF or DOCX file(s), directory, or glob pattern")
    parser.add_argument("--config", default="config/default.json", help="Path to runtime projection config JSON")
    parser.add_argument("--output", default="output/", help="Path to output directory")

    args = parser.parse_args()

    try:
        summary, profiles = run_pipeline(
            csv_path=args.csv,
            ats_path=args.ats,
            github_source=args.github,
            resume_path=args.resume,
            config_path=args.config,
            output_dir=args.output
        )
        print(f"Successfully processed {len(profiles)} candidates.")
        print(f"Wrote run summary to {os.path.join(args.output, 'run_summary.json')}")
    except Exception as e:
        print(f"[ERROR] Pipeline failed: {str(e)}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
