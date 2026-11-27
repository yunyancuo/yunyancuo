"""仓库自动化脚本共享工具模块。

提供安全 GitHub 请求头构造、带重试与脱敏的 HTTP JSON 请求、
文件原子写入、防注入锚点替换以及显示宽度截断等通用能力。
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable
from pathlib import Path
from typing import Any

DEFAULT_TIMEOUT = 30
DEFAULT_RETRIES = 3
DEFAULT_RETRY_DELAY = 2.0

# 匹配常见凭据模式的正则，用于日志与错误输出脱敏
_SENSITIVE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?i)(cookie=)[^&\s\"']+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(MUSIC_U=)[^;\s&\"']+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(__csrf=)[^;\s&\"']+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(csrf_token=)[^&\s\"']+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9._\-]+"), r"\1[REDACTED]"),
)


def build_github_headers(
    token: str | None = None,
    user_agent: str = "yunyancuo-profile-automation",
    api_version: str = "2022-11-28",
) -> dict[str, str]:
    """构造安全的 GitHub REST API 请求头。

    仅在提供非空 Token 时附带 Authorization 请求头，避免发送畸形的
    ``Authorization: Bearer `` 导致 GitHub API 返回 401。
    """
    headers: dict[str, str] = {
        "Accept": "application/vnd.github+json",
        "User-Agent": user_agent,
        "X-GitHub-Api-Version": api_version,
    }
    cleaned = (token or "").strip()
    if cleaned:
        headers["Authorization"] = f"Bearer {cleaned}"
    return headers


def sanitize_sensitive(text: str, secrets: Iterable[str] = ()) -> str:
    """对日志或错误消息执行敏感信息脱敏，避免 Cookie/Token 泄漏。"""
    result = str(text)
    for secret in secrets:
        cleaned = (secret or "").strip()
        if not cleaned:
            continue
        result = result.replace(cleaned, "[REDACTED]")
        quoted = urllib.parse.quote(cleaned, safe="")
        if quoted and quoted != cleaned:
            result = result.replace(quoted, "[REDACTED]")
    for pattern, repl in _SENSITIVE_PATTERNS:
        result = pattern.sub(repl, result)
    return result


def request_json(
    url: str,
    headers: dict[str, str] | None = None,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    retries: int = DEFAULT_RETRIES,
    retry_delay: float = DEFAULT_RETRY_DELAY,
    secrets: Iterable[str] = (),
) -> Any:
    """发送 HTTP GET 请求并解析 JSON，内置指数退避重试与错误脱敏。"""
    req_headers = dict(headers or {})
    secret_list = tuple(secrets)
    last_error: Exception | None = None

    for attempt in range(1, max(1, retries) + 1):
        request = urllib.request.Request(url, headers=req_headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as err:
            body = ""
            try:
                body = err.read().decode("utf-8", errors="replace")[:300]
            except Exception:
                body = ""
            safe_url = sanitize_sensitive(url, secret_list)
            safe_body = sanitize_sensitive(body or str(err.reason), secret_list)
            last_error = RuntimeError(f"HTTP {err.code} ({safe_url}): {safe_body}")
            # 4xx（除 429 限流外）通常不可重试，直接抛出减少无效等待
            if 400 <= err.code < 500 and err.code != 429:
                raise last_error from err
        except Exception as err:
            safe_msg = sanitize_sensitive(str(err), secret_list)
            last_error = RuntimeError(safe_msg)

        if attempt < retries:
            wait_seconds = retry_delay * attempt
            print(
                f"[retry {attempt}/{retries}] 请求失败 ({last_error})，"
                f"{wait_seconds:.1f}s 后重试..."
            )
            time.sleep(wait_seconds)

    assert last_error is not None
    raise last_error


def atomic_write_bytes(path: str | Path, data: bytes, *, mode: int | None = None) -> None:
    """以临时文件 + os.replace 方式原子写入二进制文件。"""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(target.parent),
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None and os.name != "nt":
            os.chmod(tmp_path, mode)
        os.replace(tmp_path, target)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def atomic_write_text(
    path: str | Path,
    content: str,
    *,
    encoding: str = "utf-8",
    newline: str = "\n",
    mode: int | None = None,
) -> None:
    """以原子方式写入 UTF-8 文本并统一换行符。"""
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    if newline != "\n":
        normalized = normalized.replace("\n", newline)
    atomic_write_bytes(path, normalized.encode(encoding), mode=mode)


def replace_anchor_block(
    content: str,
    start_marker: str,
    end_marker: str,
    replacement_body: str,
) -> str:
    """安全替换一对 HTML 注释锚点之间的内容。

    特性：
    - 校验锚点在文档中精确存在且仅出现一次；
    - 使用回调函数替换，彻底防止替换文本中含 ``\\1``、``\\g<0>`` 等序列引发正则注入。
    """
    pattern = re.compile(
        re.escape(start_marker) + r".*?" + re.escape(end_marker),
        flags=re.DOTALL,
    )
    block = f"{start_marker}\n{replacement_body}\n{end_marker}"
    updated, count = pattern.subn(lambda _match: block, content)
    if count != 1:
        raise RuntimeError(
            f"文档中必须存在唯一的锚点区块：{start_marker} ... {end_marker}"
            f"（当前匹配 {count} 处）。"
        )
    return updated


def sanitize_url(url: str, allowed_schemes: tuple[str, ...] = ("https", "http")) -> str:
    """校验 URL 仅使用允许的安全协议，防止 javascript: 等非法协议注入。"""
    cleaned = (url or "").strip()
    if not cleaned:
        return ""
    parsed = urllib.parse.urlparse(cleaned)
    if parsed.scheme.lower() not in allowed_schemes:
        return ""
    return cleaned


def _char_display_width(ch: str) -> int:
    """计算单个字符的近似终端/卡片显示宽度（东亚宽字符计为 2）。"""
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def truncate_display_width(text: str, max_width: int = 120) -> str:
    """按中英文视觉宽度优雅截断字符串，超出部分使用省略号代替。"""
    collapsed = " ".join((text or "").split())
    if not collapsed:
        return ""
    total_width = sum(_char_display_width(ch) for ch in collapsed)
    if total_width <= max_width:
        return collapsed

    budget = max(1, max_width - 1)
    acc: list[str] = []
    width = 0
    for ch in collapsed:
        ch_w = _char_display_width(ch)
        if width + ch_w > budget:
            break
        acc.append(ch)
        width += ch_w

    truncated = "".join(acc).rstrip()
    # 英文文本尽量在空格边界截断，避免截断单词中间
    if " " in truncated and all(ord(c) < 128 for c in truncated[-6:]):
        candidate = truncated.rsplit(" ", 1)[0].rstrip(" ,;:-—–")
        if len(candidate) >= len(truncated) * 0.65:
            truncated = candidate
    return f"{truncated.rstrip(' ,;:-—–')}…"
