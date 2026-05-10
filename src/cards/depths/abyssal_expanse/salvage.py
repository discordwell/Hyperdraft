"""ABYS Salvage archetype: recursive attrition through sunk Vessels."""

from __future__ import annotations

from ._mechanics import (
    DepthBand,
    abys_action,
    abys_crew,
    abys_doctrine,
    abys_vessel,
    action_create_drones,
    action_draw_charge,
    compose_setups,
    make_depth_end_charge_setup,
    make_damage_flagship_draw_setup,
    make_formation_attack_setup,
    make_salvage_setup,
    make_simple_activated_setup,
)


SALVAGE_CARDS = {
    "Scrap Skimmer": abys_vessel("Scrap Skimmer", power=1, hull=1, cost="{1T}", subtypes={"Drone", "Salvage"}, setup_interceptors=make_salvage_setup(tc=1), text="Salvage - gain 1 TC."),
    "Wreck Lantern": abys_vessel("Wreck Lantern", power=1, hull=3, cost="{1S}", subtypes={"Drone", "Salvage"}, default_depth=DepthBand.MID, setup_interceptors=make_salvage_setup(draw=1), text="Salvage - draw 1."),
    "Hull Picker": abys_vessel("Hull Picker", power=2, hull=2, cost="{2T}", subtypes={"Submarine", "Salvage"}, setup_interceptors=make_salvage_setup(sc=1), text="Salvage - gain 1 SC."),
    "Cable Diver": abys_crew("Cable Diver", cost="{1S}", toughness_mod=1, keywords_to_grant={"silent_running"}, text="Equipped Vessel gets +0/+1 and silent_running."),
    "Jury-Rig": abys_action("Jury-Rig", cost="{1T}", cast_effect_fn=action_draw_charge(1, tc=1), text="Draw 1 and gain 1 TC."),
    "Scrapyard Drone Wave": abys_action("Scrapyard Drone Wave", cost="{1T}", cast_effect_fn=action_create_drones(2), text="Create two 1/1 homing Drone tokens."),
    "Salvage Code": abys_doctrine("Salvage Code", cost="{2T}", setup_interceptors=make_depth_end_charge_setup(tc=1), text="At your Surface phase, gain 1 TC."),
    "Bonefield Tug": abys_vessel("Bonefield Tug", power=2, hull=4, cost="{2T,1S}", subtypes={"Submarine", "Salvage"}, default_depth=DepthBand.MID, setup_interceptors=compose_setups(make_salvage_setup(tc=1, sc=1), make_damage_flagship_draw_setup()), text="Salvage - gain 1 TC/SC. Draw when it damages a Flagship."),
    "Recovery Admiral Nia": abys_vessel("Recovery Admiral Nia", power=4, hull=6, cost="{3T,1S}", subtypes={"Submarine", "Legendary", "Salvage"}, default_depth=DepthBand.PERISCOPE, setup_interceptors=compose_setups(make_salvage_setup(draw=2, drone=True), make_depth_end_charge_setup(drones=1)), text="At your Surface phase create a Drone. Salvage - draw 2 and create a Drone."),
    "Prize Barge": abys_vessel("Prize Barge", power=1, hull=6, cost="{3T}", subtypes={"Carrier", "Salvage"}, default_depth=DepthBand.PERISCOPE, setup_interceptors=make_depth_end_charge_setup(drones=1), text="At your Surface phase create a Drone."),
}

