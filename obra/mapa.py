"""Plano interactivo (Plotly) con las terrazas coloreadas."""
import json

import plotly.graph_objects as go

COLORES = {
    'sin_intervenir': '#d5dbd6', 'en_proceso': '#e9a23b', 'entregado': '#2f9e6b', 'terminado': '#2f9e6b',
    'atrasado': '#d64545', 'al_dia': '#2f9e6b', 'adelantado': '#3b7dd8', None: '#eef0ee',
}
NOMBRES = {
    'sin_intervenir': 'Sin intervenir', 'en_proceso': 'En proceso', 'entregado': 'Entregado', 'terminado': 'Terminado',
    'atrasado': 'Atrasado', 'al_dia': 'Al día', 'adelantado': 'Adelantado', None: 'Sin programa',
}
ZONAS = {'acceso': 'Acceso', 'living': 'Living', 'fondo_patio': 'Fondo de patio', 'unica': 'Zona única'}
ESCALA = ['#e6f2ea', '#b9dcc6', '#84c2a0', '#4fa379', '#2a7f57', '#17583b']


def color_avance(av):
    if av is None or av != av:  # None o NaN
        return COLORES[None]
    return ESCALA[min(len(ESCALA) - 1, int(min(av, 1) * (len(ESCALA) - 1) + 1e-9))]


def centroide(pts):
    a = cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
        f = x0 * y1 - x1 * y0
        a += f
        cx += (x0 + x1) * f
        cy += (y0 + y1) * f
    return (cx / (3 * a), cy / (3 * a)) if a else tuple(pts[0])


def figura(geo, zonas, color_de, hover_de, leyenda, seleccion=None, alto=680):
    """zonas: DataFrame con poligono, zona, terreno_id, codigo, nombre.
    color_de / hover_de: funciones fila -> color / texto. leyenda: [(color, texto)]."""
    fig = go.Figure()
    xs, ys = [], []
    for linea in geo['fondo']:
        for x, y in linea:
            xs.append(x)
            ys.append(y)
        xs.append(None)
        ys.append(None)
    fig.add_trace(go.Scatter(x=xs, y=ys, mode='lines', line=dict(color='#a3aca6', width=0.7),
                             hoverinfo='skip', showlegend=False))
    etiquetas = []
    for _, z in zonas.iterrows():
        pts = json.loads(z['poligono']) if isinstance(z['poligono'], str) else z['poligono']
        sel = seleccion is not None and z['terreno_id'] == seleccion
        fig.add_trace(go.Scatter(
            x=[p[0] for p in pts] + [pts[0][0]], y=[p[1] for p in pts] + [pts[0][1]],
            mode='lines', fill='toself', fillcolor=color_de(z), hoveron='fills',
            line=dict(color='#1d2320' if sel else '#ffffff', width=2.2 if sel else 0.8),
            text=hover_de(z), hoverinfo='text', showlegend=False, name=z['codigo']))
        if z['zona'] in ('living', 'unica'):
            cx, cy = centroide(pts)
            etiquetas.append((cx, cy, str(int(z['codigo'][2:])) if z['codigo'].startswith('S-') else z['codigo']))
    fig.add_trace(go.Scatter(x=[e[0] for e in etiquetas], y=[e[1] for e in etiquetas], text=[e[2] for e in etiquetas],
                             mode='text', textfont=dict(size=10, color='#1d2320'), hoverinfo='skip', showlegend=False))
    for color, texto in leyenda:
        fig.add_trace(go.Scatter(x=[None], y=[None], mode='markers', name=texto,
                                 marker=dict(size=12, color=color, symbol='square')))
    fig.update_xaxes(visible=False, range=[0, geo['ancho']])
    fig.update_yaxes(visible=False, range=[geo['alto'], 0], scaleanchor='x', scaleratio=1)
    fig.update_layout(height=alto, margin=dict(l=0, r=0, t=10, b=0), plot_bgcolor='rgba(0,0,0,0)',
                      paper_bgcolor='rgba(0,0,0,0)', hoverlabel=dict(bgcolor='white'),
                      legend=dict(orientation='h', yanchor='bottom', y=1.0, x=0), dragmode='pan')
    return fig
