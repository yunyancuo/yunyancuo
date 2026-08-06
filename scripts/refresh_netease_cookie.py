#!/usr/bin/env python3
"""
Refresh NetEase Cloud Music cookie via phone login.
Uses NeteaseCloudMusicApi (must be running on localhost:3000).
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


def api_req(path, data=None, cookie=None, method="POST"):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://music.163.com/",
    }
    if cookie:
        headers["Cookie"] = cookie
    if data:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        body = urllib.parse.urlencode(data).encode()
    else:
        body = None
        if method == "GET":
            headers.pop("Content-Type", None)

    req = urllib.request.Request(
        f"{API_BASE}{path}", data=body, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.load(resp)
            return body, dict(resp.getheaders())
    except urllib.error.HTTPError as e:
        try:
            body = json.load(e)
        except:
            body = {"code": e.code, "message": str(e)}
        return body, dict(e.headers.items())
    except Exception as e:
        return {"code": -1, "message": str(e)}, {}


def wait_for_api():
    for _ in range(30):
        try:
            urllib.request.urlopen(f"{API_BASE}/", timeout=2)
            return True
        except Exception:
            time.sleep(2)
    return False


def build_cookie_string(headers):
    """Extract Set-Cookie values from response headers."""
    cookies = []
    for k, v in headers.items():
        if k.lower() == "set-cookie":
            # Get the cookie part before ';'
            parts = v.split(";")
            if parts:
                cookie_part = parts[0].strip()
                if cookie_part and "=" in cookie_part:
                    cookies.append(cookie_part)
    return "; ".join(cookies)


def main():
    if not wait_for_api():
        print("ERROR: NeteaseCloudMusicApi not ready", file=sys.stderr)
        with open("bgm-error.log", "w") as f:
            f.write("NeteaseCloudMusicApi did not start within 60s\n")
        sys.exit(1)

    # Step 1: Try existing cookie
    if OLD_COOKIE:
        result, _ = api_req("/login/status", cookie=OLD_COOKIE, method="GET")
        if result.get("data", {}).get("account"):
            print(f"COOKIE_OK:{OLD_COOKIE}")
            return

    # Step 2: Login with phone + MD5 password
    # Note: NeteaseCloudMusicApi v4 expects phone and md5_password as query params
    md5_pw = hashlib.md5(PASSWORD.encode("utf-8")).hexdigest()

    # Try query-param style (newer API versions)
    for attempt, (use_get, use_body) in enumerate([
        (True, True),    # GET with both query and body
        (False, True),   # POST with body
        (False, False),  # POST with query params
    ]):
        data = {}
        qs_params = {}
        if use_body:
            data = {"phone": PHONE, "md5_password": md5_pw}
        else:
            qs_params = {"phone": PHONE, "md5_password": md5_pw}

        path = "/login/cellphone"
        if qs_params:
            path += "?" + urllib.parse.urlencode(qs_params)

        method = "GET" if use_get else "POST"
        result, headers = api_req(path, data=data, method=method)

        code = result.get("code", -1)
        msg = result.get("message", str(result))

        if code == 200:
            # Success! Get cookie from response
            cookie = result.get("cookie", "")
            if not cookie:
                cookie = build_cookie_string(headers)
            if cookie:
                print(f"COOKIE_NEW:{cookie}")
                return

        # 301=need login, 400/501/502=bad request or captcha
        if code in (400, 501, 502):
            # May need captcha, try different method
            continue
        if code == 803:
            # Account not found or password error
            print(f"ERROR: Login rejected: {msg}", file=sys.stderr)
            break

    # Step 3: Try QR code login hint
    if not OLD_COOKIE:
        print("ERROR: All login attempts failed. Phone verification likely required.", file=sys.stderr)
    else:
        print(f"COOKIE_OK:{OLD_COOKIE}")

    with open("bgm-error.log", "w") as f:
        f.write(f"Auto-login failed. Phone verification or captcha required.\n")


if __name__ == "__main__":
    main()
