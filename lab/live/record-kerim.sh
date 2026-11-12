#!/bin/zsh
# Records Kerim's own play: starts when his controller reports input through the bridge and no
# recording runs, stops after ten quiet minutes, which keeps a cutscene and the objective after it.
# A running recording is cut every twenty minutes: the video can only be read once it is closed, and
# a bridge that dies would otherwise take hours of play with it. Gives up when the disk runs low.
# Started while a recording of his is already running, it takes that one over. Prints one line per
# start, cut and stop.
#
#   lab/live/record-kerim.sh [quiet seconds before it stops, default 600]
cd /Users/kerim/Documents/ChatGPT/gta
out=/Users/kerim/recordings/kerim
note="Kerim plays on $(LC_ALL=C date '+%-d %B'), started by the watcher"
quiet_limit=${1:-600}; cut_after=1200; min_free_gb=4
mine=0; quiet=0; began=0
start() { remoteplay/.venv/bin/ps5rp record start -o $out --note "$note" >/dev/null 2>&1; }
stop() { remoteplay/.venv/bin/ps5rp record stop >/dev/null 2>&1; }
last() { ls -d $out/2026* | tail -n 1; }
if [[ $(curl -s -m 2 http://127.0.0.1:9395/record) == *'"recording": true'*"\"dir\": \"$out/"* ]]; then
  mine=1; began=$SECONDS; echo "$(date +%H:%M:%S) taking over the running recording"
fi
while true; do
  state=$(curl -s -m 2 http://127.0.0.1:9395/status)
  human=$(print -r -- "$state" | grep -c '"human_input": true')
  recording=$(print -r -- "$state" | grep -c '"recording": true')
  free=$(df -g $out | awk 'NR == 2 { print $4 }')
  if (( mine == 0 )); then
    if (( human == 1 && recording == 0 )); then
      if (( free < min_free_gb )); then
        echo "$(date +%H:%M:%S) only $free GB left on the disk, not recording"; exit 1
      fi
      start && { mine=1; quiet=0; began=$SECONDS; echo "$(date +%H:%M:%S) recording started"; }
    fi
  else
    if (( human == 1 )); then quiet=0; else quiet=$((quiet + 1)); fi
    if (( quiet >= quiet_limit || recording == 0 || free < min_free_gb )); then
      stop; mine=0
      echo "$(date +%H:%M:%S) recording stopped: $(last)"
    elif (( SECONDS - began >= cut_after )); then
      stop
      echo "$(date +%H:%M:%S) recording cut: $(last)"
      if start; then began=$SECONDS; else mine=0; fi
    fi
  fi
  sleep 1
done
