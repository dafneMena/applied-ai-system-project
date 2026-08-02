"""Retrieval over the local pet care knowledge base (RAG half of the AI Care Assistant).

No LLM/network dependency lives here on purpose - this module stays pure and
independently testable so retrieval quality can be verified without any API access.
"""
import json
from functools import lru_cache
from pathlib import Path

DEFAULT_KB_PATH = Path(__file__).parent / "data" / "breed_guidelines.json"


@lru_cache(maxsize=1)
def load_guidelines(path: str = None) -> list:
    """Load and cache the knowledge base JSON. Raises FileNotFoundError /
    json.JSONDecodeError unmodified if the file is missing or malformed."""
    kb_path = Path(path) if path else DEFAULT_KB_PATH
    with open(kb_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["guidelines"]


def _matches(entry: dict, pet_type: str, breed: str, activity_level: str, age: int) -> bool:
    """Species is a required match. breeds/activity_levels/age_range are optional
    filters - an empty list or null on the entry means 'no restriction' and always passes."""
    if pet_type.lower() not in [s.lower() for s in entry["species"]]:
        return False

    if entry["breeds"] and breed.lower() not in [b.lower() for b in entry["breeds"]]:
        return False

    if entry["activity_levels"] and activity_level.lower() not in [
        a.lower() for a in entry["activity_levels"]
    ]:
        return False

    age_range = entry["age_range"]
    if age_range is not None:
        low, high = age_range
        if not (low <= age <= high):
            return False

    return True


def _specificity(entry: dict) -> int:
    """Score how specific an entry's match filters are - higher means more
    tailored to this exact pet, so it should rank ahead of generic entries."""
    score = 0
    if entry["breeds"]:
        score += 2
    if entry["activity_levels"]:
        score += 1
    if entry["age_range"] is not None:
        score += 1
    return score


def retrieve_guidelines(pet, top_k: int = 6) -> list:
    """Return up to top_k guideline entries relevant to the given Pet, most
    specific (breed/activity/age-matched) first. Ties broken by id for
    deterministic ordering."""
    entries = load_guidelines()
    matched = [
        entry
        for entry in entries
        if _matches(entry, pet.type, pet.breed, pet.activityLevel, pet.age)
    ]
    matched.sort(key=lambda e: (-_specificity(e), e["id"]))
    return matched[:top_k]
