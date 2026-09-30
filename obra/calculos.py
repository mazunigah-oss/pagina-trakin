"""Cálculos: volúmenes retirados, prorrateo, estado programado vs real y resumen diario."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

CHILE = ZoneInfo('America/Santiago')
RANGO = {'sin_intervenir': 0, 'en_proceso': 1, 'entregado': 2, 'terminado': 2}


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
                _repartir(m3, acts, directo)
        general = viajes.loc[viajes['terreno_id'].isna(), 'volumen_m3'].sum()
        cand = actividades[actividades['estado'] == 'en_proceso']
        if cand.empty:
            cand = actividades[actividades['estado'] != 'terminado']
        if cand.empty:
            cand = actividades
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
    proy = acts['volumen_proyectado_m3'].sum()
    if (acts['estado'] == 'terminado').all() or (proy > 0 and acts['retirado_m3'].sum() >= proy):
        return 'terminado'
    if (acts['estado'] != 'sin_intervenir').any() or (acts['retirado_m3'] > 0).any():
        return 'en_proceso'
    return 'sin_intervenir'


def programa_terrenos(terrenos, acts, gantt, dia):
    """Por terreno: estado real del movimiento de tierra, estado y % programado, comparación."""
    g = gantt[gantt['zona'].isna()] if not gantt.empty else gantt
    rango = g.groupby('terreno_id').agg(inicio=('inicio', 'min'), termino=('termino', 'max')) if not g.empty \
        else pd.DataFrame(columns=['inicio', 'termino'])
    filas = []
    for _, t in terrenos.iterrows():
        a = acts[acts['terreno_id'] == t['id']]
        real = estado_real_terreno(a)
        ini = rango['inicio'].get(t['id']) if t['id'] in rango.index else None
        fin = rango['termino'].get(t['id']) if t['id'] in rango.index else None
        prog, pct_prog = estado_programado(ini, fin, dia, 'terminado') if ini else (None, None)
        proy, ret = a['volumen_proyectado_m3'].sum(), a['retirado_m3'].sum()
        filas.append(dict(terreno_id=t['id'], codigo=t['codigo'], real=real, programado=prog, inicio=ini, termino=fin,
                          avance_programado=pct_prog, proyectado_m3=proy, retirado_m3=ret,
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
