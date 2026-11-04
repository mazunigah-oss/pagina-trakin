"""Genera el archivo Excel con macros (.xlsm) de seguimiento de movimiento de tierra y entregas.

    python scripts/excel/construir.py [salida.xlsm]

Todo se calcula con fórmulas (funciona aunque las macros estén desactivadas); las macros agregan los botones,
el clic en los mapas y la importación de tickets y de la planilla de obra.
"""
import csv
import json
import sys
from datetime import date, datetime
from pathlib import Path

import numpy as np
from matplotlib.path import Path as Poligono
from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.formatting.rule import DataBarRule, FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter as L
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.hyperlink import Hyperlink

sys.path.insert(0, str(Path(__file__).parent))
import vba_proyecto  # noqa: E402
import xlsm  # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]
SALIDA = Path(sys.argv[1]) if len(sys.argv) > 1 else RAIZ / 'data' / 'excel' / 'Seguimiento_Loma_La_Cruz.xlsm'
GEO = json.loads((RAIZ / 'data' / 'geometria.json').read_text())

# colores de la página
VERDE, AMARILLO, GRIS, CLARO, ROJO = '2F9E6B', 'FBE08C', 'CFD6D1', 'F1F3F0', 'E06666'
TINTA, SUAVE, FONDO, BORDE = '1D2320', '5F6B64', 'F6F7F5', 'D9DED9'
AZUL = '3B7DD8'

MAX_MOV, MAX_CAM, MAX_ENT, MAX_GANTT, MAX_NOTAS = 5000, 5000, 400, 400, 2000
PASO = 2.5                                        # metros por celda del mapa
NC, NR = int(GEO['ancho'] / PASO) + 1, int(GEO['alto'] / PASO) + 1
M1, M2, MR = 3, 3 + NC + 6, 22                    # columnas de inicio de los mapas y fila de inicio
G1, G2 = 210, 210 + NC                            # grillas ocultas (índice de sitio / de terraza)
CODS, CODZ, ZSIT = G2 + NC, G2 + NC + 1, G2 + NC + 2  # códigos de color por sitio, por terraza y sitio de cada terraza
ULT = M2 + NC - 1                                 # última columna visible

delgado = Side(style='thin', color=BORDE)
caja = Border(left=delgado, right=delgado, top=delgado, bottom=delgado)


def relleno(c):
    return PatternFill('solid', start_color=c, end_color=c)


def fuente(tam=10, negrita=False, color=TINTA, cursiva=False):
    return Font(name='Calibri', size=tam, bold=negrita, color=color, italic=cursiva)


def fecha_txt(ref):
    """Fecha como texto dd-mm-aaaa sin TEXT() (sus códigos dependen del idioma de Excel)."""
    return f'RIGHT("0"&DAY({ref}),2)&"-"&RIGHT("0"&MONTH({ref}),2)&"-"&YEAR({ref})'


def fecha_corta(ref):
    return f'RIGHT("0"&DAY({ref}),2)&"-"&RIGHT("0"&MONTH({ref}),2)'


def leer_csv(p):
    with open(p, encoding='utf-8-sig') as f:
        return list(csv.DictReader(f, delimiter=';'))


def a_fecha(s):
    s = (s or '').strip()
    if not s:
        return None
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def sitio_de(codigo):
    return int(codigo[2:]) if codigo.startswith('S-') else codigo   # S-07 -> 7 ; ED-1 queda igual


def nombre(wb, n, ref):
    wb.defined_names[n] = DefinedName(n, attr_text=ref)


def encabezados(ws, fila, titulos, anchos, nota_auto=()):
    for i, (t, a) in enumerate(zip(titulos, anchos), 1):
        c = ws.cell(fila, i, t)
        auto = i in nota_auto
        c.font = fuente(10, True, SUAVE if auto else 'FFFFFF')
        c.fill = relleno('E9ECE9' if auto else '2F5D4A')
        c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        c.border = caja
        ws.column_dimensions[L(i)].width = a
    ws.row_dimensions[fila].height = 32
    ws.freeze_panes = ws.cell(fila + 1, 1)


def titulo_hoja(ws, texto, sub=''):
    ws['A1'] = texto
    ws['A1'].font = fuente(15, True)
    if sub:
        ws['A2'] = sub
        ws['A2'].font = fuente(10, color=SUAVE, cursiva=True)


# ---------------------------------------------------------------- datos iniciales

TERRENOS = [sitio_de(t['codigo']) for t in GEO['terrenos']]
TERRENOS = sorted([t for t in TERRENOS if isinstance(t, int)]) + [t for t in TERRENOS if not isinstance(t, int)]
FILA_SITIO = {s: i + 4 for i, s in enumerate(TERRENOS)}            # fila en la hoja Sitios
TERRAZA = {'acceso': 'Acceso', 'living': 'Living', 'fondo_patio': 'Fondo de patio', 'unica': 'Única'}
ZONAS = [(sitio_de(z['terreno']), TERRAZA[z['zona']], z) for z in GEO['zonas']]

# planilla "Resumen x Terraza" al 30/10/2026 (sitio, escarpe, corte geométrico, esc + corte c/esp, a botadero)
MOV_30_10 = [
    (1, 57, 2490, 3566, 3566), (2, 62, 1709, 2479, 2479), (3, 61, 463, 735, 431), (4, 67, 413, 673, 673),
    (5, 59, 590, 909, 909), (6, 48, 590, 894, 894), (7, 45, 599, 902, 902), (8, 46, 533, 811, 811),
    (30, 72, 279, 491, 491), (30, 0, 0, 0, 228), (31, 60, 105, 230, 230), (31, 0, 0, 0, 350),
    (32, 58, 46, 145, 145), (32, 0, 0, 0, 1095), (33, 43, 662, 987, 987), (33, 0, 0, 0, 760),
    (34, 42, 635, 948, 948), (34, 0, 0, 0, 720), (35, 44, 414, 641, 641), (35, 0, 0, 0, 781),
    (36, 49, 458, 709, 709), (36, 0, 0, 0, 554), (47, 57, 1133, 1667, 0), (48, 79, 413, 689, 0),
    (9, 61, 2014, 2905, 2905), (10, 58, 1559, 2263, 2263), (11, 82, 1794, 2626, 2624), (40, 71, 1079, 1610, 1610),
    (41, 68, 1397, 2052, 2052), (42, 52, 1126, 1649, 1649), (43, 66, 688, 1055, 1053), (44, 45, 414, 643, 643),
    (45, 56, 619, 946, 946), (46, 68, 1084, 1613, 1611), (37, 54, 631, 959, 215), (38, 59, 219, 389, 189),
    (39, 75, 74, 209, 209), (39, 0, 0, 0, 80), (25, 73, 1375, 2027, 729), (29, 59, 415, 665, 412),
    (28, 52, 323, 525, 525), (27, 56, 193, 348, 348), (26, 58, 36, 131, 130), (24, 73, 34, 150, 150),
    (23, 66, 40, 148, 64), (22, 68, 19, 122, 50), (21, 79, 0, 110, 50), (20, 68, 0, 95, 50), (19, 71, 35, 148, 50),
    (18, 75, 673, 1047, 584), (17, 74, 252, 457, 269), (16, 63, 785, 1187, 0), (15, 54, 204, 361, 0),
    (14, 59, 0, 83, 0), (13, 55, 6, 85, 0), (12, 99, 734, 1166, 0),
]
FECHA_MOV = date(2026, 10, 30)

# ---------------------------------------------------------------- libro y hojas

wb = Workbook()
wb.code_name = 'ThisWorkbook'
orden = [('Panel', 'Panel'), ('Ficha sitio', 'Ficha'), ('Programa', 'Programa'), ('Sitios', 'Sitios'),
         ('Movimiento', 'Movimiento'), ('Camiones', 'Camiones'), ('Entregas', 'Entregas'), ('Gantt', 'Gantt'),
         ('Notas', 'Notas'), ('Ayuda', 'Ayuda'), ('Listas', 'Listas')]
