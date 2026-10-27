"""Avance de movimiento de tierra — Loma La Cruz (48 sitios, Etapas 1 y 2).

Visita: acceso libre, solo lectura. Administrador: contraseña (secreto ADMIN_PASSWORD).
"""
import hmac
import json
import os
from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import insert, update

from obra import calculos as C
from obra import db as T
from obra import importar as I
from obra.mapa import CONFIG_FIJO, ZONAS, centroide, figura, puntos

st.set_page_config(page_title='Avance movimiento de tierra', page_icon='🚜', layout='wide')


def secreto(nombre):
    try:
        if nombre in st.secrets:
            return st.secrets[nombre]
    except Exception:  # no hay secrets.toml
        pass
    return os.environ.get(nombre)


@st.cache_resource
def motor(version):  # la versión fuerza una conexión nueva cuando se publica código nuevo
    return T.crear_motor(secreto('DATABASE_URL'))


@st.cache_resource
def geometria():
    return T.cargar_geometria()


MOTOR = motor(T.VERSION)
GEO = geometria()
PERSISTENTE = bool(secreto('DATABASE_URL'))


def num(x, d=0):
    if x is None or x != x:
        return '—'
    return f'{x:,.{d}f}'.replace(',', '_').replace('.', ',').replace('_', '.')


def fecha_cl(iso):
    return '—' if not iso or iso != iso else '-'.join(reversed(str(iso)[:10].split('-')))


# ---------------------------------------------------------------- colores y textos

VERDE, AMARILLO, GRIS, CLARO, ROJO = '#2f9e6b', '#fbe08c', '#cfd6d1', '#f1f3f0', '#e06666'
ESCALA = ['#e6f2ea', '#b9dcc6', '#84c2a0', '#4fa379', '#2a7f57', '#17583b']
NOMBRE_ACT = {'escarpe': 'Escarpe', 'corte': 'Corte geométrico', 'adicional': 'Extra a botadero (proforma)'}
NOMBRE_ESTADO = {'sin_intervenir': 'Sin intervenir', 'en_proceso': 'En proceso', 'entregado': 'Entregada',
                 'terminado': 'Terminado', None: '—'}
NOMBRE_INTERV = {'completo': 'Movimiento completo (100 %)', 'en_intervencion': 'Con intervención',
                 'sin_intervenir': 'Sin intervención'}
NOMBRE_CUMPLE = {'entregado': '✅ Entregado', 'atrasado': '⚠️ Atrasado', 'pendiente': 'Pendiente', None: 'Sin programa'}


def color_avance(av):
    if av is None or av != av:
        return CLARO
    return ESCALA[min(len(ESCALA) - 1, int(min(av, 1) * (len(ESCALA) - 1) + 1e-9))]


def leyenda_abajo(items):
    """Leyenda en lenguaje simple debajo del mapa: (color o emoji, título, detalle)."""
    html = []
    for c, t, d in items:
        icono = (f'<span style="display:inline-block;width:14px;height:14px;border-radius:3px;background:{c};'
                 f'border:1px solid #c9cfca;vertical-align:-2px;margin-right:8px"></span>' if c.startswith('#')
                 else f'<span style="display:inline-block;width:14px;margin-right:8px">{c}</span>')
        html.append(f'<div>{icono}<b>{t}</b>' + (f' — {d}' if d else '') + '</div>')
    st.markdown('<div style="display:flex;flex-direction:column;gap:5px;font-size:0.9rem">' + ''.join(html) + '</div>',
                unsafe_allow_html=True)


# ---------------------------------------------------------------- barra lateral

with st.sidebar:
    st.header('Loma La Cruz')
    dia = st.date_input('Ver al día', value=date.fromisoformat(C.hoy_chile()), format='DD/MM/YYYY').isoformat()
    st.divider()
    clave = secreto('ADMIN_PASSWORD')
    if st.session_state.get('admin'):
        st.success('Sesión de administrador')
        if st.button('Cerrar sesión', use_container_width=True):
            st.session_state.admin = False
            st.rerun()
    else:
        with st.expander('Acceso administrador'):
            if not clave:
                st.caption('Defina el secreto ADMIN_PASSWORD para habilitar el acceso de administrador.')
            else:
                with st.form('login', border=False):
                    dada = st.text_input('Contraseña', type='password')
                    if st.form_submit_button('Ingresar', use_container_width=True):
                        if hmac.compare_digest(dada.encode(), str(clave).encode()):
                            st.session_state.admin = True
                            st.rerun()
                        else:
                            st.error('Contraseña incorrecta')
    st.caption(f'Versión {T.VERSION}')
    if not PERSISTENTE:
        st.warning('Base de datos local: en Streamlit Cloud los datos cargados se pierden al reiniciar la app. '
                   'Configure DATABASE_URL para guardarlos de forma permanente.', icon='⚠️')

ADMIN = bool(st.session_state.get('admin'))

# ---------------------------------------------------------------- datos

terrenos = C.leer(MOTOR, 'terreno')
zonas = C.leer(MOTOR, 'zona').merge(terrenos[['id', 'codigo', 'nombre', 'tipo', 'modelo', 'etapa']]
                                    .rename(columns={'id': 'terreno_id'}), on='terreno_id')
viajes = C.leer(MOTOR, 'viaje')
ajustes = C.leer(MOTOR, 'ajuste')
gantt = C.leer(MOTOR, 'gantt')
hitos = C.leer(MOTOR, 'hito').sort_values('fecha')
notas = C.leer(MOTOR, 'nota')
acts = C.volumenes(C.leer(MOTOR, 'actividad'), viajes, ajustes, hasta=dia)
ES = C.estado_sitios(terrenos, acts, zonas, gantt, dia).set_index('terreno_id')

