"""Genera el archivo Excel con macros (.xlsm) de seguimiento de movimiento de tierra y entregas.

    python scripts/excel/construir.py [salida.xlsm]

Los datos van en tablas de Excel (crecen solas); el Panel tiene indicadores, dos mapas dibujados como figuras
(sitios y terrazas del plano), gráficos y referencias a las tablas dinámicas. Todo se calcula con fórmulas; las
macros recolorean los mapas, responden al clic en un sitio, importan tickets, la planilla de obra y planos DXF.
"""
import csv
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from openpyxl import Workbook
from openpyxl.chart import BarChart, DoughnutChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.chart.series import DataPoint
from openpyxl.formatting.rule import DataBarRule, FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter as L
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.hyperlink import Hyperlink
from openpyxl.worksheet.table import Table, TableFormula, TableStyleInfo

sys.path.insert(0, str(Path(__file__).parent))
import dibujo  # noqa: E402
import tablas_dinamicas as TD  # noqa: E402
import vba_proyecto  # noqa: E402
import xlsm  # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]
SALIDA = Path(sys.argv[1]) if len(sys.argv) > 1 else RAIZ / 'data' / 'excel' / 'Seguimiento_Loma_La_Cruz.xlsm'
GEO = json.loads((RAIZ / 'data' / 'geometria.json').read_text())
HOY = (datetime.utcnow() - timedelta(hours=3)).date()     # Chile

VERDE, AMARILLO, GRIS, CLARO, ROJO = '2F9E6B', 'FBE08C', 'CFD6D1', 'F1F3F0', 'E06666'
TINTA, SUAVE, FONDO, BORDE, OSCURO, AZUL, OCRE = '1D2320', '5F6B64', 'F4F6F3', 'D9DED9', '2F5D4A', '3B7DD8', 'B07A1F'

delgado = Side(style='thin', color=BORDE)
caja = Border(left=delgado, right=delgado, top=delgado, bottom=delgado)


def relleno(c):
    return PatternFill('solid', start_color=c, end_color=c)


def fuente(tam=10, negrita=False, color=TINTA, cursiva=False):
    return Font(name='Calibri', size=tam, bold=negrita, color=color, italic=cursiva)


def fecha_txt(ref):
    """dd-mm-aaaa sin TEXT() (sus códigos de formato dependen del idioma de Excel)."""
    return f'RIGHT("0"&DAY({ref}),2)&"-"&RIGHT("0"&MONTH({ref}),2)&"-"&YEAR({ref})'


def fecha_corta(ref):
    return f'RIGHT("0"&DAY({ref}),2)&"-"&RIGHT("0"&MONTH({ref}),2)'


def leer_csv(p):
    with open(p, encoding='utf-8-sig') as f:
        return list(csv.DictReader(f, delimiter=';'))


def a_fecha(s):
    s = (s or '').strip()
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


def ancho_px(w):
    return int(((256 * w + int(128 / 7)) / 256) * 7)


def titulo_hoja(ws, texto, sub=''):
    ws['A1'] = texto
    ws['A1'].font = fuente(15, True)
    if sub:
        ws['A2'] = sub
        ws['A2'].font = fuente(10, color=SUAVE, cursiva=True)


# ---------------------------------------------------------------- datos (lo más reciente)

TERRENOS = [sitio_de(t['codigo']) for t in GEO['terrenos']]
TERRENOS = sorted(t for t in TERRENOS if isinstance(t, int)) + [t for t in TERRENOS if not isinstance(t, int)]
FILA_SITIO = {s: i + 4 for i, s in enumerate(TERRENOS)}
TERRAZA = {'acceso': 'Acceso', 'living': 'Living', 'fondo_patio': 'Fondo de patio', 'unica': 'Única'}
CLAVE_FIG = {'acceso': 'acceso', 'living': 'living', 'fondo_patio': 'fondo', 'unica': 'unica'}

# planilla "Resumen x Terraza" al 30/10/2026: sitio, escarpe, corte geométrico, esc + corte c/esp, a botadero
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
MOV = [[FECHA_MOV, s, e, c, p, b, None, None, 'Presupuestado' if p > 0 else 'Extra'] for s, e, c, p, b in MOV_30_10]

CAM = []
for t in leer_csv(RAIZ / 'data' / 'carga_2026-10-19' / '2_tickets_19-10.csv'):
    sector = (t['SECTOR'] or '').strip()
    CAM.append([t['TICKET'], a_fecha(t['FECHA']), t['HORA'], t['PATENTE'], float(t['VOLUMEN_M3'].replace(',', '.')),
                int(sector) if sector.isdigit() and 1 <= int(sector) <= 48 else None, sector, t['TIPO'] or None,
                t['ESTADO'] or 'VALIDO', t.get('EMPRESA') or None])
for r in CAM:   # columnas calculadas: Semana, Viaje, Camión día, Camión semana
    sem = r[1] - timedelta(days=r[1].weekday())
    r += [sem, -1 if r[8] == 'ANULACION' else 1,
          1 / sum(1 for x in CAM if x[3] == r[3] and x[1] == r[1]),
          1 / sum(1 for x in CAM if x[3] == r[3] and x[1] - timedelta(days=x[1].weekday()) == sem)]

ENTREGADAS = {(int(r['sitio']), r['zona']) for r in leer_csv(RAIZ / 'data' / 'carga_2026-10-19' /
                                                              '3_terrazas_entregadas.csv') if r['estado'] == 'entregado'}
ZONAS = [(sitio_de(z['terreno']), z['zona'], z) for z in GEO['zonas']]
ORDEN_T = ['acceso', 'living', 'fondo_patio', 'unica']
ENT = []
for s, z, _ in sorted(ZONAS, key=lambda x: (TERRENOS.index(x[0]), ORDEN_T.index(x[1]))):
    est = 'Entregada' if (s, z) in ENTREGADAS else 'Pendiente'
    ENT.append([s, TERRAZA[z], est, None, None, est, f'{s}|{TERRAZA[z]}'])

GAN = [[int(g['sitio']), a_fecha(g['inicio']), a_fecha(g['termino']), g['tarea']]
       for g in sorted(leer_csv(RAIZ / 'data' / 'carga_inicial' / '5_programa_gantt.csv'), key=lambda g: int(g['sitio']))]

# ---------------------------------------------------------------- libro

wb = Workbook()
wb.code_name = 'ThisWorkbook'
orden = [('Panel', 'Panel'), ('Tablas dinámicas', 'TablasDin'), ('Ficha sitio', 'Ficha'), ('Programa', 'Programa'),
         ('Sitios', 'Sitios'), ('Movimiento', 'Movimiento'), ('Camiones', 'Camiones'), ('Entregas', 'Entregas'),
         ('Gantt', 'Gantt'), ('Notas', 'Notas'), ('Geometría', 'Geometria'), ('Ayuda', 'Ayuda'), ('Listas', 'Listas')]
H = {}
for i, (titulo, codigo_hoja) in enumerate(orden):
    ws = wb.active if i == 0 else wb.create_sheet()
    ws.title = titulo
    ws.sheet_properties.codeName = codigo_hoja
    H[codigo_hoja] = ws
pan, tdn, fic, pro, sit, mov, cam, ent, gan, notas, geo, ayu, lis = (H[c] for _, c in orden)
lis.sheet_state = 'hidden'
for ws in H.values():
    ws.sheet_view.showGridLines = False
pan.sheet_properties.tabColor = VERDE
tdn.sheet_properties.tabColor = AZUL
for ws in (mov, cam, ent, gan, notas):
    ws.sheet_properties.tabColor = AMARILLO


