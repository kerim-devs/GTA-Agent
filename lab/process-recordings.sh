#!/bin/zsh
# Classifies every finished recording of Kerim's play that has not been classified yet: sections with
# the judge, screen texts, missions with what each objective asks for, what went wrong, and the action
# of every stretch. Everything derived lies beside the recordings and never in them:
#
#   <recordings root>/kerim/<name>/            video.mp4, frames.jsonl, pad.jsonl, meta.json (never written)
#   <recordings root>/derived/kerim/<name>/    sections.json, texts.jsonl, missions.json, cases.json,
#                                              incidents.jsonl, actions.jsonl and the readers' caches
#   <recordings root>/derived/kerim/           index.jsonl, summary.md, incidents.md over all of them
#
#   lab/process-recordings.sh [recordings root, default /Users/kerim/recordings] [judge URL=MODEL]
#
# A recording still being written (its meta.json has no "seconds") is left alone. Without a judge that
# answers, the sections come from the readers alone and more of them stay unknown.
root=${1:-/Users/kerim/recordings}
judge=${2:-http://192.168.0.248:1234=qwen/qwen3-vl-8b}
here=${0:A:h}
pilot=$here/../pilot
python=$pilot/.venv/bin/python
rec=$root/kerim
out=$root/derived/kerim
unset PS5_HOST
mkdir -p $out || exit 1
now() { date +%H:%M:%S }

server=${judge%%=*}
if curl -s -m 4 $server/v1/models >/dev/null; then with=(--judge $judge); else with=(); echo "$(now) the judge does not answer, sections from the readers alone"; fi
for dir in $rec/*(/N); do
  name=${dir:t}
  [[ -f $dir/meta.json && -f $dir/video.mp4 ]] || continue
  grep -q '"seconds"' $dir/meta.json || { echo "$(now) $name is still being recorded"; continue; }
  [[ -f $out/$name/sections.json ]] && continue
  echo "$(now) $name: sections"
  (cd $pilot && $python tools/sections.py $dir --out $out $with) || echo "$(now) $name: sections failed"
done
echo "$(now) texts, missions and incidents"
$here/notes/process-new.sh $rec $out
echo "$(now) actions"
$here/actions/process-new.sh $rec $out
echo "$(now) done"
