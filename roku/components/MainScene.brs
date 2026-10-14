sub Init()
    m.homeView = m.top.FindNode("homeView")
    m.playerView = m.top.FindNode("playerView")

    m.homeView.ObserveField("selectedVideoId", "OnVideoSelected")
    m.playerView.ObserveField("closeRequested", "OnPlayerClosed")

    m.homeView.SetFocus(true)

    m.top.ObserveField("focusedChild", "NoOp")
end sub

sub NoOp()
end sub

sub OnVideoSelected()
    videoId = m.homeView.selectedVideoId
    if videoId = invalid or videoId = "" then return

    m.homeView.visible = false
    m.playerView.visible = true
    m.playerView.videoId = videoId
    m.playerView.SetFocus(true)
end sub

sub OnPlayerClosed()
    if m.playerView.closeRequested <> true then return

    m.playerView.visible = false
    m.playerView.callFunc("Reset")
    m.playerView.closeRequested = false

    m.homeView.visible = true
    m.homeView.SetFocus(true)
end sub

function OnKeyEvent(key as String, press as Boolean) as Boolean
    ' Fallback: fecha o canal com VOLTAR quando estamos na Home (comportamento
    ' padrão do Roku se este handler devolver false, então nem precisamos
    ' tratar isso aqui).
    return false
end function
