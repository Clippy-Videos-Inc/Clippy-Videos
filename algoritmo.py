# algoritmo.py
# Algoritmo de feeds - estilo YouTube "Broadcast Yourself" (2005-2010)
# Coloque este arquivo na mesma pasta do app.py

from datetime import datetime, timezone


# ─────────────────────────── helpers internos ────────────────────────────────

def _horas_desde(created_at: str) -> float:
    """Quantas horas se passaram desde 'created_at'."""
    try:
        data = datetime.fromisoformat(str(created_at))
        agora = datetime.now(timezone.utc) if data.tzinfo else datetime.now()
        return max((agora - data).total_seconds() / 3600, 0.0)
    except Exception:
        return 999_999.0  # data inválida → vídeo "muito velho"


def _score_em_alta(views: int, likes: int, horas: float) -> float:
    """
    Fórmula de tendência (inspirada no Hacker News gravity):
      score = (views + likes*2) / (horas + 2)^1.5

    - Likes valem o dobro das views (engajamento ativo)
    - Quanto mais velho o vídeo, o denominador cresce e o score cai
    - Vídeos de 1h ainda quentes batem vídeos de 1 semana com mais views
    """
    return (views + likes * 2) / ((horas + 2) ** 1.5)


# ──────────────────────────── funções de feed ────────────────────────────────

def feed_em_alta(videos: list, likes_dict: dict, limite: int = 16) -> list:
    """
    Vídeos mais quentes: pondera views, likes e idade.

    Parâmetros
    ----------
    videos      : lista de dicionários retornada por load_videos()
    likes_dict  : {str(video_id): contagem}  ← use carregar_likes(conn)
    limite      : máximo de itens a retornar

    Retorno     : lista ordenada do mais quente ao menos quente
    """
    # Mostra tudo exceto bloqueados (pendente e aprovado aparecem normalmente)
    visiveis = [v for v in videos if v.get('status') != 'bloqueado']
    pontuados = []

    for v in visiveis:
        vid_id = str(v.get('id', ''))
        views  = int(v.get('views', 0))
        likes  = int(likes_dict.get(vid_id, 0))
        horas  = _horas_desde(v.get('created_at', ''))
        score  = _score_em_alta(views, likes, horas)

        item = dict(v)
        item['_score'] = round(score, 4)
        pontuados.append(item)

    pontuados.sort(key=lambda x: x['_score'], reverse=True)
    return pontuados[:limite]

def _to_datetime(created_at: str):
    """Converte string ISO para datetime, sempre retornando aware (UTC)."""
    if not created_at:
        return datetime.min.replace(tzinfo=timezone.utc)
    
    try:
        dt = datetime.fromisoformat(str(created_at))
        # Se for naive, assume UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            # Converte para UTC para padronizar
            dt = dt.astimezone(timezone.utc)
        return dt
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


def feed_recentes(videos: list, limite: int = 16) -> list:
    """Vídeos mais novos em ordem cronológica inversa."""
    visiveis = [v for v in videos if v.get('status') != 'bloqueado']

    def chave(v):
        return _to_datetime(v.get('created_at', ''))

    return sorted(visiveis, key=chave, reverse=True)[:limite]


def feed_de_seus_canais(videos: list, canais_inscritos: list, limite: int = 30) -> list:
    """Vídeos dos canais inscritos, do mais novo ao mais antigo."""
    if not canais_inscritos:
        return []

    filtrados = [
        v for v in videos
        if v.get('channel') in canais_inscritos
        and v.get('status') != 'bloqueado'
    ]

    def chave(v):
        return _to_datetime(v.get('created_at', ''))

    return sorted(filtrados, key=chave, reverse=True)[:limite]

# ──────────────────────── utilitários para o app.py ──────────────────────────

def carregar_likes(conn) -> dict:
    """
    Carrega todos os likes do banco e retorna {str(video_id): contagem}.

    Uso no app.py:
        from algoritmo import carregar_likes
        conn = get_db()
        likes = carregar_likes(conn)
    """
    c = conn.cursor()
    c.execute("SELECT video_id, count FROM likes")
    return {str(r[0]): int(r[1]) for r in c.fetchall()}


def carregar_canais_inscritos(conn, username: str) -> list:
    """
    Retorna lista de canais que 'username' segue.

    Uso no app.py:
        from algoritmo import carregar_canais_inscritos
        canais = carregar_canais_inscritos(conn, session.get('username'))
    """
    if not username:
        return []
    c = conn.cursor()
    c.execute("SELECT channel FROM subscribers WHERE username = ?", (username,))
    return [r[0] for r in c.fetchall()]