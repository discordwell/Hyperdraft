"""ABYS Thermals archetype: vent-ramp midrange.

Thermal decks use Sonar to dive, then Vent triggers refund charges once their
fleet reaches DEEP/CRUSH. Costing follows the Depths curve: 1-cost 2/1 or
0/3, 2-cost 2/3 with a conditional trigger, 4+ cost for repeatable charge
engines and homing finishers.
"""

from __future__ import annotations

from ._mechanics import (
    DepthBand,
    abys_action,
    abys_crew,
    abys_doctrine,
    abys_vessel,
    abys_weapon,
    action_damage,
    action_draw_charge,
    compose_setups,
    make_depth_end_charge_setup,
    make_pressure_setup,
    make_same_depth_lord_setup,
    make_simple_activated_setup,
    make_vent_setup,
)


THERMAL_CARDS = {
    "Vent Minnow": abys_vessel(
        "Vent Minnow", power=1, hull=2, cost="{1S}", subtypes={"Submarine", "Vent"},
        default_depth=DepthBand.MID, keywords={"bottom_crawler"},
        setup_interceptors=make_vent_setup(sc=1),
        text="Vent - When this dives to DEEP/CRUSH, gain 1 SC.",
    ),
    "Sulfur Skiff": abys_vessel(
        "Sulfur Skiff", power=2, hull=1, cost="{1T}", subtypes={"Submarine", "Vent"},
        default_depth=DepthBand.SURFACE, setup_interceptors=make_vent_setup(tc=1),
        text="Vent - When this dives to DEEP/CRUSH, gain 1 TC.",
    ),
    "Rift Geologist": abys_crew(
        "Rift Geologist", cost="{1S}", toughness_mod=1, keywords_to_grant={"bottom_crawler"},
        text="Equipped Vessel gets +0/+1 and bottom_crawler.",
    ),
    "Thermal Plume": abys_action(
        "Thermal Plume", cost="{1S}", cast_effect_fn=action_draw_charge(1, sc=1),
        text="Draw 1 and gain 1 SC.",
    ),
    "Black Smoker": abys_vessel(
        "Black Smoker", power=2, hull=4, cost="{2S}", subtypes={"Submarine", "Vent"},
        default_depth=DepthBand.DEEP,
        setup_interceptors=compose_setups(make_vent_setup(sc=1, pump=1), make_pressure_setup(power=1)),
        text="Vent - gain 1 SC and +1 power EOT. Pressure +1/+0.",
    ),
    "Magma Intake": abys_weapon(
        "Magma Intake", cost="{1T,1S}", power_mod=1,
        granted_activated_abilities=[{
            "cost": "{1S}",
            "description": "Gain 1 TC.",
            "effect": lambda game, player_id, source, targets: [],
        }],
        text="Equipped Vessel gets +1/+0. ABYS approximates the printed charge valve on dedicated Vessels instead.",
    ),
    "Ventfield Doctrine": abys_doctrine(
        "Ventfield Doctrine", cost="{2S}", setup_interceptors=make_depth_end_charge_setup(sc=1),
        text="At your Surface phase, gain 1 SC.",
    ),
    "Geyser Runner": abys_vessel(
        "Geyser Runner", power=2, hull=2, cost="{2T,1S}", subtypes={"Submarine", "Vent"},
        default_depth=DepthBand.MID, keywords={"homing"},
        setup_interceptors=make_vent_setup(tc=1, pump=1),
        text="Homing. Vent - gain 1 TC and +1 power EOT.",
    ),
    "Ridge Foundry": abys_vessel(
        "Ridge Foundry", power=1, hull=5, cost="{3S}", subtypes={"Station", "Vent"},
        default_depth=DepthBand.DEEP,
        setup_interceptors=make_same_depth_lord_setup(subtype="Vent", power=1, hull=0),
        text="Formation engine - your Vent Vessels at this depth get +1/+0.",
    ),
    "Admiral of the Vents": abys_vessel(
        "Admiral of the Vents", power=4, hull=6, cost="{4T,2S}",
        subtypes={"Submarine", "Legendary", "Vent"}, default_depth=DepthBand.MID,
        keywords={"homing"},
        setup_interceptors=compose_setups(make_vent_setup(tc=1, sc=1, draw=1), make_pressure_setup(power=2)),
        text="Homing. Vent - gain 1 TC/1 SC and draw 1. Pressure +2/+0.",
    ),
}


