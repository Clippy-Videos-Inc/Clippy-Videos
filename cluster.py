# cluster.py
# Replicação de arquivos entre servidores do Clippy Videos.
#  - Sem peers configurados: não faz nada (usa só o servidor atual).
#  - Com peers: envia (push) os arquivos deste servidor que faltam nos outros.
# Autenticação por HMAC-SHA256 com segredo compartilhado.

import os
import json
import time
import uuid
import hmac
import socket
import hashlib
import logging
import threading

import requests
from flask import Blueprint, request, jsonify, abort, session

log = logging.getLogger("cluster")

cluster_bp = Blueprint('cluster', __name__, url_prefix='/cluster')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.environ.get('CLUSTER_CONFIG', os.path.join(BASE_DIR, 'cluster.json'))
NODE_ID_PATH = os.path.join(BASE_DIR, '.cluster_node_id')

ADMIN_USER = 'pixelado'  # mesmo admin usado em admin.py (check_admin)

ALLOWED_EXT = {
    '.mp4', '.webm', '.mkv', '.mov', '.avi', '.mpeg', '.mpg', '.mpe', '.ogv',
    '.ogm', '.m4v', '.wmv', '.asx',
    '.jpg', '.jpeg', '.png', '.webp', '.gif',
    '.srt', '.txt',
    '.mp3', '.wav', '.ogg',
}
MAX_SKEW = 300      # segundos de tolerância no relógio entre servidores
MIN_AGE = 15        # ignora arquivos modificados há menos de N s (ainda sendo gravados)
CHUNK = 1024 * 1024

_roots = {}         # nome -> pasta absoluta
_lock = threading.Lock()
_started = False
_wake = threading.Event()
_hash_cache = {}
_peer_state = {}    # url -> dict de status/backoff


# ───────────────────────────── configuração ─────────────────────────────

def _node_id():
    try:
        if os.path.exists(NODE_ID_PATH):
            with open(NODE_ID_PATH, 'r', encoding='utf-8') as f:
                v = f.read().strip()
            if v:
                return v
        v = f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
        with open(NODE_ID_PATH, 'w', encoding='utf-8') as f:
            f.write(v)
        return v
    except OSError:
        return socket.gethostname()


def load_config():
    """Lê o cluster.json a cada ciclo: dá pra adicionar/remover peers sem reiniciar."""
    cfg = {"secret": "", "peers": [], "interval": 30, "verify_tls": True}
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict):
                cfg.update(data)
    except Exception as e:
        log.warning("cluster.json inválido: %s", e)

    env_secret = os.environ.get('CLUSTER_SECRET')
    if env_secret:
        cfg['secret'] = env_secret

    peers = []
    for p in cfg.get('peers') or []:
        url = (p.get('url') if isinstance(p, dict) else p) or ''
        url = str(url).strip().rstrip('/')
        if url.startswith(('http://', 'https://')) and url not in peers:
            peers.append(url)
    cfg['peers'] = peers

    try:
        cfg['interval'] = max(5, int(cfg.get('interval', 30)))
    except (TypeError, ValueError):
        cfg['interval'] = 30

    cfg['secret'] = str(cfg.get('secret') or '')
    cfg['node_id'] = _node_id()
    return cfg


# ───────────────────────────── assinatura ─────────────────────────────

def _sign(secret, method, route, ts, rel='', sha='', size='', mtime=''):
    msg = "\n".join([method, route, str(ts), rel, sha, str(size), str(mtime)])
    return hmac.new(secret.encode('utf-8'), msg.encode('utf-8'), hashlib.sha256).hexdigest()


def _auth(method, route, rel='', sha='', size='', mtime=''):
    cfg = load_config()
    if not cfg['secret']:
        abort(404)  # recurso desligado
    ts = request.headers.get('X-Cluster-Time', '')
    sig = request.headers.get('X-Cluster-Sig', '')
    try:
        ts_int = int(ts)
    except ValueError:
        abort(401)
    if abs(time.time() - ts_int) > MAX_SKEW:
        abort(401)
    expected = _sign(cfg['secret'], method, route, ts_int, rel, sha, size, mtime)
    if not hmac.compare_digest(expected, sig):
        abort(401)
    return cfg


def _headers(cfg, method, route, rel='', sha='', size='', mtime=''):
    ts = int(time.time())
    return {
        'X-Cluster-Time': str(ts),
        'X-Cluster-Node': cfg['node_id'],
        'X-Cluster-Sig': _sign(cfg['secret'], method, route, ts, rel, sha, size, mtime),
    }


