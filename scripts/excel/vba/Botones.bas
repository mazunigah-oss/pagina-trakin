Option Explicit
Private Const MAX_MOV As Long = 5000   ' filas de datos de la hoja Movimiento (A4:H5003)
' Macros del archivo de seguimiento de movimiento de tierra (Loma La Cruz).
' Funcionan en Excel para Windows y Mac (sin librerías externas).

' ------------------------------------------------------------ fecha y vista

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
End Sub

Public Sub IrHoy()
    ThisWorkbook.Names("FechaPanel").RefersToRange.Formula = "=TODAY()"
End Sub

Public Sub Actualizar()
    Recalcular
    Application.StatusBar = "Datos actualizados a las " & Format(Now, "hh:mm")
End Sub

Public Sub VerFicha()
    Ficha.Activate
End Sub

Public Sub VolverPanel()
    Panel.Activate
End Sub

Public Sub SeleccionarSitio(ByVal idx As Long)
    ' idx = fila del sitio en la hoja Sitios (1 = sitio 1 ... 50 = ED-2)
    If idx < 1 Or idx > 50 Then Exit Sub
    Ficha.Range("C3").Value = Sitios.Cells(idx + 3, 1).Value
    Application.StatusBar = "Sitio seleccionado: " & Sitios.Cells(idx + 3, 1).Value & _
        "  (detalle abajo en el Panel o en la hoja Ficha sitio)"
End Sub

' ------------------------------------------------------------ importar tickets de la máquina (CSV)

Public Sub ImportarCamiones()
    Dim ruta As Variant, res As String
    ruta = Application.GetOpenFilename()
    If VarType(ruta) = vbBoolean Then Exit Sub
    res = ImportarCamionesDesde(CStr(ruta))
    MsgBox res, IIf(Left$(res, 2) = "No", vbExclamation, vbInformation), "Tickets de camiones"
End Sub

Public Function ImportarCamionesDesde(ByVal ruta As String) As String
    ' agrega los tickets nuevos del CSV de la máquina; devuelve el resumen
    Dim texto As String, lineas() As String, sep As String
    Dim cab() As String, i As Long, j As Long, campos() As String
    Dim cTicket As Long, cFecha As Long, cHora As Long, cPatente As Long, cVol As Long
    Dim cSector As Long, cTipo As Long, cEstado As Long, cEmpresa As Long
    Dim fila As Long, nuevos As Long, repetidos As Long, malos As Long, generales As Long
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

    ' tickets ya cargados (ticket + estado)
    fila = UltimaFila(Camiones, 1)
    On Error Resume Next
    For i = 4 To fila
        existentes.Add 1, CStr(Camiones.Cells(i, 1).Value) & "|" & UCase(CStr(Camiones.Cells(i, 9).Value))
    Next i
    On Error GoTo 0
    fila = fila + 1

    Application.ScreenUpdating = False
    CalculoManual True
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
                    Camiones.Cells(fila, 1).Value = Campo(campos, cTicket)
                    Camiones.Cells(fila, 2).Value = f
                    Camiones.Cells(fila, 3).Value = Campo(campos, cHora)
                    Camiones.Cells(fila, 4).Value = UCase(Campo(campos, cPatente))
                    Camiones.Cells(fila, 5).Value = LeerNumero(Campo(campos, cVol))
                    sector = Campo(campos, cSector)
                    If EsSitio(sector) Then
                        Camiones.Cells(fila, 6).Value = CLng(sector)
                    Else
                        generales = generales + 1
                    End If
                    Camiones.Cells(fila, 7).Value = sector
                    Camiones.Cells(fila, 8).Value = Campo(campos, cTipo)
                    Camiones.Cells(fila, 9).Value = estado
                    Camiones.Cells(fila, 10).Value = Campo(campos, cEmpresa)
                    fila = fila + 1
                    nuevos = nuevos + 1
                End If
            End If
        End If
    Next i
    ExtenderFormulas fila
    CalculoManual False
    Application.ScreenUpdating = True
    ImportarCamionesDesde = nuevos & " tickets agregados." & vbLf & _
        IIf(repetidos > 0, repetidos & " ya estaban cargados (no se repiten)." & vbLf, "") & _
        IIf(generales > 0, generales & " sin número de sitio (quedan como generales: pasajes, calle, etc.)." & vbLf, "") & _
        IIf(malos > 0, malos & " filas sin ticket o con fecha no reconocida (se omitieron).", "")
End Function

