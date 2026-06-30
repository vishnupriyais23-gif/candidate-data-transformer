import pytest
import os
from unittest.mock import patch, MagicMock
from sources.github_fetcher import fetch_github_profile
from sources.pdf_parser import parse_resume, parse_experience_section, parse_education_section
from transform import run_pipeline, resolve_candidate_profile
from core.merger import merge_sources

def test_github_404_returns_null_fields():
    # Mock requests.get to return a 404 response
    with patch("requests.get") as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response
        
        profile = fetch_github_profile("nonexistent_user_123456")
        assert isinstance(profile, dict)
        assert profile["full_name"] is None
        assert profile["headline"] is None
        assert len(profile["emails"]) == 0
        assert len(profile["skills"]) == 0
        assert profile["links"]["github"] == "https://github.com/nonexistent_user_123456"

def test_missing_csv_file_does_not_crash():
    # Run the pipeline with a non-existent CSV file but a valid ATS file
    # It should log the error for CSV, but successfully process ATS and not crash
    summary, profiles = run_pipeline(
        csv_path="nonexistent_file.csv",
        ats_path="data/ats_export.json",
        config_path="config/default.json",
        output_dir="output/"
    )
    
    assert "csv" in summary["errors"]
    assert "File not found" in summary["errors"]["csv"]
    assert "ats" in summary["sources_successfully_used"]
    assert len(profiles) > 0

def test_conflicting_emails_union_merged():
    # Two sources with different emails for the same candidate (matched by fuzzy name)
    csv_data = [{"full_name": "Vishwesh Neww", "emails": ["vishwesh.n@example.com"]}]
    ats_data = [{"full_name": "Vishwesh Neww", "emails": ["vishwesh.neww@example.com"]}]
    
    parsed_sources = [
        ("csv", csv_data, 1000.0),
        ("ats", ats_data, 2000.0)
    ]
    
    merged = merge_sources(parsed_sources)
    assert len(merged) == 1
    
    resolved = resolve_candidate_profile(merged[0])
    # Both emails should be in the union-merged list
    assert "vishwesh.n@example.com" in resolved["emails"]
    assert "vishwesh.neww@example.com" in resolved["emails"]
    
    # Check that each email is represented in provenance
    prov_emails = [p for p in resolved["provenance"] if p["field"] == "emails"]
    assert len(prov_emails) >= 2
    sources_in_prov = [p["source"] for p in prov_emails]
    assert "csv" in sources_in_prov
    assert "ats" in sources_in_prov

def test_provenance_exists_for_every_field():
    # Verify that every canonical field is represented in the provenance list
    csv_data = [{"full_name": "Jane Doe", "emails": ["jane@example.com"]}]
    parsed_sources = [("csv", csv_data, 1000.0)]
    
    merged = merge_sources(parsed_sources)
    resolved = resolve_candidate_profile(merged[0])
    
    canonical_fields = [
        "full_name", "headline", "years_experience",
        "location.city", "location.region", "location.country",
        "links.linkedin", "links.github", "links.portfolio", "links.other",
        "emails", "phones", "skills", "experience", "education"
    ]
    
    prov_fields = [p["field"] for p in resolved["provenance"]]
    for field in canonical_fields:
        assert field in prov_fields, f"Missing provenance for field: {field}"

def test_overall_confidence_between_0_and_1():
    # Verify that overall confidence is bounded between 0.0 and 1.0
    csv_data = [{"full_name": "Jane Doe", "emails": ["jane@example.com"]}]
    parsed_sources = [("csv", csv_data, 1000.0)]
    
    merged = merge_sources(parsed_sources)
    resolved = resolve_candidate_profile(merged[0])
    
    assert 0.0 <= resolved["overall_confidence"] <= 1.0

def test_garbage_pdf_returns_null_fields():
    # Mock pdfplumber to simulate a scanned PDF with no text layer
    with patch("pdfplumber.open") as mock_pdf_open:
        mock_pdf = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = None  # No text extracted
        mock_pdf.pages = [mock_page]
        mock_pdf_open.return_value.__enter__.return_value = mock_pdf
        
        result = parse_resume("scanned_resume.pdf")
        assert result["full_name"] is None
        assert len(result["emails"]) == 0
        assert len(result["phones"]) == 0
        assert len(result["skills"]) == 0
        assert len(result["experience"]) == 0
        assert len(result["education"]) == 0

