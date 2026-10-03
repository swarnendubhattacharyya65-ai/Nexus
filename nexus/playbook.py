"""Solution playbooks for NEXUS recommendations.

The rules in recommend.py decide WHEN something deserves attention and HOW MUCH energy is involved,
from the data. This file says WHAT TO DO about it: common causes to rule out, a staged action plan
with an owner for each step, and how to confirm the fix worked in NEXUS.

The playbooks are general building-energy practice, not findings: NEXUS cannot see inside a building,
so causes are things to rule out, never diagnoses. No savings percentages are claimed here; the
saving shown in the app is a scenario the person sets. The one external fact used (the 24 °C default
for room ACs in India) is cited.
"""
import re

NOW, MONTH, LATER = "This week · no cost", "This month · low cost", "Next budget · investment"
STAGES = [NOW, MONTH, LATER]
BEE_24C = ("India's Bureau of Energy Efficiency made 24 °C the default setting of star-labelled room ACs "
           "from 1 January 2020 (PIB, Ministry of Power).")
BEE_24C_URL = "https://www.pib.gov.in/PressReleasePage.aspx?PRID=1598508"

TYPES = [  # (type, words in the building's name) - first match wins
    ("residence", r"dorm|hostel|residen|quarters|housing|apartment"),
    ("dining", r"dining|mess|canteen|cafeteria|cafe|kitchen|food"),
    ("plant", r"facilit|plant|pump|utility|utilities|services|workshop|maintenance|substation|chiller"),
    ("library", r"librar"),
]
TYPE_LABEL = {"residence": "residence", "dining": "dining hall", "plant": "facilities / plant",
              "library": "library", "academic": "academic / office", "campus": "whole campus"}


def building_type(name):
    """Guess what kind of building this is from its name (an assumption, shown in the app)."""
    n = str(name).lower()
    for kind, words in TYPES:
        if re.search(words, n):
            return kind
    return "academic"


# ---------------------------------------------------------------- per-rule playbooks
# Each returns (causes, actions, verify). actions = [(stage, what, who)].

def unusual_high(building, when, weekday, out_of_hours, extreme, expected_per_hour):
    causes = ["AC / air-handling units left in 'occupied' mode after a booking or event",
              "An event, exam or lab run that was not in the calendar",
              "Equipment left running (lab ovens, pumps, heaters, chillers)"]
    if extreme:
        causes.insert(0, "A meter or data fault: the jump is far outside anything normal")
    actions = [
        (NOW, f"Pull the AC/BMS timer log and the room-booking list for {when}; ask the {building} "
              "in-charge what was running.", "Facilities manager"),
        (NOW, f"If nothing was booked, walk through {building} at the same time next {weekday} and note "
              "what is on.", "Security / facilities"),
        (MONTH, "Put AC units and corridor lighting on timers that follow the academic calendar; make "
                "weekend bookings include an end time so systems switch back off.", "Facilities"),
        (LATER, f"Set an alarm (BMS or NEXUS export) for when {building} runs well above its usual "
                "level for 2+ hours outside working hours.", "Facilities + IT"),
    ]
    if extreme:
        actions.insert(0, (NOW, "Check the meter first: compare with the main campus meter or that day's "
                                "bill. If the spike is not there, treat it as a data fault.", "Electrician"))
    if not out_of_hours:
        actions[1] = (NOW, f"Ask the departments in {building} whether extra equipment or a special event "
                           f"explains {when}.", "Building in-charge")
    verify = (f"No repeat on the following {weekday}s in Resource Intelligence, and {building} returns to "
              f"its usual ~{expected_per_hour:,.0f} kWh/h at that time.")
    return causes, actions, verify


def long_low(building):
    causes = ["Meter or logger offline, or a current transformer (CT) disconnected",
              "Network outage between the meter and the data system",
              f"{building} genuinely closed (vacation, renovation)",
              "Meter replaced or rewired without the data being updated"]
    actions = [
        (NOW, f"Ask the {building} in-charge whether it was closed then; check the logger's status page.",
         "Facilities"),
        (MONTH, "Set a data-gap alarm: no data, or near-zero, for 6+ hours on a working day sends a "
                "message to the electrician.", "IT / electrician"),
        (MONTH, "Compare the month's sub-meter total with the electricity bill to find meters that "
                "under-read.", "Accounts + electrician"),
        (LATER, "Keep a meter register: location, CT ratio, last calibration, and who to call.", "Facilities"),
    ]
    verify = "No new long low readings for this building in Resource Intelligence; the data is complete."
    return causes, actions, verify


