"""
Auto-refresh Instagram long-lived access token.
Runs every Monday via GitHub Actions (token_refresh.yml).
"""
import urllib.request, json, sys, os, subprocess

token = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "")
if not token:
    print("ERREUR: INSTAGRAM_ACCESS_TOKEN manquant")
    sys.exit(1)

url = (
    "https://graph.instagram.com/refresh_access_token"
    "?grant_type=ig_refresh_token"
    "&access_token=" + token
)

try:
    with urllib.request.urlopen(url, timeout=30) as r:
        data = json.loads(r.read())
except Exception as e:
    print(f"ERREUR refresh API: {e}")
    sys.exit(1)

new_token = data.get("access_token", "")
expires_in = data.get("expires_in", 0)
days = expires_in // 86400

if not new_token:
    print(f"ERREUR: pas de token dans la reponse: {data}")
    sys.exit(1)

print(f"Token rafraichi — valide pour {days} jours")

repo = os.environ.get("REPO", "")
result = subprocess.run(
    ["gh", "secret", "set", "INSTAGRAM_ACCESS_TOKEN", "--repo", repo, "--body", new_token],
    capture_output=True, text=True
)
if result.returncode != 0:
    print(f"ERREUR mise a jour secret: {result.stderr}")
    sys.exit(1)

print("Secret INSTAGRAM_ACCESS_TOKEN mis a jour avec succes")
