# FitFindr — Project Planning

## A Complete Interaction

FitFindr is a multi-tool AI agent that helps users find secondhand clothing and style it. When a user submits a natural language query, the agent extracts search parameters and calls `search_listings` to find matching items from the mock dataset. If results are found, it passes the top result and the user's wardrobe into `suggest_outfit` to get styling advice, then feeds both into `create_fit_card` to generate a shareable caption. If any tool fails or returns nothing useful, the agent communicates the failure clearly and stops rather than passing bad data downstream.

**Example query:** "I'm looking for a vintage graphic tee under $30, size M. I mostly wear baggy jeans and chunky sneakers."

- Step 1: `search_listings("vintage graphic tee", size="M", max_price=30.0)` → returns list of matching listings sorted by relevance. Agent picks `results[0]`: `{"title": "Faded Band Tee", "price": 22.0, "platform": "depop", "condition": "good", ...}`
- Step 2: `suggest_outfit(new_item=results[0], wardrobe=get_example_wardrobe())` → LLM returns: `"Pair this faded band tee with your baggy dark-wash jeans and chunky white sneakers for an effortless 90s streetwear look. Tuck the front slightly for shape."`
- Step 3: `create_fit_card(outfit="Pair this faded band tee...", new_item=results[0])` → LLM returns: `"thrifted this faded band tee off depop for $22 and i'm never taking it off 🖤 baggy jeans + chunky sneakers and we're done here"`
- Error path: If `search_listings` returns `[]`, agent sets `session["error"]` and returns early — `suggest_outfit` and `create_fit_card` are never called.

---

## Tool Specifications

### Tool 1 — search_listings

**What it does:** Filters the mock listings dataset by keyword match, size, and max price. Returns a ranked list of matching items.

**Inputs:**
- `description` (str): keyword(s) to match against title, description, style_tags, category, brand, and colors fields
- `size` (str or None): exact size string to match (e.g. "M", "W30 L30"); if None, size is not filtered
- `max_price` (float or None): upper price bound inclusive; if None, price is not filtered

**Returns:** A list of dicts, each being a full listing object with keys: `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, `platform`. List is sorted by number of keyword matches descending. Returns `[]` if no matches found.

**On failure / empty results:** Returns `[]` without raising an exception. The planning loop checks `if len(results) == 0` and sets `session["error"] = "No listings matched your search. Try broader keywords, a different size, or raise your budget."` then returns the session early without calling downstream tools.

---

### Tool 2 — suggest_outfit

**What it does:** Given a new thrifted item and the user's wardrobe, calls the LLM to suggest one or more complete outfit combinations.

**Inputs:**
- `new_item` (dict): a single listing object (same schema as search_listings output — keys: id, title, description, category, style_tags, size, condition, price, colors, brand, platform)
- `wardrobe` (dict): wardrobe object with key `"items"` containing a list of wardrobe item dicts, each with keys: id, name, category, colors, style_tags, notes. May be empty (`{"items": []}`).

**Returns:** A string containing the outfit suggestion — 2–4 sentences of styling advice referencing specific wardrobe pieces if available, or general styling advice if wardrobe is empty.

**On failure / empty wardrobe:** If `wardrobe["items"]` is empty, the LLM prompt instructs it to give general styling advice for the item without referencing specific wardrobe pieces. If the LLM call raises an exception, returns the string `"Could not generate outfit suggestion. Please try again."` — never raises an exception.

---

### Tool 3 — create_fit_card

**What it does:** Given an outfit suggestion and the new item's details, calls the LLM to generate a short, shareable, social-media-style caption.

**Inputs:**
- `outfit` (str): the outfit suggestion string returned by suggest_outfit
- `new_item` (dict): the listing object (keys: id, title, description, category, style_tags, size, condition, price, colors, brand, platform)

**Returns:** A string of 1–3 sentences written in casual, first-person social media voice. Mentions the item, price, and platform. Varies between calls (LLM temperature 1.0+).

**On failure / empty outfit:** If `outfit` is an empty string or None, returns `"Could not generate fit card — outfit description was empty."` without calling the LLM. If the LLM call raises an exception, returns `"Could not generate fit card. Please try again."`.

---

### Tool 4 (Stretch) — compare_price

**What it does:** Given a listing, finds comparable items in the dataset and assesses whether the price is fair, high, or a steal.

**Inputs:**
- `item` (dict): a listing object with at least `category` (str), `price` (float), and `condition` (str)

**Returns:** A dict with keys: `verdict` (str: "steal", "fair", or "high"), `avg_comparable_price` (float), `comparable_count` (int), `reasoning` (str explaining the comparison).

**On failure:** If fewer than 2 comparable items are found, returns `{"verdict": "unknown", "avg_comparable_price": None, "comparable_count": 0, "reasoning": "Not enough comparable listings to assess price."}`.

---

## Planning Loop

The planning loop lives in `run_agent()` in `agent.py`. It runs sequentially but branches on results at each step:

```
1. Call search_listings(description, size, max_price)
   ├── IF results == []:
   │     session["error"] = "No listings matched..."
   │     RETURN session early (suggest_outfit and create_fit_card are NOT called)
   └── IF results != []:
         session["selected_item"] = results[0]
         session["search_results"] = results

