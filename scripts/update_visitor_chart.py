#!/usr/bin/env python3
"""Persist GitHub repository traffic and render a README-friendly SVG chart."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen


API_VERSION = "2022-11-28"
DEFAULT_DATA = Path("data/visitor-analytics.json")
DEFAULT_OUTPUT = Path("assets/visitor-analytics.svg")


def fetch_views(repo: str, token: str) -> list[dict]:
    url = f"https://api.github.com/repos/{repo}/traffic/views"
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": "github-profile-visitor-analytics",
        },
    )
    with urlopen(request, timeout=30) as response:
        payload = json.load(response)
    return payload.get("views", [])


def load_data(path: Path) -> dict:
    if not path.exists():
        return {"repository": os.environ.get("GITHUB_REPOSITORY", ""), "views": []}
    return json.loads(path.read_text(encoding="utf-8"))


def merge_views(existing: list[dict], incoming: list[dict]) -> list[dict]:
    merged = {
        item["date"]: {
            "date": item["date"],
            "views": int(item.get("views", 0)),
            "uniques": int(item.get("uniques", 0)),
        }
        for item in existing
        if "date" in item
    }
    for item in incoming:
        timestamp = item.get("timestamp", "")
        date = timestamp[:10] if timestamp else item.get("date")
        if date:
            merged[date] = {
                "date": date,
                "views": int(item.get("count", item.get("views", 0))),
                "uniques": int(item.get("uniques", 0)),
            }
    return [merged[key] for key in sorted(merged)][-365:]


def esc(value: object) -> str:
    return (str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def render_svg(data: list[dict], output: Path, repository: str) -> None:
    points = data[-30:]
    if not points:
        points = [{"date": "No data", "views": 0, "uniques": 0}]
    max_value = max(max(int(item["views"]), int(item["uniques"])) for item in points) or 1
    width, height = 960, 330
    chart_x, chart_y, chart_w, chart_h = 56, 130, 848, 128
    step = chart_w / max(len(points) - 1, 1)
    bars = []
    labels = []
    line_points = []
    unique_points = []
    for index, item in enumerate(points):
        x = chart_x + index * step
        views = int(item["views"])
        uniques = int(item["uniques"])
        bar_h = (views / max_value) * chart_h
        y = chart_y + chart_h - bar_h
        bars.append(f'<rect x="{x - 7:.1f}" y="{y:.1f}" width="14" height="{bar_h:.1f}" rx="4" fill="#60a5fa" opacity=".88"><title>{esc(item["date"])}: {views} views</title></rect>')
        line_y = chart_y + chart_h - (views / max_value) * chart_h
        unique_y = chart_y + chart_h - (uniques / max_value) * chart_h
        line_points.append(f"{x:.1f},{line_y:.1f}")
        unique_points.append(f"{x:.1f},{unique_y:.1f}")
        if index in {0, len(points) // 2, len(points) - 1}:
            labels.append(f'<text x="{x:.1f}" y="286" text-anchor="middle" font-size="11" fill="#64748b">{esc(item["date"][5:])}</text>')
    total_views = sum(int(item["views"]) for item in points)
    total_uniques = sum(int(item["uniques"]) for item in points)
    latest = points[-1]["date"]
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
  <title id="title">Visitor analytics for {esc(repository)}</title>
  <desc id="desc">A repository-owned chart of GitHub traffic views and unique visitors for the latest available daily observations.</desc>
  <defs><linearGradient id="bg" x1="0" x2="1"><stop stop-color="#f8fafc"/><stop offset="1" stop-color="#eff6ff"/></linearGradient><filter id="shadow"><feDropShadow dx="0" dy="5" stdDeviation="8" flood-color="#1e3a8a" flood-opacity=".12"/></filter></defs>
  <rect width="{width}" height="{height}" rx="24" fill="url(#bg)"/>
  <text x="38" y="40" font-family="Inter,Arial,sans-serif" font-size="19" font-weight="700" fill="#0f172a">Visitor analytics</text>
  <text x="38" y="64" font-family="Inter,Arial,sans-serif" font-size="12" fill="#64748b">GitHub Traffic API · latest persisted daily observations · updated {esc(generated)}</text>
  <g font-family="Inter,Arial,sans-serif" text-anchor="middle" filter="url(#shadow)">
    <g transform="translate(38 78)"><rect width="175" height="42" rx="12" fill="#fff" stroke="#bfdbfe"/><text x="87" y="27" font-size="16" font-weight="700" fill="#2563eb">{total_views}</text><text x="132" y="27" font-size="11" fill="#64748b">views</text></g>
    <g transform="translate(228 78)"><rect width="175" height="42" rx="12" fill="#fff" stroke="#c7d2fe"/><text x="87" y="27" font-size="16" font-weight="700" fill="#4f46e5">{total_uniques}</text><text x="135" y="27" font-size="11" fill="#64748b">unique</text></g>
    <g transform="translate(418 78)"><rect width="175" height="42" rx="12" fill="#fff" stroke="#ddd6fe"/><text x="87" y="27" font-size="16" font-weight="700" fill="#7c3aed">{len(points)}</text><text x="136" y="27" font-size="11" fill="#64748b">days</text></g>
    <g transform="translate(608 78)"><rect width="314" height="42" rx="12" fill="#fff" stroke="#bbf7d0"/><text x="157" y="27" font-size="13" font-weight="700" fill="#15803d">Last observation: {esc(latest)}</text></g>
  </g>
  <line x1="{chart_x}" y1="{chart_y + chart_h}" x2="{chart_x + chart_w}" y2="{chart_y + chart_h}" stroke="#cbd5e1"/>
  {''.join(bars)}
  <polyline points="{' '.join(line_points)}" fill="none" stroke="#1d4ed8" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
  <polyline points="{' '.join(unique_points)}" fill="none" stroke="#7c3aed" stroke-width="2" stroke-dasharray="6 6" stroke-linecap="round"/>
  {''.join(labels)}
  <circle cx="72" cy="311" r="5" fill="#1d4ed8"/><text x="84" y="315" font-family="Inter,Arial,sans-serif" font-size="11" fill="#475569">views</text><circle cx="133" cy="311" r="5" fill="#7c3aed"/><text x="145" y="315" font-family="Inter,Arial,sans-serif" font-size="11" fill="#475569">unique visitors</text>
</svg>
'''
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(svg, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--views-json", type=Path, help="Use a saved Traffic API response for local seeding")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    repo = os.environ.get("GITHUB_REPOSITORY", "Sohila-Khaled-Abbas/Sohila-Khaled-Abbas")
    state = load_data(args.data)
    if args.views_json:
        payload = json.loads(args.views_json.read_text(encoding="utf-8"))
        incoming = payload.get("views", payload if isinstance(payload, list) else [])
    else:
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            raise SystemExit("GITHUB_TOKEN is required unless --views-json is provided")
        incoming = fetch_views(repo, token)
    state["repository"] = repo
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    state["views"] = merge_views(state.get("views", []), incoming)
    args.data.parent.mkdir(parents=True, exist_ok=True)
    args.data.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    render_svg(state["views"], args.output, repo)
    print(f"Persisted {len(state['views'])} daily observations to {args.data} and rendered {args.output}")


if __name__ == "__main__":
    main()
