#!/usr/bin/env python3
"""
Refresh NetEase Cloud Music cookie via phone login.
Starts NeteaseCloudMusicApi, logs in with phone + password,
outputs the new cookie to stdout.
"""

import json
import time
import hashlib
import urllib.request
import urllib.parse
import sys
import os

API_BASE = "http://127.0.0.1:3000"
PHONE = os.environ.get("NETEASE_PHONE", "").strip()
PASSWORD = os.environ.get("NETEASE_PASSWORD", "").strip()
OLD_COOKIE = os.environ.get("NETEASE_COOKIE", "").strip()


def api_post(path, data=None, cookie=None):
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "Mozilla/5.0 GitHub Actions",
    }
    if cookie:
        headers["Cookie"] = cookie
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(f"{API_BASE}{path}", data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)
    except Exception as e:
        return {"code": -1, "message": str(e)}


def wait_for_api():
    for _ in range(30):
        try:
            urllib.request.urlopen(f"{API_BASE}/", timeout=2)
            return True
        except Exception:
            time.sleep(2)
    return False


def parse_cookies(headers):
    """Extract cookies from Set-Cookie headers as a single string."""
    cookies = []
    for h in headers:
        parts = h.split(";")
        if parts:
            cookies.append(parts[0].strip())
    return "; ".join(cookies)


def main():
    if not wait_for_api():
        print("ERROR: NeteaseCloudMusicApi not ready", file=sys.stderr)
        sys.exit(1)

    # Step 1: Try existing cookie first
    if OLD_COOKIE:
        test = api_post("/login/status", cookie=OLD_COOKIE)
        if test.get("data", {}).get("account"):
            print(f"COOKIE_OK:{OLD_COOKIE}")
            return

    # Step 2: Login with phone + password
    md5_pw = hashlib.md5(PASSWORD.encode()).hexdigest()
    result = api_post("/login/cellphone", {
        "phone": PHONE,
        "md5_password": md5_pw,
    })

    if result.get("code") != 200:
        msg = result.get("message", str(result))
        print(f"ERROR: Login failed: {msg}", file=sys.stderr)
        # Write error for workflow to detect
        with open("bgm-error.log", "w") as f:
            f.write(f"NetEase login failed: {msg}\n")
        sys.exit(1)

    # Step 3: Get cookie from login response headers
    # The API sets cookies via Set-Cookie headers. We need to make a
    # follow-up request to capture the cookie.
    # Instead, use the token/cookie from the login response.
    token = result.get("token", "")
    cookie_str = result.get("cookie", "")

    if not cookie_str:
        # Build cookie manually from known fields
        cookies = []
        if token:
            cookies.append(f"MUSIC_U={token}")
        cookies.append("appver=1.5.2")
        cookies.append("os=pc")
        cookie_str = "; ".join(cookies)

    print(f"COOKIE_NEW:{cookie_str}")


if __name__ == "__main__":
    main()
