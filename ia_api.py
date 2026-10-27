"""
ia_api.py — ponte entre o Clippy Videos e o Assistente Local (a IA).

Coloque este arquivo na MESMA pasta do app.py do Clippy e registre-o (2 linhas,
veja LEIA-ME.txt). Ele cria rotas em /api/ia/... que SÓ funcionam para quem tem a
chave secreta (a própria IA, de servidor para servidor). O navegador dos usuários
nunca recebe essa chave.

Rotas:
    GET  /api/ia/ping                    -> testa a conexão
    POST /api/ia/login                   -> confere usuário/senha de uma conta do Clippy
    GET  /api/ia/videos?q=&username=     -> busca vídeos (respeita a classificação indicativa)
    GET  /api/ia/video/<id>?username=    -> título, descrição, canal, legenda, comentários...

Segurança:
- Sem a variável IA_API_KEY (ou o arquivo ia_api.key) a ponte fica DESATIVADA.
- A chave é comparada em tempo constante.
- Vídeos 'bloqueado' ou acima da classificação máxima do usuário não são entregues,
  igual ao site.
- Contas em modo infantil (supervisão, 2 a 11 anos) NÃO podem usar a IA, a menos que
  você defina IA_API_ALLOW_KIDS=1.
"""
import hmac
import json
import os
import re
import time

from flask import Blueprint, jsonify, request
from werkzeug.security import check_password_hash

_TS = re.compile(r"(\d+):(\d\d):(\d\d)[,.](\d{1,3})\s*-->")
_TS_SHORT = re.compile(r"(\d+):(\d\d)[,.](\d{1,3})\s*-->")  # VTT sem hora


def _read_key():
    key = os.environ.get("IA_API_KEY", "").strip()
    if key:
        return key
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ia_api.key")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""


def parse_subtitles(text):
    """Lê SRT/VTT e devolve [(segundo_inicial, texto), ...]."""
    cues = []
    blocks = re.split(r"\n\s*\n", text.replace("\r\n", "\n").replace("\r", "\n").strip())
    for block in blocks:
        lines = block.split("\n")
        for i, line in enumerate(lines):
            m = _TS.search(line)
            if m:
                start = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
            else:
                m = _TS_SHORT.search(line)
                if not m:
                    continue
                start = int(m.group(1)) * 60 + int(m.group(2))
            body = " ".join(lines[i + 1:])
            body = re.sub(r"<[^>]+>", "", body)
            body = re.sub(r"\s+", " ", body).strip()
            if body:
                cues.append((start, body))
            break
    return cues


