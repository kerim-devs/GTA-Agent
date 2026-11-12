#!/bin/zsh
# Makes room on the Mac when it runs short: moves the oldest finished recordings to the external
# disk and leaves a link in their place, so that every tool still finds them while the disk is
# attached. Kerim's recordings go only once they are classified, the pilot's sessions as they are.
# Does nothing while enough is free. Kerim's word of 12 November: when there is no room left, things go
# to the disk for the time being.
#
#   lab/offload-recordings.sh [GB that must be free, default 10] [folder on the disk] [dry]
need=${1:-10}
disk=${2:-"/Volumes/Festplatte 5TB/gta-agent/recordings"}
dry=${3:-}
root=/Users/kerim/recordings
free() { df -g $root | awk 'NR == 2 { print $4 }' }

if (( $(free) >= need )); then echo "$(free) GB free, nothing to do"; exit 0; fi
if [[ ! -d ${disk:h:h} ]]; then echo "the disk is not attached: ${disk:h:h}"; exit 1; fi
for kind in kerim pilot; do
  [[ -n $dry ]] || mkdir -p $disk/$kind
  for rec in $root/$kind/2026*(N/); do  # real folders only: a link is a recording that has gone already
    (( $(free) >= need )) && break 2
    name=$rec:t
    grep -qs '"seconds"' $rec/meta.json || continue  # still being written
    [[ $kind == kerim && ! -f $root/derived/kerim/$name/actions.jsonl ]] && continue  # not classified yet
    if [[ -n $dry ]]; then echo "would move $kind/$name ($(du -sm $rec | cut -f1) MB)"; continue; fi
    # rsync takes a file away here only after it has arrived whole over there; what is left is an
    # empty folder, and rmdir removes nothing else.
    if rsync -a --remove-source-files $rec/ $disk/$kind/$name/ && rmdir $rec; then
      ln -s $disk/$kind/$name $rec && echo "moved $kind/$name, $(free) GB free"
    else
      echo "$kind/$name did not go over completely, what is left stays here"
    fi
  done
done
echo "$(free) GB free"
