"""
ig_reauth.py
============
Re-autorisation complete Instagram (token expire ou revoque).

Usage :
  set FACEBOOK_APP_ID=<ton_app_id>
  set FACEBOOK_APP_SECRET=<ton_app_secret>
  python ig_reauth.py

Le script ouvre le navigateur Facebook Login, capture le code OAuth,
echange contre un token long-lived (60 jours), et met a jour le secret GitHub.

Trouve App ID et App Secret dans :
  https://developers.facebook.com/apps/ -> ton app -> Settings -> Basic
"""

import os, sys, json, webbrowser, urllib.parse, subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests

APP_ID     = os.environ.get("FACEBOOK_APP_ID", "")
APP_SECRET = os.environ.get("FACEBOOK_APP_SECRET", "")
REDIRECT_URI = "http://localhost:5000/callback"
REPO         = os.environ.get("REPO", "dali-aoun/Astro-Hugo-Clickbank-Auto")

SCOPES = [
    "instagram_basic",
    "instagram_content_publish",
    "instagram_manage_comments",
    "pages_show_list",
    "pages_read_engagement",
]

auth_code = None


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        if "code" in params:
            auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<h2>Autorisation Instagram reussie ! Retourne dans le terminal.</h2>")
        elif "error" in params:
            error = params.get("error", ["?"])[0]
            reason = params.get("error_description", [""])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(f"<h2>Erreur : {error} — {reason}</h2>".encode())
            print(f"Erreur Facebook OAuth : {error} — {reason}")
        else:
            self.send_response(200)
            self.end_headers()

    def log_message(self, *args):
        pass


def exchange_code_for_token(code):
    """Echange le code OAuth contre un token court."""
    r = requests.get("https://graph.facebook.com/v19.0/oauth/access_token", params={
        "client_id":     APP_ID,
        "redirect_uri":  REDIRECT_URI,
        "client_secret": APP_SECRET,
        "code":          code,
    })
    if r.status_code != 200:
        print(f"Erreur echange code : {r.status_code} {r.text}")
        sys.exit(1)
    return r.json().get("access_token", "")


def extend_token(short_token):
    """Echange le token court (1h) contre un token long-lived (60 jours)."""
    r = requests.get("https://graph.facebook.com/v19.0/oauth/access_token", params={
        "grant_type":        "fb_exchange_token",
        "client_id":         APP_ID,
        "client_secret":     APP_SECRET,
        "fb_exchange_token": short_token,
    })
    if r.status_code != 200:
        print(f"Erreur extension token : {r.status_code} {r.text}")
        return short_token
    data = r.json()
    long_token = data.get("access_token", short_token)
    expires_in = data.get("expires_in", 0)
    days = expires_in // 86400
    print(f"Token long-lived obtenu — valide {days} jours")
    return long_token


def save_to_github(token, ig_user_id=""):
    """Met a jour INSTAGRAM_ACCESS_TOKEN sur GitHub."""
    print("\n[GitHub] Mise a jour du secret INSTAGRAM_ACCESS_TOKEN...")
    r = subprocess.run(
        ["gh", "secret", "set", "INSTAGRAM_ACCESS_TOKEN",
         "--repo", REPO, "--body", token],
        capture_output=True, text=True
    )
    if r.returncode == 0:
        print("[GitHub] Secret INSTAGRAM_ACCESS_TOKEN mis a jour.")
    else:
        print(f"[GitHub] ERREUR : {r.stderr}")
        print(f"[MANUEL] Token a copier manuellement dans GitHub Secrets :")
        print(f"  {token[:40]}...")

    if ig_user_id:
        print("[GitHub] Mise a jour INSTAGRAM_USER_ID...")
        r2 = subprocess.run(
            ["gh", "secret", "set", "INSTAGRAM_USER_ID",
             "--repo", REPO, "--body", ig_user_id],
            capture_output=True, text=True
        )
        if r2.returncode == 0:
            print("[GitHub] Secret INSTAGRAM_USER_ID mis a jour.")


def get_ig_user_id(token):
    """Recupere l'IG User ID via le token."""
    r = requests.get("https://graph.facebook.com/v19.0/me/accounts", params={
        "access_token": token,
        "fields": "instagram_business_account,name",
    })
    if r.status_code != 200:
        print(f"Impossible de recuperer le compte IG : {r.text}")
        return ""
    data = r.json()
    for page in data.get("data", []):
        ig_acc = page.get("instagram_business_account", {})
        if ig_acc and ig_acc.get("id"):
            print(f"Compte Instagram Business trouve : {ig_acc['id']} (page: {page.get('name')})")
            return ig_acc["id"]
    print("Compte Instagram Business non trouve dans les pages.")
    return ""


def main():
    if not APP_ID or not APP_SECRET:
        print("\nERREUR : variables manquantes")
        print("")
        print("  set FACEBOOK_APP_ID=<ton_app_id>")
        print("  set FACEBOOK_APP_SECRET=<ton_app_secret>")
        print("")
        print("Trouve ces valeurs dans : https://developers.facebook.com/apps/")
        print("  -> Selectionne ton app -> Settings -> Basic")
        sys.exit(1)

    auth_url = (
        "https://www.facebook.com/dialog/oauth"
        f"?client_id={APP_ID}"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
        f"&scope={','.join(SCOPES)}"
        "&response_type=code"
    )

    print("\nOuverture du navigateur pour connexion Facebook / Instagram...")
    print("Si le navigateur ne s'ouvre pas, copie cette URL :")
    print(auth_url)
    webbrowser.open(auth_url)

    print("\nEn attente du callback sur http://localhost:5000 ...")
    print(">>> Connecte-toi a Facebook et autorise l'acces dans le navigateur <<<\n")

    server = HTTPServer(("localhost", 5000), Handler)
    while not auth_code:
        server.handle_request()

    if not auth_code:
        print("Erreur : pas de code recu.")
        sys.exit(1)

    print("Code OAuth recu. Echange en cours...")
    short_token = exchange_code_for_token(auth_code)
    if not short_token:
        print("Erreur : token court non obtenu.")
        sys.exit(1)

    long_token = extend_token(short_token)
    ig_user_id = get_ig_user_id(long_token)
    save_to_github(long_token, ig_user_id)

    print("\nInstagram operationnel. Lance un test :")
    print("  gh workflow run social_publisher.yml --repo dali-aoun/Astro-Hugo-Clickbank-Auto -f platform=instagram")


if __name__ == "__main__":
    main()
