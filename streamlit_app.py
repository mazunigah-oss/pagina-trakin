"""Avance de movimiento de tierra — Loma La Cruz (48 sitios, Etapas 1 y 2).

Visita: acceso libre, solo lectura. Administrador: contraseña (secreto ADMIN_PASSWORD).
"""
import hmac
import json
import os
from datetime import date

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
def motor():
    return T.crear_motor(secreto('DATABASE_URL'))


@st.cache_resource
def geometria():
    return T.cargar_geometria()


MOTOR = motor()
GEO = geometria()
PERSISTENTE = bool(secreto('DATABASE_URL'))


def num(x, d=0):
    if x is None or x != x:
        return '—'
    return f'{x:,.{d}f}'.replace(',', '_').replace('.', ',').replace('_', '.')


def fecha_cl(iso):
    return '—' if not iso or iso != iso else '-'.join(reversed(str(iso)[:10].split('-')))


def pastilla(estado):
    return f':{ {"entregado": "green", "terminado": "green", "al_dia": "green", "en_proceso": "orange", "atrasado": "red", "adelantado": "blue"}.get(estado, "gray")}-badge[{NOMBRES.get(estado, "Sin programa")}]'


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
acts = C.volumenes(C.leer(MOTOR, 'actividad'), viajes, ajustes, hasta=dia)
viajes_hasta = viajes[viajes['fecha'] <= dia]
prog_t = C.programa_terrenos(terrenos, acts, gantt, dia)
prog_z = C.programa_zonas(zonas, gantt, dia)

st.title('Avance movimiento de tierra')
st.caption(f'Loma La Cruz · 48 sitios · Etapas 1 y 2 · datos al {fecha_cl(dia)}')

pestanas = ['Resumen', 'Curva de avance', 'Entregas', 'Programa', 'Movimiento de tierra', 'Tickets']
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
    r = C.resumen_dia(viajes, terrenos, dia)
    total_proy = acts['volumen_proyectado_m3'].sum()
    total_ret = acts['retirado_m3'].sum()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric('Camiones', num(r['camiones']), help='Patentes distintas con tickets válidos en el día')
    c2.metric('Viajes', num(r['viajes']), help='Tickets válidos menos anulados')
    c3.metric('m³ retirados', num(r['m3'], 1))
    c4.metric('Acumulado obra', f'{num(total_ret)} m³',
              f'{num(100 * total_ret / total_proy, 1)} % de {num(total_proy)} m³' if total_proy else 'sin proyectado',
              delta_color='off')
    if r['anulaciones']:
        st.caption(f'{r["anulaciones"]} ticket(s) anulados en el día (ya descontados).')
    izq, der = st.columns(2)
    with izq:
        st.markdown(f'**Origen de la tierra — {fecha_cl(dia)}**')
        if r['por_origen'].empty:
            ultimo = viajes['fecha'].max() if not viajes.empty else None
            st.info(f'Sin tickets el {fecha_cl(dia)}.' + (f' Último día con tickets: {fecha_cl(ultimo)}.' if ultimo else ''))
        else:
            st.dataframe(r['por_origen'].rename(columns={'origen': 'Origen', 'viajes': 'Viajes', 'm3': 'm³'}),
                         hide_index=True, use_container_width=True,
                         column_config={'m³': st.column_config.NumberColumn(format='%.1f')})
    with der:
        st.markdown('**m³ netos por día (últimos 30 días)**')
        serie = C.serie_diaria(viajes, dia)
        fig = px.bar(serie, x='fecha', y='m3', labels={'fecha': '', 'm3': 'm³'}, color_discrete_sequence=['#2f6d4f'])
        fig.update_layout(height=280, margin=dict(l=0, r=0, t=10, b=0), bargap=0.15)
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

    st.markdown('**Entregas de terrazas**')
    cont = prog_z['estado'].value_counts()
    e1, e2, e3, e4 = st.columns(4)
    e1.metric('Entregadas', num(cont.get('entregado', 0)), f'de {len(prog_z)}', delta_color='off')
    e2.metric('En proceso', num(cont.get('en_proceso', 0)))
    e3.metric('Sin intervenir', num(cont.get('sin_intervenir', 0)))
    e4.metric('Sitios atrasados (programa)', num((prog_t['comparacion'] == 'atrasado').sum()))

# ---------------------------------------------------------------- Curva de avance

