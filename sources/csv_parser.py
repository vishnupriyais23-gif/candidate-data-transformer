import pandas as pd
import numpy as np
from typing import List, Dict, Any

def parse_csv(file_path: str) -> List[Dict[str, Any]]:
    """
    Parses recruiter CSV using pandas.
    Handles encoding fallback (utf-8 -> latin-1).
    Strips whitespace and converts empty values to None.
    """
    try:
        df = pd.read_csv(file_path, encoding="utf-8")
    except UnicodeDecodeError:
        df = pd.read_csv(file_path, encoding="latin-1")
    except Exception as e:
        raise ValueError(f"Failed to read CSV file {file_path}: {str(e)}")

    # Clean the dataframe: strip whitespace from strings, replace NaN with None
    df = df.map(lambda x: x.strip() if isinstance(x, str) else x)
    df = df.replace({np.nan: None})

    candidates = []
    for _, row in df.iterrows():
        # Skip empty rows silently
        if all(val is None or str(val).strip() == "" for val in row.values):
            continue
            
        candidate = {}
        
        # Extract name
        name = row.get("name")
        candidate["full_name"] = name if name else None

        # Extract emails
        email = row.get("email")
        candidate["emails"] = [email] if email else []

        # Extract phones
        phone = row.get("phone")
        candidate["phones"] = [phone] if phone else []

        # Map current_company and title to an experience entry
        current_company = row.get("current_company")
        title = row.get("title")
        
        experience = []
        if current_company or title:
            experience.append({
                "company": current_company if current_company else "Unknown",
                "title": title if title else "Unknown",
                "start": None,
                "end": None,
                "summary": "Current role from recruiter CSV"
            })
        candidate["experience"] = experience

        # Initialize empty fields for consistency
        candidate["location"] = {"city": None, "region": None, "country": None}
        candidate["links"] = {"linkedin": None, "github": None, "portfolio": None, "other": []}
        candidate["headline"] = None
        candidate["years_experience"] = None
        candidate["skills"] = []
        candidate["education"] = []

        candidates.append(candidate)

    return candidates