def near_empty(building, btype, ratio, threshold):
    causes = ["AC / air-handling schedules that ignore how many people are in",
              "Corridor, washroom and staircase lights always on",
              "PCs, projectors, printers and displays left on or on standby",
              "Water coolers and dispensers running all night"]
    if btype == "dining":
        causes = ["Kitchen exhaust hoods, lights and water heating left on after service",
                  "Cold rooms and fridges (essential) mixed with non-essential loads on the same circuits",
                  "Dining-hall AC and fans running between meals"]
    actions = [
        (NOW, f"Do a walk-through of {building} at a near-empty hour (late evening or Sunday) with a "
              "checklist; photograph everything that is on.", "Facilities + student volunteers"),
        (NOW, "Start a 'last person out' switch-off routine with signs at exits.", "Building in-charge"),
        (MONTH, "Occupancy sensors in washrooms, corridors and low-use rooms; IT policy that puts PCs to "
                "sleep when idle.", "Facilities + IT"),
        (LATER, "Link AC control to occupancy: NEXUS already sees Wi-Fi counts, which a BMS can use "
                "to switch zones off when empty.", "Facilities + IT"),
    ]
    if btype == "dining":
        actions[2] = (MONTH, "Label circuits essential (cold rooms) vs non-essential; put exhausts, "
                             "lights and water heating on timers tied to meal times.", "Mess manager + electrician")
    verify = (f"Next semester, Institutional Intelligence shows {building}'s near-empty use below "
              f"{threshold:.0%} of its busy level (now {ratio:.0%}).")
    return causes, actions, verify


def plan_ahead(building, span, rising):
    if rising:
        causes = ["Planned events, exams or admissions in that period",
                  "Warmer weather than last year (NEXUS has no weather data to confirm)",
                  "New equipment or more people in the building"]
        actions = [(NOW, f"Check the event calendar for {span}; tell facilities which rooms need AC and when.",
                    "Admin office"),
                   (MONTH, "Service ACs before the busy period (filters, coils).", "Facilities"),
                   (MONTH, "Share the expected rise with the accounts office for the electricity budget.",
                    "Facilities + accounts")]
    else:
        causes = ["Vacation or partial closure", "Fewer people than last year",
                  "Last year's period had something unusual in it"]
        actions = [(NOW, f"If parts of {building} close during {span}, use a closure checklist: AC, "
                         "water heaters, lab equipment and non-essential lights off.", "Building in-charge"),
                   (NOW, "Keep essential loads (servers, cold storage, security lighting) on a short "
                         "written list so nothing else is left running.", "Facilities")]
    verify = f"After {span}, compare actual use with the forecast in Predictive Intelligence."
    return causes, actions, verify


def unreliable_forecast(building):
    causes = ["Weather drives a lot of the use and NEXUS has no weather data",
              "Irregular events the calendar does not record"]
    actions = [(NOW, f"Use {building}'s forecast as a range, not a number.", "Whoever plans with it"),
               (MONTH, "Record events and closures in the calendar so the forecast can use them.", "Admin office"),
               (LATER, "Add daily temperature to NEXUS (a free weather API) and re-test the forecast.",
                "NEXUS maintainer")]
    verify = "The forecast's test error in Predictive Intelligence falls below 15% of a typical day."
    return causes, actions, verify


