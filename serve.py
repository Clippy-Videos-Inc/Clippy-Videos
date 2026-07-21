"""
Servidor de PRODUÇÃO do Clippy Videos, usando Waitress.

Por quê Waitress e não `python app.py`?
- app.run() é o servidor de desenvolvimento do Flask: não foi feito pra
  aguentar tráfego real nem hostil, e com debug=True é um risco de
  segurança grave se ficar exposto.
- Waitress é um servidor WSGI de produção, funciona bem no Windows
  (diferente do Gunicorn, que é só Linux) e é simples de configurar.

Como isso se encaixa com o Nginx:
    internet ---HTTPS(443)---> Nginx ---HTTP(127.0.0.1:8000)---> Waitress/Flask

O Waitress só escuta em 127.0.0.1 (localhost) -- ele NUNCA deve ser
acessível diretamente da internet. Só o Nginx fala com ele. Por isso é
importante também bloquear a porta 8000 no Firewall do Windows para
qualquer coisa que não seja localhost (veja instruções no final do
nginx.conf).

Uso:
    pip install waitress
    python serve.py
"""

from waitress import serve
from app import app

if __name__ == '__main__':
    serve(
        app,
        host='127.0.0.1',
        port=8000,
        threads=2,              # ajuste conforme os núcleos da sua CPU
        connection_limit=1000,
        channel_timeout=180,    # generoso por causa dos uploads grandes (até 5GB)
        cleanup_interval=30,
        max_request_body_size=5 * 1024 * 1024 * 1024,  # 5GB, mesmo limite do Flask
        ident='ClippyVideos',   # não expõe versão do Waitress no header Server
    )