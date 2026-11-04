Option Explicit

Private Sub Workbook_Open()
    ' las tablas dinámicas se actualizan solas al abrir; aquí se pintan los mapas con los datos actuales
    On Error Resume Next
    If TablasDin.PivotTables.Count = 0 Then CrearTablasDinamicas
    ColorearMapas
End Sub
