sub Init()
    m.channelPhoto = m.top.FindNode("channelPhoto")
    m.displayNameLabel = m.top.FindNode("displayNameLabel")
    m.handleLabel = m.top.FindNode("handleLabel")
    m.bioLabel = m.top.FindNode("bioLabel")
    m.spinner = m.top.FindNode("spinner")
    m.errorLabel = m.top.FindNode("errorLabel")
    m.videosGrid = m.top.FindNode("videosGrid")

    m.videosGrid.ObserveField("itemSelected", "OnItemSelected")
end sub

sub FocusGrid()
    if m.videosGrid.visible
        m.videosGrid.SetFocus(true)
    end if
end sub

sub OnUsernameChange()
    username = m.top.username
    if username = invalid or username = "" then return

    m.displayNameLabel.text = username
    m.handleLabel.text = "@" + username
    m.bioLabel.text = ""
    m.videosGrid.visible = false
    m.errorLabel.visible = false
    m.spinner.visible = true

    m.task = CreateObject("roSGNode", "FetchChannelTask")
    m.task.username = username
    m.task.ObserveField("result", "OnChannelResult")
    m.task.ObserveField("errorMessage", "OnFetchError")
    m.task.control = "RUN"
end sub

sub OnChannelResult(event as Object)
    data = event.GetData()
    if data = invalid then return

    m.spinner.visible = false
    m.displayNameLabel.text = data.display_name
    m.handleLabel.text = "@" + data.username
    m.bioLabel.text = data.bio
    if data.foto_url <> invalid and data.foto_url <> ""
        m.channelPhoto.uri = data.foto_url
    end if

    root = CreateObject("roSGNode", "ContentNode")
    for each v in data.videos
        root.AppendChild(MakeVideoContentNode(v, data.static_url))
    end for

    if root.GetChildCount() = 0
        m.errorLabel.text = "Esse canal ainda não publicou nenhum vídeo."
        m.errorLabel.visible = true
        return
    end if

    m.videosGrid.content = root
    m.videosGrid.visible = true
end sub

sub OnFetchError(event as Object)
    msg = event.GetData()
    if msg = invalid or msg = "" then return
    m.spinner.visible = false
    m.errorLabel.text = msg
    m.errorLabel.visible = true
end sub

sub OnItemSelected(event as Object)
    index = event.GetData()
    if index = invalid then return
    content = m.videosGrid.content.GetChild(index)
    if content = invalid then return
    if content.videoId <> invalid and content.videoId <> ""
        m.top.selectedVideoId = content.videoId
    end if
end sub
