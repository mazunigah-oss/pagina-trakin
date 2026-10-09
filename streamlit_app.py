"""Avance de movimiento de tierra — Loma La Cruz (48 sitios, Etapas 1 y 2).

Visita: acceso libre, solo lectura. Administrador: contraseña (secreto ADMIN_PASSWORD).
"""
import hmac
import json
import os
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from sqlalchemy import insert, select, update

from obra import calculos as C
from obra import db as T
from obra import importar as I
from obra.mapa import COLORES, ESCALA, NOMBRES, ZONAS, color_avance, figura

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


NOMBRE_ACT = {'escarpe': 'Escarpe', 'corte': 'Corte / excavación',
              'adicional': 'Proforma · adicional a botadero (no planificado)'}
COLOR_AVANCE = {'terminado': '#2f9e6b', 'en_proceso': '#f2c230', 'sin_intervenir': '#d5dbd6'}
COLOR_COMPARA = {'atrasado': '#d64545', 'al_dia': '#2f9e6b', 'adelantado': '#3b7dd8', None: '#f1f3f0'}
COLOR_GANTT = {'terminado': '#2f9e6b', 'en_proceso': '#f2c230', 'sin_intervenir': '#c9d1cb', None: '#f1f3f0'}
NOMBRE_GANTT = {'terminado': 'Debería estar listo', 'en_proceso': 'Debería estar en trabajos',
                'sin_intervenir': 'Aún no le toca'}


def pastilla(estado):
    return f':{ {"entregado": "green", "terminado": "green", "al_dia": "green", "en_proceso": "orange", "atrasado": "red", "adelantado": "blue"}.get(estado, "gray")}-badge[{NOMBRES.get(estado, "Sin programa")}]'


def leyenda_abajo(items):
    """Leyenda de colores en lenguaje simple, debajo del mapa."""
    st.markdown('<div style="display:flex;flex-direction:column;gap:6px;font-size:0.92rem;margin-top:-6px">' + ''.join(
        f'<div><span style="display:inline-block;width:14px;height:14px;border-radius:3px;background:{c};'
        f'border:1px solid #c9cfca;vertical-align:-2px;margin-right:8px"></span><b>{t}</b>'
        + (f' — {d}' if d else '') + '</div>' for c, t, d in items) + '</div>', unsafe_allow_html=True)


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
rellenos = C.leer(MOTOR, 'relleno')
acts = C.volumenes(C.leer(MOTOR, 'actividad'), viajes, ajustes, hasta=dia)
viajes_hasta = viajes[viajes['fecha'] <= dia]
prog_t = C.programa_terrenos(terrenos, acts, gantt, dia)
prog_z = C.programa_zonas(zonas, gantt, dia)

st.title('Avance movimiento de tierra')
st.caption(f'Loma La Cruz · 48 sitios · Etapas 1 y 2 · datos al {fecha_cl(dia)}')

pestanas = ['Resumen', 'Curva de avance', 'Entregas', 'Programa', 'Movimiento de tierra', 'Rellenos', 'Tickets']
if ADMIN:
    pestanas += ['Cargar datos', 'Editar estados']
tabs = dict(zip(pestanas, st.tabs(pestanas)))


def elegir_sitio(key):
    opciones = ['—'] + [f'{r.nombre}' for r in terrenos.itertuples()]
    eleccion = st.selectbox('Ver detalle de', opciones, key=key)
    return None if eleccion == '—' else int(terrenos.loc[terrenos['nombre'] == eleccion, 'id'].iloc[0])


def encabezado_sitio(tid):
    t = terrenos.set_index('id').loc[tid]
    extra = ' · '.join(x for x in [f'Modelo {t.modelo}' if t.modelo else '', f'Etapa {int(t.etapa)}' if t.etapa == t.etapa and t.etapa else '',
                                   f'{num(t.area_m2)} m²'] if x)
    st.subheader(t.nombre)
    st.caption(extra)


# ---------------------------------------------------------------- Resumen

