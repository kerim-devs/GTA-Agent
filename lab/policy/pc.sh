#!/bin/zsh
# Runs a PowerShell script on the gaming PC, in Kerim's account gta and nowhere else (card P63).
# The script goes over as an encoded command, because the PC's shell is a German Windows PowerShell.
#
#   lab/policy/pc.sh <file.ps1>
enc=$( (print -r -- '[Console]::OutputEncoding=[Text.Encoding]::UTF8; $ProgressPreference="SilentlyContinue"'; cat "$1") | iconv -f UTF-8 -t UTF-16LE | base64 | tr -d '\n')
exec ssh -i ~/.ssh/gta_pc_ed25519 -o IdentitiesOnly=yes -o HostKeyAlias=192.168.178.23 -o ConnectTimeout=8 \
  -o BatchMode=yes -o ServerAliveInterval=30 -l gta 192.168.0.248 "powershell -NoProfile -EncodedCommand $enc"
