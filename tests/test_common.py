"""scripts._common 共享基础设施模块的单元测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts._common import (
    atomic_write_bytes,
    atomic_write_text,
    build_github_headers,
    replace_anchor_block,
    sanitize_sensitive,
    sanitize_url,
    truncate_display_width,
)


@pytest.mark.parametrize("token", [None, "", "   ", "\t\n"])
def test_build_github_headers_omits_authorization_when_token_empty(token: str | None) -> None:
    """未提供 Token 或仅为空白时，绝不能附带畸形 Authorization 请求头。"""
    headers = build_github_headers(token=token, user_agent="tester")
    assert "Authorization" not in headers
    assert headers["Accept"] == "application/vnd.github+json"
    assert headers["User-Agent"] == "tester"


def test_build_github_headers_strips_and_sets_bearer_token() -> None:
    """提供有效 Token 时应自动去除首尾空白并构造 Bearer 头。"""
    headers = build_github_headers(token="  ghp_example_token_123  ")
    assert headers["Authorization"] == "Bearer ghp_example_token_123"


def test_replace_anchor_block_handles_regex_backreferences_safely() -> None:
    """替换内容含 \\1、\\g<0> 等正则反向引用时不应崩溃或损坏内容。"""
    source = "top\n<!-- TAG:START -->\nold\n<!-- TAG:END -->\nbottom\n"
    payload = r"Song \1 & \g<0> \n end"
    updated = replace_anchor_block(source, "<!-- TAG:START -->", "<!-- TAG:END -->", payload)
    assert payload in updated
    # 再次使用相同内容替换应保持完全幂等
    second = replace_anchor_block(updated, "<!-- TAG:START -->", "<!-- TAG:END -->", payload)
    assert second == updated


def test_replace_anchor_block_requires_unique_markers() -> None:
    """缺少锚点或锚点重复出现时必须抛出 RuntimeError。"""
    with pytest.raises(RuntimeError):
        replace_anchor_block("no markers here", "<!-- A:START -->", "<!-- A:END -->", "body")

    duplicated = (
        "<!-- A:START -->\n1\n<!-- A:END -->\n"
        "<!-- A:START -->\n2\n<!-- A:END -->\n"
    )
    with pytest.raises(RuntimeError):
        replace_anchor_block(duplicated, "<!-- A:START -->", "<!-- A:END -->", "body")


def test_sanitize_sensitive_redacts_cookies_and_tokens() -> None:
    """脱敏函数应隐藏原始 Cookie、URL 编码 Cookie、MUSIC_U 与 Bearer Token。"""
    secret_cookie = "MUSIC_U=secret_value_abc; __csrf=csrf_999"
    raw_msg = (
        f"GET /user/playlist?cookie=MUSIC_U%3Dsecret_value_abc%3B%20__csrf%3Dcsrf_999 "
        f"failed with header Authorization: Bearer ghp_secret123 and {secret_cookie}"
    )
    sanitized = sanitize_sensitive(raw_msg, secrets=(secret_cookie,))
    assert "secret_value_abc" not in sanitized
    assert "csrf_999" not in sanitized
    assert "ghp_secret123" not in sanitized
    assert "[REDACTED]" in sanitized


def test_sanitize_url_blocks_unsafe_schemes() -> None:
    """仅允许 http/https 链接，拦截 javascript: / data: 等危险协议。"""
    assert sanitize_url("https://github.com/yunyancuo") == "https://github.com/yunyancuo"
    assert sanitize_url("javascript:alert(1)") == ""
    assert sanitize_url("data:text/html,<script>alert(1)</script>") == ""


def test_truncate_display_width_cjk_and_ascii() -> None:
    """中英文混排超长文本应按显示宽度截断并追加省略号。"""
    short = "Short description"
    assert truncate_display_width(short, max_width=40) == short

    long_cn = "这是一个非常非常长的中文项目介绍用来测试东亚全角字符显示宽度截断行为是否准确有效"
    truncated = truncate_display_width(long_cn, max_width=30)
    assert truncated.endswith("…")
    assert len(truncated) < len(long_cn)


def test_atomic_write_text_and_bytes(tmp_path: Path) -> None:
    """原子写入应规范换行符并确保不遗留临时文件。"""
    txt_file = tmp_path / "sample.txt"
    atomic_write_text(txt_file, "line1\r\nline2\r\n")
    assert txt_file.read_bytes() == b"line1\nline2\n"

    bin_file = tmp_path / "cover.bin"
    atomic_write_bytes(bin_file, b"\x89PNG\r\n")
    assert bin_file.read_bytes() == b"\x89PNG\r\n"
    assert not list(tmp_path.glob("*.tmp"))
