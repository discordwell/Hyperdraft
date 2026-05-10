"""ABYS Leviathans archetype: giant pressure threats."""

from __future__ import annotations

from ._mechanics import (
    DepthBand,
    abys_action,
    abys_crew,
    abys_doctrine,
    abys_vessel,
    action_damage,
    action_draw_charge,
    compose_setups,
    make_formation_attack_setup,
    make_pressure_count_setup,
    make_pressure_setup,
    make_salvage_setup,
    make_simple_activated_setup,
    make_vent_setup,
)


LEVIATHAN_CARDS = {
    "Abyss Larva": abys_vessel("Abyss Larva", power=0, hull=3, cost="{2S}", subtypes={"Leviathan"}, default_depth=DepthBand.MID, keywords={"bottom_crawler"}, setup_interceptors=make_pressure_setup(power=1), text="Pressure +1/+0."),
    "Pressure Calf": abys_vessel("Pressure Calf", power=2, hull=3, cost="{2T,2S}", subtypes={"Leviathan"}, default_depth=DepthBand.MID, keywords={"bottom_crawler"}, setup_interceptors=make_vent_setup(sc=1), text="Vent - gain 1 SC."),
    "Trench Maw": abys_vessel("Trench Maw", power=3, hull=4, cost="{4T,1S}", subtypes={"Leviathan"}, default_depth=DepthBand.DEEP, keywords={"homing"}, setup_interceptors=make_pressure_setup(power=1), text="Homing. Pressure +1/+0."),
    "Pressure Crown": abys_crew("Pressure Crown", cost="{2S}", power_mod=1, toughness_mod=2, keywords_to_grant={"homing"}, text="Equipped Vessel gets +1/+2 and homing."),
    "Abyssal Feeding": abys_action("Abyssal Feeding", cost="{2S}", cast_effect_fn=action_draw_charge(1, sc=2), text="Draw 1 and gain 2 SC."),
    "Crushfield Roar": abys_action("Crushfield Roar", cost="{3T,1S}", cast_effect_fn=action_damage(3), text="Deal 3 to an opposing Vessel."),
    "Leviathan Wake": abys_doctrine("Leviathan Wake", cost="{3S}", setup_interceptors=make_pressure_count_setup(), text="Source gets +1/+0 for each deep friendly Vessel, capped at +3."),
    "Old Hundred Fathoms": abys_vessel("Old Hundred Fathoms", power=7, hull=7, cost="{5T,3S}", subtypes={"Leviathan", "Legendary"}, default_depth=DepthBand.DEEP, keywords={"homing", "bottom_crawler"}, setup_interceptors=compose_setups(make_pressure_setup(power=2), make_salvage_setup(draw=2)), text="Homing. Pressure +2/+0. Salvage - draw 2."),
    "World-Shell Sleeper": abys_vessel("World-Shell Sleeper", power=5, hull=9, cost="{4T,4S}", subtypes={"Leviathan"}, default_depth=DepthBand.CRUSH, keywords={"bottom_crawler"}, setup_interceptors=make_simple_activated_setup(cost="{2S}", description="Deal 2 damage.", damage=2), text="{2S}: deal 2 to a target opposing Vessel."),
    "Lantern-Back Colossus": abys_vessel("Lantern-Back Colossus", power=6, hull=6, cost="{5T,2S}", subtypes={"Leviathan"}, default_depth=DepthBand.DEEP, keywords={"homing"}, setup_interceptors=make_formation_attack_setup(n=1, flag_damage=2), text="Formation 1 - deal 2 to opposing Flagship."),
}

_SPECS = [
    ("Deep Plankton Grazer", 2, 5, "{2S}", DepthBand.DEEP, {"Leviathan"}, {"bottom_crawler"}, make_pressure_setup(power=1)),
    ("Blackwater Eel", 2, 3, "{3T,1S}", DepthBand.MID, {"Leviathan"}, set(), make_vent_setup(sc=1)),
    ("Crush-Tusk Juvenile", 4, 3, "{3T}", DepthBand.PERISCOPE, {"Leviathan"}, set(), None),
    ("Cathedral Ray", 3, 6, "{3S}", DepthBand.DEEP, {"Leviathan"}, {"bottom_crawler"}, make_pressure_setup(hull=1)),
    ("Moonless Angler", 3, 4, "{3T,2S}", DepthBand.DEEP, {"Leviathan"}, {"homing"}, make_pressure_setup(power=1)),
    ("Ridgeback Whale", 5, 5, "{4T,1S}", DepthBand.MID, {"Leviathan"}, set(), make_vent_setup(tc=1)),
    ("Grave Current Serpent", 3, 7, "{3T,2S}", DepthBand.DEEP, {"Leviathan"}, {"bottom_crawler"}, make_salvage_setup(sc=2)),
    ("White-Eye Horror", 5, 4, "{5T,2S}", DepthBand.DEEP, {"Leviathan"}, {"homing"}, make_pressure_setup(power=1)),
    ("Silent Giant", 5, 6, "{4T,2S}", DepthBand.DEEP, {"Leviathan"}, {"silent_running"}, make_pressure_setup(power=1, hull=1)),
    ("Brine Titan", 7, 5, "{5T,2S}", DepthBand.MID, {"Leviathan"}, {"homing"}, None),
    ("Vent-Eater Kraken", 6, 7, "{4T,3S}", DepthBand.CRUSH, {"Leviathan", "Vent"}, {"bottom_crawler"}, make_vent_setup(tc=1, sc=1)),
    ("Crush Palace Guardian", 4, 8, "{4S}", DepthBand.CRUSH, {"Leviathan"}, {"defender", "bottom_crawler"}, make_pressure_setup(hull=2)),
    ("Abyss Herdmother", 5, 8, "{5T,3S}", DepthBand.DEEP, {"Leviathan"}, {"homing"}, compose_setups(make_salvage_setup(draw=1), make_pressure_setup(power=1))),
    ("No-Light Devourer", 8, 6, "{6T,2S}", DepthBand.CRUSH, {"Leviathan"}, {"homing", "bottom_crawler"}, make_pressure_setup(power=2)),
    ("Continental Bite", 9, 9, "{7T,3S}", DepthBand.CRUSH, {"Leviathan"}, {"homing"}, make_salvage_setup(draw=3)),
]

for name, power, hull, cost, depth, subs, keywords, setup in _SPECS:
    LEVIATHAN_CARDS[name] = abys_vessel(name, power=power, hull=hull, cost=cost, subtypes=subs, default_depth=depth, keywords=keywords, setup_interceptors=setup, text="Large pressure threat.")

LEVIATHAN_CARDS.update({
    "Abyss Harness": abys_crew("Abyss Harness", cost="{2T,1S}", power_mod=2, toughness_mod=1, text="Equipped Vessel gets +2/+1."),
    "Whale-Fall Map": abys_action("Whale-Fall Map", cost="{1S}", cast_effect_fn=action_draw_charge(2), text="Draw 2."),
    "Crush Ration": abys_action("Crush Ration", cost="{1S}", cast_effect_fn=action_draw_charge(1, sc=1), text="Draw 1 and gain 1 SC."),
    "Lure Chain": abys_crew("Lure Chain", cost="{1T,1S}", power_mod=1, keywords_to_grant={"reach"}, text="Equipped Vessel gets +1/+0 and reach."),
    "Apex Sounding": abys_doctrine("Apex Sounding", cost="{2T,2S}", setup_interceptors=make_formation_attack_setup(n=1, power=1), text="A narrow simulated anthem body for Leviathan attacks."),
})

__all__ = ["LEVIATHAN_CARDS"]
