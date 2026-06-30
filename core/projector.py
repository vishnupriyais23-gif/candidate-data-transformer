import re
from typing import Dict, Any, List, Optional
from schemas.config_schema import ProjectionConfig, FieldProjection
from core.normalizer import normalize_phone, normalize_skill

def get_value_by_path(obj: Any, path: str) -> Any:
    """
    Resolves a path in a nested dictionary/object.
    Supports:
    - Dot notation: 'location.city'
    - Array indexing: 'emails[0]'
    - Array mapping: 'skills[].name'
    """
    if not path:
        return obj

    parts = path.split(".")
    current = obj

    for i, part in enumerate(parts):
        if current is None:
            return None

        # Check for array mapping: e.g., 'skills[]'
        if part.endswith("[]"):
            array_key = part[:-2]
            if isinstance(current, dict) and array_key in current:
                array_val = current[array_key]
            elif hasattr(current, array_key):
                array_val = getattr(current, array_key)
            else:
                return None

            if not isinstance(array_val, list):
                return None

            # If there are remaining parts, map them over the array elements
            remaining_path = ".".join(parts[i+1:])
            if remaining_path:
                res_list = []
                for item in array_val:
                    val = get_value_by_path(item, remaining_path)
                    if val is not None:
                        res_list.append(val)
                return res_list
            else:
                return array_val

        # Check for array indexing: e.g., 'emails[0]'
        idx_match = re.match(r'^([^\[]+)\[(\d+)\]$', part)
        if idx_match:
            key = idx_match.group(1)
            idx = int(idx_match.group(2)) - 1
            
            if idx < 0:
                return None
            
            if isinstance(current, dict) and key in current:
                val = current[key]
            elif hasattr(current, key):
                val = getattr(current, key)
            else:
                return None

            if isinstance(val, list) and len(val) > idx:
                current = val[idx]
            else:
                return None
        else:
            # Standard field access
            if isinstance(current, dict):
                current = current.get(part)
            elif hasattr(current, part):
                current = getattr(current, part)
            else:
                return None

    return current


def cast_type(value: Any, target_type: str) -> Any:
    """Casts a value to the target type specified in the config."""
    if value is None:
        return None

    try:
        if target_type == "string":
            return str(value)
        elif target_type == "number":
            return float(value) if "." in str(value) else int(value)
        elif target_type == "integer":
            return int(value)
        elif target_type == "boolean":
            return bool(value)
        elif target_type == "string[]":
            if isinstance(value, list):
                return [str(v) for v in value if v is not None]
            return [str(value)]
        elif target_type == "object[]":
            if isinstance(value, list):
                return value
            return [value]
    except Exception:
        pass

    return value


def project_candidate(
    candidate_dict: Dict[str, Any],
    config: ProjectionConfig
) -> Dict[str, Any]:
    """
    Projects a canonical candidate profile dictionary using the runtime configuration.
    Handles on_missing strategies:
      - "error": raises ValueError with the missing field name.
      - "omit": completely removes the field from the output.
      - "null": sets the field to None.
    """
    output = {}

    # Always include candidate_id
    output["candidate_id"] = candidate_dict.get("candidate_id")

    for field_proj in config.fields:
        src_path = field_proj.from_path if field_proj.from_path is not None else field_proj.path
        
        # Extract value
        val = get_value_by_path(candidate_dict, src_path)

        # Apply post-extraction normalization if specified
        if val is not None and field_proj.normalize:
            norm_type = field_proj.normalize.lower()
            if norm_type == "e164":
                if isinstance(val, list):
                    val = [normalize_phone(v) for v in val if normalize_phone(v)]
                else:
                    val = normalize_phone(val)
            elif norm_type == "canonical":
                if isinstance(val, list):
                    val = [normalize_skill(v) for v in val if normalize_skill(v)]
                else:
                    val = normalize_skill(val)

        # Cast to target type
        val = cast_type(val, field_proj.type)

        # Check if the value is missing/empty
        is_missing = val is None or (isinstance(val, list) and len(val) == 0)

        if is_missing:
            # Handle required field missing or on_missing = "error"
            if field_proj.required or config.on_missing == "error":
                raise ValueError(f"Field '{field_proj.path}' is missing or null.")
            
            if config.on_missing == "omit":
                # Do not add the key to the output dictionary at all
                continue
            else:  # "null"
                output[field_proj.path] = None
        else:
            output[field_proj.path] = val

    # Include confidence if configured
    if config.include_confidence:
        output["overall_confidence"] = candidate_dict.get("overall_confidence", 0.0)

    # Include confidence breakdown if configured
    if config.include_confidence_breakdown:
        output["confidence_breakdown"] = candidate_dict.get("confidence_breakdown")

    # Include provenance if configured
    if config.include_provenance:
        output["provenance"] = candidate_dict.get("provenance", [])

    # Add debugging for projection
    canonical_skills = []
    for s in candidate_dict.get("skills", []):
        if isinstance(s, dict):
            canonical_skills.append(s.get("name"))
        elif hasattr(s, "name"):
            canonical_skills.append(s.name)
        else:
            canonical_skills.append(str(s))
            
    projected_skills = output.get("skills", [])
    print(f"\nCanonical skills:\n{canonical_skills}", flush=True)
    print(f"Projected skills:\n{projected_skills}\n", flush=True)

    return output
