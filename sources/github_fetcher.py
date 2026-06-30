import os
import re
import sys
import requests
from typing import Dict, Any, Optional, Tuple, List
from urllib.parse import urlparse
from core.normalizer import normalize_skill, normalize_country

def extract_username(github_url_or_username: str) -> str:
    """Extracts username from a GitHub URL or cleans a bare username string."""
    if not github_url_or_username:
        return ""
    val = github_url_or_username.strip()
    
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
        
    return val.strip()

def fetch_github_profile(github_url_or_username: str, errors_dict: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """
    Fetches candidate details from GitHub (profile and repositories).
    Handles 404, rate limits (403), and timeouts (5s) gracefully.
    Returns a dictionary with null/empty fields and records errors if fetch fails.
    """
    username = extract_username(github_url_or_username)
    
    candidate = {
        "full_name": None,
        "emails": [],
        "phones": [],
        "location": {"city": None, "region": None, "country": None},
        "links": {
            "linkedin": None, 
            "github": f"https://github.com/{username}" if username else None, 
            "portfolio": None, 
            "other": []
        },
        "headline": None,
        "years_experience": None,
        "skills": [],
        "experience": [],
        "education": []
    }

    # Empty username -> skip fetch entirely
    if not username:
        return candidate

    headers = {}
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"token {token}"

    user_url = f"https://api.github.com/users/{username}"
    repos_url = f"https://api.github.com/users/{username}/repos?sort=updated&per_page=10"

    try:
        # Fetch user profile with strict 5s timeout
        user_response = requests.get(user_url, headers=headers, timeout=5)
        
        if user_response.status_code == 404:
            err_msg = f"GitHub user not found (404): {username}"
            if errors_dict is not None:
                errors_dict["github"] = err_msg
            print(f"[INFO] {err_msg}", file=sys.stderr)
            return candidate
            
        elif user_response.status_code in [403, 429]:
            err_msg = f"GitHub API Forbidden/Rate Limit ({user_response.status_code}) for user: {username}"
            if errors_dict is not None:
                errors_dict["github"] = err_msg
            print(f"[WARNING] {err_msg}", file=sys.stderr)
            return candidate
            
        user_response.raise_for_status()
        user_data = user_response.json()

        # Populate profile fields
        candidate["full_name"] = user_data.get("name")
        if user_data.get("email"):
            candidate["emails"].append(user_data["email"])
        candidate["headline"] = user_data.get("bio")
        
        # Populate github link
        if user_data.get("html_url"):
            candidate["links"]["github"] = user_data["html_url"]
            
        # Parse location
        loc_str = user_data.get("location")
        if loc_str:
            parts = [p.strip() for p in loc_str.split(",") if p.strip()]
            if len(parts) == 1:
                candidate["location"]["city"] = parts[0]
            elif len(parts) >= 2:
                candidate["location"]["city"] = parts[0]
                candidate["location"]["country"] = normalize_country(parts[-1]) or parts[-1]
                if len(parts) == 3:
                    candidate["location"]["region"] = parts[1]

        # Parse blog link (portfolio)
        if user_data.get("blog"):
            blog_url = user_data["blog"]
            if not (blog_url.startswith("http://") or blog_url.startswith("https://")):
                blog_url = f"https://{blog_url}"
            candidate["links"]["portfolio"] = blog_url

        # Fetch repositories with strict 5s timeout
        repos_response = requests.get(repos_url, headers=headers, timeout=5)
        if repos_response.status_code in [403, 429]:
            err_msg = f"GitHub Repos Forbidden/Rate Limit ({repos_response.status_code}) for user: {username}"
            if errors_dict is not None:
                errors_dict["github"] = err_msg
            print(f"[WARNING] {err_msg}", file=sys.stderr)
            return candidate
            
        if repos_response.status_code == 200:
            repos_data = repos_response.json()
            if isinstance(repos_data, list) and len(repos_data) > 0:
                # Count frequency of each language
                lang_counts = {}
                for repo in repos_data:
                    lang = repo.get("language")
                    if lang:
                        # Exclude Jupyter Notebook
                        if lang.lower() == "jupyter notebook":
                            continue
                        norm_lang = normalize_skill(lang)
                        if norm_lang:
                            lang_counts[norm_lang] = lang_counts.get(norm_lang, 0) + 1
                            
                # Scale confidence by frequency and populate skills
                total_repos = len(repos_data)
                github_skills = []
                for skill_name, count in lang_counts.items():
                    freq_ratio = count / total_repos
                    conf = round(min(0.9, 0.5 + 0.4 * freq_ratio), 2)
                    github_skills.append({
                        "name": skill_name,
                        "confidence": conf
                    })
                candidate["skills"] = github_skills
        else:
            print(f"[WARNING] Could not fetch GitHub repos for {username}: HTTP {repos_response.status_code}", file=sys.stderr)

    except requests.exceptions.Timeout:
        err_msg = f"GitHub API timeout (5s) for user: {username}"
        if errors_dict is not None:
            errors_dict["github"] = err_msg
        print(f"[WARNING] {err_msg}", file=sys.stderr)

    except requests.exceptions.RequestException as e:
        err_msg = f"GitHub API connection error for user: {username}: {str(e)}"
        if errors_dict is not None:
            errors_dict["github"] = err_msg
        print(f"[ERROR] {err_msg}", file=sys.stderr)

    return candidate
