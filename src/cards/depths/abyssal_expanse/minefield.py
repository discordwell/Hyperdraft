"""ABYS Minefield archetype: detection-control and mine punishment."""

from __future__ import annotations

from ._mechanics import (
    DepthBand,
    abys_action,
    abys_crew,
    abys_doctrine,
    abys_mine,
    abys_vessel,
    action_damage,
    action_scan_damage,
    compose_setups,
    make_depth_end_charge_setup,
    make_dive_phase_scan_setup,
    make_salvage_setup,
    make_scan_etb_setup,
    make_simple_activated_setup,
)


MINEFIELD_CARDS = {
    "Tripwire Drone": abys_vessel("Tripwire Drone", power=1, hull=1, cost="{1S}", subtypes={"Drone", "Minefield"}, keywords={"homing"}, setup_interceptors=make_scan_etb_setup(count=1), text="ETB scan 1."),
    "Shelf Mine": abys_mine("Shelf Mine", cost="{1T}", damage=2, default_depth=DepthBand.PERISCOPE, text="Mine for 2 at PERISCOPE."),
    "Cold Pressure Mine": abys_mine("Cold Pressure Mine", cost="{1T,1S}", damage=3, default_depth=DepthBand.MID, detect_triggering_vessel=True, text="Mine for 3 at MID; detects."),
    "Listening Net": abys_doctrine("Listening Net", cost="{3S}", setup_interceptors=make_dive_phase_scan_setup(count=1), text="At your Dive phase, scan 1 opposing Vessel."),
    "Marked for Depth Charges": abys_action("Marked for Depth Charges", cost="{2T}", cast_effect_fn=action_scan_damage(2, count=1), text="Scan 1 and deal 2 to it."),
    "Mine Tender": abys_vessel("Mine Tender", power=0, hull=4, cost="{2S}", subtypes={"Submarine", "Minefield"}, default_depth=DepthBand.PERISCOPE, keywords={"defender"}, setup_interceptors=make_depth_end_charge_setup(sc=1), text="Defender. Surface phase gain 1 SC."),
    "Dead Zone Cartographer": abys_vessel("Dead Zone Cartographer", power=2, hull=3, cost="{3T,1S}", subtypes={"Submarine", "Minefield"}, default_depth=DepthBand.MID, keywords={"silent_running"}, setup_interceptors=make_scan_etb_setup(count=2), text="ETB scan 2."),
    "Net Captain Orlov": abys_vessel("Net Captain Orlov", power=3, hull=5, cost="{3T,2S}", subtypes={"Submarine", "Legendary", "Minefield"}, default_depth=DepthBand.MID, keywords={"silent_running"}, setup_interceptors=compose_setups(make_scan_etb_setup(count=2, damage_detected=1), make_dive_phase_scan_setup(count=1)), text="ETB scan 2 and ping. Dive phase scan 1."),
    "Mine-Layer Manta": abys_vessel("Mine-Layer Manta", power=2, hull=5, cost="{3T,1S}", subtypes={"Carrier", "Minefield"}, default_depth=DepthBand.PERISCOPE, setup_interceptors=make_simple_activated_setup(cost="{2T,1S}", description="Deal 2 damage.", damage=2), text="{2T,1S}: deal 2 to a target opposing Vessel."),
    "Abyssal Exclusion Zone": abys_doctrine("Abyssal Exclusion Zone", cost="{3T,2S}", setup_interceptors=make_dive_phase_scan_setup(count=2), text="At your Dive phase, scan 2 opposing Vessels."),
}