2. Call suggest_outfit(session["selected_item"], wardrobe)
   ├── IF return value starts with "Could not":
   │     session["error"] = <the error string>
   │     RETURN session early (create_fit_card is NOT called)
   └── IF valid suggestion:
         session["outfit_suggestion"] = suggestion

3. Call compare_price(session["selected_item"])  [stretch]
         session["price_verdict"] = verdict dict

4. Call create_fit_card(session["outfit_suggestion"], session["selected_item"])
   ├── IF return value starts with "Could not":
   │     session["error"] = <the error string>
   │     RETURN session
   └── IF valid fit card:
         session["fit_card"] = fit_card

5. RETURN session
```

The loop is NOT a fixed sequence — if step 1 returns empty, steps 2–4 never execute. The agent's output depends entirely on what each tool returns.

---

## State Management

A single `session` dict is initialized at the start of `run_agent()` and passed by reference through each step:

```python
session = {
    "query": query,
    "search_results": [],       # set after search_listings
    "selected_item": None,      # set to results[0] if found
    "outfit_suggestion": None,  # set after suggest_outfit
    "price_verdict": None,      # set after compare_price (stretch)
    "fit_card": None,           # set after create_fit_card
    "error": None,              # set if any tool fails
}
```

Each tool call reads from and writes to this dict. No tool is ever called with a hardcoded value — all inputs come from the session. The Gradio UI reads from `session` keys at the end to populate output panels.

---

## Error Handling Table

| Tool | Failure Mode | Agent Response |
|------|-------------|----------------|
| `search_listings` | Returns `[]` (no matches) | Sets `session["error"] = "No listings matched your search. Try broader keywords, a different size, or raise your budget."` Returns early. Never calls downstream tools. |
| `search_listings` | Exception during filtering | Catches exception, sets `session["error"] = "Search failed unexpectedly. Please try again."` Returns early. |
| `suggest_outfit` | Empty wardrobe | LLM gives general styling advice instead of wardrobe-specific combos. Does not error. |
| `suggest_outfit` | LLM API exception | Returns string `"Could not generate outfit suggestion. Please try again."` Planning loop detects this and sets session error. |
| `create_fit_card` | Empty outfit string | Returns `"Could not generate fit card — outfit description was empty."` without calling LLM. |
| `create_fit_card` | LLM API exception | Returns `"Could not generate fit card. Please try again."` |
| `compare_price` | Too few comparables | Returns dict with `"verdict": "unknown"` and explanation. Never raises exception. |

---

## Architecture

```
User Query (natural language)
    │
    ▼