def test_multiple_resumes_match_correct_candidates():
    csv_data = [
        {"full_name": "Aarav Sharma", "emails": ["aarav@example.com"]},
        {"full_name": "Priya Menon", "emails": ["priya@example.com"]}
    ]
    resume_data = [
        {"full_name": "Aarav Sharma", "emails": ["aarav@example.com"], "skills": ["Java"]},
        {"full_name": "Priya Menon", "emails": ["priya@example.com"], "skills": ["Python"]}
    ]
    
    parsed_sources = [
        ("csv", csv_data, 1000.0),
        ("resume", resume_data, 2000.0)
    ]
    
    merged = merge_sources(parsed_sources)
    assert len(merged) == 2
    
    resolved_profiles = [resolve_candidate_profile(m) for m in merged]
    resolved_profiles.sort(key=lambda p: p["full_name"])
    
    aarav_profile = resolved_profiles[0]
    priya_profile = resolved_profiles[1]
    
    assert aarav_profile["full_name"] == "Aarav Sharma"
    assert "Java" in [s["name"] for s in aarav_profile["skills"]]
    assert "Python" not in [s["name"] for s in aarav_profile["skills"]]
    
    assert priya_profile["full_name"] == "Priya Menon"
    assert "Python" in [s["name"] for s in priya_profile["skills"]]
    assert "Java" not in [s["name"] for s in priya_profile["skills"]]

def test_merge_does_not_cross_contaminate_candidates():
    csv_data = [
        {"full_name": "Aarav Sharma", "emails": ["aarav@example.com"], "phones": ["+919876543210"]},
        {"full_name": "Priya Menon", "emails": ["priya@example.com"], "phones": ["+919123456780"]}
    ]
    resume_data = [
        {"full_name": "Aarav Sharma", "emails": ["aarav@example.com"], "phones": ["+919876543210"]},
        {"full_name": "Priya Menon", "emails": ["p.menon@example.com"], "phones": ["+919123456780"]}
    ]
    
    parsed_sources = [
        ("csv", csv_data, 1000.0),
        ("resume", resume_data, 2000.0)
    ]
    
    merged = merge_sources(parsed_sources)
    assert len(merged) == 2
    
    resolved_profiles = [resolve_candidate_profile(m) for m in merged]
    resolved_profiles.sort(key=lambda p: p["full_name"])
    
    aarav_profile = resolved_profiles[0]
    priya_profile = resolved_profiles[1]
    
    assert aarav_profile["full_name"] == "Aarav Sharma"
    assert "aarav@example.com" in aarav_profile["emails"]
    assert "p.menon@example.com" not in aarav_profile["emails"]
    assert "+919876543210" in aarav_profile["phones"]
    assert "+919123456780" not in aarav_profile["phones"]
    
    assert priya_profile["full_name"] == "Priya Menon"
    assert "priya@example.com" in priya_profile["emails"]
    assert "p.menon@example.com" in priya_profile["emails"]
    assert "aarav@example.com" not in priya_profile["emails"]
    assert "+919123456780" in priya_profile["phones"]
    assert "+919876543210" not in priya_profile["phones"]
    
    # Assert provenance tracing:
    aarav_mc = [m for m in merged if m.get_name() == "Aarav Sharma"][0]
    for email in aarav_profile["emails"]:
        contribs = [c for c in aarav_mc.contributions.get("emails", []) if c["value"] == email]
        assert len(contribs) > 0, f"Email {email} has no raw contribution"
        for c in contribs:
            source_candidates = [s[1] for s in parsed_sources if s[0] == c["source"]][0]
            source_c = [sc for sc in source_candidates if sc.get("full_name") == "Aarav Sharma"][0]
            assert email in source_c.get("emails", []), f"Source did not contain email for Aarav"
            
    for phone in aarav_profile["phones"]:
        contribs = [c for c in aarav_mc.contributions.get("phones", []) if c["value"] == phone]
        assert len(contribs) > 0, f"Phone {phone} has no raw contribution"
        for c in contribs:
            source_candidates = [s[1] for s in parsed_sources if s[0] == c["source"]][0]
            source_c = [sc for sc in source_candidates if sc.get("full_name") == "Aarav Sharma"][0]
            assert phone in source_c.get("phones", []), f"Source did not contain phone for Aarav"

