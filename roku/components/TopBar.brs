sub Init()
    m.tabHomeLabel = m.top.FindNode("tabHomeLabel")
    m.tabSearchLabel = m.top.FindNode("tabSearchLabel")
    m.tabs = ["home", "search"]
    m.highlightIndex = 0
    RenderHighlight()
end sub

sub FocusBar()
    tabIndex = m.tabs.Indexof(m.top.activeTab)
    if tabIndex >= 0 then m.highlightIndex = tabIndex
    m.top.SetFocus(true)
    RenderHighlight()
end sub

sub OnActiveTabChange()
    ' guarda contra o onChange disparar antes do Init() rodar (pode
    ' acontecer se o nó pai setar o campo logo na criação do componente)
    if m.tabs = invalid then return

    tabIndex = m.tabs.Indexof(m.top.activeTab)
    if tabIndex >= 0 then m.highlightIndex = tabIndex
    RenderHighlight()
end sub

sub RenderHighlight()
    hasFocus = m.top.IsInFocusChain()

    for i = 0 to 2 - 1
        label = m.tabHomeLabel
        if i = 1 then label = m.tabSearchLabel

        isHighlighted = (i = m.highlightIndex) and hasFocus
        isActive = (m.tabs[i] = m.top.activeTab)

        if isHighlighted
            label.color = "0xFFFFFFFF"
        else if isActive
            label.color = "0x7C3AEDFF"
        else
            label.color = "0x9A9AA5FF"
        end if
    end for
end sub

function OnKeyEvent(key as String, press as Boolean) as Boolean
    if not press then return false

    if key = "left"
        if m.highlightIndex > 0
            m.highlightIndex = m.highlightIndex - 1
            RenderHighlight()
        end if
        return true
    else if key = "right"
        if m.highlightIndex < m.tabs.Count() - 1
            m.highlightIndex = m.highlightIndex + 1
            RenderHighlight()
        end if
        return true
    else if key = "OK"
        m.top.confirmedTab = m.tabs[m.highlightIndex]
        return true
    end if

    ' "down" (e deixar focus chain) bubbla pra MainScene cuidar da navegação
    ' pro conteúdo abaixo.
    return false
end function
