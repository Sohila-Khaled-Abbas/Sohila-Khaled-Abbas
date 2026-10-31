# Profile README automation

The profile shares its professional content with [Sohila’s portfolio](https://sohila-khaled-abbas.vercel.app/). New public projects and existing project metadata refresh without hand-editing the profile README.

## What refreshes

| Content | Source |
| --- | --- |
| Name, role, bio, location, contact links, toolkit, experience, education, training | `portfolio-site/content/profile.json` in `Sohila-Khaled-Abbas/sohila-k-abbas-website` |
| Explicit project status and current focus | Portfolio `content/project-status.json` |
| Project preview links and fallback summaries/live links | Portfolio `content/project-details.json` |
| New repositories, descriptions, Website links, archive labels, and activity dates | GitHub’s public `/users/Sohila-Khaled-Abbas/repos` endpoint, with complete pagination |
| Featured project selection and learning links | Local `profile.config.json` |
| Page structure and the manually written learning focus | Local `templates/README.md` |

The banner is generated with the current name and role. The full project collection includes every public original repository except the profile repository itself, including clearly labeled archives. Forks, private repositories, and repositories owned by other accounts are excluded. Featured and learning entries must still exist in the current public list to appear.

GitHub repository descriptions are preferred over portfolio summaries so updates appear promptly. A missing Website field can fall back to the portfolio’s curated live link; remove that curated link too when retiring a website. A source push updates its activity date, but this automation does not infer completion, skill proficiency, employment, or business results from code changes. It does not summarize arbitrary commits with AI. Add substantive changes to the project description or portfolio content when you want the overview to reflect them.

## Schedule and first run

[**Sync profile README**](https://github.com/Sohila-Khaled-Abbas/Sohila-Khaled-Abbas/actions/workflows/sync-profile.yml) runs hourly at minute **37**, after the portfolio’s minute-17 sync. It also runs when its template, implementation, configuration, or tests change on `main`. Use **Actions → Sync profile README → Run workflow** for an earlier refresh.

This is periodic synchronization. GitHub can delay scheduled runs, and the portfolio and profile jobs are independent. Changes to portfolio content appear on the next successful profile run; curated README excerpts can take the preceding portfolio sync as well. GitHub disables public-repository schedules after 60 days without repository activity; re-enable a paused workflow from Actions.

The workflow uses GitHub’s built-in ephemeral `GITHUB_TOKEN`; no PAT, Vercel secret, additional service, or ChatGPT scheduled task is needed. Write permission is scoped to this profile repository. The portfolio repository is only read, at one resolved commit so its three content files form a consistent snapshot.

## Edit content

1. Update your portfolio `profile.json` for a changed role, skill, training item, or contact link.
2. Update portfolio `project-status.json` for project status and active focus.
3. Update a public repository’s description and Website setting for its current overview and destination.
4. Edit local `profile.config.json` to change featured projects or learning resources. `ignored_websites` suppresses exact unavailable or access-restricted URLs; a replacement URL on the source repository is still discovered automatically. Their public source repositories remain listed. Remove a suppression when the same URL becomes publicly available again.
5. Edit `templates/README.md` for layout, capability descriptions, or the learning-focus paragraph. Avoid editing generated `README.md` directly: the next sync replaces it.

Existing metric, snake, visitor-chart, and link-validation workflows are preserved. Their assets retain their own refresh schedules.

### Website exceptions verified during this update

| Website | Observation | Profile behavior |
| --- | --- | --- |
| `the-data-tea.vercel.app` | HTTP 404 | Keep the public source repository; omit the unavailable website. |
| FlyRank internship GitHub Pages URL | Repeated HTTP 503 | Keep the public source repository; omit the unavailable website. |
| `data-engineering-learning-roadmap.vercel.app` | HTTP 403 in GitHub Actions; the Vercel project reports SSO protection on all deployments | Learning link falls back to the public GitHub repository. Hosting protection is unchanged. |
| Stock Price Data Pipeline’s Udemy share URL | Course link, not a project deployment; HTTP 403 in GitHub Actions | Keep the public project source; omit the restricted course URL as a project website. |

## Validation and failure behavior

```sh
python3 -m unittest discover -s tests -v
python3 scripts/sync_profile.py
python3 scripts/check_readme_mobile.py
```

The generator uses Python’s standard library. For offline validation, `--source-dir PATH` accepts `profile.json`, `project-details.json`, `project-status.json`, and `repositories.json`; the repository file must contain a complete raw public REST response list. Add `--check` to compare outputs without writing.

All sources must load, all repository pages must complete, and schema validation and rendering must succeed before files are replaced. A rate limit or source failure leaves the last published profile intact and fails the Actions run. External text is escaped before Markdown/HTML rendering, and non-HTTPS project links are dropped.

Output is deterministic. There is no “last checked” timestamp or empty hourly commit. The profile itself is excluded from discovery, and portfolio synchronization activity is excluded from the recent-project ranking, preventing the profile and portfolio from repeatedly updating each other. Only `README.md` and `assets/header.svg` are committed by the refresh job.

Pull requests run validation with read-only permissions; they do not publish. A normal refresh validates generated mobile/SVG layout before committing because pushes made with `GITHUB_TOKEN` do not start the separate push-validation workflows. Publishing uses normal fast-forward/rebase behavior and never force-pushes. If branch protection later requires PRs, adapt the publisher to that policy rather than weakening branch rules.

## References

- [Public repository listing and pagination](https://docs.github.com/en/rest/repos/repos#list-repositories-for-a-user)
- [Scheduled workflow behavior](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
- [GITHUB_TOKEN and workflow triggering](https://docs.github.com/en/actions/concepts/security/github_token)
