"""
get_yt_refresh_token.py
=======================
Script one-shot pour obtenir ET ENREGISTRER le refresh token YouTube OAuth2.

Usage :
  set YT_CLIENT_ID=...
  set YT_CLIENT_SECRET=...
  python get_yt_refresh_token.py

Le script ouvre le navigateur, tu autorises, il recupere le refresh token
et met automatiquement a jour le secret GitHub YT_REFRESH_TOKEN.
"""

import os, sys, json, webbrowser, urllib.parse, subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests

CLIENT_ID     = os.environ.get("YT_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("YT_CLIENT_SECRET", "")
REDIRECT_URI  = "http://localhost:8080/callback"
SCOPE         = "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube"
REPO          = os.environ.get("REPO", "dali-aoun/Astro-Hugo-Clickbank-Auto")

AUTH_URL   = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL  = "https://oauth2.googleapis.com/token"

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
            self.wfile.write(b"<h2>Autorisation reussie ! Retourne dans le terminal.</h2>")
        elif "error" in params:
            error = params["error"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(f"<h2>Erreur Google : {error}</h2>".encode())
            print(f"Erreur Google OAuth : {error}")
        else:
            self.send_response(200)
            self.end_headers()

    def log_message(self, *args):
        pass


def save_to_github(refresh_token):
    """Met a jour le secret YT_REFRESH_TOKEN sur GitHub."""
    print("\n[GitHub] Mise a jour du secret YT_REFRESH_TOKEN...")
    r = subprocess.run(
        ["gh", "secret", "set", "YT_REFRESH_TOKEN",
         "--repo", REPO, "--body", refresh_token],
        capture_output=True, text=True
    )
    if r.returncode == 0:
        print("[GitHub] Secret YT_REFRESH_TOKEN mis a jour avec succes.")
    else:
        print(f"[GitHub] ERREUR mise a jour secret: {r.stderr}")
        print(f"[MANUEL] Copie ce refresh token dans GitHub Secrets manuellement:")
        print(f"  {refresh_token}")


def main():
    if not CLIENT_ID or not CLIENT_SECRET:
        print("\nERREUR : variables manquantes")
        print("  set YT_CLIENT_ID=<ton_client_id>")
        print("  set YT_CLIENT_SECRET=<ton_client_secret>")
        print("")
        print("Trouve ces valeurs dans : https://console.cloud.google.com/apis/credentials")
        sys.exit(1)

    params = {
        "client_id":     CLIENT_ID,
        "redirect_uri":  REDIRECT_URI,
        "response_type": "code",
        "scope":         SCOPE,
        "access_type":   "offline",
        "prompt":        "consent",
    }
    url = AUTH_URL + "?" + urllib.parse.urlencode(params)

    print("\nOuverture du navigateur pour autorisation YouTube...")
    print("Si le navigateur ne s'ouvre pas, copie cette URL :")
    print(url)
    webbrowser.open(url)

    print("\nEn attente du callback sur http://localhost:8080 ...")
    print(">>> Autorise l'acces dans le navigateur qui vient de s'ouvrir <<<\n")
    server = HTTPServer(("localhost", 8080), Handler)
    while not auth_code:
        server.handle_request()

    if not auth_code:
        print("Erreur : pas de code recu.")
        sys.exit(1)

    r = requests.post(TOKEN_URL, data={
        "code":          auth_code,
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri":  REDIRECT_URI,
        "grant_type":    "authorization_code",
    })

    if r.status_code != 200:
        print(f"Erreur echange de code : {r.status_code} {r.text}")
        sys.exit(1)

    data = r.json()
    refresh_token = data.get("refresh_token", "")
    access_token  = data.get("access_token", "")

    if not refresh_token:
        print(f"ERREUR : pas de refresh_token dans la reponse : {data}")
        sys.exit(1)

    print(f"\nRefresh token obtenu avec succes.")
    save_to_github(refresh_token)
    print("\nYouTube operationnel. Lance un test :")
    print("  gh workflow run social_publisher.yml --repo dali-aoun/Astro-Hugo-Clickbank-Auto -f platform=youtube")


if __name__ == "__main__":
    main()
