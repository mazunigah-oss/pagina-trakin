Option Explicit
Private Const MAX_POL As Long = 3000    ' polígonos que se leen de un DXF
Private Const MAX_PTS As Long = 20000   ' vértices por polígono
' Macros del archivo de seguimiento de movimiento de tierra (Loma La Cruz).
' Funcionan en Excel para Windows y Mac (sin librerías externas).

' ------------------------------------------------------------ fecha, vista y actualización

Public Sub DiaAnterior()
    MoverDia -1
End Sub

Public Sub DiaSiguiente()
    MoverDia 1
End Sub

Private Sub MoverDia(ByVal signo As Long)
    Dim c As Range, d As Date, paso As Long
    Set c = ThisWorkbook.Names("FechaPanel").RefersToRange
    paso = 1
    If CStr(ThisWorkbook.Names("Vista").RefersToRange.Value) = "Semana" Then paso = 7
    d = c.Value
    c.Value = DateSerial(Year(d), Month(d), Day(d) + signo * paso)
    ColorearMapas
End Sub

Public Sub IrHoy()
    ThisWorkbook.Names("FechaPanel").RefersToRange.Formula = "=TODAY()"
    ColorearMapas
End Sub

Public Sub CrearTablasDinamicas()
    ' crea las 4 tablas dinámicas con la API de Excel (desde las tablas tblCamiones, tblMovimiento y tblEntregas)
    Dim ws As Worksheet, pt As PivotTable
    Set ws = TablasDin
    On Error Resume Next
    For Each pt In ws.PivotTables
        pt.TableRange2.Clear
    Next pt
    ws.Range("B4:Z1000").Clear
    On Error GoTo 0
    Set pt = NuevaTD(ws, "tblCamiones", "B4", "tdCamionesDia", "Fecha")
    pt.AddDataField pt.PivotFields("m³"), "Total m³", xlSum
    pt.AddDataField pt.PivotFields("Viaje"), "Viajes", xlSum
    pt.AddDataField pt.PivotFields("Camión día"), "Camiones", xlSum
    Set pt = NuevaTD(ws, "tblCamiones", "G4", "tdCamionesSitio", "Sitio")
    pt.AddDataField pt.PivotFields("m³"), "Total m³ ", xlSum
    pt.AddDataField pt.PivotFields("Viaje"), "Viajes ", xlSum
    Set pt = NuevaTD(ws, "tblMovimiento", "K4", "tdPlanillas", "Fecha")
    pt.PivotFields("Tipo").Orientation = xlColumnField
    pt.AddDataField pt.PivotFields("A botadero m³"), "Botadero m³", xlSum
    Set pt = NuevaTD(ws, "tblEntregas", "Q4", "tdEntregas", "Terraza")
    pt.PivotFields("Estado").Orientation = xlColumnField
    pt.AddDataField pt.PivotFields("Sitio"), "Terrazas", xlCount
End Sub

Private Function NuevaTD(ByVal ws As Worksheet, ByVal origen As String, ByVal celda As String, _
                         ByVal nombre As String, ByVal filas As String) As PivotTable
    Dim pc As PivotCache
    Set pc = ThisWorkbook.PivotCaches.Create(SourceType:=xlDatabase, SourceData:=origen)
    Set NuevaTD = pc.CreatePivotTable(TableDestination:=ws.Range(celda), TableName:=nombre)
    With NuevaTD.PivotFields(filas)
        .Orientation = xlRowField
        .Position = 1
    End With
    On Error Resume Next
    NuevaTD.PivotFields(filas).DataRange.Cells(1, 1).Ungroup   ' Excel agrupa fechas por mes: se deja por día
    NuevaTD.RowAxisLayout xlTabularRow
    On Error GoTo 0
End Function

Public Sub Actualizar()
    ' tablas dinámicas + fórmulas + colores de los mapas
    On Error Resume Next
    If TablasDin.PivotTables.Count = 0 Then CrearTablasDinamicas
    ThisWorkbook.RefreshAll
    Application.CalculateFull
    On Error GoTo 0
    ColorearMapas
    Application.StatusBar = "Datos actualizados a las " & Format(Now, "hh:mm")
End Sub

Public Sub VerFicha()
    Ficha.Activate
End Sub

Public Sub VerTablasDinamicas()
    TablasDin.Activate
End Sub

' ------------------------------------------------------------ mapas (figuras I_<sitio> y E_<sitio>_<terraza>)

