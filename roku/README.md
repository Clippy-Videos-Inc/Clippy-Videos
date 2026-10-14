# Clippy Videos — canal Roku

Canal não-publicado (sideload) para assistir ao Clippy Videos na Roku TV: tela inicial com "Em alta" / "Recentes" e player de vídeo nativo.

## O que tem aqui

```
roku/
├── manifest                    # metadados do canal
├── source/
│   ├── Main.brs                 # entry point
│   ├── Config.brs                # URL base da API (edite aqui!)
│   └── Net.brs                   # helper de GET/JSON
├── components/
│   ├── MainScene.xml/.brs        # tela raiz, alterna Home <-> Player
│   ├── HomeView.xml/.brs         # grade "Em alta" / "Recentes"
│   ├── VideoItem.xml/.brs        # card de cada vídeo na grade
│   ├── PlayerView.xml/.brs       # player de vídeo em tela cheia
│   ├── FetchVideosTask.*         # Task: busca /api/videos
│   └── FetchVideoDetailTask.*    # Task: busca /api/video/<id>
└── images/                       # ícones e splash screen (placeholder)
```

## Mudanças feitas no app Flask (`app.py`)

Adicionei o endpoint `GET /api/video/<video_id>`, que o canal Roku usa para
abrir o player (o `/api/videos` que já existia só manda id/título/views/
thumb — não tinha o nome do arquivo de vídeo). Ele devolve:

```json
{
  "id": "...", "title": "...", "channel": "...",
  "stream_url": "https://.../uploads/arquivo.mp4",
  "qualities": [{"label": "Original", "url": "..."}, ...],
  "subtitle_url": "...", "thumb": "...", "static_url": "..."
}
```

Respeita a mesma checagem de classificação indicativa que o `/api/videos`
já fazia (devolve 403 se o vídeo for bloqueado pra conta logada — como o
canal Roku não faz login, isso vale pro limite padrão `'18'`).

## ⚠️ Antes de instalar: o certificado autoassinado

`STATIC_SERVER_URL` no seu `app.py` aponta pra
`https://192.168.0.150:7071/`, com um certificado autoassinado
(`192.168.0.150.pem`). Isso dá problema de duas formas no canal Roku:

1. **Carregar a lista de vídeos** (`/api/videos`, `/api/video/<id>`): eu
   já contornei isso no `Net.brs` com
   `EnablePeerVerification(false)` / `EnableHostVerification(false)` —
   funciona normalmente.
2. **Tocar o vídeo de verdade**: o nó `Video` do SceneGraph usa o
   verificador de TLS do próprio sistema da Roku, que **não** tem como
   ser desligado via código. Com certificado autoassinado, alguns
   modelos/versões de firmware recusam o handshake e o player cai com
   erro de rede.

**Duas opções:**

- **Mesma rede local (dev/teste rápido)**: deixe `Config.brs` como está
  (`https://192.168.0.150`). Funciona bem para a lista e os thumbnails;
  se o player de vídeo falhar com erro de conexão, é esse o motivo.
- **Produção (recomendado)**: troque a URL em `roku/source/Config.brs`
  para o domínio do Fly.io que já está no `fly.toml`
  (`https://play-videos.fly.dev`), que tem certificado válido e funciona
  em qualquer Roku, em qualquer rede:

  ```brightscript
  function ApiBaseUrl() as String
      return "https://play-videos.fly.dev"
  end function
  ```

  (A Roku também precisa estar na mesma rede do seu PC pra usar o IP
  local de qualquer forma, então pra assistir fora de casa o domínio
  público é obrigatório.)

## Como instalar no seu Roku (sideload / Developer Mode)

1. Na Roku TV: **Configurações → Sistema → Avançado → Modo desenvolvedor
   ativado** (ou aperte, no controle, na sequência: Início 3x, Cima 2x,
   Voltar, Avançar, Voltar, Avançar, Voltar). Anote o IP mostrado na tela.
2. No navegador do seu PC (mesma rede), acesse `http://<IP-DA-ROKU>`.
   Crie usuário/senha de desenvolvedor na primeira vez.
3. Edite `roku/source/Config.brs` se quiser mudar a URL da API (veja
   acima).
4. Compacte a **pasta `roku/`** em um `.zip` (manifest precisa estar na
   raiz do zip, não dentro de uma subpasta) — ou use o arquivo já
   empacotado que te mandei.
5. Na página do installer da Roku, envie esse `.zip` em "Upload".
   O canal "Clippy Videos" aparece na tela inicial da Roku.

## Limitações desta primeira versão

- Só tem Início (Em alta / Recentes) + Player — sem busca, canais,
  shorts, histórico, comentários ou chat (puro consumo de vídeo).
- Legendas: se o vídeo tiver `.srt` associado, o player tenta carregar
  — não testado a fundo com o formato do Roku (`Subtitle` node espera
  WebVTT/SRT; se der problema, me avisa que eu ajusto).
- Vídeos 360°: o campo `is_360` já vem na resposta da API, mas o player
  ainda não faz a projeção esférica (isso exigiria desenhar em 3D, o que
  dá pra fazer depois com um `Scene3D`/shader próprio).
- Ícones e splash screen são placeholders gerados automaticamente — troque
  os arquivos em `images/` pela identidade visual real do Clippy Videos
  quando quiser.
