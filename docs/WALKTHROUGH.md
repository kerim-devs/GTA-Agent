# The walkthrough with Kerim

Kerim asked on the evening of 12 November for a list of everything the pilot does badly today, to be gone through at the console one piece after another: the pilot shows a piece, he watches and judges it as the player he is, says what a player would do differently, the piece is corrected and shown again. When a basic structure stands he plays on, and what is still missing is learnt from watching him. This file is that list and keeps his verdicts. The numbers behind each state are in `docs/LOG.md`, the capabilities with their proofs in `docs/tasks/P58-the-bench.md`.

A station goes like this. The pilot runs the piece alone for a short session, recorded, with nobody on the controller. Kerim says what was good and what was not, and how the game itself works at that point. His verdict and the rule taken from it are written here on the same day. A station is ticked off when it has gone well three times in a row without a hand on the controller, as on the live ladder of the plan. From 12 November, 23:37, by his word: a piece is built, tried at the console in a loop without him, corrected and tried again until it runs fluidly, with no stutter and no standing still, and he is then shown the result and rates that. (For a quarter of an hour before, the rule was a list to rate before every run; the list of ten points for the walk was the one he rated.)

Two things hold for every station. What the game does by itself (the lock of L2, the rhythm in which it takes presses, a pickup taken by walking over it) is asked of Kerim and timed on his recordings before anything is estimated. And all of it is the preparation for GTA VI: the movements learnt here carry over, the logic is taught anew when that game is out, and since its minimap by rumour no longer shows the police, no piece may depend on the minimap alone.

| No. | Station | State on 12 November | Kerim's verdict | What follows |
|---|---|---|---|---|
| 1 | Walking along a road | runs; hangs on knee-high walls in front gardens, `walk_road` gave up thirteen times in one afternoon; the bench cannot measure it yet | open | |
| 2 | Setting the view from behind | right 4 times of 14 with the first reader; the game's idle camera after thirty quiet seconds fools every reader | open | |
| 3 | Walking to a point on the map | `walk_to_point` sprints in Kerim's rhythm, keeps to the minimap's roads, reads its stamina from the health track, follows the place's symbol once the game has removed the marker, climbs with Square and goes round what stops it. Tried in a loop at the console in the night to 13 November (`lab/live/walks.py`): of the fourteen walks begun on the 180 to 250 m between the barber's and Ammu-Nation in Sandy Shores after the changes of 00:50, nine arrived, in 37 to 57 s, with the stick never let go and no sharp turn of the stick but the guard's own; five of them in a row. Of the other five, two found no marker on the map, two were stuck at the barber's, under its porch and behind its back wall, and one was run over. It gives up in a yard with one gate and in a wedge between three things, and learns of a wall only by standing against it. On 13 November, 02:26, with what the second review changed: two more arrived (196 m in 35.9 s, 232 m in 51.7 s), and a third, begun in front of the barber's door, ran in at it and ended in the shop's welcome scene. From inside the shop the way out was found by the local model's eye after 65 s, twice by way of the barred window beside the door. Since 03:20 the walk asks the model once a second whether it is in a room, goes back out the way it came, waits a scene out, goes round a room along its walls where no way out is seen, and outdoors feels for a side before it stands and looks (not yet at the console) | 12 Nov, on the first two runs: far too slow, the sprint good but with a stop again and again; it has to be quick and fluid, the way worked out first and then run in one go. On the third run: very good; the time before it was far too long. On the list of ten points (23:28): sprint rhythm and a start without a wobble, yes; a way from the pause map, only for special cases; roadside and arriving off the carriageway, yes, as a switch; over cars and walls with Square, round them otherwise, the local model to say which way; across country yes, never into water; keeping clear of people and cars, no; a final test, yes. 13 Nov, 02:53, on the minutes in the barber's: it stands in a corner and turns in circles; use the way out you came in by; this has to get better far more quickly. 03:05: remember the entrance when you go into a shop; if nothing helps, run at every face once, all round the shop; once out, three or four steps straight on before a turn | the way back out, the scene, the wall round and the new order outdoors at the console, from in front of the barber's door and from inside it; the second review of all of it; then three good walks in a row and his verdict. After that: the walk still starts through a door it stands in front of, which only the model's eye could prevent; water in the planner; a run with `side=true` (log of 13 November) |
| 4 | Getting into a vehicle | seated after 8.4 s in a truck that came past (22:19); once followed a moving pickup onto a junction and stood there | 12 Nov: taking the next vehicle at once is very good | the reviewer's note that an empty vehicle should come first, because pulling a driver out added a star, is his to confirm or drop |
| 5 | Getting out | 2 of 2 | open | |
| 6 | Following a route and arriving | two kilometres in one go at about 9 m/s; stood twice for 70 s short of the goal because the reader called every map damaged | open | |
| 7 | Driving off with no destination | not built | 12 Nov: with the police behind you, never open the map and never look for a destination; drive, right, left, across the fields, up the hills, only never into water | P68 |
| 8 | Getting free and turning round | not measurable, turning not built | open | |
| 9 | Opening and closing the map | 1 of 1 | open | |
| 10 | Choosing a place or a mission on the map | failed four times of five on the desert map by day (22:19), 11 of 12 on earlier tries | 12 Nov: not while fleeing | the map reader on a bright map |
| 11 | Punching | first man down at 22:03 after the reach was corrected; one punch thrown of four presses | 12 Nov: strong, but only one punch came, the game's own logic must be respected; L2 targets the opponent and always helps; punching without L2, the stick held at the man, is for later | rhythm now Kerim's own, four presses a punch, not yet run at the console; an opponent who hits back not yet met; `aim=free` exists as a switch |
| 12 | Shooting at a red marker | never run at the console; turns the camera first and presses L2 late; nothing reads whether a weapon is in the hand | 12 Nov: L2 first, also when shooting | to be changed to L2 first, then run |
| 13 | Noticing a hit without a marker | the health reader makes falls up | 12 Nov: a brawl or an attacker in the street shows no red marker and must be recognised too | P66 |
| 14 | The guard: answering a threat without waiting for a model | being measured on the bench (P65), not yet at the console | open | |
| 15 | Cover and low health | never run at the console | open | |
| 16 | Collecting money and weapons | not built; a blind walk over the place collected nothing | 12 Nov: collect when nobody is left to fight; in a shootout only with health to spare; with little health not before every enemy is down | P67 |
| 17 | Losing the stars | sprinted on the first tick and sat in a vehicle after 8.4 s, then stalled on the map with two stars lit | see 7 | P68, then the head's rules for stars use it |
| 18 | Going on after a death or an arrest, closing a menu nobody asked for | not measurable on the bench yet | open | |
| 19 | The basic chain and a whole mission | never run in one piece | open | |

