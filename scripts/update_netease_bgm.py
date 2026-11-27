"""同步网易云音乐「喜欢的音乐」最新一首歌曲到 README.md 与 player-data.json。

通过官方接口或本地 NeteaseCloudMusicApi 代理拉取最新收藏曲目，下载封面到本地
``assets/bgm-cover.*``，并对所有异常日志严格脱敏，避免 Cookie 泄漏。
"""

from __future__ import annotations

import html
import json
import os
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

from _common import (  # noqa: E402
    atomic_write_bytes,
    atomic_write_text,
    replace_anchor_block,
    sanitize_sensitive,
    sanitize_url,
)

ROOT = _SCRIPTS_DIR.parent
DEFAULT_UID = "1591928592"
DEFAULT_API_BASE = "https://music.163.com"
README_PATH = Path("README.md")
ERROR_LOG_PATH = Path("bgm-error.log")
PLAYER_DATA_PATH = Path("player-data.json")
ASSETS_DIR = Path("assets")
BGM_START = "<!-- NETEASE_BGM:START -->"
BGM_END = "<!-- NETEASE_BGM:END -->"


def load_env_config() -> tuple[str, str, str]:
    """在运行时读取网易云同步所需的环境变量配置。"""
    uid = os.environ.get("NETEASE_UID", DEFAULT_UID).strip() or DEFAULT_UID
    cookie = os.environ.get("NETEASE_COOKIE", "").strip()
    api_base = os.environ.get("NETEASE_API_BASE", DEFAULT_API_BASE).strip().rstrip("/")
    return uid, cookie, api_base or DEFAULT_API_BASE


def cookie_value(cookie: str, name: str) -> str:
    """从标准 Cookie 串中提取指定键的值。"""
    prefix = f"{name}="
    for part in cookie.split(";"):
        cleaned = part.strip()
        if cleaned.startswith(prefix):
            return cleaned[len(prefix) :]
    return ""


