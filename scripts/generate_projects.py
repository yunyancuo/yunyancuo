import os
import re
import httpx
from datetime import datetime, timezone

USER = os.environ["GH_USER"]
TOKEN = os.environ["GH_TOKEN"]
ORGS = ["Infinite-Monkey-Lab"]

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

EXCLUDED = {USER, ".github", "demo-repository", "infinite-monkey-lab"}

# 置顶顺序 + 精修文案 + 技术标签（写过的项目不该被 0 星埋没）
PRIORITY = [
    "todotree",
    "astrbot_plugin_zhiren_leaderboard",
    "FeiyuCursor",
    "velorag",
    "astrbot_plugin_wuwa_echo",
    "keresearch",
    "notes-for-deep-learniung",
]
MAX_CARDS = 8

ICONS = {
    "todotree": "🖥️",
    "astrbot_plugin_zhiren_leaderboard": "🏆",
    "FeiyuCursor": "🐋",
    "MoeCursor": "🖱️",
    "velorag": "🚀",
    "astrbot_plugin_wuwa_echo": "🐍",
    "keresearch": "🧪",
    "notes-for-deep-learniung": "📚",
}

BLURBS = {
    "astrbot_plugin_zhiren_leaderboard": "Group-chat leaderboard plugin for AstrBot — score tracking, weekly auto-broadcasts and a built-in web ranking page",
    "FeiyuCursor": "DeepSeek-chan (大肥鱼) animated mouse cursor pack for Windows 11 — 16-frame breathing star-trail & full 17-role coverage",
    "MoeCursor": "DeepSeek-chan mouse cursor pack for Windows 11 — 17 sticker-style cursors in multi-size .cur files",
    "todotree": "A Windows desktop todo wall — dark-gold, semi-transparent, truly pinned to the desktop layer (WorkerW). Data is just one Markdown file",
    "velorag": "Production-grade RAG framework — hybrid search + knowledge graph + agent canvas",
    "astrbot_plugin_wuwa_echo": "Wuthering Waves echo scoring plugin for AstrBot",
    "keresearch": "Research-lifecycle Agent Skills: topic selection → experiments → writing → submission (Claude Code & ZCode ready)",
    "notes-for-deep-learniung": "Deep learning paper notes with hands-on code",
}

TAGS = {
    "astrbot_plugin_zhiren_leaderboard": ["Python", "AstrBot Plugin", "Web UI"],
    "FeiyuCursor": ["Windows 11", "Cursor Pack", "DeepSeek"],
    "MoeCursor": ["Windows 11", "Cursor Pack"],
    "todotree": ["Electron", "Markdown", "WorkerW"],
    "velorag": ["Python", "RAG", "Knowledge Graph"],
    "astrbot_plugin_wuwa_echo": ["Python", "AstrBot Plugin"],
    "keresearch": ["Agent Skills", "Claude Code", "ZCode"],
    "notes-for-deep-learniung": ["Jupyter", "Deep Learning"],
}


def fetch_json(url: str) -> dict | list:
    resp = httpx.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_head(url: str) -> httpx.Response:
    return httpx.head(url, headers=HEADERS, timeout=30)


def render_card(repo: dict) -> str:
    name = repo["name"]
    full_name = repo.get("full_name", f"{USER}/{name}")
    owner_login = repo.get("owner", {}).get("login", USER)
    icon = ICONS.get(name, "📦")
    blurb = BLURBS.get(name) or (repo.get("description") or name)
    blurb = blurb.replace("|", "\\|").replace("\n", " ")
    tags = list(TAGS.get(name) or [repo.get("language") or "Code"])
    if owner_login in ORGS and "Infinite Monkey Lab" not in tags:
        tags.append("Infinite Monkey Lab")
    tag_line = " ".join(f"`{t}`" for t in tags)
    extra = ""
    if name == "todotree":
        extra = f' ![release](https://img.shields.io/github/v/release/{full_name}?style=flat-square&color=dd4f6b)'
    return (
        '<td width="50%" valign="top">\n\n'
        f"**{icon} [{name}]({repo['html_url']})**{extra}  \n"
        f"{blurb}  \n"
        f"{tag_line}\n\n"
        "</td>"
    )


def main():
    repos = list(
        fetch_json(
            f"https://api.github.com/users/{USER}/repos?per_page=50&sort=updated&type=owner"
        )
    )
    seen_names = {r["name"] for r in repos}

    for org in ORGS:
        try:
            org_repos = fetch_json(
                f"https://api.github.com/orgs/{org}/repos?per_page=50&sort=updated&type=public"
            )
            for r in org_repos:
                if r["name"] in seen_names or r["name"] in EXCLUDED:
                    continue
                if r["name"] in PRIORITY:
                    repos.append(r)
                    seen_names.add(r["name"])
        except Exception as e:
            print(f"Warning: failed to fetch org {org}: {e}")

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
            "**🔎 More experiments**  \n"
            "Crawlers, scripts and lessons learned — see the full repo list  \n"
            f"[All repositories →](https://github.com/{USER}?tab=repositories)\n\n"
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
        + f"\n\n> Auto-updated · {stamp}\n"
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
