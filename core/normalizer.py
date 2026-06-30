import re
import phonenumbers
import dateparser
import pycountry
from rapidfuzz import process, fuzz
from typing import Optional, List, Dict, Any

# A dictionary of common skill synonyms to their canonical name
CANONICAL_SKILLS = {
    "javascript": "JavaScript",
    "js": "JavaScript",
    "typescript": "TypeScript",
    "ts": "TypeScript",
    "python": "Python",
    "py": "Python",
    "mongodb": "MongoDB",
    "mongo": "MongoDB",
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "docker": "Docker",
    "kubernetes": "Kubernetes",
    "k8s": "Kubernetes",
    "machine learning": "Machine Learning",
    "ml": "Machine Learning",
    "artificial intelligence": "Artificial Intelligence",
    "ai": "Artificial Intelligence",
    "deep learning": "Deep Learning",
    "dl": "Deep Learning",
    "golang": "Go",
    "go": "Go",
    "reactjs": "React",
    "react.js": "React",
    "react": "React",
    "nodejs": "Node.js",
    "node": "Node.js",
    "aws": "Amazon Web Services",
    "amazon web services": "Amazon Web Services",
    "gcp": "Google Cloud Platform",
    "google cloud": "Google Cloud Platform",
    "azure": "Microsoft Azure",
    "git": "Git",
    "github": "GitHub",
    "django": "Django",
    "flask": "Flask",
    "fastapi": "FastAPI",
    "java": "Java",
    "spring": "Spring Framework",
    "html": "HTML5",
    "css": "CSS3",
    "sql": "SQL",
    "pandas": "Pandas",
    "numpy": "NumPy"
}

def normalize_name(name: Optional[str]) -> Optional[str]:
    """Strips extra whitespace and returns title case."""
    if not name:
        return None
    # Remove extra spaces inside
    cleaned = " ".join(name.split())
    return cleaned.title() if cleaned else None

def normalize_email(email: Optional[str]) -> Optional[str]:
    """Lowercase, strip whitespace, and validate basic format."""
    if not email:
        return None
    email_clean = email.strip().lower()
    # Simple email validation regex
    if re.match(r'^[^@]+@[^@]+\.[^@]+$', email_clean):
        return email_clean
    return None

def normalize_phone(phone: Any, default_region: str = "IN") -> Optional[str]:
    """
    Normalizes phone number to E.164 format.
    If parsing fails, returns None.
    """
    if phone is None:
        return None
    phone_str = str(phone).strip()
    if not phone_str:
        return None
    
    # Strip common non-numeric chars except +
    cleaned = re.sub(r'[^\d+]', '', phone_str)
    if not cleaned:
        return None

    try:
        # First attempt to parse directly (with plus sign)
        parsed = phonenumbers.parse(cleaned, None)
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        pass

    try:
        # Second attempt with default region
        parsed = phonenumbers.parse(phone_str, default_region)
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        pass

    return None

def normalize_date(date_str: Optional[str]) -> Optional[str]:
    """
    Normalizes various date formats to YYYY-MM.
    Returns None if unparseable.
    """
    if not date_str:
        return None
    
    date_str_clean = date_str.strip()
    if date_str_clean.lower() in ["present", "current", "now"]:
        return None

    # Use dateparser
    parsed_date = dateparser.parse(
        date_str_clean,
        settings={'PREFER_DAY_OF_MONTH': 'first', 'REQUIRE_PARTS': ['year']}
    )
    
    if parsed_date:
        return parsed_date.strftime("%Y-%m")
    
    return None

def normalize_country(country_str: Optional[str]) -> Optional[str]:
    """
    Normalizes country name to ISO-3166 alpha-2.
    Returns None if not matched.
    """
    if not country_str:
        return None
    
    country_clean = country_str.strip()
    if len(country_clean) == 2:
        # Already seems to be alpha-2, validate it
        try:
            country = pycountry.countries.get(alpha_2=country_clean.upper())
            if country:
                return country.alpha_2
        except Exception:
            pass

    # Try lookup by name
    try:
        country = pycountry.countries.lookup(country_clean)
        if country:
            return country.alpha_2
    except LookupError:
        pass

    return None

def normalize_skill(skill_str: Optional[str]) -> Optional[str]:
    """
    Normalizes skill name using rapidfuzz against canonical_skills dict.
    If match score >= 85, returns canonical name.
    Else, returns title-cased version of the skill.
    """
    if not skill_str:
        return None
    
    skill_clean = skill_str.strip().lower()
    if not skill_clean:
        return None
        
    SKILL_BLACKLIST = {
        "coursework", "languages", "tools", "systems", "mathematics", "discrete", "engineering", 
        "databasemanagement", "datastructures&algorithms", "software engineering", "web & frameworks", 
        "cryptography & network", "computer organization & architecture", "operating systems",
        "relevant coursework", "programming languages", "technical skills", "web technologies", 
        "databases", "other skills problem solving", "programming languages c", "other skills",
        "web development", "databases & tools", "developer tools", "computer science", "frameworks",
        "database management", "data structures", "algorithms", "problem solving", "networks",
        "computer networks", "cryptography", "network security", "computer organization",
        "architecture", "operating system", "data structures & algorithms", "web", "framework"
    }
    
    if skill_clean in SKILL_BLACKLIST or any(b == skill_clean for b in SKILL_BLACKLIST):
        return None

    # Exact match check first
    if skill_clean in CANONICAL_SKILLS:
        return CANONICAL_SKILLS[skill_clean]

    # Fuzzy match against the keys of CANONICAL_SKILLS
    keys = list(CANONICAL_SKILLS.keys())
    match = process.extractOne(skill_clean, keys, scorer=fuzz.token_sort_ratio)
    
    if match and match[1] >= 85:
        return CANONICAL_SKILLS[match[0]]

    # If no close canonical match, just title case it
    return skill_str.strip()
