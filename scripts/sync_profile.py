#!/usr/bin/env python3
"""Render the profile from a coherent public portfolio revision and public GitHub repos.

Standard library only. Build every output before replacing any file. Never enumerate
authenticated /user/repos or persist tokens, private data, or API response bodies.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.github.com"
SOURCE_FILES = ("profile.json", "project-details.json", "project-status.json")


def text(value: object, limit: int | None = None) -> str:
    value = " ".join(str(value or "").split())
    if limit and len(value) > limit:
        value = value[: limit - 1].rsplit(" ", 1)[0] + "…"
    value = html.escape(value, quote=False)
    return re.sub(r"([\\`*{}\[\]()|])", r"\\\1", value)


def url(value: object) -> str:
    value = str(value or "").strip()
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return ""
    return quote(value, safe=":/?#@!$&'+,;=%~-._")


def link(label: object, target: str) -> str:
    return f"[{text(label)}]({url(target)})"


def fetch_json(target: str) -> object:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "sohila-profile-sync/1.0"}
    if urlparse(target).netloc == "api.github.com":
        headers["X-GitHub-Api-Version"] = "2022-11-28"
        if token := os.environ.get("GITHUB_TOKEN"):
            headers["Authorization"] = f"Bearer {token}"
    for attempt in range(3):
        try:
            with urlopen(Request(target, headers=headers), timeout=25) as response:
                return json.load(response)
        except HTTPError as exc:
            if exc.code not in {429, 500, 502, 503, 504} or attempt == 2:
                raise RuntimeError(f"Public source request failed: HTTP {exc.code}") from None
        except (URLError, TimeoutError, OSError):
            if attempt == 2:
                raise RuntimeError("Public source request failed; previous profile kept.") from None
        time.sleep(2**attempt)
    raise RuntimeError("Public source could not be read.")


def fetch_repositories(owner: str, fetch=fetch_json) -> list[dict]:
    repositories = []
    for page in range(1, 101):
        batch = fetch(f"{API}/users/{quote(owner, safe='')}/repos?type=owner&sort=full_name&per_page=100&page={page}")
        if not isinstance(batch, list) or any(not isinstance(repo, dict) for repo in batch):
            raise ValueError("Incomplete public repository response; previous profile kept.")
        repositories.extend(batch)
        if len(batch) < 100:
            return repositories
    raise ValueError("Repository pagination did not complete; previous profile kept.")


def public_projects(repositories: list[dict], owner: str) -> list[dict]:
    projects = {}
    for repo in repositories:
        name = repo.get("name", "")
        if (repo.get("private") is not False or repo.get("fork") is not False
                or repo.get("owner", {}).get("login", "").casefold() != owner.casefold()
                or not re.fullmatch(r"[\w.-]+", name) or name.casefold() == owner.casefold()):
            continue
        if repo.get("full_name", "").casefold() != f"{owner}/{name}".casefold():
            continue
        projects[name.casefold()] = repo
    if not projects:
        raise ValueError("No public original projects found; previous profile kept.")
    return sorted(projects.values(), key=lambda repo: repo["name"].casefold())


def validate_sources(profile: dict, details: dict, statuses: dict) -> None:
    if not isinstance(profile, dict) or not all(profile.get(key) for key in ("name", "role", "summary", "website")):
        raise ValueError("Portfolio profile is incomplete.")
    if not url(profile["website"]) or not url(profile.get("linkedin")):
        raise ValueError("Portfolio contact links are invalid.")
    if not isinstance(profile.get("skill_groups"), list) or not profile["skill_groups"]:
        raise ValueError("Portfolio skills are incomplete.")
    if not isinstance(profile.get("training"), list) or not isinstance(profile.get("experience"), list):
        raise ValueError("Portfolio learning or experience is incomplete.")
    if not isinstance(profile.get("education"), dict) or not profile["education"].get("degree"):
        raise ValueError("Portfolio education is incomplete.")
    if not isinstance(details, dict) or not isinstance(details.get("projects"), list):
        raise ValueError("Portfolio project details are incomplete.")
    if not isinstance(statuses, dict) or any(not isinstance(item, dict) for item in statuses.values()):
        raise ValueError("Portfolio project statuses are incomplete.")


def badge(label: str, target: str, color: str) -> str:
    src = f"https://img.shields.io/badge/{quote(label, safe='')}-{color}?style=flat-square"
    return f'<a href="{html.escape(target, quote=True)}"><img src="{src}" alt="{html.escape(label, quote=True)}" /></a>'


def render(profile: dict, repositories: list[dict], details: dict, statuses: dict, config: dict, template: str) -> tuple[str, str]:
    validate_sources(profile, details, statuses)
    owner = config["owner"]
    projects = public_projects(repositories, owner)
    by_name = {p["name"]: p for p in projects}
    curated = {p["repo"]: p for p in details["projects"] if isinstance(p, dict) and p.get("repo")}
    portfolio = url(profile["website"]).rstrip("/")
    contact_email = str(profile.get("email", ""))
    if not re.fullmatch(r"[^\s<>\"@]+@[^\s<>\"@]+\.[^\s<>\"@]+", contact_email):
        raise ValueError("Portfolio contact email is invalid.")
    contact = "mailto:" + quote(contact_email, safe="@.+-")

    def repo_url(name):
        return f"https://github.com/{owner}/{name}"

    def title(name):
        override = next((p["title"] for p in config["featured"] if p["repo"] == name), None)
        return override or name

    def summary(repo):
        detail = curated.get(repo["name"], {})
        return text(repo.get("description") or detail.get("github", {}).get("readme_excerpt") or detail.get("summary") or "Source code, documentation, and project notes.", 210)

    def status(name):
        if by_name[name].get("archived"):
            return " · **Archived**"
        label = statuses.get(name, {}).get("label")
        return f" · **{text(label)}**" if label else ""

    def live(repo):
        # The current public repo Website setting is authoritative. A portfolio
        # live link is a fallback only when the field has not been populated.
        detail = curated.get(repo["name"], {})
        target = url(repo.get("homepage")) or url(detail.get("live"))
        ignored = {url(item).rstrip("/") for item in config.get("ignored_websites", [])}
        return "" if target.rstrip("/") in ignored else target

    blocks = {}
    blocks["INTRO"] = f'# {text(profile["name"])}\n\n### {text(profile["role"].replace(" | ", " · "))}\n\n'
    blocks["INTRO"] += "<p>" + "\n".join([
        badge("Portfolio", portfolio + "/", "79515D"),
        badge("LinkedIn", url(profile["linkedin"]), "5F514A"),
        badge("Email", contact, "79515D"),
    ]) + "</p>\n\n"
    blocks["INTRO"] += f'{text(profile.get("location"))} · Open to remote collaboration'
    blocks["ABOUT"] = text(profile["summary"])

    current = []
    for name, item in statuses.items():
        if name in by_name and not by_name[name].get("archived"):
            current.append(f'- **{link(title(name), repo_url(name))}**{status(name)}<br>\n  {text(item.get("focus"))}')
    blocks["CURRENT"] = "\n".join(current) or "Explore the latest public work below."

    featured = []
    for item in config["featured"]:
        name = item["repo"]
        if name not in by_name or by_name[name].get("archived"):
            continue
        repo = by_name[name]
        links = []
        if name in curated:
            links.append(link("Project preview", f"{portfolio}/projects/{name}/"))
        if target := live(repo):
            links.append(link("Website / report", target))
        suffix = " · ".join(links)
        featured.append(f'- **{link(item["title"], repo_url(name))}**{status(name)}<br>\n  {summary(repo)}' + (f'<br>\n  {suffix}' if suffix else ""))
    blocks["FEATURED"] = "\n\n".join(featured)

    blocks["SKILLS"] = "\n".join(f'- **{text(group["title"])}:** ' + ", ".join(text(item) for item in group["items"]) for group in profile["skill_groups"])
    blocks["LEARNING"] = "\n".join(f'- **{link(item["title"], live(by_name[item["repo"]]) or repo_url(item["repo"]))}** — {text(item["focus"])}' for item in config["learning"] if item["repo"] in by_name)

    education = profile["education"]
    blocks["BACKGROUND"] = '<details>\n<summary><strong>Background, experience & training</strong></summary>\n\n'
    blocks["BACKGROUND"] += f'**{text(education["degree"])}** · {text(education.get("institution"))} · {text(education.get("year"))}\n\n'
    blocks["BACKGROUND"] += "### Experience\n\n" + "\n".join(f'- **{text(item["role"])}** · {text(item["organization"])} · {text(item["dates"])}' for item in profile["experience"])
    blocks["BACKGROUND"] += "\n\n### Training\n\n" + "\n".join(f'- **{text(item["title"])}** · {text(item["provider"])} · {text(item["date"])}' for item in profile["training"])
    blocks["BACKGROUND"] += f'\n\n{link("Full résumé", portfolio + "/resume/")} · {link("Courses & credentials", portfolio + "/credentials/")}\n\n</details>'

    # Infrastructure synchronization commits must not bounce between profile and
    # portfolio. Exclude both repositories from the activity ranking.
    infrastructure = {owner.casefold(), config["portfolio_repository"].split("/")[1].casefold()}
    recent = [p for p in projects if not p.get("archived") and p["name"].casefold() not in infrastructure]
    recent.sort(key=lambda p: (max(p.get("updated_at") or "", p.get("pushed_at") or ""), p["name"].casefold()), reverse=True)
    recent_lines = []
    for repo in recent[:config.get("recent_limit", 5)]:
        date = max(repo.get("updated_at") or "", repo.get("pushed_at") or "")[:10]
        recent_lines.append(f'- **{link(title(repo["name"]), repo_url(repo["name"]))}** · {text(date) or "Date unavailable"}{status(repo["name"])}<br>\n  {summary(repo)}')
    blocks["RECENT"] = "\n\n".join(recent_lines) + "\n\n<sub>Public repository updates, newest first. Dates are UTC; activity does not imply project completion.</sub>"

    blocks["CATALOG"] = f'<details>\n<summary><strong>Explore all {len(projects)} public original projects</strong></summary>\n\n'
    entries = []
    for repo in projects:
        target = live(repo)
        website = f' · {link("Website", target)}' if target else ""
        entries.append(f'- **{link(repo["name"], repo_url(repo["name"]))}**{status(repo["name"])}{website}<br>\n  {summary(repo)}')
    blocks["CATALOG"] += "\n\n".join(entries) + "\n\n</details>"
    blocks["CONNECT"] = f'## Let’s build something useful\n\nOpen to remote projects in **business intelligence, data & analytics engineering, and workflow automation**.\n\n{link("Explore my portfolio", portfolio + "/")} · {link("Connect on LinkedIn", profile["linkedin"])} · [Email me]({contact})'

    for key, value in blocks.items():
        marker = "{{" + key + "}}"
        if template.count(marker) != 1:
            raise ValueError(f"Template must contain exactly one {marker} marker.")
        template = template.replace(marker, value)
    if re.search(r"\{\{[A-Z_]+\}\}", template):
        raise ValueError("Unresolved template marker.")
    return template, render_header(profile)


def render_header(profile: dict) -> str:
    name = html.escape(profile["name"])
    role = html.escape(profile["role"].replace(" | ", " · "))
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="280" viewBox="0 0 1200 280" role="img" aria-labelledby="title desc">
  <title id="title">{name} — Good data. Better decisions.</title>
  <desc id="desc">Ivory and burgundy data-flow illustration. {role}.</desc>
  <defs>
    <linearGradient id="bg" x2="1" y2="1"><stop stop-color="#32272b"/><stop offset="1" stop-color="#211c20"/></linearGradient>
    <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse"><path d="M40 0H0V40" fill="none" stroke="#f4e9dc" stroke-opacity=".045"/></pattern>
  </defs>
  <rect width="1200" height="280" rx="22" fill="url(#bg)"/>
  <rect width="1200" height="280" rx="22" fill="url(#grid)"/>
  <path d="M840 0V65Q840 92 868 92H1000Q1030 92 1030 122V190Q1030 220 1060 220H1200" fill="none" stroke="#b1808b" stroke-width="2"/>
  <path d="M920 0V160Q920 190 950 190H1200" fill="none" stroke="#d1b9a6" stroke-opacity=".35" stroke-width="2"/>
  <g fill="#2b2227" stroke="#c598a2" stroke-width="2"><circle cx="840" cy="65" r="8"/><circle cx="1030" cy="122" r="8"/><circle cx="1030" cy="190" r="8"/><circle cx="920" cy="160" r="8"/></g>
  <text x="58" y="58" font-family="Arial,sans-serif" font-size="13" letter-spacing="3" fill="#c69ba5">ENGINEER / ANALYZE / AUTOMATE</text>
  <text x="56" y="124" font-family="Georgia,serif" font-size="48" fill="#f7efe5">{name}</text>
  <text x="59" y="167" font-family="Arial,sans-serif" font-size="20" fill="#dfcdbf">{role}</text>
  <path d="M58 197H122" stroke="#b1808b" stroke-width="3"/>
  <text x="58" y="235" font-family="Arial,sans-serif" font-size="20" fill="#f1e5da">Good data. Better decisions.</text>
</svg>
'''


def load_sources(config: dict, source_dir: Path | None = None) -> tuple:
    if source_dir:
        files = {name: json.loads((source_dir / name).read_text()) for name in SOURCE_FILES}
        repositories = json.loads((source_dir / "repositories.json").read_text())
        if not isinstance(repositories, list):
            raise ValueError("Offline repositories must be a complete public REST response list.")
    else:
        repository = config["portfolio_repository"]
        revision = fetch_json(f'{API}/repos/{repository}/commits/{quote(config["portfolio_branch"], safe="")}')
        sha = revision.get("sha", "") if isinstance(revision, dict) else ""
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise ValueError("Cannot resolve a coherent portfolio revision.")
        base = f'https://raw.githubusercontent.com/{repository}/{sha}/{config["portfolio_content_path"]}'
        files = {name: fetch_json(f"{base}/{name}") for name in SOURCE_FILES}
        repositories = fetch_repositories(config["owner"])
    return files["profile.json"], repositories, files["project-details.json"], files["project-status.json"]


def update(root: Path = ROOT, source_dir: Path | None = None, check: bool = False) -> bool:
    config = json.loads((root / "profile.config.json").read_text())
    profile, repositories, details, statuses = load_sources(config, source_dir)
    readme, header = render(profile, repositories, details, statuses, config, (root / "templates/README.md").read_text())
    outputs = {root / "README.md": readme, root / "assets/header.svg": header}
    changed = {path: value for path, value in outputs.items() if not path.exists() or path.read_text() != value}
    if check:
        if changed:
            raise ValueError("Profile differs from its sources. Run scripts/sync_profile.py.")
    else:
        # Fetching, schema checks, and rendering have all succeeded before writes.
        for path, value in changed.items():
            temp = path.with_suffix(path.suffix + ".tmp")
            temp.write_text(value, encoding="utf-8")
            temp.replace(path)
    print(f'Profile {"refreshed" if changed else "is current"}: {len(public_projects(repositories, config["owner"]))} public original projects; {len(changed)} changed files.')
    return bool(changed)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, help="Use previously retrieved public JSON for offline validation.")
    parser.add_argument("--check", action="store_true", help="Validate generated content without writing.")
    args = parser.parse_args()
    try:
        update(source_dir=args.source_dir, check=args.check)
    except (ValueError, KeyError, TypeError, RuntimeError, OSError) as exc:
        print(f"Profile sync stopped: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