H = {}
for i, (titulo, codigo) in enumerate(orden):
    ws = wb.active if i == 0 else wb.create_sheet()
    ws.title = titulo
    ws.sheet_properties.codeName = codigo
    H[codigo] = ws
pan, fic, pro, sit, mov, cam, ent, gan, notas, ayu, lis = (H[c] for _, c in orden)
lis.sheet_state = 'hidden'
for ws in H.values():
    ws.sheet_view.showGridLines = ws in (mov, cam, ent, gan, notas)
pan.sheet_properties.tabColor = VERDE
for ws in (mov, cam, ent, gan, notas):
    ws.sheet_properties.tabColor = AMARILLO

# ---------------------------------------------------------------- Movimiento (datos)

titulo_hoja(mov, 'Movimiento de tierra por sitio', 'Pegue aquí la planilla "Resumen x Terraza" (o use el botón '
            '"Planilla de movimiento" del Panel). Una fila por sitio y fecha; las filas sin presupuesto (esponjado 0) '
            'con m³ a botadero cuentan como extra. Se usa el dato más reciente de cada sitio hasta el día del Panel.')
encabezados(mov, 3, ['Fecha', 'Sitio', 'Escarpe m³', 'Corte geométrico m³', 'Esc + corte c/esp m³ (proyectado)',
                     'A botadero m³ (retirado)', 'Extra adicional m³ (opcional)', 'Observación'],
            [12, 8, 12, 14, 18, 16, 16, 40])
for i, (s, e, c, p, b) in enumerate(MOV_30_10, 4):
    for j, v in enumerate([FECHA_MOV, s, e, c, p, b], 1):
        mov.cell(i, j, v)
for r in range(4, MAX_MOV + 4):
    mov.cell(r, 1).number_format = 'dd-mm-yyyy'
    for j in range(3, 8):
        mov.cell(r, j).number_format = '#,##0'
mov.auto_filter.ref = f'A3:H{MAX_MOV + 3}'
MV = {k: f'Movimiento!${c}$4:${c}${MAX_MOV + 3}' for k, c in zip('fecha sitio esc corte proy bot extra'.split(), 'ABCDEFG')}

# ---------------------------------------------------------------- Camiones (datos)

titulo_hoja(cam, 'Tickets de camiones', 'Use el botón "Tickets de camiones (CSV)" del Panel, o pegue las filas desde '
            'la columna A. Sitio = número de sitio (vacío = general: pasajes, calle, etc.). Las columnas grises son '
            'automáticas.')
encabezados(cam, 3, ['Ticket', 'Fecha', 'Hora', 'Patente', 'm³', 'Sitio', 'Sector original', 'Tipo', 'Estado',
                     'Empresa', 'Camión nuevo (período)', 'Camión nuevo (período anterior)'],
            [14, 12, 8, 10, 8, 7, 12, 9, 11, 14, 11, 11], nota_auto=(11, 12))
for i, t in enumerate(leer_csv(RAIZ / 'data' / 'carga_2026-10-19' / '2_tickets_19-10.csv'), 4):
    sector = (t['SECTOR'] or '').strip()
    vals = [t['TICKET'], a_fecha(t['FECHA']), t['HORA'], t['PATENTE'], float(t['VOLUMEN_M3'].replace(',', '.')),
            int(sector) if sector.isdigit() and 1 <= int(sector) <= 48 else None, sector, t['TIPO'] or None,
            t['ESTADO'] or 'VALIDO', t.get('EMPRESA') or None]
    for j, v in enumerate(vals, 1):
        cam.cell(i, j, v)
CM = {k: f'Camiones!${c}$4:${c}${MAX_CAM + 3}' for k, c in
      zip('ticket fecha hora patente m3 sitio sector tipo estado empresa nuevo nuevo_ant'.split(), 'ABCDEFGHIJKL')}
for r in range(4, MAX_CAM + 4):
    cam.cell(r, 1).number_format = '@'
    cam.cell(r, 2).number_format = 'dd-mm-yyyy'
    cam.cell(r, 3).number_format = '@'
    cam.cell(r, 7).number_format = '@'
    for k, (ini, fin) in ((11, ('PerIni', 'PerFin')), (12, ('PrevIni', 'PrevFin'))):
        cam.cell(r, k, f'=IF(OR(B{r}="",B{r}<{ini},B{r}>{fin}),"",IF(COUNTIFS($D$4:D{r},D{r},$B$4:B{r},">="&{ini},'
                       f'$B$4:B{r},"<="&{fin})=1,1,0))').font = fuente(9, color=SUAVE)
cam.auto_filter.ref = f'A3:L{MAX_CAM + 3}'
dv = DataValidation(type='list', formula1='"VALIDO,ANULACION"', allow_blank=True)
cam.add_data_validation(dv)
dv.add(f'I4:I{MAX_CAM + 3}')

# ---------------------------------------------------------------- Entregas (datos)

titulo_hoja(ent, 'Entregas de terrazas', 'Cambie el estado con la lista desplegable y anote la fecha de entrega. '
            'Un sitio está entregado cuando su acceso y su living están entregados (el fondo de patio no se considera).')
encabezados(ent, 3, ['Sitio', 'Terraza', 'Estado', 'Fecha entrega', 'Observación', 'Estado al día del Panel', 'Clave'],
            [8, 15, 13, 13, 40, 16, 10], nota_auto=(6, 7))
entregadas = {(int(r['sitio']), r['zona']) for r in leer_csv(RAIZ / 'data' / 'carga_2026-10-19' /
                                                              '3_terrazas_entregadas.csv') if r['estado'] == 'entregado'}
zonas_orden = sorted(ZONAS, key=lambda x: (TERRENOS.index(x[0]), ['Acceso', 'Living', 'Fondo de patio', 'Única']
                                                                  .index(x[1])))
for i, (s, t, z) in enumerate(zonas_orden, 4):
    clave_csv = {'Acceso': 'acceso', 'Living': 'living'}.get(t)
    ent.cell(i, 1, s)
    ent.cell(i, 2, t)
    ent.cell(i, 3, 'Entregada' if (s, clave_csv) in entregadas else 'Pendiente')
for r in range(4, MAX_ENT + 4):
    ent.cell(r, 4).number_format = 'dd-mm-yyyy'
    ent.cell(r, 6, f'=IF(A{r}="","",IF(AND(C{r}="Entregada",D{r}<>"",D{r}>FechaPanel),"En proceso",C{r}))').font = \
        fuente(9, color=SUAVE)
    ent.cell(r, 7, f'=IF(A{r}="","",A{r}&"|"&B{r})').font = fuente(9, color=SUAVE)
ent.auto_filter.ref = f'A3:G{MAX_ENT + 3}'
for rng, lista in ((f'C4:C{MAX_ENT + 3}', '"Pendiente,En proceso,Entregada"'),
                   (f'B4:B{MAX_ENT + 3}', '"Acceso,Living,Fondo de patio,Única"')):
    dv = DataValidation(type='list', formula1=lista, allow_blank=True)
    ent.add_data_validation(dv)
    dv.add(rng)
EN = {k: f'Entregas!${c}$4:${c}${MAX_ENT + 3}' for k, c in zip('sitio terraza estado fecha obs aldia clave'.split(),
                                                                 'ABCDEFG')}

# ---------------------------------------------------------------- Gantt (datos)

titulo_hoja(gan, 'Carta Gantt (programa)', 'Una fila por sitio con el inicio y el término del programa. Si un sitio '
            'tiene varias filas se usa el primer inicio y el último término. La fecha de término es la fecha en que '
            'acceso y living deberían estar entregados.')
