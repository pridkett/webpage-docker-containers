Patrick Wagstrom's Webpage Docker Setup
=======================================

This is the collection of docker containers that I use to serve my personal web
page. There's really not that much that is super fancy about the setup.

Mounted Volumes
---------------

Right now this setup requires two different mounted volumes:

* `~/public_html`: the static HTML content to be served
* `~/ssl`: the SSL certificates required to enable encryption. This must the following files:
    * `~/ssl/certs/chain.pem`
    * `~/ssl/certs/fullchain.pem`
    * `~/ssl/private/cert.pem`
    * `~/ssl/private/dhparams.pem`
    * `~/ssl/private/privkey.pem`

Future Changes
--------------

* Integration with ElasticSearch to ship logs to a remote host
* Use Caddy's automatic TLS certificate features

License
-------

Licensed under the MIT License.
