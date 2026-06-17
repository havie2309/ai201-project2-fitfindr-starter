"""
Gradio interface for FitFindr.
Run with: python app.py
"""

import gradio as gr

from agent import run_agent
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe
from tools import load_style_profile


# ── query handler ─────────────────────────────────────────────────────────────

def handle_query(user_query: str, wardrobe_choice: str) -> tuple[str, str, str, str]:
    if not user_query or not user_query.strip():
        return "Please enter a search query.", "", "", "📭 No style memory yet."

    wardrobe = (
        get_example_wardrobe()
        if wardrobe_choice == "Example wardrobe"
        else get_empty_wardrobe()
    )

    session = run_agent(user_query.strip(), wardrobe)

    # Build memory panel text
    profile = load_style_profile()
    if profile.get("past_items"):
        last = profile["past_items"][0]
        prefs = ", ".join(profile.get("preferences", [])[:6])
        profile_text = (
            f"📚 Style memory active\n"
            f"Last thrifted: {last['title']}\n"
            f"Saved preferences: {prefs}"
        )
    else:
        profile_text = "📭 No style memory yet — this is your first search."

    if session["error"]:
        error_text = f"❌ {session['error']}"
        if session.get("retry_note"):
            error_text = f"🔄 {session['retry_note']}\n\n{error_text}"
        return error_text, "", "", profile_text

    item = session["selected_item"]
    verdict = session.get("price_verdict")

    price_line = ""
    if verdict and verdict["verdict"] != "unknown":
        emoji = {"steal": "🟢 STEAL", "fair": "🟡 FAIR", "high": "🔴 HIGH"}[verdict["verdict"]]
        price_line = f"\n💰 Price verdict: {emoji}\n   {verdict['reasoning']}"

    retry_note = ""
    if session.get("retry_note"):
        retry_note = f"\n⚠️  {session['retry_note']}"

    listing_text = (
        f"🏷️  {item['title']}\n"
        f"💵  ${item['price']} on {item['platform'].title()}\n"
        f"📐  Size: {item['size']}\n"
        f"✅  Condition: {item['condition'].title()}\n"
        f"🎨  Colors: {', '.join(item['colors']).title()}\n"
        f"🏷️  Style: {', '.join(item['style_tags'])}\n"
        f"📦  Brand: {item.get('brand') or 'Unknown'}"
        f"{price_line}"
        f"{retry_note}"
    )

    return listing_text, session["outfit_suggestion"], session["fit_card"], profile_text


def clear_memory() -> str:
    from pathlib import Path
    Path("data/style_profile.json").unlink(missing_ok=True)
    return "📭 Memory cleared — no style memory yet."


# ── interface ─────────────────────────────────────────────────────────────────

EXAMPLE_QUERIES = [
    "vintage graphic tee under $30",
    "90s track jacket in size M",
    "flowy midi skirt under $40",
    "black combat boots size 8",
    "designer ballgown size XXS under $5",
]


def build_interface():
    with gr.Blocks(title="FitFindr") as demo:
        gr.Markdown("""
# FitFindr 🛍️
Find secondhand pieces and get outfit ideas based on your wardrobe.
Describe what you're looking for — include size and price if you want to filter.
        """)

        with gr.Row():
            query_input = gr.Textbox(
                label="What are you looking for?",
                placeholder="e.g. vintage graphic tee under $30, size M",
                lines=2,
                scale=3,
            )
            wardrobe_choice = gr.Radio(
                choices=["Example wardrobe", "Empty wardrobe (new user)"],
                value="Example wardrobe",
                label="Wardrobe",
                scale=1,
            )

        with gr.Row():
            submit_btn = gr.Button("Find it", variant="primary")
            clear_btn = gr.Button("🗑️ Clear style memory", variant="secondary")

        with gr.Row():
            listing_output = gr.Textbox(
                label="🛍️ Top listing found",
                lines=10,
                interactive=False,
            )
            outfit_output = gr.Textbox(
                label="👗 Outfit idea",
                lines=10,
                interactive=False,
            )
            fitcard_output = gr.Textbox(
                label="✨ Your fit card",
                lines=10,
                interactive=False,
            )
            memory_output = gr.Textbox(
                label="🧠 Style memory",
                lines=10,
                interactive=False,
            )

        gr.Examples(
            examples=[[q, "Example wardrobe"] for q in EXAMPLE_QUERIES],
            inputs=[query_input, wardrobe_choice],
            label="Try these queries",
        )

        submit_btn.click(
            fn=handle_query,
            inputs=[query_input, wardrobe_choice],
            outputs=[listing_output, outfit_output, fitcard_output, memory_output],
        )
        query_input.submit(
            fn=handle_query,
            inputs=[query_input, wardrobe_choice],
            outputs=[listing_output, outfit_output, fitcard_output, memory_output],
        )
        clear_btn.click(
            fn=clear_memory,
            inputs=[],
            outputs=[memory_output],
        )

    return demo


if __name__ == "__main__":
    demo = build_interface()
    demo.launch()