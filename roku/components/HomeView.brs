sub Init()
    m.rowList = m.top.FindNode("rowList")
    m.loadingLabel = m.top.FindNode("loadingLabel")
    m.errorLabel = m.top.FindNode("errorLabel")

    m.rowList.ObserveField("rowItemSelected", "OnItemSelected")

    m.rowsData = {
        emAlta: invalid
        recentes: invalid
    }

    LoadFeeds()
end sub

sub LoadFeeds()
    m.loadingLabel.visible = true
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

function MakeVideoContentNode(video as Object, staticUrl as String) as Object
    item = CreateObject("roSGNode", "ContentNode")
    item.Title = video.title
    thumbUri = ""
    if video.thumb <> invalid and video.thumb <> ""
        thumbUri = staticUrl + "uploads/" + video.thumb
    end if
    item.HDPosterUrl = thumbUri
    item.SDPosterUrl = thumbUri
    item.AddFields({
        videoId: video.id.ToStr()
        channelName: video.channel
        viewsCount: video.views
    })
    return item
end function

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
    m.loadingLabel.visible = false
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

    m.rowList.content = root
    m.loadingLabel.visible = false
    m.errorLabel.visible = false
    m.rowList.visible = true
    m.rowList.SetFocus(true)
end sub

sub OnItemSelected(event as Object)
    indices = event.GetData()
    if indices = invalid then return
    rowIndex = indices[0]
    itemIndex = indices[1]

    rowContent = m.rowList.content.GetChild(rowIndex)
    if rowContent = invalid then return
    itemContent = rowContent.GetChild(itemIndex)
    if itemContent = invalid then return

    videoId = itemContent.videoId
    if videoId = invalid or videoId = "" then return

    m.top.selectedVideoId = videoId
end sub