# contornos de sitio (sin divisiones de terrazas) y posiciones de etiquetas y marcas
_sitios = pd.DataFrame(GEO.get('sitios', []))
if _sitios.empty:  # geometría antigua: se usan las terrazas
    _sitios = zonas[zonas['zona'].isin(['living', 'unica'])][['codigo', 'poligono']].rename(columns={'codigo': 'terreno'})
SITIOS = _sitios.rename(columns={'terreno': 'codigo', 'puntos': 'poligono'}).merge(
    terrenos[['id', 'codigo', 'nombre', 'tipo']].rename(columns={'id': 'terreno_id'}), on='codigo')
SITIOS['centro'] = SITIOS['poligono'].map(lambda p: centroide(puntos(p)))
zonas['centro'] = zonas['poligono'].map(lambda p: centroide(puntos(p)))
CENTRO_SITIO = SITIOS.set_index('terreno_id')['centro'].to_dict()
CENTRO_ZONA = {(r.terreno_id, r.zona): r.centro for r in zonas.itertuples()}


def corto(codigo):
    return str(int(codigo[2:])) if codigo.startswith('S-') else codigo


def etiquetas_sitio(sufijo=lambda tid: '', color=lambda tid: '#1d2320'):
    return [(*CENTRO_SITIO[r.terreno_id], corto(r.codigo) + sufijo(r.terreno_id), color(r.terreno_id))
            for r in SITIOS.itertuples()]


def etiquetas_terraza():
    """Número de sitio en el fondo de patio (acceso y living quedan libres para ✅ / ⚠️)."""
    return [(*r.centro, corto(r.codigo)) for r in zonas.itertuples() if r.zona in ('fondo_patio', 'unica')]


def filas(df):
    return [r for _, r in df.iterrows()]


st.title('Avance movimiento de tierra')
st.caption(f'Loma La Cruz · 48 sitios · Etapas 1 y 2 · datos al {fecha_cl(dia)}')

pestanas = ['Resumen', 'Entregas', 'Programa', 'Movimiento de tierra', 'Tickets']
if ADMIN:
    pestanas += ['Cargar datos', 'Editar estados']
tabs = dict(zip(pestanas, st.tabs(pestanas)))


def encabezado_sitio(tid):
    t = terrenos.set_index('id').loc[tid]
    extra = ' · '.join(x for x in [f'Modelo {t.modelo}' if t.modelo else '',
                                   f'Etapa {int(t.etapa)}' if t.etapa == t.etapa and t.etapa else '',
                                   f'{num(t.area_m2)} m²'] if x)
    st.subheader(t.nombre)
    st.caption(extra)


# ---------------------------------------------------------------- mapas compartidos

def hover_intervencion(r):
    e = ES.loc[r['terreno_id']]
    txt = f"<b>{r['nombre']}</b>{' ⚠️' if e['tiene_extra'] else ''}<br>{NOMBRE_INTERV[e['intervencion']]}"
    if e['proyectado_m3'] > 0 or e['retirado_total_m3'] > 0:
        txt += (f"<br>m³ proyectados: {num(e['proyectado_m3'])}"
                f"<br>m³ retirados: {num(e['retirado_total_m3'])}"
                + (f" (incluye {num(e['retirado_extra_m3'])} m³ extra)" if e['tiene_extra'] else '')
                + (f"<br>Avance: {num(100 * e['pct_total'], 1)} %" if e['pct_total'] is not None else ''))
    if e['tiene_extra']:
        txt += '<br>⚠️ Tiene movimiento extra (mayor al proyectado)'
    return txt


def mapa_intervencion(alto=560, key=None):
    color = {'completo': VERDE, 'en_intervencion': AMARILLO, 'sin_intervenir': GRIS}
    st.plotly_chart(figura(GEO, filas(SITIOS), lambda r: color[ES.loc[r['terreno_id'], 'intervencion']],
                           hover_intervencion, etiquetas_sitio(lambda t: ' ⚠️' if ES.loc[t, 'tiene_extra'] else ''),
                           alto=alto), use_container_width=True, config=CONFIG_FIJO, key=key)
    cont = ES['intervencion'].value_counts()
    leyenda_abajo([(VERDE, f"Movimiento completo ({cont.get('completo', 0)})", '100 % del volumen proyectado'),
                   (AMARILLO, f"Con intervención ({cont.get('en_intervencion', 0)})", 'se está trabajando'),
                   (GRIS, f"Sin intervención ({cont.get('sin_intervenir', 0)})", ''),
                   ('⚠️', f"Movimiento extra ({int(ES['tiene_extra'].sum())})",
                    'retiró volumen adicional al proyectado (puede pasar del 100 %)')])


def estado_terraza(z):
    """Para el mapa de entregas: entregada, atrasada, en_proceso, pendiente o patio (no se considera)."""
    if z['zona'] == 'fondo_patio':
        return 'patio'
    if z['estado'] == 'entregado':
        return 'entregado'
    if ES.loc[z['terreno_id'], 'debe_entregar']:
        return 'atrasado'
    return 'en_proceso' if z['estado'] == 'en_proceso' else 'pendiente'


def hover_entrega(z):
    e = ES.loc[z['terreno_id']]
    txt = f"<b>{z['nombre']} · {ZONAS[z['zona']]}</b>"
    if z['zona'] == 'fondo_patio':
        return txt + '<br>El fondo de patio no se considera en las entregas'
    est = estado_terraza(z)
    if est == 'entregado':
        txt += '<br>✅ Entregada' + (f" el {fecha_cl(z['fecha_entrega'])}" if pd.notna(z['fecha_entrega']) else '')
    elif est == 'atrasado':
        txt += '<br>⚠️ Debería estar entregada'
    else:
        txt += f"<br>{NOMBRE_ESTADO[z['estado']]}"
    if e['termino']:
        txt += f"<br>Fecha de entrega (Gantt): {fecha_cl(e['termino'])}"
    return txt


