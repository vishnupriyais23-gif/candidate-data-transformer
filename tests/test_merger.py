import pytest
from core.merger import merge_sources, MergedCandidate
from transform import resolve_candidate_profile

def test_merge_same_candidate_by_email():
    # Candidate in CSV and ATS with same email but slightly different names
    csv_data = [
        {
            "full_name": "Vishwesh N",
            "emails": ["vishwesh@example.com"],
            "phones": ["+919014746514"]
        }
    ]
    ats_data = [
        {
            "full_name": "Vishwesh Neww",
            "emails": ["vishwesh@example.com"],
            "phones": ["+919014746514"]
        }
    ]
    
    parsed_sources = [
        ("csv", csv_data, 1000.0),
        ("ats", ats_data, 2000.0)
    ]
    
    merged = merge_sources(parsed_sources)
    assert len(merged) == 1
    
    resolved = resolve_candidate_profile(merged[0])
    # CSV has higher trust (0.85) than ATS (0.80), so name should be from CSV
    assert resolved["full_name"] == "Vishwesh N"
    assert "vishwesh@example.com" in resolved["emails"]

def test_merge_conflict_picks_higher_trust_source():
    # Conflict in years of experience between CSV (trust 0.85) and Resume (trust 0.60)
    csv_data = [{"full_name": "Jane Doe", "emails": ["jane@example.com"], "years_experience": 5.0}]
    resume_data = [{"full_name": "Jane Doe", "emails": ["jane@example.com"], "years_experience": 8.0}]
    
    parsed_sources = [
        ("resume", resume_data, 1000.0),
        ("csv", csv_data, 2000.0)
    ]
    
    merged = merge_sources(parsed_sources)
    resolved = resolve_candidate_profile(merged[0])
    # Should pick 5.0 from CSV due to higher trust
    assert resolved["years_experience"] == 5.0

def test_merge_unknown_candidate_gets_new_id():
    # Two different candidates
    csv_data = [{"full_name": "John Doe", "emails": ["john@example.com"]}]
    ats_data = [{"full_name": "Jane Doe", "emails": ["jane@example.com"]}]
    
    parsed_sources = [
        ("csv", csv_data, 1000.0),
        ("ats", ats_data, 2000.0)
    ]
    
    merged = merge_sources(parsed_sources)
    assert len(merged) == 2
    assert merged[0].candidate_id != merged[1].candidate_id