with tabs['Resumen']:
    plan = C.planificadas(acts)
    total_proy = float(plan['volumen_proyectado_m3'].sum())
    total_ret = float(plan['retirado_m3'].sum())
    debe = float(prog_t['programado_m3'].sum())
    dif = total_ret - debe
    proforma = acts[acts['tipo'] == 'adicional']
    c1, c2, c3, c4 = st.columns(4)
    c1.metric('Avance movimiento de tierra', f'{num(100 * total_ret / total_proy, 1)} %' if total_proy else '—',
              help='m³ retirados / m³ proyectados (esponjados) de todos los sitios. No incluye la proforma.')
    c2.metric('m³ retirados', f'{num(total_ret)} m³', f'de {num(total_proy)} m³ proyectados', delta_color='off')
    c3.metric('Deberían ir retirados', f'{num(debe)} m³', help='Según la carta Gantt a la fecha: cada sitio en '
              'proporción a los días transcurridos de su programa. Sitios sin programa: se toma lo real.')
    c4.metric('Diferencia', f"{'+' if dif >= 0 else '−'}{num(abs(dif))} m³",
              'adelantados' if dif >= 0 else 'atrasados', delta_color='normal' if dif >= 0 else 'inverse')

    pt = prog_t.set_index('terreno_id')
    mapa, lista = st.columns([1, 1])
    with mapa:
        st.markdown('**Estado de los sitios**')

        def hover_inicio(z):
            f = pt.loc[z['terreno_id']]
            txt = f"<b>{z['nombre']}</b><br>{NOMBRES[f['real']]}"
            if f['proyectado_m3'] > 0:
                txt += (f"<br>Retirado: {num(f['retirado_m3'])} de {num(f['proyectado_m3'])} m³ "
                        f"({num(100 * f['avance_real'])} %)")
            if f['con_programa']:
                txt += (f"<br>Debería ir: {num(f['programado_m3'])} m³ "
                        f"({'+' if f['diferencia_m3'] >= 0 else '−'}{num(abs(f['diferencia_m3']))} m³)")
            return txt

        st.plotly_chart(figura(GEO, zonas, lambda z: COLOR_AVANCE[pt.loc[z['terreno_id'], 'real']], hover_inicio, [],
                               alto=560),
                        use_container_width=True, config={'displayModeBar': False, 'scrollZoom': True})
        leyenda_abajo([(COLOR_AVANCE['terminado'], 'Listo', 'movimiento de tierra terminado'),
                       (COLOR_AVANCE['en_proceso'], 'En trabajos', 'con avance, aún no termina'),
                       (COLOR_AVANCE['sin_intervenir'], 'Sin iniciar', '')])
    with lista:
        cont = prog_t['real'].value_counts()
        k1, k2, k3 = st.columns(3)
        k1.metric('Listos', num(cont.get('terminado', 0)))
        k2.metric('En trabajos', num(cont.get('en_proceso', 0)))
        k3.metric('Sin iniciar', num(cont.get('sin_intervenir', 0)))
        trabajo = prog_t[prog_t['real'] == 'en_proceso'].sort_values('codigo')
        if not trabajo.empty:
            st.markdown('**Sitios en trabajos**')
            st.dataframe(pd.DataFrame({
                'Sitio': trabajo['codigo'].str.replace('S-0', 'S-').str.replace('S-', ''),
                'Avance': 100 * trabajo['avance_real'].astype(float),
                'Retirado': trabajo['retirado_m3'],
                'Debería': trabajo['programado_m3'].where(trabajo['con_programa']),
                'Dif.': trabajo['diferencia_m3'].where(trabajo['con_programa'])}),
                hide_index=True, use_container_width=True, height=min(460, 38 + 35 * len(trabajo)),
                column_config={'Sitio': st.column_config.TextColumn('Sitio', width='small'),
                               'Avance': st.column_config.ProgressColumn('Avance', format='%.0f %%', min_value=0,
                                                                         max_value=100, width='small'),
                               'Retirado': st.column_config.NumberColumn('Retirado m³', format='%.0f'),
                               'Debería': st.column_config.NumberColumn('Debería m³', format='%.0f',
                                                                        help='Según la carta Gantt a la fecha'),
                               'Dif.': st.column_config.NumberColumn('Dif. m³', format='%+.0f')})
        if proforma['volumen_proyectado_m3'].sum() > 0:
            st.caption(f"Proforma (volumen adicional a botadero, no planificado): "
                       f"{num(proforma['retirado_m3'].sum())} de {num(proforma['volumen_proyectado_m3'].sum())} m³. "
                       'No se incluye en el avance.')

    st.divider()
    ayer = (date.fromisoformat(dia) - timedelta(days=1)).isoformat()
    r, ra = C.resumen_dia(viajes, terrenos, dia), C.resumen_dia(viajes, terrenos, ayer)
    st.markdown(f'**Camiones — {fecha_cl(dia)} comparado con {fecha_cl(ayer)}**')

    def delta(hoy_v, ayer_v, d=0):
        x = hoy_v - ayer_v
        return f"{'+' if x >= 0 else '−'}{num(abs(x), d)} vs ayer"

    t1, t2, t3 = st.columns(3)
    t1.metric('Camiones', num(r['camiones']), delta(r['camiones'], ra['camiones']),
              help='Patentes distintas con tickets válidos en el día')
    t2.metric('Viajes', num(r['viajes']), delta(r['viajes'], ra['viajes']), help='Tickets válidos menos anulados')
    t3.metric('m³ trasladados', num(r['m3'], 1), delta(r['m3'], ra['m3'], 1))
    if r['anulaciones']:
        st.caption(f'{r["anulaciones"]} ticket(s) anulados en el día (ya descontados).')
    if r['por_origen'].empty and ra['por_origen'].empty:
        ultimo = viajes['fecha'].max() if not viajes.empty else None
        st.info(f'Sin tickets de camiones el {fecha_cl(dia)} ni el {fecha_cl(ayer)}.'
                + (f' Último día con tickets: {fecha_cl(ultimo)}.' if ultimo else ' Aún no se han cargado tickets.'))
    else:
        origen = r['por_origen'].rename(columns={'viajes': 'Viajes hoy', 'm3': 'm³ hoy'}).merge(
            ra['por_origen'].rename(columns={'viajes': 'Viajes ayer', 'm3': 'm³ ayer'}), on='origen', how='outer').fillna(0)
        izq, der = st.columns(2)
        with izq:
            st.markdown('**Origen de la tierra**')
            st.dataframe(origen.rename(columns={'origen': 'Origen'}).sort_values('m³ hoy', ascending=False),
                         hide_index=True, use_container_width=True,
                         column_config={c: st.column_config.NumberColumn(format='%.1f') for c in ('m³ hoy', 'm³ ayer')})
        with der:
            st.markdown('**m³ por día (últimos 30 días)**')
            serie = C.serie_diaria(viajes, dia)
            fig = px.bar(serie, x='fecha', y='m3', labels={'fecha': '', 'm3': 'm³'}, color_discrete_sequence=['#2f6d4f'])
            fig.update_layout(height=260, margin=dict(l=0, r=0, t=10, b=0), bargap=0.15)
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