with tabs['Curva de avance']:
    total_proy = float(acts['volumen_proyectado_m3'].sum())
    prog = C.curva_programada(gantt, acts)
    real = C.curva_real(viajes, ajustes, total_proy, dia)
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
              (f"{p['dias_desfase']} días de atraso" if p['dias_desfase'] > 0 else
               f"{-p['dias_desfase']} días antes" if p['dias_desfase'] < 0 else 'a tiempo'),
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
                texto += (f" → hay que acelerar **{num(100 * (veces - 1))} %**" if veces > 1 else
                          f" → alcanza con el **{num(100 * veces)} %** del ritmo actual")
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
    fig.add_hline(y=100, line_color='#c9cfca', line_width=1)
    fig.update_yaxes(title='% de avance', range=[0, 110], ticksuffix=' %')
    fig.update_xaxes(title='', tickformat='%d/%m/%y')
    fig.update_layout(height=460, margin=dict(l=0, r=0, t=30, b=0), hovermode='x unified',
                      legend=dict(orientation='h', yanchor='bottom', y=1.02, x=0))
    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
    st.caption('Programada: el volumen proyectado de cada sitio repartido entre el inicio y el término de su tarea en '
               'la carta Gantt. Real: m³ netos de tickets + ajustes sobre el volumen proyectado total. Proyección: '
               'línea recta desde hoy con el ritmo promedio del período elegido.')

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
    modo = st.segmented_control('Mostrar', ['Cómo deberíamos ir', 'Real vs. programado'], default='Cómo deberíamos ir')
    pt = prog_t.set_index('terreno_id')
    mapa, panel = st.columns([3, 1])
    with panel:
        sel = elegir_sitio('sel_programa')
    if modo == 'Real vs. programado':
        color = lambda z: COLORES[pt.loc[z['terreno_id'], 'comparacion']]
        ley = [(COLORES[k], NOMBRES[k]) for k in ('atrasado', 'al_dia', 'adelantado', None)]
    else:
        color = lambda z: COLORES[pt.loc[z['terreno_id'], 'programado']]
        ley = [(COLORES[k], NOMBRES[k]) for k in ('sin_intervenir', 'en_proceso', 'terminado', None)]

    def hover_prog(z):
        p = pt.loc[z['terreno_id']]
        if p['programado'] is None:
            return f"<b>{z['nombre']}</b><br>Sin programa"
        return (f"<b>{z['nombre']}</b><br>Programa: {fecha_cl(p['inicio'])} → {fecha_cl(p['termino'])}"
                f"<br>Debería estar: {NOMBRES[p['programado']]} ({num(100 * p['avance_programado'])} %)"
                f"<br>Real: {NOMBRES[p['real']]}" + (f" ({num(100 * p['avance_real'])} % m³)" if p['avance_real'] == p['avance_real'] and p['avance_real'] is not None else ''))

    with mapa:
        st.plotly_chart(figura(GEO, zonas, color, hover_prog, ley, sel), use_container_width=True,
                        config={'displayModeBar': False, 'scrollZoom': True})
    with panel:
        if sel:
            encabezado_sitio(sel)
            p = pt.loc[sel]
            if p['programado'] is None:
                st.caption('Sin tarea en el programa.')
            else:
                st.markdown(f"Programa: **{fecha_cl(p['inicio'])} → {fecha_cl(p['termino'])}**  \n"
                            f"Debería estar {pastilla(p['programado'])} ({num(100 * p['avance_programado'])} % del plazo)  \n"
                            f"Real {pastilla(p['real'])}  \n{pastilla(p['comparacion'])}")
        atrasados = prog_t[prog_t['comparacion'] == 'atrasado']
        if not atrasados.empty:
            st.markdown('**Sitios atrasados**')
            st.dataframe(atrasados[['codigo', 'termino', 'real']].assign(
                termino=atrasados['termino'].map(fecha_cl), real=atrasados['real'].map(NOMBRES))
                .rename(columns={'codigo': 'Sitio', 'termino': 'Debía terminar', 'real': 'Real'}),
                hide_index=True, use_container_width=True)
    if not gantt.empty:
        with st.expander('Ver carta Gantt'):
            g = gantt.merge(terrenos[['id', 'codigo']].rename(columns={'id': 'terreno_id'}), on='terreno_id')
            g = g.assign(Inicio=pd.to_datetime(g['inicio']), Fin=pd.to_datetime(g['termino']) + pd.Timedelta(days=1),
                         Sitio=g['codigo'], Actividad=g['actividad'].fillna('movimiento de tierra'))
            fig = px.timeline(g.sort_values('inicio'), x_start='Inicio', x_end='Fin', y='Sitio', color='Actividad',
                              color_discrete_sequence=['#2f6d4f', '#e9a23b', '#3b7dd8'])
            fig.add_vline(x=pd.Timestamp(dia), line_color='#d64545', line_dash='dash')
            fig.update_yaxes(autorange='reversed', title='')
            fig.update_layout(height=max(300, 16 * g['Sitio'].nunique()), margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------------- Movimiento de tierra

with tabs['Movimiento de tierra']:
    avance = acts.groupby('terreno_id')[['volumen_proyectado_m3', 'retirado_m3']].sum()
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
            for a in acts[acts['terreno_id'] == sel].itertuples():
                st.markdown(f"**{'Escarpe' if a.tipo == 'escarpe' else 'Corte'}** {pastilla(a.estado)}")
                st.dataframe(pd.DataFrame({'m³': [a.volumen_proyectado_m3, a.directo_m3, a.prorrateo_m3, a.ajustes_m3, a.retirado_m3]},
                                          index=['Proyectado', 'Tickets del sitio', 'Prorrateo General', 'Ajustes', 'Retirado']),
                             use_container_width=True, column_config={'m³': st.column_config.NumberColumn(format='%.1f')})
                if a.avance == a.avance and a.avance is not None:
                    st.progress(min(1.0, float(a.avance)), text=f'{num(100 * a.avance, 1)} %')
    st.caption('m³ retirados = tickets del sitio + prorrateo de los tickets sin sitio (General, repartidos entre las '
               'actividades en proceso según su volumen proyectado) + ajustes manuales. Las anulaciones restan.')

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
        st.markdown('Suba archivos **CSV** (separados por `;` o `,`) o **Excel**. Primero se **revisan** y se muestra '
                    'qué va a cambiar; los datos se guardan solo al **confirmar**.')
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
                st.markdown(f'**Revisión: {rev.filas} filas leídas** (aún no se guarda nada)')
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
                    st.toast('Carga guardada', icon='✅')
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
