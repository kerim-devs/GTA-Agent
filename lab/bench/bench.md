# Capability bench

43 tries; 24 counted failures; unclear 0/24 (0.0%).

Historical code versions are unknown unless recorded at execution. Missing evidence is excluded, never converted into a pass.

| Capability | State | Last ten | All | Median s | Excluded | Causes | Top reasons |
| --- | --- | --- | --- | --- | --- | --- | --- |
| foot.view | not measurable | 0/0 | 0/0 | None | 0 | {} | [] |
| foot.walk | not measurable | 0/0 | 0/0 | None | 6 | {} | [] |
| foot.walk_to | not measurable | 0/0 | 0/0 | None | 0 | {} | [] |
| foot.roadside | not built | 0/0 | 0/0 | None | 0 | {} | [] |
| foot.enter | not measurable | 0/3 | 0/3 | 32.992 | 2 | {'act': 2, 'see': 1} | [('could not reach it', 2), ('nothing found', 1)] |
| car.leave | too few tries | 3/3 | 3/3 | 7.987 | 4 | {} | [] |
| car.follow | not measurable | 0/1 | 0/1 | 66.0 | 3 | {'decide': 1} | [('replaced', 1)] |
| car.arrive | too few tries | 0/0 | 0/0 | None | 0 | {} | [] |
| car.free | not measurable | 0/0 | 0/0 | None | 0 | {} | [] |
| car.turn | not built | 0/0 | 0/0 | None | 0 | {} | [] |
| map.open_close | too few tries | 0/0 | 0/0 | None | 0 | {} | [] |
| map.place | not measurable | 0/10 | 0/20 | 31.991 | 1 | {'decide': 2, 'see': 4, 'proof': 14} | [('waypoint set: Ammu-Nation (294m); gameplay observed; places: Ammu-Nation, Ammu-Nation mit Schießstand, Beekers Garage, Los Santos Customs', 4), ('existing-waypoint-at-target; avoid toggling it off; gameplay observed', 2), ('waypoint set: Ammu-Nation mit Schießstand (6078m); gameplay observed; places: Ammu-Nation, Ammu-Nation mit Schießstand, Beekers Garage, Los Santos Customs', 2)] |
| map.mission | not measurable | 0/0 | 0/0 | None | 0 | {} | [] |
| goal.keep | not measurable | 0/0 | 0/0 | None | 0 | {} | [] |
| incident.menu | not measurable | 0/0 | 0/0 | None | 0 | {} | [] |
| incident.down | not measurable | 0/0 | 0/0 | None | 0 | {} | [] |
| incident.wanted | not measurable | 0/0 | 0/0 | None | 0 | {} | [] |
| chain.basic | not measurable | 0/0 | 0/0 | None | 0 | {} | [] |

## Evidence and newest failures

foot.view: Camera pose/distance missing: perception reader and cli play logger. Marked: 0. Newest failures: none.

foot.walk: Independent moving field at <3s intervals for 20s: flow reader and cli play logger. Marked: 0. Newest failures: none.

foot.walk_to: Blip distance in metres missing: minimap reader and cli play logger. Marked: 0. Newest failures: none.

foot.roadside: Roadside position missing: road reader and cli play logger; no roadside skill. Marked: 0. Newest failures: none.

foot.enter: Target speed and driver occupancy missing: vehicle detector and cli/head logger. Marked: 0. Newest failures: /Users/kerim/recordings/pilot/20261112-111123, /Users/kerim/recordings/pilot/20261112-110806, /Users/kerim/recordings/pilot/20261112-110449.

car.leave: Final stable flat minimap, initially tilted; independent of press result. Marked: 0. Newest failures: none.

car.follow: GPS distance/speed in metres at sufficient cadence: minimap/OCR reader and cli play logger. Marked: 0. Newest failures: /Users/kerim/recordings/pilot/20261112-122756.

car.arrive: Final GPS <=30m, speed stopped, arrival sentence in head response. Marked: 0. Newest failures: none.

car.free: Recovery attempt identity/start missing: driver and cli play logger. Marked: 0. Newest failures: none.

car.turn: No standalone turn skill; route-relative heading missing from play logger. Marked: 0. Newest failures: none.

