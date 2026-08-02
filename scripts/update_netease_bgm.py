import json
import os
import re
import urllib.parse
import urllib.request


UID = os.environ.get("NETEASE_UID", "1591928592")
COOKIE = os.environ.get("NETEASE_COOKIE", "").strip()
README = "README.md"
ERROR_LOG = "bgm-error.log"


def cookie_value(name):
    prefix = f"{name}="
    for part in COOKIE.split(";"):
        part = part.strip()
        if part.startswith(prefix):
            return part[len(prefix):]
    return ""


def request_json(path):
    csrf = cookie_value("__csrf")
    if csrf:
        separator = "&" if "?" in path else "?"
        path = f"{path}{separator}csrf_token={urllib.parse.quote(csrf)}"
    request = urllib.request.Request(
        f"https://music.163.com{path}",
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


def main():
    if not COOKIE:
        raise RuntimeError("缺少 NETEASE_COOKIE。请在 GitHub 仓库 Settings > Secrets and variables > Actions 中添加它。")

    playlists = request_json(f"/api/user/playlist?uid={UID}&limit=1000&offset=0").get("playlist", [])
    liked = next((item for item in playlists if "喜欢的音乐" in item.get("name", "")), None)
    if not liked:
        raise RuntimeError(f"找不到用户 {UID} 的“喜欢的音乐”歌单，请确认 UID 和 Cookie 属于同一个账号。")

    detail = request_json(f"/api/playlist/detail?id={liked['id']}&s=0")
    tracks = (detail.get("playlist") or {}).get("tracks", [])
    if not tracks:
        raise RuntimeError("“喜欢的音乐”歌单为空，或网易云没有返回歌曲数据。")

    song = tracks[0]
    artists = "、".join(artist.get("name", "未知歌手") for artist in song.get("ar", []))
    song_url = f"https://music.163.com/#/song?id={song['id']}"
    replacement = f"🎵 [**{song.get('name', '未知歌曲')}**]({song_url}) · {artists}"

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
    print(f"已更新 BGM: {song.get('name', '未知歌曲')} - {artists}")


try:
    main()
except Exception as error:
    with open(ERROR_LOG, "w", encoding="utf-8") as file:
        file.write(str(error))
    raise