def tabla(ws, nombre_t, cab, filas, anchos, calc=None, formatos=None, sub='', fila0=3):
    """Tabla de Excel con columnas calculadas (calc: {columna: fórmula con [#This Row]})."""
    calc, formatos = calc or {}, formatos or {}
    for j, (t, a) in enumerate(zip(cab, anchos), 1):
        c = ws.cell(fila0, j, t)
        c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        ws.column_dimensions[L(j)].width = a
    ws.row_dimensions[fila0].height = 32
    filas = filas or [[None] * len(cab)]
    for i, fila in enumerate(filas, fila0 + 1):
        for j, t in enumerate(cab, 1):
            v = f'={calc[t]}' if t in calc else fila[j - 1] if j - 1 < len(fila) else None
            c = ws.cell(i, j, v)
            if t in formatos:
                c.number_format = formatos[t]
    t = Table(displayName=nombre_t, ref=f'A{fila0}:{L(len(cab))}{fila0 + len(filas)}')
    t.tableStyleInfo = TableStyleInfo(name='TableStyleMedium7', showRowStripes=True)
    t._initialise_columns()
    for col in t.tableColumns:
        if col.name in calc:
            col.calculatedColumnFormula = TableFormula(attr_text=calc[col.name])
    ws.add_table(t)
    ws.freeze_panes = ws.cell(fila0 + 1, 1)
    if sub:
        ws['A2'] = sub
        ws['A2'].font = fuente(10, color=SUAVE, cursiva=True)
    return t


def esta(tbl, col):
    return f'{tbl}[[#This Row],[{col}]]'


# ---------------------------------------------------------------- hojas de datos (tablas de Excel)

titulo_hoja(mov, 'Movimiento de tierra por sitio (planilla "Resumen x Terraza")')
CAB_MOV = ['Fecha', 'Sitio', 'Escarpe m³', 'Corte geométrico m³', 'Proyectado m³', 'A botadero m³', 'Extra m³',
           'Observación', 'Tipo']
tabla(mov, 'tblMovimiento', CAB_MOV, MOV, [12, 8, 12, 15, 14, 14, 11, 34, 15],
      calc={'Tipo': f'IF({esta("tblMovimiento", "Proyectado m³")}>0,"Presupuestado","Extra")'},
      formatos={'Fecha': 'dd-mm-yyyy', **{k: '#,##0' for k in CAB_MOV[2:7]}},
      sub='Una fila por sitio y fecha (Proyectado = "Esc + corte c/esp"; Retirado = "a botadero"). Filas sin '
          'presupuesto (Proyectado 0) = extra. Para cada sitio se usa la fecha más reciente hasta el día del Panel, '
          'así que una planilla nueva reemplaza a la anterior. Botón "📥 Planilla movimiento" del Panel.')

titulo_hoja(cam, 'Tickets de camiones')
CAB_CAM = ['Ticket', 'Fecha', 'Hora', 'Patente', 'm³', 'Sitio', 'Sector original', 'Tipo', 'Estado', 'Empresa',
           'Semana', 'Viaje', 'Camión día', 'Camión semana']
tabla(cam, 'tblCamiones', CAB_CAM, CAM, [13, 12, 8, 10, 8, 7, 12, 8, 11, 13, 12, 7, 10, 11],
      calc={'Semana': f'{esta("tblCamiones", "Fecha")}-WEEKDAY({esta("tblCamiones", "Fecha")},2)+1',
            'Viaje': f'IF({esta("tblCamiones", "Estado")}="ANULACION",-1,1)',
            'Camión día': f'1/COUNTIFS(tblCamiones[Patente],{esta("tblCamiones", "Patente")},tblCamiones[Fecha],'
                          f'{esta("tblCamiones", "Fecha")})',
            'Camión semana': f'1/COUNTIFS(tblCamiones[Patente],{esta("tblCamiones", "Patente")},tblCamiones[Semana],'
                             f'{esta("tblCamiones", "Semana")})'},
      formatos={'Fecha': 'dd-mm-yyyy', 'Semana': 'dd-mm-yyyy', 'm³': '#,##0.0', 'Camión día': '0.00',
                'Camión semana': '0.00', 'Ticket': '@', 'Hora': '@', 'Sector original': '@'},
      sub='Botón "📥 Tickets (CSV)" del Panel, o pegue debajo de la última fila (la tabla crece sola). Sitio vacío = '
          'general (pasajes, calle). Las 4 últimas columnas son automáticas.')
dv = DataValidation(type='list', formula1='"VALIDO,ANULACION"', allow_blank=True)
cam.add_data_validation(dv)
dv.add('I4:I3000')

titulo_hoja(ent, 'Entregas de terrazas')
CAB_ENT = ['Sitio', 'Terraza', 'Estado', 'Fecha entrega', 'Observación', 'Estado al día', 'Clave']
tabla(ent, 'tblEntregas', CAB_ENT, ENT, [8, 15, 13, 13, 36, 14, 12],
      calc={'Estado al día': f'IF(AND({esta("tblEntregas", "Estado")}="Entregada",{esta("tblEntregas", "Fecha entrega")}'
                             f'<>"",{esta("tblEntregas", "Fecha entrega")}>FechaPanel),"En proceso",'
                             f'{esta("tblEntregas", "Estado")})',
            'Clave': f'{esta("tblEntregas", "Sitio")}&"|"&{esta("tblEntregas", "Terraza")}'},
      formatos={'Fecha entrega': 'dd-mm-yyyy'},
      sub='Cambie el estado con la lista y anote la fecha. Un sitio está entregado cuando su acceso y su living '
          'están entregados (el fondo de patio no cuenta).')
for rng, lista in (('C4:C400', '"Pendiente,En proceso,Entregada"'), ('B4:B400', '"Acceso,Living,Fondo de patio,Única"')):
    dv = DataValidation(type='list', formula1=lista, allow_blank=True)
    ent.add_data_validation(dv)
    dv.add(rng)

titulo_hoja(gan, 'Carta Gantt (programa)')
tabla(gan, 'tblGantt', ['Sitio', 'Inicio', 'Término', 'Tarea'], GAN, [8, 12, 12, 70],
      formatos={'Inicio': 'dd-mm-yyyy', 'Término': 'dd-mm-yyyy'},
      sub='Inicio y término del programa de cada sitio. El término es la fecha en que acceso y living deberían '
          'estar entregados.')

titulo_hoja(notas, 'Notas por sitio 📌')
tabla(notas, 'tblNotas', ['Fecha y hora', 'Sitio', 'Responsable', 'Nota'], [], [17, 8, 20, 90],
      formatos={'Fecha y hora': 'dd-mm-yyyy hh:mm'},
      sub='Bitácora: cada actualización es una fila nueva (botón "📌 Nota" o escribiendo debajo).')

# ---------------------------------------------------------------- Listas (oculta)

for i, (n, f) in enumerate([
        ('PerIni', '=IF(Vista="Semana",FechaPanel-WEEKDAY(FechaPanel,2)+1,FechaPanel)'),
        ('PerFin', '=IF(Vista="Semana",B2+6,FechaPanel)'),
        ('PrevIni', '=B2-IF(Vista="Semana",7,1)'),
        ('PrevFin', '=B3-IF(Vista="Semana",7,1)'),
        ('PerTxt', f'=IF(Vista="Semana","semana del "&{fecha_corta("B2")}&" al "&{fecha_txt("B3")},'
                   f'"día "&{fecha_txt("B2")})'),
        ('PrevTxt', '=IF(Vista="Semana","semana anterior","día anterior")')], 2):
    lis.cell(i, 1, n)
    lis.cell(i, 2, f).number_format = 'dd-mm-yyyy'
    nombre(wb, n, f'Listas!$B${i}')
lis['D1'], lis['E1'], lis['F1'], lis['G1'] = 'Desde', 'Hasta', 'Período', 'm³ a botadero'
for k in range(14):
    r = k + 2
    lis.cell(r, 4, f'=PerIni-IF(Vista="Semana",7,1)*{13 - k}').number_format = 'dd-mm-yyyy'
    lis.cell(r, 5, f'=D{r}+IF(Vista="Semana",6,0)').number_format = 'dd-mm-yyyy'
    lis.cell(r, 6, f'={fecha_corta(f"D{r}")}')
    lis.cell(r, 7, f'=SUMIFS(tblCamiones[m³],tblCamiones[Fecha],">="&D{r},tblCamiones[Fecha],"<="&E{r})')
