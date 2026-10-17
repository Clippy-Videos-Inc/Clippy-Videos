' ============================================================
' Utils.brs — helpers compartilhados entre telas
' ============================================================

' Converte um item de vídeo vindo da API (/api/videos, /api/buscar,
' /api/channel/<user>) num ContentNode pronto pra RowList/MarkupGrid.
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

' Converte um canal (de /api/buscar) num ContentNode pro mesmo grid de
' vídeos — o VideoItem mostra só o nome e "Canal" como legenda.
function MakeChannelContentNode(canal as Object) as Object
    item = CreateObject("roSGNode", "ContentNode")
    item.Title = canal.display_name
    item.HDPosterUrl = ""
    item.SDPosterUrl = ""
    item.AddFields({
        videoId: ""
        channelName: canal.username
        viewsCount: invalid
        isChannelResult: true
    })
    return item
end function

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