def request_json(
    path: str,
    *,
    cookie: str,
    api_base: str,
    retries: int = 3,
    delay: float = 3.0,
) -> dict[str, Any]:
    """向网易云接口或本地代理发起带重试的 JSON 请求，错误消息自动脱敏。"""
    base_path = path
    if api_base != DEFAULT_API_BASE:
        separator = "&" if "?" in base_path else "?"
        base_path = f"{base_path}{separator}cookie={urllib.parse.quote(cookie)}"
    csrf = cookie_value(cookie, "__csrf")
    if csrf and api_base == DEFAULT_API_BASE:
        separator = "&" if "?" in base_path else "?"
        base_path = f"{base_path}{separator}csrf_token={urllib.parse.quote(csrf)}"

    secrets = (cookie, csrf) if csrf else (cookie,)
    last_error: Exception | None = None

    for attempt in range(1, max(1, retries) + 1):
        req_path = base_path
        if attempt > 1 and api_base != DEFAULT_API_BASE:
            sep = "&" if "?" in req_path else "?"
            req_path = f"{req_path}{sep}timestamp={int(time.time() * 1000)}"
        request = urllib.request.Request(
            f"{api_base}{req_path}",
            headers={
                "Cookie": cookie,
                "User-Agent": "Mozilla/5.0 GitHub Actions",
                "Referer": "https://music.163.com/",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                result = json.load(response)
            if result.get("code") != 200:
                msg = result.get("msg") or result.get("message") or "未知错误"
                safe_msg = sanitize_sensitive(str(msg), secrets)
                raise RuntimeError(f"网易云接口返回 code={result.get('code')}: {safe_msg}")
            return result
        except urllib.error.HTTPError as err:
            body = ""
            try:
                body = err.read().decode("utf-8", errors="replace")[:300]
            except Exception:
                body = ""
            safe_detail = sanitize_sensitive(body or str(err.reason), secrets)
            last_error = RuntimeError(f"HTTP {err.code} ({path}): {safe_detail}")
        except Exception as err:
            last_error = RuntimeError(sanitize_sensitive(str(err), secrets))

        if attempt < retries:
            print(
                f"[retry {attempt}/{retries}] 请求 {path} 失败 ({last_error})，"
                f"{delay}s 后重试..."
            )
            time.sleep(delay)

    assert last_error is not None
    raise last_error


def download_cover(
    url: str,
    *,
    assets_dir: Path = ASSETS_DIR,
    retries: int = 3,
    delay: float = 2.0,
) -> str:
    """将专辑封面下载并原子落盘到仓库本地，规避 126.net CDN 在 GitHub camo 下超时。"""
    safe_url = sanitize_url(url)
    if not safe_url:
        raise ValueError("封面 URL 协议不合法或为空")

    last_error: Exception | None = None
    data = b""
    content_type = ""
    for attempt in range(1, max(1, retries) + 1):
        request = urllib.request.Request(
            safe_url,
            headers={"User-Agent": "Mozilla/5.0 GitHub Actions"},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                data = response.read()
                content_type = response.headers.get("Content-Type", "")
            if not data:
                raise RuntimeError("下载的封面文件内容为空")
            break
        except Exception as err:
            last_error = err
            if attempt < retries:
                time.sleep(delay)
    else:
        assert last_error is not None
        raise last_error

    ext = ".png" if "png" in content_type.lower() else ".jpg"
    assets_dir.mkdir(parents=True, exist_ok=True)
    target = assets_dir / f"bgm-cover{ext}"
    atomic_write_bytes(target, data)

    # 先确保新封面写入成功，再移除旧后缀文件，防止下载异常造成封面丢失
    for candidate_name in ("bgm-cover.jpg", "bgm-cover.png"):
        candidate = assets_dir / candidate_name
        if candidate != target and candidate.exists():
            candidate.unlink()

    return target.as_posix()


def render_bgm_html(
    *,
    title: str,
    artists: str,
    song_url: str,
    cover_src: str = "",
) -> str:
    """安全渲染 Today's BGM 的 HTML 片段，彻底转义歌名、歌手与链接属性。"""
    safe_title = html.escape(title or "未知歌曲", quote=True)
    safe_artists = html.escape(artists or "未知歌手", quote=True)
    safe_song_url = html.escape(sanitize_url(song_url) or "https://music.163.com/", quote=True)

    if cover_src:
        safe_cover_src = html.escape(cover_src, quote=True)
        return (
            f'<a href="{safe_song_url}"><img src="{safe_cover_src}" '
            f'width="180" alt="{safe_title} cover"></a><br><br>'
            f"🎵 <strong>{safe_title}</strong><br>"
            f"🎼 {safe_artists}<br>"
            f'<a href="{safe_song_url}">▶ Play on NetEase Music</a>'
        )
    return (
        f'🎵 <a href="{safe_song_url}"><strong>{safe_title}</strong></a> · {safe_artists}'
    )


def update_bgm_files(
    *,
    song: dict[str, Any],
    audio_url: str,
    local_cover: str,
    readme_path: Path = README_PATH,
    player_data_path: Path = PLAYER_DATA_PATH,
) -> dict[str, Any]:
    """根据曲目数据原子更新 README.md 与 player-data.json。"""
    raw_name = str(song.get("name") or "未知歌曲")
    artist_list = [
        str(artist.get("name") or "未知歌手")
        for artist in (song.get("ar") or [])
        if isinstance(artist, dict)
    ]
    artists = "、".join(artist_list) or "未知歌手"
    song_id = song.get("id", "")
    song_url = f"https://music.163.com/#/song?id={song_id}"
    cover_url = ((song.get("al") or {}).get("picUrl") or "").replace("http://", "https://")
    img_src = local_cover or cover_url

    replacement = render_bgm_html(
        title=raw_name,
        artists=artists,
        song_url=song_url,
        cover_src=img_src,
    )

    content = readme_path.read_text(encoding="utf-8")
    updated = replace_anchor_block(content, BGM_START, BGM_END, replacement)
    atomic_write_text(readme_path, updated)

    payload = {
        "title": raw_name,
        "artist": artists,
        "url": song_url,
        "coverUrl": cover_url,
        "audioUrl": audio_url or None,
    }
    atomic_write_text(
        player_data_path,
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    )
    return payload


def main(
    *,
    readme_path: Path = README_PATH,
    player_data_path: Path = PLAYER_DATA_PATH,
    assets_dir: Path = ASSETS_DIR,
) -> dict[str, Any]:
    """拉取最新收藏曲目并更新 README 与播放器数据。"""
    uid, cookie, api_base = load_env_config()
    if not cookie:
        raise RuntimeError(
            "缺少 NETEASE_COOKIE。请在 GitHub 仓库 Settings > "
            "Secrets and variables > Actions 中添加它。"
        )

    playlist_path = "/api/user/playlist" if api_base == DEFAULT_API_BASE else "/user/playlist"
    playlists = request_json(
        f"{playlist_path}?uid={uid}&limit=1000&offset=0",
        cookie=cookie,
        api_base=api_base,
    ).get("playlist", [])
    liked = next((item for item in playlists if "喜欢的音乐" in item.get("name", "")), None)
    if not liked:
        raise RuntimeError(
            f"找不到用户 {uid} 的“喜欢的音乐”歌单，请确认 UID 和 Cookie 属于同一个账号。"
        )

    if api_base == DEFAULT_API_BASE:
        detail = request_json(
            f"/api/playlist/detail?id={liked['id']}&s=0",
            cookie=cookie,
            api_base=api_base,
        )
        tracks = (detail.get("playlist") or {}).get("tracks", [])
    else:
        try:
            tracks = request_json(
                f"/playlist/track/all?id={liked['id']}&limit=1&offset=0",
                cookie=cookie,
                api_base=api_base,
            ).get("songs", [])
        except Exception as err:
            print(f"/playlist/track/all 失败 ({err})，回退至 /playlist/detail...")
            detail = request_json(
                f"/playlist/detail?id={liked['id']}",
                cookie=cookie,
                api_base=api_base,
            )
            tracks = (detail.get("playlist") or {}).get("tracks", [])

    if not tracks:
        raise RuntimeError("“喜欢的音乐”歌单为空，或网易云没有返回歌曲数据。")

    song = tracks[0]
    cover_url = ((song.get("al") or {}).get("picUrl") or "").replace("http://", "https://")
    audio_url = ""
    try:
        audio = request_json(
            f"/song/url?id={song['id']}&br=320000",
            cookie=cookie,
            api_base=api_base,
        ).get("data", [])
        raw_audio_url = ((audio[0] or {}).get("url") or "") if audio else ""
        audio_url = str(raw_audio_url).replace("http://", "https://")
    except Exception:
        audio_url = ""

    local_cover = ""
    if cover_url:
        try:
            local_cover = download_cover(cover_url, assets_dir=assets_dir)
        except Exception as err:
            print(f"封面下载失败，回退到网易云外链: {err}")

    payload = update_bgm_files(
        song=song,
        audio_url=audio_url,
        local_cover=local_cover,
        readme_path=readme_path,
        player_data_path=player_data_path,
    )
    print(f"已更新 BGM: {payload['title']} - {payload['artist']}")
    return payload


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        _, active_cookie, _ = load_env_config()
        safe_error = sanitize_sensitive(str(exc), (active_cookie,) if active_cookie else ())
        atomic_write_text(ERROR_LOG_PATH, safe_error + "\n")
        raise RuntimeError(safe_error) from None
