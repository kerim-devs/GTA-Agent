#!/bin/zsh
# Says whether the line from this Mac to the console is fit for a live session, and watches it while
# one runs. On 13 November, 16:35, the picture broke up in the middle of a drive: 628 frames the
# decoder could not read, no video for the watchdog's patience, three reconnects the console refused
# because it still held the old session, and a new one 19 s after the first bad frame. The Mac was
# reaching the console over Wi-Fi all along (en0, pings from 3 to 81 ms within six seconds), although
# the console itself hangs on a cable. A line that passes here is a cable on both ends.
#
#   lab/live/line.sh            one check, twenty seconds: the interface, the pings, the bridge
#   lab/live/line.sh watch      a line whenever the pings or the bridge go bad, until stopped
#   lab/live/line.sh watch all  a line every round, good or bad
#
# Ends 0 when the line is fit and 1 when it is not, so that a session script can refuse to start.
host=${PS5_LINE_HOST:-192.168.0.93}
api=http://127.0.0.1:9395
max_ms=15      # the slowest ping a cable in one room may show
avg_ms=3
now() { date +%H:%M:%S }

interface() {
  local dev port
  dev=$(route -n get $host 2>/dev/null | awk '/interface:/{print $2}')
  port=$(networksetup -listallhardwareports 2>/dev/null | awk -v d="$dev" '/Hardware Port:/{p=substr($0, 16)} $0 == "Device: " d {print p}')
  print -r -- "${dev:-none} ${port:-unknown}"
}

# loss in percent, then the average, the slowest and the spread in ms
pings() {
  ping -c $1 -i 0.2 -q $host 2>/dev/null | awk -F'[ /%]+' '
    /packet loss/ { for (i = 1; i <= NF; i++) if ($i == "packet" && $(i+1) == "loss") loss = $(i-1) }
    /round-trip/  { n = split($0, part, " = "); split(part[2], v, "/"); avg = v[2]; max = v[3]; sd = v[4] + 0 }
    END { printf "%s %s %s %s\n", (loss == "" ? 100 : loss), (avg == "" ? 0 : avg), (max == "" ? 0 : max), (sd == "" ? 0 : sd) }'
}

bridge() {
  local state
  state=$(curl -s -m 2 $api/status)
  if [[ -z $state ]]; then print "down"; return; fi
  [[ $state == *'"session_up": true'* ]] && print "up" || print "no-session"
}

verdict() {  # loss avg max -> the reasons the pings are not good enough, or nothing
  local bad=()
  (( $1 > 0 )) && bad+=("$1 % of the pings lost")
  (( $3 > max_ms )) && bad+=("a ping of ${3%.*} ms, more than $max_ms")
  (( $2 > avg_ms )) && bad+=("${2%.*} ms on average, more than $avg_ms")
  print -r -- ${(j:; :)bad}
}

if [[ $1 == watch ]]; then
  echo "$(now) watching the line to $host: $(interface)"
  while true; do
    read loss avg max sd <<< "$(pings 25)"
    why=$(verdict $loss $avg $max)
    up=$(bridge)
    [[ $up != up ]] && why="${why:+$why; }the bridge is $up"
    if [[ -n $why ]]; then
      echo "$(now) BAD  $why (avg $avg, max $max, spread $sd ms)"
    elif [[ $2 == all ]]; then
      echo "$(now) good avg $avg, max $max, spread $sd ms"
    fi
    sleep 25
  done
fi

fit=0
read dev port <<< "$(interface)"
if [[ $port == *Wi-Fi* || $port == *AirPort* ]]; then
  echo "NOT FIT  the Mac reaches the console over Wi-Fi ($dev). Plug the Mac into the router by cable"
  echo "         and put that cable above Wi-Fi in System Settings, Network, service order."
  fit=1
elif [[ $dev == none ]]; then
  echo "NOT FIT  no way to $host"
  fit=1
else
  echo "ok       the Mac reaches the console over $port ($dev)"
fi
echo "         pinging for twenty seconds ..."
read loss avg max sd <<< "$(pings 100)"
why=$(verdict $loss $avg $max)
if [[ -n $why ]]; then
  echo "NOT FIT  $why (avg $avg, max $max, spread $sd ms)"
  fit=1
else
  echo "ok       100 pings, none lost, avg $avg, max $max, spread $sd ms"
fi
case $(bridge) in
  up) echo "ok       the bridge is up and has a picture" ;;
  no-session) echo "note     the bridge is up without a picture from the console" ;;
  *) echo "note     no bridge is running (lab/live/bridge.sh starts one that stays)" ;;
esac
(( fit == 0 )) && echo "The line is fit for a live session." || echo "The line is NOT fit for a live session."
exit $fit