def mapa_entregas(alto=560, key=None):
    color = {'entregado': VERDE, 'atrasado': ROJO, 'en_proceso': AMARILLO, 'pendiente': GRIS, 'patio': CLARO}
    marcas = []
    for _, z in zonas.iterrows():
        est = estado_terraza(z)
        if est in ('entregado', 'atrasado'):
            marcas.append((*z['centro'], '✅' if est == 'entregado' else '⚠️'))
    st.plotly_chart(figura(GEO, filas(zonas), lambda z: color[estado_terraza(z)], hover_entrega, etiquetas_terraza(),
                           marcas, alto=alto), use_container_width=True, config=CONFIG_FIJO, key=key)
    sit = ES[ES['tipo'] == 'sitio']
    leyenda_abajo([(VERDE, f"✅ Entregada ({int(sit['entregado'].sum())} sitios)", 'acceso y living entregados'),
                   (ROJO, f"⚠️ Debería estar entregada ({int((sit['cumplimiento'] == 'atrasado').sum())} sitios)",
                    'su fecha de la carta Gantt ya pasó'),
                   (AMARILLO, 'En proceso de entrega', ''), (GRIS, 'Pendiente', 'aún no le toca'),
                   (CLARO, 'Fondo de patio', 'no se considera en las entregas')])


# ---------------------------------------------------------------- Resumen

with tabs['Resumen']:
    fant = C.dia_anterior_con_movimiento(viajes, dia)
    r = C.resumen_dia(viajes, terrenos, fant)
    fprev = C.dia_anterior_con_movimiento(viajes, fant)
    rp = C.resumen_dia(viajes, terrenos, fprev)
    st.markdown(f'#### 🚚 Movimiento del día anterior — {fecha_cl(fant)}')
    if r['por_origen'].empty:
        st.info(f'Sin tickets de camiones el {fecha_cl(fant)}.'
                + ('' if viajes.empty else f" Último día con tickets: {fecha_cl(viajes['fecha'].max())}."))
    else:
        def delta(a, b, d=0):
            x = a - b
            return f"{'+' if x >= 0 else '−'}{num(abs(x), d)} vs {fecha_cl(fprev)}"

        t1, t2, t3, t4 = st.columns([1, 1, 1, 2])
        t1.metric('Camiones', num(r['camiones']), delta(r['camiones'], rp['camiones']))
        t2.metric('Viajes', num(r['viajes']), delta(r['viajes'], rp['viajes']), help='Tickets válidos menos anulados')
        t3.metric('m³ a botadero', num(r['m3'], 1), delta(r['m3'], rp['m3'], 1))
        with t4:
            st.markdown('**Origen**')
            st.markdown('  \n'.join(f"{o.origen}: {num(o.viajes)} viajes · {num(o.m3, 1)} m³"
                                    for o in r['por_origen'].itertuples()))

    st.divider()
    sit = ES[ES['tipo'] == 'sitio']
    proy, ret, extra = sit['proyectado_m3'].sum(), sit['retirado_plan_m3'].sum(), ES['retirado_extra_m3'].sum()
    deben, entregados = int(sit['debe_entregar'].sum()), int(sit['entregado'].sum())
    cumplen = int((sit['debe_entregar'] & sit['entregado']).sum())
    k1, k2, k3, k4 = st.columns(4)
    k1.metric('Avance movimiento de tierra', f'{num(100 * ret / proy, 1)} %' if proy else '—',
              f'{num(ret)} de {num(proy)} m³', delta_color='off',
              help='m³ retirados / m³ proyectados (esponjados). No incluye el movimiento extra.')
    k2.metric('Movimiento extra', f'{num(extra)} m³', help='Volumen adicional a botadero, no proyectado (proforma)')
    k3.metric('Sitios entregados', num(entregados), help='Sitios con acceso y living entregados')
    k4.metric('Cumplimiento carta Gantt', f'{cumplen} de {deben}' if deben else '—',
              f'{deben - cumplen} atrasados' if deben - cumplen else 'al día',
              delta_color='inverse' if deben - cumplen else 'normal',
              help='Sitios que según la carta Gantt ya debían estar entregados y lo están')

    izq, der = st.columns(2)
    with izq:
        st.markdown('#### Mapa de intervención')
        mapa_intervencion(key='res_interv')
    with der:
        st.markdown('#### Mapa de entregas y cumplimiento')
        mapa_entregas(key='res_entregas')

# ---------------------------------------------------------------- Entregas

