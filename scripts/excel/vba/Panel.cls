Option Explicit
' Panel: botones (celdas con vínculo a sí mismas); los mapas se recolorean al volver a la hoja o al cambiar la fecha.

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
    ElseIf Toca(c, "BtnDXF") Then
        ImportarDXF
    End If
End Sub

Private Sub Worksheet_Activate()
    ColorearMapas
End Sub

Private Sub Worksheet_Change(ByVal Target As Range)
    If Not Intersect(Target, ThisWorkbook.Names("FechaPanel").RefersToRange) Is Nothing Or _
       Not Intersect(Target, ThisWorkbook.Names("Vista").RefersToRange) Is Nothing Then ColorearMapas
End Sub

Private Function Toca(ByVal c As Range, ByVal nombre As String) As Boolean
    Toca = Not Intersect(c, Me.Range(nombre)) Is Nothing
End Function
