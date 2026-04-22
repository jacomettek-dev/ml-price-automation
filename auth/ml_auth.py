import os
import webbrowser
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import requests
from dotenv import load_dotenv, set_key

AUTH_URL = "https://auth.mercadolivre.com.br/authorization"
TOKEN_URL = "https://api.mercadolibre.com/oauth/token"
ENV_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")

_auth_code: str | None = None


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global _auth_code
        params = parse_qs(urlparse(self.path).query)
        if "code" in params:
            _auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<h2>Autorizado! Pode fechar esta aba e voltar ao aplicativo.</h2>"
            )
        else:
            self.send_response(400)
            self.end_headers()

    def log_message(self, *args):
        pass


def get_auth_url(client_id: str, redirect_uri: str) -> str:
    return (
        f"{AUTH_URL}?response_type=code"
        f"&client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
    )


def wait_for_code(timeout: int = 120) -> str | None:
    global _auth_code
    _auth_code = None
    server = HTTPServer(("localhost", 8080), _CallbackHandler)
    server.timeout = 1
    deadline = time.time() + timeout
    while time.time() < deadline:
        server.handle_request()
        if _auth_code:
            server.server_close()
            return _auth_code
    server.server_close()
    return None


def exchange_code(code: str, client_id: str, client_secret: str, redirect_uri: str) -> dict:
    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def refresh_access_token(client_id: str, client_secret: str, refresh_token: str) -> dict:
    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def save_tokens(token_data: dict) -> None:
    if not os.path.exists(ENV_FILE):
        open(ENV_FILE, "w").close()
    set_key(ENV_FILE, "ML_ACCESS_TOKEN", token_data.get("access_token", ""))
    set_key(ENV_FILE, "ML_REFRESH_TOKEN", token_data.get("refresh_token", ""))
    set_key(ENV_FILE, "ML_USER_ID", str(token_data.get("user_id", "")))


def _save_credentials(client_id: str, client_secret: str) -> None:
    if not os.path.exists(ENV_FILE):
        open(ENV_FILE, "w").close()
    set_key(ENV_FILE, "ML_CLIENT_ID", client_id)
    set_key(ENV_FILE, "ML_CLIENT_SECRET", client_secret)


def load_tokens() -> dict:
    load_dotenv(ENV_FILE, override=True)
    return {
        "client_id": os.getenv("ML_CLIENT_ID", ""),
        "client_secret": os.getenv("ML_CLIENT_SECRET", ""),
        "access_token": os.getenv("ML_ACCESS_TOKEN", ""),
        "refresh_token": os.getenv("ML_REFRESH_TOKEN", ""),
        "user_id": os.getenv("ML_USER_ID", ""),
    }


def authenticate_ngrok(
    client_id: str,
    client_secret: str,
    ngrok_url: str,
    on_status: callable = None,
) -> dict:
    """
    Fluxo ngrok: redirect URI = ngrok_url/callback → ngrok encaminha para localhost:8080.
    O app sobe um servidor local em 8080 para capturar o code automaticamente.
    """
    def _s(msg):
        if on_status:
            on_status(msg)

    redirect_uri = ngrok_url.rstrip("/") + "/callback"
    url = get_auth_url(client_id, redirect_uri)

    _s("Abrindo navegador para autorização...")
    webbrowser.open(url)
    _s("Aguardando autorização no navegador (até 2 min)...")

    code = wait_for_code(timeout=120)
    if not code:
        raise TimeoutError("Tempo esgotado. Verifique se o ngrok está rodando e tente novamente.")

    _s("Código recebido. Trocando por tokens...")
    token_data = exchange_code(code, client_id, client_secret, redirect_uri)
    save_tokens(token_data)
    _save_credentials(client_id, client_secret)
    _s("Autenticação concluída com sucesso!")
    return token_data


def authenticate_manual(
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    manual_code: str,
    on_status: callable = None,
) -> dict:
    """
    Fluxo manual: o usuário abre a URL de auth, ML redireciona para redirect_uri?code=XXX,
    o usuário copia o código e cola no app.
    """
    def _s(msg):
        if on_status:
            on_status(msg)

    _s("Trocando código por tokens...")
    token_data = exchange_code(manual_code.strip(), client_id, client_secret, redirect_uri)
    save_tokens(token_data)
    _save_credentials(client_id, client_secret)
    _s("Autenticação concluída com sucesso!")
    return token_data


def open_auth_browser(client_id: str, redirect_uri: str) -> None:
    webbrowser.open(get_auth_url(client_id, redirect_uri))


def try_auto_refresh() -> str | None:
    tokens = load_tokens()
    if not tokens["refresh_token"] or not tokens["client_id"]:
        return None
    try:
        data = refresh_access_token(
            tokens["client_id"], tokens["client_secret"], tokens["refresh_token"]
        )
        save_tokens(data)
        return data["access_token"]
    except Exception:
        return None
