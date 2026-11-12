#!/usr/bin/env bash
# Label every finished recording that has no labels yet, then refresh the index and the summary.
#
#   lab/actions/process-new.sh [RECORDINGS_ROOT] [OUTPUT_ROOT]
#
# A finished recording is a folder whose meta.json has "seconds"; one still being recorded is left alone.
# Everything runs in one process, about three and a half minutes per hour of recording on this Mac.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
pilot="$here/../../pilot"
python="$pilot/.venv/bin/python"
recordings="${1:-/Users/kerim/recordings/kerim}"
out="${2:-/Users/kerim/recordings/derived/kerim}"

new=()
for meta in "$recordings"/*/meta.json; do
  [ -e "$meta" ] || continue
  dir="$(dirname "$meta")"
  name="$(basename "$dir")"
  [ -e "$out/$name/actions.jsonl" ] && continue
  "$python" -c 'import json, sys; sys.exit(json.load(open(sys.argv[1])).get("seconds") is None)' "$meta" \
    2>/dev/null || continue
  new+=("$dir")
done

mkdir -p "$out"
echo "${#new[@]} new recording(s) under $recordings"
exec "$python" "$pilot/tools/label_actions.py" ${new[@]+"${new[@]}"} --out "$out" --index "$out" \
  --recordings-root "$recordings"
