import json
import pytest
from unittest.mock import patch, MagicMock
import requests
from core.projector import project_candidate
from core.normalizer import normalize_skill
from core.confidence import calculate_overall_confidence
from schemas.config_schema import ProjectionConfig
from transform import run_pipeline, resolve_candidate_profile
from core.merger import MergedCandidate

def test_projection_retains_all_skills():
    # Canonical profile
    candidate = {
        "candidate_id": "123",
        "full_name": "Aarav Sharma",
        "emails": ["aarav@example.com"],
        "skills": [
            {"name": "Python", "confidence": 0.9, "sources": ["resume"]},
            {"name": "Docker", "confidence": 0.8, "sources": ["resume"]},
            {"name": "MongoDB", "confidence": 0.7, "sources": ["resume"]}
        ]
    }
    config = ProjectionConfig(
        fields=[
            {"path": "full_name", "type": "string"},
            {"path": "skills", "from": "skills[].name", "type": "string[]"}
        ],
        include_confidence=False,
        include_provenance=False
    )
    projected = project_candidate(candidate, config)
    assert projected["skills"] == ["Python", "Docker", "MongoDB"]

def test_projection_retains_provenance():
    candidate = {
        "candidate_id": "123",
        "full_name": "Aarav Sharma",
        "provenance": [
            {"field": "full_name", "source": "resume", "method": "direct_extract"}
        ]
    }
    config = ProjectionConfig(
        fields=[{"path": "full_name", "type": "string"}],
        include_confidence=False,
        include_provenance=True
    )
    projected = project_candidate(candidate, config)
    assert "provenance" in projected
    assert len(projected["provenance"]) == 1
    assert projected["provenance"][0]["field"] == "full_name"

@patch("requests.get")
def test_github_fetch_timeout_handling(mock_get):
    mock_get.side_effect = requests.exceptions.Timeout("Connection timed out")
    from sources.github_fetcher import fetch_github_profile
    errors = {}
    res = fetch_github_profile("testuser", errors)
    assert res["full_name"] is None
    assert "github" in errors
    assert "timeout" in errors["github"]

@patch("requests.get")
def test_github_fetch_rate_limit_handling(mock_get):
    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_get.return_value = mock_response
    from sources.github_fetcher import fetch_github_profile
    errors = {}
    res = fetch_github_profile("testuser", errors)
    assert res["full_name"] is None
    assert "github" in errors
    assert "429" in errors["github"]

def test_canonical_skill_mapping_reactjs():
    assert normalize_skill("ReactJS") == "React"
    assert normalize_skill("react.js") == "React"
    assert normalize_skill("AWS") == "Amazon Web Services"
    assert normalize_skill("ML") == "Machine Learning"
    assert normalize_skill("Py") == "Python"

def test_confidence_breakdown():
    candidate = {
        "candidate_id": "123",
        "full_name": "Aarav Sharma",
        "confidence_breakdown": {
            "full_name": 0.95,
            "email": 1.0,
            "phone": 0.9,
            "skills": 0.82,
            "education": 0.88,
            "experience": 0.79
        }
    }
    config = ProjectionConfig(
        fields=[{"path": "full_name", "type": "string"}],
        include_confidence=False,
        include_provenance=False,
        include_confidence_breakdown=True
    )
    projected = project_candidate(candidate, config)
    assert "confidence_breakdown" in projected
    assert projected["confidence_breakdown"]["full_name"] == 0.95
    assert projected["confidence_breakdown"]["skills"] == 0.82

def test_runtime_config_minimal_schema():
    candidate = {
        "candidate_id": "123",
        "full_name": "Aarav Sharma",
        "emails": ["aarav@example.com"],
        "skills": [
            {"name": "Python", "confidence": 0.9, "sources": ["resume"]}
        ]
    }
    with open("config/minimal.json", "r") as f:
        config_data = json.load(f)
    config = ProjectionConfig(**config_data)
    projected = project_candidate(candidate, config)
    assert "full_name" in projected
    assert "primary_email" in projected
    assert "skills" in projected
    assert "location" not in projected
    assert "experience" not in projected

def test_runtime_config_default_schema():
    candidate = {
        "candidate_id": "123",
        "full_name": "Aarav Sharma",
        "emails": ["aarav@example.com"],
        "location": {"city": "Bangalore", "region": "Karnataka", "country": "IN"},
        "skills": [
            {"name": "Python", "confidence": 0.9, "sources": ["resume"]}
        ]
    }
    with open("config/default.json", "r") as f:
        config_data = json.load(f)
    config = ProjectionConfig(**config_data)
    projected = project_candidate(candidate, config)
    assert "full_name" in projected
    assert "location.city" in projected
    assert "skills" in projected
    assert projected["location.city"] == "Bangalore"

def test_leetcode_prioritization_and_hackerrank():
    from sources.pdf_parser import parse_resume
    resume_text = """
    John Doe
    Email: john@example.com
    LeetCode: https://leetcode.com/u/johndoe
    HackerRank: hackerrank.com/johndoe
    """
    with patch("sources.pdf_parser.extract_text_from_pdf", return_value=resume_text):
        res = parse_resume("dummy.pdf")
        assert res["links"]["leetcode"] == "https://leetcode.com/u/johndoe"
        assert res["links"]["hackerrank"] == "https://hackerrank.com/johndoe"

def test_leetcode_only_prioritization():
    from sources.pdf_parser import parse_resume
    resume_text = """
    John Doe
    Email: john@example.com
    LeetCode: https://leetcode.com/u/johndoe
    """
    with patch("sources.pdf_parser.extract_text_from_pdf", return_value=resume_text):
        res = parse_resume("dummy.pdf")
        assert res["links"]["leetcode"] == "https://leetcode.com/u/johndoe"

def test_hackerrank_only_prioritization():
    from sources.pdf_parser import parse_resume
    resume_text = """
    John Doe
    Email: john@example.com
    HackerRank: https://hackerrank.com/johndoe
    """
    with patch("sources.pdf_parser.extract_text_from_pdf", return_value=resume_text):
        res = parse_resume("dummy.pdf")
        assert res["links"]["hackerrank"] == "https://hackerrank.com/johndoe"

def test_skill_blacklist_filtering():
    assert normalize_skill("Discrete") is None
    assert normalize_skill("Mathematics") is None
    assert normalize_skill("Coursework") is None
    assert normalize_skill("Languages") is None
    assert normalize_skill("Python") == "Python"
    assert normalize_skill("Node") == "Node.js"

def test_location_auto_inference_bangalore():
    from transform import resolve_candidate_profile
    mc = MergedCandidate()
    mc.candidate_id = "test-id"
    mc.contributions = {
        "location.city": [{"value": "Bangalore", "source": "resume", "trust": 0.6, "timestamp": 123.0}]
    }
    resolved = resolve_candidate_profile(mc)
    assert resolved["location"]["city"] == "Bangalore"
    assert resolved["location"]["region"] == "Karnataka"
    assert resolved["location"]["country"] == "IN"
