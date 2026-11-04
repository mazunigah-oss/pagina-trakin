"""Agrega figuras (polígonos con texto) al dibujo de una hoja de un .xlsx/.xlsm ya guardado.

Las figuras se escriben como DrawingML (xdr:sp con geometría propia), con posición absoluta en la hoja; cada una puede
tener una macro asignada (se ejecuta al hacer clic) y un nombre para que el código VBA la encuentre.
"""
import re
import zipfile
from xml.sax.saxutils import escape

EMU_PX = 9525          # 1 píxel (96 ppp) en EMU
NS_A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
NS_XDR = 'http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing'
NS_R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'


class Grilla:
    """Convierte píxeles de la hoja en (celda, desplazamiento) según los anchos de columna y altos de fila."""

    def __init__(self, cols_px, filas_px):
        self.cols, self.filas = cols_px, filas_px

    @staticmethod
    def _ubicar(tamanos, v):
        acum = 0
        for i, t in enumerate(tamanos):
            if v < acum + t:
                return i, v - acum
            acum += t
        return len(tamanos) - 1, tamanos[-1]

    def ancla(self, x, y):
        c, dx = self._ubicar(self.cols, x)
        r, dy = self._ubicar(self.filas, y)
        return (f'<xdr:col>{c}</xdr:col><xdr:colOff>{round(dx * EMU_PX)}</xdr:colOff>'
                f'<xdr:row>{r}</xdr:row><xdr:rowOff>{round(dy * EMU_PX)}</xdr:rowOff>')


def figura(grilla, id_, nombre, puntos_px, relleno, texto='', borde='FFFFFF', macro=None, tam_texto=7,
           ancho_borde=0.75, texto_color='1D2320'):
    """puntos_px: [(x, y)] en píxeles desde la esquina superior izquierda de la hoja."""
    xs, ys = [p[0] for p in puntos_px], [p[1] for p in puntos_px]
    x0, y0 = min(xs), min(ys)
    w, h = max(max(xs) - x0, 1), max(max(ys) - y0, 1)
    pe = [(round((x - x0) * EMU_PX), round((y - y0) * EMU_PX)) for x, y in puntos_px]
    ruta = f'<a:moveTo><a:pt x="{pe[0][0]}" y="{pe[0][1]}"/></a:moveTo>' + ''.join(
        f'<a:lnTo><a:pt x="{x}" y="{y}"/></a:lnTo>' for x, y in pe[1:]) + '<a:close/>'
    W, H = round(w * EMU_PX), round(h * EMU_PX)
    cuerpo = ''
    if texto is not None:
        cuerpo = ('<xdr:txBody><a:bodyPr vertOverflow="overflow" horzOverflow="overflow" wrap="none" lIns="0" tIns="0" '
                  'rIns="0" bIns="0" rtlCol="0" anchor="ctr"/><a:lstStyle/><a:p><a:pPr algn="ctr"/>'
                  f'<a:r><a:rPr lang="es-CL" sz="{int(tam_texto * 100)}" b="1"><a:solidFill><a:srgbClr val="{texto_color}"/>'
                  f'</a:solidFill></a:rPr><a:t>{escape(texto)}</a:t></a:r></a:p></xdr:txBody>')
    attr_macro = f' macro="[0]!{macro}"' if macro else ''
    return (f'<xdr:twoCellAnchor editAs="absolute"><xdr:from>{grilla.ancla(x0, y0)}</xdr:from>'
            f'<xdr:to>{grilla.ancla(x0 + w, y0 + h)}</xdr:to>'
            f'<xdr:sp{attr_macro} textlink=""><xdr:nvSpPr><xdr:cNvPr id="{id_}" name="{escape(nombre)}"/>'
            '<xdr:cNvSpPr/></xdr:nvSpPr><xdr:spPr>'
            f'<a:xfrm><a:off x="{round(x0 * EMU_PX)}" y="{round(y0 * EMU_PX)}"/><a:ext cx="{W}" cy="{H}"/></a:xfrm>'
            '<a:custGeom><a:avLst/><a:gdLst/><a:ahLst/><a:cxnLst/><a:rect l="0" t="0" r="r" b="b"/>'
            f'<a:pathLst><a:path w="{W}" h="{H}">{ruta}</a:path></a:pathLst></a:custGeom>'
            f'<a:solidFill><a:srgbClr val="{relleno}"/></a:solidFill>'
            f'<a:ln w="{int(ancho_borde * 12700)}"><a:solidFill><a:srgbClr val="{borde}"/></a:solidFill></a:ln>'
            f'</xdr:spPr>{cuerpo}</xdr:sp><xdr:clientData/></xdr:twoCellAnchor>')


def agregar(archivo, hoja_xml, figuras_xml, salida):
    """Inserta las figuras en el dibujo de la hoja (xl/worksheets/sheetN.xml). La hoja debe tener ya un dibujo
    (por ejemplo, un gráfico agregado con openpyxl)."""
    with zipfile.ZipFile(archivo) as z:
        rels = z.read(hoja_xml.replace('worksheets/', 'worksheets/_rels/') + '.rels').decode('utf-8')
        destino = re.search(r'Type="[^"]*/drawing" Target="([^"]+)"', rels) or \
            re.search(r'Target="([^"]+)" Type="[^"]*/drawing"', rels)
        dibujo = 'xl/drawings/' + destino.group(1).split('/')[-1]
        with zipfile.ZipFile(salida, 'w', zipfile.ZIP_DEFLATED) as zo:
            for it in z.infolist():
                datos = z.read(it.filename)
                if it.filename == dibujo:
                    t = datos.decode('utf-8')
                    raiz = re.search(r'<(xdr:)?wsDr\b[^>]*>', t)
                    abre = raiz.group(0)
                    nuevo = abre
                    for pre, ns in (('xdr', NS_XDR), ('a', NS_A)):
                        if f'xmlns:{pre}=' not in nuevo:
                            nuevo = nuevo[:-1] + f' xmlns:{pre}="{ns}">'
                    cierre = '</xdr:wsDr>' if raiz.group(1) else '</wsDr>'
                    t = t.replace(abre, nuevo, 1).replace(cierre, ''.join(figuras_xml) + cierre)
                    datos = t.encode('utf-8')
                zo.writestr(it, datos)