with tabs['Entregas']:
    mapa, panel = st.columns([3, 2])
    with mapa:
        mapa_entregas(alto=640, key='ent_mapa')
    with panel:
        opciones = ['—'] + terrenos['nombre'].tolist()
        eleccion = st.selectbox('Ver detalle de', opciones, key='sel_entregas')
        if eleccion != '—':
            tid = int(terrenos.loc[terrenos['nombre'] == eleccion, 'id'].iloc[0])
            e = ES.loc[tid]
            encabezado_sitio(tid)
            st.markdown(f"**Cumplimiento:** {NOMBRE_CUMPLE[e['cumplimiento']]}"
                        + (f"  \nFecha de entrega según carta Gantt: **{fecha_cl(e['termino'])}**" if e['termino'] else '')
                        + (f"  \nEntregado el {fecha_cl(e['fecha_entrega'])}"
                           + (' (a tiempo)' if e['a_tiempo'] else ' (con atraso)' if e['termino'] else '')
                           if e['fecha_entrega'] else ''))
            for z in zonas[zonas['terreno_id'] == tid].itertuples():
                cuenta = '' if z.zona != 'fondo_patio' else ' · _no se considera_'
                st.markdown(f"**{ZONAS[z.zona]}** · {num(z.area_m2)} m²{cuenta}  \n"
                            + ('✅ Entregada' + (f' el {fecha_cl(z.fecha_entrega)}' if pd.notna(z.fecha_entrega) else '')
                               if z.estado == 'entregado' else NOMBRE_ESTADO[z.estado]))
        st.markdown('**Entregas por sitio**')
        sit = ES[ES['tipo'] == 'sitio'].copy()
        icono = {'entregado': '✅', 'en_proceso': '🟡', 'sin_intervenir': '·', None: ''}
        st.dataframe(pd.DataFrame({
            'Sitio': sit['codigo'].map(corto),
            'Acceso': sit['acceso'].map(icono), 'Living': sit['living'].map(icono),
            'Fecha Gantt': sit['termino'].map(fecha_cl),
            'Cumplimiento': sit['cumplimiento'].map(NOMBRE_CUMPLE)}),
            hide_index=True, use_container_width=True, height=420)

# ---------------------------------------------------------------- Programa

with tabs['Programa']:
    if gantt.empty:
        st.info('Aún no se ha cargado el programa (carta Gantt). El administrador puede subirlo en "Cargar datos".')

    def hover_programa(z):
        e = ES.loc[z['terreno_id']]
        txt = f"<b>{z['nombre']}</b> · {ZONAS[z['zona']]}"
        txt += (f"<br>Carta Gantt: {fecha_cl(e['inicio'])} → {fecha_cl(e['termino'])}" if e['termino']
                else '<br>Sin programa en la carta Gantt')
        txt += f"<br>Movimiento: {num(100 * e['pct_plan'], 1)} %" if e['pct_plan'] is not None else ''
        if z['zona'] != 'fondo_patio':
            txt += '<br>✅ Entregada' if z['estado'] == 'entregado' else f"<br>Entrega: {NOMBRE_ESTADO[z['estado']]}"
        return txt

    def color_real(tid):
        e = ES.loc[tid]
        if e['pct_plan'] is not None and e['pct_plan'] >= C.UMBRAL_REAL_VERDE:
            return VERDE
        return AMARILLO if e['intervencion'] != 'sin_intervenir' else GRIS

    color_gantt = {'completo': VERDE, 'en_intervencion': AMARILLO, 'pendiente': GRIS, None: CLARO}
    ac_li = zonas['zona'].isin(['acceso', 'living', 'unica'])
    marcas_gantt = [(*z.centro, '✅') for z in zonas[ac_li].itertuples()
                    if ES.loc[z.terreno_id, 'gantt_estado'] == 'completo']
    marcas_real = [(*z.centro, '✅') for z in zonas[ac_li].itertuples() if z.estado == 'entregado']
    izq, der = st.columns(2)
    with izq:
        st.markdown(f'#### ¿Cómo deberíamos ir? — carta Gantt al {fecha_cl(dia)}')
        st.plotly_chart(figura(GEO, filas(zonas), lambda z: color_gantt[ES.loc[z['terreno_id'], 'gantt_estado']],
                               hover_programa, etiquetas_terraza(), marcas_gantt, alto=560),
                        use_container_width=True, config=CONFIG_FIJO, key='prog_gantt')
        cont = ES['gantt_estado'].value_counts()
        leyenda_abajo([(VERDE, f"Debería estar al 100 % ({cont.get('completo', 0)})",
                        'su programa ya terminó: movimiento completo'),
                       ('✅', 'Acceso y living deberían estar entregados', ''),
                       (AMARILLO, f"Debería estar con intervención ({cont.get('en_intervencion', 0)})",
                        'hoy está dentro de su programa'),
                       (GRIS, f"Aún no le toca ({cont.get('pendiente', 0)})", ''),
                       (CLARO, 'Sin programa', 'no está en la carta Gantt')])
    with der:
        st.markdown(f'#### ¿Qué está pasando? — real al {fecha_cl(dia)}')
        st.plotly_chart(figura(GEO, filas(zonas), lambda z: color_real(z['terreno_id']), hover_programa,
                               etiquetas_terraza(), marcas_real, alto=560),
                        use_container_width=True, config=CONFIG_FIJO, key='prog_real')
        verdes = sum(color_real(t) == VERDE for t in ES.index)
        amarillos = sum(color_real(t) == AMARILLO for t in ES.index)
        leyenda_abajo([(VERDE, f'Movimiento sobre 95 % ({verdes})', 'sin ✅ si aún no se entrega'),
                       ('✅', f"Terraza entregada ({len(marcas_real)})", 'acceso o living'),
                       (AMARILLO, f'Con intervención ({amarillos})', 'se está trabajando'),
                       (GRIS, 'Sin intervención', '')])

    atrasados = ES[ES['cumplimiento'] == 'atrasado']
    if not atrasados.empty:
        st.markdown('<br>**⚠️ Sitios que deberían estar entregados y no lo están**', unsafe_allow_html=True)
        st.dataframe(pd.DataFrame({
            'Sitio': atrasados['codigo'].map(corto), 'Fecha Gantt': atrasados['termino'].map(fecha_cl),
            'Acceso': atrasados['acceso'].map(NOMBRE_ESTADO), 'Living': atrasados['living'].map(NOMBRE_ESTADO),
            'Movimiento': 100 * atrasados['pct_plan'].astype(float)}),
            hide_index=True, use_container_width=True,
            column_config={'Movimiento': st.column_config.ProgressColumn('Movimiento', format='%.0f %%', min_value=0,
                                                                          max_value=100)})
    if not gantt.empty:
        with st.expander('Ver carta Gantt'):
            g = gantt.merge(terrenos[['id', 'codigo']].rename(columns={'id': 'terreno_id'}), on='terreno_id')
            g = g.assign(Inicio=pd.to_datetime(g['inicio']), Fin=pd.to_datetime(g['termino']) + pd.Timedelta(days=1),
                         Sitio=g['codigo'], Actividad=g['actividad'].fillna('movimiento de tierra'))
            fig = px.timeline(g.sort_values('inicio'), x_start='Inicio', x_end='Fin', y='Sitio', color='Actividad',
                              color_discrete_sequence=['#2f6d4f', '#e9a23b', '#3b7dd8'])
            fig.add_vline(x=pd.Timestamp(dia), line_color='#d64545', line_dash='dash')
            for h in hitos.itertuples():
                fig.add_vline(x=pd.Timestamp(h.fecha), line_color='#3b7dd8', line_dash='dot')
                fig.add_annotation(x=pd.Timestamp(h.fecha), y=1, yref='paper', text=h.nombre, showarrow=False,
                                   font=dict(size=10, color='#3b7dd8'), xanchor='left', yanchor='bottom')
            fig.update_yaxes(autorange='reversed', title='')
            fig.update_layout(height=max(300, 16 * g['Sitio'].nunique()), margin=dict(l=0, r=0, t=20, b=0))
            st.plotly_chart(fig, use_container_width=True, config=CONFIG_FIJO)

