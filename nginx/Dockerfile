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

# RUN apt-get update && apt-get install -y build-essential wget unzip libpcre3 libpcre3-dev zlib1g-dev


# \ python \
      # python-pip \
      # python-dev \
      # nginx-extras \
      # libfreetype6 \
      # libfontconfig1 \
      # wget build-essential \
      # zlib1g-dev \
      # libpcre3 \
      # libpcre3-dev \
      # unzip -y && \

# RUN cd /usr/src && wget --progress=$WGET_PROGRESS --no-check-certificate https://github.com/pagespeed/ngx_pagespeed/archive/release-${NPS_VERSION}-beta.zip -O release-${NPS_VERSION}-beta.zip && \
     # unzip release-${NPS_VERSION}-beta.zip
# 
# RUN cd /usr/src/ngx_pagespeed-release-${NPS_VERSION}-beta/ && \
        # wget --no-check-certificate --progress=$WGET_PROGRESS https://dl.google.com/dl/page-speed/psol/${NPS_VERSION}.tar.gz && \
        # tar -xzvf ${NPS_VERSION}.tar.gz
# 
# RUN cd /usr/src && \
        # wget --progress=$WGET_PROGRESS http://nginx.org/download/nginx-${NGINX_VERSION}.tar.gz && \
	# tar -xvzf nginx-${NGINX_VERSION}.tar.gz && \
	# cd /usr/src/nginx-${NGINX_VERSION}/ && \
          # ./configure --add-module=/usr/src/ngx_pagespeed-release-${NPS_VERSION}-beta \
            # --prefix=/usr/local/share/nginx --conf-path=/etc/nginx/nginx.conf \
            # --sbin-path=/usr/local/sbin --error-log-path=/var/log/nginx/error.log && \
            # make && make install && \
      # cd /usr && \
      # rm -fr /usr/src/* && \
      # mkdir -p /var/pagespeed/cache

RUN apt-get update && apt-get -y build-dep nginx && apt-get -y install wget unzip

RUN mkdir -p /usr/src/custom-nginx && \
    cd /usr/src/custom-nginx && \
      apt-get source nginx && \
      cd $(find . -maxdepth 1 -type d | grep nginx) && \
        cd debian/modules && \
          wget --progress=$WGET_PROGRESS --no-check-certificate https://github.com/pagespeed/ngx_pagespeed/archive/release-${NPS_VERSION}-beta.zip -O release-${NPS_VERSION}-beta.zip && \
          unzip release-${NPS_VERSION}-beta.zip && \
          mv ngx_pagespeed-release-${NPS_VERSION}-beta ngx_pagespeed && \
          cd ngx_pagespeed && \
            wget --no-check-certificate --progress=$WGET_PROGRESS https://dl.google.com/dl/page-speed/psol/${NPS_VERSION}.tar.gz && \
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

# Add DH parameters (generated with openssl dhparam -out dhparams.pem 2048)
COPY ssl/dhparams.pem /etc/ssl/private/

# Add www certificates
COPY ssl/fullchain.pem /etc/ssl/certs/
COPY ssl/chain.pem /etc/ssl/certs/
COPY ssl/cert.pem /etc/ssl/private/
COPY ssl/privkey.pem /etc/ssl/private/

# Add virtual hosts
COPY vhosts/ /etc/nginx/conf.d/

# Add static content
COPY html/ /usr/share/nginx/html/

CMD ["nginx", "-g", "daemon off;"]
