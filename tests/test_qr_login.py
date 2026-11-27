"""scripts/qr_login.py 的二维码状态机与隐私保护单元测试。"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import pytest

from scripts import qr_login


def test_qr_login_status_machine_handles_expiry_and_803_success_without_printing_cookie(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """验证 800 刷新、801 等待、802 待确认、803 授权成功并安全保存且不回显明文 Cookie。"""
    fake_png = base64.b64encode(b"\x89PNG-mock").decode("ascii")
    secret_cookie = "MUSIC_U=qr_secret_token_abcdefg123456; __csrf=xyz"
    responses = iter(
        [
            {"data": {"unikey": "key-round-1"}},
            {
                "data": {
                    "qrurl": "https://music.163.com/login?codekey=1",
                    "qrimg": f"data:image/png;base64,{fake_png}",
                }
            },
            {"code": qr_login.QR_WAITING_SCAN},
            {"code": qr_login.QR_EXPIRED},
            {"data": {"unikey": "key-round-2"}},
            {"data": {"qrurl": "https://music.163.com/login?codekey=2", "qrimg": ""}},
            {"code": qr_login.QR_WAITING_CONFIRM},
            {"code": qr_login.QR_AUTHORIZED, "cookie": secret_cookie},
        ]
    )

    called_paths: list[str] = []

    def fake_api(path: str, **_kwargs: Any) -> dict[str, Any]:
        called_paths.append(path)
        return next(responses)

    monkeypatch.setattr(qr_login, "api", fake_api)
    monkeypatch.setattr(qr_login, "render_terminal_qr", lambda _url: False)
    monkeypatch.setattr(qr_login.time, "sleep", lambda _sec: None)

    cookie_file = tmp_path / "netease_cookie.txt"
    qr_file = tmp_path / "netease_qr.png"
    result = qr_login.run_qr_login(
        output_path=cookie_file,
        qr_image_path=qr_file,
        max_rounds=2,
        poll_steps=5,
        poll_interval=0,
    )

    assert result == secret_cookie
    assert cookie_file.read_text(encoding="utf-8").strip() == secret_cookie
    assert qr_file.read_bytes() == b"\x89PNG-mock"

    # 确保终端输出绝不包含明文 Cookie
    stdout = capsys.readouterr().out
    assert "qr_secret_token_abcdefg123456" not in stdout
    assert "key-round-2" in called_paths[-1]
