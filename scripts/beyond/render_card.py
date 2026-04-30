"""
Beyond Ravnica — PIL compositor for Pokemon SV-style card frames.

Takes a CardDefinition + an art PNG and produces a final card PNG mimicking
the modern Scarlet & Violet "ex" layout. Two main layouts:

  - Pokemon (Basic / Stage 1 / Stage 2 ex)
  - Trainer  (Item / Supporter / Stadium)

Run directly to render the 8-card Izzet PoC with placeholder solid-color art:
    python scripts/beyond/render_card.py
"""

from __future__ import annotations

import os
import sys
import textwrap
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

# Imports after sys.path adjustment
from src.engine.types import CardType, PokemonType  # noqa: E402

# -----------------------------------------------------------------------------
# Card geometry — ~5:7 ratio matching standard digital Pokemon TCG
# -----------------------------------------------------------------------------
CARD_W = 660
CARD_H = 920
PAD = 22       # outer padding inside the silver border
ART_TOP = 110
ART_BOTTOM = 540   # 430px tall art window for Pokemon

TYPE_COLORS = {
    "R": (228, 84, 56),       # Fire
    "W": (62, 142, 222),      # Water
    "G": (104, 188, 90),      # Grass
    "L": (246, 208, 54),      # Lightning
    "P": (174, 96, 188),      # Psychic
    "F": (202, 134, 70),      # Fighting
    "D": (88, 76, 112),       # Darkness
    "M": (148, 152, 162),     # Metal
    "C": (230, 220, 198),     # Colorless
}

TRAINER_BANNER = {
    "ITEM": (62, 142, 222),
    "SUPPORTER": (228, 138, 56),
    "STADIUM": (158, 110, 70),
}

# macOS system fonts; close-enough proxies for Pokemon's Futura Std
FONT_REGULAR = "/System/Library/Fonts/Avenir Next.ttc"
FONT_BOLD = "/System/Library/Fonts/Avenir Next.ttc"


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = FONT_BOLD if bold else FONT_REGULAR
    # Avenir Next.ttc index 0 is regular, 1 is italic, 2 is bold; close enough
    return ImageFont.truetype(path, size, index=2 if bold else 0)


def _italic(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_REGULAR, size, index=1)