Private Function UltimaFila(ByVal h As Worksheet, ByVal col As Long) As Long
    ' última fila con datos (los títulos ocupan hasta la fila 3)
    UltimaFila = h.Cells(h.Rows.Count, col).End(xlUp).Row
    If UltimaFila < 3 Then UltimaFila = 3
End Function

Private Sub ExtenderFormulas(ByVal ultima As Long)
    ' las columnas automáticas K:L vienen hasta la fila 5000; si hay más tickets se copian hacia abajo
    Dim hasta As Long
    hasta = UltimaFila(Camiones, 11)
    If ultima > hasta Then
        Camiones.Range(Camiones.Cells(hasta, 11), Camiones.Cells(ultima + 500, 12)).FillDown
    End If
End Sub

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
    MsgBox res, IIf(Left$(res, 2) = "No", vbExclamation, vbInformation), "Planilla de movimiento"
End Sub

Private Function FilasConFecha(ByVal f As Date) As Long
    Dim i As Long, v As Variant
    v = Movimiento.Range("A4:A" & (MAX_MOV + 3)).Value
    For i = 1 To MAX_MOV
        If SerieFecha(v(i, 1)) = CLng(f) Then FilasConFecha = FilasConFecha + 1
    Next i
End Function

Public Function ImportarPlanillaDesde(ByVal ruta As String, ByVal f As Date) As String
    ' copia la planilla "Resumen x Terraza" a la hoja Movimiento con la fecha f (reemplaza las filas de esa fecha)
    Dim wb As Workbook, ws As Worksheet, h As Worksheet
    Dim r As Long, c As Long, filaCab As Long, t As String, i As Long, ultima As Long, fila As Long
    Dim cSitio As Long, cEsc As Long, cCorte As Long, cEsp As Long, cBot As Long
    Dim sitio As Variant, esc As Double, corte As Double, esp As Double, bot As Double
    Dim n As Long, extra As Double, total As Double

    Dim mv As Worksheet
    Set mv = Movimiento   ' referencia tomada antes de abrir la planilla (que pasa a ser el libro activo)
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

    ' 1) leer las filas de sitios de la planilla y cerrarla
    Dim datos() As Double, k As Long, filaTxt As String
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
                If InStr(filaTxt, "ADICIONAL") > 0 Then esc = 0: corte = 0: esp = 0
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

    ' 2) reemplazar los datos de esa fecha: se trabaja sobre una copia en memoria de la hoja y se escribe de una vez
    '    (las filas de esa fecha se vacían, sin borrarlas, para no achicar los rangos de las fórmulas)
    Dim hoja As Variant, libres As Long
    hoja = mv.Range("A4:H" & (MAX_MOV + 3)).Value
    For i = 1 To MAX_MOV
        If SerieFecha(hoja(i, 1)) = CLng(f) Then
            For c = 1 To 8
                hoja(i, c) = Empty
            Next c
        End If
        If IsEmpty(hoja(i, 1)) Then libres = libres + 1
    Next i
    If libres < n Then
        Application.ScreenUpdating = True
        ImportarPlanillaDesde = "No queda espacio en la hoja Movimiento (" & MAX_MOV & " filas). Borre fechas antiguas."
        Exit Function
    End If
    i = 1
    For k = 1 To n
        Do While Not IsEmpty(hoja(i, 1))
            i = i + 1
        Loop
        hoja(i, 1) = f
        For c = 1 To 5
            hoja(i, c + 1) = datos(k, c)
        Next c
    Next k
    mv.Range("A4:H" & (MAX_MOV + 3)).Value = hoja
    Application.ScreenUpdating = True
    Recalcular
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
    Dim s As String, resp As String, texto As String, idx As Variant, fila As Long, sitio As Variant
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
    fila = UltimaFila(Notas, 1) + 1
    Notas.Cells(fila, 1).Value = Now
    Notas.Cells(fila, 2).Value = sitio
    Notas.Cells(fila, 3).Value = Trim(resp)
    Notas.Cells(fila, 4).Value = Trim(texto)
    Ficha.Range("C3").Value = sitio
    MsgBox "Nota agregada al sitio " & sitio & ".", vbInformation
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

Private Sub CalculoManual(ByVal manual As Boolean)
    On Error Resume Next
    If manual Then
        Application.Calculation = xlCalculationManual
    Else
        Application.Calculation = xlCalculationAutomatic
    End If
End Sub

Private Sub Recalcular()
    On Error Resume Next
    Application.CalculateFull
End Sub

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
    If n = 0 Then Close #f: Exit Function
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