lis['J1'] = 'Sitios'
for i, s in enumerate(TERRENOS, 2):
    lis.cell(i, 10, s)
nombre(wb, 'ListaSitios', f'Listas!$J$2:$J${len(TERRENOS) + 1}')
lis['L1'], lis['M1'] = 'Estado de los sitios', 'Sitios'
for i, (et, f) in enumerate([('Completo', '=COUNTIF(Sitios!$K$4:$K$51,"Completo")'),
                             ('Con intervención', '=COUNTIF(Sitios!$K$4:$K$51,"En intervención")'),
                             ('Sin intervención', '=COUNTIF(Sitios!$K$4:$K$51,"Sin intervenir")')], 2):
    lis.cell(i, 12, et)
    lis.cell(i, 13, f)
lis['O1'], lis['P1'] = 'Cumplimiento carta Gantt', 'Sitios'
for i, (et, f) in enumerate([('Entregado', '=COUNTIF(Sitios!$R$4:$R$51,"Entregado*")'),
                             ('Atrasado', '=COUNTIF(Sitios!$R$4:$R$51,"Atrasado")'),
                             ('Pendiente', '=COUNTIF(Sitios!$R$4:$R$51,"Pendiente")'),
                             ('Sin programa', '=COUNTIF(Sitios!$R$4:$R$51,"Sin programa")')], 2):
    lis.cell(i, 15, et)
    lis.cell(i, 16, f)

# ---------------------------------------------------------------- Sitios (cálculo y detalle)

titulo_hoja(sit, 'Detalle por sitio')
sit['A2'] = (f'="Al "&{fecha_txt("FechaPanel")}&" · avance = m³ retirados / m³ proyectados (esponjados). '
             f'El extra (proforma) no entra al avance."')
sit['A2'].font = fuente(10, color=SUAVE, cursiva=True)
COLS_SIT = ['Sitio', 'Fecha del dato', 'Escarpe m³', 'Corte geom. m³', 'Proyectado m³', 'Retirado planilla m³',
            'Camiones posteriores m³', 'Retirado total m³', 'Avance', 'Extra m³ (proforma)', 'Movimiento', 'Acceso',
            'Living', 'Entregado', 'Fecha entrega', 'Inicio Gantt', 'Término Gantt', 'Cumplimiento carta Gantt',
            'Notas', 'cód.', 'debe', 'etiq. interv.', 'etiq. entregas']
for j, (t, a) in enumerate(zip(COLS_SIT, [7, 11, 10, 11, 12, 12, 12, 12, 16, 12, 15, 11, 11, 10, 11, 11, 11, 21, 7,
                                          5, 5, 9, 9]), 1):
    c = sit.cell(3, j, t)
    c.font = fuente(10, True, 'FFFFFF' if j < 20 else SUAVE)
    c.fill = relleno(OSCURO if j < 20 else 'E9ECE9')
    c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    sit.column_dimensions[L(j)].width = a
sit.row_dimensions[3].height = 32
sit.freeze_panes = 'B4'
MV = 'tblMovimiento'
for s in TERRENOS:
    r = FILA_SITIO[s]
    ta, tl = ('"|Única"', '"|Única"') if not isinstance(s, int) else ('"|Acceso"', '"|Living"')
    f = {
        1: s,
        2: f'=IFERROR(_xlfn.AGGREGATE(14,6,{MV}[Fecha]/({MV}[Sitio]=A{r})/({MV}[Fecha]<=FechaPanel),1),"")',
        3: f'=IF(B{r}="",0,SUMIFS({MV}[Escarpe m³],{MV}[Sitio],A{r},{MV}[Fecha],B{r}))',
        4: f'=IF(B{r}="",0,SUMIFS({MV}[Corte geométrico m³],{MV}[Sitio],A{r},{MV}[Fecha],B{r}))',
        5: f'=IF(B{r}="",0,SUMIFS({MV}[Proyectado m³],{MV}[Sitio],A{r},{MV}[Fecha],B{r}))',
        6: f'=IF(B{r}="",0,SUMIFS({MV}[A botadero m³],{MV}[Sitio],A{r},{MV}[Fecha],B{r},{MV}[Proyectado m³],">0"))',
        7: f'=SUMIFS(tblCamiones[m³],tblCamiones[Sitio],A{r},tblCamiones[Fecha],">"&IF(B{r}="",0,B{r}),'
           f'tblCamiones[Fecha],"<="&FechaPanel)',
        8: f'=F{r}+G{r}',
        9: f'=IF(E{r}>0,H{r}/E{r},"")',
        10: f'=IF(B{r}="",0,SUMIFS({MV}[A botadero m³],{MV}[Sitio],A{r},{MV}[Fecha],B{r})-F{r}'
            f'+SUMIFS({MV}[Extra m³],{MV}[Sitio],A{r},{MV}[Fecha],B{r}))',
        11: f'=IF(AND(E{r}>0,H{r}>=0.99*E{r}),"Completo",IF(H{r}+J{r}>0,"En intervención","Sin intervenir"))',
        12: f'=IFERROR(INDEX(tblEntregas[Estado al día],MATCH(A{r}&{ta},tblEntregas[Clave],0)),"Pendiente")',
        13: f'=IFERROR(INDEX(tblEntregas[Estado al día],MATCH(A{r}&{tl},tblEntregas[Clave],0)),"Pendiente")',
        14: f'=IF(AND(L{r}="Entregada",M{r}="Entregada"),"Sí","No")',
        15: f'=IF(N{r}="Sí",IF(MAX(SUMIFS(tblEntregas[Fecha entrega],tblEntregas[Clave],A{r}&{ta}),'
            f'SUMIFS(tblEntregas[Fecha entrega],tblEntregas[Clave],A{r}&{tl}))=0,"",'
            f'MAX(SUMIFS(tblEntregas[Fecha entrega],tblEntregas[Clave],A{r}&{ta}),'
            f'SUMIFS(tblEntregas[Fecha entrega],tblEntregas[Clave],A{r}&{tl}))),"")',
        16: f'=IFERROR(_xlfn.AGGREGATE(15,6,tblGantt[Inicio]/(tblGantt[Sitio]=A{r}),1),"")',
        17: f'=IFERROR(_xlfn.AGGREGATE(14,6,tblGantt[Término]/(tblGantt[Sitio]=A{r}),1),"")',
        18: f'=IF(Q{r}="","Sin programa",IF(N{r}="Sí",IF(O{r}="","Entregado",IF(O{r}<=Q{r},"Entregado a tiempo",'
            f'"Entregado con atraso")),IF(FechaPanel>Q{r},"Atrasado","Pendiente")))',
        19: f'=COUNTIF(tblNotas[Sitio],A{r})',
        20: f'=IF(K{r}="Completo",1,IF(K{r}="En intervención",2,3))',
        21: f'=IF(AND(Q{r}<>"",N{r}="No"),IF(FechaPanel>Q{r},1,0),0)',
        22: f'=A{r}&IF(J{r}>0," ⚠","")',
        23: f'=A{r}&IF(N{r}="Sí"," ✅",IF(U{r}=1," ⚠",""))',
    }
    for j, v in f.items():
        c = sit.cell(r, j, v)
        c.border = caja
        c.font = fuente(10 if j < 20 else 8, j == 1, TINTA if j < 20 else SUAVE)
        c.alignment = Alignment(horizontal='center')
    for j in (2, 15, 16, 17):
        sit.cell(r, j).number_format = 'dd-mm-yyyy'
    for j in (3, 4, 5, 6, 7, 8, 10):
        sit.cell(r, j).number_format = '#,##0'
    sit.cell(r, 9).number_format = '0.0%'
