sub Init()
    m.top.functionName = "DoFetch"
end sub

sub DoFetch()
    url = ApiVideoDetailUrl(m.top.videoId)
    data = GetJson(url)

    if data = invalid
        m.top.errorMessage = "Não foi possível carregar este vídeo. Verifique a conexão com o servidor."
        return
    end if

    if data.error <> invalid
        m.top.errorMessage = data.error
        return
    end if

    if data.stream_url = invalid or data.stream_url = ""
        m.top.errorMessage = "Este vídeo não tem um arquivo de stream disponível."
        return
    end if

    m.top.result = data
end sub
