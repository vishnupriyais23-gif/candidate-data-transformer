import re
from typing import Dict, Any, List

# Basic regexes
EMAIL_REGEX = re.compile(r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b')
PHONE_REGEX = re.compile(r'\+?\d{1,4}[-.\s]?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}')
YEARS_EXP_REGEX = re.compile(r'\b(\d+(?:\.\d+)?)\s*(?:year|yr)[s]?\s*(?:of\s*)?experience\b', re.IGNORECASE)

CANDIDATE_HEADERS = re.compile(r'\b(?:Candidate Name|Candidate|Name|Applicant)\s*:', re.IGNORECASE)

# Standard skills to scan for (in addition to explicit sections)
COMMON_SKILLS = [
    "Python", "JavaScript", "JS", "TypeScript", "TS", "Go", "Golang", "Java", "C++", "C#",
    "Ruby", "PHP", "HTML", "CSS", "SQL", "NoSQL", "MongoDB", "Mongo", "Postgres", "PostgreSQL",
    "MySQL", "Redis", "Docker", "Kubernetes", "K8s", "AWS", "Azure", "GCP", "Git", "GitHub",
    "React", "Angular", "Vue", "Node", "Node.js", "Django", "Flask", "FastAPI", "Spring",
    "Machine Learning", "ML", "Artificial Intelligence", "AI", "Deep Learning", "DL", "NLP",
    "Data Science", "Pandas", "NumPy", "TensorFlow", "PyTorch", "Spark", "Hadoop", "Express.js",
    "Spring Boot", "Kafka"
]

def parse_notes(file_path: str) -> List[Dict[str, Any]]:
    """
    Parses free-text recruiter notes.
    Supports single or multi-candidate notes files.
    Splits content by candidate headers and separator lines (e.g. '---') to parse each candidate independently.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read()
    except UnicodeDecodeError:
        with open(file_path, "r", encoding="latin-1") as f:
            text = f.read()
    except Exception as e:
        raise ValueError(f"Failed to read notes file {file_path}: {str(e)}")

    if not text.strip():
        return []

    # First split by hyphen lines (e.g. ---)
    raw_blocks = re.split(r'\n-+\n', text)
    blocks = []

    for rb in raw_blocks:
        rb_clean = rb.strip()
        if not rb_clean:
            continue
            
        # Within each block, if there are multiple candidate headers, split them further
        matches = list(CANDIDATE_HEADERS.finditer(rb_clean))
        if not matches:
            blocks.append(rb_clean)
        else:
            first_part = rb_clean[:matches[0].start()].strip()
            if first_part:
                if len(EMAIL_REGEX.findall(first_part)) > 0 or len(PHONE_REGEX.findall(first_part)) > 0:
                    blocks.append(first_part)
            for i in range(len(matches)):
                start_idx = matches[i].start()
                end_idx = matches[i+1].start() if i + 1 < len(matches) else len(rb_clean)
                blocks.append(rb_clean[start_idx:end_idx])

    candidates = []
    for block in blocks:
        block_clean = block.strip()
        if not block_clean:
            continue

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

        # Extract emails and phones restricted to this block
        candidate["emails"] = list(set(EMAIL_REGEX.findall(block_clean)))
        candidate["phones"] = list(set(PHONE_REGEX.findall(block_clean)))

        # Extract name from this block, supporting "Call notes - Name" as well as standard headers
        name_match = re.search(r'\b(?:Call notes\s*-?|Candidate Name|Candidate|Name|Applicant)\s*[:-]?\s*([A-Z][a-zA-Z\s]{1,30})', block_clean, re.IGNORECASE)
        if name_match:
            candidate["full_name"] = name_match.group(1).strip()
        else:
            # Fallback: look at first 3 non-empty lines in the block
            lines = [line.strip() for line in block_clean.split("\n") if line.strip()]
            for line in lines[:3]:
                if "@" in line or any(c in line for c in ["/", "http", "phone:", "email:", "candidate", "name:"]):
                    continue
                if 2 <= len(line.split()) <= 4:
                    candidate["full_name"] = line
                    break

        # Extract years of experience
        exp_match = YEARS_EXP_REGEX.search(block_clean)
        if exp_match:
            candidate["years_experience"] = float(exp_match.group(1))

        # Extract skills
        extracted_skills = []
        skills_match = re.search(r'\b(?:Skills|Keywords|Technologies|Stack)\s*:\s*([^\n]+)', block_clean, re.IGNORECASE)
        if skills_match:
            skills_line = skills_match.group(1)
            for s in re.split(r'[,;\s]+', skills_line):
                s_clean = s.strip().strip(".-*•")
                if s_clean and len(s_clean) < 30:
                    extracted_skills.append(s_clean)

        # Scan for common skills inside the block
        for skill in COMMON_SKILLS:
            if re.search(rf'\b{re.escape(skill)}\b', block_clean, re.IGNORECASE):
                extracted_skills.append(skill)

        candidate["skills"] = list(set(extracted_skills))
        candidates.append(candidate)

    return candidates
