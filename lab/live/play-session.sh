#!/bin/zsh
# Kerim plays and everything is kept: starts the bridge if it is not running and records picture and
# controller without a break, a new folder every fifteen minutes, until Ctrl-C or until less than
# 4 GB are left on the disk.
#
#   lab/live/play-session.sh [console address]        default 192.168.0.93
#
# Run it in a terminal of your own. An agent's session ends its background tasks after two hours and
# whenever the chat restarts. The controller is only recorded when it is plugged into this Mac and
# plays through the bridge; on the console itself it leaves no trace here and only the picture is kept.
host=${1:-192.168.0.93}
out=/Users/kerim/recordings/kerim
every=900
min_free_gb=4
cd /Users/kerim/Documents/ChatGPT/gta || exit 1
rp=remoteplay/.venv/bin/ps5rp
api=http://127.0.0.1:9395
state=""
field() { print -r -- "$state" | grep -o "\"$1\": [^,}]*" | head -n 1 | cut -d' ' -f2- }
now() { date +%H:%M:%S }
started=0; chunks=0; since=0; told=""; gone=0

if ! curl -s -m 2 $api/status >/dev/null; then
  echo "$(now) starting the bridge to $host"
  $rp --host $host --fps 60 daemon >/dev/null 2>&1 &
  started=1
fi

finish() {
  (( chunks )) && $rp record stop >/dev/null 2>&1
  (( started )) && $rp stop >/dev/null 2>&1
  echo "$(now) stopped; $chunks recordings under $out"
  exit ${1:-0}
}
trap 'finish 0' INT TERM

for i in {1..60}; do
  state=$(curl -s -m 2 $api/status)
  [[ $(field session_up) == true ]] && break
  sleep 1
done
if [[ $(field session_up) != true ]]; then
  echo "$(now) no picture from the console at $host: ${$(field last_error):-no answer}"
  echo "         is this Mac on the console's network, and is the console on?"
  finish 1
fi
if [[ $(field agent_pad) == true ]]; then
  echo "$(now) the pilot is sending to the console; stop it first"
  finish 1
fi
# A recording somebody else started would never be cut into pieces here; close it and start our own.
[[ $(field recording) == true ]] && $rp record stop >/dev/null 2>&1

while true; do
  state=$(curl -s -m 2 $api/status)
  if [[ -z $state ]]; then
    # A network that drops takes the bridge's answer with it for a moment; a bridge that died is started again.
    (( gone == 0 )) && echo "$(now) the bridge does not answer, waiting"
    gone=$((gone + 1))
    if (( gone % 15 == 0 )) && ! pgrep -f "ps5rp.*daemon" >/dev/null; then
      echo "$(now) starting the bridge again"
      $rp --host $host --fps 60 daemon >/dev/null 2>&1 &
      started=1
    fi
    sleep 2
    continue
  fi
  (( gone )) && { echo "$(now) the bridge answers again"; gone=0; }
  free=$(df -g $out | awk 'NR == 2 { print $4 }')
  if (( free < min_free_gb )); then
    echo "$(now) only $free GB left on the disk"
    finish 1
  fi
  pad=$(field gamepad)
  if [[ $pad != $told ]]; then
    if [[ $pad == null ]]; then
      echo "$(now) no controller on this Mac: only the picture is kept"
    else
      echo "$(now) controller on this Mac: $pad, its input is kept"
    fi
    told=$pad
  fi
  if [[ $(field recording) != true ]]; then
    if $rp record start -o $out --note "Kerim plays, play-session.sh, controller on the Mac: $pad" >/dev/null 2>&1; then
      chunks=$((chunks + 1)); since=$SECONDS
      echo "$(now) recording $chunks"
    else
      echo "$(now) the recording did not start: ${$(field last_error):-no reason given}"
      sleep 5
    fi
  elif (( SECONDS - since >= every )); then
    $rp record stop >/dev/null 2>&1  # the next round opens the next folder
  fi
  sleep 2
done
