#!/usr/bin/env python3
"""网易云音乐本地扫码登录工具。

用法：``python scripts/qr_login.py``
自动拉起本地 NeteaseCloudMusicApi 服务生成登录二维码，扫码确认后将 Cookie
安全写入本地 ``netease_cookie.txt``（已被 .gitignore 忽略），不在终端回显明文凭据。
"""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from _common import atomic_write_bytes, atomic_write_text  # noqa: E402

API = "http://127.0.0.1:3000"
COOKIE_OUTPUT = Path("netease_cookie.txt")
QR_IMAGE_OUTPUT = Path("netease_qr.png")
MAX_QR_ROUNDS = 3
POLL_STEPS_PER_ROUND = 60
POLL_INTERVAL_SECONDS = 2.0

# NeteaseCloudMusicApi 二维码检测状态码
QR_EXPIRED = 800
QR_WAITING_SCAN = 801
QR_WAITING_CONFIRM = 802
QR_AUTHORIZED = 803


def _with_timestamp(path: str) -> str:
    """追加毫秒时间戳参数，避免本地 API 缓存二维码检查结果。"""
    separator = "&" if "?" in path else "?"
    return f"{path}{separator}timestamp={int(time.time() * 1000)}"


def api(path: str, *, base_url: str = API, timeout: float = 30.0) -> dict[str, Any]:
    """调用本地 NeteaseCloudMusicApi 接口并返回 JSON 响应。"""
    req = urllib.request.Request(
        f"{base_url}{_with_timestamp(path)}",
        headers={"User-Agent": "Mozilla/5.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.load(response)
    except Exception as err:
        return {"code": -1, "message": str(err)}


def is_api_ready(*, base_url: str = API, timeout: float = 2.0) -> bool:
    """探测本地 NeteaseCloudMusicApi 是否已就绪。"""
    try:
        with urllib.request.urlopen(f"{base_url}/", timeout=timeout):
            return True
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def start_api_server() -> subprocess.Popen[bytes] | None:
    """按需启动本地 NeteaseCloudMusicApi 进程；若端口已就绪则复用现有实例。"""
    if is_api_ready():
        return None
    npx_bin = shutil.which("npx")
    if not npx_bin:
        raise RuntimeError("未找到 npx，请先安装 Node.js（用于启动 NeteaseCloudMusicApi）。")
    print("正在启动本地 NeteaseCloudMusicApi...")
    proc = subprocess.Popen(
        [npx_bin, "--yes", "NeteaseCloudMusicApi@4.32.0"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(25):
        if is_api_ready():
            return proc
        time.sleep(2)
    proc.terminate()
    raise RuntimeError("NeteaseCloudMusicApi 启动超时，请检查本机网络与 Node.js 环境。")


def save_qr_image(qrimg_data_url: str, output_path: Path = QR_IMAGE_OUTPUT) -> bool:
    """将 data URL 格式的二维码 PNG 解码保存为本地图片文件，便于扫码。"""
    if not qrimg_data_url.startswith("data:image/"):
        return False
    _, _, encoded = qrimg_data_url.partition(",")
    if not encoded:
        return False
    atomic_write_bytes(output_path, base64.b64decode(encoded))
    return True


def render_terminal_qr(qr_url: str) -> bool:
    """如本地已安装 qrcode 库，直接在终端渲染 ASCII 二维码。"""
    try:
        import qrcode  # type: ignore[import-not-found]
    except ImportError:
        return False
    qr = qrcode.QRCode(border=1)
    qr.add_data(qr_url)
    qr.make(fit=True)
    qr.print_ascii(invert=True)
    return True


def save_cookie_securely(cookie: str, output_path: Path = COOKIE_OUTPUT) -> Path:
    """以原子方式保存 Cookie（类 Unix 系统限制为 0600 权限）。"""
    atomic_write_text(output_path, cookie.strip() + "\n", mode=0o600)
    return output_path


def run_qr_login(
    *,
    output_path: Path = COOKIE_OUTPUT,
    qr_image_path: Path = QR_IMAGE_OUTPUT,
    max_rounds: int = MAX_QR_ROUNDS,
    poll_steps: int = POLL_STEPS_PER_ROUND,
    poll_interval: float = POLL_INTERVAL_SECONDS,
) -> str | None:
    """执行二维码申请与状态轮询，登录成功后安全落盘 Cookie 并返回。"""
    for round_idx in range(1, max_rounds + 1):
        key_resp = api("/login/qr/key")
        unikey = (key_resp.get("data") or {}).get("unikey")
        if not unikey:
            print(f"获取二维码 Key 失败：{key_resp.get('message') or key_resp}")
            return None

        encoded_key = urllib.parse.quote(str(unikey), safe="")
        qr_resp = api(f"/login/qr/create?key={encoded_key}&qrimg=true")
        qr_data = qr_resp.get("data") or {}
        qr_url = str(qr_data.get("qrurl") or "")
        qr_img = str(qr_data.get("qrimg") or "")
        if not qr_url and not qr_img:
            print(f"生成二维码失败：{qr_resp.get('message') or qr_resp}")
            return None

        print(f"\n[第 {round_idx}/{max_rounds} 轮] 请使用网易云音乐 App 扫描二维码：")
        if qr_url and not render_terminal_qr(qr_url):
            print(f"  二维码内容链接：{qr_url}")
            print("  提示：安装 `pip install qrcode` 可直接在终端显示二维码。")
        if qr_img and save_qr_image(qr_img, qr_image_path):
            print(f"  二维码图片已保存到：{qr_image_path}（扫码完成后会自动删除）")

        print(f"等待扫码确认（本轮超时 {int(poll_steps * poll_interval)} 秒）...")

        expired = False
        for step in range(poll_steps):
            check = api(f"/login/qr/check?key={encoded_key}")
            code = check.get("code", -1)
            elapsed = int(step * poll_interval)
            if code == QR_WAITING_SCAN:
                print(f"  [{elapsed}s] 等待扫码...")
            elif code == QR_WAITING_CONFIRM:
                print(f"  [{elapsed}s] 已扫码，请在手机端点击确认登录...")
            elif code == QR_AUTHORIZED:
                cookie = str(check.get("cookie") or "").strip()
                if not cookie:
                    print("登录成功但响应中未包含 Cookie，请重试。")
                    return None
                saved_path = save_cookie_securely(cookie, output_path)
                print("\n登录成功！")
                print(
                    f"Cookie 已安全写入：{saved_path}"
                    f"（长度 {len(cookie)} 字符，不在终端打印明文）"
                )
                print("请将文件内容复制到 GitHub Secrets -> NETEASE_COOKIE，完成后删除该本地文件。")
                return cookie
            elif code == QR_EXPIRED:
                print(f"  [{elapsed}s] 二维码已过期，正在刷新二维码...")
                expired = True
                break
            else:
                print(f"  [{elapsed}s] 状态码 {code}: {check.get('message', 'unknown')}")
            time.sleep(poll_interval)

        if not expired:
            print("等待扫码超时，请重新运行脚本。")
            return None

    print("连续多轮二维码均已过期，请稍后重试。")
    return None


def main() -> None:
    """命令行入口：管理本地 API 进程生命周期并清理临时二维码图片。"""
    proc: subprocess.Popen[bytes] | None = None
    try:
        proc = start_api_server()
        run_qr_login()
    finally:
        if QR_IMAGE_OUTPUT.exists():
            QR_IMAGE_OUTPUT.unlink()
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    main()