# ---------------------------------------------------------------- Movimiento de tierra

with tabs['Movimiento de tierra']:
    por_tipo = acts.groupby('tipo')[['volumen_proyectado_m3', 'retirado_m3']].sum()

    def bloque(col, titulo, tipos):
        p = por_tipo.reindex(tipos).fillna(0).sum()
        col.metric(titulo, f"{num(100 * p['retirado_m3'] / p['volumen_proyectado_m3'], 1)} %" if p['volumen_proyectado_m3'] else '—',
                   f"{num(p['retirado_m3'])} de {num(p['volumen_proyectado_m3'])} m³", delta_color='off')

    m1, m2, m3, m4 = st.columns(4)
    bloque(m1, 'Escarpe', ['escarpe'])
    bloque(m2, 'Corte geométrico', ['corte'])
    bloque(m3, 'Escarpe + corte', ['escarpe', 'corte'])
    m4.metric('Extra a botadero (proforma)', f"{num(por_tipo['retirado_m3'].get('adicional', 0))} m³",
              help='Volumen adicional, no considerado en la planificación inicial')

    con_nota = set(notas['terreno_id']) if not notas.empty else set()
    mapa, panel = st.columns([3, 2])
    with mapa:
        clic = [(*CENTRO_SITIO[r.terreno_id], r.terreno_id, hover_intervencion(r._asdict()))
                for r in SITIOS.itertuples()]
        evento = st.plotly_chart(
            figura(GEO, filas(SITIOS), lambda r: color_avance(ES.loc[r['terreno_id'], 'pct_plan']), hover_intervencion,
                   etiquetas_sitio(lambda t: (' ⚠️' if ES.loc[t, 'tiene_extra'] else '') + (' 📌' if t in con_nota else ''),
                                   lambda t: '#ffffff' if (ES.loc[t, 'pct_plan'] or 0) >= 0.7 else '#1d2320'),
                   clic=clic, alto=640),
            use_container_width=True, config=CONFIG_FIJO, key=f"mt_mapa_{st.session_state.get('mt_n', 0)}",
            on_select='rerun', selection_mode='points')
        leyenda_abajo([(CLARO, 'Sin volumen proyectado', ''), (ESCALA[0], '0 %', ''), (ESCALA[2], '40 %', ''),
                       (ESCALA[4], '80 %', ''), (ESCALA[5], '100 %', ''),
                       ('⚠️', 'Movimiento extra', 'retiró más de lo proyectado'),
                       ('📌', 'Tiene notas', 'haga clic en el sitio para verlas')])
    elegido = None
    try:
        pts = evento.selection['points'] if evento else []
        if pts:
            cd = pts[0].get('customdata')
            elegido = int(cd[0] if isinstance(cd, (list, tuple)) else cd)
    except (AttributeError, KeyError, TypeError, ValueError):
        elegido = None
    # el clic se guarda y el mapa se vuelve a dibujar sin selección (Plotly atenúa lo no seleccionado)
    if elegido is not None:
        st.session_state.mt_sitio = elegido
        st.session_state.mt_n = st.session_state.get('mt_n', 0) + 1
        st.rerun()
    with panel:
        nombres = terrenos.set_index('id')['nombre']
        opciones = ['—'] + nombres.tolist()
        actual = st.session_state.get('mt_sitio')
        idx = opciones.index(nombres[actual]) if actual in nombres.index else 0
        eleccion = st.selectbox('Sitio (o haga clic en el mapa)', opciones, index=idx)
        tid = None if eleccion == '—' else int(nombres[nombres == eleccion].index[0])
        st.session_state.mt_sitio = tid
        if tid is None:
            st.caption('Haga clic en un sitio del mapa para ver su detalle y sus notas 📌.')
        else:
            encabezado_sitio(tid)
            a = acts[acts['terreno_id'] == tid].set_index('tipo')
            filas_t = []
            for tipo in ('escarpe', 'corte', 'adicional'):
                if tipo in a.index and (a.loc[tipo, 'volumen_proyectado_m3'] > 0 or a.loc[tipo, 'retirado_m3'] != 0):
                    p_, r_ = a.loc[tipo, 'volumen_proyectado_m3'], a.loc[tipo, 'retirado_m3']
                    filas_t.append(dict(Actividad=NOMBRE_ACT[tipo], Proyectado=p_ if tipo != 'adicional' else None,
                                        Retirado=r_, Avance=100 * r_ / p_ if p_ and tipo != 'adicional' else None))
            if filas_t:
                e = ES.loc[tid]
                filas_t.append(dict(Actividad='Total', Proyectado=e['proyectado_m3'], Retirado=e['retirado_total_m3'],
                                    Avance=100 * e['pct_total'] if e['pct_total'] is not None else None))
                st.dataframe(pd.DataFrame(filas_t), hide_index=True, use_container_width=True,
                             column_config={'Proyectado': st.column_config.NumberColumn('Proyectado m³', format='%.1f'),
                                            'Retirado': st.column_config.NumberColumn('Retirado m³', format='%.1f'),
                                            'Avance': st.column_config.NumberColumn('Avance', format='%.1f %%')})
                if e['tiene_extra']:
                    st.warning(f"Movimiento extra: {num(e['retirado_extra_m3'])} m³ sobre lo proyectado.", icon='⚠️')
            else:
                st.caption('Sin volumen proyectado ni movimientos.')

            st.markdown('##### 📌 Notas')
            ns = notas[notas['terreno_id'] == tid].sort_values('creado_en', ascending=False) if not notas.empty else notas
            if ns.empty:
                st.caption('Este sitio no tiene notas.')
            for n_ in ns.itertuples():
                with st.container(border=True):
                    st.markdown(f"📌 **{n_.responsable}** · {fecha_cl(n_.creado_en[:10])} {n_.creado_en[11:16]}  \n{n_.texto}")
            if ADMIN:
                with st.form(f'nota_{tid}', clear_on_submit=True):
                    resp = st.text_input('Responsable')
                    texto = st.text_area('Nota', placeholder='Nueva actualización…')
                    if st.form_submit_button('📌 Guardar nota'):
                        if resp.strip() and texto.strip():
                            with MOTOR.begin() as con:
                                con.execute(insert(T.nota).values(terreno_id=tid, responsable=resp.strip()[:80],
                                                                  texto=texto.strip(), creado_en=C.ahora_chile()))
                            st.rerun()
                        else:
                            st.error('Complete el responsable y la nota.')
            else:
                st.caption('Para agregar notas, ingrese como administrador.')

    st.markdown('#### Detalle por sitio')
    sit = ES[ES['tipo'] == 'sitio']
    ap = acts.pivot_table(index='terreno_id', columns='tipo', values=['volumen_proyectado_m3', 'retirado_m3'],
                          aggfunc='sum', fill_value=0)

    def col(valor, tipo):
        return ap[(valor, tipo)] if (valor, tipo) in ap.columns else pd.Series(0.0, index=ap.index)

    tabla = pd.DataFrame({
        'Sitio': sit['codigo'].map(corto),
        'Escarpe': col('volumen_proyectado_m3', 'escarpe').reindex(sit.index).values,
        'Corte': col('volumen_proyectado_m3', 'corte').reindex(sit.index).values,
        'Proyectado': sit['proyectado_m3'].values, 'Retirado': sit['retirado_plan_m3'].values,
        'Avance': (100 * sit['pct_plan'].astype(float)).values,
        'Extra': sit['retirado_extra_m3'].values, 'Total retirado': sit['retirado_total_m3'].values,
        'Avance con extra': (100 * sit['pct_total'].astype(float)).values,
        'Notas': ['📌' if t in con_nota else '' for t in sit.index]})
    st.dataframe(tabla, hide_index=True, use_container_width=True, height=460, column_config={
        'Escarpe': st.column_config.NumberColumn('Escarpe proy. m³', format='%.1f'),
        'Corte': st.column_config.NumberColumn('Corte proy. m³', format='%.1f'),
        'Proyectado': st.column_config.NumberColumn('Proyectado m³', format='%.1f'),
        'Retirado': st.column_config.NumberColumn('Retirado m³', format='%.0f'),
        'Avance': st.column_config.ProgressColumn('Avance', format='%.0f %%', min_value=0, max_value=100),
        'Extra': st.column_config.NumberColumn('Extra m³', format='%.0f'),
        'Total retirado': st.column_config.NumberColumn('Total con extra m³', format='%.0f'),
        'Avance con extra': st.column_config.NumberColumn('Avance con extra', format='%.0f %%')})
    st.caption('Proyectado = (escarpe + corte geométrico) esponjado. El extra a botadero (proforma) no entra al avance; '
               '"Avance con extra" lo incluye y puede pasar del 100 %.')

