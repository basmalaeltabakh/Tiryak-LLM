from typing import Dict, List
from app.advanced.egypt_drug_database import search_egyptian_drug
from app.advanced.drug_database import lookup_drug_info as lookup_fda


def lookup_drug(name: str) -> Dict:
    """
    Tries the Egyptian drug database first (since this app targets the
    Egyptian market), and falls back to the FDA database for foreign/
    international products not found locally. Never guesses — if neither
    source has a match, it's reported honestly as not found.
    """
    egypt_matches = search_egyptian_drug(name, max_results=1)
    if egypt_matches:
        row = egypt_matches[0]
        return {
            "matched_name": name,
            "source": "egypt",
            "commercial_name_en": row.get("commercial_name_en"),
            "commercial_name_ar": row.get("commercial_name_ar"),
            "active_ingredients": row.get("scientific_name"),
            "manufacturer": row.get("manufacturer"),
            "drug_class": row.get("drug_class"),
            "route": row.get("route"),
            "price_egp": row.get("price_egp"),
        }

    fda_result = lookup_fda(name)
    if fda_result:
        return {
            "matched_name": name,
            "source": "fda",
            "commercial_name_en": fda_result.get("brand_names", [name])[0] if fda_result.get("brand_names") else name,
            "commercial_name_ar": None,
            "active_ingredients": ", ".join(fda_result.get("active_ingredients", [])) or None,
            "manufacturer": None,
            "drug_class": ", ".join(fda_result.get("drug_class", [])) or None,
            "route": None,
            "price_egp": None,
            "purpose": fda_result.get("purpose"),
        }

    return {"matched_name": name, "source": None, "not_found": True}


def lookup_multiple_drugs(drug_names: List[str]) -> List[Dict]:
    return [lookup_drug(name) for name in drug_names]