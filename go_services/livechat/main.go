// Serviço de chat ao vivo do Clippy Videos, em Go.
//
// Um WebSocket por live_id: todo mundo que entra em /ws/live/<live_id>
// recebe o histórico recente e qualquer mensagem nova em tempo real.
// Ver assistir é livre (sem login); para ENVIAR mensagem é preciso um
// token válido, emitido pelo Flask em GET /api/go-token (o usuário
// logado no site principal). O token é validado aqui sem precisar
// reimplementar o cookie de sessão do Flask -- é só um HMAC-SHA256
// compartilhado (mesmo esquema que cluster.py já usa entre servidores
// do próprio projeto).
//
// Sem dependências externas de propósito: só a biblioteca padrão do Go
// (inclusive o WebSocket, implementado à mão em ws.go -- ver esse
// arquivo pra detalhes). Isso evita precisar de "go mod tidy" baixando
// pacote de internet pra rodar o serviço -- só "go run .".
//
// Armazenamento: cada live tem um arquivo texto (JSON Lines, uma
// mensagem por linha) em CLIPPY_LIVECHAT_DATA_DIR -- mesma ideia das
// pastas "channels/@usuario" e "users/usuario" que o resto do projeto
// já usa, só que pra mensagens de chat em vez de perfil.
//
// Uso:
//
//	cd go_services/livechat
//	go run .
//
// Variáveis de ambiente (todas opcionais, com um padrão razoável):
//
//	LIVECHAT_PORT             porta HTTP/WS (padrão 7079)
//	CLIPPY_LIVECHAT_DATA_DIR  pasta onde o histórico de cada live fica
//	                          salvo (padrão "live_chat_data", criada do
//	                          lado da raiz do projeto se rodar de lá)
//	CLIPPY_SHARED_SECRET_PATH caminho do go_shared_secret.txt (padrão
//	                          "go_shared_secret.txt" -- o mesmo arquivo que
//	                          o app.py cria sozinho na primeira vez que roda)
//	GO_TLS_CERT / GO_TLS_KEY  caminho dos certificados, se quiser servir
//	                          HTTPS/WSS direto (igual aos outros serviços
//	                          do projeto, ex: 192.168.0.150.pem). Sem isso,
//	                          roda em HTTP puro -- ok pra rodar atrás de
//	                          um proxy reverso que termina o TLS.
package main

import (
	"bufio"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"
)

// ---------- Config ----------

func envOr(chave, padrao string) string {
	if v := os.Getenv(chave); v != "" {
		return v
	}
	return padrao
}

var (
	dataDir      = envOr("CLIPPY_LIVECHAT_DATA_DIR", "live_chat_data")
	secretPath   = envOr("CLIPPY_SHARED_SECRET_PATH", "go_shared_secret.txt")
	porta        = envOr("LIVECHAT_PORT", "7079")
	certFile     = os.Getenv("GO_TLS_CERT")
	keyFile      = os.Getenv("GO_TLS_KEY")
	segredoBytes []byte
)

var nomeSeguroRe = regexp.MustCompile(`[^a-zA-Z0-9_\-]`)

func nomeSeguro(s string) string {
	s = nomeSeguroRe.ReplaceAllString(s, "_")
	if s == "" {
		s = "_"
	}
	return s
}

func carregarSegredo() []byte {
	data, err := os.ReadFile(secretPath)
	if err != nil {
		log.Fatalf("não consegui ler o segredo compartilhado em %s (ele é criado pelo app.py na primeira vez que ele roda): %v", secretPath, err)
	}
	return []byte(strings.TrimSpace(string(data)))
}

// validarToken confere a assinatura HMAC-SHA256 gerada por
// app.py:gerar_go_token() e devolve o username se o token for válido
// e ainda não tiver expirado.
func validarToken(token string) (string, bool) {
	if token == "" {
		return "", false
	}
	partes := strings.SplitN(token, ".", 2)
	if len(partes) != 2 {
		return "", false
	}
	payloadBytes, err := base64.URLEncoding.DecodeString(partes[0])
	if err != nil {
		return "", false
	}
	mac := hmac.New(sha256.New, segredoBytes)
	mac.Write(payloadBytes)
	esperado := hex.EncodeToString(mac.Sum(nil))
	if !hmac.Equal([]byte(esperado), []byte(partes[1])) {
		return "", false
	}
	payload := string(payloadBytes)
	idx := strings.LastIndex(payload, ".")
	if idx < 0 {
		return "", false
	}
	username, expiraStr := payload[:idx], payload[idx+1:]
	expira, err := strconv.ParseInt(expiraStr, 10, 64)
	if err != nil || time.Now().Unix() > expira || username == "" {
		return "", false
	}
	return username, true
}

// ---------- Persistência (um arquivo JSON Lines por live) ----------

type MensagemChat struct {
	Tipo      string `json:"tipo"`
	Username  string `json:"username,omitempty"`
	Texto     string `json:"texto"`
	CreatedAt string `json:"created_at,omitempty"`
}