ULT_S = FILA_SITIO[TERRENOS[-1]]
R_TOT = ULT_S + 2
sit.cell(R_TOT, 1, 'Total sitios').font = fuente(10, True)
for j in (3, 4, 5, 6, 7, 8, 10):
    c = sit.cell(R_TOT, j, f'=SUM({L(j)}4:{L(j)}51)')
    c.number_format, c.font = '#,##0', fuente(10, True)
sit.cell(R_TOT, 9, f'=IF(E{R_TOT}>0,H{R_TOT}/E{R_TOT},"")').number_format = '0.0%'
sit.conditional_formatting.add(f'I4:I{ULT_S}', DataBarRule(start_type='num', start_value=0, end_type='num',
                                                            end_value=1, color=VERDE))
for col, reglas in (('K', [('Completo', VERDE, 'FFFFFF'), ('En intervención', AMARILLO, TINTA)]),
                    ('R', [('Atrasado', ROJO, 'FFFFFF'), ('Entregado', VERDE, 'FFFFFF')]),
                    ('N', [('Sí', VERDE, 'FFFFFF')])):
    for txt, bg, fg in reglas:
        sit.conditional_formatting.add(f'{col}4:{col}{ULT_S}', FormulaRule(
            formula=[f'LEFT({col}4,{len(txt)})="{txt}"'], fill=relleno(bg), font=Font(color=fg, bold=True)))
for col in ('L', 'M'):
    sit.conditional_formatting.add(f'{col}4:{col}{ULT_S}', FormulaRule(formula=[f'{col}4="Entregada"'],
                                                                      fill=relleno('D5EEDF')))
sit.auto_filter.ref = f'A3:S{ULT_S}'
SI = {k: f'Sitios!${c}$4:${c}$51' for k, c in zip('sitio fdato esc corte proy retpl cam ret av extra mov acc liv '
                                                   'entr fent ini fin cumpl notas cod debe'.split(), 'ABCDEFGHIJKLMNOPQRSTU')}

# ---------------------------------------------------------------- Panel

COL_W = [2] + [9.3] * 28
for i, w in enumerate(COL_W, 1):
    pan.column_dimensions[L(i)].width = w
ALTO = {1: 30, 2: 15, 3: 4, 4: 22, 5: 6, 6: 18, 7: 14, 8: 28, 9: 14, 10: 8, 11: 18, 12: 13}
FILA_MAPA0, FILA_MAPA1 = 13, 38                   # filas de los mapas (20 px c/u)
for r in range(FILA_MAPA0, FILA_MAPA1 + 1):
    ALTO[r] = 15
ALTO.update({39: 6, 40: 14, 41: 14, 42: 14, 43: 14, 44: 14, 45: 8, 46: 20})
for r in range(47, 64):
    ALTO[r] = 15
ALTO.update({64: 8, 65: 20, 66: 16})
for r, h in ALTO.items():
    pan.row_dimensions[r].height = h
pan.sheet_view.zoomScale = 85


def unir(r1, c1, r2, c2, valor=None, f=None, fill=None, al='center', borde=None, fmt=None, ws=pan):
    if (r1, c1) != (r2, c2):
        ws.merge_cells(start_row=r1, start_column=c1, end_row=r2, end_column=c2)
    c = ws.cell(r1, c1)
    if valor is not None:
        c.value = valor
    c.font = f or fuente()
    c.alignment = Alignment(horizontal=al, vertical='center', wrap_text=True, indent=1 if al == 'left' else 0)
    for rr in range(r1, r2 + 1):
        for cc in range(c1, c2 + 1):
            if fill:
                ws.cell(rr, cc).fill = relleno(fill)
            if borde:
                ws.cell(rr, cc).border = borde
    if fmt:
        c.number_format = fmt
    return c


def boton(r, c1, c2, texto, nombre_btn, color=OSCURO, destino=None, ws=pan):
    celda = unir(r, c1, r, c2, texto, None, color, ws=ws)
    celda.hyperlink = Hyperlink(ref=celda.coordinate, location=destino or f"'{ws.title}'!{celda.coordinate}",
                                tooltip=texto)
    celda.font = fuente(10, True, 'FFFFFF')   # el vínculo aplica el estilo "Hipervínculo"; se deja como botón
    if nombre_btn:
        nombre(wb, nombre_btn, f"'{ws.title}'!${L(c1)}${r}:${L(c2)}${r}")
    return celda


unir(1, 2, 1, 20, 'Avance movimiento de tierra — Loma La Cruz', fuente(20, True), al='left')
unir(2, 2, 2, 28, f'="48 sitios · Etapas 1 y 2 · datos al "&{fecha_txt("FechaPanel")}&"   ·   los datos se '
                  f'editan en las hojas amarillas; mapas, gráficos y tablas dinámicas se actualizan con ↻"',
     fuente(10, color=SUAVE), al='left')
unir(4, 2, 4, 2, 'Ver al día', fuente(10, True), al='right')
unir(4, 3, 4, 4, '=TODAY()', fuente(12, True), 'FFF7D6', borde=caja, fmt='dd-mm-yyyy')
nombre(wb, 'FechaPanel', 'Panel!$C$4')
dv = DataValidation(type='date', operator='greaterThan', formula1='40000', allow_blank=False,
                    error='Escriba una fecha (dd-mm-aaaa).', errorTitle='Fecha', showErrorMessage=True)
pan.add_data_validation(dv)
dv.add('C4')
boton(4, 5, 5, '◀', 'BtnAnterior')
boton(4, 6, 6, 'Hoy', 'BtnHoy')
boton(4, 7, 7, '▶', 'BtnSiguiente')
unir(4, 8, 4, 8, 'Vista', fuente(10, True), al='right')
unir(4, 9, 4, 9, 'Día', fuente(12, True), 'FFF7D6', borde=caja)
nombre(wb, 'Vista', 'Panel!$I$4')
dv = DataValidation(type='list', formula1='"Día,Semana"', allow_blank=False)
pan.add_data_validation(dv)
dv.add('I4')
boton(4, 10, 11, '↻ Actualizar', 'BtnActualizar', AZUL)
boton(4, 12, 14, '📥 Tickets (CSV)', 'BtnCamiones', OCRE)
boton(4, 15, 17, '📥 Planilla movimiento', 'BtnPlanilla', OCRE)
boton(4, 18, 19, '📌 Nota', 'BtnNota', OCRE)
boton(4, 20, 21, '📐 Plano DXF', 'BtnDXF', '5F6B64')
boton(4, 22, 24, '🔄 Tablas dinámicas', None, AZUL, destino="'Tablas dinámicas'!A1")
boton(4, 25, 26, '❔ Ayuda', None, '5F6B64', destino="'Ayuda'!A1")

# indicadores (6 tarjetas)
unir(6, 2, 6, 28, f'="📊 Indicadores al "&{fecha_txt("FechaPanel")}&"  ·  camiones del "&PerTxt', fuente(13, True),
     al='left')
proy, ret = f'SUM({SI["proy"]})', f'SUM({SI["ret"]})'
deben = f'COUNTIF({SI["debe"]},1)+COUNTIFS({SI["fin"]},"<"&FechaPanel,{SI["entr"]},"Sí")'
cumplen = f'COUNTIFS({SI["fin"]},"<"&FechaPanel,{SI["entr"]},"Sí")'
cam_p = ('ROUND(IF(Vista="Semana",SUMIFS(tblCamiones[Camión semana],tblCamiones[Semana],{i}),'
         'SUMIFS(tblCamiones[Camión día],tblCamiones[Fecha],{i})),0)')


def viajes(i, f):
    return f'SUMIFS(tblCamiones[Viaje],tblCamiones[Fecha],">="&{i},tblCamiones[Fecha],"<="&{f})'


def m3(i, f):
    return f'SUMIFS(tblCamiones[m³],tblCamiones[Fecha],">="&{i},tblCamiones[Fecha],"<="&{f})'


def comparar(a, b):
    return f'IF(({a})-({b})>=0,"+","−")&FIXED(ABS(({a})-({b})),0)'


