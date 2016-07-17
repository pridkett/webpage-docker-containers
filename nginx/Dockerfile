# Create proxy container for my web sites
#
# This will terminate SSL, do compression, support HTTP/2 etc
FROM ubuntu:xenial

MAINTAINER Patrick Wagstrom <patrick@wagstrom.net>

ENV DEBIAN_FRONTEND noninteractive
ENV NPS_VERSION 1.11.33.1
ENV WGET_PROGRESS dot:mega

RUN echo "America/New_York" > /etc/timezone
RUN locale-gen en_US.UTF-8 && dpkg-reconfigure locales

RUN apt-get update && apt-get -y build-dep nginx && apt-get -y install wget unzip

RUN mkdir -p /usr/src/custom-nginx && \
    cd /usr/src/custom-nginx && \
      apt-get source nginx && \
      cd $(find . -maxdepth 1 -type d | grep nginx) && \
        cd debian/modules && \
          wget --progress=${WGET_PROGRESS} --no-check-certificate https://github.com/pagespeed/ngx_pagespeed/archive/release-${NPS_VERSION}-beta.zip -O release-${NPS_VERSION}-beta.zip && \
          unzip release-${NPS_VERSION}-beta.zip && \
          mv ngx_pagespeed-release-${NPS_VERSION}-beta ngx_pagespeed && \
          cd ngx_pagespeed && \
            wget --no-check-certificate --progress=${WGET_PROGRESS} https://dl.google.com/dl/page-speed/psol/${NPS_VERSION}.tar.gz && \
            tar -xzvf ${NPS_VERSION}.tar.gz && \
          cd ..  && \
        cd ../.. && \
        cd debian && \
          sed -i '/extras_configure_flags/a --add-module=$(MODULESDIR)/ngx_pagespeed \\' rules && \
          sed -i '0,/nginx (\(.*\))/s//nginx (\1-pagespeed)/' changelog && \
        cd .. && \
        dpkg-buildpackage -b && \
      cd .. && \
      dpkg -i nginx-common_*.deb nginx-extras_*.deb

# Add main NGINX configuration
COPY nginx.conf /etc/nginx/

# Add virtual hosts
COPY vhosts/ /etc/nginx/conf.d/

# Add static content
COPY html/ /usr/share/nginx/html/

COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh
CMD ["/docker-entrypoint.sh"]
