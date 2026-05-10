"""ABYS Research archetype: scan, draw, and charge smoothing."""

from __future__ import annotations

from ._mechanics import (
    DepthBand,
    abys_action,
    abys_crew,
    abys_doctrine,
    abys_vessel,
    abys_weapon,
    action_create_drones,
    action_damage,
    action_draw_charge,
    action_scan_damage,
    compose_setups,
    make_depth_end_charge_setup,
    make_damage_flagship_draw_setup,
    make_dive_phase_scan_setup,
    make_pressure_setup,
    make_scan_etb_setup,
    make_simple_activated_setup,
)


RESEARCH_CARDS = {
    "Probe Scribe": abys_vessel("Probe Scribe", power=1, hull=2, cost="{1S}", subtypes={"Drone", "Research"}, default_depth=DepthBand.PERISCOPE, setup_interceptors=make_scan_etb_setup(count=1, draw_if_any=True), text="ETB scan 1; if you do, draw 1."),
    "Bathymetry Intern": abys_vessel("Bathymetry Intern", power=1, hull=3, cost="{1S}", subtypes={"Submarine", "Research"}, setup_interceptors=make_depth_end_charge_setup(sc=1), text="Surface phase gain 1 SC."),
    "Charts and Coffee": abys_action("Charts and Coffee", cost="{1S}", cast_effect_fn=action_draw_charge(2), text="Draw 2."),
    "Sample Drone": abys_vessel("Sample Drone", power=2, hull=1, cost="{1T}", subtypes={"Drone", "Research"}, keywords={"homing"}, text="Homing."),
    "Research Grant": abys_doctrine("Research Grant", cost="{2S}", setup_interceptors=make_depth_end_charge_setup(sc=1), text="Surface phase gain 1 SC."),
    "Abyssal Microscope": abys_weapon("Abyssal Microscope", cost="{1S}", toughness_mod=1, keywords_to_grant={"silent_running"}, text="Equipped Vessel gets +0/+1 and silent_running."),
    "Signal Analyst": abys_crew("Signal Analyst", cost="{1S}", power_mod=1, text="Equipped Vessel gets +1/+0."),
    "Deep Thesis": abys_action("Deep Thesis", cost="{2S}", cast_effect_fn=action_draw_charge(2, sc=1), text="Draw 2 and gain 1 SC."),
    "Professor Vela": abys_vessel("Professor Vela", power=3, hull=5, cost="{2T,2S}", subtypes={"Submarine", "Legendary", "Research"}, default_depth=DepthBand.MID, keywords={"silent_running"}, setup_interceptors=compose_setups(make_scan_etb_setup(count=2, draw_if_any=True), make_dive_phase_scan_setup(count=1)), text="ETB scan 2 and draw if any. Dive phase scan 1."),
    "Archive Submersible": abys_vessel("Archive Submersible", power=4, hull=5, cost="{2T,1S}", subtypes={"Submarine", "Research"}, default_depth=DepthBand.DEEP, keywords={"homing", "bottom_crawler"}, setup_interceptors=compose_setups(make_pressure_setup(power=1), make_damage_flagship_draw_setup()), text="Homing. Pressure +1/+0. Draw when it damages a Flagship."),
}

_SPECS = [
    ("Echo Graduate", 1, 3, "{1T,1S}", DepthBand.PERISCOPE, {"Submarine", "Research"}, {"silent_running"}, make_scan_etb_setup(count=1)),
    ("Clipboard Towfish", 2, 2, "{2T}", DepthBand.SURFACE, {"Drone", "Research"}, {"homing"}, None),
    ("Wet Lab Cutter", 2, 3, "{2T}", DepthBand.SURFACE, {"Destroyer", "Research"}, {"reach"}, make_scan_etb_setup(count=1)),
    ("Specimen Skiff", 1, 4, "{2S}", DepthBand.MID, {"Submarine", "Research"}, {"bottom_crawler"}, make_depth_end_charge_setup(sc=1)),
    ("Pressure Archivist", 2, 4, "{2T,1S}", DepthBand.MID, {"Submarine", "Research"}, {"silent_running"}, make_scan_etb_setup(count=1, draw_if_any=True)),
    ("Glass-Sphere Observer", 1, 5, "{3S}", DepthBand.DEEP, {"Submarine", "Research"}, {"defender", "bottom_crawler"}, make_simple_activated_setup(cost="{1S}", description="Draw and gain TC.", tc=1)),
    ("Sonar Mathematician", 3, 3, "{2T,1S}", DepthBand.PERISCOPE, {"Submarine", "Research"}, set(), make_dive_phase_scan_setup(count=1)),
    ("Kelp Data Mule", 2, 5, "{3T}", DepthBand.MID, {"Submarine", "Research"}, set(), make_depth_end_charge_setup(tc=1)),
    ("Thesis Defense Boat", 4, 3, "{3T,1S}", DepthBand.PERISCOPE, {"Destroyer", "Research"}, {"reach"}, None),
    ("Midnight Enumerator", 3, 5, "{3T,2S}", DepthBand.DEEP, {"Submarine", "Research"}, {"silent_running"}, make_scan_etb_setup(count=2)),
    ("Lantern Array", 1, 6, "{3S}", DepthBand.PERISCOPE, {"Station", "Research"}, {"defender"}, make_dive_phase_scan_setup(count=2)),
    ("Abyss Cartographer", 4, 4, "{4T,1S}", DepthBand.MID, {"Submarine", "Research"}, {"homing"}, make_damage_flagship_draw_setup()),
    ("Cold Census Cruiser", 3, 6, "{4T,1S}", DepthBand.MID, {"Destroyer", "Research"}, {"reach"}, make_scan_etb_setup(count=1, damage_detected=1)),
    ("Final Expedition", 5, 5, "{3T,1S}", DepthBand.DEEP, {"Submarine", "Research"}, {"homing", "bottom_crawler"}, make_pressure_setup(power=1)),
    ("Library Leviathan", 6, 7, "{5T,3S}", DepthBand.DEEP, {"Leviathan", "Research"}, {"homing"}, compose_setups(make_scan_etb_setup(count=2, draw_if_any=True), make_pressure_setup(power=1))),
]

for name, power, hull, cost, depth, subs, keywords, setup in _SPECS:
    RESEARCH_CARDS[name] = abys_vessel(name, power=power, hull=hull, cost=cost, subtypes=subs, default_depth=depth, keywords=keywords, setup_interceptors=setup, text="Research scan/draw support.")

RESEARCH_CARDS.update({
    "Field Notes": abys_action("Field Notes", cost="{1S}", cast_effect_fn=action_draw_charge(1, sc=1), text="Draw 1 and gain 1 SC."),
    "Peer Review": abys_action("Peer Review", cost="{2S}", cast_effect_fn=action_scan_damage(0, count=2), text="Scan up to 2 opposing Vessels."),
    "Grant Extension": abys_action("Grant Extension", cost="{1T,1S}", cast_effect_fn=action_draw_charge(1, tc=1, sc=1), text="Draw 1 and gain 1 TC/SC."),
    "Lab Drones": abys_action("Lab Drones", cost="{2T}", cast_effect_fn=action_create_drones(2), text="Create two homing Drones."),
    "Implosion Paper": abys_action("Implosion Paper", cost="{3T,1S}", cast_effect_fn=action_damage(4), text="Deal 4 to an opposing Vessel."),
})

__all__ = ["RESEARCH_CARDS"]