TARJETAS = [
    ('Avance movimiento de tierra', f'=IF({proy}>0,{ret}/{proy},0)', '0.0%',
     f'=FIXED({ret},0)&" de "&FIXED({proy},0)&" m³"', SUAVE),
    ('Movimiento extra (proforma)', '=SUM(Sitios!$J$4:$J$53)', '#,##0" m³"', '="no entra al avance"', SUAVE),
    ('Sitios con movimiento completo', '=COUNTIF(Sitios!$K$4:$K$51,"Completo")', '0" de 48"',
     '=COUNTIF(Sitios!$K$4:$K$51,"En intervención")&" con intervención"', SUAVE),
    ('Sitios entregados', f'=COUNTIF({SI["entr"]},"Sí")', '0', '="acceso y living entregados"', SUAVE),
    ('Cumplimiento carta Gantt', f'={cumplen}&" de "&({deben})', None,
     f'=IF(({deben})-({cumplen})>0,FIXED(({deben})-({cumplen}),0)&" atrasados","al día")', ROJO),
    ('Camiones · viajes · m³ del período', f'={cam_p.format(i="PerIni")}&" · "&{viajes("PerIni", "PerFin")}&" · "&'
                                          f'FIXED({m3("PerIni", "PerFin")},0)', None,
     f'={comparar(m3("PerIni", "PerFin"), m3("PrevIni", "PrevFin"))}&" m³ vs "&PrevTxt', SUAVE),
]
for k, (et, val, fmt, sub, color_sub) in enumerate(TARJETAS):
    c1, c2 = 2 + k * 4, 28 if k == 5 else 2 + k * 4 + 3
    unir(7, c1, 7, c2, et, fuente(9, True, SUAVE), FONDO, al='left')
    unir(8, c1, 8, c2, val, fuente(18, True), FONDO, al='left', fmt=fmt)
    unir(9, c1, 9, c2, sub, fuente(9, color=color_sub), FONDO, al='left')
    for r in (7, 8, 9):
        pan.cell(r, c1).border = Border(left=Side(style='thick', color='FFFFFF'))

# títulos de los mapas y panel derecho (sitio seleccionado)
unir(11, 2, 11, 8, 'Mapa de intervención', fuente(13, True), al='left')
unir(11, 9, 11, 15, 'Mapa de entregas y cumplimiento', fuente(13, True), al='left')
unir(12, 2, 12, 15, 'Clic en un sitio para ver su detalle →', fuente(9, color=SUAVE, cursiva=True), al='left')
nombre(wb, 'CajaMapa1', f'Panel!$B${FILA_MAPA0}:$H${FILA_MAPA1}')
nombre(wb, 'CajaMapa2', f'Panel!$I${FILA_MAPA0}:$O${FILA_MAPA1}')
SEL = "'Ficha sitio'!$C$3"
fila_sel = f'MATCH({SEL},Sitios!$A$4:$A$53,0)'


def dato(col):
    return f'INDEX(Sitios!${col}$4:${col}$53,{fila_sel})'


unir(11, 17, 11, 28, f'=IFERROR("🔎 Sitio "&{SEL}&" — "&{dato("K")},"🔎 Haga clic en un sitio")', fuente(13, True),
     FONDO, al='left')
campos_sel = [
    ('Avance', f'=IFERROR(IF({dato("E")}>0,FIXED(100*{dato("H")}/{dato("E")},1)&" %","sin volumen proyectado"),"")'),
    ('Retirado / proyectado', f'=IFERROR(FIXED({dato("H")},0)&" de "&FIXED({dato("E")},0)&" m³","")'),
    ('Extra (proforma)', f'=IFERROR(FIXED({dato("J")},0)&" m³","")'),
    ('Dato de la planilla', f'=IFERROR(IF({dato("B")}="","sin datos",{fecha_txt(dato("B"))}),"")'),
    ('Acceso / Living', f'=IFERROR({dato("L")}&" / "&{dato("M")},"")'),
    ('Carta Gantt', f'=IFERROR(IF({dato("Q")}="","sin programa",{fecha_txt(dato("P"))}&" al "&'
                    f'{fecha_txt(dato("Q"))}),"")'),
    ('Cumplimiento', f'=IFERROR({dato("R")},"")'),
    ('Notas 📌', f'=IFERROR({dato("S")}&IF({dato("S")}>0," · última: "&INDEX(tblNotas[Nota],_xlfn.AGGREGATE(14,6,'
                f'(ROW(tblNotas[Sitio])-ROW(tblNotas[#Headers]))/(tblNotas[Sitio]={SEL}),1)),""),"")'),
]
for k, (et, f) in enumerate(campos_sel):
    r = 13 + k
    unir(r, 17, r, 19, et, fuente(9, True, SUAVE), FONDO, al='left')
    unir(r, 20, r, 28, f, fuente(10), FONDO, al='left')
for txt, color in (('Entregado', VERDE), ('Atrasado', ROJO)):
    pan.conditional_formatting.add('T19', FormulaRule(formula=[f'LEFT(T19,{len(txt)})="{txt}"'],
                                                      font=Font(color=color, bold=True)))

# leyendas
LEY1 = [(VERDE, f'="Movimiento completo ("&COUNTIF({SI["mov"]},"Completo")&") — 100 % del volumen proyectado"'),
        (AMARILLO, f'="Con intervención ("&COUNTIF({SI["mov"]},"En intervención")&") — se está trabajando"'),
        (GRIS, f'="Sin intervención ("&COUNTIF({SI["mov"]},"Sin intervenir")&")"'),
        ('FFFFFF', f'="⚠ Movimiento extra ("&COUNTIF({SI["extra"]},">0")&") — volumen adicional (proforma)"')]
LEY2 = [(VERDE, f'="✅ Entregada ("&COUNTIF({SI["entr"]},"Sí")&" sitios) — acceso y living"'),
        (ROJO, f'="⚠ Debería estar entregada ("&COUNTIF({SI["debe"]},1)&") — su fecha Gantt ya pasó"'),
        (AMARILLO, 'En proceso de entrega'), (GRIS, 'Pendiente — aún no le toca'),
        (CLARO, 'Fondo de patio — no se considera')]
for c0, ley in ((2, LEY1), (9, LEY2)):
    for k, (color, texto) in enumerate(ley):
        r = 40 + k
        pan.cell(r, c0).fill = relleno(color)
        pan.cell(r, c0).border = caja
        unir(r, c0 + 1, r, c0 + 6, texto, fuente(9), al='left')

# gráficos
unir(46, 2, 46, 28, '📈 Gráficos', fuente(13, True), al='left')


def cm(px):
    return px / 37.8


g1 = BarChart()
g1.type, g1.style, g1.title, g1.legend = 'col', 10, 'Avance por sitio (m³ retirados / proyectados)', None
g1.y_axis.number_format, g1.y_axis.scaling.max, g1.y_axis.scaling.min = '0%', 1.2, 0
g1.x_axis.delete = g1.y_axis.delete = False
g1.add_data(Reference(sit, min_col=9, min_row=3, max_row=51), titles_from_data=True)
g1.set_categories(Reference(sit, min_col=1, min_row=4, max_row=51))
g1.series[0].graphicalProperties.solidFill = VERDE
g1.gapWidth = 40
g1.width, g1.height = cm(13 * 65 - 10), cm(16 * 20)
pan.add_chart(g1, 'B47')


def dona(titulo, col_cat, col_val, n, colores, ancla, ancho_cols):
    g = DoughnutChart()
    g.title, g.holeSize = titulo, 55
    g.add_data(Reference(lis, min_col=col_val, min_row=1, max_row=1 + n), titles_from_data=True)
    g.set_categories(Reference(lis, min_col=col_cat, min_row=2, max_row=1 + n))
    for i, col in enumerate(colores):
        pt = DataPoint(idx=i)
        pt.graphicalProperties.solidFill = col
        g.series[0].dPt.append(pt)
    g.dataLabels = DataLabelList()
    g.dataLabels.showVal = True
    g.dataLabels.showSerName = g.dataLabels.showCatName = False
    g.dataLabels.showPercent = g.dataLabels.showLegendKey = False
    g.width, g.height = cm(ancho_cols * 65 - 10), cm(16 * 20)
    pan.add_chart(g, ancla)


