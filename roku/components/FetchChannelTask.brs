sub Init()
    m.top.functionName = "DoFetch"
end sub

sub DoFetch()
    data = GetJson(ApiChannelUrl(m.top.username))

    if data = invalid or data.videos = invalid
        m.top.errorMessage = "Não foi possível carregar este canal agora."
        return
    end if

    m.top.result = data
end sub
