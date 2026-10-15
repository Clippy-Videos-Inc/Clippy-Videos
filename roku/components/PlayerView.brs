sub Init()
    m.video = m.top.FindNode("video")
    m.spinner = m.top.FindNode("spinner")
    m.errorLabel = m.top.FindNode("errorLabel")
    m.titleBar = m.top.FindNode("titleBar")
    m.titleOverlay = m.top.FindNode("titleOverlay")
    m.badge360 = m.top.FindNode("badge360")
    m.channelButton = m.top.FindNode("channelButton")
    m.toastLabel = m.top.FindNode("toastLabel")
    m.hintLabel = m.top.FindNode("hintLabel")

    m.video.ObserveField("state", "OnVideoStateChange")
    m.channelButton.ObserveField("buttonSelected", "OnChannelButtonSelected")

    m.toastTimer = CreateObject("roSGNode", "Timer")
    m.toastTimer.duration = 2
    m.toastTimer.ObserveField("fire", "OnToastTimerFire")

    m.qualities = []
    m.qualityIndex = 0
    m.channelUsername = ""
end sub

sub OnVideoIdChange()
    videoId = m.top.videoId
    if videoId = invalid or videoId = "" then return

    m.spinner.visible = true
    m.errorLabel.visible = false
    m.video.visible = false
    m.titleBar.visible = false
    m.titleOverlay.visible = false
    m.badge360.visible = false
    m.channelButton.visible = false
    m.hintLabel.visible = false

    m.task = CreateObject("roSGNode", "FetchVideoDetailTask")
    m.task.videoId = videoId
    m.task.ObserveField("result", "OnDetailResult")
    m.task.ObserveField("errorMessage", "OnFetchError")
    m.task.control = "RUN"
end sub

function BuildVideoContent(streamUrl as String, title as String, subtitleUrl as String) as Object
    content = CreateObject("roSGNode", "ContentNode")
    content.Title = title
    content.Url = streamUrl
    content.StreamFormat = "mp4"

    if subtitleUrl <> invalid and subtitleUrl <> ""
        sub1 = content.CreateChild("Subtitle")
        sub1.Url = subtitleUrl
        sub1.TrackName = "Português"
        sub1.Language = "por"
    end if

    return content
end function

sub OnDetailResult(event as Object)
    data = event.GetData()
    if data = invalid then return

    m.videoTitle = data.title
    m.subtitleUrl = data.subtitle_url
    m.qualities = data.qualities
    m.qualityIndex = 0
    m.channelUsername = data.channel

    m.video.content = BuildVideoContent(data.stream_url, data.title, data.subtitle_url)

    m.titleOverlay.text = data.title
    m.titleBar.visible = true
    m.titleOverlay.visible = true
    m.badge360.visible = (data.is_360 = true)

    if data.channel <> invalid and data.channel <> ""
        label = data.channel_display_name
        if label = invalid or label = "" then label = data.channel
        m.channelButton.text = "@ " + label
        m.channelButton.visible = true
    end if

    m.hintLabel.visible = true

    m.video.visible = true
    m.spinner.visible = false
    m.video.control = "play"
    m.video.SetFocus(true)
end sub

sub OnFetchError(event as Object)
    msg = event.GetData()
    if msg = invalid or msg = "" then return
    m.spinner.visible = false
    m.video.visible = false
    m.errorLabel.text = msg + Chr(10) + Chr(10) + "Pressione VOLTAR para retornar ao início."
    m.errorLabel.visible = true
    m.top.SetFocus(true)
end sub

sub OnVideoStateChange()
    state = m.video.state
    if state = "error"
        m.spinner.visible = false
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
        m.top.closeRequested = true
    end if
end sub

sub CycleQuality()
    if m.qualities = invalid or m.qualities.Count() <= 1 then
        ShowToast("Só tem uma qualidade disponível pra esse vídeo.")
        return
    end if

    currentPos = m.video.position
    m.qualityIndex = (m.qualityIndex + 1) mod m.qualities.Count()
    nextQuality = m.qualities[m.qualityIndex]

    m.video.content = BuildVideoContent(nextQuality.url, m.videoTitle, m.subtitleUrl)
    m.video.seek = currentPos
    m.video.control = "play"

    ShowToast("Qualidade: " + nextQuality.label)
end sub

sub ShowToast(msg as String)
    m.toastLabel.text = msg
    m.toastLabel.visible = true
    m.toastTimer.control = "stop"
    m.toastTimer.control = "start"
end sub

sub OnToastTimerFire()
    m.toastLabel.visible = false
end sub

sub OnChannelButtonSelected()
    if m.channelUsername <> invalid and m.channelUsername <> ""
        m.top.selectedChannel = m.channelUsername
    end if
end sub

sub Reset()
    m.video.control = "stop"
    m.video.content = invalid
    m.video.visible = false
    m.titleBar.visible = false
    m.titleOverlay.visible = false
    m.badge360.visible = false
    m.channelButton.visible = false
    m.toastLabel.visible = false
    m.hintLabel.visible = false
    m.errorLabel.visible = false
    m.spinner.visible = false
    m.qualities = []
    m.qualityIndex = 0
    m.channelUsername = ""
    m.top.videoId = ""
end sub

function OnKeyEvent(key as String, press as Boolean) as Boolean
    if not press then return false

    if key = "back"
        m.top.closeRequested = true
        return true
    end if

    if key = "options"
        if m.video.visible
            CycleQuality()
            return true
        end if
    end if

    if key = "down"
        if m.channelButton.visible and not m.channelButton.IsInFocusChain()
            m.channelButton.SetFocus(true)
            return true
        end if
    end if

    if key = "up"
        if m.channelButton.IsInFocusChain()
            m.video.SetFocus(true)
            return true
        end if
    end if

    return false
end function
