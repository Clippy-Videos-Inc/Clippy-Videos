' ============================================================
' Net.brs — pequenos helpers de rede (JSON síncrono)
' ============================================================

' Faz GET em uma URL e devolve o JSON já parseado (roAssociativeArray
' ou roArray), ou invalid em caso de erro.
function GetJson(url as String) as Object
    xfer = CreateObject("roUrlTransfer")
    xfer.SetUrl(url)
    xfer.SetCertificatesFile("common:/certs/ca-bundle.crt")
    xfer.InitClientCertificates()
    ' Permite falar com o servidor local do JP mesmo com certificado
    ' autoassinado. Em produção (domínio com certificado válido) isso
    ' não faz diferença nenhuma.
    xfer.EnablePeerVerification(false)
    xfer.EnableHostVerification(false)
    xfer.AddHeader("User-Agent", "ClippyVideos-Roku/1.0")
    xfer.AddHeader("Accept", "application/json")

    response = xfer.GetToString()
    if response = invalid or response = ""
        print "[Net] GetJson: resposta vazia para "; url
        return invalid
    end if

    parsed = ParseJson(response)
    if parsed = invalid
        print "[Net] GetJson: falha ao parsear JSON de "; url
    end if
    return parsed
end function