## What was added on the morning of 13 November, none of it run at the console yet

Kerim, that night: the pilot is to play the story by itself, decide quickly and well, not get in its own way, find its way, drive as one drives in this game, be allowed a shootout, and now and then go home, change clothes, get a haircut or walk into a shop, at random. The gaming PC was off and the console too, so everything below was built on his recordings, on the simulators and on replays, and each piece is a station of its own for the next session. The command for that session is `lab/live/story.sh`.

| No. | Station | State on 13 November | Kerim's verdict | What follows |
|---|---|---|---|---|
| 20 | Errands chosen at random: story, a shop, home, mayhem, a cruise | built (P70): weights 5, 3, 2, 1, 1, no errand twice running except the story, a shop not again within half an hour, home not within the hour; a trip of up to 250 m is walked, a longer one driven; replayed over 1315 recorded requests without an error | open | |
| 21 | Not getting in its own way | built: the rules leave a running skill running when they would ask for the same call again (89 such replacements in the old logs, 7 in the replay); a button the bridge let go of in mid-press is not pressed a second time; a hand on the controller puts the plan down and nothing is pressed until it is let go of | open | |
| 22 | Noticing that the figure stands | built: twelve seconds without movement in the game, with a skill that should move it, are told to the head, which jumps and sprints, then turns and goes, then backs off to the road, and gives the errand up the fourth time | open | |
| 23 | A help text's button | built (P71): seven kinds of offer from his recordings with the button he pressed; an offer not in the table is tried with the d-pad's right; never a bed, a save, a purchase, Online or the phone | open | the table rests on 40 of 469 recorded help texts |
| 24 | A shop from the inside | built (P71): opens the offer, reads rows and prices, goes down a random number of rows, buys at most one thing for at most 150 dollars and only where every row on screen is priced within that, and backs out | open | which row is highlighted is not read |
| 25 | In through a door and out again | built (P72): at the place's symbol the walk looks for the door for up to forty seconds; `leave_building` goes back the way it came, then by the model's door, then along the walls | open | needs the local model to know inside from outside; the picture alone was right on 84 % indoors and 25 % outdoors |
| 26 | A menu left open | built: a shop's or wardrobe's menu nobody asked for is backed out of after about four seconds, one level a press; in a mission the head is told first and uses it | open | |
| 27 | A call | built: one that rings is taken with the cross as he takes it, one that runs is left to run, and the figure walks and drives on meanwhile; until now the reflex hung up on every call | open | |
| 28 | Driving like a player | partly built (P73): two seconds behind a stopped vehicle, then round it by backing up and the other lock; a recovery is forgotten after thirty metres; brakes into its arrival; ends when it stands in water. In the simulator not faster than before, and from close behind a parked car it did not get past in fifteen seconds | open | speed and the turn round are for the console, with him watching; `story.sh 1800 careful` drives as before |
| 29 | A shootout | rebuilt (P77): L2 first, the trigger in his rhythm (0.22 s, one burst a lock), the lock let go and taken again, a step to the side when hit; on the bench it aims within a second in 15 of 20 enemy scenes where it was 3, and fires in 16 where it was 4 | 12 Nov: L2 first | nothing reads whether a weapon is in the hand |
| 30 | A failed mission | built (P75): the retry as before; the third failure of the same mission in a row takes the skip where the game offers it (Square) | open | |
| 31 | Switching the character | built (P79): the wheel with Down, the right stick only ever left, up or right, never down, so that the lower slot cannot be highlighted; reads which slot is highlighted (right on 126 of 127 recorded frames, no wheel seen on 200 others) | open | his hand next to the controller the first time |
| 32 | The local model decides | built (P74): it picks the next errand, and the next step where the rules have none, among up to six things the rules offer, within a second and a half; silent twice, it is left alone for a minute and the rules play | open | never measured against the real model: it was off |