# ---------------------------------------------------------------- Tickets

with tabs['Tickets']:
    c1, c2 = st.columns(2)
    desde = c1.date_input('Desde', value=date.fromisoformat(C.dia_anterior_con_movimiento(viajes, dia)),
                          format='DD/MM/YYYY', key='t_desde').isoformat()
    hasta = c2.date_input('Hasta', value=date.fromisoformat(dia), format='DD/MM/YYYY', key='t_hasta').isoformat()
    v = viajes[(viajes['fecha'] >= desde) & (viajes['fecha'] <= hasta)].sort_values(['fecha', 'hora'], ascending=False)
    if v.empty:
        st.info('No hay tickets en el período.')
    else:
        nombres = terrenos.set_index('id')['nombre']
        st.markdown(f"{len(v)} tickets · {v.loc[v['estado'] == 'VALIDO', 'patente'].nunique()} camiones · "
                    f"**{num(v['volumen_m3'].sum(), 1)} m³ netos**")
        st.dataframe(v.assign(fecha=v['fecha'].map(fecha_cl),
                              sitio=v['terreno_id'].map(lambda x: nombres.get(x) if pd.notna(x) else 'General'))
                     [['ticket', 'fecha', 'hora', 'patente', 'volumen_m3', 'sector', 'sitio', 'tipo', 'estado']],
                     hide_index=True, use_container_width=True,
                     column_config={'volumen_m3': st.column_config.NumberColumn('m³', format='%.1f')})

