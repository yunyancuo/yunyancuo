import json
import os
import re
import urllib.request


USERNAME = "yunyancuo"
README = "README.md"


def get_repositories():
    request = urllib.request.Request(
        f"https://api.github.com/users/{USERNAME}/repos?per_page=100&type=owner&sort=pushed",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USERNAME,
            "Authorization": f"Bearer {os.environ.get('GITHUB_TOKEN', '')}",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def clean(value):
    return (value or "暂无简介").replace("|", "\\|").replace("\n", " ").strip()


def main():
    repositories = [
        repo
        for repo in get_repositories()
        if repo["name"] != USERNAME and not repo.get("archived")
    ][:6]
    icons = {
        "Python": "🐍",
        "JavaScript": "🟨",
        "TypeScript": "🔷",
        "Jupyter Notebook": "📚",
        "Vue": "💚",
    }
    rows = ["| 项目 | 简介 |", "| --- | --- |"]
    for repo in repositories:
        icon = icons.get(repo.get("language"), "✨")
        rows.append(
            f"| [{icon} {repo['name']}]({repo['html_url']}) | {clean(repo.get('description'))} |"
        )
    replacement = "<!-- PROJECTS:START -->\n" + "\n".join(rows) + "\n<!-- PROJECTS:END -->"
    with open(README, "r", encoding="utf-8") as file:
        content = file.read()
    updated, count = re.subn(
        r"<!-- PROJECTS:START -->.*?<!-- PROJECTS:END -->",
        replacement,
        content,
        flags=re.DOTALL,
    )
    if count != 1:
        raise RuntimeError("README.md 中找不到唯一的 PROJECTS 标记。")
    with open(README, "w", encoding="utf-8", newline="\n") as file:
        file.write(updated)


main()