Public Sub ColorearMapas()
    Dim sh As Shape, p() As String, fila As Variant, sel As String, sitio As Variant
    Dim verde As Long, amarillo As Long, gris As Long, claro As Long, rojo As Long, est As String
    verde = RGB(47, 158, 107): amarillo = RGB(251, 224, 140): gris = RGB(207, 214, 209)
    claro = RGB(241, 243, 240): rojo = RGB(224, 102, 102)
    On Error Resume Next
    Application.ScreenUpdating = False   ' en Mac redibujar ~200 figuras una por una es lento
    Application.Calculate
    sel = CStr(Ficha.Range("C3").Value)
    For Each sh In Panel.Shapes
        p = Split(sh.Name, "_")
        If UBound(p) >= 1 And (p(0) = "I" Or p(0) = "E") Then
            If IsNumeric(p(1)) Then sitio = CLng(p(1)) Else sitio = p(1)
            fila = Application.Match(sitio, Sitios.Range("A4:A53"), 0)
            If Not IsError(fila) Then
                fila = fila + 3
                If p(0) = "I" Then
                    Select Case Sitios.Cells(fila, 20).Value   ' código: 1 completo, 2 con intervención, 3 sin intervenir
                        Case 1: sh.Fill.ForeColor.RGB = verde
                        Case 2: sh.Fill.ForeColor.RGB = amarillo
                        Case Else: sh.Fill.ForeColor.RGB = gris
                    End Select
                    PonerTexto sh, CStr(Sitios.Cells(fila, 22).Value)
                Else
                    If UBound(p) >= 2 Then
                        If p(2) = "fondo" Then
                            sh.Fill.ForeColor.RGB = claro
                        Else
                            If p(2) = "living" Then est = Sitios.Cells(fila, 13).Value Else est = Sitios.Cells(fila, 12).Value
                            If est = "Entregada" Then
                                sh.Fill.ForeColor.RGB = verde
                            ElseIf Sitios.Cells(fila, 21).Value = 1 Then
                                sh.Fill.ForeColor.RGB = rojo
                            ElseIf est = "En proceso" Then
                                sh.Fill.ForeColor.RGB = amarillo
                            Else
                                sh.Fill.ForeColor.RGB = gris
                            End If
                            If p(2) = "living" Or p(2) = "unica" Then
                                PonerTexto sh, CStr(Sitios.Cells(fila, 23).Value)
                            End If
                        End If
                    End If
                End If
                ' sitio seleccionado: borde oscuro en ambos mapas
                If CStr(Sitios.Cells(fila, 1).Value) = sel Then
                    sh.Line.ForeColor.RGB = RGB(29, 35, 32): sh.Line.Weight = 2
                Else
                    sh.Line.ForeColor.RGB = RGB(255, 255, 255): sh.Line.Weight = 0.75
                End If
            End If
        End If
    Next sh
    Application.ScreenUpdating = True
End Sub

Private Sub PonerTexto(ByVal sh As Shape, ByVal texto As String)
    ' cambia el texto de la figura solo si es distinto (en Mac cada cambio de texto redibuja la figura)
    If sh.TextFrame.Characters.Text <> texto Then sh.TextFrame.Characters.Text = texto
End Sub

Public Sub ClicMapa()
    ' se ejecuta al hacer clic en una figura del mapa
    Dim p() As String
    On Error Resume Next
    p = Split(CStr(Application.Caller), "_")
    If UBound(p) < 1 Then Exit Sub
    If IsNumeric(p(1)) Then Ficha.Range("C3").Value = CLng(p(1)) Else Ficha.Range("C3").Value = p(1)
    ColorearMapas
    Application.StatusBar = "Sitio seleccionado: " & p(1) & " (detalle a la derecha de los mapas)"
End Sub

' ------------------------------------------------------------ importar tickets de la máquina (CSV)

Public Sub ImportarCamiones()
    Dim ruta As Variant, res As String
    ruta = Application.GetOpenFilename()
    If VarType(ruta) = vbBoolean Then Exit Sub
    res = ImportarCamionesDesde(CStr(ruta))
    Actualizar
    MsgBox res, IIf(Left$(res, 2) = "No", vbExclamation, vbInformation), "Tickets de camiones"
End Sub

