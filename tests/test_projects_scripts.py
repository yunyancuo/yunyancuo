"""项目列表更新脚本（generate_projects.py 与 update_profile_projects.py）单元测试。"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from scripts import generate_projects, update_profile_projects


def test_render_card_escapes_html_markdown_and_unsafe_urls() -> None:
    """仓库名、描述、标签含恶意 HTML/Markdown 字符时应安全转义。"""
    config = generate_projects.load_config()
    repo = {
        "name": 'evil<img src=x onerror=alert(1)>|repo',
        "full_name": "yunyancuo/evil-repo",
        "owner": {"login": "yunyancuo"},
        "html_url": "javascript:alert(1)",
        "description": 'Hello </td><script>alert("x")</script> & a | b ' + "x" * 200,
        "language": 'Python`<script>',
    }
    card = generate_projects.render_card(repo, "yunyancuo", config)
    assert "<script>" not in card
    assert "</td><script>" not in card
    assert "javascript:" not in card
    assert "&lt;script&gt;" in card
    assert "\\|" in card
    assert "…" in card


def test_campus_tls_fix_and_multi_agent_metadata_config() -> None:
    """campus-tls-fix 与 multi-agent-study-notes 应使用统一的英文精选元数据。"""
    config = generate_projects.load_config()
    campus_repo = {
        "name": "campus-tls-fix",
        "full_name": "yunyancuo/campus-tls-fix",
        "owner": {"login": "yunyancuo"},
        "html_url": "https://github.com/yunyancuo/campus-tls-fix",
        "description": "超长中文原始描述...",
        "language": "PowerShell",
    }
    agent_repo = {
        "name": "multi-agent-study-notes",
        "full_name": "yunyancuo/multi-agent-study-notes",
        "owner": {"login": "yunyancuo"},
        "html_url": "https://github.com/yunyancuo/multi-agent-study-notes",
        "description": "raw desc",
        "language": "Markdown",
    }
    campus_card = generate_projects.render_card(campus_repo, "yunyancuo", config)
    agent_card = generate_projects.render_card(agent_repo, "yunyancuo", config)

    assert "Zero-dependency Windows .NET utility" in campus_card
    assert "`PowerShell` `.NET` `Networking`" in campus_card
    assert "multi-agent architectures" in agent_card
    assert "`Multi-Agent` `LLM` `Study Notes`" in agent_card


def test_select_repositories_filters_and_handles_none_pushed_at() -> None:
    """应过滤 private/fork/archived/excluded，并安全处理 pushed_at 为 None 的仓库。"""
    config = generate_projects.load_config()
    repos = [
        {"name": "yunyancuo", "pushed_at": "2026-11-27T00:00:00Z"},
        {"name": "private-repo", "private": True, "pushed_at": "2026-11-27T00:00:00Z"},
        {"name": "fork-repo", "fork": True, "pushed_at": "2026-11-27T00:00:00Z"},
        {"name": "archived-repo", "archived": True, "pushed_at": "2026-11-27T00:00:00Z"},
        {"name": "empty-repo", "pushed_at": None},
        {"name": "recent-repo", "pushed_at": "2026-11-26T00:00:00Z"},
        {"name": "velorag", "pushed_at": "2026-01-01T00:00:00Z"},
        {"name": "todotree", "pushed_at": "2026-01-01T00:00:00Z"},
    ]
    selected = generate_projects.select_repositories(repos, "yunyancuo", config)
    names = [item["name"] for item in selected]
    assert names == ["todotree", "velorag", "recent-repo", "empty-repo"]


def test_update_readme_projects_is_idempotent_without_content_change(tmp_path: Path) -> None:
    """项目表格内容未变化时，重复运行不应改写时间戳与文件。"""
    config = generate_projects.load_config()
    readme = tmp_path / "README.md"
    readme.write_text(
        "# Profile\n<!-- PROJECTS:START -->\nold\n<!-- PROJECTS:END -->\n",
        encoding="utf-8",
    )
    selected = [
        {
            "name": "velorag",
            "full_name": "yunyancuo/velorag",
            "owner": {"login": "yunyancuo"},
            "html_url": "https://github.com/yunyancuo/velorag",
            "description": "RAG framework",
            "language": "Python",
        }
    ]
    t1 = datetime(2026, 11, 27, 8, 0, tzinfo=UTC)
    t2 = datetime(2026, 11, 28, 8, 0, tzinfo=UTC)

    changed_first = generate_projects.update_readme_projects(
        readme, selected, "yunyancuo", config, now=t1
    )
    first_content = readme.read_text(encoding="utf-8")
    assert changed_first is True
    assert "2026-11-27 08:00 UTC" in first_content
    # 单个项目应自动补齐 More experiments 单元格保持双列平衡
    assert "More experiments" in first_content

    changed_second = generate_projects.update_readme_projects(
        readme, selected, "yunyancuo", config, now=t2
    )
    assert changed_second is False
    assert readme.read_text(encoding="utf-8") == first_content


def test_fetch_all_repositories_without_token_sends_no_authorization_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """未配置 Token 时拉取 GitHub API 不得携带 Authorization 请求头。"""
    captured_headers: list[dict[str, str]] = []

    def fake_request_json(url: str, headers: dict[str, str] | None = None, **_kwargs: Any) -> list:
        captured_headers.append(dict(headers or {}))
        return []

    monkeypatch.setattr(generate_projects, "request_json", fake_request_json)
    config = generate_projects.load_config()
    generate_projects.fetch_all_repositories("yunyancuo", "", config)

    assert captured_headers
    assert all("Authorization" not in hdr for hdr in captured_headers)


def test_legacy_update_profile_projects_no_empty_bearer_and_safe_escape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """兼容脚本 update_profile_projects.py 在无 Token 时不发空 Bearer 且转义注入。"""
    captured_headers: list[dict[str, str]] = []

    def fake_request_json(url: str, headers: dict[str, str] | None = None, **_kwargs: Any) -> list:
        captured_headers.append(dict(headers or {}))
        return [
            {
                "name": r"demo|repo\1",
                "html_url": "https://github.com/yunyancuo/demo",
                "description": r"<b>desc</b> | \g<0>",
                "language": "Python",
                "archived": False,
                "private": False,
            }
        ]

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(update_profile_projects, "request_json", fake_request_json)

    readme = tmp_path / "README.md"
    readme.write_text(
        "Header\n<!-- PROJECTS:START -->\nold\n<!-- PROJECTS:END -->\nFooter\n",
        encoding="utf-8",
    )
    update_profile_projects.main(readme_path=readme)

    assert len(captured_headers) == 1
    assert "Authorization" not in captured_headers[0]
    rendered = readme.read_text(encoding="utf-8")
    assert "&lt;b&gt;desc&lt;/b&gt;" in rendered
    assert r"\g&lt;0&gt;" in rendered
    assert r"demo\|repo\1" in rendered
