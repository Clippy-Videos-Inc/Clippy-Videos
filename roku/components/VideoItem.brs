sub Init()
    m.poster = m.top.FindNode("poster")
    m.focusRing = m.top.FindNode("focusRing")
    m.titleLabel = m.top.FindNode("titleLabel")
    m.metaLabel = m.top.FindNode("metaLabel")
    m.top.SetFields({ scaleRotateCenter: [180, 115] })
end sub

sub OnContentChange()
    if m.poster = invalid then return ' onChange antes do Init()

    content = m.top.itemContent
    if content = invalid then return

    m.poster.uri = content.HDPosterUrl

    title = content.Title
    if title = invalid then title = ""
    m.titleLabel.text = title

    canal = content.channelName
    if canal = invalid then canal = ""

    if content.isChannelResult = true
        m.metaLabel.text = "Canal  •  @" + canal
    else
        views = FormatViews(content.viewsCount)
        if canal <> ""
            m.metaLabel.text = "@" + canal + "  •  " + views
        else
            m.metaLabel.text = views
        end if
    end if
end sub

sub OnFocusChange()
    if m.focusRing = invalid then return ' onChange antes do Init()

    pct = m.top.focusPercent
    if pct > 0.5
        m.focusRing.color = "0x7C3AEDFF"
        m.titleLabel.color = "0xFFFFFFFF"
        m.top.scale = [1.05, 1.05]
    else
        m.focusRing.color = "0x00000000"
        m.titleLabel.color = "0xE5E5EAFF"
        m.top.scale = [1.0, 1.0]
    end if
end sub
