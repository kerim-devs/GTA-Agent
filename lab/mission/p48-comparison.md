# P48 derived comparison

The baseline is `f28da2e2230bb504a72f4ce4726dcb8c0db52d37`. P42 action files are absent. Whole-step coarse signals and frozen three-second samples below are proxies, not the requested 18-label or first-20-second measurements.

| Class | Steps | Recordings | Observed seconds | Driving share | Walking share | Sample |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| bring | 4 | 4 | 254.99 | 76.1% | 0.0% | insufficient |
| destroy | 0 | 0 | 0.00 | 0.0% | 0.0% | insufficient |
| enter_vehicle | 8 | 5 | 324.34 | 43.5% | 24.3% | small descriptive sample |
| escape | 0 | 0 | 0.00 | 0.0% | 0.0% | insufficient |
| follow | 8 | 6 | 418.60 | 25.3% | 25.5% | small descriptive sample |
| go_to | 26 | 16 | 1351.37 | 51.6% | 18.9% | small descriptive sample |
| pick_up | 1 | 1 | 2.99 | 0.0% | 31.7% | insufficient |
| protect | 0 | 0 | 0.00 | 0.0% | 0.0% | insufficient |
| return_to | 6 | 3 | 395.16 | 50.9% | 21.9% | small descriptive sample |
| sneak | 0 | 0 | 0.00 | 0.0% | 0.0% | insufficient |
| steal | 1 | 1 | 57.00 | 0.0% | 43.9% | insufficient |
| take_out | 4 | 3 | 240.73 | 6.5% | 40.4% | insufficient |
| unknown | 5 | 2 | 173.06 | 1.5% | 35.9% | insufficient |
| use | 1 | 1 | 28.50 | 52.4% | 13.8% | insufficient |
| wait | 2 | 1 | 118.43 | 58.7% | 0.1% | insufficient |