_EXTRA_SPECS = [
    ("Warm Current Scout", 1, 3, "{1S}", DepthBand.PERISCOPE, {"Submarine", "Vent"}, set(), make_vent_setup(sc=1)),
    ("Basalt Nibbler", 2, 2, "{2T}", DepthBand.SURFACE, {"Drone", "Vent"}, set(), None),
    ("Boiling Wake Cutter", 3, 2, "{2T}", DepthBand.SURFACE, {"Destroyer", "Vent"}, {"reach"}, None),
    ("Fumarole Listener", 1, 4, "{2S}", DepthBand.MID, {"Submarine", "Vent"}, {"silent_running"}, make_vent_setup(sc=1)),
    ("Trench Heat Cart", 2, 3, "{2T,1S}", DepthBand.MID, {"Submarine", "Vent"}, set(), make_vent_setup(tc=1)),
    ("Pipejaw Sub", 3, 3, "{3T}", DepthBand.PERISCOPE, {"Submarine", "Vent"}, set(), make_vent_setup(pump=1)),
    ("Molten Battery Tender", 1, 4, "{1T,2S}", DepthBand.DEEP, {"Submarine", "Vent"}, {"bottom_crawler"}, make_depth_end_charge_setup(tc=1)),
    ("Soot Plume Escort", 3, 4, "{3T,1S}", DepthBand.MID, {"Destroyer", "Vent"}, {"reach"}, None),
    ("Abyssal Turbine", 4, 4, "{3T,2S}", DepthBand.DEEP, {"Submarine", "Vent"}, {"homing"}, make_pressure_setup(power=1)),
    ("Kelp-Heat Tender", 2, 5, "{2T,2S}", DepthBand.DEEP, {"Submarine", "Vent"}, {"bottom_crawler"}, make_vent_setup(sc=1, draw=1)),
    ("Riftline Surveyor", 2, 3, "{2S}", DepthBand.MID, {"Submarine", "Vent"}, {"silent_running"}, make_vent_setup(sc=1)),
    ("Smoker-Side Ram", 4, 2, "{3T}", DepthBand.PERISCOPE, {"Submarine", "Vent"}, set(), make_vent_setup(pump=2)),
    ("Lava Shelf Monitor", 2, 6, "{3S}", DepthBand.DEEP, {"Station", "Vent"}, {"defender"}, make_depth_end_charge_setup(sc=1)),
    ("Thermal Needle", 4, 3, "{3T,1S}", DepthBand.MID, {"Submarine", "Vent"}, {"homing"}, make_vent_setup(tc=1)),
    ("Aft Boiler Veteran", 3, 5, "{4T}", DepthBand.PERISCOPE, {"Submarine", "Vent"}, set(), make_pressure_setup(power=1, hull=1)),
]

for name, power, hull, cost, depth, subs, keywords, setup in _EXTRA_SPECS:
    THERMAL_CARDS[name] = abys_vessel(
        name, power=power, hull=hull, cost=cost, subtypes=subs,
        default_depth=depth, keywords=keywords, setup_interceptors=setup,
        text="Vent/pressure support for the Thermals archetype.",
    )

THERMAL_CARDS.update({
    "Rift Valve": abys_action("Rift Valve", cost="{1S}", cast_effect_fn=action_draw_charge(1, tc=1), text="Draw 1 and gain 1 TC."),
    "Boiler Breach": abys_action("Boiler Breach", cost="{2T}", cast_effect_fn=action_damage(2), text="Deal 2 to the lowest-hull opposing Vessel."),
    "Vent Map": abys_action("Vent Map", cost="{1S}", cast_effect_fn=action_draw_charge(2), text="Draw 2."),
    "Superheated Lance": abys_action("Superheated Lance", cost="{3T,1S}", cast_effect_fn=action_damage(4), text="Deal 4 to an opposing Vessel."),
    "Pressure Foreman": abys_crew("Pressure Foreman", cost="{2S}", power_mod=1, toughness_mod=1, text="Equipped Vessel gets +1/+1."),
})

__all__ = ["THERMAL_CARDS"]
