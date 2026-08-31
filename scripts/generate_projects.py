import os
import re
import httpx
from datetime import datetime, timezone

USER = os.environ["GH_USER"]
TOKEN = os.environ["GH_TOKEN"]

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

EXCLUDED = {USER}

ICONS = {
    "velorag": "🚀",
    "AstrBot": "✨",
    "astrbot_plugin_wuwa_echo": "🐍",
    "HDU_AUTO_BOOK-public": "✨",
    "notes-for-deep-learniung": "📚",
}

ROLE_ORDER = {"Creator": 0, "Core": 1, "Contributor": 2, "viewer": 3}


def fetch_json(url: str) -> dict | list:
    resp = httpx.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_head(url: str) -> httpx.Response:
    return httpx.head(url, headers=HEADERS, timeout=30)


def get_contribution_info(owner: str, repo: str, is_fork: bool) -> dict:
    """
    Returns dict with 'commits' and 'role'.
    For forks, checks contributions on the upstream source repo.
    """
    # For forks, find the source repo to check real contributions
    target_owner = owner
    target_repo = repo
    if is_fork:
        try:
            repo_info = fetch_json(f"https://api.github.com/repos/{owner}/{repo}")
            source = repo_info.get("source") or repo_info.get("parent")
            if source:
                target_owner = source["owner"]["login"]
                target_repo = source["name"]
        except Exception:
            pass

    # Strategy 1: use author-filtered commits to get count
    commits = 0
    try:
        resp = fetch_head(
            f"https://api.github.com/repos/{target_owner}/{target_repo}/commits?author={USER}&per_page=1"
        )
        link = resp.headers.get("link", "")
        if 'rel="last"' in link:
            last_page = int(re.search(r'page=(\d+)>; rel="last"', link).group(1))
            commits = last_page
        else:
            commits_page = fetch_json(
                f"https://api.github.com/repos/{target_owner}/{target_repo}/commits?author={USER}&per_page=1"
            )
            commits = 1 if (isinstance(commits_page, list) and len(commits_page) > 0) else 0
    except Exception:
        pass

    # Strategy 2: try stats API on target repo
    try:
        stats = fetch_json(
            f"https://api.github.com/repos/{target_owner}/{target_repo}/stats/contributors"
        )
        if isinstance(stats, list) and len(stats) > 0:
            total = sum(a.get("total", 0) for a in stats)
            user_commits = 0
            for author in stats:
                if author.get("author", {}).get("login") == USER:
                    user_commits = author.get("total", 0)
            if total > 0:
                commits = max(commits, user_commits)
    except Exception:
        pass

    # Determine role
    if is_fork:
        if commits > 10:
            role = "Core"
        elif commits > 0:
            role = "Contributor"
        else:
            role = "Contributor" if commits > 0 else "viewer"
    else:
        if commits > 0:
            role = "Creator"
        else:
            role = "Creator"

    return {"commits": commits, "role": role}


def main():
    repos = fetch_json(
        f"https://api.github.com/users/{USER}/repos?per_page=50&sort=updated&type=owner"
    )

    rows = []
    for repo in repos:
        name = repo["name"]
        if name in EXCLUDED or repo.get("private"):
            continue

        icon = ICONS.get(name, "📦")
        desc = ((repo.get("description") or name)[:80]).replace("|", "\\|")
        url = repo["html_url"]
        lang = repo.get("language") or "—"
        stars = repo.get("stargazers_count", 0)
        is_fork = repo.get("fork", False)
        fork_label = "🍴 fork" if is_fork else "📦 source"

        info = get_contribution_info(repo["owner"]["login"], name, is_fork)
        role = info["role"]
        commits = info["commits"]
        commit_str = f"{commits} commits" if commits > 0 else "—"

        row = f"| [{icon} {name}]({url}) | {desc} | {stars} ⭐ | {lang} | {fork_label} | {role} ({commit_str}) |"
        rows.append(row)

    rows.append(f"\n> 自动更新 · {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")

    # Read README
    with open("README.md", "r", encoding="utf-8") as f:
        content = f.read()

    pattern = r"(<!-- PROJECTS:START -->).*?(<!-- PROJECTS:END -->)"
    replacement = f"<!-- PROJECTS:START -->\n| 项目 | 简介 | Stars | 语言 | 类型 | 我的参与 |\n| --- | --- | --- | --- | --- | --- |\n" + "\n".join(rows) + "\n<!-- PROJECTS:END -->"

    content = re.sub(pattern, replacement, content, flags=re.DOTALL)

    with open("README.md", "w", encoding="utf-8") as f:
        f.write(content)

    print("Projects table updated.")


if __name__ == "__main__":
    main()