# ---------------------------------------------------------------- Curva de avance

with tabs['Curva de avance']:
    sitios_prog = sorted(gantt.loc[gantt['zona'].isna(), 'terreno_id'].unique()) if not gantt.empty else []
    opciones = ([f'Sitios con programa ({len(sitios_prog)})'] if sitios_prog else []) + ['Toda la obra']
    alcance = st.segmented_control('Alcance', opciones, default=opciones[0],
                                   help='La curva programada solo existe para los sitios que están en la carta Gantt. '
                                        '"Sitios con programa" compara real y programado sobre los mismos sitios. '
                                        '"Toda la obra" usa el volumen de todos los sitios (incluye los tickets sin sitio).')
    ids_alcance = sitios_prog if alcance and alcance.startswith('Sitios') else None
    acts_plan = C.planificadas(acts)  # la proforma no entra a la curva
    acts_alc = acts_plan if ids_alcance is None else acts_plan[acts_plan['terreno_id'].isin(ids_alcance)]
    total_proy = float(acts_alc['volumen_proyectado_m3'].sum())
    prog = C.curva_programada(gantt, acts)
    real = C.curva_real(viajes, ajustes, total_proy, dia, inicio=None if gantt.empty else gantt['inicio'].min(),
                        actividades=acts, terreno_ids=ids_alcance)
    if ids_alcance is None and sitios_prog:
        prog = prog.assign(pct=prog['pct'] * float(acts_plan[acts_plan['terreno_id'].isin(sitios_prog)]['volumen_proyectado_m3'].sum())
                           / total_proy) if total_proy > 0 else prog
    if total_proy <= 0:
        st.info('Para calcular el % de avance hay que cargar los volúmenes proyectados (Cargar datos → Volúmenes '
                'proyectados). Mientras tanto la curva programada se calcula con el mismo peso para cada sitio.')
    ventana = st.segmented_control('Ritmo para proyectar', ['Últimos 7 días', 'Últimos 14 días', 'Últimos 30 días'],
                                   default='Últimos 14 días', help='La proyección supone que el avance sigue al '
                                   'ritmo promedio de este período (días corridos, incluye fines de semana).')
    ventana_dias = {'Últimos 7 días': 7, 'Últimos 14 días': 14, 'Últimos 30 días': 30}.get(ventana, 14)
    p = C.proyeccion(real, prog, dia, ventana_dias)

    def fecha_ts(ts):
        return '—' if ts is None else ts.strftime('%d-%m-%Y')

    c1, c2, c3, c4 = st.columns(4)
    dif = (p['avance_real'] - p['avance_programado']) if None not in (p['avance_real'], p['avance_programado']) else None
    c1.metric('Avance real', f"{num(p['avance_real'], 1)} %",
              None if dif is None else f'{num(dif, 1)} pp vs programado', delta_color='normal')
    c2.metric('Avance programado a la fecha', f"{num(p['avance_programado'], 1)} %")
    c3.metric('Término estimado', fecha_ts(p['fecha_termino_estimada']),
              None if p['dias_desfase'] is None else
              (f"{p['dias_desfase']} día{'s' if p['dias_desfase'] != 1 else ''} de atraso" if p['dias_desfase'] > 0 else
               f"{-p['dias_desfase']} día{'s' if p['dias_desfase'] != -1 else ''} antes" if p['dias_desfase'] < 0 else 'a tiempo'),
              delta_color='inverse' if (p['dias_desfase'] or 0) > 0 else 'normal',
              help='Fecha en que se llegaría al 100 % si se mantiene el ritmo actual.')
    c4.metric(f"Avance al {fecha_ts(p['fecha_termino_programada'])}", f"{num(p['pct_a_termino_programado'], 1)} %",
              help='% que se alcanzaría en la fecha de término programada si se mantiene el ritmo actual.')

    if p['ritmo'] is not None:
        m3_dia = p['ritmo'] * total_proy / 100
        texto = f"**Ritmo actual:** {num(p['ritmo'], 2)} % por día ({num(m3_dia, 0)} m³/día corrido)"
        if p['ritmo_necesario'] is not None:
            nec_m3 = p['ritmo_necesario'] * total_proy / 100
            texto += (f" · **Ritmo necesario para terminar a tiempo:** {num(p['ritmo_necesario'], 2)} % por día "
                      f"({num(nec_m3, 0)} m³/día)")
            if p['ritmo'] > 0:
                veces = p['ritmo_necesario'] / p['ritmo']
                texto += (f" → hay que acelerar **{num(100 * (veces - 1))} %**" if veces > 1.02 else
                          f" → alcanza con el **{num(100 * veces)} %** del ritmo actual" if veces < 0.98 else
                          ' → hay que mantener el ritmo actual, sin margen')
        st.markdown(texto)
        if p['ritmo'] <= 0 and (p['avance_real'] or 0) < 100:
            st.warning(f'No hubo avance en los últimos {ventana_dias} días: con ese ritmo la obra no termina.')

    fig = go.Figure()
    if not prog.empty:
        fig.add_trace(go.Scatter(x=prog['fecha'], y=prog['pct'], name='Programada', mode='lines',
                                 line=dict(color='#8a948e', width=2.5),
                                 hovertemplate='%{x|%d-%m-%Y}<br>Programado: %{y:.1f} %<extra></extra>'))
    if not real.empty:
        fig.add_trace(go.Scatter(x=real['fecha'], y=real['pct'], name='Real', mode='lines',
                                 line=dict(color='#2f6d4f', width=3), customdata=real['m3'],
                                 hovertemplate='%{x|%d-%m-%Y}<br>Real: %{y:.1f} % (%{customdata:,.0f} m³)<extra></extra>'))
    if not p['serie'].empty:
        fig.add_trace(go.Scatter(x=p['serie']['fecha'], y=p['serie']['pct'], name='Proyección al ritmo actual',
                                 mode='lines', line=dict(color='#e9a23b', width=3, dash='dot'),
                                 hovertemplate='%{x|%d-%m-%Y}<br>Proyectado: %{y:.1f} %<extra></extra>'))
    if p['fecha_termino_programada'] is not None and p['pct_a_termino_programado'] is not None:
        fig.add_trace(go.Scatter(x=[p['fecha_termino_programada']], y=[p['pct_a_termino_programado']], mode='markers+text',
                                 marker=dict(size=11, color='#e9a23b', line=dict(color='white', width=2)),
                                 text=[f"{num(p['pct_a_termino_programado'])} %"], textposition='middle left',
                                 name='% al término programado', hoverinfo='skip'))
    if p['fecha_termino_estimada'] is not None and (p['avance_real'] or 0) < 100:
        fig.add_trace(go.Scatter(x=[p['fecha_termino_estimada']], y=[100], mode='markers+text',
                                 marker=dict(size=11, color='#d64545', symbol='diamond', line=dict(color='white', width=2)),
                                 text=[f"100 % el {fecha_ts(p['fecha_termino_estimada'])}"], textposition='top center',
                                 name='Término estimado', hoverinfo='skip'))
    fig.add_vline(x=pd.Timestamp(dia), line_color='#1d2320', line_dash='dash', line_width=1)
    fig.add_annotation(x=pd.Timestamp(dia), y=104, text='hoy', showarrow=False, font=dict(size=11))
    for i, h in enumerate(hitos.itertuples()):
        fig.add_vline(x=pd.Timestamp(h.fecha), line_color='#3b7dd8', line_dash='dot', line_width=1)
        fig.add_annotation(x=pd.Timestamp(h.fecha), y=95 - 7 * (i % 3), text=h.nombre, showarrow=False,
                           font=dict(size=10, color='#3b7dd8'), xanchor='left', xshift=3)
    fig.add_hline(y=100, line_color='#c9cfca', line_width=1)
    fig.update_yaxes(title='% de avance', range=[0, 110], ticksuffix=' %')
    fig.update_xaxes(title='', tickformat='%d/%m/%y')
    fig.update_layout(height=460, margin=dict(l=0, r=0, t=30, b=0), hovermode='x unified',
                      legend=dict(orientation='h', yanchor='bottom', y=1.02, x=0))
    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
    if p['fecha_ultimo_dato'] is not None and p['fecha_ultimo_dato'] < pd.Timestamp(dia):
        st.caption(f"Último dato de avance: {fecha_ts(p['fecha_ultimo_dato'])}. La proyección parte desde esa fecha.")
    st.caption('Programada: el volumen proyectado de cada sitio repartido entre el inicio y el término de su tarea en '
               'la carta Gantt. Real: m³ netos de tickets + ajustes sobre el volumen proyectado total. Proyección: '
               'línea recta desde el último dato con el ritmo promedio del período elegido. Con avances informados '
               'por fecha (sin tickets), la curva real une esos puntos en línea recta desde el inicio del programa.')

