"""Route DNS through reliable public resolvers (Cloudflare / Google).

Some networks/routers intermittently return SERVFAIL or fail to resolve
MongoDB Atlas (and other) hostnames. Importing this module — before any network
connection is opened — makes the whole process resolve names through 8.8.8.8 /
1.1.1.1 instead of the local resolver, by patching both:

  1. dnspython's default resolver — used for the SRV/TXT records pymongo needs
     for a mongodb+srv:// URI.
  2. socket.getaddrinfo — used for the A-record lookup behind every actual
     socket connection (the Mongo shards, the Discord gateway, etc.).

For (2), we resolve the hostname to an IP via public DNS and connect to that IP.
TLS still verifies against the original hostname (SNI is set independently of
getaddrinfo), so this is safe.
"""

import socket

PUBLIC_DNS = ["1.1.1.1", "8.8.8.8"]

try:
    import dns.resolver

    _resolver = dns.resolver.Resolver(configure=False)
    _resolver.nameservers = PUBLIC_DNS

    # (1) pymongo's SRV/TXT lookups go through dnspython.
    dns.resolver.default_resolver = _resolver

    # (2) Wrap socket.getaddrinfo so the actual connections resolve via public DNS.
    _orig_getaddrinfo = socket.getaddrinfo

    def _getaddrinfo(host, *args, **kwargs):
        if isinstance(host, str):
            try:
                ip = _resolver.resolve(host, "A")[0].to_text()
                return _orig_getaddrinfo(ip, *args, **kwargs)
            except Exception:
                pass  # already an IP, IPv6-only, unresolvable — fall through
        return _orig_getaddrinfo(host, *args, **kwargs)

    socket.getaddrinfo = _getaddrinfo
except Exception:
    pass  # dnspython unavailable — fall back to the system resolver
