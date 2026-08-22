#!/usr/bin/env python3
"""Check README links, local assets, external badges, and theme image references."""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
readme = README.read_text(encoding="utf-8")
errors: list[str] = []
checked: list[tuple[str, int]] = []

# Collect Markdown links and HTML href/src/srcset URLs without treating local paths as remote.
urls: set[str] = set(re.findall(r"\]\((https?://[^)\s]+|mailto:[^)\s]+)", readme))
urls.update(re.findall(r"(?:href|src|srcset)=\"(https?://[^\"\s]+|mailto:[^\"\s]+)", readme))

# Validate every README-relative asset locally, including the first URL in srcset values.
for raw in re.findall(r"(?:src|srcset)=\"(\./assets/[^\"]+)", readme):
    for ref in raw.split(","):
        ref = ref.strip().split(" ", 1)[0]
        path = ROOT / ref[2:]
        if not path.exists():
            errors.append(f"missing local asset: {ref}")


def check_url(url: str) -> int:
    request = Request(
        url,
        headers={
            "User-Agent": "Sohila-Khaled-Abbas-profile-readme-link-check/1.0",
            "Accept": "image/avif,image/webp,image/svg+xml,text/html,*/*;q=0.8",
        },
        method="GET",
    )
    last_error = ""
    for attempt in range(3):
        try:
            with urlopen(request, timeout=20) as response:
                return int(response.status)
        except HTTPError as exc:
            # 405 means the endpoint exists but disallows this method; GET already used,
            # so surface all other response codes as failures.
            last_error = f"HTTP {exc.code}"
            if exc.code in {429, 500, 502, 503, 504} and attempt < 2:
                time.sleep(2 ** attempt)
                continue
            return exc.code
        except (URLError, TimeoutError, OSError) as exc:
            last_error = str(exc.reason if isinstance(exc, URLError) else exc)
            if attempt < 2:
                time.sleep(2 ** attempt)
                continue
    return 0

for url in sorted(urls):
    parsed = urlparse(url)
    if parsed.scheme == "mailto":
        if not parsed.path or "@" not in parsed.path:
            errors.append(f"invalid mailto link: {url}")
        continue
    status = check_url(url)
    checked.append((url, status))
    host = parsed.netloc.lower()
    # LinkedIn commonly returns 999 to automated clients even when a profile URL is live.
    # Keep this visible in CI output, but do not classify it as a broken README link.
    if status == 999 and host.endswith("linkedin.com"):
        continue
    if status < 200 or status >= 400:
        errors.append(f"unavailable URL ({status or 'connection error'}): {url}")

# Specifically report badge endpoints so a broken badge is easy to identify in CI logs.
badges = [
    url for url in sorted(urls)
    if any(host in urlparse(url).netloc for host in ("img.shields.io", "komarev.com", "visitor-badge.laobi.icu"))
]
print(f"Checked {len(checked)} external URLs and {len(badges)} badge endpoints.")
for url, status in checked:
    marker = "BADGE" if url in badges else "LINK"
    if status == 999 and urlparse(url).netloc.lower().endswith("linkedin.com"):
        marker = "WARN"
    print(f"{marker}\t{status}\t{url}")

if errors:
    print("README link check failed:")
    print("\n".join(f"- {error}" for error in errors))
    sys.exit(1)

print("README link and badge check passed.")
