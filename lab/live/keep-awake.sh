#!/bin/zsh
# Keeps the console and the bridge up while nobody plays: starts the bridge when it is gone, waits
# out a network that drops, and every four minutes turns the camera a little to one side and back,
# so that the console does not go to rest and the game does not drift into its idle scenery. It
# touches nothing while the pilot or a person is on the controller. Ends by itself after the given
# number of seconds, because an agent's background task lives two hours at most.
#
#   lab/live/keep-awake.sh [seconds, default 6600] [console address, default 192.168.0.93]
limit=${1:-6600}
host=${2:-192.168.0.93}
every=240
cd /Users/kerim/Documents/ChatGPT/gta || exit 1
rp=remoteplay/.venv/bin/ps5rp
api=http://127.0.0.1:9395
now() { date +%H:%M:%S }
post() { curl -s -m 2 -X POST -H 'Content-Type: application/json' -d "$1" $api/pad >/dev/null }
side=1; last=-$every; down=0; nudges=0

while (( SECONDS < limit )); do
  state=$(curl -s -m 2 $api/status)
  if [[ -z $state ]]; then
    echo "$(now) the bridge is gone, starting it"
    $rp --host $host --fps 60 daemon >/dev/null 2>&1 &
    sleep 15
    continue
  fi
  if [[ $state != *'"session_up": true'* ]]; then
    (( down == 0 )) && echo "$(now) no picture from the console, waiting"
    down=1
    sleep 10
    continue
  fi
  (( down )) && { echo "$(now) the picture is back"; down=0; }
  if (( SECONDS - last >= every )) && [[ $state == *'"agent_pad": false'* && $state == *'"human_input": false'* ]]; then
    for i in {1..8}; do post "{\"right\": [$((0.5 * side)), 0], \"ttl_ms\": 300}"; sleep 0.05; done
    post '{}'
    side=$((-side)); last=$SECONDS; nudges=$((nudges + 1))
  fi
  sleep 20
done
echo "$(now) done after $limit s, $nudges nudges"
