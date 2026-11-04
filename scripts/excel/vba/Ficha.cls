Option Explicit
' Ficha de sitio: botones.

Private Sub Worksheet_FollowHyperlink(ByVal Target As Hyperlink)
    If Not Intersect(Target.Range, Me.Range("BtnNotaFicha")) Is Nothing Then AgregarNota
End Sub
