sub Init()
    m.poster = m.top.FindNode("poster")
    m.focusRing = m.top.FindNode("focusRing")
    m.titleLabel = m.top.FindNode("titleLabel")
    m.metaLabel = m.top.FindNode("metaLabel")
end sub

function RoundTo1Decimal(x as Float) as String
    rounded = Int(x * 10 + 0.5) / 10
    return rounded.ToStr()
end function

function FormatViews(n as Dynamic) as String
    if n = invalid then return ""
    num = Val(n.ToStr())
    if num >= 1000000
        return RoundTo1Decimal(num / 1000000) + "mi visualizações"
    else if num >= 1000
        return RoundTo1Decimal(num / 1000) + "mil visualizações"
    end if
    return num.ToStr() + " visualizações"
end function

sub OnContentChange()
    content = m.top.itemContent
    if content = invalid then return

    m.poster.uri = content.HDPosterUrl

    title = content.Title
    if title = invalid then title = ""
    m.titleLabel.text = title

    canal = content.channelName
    if canal = invalid then canal = ""
    views = FormatViews(content.viewsCount)

    if canal <> ""
        m.metaLabel.text = "@" + canal + "  •  " + views
    else
        m.metaLabel.text = views
    end if
end sub

sub OnFocusChange()
    pct = m.top.focusPercent
    if pct > 0.5
        m.focusRing.color = "0x7C3AEDFF"
        m.titleLabel.color = "0xFFFFFFFF"
    else
        m.focusRing.color = "0x00000000"
        m.titleLabel.color = "0xE5E5EAFF"
    end if
end sub