encabezados(gan, 3, ['Sitio', 'Inicio', 'Término', 'Tarea'], [8, 12, 12, 70])
for i, g in enumerate(sorted(leer_csv(RAIZ / 'data' / 'carga_inicial' / '5_programa_gantt.csv'),
                             key=lambda g: int(g['sitio'])), 4):
    gan.cell(i, 1, int(g['sitio']))
    gan.cell(i, 2, a_fecha(g['inicio']))
    gan.cell(i, 3, a_fecha(g['termino']))
    gan.cell(i, 4, g['tarea'])
for r in range(4, MAX_GANTT + 4):
    gan.cell(r, 2).number_format = gan.cell(r, 3).number_format = 'dd-mm-yyyy'
gan.auto_filter.ref = f'A3:D{MAX_GANTT + 3}'
GT = {k: f'Gantt!${c}$4:${c}${MAX_GANTT + 3}' for k, c in zip(('sitio', 'ini', 'fin'), 'ABC')}

# ---------------------------------------------------------------- Notas (datos)

titulo_hoja(notas, 'Notas por sitio 📌', 'Bitácora: cada actualización es una fila nueva (botón "Agregar nota" del '
            'Panel o de la Ficha, o escribiendo directo aquí).')
encabezados(notas, 3, ['Fecha y hora', 'Sitio', 'Responsable', 'Nota'], [17, 8, 20, 90])
for r in range(4, MAX_NOTAS + 4):
    notas.cell(r, 1).number_format = 'dd-mm-yyyy hh:mm'
    notas.cell(r, 4).alignment = Alignment(wrap_text=True, vertical='top')
notas.auto_filter.ref = f'A3:D{MAX_NOTAS + 3}'
NT = {k: f'Notas!${c}$4:${c}${MAX_NOTAS + 3}' for k, c in zip(('fecha', 'sitio', 'resp', 'nota'), 'ABCD')}

# ---------------------------------------------------------------- Listas (oculta): período y gráfico

lis['A1'], lis['B1'] = 'Parámetro', 'Valor'
filas_lis = [
    ('PerIni', '=IF(Vista="Semana",FechaPanel-WEEKDAY(FechaPanel,2)+1,FechaPanel)'),
    ('PerFin', '=IF(Vista="Semana",B2+6,FechaPanel)'),
    ('PrevIni', '=B2-IF(Vista="Semana",7,1)'),
    ('PrevFin', '=B3-IF(Vista="Semana",7,1)'),
    ('PerTxt', f'=IF(Vista="Semana","semana del "&{fecha_corta("B2")}&" al "&{fecha_txt("B3")},"día "&{fecha_txt("B2")})'),
    ('PrevTxt', '=IF(Vista="Semana","semana anterior","día anterior")'),
]
for i, (n, f) in enumerate(filas_lis, 2):
    lis.cell(i, 1, n)
    lis.cell(i, 2, f).number_format = 'dd-mm-yyyy'
    nombre(wb, n, f'Listas!$B${i}')
# serie para el gráfico: 14 días o 14 semanas hasta el período elegido
lis['D1'], lis['E1'], lis['F1'], lis['G1'], lis['H1'] = 'Desde', 'Hasta', 'Etiqueta', 'm³', 'Viajes'
for k in range(14):
    r = k + 2
    lis.cell(r, 4, f'=PerIni-IF(Vista="Semana",7,1)*{13 - k}').number_format = 'dd-mm-yyyy'
    lis.cell(r, 5, f'=D{r}+IF(Vista="Semana",6,0)').number_format = 'dd-mm-yyyy'
    lis.cell(r, 6, f'={fecha_corta(f"D{r}")}')
    lis.cell(r, 7, f'=SUMIFS({CM["m3"]},{CM["fecha"]},">="&D{r},{CM["fecha"]},"<="&E{r})')
    lis.cell(r, 8, f'=COUNTIFS({CM["fecha"]},">="&D{r},{CM["fecha"]},"<="&E{r},{CM["estado"]},"VALIDO")'
                   f'-COUNTIFS({CM["fecha"]},">="&D{r},{CM["fecha"]},"<="&E{r},{CM["estado"]},"ANULACION")')
# lista de sitios para las listas desplegables
lis['J1'] = 'Sitios'
for i, s in enumerate(TERRENOS, 2):
    lis.cell(i, 10, s)
nombre(wb, 'ListaSitios', f'Listas!$J$2:$J${len(TERRENOS) + 1}')
# terrazas del mapa: sitio, terraza, fila del sitio, código de color
lis['L1'], lis['M1'], lis['N1'], lis['O1'] = 'Sitio', 'Terraza', 'Fila sitio', 'Código mapa entregas'
for zi, (s, t, z) in enumerate(ZONAS, 1):
    r = zi + 1
    lis.cell(r, 12, s)
    lis.cell(r, 13, t)
    lis.cell(r, 14, FILA_SITIO[s] - 3)
    lis.cell(r, 15, f'=IF(M{r}="Fondo de patio",5,IF(IFERROR(INDEX({EN["aldia"]},MATCH(L{r}&"|"&M{r},{EN["clave"]},0)),'
                    f'"Pendiente")="Entregada",1,IF(INDEX(Sitios!$U$4:$U$53,N{r})=1,2,IF(IFERROR(INDEX({EN["aldia"]},'
                    f'MATCH(L{r}&"|"&M{r},{EN["clave"]},0)),"")="En proceso",3,4))))')

# ---------------------------------------------------------------- Sitios (cálculo y detalle)

titulo_hoja(sit, 'Detalle por sitio', '')
sit['A2'] = f'="Al "&{fecha_txt("FechaPanel")}&" · avance = m³ retirados / m³ proyectados (esponjados). El extra (proforma) no entra al avance."'
sit['A2'].font = fuente(10, color=SUAVE, cursiva=True)
cols_sit = ['Sitio', 'Fecha del dato', 'Escarpe m³', 'Corte geom. m³', 'Proyectado m³', 'Retirado planilla m³',
            'Camiones posteriores m³', 'Retirado total m³', 'Avance', 'Extra m³ (proforma)', 'Movimiento', 'Acceso',
            'Living', 'Entregado', 'Fecha entrega', 'Inicio Gantt', 'Término Gantt', 'Cumplimiento carta Gantt',
            'Notas', 'cód. interv.', 'debe entregar', 'etiqueta interv.', 'etiqueta entregas']
encabezados(sit, 3, cols_sit, [7, 11, 10, 11, 12, 12, 12, 12, 16, 12, 15, 11, 11, 10, 11, 11, 11, 21, 7, 7, 7, 9, 9],
            nota_auto=(20, 21, 22, 23))