# ---------------------------------------------------------------- Entregas

with tabs['Entregas']:
    mapa, panel = st.columns([3, 1])
    with panel:
        sel = elegir_sitio('sel_entregas')
    with mapa:
        st.plotly_chart(figura(
            GEO, zonas, lambda z: COLORES[z['estado']],
            lambda z: f"<b>{z['nombre']}</b> · {ZONAS[z['zona']]}<br>{NOMBRES[z['estado']]}"
                      + (f" el {fecha_cl(z['fecha_entrega'])}" if pd.notna(z['fecha_entrega']) else ''),
            [(COLORES[k], NOMBRES[k]) for k in ('sin_intervenir', 'en_proceso', 'entregado')], sel),
            use_container_width=True, config={'displayModeBar': False, 'scrollZoom': True})
    with panel:
        if sel:
            encabezado_sitio(sel)
            for z in prog_z[prog_z['terreno_id'] == sel].itertuples():
                st.markdown(f'**{ZONAS[z.zona]}** · {num(z.area_m2)} m²  \n{pastilla(z.estado)}'
                            + (f' el {fecha_cl(z.fecha_entrega)}' if z.fecha_entrega else ''))
        else:
            st.caption('Pase el cursor sobre el plano para ver cada terraza, o elija un sitio.')

