"""生成并更新 README.md 中的公开项目卡片网格。

从 GitHub REST API 拉取个人与指定组织的公开仓库，结合
``scripts/projects_config.json`` 中的排序与元数据配置，安全渲染为双列 HTML 卡片并
原子更新 ``<!-- PROJECTS:START --> ... <!-- PROJECTS:END -->`` 锚点区块。
"""

from __future__ import annotations

import html
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# 允许直接通过 `python scripts/generate_projects.py` 或包导入方式运行
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from _common import (  # noqa: E402
    atomic_write_text,
    build_github_headers,
    replace_anchor_block,
    request_json,
    sanitize_url,
    truncate_display_width,
)

ROOT = _SCRIPTS_DIR.parent
DEFAULT_CONFIG_PATH = _SCRIPTS_DIR / "projects_config.json"
DEFAULT_README_PATH = ROOT / "README.md"
PROJECTS_START = "<!-- PROJECTS:START -->"
PROJECTS_END = "<!-- PROJECTS:END -->"

DEFAULT_CONFIG: dict[str, Any] = {
    "orgs": ["Infinite-Monkey-Lab"],
    "excluded": ["yunyancuo", ".github", "demo-repository", "infinite-monkey-lab"],
    "max_cards": 8,
    "max_blurb_width": 136,
    "release_badges": ["todotree"],
    "priority": [
        "todotree",
        "astrbot_plugin_zhiren_leaderboard",
        "FeiyuCursor",
        "velorag",
        "astrbot_plugin_wuwa_echo",
        "keresearch",
        "notes-for-deep-learniung",
        "campus-tls-fix",
        "multi-agent-study-notes",
    ],
    "projects": {},
}


