# P51 offline replay

Replays reuse recorded observations and runner descriptions, not a counterfactual game. Disposition counts are decision opportunities; recorded applied counts also reflect original latency/stale discards. No live completion is claimed.

| Session | Requests | Before replace | After replace | After go on |
| --- | ---: | ---: | ---: | ---: |
| 20261112-102851 | 25 | 16 | 9 | 15 |
| 20261112-103305 | 27 | 23 | 15 | 12 |
| 20261112-100318 | 26 | 14 | 14 | 12 |
| 20261112-100713 | 38 | 23 | 23 | 15 |

| Session | Time | Goal | Outcome | Reason |
| --- | ---: | --- | --- | --- |
| 20261112-102851 | 0.002 | road | started | round start |
| 20261112-102851 | 33.709 | road | reached | vehicle seen while seeking a road |
| 20261112-102851 | 33.709 | vehicle | started | road reached: vehicle seen while seeking a road |
| 20261112-102851 | 130.181 | vehicle | gave_up | limit |
| 20261112-102851 | 140.268 | road | started | round start |
| 20261112-102851 | 155.344 | road | reached | vehicle seen while seeking a road |
| 20261112-102851 | 155.344 | vehicle | started | road reached: vehicle seen while seeking a road |
| 20261112-102851 | 169.584 | vehicle | reached | vehicle observed |
| 20261112-102851 | 169.584 | drive | started | vehicle reached: vehicle observed |
| 20261112-102851 | 237.496 | drive | gave_up | limit |
| 20261112-102851 | 237.496 | fight | started | drive gave_up: limit |
| 20261112-103305 | 0.004 | road | started | round start |
| 20261112-103305 | 16.377 | road | reached | vehicle seen while seeking a road |
| 20261112-103305 | 16.377 | vehicle | started | road reached: vehicle seen while seeking a road |
| 20261112-103305 | 18.558 | vehicle | reached | vehicle observed |
| 20261112-103305 | 18.558 | drive | started | vehicle reached: vehicle observed |
| 20261112-103305 | 64.169 | drive | gave_up | limit |
| 20261112-103305 | 64.169 | fight | started | drive gave_up: limit |
| 20261112-103305 | 172.949 | fight | gave_up | limit |
| 20261112-103305 | 172.949 | drive | started | fight gave_up: limit |
| 20261112-103305 | 231.867 | drive | gave_up | limit |
| 20261112-103305 | 231.867 | fight | started | drive gave_up: limit |
| 20261112-100318 | 0.002 | road | started | round start |
| 20261112-100318 | 74.405 | road | gave_up | limit |
| 20261112-100318 | 74.405 | vehicle | started | road gave_up: limit |
| 20261112-100318 | 105.822 | vehicle | gave_up | limit |
| 20261112-100318 | 105.822 | road | started | vehicle gave_up: limit |
| 20261112-100318 | 143.663 | road | gave_up | limit |
| 20261112-100318 | 143.663 | vehicle | started | road gave_up: limit |
| 20261112-100713 | 0.002 | road | started | round start |
| 20261112-100713 | 52.273 | road | gave_up | limit |
| 20261112-100713 | 52.273 | vehicle | started | road gave_up: limit |
| 20261112-100713 | 77.550 | vehicle | gave_up | limit |
| 20261112-100713 | 77.550 | road | started | vehicle gave_up: limit |
| 20261112-100713 | 128.016 | road | gave_up | limit |
| 20261112-100713 | 128.016 | vehicle | started | road gave_up: limit |
| 20261112-100713 | 164.693 | vehicle | gave_up | limit |
| 20261112-100713 | 164.693 | road | started | vehicle gave_up: limit |
| 20261112-100713 | 190.188 | road | gave_up | limit |
| 20261112-100713 | 190.188 | vehicle | started | road gave_up: limit |
| 20261112-100713 | 234.079 | vehicle | gave_up | limit |
| 20261112-100713 | 234.079 | road | started | vehicle gave_up: limit |

