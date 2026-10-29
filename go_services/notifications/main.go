// Serviço de notificações da conta do Clippy Videos, em Go.
//
// O Flask (app.py / studio.py) só avisa "aconteceu isso pra esse
// usuário" via POST /internal/notify -- quem grava, lista e empurra
// (push) em tempo real pro navegador é este serviço.
//
// Front-end (ver templates/index.html, o sino no canto superior
// direito):
//
//	GET  /api/notificacoes?token=...           lista + contagem de não lidas
//	POST /api/notificacoes/<id>/lida?token=...  marca uma como lida
//	GET  /ws/notificacoes?token=...             push em tempo real
//
// Servidor-a-servidor (Flask -> Go), autenticado por segredo
// compartilhado (ver go_shared_secret.txt, criado pelo app.py):
//
//	POST /internal/notify   { "username", "tipo", "texto", "link" }
//
// Sem dependências externas de propósito -- só a biblioteca padrão do
// Go (o WebSocket é implementado à mão em ws.go). Armazenamento: um
// arquivo JSON por usuário em CLIPPY_NOTIF_DATA_DIR, igual ao
// "users/<usuario>/configs.json" que o resto do projeto já usa.
//
// Uso:
//
//	cd go_services/notifications
//	go run .
//
// Variáveis de ambiente (mesmas convenções do serviço de chat, ver
// go_services/livechat/main.go): NOTIF_PORT, CLIPPY_NOTIF_DATA_DIR,
// CLIPPY_SHARED_SECRET_PATH, GO_TLS_CERT, GO_TLS_KEY
package main

import (
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
	"sort"
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
	dataDir      = envOr("CLIPPY_NOTIF_DATA_DIR", "notifications_data")
	secretPath   = envOr("CLIPPY_SHARED_SECRET_PATH", "go_shared_secret.txt")
	porta        = envOr("NOTIF_PORT", "7080")
	certFile     = os.Getenv("GO_TLS_CERT")
	keyFile      = os.Getenv("GO_TLS_KEY")
	segredoBytes []byte
	segredoStr   string
)

var nomeSeguroRe = regexp.MustCompile(`[^a-zA-Z0-9_\-]`)

func nomeSeguro(s string) string {
	s = nomeSeguroRe.ReplaceAllString(s, "_")
	if s == "" {
		s = "_"
	}
	return s
}

func carregarSegredo() {
	data, err := os.ReadFile(secretPath)
	if err != nil {
		log.Fatalf("não consegui ler o segredo compartilhado em %s (ele é criado pelo app.py na primeira vez que ele roda): %v", secretPath, err)
	}
	segredoStr = strings.TrimSpace(string(data))
	segredoBytes = []byte(segredoStr)
}

// validarToken confere a assinatura HMAC-SHA256 gerada por
// app.py:gerar_go_token() -- mesmo esquema usado pelo serviço de chat.
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

// ---------- Persistência (um arquivo JSON por usuário) ----------

type Notificacao struct {
	ID        int64  `json:"id"`
	Tipo      string `json:"tipo"`
	Texto     string `json:"texto"`
	Link      string `json:"link"`
	CreatedAt string `json:"created_at"`
	Lida      bool   `json:"lida"`
}

const maxPorUsuario = 200

var arquivosMu sync.Mutex // simples e suficiente para a escala de um projeto pessoal

func arquivoDoUsuario(username string) string {
	return filepath.Join(dataDir, nomeSeguro(username)+".json")
}

func carregarNotificacoes(username string) []Notificacao {
	data, err := os.ReadFile(arquivoDoUsuario(username))
	if err != nil {
		return nil
	}
	var lista []Notificacao
	if json.Unmarshal(data, &lista) != nil {
		return nil
	}
	return lista
}

func salvarNotificacoes(username string, lista []Notificacao) {
	data, err := json.Marshal(lista)
	if err != nil {
		return
	}
	os.WriteFile(arquivoDoUsuario(username), data, 0644)
}

func criarNotificacao(username, tipo, texto, link string) Notificacao {
	arquivosMu.Lock()
	defer arquivosMu.Unlock()

	n := Notificacao{
		ID:        time.Now().UnixNano(),
		Tipo:      tipo,
		Texto:     texto,
		Link:      link,
		CreatedAt: time.Now().UTC().Format(time.RFC3339),
		Lida:      false,
	}
	lista := carregarNotificacoes(username)
	lista = append(lista, n)
	if len(lista) > maxPorUsuario {
		lista = lista[len(lista)-maxPorUsuario:]
	}
	salvarNotificacoes(username, lista)
	return n
}

func listarNotificacoes(username string, limite int) ([]Notificacao, int) {
	arquivosMu.Lock()
	lista := carregarNotificacoes(username)
	arquivosMu.Unlock()

	// Mais recente primeiro.
	sort.Slice(lista, func(i, j int) bool { return lista[i].ID > lista[j].ID })

	naoLidas := 0
	for _, n := range lista {
		if !n.Lida {
			naoLidas++
		}
	}
	if len(lista) > limite {
		lista = lista[:limite]
	}
	return lista, naoLidas
}

