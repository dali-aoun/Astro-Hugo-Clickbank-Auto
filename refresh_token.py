"""
Auto-refresh Instagram long-lived access token.
Runs every Monday via GitHub Actions (token_refresh.yml).
Strategy:
  1. Try graph.instagram.com (Basic Display API)
  2. Fallback: graph.facebook.com exchange (Business Graph API)
  3. Verify current token is still valid regardless
"""
import urllib.request, urllib.error, json, sys, os, subprocess

token = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "")
if not token:
    print("ERREUR: INSTAGRAM_ACCESS_TOKEN manquant")
    sys.exit(1)

repo = os.environ.get("REPO", "")


def check_token_valid(t):
    """Returns (valid: bool, days_remaining: int)."""
    url = f"https://graph.facebook.com/v19.0/me?fields=id,name&access_token={t}"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.loads(r.read())
            if "id" in data:
                return True, -1
    except Exception:
        pass
    return False, -1


def try_refresh_basic_display(t):
    """graph.instagram.com refresh — works for Basic Display API tokens."""
    url = (
        "https://graph.instagram.com/refresh_access_token"
        "?grant_type=ig_refresh_token"
        "&access_token=" + t
    )
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            data = json.loads(r.read())
            return data.get("access_token", ""), data.get("expires_in", 0)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"  [basic_display] HTTP {e.code}: {body}")
    except Exception as e:
        print(f"  [basic_display] {e}")
    return "", 0


def try_refresh_graph(t):
    """graph.facebook.com exchange — works for Business/Graph API tokens."""
    app_id     = os.environ.get("FB_APP_ID", "")
    app_secret = os.environ.get("FB_APP_SECRET", "")
    if not app_id or not app_secret:
        print("  [graph_api] FB_APP_ID / FB_APP_SECRET non configurés — skip")
        return "", 0
    url = (
        f"https://graph.facebook.com/v19.0/oauth/access_token"
        f"?grant_type=fb_exchange_token"
        f"&client_id={app_id}"
        f"&client_secret={app_secret}"
        f"&fb_exchange_token={t}"
    )
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            data = json.loads(r.read())
            return data.get("access_token", ""), data.get("expires_in", 0)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"  [graph_api] HTTP {e.code}: {body}")
    except Exception as e:
        print(f"  [graph_api] {e}")
    return "", 0


def update_secret(new_token):
    result = subprocess.run(
        ["gh", "secret", "set", "INSTAGRAM_ACCESS_TOKEN",
         "--repo", repo, "--body", new_token],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"ERREUR mise a jour secret: {result.stderr}")
        return False
    print("Secret INSTAGRAM_ACCESS_TOKEN mis a jour avec succes")
    return True


# ── 1. Verify current token ───────────────────────────────────────────────────
valid, _ = check_token_valid(token)
print(f"Token actuel valide: {valid}")

# ── 2. Try Basic Display API refresh ─────────────────────────────────────────
print("Tentative refresh Basic Display API...")
new_token, expires_in = try_refresh_basic_display(token)

# ── 3. Fallback: Graph API exchange ──────────────────────────────────────────
if not new_token:
    print("Tentative refresh Graph API (fallback)...")
    new_token, expires_in = try_refresh_graph(token)

# ── 4. Result ─────────────────────────────────────────────────────────────────
if new_token:
    days = expires_in // 86400 if expires_in else "?"
    print(f"Token rafraichi — valide pour {days} jours")
    update_secret(new_token)
    sys.exit(0)

# Refresh failed — exit with error only if token is invalid (about to expire)
if not valid:
    print("CRITIQUE: token expiré et refresh impossible — reauth manuelle requise")
    sys.exit(1)

print("WARNING: refresh échoué mais token toujours valide — reauth dans les 7 prochains jours recommandée")
sys.exit(0)
