"""
LLM Prompts for Deck Building

System and user prompts for AI-powered deck construction.
"""

DECK_BUILD_SYSTEM = """You are an expert Magic: The Gathering deck builder with extensive tournament experience.

Your task is to build competitive, balanced 60-card decks with proper mana bases.

Guidelines:
- Mainboard should be exactly 60 cards
- Include 24-26 lands depending on curve
- 4 copies of key cards for consistency
- Curve should match archetype (aggro = low, control = high)
- Sideboard is 15 cards for specific matchups
- Only use cards from the provided card pool

Respond ONLY with valid JSON. No explanations or commentary."""


DECK_BUILD_PROMPT = """Build a {format} deck based on this request:

"{user_request}"

Constraints:
- Colors: {colors}
- Available cards: {card_pool_summary}

Return JSON with this exact structure:
{{
  "name": "Deck Name",
  "archetype": "Aggro|Control|Midrange|Combo|Ramp",
  "colors": ["W", "U", "B", "R", "G"],
  "description": "Brief strategy description",
  "mainboard": [
    {{"card": "Card Name", "qty": 4}},
    ...
  ],
  "sideboard": [
    {{"card": "Sideboard Card", "qty": 2}},
    ...
  ],
  "explanation": "Why these cards work together"
}}

IMPORTANT: Only use cards from the available card pool. Make sure mainboard has exactly 60 cards total."""


DECK_SUGGEST_SYSTEM = """You are an expert MTG deck tuner. Analyze the deck and suggest improvements.

You can suggest:
- Cards to add (from the available pool)
- Cards to remove (give reasons)
- Quantity adjustments
- Sideboard changes

Respond ONLY with valid JSON."""


DECK_SUGGEST_PROMPT = """Analyze this deck and suggest improvements:

Deck: {deck_name}
Archetype: {archetype}
Colors: {colors}

Current mainboard:
{mainboard_list}

Current sideboard:
{sideboard_list}

Deck stats:
- Average CMC: {avg_cmc}
- Land count: {land_count}
- Creature count: {creature_count}

User request: "{user_request}"

Available cards for additions:
{available_cards}

Return JSON with suggestions:
{{
  "analysis": "Brief analysis of current deck",
  "suggestions": [
    {{
      "action": "add|remove|adjust",
      "card": "Card Name",
      "from_qty": 0,
      "to_qty": 4,
      "reason": "Why this change"
    }}
  ],
  "priority_changes": ["List of most important changes"]
}}"""


DECK_SCHEMA = {
    "name": "str",
    "archetype": "str",
    "colors": "list[str]",
    "description": "str",
    "mainboard": "list[dict]",
    "sideboard": "list[dict]",
    "explanation": "str"
}


SUGGEST_SCHEMA = {
    "analysis": "str",
    "suggestions": "list[dict]",
    "priority_changes": "list[str]"
}


# =============================================================================
# Hybrid Deck Polish (W3): refine a heuristic skeleton
# =============================================================================

DECK_POLISH_SYSTEM = """You are an MTG deck tuner. You receive a complete, valid 60-card skeleton and may make AT MOST 6 mainboard swaps (1-for-1, same CMC ±1) plus choose a 15-card sideboard. You must NOT change the mana base, archetype, color identity, or total card count. Respond ONLY with JSON: {name, description, swaps:[{out, in, qty, reason}], sideboard:[{card, qty}]}."""


DECK_POLISH_PROMPT = """Polish this complete heuristic deck skeleton.

Skeleton name: {deck_name}
Archetype: {archetype}
Color identity: {colors}
Sets: {set_codes}
User hint: "{user_hint}"

Current mainboard (60 cards, valid mana base — do not modify lands):
{mainboard_list}

Available card pool (already filtered to color identity):
{card_pool_summary}

Constraints:
- Make at most 6 swaps. Each swap is 1-for-1, same CMC ±1.
- Never swap a land or change the land count.
- Stay within the listed colors.
- Provide a flavor name and brief description.
- Pick a 15-card sideboard from the pool. Each card max qty 4.

Return JSON exactly:
{{
  "name": "Flavorful Deck Name",
  "description": "Brief strategy description (1-2 sentences)",
  "swaps": [
    {{"out": "Card to remove", "in": "Card to add", "qty": 1, "reason": "Why"}}
  ],
  "sideboard": [
    {{"card": "Sideboard Card", "qty": 2}}
  ]
}}"""


POLISH_SCHEMA = {
    "name": "str",
    "description": "str",
    "swaps": "list[dict]",
    "sideboard": "list[dict]",
}
