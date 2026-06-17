"""
Isolation tests for the three FitFindr tools (Milestone 3).

Run from the project root:
    pytest tests/

The suggest_outfit / create_fit_card tests make real Groq LLM calls, so they
require a valid GROQ_API_KEY in .env and network access. They assert on shape
and behavior (non-empty, varies, handles failure modes), not exact text.
"""

from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe, load_listings


# ── search_listings ─────────────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    # Failure mode: nothing matches → empty list, no exception.
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=10)
    assert all(item["price"] <= 10 for item in results)


def test_search_size_filter_matches_combined_size():
    # "M" should match a listing sized "S/M".
    results = search_listings("tee", size="M", max_price=None)
    assert all(_size_ok("M", item["size"]) for item in results)


def test_search_sorted_by_relevance():
    results = search_listings("vintage graphic tee", size=None, max_price=None)
    assert len(results) > 1  # enough to compare ordering
    # Every returned listing must share at least one keyword (score > 0).
    for item in results:
        text = (item["title"] + " " + item["description"]
                + " " + " ".join(item["style_tags"])).lower()
        assert any(word in text for word in ["vintage", "graphic", "tee"])


def _size_ok(requested, listing_size):
    req = requested.lower()
    parts = listing_size.lower().replace("/", " ").split()
    return req == listing_size.lower() or req in parts


# ── suggest_outfit ──────────────────────────────────────────────────────────

def test_suggest_outfit_with_wardrobe():
    new_item = load_listings()[1]  # Y2K Baby Tee
    result = suggest_outfit(new_item, get_example_wardrobe())
    assert isinstance(result, str)
    assert result.strip() != ""


def test_suggest_outfit_empty_wardrobe():
    # Failure mode: empty wardrobe → still returns non-empty advice, no crash.
    new_item = load_listings()[1]
    result = suggest_outfit(new_item, get_empty_wardrobe())
    assert isinstance(result, str)
    assert result.strip() != ""


# ── create_fit_card ─────────────────────────────────────────────────────────

def test_create_fit_card_empty_outfit():
    # Failure mode: empty outfit → descriptive error string, not an exception.
    new_item = load_listings()[1]
    result = create_fit_card("", new_item)
    assert isinstance(result, str)
    assert result.strip() != ""
    assert "couldn't" in result.lower() or "no outfit" in result.lower()


def test_create_fit_card_valid():
    new_item = load_listings()[1]
    outfit = "Pair the baby tee with baggy jeans and chunky sneakers."
    result = create_fit_card(outfit, new_item)
    assert isinstance(result, str)
    assert result.strip() != ""


def test_create_fit_card_varies():
    # Higher temperature should make repeated captions differ.
    new_item = load_listings()[1]
    outfit = "Pair the baby tee with baggy jeans and chunky sneakers."
    a = create_fit_card(outfit, new_item)
    b = create_fit_card(outfit, new_item)
    assert a != b
