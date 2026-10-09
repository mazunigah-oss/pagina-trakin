"""Cálculos: volúmenes retirados, prorrateo, estado programado vs real y resumen diario."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

CHILE = ZoneInfo('America/Santiago')
RANGO = {'sin_intervenir': 0, 'en_proceso': 1, 'entregado': 2, 'terminado': 2}
# 'adicional' = proforma: volumen no considerado en la planificación inicial. Se muestra aparte y no
# entra al avance, al programa ni a las curvas.
PLANIFICADAS = ('escarpe', 'corte')


def planificadas(acts: pd.DataFrame):
    return acts[acts['tipo'].isin(PLANIFICADAS)]


def hoy_chile():
    return datetime.now(CHILE).date().isoformat()


def ahora_chile():
    return datetime.now(CHILE).strftime('%Y-%m-%d %H:%M:%S')


def leer(motor, tabla):
    with motor.connect() as con:
        return pd.read_sql_table(tabla, con)


def _repartir(volumen, candidatas: pd.DataFrame, acumulado: dict):
    if candidatas.empty or not volumen:
        return
    total = candidatas['volumen_proyectado_m3'].sum()
    for _, a in candidatas.iterrows():
        peso = a['volumen_proyectado_m3'] / total if total > 0 else 1 / len(candidatas)
        acumulado[a['id']] = acumulado.get(a['id'], 0) + volumen * peso


def volumenes(actividades: pd.DataFrame, viajes: pd.DataFrame, ajustes: pd.DataFrame, hasta: str | None = None):
    """Agrega a cada actividad: directo_m3, prorrateo_m3, ajustes_m3, retirado_m3 y avance.

    - Viaje con sitio y tipo -> a esa actividad.
    - Viaje con sitio sin tipo -> se reparte entre escarpe y corte del sitio (según proyectado).
    - Viaje sin sitio (General) -> se reparte entre las actividades en proceso según su volumen
      proyectado (si no hay en proceso, entre las no terminadas; si no, entre todas).
    Las anulaciones tienen volumen negativo y restan.
    """
    if hasta:
        viajes = viajes[viajes['fecha'] <= hasta]
        ajustes = ajustes[ajustes['fecha'] <= hasta]
    directo, prorrateo = {}, {}
    por_terreno = {k: g for k, g in actividades.groupby('terreno_id')}
    if not viajes.empty:
        g = viajes.assign(terreno_id=viajes['terreno_id'].astype('Int64'), tipo=viajes['tipo'].fillna(''))
        for (tid, tipo), m3 in g.groupby(['terreno_id', 'tipo'], dropna=False)['volumen_m3'].sum().items():
            if pd.isna(tid):
                continue
            acts = por_terreno[int(tid)]
            if tipo:
                aid = acts.loc[acts['tipo'] == tipo, 'id'].iloc[0]
                directo[aid] = directo.get(aid, 0) + m3
            else:
                _repartir(m3, planificadas(acts), directo)
        general = viajes.loc[viajes['terreno_id'].isna(), 'volumen_m3'].sum()
        plan = planificadas(actividades)
        cand = plan[plan['estado'] == 'en_proceso']
        if cand.empty:
            cand = plan[plan['estado'] != 'terminado']
        if cand.empty:
            cand = plan
        _repartir(general, cand, prorrateo)
    aj = ajustes.groupby('actividad_id')['volumen_m3'].sum().to_dict() if not ajustes.empty else {}
    out = actividades.copy()
    out['directo_m3'] = out['id'].map(directo).fillna(0.0)
    out['prorrateo_m3'] = out['id'].map(prorrateo).fillna(0.0)
    out['ajustes_m3'] = out['id'].map(aj).fillna(0.0)
    out['retirado_m3'] = out['directo_m3'] + out['prorrateo_m3'] + out['ajustes_m3']
    out['avance'] = (out['retirado_m3'] / out['volumen_proyectado_m3']).where(out['volumen_proyectado_m3'] > 0)
    return out


def estado_programado(inicio, termino, dia, final):
    if pd.isna(inicio):
        return None, None
    if dia < inicio:
        return 'sin_intervenir', 0.0
    if dia > termino:
        return final, 1.0
    d0, d1, d = (date.fromisoformat(x) for x in (inicio, termino, dia))
    total = (d1 - d0).days + 1
    return 'en_proceso', ((d - d0).days + 1) / total


def comparar(real, programado):
    if programado is None or real is None:
        return None
    d = RANGO[real] - RANGO[programado]
    return 'atrasado' if d < 0 else 'adelantado' if d > 0 else 'al_dia'


def estado_real_terreno(acts: pd.DataFrame):
    """Terminado si el administrador marcó ambas actividades como terminadas, o si ya se retiró
    todo el volumen proyectado del sitio. En proceso si hay tickets o alguna actividad iniciada."""
    acts = planificadas(acts)
    proy = acts['volumen_proyectado_m3'].sum()
    if (acts['estado'] == 'terminado').all() or (proy > 0 and acts['retirado_m3'].sum() >= proy):
        return 'terminado'
    if (acts['estado'] != 'sin_intervenir').any() or (acts['retirado_m3'] > 0).any():
        return 'en_proceso'
    return 'sin_intervenir'


def programa_terrenos(terrenos, acts, gantt, dia):
    """Por terreno: estado real del movimiento de tierra, estado y % programado, comparación y m³ que
    deberían ir retirados según el programa (sin programa: se toma lo real, sin diferencia)."""
    g = gantt[gantt['zona'].isna()] if not gantt.empty else gantt
    rango = g.groupby('terreno_id').agg(inicio=('inicio', 'min'), termino=('termino', 'max')) if not g.empty \
        else pd.DataFrame(columns=['inicio', 'termino'])
    filas = []
    for _, t in terrenos.iterrows():
        a = planificadas(acts[acts['terreno_id'] == t['id']])
        real = estado_real_terreno(a)
        ini = rango['inicio'].get(t['id']) if t['id'] in rango.index else None
        fin = rango['termino'].get(t['id']) if t['id'] in rango.index else None
        prog, pct_prog = estado_programado(ini, fin, dia, 'terminado') if ini else (None, None)
        proy, ret = float(a['volumen_proyectado_m3'].sum()), float(a['retirado_m3'].sum())
        debe = proy * pct_prog if pct_prog is not None else ret
        filas.append(dict(terreno_id=t['id'], codigo=t['codigo'], real=real, programado=prog, inicio=ini, termino=fin,
                          avance_programado=pct_prog, proyectado_m3=proy, retirado_m3=ret,
                          programado_m3=debe, diferencia_m3=ret - debe, con_programa=pct_prog is not None,
                          avance_real=ret / proy if proy > 0 else None, comparacion=comparar(real, prog)))
    return _sin_nan(pd.DataFrame(filas), ['programado', 'comparacion', 'inicio', 'termino'])


def _sin_nan(df, columnas):
    """pandas convierte None en NaN; los estados vacíos deben quedar como None."""
    for c in columnas:
        df[c] = df[c].astype(object).where(df[c].notna(), None)
    return df


def programa_zonas(zonas, gantt, dia):
    g = gantt[gantt['zona'].notna()] if not gantt.empty else gantt
    z = zonas.copy()
    prog, comp, ini, fin = [], [], [], []
    for _, r in z.iterrows():
        t = g[(g['terreno_id'] == r['terreno_id']) & (g['zona'] == r['zona'])] if not g.empty else g
        if t.empty:
            prog.append(None); comp.append(None); ini.append(None); fin.append(None)
            continue
        p, _ = estado_programado(t['inicio'].min(), t['termino'].max(), dia, 'entregado')
        prog.append(p); comp.append(comparar(r['estado'], p)); ini.append(t['inicio'].min()); fin.append(t['termino'].max())
    return _sin_nan(z.assign(programado=prog, comparacion=comp, prog_inicio=ini, prog_termino=fin),
                    ['programado', 'comparacion', 'prog_inicio', 'prog_termino', 'fecha_entrega'])


def resumen_dia(viajes: pd.DataFrame, terrenos: pd.DataFrame, dia: str):
    """Tickets del día: viajes netos (válidos - anulados), camiones, m³ netos y origen."""
    v = viajes[viajes['fecha'] == dia]
    anulados = set(v.loc[v['estado'] == 'ANULACION', 'ticket'])
    efectivos = v[(v['estado'] == 'VALIDO') & ~v['ticket'].isin(anulados)]
    nombres = terrenos.set_index('id')['nombre'].to_dict()
    origen = v.assign(origen=v['terreno_id'].map(lambda x: nombres.get(x, 'General (sin sitio)') if pd.notna(x)
                                                 else 'General (sin sitio)'))
    por_origen = (origen.groupby('origen')
                  .agg(viajes=('estado', lambda s: (s == 'VALIDO').sum() - (s == 'ANULACION').sum()),
                       m3=('volumen_m3', 'sum'))
                  .sort_values('m3', ascending=False).reset_index())
    return dict(viajes=len(efectivos), camiones=efectivos['patente'].nunique(), m3=float(v['volumen_m3'].sum()),
                anulaciones=len(anulados), por_origen=por_origen)


def serie_diaria(viajes: pd.DataFrame, dia: str, dias=30):
    fin = date.fromisoformat(dia)
    fechas = [(fin - timedelta(days=i)).isoformat() for i in range(dias - 1, -1, -1)]
    m3 = viajes.groupby('fecha')['volumen_m3'].sum() if not viajes.empty else pd.Series(dtype=float)
    return pd.DataFrame({'fecha': pd.to_datetime(fechas), 'm3': [float(m3.get(f, 0.0)) for f in fechas]})


# ---------------------------------------------------------------- curva de avance


def curva_programada(gantt: pd.DataFrame, actividades: pd.DataFrame):
    """Serie diaria del % acumulado programado.

    Cada tarea del Gantt (sin zona) reparte el volumen proyectado de su sitio (o de su actividad, si la
    indica) en partes iguales entre los días de inicio a término. Si no hay volúmenes proyectados,
    cada tarea pesa lo mismo. Devuelve DataFrame (fecha, pct) o vacío si no hay programa.
    """
    g = gantt[gantt['zona'].isna()] if not gantt.empty else gantt
    if g.empty:
        return pd.DataFrame(columns=['fecha', 'pct'])
    actividades = planificadas(actividades)
    proy = actividades.groupby(['terreno_id', 'tipo'])['volumen_proyectado_m3'].sum()
    pesos = []
    for _, t in g.iterrows():
        if t['actividad']:
            pesos.append(float(proy.get((t['terreno_id'], t['actividad']), 0.0)))
        else:
            pesos.append(float(proy.loc[t['terreno_id']].sum()) if t['terreno_id'] in proy.index.get_level_values(0) else 0.0)
    if sum(pesos) == 0:
        pesos = [1.0] * len(g)
    total = sum(pesos)
    inicio, fin = date.fromisoformat(g['inicio'].min()), date.fromisoformat(g['termino'].max())
    fechas = pd.date_range(inicio - timedelta(days=1), fin)
    diario = pd.Series(0.0, index=fechas)
    for (_, t), peso in zip(g.iterrows(), pesos):
        dias = pd.date_range(t['inicio'], t['termino'])
        diario[dias] += peso / len(dias)
    return pd.DataFrame({'fecha': fechas, 'pct': 100 * diario.cumsum().values / total})


def curva_real(viajes: pd.DataFrame, ajustes: pd.DataFrame, total_proyectado: float, hasta: str, inicio=None,
               actividades: pd.DataFrame | None = None, terreno_ids=None):
    """Serie diaria del % acumulado real (tickets netos + ajustes) / volumen proyectado total.

    Entre fechas con datos se interpola en línea recta (así, con avances informados cada semana la curva
    no queda en escalones). Si se da `inicio` (comienzo del programa), la curva parte en 0 ese día.
    La serie termina en el último día con datos (no se inventa avance después).
    """
    if actividades is not None:  # la proforma (adicional) no entra a la curva
        viajes = viajes[viajes['tipo'].fillna('') != 'adicional']
        actividades = planificadas(actividades)
        ajustes = ajustes[ajustes['actividad_id'].isin(actividades['id'])]
    if terreno_ids is not None:  # solo los sitios del alcance elegido (los tickets "General" quedan fuera)
        viajes = viajes[viajes['terreno_id'].isin(terreno_ids)]
        ajustes = ajustes[ajustes['actividad_id'].isin(actividades.loc[actividades['terreno_id'].isin(terreno_ids), 'id'])]
    movs = pd.concat([viajes[['fecha', 'volumen_m3']], ajustes[['fecha', 'volumen_m3']]])
    movs = movs[movs['fecha'] <= hasta]
    if movs.empty or total_proyectado <= 0:
        return pd.DataFrame(columns=['fecha', 'pct', 'm3'])
    acum = movs.groupby('fecha')['volumen_m3'].sum().cumsum()
    acum.index = pd.to_datetime(acum.index)
    origen = acum.index.min() - pd.Timedelta(days=1)
    if inicio:
        origen = min(origen, pd.Timestamp(inicio) - pd.Timedelta(days=1))
    acum.loc[origen] = 0.0
    acum = acum.sort_index()
    fechas = pd.date_range(origen, acum.index.max())
    m3 = acum.reindex(fechas).interpolate(method='time').values
    return pd.DataFrame({'fecha': fechas, 'm3': m3, 'pct': 100 * m3 / total_proyectado})


def proyeccion(real: pd.DataFrame, programada: pd.DataFrame, hasta: str, ventana_dias=14):
    """Proyecta el avance real con el ritmo de los últimos `ventana_dias` días corridos.

    Devuelve dict con: avance_real, avance_programado (a la fecha), ritmo (pp/día), ritmo_necesario,
    fecha_termino_estimada, fecha_termino_programada, pct_a_termino_programado, dias_desfase y la
    serie (fecha, pct) de la proyección. Valores None cuando no se pueden calcular.
    """
    hoy = pd.Timestamp(hasta)
    out = dict(avance_real=None, avance_programado=None, ritmo=None, ritmo_necesario=None,
               fecha_termino_estimada=None, fecha_termino_programada=None, pct_a_termino_programado=None,
               dias_desfase=None, fecha_ultimo_dato=None, serie=pd.DataFrame(columns=['fecha', 'pct']))
    if not programada.empty:
        out['fecha_termino_programada'] = programada['fecha'].max()
        antes = programada[programada['fecha'] <= hoy]
        out['avance_programado'] = float(antes['pct'].iloc[-1]) if not antes.empty else 0.0
    if real.empty:
        return out
    serie = real.set_index('fecha')['pct']
    hoy = min(hoy, serie.index[-1])  # se proyecta desde el último dato real
    out['fecha_ultimo_dato'] = hoy
    actual = float(serie.iloc[-1])
    out['avance_real'] = actual
    desde = hoy - pd.Timedelta(days=ventana_dias)
    base = float(serie[serie.index <= desde].iloc[-1]) if (serie.index <= desde).any() else float(serie.iloc[0])
    dias = min(ventana_dias, (hoy - serie.index[0]).days) or 1
    ritmo = (actual - base) / dias
    out['ritmo'] = ritmo
    fin_prog = out['fecha_termino_programada']
    if fin_prog is not None and fin_prog > hoy and actual < 100:
        out['ritmo_necesario'] = (100 - actual) / (fin_prog - hoy).days
    if actual >= 100:
        out['fecha_termino_estimada'] = serie[serie >= 100].index[0]
    elif ritmo > 0:
        out['fecha_termino_estimada'] = hoy + pd.Timedelta(days=int(-(-(100 - actual) // ritmo)))
    if fin_prog is not None:
        out['pct_a_termino_programado'] = min(100.0, actual + ritmo * max(0, (fin_prog - hoy).days))
        if out['fecha_termino_estimada'] is not None:
            out['dias_desfase'] = (out['fecha_termino_estimada'] - fin_prog).days
    if ritmo > 0 and actual < 100:
        fin = max(x for x in (out['fecha_termino_estimada'], fin_prog) if x is not None)
        fechas = pd.date_range(hoy, fin)
        out['serie'] = pd.DataFrame({'fecha': fechas,
                                     'pct': [min(100.0, actual + ritmo * (f - hoy).days) for f in fechas]})
    return out
