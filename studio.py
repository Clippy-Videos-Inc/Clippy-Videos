# studio.py (servidor Flask independente para o Studio)

import os
import uuid
import subprocess
import sqlite3
import json
import functools
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from werkzeug.utils import secure_filename
from flask import current_app

# Configurações globais
STATIC_SERVER_URL = "https://192.168.0.150:7071/"  # Servidor estático separado
APP_BASE_URL = "https://192.168.0.150:443/"       # URL do app principal
SQLITE_DB = r'D:\sqlite\app.db' if os.name == 'nt' else 'app.db'  # Banco compartilhado
UPLOAD_FOLDER = r'D:\cstatic\static\uploads' if os.name == 'nt' else 'static/uploads'
FFMPEG_PATH = r'L:\ffmpeg\bin\ffmpeg.exe' if os.name == 'nt' else 'ffmpeg'
SUBTITLES_FOLDER = os.path.join(UPLOAD_FOLDER, 'subtitles')
BANNERS_FOLDER = os.path.join(UPLOAD_FOLDER, 'banners')

os.makedirs(SUBTITLES_FOLDER, exist_ok=True)
os.makedirs(BANNERS_FOLDER, exist_ok=True)

# Cria o app Flask independente
studio_app = Flask(__name__)
# IMPORTANTE: precisa ser a MESMA secret_key do app.py principal. Sessão é
# um cookie assinado com essa chave — se as chaves forem diferentes, o
# Studio nunca vai reconhecer quem fez login no site principal, e o
# controle de "só o dono pode entrar" simplesmente não funciona.
studio_app.secret_key = 'WsTDo1zxc0oxx2o9Xo*188m'
studio_app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
studio_app.config['MAX_CONTENT_LENGTH'] = int(5 * 1024 * 1024 * 1024)  # 5GB max
studio_app.config['FFMPEG_PATH'] = FFMPEG_PATH

# Garante pasta de uploads
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Função para configs do usuário (copiada para independência)
def get_user_config_path(username):
    user_folder = os.path.join('users', username)
    if not os.path.exists(user_folder):
        os.makedirs(user_folder)
    config_path = os.path.join(user_folder, 'configs.json')
    if not os.path.exists(config_path):
        default_configs = {
            'cor_fundo': '#f0f2f5',
            'idade': '18',
            'tema': 'claro'
        }
        with open(config_path, 'w') as f:
            json.dump(default_configs, f)
    return config_path
# Context processor para injetar user_settings (corrige o erro no template)
@studio_app.context_processor
def inject_user_settings():
    if 'username' in session:
        path = get_user_config_path(session['username'])
        if os.path.exists(path):
            with open(path, 'r') as f:
                return dict(user_settings=json.load(f))
    return dict(user_settings={'cor_fundo': '#f0f2f5', 'idade': '18'})

@studio_app.context_processor
def inject_static_url():
    return dict(static_url=STATIC_SERVER_URL)

