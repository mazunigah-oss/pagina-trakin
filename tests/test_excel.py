"""El .xlsm generado por scripts/excel/construir.py debe abrir en Excel sin "reparaciones".

Excel no acepta una tabla cuyos nombres de columna no coinciden con las celdas de encabezado: la repara y borra las
fórmulas que la nombran (tblX[Columna]). Estas pruebas revisan el archivo entregado en data/excel/.
"""
import re
import zipfile
from html import unescape
from pathlib import Path

import pytest
from openpyxl import load_workbook

XLSM = Path(__file__).resolve().parents[1] / 'data' / 'excel' / 'Seguimiento_Loma_La_Cruz.xlsm'


@pytest.fixture(scope='module')
def libro():
    return load_workbook(XLSM, keep_vba=True)


def columnas(libro):
    return {t.displayName: [c.name for c in t.tableColumns] for ws in libro.worksheets for t in ws.tables.values()}


def test_columnas_de_tabla_iguales_al_encabezado(libro):
    for ws in libro.worksheets:
        for t in ws.tables.values():
            fila = ws[t.ref][0]
            nombres = [c.name for c in t.tableColumns]
            assert nombres == [c.value for c in fila], t.displayName
            assert len({n.lower() for n in nombres}) == len(nombres), t.displayName


def test_referencias_estructuradas_existen(libro):
    cols = columnas(libro)
    assert set(cols) == {'tblMovimiento', 'tblCamiones', 'tblEntregas', 'tblGantt', 'tblNotas'}
    with zipfile.ZipFile(XLSM) as z:
        for n in z.namelist():
            if not (n.startswith('xl/') and n.endswith('.xml')):
                continue
            texto = unescape(z.read(n).decode('utf-8'))
            for tbl, cuerpo in re.findall(r'(tbl\w+)\[((?:[^\[\]]|\[[^\[\]]*\])*)\]', texto):
                assert tbl in cols, (n, tbl)
                for p in re.findall(r'\[([^\]]*)\]', cuerpo) or [cuerpo]:
                    assert p.startswith('#') or p in cols[tbl], (n, tbl, p)


def test_columnas_calculadas(libro):
    calc = {(t.displayName, c.name) for ws in libro.worksheets for t in ws.tables.values()
            for c in t.tableColumns if c.calculatedColumnFormula is not None}
    assert {('tblMovimiento', 'Tipo'), ('tblCamiones', 'Semana'), ('tblCamiones', 'Viaje'),
            ('tblEntregas', 'Estado al día'), ('tblEntregas', 'Clave')} <= calc


def test_macros_y_figuras():
    with zipfile.ZipFile(XLSM) as z:
        tipos = z.read('[Content_Types].xml').decode()
        assert 'macroEnabled.main+xml' in tipos and 'xl/vbaProject.bin' in z.namelist()
        assert z.read('xl/vbaProject.bin')[:8] == bytes.fromhex('D0CF11E0A1B11AE1')
        dibujo = z.read('xl/drawings/drawing1.xml').decode()
        ids = re.findall(r'cNvPr id="(\d+)"', dibujo)
        assert len(ids) == len(set(ids))
        assert dibujo.count('macro="[0]!ClicMapa"') > 150
