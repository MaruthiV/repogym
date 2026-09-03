import json
import re
import subprocess
from pathlib import Path

import yaml

from repogym.images import RepoEntry, image_tag

CLOSES_RE = re.compile(r"(?:close[sd]?|fix(?:es|ed)?|resolve[sd]?)\s+#(\d+)", re.IGNORECASE)
ADDED_TEST_RE = re.compile(r"^\+\s*(?:async )?def (test_\w+)", re.MULTILINE)
MAX_TOTAL_CHANGES = 400
MAX_SOURCE_FILES = 5
MIN_ISSUE_BODY = 80


def gh_api(path: str, accept: str | None = None) -> str:
    cmd = ["gh", "api", path]
    if accept:
        cmd += ["-H", f"Accept: {accept}"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(f"gh api {path} failed: {r.stderr[-300:]}")
    return r.stdout


def linked_issue(slug: str, pr_num: int, pr_body: str) -> dict | None:
    m = CLOSES_RE.search(pr_body or "")
    if m:
        try:
            issue = json.loads(gh_api(f"repos/{slug}/issues/{m.group(1)}"))
            if not issue.get("pull_request"):
                return issue
        except RuntimeError:
            pass  # issues disabled (httpx uses discussions) or bad ref - try graphql
    # fall back to ui-linked issues via graphql
    owner, name = slug.split("/")
    q = ("query($owner:String!,$name:String!,$number:Int!){repository(owner:$owner,name:$name)"
         "{pullRequest(number:$number){closingIssuesReferences(first:1)"
         "{nodes{number title body url}}}}}")
    r = subprocess.run(
        ["gh", "api", "graphql", "-f", f"query={q}", "-F", f"owner={owner}",
         "-F", f"name={name}", "-F", f"number={pr_num}"],
        capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        return None
    nodes = (json.loads(r.stdout).get("data", {}).get("repository", {})
             .get("pullRequest", {}).get("closingIssuesReferences", {}).get("nodes") or [])
    if not nodes:
        return None
    n = nodes[0]
    return {"title": n["title"], "body": n.get("body") or "", "html_url": n["url"],
            "number": n["number"]}


def is_test_file(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return path.startswith("tests/") or "/tests/" in path or name.startswith("test_")


def split_diff(diff: str) -> dict[str, str]:
    # chunk a unified diff into per-file pieces keyed by new path
    files: dict[str, str] = {}
    for chunk in re.split(r"(?m)^(?=diff --git )", diff):
        if not chunk.startswith("diff --git "):
            continue
        m = re.search(r"^diff --git a/(\S+) b/(\S+)", chunk)
        if m:
            files[m.group(2)] = chunk
    return files


def clean_issue_body(body: str) -> str:
    body = re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL)
    body = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", body)
    return body.strip()[:4000]


def mine_repo(repo_key: str, entry: RepoEntry, out_dir: Path, limit: int = 50) -> dict:
    slug = entry.url.removeprefix("https://github.com/")
    stats = {"scanned": 0, "no_linked_issue": 0, "bad_shape": 0, "thin_issue": 0,
             "no_added_tests": 0, "written": 0}

    prs = []
    for page in range(1, 11):
        batch = json.loads(gh_api(
            f"repos/{slug}/pulls?state=closed&per_page=100&page={page}&sort=updated&direction=desc"))
        if not batch:
            break
        prs += [pr for pr in batch if pr.get("merged_at")]
        if len(prs) >= limit:
            break
    for pr in prs[:limit]:
        stats["scanned"] += 1
        num = pr["number"]

        issue = linked_issue(slug, num, pr.get("body") or "")
        if issue is None:
            stats["no_linked_issue"] += 1
            continue
        if len(issue.get("body") or "") < MIN_ISSUE_BODY:
            stats["thin_issue"] += 1
            continue

        files = json.loads(gh_api(f"repos/{slug}/pulls/{num}/files?per_page=100"))
        test_files = [f["filename"] for f in files if is_test_file(f["filename"])]
        src_files = [f["filename"] for f in files if not is_test_file(f["filename"])]
        total = sum(f.get("changes", 0) for f in files)
        if not test_files or not src_files or len(src_files) > MAX_SOURCE_FILES \
                or total > MAX_TOTAL_CHANGES:
            stats["bad_shape"] += 1
            continue

        diff = gh_api(f"repos/{slug}/pulls/{num}", accept="application/vnd.github.diff")
        chunks = split_diff(diff)
        tests_diff = "".join(v for k, v in chunks.items() if is_test_file(k))
        gold_diff = "".join(v for k, v in chunks.items() if not is_test_file(k))

        f2p = [f"{path}::{name}"
               for path, chunk in chunks.items() if is_test_file(path)
               for name in ADDED_TEST_RE.findall(chunk)]
        if not f2p or not gold_diff.strip():
            stats["no_added_tests"] += 1
            continue

        # base.sha can postdate the fix; the true pre-fix state is the merge's first parent
        merge_sha = pr.get("merge_commit_sha")
        base_commit = pr["base"]["sha"]
        if merge_sha:
            commit = json.loads(gh_api(f"repos/{slug}/commits/{merge_sha}"))
            parents = commit.get("parents") or []
            if parents:
                base_commit = parents[0]["sha"]

        task_id = f"{repo_key}-pr{num}"
        tdir = out_dir / task_id
        tdir.mkdir(parents=True, exist_ok=True)
        (tdir / "tests.patch").write_text(tests_diff)
        (tdir / "gold.patch").write_text(gold_diff)
        spec = {
            "id": task_id,
            "repo": slug,
            "base_commit": base_commit,
            "language": entry.language,
            "category": "bug_fix",
            "level": "L2" if len(src_files) == 1 else "L3",
            "source": "mined",
            "prompt": f"{issue['title']}\n\n{clean_issue_body(issue.get('body') or '')}\n",
            "hidden_tests": {"patch": "tests.patch", "fail_to_pass": f2p,
                             "pass_to_pass": list(entry.default_p2p)},
            "oracle": {"patch": "gold.patch"},
            "runtime": {"profile": entry.language, "repo_key": repo_key,
                        "image": image_tag(repo_key, entry)},
            "timeouts": {"agent_s": 900, "eval_s": 300},
            "security_probes": ["secret_canary"],
            "meta": {"pr": num, "issue": issue.get("number"),
                     "merged_at": pr["merged_at"], "issue_url": issue["html_url"]},
        }
        (tdir / "task.yaml").write_text(yaml.safe_dump(spec, sort_keys=False, allow_unicode=True))
        stats["written"] += 1

    return stats
