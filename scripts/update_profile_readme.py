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
import textwrap
import urllib.request
import xml.sax.saxutils as saxutils

ORG = "PotenFYR-Studios"
README = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "profile", "README.md")
CARDS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "profile", "cards")

LANGUAGE_COLORS = {
    "PowerShell": "012456",
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
        f"| {cell(shield('🛠️', issues, 'db61a2'), f'https://github.com/search?q=org%3A{ORG}+is%3Aopen')} "
        f"| {cell(shield('👥', members, '8957e5'), f'https://github.com/orgs/{ORG}/people')} |\n\n"
        f"> 🏠 Based in {org.get('location') or 'planet Earth'} · On GitHub since {created} · Everything below is pulled straight from the GitHub API and refreshes itself."
    )


def build_repos(repos):
    rows = []
    for r in repos:
        desc = (r.get("description") or "No description yet.").replace("|", "/").replace("\n", " ").strip()
        if len(desc) > 110:
            desc = desc[:107] + "…"
        topics = r.get("topics") or []
        if topics:
            tags = " ".join(
                f"![](https://img.shields.io/badge/%23{esc(t)}-24292f?style=flat-square&labelColor=1c1e26)"
                for t in topics[:4]
            )
            desc += f"<br>{tags}"
        lang = r.get("language")
        if lang:
            color = LANGUAGE_COLORS.get(lang, FALLBACK_COLOR)
            lang_cell = f"![](https://img.shields.io/badge/{esc(lang)}-{color}?style=flat-square&labelColor=1c1e26)"
        else:
            lang_cell = "n/a"
        stars_href = f"{r['html_url']}/stargazers" if r["stargazers_count"] > 0 else r["html_url"]
        forks_href = f"{r['html_url']}/forks" if r["forks_count"] > 0 else r["html_url"]
        stars = f'[![Stars](https://img.shields.io/github/stars/{ORG}/{r["name"]}?style=flat-square&logo=github&labelColor=1c1e26&color=eac54f)]({stars_href})'
        forks = f'[![Forks](https://img.shields.io/github/forks/{ORG}/{r["name"]}?style=flat-square&logo=github&labelColor=1c1e26&color=0078d7)]({forks_href})'
        activity = f'![](https://img.shields.io/github/last-commit/{ORG}/{r["name"]}?style=flat-square&logo=git&labelColor=1c1e26&color=2ea043)'
        archived = " 📦`archived`" if r.get("archived") else ""
        rows.append(
            f'| 🗂️ [**{r["name"]}**]({r["html_url"]}){archived} | {desc} | {lang_cell} | {stars} | {forks} | {activity} |'
        )
    return (
        "| Repository | About | Language | Stars | Forks | Last Commit |\n"
        "|:---|:---|:---:|:---:|:---:|:---:|\n" + "\n".join(rows)
    )


