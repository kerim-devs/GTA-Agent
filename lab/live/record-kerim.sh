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
owned=; quiet=0; began=0
# A successful read prints only an active recording's exact directory; an empty line means stopped.
active_dir() {
  python3 -c 'import json, sys
try:
    row = json.load(sys.stdin)
    assert type(row["recording"]) is bool
    directory = row.get("dir")
    assert not row["recording"] or (isinstance(directory, str) and directory)
    print(directory if row["recording"] else "")
except (ValueError, KeyError, TypeError, AssertionError):
    sys.exit(1)'
}
read_record() {
  local reply
  reply=$(curl -fsS -m 2 http://127.0.0.1:9395/record 2>/dev/null) || return 1
  print -r -- "$reply" | active_dir
}
start() {
  local reply
  reply=$(remoteplay/.venv/bin/ps5rp record start -o $out --note "$note" 2>/dev/null) || return 1
  owned=$(print -r -- "$reply" | active_dir) || return 1
  [[ "$owned" == "$out/"* ]] || { owned=; return 1; }
  quiet=0; began=$SECONDS
}
stop() {
  local current
  current=$(read_record) || return 1
  [[ -n "$owned" && "$current" == "$owned" ]] || return 1
  remoteplay/.venv/bin/ps5rp record stop >/dev/null 2>&1
}
record_dir=$(read_record) && [[ "$record_dir" == "$out/"* ]] && {
  owned=$record_dir; began=$SECONDS; echo "$(date +%H:%M:%S) taking over the running recording"
}
while true; do
  state=$(curl -fsS -m 2 http://127.0.0.1:9395/status 2>/dev/null) || { sleep 1; continue; }
  human=$(print -r -- "$state" | python3 -c 'import json, sys
try:
    value = json.load(sys.stdin)["human_input"]
    assert type(value) is bool
    print(int(value))
except (ValueError, KeyError, TypeError, AssertionError):
    sys.exit(1)') || { sleep 1; continue; }
  record_dir=$(read_record) || { sleep 1; continue; }
  free=$(df -g $out | awk 'NR == 2 { print $4 }')
  if [[ -n "$owned" && "$record_dir" != "$owned" ]]; then
    echo "$(date +%H:%M:%S) recording no longer owned: $owned"
    owned=; quiet=0
  fi
  if [[ -z "$owned" ]]; then
    if [[ "$human" == 1 && -z "$record_dir" ]]; then
      if (( free < min_free_gb )); then
        echo "$(date +%H:%M:%S) only $free GB left on the disk, not recording"; exit 1
      fi
      start && echo "$(date +%H:%M:%S) recording started"
    fi
  else
    if (( human == 1 )); then quiet=0; else quiet=$((quiet + 1)); fi
    if (( quiet >= quiet_limit || free < min_free_gb )); then
      if stop; then
        echo "$(date +%H:%M:%S) recording stopped: $owned"
        owned=
      fi
    elif (( SECONDS - began >= cut_after )); then
      if stop; then
        echo "$(date +%H:%M:%S) recording cut: $owned"
        owned=
        start || owned=
      fi
    fi
  fi
  sleep 1
done