# Funções do banco (independentes)
def get_db():
    conn = sqlite3.connect(SQLITE_DB, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def get_channel_info(username):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM channels WHERE username = ?", (username,))
    r = c.fetchone()
    conn.close()
    return dict(r) if r else None

def load_videos():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM videos")
    rows = c.fetchall()
    videos = [dict(r) for r in rows]
    for v in videos:
        v['subtitles'] = json.loads(v['subtitles']) if v.get('subtitles') else []
    conn.close()
    return videos

def get_video(video_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM videos WHERE id = ?", (str(video_id),))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    v = dict(row)
    v['subtitles'] = json.loads(v['subtitles']) if v.get('subtitles') else []
    try:
        v['cards'] = json.loads(v['cards']) if v.get('cards') else []
    except (json.JSONDecodeError, TypeError):
        v['cards'] = []
    return v

def save_video_entry(video_entry):
    conn = get_db()
    c = conn.cursor()
    cards = video_entry.get('cards', [])
    if not isinstance(cards, str):
        cards = json.dumps(cards)
    c.execute("""
        INSERT OR REPLACE INTO videos 
        (id, filename, filename_144p, filename_360p, filename_480p, title, 
         description, views, channel, thumb, subtitles, chapters, subtitle_file, status, cards)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        video_entry['id'],
        video_entry.get('filename'),
        video_entry.get('filename_144p', ''),
        video_entry.get('filename_360p', ''),
        video_entry.get('filename_480p', ''),
        video_entry.get('title'),
        video_entry.get('description', ''),
        int(video_entry.get('views', 0)),
        video_entry.get('channel'),
        video_entry.get('thumb'),
        json.dumps(video_entry.get('subtitles', [])),
        video_entry.get('chapters', ''),
        video_entry.get('subtitle_file', ''),
        video_entry.get('status', 'publicado'),
        cards
    ))
    conn.commit()
    conn.close()

def create_channel_record(username, display_name, bio, password, foto_path=None):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO channels (username, display_name, bio, password, foto_path) VALUES (?, ?, ?, ?, ?)
    """, (username, display_name, bio, password, foto_path))
    conn.commit()
    conn.close()

def verify_channel_password(senha_digitada, senha_salva):
    return senha_digitada == senha_salva

# Garante que colunas novas existam no banco (banco é compartilhado com o
# app.py principal; isso é seguro de rodar toda vez, se a coluna já existe
# ele so ignora o erro)
def garantir_colunas_novas():
    conn = get_db()
    c = conn.cursor()
    for tabela, coluna, tipo in [
        ("channels", "banner_path", "TEXT"),
        ("videos", "cards", "TEXT DEFAULT '[]'"),
    ]:
        try:
            c.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")
            conn.commit()
        except sqlite3.OperationalError:
            pass  # coluna já existe, tudo certo
    conn.close()

garantir_colunas_novas()

# ---------- Segurança: só o dono do canal acessa as páginas do Studio ----------
def dono_do_canal(view_func):
    """Protege qualquer rota que receba <username> na URL. Só deixa passar
    se a pessoa logada (sessão) for exatamente o dono daquele canal.
    Sem sessão ou sessão de outro usuário -> manda pro login do site
    principal, com 'next' pra voltar direto pra cá depois de logar."""
    @functools.wraps(view_func)
    def wrapper(username, *args, **kwargs):
        if session.get('username') != username:
            return redirect(f"{APP_BASE_URL}login?next={request.url}")
        return view_func(username, *args, **kwargs)
    return wrapper


def dono_do_video(view_func):
    """Mesma ideia do decorator acima, mas para rotas que só recebem
    <video_id> (edição/exclusão de vídeo) -- busca o vídeo, descobre o
    canal dono, e só então verifica a sessão."""
    @functools.wraps(view_func)
    def wrapper(video_id, *args, **kwargs):
        video = get_video(video_id)
        if not video:
            return "Vídeo não encontrado", 404
        if session.get('username') != video.get('channel'):
            return redirect(f"{APP_BASE_URL}login?next={request.url}")
        return view_func(video_id, *args, **kwargs)
    return wrapper

# --- Rotas do Studio (com prefixo /studio/<username> onde faz sentido) ---

@studio_app.route('/create', methods=['GET', 'POST'])
def create_channel():
    # Precisa estar logado no site principal pra criar um canal -- e o
    # canal SEMPRE usa o mesmo username da conta logada. Sem isso, dava
    # pra criar um canal "joaocanal" estando logado como "joao", e aí o
    # Studio nunca deixava entrar (sessão "joao" != canal "joaocanal").
    if 'username' not in session:
        return redirect(f"{APP_BASE_URL}login?next={request.url}")

    username = session['username']

    if request.method == 'POST':
        display_name = request.form.get('display_name').strip()
        bio = request.form.get('bio').strip()
        password = request.form.get('password', 'admin').strip()
        foto = request.files.get('foto')

        if not all([display_name, bio]):
            return 'Todos os campos são obrigatórios', 400

        channel_path = os.path.join('channels', f'@{username}')
        if os.path.exists(channel_path):
            return 'Você já tem um canal criado', 409
        os.makedirs(channel_path, exist_ok=True)

        # Salva info.txt para compatibilidade
        info_path = os.path.join(channel_path, 'info.txt')
        with open(info_path, 'w', encoding='utf-8') as f:
            f.write(f"{display_name}\n{bio}\n")

        foto_path = None
        if foto and foto.filename != '':
            foto_path = os.path.join(channel_path, "foto.jpg")
            foto.save(foto_path)

        # Salva no banco
        create_channel_record(username, display_name, bio, password, foto_path)

        return redirect(url_for('studio', username=username))

    return render_template('create.html', username=username)

@studio_app.route('/studio/<username>')
@dono_do_canal
def studio(username):
    ch = get_channel_info(username)
    if not ch:
        return "Erro 404, Canal não encontrado", 404

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM videos WHERE channel = ?", (username,))
    videos = [dict(row) for row in c.fetchall()]
    conn.close()

    # Anexa colaboradores aceitos e quantidade de cards em cada vídeo
    # (usado pra mostrar as badges "Colabs: X" e "Cards: X" no template)
    conn = get_db()
    c = conn.cursor()
    for v in videos:
        c.execute("SELECT name, role FROM collabs WHERE video_id = ? AND status = 'aceito'", (v['id'],))
        v['collaborators'] = [dict(r) for r in c.fetchall()]
        try:
            v['cards'] = json.loads(v['cards']) if v.get('cards') else []
        except (json.JSONDecodeError, TypeError):
            v['cards'] = []
    conn.close()

    total_views = sum(v.get('views', 0) for v in videos)
    total_videos = len(videos)

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as cnt FROM subscribers WHERE channel = ?", (username,))
    subscribers = c.fetchone()['cnt']
    conn.close()

    return render_template('studio.html',
                           display_name=ch.get('display_name', username),
                           bio=ch.get('bio', ''),
                           username=username,
                           total_views=total_views,
                           total_videos=total_videos,
                           subscribers=subscribers,
                           channel_videos=videos,
                           banner_path=ch.get('banner_path'))

@studio_app.route('/studio/<username>/upload_mobile', methods=['GET', 'POST'])
@dono_do_canal
def studio_mobile_upload(username):
    if request.method == 'POST':
        senha_digitada = request.form.get('password')
        ch = get_channel_info(username)
        if not ch:
            return 'Canal não encontrado', 404
        if not verify_channel_password(senha_digitada, ch.get('password', '')):
            return 'Senha do canal incorreta', 403

        title = request.form.get('title')
        description = request.form.get('description')
        video_file = request.files.get('video')
        thumb_file = request.files.get('thumb')

        if not video_file or not title:
            return 'Título e vídeo são obrigatórios', 400

        upload_folder = current_app.config['UPLOAD_FOLDER']
        
        filename = secure_filename(video_file.filename)
        unique_name = f"{uuid.uuid4().hex[:8]}_{filename}"
        video_path = os.path.join(upload_folder, unique_name)
        video_file.save(video_path)

        # Thumbnail automática
        thumb_filename = f"thumb_{os.path.splitext(unique_name)[0]}.jpg"
        thumb_path = os.path.join(upload_folder, thumb_filename)
        ffmpeg_path = current_app.config.get('FFMPEG_PATH', 'ffmpeg')
        try:
            subprocess.run([
                ffmpeg_path, '-i', video_path, '-ss', '00:00:01', '-vframes', '1', thumb_path
            ], check=True)
        except Exception as e:
            print("Erro ao gerar thumb:", e)
            thumb_filename = 'default_thumb.jpg'

        # Thumb manual
        if thumb_file and thumb_file.filename != '':
            thumb_filename = f"thumb_manual_{uuid.uuid4().hex[:5]}.jpg"
            thumb_file.save(os.path.join(upload_folder, thumb_filename))

        # Transcodes (144p, 360p, 480p)
        filename_144p = f'144p_{unique_name}'
        video_path_144p = os.path.join(upload_folder, filename_144p)
        try:
            subprocess.run([ffmpeg_path, '-i', video_path, '-vf', 'scale=256:-2', '-c:v', 'libx264', '-preset', 'fast',
                            '-crf', '28', '-c:a', 'aac', '-b:a', '64k', video_path_144p], check=True)
        except Exception as e:
            print("Erro 144p:", e)
            filename_144p = ''

        filename_360p = f'360p_{unique_name}'
        video_path_360p = os.path.join(upload_folder, filename_360p)
        try:
            subprocess.run([ffmpeg_path, '-i', video_path, '-vf', 'scale=640:-2', '-c:v', 'libx264', '-preset', 'fast',
                            '-crf', '25', '-c:a', 'aac', '-b:a', '96k', video_path_360p], check=True)
        except Exception as e:
            print("Erro 360p:", e)
            filename_360p = ''

        filename_480p = f'480p_{unique_name}'
        video_path_480p = os.path.join(upload_folder, filename_480p)
        try:
            subprocess.run([ffmpeg_path, '-i', video_path, '-vf', 'scale=854:-2', '-c:v', 'libx264', '-preset', 'fast',
                            '-crf', '23', '-c:a', 'aac', '-b:a', '128k', video_path_480p], check=True)
        except Exception as e:
            print("Erro 480p:", e)
            filename_480p = ''

        video_id = uuid.uuid4().hex[:10]
        video_entry = {
            'id': video_id,
            'filename': unique_name,
            'filename_144p': filename_144p,
            'filename_360p': filename_360p,
            'filename_480p': filename_480p,
            'title': title,
            'description': description,
            'views': 0,
            'channel': username,
            'thumb': thumb_filename,
            'subtitles': [],
            'status': 'pendente'
        }
        
        save_video_entry(video_entry)
        
        return redirect(f'/lang=mobile/video/{video_id}')

    return render_template('studio_mobile.html', username=username)

@studio_app.route('/studio/<username>/upload_video', methods=['POST'])
@dono_do_canal
def upload_video(username):
    senha = request.form.get('password')
    ch = get_channel_info(username)
    if not ch or senha != ch.get('password'):
        return "Senha incorreta", 403

    title = request.form.get('title')
    description = request.form.get('description')
    chapters = request.form.get('chapters', '')
    video_file = request.files.get('video')
    thumb_file = request.files.get('thumb')
    subtitle_file = request.files.get('subtitle')

    if not video_file or not title:
        return "Título e vídeo são obrigatórios", 400

    # Salvar vídeo
    filename = secure_filename(video_file.filename)
    unique_name = f"{uuid.uuid4().hex[:8]}_{filename}"
    video_path = os.path.join(UPLOAD_FOLDER, unique_name)
    video_file.save(video_path)

    # Thumbnail
    thumb_filename = f"thumb_{os.path.splitext(unique_name)[0]}.jpg"
    ffmpeg_path = studio_app.config.get('FFMPEG_PATH', 'ffmpeg')

    if thumb_file and thumb_file.filename:
        thumb_file.save(os.path.join(UPLOAD_FOLDER, thumb_filename))
    else:
        # Gera thumb automática
        try:
            subprocess.run([ffmpeg_path,
                            '-i', video_path, '-ss', '00:00:03', '-vframes', '1',
                            os.path.join(UPLOAD_FOLDER, thumb_filename)], check=True)
        except Exception as e:
            print("Erro ao gerar thumb:", e)
            thumb_filename = 'default_thumb.jpg'

    # Transcodes (144p, 360p, 480p) -- roda sempre, independente de ter
    # sido enviada uma thumb manual ou não (bug anterior: isso ficava
    # dentro do 'else' da thumb e nunca rodava quando a thumb era manual,
    # deixando as variáveis abaixo indefinidas e derrubando o upload)
    filename_144p = f'144p_{unique_name}'
    video_path_144p = os.path.join(UPLOAD_FOLDER, filename_144p)
    try:
        subprocess.run([ffmpeg_path, '-i', video_path, '-vf', 'scale=256:-2', '-c:v', 'libx264', '-preset', 'fast',
                        '-crf', '28', '-c:a', 'aac', '-b:a', '64k', video_path_144p], check=True)
    except Exception as e:
        print("Erro 144p:", e)
        filename_144p = ''

    filename_360p = f'360p_{unique_name}'
    video_path_360p = os.path.join(UPLOAD_FOLDER, filename_360p)
    try:
        subprocess.run([ffmpeg_path, '-i', video_path, '-vf', 'scale=640:-2', '-c:v', 'libx264', '-preset', 'fast',
                        '-crf', '25', '-c:a', 'aac', '-b:a', '96k', video_path_360p], check=True)
    except Exception as e:
        print("Erro 360p:", e)
        filename_360p = ''

    filename_480p = f'480p_{unique_name}'
    video_path_480p = os.path.join(UPLOAD_FOLDER, filename_480p)
    try:
        subprocess.run([ffmpeg_path, '-i', video_path, '-vf', 'scale=854:-2', '-c:v', 'libx264', '-preset', 'fast',
                        '-crf', '23', '-c:a', 'aac', '-b:a', '128k', video_path_480p], check=True)
    except Exception as e:
        print("Erro 480p:", e)
        filename_480p = ''

    # Legenda .srt
    subtitle_path = ''
    if subtitle_file and subtitle_file.filename.endswith('.srt'):
        subtitle_path = f"{uuid.uuid4().hex[:8]}_{secure_filename(subtitle_file.filename)}"
        subtitle_file.save(os.path.join(SUBTITLES_FOLDER, subtitle_path))

    video_id = uuid.uuid4().hex[:10]

    video_entry = {
        'id': video_id,
        'filename': unique_name,
        'filename_144p': filename_144p,
        'filename_360p': filename_360p,
        'filename_480p': filename_480p,
        'title': title,
        'description': description,
        'views': 0,
        'channel': username,
        'thumb': thumb_filename,
        'subtitles': [],
        'chapters': chapters,
        'subtitle_file': subtitle_path,
        'status': 'publicado'
    }

    save_video_entry(video_entry)

    return redirect(f'/studio/{username}')

@studio_app.route('/studio/<username>/trocar_foto', methods=['POST'])
@dono_do_canal
def trocar_foto(username):
    senha_digitada = request.form.get('password')
    ch = get_channel_info(username)
    if not ch:
        return "Canal não encontrado.", 404
    if not verify_channel_password(senha_digitada, ch.get('password', '')):
        return "Senha incorreta.", 403

    foto = request.files.get('nova_foto')
    if not foto:
        return "Nenhuma imagem enviada.", 400

    channel_dir = os.path.join("channels", f"@{username}")
    foto_path = os.path.join(channel_dir, "foto.jpg")
    foto.save(foto_path)

    create_channel_record(username, ch.get('display_name', username), ch.get('bio', ''), ch.get('password', ''), foto_path)

    return redirect(url_for('studio', username=username))

@studio_app.route('/request_collab', methods=['POST'])
def request_collab():
    if 'username' not in session:
        return 'É preciso estar logado para pedir uma colaboração', 401

    video_id = request.form.get('video_id')
    channel = request.form.get('channel')
    name = request.form.get('name')
    role = request.form.get('role')
    username_form = request.form.get('username')  # optional

    if not all([video_id, channel, name, role]):
        return 'Dados incompletos', 400

    conn = get_db()
    c = conn.cursor()

    vid = get_video(video_id)
    title = vid.get('title') if vid else "Título desconhecido"

    c.execute("INSERT INTO collabs (video_id, video_title, channel, name, role, status) VALUES (?, ?, ?, ?, ?, ?)",
              (video_id, title, channel, name, role, "pedido"))

    conn.commit()
    conn.close()

    return 'Pedido de colaboração registrado com sucesso'

@studio_app.route('/studio/<username>/posts', methods=['GET', 'POST'])
@dono_do_canal
def studio_posts(username):
    conn = get_db()
    c = conn.cursor()

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'create':
            title = request.form.get('title')
            content = request.form.get('content')
            date = datetime.now().strftime("%d/%m/%Y")
            post_id = str(uuid.uuid4())[:8]
            c.execute("INSERT INTO posts (id, channel, title, content, date) VALUES (?, ?, ?, ?, ?)",
                      (post_id, username, title, content, date))
        elif action == 'delete':
            post_id = request.form.get('post_id')
            c.execute("DELETE FROM posts WHERE id = ?", (post_id,))
        conn.commit()

    c.execute("SELECT id, title, content, date FROM posts WHERE channel = ?", (username,))
    posts = [dict(r) for r in c.fetchall()]
    conn.close()

    return render_template('studio_posts.html', username=username, posts=posts)

@studio_app.route('/delete_video/<video_id>', methods=['POST'])
@dono_do_video
def delete_video(video_id):
    video = get_video(video_id)
    if not video:
        return "Vídeo não encontrado", 404

    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM videos WHERE id = ?", (str(video_id),))
    conn.commit()
    conn.close()

    for fname in [video.get('filename'),
                  video.get('filename_144p'),
                  video.get('filename_360p'),
                  video.get('filename_480p')]:
        if fname:
            path = os.path.join(UPLOAD_FOLDER, fname)
            if os.path.exists(path):
                os.remove(path)

    channel = video.get('channel', '')
    return redirect(url_for('studio', username=channel))

@studio_app.route('/api/collab/gerenciar', methods=['POST'])
def api_gerenciar_collab():
    if 'username' not in session:
        return jsonify({'error': 'Login necessário'}), 401

    action = request.form.get('action')
    collab_id = request.form.get('collab_id')

    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT channel FROM collabs WHERE id = ?", (collab_id,))
    row = c.fetchone()

    # Bug corrigido: antes comparava com uma variável 'username' que nunca
    # tinha sido definida (sempre dava erro). Agora usa quem está logado.
    if not row or row['channel'] != session['username']:
        conn.close()
        return jsonify({'error': 'Acesso negado ou collab não encontrada'}), 403

    if action == 'aceitar':
        c.execute("UPDATE collabs SET status = 'aceito' WHERE id = ?", (collab_id,))
    elif action in ['rejeitar', 'remover']:
        c.execute("DELETE FROM collabs WHERE id = ?", (collab_id,))

    conn.commit()
    conn.close()

    return redirect(url_for('gerenciar_collabs', username=session['username']))

@studio_app.route('/studio/<username>/collabs')
@dono_do_canal
def gerenciar_collabs(username):
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT * FROM collabs 
        WHERE channel = ? 
        ORDER BY status DESC, id DESC
    """, (username,))
    all_collabs = [dict(r) for r in c.fetchall()]
    conn.close()

    pedidos = [c for c in all_collabs if c['status'] == 'pedido']
    ativos = [c for c in all_collabs if c['status'] == 'aceito']

    return render_template("collabs.html", username=username, pedidos=pedidos, ativos=ativos)

@studio_app.route('/studio/<username>/upload_banner', methods=['POST'])
@dono_do_canal
def upload_banner(username):
    ch = get_channel_info(username)
    if not ch:
        return jsonify({'error': 'Canal não encontrado'}), 404

    banner = request.files.get('banner')
    if not banner or banner.filename == '':
        return jsonify({'error': 'Nenhum arquivo enviado'}), 400

    ext = banner.filename.rsplit('.', 1)[-1].lower() if '.' in banner.filename else ''
    if ext not in {'jpg', 'jpeg', 'png', 'webp', 'gif'}:
        return jsonify({'error': 'Formato inválido. Use jpg, png, webp ou gif.'}), 400

    banner_name = f"banner_{username}_{uuid.uuid4().hex[:6]}.{ext}"
    banner_path = os.path.join(BANNERS_FOLDER, banner_name)
    banner.save(banner_path)

    # Remove o banner antigo do disco pra não acumular lixo
    banner_antigo = ch.get('banner_path')
    if banner_antigo:
        caminho_antigo = os.path.join(BANNERS_FOLDER, banner_antigo)
        if os.path.exists(caminho_antigo):
            try:
                os.remove(caminho_antigo)
            except OSError:
                pass

    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE channels SET banner_path = ? WHERE username = ?",
              (banner_name, username))
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'banner': banner_name})


@studio_app.route('/studio/<username>/remover_banner', methods=['POST'])
@dono_do_canal
def remover_banner(username):
    ch = get_channel_info(username)
    if not ch:
        return jsonify({'error': 'Canal não encontrado'}), 404

    banner_antigo = ch.get('banner_path')
    if banner_antigo:
        caminho_antigo = os.path.join(BANNERS_FOLDER, banner_antigo)
        if os.path.exists(caminho_antigo):
            try:
                os.remove(caminho_antigo)
            except OSError:
                pass

    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE channels SET banner_path = NULL WHERE username = ?", (username,))
    conn.commit()
    conn.close()

    return jsonify({'success': True})


# ---------- Editar vídeo (dentro do Studio, não mais na página do player) ----------
def _parse_cards(texto_cards):
    """Formato esperado, uma linha por card: 'video_id | tempo_em_segundos'.
    O título e a miniatura do card vêm automaticamente do vídeo referenciado
    (assim nunca ficam desatualizados). IDs inválidos ou de vídeos que não
    existem são simplesmente ignorados."""
    cards = []
    if not texto_cards:
        return cards
    for linha in texto_cards.strip().splitlines():
        linha = linha.strip()
        if not linha:
            continue
        partes = linha.split('|')
        video_id_ref = partes[0].strip()
        try:
            tempo = int(partes[1].strip()) if len(partes) > 1 and partes[1].strip() else 0
        except ValueError:
            tempo = 0

        alvo = get_video(video_id_ref)
        if not alvo:
            continue  # ignora referência quebrada

        cards.append({
            'video_id': alvo['id'],
            'title': alvo.get('title', ''),
            'thumb': alvo.get('thumb', ''),
            'time': max(0, tempo),
        })
        if len(cards) >= 5:  # limite razoável de cards por vídeo
            break
    return cards


def _cards_para_texto(cards):
    """Converte a lista de cards salva no banco de volta pro formato de
    texto editável (usado pra pré-preencher o textarea na hora de editar)."""
    linhas = [f"{c.get('video_id','')} | {c.get('time', 0)}" for c in (cards or [])]
    return "\n".join(linhas)


@studio_app.route('/studio/<username>/editar-video/<video_id>', methods=['GET', 'POST'])
@dono_do_canal
def editar_video(username, video_id):
    video = get_video(video_id)
    if not video:
        return "Vídeo não encontrado", 404
    if video.get('channel') != username:
        return "Esse vídeo não pertence a este canal", 403

    if request.method == 'POST':
        video['title'] = request.form.get('title', video.get('title'))
        video['description'] = request.form.get('description', video.get('description'))
        video['chapters'] = request.form.get('chapters', video.get('chapters', ''))

        cards_texto = request.form.get('cards', '')
        video['cards'] = _parse_cards(cards_texto)

        subtitle_file = request.files.get('subtitle')
        if subtitle_file and subtitle_file.filename.endswith('.srt'):
            novo_nome = f"{uuid.uuid4().hex[:8]}_{secure_filename(subtitle_file.filename)}"
            subtitle_file.save(os.path.join(SUBTITLES_FOLDER, novo_nome))
            video['subtitle_file'] = novo_nome

        save_video_entry(video)
        return redirect(url_for('studio', username=username))

    video['cards_texto'] = _cards_para_texto(video.get('cards'))
    return render_template('editar_video.html', video=video, username=username)

if __name__ == '__main__':
    studio_app.run(host="0.0.0.0", port=7072, threaded=True, debug=True, ssl_context=('192.168.0.150.pem', '192.168.0.150-key.pem'))  # Porta separada para independência