Patrick Wagstrom's Webpage Docker Setup
=======================================

This is the collection of docker containers that I use to
serve my personal web page. There's really not that much
that is super fancy about the setup. Most notably, this
makes use of
[caddy-gen](https://github.com/wemake-services/caddy-gen)
for automatic discovery of hosts and provisioning of SSL
certificates. This change, which was done in December 2019,
greatly simplifies the deployment of the stack.

Containers
----------

* `caddy-gen`: This is the brains of the operation that does the magic of putting all of the containers behind the Caddy front door, grabbing SSL certificates, and more. This is a pretty basic configuration right now with no magic bells and whistles.
* `personal-website`: A static content website based on nginx for my personal webpage.
* `webdav-server`: A caddy based webdav server that I mainly use for syncing my [Zotero](https://www.zotero.org/) library across machines.
* `vscode`: A browser based instance of Visual Studio Code. I often find myself traveling with only my work laptop and my personal iPad pro. This lets me have a full fledged development environment that I can work on when I don't have a physical machine with me.

Mounted Volumes
---------------

These containers require some persistence in order to function properly. In general, the directories should be made auotmatically, but in the off chance that they're not, here's a description:

### caddy-gen

In addition to needing access to the docker host instance of `/var/run/docker.sock`, it also benefits from a persistent path mounted to `/etc/caddy/acme` and `/etc/caddy/ocsp`. This will make startup of the container much faster in the even that something goes haywire.

### personal-website

This will serve all of the static content that is mounted to `/srv`.

### webdav-server

This will serve all of the content that is mounted to `/srv` over webdav. By default this will be read-write once you're logged in.

### vscode

Persistence for the Visual Studio code setup is done by mounting a directoy to `/home/coder/.local/share/code-server`. Access to the underlying filesystem is done by mounting to `/home/coder/projects`.

Hostnames
---------

Hostnames for each of the individual services are set through the `virtual.host` and `virual.alias` labels that are applied to each container. This is the standard for projects that use `caddy-gen`.

Future Changes
--------------

* Integration with ElasticSearch to ship logs to a remote host

License
-------

Licensed under the MIT License.
