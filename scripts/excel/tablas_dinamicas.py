"""Tablas dinámicas nativas de Excel escritas directo en el paquete .xlsx/.xlsm.

La caché se guarda sin registros (saveData=0) y con refreshOnLoad=1: Excel la reconstruye desde la tabla de origen
(un ListObject, así crece con los datos) cada vez que se abre el archivo. Los elementos y el resultado inicial se
escriben igual, calculados con los datos actuales, para que la tabla se vea completa desde el principio.
"""
import re
import zipfile
from datetime import date, datetime
from xml.sax.saxutils import escape

NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
NS_R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
CT_CACHE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.pivotCacheDefinition+xml'
CT_TABLA = 'application/vnd.openxmlformats-officedocument.spreadsheetml.pivotTable+xml'


def _iso(v):
    return (v if isinstance(v, datetime) else datetime(v.year, v.month, v.day)).strftime('%Y-%m-%dT%H:%M:%S')


def _num(v):
    return repr(float(v)).rstrip('0').rstrip('.') if float(v) != int(v) else str(int(v))


def _item(v):
    if v is None or v == '':
        return '<m/>'
    if isinstance(v, (date, datetime)):
        return f'<d v="{_iso(v)}"/>'
    if isinstance(v, (int, float)):
        return f'<n v="{_num(v)}"/>'
    return f'<s v="{escape(str(v))}"/>'


def _orden(v):
    return (0, v) if isinstance(v, (int, float)) else (1, v) if isinstance(v, (date, datetime)) else (2, str(v))


def _shared(valores, con_items):
    """Atributos de sharedItems según los tipos de los valores (y la lista de elementos si es un campo de eje)."""
    vals = [v for v in valores if v not in (None, '')]
    blanco = len(vals) < len(valores)
    nums = [v for v in vals if isinstance(v, (int, float))]
    fechas = [v for v in vals if isinstance(v, (date, datetime))]
    textos = [v for v in vals if not isinstance(v, (int, float, date, datetime))]
    a = []
    if fechas and not nums and not textos:
        a += ['containsSemiMixedTypes="0"', 'containsNonDate="0"', 'containsDate="1"', 'containsString="0"',
              f'minDate="{_iso(min(fechas))}"', f'maxDate="{_iso(max(fechas))}"']
    elif nums and not textos and not fechas:
        a += ['containsSemiMixedTypes="0"' if not blanco else '', 'containsString="0"', 'containsNumber="1"']
        if all(float(v) == int(v) for v in nums):
            a.append('containsInteger="1"')
        a += [f'minValue="{_num(min(nums))}"', f'maxValue="{_num(max(nums))}"']
    elif textos and (nums or fechas):
        a.append('containsMixedTypes="1"')
    if blanco:
        a.append('containsBlank="1"')
    a = ' '.join(x for x in a if x)
    if not con_items:
        return f'<sharedItems {a}/>' if a else '<sharedItems/>', []
    unicos = sorted(set(vals), key=_orden) + ([None] if blanco else [])
    return (f'<sharedItems {a} count="{len(unicos)}">' + ''.join(_item(v) for v in unicos) + '</sharedItems>'), unicos


class Cache:
    def __init__(self, tabla, campos, filas, formatos=None):
        """tabla: nombre del ListObject de origen; campos: encabezados; filas: listas de valores (ya calculados)."""
        self.tabla, self.campos, self.filas = tabla, campos, filas
        self.formatos = formatos or {}
        self.ejes = set()
        self.id = None

    def columna(self, campo):
        i = self.campos.index(campo)
        return [f[i] for f in self.filas]