def group_cues(cues, window=30, max_chars=120_000):
    """Junta as falas em blocos de ~30 s: [{'t': 120, 'text': '...'}, ...]."""
    buckets = {}
    for start, body in cues:
        buckets.setdefault((start // window) * window, []).append(body)
    out, total = [], 0
    for t in sorted(buckets):
        text = " ".join(buckets[t])
        total += len(text)
        if total > max_chars:
            break
        out.append({"t": t, "text": text})
    return out


def register_ia_api(app, get_db, comments_folder, upload_folder,
                    get_user_config_path, pode_assistir_video,
                    precisa_supervisao=None, subtitles_folder=None):
    """Registra as rotas da ponte no app do Clippy."""
    bp = Blueprint("ia_api", __name__, url_prefix="/api/ia")
    api_key = _read_key()
    subs_dir = subtitles_folder or os.path.join(upload_folder, "subtitles")
    allow_kids = os.environ.get("IA_API_ALLOW_KIDS") == "1"
    fails = {}  # username -> [timestamps] (limite de tentativas de senha)

    @bp.before_request
    def _auth():
        if not api_key:
            return jsonify({"error": "Ponte da IA desativada: defina IA_API_KEY."}), 503
        sent = request.headers.get("X-IA-Key", "")
        if not hmac.compare_digest(sent.encode("utf-8"), api_key.encode("utf-8")):
            return jsonify({"error": "Chave inválida."}), 403

    def _too_many(username, limit=10, window=600):
        now = time.time()
        lst = [t for t in fails.get(username, []) if now - t < window]
        fails[username] = lst
        return len(lst) >= limit

    def _user_exists(conn, username):
        if not username:
            return False
        return conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone() is not None

    def _max_class(conn, username):
        """Classificação máxima do usuário (18 para anônimos, como no site)."""
        if not _user_exists(conn, username):  # evita criar pastas para nomes inventados
            return "18"
        path = get_user_config_path(username)
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f).get("classificacao_maxima", "18")
        except (OSError, ValueError):
            return "18"

    @bp.get("/ping")
    def ping():
        return jsonify({"ok": True, "service": "clippy-ia-api"})

    @bp.post("/login")
    def login():
        d = request.get_json(silent=True) or {}
        username = str(d.get("username", "")).strip()
        password = str(d.get("password", ""))
        if not username or not password:
            return jsonify({"ok": False, "error": "Informe usuário e senha."}), 400
        if _too_many(username):
            return jsonify({"ok": False, "error": "Muitas tentativas. Aguarde alguns minutos."}), 429
        conn = get_db()
        row = conn.execute(
            "SELECT username, nome, password, is_pro FROM users WHERE username = ?", (username,)
        ).fetchone()
        conn.close()
        ok = False
        if row:
            stored = row["password"] or ""
            if stored.startswith(("scrypt:", "pbkdf2:")):   # já com hash
                ok = check_password_hash(stored, password)
            else:                                            # texto puro (formato atual do Clippy)
                ok = hmac.compare_digest(stored.encode("utf-8"), password.encode("utf-8"))
        if not ok:
            fails.setdefault(username, []).append(time.time())
            return jsonify({"ok": False, "error": "Usuário ou senha do Clippy incorretos."}), 401
        if precisa_supervisao and not allow_kids and precisa_supervisao(row["username"]):
            return jsonify({"ok": False, "error": "Contas em modo infantil não podem usar a IA."}), 403
        fails.pop(username, None)
        return jsonify({"ok": True, "username": row["username"], "nome": row["nome"],
                        "is_pro": bool(row["is_pro"])})

    @bp.get("/videos")
    def videos():
        q = (request.args.get("q") or "").strip().lower()[:100]
        username = (request.args.get("username") or "").strip()
        limit = max(1, min(int(request.args.get("limit", 20) or 20), 50))
        conn = get_db()
        max_class = _max_class(conn, username)
        sql = ("SELECT id, title, channel, views, created_at, classificacao FROM videos "
               "WHERE COALESCE(status,'') != 'bloqueado'")
        args = []
        if q:
            like = f"%{q}%"
            sql += " AND (LOWER(COALESCE(title,'')) LIKE ? OR LOWER(COALESCE(description,'')) LIKE ?)"
            args += [like, like]
        sql += " ORDER BY views DESC, created_at DESC LIMIT ?"
        args.append(limit * 3)  # folga para o filtro de classificação
        rows = conn.execute(sql, args).fetchall()
        conn.close()
        out = [{"id": r["id"], "title": r["title"], "channel": r["channel"],
                "views": r["views"], "created_at": r["created_at"]}
               for r in rows if pode_assistir_video(r["classificacao"] or "L", max_class)]
        return jsonify({"videos": out[:limit]})

    @bp.get("/video/<video_id>")
    def video(video_id):
        username = (request.args.get("username") or "").strip()
        conn = get_db()
        row = conn.execute("SELECT * FROM videos WHERE id = ?", (str(video_id),)).fetchone()
        if not row:
            conn.close()
            return jsonify({"error": "Vídeo não encontrado."}), 404
        v = dict(row)
        if v.get("status") == "bloqueado":
            conn.close()
            return jsonify({"error": "Este vídeo foi bloqueado."}), 403
        if not pode_assistir_video(v.get("classificacao") or "L", _max_class(conn, username)):
            conn.close()
            return jsonify({"error": "Vídeo acima da classificação indicativa permitida para esta conta."}), 403

        likes_row = conn.execute("SELECT count FROM likes WHERE video_id = ?", (str(video_id),)).fetchone()
        react = conn.execute(
            "SELECT SUM(CASE WHEN reaction = 1 THEN 1 ELSE 0 END) AS l, "
            "SUM(CASE WHEN reaction = -1 THEN 1 ELSE 0 END) AS d "
            "FROM video_reactions WHERE video_id = ?", (str(video_id),)).fetchone()
        channel_name, channel_display, channel_bio, subs = v.get("channel"), "", "", 0
        if channel_name:
            ch = conn.execute("SELECT display_name, bio FROM channels WHERE username = ?",
                              (channel_name,)).fetchone()
            if ch:
                channel_display, channel_bio = ch["display_name"] or "", ch["bio"] or ""
            subs = conn.execute("SELECT COUNT(*) FROM subscribers WHERE channel = ?",
                                (channel_name,)).fetchone()[0]
        conn.close()

        # comentários (arquivo coments/<id>.txt, linhas "usuario|texto")
        comments = []
        cpath = os.path.join(comments_folder, f"{os.path.basename(str(video_id))}.txt")
        if os.path.exists(cpath):
            with open(cpath, "r", encoding="utf-8", errors="replace") as f:
                for line in f.readlines()[-40:]:
                    user, _, text = line.rstrip("\n").partition("|")
                    if text.strip():
                        comments.append({"user": user.strip(), "text": text.strip()[:400]})

        # legenda (.srt/.vtt)
        segments = []
        sub_name = v.get("subtitle_file") or ""
        if sub_name and os.path.basename(sub_name) == sub_name:
            spath = os.path.join(subs_dir, sub_name)
            if os.path.exists(spath):
                raw = open(spath, "rb").read()
                try:
                    text = raw.decode("utf-8-sig")
                except UnicodeDecodeError:
                    text = raw.decode("latin-1")
                segments = group_cues(parse_subtitles(text))

        return jsonify({
            "id": v["id"],
            "title": v.get("title") or "",
            "description": v.get("description") or "",
            "channel": channel_name,
            "channel_display_name": channel_display or channel_name or "",
            "channel_bio": channel_bio,
            "subscribers": subs,
            "views": v.get("views") or 0,
            "likes": (react["l"] or 0) + (likes_row["count"] if likes_row else 0),
            "dislikes": react["d"] or 0,
            "created_at": v.get("created_at") or "",
            "classificacao": v.get("classificacao") or "L",
            "chapters": v.get("chapters") or "",
            "has_transcript": bool(segments),
            "transcript": segments,
            "comments": comments,
        })

    app.register_blueprint(bp)
    state = "ATIVA" if api_key else "DESATIVADA (defina IA_API_KEY)"
    print(f"[ia_api] Ponte da IA {state}")