var arquivosMu sync.Mutex // simples e suficiente para a escala de um projeto pessoal

func arquivoDaLive(liveID string) string {
	return filepath.Join(dataDir, nomeSeguro(liveID)+".jsonl")
}

func salvarMensagem(liveID, username, texto string) MensagemChat {
	m := MensagemChat{Tipo: "mensagem", Username: username, Texto: texto, CreatedAt: time.Now().UTC().Format(time.RFC3339)}

	arquivosMu.Lock()
	defer arquivosMu.Unlock()
	f, err := os.OpenFile(arquivoDaLive(liveID), os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err != nil {
		log.Println("não consegui gravar mensagem de chat:", err)
		return m
	}
	defer f.Close()
	linha, _ := json.Marshal(m)
	f.Write(linha)
	f.Write([]byte("\n"))
	return m
}

func historico(liveID string, limite int) []MensagemChat {
	arquivosMu.Lock()
	defer arquivosMu.Unlock()

	f, err := os.Open(arquivoDaLive(liveID))
	if err != nil {
		return nil
	}
	defer f.Close()

	var todas []MensagemChat
	scanner := bufio.NewScanner(f)
	scanner.Buffer(make([]byte, 0, 64*1024), 1024*1024)
	for scanner.Scan() {
		var m MensagemChat
		if json.Unmarshal(scanner.Bytes(), &m) == nil {
			todas = append(todas, m)
		}
	}
	if len(todas) > limite {
		todas = todas[len(todas)-limite:]
	}
	return todas
}

// ---------- Salas (hub) ----------

type sala struct {
	mu      sync.Mutex
	clients map[*wsConn]bool
}

type hub struct {
	mu    sync.Mutex
	salas map[string]*sala
}

func (h *hub) salaDe(liveID string) *sala {
	h.mu.Lock()
	defer h.mu.Unlock()
	s, ok := h.salas[liveID]
	if !ok {
		s = &sala{clients: make(map[*wsConn]bool)}
		h.salas[liveID] = s
	}
	return s
}

func (s *sala) entrar(c *wsConn) {
	s.mu.Lock()
	s.clients[c] = true
	s.mu.Unlock()
}

func (s *sala) sair(c *wsConn) {
	s.mu.Lock()
	delete(s.clients, c)
	s.mu.Unlock()
}

func (s *sala) broadcast(msg MensagemChat) {
	payload, _ := json.Marshal(msg)
	s.mu.Lock()
	defer s.mu.Unlock()
	for c := range s.clients {
		c.WriteMessage(payload)
	}
}

var h = &hub{salas: make(map[string]*sala)}

type mensagemRecebida struct {
	Texto string `json:"texto"`
}

func wsLiveHandler(w http.ResponseWriter, r *http.Request) {
	liveID := strings.TrimPrefix(r.URL.Path, "/ws/live/")
	if liveID == "" {
		http.Error(w, "live_id ausente", http.StatusBadRequest)
		return
	}
	username, _ := validarToken(r.URL.Query().Get("token")) // "" = somente leitura

	conn, err := wsUpgrade(w, r)
	if err != nil {
		log.Println("upgrade de websocket falhou:", err)
		return
	}
	defer conn.Close()

	s := h.salaDe(liveID)
	s.entrar(conn)
	defer s.sair(conn)

	// Histórico recente ao entrar.
	hist := historico(liveID, 50)
	if hist == nil {
		hist = []MensagemChat{}
	}
	payload, _ := json.Marshal(map[string]any{"tipo": "historico", "mensagens": hist})
	conn.WriteMessage(payload)

	for {
		raw, err := conn.ReadMessage()
		if err != nil {
			break
		}
		if username == "" {
			// Conexão somente leitura -- ignora qualquer tentativa de envio.
			continue
		}
		var m mensagemRecebida
		if json.Unmarshal(raw, &m) != nil {
			continue
		}
		texto := strings.TrimSpace(m.Texto)
		if texto == "" {
			continue
		}
		if len(texto) > 500 {
			texto = texto[:500]
		}
		msg := salvarMensagem(liveID, username, texto)
		s.broadcast(msg)
	}
}

func main() {
	segredoBytes = carregarSegredo()
	if err := os.MkdirAll(dataDir, 0755); err != nil {
		log.Fatalf("não consegui criar a pasta %s: %v", dataDir, err)
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/ws/live/", wsLiveHandler)
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte("clippy-livechat ok"))
	})

	addr := ":" + porta
	if certFile != "" && keyFile != "" {
		log.Printf("chat ao vivo em https://0.0.0.0%s (TLS)", addr)
		log.Fatal(http.ListenAndServeTLS(addr, certFile, keyFile, mux))
	} else {
		log.Printf("chat ao vivo em http://0.0.0.0%s (sem TLS -- defina GO_TLS_CERT/GO_TLS_KEY pra servir HTTPS direto)", addr)
		log.Fatal(http.ListenAndServe(addr, mux))
	}
}