for s in TERRENOS:
    r = FILA_SITIO[s]
    terr = '"Única"' if not isinstance(s, int) else None
    f = {
        1: s,
        2: f'=IFERROR(_xlfn.AGGREGATE(14,6,{MV["fecha"]}/({MV["sitio"]}=A{r})/({MV["fecha"]}<=FechaPanel),1),"")',
        3: f'=IF(B{r}="",0,SUMIFS({MV["esc"]},{MV["sitio"]},A{r},{MV["fecha"]},B{r}))',
        4: f'=IF(B{r}="",0,SUMIFS({MV["corte"]},{MV["sitio"]},A{r},{MV["fecha"]},B{r}))',
        5: f'=IF(B{r}="",0,SUMIFS({MV["proy"]},{MV["sitio"]},A{r},{MV["fecha"]},B{r}))',
        6: f'=IF(B{r}="",0,SUMIFS({MV["bot"]},{MV["sitio"]},A{r},{MV["fecha"]},B{r},{MV["proy"]},">0"))',
        7: f'=SUMIFS({CM["m3"]},{CM["sitio"]},A{r},{CM["fecha"]},">"&IF(B{r}="",0,B{r}),{CM["fecha"]},"<="&FechaPanel)',
        8: f'=F{r}+G{r}',
        9: f'=IF(E{r}>0,H{r}/E{r},"")',
        10: f'=IF(B{r}="",0,SUMIFS({MV["bot"]},{MV["sitio"]},A{r},{MV["fecha"]},B{r})-F{r}'
            f'+SUMIFS({MV["extra"]},{MV["sitio"]},A{r},{MV["fecha"]},B{r}))',
        11: f'=IF(AND(E{r}>0,H{r}>=0.99*E{r}),"Completo",IF(H{r}+J{r}>0,"En intervención","Sin intervenir"))',
        12: f'=IFERROR(INDEX({EN["aldia"]},MATCH(A{r}&"|"&{terr or chr(34) + "Acceso" + chr(34)},{EN["clave"]},0)),"Pendiente")',
        13: f'=IFERROR(INDEX({EN["aldia"]},MATCH(A{r}&"|"&{terr or chr(34) + "Living" + chr(34)},{EN["clave"]},0)),"Pendiente")',
        14: f'=IF(AND(L{r}="Entregada",M{r}="Entregada"),"Sí","No")',
        15: f'=IF(N{r}="Sí",IF(MAX(SUMIFS({EN["fecha"]},{EN["clave"]},A{r}&"|"&{terr or chr(34) + "Acceso" + chr(34)}),'
            f'SUMIFS({EN["fecha"]},{EN["clave"]},A{r}&"|"&{terr or chr(34) + "Living" + chr(34)}))=0,"",'
            f'MAX(SUMIFS({EN["fecha"]},{EN["clave"]},A{r}&"|"&{terr or chr(34) + "Acceso" + chr(34)}),'
            f'SUMIFS({EN["fecha"]},{EN["clave"]},A{r}&"|"&{terr or chr(34) + "Living" + chr(34)}))),"")',
        16: f'=IFERROR(_xlfn.AGGREGATE(15,6,{GT["ini"]}/({GT["sitio"]}=A{r}),1),"")',
        17: f'=IFERROR(_xlfn.AGGREGATE(14,6,{GT["fin"]}/({GT["sitio"]}=A{r}),1),"")',
        18: f'=IF(Q{r}="","Sin programa",IF(N{r}="Sí",IF(O{r}="","Entregado",IF(O{r}<=Q{r},"Entregado a tiempo",'
            f'"Entregado con atraso")),IF(FechaPanel>Q{r},"Atrasado","Pendiente")))',
        19: f'=COUNTIF({NT["sitio"]},A{r})',
        20: f'=IF(K{r}="Completo",1,IF(K{r}="En intervención",2,3))',
        21: f'=IF(AND(Q{r}<>"",N{r}="No"),IF(FechaPanel>Q{r},1,0),0)',
        22: f'=A{r}&IF(J{r}>0," ⚠","")',
        23: f'=A{r}&IF(N{r}="Sí"," ✅",IF(U{r}=1," ⚠",""))',
    }
    for j, v in f.items():
        c = sit.cell(r, j, v)
        c.border = caja
        c.font = fuente(10, j == 1)
        c.alignment = Alignment(horizontal='center')
        if j in (20, 21, 22, 23):
            c.font = fuente(8, color=SUAVE)
    for j in (2, 15, 16, 17):
        sit.cell(r, j).number_format = 'dd-mm-yyyy'
    for j in (3, 4, 5, 6, 7, 8, 10):
        sit.cell(r, j).number_format = '#,##0'
    sit.cell(r, 9).number_format = '0.0%'
ult_s = FILA_SITIO[TERRENOS[-1]]
r_tot = ult_s + 2
sit.cell(r_tot, 1, 'Total sitios').font = fuente(10, True)
for j in (3, 4, 5, 6, 7, 8, 10):
    sit.cell(r_tot, j, f'=SUM({L(j)}4:{L(j)}51)').number_format = '#,##0'
    sit.cell(r_tot, j).font = fuente(10, True)
sit.cell(r_tot, 9, f'=IF(E{r_tot}>0,H{r_tot}/E{r_tot},"")').number_format = '0.0%'
sit.cell(ult_s + 1, 20, 0)  # fila 54: centinela (celdas del mapa sin sitio)
sit.conditional_formatting.add(f'I4:I{ult_s}', DataBarRule(start_type='num', start_value=0, end_type='num',
                                                            end_value=1, color=VERDE))
for col, reglas in (('K', [('Completo', VERDE, 'FFFFFF'), ('En intervención', AMARILLO, TINTA)]),
                    ('R', [('Atrasado', ROJO, 'FFFFFF'), ('Entregado', VERDE, 'FFFFFF')]),
                    ('N', [('Sí', VERDE, 'FFFFFF')])):
    for txt, bg, fg in reglas:
        sit.conditional_formatting.add(f'{col}4:{col}{ult_s}', FormulaRule(
            formula=[f'LEFT({col}4,{len(txt)})="{txt}"'], fill=relleno(bg), font=Font(color=fg, bold=True)))
for col in ('L', 'M'):
    sit.conditional_formatting.add(f'{col}4:{col}{ult_s}', FormulaRule(formula=[f'{col}4="Entregada"'],
                                                                      fill=relleno('D5EEDF')))
sit.column_dimensions.group('T', 'W', hidden=True)
sit.auto_filter.ref = f'A3:S{ult_s}'
SI = {k: f'Sitios!${c}$4:${c}$51' for k, c in zip('sitio fdato esc corte proy retpl cam ret av extra mov acc liv '
                                                   'entr fent ini fin cumpl notas cod debe'.split(), 'ABCDEFGHIJKLMNOPQRSTU')}

# ---------------------------------------------------------------- Panel

for c in range(1, ULT + 3):
    pan.column_dimensions[L(c)].width = 0.86 if c >= M1 else 1.7
pan.sheet_view.zoomScale = 100


def unir(ws, r1, c1, r2, c2, valor=None, f=None, fill=None, al='center', borde=None, fmt=None):
    if (r1, c1) != (r2, c2):
        ws.merge_cells(start_row=r1, start_column=c1, end_row=r2, end_column=c2)
    c = ws.cell(r1, c1)
    if valor is not None:
        c.value = valor
    c.font = f or fuente()
    c.alignment = Alignment(horizontal=al, vertical='center', wrap_text=True)
    if fill:
        for rr in range(r1, r2 + 1):
            for cc in range(c1, c2 + 1):
                ws.cell(rr, cc).fill = relleno(fill)
    if borde:
        for rr in range(r1, r2 + 1):
            for cc in range(c1, c2 + 1):
                ws.cell(rr, cc).border = borde
    if fmt:
        c.number_format = fmt
    return c


def boton(ws, r, c1, c2, texto, nombre_btn, color='2F5D4A', destino=None):
    celda = unir(ws, r, c1, r, c2, texto, fuente(10, True, 'FFFFFF'), color, borde=Border())
    celda.hyperlink = Hyperlink(ref=celda.coordinate, location=destino or f"'{ws.title}'!{celda.coordinate}",
                                tooltip=texto)
    celda.font = fuente(10, True, 'FFFFFF')   # el vínculo aplica el estilo "Hipervínculo"; se deja como botón
    if nombre_btn:
        nombre(wb, nombre_btn, f"'{ws.title}'!${L(c1)}${r}:${L(c2)}${r}")
    return celda


alturas = {1: 32, 2: 18, 3: 6, 4: 24, 5: 5, 6: 24, 7: 10, 8: 22, 9: 15, 10: 30, 11: 15, 12: 10, 13: 22, 14: 15,
           15: 30, 16: 15, 17: 10, 18: 22, 19: 14, 20: 4, 21: 4}
for r, h in alturas.items():
    pan.row_dimensions[r].height = h
unir(pan, 1, M1, 1, ULT, 'Avance movimiento de tierra — Loma La Cruz', fuente(20, True), al='left')
unir(pan, 2, M1, 2, ULT, f'="48 sitios · Etapas 1 y 2 · datos al "&{fecha_txt("FechaPanel")}&'
                         f'"   (los datos se editan en las hojas amarillas)"', fuente(10, color=SUAVE), al='left')
