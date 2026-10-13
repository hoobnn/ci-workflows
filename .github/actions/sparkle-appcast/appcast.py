"""Build a Sparkle appcast from GitHub Releases.

Each release item comes from the `<basename>-<version>-macOS<suffix>.zip.sparkle.json`
asset that macos-release.yml writes when `sparkle: true`: the EdDSA signature,
the zip's length and the bundle versions. Nothing else is trusted for those.
"""

from __future__ import annotations

import email.utils
import html
import json
import os
import re
import sys
import urllib.request
from datetime import datetime
from xml.sax.saxutils import escape, quoteattr

API = "https://api.github.com"


def api_get(url: str, token: str, accept: str = "application/vnd.github+json") -> bytes:
    req = urllib.request.Request(url, headers={
        "Accept": accept,
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def list_releases(repo: str, token: str) -> list[dict]:
    out, page = [], 1
    while True:
        batch = json.loads(api_get(f"{API}/repos/{repo}/releases?per_page=100&page={page}", token))
        out += batch
        if len(batch) < 100:
            return out
        page += 1


def release_notes_html(body: str) -> str:
    # Sparkle renders the description as HTML; keep the markdown readable as-is.
    text = html.escape(body.strip() or "")
    return f'<pre style="white-space: pre-wrap; font: 13px -apple-system, sans-serif">{text}</pre>'


def build(releases: list[dict], fetch_asset, *, basename: str, title: str, link: str,
          max_items: int, include_prereleases: bool, suffix: str = "") -> str:
    pattern = re.compile(rf"^{re.escape(basename)}-.+-macOS{re.escape(suffix)}\.zip\.sparkle\.json$")
    items = []
    for rel in releases:
        if rel.get("draft") or (rel.get("prerelease") and not include_prereleases):
            continue
        assets = {a["name"]: a for a in rel.get("assets", [])}
        meta_asset = next((a for n, a in assets.items() if pattern.match(n)), None)
        if meta_asset is None:
            continue
        meta = json.loads(fetch_asset(meta_asset))
        zip_asset = assets.get(meta["file"])
        if zip_asset is None:
            print(f"::warning::{rel['tag_name']}: {meta['file']} missing, skipped", file=sys.stderr)
            continue
        if zip_asset["size"] != meta["length"]:
            print(f"::warning::{rel['tag_name']}: zip size differs from its signed length, skipped",
                  file=sys.stderr)
            continue
        published = datetime.fromisoformat(rel["published_at"].replace("Z", "+00:00"))
        lines = [
            "    <item>",
            f"      <title>{escape(rel.get('name') or rel['tag_name'])}</title>",
            f"      <pubDate>{email.utils.format_datetime(published)}</pubDate>",
            f"      <sparkle:version>{escape(meta['version'])}</sparkle:version>",
            f"      <sparkle:shortVersionString>{escape(meta['shortVersion'])}</sparkle:shortVersionString>",
        ]
        if meta.get("minimumSystemVersion"):
            lines.append(f"      <sparkle:minimumSystemVersion>{escape(meta['minimumSystemVersion'])}"
                         "</sparkle:minimumSystemVersion>")
        lines += [
            f"      <sparkle:fullReleaseNotesLink>{escape(rel['html_url'])}</sparkle:fullReleaseNotesLink>",
            f"      <description><![CDATA[{release_notes_html(rel.get('body') or '')}]]></description>",
            f"      <enclosure url={quoteattr(zip_asset['browser_download_url'])}"
            f" length=\"{meta['length']}\" type=\"application/octet-stream\""
            f" sparkle:edSignature={quoteattr(meta['edSignature'])} />",
            "    </item>",
        ]
        items.append((published, "\n".join(lines)))
        if len(items) >= max_items:
            break

    items.sort(key=lambda x: x[0], reverse=True)
    return "\n".join([
        '<?xml version="1.0" encoding="utf-8"?>',
        '<rss version="2.0" xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle">',
        "  <channel>",
        f"    <title>{escape(title)}</title>",
        f"    <link>{escape(link)}</link>",
        *(body for _, body in items),
        "  </channel>",
        "</rss>",
        "",
    ])


def main() -> None:
    repo, token = os.environ["REPOSITORY"], os.environ["GH_TOKEN"]
    xml = build(
        list_releases(repo, token),
        lambda asset: api_get(asset["url"], token, "application/octet-stream"),
        basename=os.environ["BASENAME"],
        suffix=os.environ.get("ARTIFACT_SUFFIX", ""),
        title=os.environ["TITLE"],
        link=f"https://github.com/{repo}",
        max_items=int(os.environ.get("MAX_ITEMS") or 10),
        include_prereleases=os.environ.get("INCLUDE_PRERELEASES") == "true",
    )
    out = os.environ["OUTPUT"]
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(xml)
    print(f"Wrote {out} with {xml.count('<item>')} item(s)")


if __name__ == "__main__":
    main()