Public Function ImportarCamionesDesde(ByVal ruta As String) As String
    ' agrega los tickets nuevos del CSV de la máquina a la tabla tblCamiones; devuelve el resumen
    Dim texto As String, lineas() As String, sep As String, lo As ListObject, fila As Range
    Dim cab() As String, i As Long, j As Long, campos() As String, v As Variant
    Dim cTicket As Long, cFecha As Long, cHora As Long, cPatente As Long, cVol As Long
    Dim cSector As Long, cTipo As Long, cEstado As Long, cEmpresa As Long
    Dim nuevos As Long, repetidos As Long, malos As Long, generales As Long
    Dim existentes As New Collection, clave As String, f As Variant, sector As String, estado As String

    texto = Replace(LeerTexto(ruta), vbCr, "")
    lineas = Split(texto, vbLf)
    If UBound(lineas) < 1 Then
        ImportarCamionesDesde = "No hay filas en el archivo.": Exit Function
    End If
    sep = ";"
    If InStr(lineas(0), ";") = 0 Then sep = ","
    cab = Split(UCase(lineas(0)), sep)
    For j = 0 To UBound(cab)
        Select Case Trim(Replace(cab(j), """", ""))
            Case "TICKET": cTicket = j + 1
            Case "FECHA": cFecha = j + 1
            Case "HORA": cHora = j + 1
            Case "PATENTE": cPatente = j + 1
            Case "VOLUMEN_M3", "VOLUMEN", "M3": cVol = j + 1
            Case "SECTOR", "SITIO": cSector = j + 1
            Case "TIPO": cTipo = j + 1
            Case "ESTADO": cEstado = j + 1
            Case "EMPRESA": cEmpresa = j + 1
        End Select
    Next j
    If cTicket = 0 Or cFecha = 0 Or cVol = 0 Then
        ImportarCamionesDesde = "No se encontraron las columnas TICKET, FECHA y VOLUMEN_M3 en la primera fila."
        Exit Function
    End If

    Set lo = Camiones.ListObjects("tblCamiones")
    On Error Resume Next   ' tickets ya cargados (ticket + estado)
    If Not lo.DataBodyRange Is Nothing Then
        v = lo.DataBodyRange.Value
        For i = 1 To UBound(v, 1)
            existentes.Add 1, CStr(v(i, 1)) & "|" & UCase(CStr(v(i, 9)))
        Next i
    End If
    On Error GoTo 0

    Application.ScreenUpdating = False
    For i = 1 To UBound(lineas)
        If Len(Trim(lineas(i))) > 0 Then
            campos = Split(Replace(lineas(i), """", ""), sep)
            f = LeerFecha(Campo(campos, cFecha))
            If IsEmpty(f) Or Len(Campo(campos, cTicket)) = 0 Then
                malos = malos + 1
            Else
                estado = UCase(Campo(campos, cEstado))
                If estado = "" Then estado = "VALIDO"
                clave = Campo(campos, cTicket) & "|" & estado
                If Existe(existentes, clave) Then
                    repetidos = repetidos + 1
                Else
                    existentes.Add 1, clave
                    Set fila = FilaNueva(lo)
                    fila.Cells(1, 1).NumberFormat = "@"
                    fila.Cells(1, 1).Value = Campo(campos, cTicket)
                    fila.Cells(1, 2).Value = f
                    fila.Cells(1, 3).NumberFormat = "@"
                    fila.Cells(1, 3).Value = Campo(campos, cHora)
                    fila.Cells(1, 4).Value = UCase(Campo(campos, cPatente))
                    fila.Cells(1, 5).Value = LeerNumero(Campo(campos, cVol))
                    sector = Campo(campos, cSector)
                    If EsSitio(sector) Then
                        fila.Cells(1, 6).Value = CLng(sector)
                    Else
                        generales = generales + 1
                    End If
                    fila.Cells(1, 7).NumberFormat = "@"
                    fila.Cells(1, 7).Value = sector
                    fila.Cells(1, 8).Value = Campo(campos, cTipo)
                    fila.Cells(1, 9).Value = estado
                    fila.Cells(1, 10).Value = Campo(campos, cEmpresa)
                    nuevos = nuevos + 1
                End If
            End If
        End If
    Next i
    Application.ScreenUpdating = True
    ImportarCamionesDesde = nuevos & " tickets agregados." & vbLf & _
        IIf(repetidos > 0, repetidos & " ya estaban cargados (no se repiten)." & vbLf, "") & _
        IIf(generales > 0, generales & " sin número de sitio (quedan como generales: pasajes, calle, etc.)." & vbLf, "") & _
        IIf(malos > 0, malos & " filas sin ticket o con fecha no reconocida (se omitieron).", "")
End Function

Private Function FilaNueva(ByVal lo As ListObject) As Range
    ' fila nueva al final de la tabla (si la tabla solo tiene una fila vacía, se usa esa)
    If lo.ListRows.Count = 1 Then
        If Application.WorksheetFunction.CountA(lo.ListRows(1).Range) = 0 Then
            Set FilaNueva = lo.ListRows(1).Range
            Exit Function
        End If
    End If
    Set FilaNueva = lo.ListRows.Add.Range
End Function

Private Function EsSitio(ByVal s As String) As Boolean
    Dim k As Long
    s = Trim(s)
    If Len(s) = 0 Or Len(s) > 2 Then Exit Function
    For k = 1 To Len(s)
        If Mid$(s, k, 1) < "0" Or Mid$(s, k, 1) > "9" Then Exit Function
    Next k
    EsSitio = (CLng(s) >= 1 And CLng(s) <= 48)
End Function

' ------------------------------------------------------------ importar la planilla "Resumen x Terraza"

Public Sub ImportarPlanilla()
    Dim ruta As Variant, fechaTxt As String, f As Variant, n As Long, res As String
    ruta = Application.GetOpenFilename()
    If VarType(ruta) = vbBoolean Then Exit Sub
    fechaTxt = InputBox("Fecha de los datos de la planilla (dd-mm-aaaa):", "Planilla de movimiento", _
                        Format(ThisWorkbook.Names("FechaPanel").RefersToRange.Value, "dd-mm-yyyy"))
    If Len(fechaTxt) = 0 Then Exit Sub
    f = LeerFecha(fechaTxt)
    If IsEmpty(f) Then
        MsgBox "Fecha no reconocida: " & fechaTxt, vbExclamation: Exit Sub
    End If
    n = FilasConFecha(CDate(f))
    If n > 0 Then
        If MsgBox("Ya hay " & n & " filas con fecha " & Format(f, "dd-mm-yyyy") & " en la hoja Movimiento." & vbLf & _
                  "¿Reemplazarlas por las de esta planilla?", vbYesNo + vbQuestion) = vbNo Then Exit Sub
    End If
    res = ImportarPlanillaDesde(CStr(ruta), CDate(f))
    Actualizar
    MsgBox res, IIf(Left$(res, 2) = "No", vbExclamation, vbInformation), "Planilla de movimiento"
End Sub

Private Function FilasConFecha(ByVal f As Date) As Long
    Dim lo As ListObject, i As Long, v As Variant
    Set lo = Movimiento.ListObjects("tblMovimiento")
    If lo.DataBodyRange Is Nothing Then Exit Function
    v = lo.ListColumns(1).DataBodyRange.Value
    If Not IsArray(v) Then
        If SerieFecha(v) = CLng(f) Then FilasConFecha = 1
        Exit Function
    End If
    For i = 1 To UBound(v, 1)
        If SerieFecha(v(i, 1)) = CLng(f) Then FilasConFecha = FilasConFecha + 1
    Next i
End Function

Public Function ImportarPlanillaDesde(ByVal ruta As String, ByVal f As Date) As String
    ' copia la planilla "Resumen x Terraza" a la tabla tblMovimiento con la fecha f (reemplaza las filas de esa fecha)
    Dim wb As Workbook, ws As Worksheet, h As Worksheet, lo As ListObject, fila As Range
    Dim r As Long, c As Long, filaCab As Long, t As String, i As Long, ultima As Long, k As Long
    Dim cSitio As Long, cEsc As Long, cCorte As Long, cEsp As Long, cBot As Long
    Dim sitio As Variant, esc As Double, corte As Double, esp As Double, bot As Double
    Dim n As Long, extra As Double, total As Double, datos() As Double, filaTxt As String

    Set lo = Movimiento.ListObjects("tblMovimiento")   ' antes de abrir la planilla (pasa a ser el libro activo)
    Application.ScreenUpdating = False
    Set wb = Workbooks.Open(ruta, UpdateLinks:=0, ReadOnly:=True)
    For Each h In wb.Worksheets
        For r = 1 To 40
            For c = 1 To 30
                If UCase(Trim(CStr(h.Cells(r, c).Value))) = "SITIO" Then
                    Set ws = h: filaCab = r: cSitio = c
                    Exit For
                End If
            Next c
            If filaCab > 0 Then Exit For
        Next r
        If filaCab > 0 Then Exit For
    Next h
    If filaCab = 0 Then
        wb.Close False: Application.ScreenUpdating = True
        ImportarPlanillaDesde = "No se encontró la columna 'Sitio' en las primeras 40 filas.": Exit Function
    End If
    ' columnas de la tabla de sitios: desde 'Sitio' hasta el primer '% AVANCE' (a la derecha suele venir el camino)
    For c = cSitio + 1 To cSitio + 15
        t = UCase(CStr(ws.Cells(filaCab, c).Value))
        If InStr(t, "AVANCE") > 0 Then Exit For
        If InStr(t, "BOTADERO") > 0 And cBot = 0 Then
            cBot = c
        ElseIf InStr(t, "ESP") > 0 And InStr(t, "CORTE") > 0 And cEsp = 0 Then
            cEsp = c
        ElseIf InStr(t, "CORTE") > 0 And cCorte = 0 Then
            cCorte = c
        ElseIf InStr(t, "ESCARPE") > 0 And cEsc = 0 Then
            cEsc = c
        End If
    Next c
    If cBot = 0 Or cEsp = 0 Then
        wb.Close False: Application.ScreenUpdating = True
        ImportarPlanillaDesde = "No se encontraron las columnas 'ESC + CORTE c/esp' y 'a botadero' en la fila de títulos."
        Exit Function
    End If

    ' 1) leer las filas de sitios y cerrar la planilla
    ultima = ws.Cells(ws.Rows.Count, cSitio).End(xlUp).Row
    ReDim datos(1 To ultima, 1 To 5)
    For r = filaCab + 1 To ultima
        sitio = ws.Cells(r, cSitio).Value
        If IsNumeric(sitio) And Not IsEmpty(sitio) Then
            If sitio = Int(sitio) And sitio >= 1 And sitio <= 48 Then
                esc = 0: corte = 0
                If cEsc > 0 Then esc = ValorNum(ws.Cells(r, cEsc))
                If cCorte > 0 Then corte = ValorNum(ws.Cells(r, cCorte))
                esp = ValorNum(ws.Cells(r, cEsp)): bot = ValorNum(ws.Cells(r, cBot))
                filaTxt = ""
                For c = 1 To 30
                    filaTxt = filaTxt & " " & UCase(CStr(ws.Cells(r, c).Value))
                Next c
                If InStr(filaTxt, "ADICIONAL") > 0 Then
                    esc = 0
                    corte = 0
                    esp = 0
                End If
                n = n + 1
                datos(n, 1) = CLng(sitio): datos(n, 2) = esc: datos(n, 3) = corte: datos(n, 4) = esp: datos(n, 5) = bot
                If esp = 0 Then extra = extra + bot Else total = total + bot
            End If
        End If
    Next r
    wb.Close False
    If n = 0 Then
        Application.ScreenUpdating = True
        ImportarPlanillaDesde = "No se encontraron filas de sitios (números 1 a 48) bajo la columna 'Sitio'."
        Exit Function
    End If

    ' 2) borrar las filas de esa fecha y agregar las nuevas
    If Not lo.DataBodyRange Is Nothing Then
        For i = lo.ListRows.Count To 1 Step -1
            If SerieFecha(lo.ListRows(i).Range.Cells(1, 1).Value) = CLng(f) Then lo.ListRows(i).Delete
        Next i
    End If
    For k = 1 To n
        Set fila = FilaNueva(lo)
        fila.Cells(1, 1).Value = f
        For c = 1 To 5
            fila.Cells(1, c + 1).Value = datos(k, c)
        Next c
    Next k
    Application.ScreenUpdating = True
    ImportarPlanillaDesde = n & " filas cargadas con fecha " & Format(f, "dd-mm-yyyy") & "." & vbLf & _
        "m³ a botadero (presupuestado): " & Format(total, "#,##0") & vbLf & _
        "m³ extra (sin presupuesto / adicional): " & Format(extra, "#,##0") & vbLf & vbLf & _
        "Revise en la hoja Movimiento que los números de sitio estén bien escritos."
End Function

Private Function ValorNum(ByVal celda As Range) As Double
    If IsNumeric(celda.Value) And Not IsEmpty(celda.Value) Then ValorNum = CDbl(celda.Value)
End Function

' ------------------------------------------------------------ notas

Public Sub AgregarNota()
    Dim s As String, resp As String, texto As String, idx As Variant, fila As Range, sitio As Variant
    s = InputBox("Sitio (número, o ED-1 / ED-2):", "Agregar nota", CStr(Ficha.Range("C3").Value))
    If Len(Trim(s)) = 0 Then Exit Sub
    If IsNumeric(s) Then sitio = CLng(s) Else sitio = UCase(Trim(s))
    idx = Application.Match(sitio, Sitios.Range("A4:A53"), 0)
    If IsError(idx) Then
        MsgBox "El sitio '" & s & "' no existe.", vbExclamation: Exit Sub
    End If
    resp = InputBox("Responsable:", "Agregar nota")
    If Len(Trim(resp)) = 0 Then Exit Sub
    texto = InputBox("Nota (máximo 255 caracteres; para textos más largos escriba directo en la hoja Notas):", _
                     "Agregar nota")
    If Len(Trim(texto)) = 0 Then Exit Sub
    Set fila = FilaNueva(Notas.ListObjects("tblNotas"))
    fila.Cells(1, 1).Value = Now
    fila.Cells(1, 2).Value = sitio
    fila.Cells(1, 3).Value = Trim(resp)
    fila.Cells(1, 4).Value = Trim(texto)
    Ficha.Range("C3").Value = sitio
    ColorearMapas
    MsgBox "Nota agregada al sitio " & sitio & ".", vbInformation
End Sub

' ------------------------------------------------------------ figuras desde el DXF

Public Sub ImportarDXF()
    Dim ruta As Variant, res As String
    ruta = Application.GetOpenFilename()
    If VarType(ruta) = vbBoolean Then Exit Sub
    res = ImportarDXFDesde(CStr(ruta))
    If Left$(res, 2) <> "No" Then
        DibujarMapas
        Panel.Activate
    End If
    MsgBox res, IIf(Left$(res, 2) = "No", vbExclamation, vbInformation), "Plano DXF"
End Sub

Public Function ImportarDXFDesde(ByVal ruta As String) As String
    ' lee polilíneas cerradas (LWPOLYLINE o POLYLINE) por capa y las deja en la hoja Geometria:
    ' capas 1..48 = sitios; Acceso, Living, Patio = terrazas (se asignan al sitio que contiene su centro);
    ' Edificios = ED-1, ED-2...; Etapa*, rótulos y capas sin polígonos cerrados se ignoran; el resto (calle, pasajes) = otras
    Dim lineas() As String, i As Long, cod As String, valor As String, ent As String, enVertice As Boolean
    Dim capa As String, cerrada As Boolean, xs() As Double, ys() As Double, np As Long
    Dim polCapa() As String, polPts() As String, nPol As Long, k As Long, j As Long
    Dim minX As Double, minY As Double, maxX As Double, maxY As Double, f As Double, hayPts As Boolean

    lineas = Split(Replace(LeerTexto(ruta), vbCr, ""), vbLf)
    ReDim polCapa(1 To MAX_POL)
    ReDim polPts(1 To MAX_POL)
    ReDim xs(1 To MAX_PTS)
    ReDim ys(1 To MAX_PTS)
    For i = 0 To UBound(lineas) - 1 Step 2
        cod = Trim(lineas(i)): valor = Trim(lineas(i + 1))
        If cod = "0" Then
            If ent = "POLYLINE" And (valor = "VERTEX") Then
                enVertice = True
            Else
                If (ent = "LWPOLYLINE" Or ent = "POLYLINE") And np >= 3 Then
                    If Not cerrada Then cerrada = (Abs(xs(1) - xs(np)) < 1 And Abs(ys(1) - ys(np)) < 1)
                    If cerrada And nPol < MAX_POL Then
                        nPol = nPol + 1
                        polCapa(nPol) = capa
                        polPts(nPol) = ""
                        For k = 1 To np
                            polPts(nPol) = polPts(nPol) & NumTxt(xs(k)) & " " & NumTxt(ys(k)) & ";"
                            If Not hayPts Then
                                minX = xs(k)
                                maxX = xs(k)
                                minY = ys(k)
                                maxY = ys(k)
                                hayPts = True
                            End If
                            If xs(k) < minX Then minX = xs(k)
                            If xs(k) > maxX Then maxX = xs(k)
                            If ys(k) < minY Then minY = ys(k)
                            If ys(k) > maxY Then maxY = ys(k)
                        Next k
                    End If
                End If
                ent = valor: np = 0: cerrada = False: capa = "": enVertice = False
            End If
        ElseIf ent = "LWPOLYLINE" Or ent = "POLYLINE" Then
            ' en POLYLINE el encabezado trae capa, banderas y un punto de elevación; los puntos son los VERTEX
            If cod = "8" Then
                If Not enVertice Then capa = valor
            ElseIf cod = "70" Then
                If Not enVertice Then cerrada = ((CLng(Val(valor)) And 1) = 1)
            ElseIf cod = "10" Then
                If (ent = "LWPOLYLINE" Or enVertice) And np < MAX_PTS Then
                    np = np + 1
                    xs(np) = Val(valor)
                End If
            ElseIf cod = "20" Then
                If np > 0 And (ent = "LWPOLYLINE" Or enVertice) Then ys(np) = Val(valor)
            End If
        End If
    Next i
    If nPol = 0 Then
        ImportarDXFDesde = "No se encontraron polilíneas cerradas en el archivo." & vbLf & _
            "El plano debe tener los contornos como polilíneas cerradas (ver la hoja Ayuda)."
        Exit Function
    End If
    ' milímetros -> metros, origen arriba a la izquierda (y hacia abajo)
    f = 1
    If maxX - minX > 5000 Or maxY - minY > 5000 Then f = 1000
    Dim sitiosTxt(1 To 48) As String, ter() As String, nTer As Long, otros As Long, ed As Long, fila As Long
    Dim pts As String, cx As Double, cy As Double, s As Long, nombreTer As String, mapaTer As String
    For k = 1 To nPol
        polPts(k) = Normalizar(polPts(k), minX, maxY, f)
    Next k
    Geometria.Range("A4:F2000").ClearContents
    fila = 4
    For k = 1 To nPol
        If IsNumeric(polCapa(k)) Then
            s = CLng(Val(polCapa(k)))
            If s >= 1 And s <= 48 Then
                sitiosTxt(s) = polPts(k)
                EscribirFigura fila, "I_" & s, "I", s, "", polCapa(k), polPts(k)
            End If
        End If
    Next k
    For k = 1 To nPol
        Select Case UCase(polCapa(k))
            Case "ACCESO", "LIVING", "PATIO"
                Centro polPts(k), cx, cy
                s = 0
                For j = 1 To 48
                    If Len(sitiosTxt(j)) > 0 Then
                        If DentroDe(cx, cy, sitiosTxt(j)) Then
                            s = j
                            Exit For
                        End If
                    End If
                Next j
                nombreTer = LCase(polCapa(k))
                If nombreTer = "patio" Then nombreTer = "fondo"
                If s > 0 Then
                    EscribirFigura fila, "E_" & s & "_" & nombreTer, "E", s, nombreTer, polCapa(k), polPts(k)
                    nTer = nTer + 1
                Else
                    otros = otros + 1
                    EscribirFigura fila, "OI_" & polCapa(k) & "_" & k, "O", "", "", polCapa(k) & " (sin sitio)", polPts(k)
                End If
            Case "EDIFICIOS", "EDIFICIO"
                ed = ed + 1
                EscribirFigura fila, "I_ED-" & ed, "I", "ED-" & ed, "", polCapa(k), polPts(k)
                EscribirFigura fila, "E_ED-" & ed & "_unica", "E", "ED-" & ed, "unica", polCapa(k), polPts(k)
            Case Else
                If Not IsNumeric(polCapa(k)) And Left$(UCase(polCapa(k)), 5) <> "ETAPA" Then
                    otros = otros + 1
                    EscribirFigura fila, "OI_" & polCapa(k) & "_" & k, "O", "", "", polCapa(k), polPts(k)
                End If
        End Select
    Next k
    s = 0
    For j = 1 To 48
        If Len(sitiosTxt(j)) > 0 Then s = s + 1
    Next j
    ImportarDXFDesde = "Plano leído: " & s & " sitios, " & nTer & " terrazas, " & ed & " edificios y " & otros & _
        " figuras de otras capas (calle, pasajes, etc.)." & IIf(s < 48, vbLf & "Faltan sitios: revise que cada sitio " & _
        "esté en su capa (1 a 48) como polilínea cerrada.", "")
End Function

Private Sub EscribirFigura(ByRef fila As Long, ByVal nombre As String, ByVal mapa As String, ByVal sitio As Variant, _
                          ByVal terraza As String, ByVal capa As String, ByVal pts As String)
    Geometria.Cells(fila, 1).Value = nombre
    Geometria.Cells(fila, 2).Value = mapa
    Geometria.Cells(fila, 3).Value = sitio
    Geometria.Cells(fila, 4).Value = terraza
    Geometria.Cells(fila, 5).Value = capa
    Geometria.Cells(fila, 6).Value = pts
    fila = fila + 1
End Sub

Private Function Normalizar(ByVal pts As String, ByVal x0 As Double, ByVal y1 As Double, ByVal f As Double) As String
    Dim p() As String, q() As String, i As Long, s As String
    p = Split(pts, ";")
    For i = 0 To UBound(p)
        If Len(p(i)) > 0 Then
            q = Split(p(i), " ")
            s = s & NumTxt(Round((Val(q(0)) - x0) / f, 2)) & " " & NumTxt(Round((y1 - Val(q(1))) / f, 2)) & ";"
        End If
    Next i
    Normalizar = s
End Function

Private Function NumTxt(ByVal x As Double) As String
    ' número como texto con punto decimal (Val lo lee igual en cualquier idioma)
    NumTxt = Replace(CStr(x), ",", ".")
End Function

Private Sub Centro(ByVal pts As String, ByRef cx As Double, ByRef cy As Double)
    Dim p() As String, q() As String, i As Long, n As Long
    cx = 0: cy = 0
    p = Split(pts, ";")
    For i = 0 To UBound(p)
        If Len(p(i)) > 0 Then
            q = Split(p(i), " ")
            cx = cx + Val(q(0)): cy = cy + Val(q(1)): n = n + 1
        End If
    Next i
    If n > 0 Then
        cx = cx / n
        cy = cy / n
    End If
End Sub

Private Function DentroDe(ByVal x As Double, ByVal y As Double, ByVal pts As String) As Boolean
    ' punto en polígono (rayo horizontal)
    Dim p() As String, a() As String, b() As String, i As Long, j As Long, n As Long
    Dim xi As Double, yi As Double, xj As Double, yj As Double
    p = Split(pts, ";")
    n = UBound(p)
    If Len(p(n)) = 0 Then n = n - 1
    j = n
    For i = 0 To n
        a = Split(p(i), " "): b = Split(p(j), " ")
        xi = Val(a(0)): yi = Val(a(1)): xj = Val(b(0)): yj = Val(b(1))
        If ((yi > y) <> (yj > y)) Then
            If x < (xj - xi) * (y - yi) / (yj - yi) + xi Then DentroDe = Not DentroDe
        End If
        j = i
    Next i
End Function

Public Sub DibujarMapas()
    ' dibuja las figuras de la hoja Geometria en los dos mapas del Panel (borra las anteriores)
    Dim i As Long, sh As Shape, nombre As String, mapa As String, ultima As Long, k As Long
    Dim maxX As Double, maxY As Double, p() As String, q() As String, esc As Double
    Dim caja As Range, x0 As Double, y0 As Double, m As Long, ff As FreeformBuilder, texto As String
    For k = Panel.Shapes.Count To 1 Step -1
        nombre = Panel.Shapes(k).Name
        If Left$(nombre, 2) = "I_" Or Left$(nombre, 2) = "E_" Or Left$(nombre, 3) = "OI_" Or Left$(nombre, 3) = "OE_" Then
            Panel.Shapes(k).Delete
        End If
    Next k
    ultima = Geometria.Cells(Geometria.Rows.Count, 1).End(xlUp).Row
    For i = 4 To ultima
        p = Split(CStr(Geometria.Cells(i, 6).Value), ";")
        For k = 0 To UBound(p)
            If Len(p(k)) > 0 Then
                q = Split(p(k), " ")
                If Val(q(0)) > maxX Then maxX = Val(q(0))
                If Val(q(1)) > maxY Then maxY = Val(q(1))
            End If
        Next k
    Next i
    If maxX = 0 Or maxY = 0 Then Exit Sub
    Application.ScreenUpdating = False
    For i = 4 To ultima
        mapa = CStr(Geometria.Cells(i, 2).Value)
        For m = 1 To 2
            If (mapa = "I" And m = 1) Or (mapa = "E" And m = 2) Or mapa = "O" Then
                Set caja = Panel.Range(IIf(m = 1, "CajaMapa1", "CajaMapa2"))
                esc = caja.Width / maxX
                If caja.Height / maxY < esc Then esc = caja.Height / maxY
                x0 = caja.Left + (caja.Width - maxX * esc) / 2
                y0 = caja.Top
                p = Split(CStr(Geometria.Cells(i, 6).Value), ";")
                q = Split(p(0), " ")
                Set ff = Panel.Shapes.BuildFreeform(msoEditingAuto, x0 + Val(q(0)) * esc, y0 + Val(q(1)) * esc)
                For k = 1 To UBound(p)
                    If Len(p(k)) > 0 Then
                        q = Split(p(k), " ")
                        ff.AddNodes msoSegmentLine, msoEditingAuto, x0 + Val(q(0)) * esc, y0 + Val(q(1)) * esc
                    End If
                Next k
                q = Split(p(0), " ")
                ff.AddNodes msoSegmentLine, msoEditingAuto, x0 + Val(q(0)) * esc, y0 + Val(q(1)) * esc
                Set sh = ff.ConvertToShape
                nombre = CStr(Geometria.Cells(i, 1).Value)
                If mapa = "O" Then nombre = IIf(m = 1, "OI_", "OE_") & Mid$(nombre, 4)
                sh.Name = nombre
                sh.Line.ForeColor.RGB = RGB(255, 255, 255)
                sh.Line.Weight = 0.75
                If mapa = "O" Then
                    sh.Fill.ForeColor.RGB = RGB(230, 233, 230)
                    texto = CStr(Geometria.Cells(i, 5).Value)
                Else
                    sh.Fill.ForeColor.RGB = RGB(207, 214, 209)
                    sh.OnAction = "ClicMapa"
                    texto = ""
                    If mapa = "I" Or Geometria.Cells(i, 4).Value = "living" Or Geometria.Cells(i, 4).Value = "unica" Then
                        texto = CStr(Geometria.Cells(i, 3).Value)
                    End If
                End If
                If Len(texto) > 0 Then
                    With sh.TextFrame
                        .Characters.Text = texto
                        .Characters.Font.Size = 7
                        .Characters.Font.Bold = True
                        .HorizontalAlignment = xlHAlignCenter
                        .VerticalAlignment = xlVAlignCenter
                        .MarginLeft = 0: .MarginRight = 0: .MarginTop = 0: .MarginBottom = 0
                    End With
                End If
            End If
        Next m
    Next i
    Application.ScreenUpdating = True
    ColorearMapas
End Sub

' ------------------------------------------------------------ utilidades

Private Function Campo(campos() As String, ByVal col As Long) As String
    If col > 0 And col - 1 <= UBound(campos) Then Campo = Trim(campos(col - 1))
End Function

Private Function Existe(col As Collection, ByVal clave As String) As Boolean
    Dim v As Variant
    On Error GoTo NoEsta
    v = col.Item(clave)
    Existe = True
    Exit Function
NoEsta:
    Existe = False
End Function

Private Function SerieFecha(ByVal v As Variant) As Long
    ' número de serie de una fecha de celda (0 si no es fecha)
    If IsDate(v) Then
        SerieFecha = CLng(CDate(v))
    ElseIf IsNumeric(v) And Not IsEmpty(v) Then
        SerieFecha = CLng(CDbl(v))
    End If
End Function

Public Function LeerFecha(ByVal s As String) As Variant
    ' acepta dd/mm/aaaa, dd-mm-aaaa y aaaa-mm-dd; devuelve Empty si no se reconoce
    Dim p() As String, d As Long, m As Long, a As Long
    s = Trim(Replace(Replace(s, ".", "/"), "-", "/"))
    If InStr(s, " ") > 0 Then s = Left$(s, InStr(s, " ") - 1)
    p = Split(s, "/")
    If UBound(p) <> 2 Then Exit Function
    If Not (IsNumeric(p(0)) And IsNumeric(p(1)) And IsNumeric(p(2))) Then Exit Function
    If Len(p(0)) = 4 Then
        a = CLng(p(0)): m = CLng(p(1)): d = CLng(p(2))
    Else
        d = CLng(p(0)): m = CLng(p(1)): a = CLng(p(2))
    End If
    If a < 100 Then a = a + 2000
    If m < 1 Or m > 12 Or d < 1 Or d > 31 Then Exit Function
    LeerFecha = DateSerial(a, m, d)
End Function

Public Function LeerNumero(ByVal s As String) As Double
    ' "1.234,5" o "1234,5" o "1234.5"
    s = Trim(Replace(s, " ", ""))
    If InStr(s, ",") > 0 And InStr(s, ".") > 0 Then
        s = Replace(s, ".", "")
    End If
    LeerNumero = Val(Replace(s, ",", "."))
End Function

Private Function LeerTexto(ByVal ruta As String) As String
    ' lee el archivo como UTF-8 (o Latin-1 si no es UTF-8 válido), sin depender de librerías de Windows
    Dim f As Integer, n As Long, b() As Byte, i As Long, k As Long, cp As Long, sal As String
    f = FreeFile
    Open ruta For Binary Access Read As #f
    n = LOF(f)
    If n = 0 Then
        Close #f
        Exit Function
    End If
    ReDim b(0 To n - 1)
    Get #f, , b
    Close #f
    sal = Space$(n)
    i = 0: k = 0
    If n >= 3 Then
        If b(0) = &HEF And b(1) = &HBB And b(2) = &HBF Then i = 3
    End If
    Do While i < n
        cp = b(i)
        If cp < &H80 Then
            i = i + 1
        ElseIf cp >= &HC2 And cp < &HE0 And i + 1 < n Then
            If (b(i + 1) And &HC0) = &H80 Then
                cp = (cp And &H1F) * 64 + (b(i + 1) And &H3F): i = i + 2
            Else
                i = i + 1
            End If
        ElseIf cp >= &HE0 And cp < &HF0 And i + 2 < n Then
            If (b(i + 1) And &HC0) = &H80 And (b(i + 2) And &HC0) = &H80 Then
                cp = (cp And &HF) * 4096 + (b(i + 1) And &H3F) * 64 + (b(i + 2) And &H3F): i = i + 3
            Else
                i = i + 1
            End If
        Else
            i = i + 1   ' Latin-1 u otro byte: se deja tal cual
        End If
        k = k + 1
        Mid$(sal, k, 1) = ChrW(cp)
    Loop
    LeerTexto = Left$(sal, k)
End Function
