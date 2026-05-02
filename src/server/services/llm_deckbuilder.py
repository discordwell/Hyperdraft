"""
LLM Deck Builder Service

Uses LLM to generate and improve decks based on user requests.
"""

import asyncio
from typing import Optional

from src.ai.llm import OllamaProvider, LLMProvider
from src.ai.llm.deck_prompts import (
    DECK_BUILD_SYSTEM,
    DECK_BUILD_PROMPT,
    DECK_SUGGEST_SYSTEM,
    DECK_SUGGEST_PROMPT,
    DECK_SCHEMA,
    SUGGEST_SCHEMA,
    DECK_POLISH_SYSTEM,
    DECK_POLISH_PROMPT,
    POLISH_SCHEMA,
)
from src.cards import ALL_CARDS
from src.cards.set_registry import get_cards_in_set
from src.decks.deck import Deck, DeckEntry
from src.engine.types import Color


class LLMDeckBuilderService:
    """
    Service for AI-powered deck building using LLM.

    Uses Ollama by default for local inference.
    Falls back to API providers if configured.
    """

    def __init__(self, provider: Optional[LLMProvider] = None):
        """
        Initialize the deck builder service.

        Args:
            provider: LLM provider to use. Defaults to Ollama.
        """
        self.provider = provider or OllamaProvider(
            model="qwen2.5:7b",  # Larger model for better deck building
            timeout=120.0  # Deck building may take longer
        )

    @property
    def is_available(self) -> bool:
        """Check if the LLM provider is available."""
        return self.provider.is_available

    def _get_card_pool_summary(self, colors: Optional[list[str]] = None) -> str:
        """
        Get a summary of available cards for the prompt.

        Args:
            colors: Optional color filter (W, U, B, R, G)

        Returns:
            String summary of available cards by type
        """
        # Group cards by type
        creatures = []
        instants = []
        sorceries = []
        enchantments = []
        artifacts = []
        lands = []
        other = []

        color_set = None
        if colors:
            color_map = {'W': Color.WHITE, 'U': Color.BLUE, 'B': Color.BLACK, 'R': Color.RED, 'G': Color.GREEN}
            color_set = {color_map.get(c) for c in colors if c in color_map}

        for name, card_def in ALL_CARDS.items():
            chars = card_def.characteristics

            # Filter by color if specified
            if color_set:
                card_colors = chars.colors
                # Include colorless cards and cards matching any of the requested colors
                if card_colors and not any(c in color_set for c in card_colors):
                    continue

            type_names = [t.name for t in chars.types]

            if 'CREATURE' in type_names:
                creatures.append(name)
            elif 'INSTANT' in type_names:
                instants.append(name)
            elif 'SORCERY' in type_names:
                sorceries.append(name)
            elif 'ENCHANTMENT' in type_names:
                enchantments.append(name)
            elif 'ARTIFACT' in type_names:
                artifacts.append(name)
            elif 'LAND' in type_names:
                lands.append(name)
            else:
                other.append(name)

        # Limit each category for prompt length
        limit = 50

        summary_parts = []
        if creatures:
            summary_parts.append(f"Creatures ({len(creatures)} total): {', '.join(creatures[:limit])}")
        if instants:
            summary_parts.append(f"Instants ({len(instants)} total): {', '.join(instants[:limit])}")
        if sorceries:
            summary_parts.append(f"Sorceries ({len(sorceries)} total): {', '.join(sorceries[:limit])}")
        if enchantments:
            summary_parts.append(f"Enchantments ({len(enchantments)} total): {', '.join(enchantments[:limit])}")
        if artifacts:
            summary_parts.append(f"Artifacts ({len(artifacts)} total): {', '.join(artifacts[:limit])}")
        if lands:
            summary_parts.append(f"Lands ({len(lands)} total): {', '.join(lands[:limit])}")

        return '\n'.join(summary_parts)

    async def build_deck(
        self,
        prompt: str,
        colors: Optional[list[str]] = None,
        format: str = "Standard"
    ) -> dict:
        """
        Build a complete deck based on user request.

        Args:
            prompt: User's deck building request
            colors: Optional color restriction
            format: Game format (Standard, Modern, etc.)

        Returns:
            Dict with deck data or error
        """
        if not self.is_available:
            return {
                "success": False,
                "error": "LLM provider is not available. Please install Ollama and pull the model."
            }

        try:
            card_pool = self._get_card_pool_summary(colors)

            user_prompt = DECK_BUILD_PROMPT.format(
                format=format,
                user_request=prompt,
                colors=', '.join(colors) if colors else 'any',
                card_pool_summary=card_pool
            )

            result = await self.provider.complete_json(
                prompt=user_prompt,
                schema=DECK_SCHEMA,
                system=DECK_BUILD_SYSTEM,
                temperature=0.3
            )

            # Validate the deck
            deck_data = self._validate_deck_data(result)

            return {
                "success": True,
                "deck": deck_data
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    async def suggest_cards(
        self,
        deck_name: str,
        archetype: str,
        colors: list[str],
        mainboard: list[dict],
        sideboard: list[dict],
        prompt: str
    ) -> dict:
        """
        Suggest improvements for an existing deck.

        Args:
            deck_name: Name of the deck
            archetype: Deck archetype
            colors: Deck colors
            mainboard: Current mainboard
            sideboard: Current sideboard
            prompt: User's improvement request

        Returns:
            Dict with suggestions or error
        """
        if not self.is_available:
            return {
                "success": False,
                "error": "LLM provider is not available."
            }

        try:
            # Calculate stats
            total_cards = sum(e['qty'] for e in mainboard)
            land_count = sum(
                e['qty'] for e in mainboard
                if any(kw in e['card'] for kw in ['Island', 'Forest', 'Plains', 'Mountain', 'Swamp', 'Land'])
            )
            creature_count = 0
            total_cmc = 0

            for entry in mainboard:
                card_def = ALL_CARDS.get(entry['card'])
                if card_def:
                    if 'CREATURE' in [t.name for t in card_def.characteristics.types]:
                        creature_count += entry['qty']
                    # Simple CMC calculation
                    mana_cost = card_def.characteristics.mana_cost or ''
                    cmc = sum(1 for c in mana_cost if c in 'WUBRG') + sum(int(c) for c in mana_cost if c.isdigit())
                    total_cmc += cmc * entry['qty']

            avg_cmc = total_cmc / (total_cards - land_count) if total_cards > land_count else 0

            # Format mainboard/sideboard for prompt
            mainboard_str = '\n'.join(f"{e['qty']}x {e['card']}" for e in mainboard)
            sideboard_str = '\n'.join(f"{e['qty']}x {e['card']}" for e in sideboard) if sideboard else "Empty"

            # Get available cards
            available = self._get_card_pool_summary(colors)

            user_prompt = DECK_SUGGEST_PROMPT.format(
                deck_name=deck_name,
                archetype=archetype,
                colors=', '.join(colors),
                mainboard_list=mainboard_str,
                sideboard_list=sideboard_str,
                avg_cmc=f"{avg_cmc:.1f}",
                land_count=land_count,
                creature_count=creature_count,
                user_request=prompt,
                available_cards=available
            )

            result = await self.provider.complete_json(
                prompt=user_prompt,
                schema=SUGGEST_SCHEMA,
                system=DECK_SUGGEST_SYSTEM,
                temperature=0.3
            )

            return {
                "success": True,
                "suggestions": result
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    async def polish_deck(
        self,
        skeleton: Deck,
        *,
        set_codes: list[str],
        user_hint: str = "",
    ) -> dict:
        """
        Refine a heuristic skeleton with up to 6 mainboard swaps, a flavor name,
        and a 15-card sideboard. Validates LLM output against the resolved pool
        and skeleton color identity, dropping any swaps that would change the
        mana base, exceed 4-of, leave the pool, or violate color identity.

        Args:
            skeleton: A complete, validated Deck (from build_heuristic_deck).
            set_codes: Set codes used to build the skeleton (for the resolved pool).
            user_hint: Optional free-form hint to bias the LLM polish.

        Returns:
            Dict with:
              - success: bool
              - deck: dict (polished Deck.to_dict())
              - swaps: list[dict] (audit trail of accepted swaps)
              - error: str (only on failure)
        """
        if not self.is_available:
            return {
                "success": False,
                "error": "LLM provider is not available.",
                "deck": skeleton.to_dict(),
                "swaps": [],
            }

        # Resolve the same card pool the heuristic builder used so we can
        # validate "in" cards exist before applying any swap.
        pool: dict = {}
        for code in set_codes:
            cards = get_cards_in_set(code)
            for name, card_def in cards.items():
                # Earlier set codes win on collision (matches W1 pool resolver).
                if name not in pool:
                    pool[name] = card_def

        # Color identity for skeleton, e.g. {Color.RED}.
        color_map = {
            'W': Color.WHITE,
            'U': Color.BLUE,
            'B': Color.BLACK,
            'R': Color.RED,
            'G': Color.GREEN,
        }
        color_set = {color_map[c] for c in skeleton.colors if c in color_map}

        try:
            card_pool_summary = self._get_card_pool_summary(skeleton.colors)
            mainboard_str = '\n'.join(
                f"{e.quantity}x {e.card_name}" for e in skeleton.mainboard
            )

            user_prompt = DECK_POLISH_PROMPT.format(
                deck_name=skeleton.name,
                archetype=skeleton.archetype,
                colors=', '.join(skeleton.colors),
                set_codes=', '.join(set_codes),
                user_hint=user_hint,
                mainboard_list=mainboard_str,
                card_pool_summary=card_pool_summary,
            )

            result = await self.provider.complete_json(
                prompt=user_prompt,
                schema=POLISH_SCHEMA,
                system=DECK_POLISH_SYSTEM,
                temperature=0.3,
            )
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
                "deck": skeleton.to_dict(),
                "swaps": [],
            }

        return self._apply_polish(skeleton, result, pool, color_set)

    def _apply_polish(
        self,
        skeleton: Deck,
        polish: dict,
        pool: dict,
        color_set: set,
    ) -> dict:
        """
        Validate an LLM polish payload against the skeleton + pool and apply it.

        Validation rules:
        - Drop swap where `out` not in mainboard at >= qty.
        - Drop swap where `in` not in resolved pool or violates color identity.
        - Drop swap where `out` is a basic land (mana base must not change).
        - Cap accepted swap count at 6.
        - If sideboard total > 15, truncate. Clamp any sideboard qty > 4 to 4.

        Returns dict { success, deck, swaps }.
        """
        # Build a working mutable copy of the mainboard keyed by card name.
        mainboard_qty: dict[str, int] = {}
        for entry in skeleton.mainboard:
            mainboard_qty[entry.card_name] = mainboard_qty.get(entry.card_name, 0) + entry.quantity

        basic_lands = {'Plains', 'Island', 'Swamp', 'Mountain', 'Forest'}
        accepted_swaps: list[dict] = []

        for raw_swap in polish.get("swaps", []) or []:
            if len(accepted_swaps) >= 6:
                break
            if not isinstance(raw_swap, dict):
                continue

            out_name = raw_swap.get("out") or ""
            in_name = raw_swap.get("in") or ""
            try:
                qty = int(raw_swap.get("qty", 1))
            except (TypeError, ValueError):
                qty = 1
            if qty < 1:
                continue
            reason = raw_swap.get("reason", "")

            if not out_name or not in_name:
                continue

            # Drop: never modify the mana base.
            if out_name in basic_lands or in_name in basic_lands:
                continue

            # Drop: out card not present at requested qty.
            if mainboard_qty.get(out_name, 0) < qty:
                continue

            # Drop: in card not in resolved pool.
            in_card = pool.get(in_name)
            if in_card is None:
                continue

            # Drop: in card violates color identity.
            in_colors = in_card.characteristics.colors or set()
            if color_set and in_colors and not in_colors.issubset(color_set):
                continue

            # Apply the swap to working state.
            mainboard_qty[out_name] = mainboard_qty.get(out_name, 0) - qty
            if mainboard_qty[out_name] <= 0:
                mainboard_qty.pop(out_name, None)
            mainboard_qty[in_name] = mainboard_qty.get(in_name, 0) + qty

            accepted_swaps.append({
                "out": out_name,
                "in": in_name,
                "qty": qty,
                "reason": reason,
            })

        # Reassemble mainboard preserving original ordering as much as possible,
        # then append any newly added card names at the end.
        seen: set[str] = set()
        new_mainboard: list[DeckEntry] = []
        for entry in skeleton.mainboard:
            if entry.card_name in seen:
                continue
            qty = mainboard_qty.get(entry.card_name, 0)
            if qty > 0:
                new_mainboard.append(DeckEntry(card_name=entry.card_name, quantity=qty))
                seen.add(entry.card_name)
        for name, qty in mainboard_qty.items():
            if name in seen or qty <= 0:
                continue
            new_mainboard.append(DeckEntry(card_name=name, quantity=qty))
            seen.add(name)

        # Validate sideboard: drop unknown cards, clamp qty to 4, truncate to 15 total.
        sideboard_entries: list[DeckEntry] = []
        sideboard_total = 0
        for raw_entry in polish.get("sideboard", []) or []:
            if not isinstance(raw_entry, dict):
                continue
            card_name = raw_entry.get("card") or ""
            try:
                qty = int(raw_entry.get("qty", 1))
            except (TypeError, ValueError):
                qty = 1
            if qty < 1 or not card_name:
                continue
            # Card must be in the resolved pool.
            in_card = pool.get(card_name)
            if in_card is None:
                continue
            # Color identity guard.
            sb_colors = in_card.characteristics.colors or set()
            if color_set and sb_colors and not sb_colors.issubset(color_set):
                continue
            qty = min(qty, 4)
            # Truncate so the total never exceeds 15.
            remaining = 15 - sideboard_total
            if remaining <= 0:
                break
            qty = min(qty, remaining)
            if qty <= 0:
                continue
            sideboard_entries.append(DeckEntry(card_name=card_name, quantity=qty))
            sideboard_total += qty

        polished = Deck(
            name=polish.get("name") or skeleton.name,
            archetype=skeleton.archetype,
            colors=list(skeleton.colors),
            description=polish.get("description") or skeleton.description,
            mainboard=new_mainboard,
            sideboard=sideboard_entries,
            author=skeleton.author,
            source=skeleton.source,
            format=skeleton.format,
        )

        return {
            "success": True,
            "deck": polished.to_dict(),
            "swaps": accepted_swaps,
        }

    def _validate_deck_data(self, data: dict) -> dict:
        """
        Validate and clean up deck data from LLM.

        Args:
            data: Raw deck data from LLM

        Returns:
            Validated deck data
        """
        # Ensure required fields
        deck = {
            "name": data.get("name", "AI Generated Deck"),
            "archetype": data.get("archetype", "Aggro"),
            "colors": data.get("colors", []),
            "description": data.get("description", ""),
            "mainboard": [],
            "sideboard": [],
            "explanation": data.get("explanation", "")
        }

        # Validate mainboard entries
        for entry in data.get("mainboard", []):
            if isinstance(entry, dict):
                card_name = entry.get("card", "")
                qty = entry.get("qty", 1)

                # Check if card exists
                if card_name in ALL_CARDS:
                    deck["mainboard"].append({
                        "card": card_name,
                        "qty": min(max(1, qty), 4) if "Basic" not in card_name else qty
                    })

        # Validate sideboard entries
        for entry in data.get("sideboard", []):
            if isinstance(entry, dict):
                card_name = entry.get("card", "")
                qty = entry.get("qty", 1)

                if card_name in ALL_CARDS:
                    deck["sideboard"].append({
                        "card": card_name,
                        "qty": min(max(1, qty), 4)
                    })

        return deck


# Global service instance
llm_deckbuilder = LLMDeckBuilderService()
