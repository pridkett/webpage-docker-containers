#!/usr/bin/env bash

function replaceVars {
  INPUT_FILE=$1
  OUTPUT_FILE=$2

  sed \
    -e "s#\${DEFAULT_SERVER_NAME}#${DEFAULT_SERVER_NAME}#" \
    -e "s#\${PRIMARY_SERVER_NAME}#${PRIMARY_SERVER_NAME}#" \
    $INPUT_FILE > $OUTPUT_FILE
}

DEFAULT_SERVER_NAME=${DEFAULT_SERVER_NAME:-wagstrom.net}
PRIMARY_SERVER_NAME=${PRIMARY_SERVER_NAME:-patrick.wagstrom.net}

TEMPLATE_DIR=/etc/nginx/conf.d
for x in $(ls ${TEMPLATE_DIR}/*.template); do
    replaceVars ${x} ${TEMPLATE_DIR}/$(basename $x .template)
done

if [ -z "$1" ]; then
    set -- "nginx" "$@"
fi

exec $@