_VESSELS = [
    ("Buoy Spotter", 0, 3, "{1S}", DepthBand.PERISCOPE, {"Drone", "Minefield"}, {"defender"}, make_scan_etb_setup(count=1)),
    ("Acoustic Sweeper", 1, 2, "{2T}", DepthBand.SURFACE, {"Destroyer", "Minefield"}, {"reach"}, make_scan_etb_setup(count=1)),
    ("Tripline Skiff", 2, 3, "{2T}", DepthBand.SURFACE, {"Submarine", "Minefield"}, set(), make_salvage_setup(sc=1)),
    ("Bluewire Mechanic", 1, 4, "{2S}", DepthBand.MID, {"Submarine", "Minefield"}, {"silent_running"}, make_depth_end_charge_setup(sc=1)),
    ("Perimeter Cutter", 3, 3, "{3T}", DepthBand.SURFACE, {"Destroyer", "Minefield"}, {"reach"}, None),
    ("Sonar Fence Guard", 2, 5, "{2T,1S}", DepthBand.PERISCOPE, {"Destroyer", "Minefield"}, {"reach"}, make_dive_phase_scan_setup(count=1)),
    ("Pressure Trigger Team", 3, 4, "{3T,1S}", DepthBand.MID, {"Submarine", "Minefield"}, {"silent_running"}, make_scan_etb_setup(count=1, damage_detected=1)),
    ("Faultline Snare-Sub", 4, 3, "{3T,1S}", DepthBand.MID, {"Submarine", "Minefield"}, set(), make_simple_activated_setup(cost="{1S}", description="Scan target.", scan=True)),
    ("Red Beacon Carrier", 2, 6, "{3T,2S}", DepthBand.PERISCOPE, {"Carrier", "Minefield"}, set(), make_depth_end_charge_setup(drones=1)),
    ("Abyss Net Kraken", 5, 6, "{4T,3S}", DepthBand.DEEP, {"Leviathan", "Minefield"}, {"homing"}, make_scan_etb_setup(count=2, damage_detected=1)),
]

for name, power, hull, cost, depth, subs, keywords, setup in _VESSELS:
    MINEFIELD_CARDS[name] = abys_vessel(name, power=power, hull=hull, cost=cost, subtypes=subs, default_depth=depth, keywords=keywords, setup_interceptors=setup, text="Scan/minefield support Vessel.")

MINEFIELD_CARDS.update({
    "Crush Mine": abys_mine("Crush Mine", cost="{2T,2S}", damage=5, default_depth=DepthBand.DEEP, detect_triggering_vessel=True, text="Mine for 5 at DEEP; detects."),
    "Surface Snare": abys_mine("Surface Snare", cost="{1T}", damage=2, default_depth=DepthBand.SURFACE, text="Mine for 2 at SURFACE."),
    "Thermocline Mine": abys_mine("Thermocline Mine", cost="{2T,1S}", damage=4, default_depth=DepthBand.MID, text="Mine for 4 at MID."),
    "Ping Cascade": abys_action("Ping Cascade", cost="{3S}", cast_effect_fn=action_scan_damage(1, count=3), text="Scan up to 3 and deal 1 to each."),
    "Depth Charge Pattern": abys_action("Depth Charge Pattern", cost="{3T,1S}", cast_effect_fn=action_damage(4), text="Deal 4 to an opposing Vessel."),
    "Red Wire Officer": abys_crew("Red Wire Officer", cost="{1T,1S}", toughness_mod=2, keywords_to_grant={"reach"}, text="Equipped Vessel gets +0/+2 and reach."),
    "Black Box Warning": abys_action("Black Box Warning", cost="{1S}", cast_effect_fn=action_scan_damage(0, count=2), text="Scan up to 2 opposing Vessels."),
    "Minefield Manual": abys_doctrine("Minefield Manual", cost="{2T,1S}", setup_interceptors=make_depth_end_charge_setup(sc=1), text="Surface phase gain 1 SC."),
    "Degaussing Rig": abys_crew("Degaussing Rig", cost="{1S}", toughness_mod=1, keywords_to_grant={"silent_running"}, text="Equipped Vessel gets +0/+1 and silent_running."),
    "No-Sail Order": abys_action("No-Sail Order", cost="{2S}", cast_effect_fn=action_scan_damage(2, count=2), text="Scan 2 and deal 2 to each."),
})

__all__ = ["MINEFIELD_CARDS"]
