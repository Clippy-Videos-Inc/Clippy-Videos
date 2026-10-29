# Serviços em Go do Clippy Videos

Dois processos novos, em Go, seguindo o mesmo padrão dos outros
serviços do projeto (`static` na 7071, `studio` na 7072, `auth_server`
na 7075): cada um roda sozinho, na sua porta, e conversa com o
Flask só por HTTP.

- **`livechat/`** — chat ao vivo, um WebSocket por `live_id`. Porta
  padrão **7079**.
- **`notifications/`** — notificações da conta (sino no canto superior
  direito da página inicial). Porta padrão **7080**.

Os dois são **zero-dependência**: só a biblioteca padrão do Go,
inclusive o WebSocket (implementado à mão em `ws.go` de cada pasta,
porque baixar `gorilla/websocket` exigiria acesso à internet durante o
build em alguns ambientes restritos). Então rodar é só:

```bash
cd go_services/livechat && go run .
cd go_services/notifications && go run .
```

Sem `go mod tidy`, sem internet, sem CGO.

## Como a autenticação funciona

O Flask já guarda quem está logado no cookie de sessão de sempre. Em
vez de reimplementar o parsing desse cookie em Go, o Flask assina um
**token curto** (usuário + validade + HMAC-SHA256) com um segredo
compartilhado, e o Go só confere a assinatura:

- `GET /api/go-token` (no `app.py`) devolve esse token pro usuário
  logado -- é o que o JavaScript do site busca antes de abrir o
  WebSocket.
- O segredo fica em **`go_shared_secret.txt`**, na raiz do projeto
  (mesmo nível de `app.py`). O `app.py` cria esse arquivo sozinho (com
  um valor aleatório) na primeira vez que roda -- não precisa criar
  manualmente. Os dois serviços em Go e o `studio.py` leem esse mesmo
  arquivo.
- **Rode os dois serviços Go a partir da raiz do projeto** (ou aponte
  `CLIPPY_SHARED_SECRET_PATH` pro caminho certo), senão eles não vão
  achar o `go_shared_secret.txt` que o Flask gerou.

Esse é o mesmo esquema que o `cluster.py` já usa pra autenticar
servidores entre si (HMAC com segredo compartilhado) -- só que aqui é
pra autenticar o *usuário*, não o servidor.

## Armazenamento

Nenhum dos dois toca o `app.db` (SQLite) do Flask -- cada um guarda os
próprios dados em arquivos texto, do mesmo jeito que o resto do
projeto já guarda coisas tipo `users/<usuario>/configs.json` ou
`channels/@<usuario>/info.txt`:

- `live_chat_data/<live_id>.jsonl` — histórico de cada live (uma
  mensagem por linha).
- `notifications_data/<usuario>.json` — notificações de cada usuário
  (lista com até 200 entradas, as mais antigas vão caindo fora).

Essas pastas são criadas sozinhas na primeira vez que cada serviço
roda.

## Variáveis de ambiente

Nenhuma é obrigatória -- os padrões já funcionam rodando os serviços a
partir da raiz do projeto.

| Variável                    | Serviço        | Padrão                 |
|------------------------------|-----------------|------------------------|
| `LIVECHAT_PORT`               | livechat        | `7079`                 |
| `NOTIF_PORT`                  | notifications   | `7080`                 |
| `CLIPPY_LIVECHAT_DATA_DIR`    | livechat        | `live_chat_data`       |
| `CLIPPY_NOTIF_DATA_DIR`       | notifications   | `notifications_data`   |
| `CLIPPY_SHARED_SECRET_PATH`   | ambos           | `go_shared_secret.txt` |
| `GO_TLS_CERT` / `GO_TLS_KEY`  | ambos           | *(vazio = HTTP puro)*  |
| `GO_NOTIFICATIONS_INTERNAL_URL` | Flask (env, não Go) | `http://127.0.0.1:7080/` |

Por padrão os dois sobem em HTTP puro -- isso é intencional pra testar
local sem complicação. Pra produção, defina `GO_TLS_CERT`/`GO_TLS_KEY`
apontando pra um dos certificados que o projeto já usa (ex:
`192.168.0.150.pem` / `192.168.0.150-key.pem`) e o `app.py` já aponta
o front-end pra `https://192.168.0.150:7079/` e `:7080/` (ver
`GO_LIVECHAT_URL` / `GO_NOTIFICATIONS_URL` no topo do `app.py`).

Se o Flask e os dois serviços Go rodarem em máquinas diferentes, troque
`GO_NOTIFICATIONS_INTERNAL_URL` pra URL pública do serviço de
notificações (variável de ambiente do processo Flask/Waitress, não do
Go).

## O que cada um expõe

### `livechat` (porta 7079)

- `GET /ws/live/<live_id>?token=...` — WebSocket. Sem `token`, a
  conexão é só leitura (dá pra assistir o chat sem estar logado); com
  um token válido, dá pra mandar mensagem também. Ao conectar, o
  servidor manda o histórico recente (`{"tipo":"historico", ...}`) e
  depois empurra cada mensagem nova (`{"tipo":"mensagem", ...}`).

### `notifications` (porta 7080)

- `GET /api/notificacoes?token=...` — lista as últimas 30 notificações
  do usuário + quantas não foram lidas.
- `POST /api/notificacoes/<id>/lida?token=...` — marca uma como lida.
- `GET /ws/notificacoes?token=...` — WebSocket, só recebe (push) as
  notificações novas em tempo real.
- `POST /internal/notify` (com header `X-Internal-Secret: <segredo>`)
  — usado pelo Flask (`notificar_usuario()` em `app.py`,
  `notificar_inscritos_novo_video()` em `studio.py`) pra criar uma
  notificação nova. Não é pra ser chamado pelo navegador.

## Quando o Flask dispara uma notificação

- Alguém se inscreve no seu canal (`app.py: inscrever()`).
- Um canal que você segue entra ao vivo (`app.py: api_live_create()`).
- Um canal que você segue publica vídeo novo
  (`studio.py: upload_video()` e `studio_mobile_upload()`).

Todas essas chamadas são "fire and forget" (best-effort): se o serviço
de notificações estiver fora do ar, o Flask só loga no console e segue
em frente -- nunca trava um upload ou uma inscrição por causa disso.