dona('Estado del movimiento de tierra', 12, 13, 3, [VERDE, AMARILLO, GRIS], 'O47', 6)
dona('Cumplimiento carta Gantt', 15, 16, 4, [VERDE, ROJO, '7DA7E0', GRIS], 'U47', 9)

g4 = BarChart()
g4.type, g4.style, g4.legend = 'col', 10, None
g4.title = 'm³ a botadero por día / semana (camiones)'
g4.x_axis.delete = g4.y_axis.delete = False
g4.add_data(Reference(lis, min_col=7, min_row=1, max_row=15), titles_from_data=True)
g4.set_categories(Reference(lis, min_col=6, min_row=2, max_row=15))
g4.series[0].graphicalProperties.solidFill = AZUL
g4.width, g4.height = cm(12 * 65 - 10), cm(16 * 20 - 10)
pan.add_chart(g4, f'Q{13 + len(campos_sel) + 1}')

# referencias a las tablas dinámicas
unir(65, 2, 65, 28, '🔄 Desde las tablas dinámicas (se actualizan al abrir el archivo y con ↻ Actualizar)',
     fuente(13, True), al='left')
REFS = [
    ('m³ a botadero según tickets (todos)', '=IFERROR(GETPIVOTDATA("Total m³",\'Tablas dinámicas\'!$B$4),0)', '#,##0',
     'Camiones por día', "'Tablas dinámicas'!B4"),
    ('Viajes (válidos − anulados)', '=IFERROR(GETPIVOTDATA("Viajes",\'Tablas dinámicas\'!$B$4),0)', '#,##0',
     'Camiones por día', "'Tablas dinámicas'!B4"),
    ('m³ a botadero en planillas (todas las fechas)',
     '=IFERROR(GETPIVOTDATA("Botadero m³",\'Tablas dinámicas\'!$K$4),0)', '#,##0', 'Planillas por fecha',
     "'Tablas dinámicas'!K4"),
    ('Terrazas entregadas', '=IFERROR(GETPIVOTDATA("Terrazas",\'Tablas dinámicas\'!$Q$4,"Estado","Entregada"),0)', '0',
     'Entregas por terraza', "'Tablas dinámicas'!Q4"),
]
for j, t in zip((2, 9, 12), ('Indicador', 'Valor', 'Tabla dinámica')):
    pan.cell(66, j, t).font = fuente(9, True, SUAVE)
for k, (et, f, fmt, td, destino) in enumerate(REFS):
    r = 67 + k
    pan.row_dimensions[r].height = 18
    unir(r, 2, r, 8, et, fuente(10), FONDO, al='left')
    unir(r, 9, r, 11, f, fuente(11, True), FONDO, al='right', fmt=fmt)
    unir(r, 12, r, 17, td, fuente(10, color=SUAVE), FONDO, al='left')
    boton(r, 18, 19, 'Ver ▸', None, AZUL, destino=destino)

# ---------------------------------------------------------------- mapas: figuras del plano

cols_px = [ancho_px(w) for w in COL_W] + [64] * 40
filas_px = [round(ALTO.get(r, 15) * 4 / 3) for r in range(1, 120)]
grilla = dibujo.Grilla(cols_px, filas_px)
x_caja1, x_caja2 = sum(cols_px[:1]), sum(cols_px[:8])
ancho_caja = sum(cols_px[1:8])
y_caja = sum(filas_px[:FILA_MAPA0 - 1])
alto_caja = sum(filas_px[FILA_MAPA0 - 1:FILA_MAPA1])
figs_geo = [('I_' + str(sitio_de(s['terreno'])), 'I', sitio_de(s['terreno']), '', s['puntos']) for s in GEO['sitios']]
figs_geo += [(f'E_{s}_{CLAVE_FIG[z]}', 'E', s, CLAVE_FIG[z], zz['puntos']) for s, z, zz in ZONAS]
max_x = max(p[0] for f in figs_geo for p in f[4])
max_y = max(p[1] for f in figs_geo for p in f[4])
esc = min(ancho_caja / max_x, alto_caja / max_y)


def estado_sitio(s):
    """Colores iniciales (mismas reglas que las fórmulas y la macro ColorearMapas, al día de hoy)."""
    filas = [m for m in MOV if m[1] == s]
    proy_ = sum(m[4] for m in filas if m[4] > 0)
    bot = sum(m[5] for m in filas if m[4] > 0)
    extra = sum(m[5] for m in filas if m[4] == 0)
    cod = 1 if proy_ > 0 and bot >= 0.99 * proy_ else 2 if bot + extra > 0 else 3
    t_ent = {z: est for (ss, z, est, *_) in ENT if ss == s}
    entregado = all(t_ent.get(k) == 'Entregada' for k in (('Acceso', 'Living') if isinstance(s, int) else ('Única',)))
    fin = max((g[2] for g in GAN if g[0] == s), default=None)
    return cod, extra > 0, entregado, bool(fin and HOY > fin and not entregado), t_ent


figs = []
for k, (nom, mapa, s, terr, pts) in enumerate(figs_geo):
    cod, extra, entregado, debe, t_ent = estado_sitio(s)
    x0 = (x_caja1 if mapa == 'I' else x_caja2) + (ancho_caja - max_x * esc) / 2
    pts_px = [(x0 + x * esc, y_caja + y * esc) for x, y in pts]
    if mapa == 'I':
        color, texto = {1: VERDE, 2: AMARILLO, 3: GRIS}[cod], f'{s}' + (' ⚠' if extra else '')
    else:
        est = t_ent.get(TERRAZA[{'fondo': 'fondo_patio'}.get(terr, terr)])
        color = CLARO if terr == 'fondo' else VERDE if est == 'Entregada' else ROJO if debe else \
            AMARILLO if est == 'En proceso' else GRIS
        texto = (f'{s}' + (' ✅' if entregado else ' ⚠' if debe else '')) if terr in ('living', 'unica') else None
    figs.append(dibujo.figura(grilla, 2000 + k, nom, pts_px, color, texto, macro='ClicMapa'))

# ---------------------------------------------------------------- Geometría (figuras del plano, desde el DXF)

titulo_hoja(geo, 'Geometría del plano (figuras de los mapas)',
            'Extraída del DXF. "📐 Importar DXF" lee un plano con polilíneas cerradas: capas 1…48 = sitios; Acceso, '
            'Living y Patio = terrazas; Edificios; otras capas (calle, pasajes) se dibujan como contexto. '
            '"✏️ Redibujar mapas" vuelve a dibujar las figuras desde esta tabla.')
for j, (t, a) in enumerate([('Figura', 16), ('Mapa', 7), ('Sitio', 7), ('Terraza', 10), ('Capa DXF', 14),
                            ('Puntos (m: x y;x y;…)', 120)], 1):
    c = geo.cell(3, j, t)
    c.font, c.fill = fuente(10, True, 'FFFFFF'), relleno(OSCURO)
    geo.column_dimensions[L(j)].width = a
for i, (nom, mapa, s, terr, pts) in enumerate(figs_geo, 4):
    capa = str(s) if mapa == 'I' else {'fondo': 'Patio'}.get(terr, terr.capitalize())
    for j, v in enumerate([nom, mapa, s, terr, capa, ';'.join(f'{x:.2f} {y:.2f}' for x, y in pts) + ';'], 1):
        geo.cell(i, j, v).font = fuente(9)
