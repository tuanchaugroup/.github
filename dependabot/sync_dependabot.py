#!/usr/bin/env python3
"""Generate and optionally propose per-repository Dependabot configs.

No third-party dependencies. Read-only by default. Apply creates PRs; never merges.
Run locally or inside a PRIVATE authorized administrative CI environment.
Do not schedule this cross-repository process in the public .github repository.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

API = "https://api.github.com"
POLICY_MARKER = "# Managed by tuanchaugroup/.github/dependabot/sync_dependabot.py"
BRANCH = "automation/dependabot-policy-v1"
EXCLUDE_SEGMENTS = {
    ".git", ".agents", ".claude", ".codex", ".cursor", ".dart_tool",
    ".gradle", ".next", ".terraform", ".venv", "venv", "env", "node_modules",
    "vendor", "third_party", "third-party", "public", "wwwroot", "dist", "build",
    "coverage", "__pycache__", "site-packages", "target", "fixtures", "examples",
}
ECOSYSTEM_ORDER = (
    "github-actions", "npm", "nuget", "dotnet-sdk", "pip", "uv", "pub",
    "cargo", "rust-toolchain", "gradle", "maven", "gomod", "composer", "docker",
    "docker-compose", "terraform", "helm", "devcontainers", "pre-commit",
)


class GitHubError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(f"GitHub HTTP {code}: {message}")
        self.code = code


@dataclass(frozen=True)
class Repository:
    full_name: str
    branch: str
    archived: bool = False


class GitHub:
    def __init__(self, token: str):
        if not token.strip():
            raise ValueError("Set GITHUB_TOKEN (read for dry-run; contents+PR write for apply)")
        self.token = token

    def request(self, method: str, path: str, payload: dict | None = None):
        url = API + path
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = Request(url, method=method, data=data,
                      headers={"Authorization": f"Bearer {self.token}",
                               "Accept": "application/vnd.github+json",
                               "X-GitHub-Api-Version": "2022-11-28",
                               "User-Agent": "tcg-dependabot-policy/1.0",
                               **({"Content-Type": "application/json"} if data is not None else {})})
        for attempt in range(3):
            try:
                with urlopen(req, timeout=35) as response:
                    raw = response.read()
                    return json.loads(raw.decode("utf-8")) if raw else None
            except HTTPError as exc:
                body = exc.read(4096).decode("utf-8", errors="replace")
                if exc.code in (429, 502, 503, 504) and attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                raise GitHubError(exc.code, body[:500]) from None
            except URLError as exc:
                if attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError("GitHub network unavailable") from exc

    def get(self, path: str):
        return self.request("GET", path)

    def post(self, path: str, payload: dict):
        return self.request("POST", path, payload)

    def put(self, path: str, payload: dict):
        return self.request("PUT", path, payload)


def package_directories(paths: list[str]) -> dict[str, list[str]]:
    """Discover eligible manifest directories only; excludes bundled/AI skill assets."""
    ecosystems: dict[str, set[str]] = defaultdict(set)
    for original in paths:
        pure = PurePosixPath(original)
        name = pure.name
        segments = pure.parts[:-1]
        if any(segment.lower() in EXCLUDE_SEGMENTS for segment in segments):
            continue
        directory = "/" + "/".join(segments) if segments else "/"
        if name == "package.json":
            ecosystems["npm"].add(directory)
        if name.endswith((".csproj", ".fsproj", ".vbproj")) or name in ("Directory.Packages.props", "packages.config"):
            ecosystems["nuget"].add(directory)
        if name == "global.json":
            ecosystems["dotnet-sdk"].add(directory)
        if name in ("pyproject.toml", "Pipfile", "poetry.lock", "setup.py", "setup.cfg") or re.fullmatch(r"requirements(?:[-_.][a-zA-Z0-9_-]+)?\.txt", name):
            ecosystems["pip"].add(directory)
        if name == "uv.lock":
            ecosystems["uv"].add(directory)
        if name == "pubspec.yaml":
            ecosystems["pub"].add(directory)
        if name == "Cargo.toml":
            ecosystems["cargo"].add(directory)
        if name in ("rust-toolchain", "rust-toolchain.toml"):
            ecosystems["rust-toolchain"].add(directory)
        if name in ("build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"):
            ecosystems["gradle"].add(directory)
        if name == "pom.xml":
            ecosystems["maven"].add(directory)
        if name == "go.mod":
            ecosystems["gomod"].add(directory)
        if name == "composer.json":
            ecosystems["composer"].add(directory)
        if name == "Dockerfile" or name.startswith("Dockerfile."):
            ecosystems["docker"].add(directory)
        if re.fullmatch(r"(?:docker-)?compose(?:[.-][A-Za-z0-9_.-]+)?\.ya?ml", name):
            ecosystems["docker-compose"].add(directory)
        if name.endswith(".tf"):
            ecosystems["terraform"].add(directory)
        if name == "Chart.yaml":
            ecosystems["helm"].add(directory)
        if name in (".devcontainer.json", "devcontainer.json") and (not segments or segments[0] == ".devcontainer"):
            ecosystems["devcontainers"].add("/")
        if name == ".pre-commit-config.yaml":
            ecosystems["pre-commit"].add(directory)
        if (len(pure.parts) >= 3 and pure.parts[0] == ".github" and
                pure.parts[1] == "workflows" and name.endswith((".yml", ".yaml"))):
            ecosystems["github-actions"].add("/")
        if name in ("action.yml", "action.yaml") and not segments:
            ecosystems["github-actions"].add("/")
    # A project managed by uv should not also be updated by pip in the same directory.
    # Likewise, prefer the active bun package manager over npm when Bun lockfiles are present.
    for item in paths:
        p = PurePosixPath(item)
        d = "/" + "/".join(p.parts[:-1]) if len(p.parts) > 1 else "/"
        if p.name in ("bun.lock", "bun.lockb") and d in ecosystems["npm"]:
            ecosystems["npm"].discard(d)
            ecosystems["bun"].add(d)
        if p.name == "uv.lock" and d in ecosystems["pip"]:
            ecosystems["pip"].discard(d)
    if "bun" in ecosystems and "bun" not in ECOSYSTEM_ORDER:
        # Bun lockfiles were detected; the ordering is handled below.
        pass
    return {key: sorted(value, key=lambda x: (x != "/", x))
            for key, value in ecosystems.items() if value}


def generate(paths: list[str]) -> str | None:
    ecosystems = package_directories(paths)
    if not ecosystems:
        return None
    order = (*ECOSYSTEM_ORDER, "bun")
    lines = [POLICY_MARKER,
             "# Each repository must store this file at .github/dependabot.yml on its default branch.",
             "# Human review + CI are mandatory. No automatic merges or production deployment.",
             "version: 2", "updates:"]
    for ecosystem in order:
        dirs = ecosystems.get(ecosystem)
        if not dirs:
            continue
        lines.append(f'  - package-ecosystem: "{ecosystem}"')
        if len(dirs) == 1:
            lines.append(f'    directory: "{dirs[0]}"')
        else:
            lines.append("    directories:")
            for directory in dirs:
                lines.append(f'      - "{directory}"')
        lines.extend(["    schedule:", '      interval: "weekly"',
                      '      day: "tuesday"', '      time: "09:00"',
                      '      timezone: "Asia/Ho_Chi_Minh"',
                      "    open-pull-requests-limit: 3",
                      "    commit-message:", '      prefix: "chore(deps)"'])
        if ecosystem in {"npm", "nuget", "pip", "cargo", "pub"}:
            lines.extend(["    groups:", "      patch-updates:", "        patterns:",
                          '          - "*"', "        update-types:", '          - "patch"'])
    return "\n".join(lines) + "\n"


def list_org_repositories(gh: GitHub, org: str) -> list[Repository]:
    found = []
    for page in range(1, 100):
        data = gh.get(f"/orgs/{quote(org)}/repos?{urlencode({'per_page':100,'page':page,'type':'all'})}")
        if not data:
            break
        for r in data:
            if not r.get("archived") and not r.get("fork"):
                found.append(Repository(r["full_name"], r["default_branch"], False))
        if len(data) < 100:
            break
    return found


def get_content(gh: GitHub, repo: str, path: str, ref: str):
    try:
        return gh.get(f"/repos/{repo}/contents/{path}?ref={quote(ref, safe='')}")
    except GitHubError as e:
        if e.code == 404:
            return None
        raise


def propose(gh: GitHub, repo: Repository, content: str, apply: bool) -> str:
    if not apply:
        return "DRY_RUN"
    # A deterministic branch means repeat invocations are idempotent and do not spam PRs.
    try:
        gh.get(f"/repos/{repo.full_name}/git/ref/heads/{BRANCH}")
        return "SKIP_BRANCH_ALREADY_EXISTS"
    except GitHubError as e:
        if e.code != 404:
            raise
    base = gh.get(f"/repos/{repo.full_name}/git/ref/heads/{quote(repo.branch, safe='')}")
    gh.post(f"/repos/{repo.full_name}/git/refs",
            {"ref": "refs/heads/" + BRANCH, "sha": base["object"]["sha"]})
    gh.put(f"/repos/{repo.full_name}/contents/.github/dependabot.yml",
           {"message": "chore: add TCG Dependabot policy", "branch": BRANCH,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii")})
    result = gh.post(f"/repos/{repo.full_name}/pulls", {
        "title": "chore: adopt TCG Dependabot policy", "head": BRANCH,
        "base": repo.branch,
        "body": "Central policy source: https://github.com/tuanchaugroup/.github/tree/main/dependabot\n\n"
                "Please review manifest paths, private registry access (NuGet, npm, Docker), CI, "
                "security updates, and breaking changes before merging. No auto-merge.\n",
        "draft": True,
    })
    return "PR " + str(result["number"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org", default="tuanchaugroup")
    parser.add_argument("--repo", action="append", help="Only this repository (repeatable)")
    parser.add_argument("--apply", action="store_true", help="Opt in to creating draft PRs")
    parser.add_argument("--max-repos", type=int, default=0, help="Cap processed repos (0=all)")
    args = parser.parse_args(argv)
    gh = GitHub(os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or "")
    wanted = set(args.repo or [])
    statuses: dict[str, int] = defaultdict(int)
    failures = []
    for n, repo in enumerate(list_org_repositories(gh, args.org), 1):
        if repo.full_name == f"{args.org}/.github":
            continue
        if wanted and repo.full_name not in wanted and repo.full_name.split("/")[1] not in wanted:
            continue
        if args.max_repos and sum(statuses.values()) >= args.max_repos:
            break
        try:
            old = get_content(gh, repo.full_name, ".github/dependabot.yml", repo.branch)
            old = old or get_content(gh, repo.full_name, ".github/dependabot.yaml", repo.branch)
            if old:
                # Preserve all existing local configurations, even previously generated files.
                statuses["SKIP_EXISTING_CONFIG"] += 1
                print(f"{repo.full_name}: SKIP_EXISTING_CONFIG")
                continue
            tree = gh.get(f"/repos/{repo.full_name}/git/trees/{quote(repo.branch, safe='')}?recursive=1")
            if tree.get("truncated"):
                statuses["SKIP_TRUNCATED_TREE"] += 1
                print(f"{repo.full_name}: SKIP_TRUNCATED_TREE")
                continue
            paths = [item["path"] for item in tree.get("tree", []) if item.get("type") == "blob"]
            config = generate(paths)
            if not config:
                statuses["SKIP_NO_MANIFESTS"] += 1
                print(f"{repo.full_name}: SKIP_NO_MANIFESTS")
                continue
            state = propose(gh, repo, config, args.apply)
            statuses[state.split(" ")[0]] += 1
            kinds = ",".join(package_directories(paths))
            flags = " [check private registry]" if any(p.endswith(("nuget.config", "NuGet.Config", ".npmrc")) for p in paths) else ""
            print(f"{repo.full_name} [{repo.branch}]: {state} [{kinds}]{flags}")
        except (GitHubError, RuntimeError) as e:
            failures.append(repo.full_name)
            statuses["ERROR"] += 1
            print(f"{repo.full_name}: ERROR ({e})", file=sys.stderr)
    print("Summary: " + json.dumps(statuses, sort_keys=True))
    if failures:
        print("Some repositories require manual follow-up; nothing was force-pushed.", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