_VESSELS = [
    ("Rusted Knife Sub", 2, 1, "{1T}", DepthBand.SURFACE, {"Submarine", "Salvage"}, set(), make_salvage_setup(tc=1)),
    ("Sunken Ledger Clerk", 1, 3, "{1S}", DepthBand.PERISCOPE, {"Submarine", "Salvage"}, {"silent_running"}, make_salvage_setup(draw=1)),
    ("Patchplate Rover", 2, 3, "{2T}", DepthBand.SURFACE, {"Drone", "Salvage"}, set(), make_salvage_setup(drone=True)),
    ("Broken Compass Boat", 3, 2, "{2T}", DepthBand.SURFACE, {"Submarine", "Salvage"}, set(), None),
    ("Chainhook Veteran", 2, 4, "{2T,1S}", DepthBand.MID, {"Submarine", "Salvage"}, {"reach"}, make_salvage_setup(tc=1)),
    ("Coffin-Weld Mate", 3, 3, "{3T}", DepthBand.PERISCOPE, {"Submarine", "Salvage"}, set(), make_formation_attack_setup(n=1, power=1)),
    ("Deep Locker Tender", 1, 5, "{2S}", DepthBand.DEEP, {"Submarine", "Salvage"}, {"bottom_crawler"}, make_salvage_setup(sc=2)),
    ("Ghost Hull Collector", 3, 4, "{3T,1S}", DepthBand.DEEP, {"Submarine", "Salvage"}, {"silent_running"}, make_salvage_setup(draw=1)),
    ("Anchor-Claw Escort", 4, 3, "{3T,1S}", DepthBand.PERISCOPE, {"Destroyer", "Salvage"}, {"reach"}, None),
    ("Titanic Bone Saw", 5, 4, "{4T,1S}", DepthBand.MID, {"Submarine", "Salvage"}, {"homing"}, make_salvage_setup(tc=2)),
    ("Invoice Wrecker", 2, 5, "{3S}", DepthBand.DEEP, {"Submarine", "Salvage"}, {"bottom_crawler"}, make_salvage_setup(sc=1, draw=1)),
    ("Knotwork Towfish", 3, 3, "{2T,2S}", DepthBand.MID, {"Drone", "Salvage"}, {"homing"}, make_salvage_setup(drone=True)),
    ("Blackbox Cartographer", 2, 4, "{2T,1S}", DepthBand.MID, {"Submarine", "Salvage"}, set(), make_salvage_setup(draw=1)),
    ("Debris Field Scavenger", 4, 5, "{4T,1S}", DepthBand.DEEP, {"Submarine", "Salvage"}, {"bottom_crawler"}, make_salvage_setup(tc=1, sc=1)),
    ("Last Bolt Leviathan", 6, 6, "{5T,2S}", DepthBand.DEEP, {"Leviathan", "Salvage"}, {"homing"}, make_salvage_setup(draw=2, drone=True)),
]

for name, power, hull, cost, depth, subs, keywords, setup in _VESSELS:
    SALVAGE_CARDS[name] = abys_vessel(name, power=power, hull=hull, cost=cost, subtypes=subs, default_depth=depth, keywords=keywords, setup_interceptors=setup, text="Salvage attrition Vessel.")

SALVAGE_CARDS.update({
    "Tow Cable": abys_crew("Tow Cable", cost="{1T}", power_mod=1, toughness_mod=1, text="Equipped Vessel gets +1/+1."),
    "Reclaimer Captain": abys_crew("Reclaimer Captain", cost="{2T}", power_mod=2, text="Equipped Vessel gets +2/+0."),
    "Salvage Rights": abys_doctrine("Salvage Rights", cost="{3T}", setup_interceptors=make_depth_end_charge_setup(tc=1, sc=1), text="At your Surface phase, gain 1 TC and 1 SC."),
    "Patchwork Torpedo": abys_action("Patchwork Torpedo", cost="{2T}", cast_effect_fn=action_create_drones(1), text="Create a homing Drone token."),
    "Winch Engine": abys_vessel("Winch Engine", power=1, hull=4, cost="{2S}", subtypes={"Station", "Salvage"}, default_depth=DepthBand.PERISCOPE, setup_interceptors=make_simple_activated_setup(cost="{1S}", description="Gain 1 TC.", tc=1), text="{1S}: gain 1 TC."),
})

__all__ = ["SALVAGE_CARDS"]
