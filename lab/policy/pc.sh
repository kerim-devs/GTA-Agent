#!/bin/zsh
# Runs a PowerShell script on the gaming PC, in Kerim's account gta and nowhere else (card P63).
# The script goes over as an encoded command, because the PC's shell is a German Windows PowerShell.
# With -L the given port of this Mac's loopback is forwarded to the same port of the PC's loopback
# for as long as the script runs, which is how a server that listens only there is reached.
#
#   lab/policy/pc.sh [-L port] <file.ps1>
forward=()
if [[ $1 == -L ]]; then forward=(-L "$2:127.0.0.1:$2" -o ExitOnForwardFailure=yes); shift 2; fi
enc=$( (print -r -- '[Console]::OutputEncoding=[Text.Encoding]::UTF8; $ProgressPreference="SilentlyContinue"'; cat "$1") | iconv -f UTF-8 -t UTF-16LE | base64 | tr -d '\n')
exec ssh -i ~/.ssh/gta_pc_ed25519 -o IdentitiesOnly=yes -o HostKeyAlias=192.168.178.23 -o ConnectTimeout=8 \
  -o BatchMode=yes -o ServerAliveInterval=30 $forward -l gta 192.168.0.248 "powershell -NoProfile -OutputFormat Text -EncodedCommand $enc"