## What can go wrong, and what answers it

Thought through on 13 November from what has gone wrong so far. "Open" means nothing answers it yet.

| What happens | What answers it |
|---|---|
| The figure walks into a wall, a fence or a kerb and stops | the walk climbs with Square or goes round; after twelve seconds the head is told that it stands (station 22) |
| It walks into a yard or a dead end | the walk keeps to the roads of the minimap and steps off a shop's front before it starts; a place given up twice within the hour is not chosen again, in this session or the next |
| It ends up inside a building it did not mean to enter | the walk asks the model whether this is a room and leaves; without the model: open |
| Two parts of it want the pad | one owner a tick, in this order: the screen reflex, the guard, the plan; the rules do not restart what already runs |
| Somebody hits it and the map shows no red | the guard punches back in free roam; in a mission the head is told, for ninety seconds after the last objective was read |
| Red markers | the guard starts the fight at once; with stars lit nothing is fired |
| Stars | away along the road without opening the map, never into water (P68); the map is tilted under stars on foot as in a car, so the seat is the one last known, for two minutes at most; a car that could not be entered is not tried again before the figure has run on |
| Little health | it runs, and the fight ends |
| It dies or is arrested | the reflex waits the screen out and the head plans afresh |
| A car stands in front of it, or the light is red | two seconds, then round it (station 28) |
| The car is stuck | back and forward with the lock changed each time, five times; then out of the car and into another |
| The car is in water | two seconds standing in it end the drive and the figure gets out; what it does swimming: open |
| The car is on its roof or burns | not read; a car that stands for twelve seconds is left the second time |
| The map is called damaged for long | a look and one more try, then out of the car |
| A mission says follow or catch and draws no route | `drive_to_blip` (P78): the car goes at the order's marker and keeps the distance or closes in; told to take somebody out it drives at the red marker for twenty seconds at a time and gets out when it is beside it |
| The map takes no waypoint | the third refusal in a row leaves the map alone for two minutes, and the figure walks the road meanwhile; no place is blamed for it |
| The same plan fails again and again | from the third time the answer changes: out of the car that gets nowhere, on foot off in another direction each time |
| It stands and nothing helps | jump and run, look round and run, back and along the road; the fourth time the errand is given up for another, in a mission the three are tried again and no errand is begun; standing on a mission's letter while it starts is left alone |
| Pause, map or phone come up unasked | the reflex backs out; a phone gets two and a half seconds first, in case it rings |
| A question with a choice, a price, a save or Online in it | never answered by the reflex; the head is told and none of its skills confirms such a thing |
| A purchase | only in a shop's menu, only on a shop's errand or in a mission, only up to 150 dollars, never from a help text, never a property, never at home |
| A bed, a save | never: the saved game is Kerim's |
| The lower slot of the character wheel | cannot be highlighted: the stick never points down |
| A hand on the controller | the plan is put down and nothing is pressed until it is let go of |
| A damaged or frozen picture | nothing new is pressed; when the pictures stop everything is let go of, and a press cut short is not made again |
| The gaming PC is off | the rules play alone |
| A mission wants something no skill does | its help text's button is pressed once; failed three times, the mission is skipped where the game offers it; otherwise: open, and learnt from watching him |