# controles
unir(pan, 4, M1, 4, M1 + 13, 'Ver al día', fuente(10, True), al='right')
dia = unir(pan, 4, M1 + 15, 4, M1 + 34, '=TODAY()', fuente(12, True), 'FFF7D6', borde=caja, fmt='dd-mm-yyyy')
nombre(wb, 'FechaPanel', f'Panel!${L(M1 + 15)}$4')
dv = DataValidation(type='date', operator='greaterThan', formula1='40000', allow_blank=False,
                    error='Escriba una fecha (dd-mm-aaaa).', errorTitle='Fecha', showErrorMessage=True)
pan.add_data_validation(dv)
dv.add(dia.coordinate)
boton(pan, 4, M1 + 37, M1 + 52, '◀ Anterior', 'BtnAnterior')
boton(pan, 4, M1 + 54, M1 + 63, 'Hoy', 'BtnHoy')
boton(pan, 4, M1 + 65, M1 + 80, 'Siguiente ▶', 'BtnSiguiente')
unir(pan, 4, M1 + 84, 4, M1 + 93, 'Vista', fuente(10, True), al='right')
vista = unir(pan, 4, M1 + 95, 4, M1 + 112, 'Día', fuente(12, True), 'FFF7D6', borde=caja)
nombre(wb, 'Vista', f'Panel!${L(M1 + 95)}$4')
dv = DataValidation(type='list', formula1='"Día,Semana"', allow_blank=False)
pan.add_data_validation(dv)
dv.add(vista.coordinate)
boton(pan, 4, M1 + 116, M1 + 135, '↻ Actualizar', 'BtnActualizar', AZUL)
unir(pan, 4, M1 + 138, 4, ULT, '◀ ▶ mueven un día o una semana según la vista', fuente(9, color=SUAVE, cursiva=True),
     al='left')
unir(pan, 6, M1, 6, M1 + 13, 'Cargar', fuente(10, True), al='right')
boton(pan, 6, M1 + 15, M1 + 48, '📥 Tickets de camiones (CSV)', 'BtnCamiones', 'B07A1F')
boton(pan, 6, M1 + 50, M1 + 83, '📥 Planilla de movimiento', 'BtnPlanilla', 'B07A1F')
boton(pan, 6, M1 + 85, M1 + 106, '📌 Agregar nota', 'BtnNota', 'B07A1F')
boton(pan, 6, M1 + 108, M1 + 127, '🔎 Ficha de sitio', 'BtnFicha', '2F5D4A')
boton(pan, 6, M1 + 129, M1 + 144, '❔ Ayuda', None, '5F6B64', destino="'Ayuda'!A1")

# indicadores
ANCHO_T = (ULT - M1 + 1 - 3 * 3) // 4


def tile(r, k, etiqueta, valor, sub, fmt=None, color_sub=SUAVE):
    c1 = M1 + k * (ANCHO_T + 3)
    c2 = c1 + ANCHO_T - 1
    unir(pan, r, c1, r, c2, etiqueta, fuente(9, True, SUAVE), FONDO, al='left')
    unir(pan, r + 1, c1, r + 1, c2, valor, fuente(18, True), FONDO, al='left', fmt=fmt)
    unir(pan, r + 2, c1, r + 2, c2, sub, fuente(9, color=color_sub), FONDO, al='left')


cam_p = f'SUM({CM["nuevo"]})'
cam_a = f'SUM({CM["nuevo_ant"]})'


def viajes(i, f):
    return (f'(COUNTIFS({CM["fecha"]},">="&{i},{CM["fecha"]},"<="&{f},{CM["estado"]},"VALIDO")'
            f'-COUNTIFS({CM["fecha"]},">="&{i},{CM["fecha"]},"<="&{f},{CM["estado"]},"ANULACION"))')


def m3(i, f, extra=''):
    return f'SUMIFS({CM["m3"]},{CM["fecha"]},">="&{i},{CM["fecha"]},"<="&{f}{extra})'


def comparar(a, b):
    return f'=IF(({a})-({b})>=0,"+","−")&FIXED(ABS(({a})-({b})),0)&" vs "&PrevTxt'


unir(pan, 8, M1, 8, ULT, '="🚚 Camiones — "&PerTxt', fuente(13, True), al='left')
tile(9, 0, 'Camiones (patentes distintas)', f'={cam_p}', comparar(cam_p, cam_a), '0')
tile(9, 1, 'Viajes (válidos − anulados)', f'={viajes("PerIni", "PerFin")}',
     comparar(viajes('PerIni', 'PerFin'), viajes('PrevIni', 'PrevFin')), '0')
tile(9, 2, 'm³ a botadero', f'={m3("PerIni", "PerFin")}', comparar(m3('PerIni', 'PerFin'), m3('PrevIni', 'PrevFin')),
     '#,##0')
SIN_SITIO = ',' + CM['sitio'] + ',""'
tile(9, 3, 'm³ sin sitio (pasajes, calle, general)', '=' + m3('PerIni', 'PerFin', SIN_SITIO),
     '="no se suman al avance de los sitios"', '#,##0')

unir(pan, 13, M1, 13, ULT, f'="📊 Avance general al "&{fecha_txt("FechaPanel")}', fuente(13, True), al='left')
proy, ret = f'SUM({SI["proy"]})', f'SUM({SI["ret"]})'
deben = f'COUNTIF({SI["debe"]},1)+COUNTIFS({SI["fin"]},"<"&FechaPanel,{SI["entr"]},"Sí")'
cumplen = f'COUNTIFS({SI["fin"]},"<"&FechaPanel,{SI["entr"]},"Sí")'
tile(14, 0, 'Avance movimiento de tierra', f'=IF({proy}>0,{ret}/{proy},0)',
     f'=FIXED({ret},0)&" de "&FIXED({proy},0)&" m³ (esponjados)"', '0.0%')
tile(14, 1, 'Movimiento extra (proforma)', '=SUM(Sitios!$J$4:$J$53)', '="no entra al avance"', '#,##0" m³"')
tile(14, 2, 'Sitios entregados', f'=COUNTIF({SI["entr"]},"Sí")', '="acceso y living entregados"', '0')
tile(14, 3, 'Cumplimiento carta Gantt', f'={cumplen}&" de "&({deben})',
     f'=IF(({deben})-({cumplen})>0,FIXED(({deben})-({cumplen}),0)&" atrasados (deberían estar entregados)","al día")',
     None, ROJO)

# mapas
unir(pan, 18, M1, 18, M1 + NC - 1, 'Mapa de intervención', fuente(13, True), al='left')
unir(pan, 18, M2, 18, M2 + NC - 1, 'Mapa de entregas y cumplimiento', fuente(13, True), al='left')
unir(pan, 19, M1, 19, ULT, 'Haga clic en un sitio de cualquiera de los mapas para ver su detalle (abajo).',
     fuente(9, color=SUAVE, cursiva=True), al='left')

ys, xs = np.mgrid[0:NR, 0:NC]
centros = np.c_[(xs.ravel() + .5) * PASO, (ys.ravel() + .5) * PASO]
gz = np.zeros((NR, NC), int)                       # índice de terraza (1..146), 0 = nada
for zi, (_, _, z) in enumerate(ZONAS, 1):
    m = Poligono(z['puntos']).contains_points(centros).reshape(NR, NC) & (gz == 0)
    gz[m] = zi
zona_fila = np.array([0] + [FILA_SITIO[s] - 3 for s, _, _ in ZONAS])
gs = zona_fila[gz]                                 # índice de sitio (1..50), 0 = nada
SIN_S, SIN_Z = len(TERRENOS) + 1, len(ZONAS) + 1   # centinelas (código 0)
blanco = Side(style='thin', color='FFFFFF')
bordes = {}


def borde_celda(g, r, c):
    v = g[r, c]
    lados = tuple(not (0 <= rr < NR and 0 <= cc < NC) or g[rr, cc] != v
                  for rr, cc in ((r, c - 1), (r, c + 1), (r - 1, c), (r + 1, c)))
    if lados not in bordes:
        bordes[lados] = Border(*(blanco if x else Side() for x in lados))
    return bordes[lados]