func marcarComoLida(username string, id int64) bool {
	arquivosMu.Lock()
	defer arquivosMu.Unlock()

	lista := carregarNotificacoes(username)
	achou := false
	for i := range lista {
		if lista[i].ID == id {
			lista[i].Lida = true
			achou = true
			break
		}
	}
	if achou {
		salvarNotificacoes(username, lista)
	}
	return achou
}

// ---------- Conexões ativas (pra push em tempo real) ----------

type hub struct {
	mu    sync.Mutex
	conns map[string]map[*wsConn]bool // username -> conjunto de conexões
}

func (h *hub) registrar(username string, c *wsConn) {
	h.mu.Lock()
	defer h.mu.Unlock()
	if h.conns[username] == nil {
		h.conns[username] = make(map[*wsConn]bool)
	}
	h.conns[username][c] = true
}

func (h *hub) remover(username string, c *wsConn) {
	h.mu.Lock()
	defer h.mu.Unlock()
	delete(h.conns[username], c)
}

func (h *hub) empurrar(username string, n Notificacao) {
	h.mu.Lock()
	defer h.mu.Unlock()
	payload, _ := json.Marshal(n)
	for c := range h.conns[username] {
		c.WriteMessage(payload)
	}
}

var h = &hub{conns: make(map[string]map[*wsConn]bool)}

// ---------- HTTP handlers ----------

func comCORS(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, X-Internal-Secret")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
		if r.Method == http.MethodOptions {
			return
		}
		next(w, r)
	}
}

func handleListar(w http.ResponseWriter, r *http.Request) {
	username, ok := validarToken(r.URL.Query().Get("token"))
	if !ok {
		http.Error(w, `{"error":"token inválido"}`, http.StatusUnauthorized)
		return
	}
	lista, naoLidas := listarNotificacoes(username, 30)
	if lista == nil {
		lista = []Notificacao{}
	}
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]any{"notificacoes": lista, "nao_lidas": naoLidas})
}

func handleMarcarLida(w http.ResponseWriter, r *http.Request) {
	username, ok := validarToken(r.URL.Query().Get("token"))
	if !ok {
		http.Error(w, `{"error":"token inválido"}`, http.StatusUnauthorized)
		return
	}
	idStr := strings.TrimSuffix(strings.TrimPrefix(r.URL.Path, "/api/notificacoes/"), "/lida")
	id, err := strconv.ParseInt(idStr, 10, 64)
	if err != nil {
		http.Error(w, `{"error":"id inválido"}`, http.StatusBadRequest)
		return
	}
	ok = marcarComoLida(username, id)
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]bool{"ok": ok})
}

func handleWs(w http.ResponseWriter, r *http.Request) {
	username, ok := validarToken(r.URL.Query().Get("token"))
	if !ok {
		http.Error(w, "token inválido", http.StatusUnauthorized)
		return
	}
	conn, err := wsUpgrade(w, r)
	if err != nil {
		return
	}
	defer conn.Close()
	h.registrar(username, conn)
	defer h.remover(username, conn)
	// Só mantém a conexão viva; o push vem de handleInternalNotify.
	for {
		if _, err := conn.ReadMessage(); err != nil {
			break
		}
	}
}

type notifyPayload struct {
	Username string `json:"username"`
	Tipo     string `json:"tipo"`
	Texto    string `json:"texto"`
	Link     string `json:"link"`
}

func handleInternalNotify(w http.ResponseWriter, r *http.Request) {
	if r.Header.Get("X-Internal-Secret") != segredoStr {
		http.Error(w, "segredo inválido", http.StatusForbidden)
		return
	}
	var p notifyPayload
	if json.NewDecoder(r.Body).Decode(&p) != nil || p.Username == "" || p.Texto == "" {
		http.Error(w, "payload inválido", http.StatusBadRequest)
		return
	}
	n := criarNotificacao(p.Username, p.Tipo, p.Texto, p.Link)
	h.empurrar(p.Username, n)
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(n)
}

func main() {
	carregarSegredo()
	if err := os.MkdirAll(dataDir, 0755); err != nil {
		log.Fatalf("não consegui criar a pasta %s: %v", dataDir, err)
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/api/notificacoes", comCORS(handleListar))
	mux.HandleFunc("/api/notificacoes/", comCORS(handleMarcarLida))
	mux.HandleFunc("/ws/notificacoes", handleWs)
	mux.HandleFunc("/internal/notify", handleInternalNotify)
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte("clippy-notifications ok"))
	})

	addr := ":" + porta
	if certFile != "" && keyFile != "" {
		log.Printf("notificações em https://0.0.0.0%s (TLS)", addr)
		log.Fatal(http.ListenAndServeTLS(addr, certFile, keyFile, mux))
	} else {
		log.Printf("notificações em http://0.0.0.0%s (sem TLS -- defina GO_TLS_CERT/GO_TLS_KEY pra servir HTTPS direto)", addr)
		log.Fatal(http.ListenAndServe(addr, mux))
	}
}
