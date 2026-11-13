#!/bin/zsh
# The pilot plays the story by itself: the rules with the local model behind them, the guard on, the
# persistent memory beside the recordings. One command for a watched session at the console.
#
#   lab/live/story.sh [seconds, default 1800] [bold|careful, default bold] [repo to run from]
#
# The bridge has to run already (remoteplay/.venv/bin/ps5rp --host <console> --fps 60 daemon) with
# GTA V in the picture: this script starts no bridge and never looks at the console's own menus.
# It does not start while a person is on the controller or a recording runs. During the session a
# hand on the controller is Kerim taking over: the pilot puts its plan down, presses nothing, and
# plans afresh from the picture once the controller is let go of. Ctrl-C ends the session at once
# with everything let go.
#
# The local model is asked only where it answers: with the gaming PC off the rules play alone, and
# the walk's readings that need it (a door, a room) say so in the log instead of guessing.
limit=${1:-1800}
style=${2:-bold}
code=${3:-/Users/kerim/Documents/ChatGPT/gta}
api=http://127.0.0.1:9395
server=http://192.168.0.248:1234
model=qwen/qwen3-vl-4b
out=/Users/kerim/recordings/pilot
now() { date +%H:%M:%S }
is() { [[ $state == *"\"$1\": true"* ]] }

[[ $style == bold || $style == careful ]] || { echo "the style is bold or careful, not $style"; exit 2 }
cd $code/pilot || exit 1
state=$(curl -s -m 2 $api/status)
if [[ -z $state ]]; then echo "$(now) the bridge does not answer on $api: start it first"; exit 1; fi
if ! is session_up; then echo "$(now) the bridge has no session with the console"; exit 1; fi
if is human_input; then echo "$(now) a hand is on the controller: let go of it and start again"; exit 1; fi
if is recording; then echo "$(now) a recording runs: stop it first, the pilot keeps its own"; exit 1; fi
free=$(df -g $out 2>/dev/null | awk 'NR == 2 { print $4 }')
if [[ -n $free ]] && (( free < 4 )); then echo "$(now) only $free GB left on the disk"; exit 1; fi

judge=()
if curl -s -m 3 $server/v1/models >/dev/null; then
  judge=(--judge $server=$model)
  echo "$(now) the local model answers: it picks among what the rules offer"
else
  echo "$(now) the local model does not answer: the rules play alone"
fi
echo "$(now) playing for $limit s, driving $style; Ctrl-C ends it"
env -u PS5_HOST .venv/bin/python -m pilot.cli play --head local --guard --seconds $limit \
  --set style=$style $judge --record-dir $out
code=$?
last=$(ls -d $out/2026* 2>/dev/null | tail -n 1)
echo "$(now) ended with $code: $last"
[[ -n $last ]] && echo "what it did: pilot/.venv/bin/python lab/live/log.py $last"
exit $code