for r in range(NR):
    pan.row_dimensions[MR + r].height = 4.6
    for c in range(NC):
        if gs[r, c]:
            pan.cell(MR + r, M1 + c).border = borde_celda(gs, r, c)
            pan.cell(MR + r, M2 + c).border = borde_celda(gz, r, c)
        pan.cell(MR + r, G1 + c, int(gs[r, c]) or SIN_S)
        pan.cell(MR + r, G2 + c, int(gz[r, c]) or SIN_Z)
for i in range(SIN_S):
    pan.cell(MR + i, CODS, f'=Sitios!T{i + 4}' if i < len(TERRENOS) else 0)
for i in range(SIN_Z):
    pan.cell(MR + i, CODZ, f'=Listas!O{i + 2}' if i < len(ZONAS) else 0)
    pan.cell(MR + i, ZSIT, int(zona_fila[i + 1]) if i < len(ZONAS) else 0)
for c in range(G1, ZSIT + 1):
    pan.column_dimensions[L(c)].hidden = True
rango1 = f'{L(M1)}{MR}:{L(M1 + NC - 1)}{MR + NR - 1}'
rango2 = f'{L(M2)}{MR}:{L(M2 + NC - 1)}{MR + NR - 1}'
nombre(wb, 'MapaInterv', f'Panel!${L(M1)}${MR}:${L(M1 + NC - 1)}${MR + NR - 1}')
nombre(wb, 'MapaEntregas', f'Panel!${L(M2)}${MR}:${L(M2 + NC - 1)}${MR + NR - 1}')
nombre(wb, 'GrillaSitios', f'Panel!${L(G1)}${MR}:${L(G1 + NC - 1)}${MR + NR - 1}')
nombre(wb, 'GrillaZonas', f'Panel!${L(G2)}${MR}:${L(G2 + NC - 1)}${MR + NR - 1}')
nombre(wb, 'ZonaSitio', f'Panel!${L(ZSIT)}${MR}:${L(ZSIT)}${MR + SIN_Z - 1}')
cods = f'${L(CODS)}${MR}:${L(CODS)}${MR + SIN_S - 1}'
codz = f'${L(CODZ)}${MR}:${L(CODZ)}${MR + SIN_Z - 1}'
for k, color in ((1, VERDE), (2, AMARILLO), (3, GRIS)):
    pan.conditional_formatting.add(rango1, FormulaRule(formula=[f'INDEX({cods},{L(G1)}{MR})={k}'],
                                                       fill=relleno(color), stopIfTrue=True))
for k, color in ((1, VERDE), (2, ROJO), (3, AMARILLO), (4, GRIS), (5, CLARO)):
    pan.conditional_formatting.add(rango2, FormulaRule(formula=[f'INDEX({codz},{L(G2)}{MR})={k}'],
                                                       fill=relleno(color), stopIfTrue=True))
# números de sitio (en la celda del sitio más cercana a su centro)
for s in TERRENOS:
    i = FILA_SITIO[s] - 3
    rr, cc = np.nonzero(gs == i)
    if not len(rr):
        continue
    k = np.argmin((rr - rr.mean()) ** 2 + (cc - cc.mean()) ** 2)
    for col0, colf in ((M1, 'V'), (M2, 'W')):
        c = pan.cell(MR + int(rr[k]), col0 + int(cc[k]), f'=Sitios!{colf}{FILA_SITIO[s]}')
        c.font = fuente(7, True)
        c.alignment = Alignment(horizontal='center', vertical='center')

# leyendas
r0 = MR + NR + 1
pan.row_dimensions[r0 - 1].height = 8


def leyenda(r, col0, color, texto):
    pan.row_dimensions[r].height = 15
    unir(pan, r, col0, r, col0 + 2, None, fill=color)
    unir(pan, r, col0 + 4, r, col0 + NC - 1, texto, fuente(9), al='left')


leyenda(r0, M1, VERDE, f'="Movimiento completo ("&COUNTIF({SI["mov"]},"Completo")&") — 100 % del volumen proyectado"')
leyenda(r0 + 1, M1, AMARILLO, f'="Con intervención ("&COUNTIF({SI["mov"]},"En intervención")&") — se está trabajando"')
leyenda(r0 + 2, M1, GRIS, f'="Sin intervención ("&COUNTIF({SI["mov"]},"Sin intervenir")&")"')
leyenda(r0 + 3, M1, 'FFFFFF', f'="⚠ Movimiento extra ("&COUNTIF({SI["extra"]},">0")&") — retiró volumen adicional '
                              f'al proyectado (proforma)"')
leyenda(r0, M2, VERDE, f'="✅ Entregada ("&COUNTIF({SI["entr"]},"Sí")&" sitios) — acceso y living entregados"')
leyenda(r0 + 1, M2, ROJO, f'="⚠ Debería estar entregada ("&COUNTIF({SI["debe"]},1)&" sitios) — su fecha de la carta '
                          f'Gantt ya pasó"')
leyenda(r0 + 2, M2, AMARILLO, 'En proceso de entrega')
leyenda(r0 + 3, M2, GRIS, 'Pendiente — aún no le toca')
leyenda(r0 + 4, M2, CLARO, 'Fondo de patio — no se considera en las entregas')

# sitio seleccionado (se elige con clic en el mapa o en la hoja Ficha sitio)
rs = r0 + 6
pan.row_dimensions[rs].height = 24
SEL = "'Ficha sitio'!$C$3"
fila_sel = f'MATCH({SEL},{SI["sitio"].replace("$51", "$53")},0)'


def dato(col):
    return f'INDEX(Sitios!${col}$4:${col}$53,{fila_sel})'


unir(pan, rs, M1, rs, ULT, f'=IFERROR("🔎 Sitio "&{SEL}&" — "&{dato("K")}&" · "&{dato("R")},'
                           f'"🔎 Haga clic en un sitio del mapa")', fuente(13, True), FONDO, al='left')
campos_sel = [
    ('Avance', f'=IFERROR(IF({dato("E")}>0,FIXED(100*{dato("H")}/{dato("E")},1)&" %  ("&FIXED({dato("H")},0)&" de "&'
               f'FIXED({dato("E")},0)&" m³)","sin volumen proyectado"),"")'),
    ('Extra (proforma)', f'=IFERROR(FIXED({dato("J")},0)&" m³","")'),
    ('Dato de la planilla', f'=IFERROR(IF({dato("B")}="","sin datos",{fecha_txt(dato("B"))}),"")'),
    ('Acceso / Living', f'=IFERROR({dato("L")}&" / "&{dato("M")},"")'),
    ('Carta Gantt', f'=IFERROR(IF({dato("Q")}="","sin programa",{fecha_txt(dato("P"))}&" al "&{fecha_txt(dato("Q"))}),"")'),
    ('Notas 📌', f'=IFERROR({dato("S")}&IF({dato("S")}>0," (ver Ficha sitio)",""),"")'),
]
anc = (ULT - M1 + 1) // 3
for k, (et, f) in enumerate(campos_sel):
    r = rs + 1 + k // 3
    c1 = M1 + (k % 3) * anc
    pan.row_dimensions[r].height = 18
    unir(pan, r, c1, r, c1 + 22, et, fuente(9, True, SUAVE), FONDO, al='left')
    unir(pan, r, c1 + 23, r, c1 + anc - 1, f, fuente(10), FONDO, al='left')
pan.row_dimensions[rs + 3].height = 8

# gráfico de camiones por día / semana
rg = rs + 4
unir(pan, rg, M1, rg, ULT, '="🚚 m³ a botadero por "&IF(Vista="Semana","semana (últimas 14)","día (últimos 14)")',
     fuente(13, True), al='left')
