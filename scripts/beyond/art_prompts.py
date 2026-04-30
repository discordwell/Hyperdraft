"""
Beyond Ravnica — ChatGPT image-generation prompts for the 8-card Izzet PoC.

Each entry is the *exact* prompt to paste into chatgpt.com. The framing
intentionally locks the style to modern Pokemon TCG Scarlet & Violet
"ex" era illustration (the Yuu Nishida / 5ban Graphics look) while
giving each card distinctly Ravnica/Izzet visual cues.

The constants are read by humans and by the chrome-driving workflow.
Output instructions ALL ask for a square 1024x1024 image with NO text,
NO card frame, NO logo — those get composited in afterwards.
"""

STYLE_BASE = (
    "Modern Pokemon Trading Card Game Scarlet & Violet ex full-art "
    "illustration style. Bright vibrant saturated colors, clean "
    "cel-shaded coloring with crisp ink outlines, soft pastel bokeh "
    "sky background with rainbow holographic shimmer, glossy "
    "ink-on-paper finish. Style of Pokemon TCG illustrators "
    "5ban Graphics, Yuu Nishida, and kawayoo. Pokemon-cute "
    "proportions: large round expressive eyes, rounded simple "
    "silhouette, friendly approachable expression, NOT menacing. "
    "Single subject dominates the frame in a dynamic but cheerful "
    "pose. Square 1:1 composition, full-bleed art, NO text, "
    "NO logos, NO card frame, NO borders — just the illustration."
)

PROMPTS = {
    "Nivlet": (
        "Cute baby dragon Pokemon called 'Nivlet' — chibi proportions, "
        "round chubby body covered in bright crimson scales with a "
        "sky-blue belly, oversized sparkling violet eyes, two tiny "
        "ridge-fins instead of wings, perky ear-tufts, a single tiny "
        "ink-spot on its snout, sitting upright with paws raised. "
        "Wisps of friendly blue static curl above its head. Pastel "
        "sky-blue bokeh background. " + STYLE_BASE
    ),
    "Mizzling": (
        "Cute juvenile dragon Pokemon called 'Mizzling' — sleek "
        "crimson scales with electric-blue belly markings, mid-sized "
        "puppy-like body, partially-grown wings crackling with little "
        "blue sparks, big round eyes, tongue lolling out playfully, "
        "tiny brass goggles askew on its forehead, mid-bounce pose. "
        "Pastel sunset-purple bokeh background. " + STYLE_BASE
    ),
    "Niv-Mizzet, Parun ex": (
        "Cute majestic dragon Pokemon called 'Niv-Mizzet ex' — long "
        "graceful serpentine body in deep crimson and bright sky-blue "
        "scales, simple stylized rune-pattern markings glowing soft "
        "blue, large friendly intelligent eyes, broad wings unfurled, "
        "coiled in a triumphant flying pose. Soft pastel cloudscape "
        "background with rainbow holographic shimmer. Distinctly "
        "Pokemon TCG ex full-art look — bright, joyful, awe-inspiring "
        "but kid-friendly, not scary. " + STYLE_BASE
    ),
    "Goblin Electromancer": (
        "Cute goblin Pokemon called 'Goblin Electromancer' — chibi "
        "goblin with bright green skin, big round eyes behind goggles, "
        "a slightly-too-large copper-helmet, holding up a tiny brass "
        "tesla-rod arcing little blue sparks, mid-cackle with a wide "
        "happy grin. Pastel yellow-orange bokeh workshop background. "
        + STYLE_BASE
    ),
    "Mercurial Mageling": (
        "Cute slime Pokemon called 'Mercurial Mageling' — round "
        "translucent blue blob with two huge sparkling eyes, a tiny "
        "spellbook floating above it, soft droplets orbiting around. "
        "Pastel turquoise bokeh background. " + STYLE_BASE
    ),
    "Niv-Mizzet's Tower": (
        "Pokemon TCG Stadium card illustration of 'Niv-Mizzet's "
        "Tower' — a friendly cartoon brass-and-copper spire bristling "
        "with cute tesla-coils, glowing blue stained-glass windows, "
        "puffy little steam clouds, sitting on a fluffy floating "
        "island. Bright cheerful sunset Ravnica skyline behind. "
        "Wide landscape framing. Pokemon TCG Stadium aesthetic, "
        "NOT a dramatic painting. " + STYLE_BASE
    ),
    "Ral, Storm Conduit": (
        "Pokemon TCG Supporter trainer-card illustration of 'Ral' — a "
        "young anime-styled man with messy dark hair, simple goggles "
        "on his forehead, wearing a stylized blue coat, both hands "
        "raised cheerfully channeling friendly blue sparks of "
        "lightning between his palms, confident smile. Pastel "
        "rainy-blue bokeh background. Character centered, "
        "shoulders-up framing typical of Pokemon TCG Supporter cards. "
        + STYLE_BASE
    ),
    "Izzet Signet": (
        "Pokemon TCG Item trainer-card illustration of 'Izzet Signet' "
        "— a single ornate red-and-blue enamel medallion shaped like "
        "a stylized boar's head with curled copper-coil horns, "
        "floating in the center of frame, surrounded by a few cheerful "
        "blue spark-icons. Soft warm-cream bokeh background. Clean "
        "centered Item-card composition. " + STYLE_BASE
    ),
}


def get_prompt(card_name: str) -> str:
    """Return the chatgpt prompt for the given card."""
    if card_name not in PROMPTS:
        raise KeyError(f"No art prompt for card: {card_name!r}")
    return PROMPTS[card_name]


def all_card_names() -> list[str]:
    return list(PROMPTS.keys())


if __name__ == "__main__":
    for name in all_card_names():
        print("=" * 60)
        print(name)
        print("-" * 60)
        print(get_prompt(name))
        print()