def generate_card_svg(repo):
    name = repo["name"]
    clean_id = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    escaped_name = saxutils.escape(name)
    raw_desc = (repo.get("description") or "No description provided.").replace("\r", " ").replace("\n", " ").strip()

    wrapped = textwrap.wrap(raw_desc, width=46)
    if not wrapped:
        desc_lines = ["No description provided."]
    elif len(wrapped) == 1:
        desc_lines = [wrapped[0]]
    else:
        line1 = wrapped[0]
        line2 = wrapped[1]
        if len(wrapped) > 2:
            line2 = line2[:40] + "..." if len(line2) > 40 else line2 + "..."
        desc_lines = [line1, line2]

    desc_escaped = [saxutils.escape(line) for line in desc_lines]

    lang = repo.get("language")
    lang_color = f"#{LANGUAGE_COLORS.get(lang, FALLBACK_COLOR)}" if lang else None
    stars = repo.get("stargazers_count", 0)
    forks = repo.get("forks_count", 0)

    def fmt_num(num):
        if num >= 1000:
            return f"{num / 1000:.1f}k"
        return str(num)

    star_str = fmt_num(stars)
    fork_str = fmt_num(forks)

    footer_elements = []
    cur_x = 25

    if lang:
        escaped_lang = saxutils.escape(lang)
        footer_elements.append(
            f'<circle cx="{cur_x + 4}" cy="107" r="5" fill="{lang_color}" />\n'
            f'    <text class="meta-text" x="{cur_x + 15}" y="111">{escaped_lang}</text>'
        )
        cur_x += int(15 + len(lang) * 7.5 + 20)

    footer_elements.append(
        f'<g transform="translate({cur_x}, 99)">\n'
        f'      <path fill="#eac54f" d="M8 .25a.75.75 0 0 1 .673.418l1.882 3.815 4.21.612a.75.75 0 0 1 .416 1.279l-3.046 2.97.719 4.192a.751.751 0 0 1-1.088.791L8 12.347l-3.766 1.98a.75.75 0 0 1-1.088-.79l.72-4.194L.818 6.374a.75.75 0 0 1 .416-1.28l4.21-.611L7.327.668A.75.75 0 0 1 8 .25Z" />\n'
        f'      <text class="meta-text" x="18" y="12">{star_str}</text>\n'
        f'    </g>'
    )
    cur_x += int(18 + len(star_str) * 7.5 + 20)

    footer_elements.append(
        f'<g transform="translate({cur_x}, 99)">\n'
        f'      <path fill="#0078d7" d="M5 3.25a.75.75 0 1 1-1.5 0 .75.75 0 0 1 1.5 0Zm0 2.122a2.25 2.25 0 1 0-1.5 0v.878A2.25 2.25 0 0 0 5.75 8.5h1.5v2.128a2.251 2.251 0 1 0 1.5 0V8.5h1.5a2.25 2.25 0 0 0 2.25-2.25v-.878a2.25 2.25 0 1 0-1.5 0v.878a.75.75 0 0 1-.75.75h-4.5A.75.75 0 0 1 5 6.25v-.878Zm3.75 7.378a.75.75 0 1 1-1.5 0 .75.75 0 0 1 1.5 0Zm3-8.75a.75.75 0 1 1-1.5 0 .75.75 0 0 1 1.5 0Z" />\n'
        f'      <text class="meta-text" x="18" y="12">{fork_str}</text>\n'
        f'    </g>'
    )

    footer_svg = "\n    ".join(footer_elements)

    if len(desc_escaped) == 1:
        desc_svg = f'<text class="card-desc" x="25" y="67">{desc_escaped[0]}</text>'
    else:
        desc_svg = (
            f'<text class="card-desc" x="25" y="60">{desc_escaped[0]}</text>\n'
            f'    <text class="card-desc" x="25" y="78">{desc_escaped[1]}</text>'
        )

    title_size = "15px" if len(name) > 24 else "16px"

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="400" height="130" viewBox="0 0 400 130" fill="none">
  <defs>
    <linearGradient id="grad-{clean_id}" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#8b5cf6" />
      <stop offset="50%" stop-color="#ec4899" />
      <stop offset="100%" stop-color="#f97316" />
    </linearGradient>
    <clipPath id="card-clip-{clean_id}">
      <rect x="0" y="0" width="400" height="130" rx="10" />
    </clipPath>
    <style>
      .card-bg {{ fill: #1a1b26; stroke: #2f334d; stroke-width: 1px; }}
      .card-title {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: {title_size}; font-weight: 600; fill: #7aa2f7; }}
      .card-desc {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 12.5px; fill: #a9b1d6; }}
      .meta-text {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 12px; fill: #787c99; font-weight: 500; }}
      @media (prefers-color-scheme: light) {{
        .card-bg {{ fill: #f7f8fc; stroke: #e1e4ea; }}
        .card-title {{ fill: #2563eb; }}
        .card-desc {{ fill: #4b5563; }}
        .meta-text {{ fill: #6b7280; }}
      }}
    </style>
  </defs>

  <!-- Card Background with Gradient Accent -->
  <g clip-path="url(#card-clip-{clean_id})">
    <rect class="card-bg" x="0.5" y="0.5" width="399" height="129" rx="10" />
    <rect x="0" y="0" width="400" height="4" fill="url(#grad-{clean_id})" />
  </g>

  <!-- Repo Icon -->
  <g transform="translate(25, 22)">
    <path fill="#7aa2f7" d="M2 2.5A2.5 2.5 0 0 1 4.5 0h8.75a.75.75 0 0 1 .75.75v12.5a.75.75 0 0 1-.75.75h-2.5a.75.75 0 0 1 0-1.5h1.75v-2h-8a1 1 0 0 0-.714 1.7.75.75 0 1 1-1.072 1.05A2.495 2.495 0 0 1 2 11.5Zm10.5-1h-8a1 1 0 0 0-1 1v6.708A2.486 2.486 0 0 1 4.5 9h8ZM5 12.25a.25.25 0 0 1 .25-.25H12v1.5H5.25a.25.25 0 0 1-.25-.25Z"/>
  </g>

  <!-- Repo Title -->
  <text class="card-title" x="48" y="36">{escaped_name}</text>

  <!-- Repo Description -->
  {desc_svg}

  <!-- Footer Meta (Lang, Stars, Forks) -->
  {footer_svg}
</svg>
"""
    return svg


def fmt_bytes(b):
    if b >= 1024 * 1024:
        return f"{b / (1024 * 1024):.1f} MB"
    if b >= 1024:
        return f"{b / 1024:.1f} KB"
    return f"{b} B"


def build_cards(repos, limit=None):
    os.makedirs(CARDS_DIR, exist_ok=True)
    card_repos = sorted(repos, key=lambda r: (r["stargazers_count"], r["forks_count"], r["name"]), reverse=True)
    if limit:
        card_repos = card_repos[:limit]

    generated_files = set()
    cells = []
    for r in card_repos:
        svg_content = generate_card_svg(r)
        filename = f"{r['name']}.svg"
        svg_file = os.path.join(CARDS_DIR, filename)
        with open(svg_file, "w", encoding="utf-8") as f:
            f.write(svg_content)
        generated_files.add(filename)
        card_url = f"https://raw.githubusercontent.com/{ORG}/.github/main/profile/cards/{r['name']}.svg"
        cells.append(f'<a href="{r["html_url"]}"><img src="{card_url}" alt="{r["name"]}"></a>')

    # Auto-cleanup stale repo SVGs in CARDS_DIR (protecting languages.svg)
    for existing in os.listdir(CARDS_DIR):
        if existing.endswith(".svg") and existing != "languages.svg":
            if existing not in generated_files:
                try:
                    os.remove(os.path.join(CARDS_DIR, existing))
                except OSError:
                    pass

    rows = []
    for i in range(0, len(cells), 2):
        row = cells[i : i + 2]
        if len(row) == 1:
            rows.append(f"| {row[0]} | |")
        else:
            rows.append(f"| {row[0]} | {row[1]} |")

    return "| 🌟 Repositories | 🌟 Repositories |\n|:---:|:---:|\n" + "\n".join(rows)


def generate_languages_svg(totals, total_bytes, num_repos):
    import math

    parts = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    clean_id = "lang_dist"

    bar_w = 750
    bar_x = 25
    bar_y = 52
    bar_h = 12

    segments = []
    cur_x = bar_x
    for lang, size in parts:
        pct = size / total_bytes
        w = max(3.0, pct * bar_w) if size > 0 else 0
        color = f"#{LANGUAGE_COLORS.get(lang, FALLBACK_COLOR)}"
        escaped_lang = saxutils.escape(lang)
        pct_label = f"{round(pct * 100, 1)}%"
        segments.append(
            f'<rect x="{cur_x:.2f}" y="{bar_y}" width="{w:.2f}" height="{bar_h}" fill="{color}">'
            f'<title>{escaped_lang}: {pct_label}</title></rect>'
        )
        cur_x += w

    cols = 3
    row_h = 24
    start_y = 86
    num_rows = math.ceil(len(parts) / cols)
    height = start_y + num_rows * row_h + 12

    legend_items = []
    for idx, (lang, size) in enumerate(parts):
        col = idx % cols
        row = idx // cols
        col_x = 25 + col * 255
        row_y = start_y + row * row_h
        color = f"#{LANGUAGE_COLORS.get(lang, FALLBACK_COLOR)}"
        pct_val = round(size / total_bytes * 100, 1)
        pct_str = f"{pct_val}%"
        size_str = fmt_bytes(size)
        escaped_lang = saxutils.escape(lang)
        legend_items.append(
            f'    <circle cx="{col_x + 5}" cy="{row_y - 4}" r="4.5" fill="{color}" />\n'
            f'    <text x="{col_x + 16}" y="{row_y}">\n'
            f'      <tspan class="lang-name">{escaped_lang}</tspan>\n'
            f'      <tspan class="lang-pct" dx="6">{pct_str}</tspan>\n'
            f'      <tspan class="lang-size" dx="6">({size_str})</tspan>\n'
            f'    </text>'
        )

    legend_svg = "\n".join(legend_items)
    segments_svg = "\n    ".join(segments)
    total_str = fmt_bytes(total_bytes)

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="800" height="{height}" viewBox="0 0 800 {height}" fill="none">
  <defs>
    <linearGradient id="grad-{clean_id}" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#8b5cf6" />
      <stop offset="50%" stop-color="#ec4899" />
      <stop offset="100%" stop-color="#f97316" />
    </linearGradient>
    <clipPath id="card-clip-{clean_id}">
      <rect x="0" y="0" width="800" height="{height}" rx="10" />
    </clipPath>
    <clipPath id="bar-clip">
      <rect x="25" y="{bar_y}" width="{bar_w}" height="{bar_h}" rx="6" />
    </clipPath>
    <style>
      .card-bg {{ fill: #1a1b26; stroke: #2f334d; stroke-width: 1px; }}
      .card-title {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 15px; font-weight: 600; fill: #7aa2f7; }}
      .card-sub {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 12px; fill: #787c99; font-weight: 500; }}
      .lang-name {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 12.5px; font-weight: 600; fill: #cdd6f4; }}
      .lang-pct {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 12px; font-weight: 600; fill: #7aa2f7; }}
      .lang-size {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 11px; fill: #6c7086; }}
      @media (prefers-color-scheme: light) {{
        .card-bg {{ fill: #f7f8fc; stroke: #e1e4ea; }}
        .card-title {{ fill: #2563eb; }}
        .card-sub {{ fill: #6b7280; }}
        .lang-name {{ fill: #1f2328; }}
        .lang-pct {{ fill: #2563eb; }}
        .lang-size {{ fill: #6b7280; }}
      }}
    </style>
  </defs>

  <!-- Card Background with Gradient Accent -->
  <g clip-path="url(#card-clip-{clean_id})">
    <rect class="card-bg" x="0.5" y="0.5" width="799" height="{height - 1}" rx="10" />
    <rect x="0" y="0" width="800" height="4" fill="url(#grad-{clean_id})" />
  </g>

  <!-- Header: Icon, Title & Meta -->
  <g transform="translate(25, 20)">
    <path fill="#7aa2f7" d="M4.72 3.22a.75.75 0 0 1 1.06 1.06L2.06 8l3.72 3.72a.75.75 0 1 1-1.06 1.06L.47 8.53a.75.75 0 0 1 0-1.06l4.25-4.25Zm6.56 0a.75.75 0 0 1 1.06 0l4.25 4.25a.75.75 0 0 1 0 1.06l-4.25 4.25a.75.75 0 0 1-1.06-1.06L13.94 8l-3.72-3.72a.75.75 0 0 1 0-1.06Z" />
    <text class="card-title" x="24" y="11">Language Share Across Repositories</text>
  </g>
  <text class="card-sub" x="775" y="31" text-anchor="end">{total_str} across {num_repos} public repos</text>

  <!-- Progress Bar Background & Segments -->
  <rect x="25" y="{bar_y}" width="{bar_w}" height="{bar_h}" rx="6" fill="#24283b" />
  <g clip-path="url(#bar-clip)">
    {segments_svg}
  </g>

  <!-- Legend -->
  <g>
{legend_svg}
  </g>
</svg>
"""
    return svg


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

    os.makedirs(CARDS_DIR, exist_ok=True)
    svg_content = generate_languages_svg(totals, total_bytes, len(repos))
    svg_file = os.path.join(CARDS_DIR, "languages.svg")
    with open(svg_file, "w", encoding="utf-8") as f:
        f.write(svg_content)

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
    inline_badges = " &nbsp; ".join(badges)
    card_url = f"https://raw.githubusercontent.com/{ORG}/.github/main/profile/cards/languages.svg"

    return (
        f'<div align="center">\n'
        f'  <img src="{card_url}" alt="Language Distribution" width="100%">\n'
        f'</div>\n\n'
        f'<p align="center">\n'
        f'  {inline_badges}\n'
        f'</p>'
    )


def build_history(repos, limit=8):
    top = [r for r in repos if r["stargazers_count"] > 0][:limit] or repos[:limit]
    names = ",".join(f"{ORG.lower()}/{r['name'].lower()}" for r in top)

    def img(url, theme):
        return f'<img src="{url}&theme={theme}" alt="Star history graph">'

    svg = f"https://api.star-history.com/svg?repos={names}&type=Date"
    return (
        "<picture>\n"
        f'  <source media="(prefers-color-scheme: dark)" srcset="{svg}&theme=dark">\n'
        f'  <source media="(prefers-color-scheme: light)" srcset="{svg}&theme=light">\n'
        f'  {img(svg, "light")}\n'
        "</picture>\n\n"
        "<sub>📈 Graph by [star-history.com](https://star-history.com), rendered live for the top repos. "
        "It updates as visitors view this page, so new stars show up instantly.</sub>"
    )


def build_meta():
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return (
        f"<sub>⚡ Last refreshed **{now}** · Data source: GitHub REST API (public repos only) · "
        f"Auto-synced continuously by [GitHub Actions](https://github.com/{ORG}/.github/blob/main/.github/workflows/update-profile-readme.yml)</sub>"
    )


SECTIONS = {
    "stats": lambda: build_stats(api(f"/orgs/{ORG}"), load_repos()),
    "repos": lambda: build_repos(load_repos()),
    "cards": lambda: build_cards(load_repos()),
    "languages": lambda: build_languages(load_repos()),
    "history": lambda: build_history(load_repos()),
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
