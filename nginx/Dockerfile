# Create proxy container for my web sites
#
# This will terminate SSL, do compression, support HTTP/2 etc
FROM ubuntu:xenial

MAINTAINER Patrick Wagstrom <patrick@wagstrom.net>

ENV DEBIAN_FRONTEND noninteractive
ENV NPS_VERSION 1.11.33.4
ENV NGINX_VERSION 1.13.0
ENV WGET_PROGRESS dot:mega

RUN apt-get update
RUN apt-get -y install curl sudo build-essential zlib1g-dev libpcre3 libpcre3-dev unzip wget locales libssl-dev

RUN echo "America/New_York" > /etc/timezone
RUN locale-gen en_US.UTF-8 && dpkg-reconfigure locales

RUN curl -f -L -sS https://ngxpagespeed.com/install -o build_ngx_pagespeed.sh
RUN bash ./build_ngx_pagespeed.sh -y -v $NPS_VERSION --nginx-version $NGINX_VERSION -a '--with-http_ssl_module --with-http_v2_module' && \
    mkdir /etc/nginx && \
    cp /root/nginx-*/conf/mime.types /etc/nginx/ && \
    rm -rf /root/nginx-$NGINX_VERSION /root/ngx_pagespeed-latest-stable

# Add main NGINX configuration
COPY nginx.conf /etc/nginx/

# Add virtual hosts
COPY vhosts/ /etc/nginx/conf.d/

# Add static content
COPY html/ /usr/share/nginx/html/

COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

CMD ["/usr/local/nginx/sbin/nginx", "-c", "/etc/nginx/nginx.conf"]
ENTRYPOINT ["/docker-entrypoint.sh"]
