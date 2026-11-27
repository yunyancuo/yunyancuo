"""仓库结构完整性、README HTML 平衡性及 GitHub Actions YAML 合规性校验。"""

from __future__ import annotations

import json
from html.parser import HTMLParser
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
README_PATH = REPO_ROOT / "README.md"
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

# HTML5 标准自闭合空元素，无需闭合标签
VOID_HTML_TAGS = frozenset({"img", "br", "hr", "source", "meta", "link", "input"})


class _HTMLStructureValidator(HTMLParser):
    """校验 Markdown 中内嵌 HTML 标签的闭合平衡与 img alt 属性完整性。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, int]] = []
        self.errors: list[str] = []
        self.imgs_without_alt: list[int] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lower = tag.lower()
        line, _ = self.getpos()
        if lower == "img":
            attr_map = {k.lower(): (v or "").strip() for k, v in attrs}
            if not attr_map.get("alt"):
                self.imgs_without_alt.append(line)
        if lower not in VOID_HTML_TAGS:
            self.stack.append((lower, line))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lower = tag.lower()
        line, _ = self.getpos()
        if lower == "img":
            attr_map = {k.lower(): (v or "").strip() for k, v in attrs}
            if not attr_map.get("alt"):
                self.imgs_without_alt.append(line)

    def handle_endtag(self, tag: str) -> None:
        lower = tag.lower()
        if lower in VOID_HTML_TAGS:
            return
        line, _ = self.getpos()
        if not self.stack:
            self.errors.append(f"第 {line} 行出现多余闭合标签 </{lower}>")
            return
        open_tag, open_line = self.stack.pop()
        if open_tag != lower:
            self.errors.append(
                f"第 {line} 行闭合标签 </{lower}> 与第 {open_line} 行起始标签 <{open_tag}> 不匹配"
            )


def test_readme_anchors_and_visual_identity_intact() -> None:
    """README.md 必须保留唯一自动更新锚点以及作者的核心个性视觉元素。"""
    content = README_PATH.read_text(encoding="utf-8")

    for marker in (
        "<!-- PROJECTS:START -->",
        "<!-- PROJECTS:END -->",
        "<!-- NETEASE_BGM:START -->",
        "<!-- NETEASE_BGM:END -->",
    ):
        assert content.count(marker) == 1, f"锚点 {marker} 必须精确出现一次"

    for signature in (
        "Hello, I'm 云烟错",
        "assets/profile-title.svg",
        "assets/live-house-pixel.jpg",
        "assets/github-snake.svg",
        "Today's BGM",
        "有目的的人才会迷路，我只是来人间散步。",
    ):
        assert signature in content, f"缺少核心个人视觉元素：{signature}"


def test_readme_html_tags_balanced_and_images_have_alt() -> None:
    """README.md 中所有内嵌 HTML 标签必须严格平衡闭合，所有 img 均有 alt。"""
    content = README_PATH.read_text(encoding="utf-8")
    validator = _HTMLStructureValidator()
    validator.feed(content)
    validator.close()

    unclosed = [f"<{tag}> (第 {line} 行)" for tag, line in validator.stack]
    assert not validator.errors, f"HTML 标签闭合错误: {validator.errors}"
    assert not unclosed, f"存在未闭合 HTML 标签: {unclosed}"
    assert not validator.imgs_without_alt, (
        f"存在缺少 alt 属性的 <img>: {validator.imgs_without_alt}"
    )


def test_all_workflows_valid_yaml_and_hardened() -> None:
    """全部 GitHub Actions 工作流必须 YAML 合法、含权限声明、并发控制与超时限制。"""
    expected_workflows = {
        "generate-snake.yml",
        "update-net-ease-bgm.yml",
        "update-profile-cards.yml",
        "update-projects.yml",
        "ci.yml",
    }
    actual_files = {p.name for p in WORKFLOWS_DIR.glob("*.yml")}
    assert expected_workflows.issubset(actual_files)

    write_workflows = {
        "generate-snake.yml",
        "update-net-ease-bgm.yml",
        "update-profile-cards.yml",
        "update-projects.yml",
    }

    for wf_path in sorted(WORKFLOWS_DIR.glob("*.yml")):
        raw_text = wf_path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw_text)
        assert isinstance(data, dict), f"{wf_path.name} 解析结果必须为字典"
        # PyYAML 可能将无引号 `on` 解析为布尔 True
        assert "on" in data or True in data, f"{wf_path.name} 缺少触发器配置"
        assert "permissions" in data, f"{wf_path.name} 缺少显式 permissions 声明"
        assert "concurrency" in data, f"{wf_path.name} 缺少 concurrency 并发控制"

        jobs = data.get("jobs") or {}
        assert jobs, f"{wf_path.name} 至少需要定义一个 job"
        for job_name, job_cfg in jobs.items():
            assert "timeout-minutes" in job_cfg, (
                f"{wf_path.name} 的 job `{job_name}` 缺少 timeout-minutes"
            )

        if wf_path.name in write_workflows:
            assert "git pull --rebase" in raw_text, (
                f"写 main 分支的工作流 {wf_path.name} 必须使用 git pull --rebase 防推送竞态"
            )


def test_json_configs_valid_and_no_leaked_secrets() -> None:
    """校验 JSON 数据文件合法，且仓库中未包含本地 Cookie 或错误日志。"""
    for rel in ("player-data.json", "scripts/projects_config.json"):
        parsed = json.loads((REPO_ROOT / rel).read_text(encoding="utf-8"))
        assert isinstance(parsed, dict)

    for forbidden in ("netease_cookie.txt", "bgm-error.log", "netease_qr.png"):
        assert not (REPO_ROOT / forbidden).exists(), f"不应在仓库中提交敏感/临时文件：{forbidden}"
