"""Genera data/geometria.json (polígonos de las 144 zonas + 2 edificios) a partir del plano DXF.

Uso:  pip install ezdxf shapely numpy opencv-python-headless
      python scripts/procesar_dxf.py data/fuente/plano.dxf data/fuente/plano_zonas.png

1. Une las líneas de las capas "1".."48", "Acceso" y "Living" y arma las caras cerradas (144).
2. Asigna a cada cara su sitio y zona leyendo los colores del PNG de zonas
   (azul = acceso, naranjo = living, verde = fondo de patio), alineado por su contorno.
3. Agrega los edificios (polilíneas de la capa "Edificios"), el modelo de casa de cada sitio
   (textos de la capa A-AREA-____-IDEN) y las líneas de contexto (capas "General" y "E").
Las coordenadas quedan en metros con el eje Y hacia abajo (listo para SVG).
"""
import json
import sys
from collections import Counter

import cv2
import ezdxf
import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import polygonize, unary_union

dxf_path, png_path = sys.argv[1], sys.argv[2]
salida = sys.argv[3] if len(sys.argv) > 3 else 'data/geometria.json'
msp = ezdxf.readfile(dxf_path).modelspace()


def lineas(capas, paso=50):
    out = []
    for e in msp:
        if e.dxf.layer not in capas:
            continue
        t = e.dxftype()
        if t == 'LINE':
            out.append(LineString([(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)]))
        elif t in ('ARC', 'SPLINE'):
            out.append(LineString([(p.x, p.y) for p in e.flattening(paso)]))
    return out


# 1. caras
capas = {str(i) for i in range(1, 49)} | {'Acceso', 'Living'}
caras = [f for f in polygonize(unary_union([shapely.set_precision(l, 50) for l in lineas(capas)])) if f.area > 2e6]
assert len(caras) == 144, f'Se esperaban 144 zonas y se encontraron {len(caras)}'

# 2. clasificación por colores del PNG
img = cv2.imread(png_path)[:, :, ::-1].astype(int)
colores = {'living': (255, 219, 170), 'fondo_patio': (193, 232, 187), 'acceso': (170, 215, 255)}
etiqueta = np.full(img.shape[:2], -1)
componentes = []
for zona, c in colores.items():
    m = (np.abs(img - np.array(c)).sum(axis=2) < 12).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, connectivity=4)
    for i in range(1, n):
        if st[i, 4] >= 40:
            etiqueta[lab == i] = len(componentes)
            componentes.append(zona)
ys, xs = np.where(etiqueta >= 0)
x0, y0, x1, y1 = unary_union(caras).bounds
sx, sy = (xs.max() - xs.min()) / (x1 - x0), (ys.max() - ys.min()) / (y1 - y0)
a_png = lambda x, y: (xs.min() + (x - x0) * sx, ys.min() + (y1 - y) * sy)
zona_de = {}
for k, f in enumerate(caras):
    m = np.zeros(etiqueta.shape, np.uint8)
    cv2.fillPoly(m, [np.array([a_png(x, y) for x, y in f.exterior.coords], np.int32)], 1)
    votos = Counter(etiqueta[m > 0].tolist())
    votos.pop(-1, None)
    zona_de[k] = componentes[votos.most_common(1)[0][0]]

# sitio: la cara con el texto "SITIO n" y sus vecinas del mismo lote (unión por adyacencia
# a través de la cara living, que toca a acceso y fondo de patio)
textos = [(e.plain_text().strip(), Point(e.dxf.insert.x, e.dxf.insert.y)) for e in msp.query('MTEXT')]
sitios = {int(t.split()[1]): p for t, p in textos if t.startswith('SITIO')}
modelos = [(t.replace('´', "'"), p) for t, p in textos if not t.startswith('SITIO')]
lote_de = {}
for n, p in sitios.items():
    cara = next(k for k, f in enumerate(caras) if f.contains(p))
    lote_de[cara] = n
livings = [k for k in range(len(caras)) if zona_de[k] == 'living']
# cada living pertenece al lote cuya cara etiquetada es ella misma o su vecina más larga
for k in livings:
    if k in lote_de:
        continue
    vecinas = sorted(((caras[k].boundary.intersection(caras[j].buffer(60)).length, j) for j in lote_de), reverse=True)
    lote_de[k] = lote_de[vecinas[0][1]]
sitio_living = {k: lote_de[k] for k in livings}
for k in range(len(caras)):
    if zona_de[k] == 'living':
        continue
    vec = max(((caras[k].boundary.intersection(caras[j].buffer(60)).length, j) for j in livings))
    lote_de[k] = sitio_living[vec[1]]
par = Counter((lote_de[k], zona_de[k]) for k in range(len(caras)))
assert all(v == 1 for v in par.values()) and len(par) == 144, 'La asignación de zonas a sitios no es única'

# 3. salida
edificios = sorted((Polygon([(p[0], p[1]) for p in e.get_points()]) for e in msp.query('LWPOLYLINE[layer=="Edificios"]')),
                   key=lambda p: -p.centroid.y)
bx0, by0, bx1, by1 = unary_union(caras + edificios).bounds
X0, Y1 = bx0 - 3000, by1 + 3000
T = lambda x, y: [round((x - X0) / 1000, 2), round((Y1 - y) / 1000, 2)]
orden = ['acceso', 'living', 'fondo_patio']
zonas = sorted(
    (dict(terreno='S-%02d' % lote_de[k], zona=zona_de[k], area_m2=round(f.area / 1e6, 1),
          puntos=[T(x, y) for x, y in list(f.simplify(20).exterior.coords)[:-1]]) for k, f in enumerate(caras)),
    key=lambda z: (z['terreno'], orden.index(z['zona'])))
for i, p in enumerate(edificios):
    zonas.append(dict(terreno='ED-%d' % (i + 1), zona='unica', area_m2=round(p.area / 1e6, 1),
                      puntos=[T(x, y) for x, y in list(p.exterior.coords)[:-1]]))
terrenos = [dict(codigo='S-%02d' % n, tipo='sitio', nombre='Sitio %d' % n,
                 modelo=min(modelos, key=lambda m: m[1].distance(sitios[n]))[0]) for n in range(1, 49)]
terrenos += [dict(codigo='ED-%d' % (i + 1), tipo='edificio', nombre='Edificio %d' % (i + 1), modelo=None)
             for i in range(len(edificios))]
ancho, alto = round((bx1 - bx0 + 6000) / 1000, 2), round((by1 - by0 + 6000) / 1000, 2)
fondo = []
for l in lineas({'General', 'E'}, paso=100):
    pts = [T(x, y) for x, y in l.simplify(30).coords]
    if all(-5 < x < ancho + 5 and -5 < y < alto + 5 for x, y in pts):
        fondo.append(pts)
json.dump(dict(fuente='plano.dxf', unidad='m', ancho=ancho, alto=alto, terrenos=terrenos, zonas=zonas, fondo=fondo),
          open(salida, 'w'), ensure_ascii=False)
print(f'{len(zonas)} zonas escritas en {salida}')