class TablaDinamica:
    def __init__(self, nombre, cache, hoja, celda, filas, datos, columnas=None, estilo='PivotStyleMedium2'):
        """filas: campo de filas; columnas: campo de columnas (opcional);
        datos: [(campo, 'sum'|'count', título, numFmtId)]."""
        self.nombre, self.cache, self.hoja, self.celda = nombre, cache, hoja, celda
        self.fila, self.columna, self.datos, self.estilo = filas, columnas, datos, estilo
        cache.ejes.add(filas)
        if columnas:
            cache.ejes.add(columnas)

    # resultado (para escribirlo en las celdas y para la ubicación)
    def resultado(self, unicos):
        fi = self.cache.campos.index(self.fila)
        filas = unicos[self.fila]
        if self.columna:
            ci = self.cache.campos.index(self.columna)
            cols = unicos[self.columna]
            campo, func = self.datos[0][0], self.datos[0][1]
            di = self.cache.campos.index(campo)

            def agg(sel):
                return len(sel) if func == 'count' else sum(r[di] or 0 for r in sel)
            tabla = [[agg([r for r in self.cache.filas if r[fi] == f and r[ci] == c]) for c in cols]
                     + [agg([r for r in self.cache.filas if r[fi] == f])] for f in filas]
            total = [agg([r for r in self.cache.filas if r[ci] == c]) for c in cols] + [agg(self.cache.filas)]
            return filas, cols, tabla, total
        out, total = [], []
        for campo, func, _, _ in self.datos:
            di = self.cache.campos.index(campo)

            def agg(sel):
                return len(sel) if func == 'count' else sum(r[di] or 0 for r in sel)
            out.append([agg([r for r in self.cache.filas if r[fi] == f]) for f in filas])
            total.append(agg(self.cache.filas))
        return filas, None, [list(x) for x in zip(*out)], total


def _col(c):
    n = 0
    for ch in c:
        n = n * 26 + ord(ch) - 64
    return n


def _letra(n):
    s = ''
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def escribir(ws_por_nombre, tablas):
    """Escribe en las hojas (openpyxl) el resultado inicial de cada tabla dinámica. Devuelve los elementos únicos."""
    unicos = {}
    for t in tablas:
        for campo in t.cache.ejes:
            vals = t.cache.columna(campo)
            u = sorted({v for v in vals if v not in (None, '')}, key=_orden)
            if any(v in (None, '') for v in vals):
                u.append(None)
            unicos[(id(t.cache), campo)] = u
    for t in tablas:
        ws = ws_por_nombre[t.hoja]
        m = re.match(r'([A-Z]+)(\d+)', t.celda)
        c0, r0 = _col(m.group(1)), int(m.group(2))
        u = {k[1]: v for k, v in unicos.items() if k[0] == id(t.cache)}
        filas, cols, tabla, total = t.resultado(u)
        fmt_fila = t.cache.formatos.get(t.fila)

        def poner(r, c, v, fmt=None, negrita=False):
            celda = ws.cell(r, c, '(en blanco)' if v is None else v)
            if fmt:
                celda.number_format = fmt
            if negrita:
                celda.font = celda.font.copy(bold=True)
        if cols is not None:
            poner(r0, c0, f'Cuenta de {t.datos[0][0]}' if t.datos[0][1] == 'count' else t.datos[0][2], negrita=True)
            poner(r0, c0 + 1, 'Etiquetas de columna', negrita=True)
            poner(r0 + 1, c0, 'Etiquetas de fila', negrita=True)
            for j, c in enumerate(cols):
                poner(r0 + 1, c0 + 1 + j, c, negrita=True)
            poner(r0 + 1, c0 + 1 + len(cols), 'Total general', negrita=True)
            for i, f in enumerate(filas):
                poner(r0 + 2 + i, c0, f, fmt_fila)
                for j, v in enumerate(tabla[i]):
                    poner(r0 + 2 + i, c0 + 1 + j, v)
            poner(r0 + 2 + len(filas), c0, 'Total general', negrita=True)
            for j, v in enumerate(total):
                poner(r0 + 2 + len(filas), c0 + 1 + j, v, negrita=True)
            t.ref = f'{t.celda}:{_letra(c0 + len(cols) + 1)}{r0 + 2 + len(filas)}'
        else:
            poner(r0, c0, 'Etiquetas de fila', negrita=True)
            for j, d in enumerate(t.datos):
                poner(r0, c0 + 1 + j, d[2], negrita=True)
            for i, f in enumerate(filas):
                poner(r0 + 1 + i, c0, f, fmt_fila)
                for j, v in enumerate(tabla[i]):
                    poner(r0 + 1 + i, c0 + 1 + j, v)
            poner(r0 + 1 + len(filas), c0, 'Total general', negrita=True)
            for j, v in enumerate(total):
                poner(r0 + 1 + len(filas), c0 + 1 + j, v, negrita=True)
            t.ref = f'{t.celda}:{_letra(c0 + len(t.datos))}{r0 + 1 + len(filas)}'
        t._u = u
    return unicos


