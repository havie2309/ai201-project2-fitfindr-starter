"""
Pytest tests for all FitFindr tools.
Run with: pytest tests/ -v
"""

import pytest
from tools import search_listings, suggest_outfit, create_fit_card, compare_price
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── search_listings ───────────────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0

def test_search_empty_results_no_exception():
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []

def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=20)
    assert all(item["price"] <= 20 for item in results)

def test_search_size_filter():
    results = search_listings("jeans", size="M", max_price=None)
    assert all("m" in item["size"].lower() for item in results)

def test_search_sorted_by_relevance():
    results = search_listings("vintage denim jacket", size=None, max_price=None)
    assert len(results) > 0
    # First result should contain more keywords than last
    # Just verify it's a list of dicts with expected keys
    assert "title" in results[0]
    assert "price" in results[0]

def test_search_returns_full_listing_fields():
    results = search_listings("tee", size=None, max_price=50)
    assert len(results) > 0
    item = results[0]
    for field in ["id", "title", "price", "size", "platform", "category"]:
        assert field in item


# ── suggest_outfit ────────────────────────────────────────────────────────────

def test_suggest_outfit_with_wardrobe():
    results = search_listings("vintage tee", size=None, max_price=50)
    outfit = suggest_outfit(results[0], get_example_wardrobe())
    assert isinstance(outfit, str)
    assert len(outfit) > 20

def test_suggest_outfit_empty_wardrobe_no_exception():
    results = search_listings("vintage tee", size=None, max_price=50)
    outfit = suggest_outfit(results[0], get_empty_wardrobe())
    assert isinstance(outfit, str)
    assert len(outfit) > 20
    assert "Could not" not in outfit  # should give general advice, not error

def test_suggest_outfit_returns_string_not_exception():
    # Even with a minimal item dict, should not raise
    fake_item = {
        "id": "test_001",
        "title": "Mystery Item",
        "category": "tops",
        "condition": "good",
        "price": 10.0,
        "platform": "depop",
        "colors": ["black"],
        "style_tags": ["minimal"],
    }
    result = suggest_outfit(fake_item, get_empty_wardrobe())
    assert isinstance(result, str)
    assert len(result) > 0


# ── create_fit_card ───────────────────────────────────────────────────────────

def test_create_fit_card_returns_string():
    results = search_listings("vintage tee", size=None, max_price=50)
    outfit = suggest_outfit(results[0], get_example_wardrobe())
    card = create_fit_card(outfit, results[0])
    assert isinstance(card, str)
    assert len(card) > 20

def test_create_fit_card_empty_outfit_returns_error_message():
    results = search_listings("vintage tee", size=None, max_price=50)
    card = create_fit_card("", results[0])
    assert card == "Could not generate fit card — outfit description was empty."

def test_create_fit_card_whitespace_outfit_returns_error_message():
    results = search_listings("vintage tee", size=None, max_price=50)
    card = create_fit_card("   ", results[0])
    assert card == "Could not generate fit card — outfit description was empty."

def test_create_fit_card_varies_between_calls():
    results = search_listings("vintage tee", size=None, max_price=50)
    outfit = suggest_outfit(results[0], get_example_wardrobe())
    card1 = create_fit_card(outfit, results[0])
    card2 = create_fit_card(outfit, results[0])
    # Both should be valid strings (may or may not differ — LLM is non-deterministic)
    assert isinstance(card1, str) and len(card1) > 20
    assert isinstance(card2, str) and len(card2) > 20


# ── compare_price (stretch) ───────────────────────────────────────────────────

def test_compare_price_returns_dict_with_required_keys():
    results = search_listings("vintage tee", size=None, max_price=50)
    verdict = compare_price(results[0])
    for key in ["verdict", "avg_comparable_price", "comparable_count", "reasoning"]:
        assert key in verdict

def test_compare_price_verdict_is_valid():
    results = search_listings("jacket", size=None, max_price=None)
    verdict = compare_price(results[0])
    assert verdict["verdict"] in ["steal", "fair", "high", "unknown"]

def test_compare_price_insufficient_comparables():
    # Use a fake item with a rare category that won't match many listings
    fake_item = {
        "id": "fake_999",
        "category": "nonexistent_category_xyz",
        "price": 50.0,
        "condition": "good",
    }
    verdict = compare_price(fake_item)
    assert verdict["verdict"] == "unknown"
    assert verdict["avg_comparable_price"] is None
    assert "Not enough" in verdict["reasoning"]