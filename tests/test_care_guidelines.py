import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pawpal_system import Pet
from care_guidelines import load_guidelines, retrieve_guidelines


def _make_pet(type="dog", breed="Labrador Retriever", age=4, activityLevel="high"):
    return Pet(
        petId="1",
        name="Test Pet",
        type=type,
        breed=breed,
        age=age,
        healthInfo="",
        activityLevel=activityLevel,
    )


def test_load_guidelines_is_well_formed():
    """Every KB entry should have the required keys and non-empty category/species."""
    entries = load_guidelines()
    assert len(entries) > 0
    required_keys = {
        "id", "category", "species", "breeds", "activity_levels",
        "age_range", "guidance", "suggested_duration_minutes",
        "suggested_frequency", "priority_hint",
    }
    for entry in entries:
        assert required_keys.issubset(entry.keys())
        assert entry["category"]
        assert len(entry["species"]) > 0
    print("[PASS] test_load_guidelines_is_well_formed passed")


def test_retrieve_guidelines_ranks_breed_specific_first():
    """A high-activity Labrador should get breed-specific entries ranked ahead
    of generic ones."""
    pet = _make_pet(breed="Labrador Retriever", activityLevel="high", age=4)
    results = retrieve_guidelines(pet)
    result_ids = [r["id"] for r in results]

    assert "ex-high-working-01" in result_ids
    assert "health-labrador-01" in result_ids

    # Breed-specific entries should rank ahead of any generic exercise entry present
    if "ex-generic-medium-01" in result_ids:
        assert result_ids.index("ex-high-working-01") < result_ids.index("ex-generic-medium-01")
    print("[PASS] test_retrieve_guidelines_ranks_breed_specific_first passed")


def test_retrieve_guidelines_falls_back_to_generic_for_unknown_breed():
    """A medium-activity dog of an unknown breed should still get non-empty
    generic results rather than nothing."""
    pet = _make_pet(breed="Mixed Breed", activityLevel="medium", age=3)
    results = retrieve_guidelines(pet)
    result_ids = [r["id"] for r in results]

    assert len(results) > 0
    assert "ex-generic-medium-01" in result_ids
    assert "health-labrador-01" not in result_ids
    print("[PASS] test_retrieve_guidelines_falls_back_to_generic_for_unknown_breed passed")


def test_retrieve_guidelines_filters_by_species():
    """A cat should never receive a dog-only breed-specific entry."""
    pet = _make_pet(type="cat", breed="Domestic Shorthair", activityLevel="medium", age=3)
    results = retrieve_guidelines(pet)
    result_ids = [r["id"] for r in results]

    assert "health-labrador-01" not in result_ids
    assert "ex-high-working-01" not in result_ids
    assert "cat-enrichment-01" in result_ids
    print("[PASS] test_retrieve_guidelines_filters_by_species passed")
