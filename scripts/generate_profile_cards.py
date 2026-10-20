import json
import os
import urllib.request

USERNAME = "yunyancuo"
ORGS = ["Infinite-Monkey-Lab"]
MY_ORG_REPOS = {"todotree", "FeiyuCursor", "keresearch", "infinite-monkey-lab"}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")


def get_json(path):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USERNAME,
    }
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        f"https://api.github.com{path}",
        headers=headers,
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def svg_escape(value):
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def write_stats(user, repos):
    stars = sum(repo["stargazers_count"] for repo in repos)
    content = f'''<svg xmlns="http://www.w3.org/2000/svg" width="495" height="165" viewBox="0 0 495 165">
  <rect width="495" height="165" rx="8" fill="#191724"/>
  <text x="24" y="34" fill="#ebbcba" font-family="sans-serif" font-size="18" font-weight="bold">{svg_escape(USERNAME)}'s GitHub Stats</text>
  <text x="24" y="72" fill="#e0def4" font-family="sans-serif" font-size="15">Public Repos</text>
  <text x="24" y="98" fill="#ebbcba" font-family="sans-serif" font-size="24" font-weight="bold">{len(repos)}</text>
  <text x="170" y="72" fill="#e0def4" font-family="sans-serif" font-size="15">Followers</text>
  <text x="170" y="98" fill="#ebbcba" font-family="sans-serif" font-size="24" font-weight="bold">{user["followers"]}</text>
  <text x="316" y="72" fill="#e0def4" font-family="sans-serif" font-size="15">Total Stars</text>
  <text x="316" y="98" fill="#ebbcba" font-family="sans-serif" font-size="24" font-weight="bold">{stars}</text>
  <path d="M24 130h447" stroke="#6e6a86" stroke-width="1"/>
  <text x="24" y="151" fill="#908caa" font-family="sans-serif" font-size="12">Auto-updated by GitHub Actions</text>
</svg>
'''
    with open(os.path.join(ASSETS, "github-stats.svg"), "w", encoding="utf-8") as file:
        file.write(content)


def write_languages(repos):
    counts = {}
    for repo in repos:
        full_name = repo.get("full_name", f'{USERNAME}/{repo["name"]}')
        for language, amount in get_json(f"/repos/{full_name}/languages").items():
            counts[language] = counts.get(language, 0) + amount
    top = sorted(counts.items(), key=lambda item: item[1], reverse=True)[:3]
    total = sum(counts.values()) or 1
    colors = {"Python": "#3572A5", "Jupyter Notebook": "#DA5B0B", "JavaScript": "#f1e05a", "HTML": "#e34c26", "CSS": "#563d7c"}
    x = 24
    bars = []
    legend = []
    for language, amount in top:
        width = max(18, round(447 * amount / total))
        bars.append(f'<rect x="{x}" y="58" width="{width}" height="16" fill="{colors.get(language, "#8b8ba7")}"/>')
        legend.append((language, colors.get(language, "#8b8ba7"), x))
        x += width
    legend_text = ''.join(f'<circle cx="{pos + 6}" cy="103" r="6" fill="{color}"/><text x="{pos + 20}" y="108" fill="#e0def4" font-family="sans-serif" font-size="14">{svg_escape(language)}</text>' for language, color, pos in legend)
    content = f'''<svg xmlns="http://www.w3.org/2000/svg" width="495" height="165" viewBox="0 0 495 165">
  <rect width="495" height="165" rx="8" fill="#191724"/>
  <text x="24" y="34" fill="#ebbcba" font-family="sans-serif" font-size="18" font-weight="bold">Top Languages</text>
  <rect x="24" y="58" width="447" height="16" rx="8" fill="#403d52"/>{''.join(bars)}
  {legend_text}
  <text x="24" y="144" fill="#908caa" font-family="sans-serif" font-size="12">Auto-updated by GitHub Actions</text>
</svg>
'''
    with open(os.path.join(ASSETS, "top-languages.svg"), "w", encoding="utf-8") as file:
        file.write(content)


user = get_json(f"/users/{USERNAME}")
repositories = list(get_json(f"/users/{USERNAME}/repos?per_page=100&type=owner"))
seen = {r["name"] for r in repositories}
for org in ORGS:
    try:
        for r in get_json(f"/orgs/{org}/repos?per_page=100&type=public"):
            if r["name"] not in seen and r["name"] in MY_ORG_REPOS and not r.get("private"):
                repositories.append(r)
                seen.add(r["name"])
    except Exception:
        pass

write_stats(user, repositories)
write_languages(repositories)