run_agent() — Planning Loop
    │
    ├─► search_listings(description, size, max_price)
    │       │
    │       ├── results == [] ──► session["error"] = "No listings matched..."
    │       │                          │
    │       │                          └──────────────────────────► RETURN session
    │       │
    │       └── results != []
    │               │
    │           session["search_results"] = results
    │           session["selected_item"]  = results[0]
    │               │
    ├─► suggest_outfit(selected_item, wardrobe)
    │       │
    │       ├── LLM error ──► session["error"] = "Could not generate..."
    │       │                          │
    │       │                          └──────────────────────────► RETURN session
    │       │
    │       └── success
    │               │
    │           session["outfit_suggestion"] = suggestion
    │               │
    ├─► compare_price(selected_item)   [stretch]
    │           │
    │       session["price_verdict"] = verdict
    │               │
    └─► create_fit_card(outfit_suggestion, selected_item)
            │
            ├── error ──► session["error"] = "Could not generate fit card..."
            │
            └── success
                    │
                session["fit_card"] = fit_card
                    │
                    ▼
              RETURN session
                    │
                    ▼
            Gradio UI reads session keys → populates output panels
```

---

## AI Tool Plan

| Milestone | AI Tool | Input I'll Provide | Expected Output | How I'll Verify |
|-----------|---------|-------------------|-----------------|-----------------|
| Tool 1: search_listings | Claude | Tool 1 spec block (inputs, return value, failure mode) + listings schema | Python function using load_listings() with keyword + size + price filtering | Check: filters all 3 params, returns [], no exception on no match |
| Tool 2: suggest_outfit | Claude | Tool 2 spec block + wardrobe schema + example wardrobe JSON | Python function calling Groq llama-3.3-70b-versatile with wardrobe-aware prompt | Check: handles empty wardrobe, returns string not exception, mentions wardrobe items |
| Tool 3: create_fit_card | Claude | Tool 3 spec block + sample listing JSON | Python function calling Groq with social-caption prompt at temp 1.1 | Check: returns string, varies on repeated calls, mentions price and platform |
| Tool 4: compare_price | Claude | Tool 4 spec block + listings schema | Python function filtering by category+condition and computing avg price | Check: returns dict with all 4 keys, handles <2 comparables gracefully |
| Planning loop | Claude | Architecture diagram + Planning Loop section + State Management section | run_agent() function with session dict and conditional branching | Check: doesn't call all tools unconditionally, session keys populated correctly, early return on empty results |

---

## Complete Interaction Walkthrough

**Query:** "I'm looking for a vintage graphic tee under $30, size M. I mostly wear baggy jeans and chunky sneakers."

**Step 1 — search_listings("vintage graphic tee", size="M", max_price=30.0)**
- Filters 40 listings: keeps items where "vintage" or "graphic" or "tee" appears in title/description/style_tags/category, size == "M", price <= 30.0
- Returns e.g. `[{"id": "lst_005", "title": "Faded Band Tee", "price": 22.0, "size": "M", "platform": "depop", ...}]`
- Planning loop: `results != []` → `session["selected_item"] = results[0]`, proceed

**Step 2 — suggest_outfit(session["selected_item"], wardrobe)**
- Sends to Groq: item details + wardrobe items list
- LLM returns: `"This faded band tee pairs perfectly with your baggy dark-wash jeans and chunky white sneakers for a 90s streetwear vibe. Add your black crossbody bag to finish the look."`
- Planning loop: valid string → `session["outfit_suggestion"] = <above>`, proceed

**Step 3 — compare_price(session["selected_item"])**
- Finds all listings where category == "tops", computes avg price
- Returns: `{"verdict": "steal", "avg_comparable_price": 31.50, "comparable_count": 8, "reasoning": "At $22, this is $9.50 below the average for tops in the dataset."}`
- `session["price_verdict"] = <above>`, proceed

**Step 4 — create_fit_card(session["outfit_suggestion"], session["selected_item"])**
- Sends to Groq: outfit suggestion + item title/price/platform
- LLM returns: `"thrifted this faded band tee off depop for $22 and honestly it was made for my wide-legs 🖤 baggy jeans + chunky sneakers, full look incoming"`
- `session["fit_card"] = <above>`

**Final state returned to UI:**
- Search panel: top listing card
- Outfit panel: styling suggestion
- Fit card panel: shareable caption
- Price verdict: "steal — $9.50 below average"

