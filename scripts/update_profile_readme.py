#!/usr/bin/env python3
"""Auto-refresh the PotenFYR Studios org profile README with live public-repo data.

Regenerates the sections between <!-- POTENFYR:START:xxx --> and
<!-- POTENFYR:END:xxx --> markers in profile/README.md. Public repos only;
private repositories are never visible through this unauthenticated API view.

Visual components are served by ReadmeFX (https://readmefx.potenfyr.in):
  - stats   -> /org organization card (live stars, repos, top repo)
  - repos   -> /repo repository cards for every public repo
  - cards   -> /repo cards for the top starred repos
  - languages -> /languages top-languages card
Static sections outside the markers (banners, badges, typing animation) are
owned by the README itself and are not touched here.
"""

import json
import os
import re
import time
import urllib.parse
import urllib.request

ORG = "PotenFYR-Studios"
README = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "profile", "README.md")
READMEFX = "https://readmefx.potenfyr.in/api"
THEME = "tokyo-night"
# Hourly cache-buster: GitHub Camo caches SVGs aggressively, and ReadmeFX
# renders must refresh after every scheduled run to show fresh numbers.
CACHE_BUSTER = int(time.time()) // 3600


def api(path):
    req = urllib.request.Request(
        f"https://api.github.com{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {os.environ.get('GITHUB_TOKEN')}" if os.environ.get("GITHUB_TOKEN") else "",
            "User-Agent": "potenfyr-readme-bot",
        },
    )
    with urllib.request.urlopen(req) as res:
        return json.load(res)


def paginate(path):
    page = 1
    items = []
    while True:
        batch = api(f"{path}{'&' if '?' in path else '?'}per_page=100&page={page}")
        items.extend(batch)
        if len(batch) < 100:
            return items
        page += 1


def esc(text):
    """Escape text for a shields.io static badge path segment."""
    return (
        str(text)
        .replace("%", "%25")
        .replace("+", "%2B")
        .replace("#", "%23")
        .replace("-", "--")
        .replace("_", "__")
        .replace(" ", "%20")
    )


def shield(label, value, color):
    return (
        f'<img src="https://img.shields.io/badge/{esc(label)}-{esc(value)}-{color}'
        f'?style=flat-square&labelColor=1c1e26" alt="{label} {value}">'
    )


def fx(path, **params):
    """Build a ReadmeFX image URL with a cache-buster appended."""
    query = "&".join(f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in params.items())
    return f"{READMEFX}{path}?{query}&t={CACHE_BUSTER}"


def build_stats(org, repos):
    """Live org overview card from ReadmeFX (/org) plus per-metric badges."""
    stars = sum(r["stargazers_count"] for r in repos)
    forks = sum(r["forks_count"] for r in repos)
    issues = sum(r["open_issues_count"] for r in repos)
    members = len(paginate(f"/orgs/{ORG}/members"))
    url = fx("/org", username=ORG, theme=THEME)
    return (
        '<div align="center">\n\n'
        f'[![PotenFYR Studios organization stats]({url})](https://github.com/{ORG})\n\n'
        f'{shield("📦", len(repos), "2ea043")} '
        f'{shield("⭐", stars, "eac54f")} '
        f'{shield("🍴", forks, "0078d7")} '
        f'{shield("🛠️", issues, "db61a2")} '
        f'{shield("👥", members, "8957e5")}\n\n'
        '</div>\n'
    )


def repo_card(r):
    url = fx("/repo", repo=f"{ORG}/{r['name']}", showDescription="true", theme=THEME)
    return f'[![{r["name"]}]({url})]({r["html_url"]})'


def build_repos(repos):
    """One ReadmeFX /repo card per public repository, centered grid."""
    cells = [repo_card(r) for r in repos]
    return '<div align="center">\n\n' + "\n".join(cells) + "\n\n</div>\n"


def build_cards(repos, limit=8):
    """Featured cards: ReadmeFX /repo embeds for the top starred repos."""
    featured = sorted(
        repos, key=lambda r: (r["stargazers_count"], r["forks_count"], r["name"]), reverse=True
    )
    if limit:
        featured = featured[:limit]
    cells = [repo_card(r) for r in featured]
    return '<div align="center">\n\n' + "\n".join(cells) + "\n\n</div>\n"


def build_languages(repos):
    """ReadmeFX /languages card for the organization."""
    url = fx("/languages", username=ORG, langsCount=8, theme=THEME)
    return (
        '<div align="center">\n'
        f'  <img src="{url}" alt="Language Distribution" width="460">\n'
        '</div>\n'
    )


def build_history(repos):
    starred = [r for r in repos if r["stargazers_count"] > 0]
    ordered = sorted(
        starred, key=lambda r: (r["stargazers_count"], r["name"]), reverse=True
    )
    names = ",".join(f"{ORG.lower()}/{r['name'].lower()}" for r in ordered)
    url = f"https://api.star-history.com/svg?repos={names}&type=Date&theme=dark"
    return (
        f'<img src="{url}" alt="Star history graph for all {ORG} public repositories">'
    )


def build_meta(repos):
    stamp = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    return (
        f'<sub>⚡ Last refreshed **{stamp}** · Data source: GitHub REST API (public repos only) · '
        f'Charts by [ReadmeFX](https://readmefx.potenfyr.in) · '
        f'Auto-synced continuously by [GitHub Actions]'
        f'(https://github.com/PotenFYR-Studios/.github/blob/main/.github/workflows/update-profile-readme.yml)</sub>'
    )


SECTIONS = {
    "stats": lambda: build_stats(api(f"/orgs/{ORG}"), load_repos()),
    "repos": lambda: build_repos(load_repos()),
    "cards": lambda: build_cards(load_repos()),
    "languages": lambda: build_languages(load_repos()),
    "history": lambda: build_history(load_repos()),
    "meta": lambda: build_meta(load_repos()),
}

_repos_cache = None


def load_repos():
    global _repos_cache
    if _repos_cache is None:
        repos = paginate(f"/orgs/{ORG}/repos?sort=updated")
        repos = [
            r
            for r in repos
            if not r.get("fork") and not r.get("private") and r["name"] != ".github"
        ]
        repos.sort(key=lambda r: (r["stargazers_count"], r["pushed_at"]), reverse=True)
        _repos_cache = repos
    return _repos_cache


def refresh(path):
    with open(path, encoding="utf-8") as f:
        content = f.read()
    for name, builder in SECTIONS.items():
        pattern = re.compile(
            rf"(<!-- POTENFYR:START:{name} -->\n?).*?(\n?<!-- POTENFYR:END:{name} -->)",
            re.DOTALL,
        )
        if not pattern.search(content):
            raise SystemExit(f"Marker POTENFYR:{name} missing from README")
        content = pattern.sub(lambda m: m.group(1) + builder() + "\n" + m.group(2), content)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("README refreshed.")


if __name__ == "__main__":
    refresh(os.path.normpath(README))
