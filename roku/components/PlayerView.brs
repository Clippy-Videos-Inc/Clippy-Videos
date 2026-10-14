sub Init()
    m.video = m.top.FindNode("video")
    m.loadingLabel = m.top.FindNode("loadingLabel")
    m.errorLabel = m.top.FindNode("errorLabel")
    m.titleOverlay = m.top.FindNode("titleOverlay")

    m.video.ObserveField("state", "OnVideoStateChange")
    m.top.ObserveField("focusedChild", "NoOp")
end sub

sub NoOp()
end sub

sub OnVideoIdChange()
    videoId = m.top.videoId
    if videoId = invalid or videoId = "" then return

    m.loadingLabel.visible = true
    m.errorLabel.visible = false
    m.video.visible = false
    m.titleOverlay.visible = false

    m.task = CreateObject("roSGNode", "FetchVideoDetailTask")
    m.task.videoId = videoId
    m.task.ObserveField("result", "OnDetailResult")
    m.task.ObserveField("errorMessage", "OnFetchError")
    m.task.control = "RUN"
end sub

sub OnDetailResult(event as Object)
    data = event.GetData()
    if data = invalid then return

    content = CreateObject("roSGNode", "ContentNode")
    content.Title = data.title
    content.Url = data.stream_url
    content.StreamFormat = "mp4"

    if data.subtitle_url <> invalid and data.subtitle_url <> ""
        sub1 = content.CreateChild("Subtitle")
        sub1.Url = data.subtitle_url
        sub1.TrackName = "Português"
        sub1.Language = "por"
    end if

    m.video.content = content
    m.titleOverlay.text = data.title
    m.titleOverlay.visible = true

    m.video.visible = true
    m.loadingLabel.visible = false
    m.video.control = "play"
    m.video.SetFocus(true)
end sub

sub OnFetchError(event as Object)
    msg = event.GetData()
    if msg = invalid or msg = "" then return
    m.loadingLabel.visible = false
    m.video.visible = false
    m.errorLabel.text = msg + Chr(10) + Chr(10) + "Pressione VOLTAR para retornar ao início."
    m.errorLabel.visible = true
    m.top.SetFocus(true)
end sub

sub OnVideoStateChange()
    state = m.video.state
    if state = "error"
        m.loadingLabel.visible = false
        m.video.visible = false
        errMsg = m.video.errorMsg
        if errMsg = invalid or errMsg = "" then errMsg = "Falha ao reproduzir o vídeo."
        msg = "Erro de reprodução: " + errMsg + Chr(10) + Chr(10)
        msg = msg + "Se o servidor usa um certificado autoassinado (rede local), tente trocar "
        msg = msg + "para a URL pública no Config.brs." + Chr(10) + Chr(10) + "Pressione VOLTAR."
        m.errorLabel.text = msg
        m.errorLabel.visible = true
        m.top.SetFocus(true)
    else if state = "finished"
        m.titleOverlay.visible = false
        m.top.closeRequested = true
    end if
end sub

sub Reset()
    m.video.control = "stop"
    m.video.content = invalid
    m.video.visible = false
    m.titleOverlay.visible = false
    m.errorLabel.visible = false
    m.loadingLabel.visible = false
    m.top.videoId = ""
end sub

function OnKeyEvent(key as String, press as Boolean) as Boolean
    if not press then return false

    if key = "back"
        m.top.closeRequested = true
        return true
    end if

    return false
end function
