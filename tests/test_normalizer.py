import pytest
from core.normalizer import (
    normalize_name, normalize_email, normalize_phone,
    normalize_date, normalize_country, normalize_skill
)

def test_phone_e164_indian_number():
    assert normalize_phone("+91 90147 46514") == "+919014746514"
    assert normalize_phone("9014746514") == "+919014746514"  # Default region IN
    assert normalize_phone("090147 46514") == "+919014746514"

def test_phone_invalid_returns_null():
    assert normalize_phone("not-a-phone-number") is None
    assert normalize_phone("") is None
    assert normalize_phone("123") is None

def test_date_various_formats_to_yyyy_mm():
    assert normalize_date("Jan 2020") == "2020-01"
    assert normalize_date("2020-06-15") == "2020-06"
    assert normalize_date("06/2021") == "2021-06"
    assert normalize_date("Present") is None
    assert normalize_date("invalid-date") is None

def test_skill_fuzzy_match_js_to_javascript():
    assert normalize_skill("JS") == "JavaScript"
    assert normalize_skill("javascript") == "JavaScript"
    assert normalize_skill("ML") == "Machine Learning"
    assert normalize_skill("Machine Learning") == "Machine Learning"
    # Unrecognized skill should be title-cased
    assert normalize_skill("some new tech") == "some new tech"
