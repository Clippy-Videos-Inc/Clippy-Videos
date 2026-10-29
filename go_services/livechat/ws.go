// Implementação mínima de WebSocket (RFC 6455) usando só a biblioteca
// padrão do Go -- sem depender de pacote nenhum de fora, pra não
// precisar de "go mod tidy" baixando coisa da internet só pra rodar
// este serviço. Suporta o necessário pra esse projeto: handshake,
// frames de texto não-fragmentados (nossas mensagens são sempre JSON
// pequeno, então isso nunca é um problema na prática), e responde
// ping com pong.
package main

import (
	"bufio"
	"crypto/sha1"
	"encoding/base64"
	"encoding/binary"
	"errors"
	"io"
	"net"
	"net/http"
	"strings"
)

const wsMagic = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

type wsConn struct {
	rw   *bufio.ReadWriter
	conn net.Conn
}

// wsUpgrade faz o handshake HTTP -> WebSocket e devolve a conexão já
// "sequestrada" (hijacked) do http.ResponseWriter.
func wsUpgrade(w http.ResponseWriter, r *http.Request) (*wsConn, error) {
	if !strings.EqualFold(r.Header.Get("Upgrade"), "websocket") {
		return nil, errors.New("requisição não é um upgrade pra websocket")
	}
	key := r.Header.Get("Sec-WebSocket-Key")
	if key == "" {
		return nil, errors.New("faltando Sec-WebSocket-Key")
	}
	soma := sha1.Sum([]byte(key + wsMagic))
	accept := base64.StdEncoding.EncodeToString(soma[:])

	hj, ok := w.(http.Hijacker)
	if !ok {
		return nil, errors.New("servidor não suporta hijack")
	}
	conn, rw, err := hj.Hijack()
	if err != nil {
		return nil, err
	}
	resp := "HTTP/1.1 101 Switching Protocols\r\n" +
		"Upgrade: websocket\r\n" +
		"Connection: Upgrade\r\n" +
		"Sec-WebSocket-Accept: " + accept + "\r\n\r\n"
	if _, err := rw.WriteString(resp); err != nil {
		conn.Close()
		return nil, err
	}
	if err := rw.Flush(); err != nil {
		conn.Close()
		return nil, err
	}
	return &wsConn{rw: rw, conn: conn}, nil
}

func (c *wsConn) Close() error { return c.conn.Close() }

// ReadMessage lê um frame de texto/binário (não-fragmentado) do
// cliente e devolve o payload cru. Frames de controle (ping/close) são
// tratados por baixo dos panos.
func (c *wsConn) ReadMessage() ([]byte, error) {
	for {
		header := make([]byte, 2)
		if _, err := io.ReadFull(c.rw, header); err != nil {
			return nil, err
		}
		fin := header[0]&0x80 != 0
		opcode := header[0] & 0x0F
		masked := header[1]&0x80 != 0
		payloadLen := int64(header[1] & 0x7F)

		switch payloadLen {
		case 126:
			ext := make([]byte, 2)
			if _, err := io.ReadFull(c.rw, ext); err != nil {
				return nil, err
			}
			payloadLen = int64(binary.BigEndian.Uint16(ext))
		case 127:
			ext := make([]byte, 8)
			if _, err := io.ReadFull(c.rw, ext); err != nil {
				return nil, err
			}
			payloadLen = int64(binary.BigEndian.Uint64(ext))
		}

		var maskKey [4]byte
		if masked {
			if _, err := io.ReadFull(c.rw, maskKey[:]); err != nil {
				return nil, err
			}
		}

		if payloadLen > 1<<20 { // 1MB de teto de segurança
			return nil, errors.New("mensagem grande demais")
		}
		payload := make([]byte, payloadLen)
		if _, err := io.ReadFull(c.rw, payload); err != nil {
			return nil, err
		}
		if masked {
			for i := range payload {
				payload[i] ^= maskKey[i%4]
			}
		}

		switch opcode {
		case 0x8: // close
			return nil, io.EOF
		case 0x9: // ping -> responde pong e continua esperando dado de verdade
			c.writeFrame(0xA, payload)
			continue
		case 0xA: // pong
			continue
		case 0x1, 0x2: // texto / binário
			if !fin {
				return nil, errors.New("frames fragmentados não são suportados")
			}
			return payload, nil
		default:
			continue
		}
	}
}

func (c *wsConn) writeFrame(opcode byte, payload []byte) error {
	var header []byte
	n := len(payload)
	switch {
	case n <= 125:
		header = []byte{0x80 | opcode, byte(n)}
	case n <= 65535:
		header = []byte{0x80 | opcode, 126, 0, 0}
		binary.BigEndian.PutUint16(header[2:], uint16(n))
	default:
		header = make([]byte, 10)
		header[0] = 0x80 | opcode
		header[1] = 127
		binary.BigEndian.PutUint64(header[2:], uint64(n))
	}
	// Frames do SERVIDOR pro cliente nunca são mascarados (isso é regra
	// do protocolo -- só o cliente mascara).
	if _, err := c.rw.Write(header); err != nil {
		return err
	}
	if _, err := c.rw.Write(payload); err != nil {
		return err
	}
	return c.rw.Flush()
}

// WriteMessage manda um frame de texto (as mensagens deste projeto são
// sempre JSON).
func (c *wsConn) WriteMessage(payload []byte) error {
	return c.writeFrame(0x1, payload)
}
