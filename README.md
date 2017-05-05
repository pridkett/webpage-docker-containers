Patrick Wagstrom's Webpage Docker Setup
=======================================

This is the collection of docker containers that I use to serve my personal web
page. There's really not that much that is super fancy about the setup.

Mounted Volumes
---------------

Right now this setup requires three different mounted volumes:

* `~/public_html`: the static HTML content to be served
* `~/ssl`: the SSL certificates required to enable encryption. This must the following files:
    * `~/ssl/certs/chain.pem`
    * `~/ssl/certs/fullchain.pem`
    * `~/ssl/private/cert.pem`
    * `~/ssl/private/dhparams.pem`
    * `~/ssl/private/privkey.pem`

Hostnames
---------

The hostnames for the system can be set through environment variables. In particular the hosts of interest are:

* `DEFAULT_SERVER_NAME`: I've always operated my machine with a default hostname even if nothing is there. This is the catch all for anything else that is routed to the machine that isn't captured by one of the other hostnames.
* `PRIMARY_SERVER_NAME`: The server name of the main web page server. Normally this is `patrick.wagstrom.net`.
* `SECURE_SERVER_NAME`: The server name of the webdav server. Normally this is `secure.wagstrom.net`. The whole naming issue dates back to times of yore when I didn't force every connection over to TLS.

For local development, it's probably best to set these in a `.env` file in the directory with the rest of the code. This file is already in `.gitignore` and will be read for local `docker-compose` operations.

Future Changes
--------------

* Integration with ElasticSearch to ship logs to a remote host
* Use Caddy's automatic TLS certificate features

License
-------

Licensed under the MIT License.
