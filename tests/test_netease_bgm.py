"""scripts/update_netease_bgm.py 的转义、幂等性、容错与日志脱敏单元测试。"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest

from scripts import update_netease_bgm


class _FakeHTTPResponse:
    """模拟 urllib urlopen 返回的上下文响应对象。"""

    def __init__(self, body: bytes, content_type: str = "image/jpeg") -> None:
        self._buf = io.BytesIO(body)
        self.headers = {"Content-Type": content_type}

    def read(self) -> bytes:
        return self._buf.read()

    def __enter__(self) -> _FakeHTTPResponse:
        return self

    def __exit__(self, *_args: Any) -> None:
        return None


def test_update_bgm_files_escapes_html_and_backreferences_idempotently(tmp_path: Path) -> None:
    """歌名/歌手含 HTML 特殊字符及 \\1 时应安全转义且重复执行幂等。"""
    readme = tmp_path / "README.md"
    player_data = tmp_path / "player-data.json"
    readme.write_text(
        "Intro\n<!-- NETEASE_BGM:START -->\nold\n<!-- NETEASE_BGM:END -->\nOutro\n",
        encoding="utf-8",
    )
    song = {
        "id": 123456,
        "name": r'<script>"Track" \1 & \g<0></script>',
        "ar": [{"name": 'Artist <A> & "B"'}],
        "al": {"picUrl": "http://p3.music.126.net/test.jpg"},
    }

    payload = update_netease_bgm.update_bgm_files(
        song=song,
        audio_url="",
        local_cover="assets/bgm-cover.jpg",
        readme_path=readme,
        player_data_path=player_data,
    )
    first_readme = readme.read_text(encoding="utf-8")
    assert "<script>" not in first_readme
    assert "&lt;script&gt;&quot;Track&quot;" in first_readme
    assert r"\1 &amp; \g&lt;0&gt;" in first_readme
    assert payload["audioUrl"] is None
    assert payload["coverUrl"] == "https://p3.music.126.net/test.jpg"

    saved_json = json.loads(player_data.read_text(encoding="utf-8"))
    assert saved_json["title"] == song["name"]
    assert player_data.read_text(encoding="utf-8").endswith("\n")

    # 幂等性校验
    update_netease_bgm.update_bgm_files(
        song=song,
        audio_url="",
        local_cover="assets/bgm-cover.jpg",
        readme_path=readme,
        player_data_path=player_data,
    )
    assert readme.read_text(encoding="utf-8") == first_readme


def test_main_handles_null_audio_and_null_cover_without_crashing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """当网易云返回 url=null、picUrl=null、ar=[] 时应优雅降级而非抛出 AttributeError。"""
    readme = tmp_path / "README.md"
    player_data = tmp_path / "player-data.json"
    readme.write_text(
        "<!-- NETEASE_BGM:START -->\nold\n<!-- NETEASE_BGM:END -->\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("NETEASE_UID", "1591928592")
    monkeypatch.setenv("NETEASE_COOKIE", "MUSIC_U=mock_cookie_val")
    monkeypatch.setenv("NETEASE_API_BASE", "http://127.0.0.1:3000")

    def fake_request_json(path: str, **_kwargs: Any) -> dict[str, Any]:
        if path.startswith("/user/playlist"):
            return {"code": 200, "playlist": [{"id": 99, "name": "我喜欢的音乐"}]}
        if path.startswith("/playlist/track/all"):
            return {
                "code": 200,
                "songs": [{"id": 777, "name": "Silent Song", "ar": [], "al": {"picUrl": None}}],
            }
        if path.startswith("/song/url"):
            return {"code": 200, "data": [{"url": None}]}
        raise AssertionError(f"Unexpected path: {path}")

    monkeypatch.setattr(update_netease_bgm, "request_json", fake_request_json)
    payload = update_netease_bgm.main(
        readme_path=readme,
        player_data_path=player_data,
        assets_dir=tmp_path / "assets",
    )
    assert payload["artist"] == "未知歌手"
    assert payload["audioUrl"] is None
    assert "Silent Song" in readme.read_text(encoding="utf-8")


def test_request_json_redacts_cookie_in_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """请求失败抛出的异常中绝不能泄漏真实 Cookie 内容。"""
    secret_cookie = "MUSIC_U=super_secret_cookie_999; __csrf=csrf_secret_888"

    def fake_urlopen(req: Any, timeout: float = 30) -> Any:
        raise RuntimeError(f"Connection error for {req.full_url}")

    monkeypatch.setattr(update_netease_bgm.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(RuntimeError) as exc_info:
        update_netease_bgm.request_json(
            "/user/playlist?uid=1",
            cookie=secret_cookie,
            api_base="http://127.0.0.1:3000",
            retries=1,
            delay=0,
        )
    message = str(exc_info.value)
    assert "super_secret_cookie_999" not in message
    assert "csrf_secret_888" not in message
    assert "[REDACTED]" in message


def test_download_cover_replaces_old_extension_atomically(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """下载 PNG 封面后应原子写出 bgm-cover.png 并自动移除旧的 bgm-cover.jpg。"""
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()
    old_jpg = assets_dir / "bgm-cover.jpg"
    old_jpg.write_bytes(b"old-jpg")

    def fake_urlopen(_req: Any, timeout: float = 30) -> _FakeHTTPResponse:
        return _FakeHTTPResponse(b"\x89PNG-fake-data", content_type="image/png")

    monkeypatch.setattr(update_netease_bgm.urllib.request, "urlopen", fake_urlopen)
    saved = update_netease_bgm.download_cover(
        "https://p3.music.126.net/cover.png",
        assets_dir=assets_dir,
        retries=1,
    )
    assert saved.endswith("bgm-cover.png")
    assert (assets_dir / "bgm-cover.png").read_bytes() == b"\x89PNG-fake-data"
    assert not old_jpg.exists()
