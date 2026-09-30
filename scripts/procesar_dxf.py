"""Genera data/geometria.json (48 sitios x 3 terrazas + edificios) desde el plano DXF.

Uso:
    pip install ezdxf shapely
    python scripts/procesar_dxf.py data/fuente/plano.dxf [data/geometria.json]

Acepta dos formas de dibujo (ver docs/FORMATO_DXF.md):

A) Formato recomendado: polígonos CERRADOS en las capas `Acceso`, `Living` y `Patio`
   (Patio opcional: si falta se calcula como sitio - acceso - living), contornos de sitio
   en las capas `1`..`48` y rótulos `SITIO N`.

B) Formato actual (solo líneas): se unen las líneas de las capas `1`..`48`, `Acceso` y
   `Living` y se arman las caras cerradas. Cada cara se clasifica por la capa que la rodea:
   la rodeada por líneas de `Acceso` es el acceso, la rodeada por `Living` es el living y
   la restante es el fondo de patio.
"""
import json
import sys
from collections import Counter, defaultdict

import ezdxf
import shapely
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import polygonize, unary_union

SNAP = 50  # mm: une micro-aberturas entre líneas
ORDEN = ['acceso', 'living', 'fondo_patio']


def geometria_lineal(e, paso=50):
    t = e.dxftype()
    if t == 'LINE':
        return [(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)]
    if t in ('ARC', 'SPLINE', 'CIRCLE', 'ELLIPSE'):
        return [(p.x, p.y) for p in e.flattening(paso)]
    if t in ('LWPOLYLINE', 'POLYLINE'):
        pts = [(p[0], p[1]) for p in (e.get_points() if t == 'LWPOLYLINE' else e.points())]
        return pts + pts[:1] if e.closed else pts
    return None


def poligonos_cerrados(msp, capa):
    out = []
    for e in msp.query(f'LWPOLYLINE POLYLINE[layer=="{capa}"]'):
        if e.closed:
            pts = geometria_lineal(e)[:-1]
            if len(pts) >= 3:
                out.append(Polygon(pts).buffer(0))
    return out


def compartido(a, b):
    return a.boundary.intersection(b.buffer(SNAP * 1.2)).length


def leer(dxf_path):
    msp = ezdxf.readfile(dxf_path).modelspace()
    textos = [(e.plain_text().strip(), Point(e.dxf.insert.x, e.dxf.insert.y)) for e in msp.query('MTEXT TEXT')
              if e.dxf.layer == 'A-AREA-____-IDEN' or e.plain_text().strip().upper().startswith('SITIO')]
    rotulos = {int(t.split()[1]): p for t, p in textos if t.upper().startswith('SITIO ') and t.split()[1].isdigit()}
    modelos = [(t.replace('´', "'"), p) for t, p in textos if not t.upper().startswith('SITIO')]
    capas_sitio = {str(i) for i in range(1, 49)}

    acc, liv, pat = (poligonos_cerrados(msp, c) for c in ('Acceso', 'Living', 'Patio'))
    zonas = []  # (sitio, zona, Polygon)
    if len(acc) == 48 and len(liv) == 48:
        # --- Formato A: polígonos cerrados ---
        sitios = {}
        for n in range(1, 49):
            polys = poligonos_cerrados(msp, str(n))
            sitios[n] = max(polys, key=lambda p: p.area) if polys else None
        for tipo, lista in (('acceso', acc), ('living', liv), ('fondo_patio', pat)):
            for p in lista:
                c = p.representative_point()
                n = next((k for k, s in sitios.items() if s is not None and s.contains(c)), None)
                if n is None:
                    n = min(rotulos, key=lambda k: rotulos[k].distance(p))
                zonas.append((n, tipo, p))
        if not pat:
            for n, s in sitios.items():
                resto = s.difference(unary_union([z[2] for z in zonas if z[0] == n]))
                if not resto.is_empty:
                    zonas.append((n, 'fondo_patio', max(getattr(resto, 'geoms', [resto]), key=lambda g: g.area)))
    else:
        # --- Formato B: solo líneas ---
        lineas, por_capa = [], defaultdict(list)
        for e in msp:
            if e.dxf.layer in capas_sitio | {'Acceso', 'Living'}:
                pts = geometria_lineal(e)
                if pts and len(pts) >= 2:
                    ls = shapely.set_precision(LineString(pts), SNAP)
                    lineas.append(ls)
                    por_capa[e.dxf.layer].append(ls)
        caras = [f for f in polygonize(unary_union(lineas)) if f.area > 2e6]
        borde = {c: unary_union(por_capa[c]).buffer(80) for c in ('Acceso', 'Living')}

        def fraccion(f, capa):
            return f.boundary.intersection(borde[capa]).length / f.boundary.length

        tipo = {}
        for k, f in enumerate(caras):
            fa, fl = fraccion(f, 'Acceso'), fraccion(f, 'Living')
            tipo[k] = 'acceso' if fa >= 0.85 else 'living' if fl >= 0.9 else 'fondo_patio'
        livings = [k for k in tipo if tipo[k] == 'living']
        sitio_living = {}
        for n, p in rotulos.items():
            k = next(i for i, f in enumerate(caras) if f.contains(p))
            if tipo[k] != 'living':  # el rótulo quedó en otra terraza: tomar el living vecino
                k = max(livings, key=lambda j: compartido(caras[k], caras[j]))
            sitio_living[k] = n
        for k, f in enumerate(caras):
            if tipo[k] == 'living':
                zonas.append((sitio_living[k], 'living', f))
            else:
                j = max(sitio_living, key=lambda j: compartido(f, caras[j]))
                zonas.append((sitio_living[j], tipo[k], f))

    cuenta = Counter((n, t) for n, t, _ in zonas)
    faltan = [(n, t) for n in range(1, 49) for t in ORDEN if cuenta[(n, t)] != 1]
    if faltan:
        raise SystemExit(f'Terrazas faltantes o repetidas (sitio, terraza): {faltan[:12]}')

    edificios = sorted(poligonos_cerrados(msp, 'Edificios'), key=lambda p: -p.centroid.y)
    etapas = {}
    for c in ('Etapa1', 'Etapa2'):
        ls = [shapely.set_precision(LineString(g), 100) for e in msp if e.dxf.layer == c
              for g in [geometria_lineal(e)] if g and len(g) > 1]
        etapas[c] = unary_union(list(polygonize(unary_union(ls)))) if ls else Polygon()
    contexto = [LineString(geometria_lineal(e, 100)) for e in msp
                if e.dxf.layer in ('General', 'E') and geometria_lineal(e, 100) and len(geometria_lineal(e, 100)) > 1]
    return rotulos, modelos, zonas, edificios, etapas, contexto


