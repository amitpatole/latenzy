#!/bin/sh
# Exports the exporter auth token from the compose secret so it never has to
# be spread through .env; keys/token still only live in env inside the process.
set -e
if [ -f /run/secrets/latenzy_token ]; then
    LATENZY_TOKEN="$(cat /run/secrets/latenzy_token)"
    export LATENZY_TOKEN
fi
exec "$@"
