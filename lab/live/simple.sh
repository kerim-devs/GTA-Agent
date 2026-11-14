#!/bin/zsh
# Three steps and nothing else: the pilot takes a car, marks a destination it chooses, drives there,
# and begins again. The model chooses the step and the destination; every other skill is out of reach.
# lab/live/simple.sh [seconds, default 600] [bold|careful, default bold] [shadow]
# Before input, check the game picture and refuse an active human pad or recording. With `shadow`
# nothing is sent to the controller and nothing is recorded: the pilot only says what it would do,
# also while a person plays.
limit=${1:-600}
style=${2:-bold}
shadow=${3:-}
code=${0:A:h:h:h}
api=http://127.0.0.1:9395
server=http://192.168.0.248:1234
model=qwen/qwen3-vl-4b
out=/Users/kerim/recordings/pilot
now() { date +%H:%M:%S }
is() { [[ $state == *"\"$1\": true"* ]] }

[[ $style == bold || $style == careful ]] || { echo "the style is bold or careful, not $style"; exit 2 }
[[ -z $shadow || $shadow == shadow ]] || { echo "the third argument is shadow or nothing, not $shadow"; exit 2 }
cd "$code/pilot" || exit 1
# A worktree without its own environment borrows one; the code is this worktree's all the same.
python=.venv/bin/python
[[ -x $python ]] || python=${PILOT_PYTHON:-/private/tmp/gta-trip/pilot/.venv/bin/python}
export PYTHONPATH=$code/pilot/src
state=$(curl -s -m 2 $api/status)
if [[ -z $state ]]; then echo "$(now) the bridge does not answer on $api: start it first"; exit 1; fi
if ! is session_up; then echo "$(now) the bridge has no session with the console"; exit 1; fi
if [[ -z $shadow ]]; then
  if is human_input; then echo "$(now) a hand is on the controller: let go of it and start again"; exit 1; fi
  if is recording; then echo "$(now) a recording runs: stop it first, the pilot keeps its own"; exit 1; fi
  free=$(df -g $out 2>/dev/null | awk 'NR == 2 { print $4 }')
  if [[ -n $free ]] && (( free < 4 )); then echo "$(now) only $free GB left on the disk"; exit 1; fi

  # This reads a fresh picture only; no controller or recording call is made by the check.
  env -u PS5_HOST $python - <<'CHECK' || exit 1
from pilot.bridge import Bridge
from pilot.conductor import minimap_crop
from pilot import hud, minimap

with Bridge() as bridge:
    frame = bridge.frame()
    if frame is None or not 0 <= frame.age <= 0.3:
        raise SystemExit("no fresh game picture")
    reading = minimap.read(minimap_crop(frame.rgb))
    screen = hud.read(frame.rgb).screen
    if screen != "game" or reading.minimap not in {"flat", "tilted"}:
        raise SystemExit("start with GTA gameplay visible")
CHECK
fi

# SIMPLE_SET="name=value name=value": driving settings on top of the style, for a trial at the console.
# Without it the line in lab/live/trial.set is read, if that file is there (it is not in the repository).
[[ -z $SIMPLE_SET && -r ${0:A:h}/trial.set ]] && SIMPLE_SET=$(<${0:A:h}/trial.set)
more=()
for setting in ${=SIMPLE_SET}; do more+=(--set $setting); done
[[ -n $SIMPLE_SET ]] && echo "$(now) trial settings: $SIMPLE_SET"
if ! curl -s -m 3 $server/v1/models >/dev/null; then
  echo "$(now) the local model does not answer on $server: it chooses the steps, so nothing starts without it"
  exit 1
fi
[[ -n $shadow ]] && more+=(--shadow --no-record)
echo "$(now) car, destination, drive for at most $limit s; $model chooses; Ctrl-C ends it"
env -u PS5_HOST $python -m pilot.cli play --task simple --seconds "$limit" \
  --set style=$style $more --judge $server=$model --record-dir $out
result=$?
echo "$(now) session ended with $result"
exit $result
