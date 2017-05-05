#!/usr/bin/env bash

function replaceVars {
  INPUT_FILE=$1
  OUTPUT_FILE=$2

  sed \
    -e "s#\${WEBDAV_USERNAME}#${WEBDAV_USERNAME}#" \
    -e "s#\${WEBDAV_PASSWORD}#${WEBDAV_PASSWORD}#" \
    $INPUT_FILE > $OUTPUT_FILE
}

WEBDAV_USERNAME=${WEBDAV_USERNAME:-admin}
WEBDAV_PASSWORD=${WEBDAV_PASSWORD:-password}

replaceVars /etc/Caddyfile.template /etc/Caddyfile

if [[ -z "$1" ]]; then
    set -- "/usr/bin/caddy" "--conf" "/etc/Caddyfile" "--log" "stdout" "$@"
fi

sh -c "$*"
