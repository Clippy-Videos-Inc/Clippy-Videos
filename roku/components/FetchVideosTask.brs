sub Init()
    m.top.functionName = "DoFetch"
end sub

sub DoFetch()
    url = ApiVideosUrl(m.top.feed, m.top.page)
    data = GetJson(url)

    if data = invalid or data.videos = invalid
        m.top.errorMessage = "Não foi possível carregar os vídeos. Verifique se o servidor do Clippy Videos está ligado e acessível na rede."
        return
    end if

    wrapper = {}
    wrapper.videos = data.videos
    if data.static_url <> invalid
        wrapper.static_url = data.static_url
    else
        wrapper.static_url = ""
    end if
    m.top.result = wrapper
end sub
