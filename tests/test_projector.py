import pytest
from schemas.config_schema import ProjectionConfig
from core.projector import project_candidate

def test_config_field_selection():
    candidate = {
        "candidate_id": "12345",
        "full_name": "John Doe",
        "emails": ["john@example.com"],
        "headline": "Software Engineer",
        "overall_confidence": 0.85,
        "provenance": []
    }
    
    config_data = {
        "fields": [
            { "path": "full_name", "type": "string" }
        ],
        "include_confidence": False,
        "include_provenance": False,
        "on_missing": "null"
    }
    config = ProjectionConfig(**config_data)
    projected = project_candidate(candidate, config)
    
    assert projected["candidate_id"] == "12345"
    assert projected["full_name"] == "John Doe"
    assert "emails" not in projected
    assert "overall_confidence" not in projected

def test_config_rename_via_from_key():
    candidate = {
        "candidate_id": "12345",
        "full_name": "John Doe",
        "emails": ["john@example.com"],
        "overall_confidence": 0.85
    }
    
    config_data = {
        "fields": [
            { "path": "primary_email", "from": "emails[1]", "type": "string" }
        ],
        "include_confidence": True,
        "include_provenance": False,
        "on_missing": "null"
    }
    config = ProjectionConfig(**config_data)
    projected = project_candidate(candidate, config)
    
    assert projected["primary_email"] == "john@example.com"
    assert projected["overall_confidence"] == 0.85

def test_config_on_missing_null():
    candidate = {
        "candidate_id": "12345",
        "full_name": "John Doe"
    }
    
    config_data = {
        "fields": [
            { "path": "full_name", "type": "string" },
            { "path": "headline", "type": "string" }
        ],
        "include_confidence": False,
        "include_provenance": False,
        "on_missing": "null"
    }
    config = ProjectionConfig(**config_data)
    projected = project_candidate(candidate, config)
    
    assert projected["full_name"] == "John Doe"
    assert projected["headline"] is None

def test_on_missing_omit_removes_field():
    candidate = {
        "candidate_id": "12345",
        "full_name": "John Doe"
    }
    
    config_data = {
        "fields": [
            { "path": "full_name", "type": "string" },
            { "path": "headline", "type": "string" }
        ],
        "include_confidence": False,
        "include_provenance": False,
        "on_missing": "omit"
    }
    config = ProjectionConfig(**config_data)
    projected = project_candidate(candidate, config)
    
    assert projected["full_name"] == "John Doe"
    assert "headline" not in projected

def test_on_missing_error_raises_clear_message():
    candidate = {
        "candidate_id": "12345",
        "full_name": "John Doe"
    }
    
    config_data = {
        "fields": [
            { "path": "full_name", "type": "string" },
            { "path": "headline", "type": "string" }
        ],
        "include_confidence": False,
        "include_provenance": False,
        "on_missing": "error"
    }
    config = ProjectionConfig(**config_data)
    
    with pytest.raises(ValueError) as excinfo:
        project_candidate(candidate, config)
        
    assert "Field 'headline' is missing or null" in str(excinfo.value)