| Corpus case | Before | After | Explanation |
| --- | --- | --- | --- |
| mission / pilot-20261110-230229-01 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| mission / pilot-20261110-230229-02 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| mission / pilot-20261110-230229-03 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| mission / pilot-20261110-230229-04 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| mission / pilot-20261110-230229-05 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| mission / pilot-20261110-230229-06 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| mission / pilot-20261110-230229-07 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| mission / pilot-20261110-230229-08 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| mission / pilot-20261110-231512-01 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| mission / pilot-20261110-231512-02 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| mission / pilot-20261110-231512-03 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| mission / pilot-20261110-231512-04 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| mission / pilot-20261110-231512-05 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| mission / pilot-20261110-231512-06 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| mission / pilot-20261110-231512-07 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| mission / pilot-20261110-231512-08 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| mission / pilot-20261110-231512-09 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| mission / pilot-20261110-231512-10 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| mission / wifi-10 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| mission / wifi-170 | vehicle_waypoint: set_waypoint, drive_route | goal_drive: set_waypoint, drive_route | No screen objective: drive now owns the free-roam plan; start next goal step. |
| mission / wifi-255 | vehicle_route: drive_route | goal_drive: drive_route | No screen objective: drive now owns the free-roam plan; start next goal step. |
| mission / wifi-275 | vehicle_route: drive_route | goal_drive: drive_route | No screen objective: drive now owns the free-roam plan; start next goal step. |
| mission / wifi-285 | vehicle_route: drive_route | goal_drive: drive_route | No screen objective: drive now owns the free-roam plan; start next goal step. |
| mission / wifi-300 | vehicle_route: drive_route | goal_drive: drive_route | No screen objective: drive now owns the free-roam plan; start next goal step. |
| mission / wifi-345 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| mission / wifi-350 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| mission / wifi-365 | vehicle_waypoint: set_waypoint, drive_route | goal_drive: set_waypoint, drive_route | No screen objective: drive now owns the free-roam plan; start next goal step. |
| mission / wifi-395 | vehicle_route: drive_route | goal_drive: drive_route | No screen objective: drive now owns the free-roam plan; start next goal step. |
| mission / wifi-410 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| mission / wifi-420 | vehicle_waypoint: set_waypoint, drive_route | goal_drive: set_waypoint, drive_route | No screen objective: drive now owns the free-roam plan; start next goal step. |
| mission / wifi-425 | vehicle_waypoint: set_waypoint, drive_route | goal_drive: set_waypoint, drive_route | No screen objective: drive now owns the free-roam plan; start next goal step. |
| mission / wifi-435 | vehicle_waypoint: set_waypoint, drive_route | goal_drive: set_waypoint, drive_route | No screen objective: drive now owns the free-roam plan; start next goal step. |
| mission / wifi-445 | vehicle_waypoint: set_waypoint, drive_route | goal_drive: set_waypoint, drive_route | No screen objective: drive now owns the free-roam plan; start next goal step. |
| mission / wifi-450 | vehicle_waypoint: set_waypoint, drive_route | goal_drive: set_waypoint, drive_route | No screen objective: drive now owns the free-roam plan; start next goal step. |
| mission / wifi-465 | vehicle_waypoint: set_waypoint, drive_route | goal_drive: set_waypoint, drive_route | No screen objective: drive now owns the free-roam plan; start next goal step. |
| mission / wifi-470 | vehicle_waypoint: set_waypoint, drive_route | goal_drive: set_waypoint, drive_route | No screen objective: drive now owns the free-roam plan; start next goal step. |
| mission / wifi-485 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| mission / wifi-490 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| mission / wifi-500 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| mission / wifi-505 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| mission / wifi-520 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| mission / wifi-530 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| take-out / 20261110-093238:213.8168 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| take-out / 20261111-164039:436.0094 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| take-out / 20261111-171046:691.5025 | vehicle_route: drive_route | goal_drive: drive_route | No screen objective: drive now owns the free-roam plan; start next goal step. |
| p45-changes / 20261111-164039-436.009 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| p45-sessions / 20261111-204712:1 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| p45-sessions / 20261111-204712:2 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| p45-sessions / 20261111-204712:4 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| p45-sessions / 20261111-204712:6 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| p45-sessions / 20261111-204712:7 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| p45-sessions / 20261111-204712:8 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| p45-sessions / 20261111-204712:10 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| p45-sessions / 20261111-204712:12 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| p45-sessions / 20261111-204712:13 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| p45-sessions / 20261111-204712:14 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| p45-sessions / 20261111-204712:15 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| p45-sessions / 20261111-204712:17 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| p45-sessions / 20261111-204712:19 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| p45-sessions / 20261111-204712:20 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| p45-sessions / 20261111-204712:21 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| p45-sessions / 20261111-204712:22 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| p45-sessions / 20261111-204712:23 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| p45-sessions / 20261112-082524:1 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| p45-sessions / 20261112-082524:2 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| p45-sessions / 20261112-082524:3 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| p45-sessions / 20261112-082524:5 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| p45-sessions / 20261112-082524:6 | foot_drive: enter_vehicle, set_waypoint, drive_route | goal_vehicle: enter_vehicle | No screen objective: vehicle now owns the free-roam plan; start next goal step. |
| p45-sessions / 20261112-082524:7 | foot_drive: enter_vehicle, set_waypoint, drive_route | goal_vehicle: enter_vehicle | No screen objective: vehicle now owns the free-roam plan; start next goal step. |
| p45-sessions / 20261112-082524:9 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| p45-sessions / 20261112-082524:10 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| p45-sessions / 20261112-082524:12 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| p45-sessions / 20261112-082524:13 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| p45-sessions / 20261112-082524:15 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| p45-sessions / 20261112-082524:17 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| p45-sessions / 20261112-082524:18 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| p45-sessions / 20261112-082524:20 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| p45-sessions / 20261112-082524:21 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| p45-sessions / 20261112-082524:23 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| p45-sessions / 20261112-082524:24 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| p45-sessions / 20261112-082524:26 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
| p45-sessions / 20261112-082524:27 | foot_explore: walk_road | goal_road: walk_road | No screen objective: road now owns the free-roam plan; start next goal step. |
