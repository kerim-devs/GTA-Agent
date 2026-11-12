#!/bin/sh
# Classify every finished recording that has not been classified yet.
#
#   lab/notes/process-new.sh [RECORDINGS_ROOT] [OUTPUT_ROOT]
#
# A recording is finished when its meta.json has "seconds"; one still being recorded is left alone.
# A recording is new when OUTPUT_ROOT/<name>/incidents.jsonl does not exist. For each new one this
# runs, in order and into OUTPUT_ROOT/<name>/: sections (pilot/tools/sections.py of this checkout,
# skipped when sections.json is already there), texts, missions and incidents. Then it rewrites
# OUTPUT_ROOT/summary.md and OUTPUT_ROOT/incidents.md over every classified recording.
# Nothing under RECORDINGS_ROOT is written. One recording is decoded at a time.

RECORDINGS=${1:-/Users/kerim/recordings/kerim}
OUT=${2:-/Users/kerim/recordings/derived/kerim}
PILOT="$(cd "$(dirname "$0")/../../pilot" && pwd)" || exit 1
PYTHON="$PILOT/.venv/bin/python"
unset PS5_HOST

if [ ! -d "$RECORDINGS" ]; then
  echo "No recordings root at $RECORDINGS" >&2
  exit 1
fi
mkdir -p "$OUT" || exit 1

finished() {
  "$PYTHON" -c 'import json, sys; sys.exit(0 if "seconds" in json.load(open(sys.argv[1])) else 1)' "$1/meta.json" 2>/dev/null
}

new=0
failed=0
for recording in "$RECORDINGS"/*/; do
  recording=${recording%/}
  name=$(basename "$recording")
  [ -f "$recording/meta.json" ] && [ -f "$recording/video.mp4" ] || continue
  finished "$recording" || { echo "$name: still being recorded, left alone"; continue; }
  [ -f "$OUT/$name/incidents.jsonl" ] && continue
  new=$((new + 1))
  echo "$name: classifying"
  if [ ! -f "$OUT/$name/sections.json" ]; then
    if [ ! -f "$PILOT/tools/sections.py" ]; then
      echo "$name: no sections.json and no $PILOT/tools/sections.py in this checkout;" \
        "merge the sections tool (P38) or put sections.json into $OUT/$name/" >&2
      failed=$((failed + 1))
      continue
    fi
    (cd "$PILOT" && "$PYTHON" tools/sections.py "$recording" --out "$OUT") || { failed=$((failed + 1)); continue; }
  fi
  (cd "$PILOT" && "$PYTHON" tools/texts.py "$recording" --out "$OUT") || { failed=$((failed + 1)); continue; }
  (cd "$PILOT" && "$PYTHON" tools/mission_notes.py "$recording" --texts "$OUT/$name/texts.jsonl" \
    --sections "$OUT/$name/sections.json" --out "$OUT/$name") || { failed=$((failed + 1)); continue; }
  (cd "$PILOT" && "$PYTHON" tools/incidents.py "$recording" --out "$OUT") || { failed=$((failed + 1)); continue; }
done

if [ "$new" -gt 0 ]; then
  set -- "$OUT"/*/missions.json
  dirs=""
  for path in "$@"; do
    dir=$(dirname "$path")
    [ -f "$dir/cases.json" ] && dirs="$dirs $dir"
  done
  if [ -n "$dirs" ]; then
    # shellcheck disable=SC2086
    (cd "$PILOT" && "$PYTHON" tools/mission_notes.py --summary "$OUT/summary.md" --dirs $dirs)
  fi
  (cd "$PILOT" && "$PYTHON" tools/incidents.py --summary "$OUT")
fi
echo "$new new recordings, $failed failed"
[ "$failed" -eq 0 ]
