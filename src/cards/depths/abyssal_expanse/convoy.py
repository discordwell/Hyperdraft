"""ABYS Convoy archetype: same-depth formation attacks and escorts."""

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
    make_formation_attack_setup,
    make_same_depth_lord_setup,
    make_scan_etb_setup,
)


CONVOY_CARDS = {
    "Convoy Tender": abys_vessel("Convoy Tender", power=1, hull=2, cost="{1T}", subtypes={"Destroyer", "Convoy"}, keywords={"reach"}, setup_interceptors=make_formation_attack_setup(n=1, power=2, same_depth_only=False), text="Formation 1 - +2 power EOT."),
    "Signal Pennant": abys_crew("Signal Pennant", cost="{1T}", power_mod=1, keywords_to_grant={"reach"}, text="Equipped Vessel gets +1/+0 and reach."),
    "Depth-Flag Runner": abys_vessel("Depth-Flag Runner", power=2, hull=3, cost="{2T}", subtypes={"Submarine", "Convoy"}, setup_interceptors=make_formation_attack_setup(n=1, power=1, draw=1, same_depth_only=False), text="Formation 1 - +1 power EOT and draw 1."),
    "Escort Screen": abys_action("Escort Screen", cost="{1T}", cast_effect_fn=action_create_drones(1), text="Create a homing Drone token."),
    "Line Ahead Doctrine": abys_doctrine("Line Ahead Doctrine", cost="{2T}", setup_interceptors=make_same_depth_lord_setup(subtype="Convoy", power=1), text="Your Convoy Vessels at this depth get +1/+0."),
    "Quartermaster Sato": abys_vessel("Quartermaster Sato", power=3, hull=5, cost="{2T,1S}", subtypes={"Destroyer", "Legendary", "Convoy"}, default_depth=DepthBand.PERISCOPE, keywords={"reach"}, setup_interceptors=compose_setups(make_same_depth_lord_setup(subtype="Convoy", power=1, hull=1), make_depth_end_charge_setup(tc=1)), text="Same-depth Convoy lord. Surface phase gain 1 TC."),
    "Crossing the Shelf": abys_action("Crossing the Shelf", cost="{1S}", cast_effect_fn=action_draw_charge(1, sc=1), text="Draw 1 and gain 1 SC."),
    "Harbor Shepherd": abys_vessel("Harbor Shepherd", power=2, hull=4, cost="{2T,1S}", subtypes={"Destroyer", "Convoy"}, keywords={"reach"}, setup_interceptors=make_scan_etb_setup(count=1), text="ETB scan 1 opposing Vessel."),
    "Convoy Bell": abys_doctrine("Convoy Bell", cost="{3T}", setup_interceptors=make_depth_end_charge_setup(drones=1), text="At your Surface phase create a Drone."),
    "Admiral Chain-Grid": abys_vessel("Admiral Chain-Grid", power=5, hull=6, cost="{3T,1S}", subtypes={"Destroyer", "Legendary", "Convoy"}, keywords={"reach", "homing"}, setup_interceptors=make_formation_attack_setup(n=2, power=2, flag_damage=2), text="Homing, reach. Formation 2 - +2 power and deal 2 to opposing Flagship."),
}

_SPECS = [
    ("Wake Boat", 2, 1, "{1T}", DepthBand.SURFACE, {"Drone", "Convoy"}, set(), None),
    ("Periscope Runner", 1, 3, "{1S}", DepthBand.PERISCOPE, {"Submarine", "Convoy"}, {"silent_running"}, make_formation_attack_setup(n=1, power=1)),
    ("Masthead Sloop", 2, 3, "{2T}", DepthBand.SURFACE, {"Destroyer", "Convoy"}, {"reach"}, None),
    ("Signal Buoy Tug", 1, 4, "{2S}", DepthBand.PERISCOPE, {"Destroyer", "Convoy"}, {"reach"}, make_scan_etb_setup(count=1)),
    ("Twin-Line Frigate", 3, 3, "{2T,1S}", DepthBand.PERISCOPE, {"Destroyer", "Convoy"}, {"reach"}, make_formation_attack_setup(n=1, power=1, same_depth_only=False)),
    ("Merchant Sub Hauler", 2, 5, "{3T}", DepthBand.PERISCOPE, {"Submarine", "Convoy"}, set(), make_depth_end_charge_setup(tc=1)),
    ("Screen Cutter", 4, 2, "{3T}", DepthBand.SURFACE, {"Destroyer", "Convoy"}, {"reach"}, make_formation_attack_setup(n=2, power=2, same_depth_only=False)),
    ("Depth Lane Pilot", 3, 4, "{3T,1S}", DepthBand.MID, {"Submarine", "Convoy"}, set(), make_formation_attack_setup(n=1, draw=1)),
    ("Anchor Route Escort", 2, 6, "{2T,2S}", DepthBand.MID, {"Destroyer", "Convoy"}, {"reach"}, None),
    ("Fleet Net Carrier", 2, 5, "{3T,1S}", DepthBand.PERISCOPE, {"Carrier", "Convoy"}, set(), make_depth_end_charge_setup(drones=1)),
    ("Mine-Lane Sweeper", 3, 4, "{3T,1S}", DepthBand.SURFACE, {"Destroyer", "Convoy"}, {"reach"}, make_scan_etb_setup(count=1, damage_detected=1)),
    ("Current Marshal", 4, 4, "{4T}", DepthBand.PERISCOPE, {"Destroyer", "Convoy"}, {"reach"}, make_formation_attack_setup(n=1, flag_damage=1)),
    ("Broadside Tender", 5, 3, "{4T,1S}", DepthBand.PERISCOPE, {"Destroyer", "Convoy"}, {"homing"}, None),
    ("Harbor Leviathan Escort", 4, 6, "{4T,2S}", DepthBand.MID, {"Leviathan", "Convoy"}, {"reach"}, make_formation_attack_setup(n=2, power=2)),
    ("Last Light Convoy", 6, 6, "{5T,2S}", DepthBand.PERISCOPE, {"Carrier", "Convoy"}, {"homing"}, make_depth_end_charge_setup(drones=2)),
]

for name, power, hull, cost, depth, subs, keywords, setup in _SPECS:
    CONVOY_CARDS[name] = abys_vessel(name, power=power, hull=hull, cost=cost, subtypes=subs, default_depth=depth, keywords=keywords, setup_interceptors=setup, text="Formation and escort support.")

CONVOY_CARDS.update({
    "Flare Order": abys_action("Flare Order", cost="{1S}", cast_effect_fn=action_draw_charge(1, tc=1), text="Draw 1 and gain 1 TC."),
    "Screen Commander": abys_crew("Screen Commander", cost="{2T}", power_mod=1, toughness_mod=1, keywords_to_grant={"reach"}, text="Equipped Vessel gets +1/+1 and reach."),
    "Hold the Route": abys_action("Hold the Route", cost="{1T}", cast_effect_fn=action_create_drones(3), text="Create three homing Drone tokens."),
    "Convoy Charter": abys_doctrine("Convoy Charter", cost="{2T,1S}", setup_interceptors=make_depth_end_charge_setup(tc=1, sc=1), text="At your Surface phase gain 1 TC and 1 SC."),
    "Long Wake Captain": abys_crew("Long Wake Captain", cost="{1T,1S}", power_mod=2, text="Equipped Vessel gets +2/+0."),
})

__all__ = ["CONVOY_CARDS"]