geo['H1'], geo['J1'] = '📐 Importar DXF', '✏️ Redibujar mapas'
for ref, nom in (('H1', 'BtnDxfGeo'), ('J1', 'BtnRedibujar')):
    c = geo[ref]
    c.hyperlink = Hyperlink(ref=ref, location=f"'Geometría'!{ref}", tooltip=c.value)
    c.font, c.fill, c.alignment = fuente(10, True, 'FFFFFF'), relleno(OSCURO), Alignment(horizontal='center')
    nombre(wb, nom, f"'Geometría'!${ref[0]}${ref[1:]}")
geo.column_dimensions['H'].width = geo.column_dimensions['J'].width = 18

# ---------------------------------------------------------------- Tablas dinámicas

titulo_hoja(tdn, 'Tablas dinámicas', 'Se actualizan al abrir el archivo y con ↻ Actualizar (o clic derecho → '
            'Actualizar). Puede arrastrar campos, filtrar y agrupar como en cualquier tabla dinámica.')
for c, t in (('B3', '🚚 Camiones por día'), ('G3', '📍 Camiones por sitio'), ('K3', '🧾 Planillas por fecha'),
             ('Q3', '🏁 Entregas por terraza')):
    tdn[c] = t
    tdn[c].font = fuente(12, True, OSCURO)
for col, w in zip('ABCDEFGHIJKLMNOPQRSTUV', [2, 13, 11, 9, 11, 3, 10, 11, 9, 3, 13, 13, 11, 13, 3, 3, 16, 11, 11, 11,
                                             13, 3]):
    tdn.column_dimensions[col].width = w
c_cam = TD.Cache('tblCamiones', CAB_CAM, CAM, {'Fecha': 'dd-mm-yyyy', 'Semana': 'dd-mm-yyyy'})
c_mov = TD.Cache('tblMovimiento', CAB_MOV, MOV, {'Fecha': 'dd-mm-yyyy'})
c_ent = TD.Cache('tblEntregas', CAB_ENT, ENT)
PIVOTES = [
    TD.TablaDinamica('tdCamionesDia', c_cam, 'Tablas dinámicas', 'B4', 'Fecha',
                     [('m³', 'sum', 'Total m³', 3), ('Viaje', 'sum', 'Viajes', 1), ('Camión día', 'sum', 'Camiones', 1)]),
    TD.TablaDinamica('tdCamionesSitio', c_cam, 'Tablas dinámicas', 'G4', 'Sitio',
                     [('m³', 'sum', 'Total m³', 3), ('Viaje', 'sum', 'Viajes', 1)]),
    TD.TablaDinamica('tdPlanillas', c_mov, 'Tablas dinámicas', 'K4', 'Fecha',
                     [('A botadero m³', 'sum', 'Botadero m³', 3)], columnas='Tipo'),
    TD.TablaDinamica('tdEntregas', c_ent, 'Tablas dinámicas', 'Q4', 'Terraza', [('Sitio', 'count', 'Terrazas', 1)],
                     columnas='Estado'),
]
TD.escribir({'Tablas dinámicas': tdn}, PIVOTES)
for r in range(5, 80):
    for c in ('B', 'K'):
        if isinstance(tdn[f'{c}{r}'].value, (date, datetime)):
            tdn[f'{c}{r}'].number_format = 'dd-mm-yyyy'
    for c in ('C', 'H', 'L', 'M', 'N'):
        tdn[f'{c}{r}'].number_format = '#,##0'

# ---------------------------------------------------------------- Ficha sitio

titulo_hoja(fic, 'Ficha de sitio', 'Elija el sitio en la celda amarilla (o haga clic en el mapa del Panel).')
for col, w in zip('ABCDEFGH', [2, 26, 22, 3, 18, 12, 20, 70]):
    fic.column_dimensions[col].width = w
fic['B3'] = 'Sitio'
fic['B3'].font = fuente(12, True)
fic['C3'] = 30
fic['C3'].font, fic['C3'].fill, fic['C3'].border = fuente(16, True), relleno('FFF7D6'), caja
fic['C3'].alignment = Alignment(horizontal='center')
dv = DataValidation(type='list', formula1='ListaSitios', allow_blank=False)
fic.add_data_validation(dv)
dv.add('C3')
fs = 'MATCH($C$3,Sitios!$A$4:$A$53,0)'
for i, (et, col, fmt) in enumerate([
        ('Movimiento', 'K', None), ('Avance', 'I', '0.0%'), ('Proyectado (esponjado) m³', 'E', '#,##0'),
        ('   Escarpe m³', 'C', '#,##0'), ('   Corte geométrico m³', 'D', '#,##0'),
        ('Retirado según planilla m³', 'F', '#,##0'), ('Camiones posteriores m³', 'G', '#,##0'),
        ('Retirado total m³', 'H', '#,##0'), ('Extra (proforma) m³', 'J', '#,##0'),
        ('Fecha del dato de planilla', 'B', 'dd-mm-yyyy'), ('Terraza de acceso', 'L', None),
        ('Terraza living', 'M', None), ('Entregado (acceso y living)', 'N', None), ('Fecha de entrega', 'O', 'dd-mm-yyyy'),
        ('Inicio carta Gantt', 'P', 'dd-mm-yyyy'), ('Término carta Gantt', 'Q', 'dd-mm-yyyy'),
        ('Cumplimiento', 'R', None)], 5):
    fic.cell(i, 2, et).font = fuente(10, True, SUAVE)
    c = fic.cell(i, 3, f'=IFERROR(INDEX(Sitios!${col}$4:${col}$53,{fs}),"")')
    c.font, c.alignment, c.border = fuente(11, i in (5, 6, 21)), Alignment(horizontal='left'), Border(bottom=delgado)
    if fmt:
        c.number_format = fmt
for txt, bg in (('Completo', VERDE), ('En intervención', AMARILLO), ('Atrasado', ROJO), ('Entregado', VERDE)):
    fic.conditional_formatting.add('C5:C21', FormulaRule(formula=[f'LEFT(C5,{len(txt)})="{txt}"'], fill=relleno(bg)))
fic['E3'] = 'Notas 📌 (más recientes primero)'
fic['E3'].font = fuente(12, True)
boton(4, 5, 5, '📌 Agregar nota', 'BtnNotaFicha', OCRE, ws=fic)
boton(4, 7, 7, '◀ Volver al Panel', None, OSCURO, destino="'Panel'!A1", ws=fic)
for j, t in zip('EFGH', ['Fecha y hora', '', 'Responsable', 'Nota']):
    fic[f'{j}6'] = t
    fic[f'{j}6'].font, fic[f'{j}6'].fill = fuente(10, True, 'FFFFFF'), relleno(OSCURO)
fic.merge_cells('E6:F6')
for k in range(1, 16):
    r = k + 6
    fila_nota = f'_xlfn.AGGREGATE(14,6,(ROW(tblNotas[Sitio])-ROW(tblNotas[#Headers]))/(tblNotas[Sitio]=$C$3),{k})'
    fic.merge_cells(f'E{r}:F{r}')
    fic[f'E{r}'] = f'=IFERROR(INDEX(tblNotas[Fecha y hora],{fila_nota}),"")'
    fic[f'E{r}'].number_format = 'dd-mm-yyyy hh:mm'
    fic[f'G{r}'] = f'=IFERROR(INDEX(tblNotas[Responsable],{fila_nota}),"")'
    fic[f'H{r}'] = f'=IFERROR(INDEX(tblNotas[Nota],{fila_nota}),"")'
    fic[f'H{r}'].alignment = Alignment(wrap_text=True, vertical='top')
    for j in 'EGH':
        fic[f'{j}{r}'].border = Border(bottom=delgado)

# ---------------------------------------------------------------- Programa (carta Gantt dibujada)

titulo_hoja(pro, 'Programa — carta Gantt por sitio')
pro['A2'] = (f'="Barra = semanas del programa · verde = entregado · rojo = atrasado · azul = pendiente · columna '
             f'rosada = semana del "&{fecha_txt("FechaPanel")}')
