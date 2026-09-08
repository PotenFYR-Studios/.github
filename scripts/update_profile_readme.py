#!/usr/bin/env python3
"""Auto-refresh the PotenFYR Studios org profile README with live public-repo data.

Regenerates the sections between <!-- POTENFYR:START:xxx --> and
<!-- POTENFYR:END:xxx --> markers in profile/README.md. Public repos only;
private repositories are never visible through this unauthenticated API view.
"""

import datetime
import json
import os
import re
import urllib.request

ORG = "PotenFYR-Studios"
README = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "profile", "README.md")

LANGUAGE_COLORS = {
    "Java": "b07219",
    "TypeScript": "3178c6",
    "JavaScript": "f1e05a",
    "Python": "3572a5",
    "Shell": "89e051",
    "HTML": "e34c26",
    "CSS": "663399",
    "Go": "00add8",
    "Rust": "dea584",
    "Kotlin": "a97bff",
    "Dart": "00b4ab",
    "PHP": "4f5d95",
    "C": "555555",
    "C++": "f34b7d",
    "C#": "178600",
    "Lua": "000080",
    "Groovy": "4298b8",
    "Dockerfile": "384d54",
    "HCL": "844fba",
    "Smarty": "f0c674",
    "Vue": "41b883",
    "MDX": "fcb32c",
    "Nix": "7ad3e7",
}
FALLBACK_COLOR = "6f42c1"


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


def build_stats(org, repos):
    stars = sum(r["stargazers_count"] for r in repos)
    forks = sum(r["forks_count"] for r in repos)
    issues = sum(r["open_issues_count"] for r in repos)
    members = len(paginate(f"/orgs/{ORG}/members"))
    created = org.get("created_at", "")[:4]

    def cell(shield, href):
        return f"[{shield}]({href})"

    return (
        "| Public Repos | Total Stars | Total Forks | Open Issues | Public Members |\n"
        "|:---:|:---:|:---:|:---:|:---:|\n"
        f"| {cell(shield('📦', len(repos), '2ea043'), f'https://github.com/orgs/{ORG}/repositories')} "
        f"| {cell(shield('⭐', stars, 'eac54f'), f'https://github.com/orgs/{ORG}/repositories?type=all&sort=stargazers')} "
        f"| {cell(shield('🍴', forks, '0078d7'), f'https://github.com/orgs/{ORG}/repositories?type=fork')} "
        f"| {cell(shield('🛠️', issues, 'db61a2'), f'https://github.com/orgs/{ORG}/repositories')} "
        f"| {cell(shield('👥', members, '8957e5'), f'https://github.com/orgs/{ORG}/people')} |\n\n"
        f"> 🏠 Based in {org.get('location') or 'planet Earth'} · On GitHub since {created} · Everything below is pulled straight from the GitHub API and refreshes itself."
    )


def build_repos(repos):
    rows = []
    for r in repos:
        desc = (r.get("description") or "—").replace("|", "/").replace("\n", " ").strip()
        if len(desc) > 110:
            desc = desc[:107] + "…"
        lang = r.get("language")
        if lang:
            color = LANGUAGE_COLORS.get(lang, FALLBACK_COLOR)
            lang_cell = f"![](https://img.shields.io/badge/{esc(lang)}-{color}?style=flat-square&labelColor=1c1e26)"
        else:
            lang_cell = "—"
        stars = f'[![Stars](https://img.shields.io/github/stars/{ORG}/{r["name"]}?style=flat-square&logo=github&labelColor=1c1e26&color=eac54f)]({r["html_url"]}/stargazers)'
        forks = f'[![Forks](https://img.shields.io/github/forks/{ORG}/{r["name"]}?style=flat-square&logo=github&labelColor=1c1e26&color=0078d7)]({r["html_url"]}/forks)'
        archived = " 📦`archived`" if r.get("archived") else ""
        rows.append(
            f'| 🗂️ [**{r["name"]}**]({r["html_url"]}){archived} | {desc} | {lang_cell} | {stars} | {forks} |'
        )
    return (
        "| Repository | About | Language | Stars | Forks |\n"
        "|:---|:---|:---:|:---:|:---:|\n" + "\n".join(rows)
    )


def build_cards(repos, limit=6):
    top = sorted(repos, key=lambda r: (r["stargazers_count"], r["forks_count"], r["name"]), reverse=True)[:limit]
    cells = [
        f'<a href="{r["html_url"]}"><img src="https://github-readme-stats.vercel.app/api/pin/?username={ORG}&repo={r["name"]}&theme=tokyonight&hide_border=true" alt="{r["name"]}"></a>'
        for r in top
    ]
    rows = []
    for i in range(0, len(cells), 2):
        row = cells[i : i + 2]
        rows.append("| " + " | ".join(row) + (" |  |" if len(row) == 1 else " |"))
    return "| 🌟 Featured | 🌟 Featured |\n|:---:|:---:|\n" + "\n".join(rows)


def build_languages(repos):
    totals = {}
    for r in repos:
        try:
            for lang, size in api(f'/repos/{ORG}/{r["name"]}/languages').items():
                totals[lang] = totals.get(lang, 0) + size
        except Exception:
            continue
    total_bytes = sum(totals.values())
    if not total_bytes:
        return "_No language data available._"
    parts = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    badges = []
    for lang, size in parts:
        pct = round(size / total_bytes * 100, 1)
        if pct < 0.1:
            continue
        color = LANGUAGE_COLORS.get(lang, FALLBACK_COLOR)
        badges.append(
            f'<img src="https://img.shields.io/badge/{esc(lang)}-{esc(f"{pct}%")}-{color}'
            f'?style=flat-square&labelColor=1c1e26" alt="{lang} {pct}%">'
        )
    bar = "\n".join(badges)
    return f"Language share across all public repos, by bytes of code:\n\n{bar}"


def build_meta():
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return (
        f"<sub>⚡ Last refreshed **{now}** · Data source: GitHub REST API (public repos only) · "
        f"Auto-updated every 3 hours by [GitHub Actions](https://github.com/{ORG}/.github/blob/main/.github/workflows/update-profile-readme.yml)</sub>"
    )


SECTIONS = {
    "stats": lambda: build_stats(api(f"/orgs/{ORG}"), load_repos()),
    "repos": lambda: build_repos(load_repos()),
    "cards": lambda: build_cards(load_repos()),
    "languages": lambda: build_languages(load_repos()),
    "meta": build_meta,
}

_repos_cache = None


def load_repos():
    global _repos_cache
    if _repos_cache is None:
        repos = paginate(f"/orgs/{ORG}/repos?sort=updated")
        repos = [r for r in repos if not r.get("fork") and r["name"] != ".github"]
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
