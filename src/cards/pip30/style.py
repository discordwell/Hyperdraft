"""PIP//30 art-style module — consumed by the art harness.

PIP//30 is a Unity deckbuilder about Lareine, a Junior Software Engineer
surviving a Performance Improvement Plan. The threats are anthropomorphized
workplace anxieties (vague tickets, flaky tests, slack nudges); the rewards
are coding skills and coping mechanisms. The tone is Severance meets Slay
the Spire — corporate burnout rendered as a roguelike."""

from __future__ import annotations

from typing import Any

STYLE_HEADLINE = (
    "All PIP//30 card art is hand-painted in a thick-brushstroke gouache style "
    "with a constrained corporate-anxiety palette: muted sage-teal (#5C7A75), "
    "bone white (#E8E2D4), fluorescent pale yellow (#D9CC6E), deep navy "
    "shadow (#1B2438), and a single sickly amber accent (#C68B3A) reserved for "
    "stress, shadow, and the moment a deadline lands. Lighting is the flat "
    "overhead fluorescence of a mid-century open-plan office — no warm sun, "
    "no soft rim light. Compositions are slightly off-center and a little too "
    "still, like a Severance still frame. Subjects are painted with the "
    "rough confident strokes of Slay the Spire's portraits but the cold "
    "color discipline and quiet menace of Disco Elysium's bleaker scenes. "
    "Never photoreal. Never anime. No gradients smoother than a half-loaded "
    "brush. Card art panel is 1024x1024, framed as if cropped from a larger "
    "painting — limbs and props can run off the edge. "
    "ABSOLUTELY NO baked-in text, no title cards, no card-name labels, no "
    "captions, no logos, no readable signage, no UI chrome of any kind in "
    "the image — the game engine renders the card name and rules text in a "
    "separate UI layer. In-world handwriting on sticky notes or papers is "
    "fine if it's clearly illegible scribbles, not real letters."
)

CATEGORY_FLAVORS: dict[str, str] = {
    "code": (
        "A focused, aggressive moment of writing or reading code. Show hands on "
        "a backlit mechanical keyboard, a terminal window glowing pale yellow on "
        "navy, a stack trace pinned to a corkboard, or a single line of "
        "highlighted source. The action is precise and small — wrists, eyes, "
        "the tip of a stylus. Body language is locked-in but tired. Pale "
        "yellow as the dominant accent for the screen glow; everything else "
        "muted teal and bone white."
    ),
    "process": (
        "A defensive, careful moment of documenting, clarifying, or organizing. "
        "Show sticky notes layered on a window, a printed ticket with margin "
        "annotations, hands holding a whiteboard marker, or a Slack thread "
        "pinned to a wall. Composition is calmer and slightly more cluttered "
        "than Code cards — paper, color-coded labels, neat handwriting. "
        "Sage-teal dominant with bone-white paper highlights."
    ),
    "survival": (
        "A small restorative ritual. A coffee mug held in both hands, a closed "
        "laptop with a hand resting on it, a deep breath in a stairwell, a "
        "phone face-down on a desk. Quiet and human. The palette warms slightly "
        "— bone white and sage-teal still, but the navy shadow softens a touch. "
        "No amber here. These are the cards that look like a held exhale."
    ),
    "shadow": (
        "A desperation move that costs something. Overtime under a single desk "
        "lamp, a half-eaten meal at a keyboard, eyes too wide in monitor glow, "
        "a clock reading 11:47 pm. The sickly amber accent is dominant on these "
        "cards — wherever the light source falls, it falls amber. Composition "
        "is closer-cropped and more claustrophobic. The figure should look like "
        "they know this is a bad idea and are doing it anyway."
    ),
    "enemy": (
        "A workplace anxiety made manifest. Render the antagonist as a "
        "physical object or anthropomorphized form, not a person: a vague "
        "ticket as a hovering manila card with smudged unreadable text, a "
        "flaky test as a glitching dashboard with a red bar that flickers "
        "between pass and fail, a slack nudge as a notification balloon "
        "swollen larger than a human head, a CI warning as a yellow caution "
        "tape wrapped around a server rack. They occupy the frame like they "
        "belong there — that's the horror. Deep navy backgrounds, amber "
        "warning accent, sage-teal cold-light fill."
    ),
    "challenge": (
        "A focused snapshot of a bug or code review. The composition centers a "
        "monitor, a printed code listing on a desk, or a whiteboard with "
        "diagrammed control flow. Pale yellow screen-light is the dominant "
        "accent. No human figures or only their hands — the puzzle is the "
        "subject. Slightly tilted angle, as if leaning in."
    ),
    "object": (
        "Fallback. A single object from Lareine's PIP — a cracked mug, a "
        "spent ergonomic mouse, a printed performance review folded once. "
        "Sage-teal and bone white only. No figures."
    ),
}


_FAMILY_TO_CATEGORY = {
    "code": "code",
    "process": "process",
    "survival": "survival",
    "shadow": "shadow",
}


def categorize(card: Any) -> str:
    """Map a PIP//30 JSON entry (as SimpleNamespace) to an art category.

    PIP//30 has three top-level entity types in StreamingAssets/:
      * cards      — have a ``family`` field (Code / Process / Survival / Shadow)
      * enemies    — have an ``intentKey`` translation key
      * challenges — have a ``codeText`` source snippet

    The order matters: a future card schema could theoretically include
    a ``maxResolve`` field by name collision, so we key off the entity-
    unique fields (``intentKey`` for enemies, ``codeText`` for challenges)
    before any generic fallback.
    """
    if card is None:
        return "object"
    family = getattr(card, "family", None)
    if isinstance(family, str) and family.lower() in _FAMILY_TO_CATEGORY:
        return _FAMILY_TO_CATEGORY[family.lower()]
    if getattr(card, "codeText", None):
        return "challenge"
    if getattr(card, "intentKey", None):
        return "enemy"
    return "object"
