import requests
from typing import Dict, List, Optional

OPENFDA_LABEL_URL = "https://api.fda.gov/drug/label.json"


def lookup_drug_info(drug_name: str) -> Optional[Dict]:
    """
    Looks up a medication's factual identity info (active ingredient,
    purpose) from the FDA's official public drug label database. This is
    kept separate from LLM generation entirely — it's a database lookup,
    not something the model invents — so ingredient info can never be
    hallucinated.
    """
    query = f'openfda.brand_name:"{drug_name}" OR openfda.generic_name:"{drug_name}" OR openfda.substance_name:"{drug_name}"'

    try:
        response = requests.get(
            OPENFDA_LABEL_URL,
            params={"search": query, "limit": 1},
            timeout=8
        )
        response.raise_for_status()
        data = response.json()
    except Exception:
        return None

    results = data.get("results")
    if not results:
        return None

    entry = results[0]
    openfda = entry.get("openfda", {})

    return {
        "matched_name": drug_name,
        "brand_names": openfda.get("brand_name", []),
        "generic_names": openfda.get("generic_name", []),
        "active_ingredients": openfda.get("substance_name", []),
        "purpose": _first_or_none(entry.get("purpose")) or _first_or_none(entry.get("indications_and_usage")),
        "drug_class": openfda.get("pharm_class_epc", []) or openfda.get("pharm_class_cs", []),
    }


def _first_or_none(field_list):
    if isinstance(field_list, list) and field_list:
        return field_list[0][:400]
    return None


def lookup_multiple_drugs(drug_names: List[str]) -> List[Dict]:
    """
    Looks up multiple drug names, marking any with no database match as
    not_found rather than guessing.
    """
    results = []
    for name in drug_names:
        info = lookup_drug_info(name)
        results.append(info if info else {"matched_name": name, "not_found": True})
    return results