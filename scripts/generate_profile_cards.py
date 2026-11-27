"""生成 GitHub Profile 统计卡片与语言分布 SVG。

产出文件：
- ``assets/github-stats.svg``：公开仓库数、关注者与总 Star 数统计；
- ``assets/top-languages.svg``：Top 语言占比进度条与不重叠固定列图例。
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
    request_json,
)

USERNAME = "yunyancuo"
ORGS = ("Infinite-Monkey-Lab",)
MY_ORG_REPOS = frozenset({"todotree", "FeiyuCursor", "keresearch", "infinite-monkey-lab"})
ROOT = _SCRIPTS_DIR.parent
ASSETS = ROOT / "assets"

# 常见语言对应的 GitHub Linguist 风格配色
LANGUAGE_COLORS: dict[str, str] = {
    "Python": "#3572A5",
    "Jupyter Notebook": "#DA5B0B",
    "JavaScript": "#f1e05a",
    "TypeScript": "#3178c6",
    "Go": "#00ADD8",
    "PowerShell": "#012456",
    "HTML": "#e34c26",
    "CSS": "#563d7c",
    "Shell": "#89e051",
    "Vue": "#41b883",
    "Rust": "#dea584",
    "C++": "#f34b7d",
    "C#": "#178600",
    "Dockerfile": "#384d54",
}
DEFAULT_LANG_COLOR = "#8b8ba7"
BAR_X = 24
BAR_TOTAL_WIDTH = 447


def svg_escape(value: Any) -> str:
    """对 SVG 文本与属性值进行完整 XML/HTML 转义（含双引号与单引号）。"""
    return html.escape(str(value), quote=True)


def get_json(path: str, *, token: str | None = None, username: str = USERNAME) -> Any:
    """调用 GitHub REST API 并返回解析后的 JSON。"""
    resolved_token = (
        token if token is not None else (os.environ.get("GITHUB_TOKEN") or "")
    ).strip()
    headers = build_github_headers(token=resolved_token, user_agent=username)
    secrets = (resolved_token,) if resolved_token else ()
    return request_json(
        f"https://api.github.com{path}",
        headers=headers,
        secrets=secrets,
    )


def build_stats_svg(
    user: dict[str, Any],
    repos: list[dict[str, Any]],
    *,
    username: str = USERNAME,
) -> str:
    """构造 GitHub Stats SVG 字符串。"""
    stars = sum(int(repo.get("stargazers_count") or 0) for repo in repos)
    followers = int(user.get("followers") or 0)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="495" height="165" viewBox="0 0 495 165">\n'
        '  <rect width="495" height="165" rx="8" fill="#191724"/>\n'
        f'  <text x="24" y="34" fill="#ebbcba" font-family="sans-serif" '
        f'font-size="18" font-weight="bold">{svg_escape(username)}\'s GitHub Stats</text>\n'
        '  <text x="24" y="72" fill="#e0def4" font-family="sans-serif" font-size="15">'
        "Public Repos</text>\n"
        f'  <text x="24" y="98" fill="#ebbcba" font-family="sans-serif" '
        f'font-size="24" font-weight="bold">{len(repos)}</text>\n'
        '  <text x="170" y="72" fill="#e0def4" font-family="sans-serif" font-size="15">'
        "Followers</text>\n"
        f'  <text x="170" y="98" fill="#ebbcba" font-family="sans-serif" '
        f'font-size="24" font-weight="bold">{followers}</text>\n'
        '  <text x="316" y="72" fill="#e0def4" font-family="sans-serif" font-size="15">'
        "Total Stars</text>\n"
        f'  <text x="316" y="98" fill="#ebbcba" font-family="sans-serif" '
        f'font-size="24" font-weight="bold">{stars}</text>\n'
        '  <path d="M24 130h447" stroke="#6e6a86" stroke-width="1"/>\n'
        '  <text x="24" y="151" fill="#908caa" font-family="sans-serif" font-size="12">'
        "Auto-updated by GitHub Actions</text>\n"
        "</svg>\n"
    )


def _compute_bar_widths(top_items: list[tuple[str, int]], total: int) -> list[int]:
    """按比例计算进度条各段宽度，保证总宽严格不超过 BAR_TOTAL_WIDTH。"""
    if not top_items or total <= 0:
        return []
    widths: list[int] = []
    remaining = BAR_TOTAL_WIDTH
    for idx, (_lang, amount) in enumerate(top_items):
        if remaining <= 0:
            widths.append(0)
            continue
        raw_width = round(BAR_TOTAL_WIDTH * amount / total)
        # 为剩余其他段预留最小可视宽度，同时避免溢出总宽度
        reserve = max(0, (len(top_items) - idx - 1) * 8)
        capped = min(max(8, raw_width), max(0, remaining - reserve))
        widths.append(capped)
        remaining -= capped
    return widths


def build_languages_svg(counts: dict[str, int]) -> str:
    """构造 Top Languages SVG 字符串，使用圆角裁剪与等距列布局防止图例重叠。"""
    positive_counts = {lang: int(val) for lang, val in counts.items() if int(val) > 0}
    top = sorted(positive_counts.items(), key=lambda item: item[1], reverse=True)[:3]
    total = sum(positive_counts.values()) or 1
    widths = _compute_bar_widths(top, total)

    bars: list[str] = []
    x = BAR_X
    for (language, _amount), width in zip(top, widths, strict=True):
        if width <= 0:
            continue
        color = LANGUAGE_COLORS.get(language, DEFAULT_LANG_COLOR)
        bars.append(f'<rect x="{x}" y="58" width="{width}" height="16" fill="{color}"/>')
        x += width

    # 采用三列固定水平锚点，避免低占比语言导致图例重叠或超出右边界
    col_positions = (24, 174, 324)
    legend_parts: list[str] = []
    for idx, (language, amount) in enumerate(top):
        pos = col_positions[idx]
        color = LANGUAGE_COLORS.get(language, DEFAULT_LANG_COLOR)
        pct = amount * 100.0 / total
        label = language if len(language) <= 13 else f"{language[:12]}…"
        legend_parts.append(
            f'<circle cx="{pos + 6}" cy="103" r="6" fill="{color}"/>'
            f'<text x="{pos + 18}" y="107" fill="#e0def4" font-family="sans-serif" '
            f'font-size="12">{svg_escape(label)} {pct:.0f}%</text>'
        )

    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="495" height="165" viewBox="0 0 495 165">\n'
        "  <defs>\n"
        '    <clipPath id="lang-bar-clip">\n'
        f'      <rect x="{BAR_X}" y="58" width="{BAR_TOTAL_WIDTH}" height="16" rx="8"/>\n'
        "    </clipPath>\n"
        "  </defs>\n"
        '  <rect width="495" height="165" rx="8" fill="#191724"/>\n'
        '  <text x="24" y="34" fill="#ebbcba" font-family="sans-serif" '
        'font-size="18" font-weight="bold">Top Languages</text>\n'
        f'  <rect x="{BAR_X}" y="58" width="{BAR_TOTAL_WIDTH}" height="16" rx="8" '
        'fill="#403d52"/>\n'
        f'  <g clip-path="url(#lang-bar-clip)">{"".join(bars)}</g>\n'
        f"  {''.join(legend_parts)}\n"
        '  <text x="24" y="144" fill="#908caa" font-family="sans-serif" font-size="12">'
        "Auto-updated by GitHub Actions</text>\n"
        "</svg>\n"
    )


def collect_language_counts(
    repos: list[dict[str, Any]],
    *,
    token: str | None = None,
    username: str = USERNAME,
) -> dict[str, int]:
    """汇总全部仓库的语言字节统计，单个仓库拉取失败时记录警告并继续。"""
    counts: dict[str, int] = {}
    for repo in repos:
        full_name = repo.get("full_name", f"{username}/{repo['name']}")
        try:
            lang_map = get_json(f"/repos/{full_name}/languages", token=token, username=username)
        except Exception as err:
            print(f"Warning: failed to fetch languages for {full_name}: {err}")
            continue
        for language, amount in (lang_map or {}).items():
            counts[language] = counts.get(language, 0) + int(amount)
    return counts


def fetch_profile_data(
    *,
    username: str = USERNAME,
    orgs: tuple[str, ...] = ORGS,
    my_org_repos: frozenset[str] = MY_ORG_REPOS,
    token: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """获取用户信息与包含个人及组织精选项目的仓库列表。"""
    user = get_json(f"/users/{username}", token=token, username=username)
    repositories = list(
        get_json(f"/users/{username}/repos?per_page=100&type=owner", token=token, username=username)
    )
    seen = {repo["name"] for repo in repositories if repo.get("name")}
    for org in orgs:
        try:
            org_repos = get_json(
                f"/orgs/{org}/repos?per_page=100&type=public",
                token=token,
                username=username,
            )
            for repo in org_repos:
                name = repo.get("name")
                if name and name not in seen and name in my_org_repos and not repo.get("private"):
                    repositories.append(repo)
                    seen.add(name)
        except Exception as err:
            print(f"Warning: failed to fetch org {org}: {err}")
    return user, repositories


def write_stats(
    user: dict[str, Any],
    repos: list[dict[str, Any]],
    *,
    assets_dir: Path = ASSETS,
    username: str = USERNAME,
) -> Path:
    """原子写出 GitHub Stats SVG 文件。"""
    output = assets_dir / "github-stats.svg"
    atomic_write_text(output, build_stats_svg(user, repos, username=username))
    return output


def write_languages(
    repos: list[dict[str, Any]],
    *,
    assets_dir: Path = ASSETS,
    token: str | None = None,
    username: str = USERNAME,
) -> Path:
    """聚合语言字节数并原子写出 Top Languages SVG 文件。"""
    counts = collect_language_counts(repos, token=token, username=username)
    output = assets_dir / "top-languages.svg"
    atomic_write_text(output, build_languages_svg(counts))
    return output


def main() -> None:
    """命令行入口：拉取统计数据并更新本地 SVG 卡片。"""
    username = os.environ.get("GH_USER", USERNAME).strip() or USERNAME
    token = (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()
    user, repositories = fetch_profile_data(username=username, token=token)
    write_stats(user, repositories, assets_dir=ASSETS, username=username)
    write_languages(repositories, assets_dir=ASSETS, token=token, username=username)
    print("Profile SVG cards updated.")


if __name__ == "__main__":
    main()
