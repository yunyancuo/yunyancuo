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

# 置顶顺序 + 精修文案 + 技术标签（写过的项目不该被 0 星埋没）
PRIORITY = ["todotree", "velorag", "astrbot_plugin_wuwa_echo", "keresearch", "notes-for-deep-learniung"]
MAX_CARDS = 6

ICONS = {
    "todotree": "🖥️",
    "velorag": "🚀",
    "astrbot_plugin_wuwa_echo": "🐍",
    "keresearch": "🧪",
    "notes-for-deep-learniung": "📚",
}

BLURBS = {
    "todotree": "Windows 桌面待办墙：暗金半透明、真·锁死在桌面底层（WorkerW），数据就是一份 Markdown",
    "velorag": "混合检索 + 知识图谱 + Agent 画布的生产级 RAG 框架",
    "astrbot_plugin_wuwa_echo": "鸣潮声骸自动评分的 AstrBot 插件",
    "keresearch": "科研全生命周期 Agent Skills：选题 → 实验 → 写作 → 投稿（ZCode / Claude Code 通用）",
    "notes-for-deep-learniung": "深度学习论文笔记与代码实践",
}

TAGS = {
    "todotree": ["Electron", "Markdown", "WorkerW"],
    "velorag": ["Python", "RAG", "知识图谱"],
    "astrbot_plugin_wuwa_echo": ["Python", "AstrBot 插件"],
    "keresearch": ["Agent Skills", "Claude Code"],
    "notes-for-deep-learniung": ["Jupyter", "深度学习"],
}


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


def render_card(repo: dict) -> str:
    name = repo["name"]
    icon = ICONS.get(name, "📦")
    blurb = BLURBS.get(name) or (repo.get("description") or name)
    blurb = blurb.replace("|", "\\|").replace("\n", " ")
    tags = TAGS.get(name) or [repo.get("language") or "Code"]
    tag_line = " ".join(f"`{t}`" for t in tags)
    extra = ""
    if name == "todotree":
        extra = ' ![release](https://img.shields.io/github/v/release/yunyancuo/todotree?style=flat-square&color=dd4f6b)'
    return (
        '<td width="50%" valign="top">\n\n'
        f"**{icon} [{name}]({repo['html_url']})**{extra}  \n"
        f"{blurb}  \n"
        f"{tag_line}\n\n"
        "</td>"
    )


def main():
    repos = fetch_json(
        f"https://api.github.com/users/{USER}/repos?per_page=50&sort=updated&type=owner"
    )

    featured, others = [], []
    for repo in repos:
        if repo["name"] in EXCLUDED or repo.get("private") or repo.get("fork"):
            continue  # fork 与个人主页仓库不上墙
        (featured if repo["name"] in PRIORITY else others).append(repo)

    featured.sort(key=lambda r: PRIORITY.index(r["name"]))
    others.sort(key=lambda r: r["pushed_at"], reverse=True)
    selected = (featured + others)[:MAX_CARDS]

    cells = [render_card(repo) for repo in selected]
    if len(cells) % 2 == 1:
        cells.append(
            '<td width="50%" valign="top">\n\n'
            "**🔎 更多实验与练习**  \n"
            "爬虫、脚本、踩坑记录都在仓库列表里  \n"
            f"[全部仓库 →](https://github.com/{USER}?tab=repositories)\n\n"
            "</td>"
        )

    rows = ["<table>", "<tr>"]
    for i, cell in enumerate(cells):
        rows.append(cell)
        if i % 2 == 1 and i != len(cells) - 1:
            rows.append("</tr>")
            rows.append("<tr>")
    rows.append("</tr>")
    rows.append("</table>")

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    replacement = (
        "<!-- PROJECTS:START -->\n"
        + "\n".join(rows)
        + f"\n\n> 自动更新 · {stamp}\n"
        + "<!-- PROJECTS:END -->"
    )

    with open("README.md", "r", encoding="utf-8") as f:
        content = f.read()

    pattern = r"(<!-- PROJECTS:START -->).*?(<!-- PROJECTS:END -->)"
    content = re.sub(pattern, replacement, content, flags=re.DOTALL)

    with open("README.md", "w", encoding="utf-8") as f:
        f.write(content)

    print("Projects card grid updated.")


if __name__ == "__main__":
    main()
