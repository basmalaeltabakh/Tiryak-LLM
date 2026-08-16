import csv
import requests
from pathlib import Path
from typing import List, Dict, Optional
from app.config import BASE_DIR

EGYPT_DRUGS_CSV_URL = "https://raw.githubusercontent.com/karem505/egyptian-drug-database/main/data/egyptian-drugs.csv"
EGYPT_DRUGS_LOCAL_PATH = BASE_DIR / "data" / "egyptian_drugs.csv"

_drug_records: Optional[List[Dict]] = None


def _download_database_if_missing():
    """
    Downloads the open-source Egyptian drug database (CC0 license, 24,868
    records) once and caches it locally, so the app doesn't depend on
    internet access to GitHub during a live demo after the first run.
    """
    if EGYPT_DRUGS_LOCAL_PATH.exists():
        return

    print("[egypt_drug_db] Local copy not found, downloading (one-time, ~3.6MB)...")
    EGYPT_DRUGS_LOCAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    response = requests.get(EGYPT_DRUGS_CSV_URL, timeout=30)
    response.raise_for_status()
    EGYPT_DRUGS_LOCAL_PATH.write_bytes(response.content)
    print(f"[egypt_drug_db] Downloaded and cached at {EGYPT_DRUGS_LOCAL_PATH}")


def preload_egyptian_drug_database():
    """Called once at FastAPI startup so the first user request isn't slow."""
    _load_database()


def _load_database() -> List[Dict]:
    global _drug_records
    if _drug_records is not None:
        return _drug_records

    _download_database_if_missing()

    records = []
    with open(EGYPT_DRUGS_LOCAL_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(row)

    _drug_records = records
    print(f"[egypt_drug_db] Loaded {len(records)} Egyptian drug records into memory.")
    return records


def search_egyptian_drug(name: str, max_results: int = 3) -> List[Dict]:
    """
    Case-insensitive substring search across the English trade name,
    Arabic trade-name alias, and active-ingredient (scientific) name.
    Returns the closest matches, preferring the shortest matching name
    first (to favor the base product over unusual pack-size variants)
    rather than picking a single guessed "best" answer silently.
    """
    if not name or not name.strip():
        return []

    records = _load_database()
    query = name.strip().lower()

    matches = []
    for row in records:
        en = (row.get("commercial_name_en") or "").lower()
        ar = (row.get("commercial_name_ar") or "").lower()
        sci = (row.get("scientific_name") or "").lower()
        if query in en or query in ar or query in sci:
            matches.append(row)

    matches.sort(key=lambda r: len(r.get("commercial_name_en") or ""))
    return matches[:max_results]