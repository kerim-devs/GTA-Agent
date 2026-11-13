The connected mission-trip tests use the 19 recorded requests committed in e93c7e5, the existing own-car-1957 fixture and the P93 arrival fixture. The request fixture names its source recordings, line numbers and hashes. Inputs come from 20261113-195746, 20261113-202110, 20261113-202400 and 20261113-183223. This is an offline decision and controller test, not evidence that new actions succeed in the recorded world.

The first run of the seven unchanged tests reported `3 failed, 4 passed in 0.19s`. Two failures were adapters: the new policy's wait had no result in the old recording, and the P93 fixture carries a mode without a complete judge response. The adapter now executes each newly planned wait through the real SkillRunner before supplying the next recorded waypoint result. The clock advances without inventing a fresh image or judge response. The observation adapter preserves P93's mode without constructing a missing Judgment. Assertions about bounded attempts, retained goals, arrival and neutral input remain unchanged.

The final run reported `2 failed, 6 passed in 0.18s`, exit 1. The original open-map test remains red. A separate regression executes two actual waits and shows that the second completion produces `go_on` although neither runner has an active plan. The equal result dictionaries collide in the draft's result deduplication. Neither failure is marked xfail or skipped. The open-map test stops before its old-deadline assertion, so that assertion remains unverified. Arrival passes at the recorded 46 m road endpoint; it does not establish mission entry. Ruff check and format passed. No production files, console inputs, bridge calls or model calls were used, and no full gate was run.

Validation imports production code from the uncommitted draft in `/private/tmp/gta-fixed-mission-trip`, based on a1b7401. The test branch alone does not contain the new MissionHead API. From `/private/tmp/gta-mission-trip-replay`, reproduce with:

```sh
env -u PS5_HOST PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/private/tmp/gta-fixed-mission-trip/pilot/src /Users/kerim/Documents/ChatGPT/gta/pilot/.venv/bin/python -m pytest -p no:cacheprovider -q pilot/tests/test_mission_trip_replay.py --basetemp=/private/tmp/gta-mission-replay-check
/Users/kerim/Documents/ChatGPT/gta/pilot/.venv/bin/ruff check --no-cache pilot/tests/test_mission_trip_replay.py
```

The captured outputs are `/private/tmp/gta-mission-replay-baseline.txt` and `/private/tmp/gta-mission-replay-adapted.txt`. The production file hashes at validation were:

```text
6b92c48f7f8f86f578cb456bfba380998529fa65066bd1dc9a00680423c39477  pilot/src/pilot/mission.py
695c964e95e46277e706bf6200fb42d94e135caa6dd3a2ebd6dc2d344e83d997  pilot/src/pilot/errands.py
9cba42f675ee22b5e44d6fd0022a46b3e796b05777306ff19ef1100ae7c460d1  pilot/src/pilot/skills.py
7880b4ca3e9b36fc9acc3be3574ef6bfafb4462c64534c8d816336a2eac20736  pilot/src/pilot/conductor.py
9de064ba5ba9890697247ec149e56a0fa4b0b739d2c8e6eecbec6443f37e0a73  pilot/src/pilot/own_vehicle.py
```
