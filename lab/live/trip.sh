#!/bin/zsh
# One fixed destination, from the nearest car to a verified arrival.
# lab/live/trip.sh [place, default Ammu-Nation] [seconds, default 900] [bold|careful, default bold]
# Before input, check the game picture and refuse an active human pad or recording.
place=${1:-Ammu-Nation}
limit=${2:-900}
style=${3:-bold}
code=${0:A:h:h:h}
api=http://127.0.0.1:9395
server=http://192.168.0.248:1234
model=qwen/qwen3-vl-4b
out=/Users/kerim/recordings/pilot
now() { date +%H:%M:%S }
is() { [[ $state == *"\"$1\": true"* ]] }

[[ $style == bold || $style == careful ]] || { echo "the style is bold or careful, not $style"; exit 2 }
cd "$code/pilot" || exit 1
state=$(curl -s -m 2 $api/status)
if [[ -z $state ]]; then echo "$(now) the bridge does not answer on $api: start it first"; exit 1; fi
if ! is session_up; then echo "$(now) the bridge has no session with the console"; exit 1; fi
if is human_input; then echo "$(now) a hand is on the controller: let go of it and start again"; exit 1; fi
if is recording; then echo "$(now) a recording runs: stop it first, the pilot keeps its own"; exit 1; fi
free=$(df -g $out 2>/dev/null | awk 'NR == 2 { print $4 }')
if [[ -n $free ]] && (( free < 4 )); then echo "$(now) only $free GB left on the disk"; exit 1; fi

# This reads a fresh picture only; no controller or recording call is made by the check.
env -u PS5_HOST .venv/bin/python - <<'CHECK' || exit 1
from pilot.bridge import Bridge
from pilot.conductor import minimap_crop
from pilot import hud, minimap

with Bridge() as bridge:
    frame = bridge.frame()
    if frame is None or not 0 <= frame.age <= 0.3:
        raise SystemExit("no fresh game picture")
    reading = minimap.read(minimap_crop(frame.rgb))
    screen = hud.read(frame.rgb).screen
    # A map called damaged is still the game's map: where a broad road's edge lies on a block border
    # the reader says so of a clean one, and five starts in a row were refused for it on 14 November.
    if screen != "game" or reading.minimap not in {"flat", "tilted"}:
        raise SystemExit("start the trip with GTA gameplay visible")
CHECK

# TRIP_SET="name=value name=value": driving settings on top of the style, for a trial at the console.
# Without it the line in lab/live/trial.set is read, if that file is there (it is not in the repository).
[[ -z $TRIP_SET && -r ${0:A:h}/trial.set ]] && TRIP_SET=$(<${0:A:h}/trial.set)
more=()
for setting in ${=TRIP_SET}; do more+=(--set $setting); done
[[ -n $TRIP_SET ]] && echo "$(now) trial settings: $TRIP_SET"
judge=()
if curl -s -m 3 $server/v1/models >/dev/null; then
  judge=(--judge $server=$model)
  echo "$(now) the local judge answers"
else
  echo "$(now) the local judge does not answer: using the readers"
fi
echo "$(now) going to $place for at most $limit s; Ctrl-C ends it"
env -u PS5_HOST .venv/bin/python -m pilot.cli play --task trip --place "$place" --seconds "$limit" \
  --set style=$style $more $judge --record-dir $out
result=$?
echo "$(now) trip session ended with $result"
exit $result
