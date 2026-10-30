"""Bounded public HTTPS reads. Resolve once and connect to that validated IP, including on redirects."""

import http.client
import ipaddress
import json
import re
import socket
import ssl
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit, urlunsplit

import certifi

_DNS_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="website-dns")


class WebUnavailable(ValueError):
    pass


@dataclass(frozen=True)
class WebPage:
    url: str
    text: str
    content_type: str


def tls_context():
    context = ssl.create_default_context()
    context.load_verify_locations(cafile=certifi.where())
    return context


def public_url(value: str) -> str:
    try:
        parts = urlsplit(value)
        host = (parts.hostname or "").encode("idna").decode("ascii").lower().rstrip(".")
        if (parts.scheme != "https" or parts.username is not None or parts.password is not None
                or parts.port not in (None, 443) or len(host) > 253
                or not re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", host)
                or host.endswith((".localhost", ".local", ".internal", ".test", ".invalid", ".example"))):
            raise ValueError()
        return urlunsplit(("https", host, parts.path or "/", parts.query, ""))
    except (ValueError, UnicodeError):
        raise WebUnavailable("Only public HTTPS websites on the standard port can be checked.") from None


class _PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host: str, address: str, timeout: float):
        super().__init__(host, timeout=timeout, context=tls_context())
        self.address = address

    def connect(self):
        # SNI and certificate validation use the hostname; DNS is never resolved a second time.
        sock = socket.create_connection((self.address, 443), timeout=self.timeout)
        try:
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except Exception:
            sock.close()
            raise


def fetch_public(url: str, *, deadline: float | None = None, max_bytes: int = 500_000,
                 content_types: tuple[str, ...] = ("text/html", "application/xhtml+xml"),
                 allowed_hosts: set[str] | None = None, headers: dict | None = None,
                 json_body: dict | None = None) -> WebPage:
    deadline = deadline if deadline is not None else time.monotonic() + 8
    if json_body is not None and not allowed_hosts:
        raise WebUnavailable("Structured source queries require a fixed source allowlist.")
    try:
        for _ in range(4):
            url = public_url(url)
            parts = urlsplit(url)
            host = parts.hostname
            if allowed_hosts is not None and host not in allowed_hosts:
                raise WebUnavailable("The website redirected outside the permitted source.")
            if time.monotonic() >= deadline:
                raise WebUnavailable("The website check timed out.")
            lookup = _DNS_POOL.submit(socket.getaddrinfo, host, 443, type=socket.SOCK_STREAM)
            try:
                resolved = lookup.result(timeout=min(3, max(0, deadline - time.monotonic())))
            except FutureTimeout:
                lookup.cancel()
                raise WebUnavailable("The website's DNS lookup timed out.") from None
            addresses = list(dict.fromkeys(row[4][0] for row in resolved))
            if not addresses or any(not ipaddress.ip_address(address).is_global
                                    or ipaddress.ip_address(address).is_multicast
                                    or ipaddress.ip_address(address).is_reserved
                                    or getattr(ipaddress.ip_address(address), "ipv4_mapped", None)
                                    or ipaddress.ip_address(address) in ipaddress.ip_network("64:ff9b::/96")
                                    or ipaddress.ip_address(address) in ipaddress.ip_network("2002::/16")
                                    for address in addresses):
                raise WebUnavailable("The website does not resolve exclusively to public addresses.")
            timeout = min(5, deadline - time.monotonic())
            if timeout <= 0:
                raise WebUnavailable("The website check timed out.")
            connection = _PinnedHTTPS(host, addresses[0], timeout)
            try:
                connection.request("POST" if json_body is not None else "GET", (parts.path or "/") + ("?" + parts.query if parts.query else ""),
                                   body=json.dumps(json_body).encode() if json_body is not None else None,
                                   headers={"User-Agent": "OfferLetterChecker/0.1 (public identity checks)",
                                            "Accept": ", ".join(content_types), "Accept-Encoding": "identity",
                                            **({"Content-Type": "application/json"} if json_body is not None else {}), **(headers or {})})
                response = connection.getresponse()
                if response.status in {301, 302, 303, 307, 308}:
                    if json_body is not None:
                        raise WebUnavailable("Structured source queries cannot be redirected.")
                    location = response.getheader("Location")
                    if not location:
                        raise WebUnavailable("The website returned an incomplete redirect.")
                    url = urljoin(url, location)
                    continue
                if response.status != 200:
                    raise WebUnavailable(f"The website did not return a readable public page (HTTP {response.status}).")
                content_type = response.getheader("Content-Type", "").split(";", 1)[0].strip().lower()
                if content_type not in content_types or response.getheader("Content-Encoding", "identity") != "identity":
                    raise WebUnavailable("The source did not return a supported page format.")
                chunks, size = [], 0
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise WebUnavailable("The website check timed out.")
                    # HTTPResponse retains its socket after a server sends Connection: close.
                    if response.fp is not None:
                        response.fp.raw._sock.settimeout(min(5, remaining))
                    chunk = response.read1(min(16_384, max_bytes + 1 - size))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    size += len(chunk)
                    if size > max_bytes:
                        raise WebUnavailable("The public page exceeded the reading limit.")
                charset = response.headers.get_content_charset() or "utf-8"
                if getattr(response, "length", None) not in (None, 0):
                    raise WebUnavailable("The source response ended before the full page was received.")
                return WebPage(url, b"".join(chunks).decode(charset, errors="replace"), content_type)
            finally:
                connection.close()
        raise WebUnavailable("The website redirected too many times.")
    except (OSError, http.client.HTTPException, ValueError, LookupError) as error:
        if isinstance(error, WebUnavailable):
            raise
        raise WebUnavailable("The public website could not be read securely.") from error
