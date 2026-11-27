"""早期 Markdown 表格版项目列表更新脚本（保留向后兼容）。

说明：当前 GitHub Actions 主工作流 ``.github/workflows/update-projects.yml`` 已迁移至
``scripts/generate_projects.py``（双列视觉卡片网格）。本脚本予以保留并修复空 Token 401、
文本转义、锚点安全替换与原子写入问题，供需要精简 Markdown 表格视图的场景兼容使用。
"""

from __future__ import annotations

import html
import os
import sys
from pathlib import Path
from typing import Any

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

USERNAME = "yunyancuo"
README = Path("README.md")
PROJECTS_START = "<!-- PROJECTS:START -->"
PROJECTS_END = "<!-- PROJECTS:END -->"

LANGUAGE_ICONS: dict[str, str] = {
    "Python": "🐍",
    "JavaScript": "🟨",
    "TypeScript": "🔷",
    "Jupyter Notebook": "📚",
    "Vue": "💚",
    "PowerShell": "🛠️",
    "Go": "🐹",
}


def get_repositories(
    *,
    username: str = USERNAME,
    token: str | None = None,
) -> list[dict[str, Any]]:
    """拉取指定用户的公开仓库列表，未配置 Token 时不发送畸形空 Authorization 头。"""
    resolved_token = (
        token if token is not None else (os.environ.get("GITHUB_TOKEN") or "")
    ).strip()
    headers = build_github_headers(token=resolved_token, user_agent=username)
    secrets = (resolved_token,) if resolved_token else ()
    result = request_json(
        f"https://api.github.com/users/{username}/repos?per_page=100&type=owner&sort=pushed",
        headers=headers,
        secrets=secrets,
    )
    return list(result)


def clean(value: str | None, *, max_width: int = 120) -> str:
    """清洗并截断仓库描述，防止 Markdown 表格或 HTML 标签注入。"""
    text = truncate_display_width(value or "暂无简介", max_width=max_width)
    return html.escape(text, quote=True).replace("|", "\\|")


def build_markdown_table(
    repositories: list[dict[str, Any]],
    *,
    username: str = USERNAME,
    limit: int = 6,
) -> str:
    """将仓库列表渲染为安全转义的 Markdown 表格。"""
    filtered = [
        repo
        for repo in repositories
        if repo.get("name") != username
        and not repo.get("archived")
        and not repo.get("private")
    ][:limit]

    rows = ["| 项目 | 简介 |", "| --- | --- |"]
    for repo in filtered:
        icon = LANGUAGE_ICONS.get(str(repo.get("language") or ""), "✨")
        raw_name = str(repo.get("name") or "")
        safe_name = (
            html.escape(raw_name, quote=True)
            .replace("|", "\\|")
            .replace("[", "\\[")
            .replace("]", "\\]")
        )
        safe_url = sanitize_url(str(repo.get("html_url") or "")) or f"https://github.com/{username}"
        rows.append(f"| [{icon} {safe_name}]({safe_url}) | {clean(repo.get('description'))} |")
    return "\n".join(rows)


def main(
    *,
    readme_path: Path = README,
    username: str = USERNAME,
    token: str | None = None,
) -> None:
    """拉取仓库并以原子方式替换 README.md 中的 PROJECTS 锚点区块。"""
    repositories = get_repositories(username=username, token=token)
    table = build_markdown_table(repositories, username=username)
    content = readme_path.read_text(encoding="utf-8")
    updated = replace_anchor_block(content, PROJECTS_START, PROJECTS_END, table)
    atomic_write_text(readme_path, updated)
    print("Projects markdown table updated.")


if __name__ == "__main__":
    main()
