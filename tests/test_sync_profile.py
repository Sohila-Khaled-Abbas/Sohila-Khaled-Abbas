"""Behavior checks for public-source automation; no live API or secret required."""

import copy
import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("sync_profile", ROOT / "scripts/sync_profile.py")
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


def repository(name="sample", **changes):
    result = {"name": name, "full_name": f"Sohila-Khaled-Abbas/{name}", "owner": {"login": "Sohila-Khaled-Abbas"},
              "private": False, "fork": False, "archived": False, "description": "Validated data workflows.",
              "updated_at": "2026-10-30T10:00:00Z", "pushed_at": "2026-10-29T10:00:00Z", "homepage": None}
    result.update(changes)
    return result


class ProfileSyncTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / "profile.config.json").read_text())
        self.template = (ROOT / "templates/README.md").read_text()
        self.profile = {"name": "Sohila Khaled Abbas", "role": "Data & Analytics Engineer | Machine Learning Engineer",
                        "summary": "I build useful data workflows.", "location": "Egypt", "email": "contact@example.com",
                        "website": "https://portfolio.example", "linkedin": "https://linkedin.com/in/example",
                        "skill_groups": [{"title": "Engineering", "items": ["Python", "SQL"]}],
                        "education": {"degree": "B.Sc.", "institution": "University", "year": "2024"},
                        "experience": [], "training": []}
        self.details = {"projects": [{"repo": "pixelfed-analytics-engineering", "summary": "Curated summary.", "live": None}]}
        self.statuses = {"pixelfed-analytics-engineering": {"label": "In progress", "focus": "Improve validation."}}
        self.repos = [repository("pixelfed-analytics-engineering"), repository("another-project")]

    def render(self, repos=None, **changes):
        return sync.render(changes.get("profile", self.profile), repos if repos is not None else self.repos,
                           self.details, self.statuses, self.config, changes.get("template", self.template))[0]

    def test_public_discovery_rejects_private_fork_unknown_owner_and_self(self):
        repos = [repository("public"), repository("private", private=True), repository("fork", fork=True),
                 repository("unknown", private=None), repository("Sohila-Khaled-Abbas"),
                 repository("other-owner", owner={"login": "someone-else"}),
                 repository("misleading-name", full_name="someone-else/misleading-name")]
        self.assertEqual([r["name"] for r in sync.public_projects(repos, self.config["owner"])], ["public"])

    def test_new_repository_appears_without_config_change(self):
        result = self.render(self.repos + [repository("brand-new-project", updated_at="2026-10-31T10:00:00Z")])
        self.assertIn("Explore all 3 public original projects", result)
        self.assertIn("[brand-new-project]", result)
        self.assertIn("2026-10-31", result)

    def test_missing_or_private_featured_project_is_removed(self):
        result = self.render([repository("another-project"), repository("pixelfed-analytics-engineering", private=True)])
        self.assertNotIn("pixelfed-analytics-engineering", result)
        self.assertNotIn("Improve validation", result)

    def test_metadata_changes_refresh_description_link_and_activity(self):
        result = self.render([repository("sample", description="Updated warehouse design.",
                                        homepage="https://project.example/new", pushed_at="2026-10-31T11:00:00Z")])
        self.assertIn("Updated warehouse design.", result)
        self.assertIn("https://project.example/new", result)
        self.assertIn("2026-10-31", result)

    def test_explicit_in_progress_status_is_preserved(self):
        result = self.render()
        self.assertIn("**In progress**", result)
        self.assertIn("Improve validation.", result)

    def test_retired_website_is_suppressed_but_replacement_appears(self):
        repo = repository("the-data-tea", homepage="https://the-data-tea.vercel.app/")
        self.assertNotIn("https://the-data-tea.vercel.app", self.render([repo]))
        repo["homepage"] = "https://replacement.example"
        self.assertIn("https://replacement.example", self.render([repo]))

    def test_archived_project_remains_in_catalog_but_not_featured_or_recent(self):
        result = self.render([repository("pixelfed-analytics-engineering", archived=True), repository("active")])
        self.assertIn("**Archived**", result)
        featured = result.split("## Selected projects")[1].split("## My toolkit")[0]
        recent = result.split("## Latest project updates")[1].split("<details>")[0]
        self.assertNotIn("pixelfed-analytics-engineering", featured)
        self.assertNotIn("pixelfed-analytics-engineering", recent)

    def test_portfolio_sync_activity_does_not_create_feedback(self):
        repos = self.repos + [repository("sohila-k-abbas-website", updated_at="2026-10-31T10:00:00Z")]
        first = self.render(repos)
        repos[-1]["updated_at"] = "2026-11-01T11:00:00Z"
        repos[-1]["pushed_at"] = "2026-11-01T11:00:00Z"
        self.assertEqual(first, self.render(repos))

    def test_same_data_produces_stable_output_in_any_repository_order(self):
        self.assertEqual(self.render(), self.render(list(reversed(self.repos))))

    def test_html_and_markdown_are_escaped_and_unsafe_links_are_dropped(self):
        result = self.render([repository("sample", description='<script>alert(1)</script> | [trap](x)', homepage="javascript:alert(1)")])
        self.assertNotIn("<script>", result)
        self.assertNotIn("javascript:", result)
        self.assertIn("&lt;script&gt;", result)
        self.assertIn(r"\[trap\]", result)
        self.assertEqual(sync.url("https://example.com/a(b)"), "https://example.com/a%28b%29")
        self.assertEqual(sync.url("https://user:password@example.com"), "")

    def test_bio_role_skills_training_and_header_follow_portfolio(self):
        profile = copy.deepcopy(self.profile)
        profile["role"] = "Updated role"
        profile["summary"] = "Updated professional summary."
        profile["training"] = [{"title": "Completed program", "provider": "Academy", "date": "2026"}]
        result, header = sync.render(profile, self.repos, self.details, self.statuses, self.config, self.template)
        self.assertIn("Updated role", result)
        self.assertIn("Updated professional summary.", result)
        self.assertIn("Completed program", result)
        self.assertIn("Updated role", header)

    def test_complete_pagination_includes_second_page(self):
        calls = []
        def fetch(target):
            calls.append(target)
            return [repository(f"repo-{n}") for n in range(100)] if parse_qs(urlparse(target).query)["page"] == ["1"] else [repository("last-project")]
        result = sync.fetch_repositories(self.config["owner"], fetch)
        self.assertEqual(len(result), 101)
        self.assertIn("page=2", calls[-1])
        self.assertIn("/users/", calls[0])
        self.assertNotIn("/user/repos", calls[0])

    def test_incomplete_pagination_fails_instead_of_publishing_partial_list(self):
        def fetch(target):
            return [repository(f"repo-{n}") for n in range(100)] if parse_qs(urlparse(target).query)["page"] == ["1"] else {"message": "rate limited"}
        with self.assertRaises(ValueError):
            sync.fetch_repositories(self.config["owner"], fetch)

    def test_missing_template_marker_fails(self):
        with self.assertRaises(ValueError):
            self.render(template=self.template.replace("{{FEATURED}}", ""))

    def test_source_failure_preserves_existing_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "assets").mkdir()
            (root / "README.md").write_text("Previous profile")
            (root / "assets/header.svg").write_text("Previous header")
            (root / "profile.config.json").write_text(json.dumps(self.config))
            with patch.object(sync, "load_sources", side_effect=RuntimeError("source unavailable")):
                with self.assertRaises(RuntimeError):
                    sync.update(root)
            self.assertEqual((root / "README.md").read_text(), "Previous profile")
            self.assertEqual((root / "assets/header.svg").read_text(), "Previous header")

    def test_invalid_or_empty_sources_do_not_replace_valid_profile(self):
        with self.assertRaises(ValueError):
            self.render(repos=[])
        with self.assertRaises(ValueError):
            self.render(profile={})

    def test_token_is_sent_only_to_github_api_not_raw_content(self):
        targets = []
        def open_request(request, timeout):
            targets.append((request.full_url, request.get_header("Authorization")))
            return io.BytesIO(b'{"ok": true}')
        with patch.dict(os.environ, {"GITHUB_TOKEN": "test-only-placeholder"}), patch.object(sync, "urlopen", side_effect=open_request):
            sync.fetch_json("https://api.github.com/repos/owner/repo")
            sync.fetch_json("https://raw.githubusercontent.com/owner/repo/main/file.json")
        self.assertEqual(targets[0][1], "Bearer test-only-placeholder")
        self.assertIsNone(targets[1][1])


if __name__ == "__main__":
    unittest.main()
