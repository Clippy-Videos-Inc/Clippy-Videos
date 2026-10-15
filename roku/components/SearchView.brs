sub Init()
    m.keyboard = m.top.FindNode("keyboard")
    m.hintLabel = m.top.FindNode("hintLabel")
    m.spinner = m.top.FindNode("spinner")
    m.errorLabel = m.top.FindNode("errorLabel")
    m.resultsGrid = m.top.FindNode("resultsGrid")

    m.keyboard.ObserveField("text", "OnTextChange")
    m.resultsGrid.ObserveField("itemSelected", "OnItemSelected")

    m.debounce = CreateObject("roSGNode", "Timer")
    m.debounce.duration = 0.5
    m.debounce.ObserveField("fire", "OnDebounceFire")

    m.lastQuery = ""
end sub

sub FocusKeyboard()
    m.keyboard.SetFocus(true)
end sub

sub ResetSearch()
    m.keyboard.text = ""
    m.resultsGrid.visible = false
    m.errorLabel.visible = false
    m.hintLabel.visible = true
    m.lastQuery = ""
end sub

sub OnTextChange()
    m.debounce.control = "stop"
    m.debounce.control = "start"
end sub

sub OnDebounceFire()
    query = m.keyboard.text
    if query = m.lastQuery then return
    m.lastQuery = query

    if query = "" or Len(query) < 2
        m.resultsGrid.visible = false
        m.errorLabel.visible = false
        m.hintLabel.visible = true
        return
    end if

    m.hintLabel.visible = false
    m.spinner.visible = true
    m.errorLabel.visible = false

    m.task = CreateObject("roSGNode", "FetchSearchTask")
    m.task.query = query
    m.task.ObserveField("result", "OnSearchResult")
    m.task.ObserveField("errorMessage", "OnFetchError")
    m.task.control = "RUN"
end sub

sub OnSearchResult(event as Object)
    data = event.GetData()
    if data = invalid then return
    ' ignora resposta de uma busca antiga que chegou atrasada
    if data.query <> invalid and data.query <> m.lastQuery then return

    m.spinner.visible = false

    root = CreateObject("roSGNode", "ContentNode")
    for each canal in data.canais
        root.AppendChild(MakeChannelContentNode(canal))
    end for
    for each v in data.videos
        root.AppendChild(MakeVideoContentNode(v, data.static_url))
    end for

    if root.GetChildCount() = 0
        m.resultsGrid.visible = false
        m.errorLabel.text = "Nada encontrado para """ + m.lastQuery + """."
        m.errorLabel.visible = true
        return
    end if

    m.resultsGrid.content = root
    m.resultsGrid.visible = true
    m.errorLabel.visible = false
end sub

sub OnFetchError(event as Object)
    msg = event.GetData()
    if msg = invalid or msg = "" then return
    m.spinner.visible = false
    m.resultsGrid.visible = false
    m.errorLabel.text = msg
    m.errorLabel.visible = true
end sub

sub OnItemSelected(event as Object)
    index = event.GetData()
    if index = invalid then return
    content = m.resultsGrid.content.GetChild(index)
    if content = invalid then return

    if content.isChannelResult = true
        m.top.selectedChannel = content.channelName
    else if content.videoId <> invalid and content.videoId <> ""
        m.top.selectedVideoId = content.videoId
    end if
end sub

function OnKeyEvent(key as String, press as Boolean) as Boolean
    if not press then return false

    if key = "down" and m.resultsGrid.visible and not m.resultsGrid.IsInFocusChain()
        m.resultsGrid.SetFocus(true)
        return true
    end if

    return false
end function