# ---------------------------------------------------------------- Administración

if ADMIN:
    with tabs['Cargar datos']:
        st.markdown('Suba archivos **Excel** o **CSV**. Pasos: elegir archivo → **Revisar archivo** → '
                    '**Confirmar carga**. Nada se guarda hasta confirmar.')
        if 'ultima_carga' in st.session_state:
            titulo, nombre, resumen = st.session_state.ultima_carga
            st.success(f'✅ Carga guardada: **{titulo}** ({nombre}) — '
                       + ' · '.join(f"{k.replace('_', ' ')}: {v}" for k, v in resumen.items()))
        def bloque_carga(tipo, abierto=False):
            with st.expander(f'**{tipo.titulo}** · {tipo.modo}', expanded=abierto):
                st.caption(tipo.ayuda)
                if getattr(tipo, 'formatos', None):
                    st.markdown('\n'.join(f'- **{t}:** {d}' for t, d in tipo.formatos))
                else:
                    st.dataframe(pd.DataFrame([dict(Columna=c.campo.upper() if tipo.id == 'viajes' else c.campo,
                                                    Obligatoria='sí' if c.requerido else '', Ejemplo=c.ejemplo,
                                                    Nota=c.descripcion) for c in tipo.columnas]),
                                 hide_index=True, use_container_width=True)
                st.download_button('Descargar plantilla', I.plantilla(tipo.id), f'plantilla_{tipo.id}.csv',
                                   'text/csv', key=f'pl_{tipo.id}')
                opciones = {}
                if tipo.id == 'movimiento':
                    opciones['fecha'] = st.date_input('Fecha de los datos', value=date.fromisoformat(dia),
                                                      format='DD/MM/YYYY', key='fecha_movimiento').isoformat()
                archivo = st.file_uploader('Archivo', type=['csv', 'txt', 'xlsx'], key=f'up_{tipo.id}')
                clave_rev = f'rev_{tipo.id}'
                if archivo is None:
                    st.session_state.pop(clave_rev, None)
                    return
                contenido = archivo.getvalue()
                firma = (archivo.name, len(contenido), json.dumps(opciones))
                if st.button('Revisar archivo', key=f'rv_{tipo.id}'):
                    st.session_state[clave_rev] = (*firma, I.revisar(MOTOR, tipo.id, contenido, archivo.name, opciones))
                guardado = st.session_state.get(clave_rev)
                if not guardado or guardado[:3] != firma:
                    return
                rev = guardado[3]
                if not rev.ok:
                    if rev.faltan_columnas:
                        st.error(f"Faltan columnas: {', '.join(rev.faltan_columnas)}. "
                                 f"Encontradas: {', '.join(rev.columnas_encontradas) or '(ninguna)'}")
                    for _, m in rev.errores:
                        st.error(m)
                    return
                st.markdown(f'**Revisión: {rev.filas} filas leídas** — :orange[aún no se guarda nada, '
                            f'presione **Confirmar carga** abajo]')
                st.dataframe(pd.DataFrame([rev.resumen]).rename(columns=lambda c: c.replace('_', ' ')),
                             hide_index=True, use_container_width=True)
                if rev.errores:
                    st.warning(f'{len(rev.errores)} filas con problemas (se omitirán):')
                    st.dataframe(pd.DataFrame(rev.errores, columns=['Fila', 'Problema']), hide_index=True,
                                 use_container_width=True, height=min(300, 38 + 35 * len(rev.errores)))
                for fila, m in rev.avisos:
                    st.info((f'Fila {fila}: ' if fila and fila < 100000 else '') + m)
                if rev.hay_cambios and st.button('Confirmar carga', type='primary', key=f'ok_{tipo.id}'):
                    I.aplicar(MOTOR, tipo.id, rev, archivo.name)
                    st.session_state.pop(clave_rev, None)
                    st.session_state.ultima_carga = (tipo.titulo, archivo.name, rev.resumen)
                    st.rerun()
                elif not rev.hay_cambios:
                    st.caption('No hay cambios para guardar: los datos ya estaban cargados.')

        for i, t in enumerate(I.CARGAS_PRINCIPALES):
            bloque_carga(I.TIPOS[t], abierto=i == 0)
        st.markdown('###### Otras cargas (uso ocasional)')
        for t in I.CARGAS_OTRAS:
            bloque_carga(I.TIPOS[t])

        st.subheader('¿De dónde vienen los m³ retirados?')
        origen = I.origen_retirado(MOTOR, dia)
        if origen.empty:
            st.caption('No hay m³ retirados cargados.')
        else:
            st.caption(f"Total al {fecha_cl(dia)}: **{num(origen['m3'].sum())} m³**. Los tickets se suman al avance "
                       'informado solo si son posteriores a la fecha de la planilla.')
            st.dataframe(origen, hide_index=True, use_container_width=True,
                         column_config={'m3': st.column_config.NumberColumn('m³', format='%.0f')})
        with st.popover('🧹 Borrar todo el movimiento de tierra cargado'):
            st.markdown('Deja **en cero** los volúmenes proyectados y los avances (planillas y ajustes). '
                        'No borra tickets, entregas, carta Gantt ni notas. Después suba de nuevo la planilla.')
            if st.button('Sí, borrar el movimiento de tierra', type='primary', key='limpiar_mov'):
                I.limpiar_movimiento(MOTOR)
                st.rerun()
        with st.popover('⚠️ Borrar TODA la información y partir de cero'):
            st.markdown('Borra **todo**: volúmenes, avances, tickets, entregas, carta Gantt, hitos, notas e historial. '
                        'Quedan solo los sitios y terrazas del plano. Después hay que subir de nuevo los archivos.')
            confirma = st.text_input('Escriba BORRAR para confirmar', key='conf_reinicio')
            if st.button('Borrar todo', type='primary', key='reiniciar', disabled=confirma.strip().upper() != 'BORRAR'):
                T.reiniciar(MOTOR)
                st.session_state.pop('ultima_carga', None)
                st.rerun()

        st.subheader('Historial de cargas')
        cargas = C.leer(MOTOR, 'carga').sort_values('id', ascending=False)
        if cargas.empty:
            st.caption('Todavía no se han cargado archivos.')
        for c in cargas.head(50).itertuples():
            a, b = st.columns([5, 1])
            res = json.loads(c.resumen or '{}')
            a.markdown(f"`{c.creado_en}` · **{c.tipo}** · {c.archivo}  \n"
                       + ' · '.join(f"{k.replace('_', ' ')}: {v}" for k, v in res.items()))
            if c.tipo in I.DESHACIBLES and b.button('Deshacer', key=f'des_{c.id}'):
                I.deshacer(MOTOR, c.id)
                st.rerun()

    with tabs['Editar estados']:
        st.markdown('Edite directamente en la tabla y presione **Guardar cambios**.')
        filtro = st.multiselect('Sitios', terrenos['nombre'].tolist(), placeholder='Todos')
        ids = terrenos.loc[terrenos['nombre'].isin(filtro), 'id'] if filtro else terrenos['id']
        est_z = ['sin_intervenir', 'en_proceso', 'entregado']
        est_a = ['sin_intervenir', 'en_proceso', 'terminado']

        st.markdown('**Entregas de terrazas**')
        z = zonas[zonas['terreno_id'].isin(ids)][['id', 'nombre', 'zona', 'estado', 'fecha_entrega']].copy()
        z['zona'] = z['zona'].map(ZONAS)
        z['fecha_entrega'] = pd.to_datetime(z['fecha_entrega'])
        ze = st.data_editor(z, hide_index=True, use_container_width=True, disabled=['id', 'nombre', 'zona'], key='ed_z',
                            column_config={'id': None, 'nombre': 'Sitio', 'zona': 'Terraza',
                                           'estado': st.column_config.SelectboxColumn('Estado', options=est_z, required=True),
                                           'fecha_entrega': st.column_config.DateColumn('Fecha entrega', format='DD/MM/YYYY')})
        st.markdown('**Escarpe y corte**')
        a = acts[acts['terreno_id'].isin(ids)].merge(terrenos[['id', 'nombre']].rename(columns={'id': 'terreno_id'}))
        a = a[['id', 'nombre', 'tipo', 'volumen_proyectado_m3', 'estado', 'retirado_m3']]
        ae = st.data_editor(a, hide_index=True, use_container_width=True, key='ed_a',
                            disabled=['id', 'nombre', 'tipo', 'retirado_m3'],
                            column_config={'id': None, 'nombre': 'Sitio', 'tipo': 'Actividad',
                                           'volumen_proyectado_m3': st.column_config.NumberColumn('Proyectado m³', min_value=0, format='%.1f'),
                                           'estado': st.column_config.SelectboxColumn('Estado', options=est_a, required=True),
                                           'retirado_m3': st.column_config.NumberColumn('Retirado m³', format='%.1f')})
        if st.button('Guardar cambios', type='primary'):
            n = 0
            with MOTOR.begin() as con:
                for antes, despues in zip(z.itertuples(), ze.itertuples()):
                    f = despues.fecha_entrega.date().isoformat() if pd.notna(despues.fecha_entrega) else None
                    if despues.estado == 'entregado' and not f:
                        f = C.hoy_chile()
                    if despues.estado != 'entregado':
                        f = None
                    fa = antes.fecha_entrega.date().isoformat() if pd.notna(antes.fecha_entrega) else None
                    if (despues.estado, f) != (antes.estado, fa):
                        con.execute(update(T.zona).where(T.zona.c.id == antes.id).values(estado=despues.estado, fecha_entrega=f))
                        if despues.estado != antes.estado:
                            con.execute(insert(T.historial).values(tabla='zona', ref_id=antes.id, estado=despues.estado,
                                                                   fecha=f or C.hoy_chile()))
                        n += 1
                for antes, despues in zip(a.itertuples(), ae.itertuples()):
                    if (despues.estado, despues.volumen_proyectado_m3) != (antes.estado, antes.volumen_proyectado_m3):
                        con.execute(update(T.actividad).where(T.actividad.c.id == antes.id)
                                    .values(estado=despues.estado, volumen_proyectado_m3=float(despues.volumen_proyectado_m3 or 0)))
                        if despues.estado != antes.estado:
                            con.execute(insert(T.historial).values(tabla='actividad', ref_id=antes.id,
                                                                   estado=despues.estado, fecha=C.hoy_chile()))
                        n += 1
            st.toast(f'{n} cambios guardados', icon='✅')
            st.rerun()
