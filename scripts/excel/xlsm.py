"""Convierte un .xlsx (guardado con openpyxl) en .xlsm agregando el proyecto VBA."""
import re
import zipfile

TIPO_LIBRO = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml'
TIPO_LIBRO_MACROS = 'application/vnd.ms-excel.sheet.macroEnabled.main+xml'
REL_VBA = 'http://schemas.microsoft.com/office/2006/relationships/vbaProject'


def empaquetar(xlsx, xlsm, vba_bin: bytes):
    with zipfile.ZipFile(xlsx) as zin, zipfile.ZipFile(xlsm, 'w', zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            datos = zin.read(item.filename)
            if item.filename == '[Content_Types].xml':
                t = datos.decode('utf-8').replace(TIPO_LIBRO, TIPO_LIBRO_MACROS)
                if 'Extension="bin"' not in t:
                    t = t.replace('<Default ', '<Default Extension="bin" ContentType="application/vnd.ms-office.'
                                  'vbaProject"/><Default ', 1)
                datos = t.encode('utf-8')
            elif item.filename == 'xl/_rels/workbook.xml.rels':
                t = datos.decode('utf-8')
                ids = [int(x) for x in re.findall(r'Id="rId(\d+)"', t)]
                t = t.replace('</Relationships>', f'<Relationship Id="rId{max(ids, default=0) + 1}" Type="{REL_VBA}" '
                                                  'Target="vbaProject.bin"/></Relationships>')
                datos = t.encode('utf-8')
            zout.writestr(item, datos)
        zout.writestr('xl/vbaProject.bin', vba_bin)