# ───────────────────────────── arquivos locais ─────────────────────────────

def _resolve(rel):
    """Converte 'raiz/sub/arquivo.mp4' num caminho seguro dentro da raiz. None se inválido."""
    if not rel or '\\' in rel or '\x00' in rel or ':' in rel or rel.startswith('/'):
        return None
    parts = rel.split('/')
    if len(parts) < 2 or any(p in ('', '.', '..') for p in parts):
        return None
    root = _roots.get(parts[0])
    if not root:
        return None
    if os.path.splitext(parts[-1])[1].lower() not in ALLOWED_EXT:
        return None
    try:
        base = os.path.realpath(root)
        target = os.path.realpath(os.path.join(base, *parts[1:]))
        if target == base or os.path.commonpath([base, target]) != base:
            return None
    except ValueError:
        return None
    return target


def scan_local(min_age=0):
    """Retorna {rel: (tamanho, mtime_int, caminho_abs)}."""
    out = {}
    now = time.time()
    for name, root in list(_roots.items()):
        if not os.path.isdir(root):
            continue
        for dp, _dns, fns in os.walk(root):
            for fn in fns:
                if os.path.splitext(fn)[1].lower() not in ALLOWED_EXT:
                    continue  # também ignora os temporários .part
                ap = os.path.join(dp, fn)
                try:
                    st = os.stat(ap)
                except OSError:
                    continue
                if now - st.st_mtime < min_age:
                    continue
                rel = name + '/' + os.path.relpath(ap, root).replace(os.sep, '/')
                out[rel] = (st.st_size, int(st.st_mtime), ap)
    return out


def _sha256(path, size, mtime):
    key = (path, size, mtime)
    v = _hash_cache.get(key)
    if v:
        return v
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for c in iter(lambda: f.read(CHUNK), b''):
            h.update(c)
    if len(_hash_cache) > 5000:
        _hash_cache.clear()
    _hash_cache[key] = h.hexdigest()
    return _hash_cache[key]


# ───────────────────────────── rotas (lado que recebe) ─────────────────────────────

@cluster_bp.route('/manifest', methods=['GET'])
def manifest():
    cfg = _auth('GET', '/cluster/manifest')
    files = {rel: [size, mtime] for rel, (size, mtime, _p) in scan_local().items()}
    return jsonify({'node_id': cfg['node_id'], 'files': files})


def _drain(size):
    left = size
    while left > 0:
        chunk = request.stream.read(min(CHUNK, left))
        if not chunk:
            break
        left -= len(chunk)


@cluster_bp.route('/receive', methods=['POST'])
def receive():
    rel = request.headers.get('X-Cluster-Path', '')
    sha = request.headers.get('X-Cluster-Sha256', '').lower()
    size_s = request.headers.get('X-Cluster-Size', '')
    mtime_s = request.headers.get('X-Cluster-Mtime', '')
    _auth('POST', '/cluster/receive', rel, sha, size_s, mtime_s)

    try:
        size = int(size_s)
        mtime = int(mtime_s)
    except ValueError:
        return jsonify({'error': 'cabeçalhos inválidos'}), 400
    if size < 0 or len(sha) != 64 or request.content_length != size:
        return jsonify({'error': 'cabeçalhos inválidos'}), 400

    target = _resolve(rel)
    if not target:
        return jsonify({'error': 'caminho não permitido'}), 400

    if os.path.exists(target):
        try:
            st = os.stat(target)
            if st.st_size == size or int(st.st_mtime) >= mtime:
                _drain(size)
                return jsonify({'status': 'exists'})
        except OSError:
            pass

    tmp = target + '.' + uuid.uuid4().hex[:8] + '.part'
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        h = hashlib.sha256()
        got = 0
        with open(tmp, 'wb') as f:
            while True:
                chunk = request.stream.read(CHUNK)
                if not chunk:
                    break
                got += len(chunk)
                if got > size:
                    raise ValueError('excedeu o tamanho declarado')
                h.update(chunk)
                f.write(chunk)
        if got != size or h.hexdigest() != sha:
            raise ValueError('tamanho/hash não conferem')
        os.utime(tmp, (mtime, mtime))
        os.replace(tmp, target)
    except ValueError as e:
        _safe_remove(tmp)
        return jsonify({'error': str(e)}), 400
    except OSError as e:
        _safe_remove(tmp)
        log.warning("Falha gravando %s: %s", rel, e)
        return jsonify({'error': 'erro de disco'}), 500

    return jsonify({'status': 'stored'})


