"""One-shot: rebuild the Clankers rulebook gallery + cover with real art.

Reads the v1 HTML at docs/rulebooks/clankers_rulebook.html, swaps the ASCII
cover for a Cores hero, and replaces the 5 dry gallery tables with image-grid
cards backed by docs/rulebooks/assets/CLAN-thumbs/*.jpg.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.cards.clankers.CLAN import CLAN_CARDS  # noqa: E402
from src.engine.types import CardType  # noqa: E402


HTML_PATH = PROJECT_ROOT / "docs" / "rulebooks" / "clankers_rulebook.html"
THUMB_REL = "assets/CLAN-thumbs"


# Cardtype mapping
TYPE_ORDER = [
    ("Cores", lambda c: CardType.CLANKERS_CORE in c.characteristics.types),
    ("Chassis", lambda c: CardType.CLANKERS_CHASSIS in c.characteristics.types),
    ("Weapons", lambda c: CardType.CLANKERS_WEAPON in c.characteristics.types),
    ("Add-Ons", lambda c: CardType.CLANKERS_ADD_ON in c.characteristics.types),
    ("Transients", lambda c: CardType.CLANKERS_TRANSIENT in c.characteristics.types),
    ("Structures", lambda c: CardType.CLANKERS_STRUCTURE in c.characteristics.types),
]


def slugify(name: str) -> str:
    s = name.lower().replace(".", "").replace("'", "")
    s = s.replace("—", "_").replace("-", "_").replace(" ", "_")
    s = re.sub(r"[^a-z0-9_α-ωΑ-Ω]", "", s)
    return s


def card_meta_line(card) -> str:
    """Cost · stats · slots line, type-dependent."""
    types = card.characteristics.types
    cost = card.mana_cost if card.mana_cost is not None else "—"
    arche = getattr(card, "clankers_archetype", "neutral") or "neutral"

    if CardType.CLANKERS_CORE in types:
        hp = getattr(card, "workshop_integrity", None) or card.characteristics.toughness
        return f"HP {hp} · {arche}"
    if CardType.CLANKERS_CHASSIS in types:
        p = card.characteristics.power
        i = card.characteristics.toughness
        return f"{cost} · {p}/{i} · {arche}"
    if CardType.CLANKERS_WEAPON in types:
        p = card.characteristics.power
        return f"{cost} · +{p} power · {arche}"
    if CardType.CLANKERS_ADD_ON in types:
        p = card.characteristics.power
        i = card.characteristics.toughness
        pi = f"+{p}/+{i}" if p or i else "+0/+0"
        return f"{cost} · {pi} · {arche}"
    if CardType.CLANKERS_TRANSIENT in types:
        return f"{cost} · {arche}"
    if CardType.CLANKERS_STRUCTURE in types:
        return f"{cost} · {arche}"
    return f"{cost} · {arche}"


def render_card(card) -> str:
    fname = slugify(card.name) + ".jpg"
    text = (card.text or "").strip()
    arche = getattr(card, "clankers_archetype", "neutral") or "neutral"
    return (
        f'<div class="g-card g-{arche}">\n'
        f'  <div class="g-art"><img src="{THUMB_REL}/{fname}" alt="{card.name}" loading="lazy"></div>\n'
        f'  <div class="g-meta">\n'
        f'    <div class="g-name">{card.name}</div>\n'
        f'    <div class="g-line">{card_meta_line(card)}</div>\n'
        f'    <div class="g-text">{text}</div>\n'
        f'  </div>\n'
        f'</div>'
    )


def render_section(title: str, cards) -> str:
    by_name = sorted(cards, key=lambda c: c.name.lower())
    cards_html = "\n".join(render_card(c) for c in by_name)
    return (
        f'<section class="page gallery-page">\n'
        f'<h3 class="gallery-h3">{title} ({len(by_name)})</h3>\n'
        f'<div class="g-grid">\n{cards_html}\n</div>\n'
        f'</section>'
    )


def render_gallery() -> str:
    sections = []
    for title, pred in TYPE_ORDER:
        cards = [c for c in CLAN_CARDS.values() if pred(c)]
        if not cards:
            continue
        sections.append(render_section(title, cards))

    intro = (
        '<section class="page">\n'
        '<div class="section-rule">SECTION 09</div>\n'
        '<h2 id="gallery">Card Gallery — 151 cards</h2>\n'
        '<p style="color: var(--ink-dim); font-size: 10pt;">'
        'All 151 cards in the CLAN set, grouped by type, sorted by name. '
        'Each card shows its commissioned Soviet-era-propaganda painting. '
        'Cost is in Compute. Chassis show power/integrity. Weapons show power-bonus. '
        'Add-Ons show +power/+integrity. Archetype tags color the card frame: '
        '<em class="arch-brick">brick</em> · <em class="arch-control">control</em> · '
        '<em class="arch-swarm">swarm</em> · <em class="arch-artillery">artillery</em> · '
        '<em class="arch-neutral">neutral</em>.</p>\n'
        '</section>'
    )

    return intro + "\n\n" + "\n\n".join(sections)


def render_cover_art() -> str:
    """Replace ASCII art with a montage of the 6 Cores."""
    cores = [
        ("forge_δ", "FORGE-Δ"),
        ("ethos_7", "ETHOS-7"),
        ("mirthbot_1", "MIRTHBOT-1"),
        ("bulwark_9", "BULWARK-9"),
        ("subroutine_α", "SUBROUTINE-α"),
        ("affectionexe", "Affection.exe"),
    ]
    cells = "\n".join(
        f'<div class="cover-cell">'
        f'<img src="{THUMB_REL}/{stem}.jpg" alt="{name}">'
        f'<div class="cover-cell-name">{name}</div>'
        f"</div>"
        for stem, name in cores
    )
    return f'<div class="cover-mosaic">\n{cells}\n</div>'


GALLERY_CSS = """
/* === Gallery image grid === */
.gallery-page { padding: 24px 32px; }
.gallery-h3 { font-family: var(--mono); color: var(--coolant); font-size: 18pt; margin: 0 0 16px; letter-spacing: -0.01em; }
.g-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 14px;
    margin: 0;
}
.g-card {
    background: var(--panel);
    border: 1px solid var(--gunmetal);
    border-left: 3px solid var(--ink-faint);
    border-radius: 4px;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    page-break-inside: avoid;
    break-inside: avoid;
}
.g-art { aspect-ratio: 1 / 1; background: #0a0f1c; }
.g-art img { width: 100%; height: 100%; object-fit: cover; display: block; }
.g-meta { padding: 8px 10px 10px; flex: 1; display: flex; flex-direction: column; gap: 3px; }
.g-name { font-family: var(--mono); color: var(--amber); font-size: 9.5pt; font-weight: 700; line-height: 1.15; }
.g-line { font-family: var(--mono); color: var(--circuit); font-size: 7.5pt; letter-spacing: 0.04em; text-transform: uppercase; }
.g-text { color: var(--ink); font-size: 8pt; line-height: 1.35; }

.g-brick     { border-left-color: #f97316; }
.g-control   { border-left-color: #2dd4bf; }
.g-swarm     { border-left-color: #e879f9; }
.g-artillery { border-left-color: #fbbf24; }
.g-neutral   { border-left-color: var(--ink-faint); }

em.arch-brick     { color: #f97316; font-style: normal; font-weight: 600; }
em.arch-control   { color: #2dd4bf; font-style: normal; font-weight: 600; }
em.arch-swarm     { color: #e879f9; font-style: normal; font-weight: 600; }
em.arch-artillery { color: #fbbf24; font-style: normal; font-weight: 600; }
em.arch-neutral   { color: var(--ink-dim); font-style: normal; font-weight: 600; }

/* Cover mosaic */
.cover-mosaic {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 14px;
    width: 100%;
    max-width: 720px;
    margin: 0 auto;
}
.cover-cell {
    background: var(--panel);
    border: 1px solid var(--gunmetal);
    border-radius: 6px;
    overflow: hidden;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.45);
}
.cover-cell img { width: 100%; aspect-ratio: 1 / 1; object-fit: cover; display: block; }
.cover-cell-name { font-family: var(--mono); color: var(--amber); font-size: 9.5pt; padding: 6px 8px; letter-spacing: 0.06em; }

@media print {
    .g-grid { gap: 10px; }
    .g-text { font-size: 7.5pt; }
}
"""


def main() -> int:
    html = HTML_PATH.read_text()

    # Inject gallery CSS just before </style>
    if "/* === Gallery image grid === */" not in html:
        html = html.replace("</style>", GALLERY_CSS + "\n</style>", 1)

    # Replace cover art
    cover_re = re.compile(r'<div class="cover-art">\s*<pre>.*?</pre>\s*</div>', re.DOTALL)
    new_cover = '<div class="cover-art">\n' + render_cover_art() + '\n</div>'
    if not cover_re.search(html):
        print("warn: cover-art block not found; cover unchanged", file=sys.stderr)
    else:
        html = cover_re.sub(new_cover, html, count=1)

    # Replace the entire §9 gallery block (from intro section through the last add-ons/transients sections,
    # stopping at §10 Quick Reference)
    gallery_start = html.find("<!-- ============================ §9 CARD GALLERY")
    quick_ref_start = html.find("<!-- ============================ §10 QUICK REFERENCE")
    if gallery_start == -1 or quick_ref_start == -1:
        print("err: could not locate gallery boundaries", file=sys.stderr)
        return 1

    new_gallery = render_gallery()
    html = (
        html[:gallery_start]
        + "<!-- ============================ §9 CARD GALLERY ============================ -->\n"
        + new_gallery
        + "\n\n"
        + html[quick_ref_start:]
    )

    HTML_PATH.write_text(html)
    print(f"wrote {HTML_PATH} ({len(html):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