def load_config(config_path: Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    """加载项目卡片元数据配置，配置文件缺失时回退到内置默认值。"""
    config = dict(DEFAULT_CONFIG)
    if config_path.exists():
        loaded = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError(f"配置文件格式无效，根节点必须为 JSON 对象：{config_path}")
        config.update(loaded)
    return config


def _escape_markdown_inline(text: str) -> str:
    """对嵌入 HTML 表格内 Markdown 的文本执行 HTML 转义与管道符清洗。"""
    collapsed = " ".join((text or "").split())
    escaped = html.escape(collapsed, quote=True)
    return escaped.replace("|", "\\|")


def _escape_code_tag(tag: str) -> str:
    """安全渲染单个行内代码标签，防止反引号或 HTML 标签破坏结构。"""
    cleaned = " ".join((tag or "").split()).replace("`", "'")
    return f"`{html.escape(cleaned, quote=True)}`"


def render_card(repo: dict[str, Any], user: str, config: dict[str, Any]) -> str:
    """将单个仓库对象安全渲染为 HTML 表格单元格。"""
    projects_meta: dict[str, dict[str, Any]] = config.get("projects") or {}
    orgs = set(config.get("orgs") or [])
    release_badges = set(config.get("release_badges") or [])
    max_blurb_width = int(config.get("max_blurb_width") or 136)

    name = str(repo["name"])
    meta = projects_meta.get(name) or {}
    full_name = str(repo.get("full_name") or f"{user}/{name}")
    owner_login = str((repo.get("owner") or {}).get("login") or user)

    icon = str(meta.get("icon") or "📦")
    raw_blurb = meta.get("blurb") or repo.get("description") or name
    blurb = _escape_markdown_inline(truncate_display_width(str(raw_blurb), max_blurb_width))

    raw_tags = meta.get("tags") or [repo.get("language") or "Code"]
    tags = [str(tag) for tag in raw_tags if tag]
    if owner_login in orgs and "Infinite Monkey Lab" not in tags:
        tags.append("Infinite Monkey Lab")
    tag_line = " ".join(_escape_code_tag(tag) for tag in tags)

    safe_name = _escape_markdown_inline(name).replace("[", "\\[").replace("]", "\\]")
    safe_url = sanitize_url(str(repo.get("html_url") or f"https://github.com/{full_name}"))
    if not safe_url:
        safe_url = f"https://github.com/{user}"

    extra = ""
    if name in release_badges:
        badge_repo = html.escape(full_name, quote=True)
        extra = (
            f" ![release](https://img.shields.io/github/v/release/"
            f"{badge_repo}?style=flat-square&color=dd4f6b)"
        )

    return (
        '<td width="50%" valign="top">\n\n'
        f"**{icon} [{safe_name}]({safe_url})**{extra}<br>\n"
        f"{blurb}<br>\n"
        f"{tag_line}\n\n"
        "</td>"
    )


def select_repositories(
    repos: list[dict[str, Any]],
    user: str,
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    """按排除规则、置顶顺序与最近推送时间筛选待展示的项目列表。"""
    excluded = set(config.get("excluded") or []) | {user}
    priority = list(config.get("priority") or [])
    priority_rank = {repo_name: idx for idx, repo_name in enumerate(priority)}
    max_cards = int(config.get("max_cards") or 8)

    featured: list[dict[str, Any]] = []
    others: list[dict[str, Any]] = []
    seen_names: set[str] = set()

    for repo in repos:
        name = repo.get("name")
        if (
            not name
            or name in seen_names
            or name in excluded
            or repo.get("private")
            or repo.get("fork")
            or repo.get("archived")
        ):
            continue
        seen_names.add(name)
        if name in priority_rank:
            featured.append(repo)
        else:
            others.append(repo)

    featured.sort(key=lambda item: priority_rank[item["name"]])
    others.sort(key=lambda item: item.get("pushed_at") or "", reverse=True)
    return (featured + others)[:max_cards]


def build_projects_table(
    selected: list[dict[str, Any]],
    user: str,
    config: dict[str, Any],
) -> str:
    """将筛选后的项目列表组装为双列 HTML 表格字符串。"""
    cells = [render_card(repo, user, config) for repo in selected]
    if len(cells) % 2 == 1:
        safe_user = html.escape(user, quote=True)
        cells.append(
            '<td width="50%" valign="top">\n\n'
            "**🔎 More experiments**<br>\n"
            "Crawlers, scripts and lessons learned — see the full repo list<br>\n"
            f"[All repositories →](https://github.com/{safe_user}?tab=repositories)\n\n"
            "</td>"
        )

    rows = ["<table>", "<tr>"]
    for idx, cell in enumerate(cells):
        rows.append(cell)
        if idx % 2 == 1 and idx != len(cells) - 1:
            rows.append("</tr>")
            rows.append("<tr>")
    rows.append("</tr>")
    rows.append("</table>")
    return "\n".join(rows)


def extract_existing_table(readme_content: str) -> str | None:
    """提取 README.md 当前锚点区块内的项目表格 HTML，用于幂等性比对。"""
    pattern = re.compile(
        re.escape(PROJECTS_START) + r"\s*(<table>.*?</table>).*?" + re.escape(PROJECTS_END),
        flags=re.DOTALL,
    )
    match = pattern.search(readme_content)
    return match.group(1).strip() if match else None


def fetch_all_repositories(
    user: str,
    token: str | None,
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    """拉取个人仓库及配置组织中的精选公开仓库。"""
    headers = build_github_headers(token=token, user_agent=user)
    secrets = (token,) if token else ()

    user_repos = request_json(
        f"https://api.github.com/users/{user}/repos?per_page=100&sort=updated&type=owner",
        headers=headers,
        secrets=secrets,
    )
    repos = list(user_repos)
    seen_names = {repo["name"] for repo in repos if repo.get("name")}
    excluded = set(config.get("excluded") or []) | {user}
    priority_set = set(config.get("priority") or [])

    for org in config.get("orgs") or []:
        try:
            org_repos = request_json(
                f"https://api.github.com/orgs/{org}/repos?per_page=100&sort=updated&type=public",
                headers=headers,
                secrets=secrets,
            )
            for repo in org_repos:
                name = repo.get("name")
                if not name or name in seen_names or name in excluded:
                    continue
                if name in priority_set:
                    repos.append(repo)
                    seen_names.add(name)
        except Exception as err:
            print(f"Warning: failed to fetch org {org}: {err}")

    return repos


def update_readme_projects(
    readme_path: Path,
    selected: list[dict[str, Any]],
    user: str,
    config: dict[str, Any],
    *,
    now: datetime | None = None,
    force_timestamp: bool = False,
) -> bool:
    """更新 README.md 项目区块；若表格内容未变化且未强制刷新时间戳则跳过写入。"""
    content = readme_path.read_text(encoding="utf-8")
    table_html = build_projects_table(selected, user, config)

    existing_table = extract_existing_table(content)
    if existing_table == table_html and not force_timestamp:
        return False

    timestamp = (now or datetime.now(UTC)).strftime("%Y-%m-%d %H:%M UTC")
    body = f"{table_html}\n\n> Auto-updated · {timestamp}"
    updated = replace_anchor_block(content, PROJECTS_START, PROJECTS_END, body)
    atomic_write_text(readme_path, updated)
    return True


def main() -> None:
    """命令行入口：拉取仓库信息并按需更新 README.md。"""
    user = os.environ.get("GH_USER", "yunyancuo").strip() or "yunyancuo"
    token = (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()
    force_timestamp = os.environ.get("FORCE_UPDATE_TIMESTAMP", "").strip() == "1"

    config = load_config(DEFAULT_CONFIG_PATH)
    repos = fetch_all_repositories(user, token, config)
    selected = select_repositories(repos, user, config)
    changed = update_readme_projects(
        DEFAULT_README_PATH,
        selected,
        user,
        config,
        force_timestamp=force_timestamp,
    )
    if changed:
        print("Projects card grid updated.")
    else:
        print("Projects card grid unchanged; skipped timestamp rewrite.")


if __name__ == "__main__":
    main()
