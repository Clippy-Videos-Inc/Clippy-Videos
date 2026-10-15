sub Init()
    m.rowList = m.top.FindNode("rowList")
    m.spinner = m.top.FindNode("spinner")
    m.errorLabel = m.top.FindNode("errorLabel")

    m.rowList.ObserveField("rowItemSelected", "OnItemSelected")
    m.rowList.ObserveField("rowItemFocused", "OnItemFocused")
    m.focusedIndices = [0, 0]

    m.rowsData = {
        emAlta: invalid
        recentes: invalid
    }

    LoadFeeds()
end sub

sub LoadFeeds()
    m.spinner.visible = true
    m.errorLabel.visible = false

    m.taskEmAlta = CreateObject("roSGNode", "FetchVideosTask")
    m.taskEmAlta.feed = "em-alta"
    m.taskEmAlta.page = 1
    m.taskEmAlta.ObserveField("result", "OnEmAltaResult")
    m.taskEmAlta.ObserveField("errorMessage", "OnFetchError")
    m.taskEmAlta.control = "RUN"

    m.taskRecentes = CreateObject("roSGNode", "FetchVideosTask")
    m.taskRecentes.feed = "recentes"
    m.taskRecentes.page = 1
    m.taskRecentes.ObserveField("result", "OnRecentesResult")
    m.taskRecentes.ObserveField("errorMessage", "OnFetchError")
    m.taskRecentes.control = "RUN"
end sub

sub OnEmAltaResult(event as Object)
    data = event.GetData()
    if data = invalid or data.videos = invalid then return
    m.rowsData.emAlta = data
    TryRenderRows()
end sub

sub OnRecentesResult(event as Object)
    data = event.GetData()
    if data = invalid or data.videos = invalid then return
    m.rowsData.recentes = data
    TryRenderRows()
end sub

sub OnFetchError(event as Object)
    msg = event.GetData()
    if msg = invalid or msg = "" then return
    m.spinner.visible = false
    m.errorLabel.text = msg
    m.errorLabel.visible = true
end sub

sub TryRenderRows()
    if m.rowsData.emAlta = invalid or m.rowsData.recentes = invalid then return

    root = CreateObject("roSGNode", "ContentNode")

    rowEmAlta = root.CreateChild("ContentNode")
    rowEmAlta.Title = "Em alta"
    for each v in m.rowsData.emAlta.videos
        rowEmAlta.AppendChild(MakeVideoContentNode(v, m.rowsData.emAlta.static_url))
    end for

    rowRecentes = root.CreateChild("ContentNode")
    rowRecentes.Title = "Recentes"
    for each v in m.rowsData.recentes.videos
        rowRecentes.AppendChild(MakeVideoContentNode(v, m.rowsData.recentes.static_url))
    end for

    if rowEmAlta.GetChildCount() = 0 and rowRecentes.GetChildCount() = 0
        m.errorLabel.text = "Nenhum vídeo encontrado ainda."
        m.errorLabel.visible = true
        m.spinner.visible = false
        return
    end if

    m.rowList.content = root
    m.spinner.visible = false
    m.errorLabel.visible = false
    m.rowList.visible = true
end sub

sub OnItemFocused(event as Object)
    indices = event.GetData()
    if indices = invalid then return
    m.focusedIndices = indices
end sub

function GetFocusedContent() as Dynamic
    if m.rowList.content = invalid then return invalid
    rowContent = m.rowList.content.GetChild(m.focusedIndices[0])
    if rowContent = invalid then return invalid
    return rowContent.GetChild(m.focusedIndices[1])
end function

sub OnItemSelected(event as Object)
    indices = event.GetData()
    if indices = invalid then return

    rowContent = m.rowList.content.GetChild(indices[0])
    if rowContent = invalid then return
    itemContent = rowContent.GetChild(indices[1])
    if itemContent = invalid then return

    videoId = itemContent.videoId
    if videoId = invalid or videoId = "" then return

    m.top.selectedVideoId = videoId
end sub

' Dá foco à grade (chamado pela MainScene ao voltar de outra tela).
sub FocusGrid()
    m.rowList.SetFocus(true)
end sub

function OnKeyEvent(key as String, press as Boolean) as Boolean
    if not press then return false

    if key = "options"
        content = GetFocusedContent()
        if content <> invalid and content.channelName <> invalid and content.channelName <> ""
            m.top.selectedChannel = content.channelName
            return true
        end if
    end if

    return false
end function