def test_resume_job_header_requires_em_dash_and_date_range():
    text = "Designed event-driven architecture using Kafka for order processing"
    entries = parse_experience_section(text)
    assert len(entries) == 0

def test_resume_bullets_appended_to_summary_not_new_entries():
    text = """Software Engineer — TechNova Solutions, Bangalore (2023-06 - Present)
- Built and maintained microservices handling 2M+ daily requests
- Reduced API latency by 35% through caching and query optimization"""
    entries = parse_experience_section(text)
    assert len(entries) == 1
    assert entries[0]["company"] == "TechNova Solutions"
    assert entries[0]["title"] == "Software Engineer"
    assert entries[0]["start"] == "2023-06"
    assert entries[0]["end"] == "Present"
    assert "Built and maintained microservices" in entries[0]["summary"]
    assert "Reduced API latency by 35%" in entries[0]["summary"]

def test_education_end_year_is_second_year_in_range():
    text = "B.E. Computer Science, BMS College of Engineering, Bangalore, India (2019 - 2023)"
    entries = parse_education_section(text)
    assert len(entries) == 1
    assert entries[0]["end_year"] == 2023

def test_education_institution_captures_full_name_with_of_in_it():
    text = "B.E. Computer Science, BMS College of Engineering, Bangalore, India (2019 - 2023)"
    entries = parse_education_section(text)
    assert len(entries) == 1
    assert entries[0]["institution"] == "BMS College of Engineering"

def test_education_field_correctly_separated_from_degree():
    text = "B.Tech Information Technology, Anna University, Chennai, India (2019 - 2023)"
    entries = parse_education_section(text)
    assert len(entries) == 1
    assert entries[0]["degree"] == "B.Tech"
    assert entries[0]["field"] == "Information Technology"

from unittest.mock import patch, MagicMock
from sources.github_fetcher import extract_username, fetch_github_profile
from core.merger import TRUST_LEVELS

def test_notes_no_longer_referenced_anywhere():
    # 1. Notes is not in TRUST_LEVELS
    assert "notes" not in TRUST_LEVELS
    # 2. verify notes_path is not in run_pipeline parameters
    import inspect
    import transform
    sig = inspect.signature(transform.run_pipeline)
    assert "notes_path" not in sig.parameters

def test_github_accepts_full_url_and_bare_username():
    assert extract_username("https://github.com/torvalds/") == "torvalds"
    assert extract_username("https://github.com/torvalds") == "torvalds"
    assert extract_username("torvalds") == "torvalds"
    assert extract_username("torvalds/") == "torvalds"
    assert extract_username("https://github.com/torvalds?tab=repositories") == "torvalds"
    assert extract_username("torvalds?tab=repositories") == "torvalds"
    assert extract_username("") == ""
    assert extract_username(None) == ""