map.open_close: Independent HUD screen visits map and returns to game. Marked: 0. Newest failures: none.

map.place: Selected legend entry identity/type missing: legend reader and conductor head/play logger. Marked: 0. Newest failures: /Users/kerim/recordings/pilot/20261112-122406, /Users/kerim/recordings/pilot/20261112-122003, /Users/kerim/recordings/pilot/20261112-121929.

map.mission: Independent selected legend identity/type missing: legend reader and conductor head/play logger. Marked: 0. Newest failures: none.

goal.keep: Goal lifecycle/id/end condition missing from head/play logger; no fixed goal plan. Marked: 0. Newest failures: none.

incident.menu: Recovery handler result/attempt id missing: conductor play/head logger. Marked: 0. Newest failures: none.

incident.down: Explicit respawn timestamp and resumed control missing: HUD reader and cli logger. Marked: 0. Newest failures: none.

incident.wanted: Recovery handler result/attempt id missing: conductor play/head logger. Marked: 0. Newest failures: none.

chain.basic: Real legend selection and arrival declaration missing; depends on map.place proof. Marked: 0. Newest failures: none.

## Repair ranking

| Capability | Cause | Reason | Count |
| --- | --- | --- | --- |
| map.place | proof | waypoint set: Ammu-Nation (294m); gameplay observed; places: Ammu-Nation, Ammu-Nation mit Schießstand, Beekers Garage, Los Santos Customs | 4 |
| foot.enter | act | could not reach it | 2 |
| map.place | decide | existing-waypoint-at-target; avoid toggling it off; gameplay observed | 2 |
| map.place | proof | waypoint set: Ammu-Nation mit Schießstand (6078m); gameplay observed; places: Ammu-Nation, Ammu-Nation mit Schießstand, Beekers Garage, Los Santos Customs | 2 |
| map.place | proof | waypoint set: Beekers Garage (3377m); gameplay observed; places: Ammu-Nation, Ammu-Nation mit Schießstand, Beekers Garage, Los Santos Customs | 2 |
| map.place | proof | waypoint set: Los Santos Customs (6598m); gameplay observed; places: Ammu-Nation, Ammu-Nation mit Schießstand, Beekers Garage, Los Santos Customs | 2 |
| car.follow | decide | replaced | 1 |
| foot.enter | see | nothing found | 1 |
| map.place | proof | waypoint set: Ammu-Nation mit Schießstand (6078m); gameplay observed; places: Ammu-Nation, Ammu-Nation mit Schießstand, Beekers Garage, SAN, Los Santos Customs | 1 |
| map.place | proof | waypoint set: Ammu-Nation mit Schießstand (6079m); gameplay observed; places: Ammu-Nation, Ammu-Nation mit Schießstand, Beekers Garage, Los Santos Customs | 1 |
| map.place | proof | waypoint set: Beekers Garage (3377m); gameplay observed; places: Ammu-Nation, Ammu-Nation mit Schießstand, Beekers Garage, ANDY, Los Santos Customs | 1 |
| map.place | proof | waypoint set: Los Santos Customs (6598m); gameplay observed; places: Ammu-Nation, Ammu-Nation mit Schießstand, Beekers Garage, Los Santos Customs, Los Santos Customs < 114> i | 1 |
| map.place | see | map-shift-unverified; damaged or ambiguous map pair; gameplay observed | 1 |
| map.place | see | place-not-in-legend: ANDY; gameplay observed; places: Ammu-Nation, Ammu-Nation mit Schießstand, Beekers Garage, Los Santos Customs | 1 |
| map.place | see | place-not-in-legend: Los Santos Customs < 114> i; gameplay observed; places: Ammu-Nation, Ammu-Nation mit Schießstand, Beekers Garage, Los Santos Customs | 1 |
| map.place | see | place-not-in-legend: SAN; gameplay observed; places: Ammu-Nation, Ammu-Nation mit Schießstand, Beekers Garage, Los Santos Customs | 1 |

## Rates by commit

foot.enter: unknown (dirty=None), 0/3.

car.leave: unknown (dirty=None), 3/3.

car.follow: unknown (dirty=None), 0/1.

map.place: unknown (dirty=None), 0/20.

