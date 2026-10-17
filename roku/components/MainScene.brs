sub Init()
    m.topBar = m.top.FindNode("topBar")
    m.homeView = m.top.FindNode("homeView")
    m.searchView = m.top.FindNode("searchView")
    m.channelView = m.top.FindNode("channelView")
    m.playerView = m.top.FindNode("playerView")

    m.topBar.ObserveField("confirmedTab", "OnTabConfirmed")

    m.homeView.ObserveField("selectedVideoId", "OnHomeVideoSelected")
    m.homeView.ObserveField("selectedChannel", "OnHomeChannelSelected")
    m.searchView.ObserveField("selectedVideoId", "OnSearchVideoSelected")
    m.searchView.ObserveField("selectedChannel", "OnSearchChannelSelected")
    m.channelView.ObserveField("selectedVideoId", "OnChannelVideoSelected")
    m.playerView.ObserveField("closeRequested", "OnPlayerClosed")
    m.playerView.ObserveField("selectedChannel", "OnPlayerChannelSelected")

    ' "home" | "search" | "channel" | "player"
    m.currentView = "home"
    ' tela de conteúdo (home ou search) a restaurar depois de fechar o
    ' player ou a tela de canal
    m.contentTab = "home"

    m.topBar.FocusBar()
end sub

sub ShowContentTab(tabName as String)
    m.contentTab = tabName
    m.currentView = tabName
    m.topBar.activeTab = tabName

    m.homeView.visible = (tabName = "home")
    m.searchView.visible = (tabName = "search")
    m.channelView.visible = false
    m.playerView.visible = false
end sub

sub OnTabConfirmed()
    tabName = m.topBar.confirmedTab
    if tabName = "" or tabName = invalid then return
    ShowContentTab(tabName)

    if tabName = "search"
        m.searchView.FocusKeyboard()
    else
        m.homeView.FocusGrid()
    end if
end sub

sub OnHomeVideoSelected()
    OpenPlayer(m.homeView.selectedVideoId)
end sub

sub OnSearchVideoSelected()
    OpenPlayer(m.searchView.selectedVideoId)
end sub

sub OnChannelVideoSelected()
    OpenPlayer(m.channelView.selectedVideoId)
end sub

sub OnPlayerChannelSelected()
    username = m.playerView.selectedChannel
    m.playerView.callFunc("Reset")
    m.playerView.visible = false
    OpenChannel(username)
end sub

sub OnHomeChannelSelected()
    OpenChannel(m.homeView.selectedChannel)
end sub

sub OnSearchChannelSelected()
    OpenChannel(m.searchView.selectedChannel)
end sub

sub OpenChannel(username as String)
    if username = invalid or username = "" then return

    m.homeView.visible = false
    m.searchView.visible = false
    m.playerView.visible = false
    m.channelView.visible = true
    m.currentView = "channel"

    m.channelView.username = username
end sub

sub OpenPlayer(videoId as String)
    if videoId = invalid or videoId = "" then return

    m.homeView.visible = false
    m.searchView.visible = false
    m.channelView.visible = false
    m.playerView.visible = true
    m.currentView = "player"

    m.playerView.videoId = videoId
    m.playerView.SetFocus(true)
end sub

sub OnPlayerClosed()
    if m.playerView.closeRequested <> true then return

    m.playerView.visible = false
    m.playerView.callFunc("Reset")
    m.playerView.closeRequested = false

    ReturnToContent()
end sub

sub ReturnToContent()
    m.channelView.visible = false
    ShowContentTab(m.contentTab)
    if m.contentTab = "search"
        m.searchView.FocusKeyboard()
    else
        m.homeView.FocusGrid()
    end if
end sub

function OnKeyEvent(key as String, press as Boolean) as Boolean
    if not press then return false

    if key = "back"
        if m.currentView = "player"
            m.playerView.callFunc("Reset")
            m.playerView.visible = false
            ReturnToContent()
            return true
        else if m.currentView = "channel"
            ReturnToContent()
            return true
        end if
        ' na Home/Busca: deixa o VOLTAR sair do canal normalmente (false)
        return false
    end if

    if key = "up" and (m.currentView = "home" or m.currentView = "search")
        if not m.topBar.IsInFocusChain()
            m.topBar.FocusBar()
            return true
        end if
    end if

    if key = "down" and m.topBar.IsInFocusChain()
        if m.currentView = "search"
            m.searchView.FocusKeyboard()
        else
            m.homeView.FocusGrid()
        end if
        return true
    end if

    return false
end function