@patch("requests.get")
def test_github_404_returns_null_fields_gracefully(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_get.return_value = mock_resp
    
    errors = {}
    profile = fetch_github_profile("nonexistent_user_12345", errors)
    assert profile["full_name"] is None
    assert profile["skills"] == []
    assert errors.get("github") is not None
    assert "404" in errors["github"]

@patch("requests.get")
def test_github_empty_username_skips_fetch(mock_get):
    profile = fetch_github_profile("   ")
    assert profile["full_name"] is None
    mock_get.assert_not_called()

@patch("requests.get")
def test_github_languages_mapped_to_canonical_skills(mock_get):
    mock_user_resp = MagicMock()
    mock_user_resp.status_code = 200
    mock_user_resp.json.return_value = {
        "name": "Linus Torvalds",
        "bio": "Creator of Linux",
        "location": "Portland, OR",
        "blog": "https://blog.example.com",
        "html_url": "https://github.com/torvalds"
    }
    
    mock_repos_resp = MagicMock()
    mock_repos_resp.status_code = 200
    mock_repos_resp.json.return_value = [
        {"language": "C"},
        {"language": "C++"},
        {"language": "Python"},
        {"language": "Python"}
    ]
    mock_get.side_effect = [mock_user_resp, mock_repos_resp]
    
    profile = fetch_github_profile("torvalds")
    assert profile["full_name"] == "Linus Torvalds"
    assert profile["headline"] == "Creator of Linux"
    assert profile["links"]["github"] == "https://github.com/torvalds"
    assert profile["links"]["portfolio"] == "https://blog.example.com"
    
    skills = profile["skills"]
    skills_map = {s["name"]: s["confidence"] for s in skills}
    assert "C" in skills_map
    assert "C++" in skills_map
    assert "Python" in skills_map
    assert skills_map["Python"] == 0.7

@patch("requests.get")
def test_github_jupyter_notebook_excluded_as_skill(mock_get):
    mock_user_resp = MagicMock()
    mock_user_resp.status_code = 200
    mock_user_resp.json.return_value = {"name": "Test User"}
    
    mock_repos_resp = MagicMock()
    mock_repos_resp.status_code = 200
    mock_repos_resp.json.return_value = [
        {"language": "Jupyter Notebook"},
        {"language": "Python"}
    ]
    mock_get.side_effect = [mock_user_resp, mock_repos_resp]
    
    profile = fetch_github_profile("testuser")
    skills = [s["name"] for s in profile["skills"]]
    assert "Python" in skills
    assert "Jupyter Notebook" not in skills

from core.merger import merge_sources

def test_github_unmatched_candidate_discarded():
    github_data = [{"full_name": "Linus Torvalds", "links": {"github": "https://github.com/torvalds"}}]
    parsed_sources = [
        ("github", github_data, 1000.0)
    ]
    errors = {}
    merged = merge_sources(parsed_sources, errors)
    assert len(merged) == 0
    assert "github" in errors
    assert "discarded" in errors["github"]

def test_github_matched_candidate_merged():
    csv_data = [{"full_name": "Aarav Sharma", "emails": ["aarav@example.com"], "links": {"github": "https://github.com/aaravsharma-dev"}}]
    github_data = [{"full_name": "Aarav Sharma", "links": {"github": "https://github.com/aaravsharma-dev"}}]
    
    parsed_sources = [
        ("csv", csv_data, 1000.0),
        ("github", github_data, 2000.0)
    ]
    
    errors = {}
    merged = merge_sources(parsed_sources, errors)
    assert len(merged) == 1
    assert "github" not in errors

from sources.pdf_parser import find_city_in_text

def test_experience_handles_en_dash_separator():
    text = "Project Collaborator – Explainable Edge-AI Image Analytics for Crop Stress Detection Feb 2026 – Present"
    entries = parse_experience_section(text)
    assert len(entries) == 1
    assert entries[0]["title"] == "Project Collaborator"
    assert entries[0]["company"] == "Explainable Edge-AI Image Analytics for Crop Stress Detection"
    assert entries[0]["start"] == "Feb 2026"
    assert entries[0]["end"] == "Present"

def test_experience_section_stops_at_next_section_header():
    text = """Project Collaborator – Explainable Edge-AI Image Analytics for Crop Stress Detection Feb 2026 – Present
• Building an Explainable Edge-AI framework
Projects
Personal Expense Tracker | C++, File Handling, Data Structures 2023 (Individual)"""
    entries = parse_experience_section(text)
    assert len(entries) == 1
    assert "Personal Expense Tracker" not in (entries[0]["summary"] or "")

def test_experience_returns_empty_list_not_garbage_blob_on_parse_failure():
    text = "Some random text without any experience headers or dates"
    entries = parse_experience_section(text)
    assert len(entries) == 0

def test_education_two_line_format_institution_correctly_extracted():
    text = """BMS College of Engineering Bengaluru, Karnataka, India
Bachelor of Engineering – Information Science and Engineering; CGPA: 8.95"""
    entries = parse_education_section(text)
    assert len(entries) == 1
    assert entries[0]["institution"] == "BMS College of Engineering"
    assert entries[0]["degree"] == "Bachelor of Engineering"
    assert entries[0]["field"] == "Information Science and Engineering"

def test_education_two_line_format_field_not_swapped_with_location():
    text = """Sanskar Public School Gwalior, Madhya Pradesh, India
Higher Secondary Certificate (HSC): 89% April 2022"""
    entries = parse_education_section(text)
    assert len(entries) == 1
    assert entries[0]["institution"] == "Sanskar Public School"
    assert entries[0]["degree"] == "Higher Secondary Certificate (HSC)"
    assert entries[0]["field"] is None
    assert entries[0]["end_year"] == 2022

def test_location_inferred_from_recent_experience_when_no_explicit_line():
    with patch("sources.pdf_parser.extract_text_from_pdf") as mock_extract:
        mock_extract.return_value = """Tanishka Agarwal
tanishkaagarwal.is23@bmsce.ac.in
Education
BMS College of Engineering Bengaluru, Karnataka, India
Bachelor of Engineering – Information Science and Engineering
Experience
Indian Institute of Horticultural Research (IIHR) Gwalior, India
Project Collaborator – Explainable Edge-AI Feb 2026 – Present"""
        
        from sources.pdf_parser import parse_resume
        res = parse_resume("dummy.pdf")
        assert res["location"]["city"] == "Gwalior"
        assert res.get("_inferred_location_city") is True

from core.merger import MergedCandidate
from transform import resolve_candidate_profile

def test_merger_deduplicates_same_job_from_csv_and_resume():
    mc = MergedCandidate()
    mc.experience_contributions.append({
        "company": "Indian Institute of Horticultural Research (IIHR)",
        "title": "Project Collaborator",
        "start": None,
        "end": None,
        "summary": None,
        "source": "csv",
        "trust": 0.85,
        "timestamp": 1000.0,
        "method": "direct_extract"
    })
    mc.experience_contributions.append({
        "company": "Indian Institute of Horticultural Research (IIHR)",
        "title": "Project Collaborator – Explainable Edge-AI Image Analytics for Crop Stress Detection",
        "start": "Feb 2026",
        "end": "Present",
        "summary": "Building an Explainable Edge-AI framework",
        "source": "resume",
        "trust": 0.60,
        "timestamp": 2000.0,
        "method": "heuristic"
    })
    
    profile = resolve_candidate_profile(mc)
    assert len(profile["experience"]) == 1
    assert profile["experience"][0]["company"] == "Indian Institute of Horticultural Research (IIHR)"
    assert profile["experience"][0]["title"] == "Project Collaborator – Explainable Edge-AI Image Analytics for Crop Stress Detection"
    assert profile["experience"][0]["start"] == "Feb 2026"
    assert profile["experience"][0]["end"] == "Present"
    assert profile["experience"][0]["summary"] == "Building an Explainable Edge-AI framework"

def test_two_line_job_format_company_above_title_below():
    text = """Indian Institute of Horticultural Research (IIHR) Bangalore, India
Project Collaborator – Explainable Edge-AI Image Analytics for Crop Stress Detection Feb 2026 – Present
• Building an Explainable Edge-AI framework"""
    entries = parse_experience_section(text)
    assert len(entries) == 1
    assert entries[0]["company"] == "Indian Institute of Horticultural Research (IIHR)"
    assert entries[0]["title"] == "Project Collaborator – Explainable Edge-AI Image Analytics for Crop Stress Detection"
    assert entries[0]["start"] == "Feb 2026"
    assert entries[0]["end"] == "Present"
    assert "Building an Explainable Edge-AI framework" in entries[0]["summary"]

def test_pdf_hyperlinks_extracted_for_github_linkedin_portfolio():
    with patch("pdfplumber.open") as mock_open:
        mock_pdf = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Tanishka Agarwal\nGitHub: Repository Demo: Live App"
        mock_page.hyperlinks = [
            {"uri": "https://github.com/tanishkaagarwalis23-coder/illness_prediction_chatbot"},
            {"uri": "https://linkedin.com/in/tanishkaagarwal"},
            {"uri": "https://illness-prediction-chatbot-8imu.onrender.com"}
        ]
        mock_pdf.pages = [mock_page]
        mock_open.return_value.__enter__.return_value = mock_pdf
        
        res = parse_resume("dummy.pdf")
        assert res["links"]["github"] == "https://github.com/tanishkaagarwalis23-coder/illness_prediction_chatbot"
        assert res["links"]["linkedin"] == "https://linkedin.com/in/tanishkaagarwal"
        assert res["links"]["portfolio"] == "https://illness-prediction-chatbot-8imu.onrender.com"
        assert res.get("_hyperlink_github") is True
        assert res.get("_hyperlink_linkedin") is True
        assert res.get("_hyperlink_portfolio") is True

def test_education_stops_at_projects_section_header():
    text = """BMS College of Engineering, Bangalore
2023 – 2027 Bachelor of Engineering in Information Science
Projects
Symptom-Based Illness Prediction Chatbot
• Developed an AI-powered chatbot"""
    entries = parse_education_section(text)
    assert len(entries) == 1
    assert entries[0]["institution"] == "BMS College of Engineering"

def test_education_year_range_before_degree_format():
    text = """2023 – 2027  B.E. Information Science, BMS College of Engineering, Bangalore  GPA: 9.38"""
    entries = parse_education_section(text)
    assert len(entries) == 1
    assert entries[0]["institution"] == "BMS College of Engineering"
    assert entries[0]["degree"] == "B.E."
    assert entries[0]["field"] == "Information Science"
    assert entries[0]["end_year"] == 2027

def test_hyperlink_extractor_excludes_tel_and_mailto_links():
    with patch("pdfplumber.open") as mock_open:
        mock_pdf = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Tanishka Agarwal"
        mock_page.hyperlinks = [
            {"uri": "mailto:tanishkaagarwal.is23@bmsce.ac.in"},
            {"uri": "tel:+919014746514"},
            {"uri": "https://github.com/tanishkaagarwal"}
        ]
        mock_pdf.pages = [mock_page]
        mock_open.return_value.__enter__.return_value = mock_pdf
        
        res = parse_resume("dummy.pdf")
        assert res["links"]["github"] == "https://github.com/tanishkaagarwal"
        assert res["links"]["portfolio"] is None

def test_multiple_github_usernames_per_candidate_supported():
    with patch("transform.fetch_github_profile") as mock_fetch:
        mock_fetch.side_effect = lambda username, errors: {
            "full_name": "Tanishka" if "tanishka" in username.lower() else "Vishnupriya",
            "emails": [],
            "location": {"city": None, "region": None, "country": None},
            "links": {"linkedin": None, "github": f"https://github.com/{username}", "portfolio": None, "other": []},
            "skills": []
        }
        
        with patch("transform.parse_resumes") as mock_resumes:
            mock_resumes.return_value = [
                {
                    "full_name": "Tanishka",
                    "emails": ["tanishka@example.com"],
                    "phones": [],
                    "location": {"city": None, "region": None, "country": None},
                    "links": {"linkedin": None, "github": None, "portfolio": None, "other": []},
                    "skills": [],
                    "experience": [],
                    "education": []
                },
                {
                    "full_name": "Vishnupriya",
                    "emails": ["vishnu@example.com"],
                    "phones": [],
                    "location": {"city": None, "region": None, "country": None},
                    "links": {"linkedin": None, "github": None, "portfolio": None, "other": []},
                    "skills": [],
                    "experience": [],
                    "education": []
                }
            ]
            
            with patch("transform.resolve_file_paths") as mock_paths:
                mock_paths.return_value = ["dummy1.pdf", "dummy2.pdf"]
                
                summary, profiles = run_pipeline(
                    github_source="tanishka-coder:tanishka@example.com, vishh-coder:vishnu@example.com",
                    resume_path=["dummy1.pdf", "dummy2.pdf"]
                )
                
                assert len(profiles) == 2
                p1 = next(p for p in profiles if p["full_name"] == "Tanishka")
                p2 = next(p for p in profiles if p["full_name"] == "Vishnupriya")
                
                assert p1["links.github"] == "https://github.com/tanishka-coder"
                assert p2["links.github"] == "https://github.com/vishh-coder"

def test_country_inferred_from_known_indian_city():
    mc = MergedCandidate()
    mc.add_contribution(
        source="resume",
        data={
            "full_name": "Test Candidate",
            "location": {"city": "Bangalore"}
        },
        timestamp=1000.0
    )
    
    profile = resolve_candidate_profile(mc)
    assert profile["location"]["city"] == "Bangalore"
    assert profile["location"]["country"] == "IN"
    
    country_provenance = next(p for p in profile["provenance"] if p["field"] == "location.country")
    assert country_provenance["source"] == "resume"
    assert country_provenance["method"] == "inferred"

def test_github_username_extraction_handles_all_url_formats():
    from sources.github_fetcher import extract_username
    from core.merger import clean_github_username
    
    test_cases = [
        ("https://github.com/vishnupriyais23-gif", "vishnupriyais23-gif"),
        ("github.com/username", "username"),
        ("username", "username"),
        ("https://github.com/username/", "username"),
    ]
    
    for input_val, expected in test_cases:
        assert extract_username(input_val) == expected
        assert clean_github_username(input_val) == expected.lower()

def test_email_extracted_from_anywhere_in_resume():
    from sources.pdf_parser import parse_resume
    with patch("sources.pdf_parser.extract_text_from_pdf") as mock_extract:
        mock_extract.return_value = """Some candidate name
        This candidate can be reached for opportunities. Contact at: vishwasr762 @gmail.com or call him.
        Education
        University of Gwalior, 2026"""
        res = parse_resume("dummy.pdf")
        assert "vishwasr762@gmail.com" in res["emails"]

def test_education_parser_stops_at_skills():
    from sources.pdf_parser import parse_education_section
    edu_text = """BMS College of Engineering
    B.E. Information Science 2026
    SKILLS & TECHNOLOGIES
    Languages: Python, Java
    Backend: React"""
    res = parse_education_section(edu_text)
    assert len(res) == 1
    assert res[0]["institution"] == "BMS College of Engineering"

def test_education_parser_groups_multiline_entries():
    from sources.pdf_parser import parse_education_section
    edu_text = """SRM Institute of Science and Technology, Kattankulathur
    9.65 / 10 2027
    B.Tech · Computer Science & Engineering
    Edify School, Tirupati
    84.4% 2023
    Class XII – CBSE"""
    res = parse_education_section(edu_text)
    assert len(res) == 2
    assert res[0]["institution"] == "SRM Institute of Science and Technology"
    assert res[0]["degree"] == "B.Tech"
    assert res[0]["field"] == "Computer Science & Engineering"
    assert res[0]["end_year"] == 2027
    assert res[1]["institution"] == "Edify School"
    assert res[1]["degree"] == "Class XII"
    assert res[1]["field"] == "CBSE"
    assert res[1]["end_year"] == 2023

def test_section_headings_not_treated_as_skills():
    from sources.pdf_parser import parse_resume
    with patch("sources.pdf_parser.extract_text_from_pdf") as mock_extract:
        mock_extract.return_value = """Name
        Skills
        Backend / Development
        Python, Java, Go
        Tools
        Git, Docker"""
        res = parse_resume("dummy.pdf")
        assert "Backend / Development" not in res["skills"]
        assert "Tools" not in res["skills"]
        assert "Python" in res["skills"]

def test_headline_never_comes_from_skills():
    from sources.pdf_parser import parse_resume
    with patch("sources.pdf_parser.extract_text_from_pdf") as mock_extract:
        mock_extract.return_value = """Vishwas Reddy
        Summary
        To work as a software engineer at a progressive company.
        Skills
        Python, software engineer, machine learning"""
        res = parse_resume("dummy.pdf")
        assert res["headline"] == "To work as a software engineer at a progressive company."
