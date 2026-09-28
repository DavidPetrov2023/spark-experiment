#!/bin/sh
# Build pro benchmark: sh build.sh
# Jen obal pro build.ps1. Claude Code na Windows neumi povolit primo volani
# powershell z nastroje Bash (vnoreny shell nejde overit), jednoduchy skript ano.
exec powershell -NoProfile -ExecutionPolicy Bypass -File "$(dirname "$0")/build.ps1"
