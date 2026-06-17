"""
The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
    compare_price(item)                             → dict  [stretch]
"""

import os

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for.
        size:        Size string to filter by, or None to skip size filtering.
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts sorted by relevance (best match first).
        Returns [] if nothing matches — does NOT raise an exception.
    """
    try:
        listings = load_listings()
        keywords = [kw.strip().lower() for kw in description.split() if kw.strip()]

        filtered = []
        for item in listings:
            # Price filter
            if max_price is not None and item["price"] > max_price:
                continue

            # Size filter (case-insensitive substring match)
            if size is not None:
                if size.strip().lower() not in item["size"].lower():
                    continue

            # Keyword scoring — search across multiple text fields
            searchable = " ".join([
                item.get("title", ""),
                item.get("description", ""),
                item.get("category", ""),
                item.get("brand", "") or "",
                item.get("platform", ""),
                " ".join(item.get("style_tags", [])),
                " ".join(item.get("colors", [])),
            ]).lower()

            score = sum(1 for kw in keywords if kw in searchable)

            if score > 0:
                filtered.append((score, item))

        # Sort by score descending, return just the dicts
        filtered.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in filtered]

    except Exception as e:
        print(f"[search_listings error] {e}")
        return []


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key. May be empty.

    Returns:
        A non-empty string with outfit suggestions, or an error message string.
        Never raises an exception.
    """
    try:
        client = _get_groq_client()
        wardrobe_items = wardrobe.get("items", [])

        item_description = (
            f"{new_item.get('title', 'Unknown item')} "
            f"({new_item.get('category', '')}, {new_item.get('condition', '')} condition, "
            f"${new_item.get('price', '?')}, from {new_item.get('platform', '?')}). "
            f"Colors: {', '.join(new_item.get('colors', []))}. "
            f"Style: {', '.join(new_item.get('style_tags', []))}."
        )

        if not wardrobe_items:
            prompt = (
                f"A user is considering buying this secondhand item: {item_description}\n\n"
                "They haven't shared their wardrobe yet. Give them 2 concrete outfit ideas "
                "for this piece — suggest the types of items it pairs well with (bottoms, shoes, "
                "outerwear), what vibe each outfit would have, and one specific styling tip. "
                "Be specific and conversational, not generic. 3–5 sentences total."
            )
        else:
            wardrobe_text = "\n".join([
                f"- {w['name']} ({w['category']}, colors: {', '.join(w.get('colors', []))}"
                f"{', notes: ' + w['notes'] if w.get('notes') else ''})"
                for w in wardrobe_items
            ])
            prompt = (
                f"A user is considering buying this secondhand item: {item_description}\n\n"
                f"Their current wardrobe includes:\n{wardrobe_text}\n\n"
                "Suggest 1–2 complete outfit combinations using the new item and specific pieces "
                "from their wardrobe above. Name the exact wardrobe pieces. Describe the vibe of "
                "each outfit and give one styling tip (tucking, layering, accessories, etc.). "
                "Be specific and conversational. 3–5 sentences total."
            )

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=300,
        )
        result = response.choices[0].message.content.strip()
        return result if result else "Could not generate outfit suggestion. Please try again."

    except Exception as e:
        print(f"[suggest_outfit error] {e}")
        return "Could not generate outfit suggestion. Please try again."


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–3 sentence Instagram/TikTok-style caption string.
        Returns an error message string if outfit is empty — never raises.
    """
    if not outfit or not outfit.strip():
        return "Could not generate fit card — outfit description was empty."

    try:
        client = _get_groq_client()

        title = new_item.get("title", "this piece")
        price = new_item.get("price", "?")
        platform = new_item.get("platform", "a thrift app")
        style_tags = ", ".join(new_item.get("style_tags", []))

        prompt = (
            f"Write a 2–3 sentence Instagram caption for a thrift find. "
            f"The item is: {title}, bought for ${price} on {platform}. "
            f"Style vibe: {style_tags}. "
            f"The outfit: {outfit}\n\n"
            "Rules:\n"
            "- Write in casual first-person (like a real person posting, not a brand)\n"
            "- Mention the item, price, and platform naturally (once each)\n"
            "- Capture the specific vibe of the outfit\n"
            "- Add 1–2 relevant emojis\n"
            "- Do NOT use hashtags\n"
            "- Sound like something worth sharing, not a product description\n"
            "Return only the caption text, nothing else."
        )

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=1.1,
            max_tokens=150,
        )
        result = response.choices[0].message.content.strip()
        return result if result else "Could not generate fit card. Please try again."

    except Exception as e:
        print(f"[create_fit_card error] {e}")
        return "Could not generate fit card. Please try again."


# ── Tool 4 (Stretch): compare_price ──────────────────────────────────────────

def compare_price(item: dict) -> dict:
    """
    Compare an item's price against similar listings in the dataset.

    Args:
        item: A listing dict with at least 'category', 'price', and 'condition'.

    Returns:
        A dict with keys:
            verdict (str): "steal", "fair", "high", or "unknown"
            avg_comparable_price (float or None): average price of comparable items
            comparable_count (int): number of items used for comparison
            reasoning (str): human-readable explanation
        Never raises an exception.
    """
    try:
        listings = load_listings()
        category = item.get("category", "").lower()
        price = item.get("price", 0)
        item_id = item.get("id", "")

        # Find comparable items: same category, exclude the item itself
        comparables = [
            l for l in listings
            if l.get("category", "").lower() == category
            and l.get("id") != item_id
        ]

        if len(comparables) < 2:
            return {
                "verdict": "unknown",
                "avg_comparable_price": None,
                "comparable_count": len(comparables),
                "reasoning": "Not enough comparable listings to assess price.",
            }

        avg_price = sum(l["price"] for l in comparables) / len(comparables)
        diff = price - avg_price
        pct = (diff / avg_price) * 100

        if pct <= -20:
            verdict = "steal"
        elif pct >= 20:
            verdict = "high"
        else:
            verdict = "fair"

        reasoning = (
            f"At ${price:.2f}, this is ${abs(diff):.2f} "
            f"{'below' if diff < 0 else 'above'} the average ${avg_price:.2f} "
            f"for {category} in the dataset ({len(comparables)} comparable listings)."
        )

        return {
            "verdict": verdict,
            "avg_comparable_price": round(avg_price, 2),
            "comparable_count": len(comparables),
            "reasoning": reasoning,
        }

    except Exception as e:
        print(f"[compare_price error] {e}")
        return {
            "verdict": "unknown",
            "avg_comparable_price": None,
            "comparable_count": 0,
            "reasoning": "Price comparison failed unexpectedly.",
        }