def always_on(building, btype, base):
    causes = {
        "academic": ["Server or network racks and the AC that cools them",
                     "Corridor, exterior and signage lighting on 24 hours",
                     "Air-handling fans running round the clock",
                     "Water coolers, printers and PCs on standby"],
        "library": ["Air-handling and AC running through the night",
                    "Reading-room and stack lighting left on", "Catalogue PCs and displays on standby"],
        "residence": ["Common-area, corridor and exterior lighting", "Water heaters (geysers) on all day",
                      "Water pumps refilling tanks", "Fans and ACs in rooms nobody is in during the day"],
        "dining": ["Cold rooms and fridges (needed) plus everything else on the same circuits",
                   "Water heating and exhaust fans running between meals"],
        "plant": ["Pumps without float switches or timers", "Compressors and treatment plants (STP/WTP)",
                  "Street and exterior lighting on in daylight"],
    }[btype]
    actions = [
        (NOW, f"Night load audit: at 02:00-04:00, when {building} is at its {base:,.1f} kWh/h minimum, "
              "an electrician lists every running load and reads the meter as non-essential sub-circuits "
              "are switched off one at a time (safely).", "Electrician"),
        (MONTH, "Timers or daylight switches on exterior and corridor lights; timers on water coolers and "
                "printers; an IT policy that sleeps idle PCs.", "Facilities + IT"),
        (LATER, "Variable-speed drives on pumps and air-handling fans; a separate meter on the biggest "
                "always-on load (e.g. the server room) so NEXUS can track it on its own.", "Facilities"),
    ]
    if btype == "residence":
        actions[1] = (MONTH, "Timers on geysers (mornings and evenings only), daylight switches on "
                             "common-area lights, float switches on pumps.", "Warden + electrician")
    if btype == "dining":
        actions[1] = (MONTH, "Put non-essential kitchen loads (exhausts, water heating, lights) on timers tied to "
                             "meal times; check cold-room door seals and defrost settings.", "Mess manager + electrician")
        actions[2] = (LATER, "Replace the oldest fridges and cold-room compressors with efficient units when "
                             "due; meter the kitchen separately from the dining hall.", "Facilities")
    if btype == "residence":
        actions[2] = (LATER, "Solar water heating for the geysers' hot-water load; variable-speed drives on "
                             "pumps.", "Facilities + management")
    if btype == "plant":
        actions[1] = (MONTH, "Float switches or timers on pumps; daylight switches on street lights; "
                             "check compressors for leaks that make them run continuously.", "Electrician")
    verify = (f"The overnight minimum of {building} in Resource Intelligence falls below {base:,.1f} kWh/h "
              "and stays there.")
    return causes, actions, verify


def days_off(building, ratio, busiest_hours):
    causes = ["AC and BMS timers set by weekday, with holidays and vacations not entered",
              "Labs, servers or experiments running over weekends",
              "Lights and ACs left on from Friday evening",
              "A few weekend bookings keeping the whole building's AC on"]
    actions = [
        (NOW, f"Open {building}'s chart in Resource Intelligence for a recent Sunday and see which hours "
              f"stay high (here, mostly {busiest_hours}).", "Facilities"),
        (NOW, "Friday-evening shutdown round with a checklist.", "Security"),
        (MONTH, "Load the academic calendar (holidays, vacations) into AC and BMS timers; give the "
                "building a 'weekend mode' with an override for booked rooms only.", "Facilities"),
        (LATER, "Zone the AC so a booked room does not cool the whole building.", "Facilities"),
    ]
    verify = (f"In Resource Intelligence, {building}'s days-off use falls from {ratio:.0%} of a working "
              "day toward its overnight minimum.")
    return causes, actions, verify


def campus_peak(peak_hours, peak_months, riser, target):
    causes = ["Many ACs and chillers starting at the same time in the morning",
              "Pumps filling tanks during the day peak", "Cooking and water heating at meal times",
              "Lab equipment switched on together"]
    actions = [
        (NOW, f"List what switches on around {peak_hours} in {peak_months}; {riser}", "Facilities"),
        (NOW, "Move tank filling, laundry and other flexible loads to night or early morning.",
         "Facilities + wardens"),
        (MONTH, "Stagger AC and air-handling start times building by building instead of all at once.",
         "Facilities"),
        (MONTH, "Check the electricity bill for contract demand and recorded maximum demand: if the tariff "
                "has a demand charge, cutting peaks saves money even when total kWh stays the same.",
         "Accounts"),
        (LATER, "Pre-cooling or thermal storage; rooftop solar, which produces most around midday "
                "when this campus peaks.", "Facilities + management"),
    ]
    verify = (f"Next {peak_months}, no campus hour in Resource Intelligence goes above about {target:,.0f} kWh "
              "(today's 95th-percentile hour).")
    return causes, actions, verify


def seasonal(building, btype, hot_months, low_months):
    causes = ["Cooling (ACs, chillers) in hot and humid months",
              "Term-time activity in the same months (NEXUS has no weather data to separate the two)",
              "ACs with dirty filters or coils working harder"]
    actions = [
        (NOW, f"Before {hot_months}: service the ACs in {building} (filters, coils, refrigerant check).",
         "Facilities / AC contractor"),
        (MONTH, f"Adopt a 24 °C setting policy for AC rooms{' with the hostel council' if btype == 'residence' else ''}; "
                + BEE_24C, "Facilities"),
        (MONTH, "Door closers and curtains in AC rooms; shading or reflective coating on top-floor roofs.",
         "Facilities"),
        (LATER, "Replace the oldest ACs with higher star-rated (BEE) units when they are due; add weather "
                "data to NEXUS to separate cooling from term-time use.", "Facilities + management"),
    ]
    verify = (f"Next year, {building}'s average day in {hot_months} is lower than this year's, while "
              f"{low_months} stays about the same.")
    return causes, actions, verify
