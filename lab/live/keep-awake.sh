#!/bin/zsh
# Keeps the console and the bridge up while nobody plays: starts the bridge when it is gone, waits
# out a network that drops, and every four minutes turns the camera a little to one side and back,
# so that the console does not go to rest and the game does not drift into its idle scenery. It
# touches nothing while the pilot or a person is on the controller. A console that has gone to rest
# all the same is woken. Every nudge is printed with what the bridge answered, so that a look at the
# output tells whether the console is being kept awake or only meant to be. Ends by itself after the
# given number of seconds, because an agent's background task lives two hours at most.
#
#   lab/live/keep-awake.sh [seconds, default 6600] [console address, default 192.168.0.93]
limit=${1:-6600}
host=${2:-192.168.0.93}
every=240
cd /Users/kerim/Documents/ChatGPT/gta || exit 1
rp=remoteplay/.venv/bin/ps5rp
api=http://127.0.0.1:9395
now() { date +%H:%M:%S }
post() { curl -s -m 2 -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' -d "$1" $api/pad }
side=1; last=-$every; down=0; nudges=0; held=0; played=-$((3 * every))

while (( SECONDS < limit )); do
  state=$(curl -s -m 2 $api/status)
  if [[ -z $state ]]; then
    echo "$(now) the bridge is gone, starting it"
    $rp --host $host --fps 60 daemon >/dev/null 2>&1 &
    sleep 15
    continue
  fi
  if [[ $state == *'"console": "standby"'* ]]; then
    echo "$(now) the console is at rest, waking it"
    curl -s -m 10 -X POST $api/wake >/dev/null
    sleep 30
    continue
  fi
  if [[ $state != *'"session_up": true'* ]]; then
    (( down == 0 )) && echo "$(now) no picture from the console, waiting"
    down=1
    sleep 10
    continue
  fi
  (( down )) && { echo "$(now) the picture is back"; down=0; }
  [[ $state == *'"agent_pad": false'* && $state == *'"human_input": false'* ]] || played=$SECONDS
  if (( SECONDS - last >= every )); then
    busy=0
    [[ $state == *'"agent_pad": false'* && $state == *'"human_input": false'* ]] || busy=1
    # A recording is a session of the pilot or a person's play, also in the moments between two
    # presses: on 13 November, 01:28, a nudge went into the pause menu the pilot had just opened.
    # A recording nobody has played into for three rounds does not put the nudge off any longer.
    # (Counted from the last nudge, as it was, a nudge went into Kerim's play at 03:36, a minute
    # after his last press.)
    [[ $state == *'"recording": true'* ]] && (( SECONDS - played < 3 * every )) && busy=1
    if (( ! busy )); then
      for i in {1..8}; do code=$(post "{\"right\": [$((0.5 * side)), 0], \"ttl_ms\": 300}"); sleep 0.05; done
      post '{}' >/dev/null
      if [[ $code == 200 ]]; then
        side=$((-side)); last=$SECONDS; nudges=$((nudges + 1)); held=0
        echo "$(now) nudge $nudges sent"
      else
        echo "$(now) the bridge refused the nudge ($code)"
      fi
    elif (( SECONDS - held >= every )); then
      # a person or the pilot is on the controller, which keeps the console awake by itself
      echo "$(now) no nudge: somebody is on the controller"
      held=$SECONDS
    fi
  fi
  sleep 20
done
echo "$(now) done after $limit s, $nudges nudges"
