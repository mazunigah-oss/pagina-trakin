Option Explicit
' Panel: botones (celdas con vínculo a sí mismas) y clic en los mapas.

Private Sub Worksheet_FollowHyperlink(ByVal Target As Hyperlink)
    Dim c As Range
    Set c = Target.Range.Cells(1, 1)
    If Toca(c, "BtnAnterior") Then
        DiaAnterior
    ElseIf Toca(c, "BtnHoy") Then
        IrHoy
    ElseIf Toca(c, "BtnSiguiente") Then
        DiaSiguiente
    ElseIf Toca(c, "BtnActualizar") Then
        Actualizar
    ElseIf Toca(c, "BtnCamiones") Then
        ImportarCamiones
    ElseIf Toca(c, "BtnPlanilla") Then
        ImportarPlanilla
    ElseIf Toca(c, "BtnNota") Then
        AgregarNota
    ElseIf Toca(c, "BtnFicha") Then
        VerFicha
    End If
End Sub

Private Sub Worksheet_SelectionChange(ByVal Target As Range)
    Dim m As Range, idx As Variant, z As Variant
    If Target.Rows.Count > 1 Or Target.Columns.Count > 1 Then Exit Sub   ' (Cells.Count desborda con la hoja entera)
    Set m = Me.Range("MapaInterv")
    If Not Intersect(Target, m) Is Nothing Then
        idx = Me.Range("GrillaSitios").Cells(Target.Row - m.Row + 1, Target.Column - m.Column + 1).Value
    Else
        Set m = Me.Range("MapaEntregas")
        If Intersect(Target, m) Is Nothing Then Exit Sub
        z = Me.Range("GrillaZonas").Cells(Target.Row - m.Row + 1, Target.Column - m.Column + 1).Value
        If IsNumeric(z) Then
            If z >= 1 And z <= 146 Then idx = Me.Range("ZonaSitio").Cells(z, 1).Value
        End If
    End If
    If IsNumeric(idx) And Not IsEmpty(idx) Then
        If idx >= 1 And idx <= 50 Then SeleccionarSitio CLng(idx)
    End If
End Sub

Private Function Toca(ByVal c As Range, ByVal nombre As String) As Boolean
    Toca = Not Intersect(c, Me.Range(nombre)) Is Nothing
End Function
