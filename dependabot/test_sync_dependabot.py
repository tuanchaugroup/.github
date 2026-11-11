import importlib.util
import pathlib
import unittest
from unittest.mock import MagicMock

MODULE = pathlib.Path(__file__).with_name("sync_dependabot.py")
spec = importlib.util.spec_from_file_location("sync_dependabot", MODULE)
mod = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

try:
    import yaml
except ImportError:
    yaml = None


class DetectionTests(unittest.TestCase):
    def test_mixed_monorepo(self):
        paths = [
            ".github/workflows/ci.yml", "package.json", "apps/admin/package.json",
            "apps/api/Api.csproj", "apps/worker/Worker.csproj", "Directory.Packages.props",
            "Dockerfile", "docker-compose.prod.yml", "mobile/pubspec.yaml",
            "mobile/android/build.gradle.kts", "src-tauri/Cargo.toml", "service/pyproject.toml",
            "deploy/main.tf", "go/go.mod", "php/composer.json", "global.json",
        ]
        result = mod.package_directories(paths)
        self.assertEqual(result["npm"], ["/", "/apps/admin"])
        self.assertEqual(result["nuget"], ["/", "/apps/api", "/apps/worker"])
        self.assertEqual(result["github-actions"], ["/"])
        self.assertEqual(result["docker-compose"], ["/"])
        for ecosystem in ["docker", "pub", "gradle", "cargo", "pip", "terraform", "gomod", "composer", "dotnet-sdk"]:
            self.assertIn(ecosystem, result)
        content = mod.generate(paths)
        self.assertIn('    directories:\n      - "/"\n      - "/apps/admin"', content)
        self.assertNotIn("target-branch", content)
        self.assertNotIn("auto-merge", content)
        self.assertIn('timezone: "Asia/Ho_Chi_Minh"', content)
        if yaml:
            x = yaml.safe_load(content)
            self.assertEqual(x["version"], 2)
            self.assertEqual(len(x["updates"]), len(result))
            self.assertTrue(all(item["open-pull-requests-limit"] == 3 for item in x["updates"]))
            self.assertTrue(all(item["schedule"]["interval"] == "weekly" for item in x["updates"]))
            self.assertTrue(all(bool(item.get("directory")) ^ bool(item.get("directories")) for item in x["updates"]))

    def test_vendor_and_agent_script_filtered(self):
        paths = [".agents/skills/ui-styling/scripts/pyproject.toml",
                 "src/wwwroot/adminlte/plugins/jquery/package.json",
                 "src/frontend/public/tinymce/composer.json",
                 "node_modules/lib/package.json", "site/venv/pyproject.toml",
                 "frontend/package.json", ".github/workflows/release.yml"]
        result = mod.package_directories(paths)
        self.assertNotIn("pip", result)
        self.assertNotIn("composer", result)
        self.assertEqual(result["npm"], ["/frontend"])
        self.assertIn("github-actions", result)

    def test_uv_precedence(self):
        paths = ["api/pyproject.toml", "api/uv.lock"]
        self.assertEqual(mod.package_directories(paths), {"uv": ["/api"]})

    def test_bun_precedence(self):
        paths = ["app/package.json", "app/bun.lock"]
        self.assertEqual(mod.package_directories(paths), {"bun": ["/app"]})

    def test_empty(self):
        self.assertIsNone(mod.generate(["README.md", "docs/manual.md"]))

    def test_apply_is_not_called_in_dry_run(self):
        github = MagicMock()
        repo = mod.Repository("tuanchaugroup/example", "developer")
        github.get.side_effect = AssertionError("GitHub should not be called for dry run propose")
        self.assertEqual(mod.propose(github, repo, "version: 2", False), "DRY_RUN")
        github.assert_not_called()

    def test_existing_branch_not_touched(self):
        github = MagicMock()
        repo = mod.Repository("tuanchaugroup/example", "main")
        github.get.return_value = {"ref": "refs/heads/automation/dependabot-policy-v1"}
        self.assertEqual(mod.propose(github, repo, "version: 2", True), "SKIP_BRANCH_ALREADY_EXISTS")
        github.post.assert_not_called()
        github.put.assert_not_called()


if __name__ == "__main__":
    unittest.main()
