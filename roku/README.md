# Clippy Videos — canal Roku

Canal não-publicado (sideload) para assistir ao Clippy Videos na Roku TV: Início (Em alta / Recentes), Busca, tela de Canal e player de vídeo nativo com troca de qualidade.

## O que tem aqui

```
roku/
├── manifest                        # metadados do canal
├── source/
│   ├── Main.brs                     # entry point
│   ├── Config.brs                    # URL base da API (edite aqui!)
│   ├── Net.brs                       # helper de GET/JSON
│   └── Utils.brs                     # helpers compartilhados (grade de vídeos)
├── components/
│   ├── MainScene.xml/.brs            # tela raiz: TopBar + navegação entre telas
│   ├── TopBar.xml/.brs               # cabeçalho fixo com abas Início/Busca
│   ├── HomeView.xml/.brs             # grade "Em alta" / "Recentes"
│   ├── SearchView.xml/.brs           # teclado + resultados (vídeos e canais)
│   ├── ChannelView.xml/.brs          # cabeçalho do canal + grade de vídeos dele
│   ├── VideoItem.xml/.brs            # card de cada vídeo/canal na grade
│   ├── PlayerView.xml/.brs           # player de vídeo em tela cheia
│   ├── FetchVideosTask.*             # Task: busca /api/videos
│   ├── FetchVideoDetailTask.*        # Task: busca /api/video/<id>
│   ├── FetchSearchTask.*             # Task: busca /api/buscar
│   └── FetchChannelTask.*            # Task: busca /api/channel/<user>
└── images/                           # ícones e splash screen (placeholder)
```

## Navegação no controle remoto

- **Início/Busca**: seta pra CIMA a partir da grade leva de volta ao cabeçalho;
  ESQUERDA/DIREITA escolhe a aba, OK confirma, BAIXO volta pro conteúdo.
- **Grade de vídeos**: OK toca o vídeo; **OPÇÕES (★)** num card abre o canal
  de quem postou, sem precisar abrir o vídeo primeiro.
- **Busca**: digite no teclado (busca automática depois de 2 letras, com
  um pequeno atraso); BAIXO leva da última linha do teclado pros resultados.
- **Player**: OPÇÕES (★) alterna entre as qualidades disponíveis do vídeo
  (mantendo a posição); BAIXO foca o nome do canal (OK abre o canal, CIMA
  volta pro vídeo); VOLTAR fecha o player.
- **Canal**: grade com os vídeos daquele canal; VOLTAR retorna pra Início/Busca
  (a aba de onde você veio).

## Mudanças feitas no app Flask (`app.py`)

O app já tinha `/api/videos` (lista) e `/buscar` / `/@<username>` (páginas
HTML), mas nada em JSON com o nome real do arquivo de vídeo nem pra busca/
canal. Adicionei três endpoints, todos reaproveitando a mesma checagem de
classificação indicativa que `/api/videos` já fazia:

- **`GET /api/video/<video_id>`** — detalhe de um vídeo pro player: URL de
  stream resolvida, qualidades disponíveis, legenda, info do canal.
  ```json
  {
    "id": "...", "title": "...", "channel": "...",
    "stream_url": "https://.../uploads/arquivo.mp4",
    "qualities": [{"label": "Original", "url": "..."}, ...],
    "subtitle_url": "...", "is_360": false, "static_url": "..."
  }
  ```
- **`GET /api/buscar?q=...`** — busca por título/descrição de vídeo e por
  nome/bio de canal, devolvendo os dois num JSON só.
- **`GET /api/channel/<username>`** — cabeçalho do canal (nome, bio, foto,
  inscritos) + lista dos vídeos dele.

## ⚠️ Antes de instalar: o certificado autoassinado

`STATIC_SERVER_URL` no seu `app.py` aponta pra
`https://192.168.0.150:7071/`, com um certificado autoassinado
(`192.168.0.150.pem`). Isso dá problema de duas formas no canal Roku:

1. **Carregar listas/thumbnails** (`/api/videos`, `/api/buscar`, `/api/channel/<user>`,
   `/api/video/<id>`, pôsteres): contornado no `Net.brs` com
   `EnablePeerVerification(false)` / `EnableHostVerification(false)` —
   funciona normalmente.
2. **Tocar o vídeo de verdade**: o nó `Video` do SceneGraph usa o
   verificador de TLS do próprio sistema da Roku, que **não** tem como
   ser desligado via código. Com certificado autoassinado, alguns
   modelos/versões de firmware recusam o handshake e o player cai com
   erro de rede.

**Duas opções:**

- **Mesma rede local (dev/teste rápido)**: deixe `Config.brs` como está
  (`https://192.168.0.150`). Funciona bem pra listas, busca, canal e
  thumbnails; se só o player de vídeo falhar com erro de conexão, é esse
  o motivo.
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

## Limitações atuais

- Shorts, histórico, comentários e chat continuam de fora — o foco é
  puro consumo de vídeo (Início, Busca, Canal, Player).
- A navegação do teclado de busca pro grid de resultados usa o
  comportamento padrão de "a tecla direcional sobe pro componente pai
  quando não há mais pra onde ir" do SceneGraph — na prática funciona,
  mas pode variar um pouco entre modelos/firmwares de Roku.
- Legendas: se o vídeo tiver `.srt` associado, o player tenta carregar
  — não testado a fundo com o formato esperado pelo nó `Subtitle` da
  Roku (idealmente WebVTT; `.srt` pode não renderizar em todo firmware).
- Vídeos 360°: o player mostra um selo "360°" (campo `is_360` da API),
  mas ainda toca "achatado" — a projeção esférica de verdade exigiria
  desenhar em 3D (dá pra fazer depois com um `Scene3D`/shader próprio).
- Ícones e splash screen são placeholders gerados automaticamente — troque
  os arquivos em `images/` pela identidade visual real do Clippy Videos
  quando quiser.
