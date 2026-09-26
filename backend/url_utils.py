"""
Kavach AI - URL structural analysis.

Purely structural / heuristic checks - no external network calls, so this
works fully offline and cannot leak the URL being checked to anyone.
"""

import re
from urllib.parse import urlparse

from risk_engine import URL_SHORTENERS, KNOWN_ORG_DOMAINS

_IP_HOST_RE = re.compile(r"^(\d{1,3}\.){3}\d{1,3}$")


def _normalize(url: str) -> str:
    url = url.strip()
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://", url):
        url = "http://" + url
    return url


def inspect_url(raw_url: str) -> dict:
    url = _normalize(raw_url)
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()

    is_https = parsed.scheme == "https"
    is_ip_host = bool(_IP_HOST_RE.match(host))
    is_shortener = host in URL_SHORTENERS

    # crude subdomain count (labels before the registrable-ish last two parts)
    labels = host.split(".") if host else []
    subdomain_count = max(0, len(labels) - 2)

    # Does the raw text (host + path) mention a known org's keyword, while
    # the *host* itself isn't one of that org's official domains?
    haystack = f"{host} {parsed.path}".lower()
    mismatched_org = None
    for org_keyword, official_domains in KNOWN_ORG_DOMAINS.items():
        if org_keyword in haystack:
            if not any(host == d or host.endswith("." + d) for d in official_domains):
                mismatched_org = org_keyword
                break

    return {
        "normalized_url": url,
        "domain": host,
        "is_https": is_https,
        "is_ip_host": is_ip_host,
        "is_shortener": is_shortener,
        "subdomain_count": subdomain_count,
        "mentions_org_but_mismatched": mismatched_org,
    }


def find_first_url(text: str):
    match = re.search(r"(https?://[^\s]+|www\.[^\s]+)", text or "", re.IGNORECASE)
    return match.group(0) if match else None