pro['A2'].font = fuente(10, color=SUAVE, cursiva=True)
SEMANAS = 30
for j, (t, a) in enumerate([('Sitio', 7), ('Inicio', 11), ('Término', 11), ('Entregado', 10), ('Cumplimiento', 19)], 1):
    c = pro.cell(4, j, t)
    c.font, c.fill = fuente(10, True, 'FFFFFF'), relleno(OSCURO)
    c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    pro.column_dimensions[L(j)].width = a
pro.row_dimensions[4].height = 34
for k in range(SEMANAS):
    c = pro.cell(4, 6 + k, f'=MIN(tblGantt[Inicio])-WEEKDAY(MIN(tblGantt[Inicio]),2)+1+7*{k}')
    c.number_format, c.font, c.fill = 'dd-mm', fuente(8, True, 'FFFFFF'), relleno(OSCURO)
    c.alignment = Alignment(text_rotation=90, horizontal='center')
    pro.column_dimensions[L(6 + k)].width = 3.2
for i, s in enumerate(TERRENOS[:48], 5):
    fr = FILA_SITIO[s]
    for j, col in enumerate(['A', 'P', 'Q', 'N', 'R'], 1):
        c = pro.cell(i, j, f'=Sitios!{col}{fr}')
        c.alignment, c.font = Alignment(horizontal='center'), fuente(9, j == 1)
        c.border = Border(bottom=Side(style='hair', color=BORDE))
    pro.cell(i, 2).number_format = pro.cell(i, 3).number_format = 'dd-mm-yyyy'
    for k in range(SEMANAS):
        pro.cell(i, 6 + k).border = Border(bottom=Side(style='hair', color=BORDE), left=Side(style='hair', color=BORDE))
ULTG = 4 + 48
area = f'F5:{L(5 + SEMANAS)}{ULTG}'
barra = 'AND($B5<>"",F$4<=$C5,F$4+6>=$B5)'
for cond, color in ((f'AND({barra},$D5="Sí")', VERDE), (f'AND({barra},$E5="Atrasado")', ROJO), (barra, '7DA7E0'),
                    ('AND(F$4<=FechaPanel,FechaPanel<F$4+7)', 'F6D5D5')):
    pro.conditional_formatting.add(area, FormulaRule(formula=[cond], fill=relleno(color), stopIfTrue=True))
for txt, bg in (('Atrasado', ROJO), ('Entregado', VERDE)):
    pro.conditional_formatting.add(f'E5:E{ULTG}', FormulaRule(formula=[f'LEFT(E5,{len(txt)})="{txt}"'],
                                                             fill=relleno(bg), font=Font(color='FFFFFF', bold=True)))
pro.freeze_panes = 'F5'

# ---------------------------------------------------------------- Ayuda

ayu.column_dimensions['A'].width = 2
ayu.column_dimensions['B'].width = 120
TEXTOS = [
    ('Cómo usar este archivo', 't'),
    ('Panel: elija el día ("Ver al día", o ◀ Hoy ▶) y la vista Día o Semana. Los indicadores, los mapas, los gráficos y '
     'el detalle del sitio se recalculan. Clic en un sitio de cualquier mapa = su detalle a la derecha.', ''),
    ('Para sumar información: escriba o pegue en las hojas amarillas (son tablas de Excel: crecen solas al escribir '
     'debajo) o use los botones 📥 del Panel. Luego ↻ Actualizar: se actualizan las tablas dinámicas, los gráficos y '
     'los colores de los mapas (también al abrir el archivo y al volver al Panel).', ''),
    ('Hojas de datos', 's'),
    ('• Movimiento: planilla "Resumen x Terraza" (una fila por sitio y fecha). Botón "📥 Planilla movimiento": elige el '
     'Excel de la planilla tal cual viene, pregunta la fecha y reemplaza los datos de esa fecha. Para cada sitio se '
     'usa la fecha más reciente hasta el día del Panel (no se suma con lo anterior). Filas sin presupuesto o "EXC '
     'ADICIONAL" = extra (proforma).', ''),
    ('• Camiones: tickets de la máquina. Botón "📥 Tickets (CSV)": agrega solo los tickets nuevos. Solo cuentan para '
     'un sitio los sectores que son un número de sitio (1 a 48); los demás quedan como generales. Los m³ de camiones '
     'de un sitio se suman a su avance solo si son posteriores a la fecha de su planilla.', ''),
    ('• Entregas: estado de cada terraza y fecha de entrega. Gantt: inicio y término por sitio. Notas: bitácora.', ''),
    ('Plano (hoja Geometría)', 's'),
    ('Las figuras de los mapas vienen del DXF del proyecto. "📐 Plano DXF" lee un DXF con polilíneas cerradas: capas '
     '1…48 = sitios; Acceso, Living, Patio = terrazas (se asignan al sitio que las contiene); Edificios; cualquier otra '
     'capa (calle, tramos, pasajes) se dibuja como contexto con el nombre de la capa. Luego redibuja los dos mapas.', ''),
    ('Reglas', 's'),
    ('• Avance = m³ retirados / m³ proyectados (esponjados); no depende de la carta Gantt. Verde = 100 % (desde 99 %).', ''),
    ('• Un sitio cumple la carta Gantt cuando su acceso y su living están entregados; si su término ya pasó y no están '
     'entregados, aparece en rojo / ⚠.', ''),
    ('Macros', 's'),
    ('Al abrir, presione "Habilitar contenido" (Windows) o "Habilitar macros" (Mac). Si Windows bloquea las macros '
     'porque el archivo viene de internet: cierre Excel, clic derecho en el archivo → Propiedades → "Desbloquear". '
     'Sin macros todo se calcula igual, pero los mapas no cambian de color, no responden al clic y los botones no '
     'funcionan. Requiere Excel 2013 o posterior (Windows o Mac).', ''),
]
for i, (t, tipo) in enumerate(TEXTOS, 2):
    c = ayu.cell(i, 2, t)
    c.font = fuente(16, True) if tipo == 't' else fuente(12, True, OSCURO) if tipo == 's' else fuente(11)
    c.alignment = Alignment(wrap_text=True, vertical='top')
    if not tipo:
        ayu.row_dimensions[i].height = 15 * (len(t) // 115 + 1)

# ---------------------------------------------------------------- impresión

pan.print_area = 'A1:AB71'
for ws in (pan, fic, pro, sit, tdn):
    ws.page_setup.orientation = 'landscape'
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_margins.left = ws.page_margins.right = 0.3
pan.page_setup.paperSize = pan.PAPERSIZE_A3
pan.page_setup.fitToHeight = 1
fic.print_area, pro.print_area, sit.print_area = 'A1:H21', f'A1:{L(5 + SEMANAS)}{ULTG}', f'A1:S{R_TOT}'

# ---------------------------------------------------------------- guardar: figuras, tablas dinámicas y macros

wb.active = 0
SALIDA.parent.mkdir(parents=True, exist_ok=True)
t1, t2, t3 = (SALIDA.with_suffix(f'.tmp{i}.xlsx') for i in (1, 2, 3))
wb.save(t1)
hojas_xml = {ws.title: f'xl/worksheets/sheet{i}.xml' for i, ws in enumerate(wb.worksheets, 1)}
dibujo.agregar(t1, hojas_xml['Panel'], figs, t2)
TD.empaquetar(t2, t3, PIVOTES, {'Tablas dinámicas': hojas_xml['Tablas dinámicas']})
vba = Path(__file__).parent / 'vba'


def codigo(nombre_mod):
    p = vba / f'{nombre_mod}.cls'
    return p.read_text(encoding='utf-8') if p.exists() else ''


modulos = [('ThisWorkbook', 'libro', codigo('ThisWorkbook'))]
modulos += [(c, 'hoja', codigo(c)) for _, c in orden]
modulos.append(('Botones', 'modulo', (vba / 'Botones.bas').read_text(encoding='utf-8')))
xlsm.empaquetar(t3, SALIDA, vba_proyecto.proyecto(modulos))
for t in (t1, t2, t3):
    t.unlink()
print(SALIDA, f'{SALIDA.stat().st_size / 1024:.0f} KB')
