Option Explicit
' Geometría del plano: botones para importar un DXF y redibujar los mapas.

Private Sub Worksheet_FollowHyperlink(ByVal Target As Hyperlink)
    If Not Intersect(Target.Range, Me.Range("BtnDxfGeo")) Is Nothing Then
        ImportarDXF
    ElseIf Not Intersect(Target.Range, Me.Range("BtnRedibujar")) Is Nothing Then
        DibujarMapas
        Panel.Activate
    End If
End Sub
