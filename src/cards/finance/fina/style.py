"""FINA art-style module — consumed by the art harness."""

from src.engine.types import CardType

STYLE_HEADLINE = (
    "All FINA card art uses a PS1-era low-polygon aesthetic: chunky flat-shaded "
    "triangular geometry, hard jewel-tone fill colors with no texture mapping, "
    "visible polygon seams treated as design features. The overall feel is a "
    "Bloomberg terminal reimagined as a PlayStation 1 FMV cutscene — expensive "
    "geometry, over-lit luxury interiors, angular silhouettes that read as "
    "authoritative and dangerous. No gradients. No soft shadows. All depth is "
    "achieved through polygon count reduction, not shading. Gold foil rares are "
    "rendered as fields of gold flat-shaded triangles catching an overlit point "
    "source, like a Fabergé egg made of polygons. Background: deep navy (#0B1A2E) "
    "card frames with jewel emerald (#0D2B1A) or sapphire accent panels."
)

CATEGORY_FLAVORS: dict[str, str] = {
    "trader": (
        "Humanoid figures built from 150–400 flat-shaded polygons. Power Traders "
        "(Leverage 3+) have larger, more angular silhouettes — broader shoulders, "
        "fewer facial polygons, imposing geometry. Low-cost Traders are sleek and "
        "compact. All Traders wear high-contrast business attire: charcoal polygon "
        "suit (#1C2A3A), sapphire polygon tie (#0B3D91), gold polygon cufflinks "
        "(#C8A84B). Background is a flat-shaded open-plan trading floor with "
        "overlit fluorescent geometry and a polygon Bloomberg terminal array. "
        "Rare Traders: deep sapphire background. Mythic Traders: gold-panel background."
    ),
    "order": (
        "Abstract polygon compositions — geometric objects mid-transformation. "
        "Market Orders show sharp angular bursts radiating from a polygon core "
        "(like a stylized explosion of flat triangles in cyan and white). "
        "Dark Pool Orders are face-down polygon slabs with a single jewel-tone "
        "polygon glow (#3D1A7A, dark purple) at one edge, implying hidden depth. "
        "Background: dark navy polygon environment with floating angular "
        "data-stream elements. No characters — pure geometry in motion."
    ),
    "strategy": (
        "Wider scene: a boardroom of polygon figures around a flat-shaded angular "
        "conference table, or a trading floor viewed from above as a polygon grid "
        "with activity nodes. High-cost Strategies have more polygon participants "
        "and more complex geometry in the room. Palette: deep emerald (#0D2B1A) "
        "and gunmetal with gold accent triangles (#C8A84B) on rares."
    ),
    "asset": (
        "Floating architectural or technological objects — a polygon server rack, "
        "a flat-shaded monitor array, a geometric golden vault door ajar. They "
        "feel permanent and weighty: more polygons per object than any Order, "
        "rendered against a warm overlit background (#1A1208) implying established "
        "infrastructure. Subtle gold polygon trim on all rare Assets. "
        "Palette: warm dark amber base with gold highlight triangles."
    ),
    "derivative": (
        "Flat-polygon attachment frameworks or interlocking geometric shells — "
        "a shield, a collar brace, an angular frame floating against a dark "
        "gradient-free background (#0B1A2E) with small angular connective geometry "
        "radiating outward. The art implies the Derivative is designed to link to "
        "something larger. Color: silver-grey (#8A9BB0) base with accent color "
        "matching the host archetype (gold for DV, cyan for HF, emerald for QT, "
        "purple for DA)."
    ),
    "structure": (
        "Large-polygon architectural pieces: a polygon trading floor terminal "
        "cluster, an angular glass-and-steel polygon building facade, a server room "
        "polygon landscape. They occupy the full card art panel with fewer dramatic "
        "action elements and more steady, wide-angle geometry. Structural blues "
        "(#0B2040) and cold greys (#3A4A5A) dominate, accented with gold polygon "
        "outlines (#C8A84B) at the corners for rare structures."
    ),
    "object": (
        "Generic fallback for uncategorized cards: flat-shaded polygon composition "
        "in the dominant navy-and-gold FINA palette. Minimal detail, maximum "
        "geometric clarity."
    ),
}


def categorize(card) -> str:
    """Map a CardDefinition to an art category string."""
    if card is None:
        return "object"
    chars = getattr(card, "characteristics", None)
    if chars is None:
        return "object"
    types = getattr(chars, "types", set()) or set()

    if CardType.FIN_TRADER in types:
        return "trader"
    if CardType.FIN_ORDER in types:
        return "order"
    if CardType.FIN_STRATEGY in types:
        return "strategy"
    if CardType.FIN_ASSET in types:
        return "asset"
    if CardType.FIN_DERIVATIVE in types:
        return "derivative"
    if CardType.FIN_STRUCTURE in types:
        return "structure"

    # MTG fallbacks (for any shared code paths)
    if CardType.CREATURE in types:
        return "trader"
    if CardType.INSTANT in types:
        return "order"
    if CardType.SORCERY in types:
        return "strategy"
    if CardType.ARTIFACT in types or CardType.ENCHANTMENT in types:
        return "asset"

    return "object"