| Class | Recording / start | Objective | Mode | First plan | Kerim 3s signal proxy | Agreement |
| --- | --- | --- | --- | --- | --- | --- |
| bring | 20261111-165543 / 417.59 | Schlepp den Wagen zum Abschleppplatz. | drive | vehicle_route: drive_route | drive | same category |
| bring | 20261111-171046 / 688.52 | Bring D zu Lamars Haus. | drive | vehicle_route: drive_route | drive | same category |
| bring | 20261111-172549 / 263.01 | Bring das Auto zum Autohaus. | drive | vehicle_waypoint: set_waypoint, drive_route | drive | same category |
| bring | 20261111-180814 / 311.00 | Bring Franklin nahe an die Yacht. | drive | vehicle_waypoint: set_waypoint, drive_route | drive | same category |
| enter_vehicle | 20261111-164039 / 877.01 | Steig auf das Motorrad. | foot | foot_target: walk_to | foot | same category |
| enter_vehicle | 20261111-171046 / 153.55 | Stelg In den Liefemagen. | drive | vehicle_waypoint: set_waypoint, drive_route | neutral | unknown |
| enter_vehicle | 20261111-171046 / 329.01 | Steig wieder in den Lieferwagen. | foot | foot_target: walk_to | drive | different category |
| enter_vehicle | 20261111-190825 / 519.52 | Steig in den Pickup. | foot | fallback: wait | neutral | unknown |
| enter_vehicle | 20261111-190825 / 685.01 | Steig in den Pickup. | foot | fallback: wait | drive | unknown |
| enter_vehicle | 20261111-212314 / 176.01 | Steig wieder In dein Auto. | foot | foot_target: walk_to | foot | same category |
| enter_vehicle | 20261111-212314 / 402.00 | Steig wieder in deln Auto. | foot | foot_target: walk_to | foot | same category |
| enter_vehicle | 20261112-085011 / 867.03 | Steig in den Transporter. | foot | foot_target: walk_to | foot | same category |
| follow | 20261111-164039 / 545.52 | Folge Lamar. | foot | fallback: wait | foot | unknown |
| follow | 20261111-171046 / 482.01 | Folge Chop. | foot | fallback: wait | foot | unknown |
| follow | 20261111-180814 / 394.00 | Verfolge die Yacht. | drive | vehicle_waypoint: set_waypoint, drive_route | drive | same category |
| follow | 20261111-190825 / 520.00 | Folge dem Tennislehrer. | drive | vehicle_waypoint: set_waypoint, drive_route | drive | same category |
| follow | 20261111-193105 / 766.51 | Folge dem Programmierer. | foot | foot_target: walk_to | foot | same category |
| follow | 20261111-193105 / 770.53 | Folge dem Programmierer. | foot | fallback: wait | foot | unknown |
| follow | 20261112-090514 / 265.01 | Folge der Crew. | unknown | fallback: wait | unknown | unknown |
| follow | 20261112-090514 / 751.51 | Folge Sapphire ins Séparee. | foot | foot_target: walk_to | foot | same category |
| go_to | 20261111-164039 / 435.01 | Begib dich nach Vespucci Beach. | foot | fallback: wait | drive | unknown |
| go_to | 20261111-164039 / 889.00 | Begib dich zu der Autowaschanlage. | foot | fallback: wait | drive | unknown |
| go_to | 20261111-165543 / 221.01 | Beglb dlch zum Abschleppwagen. | foot | foot_target: walk_to | neutral | unknown |
| go_to | 20261111-165543 / 372.51 | Begib dich zu dem herrenlosen Auto. | drive | vehicle_waypoint: set_waypoint, drive_route | drive | same category |
| go_to | 20261111-171046 / 591.51 | Begib dlch zu Chop und. zieh ihn von d | foot | fallback: wait | neutral | unknown |
| go_to | 20261111-180814 / 223.00 | Begib dich nach Pacific Bluffs. | drive | vehicle_route: drive_route | drive | same category |
| go_to | 20261111-182316 / 45.01 | Begib dich zu Michaels H | menu | fallback: wait | drive | unknown |
| go_to | 20261111-183820 / 881.51 | Begib dich zu Ammu-Nation. | foot | foot_target: walk_to | drive | different category |
| go_to | 20261111-185323 / 168.02 | Begib dich zu dem Treffen bei der Recycling-Anlage. | foot | foot_target: walk_to | foot | same category |
| go_to | 20261111-190825 / 574.51 | Fahr zum Canyon. | drive | vehicle_route: drive_route | drive | same category |
| go_to | 20261111-193105 / 386.01 | Begib dich zum Suburban-Laden in Vinewood. | foot | fallback: wait | foot | unknown |
| go_to | 20261111-193105 / 460.50 | Begib dich zum Suburban-Laden In Vinewood. | drive | vehicle_route: drive_route | drive | same category |
| go_to | 20261111-193105 / 631.60 | Beglb dich zu den Büros von Llfeinvader. | foot | foot_target: walk_to | drive | different category |
| go_to | 20261111-193105 / 692.52 | Geh zum Hintereingang. | drive | vehicle_waypoint: set_waypoint, drive_route | foot | different category |
| go_to | 20261111-200111 / 154.57 | Geh zu Amanda. | foot | foot_target: walk_to | foot | same category |
| go_to | 20261111-201615 / 29.58 | Begib dich zum Fahrradverleih. | foot | fallback: wait | foot | unknown |
| go_to | 20261111-201615 / 448.00 | Mach dlch auf zur K8nBlmündung. | foot | fallback: wait | drive | unknown |
| go_to | 20261111-210812 / 801.51 | Begib dich nach Rockford Hil!¥ | drive | vehicle_route: drive_route | drive | same category |
| go_to | 20261111-212314 / 73.51 | Begib dlch zum Juweller. | drive | vehicle_waypoint: set_waypoint, drive_route | foot | different category |
| go_to | 20261111-212314 / 232.50 | Begib dich auf das Dach,. | foot | foot_target: walk_to | foot | same category |
| go_to | 20261111-212314 / 236.50 | Begib dlch auf das Dach. | foot | foot_target: walk_to | foot | same category |
| go_to | 20261111-212314 / 324.51 | Beglb dlch zum AusslchtsP& | foot | fallback: wait | foot | unknown |
| go_to | 20261111-213150 / 194.00 | Begib dich zur Textilfabrik. | drive | vehicle_route: drive_route | drive | same category |
| go_to | 20261112-085011 / 677.51 | Begib dich zur Textilfabrik. | foot | wanted_on_foot: walk | combat | different category |
| go_to | 20261112-090514 / 1.01 | Begib dich zum Juwelier. | unknown | fallback: wait | drive | unknown |
| go_to | 20261112-090514 / 591.04 | Begib dich zur Garage. | unknown | fallback: wait | drive | unknown |
| pick_up | 20261111-164039 / 628.01 | Sammle elne Waffe auf. | foot | fallback: wait | neutral | unknown |
| return_to | 20261111-164039 / 446.00 | Kehr zurück zu Lamar. | drive | vehicle_waypoint: set_waypoint, drive_route | drive | same category |
| return_to | 20261111-185323 / 677.50 | Kehr zurück zu Lamar und Stretch. | foot | wanted_on_foot: walk | foot | same category |
| return_to | 20261111-185323 / 774.50 | Kehr zurück zu Lamar und Stretch. | foot | wanted_on_foot: walk | foot | same category |
| return_to | 20261111-190825 / 268.16 | Begib dich wieder zu Franklins Haus. | drive | fallback: wait | drive | unknown |
| return_to | 20261111-190825 / 752.58 | Kehr zurück zu Michaels Haus. | drive | vehicle_route: drive_route | drive | same category |
| return_to | 20261111-190825 / 840.01 | Kehr zurück zu Michaels Haus. | drive | vehicle_route: drive_route | drive | same category |
| steal | 20261111-172549 / 206.01 | Hol das Auto zurück. | foot | fallback: wait | neutral | unknown |
| take_out | 20261111-164039 / 631.00 | Schalte die Vagos aus. | foot | take_out_fight: fight | combat | same category |
| take_out | 20261111-164039 / 692.32 | Schalte die Vagos aus. | foot | take_out_fight: fight | combat | same category |
| take_out | 20261111-172549 / 133.00 | Schalte den Gartne | foot | take_out_fight: fight | foot | different category |
| take_out | 20261112-090514 / 524.00 | Schalte dle Cops aus, bevor du den Treffpunkt erreichst. | unknown | fallback: wait | unknown | unknown |
| unknown | 20261111-212314 / 29.50 | Sprich mit der Verkäuferin. | foot | fallback: wait | foot | unknown |
| unknown | 20261111-212314 / 116.00 | Sprich mit der Verkäuferin. | menu | fallback: wait | foot | unknown |
| unknown | 20261112-090514 / 157.01 | Halte die Wac" | foot | fallback: wait | foot | unknown |
| unknown | 20261112-090514 / 160.08 | Halte die Wache auf. | foot | fallback: wait | foot | unknown |
| unknown | 20261112-090514 / 207.01 | Halte die V"vtJi5 Iv auf. | drive | vehicle_waypoint: set_waypoint, drive_route | foot | different category |
| use | 20261111-165543 / 479.51 | Mach das Fahrzeug in der Ablieferzone lo | drive | vehicle_waypoint: set_waypoint, drive_route | drive | same category |
| wait | 20261111-165543 / 222.57 | Warte auf Tonya. | drive | objective_wait: look, wait | drive | different category |
| wait | 20261111-165543 / 316.01 | Warte auf Tonya. | foot | objective_wait: look, wait | neutral | unknown |

| Corpus | Case | Before | After | Reason |
| --- | --- | --- | --- | --- |
| derived-steps | 20261111-165543:222.5695 | vehicle_waypoint: set_waypoint, drive_route | objective_wait: look, wait | The wait objective selects its existing-skill class mapping instead of the generic route/blip default. |
| derived-steps | 20261111-165543:316.0092 | foot_target: walk_to | objective_wait: look, wait | The wait objective selects its existing-skill class mapping instead of the generic route/blip default. |
