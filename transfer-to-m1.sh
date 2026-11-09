#!/bin/bash
set -euo pipefail

if [[ $# -ne 1 || ! ${1:-} =~ ^([[:alnum:]_.-]+@)?[[:alnum:]][[:alnum:]_.-]*$ ]]; then
  printf 'Aufruf: bash %s benutzer@IP-ODER-SSH-ALIAS\n' "$0" >&2
  exit 2
fi

source_dir="$(cd -- "$(dirname -- "$0")" && pwd -P)"
if [[ ! -s "$source_dir/remoteplay.tar.gz" ]]; then
  printf 'Das Paket remoteplay.tar.gz fehlt neben dem Skript.\n' >&2
  exit 1
fi

COPYFILE_DISABLE=1 tar -C "$source_dir" -cf - remoteplay.tar.gz M1-HANDOFF.md |
  ssh -T -o ConnectTimeout=10 -o StrictHostKeyChecking=ask -- "$1" '/bin/bash -c '"'"'
    set -euo pipefail
    if [[ "$(uname -s)" != Darwin || "$(uname -m)" != arm64 ]]; then
      printf "Als Ziel wird ein Apple-Silicon-Mac erwartet.\n" >&2
      exit 1
    fi

    umask 077
    destination="$(mktemp -d "$HOME/gta-agent.XXXXXXXX")"
    trap "rm -rf -- \"\$destination\"" EXIT
    tar -xf - -C "$destination"
    tar -xzf "$destination/remoteplay.tar.gz" -C "$destination"
    commit="$(git -C "$destination/remoteplay" rev-parse --short HEAD)"
    rm -- "$destination/remoteplay.tar.gz"
    trap - EXIT

    printf "M1-Projekt: %s\n" "$destination"
    printf "Übertragener Commit: %s\n" "$commit"
    printf "In Codex öffnen und mit M1-HANDOFF.md beginnen.\n"
  '"'"''