def etapa_de(poly, etapas):
    """Etapa cuyo contorno cerrado contiene al sitio. Si solo una etapa forma un contorno
    cerrado (caso del plano actual: Etapa2 no cierra), el resto queda en la otra."""
    punto = poly.representative_point()
    cerradas = {int(k[-1]): v for k, v in etapas.items() if not v.is_empty}
    for n, v in cerradas.items():
        if v.contains(punto):
            return n
    abiertas = [int(k[-1]) for k, v in etapas.items() if v.is_empty]
    return abiertas[0] if len(abiertas) == 1 else None


def main():
    dxf_path = sys.argv[1]
    salida = sys.argv[2] if len(sys.argv) > 2 else 'data/geometria.json'
    rotulos, modelos, zonas, edificios, etapas, contexto = leer(dxf_path)

    x0, y0, x1, y1 = unary_union([z[2] for z in zonas] + edificios).bounds
    X0, Y1 = x0 - 3000, y1 + 3000
    ancho, alto = round((x1 - x0 + 6000) / 1000, 2), round((y1 - y0 + 6000) / 1000, 2)

    def T(x, y):
        return [round((x - X0) / 1000, 2), round((Y1 - y) / 1000, 2)]

    def anillo(p):
        return [T(x, y) for x, y in list(p.simplify(20).exterior.coords)[:-1]]

    out_zonas = [dict(terreno='S-%02d' % n, zona=t, area_m2=round(p.area / 1e6, 1), puntos=anillo(p))
                 for n, t, p in sorted(zonas, key=lambda z: (z[0], ORDEN.index(z[1])))]
    for i, p in enumerate(edificios):
        out_zonas.append(dict(terreno='ED-%d' % (i + 1), zona='unica', area_m2=round(p.area / 1e6, 1), puntos=anillo(p)))
    terrenos = []
    for n in range(1, 49):
        lote = unary_union([p for m, _, p in zonas if m == n])
        modelo = min(modelos, key=lambda m: m[1].distance(rotulos[n]))[0] if modelos else None
        terrenos.append(dict(codigo='S-%02d' % n, tipo='sitio', nombre='Sitio %d' % n, modelo=modelo,
                             etapa=etapa_de(lote, etapas), area_m2=round(lote.area / 1e6, 1)))
    terrenos += [dict(codigo='ED-%d' % (i + 1), tipo='edificio', nombre='Edificio %d' % (i + 1), modelo=None,
                      etapa=None, area_m2=round(p.area / 1e6, 1)) for i, p in enumerate(edificios)]
    fondo = []
    for l in contexto:
        pts = [T(x, y) for x, y in l.simplify(30).coords]
        if all(-5 < x < ancho + 5 and -5 < y < alto + 5 for x, y in pts):
            fondo.append(pts)
    with open(salida, 'w') as f:
        json.dump(dict(fuente=dxf_path.split('/')[-1], unidad='m', ancho=ancho, alto=alto,
                       terrenos=terrenos, zonas=out_zonas, fondo=fondo), f, ensure_ascii=False)
    print(f'{len(out_zonas)} zonas ({len(zonas)} terrazas + {len(edificios)} edificios) escritas en {salida}')


if __name__ == '__main__':
    main()
