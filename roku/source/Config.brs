' ============================================================
' Config.brs — configuração central do canal Clippy Videos
' ============================================================
' Troque API_BASE_URL para apontar para o seu servidor.
'
' - Rede local (dev/teste): "https://192.168.0.150"
'     * O Roku precisa estar na MESMA rede Wi-Fi/LAN que o PC
'       rodando o Clippy Videos.
'     * O certificado em cert.pem/192.168.0.150.pem é autoassinado.
'       Alguns Rokus recusam o handshake HTTPS de vídeo com um
'       certificado autoassinado (a chamada de API via roUrlTransfer
'       contorna isso com EnablePeerVerification(false), mas o nó
'       de vídeo do SceneGraph usa o verificador de TLS do sistema
'       e pode falhar). Se o player ficar com erro de rede ao dar
'       play, troque para a URL pública abaixo.
' - Produção (recomendado): "https://play-videos.fly.dev"
'     * É o domínio do fly.toml do projeto, com certificado válido
'       — funciona em qualquer Roku, em qualquer rede.
' ============================================================
function ApiBaseUrl() as String
    return "https://192.168.0.150"
end function

function ApiVideosUrl(feed as String, page as Integer) as String
    return ApiBaseUrl() + "/api/videos?feed=" + feed + "&page=" + page.ToStr() + "&per_page=24"
end function

function ApiVideoDetailUrl(videoId as String) as String
    return ApiBaseUrl() + "/api/video/" + videoId
end function

function ApiBuscarUrl(query as String) as String
    xfer = CreateObject("roUrlTransfer")
    return ApiBaseUrl() + "/api/buscar?q=" + xfer.Escape(query)
end function

function ApiChannelUrl(username as String) as String
    xfer = CreateObject("roUrlTransfer")
    return ApiBaseUrl() + "/api/channel/" + xfer.Escape(username)
end function
