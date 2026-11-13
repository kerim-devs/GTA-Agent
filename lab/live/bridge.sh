#!/bin/zsh
# Holds the bridge to the console up for as long as a live session lasts, from a terminal of
# Kerim's own. A bridge an agent starts lives in that agent's background task, which ends after two
# hours and takes the picture and the pad with it; handing it over to a fresh task leaves a gap of
# its own. This one is started once, starts the daemon again whenever it ends, and writes what the
# daemon says, with every lost picture and every reconnect, to a log beside the recordings.
#
#   lab/live/bridge.sh [console address, default 192.168.0.93]
#
# Ctrl-C ends it. Check the line first with lab/live/line.sh.
host=${1:-192.168.0.93}
cd /Users/kerim/Documents/ChatGPT/gta || exit 1
log=/Users/kerim/recordings/bridge-$(date +%Y%m%d).log
if curl -s -m 2 http://127.0.0.1:9395/status >/dev/null; then
  echo "A bridge is up already, perhaps an agent's. It has to end before this one can take the console."
  exit 1
fi
trap 'echo "$(date +%H:%M:%S) bridge stopped by hand" | tee -a $log; exit 0' INT TERM
while true; do
  echo "$(date +%H:%M:%S) bridge starting, log in $log" | tee -a $log
  remoteplay/.venv/bin/ps5rp --host $host --fps 60 daemon >>$log 2>&1
  echo "$(date +%H:%M:%S) bridge ended ($?), starting again in 3 s" | tee -a $log
  sleep 3
done