def _xml_cache(cache):
    campos = []
    for c in cache.campos:
        sh, _ = _shared(cache.columna(c), c in cache.ejes)
        fmt = cache.formatos.get(c)
        num = 14 if fmt and 'yy' in fmt else 0
        campos.append(f'<cacheField name="{escape(c)}" numFmtId="{num}">{sh}</cacheField>')
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            f'<pivotCacheDefinition xmlns="{NS}" xmlns:r="{NS_R}" saveData="0" refreshOnLoad="1" '
            f'createdVersion="3" refreshedVersion="3" minRefreshableVersion="3" recordCount="{len(cache.filas)}">'
            f'<cacheSource type="worksheet"><worksheetSource name="{cache.tabla}"/></cacheSource>'
            f'<cacheFields count="{len(campos)}">' + ''.join(campos) + '</cacheFields></pivotCacheDefinition>')


def _xml_tabla(t):
    cache = t.cache
    campos = []
    for c in cache.campos:
        if c == t.fila or c == t.columna:
            n = len(t._u[c])
            eje = 'axisRow' if c == t.fila else 'axisCol'
            campos.append(f'<pivotField axis="{eje}" showAll="0"><items count="{n + 1}">'
                          + ''.join(f'<item x="{i}"/>' for i in range(n)) + '<item t="default"/></items></pivotField>')
        elif any(d[0] == c for d in t.datos):
            campos.append('<pivotField dataField="1" showAll="0"/>')
        else:
            campos.append('<pivotField showAll="0"/>')
    nf = len(t._u[t.fila])
    fila_items = ''.join('<i><x/></i>' if i == 0 else f'<i><x v="{i}"/></i>' for i in range(nf)) + '<i t="grand"><x/></i>'
    # como lo escribe Excel: con varios valores en columnas la primera fila ya es de títulos de datos
    cab = 0 if (not t.columna and len(t.datos) > 1) else 1
    xml = [f'<location ref="{t.ref}" firstHeaderRow="{cab}" firstDataRow="{2 if t.columna else 1}" firstDataCol="1"/>']
    xml.append(f'<pivotFields count="{len(campos)}">' + ''.join(campos) + '</pivotFields>')
    xml.append(f'<rowFields count="1"><field x="{cache.campos.index(t.fila)}"/></rowFields>')
    xml.append(f'<rowItems count="{nf + 1}">{fila_items}</rowItems>')
    if t.columna:
        nc = len(t._u[t.columna])
        xml.append(f'<colFields count="1"><field x="{cache.campos.index(t.columna)}"/></colFields>')
        xml.append(f'<colItems count="{nc + 1}">' + ''.join('<i><x/></i>' if j == 0 else f'<i><x v="{j}"/></i>'
                                                             for j in range(nc)) + '<i t="grand"><x/></i></colItems>')
    elif len(t.datos) > 1:
        xml.append('<colFields count="1"><field x="-2"/></colFields>')
        xml.append(f'<colItems count="{len(t.datos)}">' + ''.join(
            '<i><x/></i>' if j == 0 else f'<i i="{j}"><x v="{j}"/></i>' for j in range(len(t.datos))) + '</colItems>')
    else:
        xml.append('<colItems count="1"><i/></colItems>')
    xml.append(f'<dataFields count="{len(t.datos)}">' + ''.join(
        f'<dataField name="{escape(tit)}" fld="{cache.campos.index(campo)}"'
        + (' subtotal="count"' if func == 'count' else '') + f' baseField="0" baseItem="0" numFmtId="{nf_}"/>'
        for campo, func, tit, nf_ in t.datos) + '</dataFields>')
    xml.append(f'<pivotTableStyleInfo name="{t.estilo}" showRowHeaders="1" showColHeaders="1" showRowStripes="0" '
               'showColStripes="0" showLastColumn="1"/>')
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            f'<pivotTableDefinition xmlns="{NS}" name="{escape(t.nombre)}" cacheId="{cache.id}" '
            'applyNumberFormats="0" applyBorderFormats="0" applyFontFormats="0" applyPatternFormats="0" '
            'applyAlignmentFormats="0" applyWidthHeightFormats="1" dataCaption="Valores" updatedVersion="3" '
            'minRefreshableVersion="3" createdVersion="3" useAutoFormatting="1" itemPrintTitles="1" indent="0" '
            'outline="1" outlineData="1" multipleFieldFilters="0" rowHeaderCaption="' + escape(t.fila) + '">'
            + ''.join(xml) + '</pivotTableDefinition>')


