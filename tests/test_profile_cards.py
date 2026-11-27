"""scripts/generate_profile_cards.py 的 SVG 生成、转义与布局单元测试。"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

import pytest

from scripts import generate_profile_cards


def test_build_stats_svg_valid_xml_and_escapes_special_chars() -> None:
    """统计卡片必须输出严格合法 XML 且对用户名中的特殊字符进行转义。"""
    svg = generate_profile_cards.build_stats_svg(
        user={"followers": 42},
        repos=[{"stargazers_count": 3}, {"stargazers_count": 7}],
        username='yun&<yan>"cuo\'',
    )
    root = ET.fromstring(svg)
    assert root.tag.endswith("svg")
    assert "&amp;&lt;yan&gt;&quot;cuo&#x27;" in svg
    assert ">10<" in svg
    assert ">42<" in svg
    assert ">2<" in svg


def test_build_languages_svg_valid_xml_no_bar_overflow_and_non_overlapping_legend() -> None:
    """Top Languages SVG 必须通过 XML 校验，进度条不溢出且三列图例固定不重叠。"""
    svg = generate_profile_cards.build_languages_svg(
        {
            "Python": 80000,
            'C++ & <"Test">': 15000,
            "Jupyter Notebook": 5000,
            "Shell": 1000,
        }
    )
    root = ET.fromstring(svg)
    ns = {"svg": "http://www.w3.org/2000/svg"}

    # 检查进度条各段总宽度不超过背景条 447px
    bar_group = root.find(".//svg:g[@clip-path='url(#lang-bar-clip)']", ns)
    assert bar_group is not None
    rects = bar_group.findall("svg:rect", ns)
    total_width = sum(int(rect.attrib["width"]) for rect in rects)
    assert 0 < total_width <= generate_profile_cards.BAR_TOTAL_WIDTH

    # 检查图例圆点位于三列固定等距坐标，绝不重叠
    circles = root.findall("svg:circle", ns)
    cx_values = [int(circle.attrib["cx"]) for circle in circles]
    assert cx_values == [30, 180, 330]
    assert "&amp;" in svg
    assert "<\"Test\">" not in svg


def test_collect_language_counts_tolerates_single_repo_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """单个仓库语言接口报错时，应记录告警并继续汇总其他仓库数据。"""

    def fake_get_json(path: str, **_kwargs: Any) -> dict[str, int]:
        if "broken" in path:
            raise RuntimeError("rate limit")
        return {"Python": 500, "TypeScript": 200}

    monkeypatch.setattr(generate_profile_cards, "get_json", fake_get_json)
    counts = generate_profile_cards.collect_language_counts(
        [
            {"name": "broken", "full_name": "yunyancuo/broken"},
            {"name": "good", "full_name": "yunyancuo/good"},
        ]
    )
    assert counts == {"Python": 500, "TypeScript": 200}


def test_get_json_omits_authorization_when_no_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """未设置 GITHUB_TOKEN 时不应传递空的 Authorization 头。"""
    captured: list[dict[str, str]] = []

    def fake_request_json(url: str, headers: dict[str, str] | None = None, **_kwargs: Any) -> dict:
        captured.append(dict(headers or {}))
        return {}

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(generate_profile_cards, "request_json", fake_request_json)
    generate_profile_cards.get_json("/users/yunyancuo")
    assert captured and "Authorization" not in captured[0]
