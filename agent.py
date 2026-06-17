"""
The FitFindr planning loop.
"""

import re

from tools import (
    search_listings,
    suggest_outfit,
    create_fit_card,
    compare_price,
    load_style_profile,
    update_style_profile,
)


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
        "retry_note": None,
        "style_profile": None,
    }


# ── query parser ──────────────────────────────────────────────────────────────

def _parse_query(query: str) -> dict:
    price_match = re.search(
        r'(?:under|below|less than|max|up to)?\s*\$?(\d+(?:\.\d+)?)\s*(?:dollars?|usd)?',
        query, re.IGNORECASE
    )
    max_price = float(price_match.group(1)) if price_match else None

    size_match = re.search(
        r'\b(XXS|XS|S/M|M/L|L/XL|XL/XXL|XXL|XL|XS|[SML]|'
        r'W\d{2}\s*L?\d{0,2}|\d{1,2}[WR]?|\d{2}x\d{2})\b',
        query, re.IGNORECASE
    )
    size = size_match.group(1).upper() if size_match else None

    description = query
    if price_match:
        description = description[:price_match.start()] + description[price_match.end():]
    if size_match:
        description = description[:size_match.start()] + description[size_match.end():]

    for filler in ["under", "below", "less than", "max", "up to", "size",
                   "i'm looking for", "looking for", "i want", "find me",
                   "i need", "can you find"]:
        description = re.sub(filler, "", description, flags=re.IGNORECASE)

    description = re.sub(r'\s+', ' ', description).strip(" ,.")
    if not description:
        description = query

    return {"description": description, "size": size, "max_price": max_price}


# ── retry with loosened constraints (stretch) ─────────────────────────────────

def _search_with_retry(parsed: dict) -> tuple[list, bool]:
    results = search_listings(
        parsed["description"],
        size=parsed["size"],
        max_price=parsed["max_price"],
    )
    if results or parsed["size"] is None:
        return results, False

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
        query (str): Natural language user request.
        wardrobe (dict): User's wardrobe dict.

    Returns:
        dict: Session dict. Check session["error"] first — if not None,
        the interaction ended early and outfit_suggestion/fit_card are None.
    """
    # Step 1: Initialize session
    session = _new_session(query, wardrobe)

    # Step 2: Load style profile from disk
    profile = load_style_profile()
    session["style_profile"] = profile
    update_style_profile(session["selected_item"], outfit)


    # Step 3: Parse query
    parsed = _parse_query(query)
    session["parsed"] = parsed

    # Step 4: Search with retry fallback
    results, was_retried = _search_with_retry(parsed)
    session["search_results"] = results

    if not results:
        msg_parts = ["No listings matched your search."]
        if parsed["size"]:
            msg_parts.append(
                f"Size '{parsed['size']}' was not found even after retrying without it."
            )
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

    # Step 5: Select top result
    session["selected_item"] = results[0]

    # Step 6: Suggest outfit — pass style profile for memory-aware suggestions
    outfit = suggest_outfit(session["selected_item"], wardrobe, profile)
    if outfit.startswith("Could not"):
        session["error"] = outfit
        return session
    session["outfit_suggestion"] = outfit

    # Step 7: Compare price (stretch)
    session["price_verdict"] = compare_price(session["selected_item"])

    # Step 8: Create fit card
    fit_card = create_fit_card(session["outfit_suggestion"], session["selected_item"])
    if fit_card.startswith("Could not"):
        session["error"] = fit_card
        return session
    session["fit_card"] = fit_card

    # Step 9: Update style profile with this interaction
    update_style_profile(session["selected_item"], outfit)

    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe
    import json

    print("=== Session 1: graphic tee ===\n")
    s1 = run_agent("vintage graphic tee under $30", get_example_wardrobe())
    if s1["error"]:
        print(f"Error: {s1['error']}")
    else:
        print(f"Found: {s1['selected_item']['title']}")
        print(f"Outfit: {s1['outfit_suggestion']}")
        print(f"Fit card: {s1['fit_card']}")
        print(f"Profile after session 1:")
        print(json.dumps(load_style_profile(), indent=2))

    print("\n\n=== Session 2: skirt (should use saved preferences) ===\n")
    s2 = run_agent("flowy midi skirt under $40", get_example_wardrobe())
    if s2["error"]:
        print(f"Error: {s2['error']}")
    else:
        print(f"Found: {s2['selected_item']['title']}")
        print(f"Outfit (memory-aware): {s2['outfit_suggestion']}")

    print("\n\n=== No-results path ===\n")
    s3 = run_agent("designer ballgown size XXS under $5", get_example_wardrobe())
    print(f"Error: {s3['error']}")

    print("\n\n=== Retry path ===\n")
    s4 = run_agent("vintage denim jacket size XXL under $60", get_example_wardrobe())
    if s4.get("retry_note"):
        print(f"Retry: {s4['retry_note']}")
    if not s4["error"]:
        print(f"Found: {s4['selected_item']['title']}")