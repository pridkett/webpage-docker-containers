FROM alpine:3.5
MAINTAINER Patrick Wagstrom <patrick@wagstrom.net>

ARG plugins=http.filemanager

RUN apk add --no-cache openssh-client git tar curl bash

RUN curl --silent --show-error --fail --location \
      --header "Accept: application/tar+gzip, application/x-gzip, application/octet-stream" -o - \
      "https://caddyserver.com/download/linux/amd64?plugins=${plugins}" \
    | tar --no-same-owner -C /usr/bin/ -xz caddy \
 && chmod 0755 /usr/bin/caddy \
 && /usr/bin/caddy -version

EXPOSE 80
VOLUME /root/.caddy
WORKDIR /srv

COPY Caddyfile /etc/Caddyfile.template

COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["/usr/bin/caddy", "--conf", "/etc/Caddyfile", "--log", "stdout"]