graf = BarChart()
graf.type = 'col'
graf.style = 10
graf.title = None
graf.legend = None
graf.y_axis.title = 'm³'
graf.y_axis.majorGridlines = None
graf.x_axis.delete = False
graf.y_axis.delete = False
graf.add_data(Reference(lis, min_col=7, min_row=1, max_row=15), titles_from_data=True)
graf.set_categories(Reference(lis, min_col=6, min_row=2, max_row=15))
graf.series[0].graphicalProperties.solidFill = VERDE
graf.height, graf.width = 7, 31
pan.add_chart(graf, f'{L(M1)}{rg + 1}')
pan.freeze_panes = None
pan.print_area = f'A1:{L(ULT + 1)}{rg + 16}'
pan.page_setup.orientation = 'landscape'
pan.page_setup.paperSize = pan.PAPERSIZE_A3
pan.page_setup.fitToWidth = 1
pan.page_setup.fitToHeight = 1
pan.sheet_properties.pageSetUpPr.fitToPage = True
pan.print_options.horizontalCentered = True
pan.page_margins.left = pan.page_margins.right = 0.3
pan.page_margins.top = pan.page_margins.bottom = 0.4

# ---------------------------------------------------------------- Ficha sitio

titulo_hoja(fic, 'Ficha de sitio', 'Elija el sitio en la celda amarilla (o haga clic en el mapa del Panel).')
fic.column_dimensions['A'].width = 2
fic.column_dimensions['B'].width = 26
fic.column_dimensions['C'].width = 22
fic.column_dimensions['D'].width = 3
fic.column_dimensions['E'].width = 18
fic.column_dimensions['F'].width = 12
fic.column_dimensions['G'].width = 20
fic.column_dimensions['H'].width = 70
fic['B3'] = 'Sitio'
fic['B3'].font = fuente(12, True)
fic['C3'] = 30
fic['C3'].font = fuente(16, True)
fic['C3'].fill = relleno('FFF7D6')
fic['C3'].border = caja
fic['C3'].alignment = Alignment(horizontal='center')
dv = DataValidation(type='list', formula1='ListaSitios', allow_blank=False)
fic.add_data_validation(dv)
dv.add('C3')
fs = f'MATCH($C$3,Sitios!$A$4:$A$53,0)'
filas_ficha = [
    ('Datos al', f'=FechaPanel', 'dd-mm-yyyy'),
    ('Movimiento', '=INDEX(Sitios!$K$4:$K$53,{})', None),
    ('Avance', '=INDEX(Sitios!$I$4:$I$53,{})', '0.0%'),
    ('Proyectado (esponjado) m³', '=INDEX(Sitios!$E$4:$E$53,{})', '#,##0'),
    ('   Escarpe m³', '=INDEX(Sitios!$C$4:$C$53,{})', '#,##0'),
    ('   Corte geométrico m³', '=INDEX(Sitios!$D$4:$D$53,{})', '#,##0'),
    ('Retirado según planilla m³', '=INDEX(Sitios!$F$4:$F$53,{})', '#,##0'),
    ('Camiones posteriores m³', '=INDEX(Sitios!$G$4:$G$53,{})', '#,##0'),
    ('Retirado total m³', '=INDEX(Sitios!$H$4:$H$53,{})', '#,##0'),
    ('Extra (proforma) m³', '=INDEX(Sitios!$J$4:$J$53,{})', '#,##0'),
    ('Fecha del dato de planilla', '=INDEX(Sitios!$B$4:$B$53,{})', 'dd-mm-yyyy'),
    ('Terraza de acceso', '=INDEX(Sitios!$L$4:$L$53,{})', None),
    ('Terraza living', '=INDEX(Sitios!$M$4:$M$53,{})', None),
    ('Entregado (acceso y living)', '=INDEX(Sitios!$N$4:$N$53,{})', None),
    ('Fecha de entrega', '=INDEX(Sitios!$O$4:$O$53,{})', 'dd-mm-yyyy'),
    ('Inicio carta Gantt', '=INDEX(Sitios!$P$4:$P$53,{})', 'dd-mm-yyyy'),
    ('Término carta Gantt', '=INDEX(Sitios!$Q$4:$Q$53,{})', 'dd-mm-yyyy'),
    ('Cumplimiento', '=INDEX(Sitios!$R$4:$R$53,{})', None),
]
for i, (et, f, fmt) in enumerate(filas_ficha, 5):
    fic.cell(i, 2, et).font = fuente(10, True, SUAVE)
    c = fic.cell(i, 3, f'=IFERROR({f[1:].format(fs)},"")' if '{}' in f else f)
    c.font = fuente(11, i in (6, 7, 22))
    c.alignment = Alignment(horizontal='left')
    c.border = Border(bottom=delgado)
    if fmt:
        c.number_format = fmt
for k, (txt, bg) in enumerate([('Completo', VERDE), ('En intervención', AMARILLO), ('Atrasado', ROJO),
                               ('Entregado', VERDE)]):
    fic.conditional_formatting.add('C6:C22', FormulaRule(formula=[f'LEFT(C6,{len(txt)})="{txt}"'], fill=relleno(bg)))
fic['E3'] = 'Notas 📌 (más recientes primero)'
fic['E3'].font = fuente(12, True)
celda_btn = fic['E4']
celda_btn.value = '📌 Agregar nota'
celda_btn.fill = relleno('B07A1F')
celda_btn.alignment = Alignment(horizontal='center')
celda_btn.hyperlink = Hyperlink(ref='E4', location="'Ficha sitio'!E4", tooltip='Agregar nota')
fic['E4'].font = fuente(10, True, 'FFFFFF')
nombre(wb, 'BtnNotaFicha', "'Ficha sitio'!$E$4")
fic['G4'] = '◀ Volver al Panel'
fic['G4'].fill = relleno('2F5D4A')
fic['G4'].alignment = Alignment(horizontal='center')
fic['G4'].hyperlink = Hyperlink(ref='G4', location="'Panel'!A1", tooltip='Volver al Panel')
fic['G4'].font = fuente(10, True, 'FFFFFF')
for j, t in zip('EFGH', ['Fecha y hora', '', 'Responsable', 'Nota']):
    fic[f'{j}6'] = t
    fic[f'{j}6'].font = fuente(10, True, 'FFFFFF')
    fic[f'{j}6'].fill = relleno('2F5D4A')
fic.merge_cells('E6:F6')
for k in range(1, 16):
    r = k + 6
    fila_nota = f'_xlfn.AGGREGATE(14,6,ROW({NT["sitio"]})/({NT["sitio"]}=$C$3),{k})'
    fic.merge_cells(f'E{r}:F{r}')
    fic[f'E{r}'] = f'=IFERROR(INDEX(Notas!$A:$A,{fila_nota}),"")'
    fic[f'E{r}'].number_format = 'dd-mm-yyyy hh:mm'
    fic[f'G{r}'] = f'=IFERROR(INDEX(Notas!$C:$C,{fila_nota}),"")'
    fic[f'H{r}'] = f'=IFERROR(INDEX(Notas!$D:$D,{fila_nota}),"")'
    fic[f'H{r}'].alignment = Alignment(wrap_text=True, vertical='top')
    for j in 'EGH':
        fic[f'{j}{r}'].border = Border(bottom=delgado)

# ---------------------------------------------------------------- Programa (carta Gantt dibujada)

titulo_hoja(pro, 'Programa — carta Gantt por sitio', '')
pro['A2'] = (f'="Barra = semanas del programa de cada sitio · verde = entregado · rojo = atrasado · azul = pendiente '
             f'· columna roja = semana del "&{fecha_txt("FechaPanel")}')
pro['A2'].font = fuente(10, color=SUAVE, cursiva=True)
SEMANAS = 30
for j, (t, a) in enumerate([('Sitio', 7), ('Inicio', 11), ('Término', 11), ('Entregado', 10), ('Cumplimiento', 19)],
                           1):
    c = pro.cell(4, j, t)
    c.font = fuente(10, True, 'FFFFFF')
    c.fill = relleno('2F5D4A')
    c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    pro.column_dimensions[L(j)].width = a
