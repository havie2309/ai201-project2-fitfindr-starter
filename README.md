# FitFindr 🛍️

A multi-tool AI agent that helps users find secondhand clothing and figure out how to wear it. FitFindr takes a natural language query, searches a mock thrift dataset, suggests outfit combinations using the user's wardrobe, assesses the price, and generates a shareable fit card — all in one flow.

[DEMO](https://www.loom.com/share/d353e5c03df844bc9922af9f4a370c1d)

---

## Setup

```bash
git clone <your-repo-url>
cd fitfindr
python -m venv .venv
source .venv/bin/activate  # Windows: source .venv/Scripts/activate
pip install -r requirements.txt
```

Create a `.env` file in the repo root:

```
GROQ_API_KEY=your_key_here
```

Run the app:

```bash
python app.py
```

Open the URL shown in your terminal (usually `http://localhost:7860`).

---

## Tool Inventory

### `search_listings(description: str, size: str | None, max_price: float | None) → list[dict]`

Filters the 40-item mock listings dataset by keyword match, size, and price ceiling. Keywords are matched case-insensitively across `title`, `description`, `category`, `style_tags`, `colors`, and `brand`. Each matching listing is scored by keyword hit count and results are returned sorted best-match first. Returns `[]` if nothing matches — never raises an exception.

Each returned dict contains: `id`, `title`, `description`, `category`, `style_tags` (list), `size`, `condition`, `price` (float), `colors` (list), `brand`, `platform`.

### `suggest_outfit(new_item: dict, wardrobe: dict) → str`

Calls the Groq LLM (`llama-3.3-70b-versatile`) to suggest 1–2 complete outfit combinations using the new item and the user's wardrobe. If the wardrobe is empty, the LLM gives general styling advice instead of wardrobe-specific combinations. Returns a non-empty string. Never raises an exception — returns an error message string if the LLM call fails.

### `create_fit_card(outfit: str, new_item: dict) → str`

Calls the Groq LLM at temperature 1.1 to generate a 2–3 sentence casual Instagram-style caption referencing the item name, price, and platform. Guards against empty `outfit` input before calling the LLM. Returns a different caption on each call for the same input. Never raises an exception.

### `compare_price(item: dict) → dict` *(stretch)*

Finds all listings in the same category, computes the average price, and returns a verdict of `"steal"` (≥20% below average), `"fair"` (within 20%), or `"high"` (≥20% above average). Returns a dict with keys: `verdict` (str), `avg_comparable_price` (float|None), `comparable_count` (int), `reasoning` (str). Returns `"unknown"` verdict if fewer than 2 comparables exist.

---

## How the Planning Loop Works

The planning loop lives in `run_agent()` in `agent.py`. It is **not a fixed sequence** — each step checks the result of the previous one before proceeding:

1. **Parse query** — regex extracts `description`, `size`, and `max_price` from the natural language input. No LLM needed for this step.
2. **Search with retry** — calls `search_listings()` with all three parameters. If results are empty and a size was specified, automatically retries without the size filter and notes this to the user. If still empty, sets `session["error"]` and **returns early** — `suggest_outfit` and `create_fit_card` are never called with empty input.
3. **Select item** — sets `session["selected_item"] = results[0]`.
4. **Suggest outfit** — calls `suggest_outfit()`. If the return value starts with `"Could not"`, sets `session["error"]` and returns early — `create_fit_card` is not called.
5. **Compare price** — calls `compare_price()` and stores the verdict. This step never causes early return.
6. **Create fit card** — calls `create_fit_card()`. If it returns an error string, sets `session["error"]`.
7. **Return session** — the Gradio UI reads all keys from the session dict to populate output panels.

**What the agent does when `search_listings` returns no results:** It sets `session["error"]` to a specific, actionable message — e.g. `"No listings matched your search. Size 'XXS' was not found even after retrying without it. Try raising your budget above $5. You can also try broader keywords."` — and returns immediately. The outfit and fit card panels stay empty.

---

## State Management

A single `session` dict is initialized at the start of `run_agent()` and written to at each step:

```python
session = {
    "query": query,              # original user input
    "parsed": {},                # extracted description, size, max_price
    "search_results": [],        # all results from search_listings
    "selected_item": None,       # results[0], passed into suggest_outfit
    "wardrobe": wardrobe,        # user's wardrobe dict
    "outfit_suggestion": None,   # string from suggest_outfit
    "price_verdict": None,       # dict from compare_price
    "fit_card": None,            # string from create_fit_card
    "error": None,               # set on any early exit
    "retry_note": None,          # set if size filter was dropped on retry
}
```

No tool ever receives a hardcoded value — every input comes from the session. The item found by `search_listings` flows directly into `suggest_outfit` as `session["selected_item"]`. The string from `suggest_outfit` flows directly into `create_fit_card` as `session["outfit_suggestion"]`. The Gradio UI reads from session keys at the end — it never re-runs any tool.

---

## Error Handling

| Tool | Failure Mode | Agent Response |
|------|-------------|----------------|
| `search_listings` | Returns `[]` | Sets specific error message with actionable suggestions (try broader keywords, raise budget). Returns early — downstream tools not called. |
| `search_listings` | Exception during filtering | Catches exception, returns `[]`, planning loop treats it as no results. |
| `search_listings` | Size returns no results | Automatically retries without size filter. Informs user via `retry_note` in the listing panel. |
| `suggest_outfit` | Empty wardrobe | LLM prompt switches to general styling advice mode — no error raised, no empty string returned. |
| `suggest_outfit` | LLM API exception | Returns `"Could not generate outfit suggestion. Please try again."` Planning loop detects this string and sets `session["error"]`, returning early. |
| `create_fit_card` | Empty `outfit` string | Returns `"Could not generate fit card — outfit description was empty."` without calling LLM. |
| `create_fit_card` | LLM API exception | Returns `"Could not generate fit card. Please try again."` |
| `compare_price` | Fewer than 2 comparables | Returns `{"verdict": "unknown", ...}` with explanation. Never causes early return. |

**Concrete example from testing:**

```bash
python -c "from tools import search_listings; print(search_listings('designer ballgown', size='XXS', max_price=5))"
# Output: []
```

Running this through the full agent:
```bash
python -c "
from agent import run_agent
from utils.data_loader import get_example_wardrobe
s = run_agent('designer ballgown size XXS under \$5', get_example_wardrobe())
print(s['error'])
print('fit_card:', s['fit_card'])
"
# Output:
# No listings matched your search. Size 'XXS' was not found even after retrying without it. Try raising your budget above $5. You can also try broader keywords.
# fit_card: None
```

The agent communicates exactly what failed and what to try next. `fit_card` is `None` confirming no downstream tools were called.

---

## Spec Reflection

**One way the spec helped:** Writing the planning loop in `planning.md` as explicit conditional branches (`if results == []: return early`) before touching any code made `agent.py` straightforward to implement. The diagram acted as a direct translation guide — each arrow became an `if` statement.

**One way implementation diverged from the spec:** The spec described query parsing as a potential LLM call. During implementation I used regex instead — it's faster, free, testable without API calls, and the structure of clothing queries (size patterns, price patterns) is regular enough that regex handles it reliably. The tradeoff is that very unusual phrasings might not parse correctly, but for the scope of this project regex proved more robust than adding an extra LLM round-trip.

---

## AI Usage

### Instance 1 — search_listings implementation
I gave Claude the Tool 1 spec block from `planning.md` (inputs with types, return value description, failure mode) and the listings schema (field names and types from the sample output). I asked it to implement `search_listings` using `load_listings()`. The generated code used `.get()` for every field access and returned `[]` on exception — matching my spec. I reviewed and added the multi-field `searchable` string construction (the generated version only searched `title` and `description`, missing `style_tags` and `colors`), and changed the score threshold from `>= 1` to `> 0` to match the TODO comment phrasing.

### Instance 2 — planning loop implementation
I gave Claude the full architecture diagram from `planning.md` and both the Planning Loop and State Management spec sections. I asked it to implement `run_agent()` using the session dict structure I defined. The generated code called all three tools unconditionally in sequence without checking results — it had `if not results` as a comment but no actual early return. I rewrote the branching logic to match the diagram exactly: checking `if not results` and returning the session immediately, and checking `if outfit.startswith("Could not")` before calling `create_fit_card`. I also added the `_search_with_retry` helper and `compare_price` call, which weren't in the generated output.

### Instance 3 — suggest_outfit prompt engineering
I gave Claude the Tool 2 spec (empty wardrobe handling, wardrobe item schema) and asked it to write the LLM prompt. The generated prompt asked the LLM to "suggest an outfit" without specifying format or length. I revised it to specify "1–2 complete outfit combinations", require naming exact wardrobe pieces, and request a specific styling tip — which produced noticeably more useful and specific suggestions in testing.

---

## Stretch Features Implemented

- **Price comparison tool** (`compare_price`) — compares item price against same-category listings, returns steal/fair/high verdict with reasoning. Shown in listing panel.
- **Retry logic with fallback** — if `search_listings` returns empty with a size filter, automatically retries without size and informs the user what was adjusted.

---

## Running Tests

```bash
pytest tests/ -v
```

17 tests covering all tools and failure modes.

