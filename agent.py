"""
The FitFindr planning loop. Orchestrates tools in response to a natural
language user query, passing state between them via a session dict.
"""

import re

from tools import search_listings, suggest_outfit, create_fit_card, compare_price


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    return {
        "query": query,
        "parsed": {},
        "search_results": [],
        "selected_item": None,
        "wardrobe": wardrobe,
        "outfit_suggestion": None,
        "price_verdict": None,
        "fit_card": None,
        "error": None,
    }


# ── query parser ──────────────────────────────────────────────────────────────

def _parse_query(query: str) -> dict:
    """
    Extract description, size, and max_price from a natural language query
    using regex. No LLM needed — keeps the agent fast and testable.

    Returns dict with keys: description (str), size (str|None), max_price (float|None)
    """
    # Extract max price — matches "$30", "under $30", "under 30", "30 dollars"
    price_match = re.search(
        r'(?:under|below|less than|max|up to)?\s*\$?(\d+(?:\.\d+)?)\s*(?:dollars?|usd)?',
        query, re.IGNORECASE
    )
    max_price = float(price_match.group(1)) if price_match else None

    # Extract size — common clothing sizes
    size_match = re.search(
        r'\b(XXS|XS|S/M|M/L|L/XL|XL/XXL|XXL|XL|XS|[SML]|'
        r'W\d{2}\s*L?\d{0,2}|\d{1,2}[WR]?|\d{2}x\d{2})\b',
        query, re.IGNORECASE
    )
    size = size_match.group(1).upper() if size_match else None

    # Description: remove price and size fragments, clean up
    description = query
    if price_match:
        description = description[:price_match.start()] + description[price_match.end():]
    if size_match:
        description = description[:size_match.start()] + description[size_match.end():]

    # Remove filler words
    for filler in ["under", "below", "less than", "max", "up to", "size", "i'm looking for",
                   "looking for", "i want", "find me", "i need", "can you find"]:
        description = re.sub(filler, "", description, flags=re.IGNORECASE)

    description = re.sub(r'\s+', ' ', description).strip(" ,.")
    if not description:
        description = query  # fallback to full query

    return {
        "description": description,
        "size": size,
        "max_price": max_price,
    }


# ── retry with loosened constraints (stretch) ─────────────────────────────────

def _search_with_retry(parsed: dict) -> tuple[list, bool]:
    """
    Try search with full constraints first. If empty, retry without size filter.
    Returns (results, was_retried).
    """
    results = search_listings(
        parsed["description"],
        size=parsed["size"],
        max_price=parsed["max_price"],
    )

    if results or parsed["size"] is None:
        return results, False

    # Retry without size filter
    results = search_listings(
        parsed["description"],
        size=None,
        max_price=parsed["max_price"],
    )
    return results, True


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop and returns
    the completed session dict.

    Args:
        query:    Natural language user request
        wardrobe: User's wardrobe dict

    Returns:
        Session dict. Check session["error"] first — if not None, the
        interaction ended early and outfit_suggestion/fit_card will be None.
    """
    # Step 1: Initialize session
    session = _new_session(query, wardrobe)

    # Step 2: Parse the query
    parsed = _parse_query(query)
    session["parsed"] = parsed

    # Step 3: Search listings (with retry fallback for stretch feature)
    results, was_retried = _search_with_retry(parsed)
    session["search_results"] = results

    if not results:
        # Build a helpful error message based on what constraints were applied
        msg_parts = ["No listings matched your search."]
        if parsed["size"]:
            msg_parts.append(f"Size '{parsed['size']}' was not found even after retrying without it.")
        if parsed["max_price"]:
            msg_parts.append(f"Try raising your budget above ${parsed['max_price']:.0f}.")
        msg_parts.append("You can also try broader keywords.")
        session["error"] = " ".join(msg_parts)
        return session

    if was_retried:
        session["retry_note"] = (
            f"No results found for size '{parsed['size']}', "
            f"so I removed the size filter and found {len(results)} item(s). "
            "Results may not match your size exactly."
        )

    # Step 4: Select top result
    session["selected_item"] = results[0]

    # Step 5: Suggest outfit
    outfit = suggest_outfit(session["selected_item"], wardrobe)
    if outfit.startswith("Could not"):
        session["error"] = outfit
        return session
    session["outfit_suggestion"] = outfit

    # Step 6: Compare price (stretch)
    session["price_verdict"] = compare_price(session["selected_item"])

    # Step 7: Create fit card
    fit_card = create_fit_card(session["outfit_suggestion"], session["selected_item"])
    if fit_card.startswith("Could not"):
        session["error"] = fit_card
        return session
    session["fit_card"] = fit_card

    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found:    {session['selected_item']['title']} — ${session['selected_item']['price']}")
        print(f"\nOutfit:   {session['outfit_suggestion']}")
        print(f"\nPrice:    {session['price_verdict']['verdict'].upper()} — {session['price_verdict']['reasoning']}")
        print(f"\nFit card: {session['fit_card']}")
        if session.get("retry_note"):
            print(f"\nRetry note: {session['retry_note']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error: {session2['error']}")

    print("\n\n=== Retry path: obscure size ===\n")
    session3 = run_agent(
        query="vintage denim jacket size XXL under $60",
        wardrobe=get_example_wardrobe(),
    )
    if session3.get("retry_note"):
        print(f"Retry note: {session3['retry_note']}")
    if session3["error"]:
        print(f"Error: {session3['error']}")
    else:
        print(f"Found: {session3['selected_item']['title']}")
        print(f"Fit card: {session3['fit_card']}")