def _safe_remove(path):
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


@cluster_bp.route('/status', methods=['GET'])
def status():
    if session.get('username') != ADMIN_USER:
        abort(403)
    cfg = load_config()
    return jsonify({
        'node_id': cfg['node_id'],
        'ativo': bool(cfg['peers'] and cfg['secret']),
        'peers': {
            url: {
                'ultimo_ok': s.get('last_ok'),
                'ultimo_erro': s.get('last_error'),
                'enviados_total': s.get('sent', 0),
                'falhas_seguidas': s.get('fails', 0),
            } for url, s in _peer_state.items()
        },
    })


# ───────────────────────────── sincronização (lado que envia) ─────────────────────────────

def _sync_peer(cfg, peer):
    verify = cfg.get('verify_tls', True)
    st = _peer_state.setdefault(peer, {'fails': 0, 'next_try': 0, 'sent': 0})

    r = requests.get(peer + '/cluster/manifest',
                     headers=_headers(cfg, 'GET', '/cluster/manifest'),
                     timeout=(10, 60), verify=verify)
    r.raise_for_status()
    data = r.json()
    if data.get('node_id') == cfg['node_id']:
        log.info("Peer %s é este próprio servidor; ignorando.", peer)
        return
    remote = data.get('files') or {}

    local = scan_local(min_age=MIN_AGE)
    for rel in sorted(local):
        size, mtime, path = local[rel]
        rf = remote.get(rel)
        if rf is not None and not (rf[0] != size and mtime > rf[1]):
            continue  # já existe no peer (ou o dele é mais novo)

        try:
            sha = _sha256(path, size, mtime)
            st2 = os.stat(path)
            if st2.st_size != size or int(st2.st_mtime) != mtime:
                continue  # mudou durante o hash; tenta no próximo ciclo
            hdr = _headers(cfg, 'POST', '/cluster/receive', rel, sha, size, mtime)
            hdr.update({
                'X-Cluster-Path': rel,
                'X-Cluster-Sha256': sha,
                'X-Cluster-Size': str(size),
                'X-Cluster-Mtime': str(mtime),
                'Content-Type': 'application/octet-stream',
            })
            with open(path, 'rb') as f:
                resp = requests.post(peer + '/cluster/receive', data=f, headers=hdr,
                                     timeout=(10, 3600), verify=verify)
        except OSError as e:
            log.warning("Não consegui ler %s: %s", rel, e)
            continue

        if resp.status_code == 200:
            st['sent'] = st.get('sent', 0) + 1
            log.info("Enviado %s -> %s", rel, peer)
        else:
            log.warning("Peer %s recusou %s (HTTP %s)", peer, rel, resp.status_code)


def _run_once():
    cfg = load_config()
    if not cfg['peers']:
        return  # nenhum outro servidor: usa só o atual
    if not cfg['secret']:
        log.warning("Há peers no cluster.json, mas falta o 'secret' (ou CLUSTER_SECRET). Nada será enviado.")
        return

    now = time.time()
    for peer in cfg['peers']:
        st = _peer_state.setdefault(peer, {'fails': 0, 'next_try': 0, 'sent': 0})
        if now < st['next_try']:
            continue
        try:
            _sync_peer(cfg, peer)
            st.update(fails=0, next_try=0, last_ok=time.strftime('%Y-%m-%d %H:%M:%S'), last_error=None)
        except Exception as e:
            st['fails'] = st.get('fails', 0) + 1
            st['next_try'] = time.time() + min(300, 5 * (2 ** min(st['fails'], 6)))
            st['last_error'] = f"{type(e).__name__}: {e}"
            log.warning("Falha sincronizando com %s: %s", peer, e)


def _loop():
    while True:
        try:
            _run_once()
        except Exception:
            log.exception("Erro inesperado no sincronizador")
        try:
            interval = load_config()['interval']
        except Exception:
            interval = 30
        _wake.wait(interval)
        _wake.clear()


def sync_now():
    """Acorda o sincronizador imediatamente (opcional, ex: após um upload)."""
    _wake.set()


def init_cluster(app, roots):
    """roots: {'uploads': pasta, 'chat_uploads': pasta, ...}"""
    global _started
    for name, path in roots.items():
        _roots[name] = os.path.abspath(path)
    app.register_blueprint(cluster_bp)
    with _lock:
        if _started:
            return
        _started = True
    threading.Thread(target=_loop, daemon=True, name='cluster-sync').start()