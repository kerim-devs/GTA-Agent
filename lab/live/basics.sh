#!/bin/zsh
# Tries the pilot's basic skills one at a time, each in a round of its own with a fixed plan and no
# head that could change its mind, so that one session folder holds one try of one skill: getting
# out, walking to the road, getting into a vehicle, setting the waypoint on a place from the map's
# legend, driving the route. Writes one line per try to the list that lab/live/basics.py counts.
# Waits while a person plays or a recording runs and ends a running try at once when a controller
# reports input.
#
#   lab/live/basics.sh [cycles, default 5] [list, default /Users/kerim/recordings/pilot/basics.tsv] [repo]
#                      [steps, default "leave walk enter place drive"; "waypoint" is the old way with the cursor]
cycles=${1:-5}
list=${2:-/Users/kerim/recordings/pilot/basics.tsv}
code=${3:-/Users/kerim/Documents/ChatGPT/gta}
chosen=(${=4:-leave walk enter place drive})
api=http://127.0.0.1:9395
judge=http://192.168.0.248:1234=qwen/qwen3-vl-8b
out=/Users/kerim/recordings/pilot
# After its one plan the scripted head would follow any route it sees, on foot as well; these keep it still.
still='[{"name": "wait", "args": {"duration": 30}}]'
steps=(
  'leave 8 [{"name": "press", "args": {"button": "triangle", "duration": 1}}]'
  'walk 28 [{"name": "walk_road", "args": {"duration": 20}}]'
  'enter 33 [{"name": "enter_vehicle", "args": {"duration": 25, "kind": "any"}}]'
  'place 32 next'
  'waypoint 52 [{"name": "set_waypoint", "args": {"target": "away"}}]'
  'drive 66 [{"name": "drive_route", "args": {"duration": 60}}]'
)
now() { date +%H:%M:%S }
pid=0
cd $code/pilot || exit 1
trap '(( pid )) && kill -INT $pid 2>/dev/null; wait; echo "$(now) stopped"; exit 0' INT TERM

for cycle in {1..$cycles}; do
  for step in $steps; do
    name=${step%% *}; rest=${step#* }; seconds=${rest%% *}; plan=${rest#* }
    (( ${chosen[(Ie)$name]} )) || continue
    # The camera is levelled before a try on foot; the map needs none, and in first person that step fails.
    level=(); [[ $name == place || $name == waypoint ]] && level=(--no-level)
    while true; do
      state=$(curl -s -m 2 $api/status)
      [[ $state == *'"session_up": true'* && $state == *'"human_input": false'* && $state == *'"recording": false'* ]] && break
      sleep 5
    done
    before=$(ls -d $out/2026* | tail -n 1)
    [[ $plan == next ]] && plan="[{\"name\": \"set_waypoint\", \"args\": $(.venv/bin/python ../lab/live/next_place.py $list)}]"
    env -u PS5_HOST .venv/bin/python -m pilot.cli play $level --head scripted --plan $plan --plan $still --plan $still \
      --plan $still --plan $still --seconds $seconds --judge $judge --record-dir $out >/dev/null 2>&1 &
    pid=$!
    cut=0
    while kill -0 $pid 2>/dev/null; do
      sleep 1
      if [[ $(curl -s -m 2 $api/status) == *'"human_input": true'* ]]; then
        kill -INT $pid 2>/dev/null; cut=1
        break
      fi
    done
    wait $pid 2>/dev/null; pid=0
    folder=$(ls -d $out/2026* | tail -n 1)
    if (( cut )) || [[ $folder == $before ]]; then
      echo "$(now) cycle $cycle $name: cut short, not counted"
    else
      printf '%s\t%s\t%s\n' $cycle $name $folder >> $list
      echo "$(now) cycle $cycle $name: $folder"
    fi
  done
done
echo "$(now) done"
