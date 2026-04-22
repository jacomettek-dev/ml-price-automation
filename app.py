import os
import uuid
import webbrowser
import threading

from flask import Flask, render_template, request, redirect, session, url_for, jsonify

from api.ml_client import MLClient
from auth.ml_auth import get_auth_url, exchange_code
from core import sku_cache
from core.price_engine import build_decisions, decisions_to_df
from core.campaign_analyzer import analyze_campaigns
from data.spreadsheet_reader import read_price_sheet

# Secret key persiste entre reinicializações
_KEY_FILE = os.path.join(os.path.dirname(__file__), ".secret_key")
if os.path.exists(_KEY_FILE):
    _secret = open(_KEY_FILE).read().strip()
else:
    _secret = uuid.uuid4().hex
    open(_KEY_FILE, "w").write(_secret)

app = Flask(__name__)
app.secret_key = _secret

# Armazena decisões em memória por sessão (evita limite de 4KB do cookie)
_state: dict[str, dict] = {}


def _sid() -> str:
    if "sid" not in session:
        session["sid"] = uuid.uuid4().hex
    return session["sid"]


def _get_client() -> MLClient:
    return MLClient(session["access_token"], session["user_id"])


@app.route("/")
def index():
    return render_template(
        "index.html",
        authenticated=bool(session.get("access_token")),
        user_id=session.get("user_id", ""),
        redirect_uri=session.get("redirect_uri", "http://localhost:5000/callback"),
    )


@app.route("/auth/start", methods=["POST"])
def auth_start():
    session["client_id"] = request.form["client_id"].strip()
    session["client_secret"] = request.form["client_secret"].strip()
    session["redirect_uri"] = request.form["redirect_uri"].strip()
    return redirect(get_auth_url(session["client_id"], session["redirect_uri"]))


@app.route("/callback")
def callback():
    code = request.args.get("code", "")
    if not code:
        return "Código não encontrado na URL.", 400
    try:
        token_data = exchange_code(
            code,
            session["client_id"],
            session["client_secret"],
            session["redirect_uri"],
        )
        session["access_token"] = token_data["access_token"]
        session["refresh_token"] = token_data.get("refresh_token", "")
        session["user_id"] = str(token_data["user_id"])
    except Exception as e:
        return f"Erro na autenticação: {e}", 400
    return redirect(url_for("index"))


@app.route("/logout", methods=["POST"])
def logout():
    sid = session.get("sid")
    if sid and sid in _state:
        del _state[sid]
    session.clear()
    return redirect(url_for("index"))


@app.route("/api/cache", methods=["POST"])
def api_cache():
    if not session.get("access_token"):
        return jsonify({"error": "Não autenticado"}), 401
    logs = []
    try:
        sku_cache.build_cache(_get_client(), on_progress=lambda m: logs.append(m))
        return jsonify({"ok": True, "logs": logs})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/prices", methods=["POST"])
def api_prices():
    if not session.get("access_token"):
        return jsonify({"error": "Não autenticado"}), 401

    promo_id = request.form.get("promo_id", "").strip()
    file = request.files.get("price_sheet")

    if not promo_id:
        return jsonify({"error": "ID da promoção é obrigatório"}), 400
    if not file:
        return jsonify({"error": "Planilha é obrigatória"}), 400

    try:
        client = _get_client()
        price_df = read_price_sheet(file)
        deal_items = client.get_deal_items(promo_id)

        if not deal_items:
            return jsonify({"error": "Nenhum item encontrado nesta promoção"})

        if not sku_cache.is_cache_valid():
            sku_cache.build_cache(client)

        decisions = build_decisions(price_df, deal_items, promo_id)
        df = decisions_to_df(decisions)
        _state[_sid()] = {"decisions": decisions}

        approved = sum(1 for d in decisions if d.aprovado)
        return jsonify({
            "table": df.values.tolist(),
            "columns": list(df.columns),
            "total": len(decisions),
            "approved": approved,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/apply", methods=["POST"])
def api_apply():
    if not session.get("access_token"):
        return jsonify({"error": "Não autenticado"}), 401

    decisions = _state.get(_sid(), {}).get("decisions", [])
    approved = [d for d in decisions if d.aprovado]

    if not approved:
        return jsonify({"error": "Nenhum item aprovado para aplicar"}), 400

    client = _get_client()
    results = []
    for d in approved:
        try:
            client.set_deal_price(d.promotion_id, d.item_id, d.preco_ml_sugerido)
            results.append({"item_id": d.item_id, "price": d.preco_ml_sugerido, "ok": True})
        except Exception as e:
            results.append({"item_id": d.item_id, "error": str(e), "ok": False})

    return jsonify({"results": results})


@app.route("/api/campaigns")
def api_campaigns():
    if not session.get("access_token"):
        return jsonify({"error": "Não autenticado"}), 401
    try:
        logs = []
        df = analyze_campaigns(_get_client(), on_progress=lambda m: logs.append(m))
        if df.empty:
            return jsonify({"table": [], "columns": [], "logs": logs})
        return jsonify({
            "table": df.values.tolist(),
            "columns": list(df.columns),
            "logs": logs,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    threading.Timer(1.2, lambda: webbrowser.open("http://localhost:5000")).start()
    app.run(debug=False, port=5000)
