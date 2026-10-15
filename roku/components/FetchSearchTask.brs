sub Init()
    m.top.functionName = "DoFetch"
end sub

sub DoFetch()
    data = GetJson(ApiBuscarUrl(m.top.query))

    if data = invalid or data.videos = invalid
        m.top.errorMessage = "Não foi possível buscar agora. Verifique a conexão com o servidor."
        return
    end if

    m.top.result = data
end sub
