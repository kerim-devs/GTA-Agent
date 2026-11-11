#!/bin/zsh
# Records Kerim's own play: starts when his controller reports input through the bridge and no
# recording runs, stops after two quiet minutes. Prints one line per start and stop.
cd /Users/kerim/Documents/ChatGPT/gta
mine=0; quiet=0
while true; do
  state=$(curl -s -m 2 http://127.0.0.1:9395/status)
  human=$(print -r -- "$state" | grep -c '"human_input": true')
  recording=$(print -r -- "$state" | grep -c '"recording": true')
  if (( mine == 0 )); then
    if (( human == 1 && recording == 0 )); then
      remoteplay/.venv/bin/ps5rp record start -o /Users/kerim/recordings/kerim --note "Kerim plays on 11 November, afternoon, started by the watcher" >/dev/null 2>&1 && { mine=1; quiet=0; echo "$(date +%H:%M:%S) recording started"; }
    fi
  else
    if (( human == 1 )); then quiet=0; else quiet=$((quiet + 1)); fi
    if (( quiet >= 120 || recording == 0 )); then
      remoteplay/.venv/bin/ps5rp record stop >/dev/null 2>&1; mine=0
      echo "$(date +%H:%M:%S) recording stopped: $(ls -d /Users/kerim/recordings/kerim/2026* | tail -n 1)"
    fi
  fi
  sleep 1
done
