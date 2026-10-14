"""Fetch both live pages with distinct cache-busting query strings and require the SAME data fingerprint (and the expected one,
if given). Usage: python scripts/verify_live.py [expected_fingerprint]. Exit 1 on any mismatch. Needs network."""
import re
import sys
import time
import urllib.request

BASE = "https://jainamh029.github.io/broker-growth-os/"


def fingerprint(page: str, tag: str) -> str:
    url = f"{BASE}{page}?bust={tag}-{int(time.time())}"
    with urllib.request.urlopen(url, timeout=30) as r:
        html = r.read().decode()
    m = re.search(r'id="fingerprint">Data fingerprint ([0-9a-f]{10}) ', html)
    if not m:
        raise SystemExit(f"{page}: no fingerprint footer (stale or old page)")
    return m.group(1)


def main() -> None:
    a, b = fingerprint("index.html", "a"), fingerprint("memo.html", "b")
    print("index.html:", a, "memo.html:", b)
    if a != b:
        raise SystemExit("MISMATCH: the live pages come from different builds")
    if len(sys.argv) > 1 and sys.argv[1] != a:
        raise SystemExit(f"live fingerprint {a} != expected {sys.argv[1]}")
    print("OK: both live pages carry the same fingerprint")


if __name__ == "__main__":
    main()
