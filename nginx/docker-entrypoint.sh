#!/usr/bin/env bash

function replaceVars {
  INPUT_FILE=$1
  OUTPUT_FILE=$2

  sed \
    -e "s#\${DEFAULT_SERVER_NAME}#${DEFAULT_SERVER_NAME}#" \
    -e "s#\${PRIMARY_SERVER_NAME}#${PRIMARY_SERVER_NAME}#" \
    -e "s#\${SECURE_SERVER_NAME}#${SECURE_SERVER_NAME}#" \
    $INPUT_FILE > $OUTPUT_FILE
}

DEFAULT_SERVER_NAME=${DEFAULT_SERVER_NAME:-wagstrom.net}
PRIMARY_SERVER_NAME=${PRIMARY_SERVER_NAME:-patrick.wagstrom.net}
SECURE_SERVER_NAME=${SECURE_SERVER_NAME:-secure.wagstrom.net}

TEMPLATE_DIR=/etc/nginx/conf.d
for x in $(ls ${TEMPLATE_DIR}/*.template); do
    replaceVars ${x} ${TEMPLATE_DIR}/$(basename $x .template)
done


if [[ ! -d /var/log/nginx ]]; then
    mkdir /var/log/nginx
fi

if [[ ! -d /var/ngx_pagespeed_cache ]]; then
    mkdir /var/ngx_pagespeed_cache
fi

if [[ ! -d /var/log/pagespeed ]]; then
    mkdir /var/log/pagespeed
fi

if [[ -z "$1" ]]; then
    set -- "/usr/local/nginx/sbin/nginx" "-c" "/etc/nginx/nginx.conf" "$@"
fi

sh -c "$*"