# ---------------------------------------------------------------- Programa

with tabs['Programa']:
    if gantt.empty:
        st.info('Aún no se ha cargado el programa (carta Gantt). El administrador puede subirlo en "Cargar datos".')
    pt = prog_t.set_index('terreno_id')

    def hover_prog(z):
        p = pt.loc[z['terreno_id']]
        if p['programado'] is None:
            return f"<b>{z['nombre']}</b><br>Sin programa en la carta Gantt<br>Real: {NOMBRES[p['real']]}"
        return (f"<b>{z['nombre']}</b><br>Programa: {fecha_cl(p['inicio'])} → {fecha_cl(p['termino'])}"
                f"<br>Según Gantt: {NOMBRE_GANTT[p['programado']]}<br>Real: {NOMBRES[p['real']]}"
                + (f" ({num(100 * p['avance_real'])} %)" if p['avance_real'] == p['avance_real'] and p['avance_real'] is not None else ''))

    izq, der = st.columns(2)
    with izq:
        st.markdown(f'**¿Cómo vamos? — estado al {fecha_cl(dia)}**')
        st.plotly_chart(figura(GEO, zonas, lambda z: COLOR_COMPARA[pt.loc[z['terreno_id'], 'comparacion']], hover_prog, [],
                               alto=560), use_container_width=True, config={'displayModeBar': False, 'scrollZoom': True},
                        key='mapa_comparacion')
        cont = prog_t['comparacion'].value_counts()
        leyenda_abajo([
            (COLOR_COMPARA['atrasado'], f"Atrasado ({cont.get('atrasado', 0)})",
             'según la carta Gantt ya debería ir más avanzado'),
            (COLOR_COMPARA['al_dia'], f"Según Gantt ({cont.get('al_dia', 0)})", 'va como estaba programado'),
            (COLOR_COMPARA['adelantado'], f"Adelantado ({cont.get('adelantado', 0)})",
             'va más avanzado de lo programado'),
            (COLOR_COMPARA[None], 'Sin programa', 'no está en la carta Gantt')])
    with der:
        st.markdown(f'**¿Cómo deberíamos ir? — según la carta Gantt al {fecha_cl(dia)}**')
        st.plotly_chart(figura(GEO, zonas, lambda z: COLOR_GANTT[pt.loc[z['terreno_id'], 'programado']], hover_prog, [],
                               alto=560), use_container_width=True, config={'displayModeBar': False, 'scrollZoom': True},
                        key='mapa_gantt')
        cont = prog_t['programado'].value_counts()
        leyenda_abajo([
            (COLOR_GANTT['terminado'], f"Debería estar listo ({cont.get('terminado', 0)})",
             'su programa ya terminó'),
            (COLOR_GANTT['en_proceso'], f"Debería estar en trabajos ({cont.get('en_proceso', 0)})",
             'hoy está dentro de su programa'),
            (COLOR_GANTT['sin_intervenir'], f"Aún no le toca ({cont.get('sin_intervenir', 0)})",
             'su programa empieza más adelante'),
            (COLOR_GANTT[None], 'Sin programa', 'no está en la carta Gantt')])

    atrasados = prog_t[prog_t['comparacion'] == 'atrasado']
    if not atrasados.empty:
        st.markdown('<br>**Sitios atrasados**', unsafe_allow_html=True)
        st.dataframe(pd.DataFrame({'Sitio': atrasados['codigo'], 'Según Gantt': atrasados['programado'].map(NOMBRE_GANTT),
                                   'Real': atrasados['real'].map(NOMBRES), 'Debía terminar': atrasados['termino'].map(fecha_cl),
                                   'Avance': 100 * atrasados['avance_real'].astype(float)}),
                     hide_index=True, use_container_width=True,
                     column_config={'Avance': st.column_config.ProgressColumn('Avance', format='%.0f %%', min_value=0,
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
            st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------------- Movimiento de tierra

with tabs['Movimiento de tierra']:
    avance = C.planificadas(acts).groupby('terreno_id')[['volumen_proyectado_m3', 'retirado_m3']].sum()
    avance['avance'] = (avance['retirado_m3'] / avance['volumen_proyectado_m3']).where(avance['volumen_proyectado_m3'] > 0)
    mapa, panel = st.columns([3, 1])
    with panel:
        sel = elegir_sitio('sel_tierra')
    with mapa:
        st.plotly_chart(figura(
            GEO, zonas, lambda z: color_avance(avance.loc[z['terreno_id'], 'avance']),
            lambda z: (f"<b>{z['nombre']}</b><br>{num(avance.loc[z['terreno_id'], 'retirado_m3'], 1)} m³ retirados"
                       + (f" de {num(avance.loc[z['terreno_id'], 'volumen_proyectado_m3'])} ({num(100 * avance.loc[z['terreno_id'], 'avance'])} %)"
                          if avance.loc[z['terreno_id'], 'volumen_proyectado_m3'] > 0 else '')),
            [(COLORES[None], 'Sin proyectado'), (ESCALA[0], '0 %'), (ESCALA[2], '40 %'), (ESCALA[4], '80 %'),
             (ESCALA[5], '100 %')], sel),
            use_container_width=True, config={'displayModeBar': False, 'scrollZoom': True})
    with panel:
        if sel:
            encabezado_sitio(sel)
            visibles = acts[(acts['terreno_id'] == sel) & ((acts['volumen_proyectado_m3'] > 0) | (acts['retirado_m3'] != 0))]
            if visibles.empty:
                st.caption('Sin volumen proyectado ni movimientos.')
            for a in visibles.itertuples():
                st.markdown(f"**{NOMBRE_ACT[a.tipo]}** {pastilla(a.estado)}")
                st.dataframe(pd.DataFrame({'m³': [a.volumen_proyectado_m3, a.directo_m3, a.prorrateo_m3, a.ajustes_m3, a.retirado_m3]},
                                          index=['Proyectado', 'Tickets del sitio', 'Prorrateo General', 'Ajustes', 'Retirado']),
                             use_container_width=True, column_config={'m³': st.column_config.NumberColumn(format='%.1f')})
                if a.avance == a.avance and a.avance is not None:
                    st.progress(min(1.0, float(a.avance)), text=f'{num(100 * a.avance, 1)} %')
    st.caption('El avance no incluye la proforma (volumen adicional a botadero no considerado en la planificación '
               'inicial), que se muestra aparte en el detalle de cada sitio.')
    st.caption('m³ retirados = tickets del sitio + prorrateo de los tickets sin sitio (General, repartidos entre las '
               'actividades en proceso según su volumen proyectado) + ajustes manuales. Las anulaciones restan.')

# ---------------------------------------------------------------- Rellenos

with tabs['Rellenos']:
    if rellenos.empty:
        st.info('Aún no hay registros de rellenos y densidades. El administrador puede cargarlos en "Cargar datos".')
    else:
        r = rellenos.copy()
        capas = ['capas_acceso', 'capas_living', 'capas_calicata']
        r['densidades'] = r[capas].fillna(0).sum(axis=1)
        suma = lambda x: x.sum(min_count=1)  # noqa: E731 - celdas vacías quedan vacías, no 0
        por_sitio = r.groupby('terreno_id').agg(corte_m3=('corte_m3', suma), relleno_m3=('relleno_m3', suma),
                                                capas_acceso=('capas_acceso', suma), capas_living=('capas_living', suma),
                                                capas_calicata=('capas_calicata', suma), densidades=('densidades', 'sum'),
                                                pendiente=('relleno_pendiente', lambda x: bool(x.max())),
                                                pend_capas=('capas_pendiente', lambda x: bool(x.max())),
                                                ok=('entrega', lambda x: x.fillna('').str.upper().eq('OK').all()))
        c1, c2, c3, c4 = st.columns(4)
        c1.metric('Corte', f"{num(r['corte_m3'].sum(), 1)} m³")
        c2.metric('Relleno compactado', f"{num(r['relleno_m3'].sum(), 1)} m³")
        c3.metric('Densidades (capas de 0,25 m)', num(r['densidades'].sum()),
                  f"acceso {num(r['capas_acceso'].sum())} · living {num(r['capas_living'].sum())} · calicata "
                  f"{num(r['capas_calicata'].sum())}", delta_color='off')
        c4.metric('Sitios entregados', f"{int(por_sitio['ok'].sum())} de {len(por_sitio)}")

        def estado_relleno(tid):
            if tid not in por_sitio.index:
                return None
            f = por_sitio.loc[tid]
            return 'entregado' if f['ok'] and not f['pendiente'] else 'en_proceso'

        def hover_relleno(z):
            if z['terreno_id'] not in por_sitio.index:
                return f"<b>{z['nombre']}</b><br>Sin registro de rellenos"
            f = por_sitio.loc[z['terreno_id']]
            return (f"<b>{z['nombre']}</b><br>Relleno: {num(f['relleno_m3'], 1)} m³" + (' (pendiente)' if f['pendiente'] else '')
                    + f"<br>Densidades: {num(f['densidades'])} (acceso {num(f['capas_acceso'])}, living "
                      f"{num(f['capas_living'])}, calicata {num(f['capas_calicata'])})"
                    + f"<br>Entrega: {'OK' if f['ok'] else 'pendiente'}")

        mapa, tabla = st.columns([3, 2])
        with mapa:
            st.plotly_chart(figura(GEO, zonas, lambda z: COLORES[estado_relleno(z['terreno_id'])], hover_relleno,
                                   [(COLORES['entregado'], 'Entregado (OK)'), (COLORES['en_proceso'], 'Con pendientes'),
                                    (COLORES[None], 'Sin registro')]),
                            use_container_width=True, config={'displayModeBar': False, 'scrollZoom': True})
        with tabla:
            nombres = terrenos.set_index('id')['nombre']
            vista = por_sitio.reset_index().assign(Sitio=lambda x: x['terreno_id'].map(nombres),
                                                   Entrega=lambda x: x['ok'].map({True: 'OK', False: 'Pendiente'}))
            numericas = ['corte_m3', 'relleno_m3', 'capas_acceso', 'capas_living', 'capas_calicata', 'densidades']
            vista[numericas] = vista[numericas].astype(float)
            st.dataframe(vista[['Sitio', 'corte_m3', 'relleno_m3', 'capas_acceso', 'capas_living', 'capas_calicata',
                                'densidades', 'Entrega']],
                         hide_index=True, use_container_width=True,
                         column_config={'corte_m3': st.column_config.NumberColumn('Corte m³', format='%.1f'),
                                        'relleno_m3': st.column_config.NumberColumn('Relleno m³', format='%.1f'),
                                        'capas_acceso': st.column_config.NumberColumn('Capas acceso', format='%d'), 'capas_living': st.column_config.NumberColumn('Capas living', format='%d'),
                                        'capas_calicata': st.column_config.NumberColumn('Capas calicata', format='%d'),
                                        'densidades': st.column_config.NumberColumn('Densidades', format='%d')})
            con_p = por_sitio.index[(por_sitio['pendiente'] | por_sitio['pend_capas']).astype(bool).to_numpy()]
            if len(con_p):
                st.caption('Relleno o capas registrados como "P" (pendiente) en: ' + ', '.join(nombres[t] for t in con_p))
        st.caption('Cada capa de ~0,25 m lleva un ensayo de densidad. Entrega OK = todos los registros del sitio con OK.')

# ---------------------------------------------------------------- Tickets

with tabs['Tickets']:
    c1, c2 = st.columns(2)
    desde = c1.date_input('Desde', value=date.fromisoformat(dia), format='DD/MM/YYYY', key='t_desde').isoformat()
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
        st.markdown('Suba archivos **CSV** (separados por `;` o `,`) o **Excel**. Pasos: elegir archivo → '
                    '**Revisar archivo** → **Confirmar carga**. Nada se guarda hasta confirmar.')
        if 'ultima_carga' in st.session_state:
            titulo, nombre, resumen = st.session_state.ultima_carga
            st.success(f'✅ Carga guardada: **{titulo}** ({nombre}) — '
                       + ' · '.join(f"{k.replace('_', ' ')}: {v}" for k, v in resumen.items()))
        for tipo in I.TIPOS.values():
            with st.expander(f'{tipo.titulo} · {tipo.modo}', expanded=tipo.id == 'viajes'):
                st.caption(tipo.ayuda)
                st.dataframe(pd.DataFrame([dict(Columna=c.campo.upper() if tipo.id == 'viajes' else c.campo,
                                                Obligatoria='sí' if c.requerido else '', Ejemplo=c.ejemplo,
                                                Nota=c.descripcion) for c in tipo.columnas]),
                             hide_index=True, use_container_width=True)
                st.download_button('Descargar plantilla', I.plantilla(tipo.id), f'plantilla_{tipo.id}.csv',
                                   'text/csv', key=f'pl_{tipo.id}')
                archivo = st.file_uploader('Archivo', type=['csv', 'txt', 'xlsx'], key=f'up_{tipo.id}')
                clave_rev = f'rev_{tipo.id}'
                if archivo is None:
                    st.session_state.pop(clave_rev, None)
                    continue
                contenido = archivo.getvalue()
                if st.button('Revisar archivo', key=f'rv_{tipo.id}'):
                    st.session_state[clave_rev] = (archivo.name, len(contenido), I.revisar(MOTOR, tipo.id, contenido, archivo.name))
                guardado = st.session_state.get(clave_rev)
                if not guardado or guardado[:2] != (archivo.name, len(contenido)):
                    continue
                rev = guardado[2]
                if not rev.ok:
                    if rev.faltan_columnas:
                        st.error(f"Faltan columnas: {', '.join(rev.faltan_columnas)}. "
                                 f"Encontradas: {', '.join(rev.columnas_encontradas) or '(ninguna)'}")
                    for _, m in rev.errores:
                        st.error(m)
                    continue
                st.markdown(f'**Revisión: {rev.filas} filas leídas** — :orange[aún no se guarda nada, '
                            f'presione **Confirmar carga** abajo]')
                st.dataframe(pd.DataFrame([rev.resumen]).rename(columns=lambda c: c.replace('_', ' ')),
                             hide_index=True, use_container_width=True)
                if rev.errores:
                    st.warning(f'{len(rev.errores)} filas con problemas (se omitirán):')
                    st.dataframe(pd.DataFrame(rev.errores, columns=['Fila', 'Problema']), hide_index=True,
                                 use_container_width=True, height=min(300, 38 + 35 * len(rev.errores)))
                for fila, m in rev.avisos:
                    st.info((f'Fila {fila}: ' if fila else '') + m)
                if rev.hay_cambios and st.button('Confirmar carga', type='primary', key=f'ok_{tipo.id}'):
                    I.aplicar(MOTOR, tipo.id, rev, archivo.name)
                    st.session_state.pop(clave_rev, None)
                    st.session_state.ultima_carga = (tipo.titulo, archivo.name, rev.resumen)
                    st.rerun()
                elif not rev.hay_cambios:
                    st.caption('No hay filas nuevas para guardar.')

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