def empaquetar(archivo, salida, tablas, hoja_xml_por_nombre):
    """Agrega cachés y tablas dinámicas al paquete. hoja_xml_por_nombre: {'Tablas dinámicas': 'xl/worksheets/sheet2.xml'}"""
    caches = []
    for t in tablas:
        if t.cache not in caches:
            caches.append(t.cache)
    for i, c in enumerate(caches):
        c.id = 100 + i
    partes = {}
    for i, c in enumerate(caches, 1):
        partes[f'xl/pivotCache/pivotCacheDefinition{i}.xml'] = _xml_cache(c)
        c.parte = f'pivotCacheDefinition{i}.xml'
    for i, t in enumerate(tablas, 1):
        partes[f'xl/pivotTables/pivotTable{i}.xml'] = _xml_tabla(t)
        partes[f'xl/pivotTables/_rels/pivotTable{i}.xml.rels'] = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'<Relationship Id="rId1" Type="{REL}/pivotCacheDefinition" Target="../pivotCache/{t.cache.parte}"/>'
            '</Relationships>')
        t.parte = f'pivotTable{i}.xml'
    with zipfile.ZipFile(archivo) as zin, zipfile.ZipFile(salida, 'w', zipfile.ZIP_DEFLATED) as zout:
        nombres = set(zin.namelist())
        rels_hojas = {}
        for hoja, xml in hoja_xml_por_nombre.items():
            rels_hojas[xml.replace('worksheets/', 'worksheets/_rels/') + '.rels'] = [t for t in tablas if t.hoja == hoja]
        for it in zin.infolist():
            d = zin.read(it.filename)
            n = it.filename
            if n == '[Content_Types].xml':
                t = d.decode('utf-8')
                extra = ''.join(f'<Override PartName="/{p}" ContentType="{CT_CACHE if "Cache" in p else CT_TABLA}"/>'
                                for p in partes if p.endswith('.xml') and '_rels' not in p)
                d = t.replace('</Types>', extra + '</Types>').encode('utf-8')
            elif n == 'xl/_rels/workbook.xml.rels':
                t = d.decode('utf-8')
                t = t.replace('</Relationships>', ''.join(
                    f'<Relationship Id="rIdPC{c.id}" Type="{REL}/pivotCacheDefinition" '
                    f'Target="pivotCache/{c.parte}"/>' for c in caches) + '</Relationships>')
                d = t.encode('utf-8')
            elif n == 'xl/workbook.xml':
                t = d.decode('utf-8')
                bloque = '<pivotCaches>' + ''.join(f'<pivotCache cacheId="{c.id}" r:id="rIdPC{c.id}"/>'
                                                  for c in caches) + '</pivotCaches>'
                raiz = re.search(r'<workbook\b[^>]*>', t).group(0)
                if 'xmlns:r=' not in raiz:
                    t = t.replace(raiz, raiz[:-1] + f' xmlns:r="{NS_R}">', 1)
                # va después de calcPr / definedNames (orden del esquema)
                m = re.search(r'<calcPr[^>]*/>', t) or re.search(r'</definedNames>', t)
                t = t[:m.end()] + bloque + t[m.end():] if m else t.replace('</workbook>', bloque + '</workbook>')
                d = t.encode('utf-8')
            elif n in rels_hojas:
                t = d.decode('utf-8')
                t = t.replace('</Relationships>', ''.join(
                    f'<Relationship Id="rIdPT{k}" Type="{REL}/pivotTable" Target="../pivotTables/{x.parte}"/>'
                    for k, x in enumerate(rels_hojas.pop(n), 1)) + '</Relationships>')
                d = t.encode('utf-8')
            zout.writestr(it, d)
        for n, lista in rels_hojas.items():   # hojas sin archivo de relaciones
            zout.writestr(n, '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                          '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                          + ''.join(f'<Relationship Id="rIdPT{k}" Type="{REL}/pivotTable" '
                                    f'Target="../pivotTables/{x.parte}"/>' for k, x in enumerate(lista, 1))
                          + '</Relationships>')
        for p, x in partes.items():
            if p not in nombres:
                zout.writestr(p, x)
