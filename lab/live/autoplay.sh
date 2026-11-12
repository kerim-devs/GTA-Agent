#!/bin/zsh
# Lets the pilot play by itself in rounds while nobody is on the controller: free roam by the rules,
# and every third round a street fight, so that walking, taking a car, driving, hitting and getting
# away from the police all come up. Starts no round while a person plays or a recording runs:
# Kerim's play is recorded by record-kerim.sh, which this script leaves alone. Ends a running round
# at once when his controller reports input. Ends by itself after the given number of seconds,
# because an agent's background task lives two hours at most.
#
#   lab/live/autoplay.sh [seconds, default 6600] [seconds per round, default 240] [repo to run from]
limit=${1:-6600}
round=${2:-240}
code=${3:-/Users/kerim/Documents/ChatGPT/gta}
api=http://127.0.0.1:9395
judge=http://192.168.0.248:1234=qwen/qwen3-vl-8b
out=/Users/kerim/recordings/pilot
punch='[{"name": "punch", "args": {"duration": 20}}, {"name": "punch", "args": {"duration": 20}}]'
now() { date +%H:%M:%S }
is() { [[ $state == *"\"$1\": true"* ]] }
n=0; pid=0
cd $code/pilot || exit 1
trap '(( pid )) && kill -INT $pid 2>/dev/null; wait; echo "$(now) stopped after $n rounds"; exit 0' INT TERM

while (( SECONDS < limit )); do
  state=$(curl -s -m 2 $api/status)
  if ! is session_up || is human_input || is recording; then sleep 5; continue; fi
  free=$(df -g $out | awk 'NR == 2 { print $4 }')
  if (( free < 4 )); then echo "$(now) only $free GB left on the disk, not playing"; exit 1; fi
  n=$((n + 1))
  if (( n % 3 == 0 )); then
    kind=punch; args=(--head scripted --plan $punch --seconds 60)
  else
    kind=rules; args=(--head rules --seconds $round)
  fi
  echo "$(now) round $n, $kind"
  env -u PS5_HOST .venv/bin/python -m pilot.cli play $args --judge $judge --record-dir $out >/dev/null 2>&1 &
  pid=$!
  while kill -0 $pid 2>/dev/null; do
    sleep 1
    if [[ $(curl -s -m 2 $api/status) == *'"human_input": true'* ]]; then
      echo "$(now) a person is on the controller, ending the round"
      kill -INT $pid 2>/dev/null
      break
    fi
  done
  wait $pid 2>/dev/null; pid=0
  echo "$(now) round $n ended: $(ls -d $out/2026* | tail -n 1)"
done
echo "$(now) done after $n rounds"
