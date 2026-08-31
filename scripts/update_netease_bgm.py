import json
import os
import re
import html
import urllib.parse
import urllib.request


UID = os.environ.get("NETEASE_UID", "1591928592")
COOKIE = os.environ.get("NETEASE_COOKIE", "").strip()
API_BASE = os.environ.get("NETEASE_API_BASE", "https://music.163.com").rstrip("/")
README = "README.md"
ERROR_LOG = "bgm-error.log"
PLAYER_DATA = "player-data.json"


def cookie_value(name):
    prefix = f"{name}="
    for part in COOKIE.split(";"):
        part = part.strip()
        if part.startswith(prefix):
            return part[len(prefix):]
    return ""


def request_json(path):
    if API_BASE != "https://music.163.com":
        separator = "&" if "?" in path else "?"
        path = f"{path}{separator}cookie={urllib.parse.quote(COOKIE)}"
    csrf = cookie_value("__csrf")
    if csrf and API_BASE == "https://music.163.com":
        separator = "&" if "?" in path else "?"
        path = f"{path}{separator}csrf_token={urllib.parse.quote(csrf)}"
    request = urllib.request.Request(
        f"{API_BASE}{path}",
        headers={
            "Cookie": COOKIE,
            "User-Agent": "Mozilla/5.0 GitHub Actions",
            "Referer": "https://music.163.com/",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.load(response)
    if result.get("code") != 200:
        raise RuntimeError(f"网易云接口返回 code={result.get('code')}: {result.get('msg', '未知错误')}")
    return result


def download_cover(url):
    """封面落盘到仓库本地：126.net CDN 对 GitHub camo 代理（海外出口）经常超时，外链时好时坏。"""
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 GitHub Actions"})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read()
        content_type = response.headers.get("Content-Type", "")
    ext = ".png" if "png" in content_type.lower() else ".jpg"
    os.makedirs("assets", exist_ok=True)
    path = f"assets/bgm-cover{ext}"
    for old in ("assets/bgm-cover.jpg", "assets/bgm-cover.png"):
        if os.path.exists(old) and old != path:
            os.remove(old)
    with open(path, "wb") as file:
        file.write(data)
    return path


def main():
    if not COOKIE:
        raise RuntimeError("缺少 NETEASE_COOKIE。请在 GitHub 仓库 Settings > Secrets and variables > Actions 中添加它。")

    playlist_path = "/api/user/playlist" if API_BASE == "https://music.163.com" else "/user/playlist"
    playlists = request_json(f"{playlist_path}?uid={UID}&limit=1000&offset=0").get("playlist", [])
    liked = next((item for item in playlists if "喜欢的音乐" in item.get("name", "")), None)
    if not liked:
        raise RuntimeError(f"找不到用户 {UID} 的“喜欢的音乐”歌单，请确认 UID 和 Cookie 属于同一个账号。")

    if API_BASE == "https://music.163.com":
        detail = request_json(f"/api/playlist/detail?id={liked['id']}&s=0")
        tracks = (detail.get("playlist") or {}).get("tracks", [])
    else:
        tracks = request_json(
            f"/playlist/track/all?id={liked['id']}&limit=1&offset=0"
        ).get("songs", [])
    if not tracks:
        raise RuntimeError("“喜欢的音乐”歌单为空，或网易云没有返回歌曲数据。")

    song = tracks[0]
    artists = "、".join(artist.get("name", "未知歌手") for artist in song.get("ar", []))
    song_url = f"https://music.163.com/#/song?id={song['id']}"
    cover_url = (song.get("al") or {}).get("picUrl", "").replace("http://", "https://")
    audio_url = ""
    try:
        audio = request_json(f"/song/url?id={song['id']}&br=320000").get("data", [])
        audio_url = (audio[0] or {}).get("url", "") if audio else ""
        audio_url = audio_url.replace("http://", "https://")
    except Exception:
        pass
    title = html.escape(song.get("name", "未知歌曲"))
    safe_artists = html.escape(artists)
    local_cover = ""
    if cover_url:
        try:
            local_cover = download_cover(cover_url)
        except Exception as error:
            print(f"封面下载失败，回退到网易云外链: {error}")
    if cover_url:
        img_src = local_cover or cover_url
        replacement = (
            f'<a href="{song_url}"><img src="{html.escape(img_src)}" '
            f'width="160" alt="{title} 封面"></a><br>'
            f"🎵 <strong>{title}</strong> · {safe_artists}<br>"
            f'<a href="{song_url}">▶ 在网易云播放</a>'
        )
    else:
        replacement = f"🎵 [**{title}**]({song_url}) · {safe_artists}"

    with open(README, "r", encoding="utf-8") as file:
        content = file.read()
    pattern = r"<!-- NETEASE_BGM:START -->.*?<!-- NETEASE_BGM:END -->"
    updated, count = re.subn(
        pattern,
        f"<!-- NETEASE_BGM:START -->\n{replacement}\n<!-- NETEASE_BGM:END -->",
        content,
        flags=re.DOTALL,
    )
    if count != 1:
        raise RuntimeError("README.md 中找不到唯一的 NETEASE_BGM 标记。")
    with open(README, "w", encoding="utf-8", newline="\n") as file:
        file.write(updated)
    with open(PLAYER_DATA, "w", encoding="utf-8", newline="\n") as file:
        json.dump(
            {
                "title": song.get("name", "未知歌曲"),
                "artist": artists,
                "url": song_url,
                "coverUrl": cover_url,
                "audioUrl": audio_url,
            },
            file,
            ensure_ascii=False,
            indent=2,
        )
    print(f"已更新 BGM: {song.get('name', '未知歌曲')} - {artists}")


try:
    main()
except Exception as error:
    with open(ERROR_LOG, "w", encoding="utf-8") as file:
        file.write(str(error))
    raise