pro.row_dimensions[4].height = 34
for k in range(SEMANAS):
    c = pro.cell(4, 6 + k, f'=MIN({GT["ini"]})-WEEKDAY(MIN({GT["ini"]}),2)+1+7*{k}')
    c.number_format = 'dd-mm'
    c.font = fuente(8, True, 'FFFFFF')
    c.fill = relleno('2F5D4A')
    c.alignment = Alignment(text_rotation=90, horizontal='center')
    pro.column_dimensions[L(6 + k)].width = 3.2
for i, s in enumerate(TERRENOS[:48], 5):
    fr = FILA_SITIO[s]
    for j, col in enumerate(['A', 'P', 'Q', 'N', 'R'], 1):
        c = pro.cell(i, j, f'=Sitios!{col}{fr}')
        c.alignment = Alignment(horizontal='center')
        c.font = fuente(9, j == 1)
        c.border = Border(bottom=Side(style='hair', color=BORDE))
    pro.cell(i, 2).number_format = pro.cell(i, 3).number_format = 'dd-mm-yyyy'
    for k in range(SEMANAS):
        pro.cell(i, 6 + k).border = Border(bottom=Side(style='hair', color=BORDE), left=Side(style='hair', color=BORDE))
ultg = 4 + 48
area = f'F5:{L(5 + SEMANAS)}{ultg}'
barra = 'AND($B5<>"",F$4<=$C5,F$4+6>=$B5)'
for cond, color in ((f'AND({barra},$D5="Sí")', VERDE), (f'AND({barra},$E5="Atrasado")', ROJO), (barra, '7DA7E0'),
                    ('AND(F$4<=FechaPanel,FechaPanel<F$4+7)', 'F6D5D5')):
    pro.conditional_formatting.add(area, FormulaRule(formula=[cond], fill=relleno(color), stopIfTrue=True))
for txt, bg in (('Atrasado', ROJO), ('Entregado', VERDE)):
    pro.conditional_formatting.add(f'E5:E{ultg}', FormulaRule(formula=[f'LEFT(E5,{len(txt)})="{txt}"'],
                                                             fill=relleno(bg), font=Font(color='FFFFFF', bold=True)))
pro.freeze_panes = 'F5'

# ---------------------------------------------------------------- Ayuda

ayu.column_dimensions['A'].width = 2
ayu.column_dimensions['B'].width = 120
textos = [
    ('Cómo usar este archivo', 'titulo'),
    ('Panel (primera hoja): elija el día en la celda amarilla "Ver al día" (o use ◀ Anterior / Hoy / Siguiente ▶) y '
     'la vista Día o Semana. Todo se recalcula solo: indicadores, mapas, ficha y gráfico.', ''),
    ('Los datos se escriben en las hojas amarillas. No hay que tocar las hojas Panel, Ficha sitio, Programa ni Sitios '
     '(son de cálculo).', ''),
    ('Hojas de datos', 'sub'),
    ('• Movimiento: la planilla "Resumen x Terraza" (una fila por sitio y fecha). Botón "📥 Planilla de movimiento" '
     'del Panel: elige el archivo Excel de la planilla, pregunta la fecha y copia las filas (si ya había datos de esa '
     'fecha los reemplaza). Para cada sitio se usa el dato más reciente hasta el día del Panel, así que no se suma con '
     'lo anterior. Filas sin presupuesto (esponjado 0) o "EXC ADICIONAL" = extra (proforma, no entra al avance).', ''),
    ('• Camiones: tickets de la máquina. Botón "📥 Tickets de camiones (CSV)": elige el CSV (TICKET;FECHA;HORA;'
     'PATENTE;VOLUMEN_M3;SECTOR;TIPO;ESTADO) y agrega solo los tickets nuevos. Solo cuentan para un sitio los '
     'sectores que son un número de sitio (1 a 48); los demás (pasajes, calle, P3, R…) quedan como generales. Los m³ '
     'de camiones de un sitio se suman a su avance solo si son posteriores a la fecha de su planilla.', ''),
    ('• Entregas: estado de cada terraza (Pendiente / En proceso / Entregada) y fecha de entrega. Un sitio está '
     'entregado cuando su acceso y su living están entregados (el fondo de patio no cuenta).', ''),
    ('• Gantt: inicio y término del programa de cada sitio. Si el término ya pasó y el sitio no está entregado, '
     'aparece como atrasado (rojo / ⚠).', ''),
    ('• Notas: bitácora por sitio (fecha y hora, responsable, nota). Botón "📌 Agregar nota".', ''),
    ('Reglas', 'sub'),
    ('• Avance de movimiento de tierra = m³ retirados / m³ proyectados (esponjados). No depende de la carta Gantt.', ''),
    ('• Mapa de intervención: verde = 100 % del volumen proyectado (desde 99 %, por redondeo de la planilla); '
     'amarillo = con intervención; gris = sin intervención; ⚠ = movimiento extra.', ''),
    ('• Mapa de entregas: ✅ entregada; rojo / ⚠ = debería estar entregada según la carta Gantt; amarillo = en proceso '
     'de entrega; gris = pendiente; muy claro = fondo de patio (no se considera).', ''),
    ('Macros', 'sub'),
    ('Los botones, el clic en los mapas y las importaciones usan macros. Al abrir, presione "Habilitar contenido" '
     '(Windows) o "Habilitar macros" (Mac). Si Windows dice que las macros están bloqueadas porque el archivo viene de '
     'internet: cierre Excel, clic derecho sobre el archivo → Propiedades → marque "Desbloquear" → Aceptar.', ''),
    ('Sin macros todo lo demás funciona igual: cambie el día escribiendo en la celda amarilla, y pegue los datos '
     'directamente en las hojas amarillas.', ''),
    ('Límites', 'sub'),
    (f'Las hojas de datos están preparadas para {MAX_MOV:,} filas de movimiento, {MAX_CAM:,} tickets (el botón de '
     f'importación extiende las fórmulas si se necesitan más), {MAX_ENT} terrazas, {MAX_GANTT} filas de Gantt y '
     f'{MAX_NOTAS:,} notas. Requiere Excel 2010 o posterior (Windows o Mac).'.replace(',', '.'), ''),
]
for i, (t, tipo) in enumerate(textos, 2):
    c = ayu.cell(i, 2, t)
    c.font = fuente(16, True) if tipo == 'titulo' else fuente(12, True, '2F5D4A') if tipo == 'sub' else fuente(11)
    c.alignment = Alignment(wrap_text=True, vertical='top')
    if not tipo:
        ayu.row_dimensions[i].height = 15 * max(1, len(t) // 115 + 1)

# impresión: horizontal, ajustada al ancho de la página
for ws in (fic, pro, sit):
    ws.page_setup.orientation = 'landscape'
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_margins.left = ws.page_margins.right = 0.3
fic.print_area = 'A1:H22'
pro.print_area = f'A1:{L(5 + SEMANAS)}{ultg}'
sit.print_area = f'A1:S{r_tot}'

# ---------------------------------------------------------------- guardar con macros

wb.active = 0
SALIDA.parent.mkdir(parents=True, exist_ok=True)
tmp = SALIDA.with_suffix('.tmp.xlsx')
wb.save(tmp)
vba = Path(__file__).parent / 'vba'
modulos = [('ThisWorkbook', 'libro', '')]
for _, codigo in orden:
    archivo = vba / f'{codigo}.cls'
    modulos.append((codigo, 'hoja', archivo.read_text(encoding='utf-8') if archivo.exists() else ''))
modulos.append(('Botones', 'modulo', (vba / 'Botones.bas').read_text(encoding='utf-8')))
xlsm.empaquetar(tmp, SALIDA, vba_proyecto.proyecto(modulos))
tmp.unlink()
print(SALIDA)
