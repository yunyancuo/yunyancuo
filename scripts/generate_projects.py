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

EXCLUDED = {USER, "yunyancuo"}

ICONS = {
    "velorag": "🚀",
    "AstrBot": "✨",
    "astrbot_plugin_wuwa_echo": "🐍",
    "HDU_AUTO_BOOK-public": "✨",
    "notes-for-deep-learniung": "📚",
}


def fetch_json(url: str) -> dict:
    resp = httpx.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_repo_contributions(owner: str, repo: str) -> dict:
    """Get commit stats for the user on a specific repo."""
    try:
        stats = fetch_json(
            f"https://api.github.com/repos/{owner}/{repo}/stats/contributors"
        )
        if isinstance(stats, dict):
            return {"commits": 0, "role": "viewer"}

        for author in stats:
            if author["author"]["login"] == USER:
                commits = author["total"]
                if commits > 0.8 * sum(a["total"] for a in stats if a["total"]):
                    role = "Creator"
                elif commits > 0.3 * sum(a["total"] for a in stats if a["total"]):
                    role = "Core"
                else:
                    role = "Contributor"
                return {"commits": commits, "role": role}
        return {"commits": 0, "role": "viewer"}
    except Exception:
        return {"commits": 0, "role": "viewer"}


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
        desc = (repo.get("description") or name)[:80]
        url = repo["html_url"]
        lang = repo.get("language") or ""
        stars = repo.get("stargazers_count", 0)
        fork = "🍴 fork" if repo.get("fork") else "📦 source"

        contrib = get_repo_contributions(repo["owner"]["login"], name)
        role = contrib["role"]
        commits = contrib["commits"]

        row = f"| [{icon} {name}]({url}) | {desc} | {stars} ⭐ | {lang} | {fork} | {role} ({commits} commits) |"
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
