"""Plano (Plotly) como imagen fija: sin zoom ni arrastre, con información al pasar el cursor y,
si se pide, sitios seleccionables con un clic."""
import json

import plotly.graph_objects as go

ZONAS = {'acceso': 'Acceso', 'living': 'Living', 'fondo_patio': 'Fondo de patio', 'unica': 'Zona única'}
# configuración de st.plotly_chart para que el mapa sea una imagen fija
CONFIG_FIJO = {'displayModeBar': False, 'scrollZoom': False, 'doubleClick': False, 'showTips': False}


def puntos(p):
    return json.loads(p) if isinstance(p, str) else p


def centroide(pts):
    a = cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
        f = x0 * y1 - x1 * y0
        a += f
        cx += (x0 + x1) * f
        cy += (y0 + y1) * f
    return (cx / (3 * a), cy / (3 * a)) if a else tuple(pts[0])


def figura(geo, poligonos, color_de, hover_de, etiquetas=(), marcas=(), clic=(), alto=600, borde='#ffffff'):
    """poligonos: filas (dict o Series) con 'poligono' y los datos que usen color_de / hover_de.
    etiquetas: [(x, y, texto)] números de sitio. marcas: [(x, y, texto)] emojis (✅ ⚠️ 📌).
    clic: [(x, y, terreno_id, hover)] puntos seleccionables (st.plotly_chart con on_select)."""
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
    for z in poligonos:
        pts = puntos(z['poligono'])
        fig.add_trace(go.Scatter(
            x=[p[0] for p in pts] + [pts[0][0]], y=[p[1] for p in pts] + [pts[0][1]],
            mode='lines', fill='toself', fillcolor=color_de(z), hoveron='fills',
            line=dict(color=borde, width=0.9), text=hover_de(z), hoverinfo='text', showlegend=False))
    if etiquetas:  # (x, y, texto) o (x, y, texto, color)
        fig.add_trace(go.Scatter(x=[e[0] for e in etiquetas], y=[e[1] for e in etiquetas], text=[e[2] for e in etiquetas],
                                 mode='text', hoverinfo='skip', showlegend=False,
                                 textfont=dict(size=10, color=[e[3] if len(e) > 3 else '#1d2320' for e in etiquetas])))
    if marcas:
        fig.add_trace(go.Scatter(x=[m[0] for m in marcas], y=[m[1] for m in marcas], text=[m[2] for m in marcas],
                                 mode='text', textfont=dict(size=11), hoverinfo='skip', showlegend=False))
    if clic:
        fig.add_trace(go.Scatter(
            x=[c[0] for c in clic], y=[c[1] for c in clic], customdata=[c[2] for c in clic],
            text=[c[3] for c in clic], hoverinfo='text', mode='markers', showlegend=False,
            marker=dict(size=26, color='rgba(0,0,0,0.01)'),
            selected=dict(marker=dict(color='rgba(29,35,32,0.25)')), unselected=dict(marker=dict(opacity=1))))
    fig.update_xaxes(visible=False, range=[0, geo['ancho']], constrain='domain', fixedrange=True)
    fig.update_yaxes(visible=False, range=[geo['alto'], 0], scaleanchor='x', scaleratio=1, constrain='domain',
                     fixedrange=True)
    fig.update_layout(height=alto, margin=dict(l=0, r=0, t=4, b=0), plot_bgcolor='rgba(0,0,0,0)',
                      paper_bgcolor='rgba(0,0,0,0)', hoverlabel=dict(bgcolor='white'), dragmode=False,
                      showlegend=False, clickmode='event+select' if clic else 'none')
    return fig