# -----------------------------------------------------------------------------
# Energy icon — colored circle with single-letter inside (good enough for PoC)
# -----------------------------------------------------------------------------
def draw_energy_icon(draw: ImageDraw.ImageDraw, xy, energy_type: str, radius: int = 18):
    cx, cy = xy
    fill = TYPE_COLORS.get(energy_type, (180, 180, 180))
    # Outer ring
    draw.ellipse([cx - radius - 2, cy - radius - 2, cx + radius + 2, cy + radius + 2],
                 fill=(40, 40, 40))
    draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=fill)
    # Letter
    font = _font(int(radius * 1.2), bold=True)
    label = energy_type
    bbox = draw.textbbox((0, 0), label, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text((cx - tw / 2, cy - th / 2 - 2), label, fill=(255, 255, 255), font=font)


# -----------------------------------------------------------------------------
# Backdrop — bright type-colored gradient with silver-foil border
# -----------------------------------------------------------------------------
def make_backdrop(primary_rgb, secondary_rgb=None) -> Image.Image:
    img = Image.new("RGB", (CARD_W, CARD_H), (240, 240, 240))
    draw = ImageDraw.Draw(img)
    secondary_rgb = secondary_rgb or tuple(min(255, int(c * 1.18)) for c in primary_rgb)
    # Vertical gradient from primary at top to secondary at bottom
    for y in range(CARD_H):
        t = y / CARD_H
        r = int(primary_rgb[0] * (1 - t) + secondary_rgb[0] * t)
        g = int(primary_rgb[1] * (1 - t) + secondary_rgb[1] * t)
        b = int(primary_rgb[2] * (1 - t) + secondary_rgb[2] * t)
        draw.line([(0, y), (CARD_W, y)], fill=(r, g, b))
    # Inner ivory panel
    panel_pad = PAD
    draw.rounded_rectangle(
        [panel_pad, panel_pad, CARD_W - panel_pad, CARD_H - panel_pad],
        radius=22, fill=(252, 248, 235), outline=(60, 50, 40), width=2,
    )
    return img


def paste_art(img: Image.Image, art_path: Optional[str], top: int, bottom: int):
    box_l = PAD + 14
    box_r = CARD_W - PAD - 14
    box_t = top
    box_b = bottom
    box_w = box_r - box_l
    box_h = box_b - box_t

    if art_path and os.path.exists(art_path):
        art = Image.open(art_path).convert("RGB")
        art_ratio = art.width / art.height
        target_ratio = box_w / box_h
        if art_ratio > target_ratio:
            new_h = box_h
            new_w = int(box_h * art_ratio)
        else:
            new_w = box_w
            new_h = int(box_w / art_ratio)
        art = art.resize((new_w, new_h), Image.LANCZOS)
        ox = (new_w - box_w) // 2
        oy = (new_h - box_h) // 2
        art = art.crop((ox, oy, ox + box_w, oy + box_h))
        img.paste(art, (box_l, box_t))
    else:
        # Placeholder: diagonal-stripe texture in muted gray
        draw = ImageDraw.Draw(img)
        draw.rectangle([box_l, box_t, box_r, box_b], fill=(60, 60, 70))
        for k in range(-box_h, box_w, 18):
            draw.line([(box_l + k, box_t), (box_l + k + box_h, box_b)],
                      fill=(80, 80, 90), width=2)
        draw.text((box_l + 14, box_t + 14), "[ART PLACEHOLDER]",
                  fill=(220, 220, 220), font=_font(20, bold=True))

    # Frame around art
    ImageDraw.Draw(img).rectangle([box_l - 2, box_t - 2, box_r + 1, box_b + 1],
                                   outline=(40, 30, 20), width=3)


def wrap_text(draw, text, font, max_width):
    words = text.split()
    lines = []
    current = []
    for w in words:
        trial = " ".join(current + [w])
        if draw.textlength(trial, font=font) <= max_width:
            current.append(w)
        else:
            if current:
                lines.append(" ".join(current))
            current = [w]
    if current:
        lines.append(" ".join(current))
    return lines


# -----------------------------------------------------------------------------
# Pokemon card layout
# -----------------------------------------------------------------------------
def render_pokemon(card_def, art_path: Optional[str] = None) -> Image.Image:
    ptype = card_def.pokemon_type or "C"
    primary = TYPE_COLORS.get(ptype, (200, 200, 200))
    img = make_backdrop(primary)
    draw = ImageDraw.Draw(img)

    # ----- TOP BAR -----
    stage_text = card_def.evolution_stage or "Basic"
    if card_def.evolves_from:
        stage_text = f"{stage_text} — Evolves from {card_def.evolves_from}"
    draw.text((PAD + 16, PAD + 10), stage_text,
              fill=(40, 30, 20), font=_font(18, bold=True))

    # Name (large, possibly with " ex" suffix styled)
    name_font = _font(34, bold=True)
    name = card_def.name
    draw.text((PAD + 16, PAD + 40), name,
              fill=(20, 20, 20), font=name_font)

    # HP and type icon (right side)
    hp_text = f"HP {card_def.hp}"
    hp_font = _font(28, bold=True)
    hp_w = draw.textlength(hp_text, font=hp_font)
    draw.text((CARD_W - PAD - 60 - hp_w, PAD + 14), hp_text,
              fill=(180, 30, 30), font=hp_font)
    draw_energy_icon(draw, (CARD_W - PAD - 30, PAD + 30), ptype, radius=22)

    # ----- ART -----
    paste_art(img, art_path, ART_TOP, ART_BOTTOM)

    # ----- STATS PANEL -----
    cursor_y = ART_BOTTOM + 14

    # Ability (if present)
    if card_def.ability:
        ab = card_def.ability
        # Banner
        draw.rounded_rectangle(
            [PAD + 14, cursor_y, CARD_W - PAD - 14, cursor_y + 30],
            radius=6, fill=(220, 60, 60), outline=(120, 30, 30), width=2,
        )
        draw.text((PAD + 24, cursor_y + 4), "Ability",
                  fill=(255, 255, 255), font=_font(16, bold=True))
        draw.text((PAD + 110, cursor_y + 4), ab.get("name", ""),
                  fill=(255, 255, 255), font=_font(20, bold=True))
        cursor_y += 36
        for line in wrap_text(draw, ab.get("text", ""), _font(14),
                               CARD_W - 2 * PAD - 30):
            draw.text((PAD + 18, cursor_y), line, fill=(40, 30, 20),
                      font=_font(14))
            cursor_y += 18
        cursor_y += 4

    # Attacks
    for attack in card_def.attacks:
        atk_y_start = cursor_y
        # Energy cost icons on left
        cost = attack.get("cost", [])
        x_icon = PAD + 20
        flat = []
        for c in cost:
            flat.extend([c["type"]] * c["count"])
        for i, et in enumerate(flat):
            draw_energy_icon(draw, (x_icon + i * 26, cursor_y + 14), et, radius=11)
        # Attack name (middle) and damage (right)
        name_x = PAD + 20 + max(len(flat), 1) * 26 + 8
        draw.text((name_x, cursor_y + 2), attack["name"],
                  fill=(20, 20, 20), font=_font(20, bold=True))
        dmg = attack.get("damage")
        if dmg:
            dmg_text = str(dmg)
            dmg_font = _font(28, bold=True)
            dmg_w = draw.textlength(dmg_text, font=dmg_font)
            draw.text((CARD_W - PAD - 16 - dmg_w, cursor_y),
                      dmg_text, fill=(180, 30, 30), font=dmg_font)
        cursor_y += 30
        # Attack text (italic flavor of the effect)
        if attack.get("text"):
            for line in wrap_text(draw, attack["text"], _font(12, bold=False),
                                   CARD_W - 2 * PAD - 30):
                draw.text((name_x, cursor_y), line,
                          fill=(60, 50, 40), font=_font(12))
                cursor_y += 14
        cursor_y += 6

    # ----- BOTTOM STRIP: Weakness / Resistance / Retreat -----
    strip_y = CARD_H - PAD - 96
    draw.line([(PAD + 14, strip_y), (CARD_W - PAD - 14, strip_y)],
              fill=(120, 100, 80), width=1)

    cell_w = (CARD_W - 2 * PAD - 28) // 3
    labels = ["weakness", "resistance", "retreat"]
    for idx, lbl in enumerate(labels):
        x0 = PAD + 14 + idx * cell_w
        draw.text((x0 + 8, strip_y + 6), lbl,
                  fill=(80, 70, 60), font=_font(11, bold=True))
    # Weakness icon
    if card_def.weakness_type:
        draw_energy_icon(draw, (PAD + 14 + 18, strip_y + 38),
                         card_def.weakness_type, radius=12)
        mod = card_def.weakness_modifier or "x2"
        draw.text((PAD + 14 + 36, strip_y + 30), mod,
                  fill=(20, 20, 20), font=_font(14, bold=True))
    # Resistance
    if card_def.resistance_type:
        draw_energy_icon(draw, (PAD + 14 + cell_w + 18, strip_y + 38),
                         card_def.resistance_type, radius=12)
        mod = str(card_def.resistance_modifier) if card_def.resistance_modifier else "-30"
        draw.text((PAD + 14 + cell_w + 36, strip_y + 30), mod,
                  fill=(20, 20, 20), font=_font(14, bold=True))
    # Retreat: colorless icons
    rc = card_def.retreat_cost or 0
    for i in range(rc):
        draw_energy_icon(draw,
                         (PAD + 14 + 2 * cell_w + 18 + i * 22, strip_y + 38),
                         "C", radius=10)

    # ex rule reminder (if ex)
    if card_def.is_ex:
        rule_y = CARD_H - PAD - 50
        draw.text((PAD + 16, rule_y),
                  "When your Pokemon ex is Knocked Out, your opponent takes 2 Prize cards.",
                  fill=(80, 30, 20), font=_italic(11))

    # Flavor text (Pokedex blurb) — small italic above the bottom rule
    if card_def.text and not card_def.is_ex:
        fl_y = CARD_H - PAD - 50
        for line in wrap_text(draw, card_def.text, _italic(12),
                               CARD_W - 2 * PAD - 30):
            draw.text((PAD + 16, fl_y), line,
                      fill=(80, 60, 40), font=_italic(12))
            fl_y += 15

    # Footer
    draw.text((PAD + 16, CARD_H - PAD - 22),
              "Beyond Ravnica · Izzet · No.001",
              fill=(80, 70, 60), font=_font(11, bold=True))
    draw.text((CARD_W - PAD - 90, CARD_H - PAD - 22),
              "© Hyperdraft", fill=(80, 70, 60), font=_font(11))

    return img


# -----------------------------------------------------------------------------
# Trainer card layout
# -----------------------------------------------------------------------------
def render_trainer(card_def, art_path: Optional[str] = None) -> Image.Image:
    types = card_def.characteristics.types
    if CardType.STADIUM in types:
        kind = "STADIUM"
    elif CardType.SUPPORTER in types:
        kind = "SUPPORTER"
    else:
        kind = "ITEM"
    banner = TRAINER_BANNER[kind]
    img = make_backdrop(banner)
    draw = ImageDraw.Draw(img)

    # Banner
    draw.rounded_rectangle(
        [PAD + 14, PAD + 16, CARD_W - PAD - 14, PAD + 56],
        radius=10, fill=banner, outline=(30, 30, 30), width=2,
    )
    draw.text((PAD + 26, PAD + 22), kind.title(),
              fill=(255, 255, 255), font=_font(22, bold=True))

    # Name
    draw.text((PAD + 16, PAD + 70),
              card_def.name, fill=(20, 20, 20), font=_font(30, bold=True))

    # Art (smaller for trainers — top half)
    paste_art(img, art_path, PAD + 130, PAD + 480)

    # Effect text (large block)
    text_y = PAD + 500
    for line in wrap_text(draw, card_def.text or "", _font(16),
                           CARD_W - 2 * PAD - 30):
        draw.text((PAD + 20, text_y), line,
                  fill=(30, 25, 20), font=_font(16))
        text_y += 22

    # Footer
    draw.text((PAD + 16, CARD_H - PAD - 22),
              f"Beyond Ravnica · {kind.title()}",
              fill=(80, 70, 60), font=_font(11, bold=True))
    draw.text((CARD_W - PAD - 90, CARD_H - PAD - 22),
              "© Hyperdraft", fill=(80, 70, 60), font=_font(11))

    return img


# -----------------------------------------------------------------------------
# Dispatcher
# -----------------------------------------------------------------------------
def render_card(card_def, art_path: Optional[str] = None) -> Image.Image:
    types = card_def.characteristics.types
    if CardType.POKEMON in types:
        return render_pokemon(card_def, art_path)
    if CardType.TRAINER in types:
        return render_trainer(card_def, art_path)
    raise ValueError(f"Unknown card type for {card_def.name}: {types}")


# -----------------------------------------------------------------------------
# Direct-run smoke: render the 8 Izzet cards with placeholder art
# -----------------------------------------------------------------------------
_ART_FILE_MAP = {
    "Nivlet": "nivlet.png",
    "Mizzling": "mizzling.png",
    "Niv-Mizzet, Parun ex": "niv_mizzet_parun_ex.png",
    "Goblin Electromancer": "goblin_electromancer.png",
    "Mercurial Mageling": "mercurial_mageling.png",
    "Niv-Mizzet's Tower": "niv_mizzets_tower.png",
    "Ral, Storm Conduit": "ral_storm_conduit.png",
    "Izzet Signet": "izzet_signet.png",
}


def _smoke():
    from src.cards.pokemon.beyond.ravnica import BEYOND_RAVNICA_IZZET

    art_dir = PROJECT_ROOT / "assets" / "card_art" / "beyond" / "ravnica"
    out_dir = art_dir / "composed"
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, card_def in BEYOND_RAVNICA_IZZET.items():
        art_filename = _ART_FILE_MAP.get(name)
        art_path = str(art_dir / art_filename) if art_filename else None
        if art_path and not os.path.exists(art_path):
            art_path = None
        img = render_card(card_def, art_path=art_path)
        safe_name = name.replace(",", "").replace(" ", "_").replace("'", "")
        out_path = out_dir / f"{safe_name}.png"
        img.save(out_path)
        marker = "[ART]" if art_path else "[PLACEHOLDER]"
        print(f"  {marker:14}  {name} -> {out_path.name}")
    print(f"\nWrote {len(BEYOND_RAVNICA_IZZET)} card PNGs to {out_dir}")


if __name__ == "__main__":
    _smoke()
