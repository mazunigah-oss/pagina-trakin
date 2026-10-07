"""Carga de archivos CSV / Excel.

Cada tipo de archivo define sus columnas y su modo:
  SUMA      agrega registros nuevos (los repetidos se omiten)
  ACTUALIZA modifica registros existentes
  REEMPLAZA borra lo anterior y carga lo nuevo
Todo se valida primero (revisión) y se guarda solo al confirmar.
"""
import io
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd
from sqlalchemy import delete, insert, select, update

from . import db as T
from .calculos import ahora_chile, hoy_chile

# ---------------------------------------------------------------- lectura


def clave(s):
    s = unicodedata.normalize('NFD', str(s or '')).encode('ascii', 'ignore').decode().lower().strip()
    return re.sub(r'[^a-z0-9]+', '_', s.replace('°', '').replace('º', '')).strip('_')


def leer_tabla(contenido: bytes, nombre: str = '', conocidas=()) -> pd.DataFrame:
    """Lee CSV (; , o tab; UTF-8 o Latin-1) o Excel. Devuelve texto sin convertir, con columnas normalizadas.
    La fila de encabezados es la primera (de las 15 primeras) que contiene algún nombre de columna conocido."""
    if nombre.lower().endswith(('.xlsx', '.xls')) or contenido[:2] == b'PK':
        crudo = pd.read_excel(io.BytesIO(contenido), dtype=object, header=None)
    else:
        try:
            texto = contenido.decode('utf-8-sig')
        except UnicodeDecodeError:
            texto = contenido.decode('latin-1')
        lineas = [l for l in texto.splitlines() if l.strip()][:15]
        sep = max([';', ',', '\t'], key=lambda c: sum(l.count(c) for l in lineas))
        crudo = pd.read_csv(io.StringIO(texto), sep=sep, dtype=str, keep_default_na=False, skip_blank_lines=True,
                            header=None, engine='python', on_bad_lines='skip')
    fila_enc = 0
    conocidas = set(conocidas)
    for i in range(min(15, len(crudo))):
        if conocidas & {clave(v) for v in crudo.iloc[i] if not vacio(v)}:
            fila_enc = i
            break
    df = crudo.iloc[fila_enc + 1:].copy()
    df.columns = [clave(c) if not vacio(c) else f'col_{j}' for j, c in enumerate(crudo.iloc[fila_enc])]
    df.index = range(fila_enc + 1, fila_enc + 1 + len(df))  # para que _fila coincida con la fila del archivo
    df = df.dropna(how='all')
    df = df[~df.apply(lambda f: all(str(v).strip() in ('', 'nan', 'None', 'NaT') for v in f), axis=1)]
    df.insert(0, '_fila', df.index + 1)  # número de fila como se ve en Excel
    return df.reset_index(drop=True)


# ---------------------------------------------------------------- normalización

MESES = dict(enero=1, febrero=2, marzo=3, abril=4, mayo=5, junio=6, julio=7, agosto=8, ago=8, septiembre=9,
             sept=9, sep=9, setiembre=9, octubre=10, oct=10, noviembre=11, nov=11, diciembre=12, dic=12)
VACIO = object()


def vacio(v):
    return v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() in ('', 'nan', 'None', 'NaT')


def norm_fecha(v):
    """Devuelve 'YYYY-MM-DD', None si está vacío o VACIO si es inválida."""
    if vacio(v):
        return None
    if isinstance(v, (datetime, pd.Timestamp)):
        return v.strftime('%Y-%m-%d')
    if isinstance(v, date):
        return v.isoformat()
    s = str(v).strip()
    m = re.match(r'^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})', s)
    if m:
        y, mo, d = int(m[1]), int(m[2]), int(m[3])
    else:
        m = re.match(r'^(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})', s)
        if not m:
            return VACIO
        d, mo, y = int(m[1]), int(m[2]), int(m[3])
        y += 2000 if y < 100 else 0
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return VACIO


def norm_hora(v):
    if vacio(v):
        return None
    if isinstance(v, (datetime, pd.Timestamp)):
        return v.strftime('%H:%M')
    if hasattr(v, 'hour'):
        return f'{v.hour:02d}:{v.minute:02d}'
    m = re.search(r'(\d{1,2})[:.](\d{2})', str(v))
    if not m or int(m[1]) > 23 or int(m[2]) > 59:
        return VACIO
    return f'{int(m[1]):02d}:{m[2]}'


def norm_numero(v):
    if vacio(v):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(' ', '').replace('m3', '').replace('m³', '')
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    elif re.fullmatch(r'-?\d{1,3}(\.\d{3})+', s):  # 1.250 = mil doscientos cincuenta
        s = s.replace('.', '')
    try:
        return float(s)
    except ValueError:
        return VACIO


def norm_patente(v):
    return re.sub(r'[^A-Z0-9]', '', str(v or '').upper())


def texto(v):
    return '' if vacio(v) else clave(v).replace('_', ' ')


def norm_terreno(v):
    """'12', 'S-12', 'Sitio 12', 'ED-1', 'Edificio 1' -> código. None si vacío, VACIO si no se entiende."""
    s = texto(v)
    if not s or s == 'general':
        return None
    m = re.fullmatch(r'(?:s|sitio|lote|sector)?\s*(\d{1,2})(?:\s*0+)?', s)
    if m and 1 <= int(m[1]) <= 48:
        return f'S-{int(m[1]):02d}'
    m = re.fullmatch(r'(?:ed|edificio)\s*(\d+)', s)
    if m:
        return f'ED-{int(m[1])}'
    return VACIO


def norm_actividad(v):
    s = texto(v)
    if not s:
        return None
    if 'adicional' in s or 'botadero' in s:
        return 'adicional'
    if 'escarpe' in s:  # incluye "descarpe"
        return 'escarpe'
    if re.search(r'corte|subterr|excav', s):
        return 'corte'
    return VACIO


def norm_zona(v):
    s = texto(v)
    if not s:
        return None
    if 'acceso' in s:
        return 'acceso'
    if 'living' in s or 'casa' in s:
        return 'living'
    if 'patio' in s or 'fondo' in s:
        return 'fondo_patio'
    if 'unica' in s:
        return 'unica'
    return VACIO


def norm_estado(v, final='entregado'):
    s = texto(v)
    if not s:
        return None
    if re.search(r'sin|no inter|pendiente|no tocado', s):
        return 'sin_intervenir'
    if re.search(r'proceso|curso|ejecucion', s):
        return 'en_proceso'
    if re.search(r'entregad|listo|termina|complet', s):
        return final
    return VACIO


# ---------------------------------------------------------------- tipos de archivo


SITIO = ('sector', 'terreno', 'n_sitio', 'numero_sitio', 'sitio_n', 'n_de_sitio', 'lote', 'casa')


@dataclass
class Columna:
    campo: str
    alias: tuple = ()
    requerido: bool = False
    ejemplo: str = ''
    descripcion: str = ''


@dataclass
class Revision:
    ok: bool = True
    faltan_columnas: list = field(default_factory=list)
    columnas_encontradas: list = field(default_factory=list)
    filas: int = 0
    resumen: dict = field(default_factory=dict)
    errores: list = field(default_factory=list)   # (fila, mensaje): se omiten
    avisos: list = field(default_factory=list)    # (fila, mensaje): se cargan igual
    ops: list = field(default_factory=list)

    @property
    def hay_cambios(self):
        return bool(self.ops)


def valor(fila, col: Columna):
    for k in (col.campo, *col.alias):
        if k in fila and not vacio(fila[k]):
            return fila[k]
    return None


def mapa_terrenos(con):
    return {r.codigo: r for r in con.execute(select(T.terreno))}


class TipoArchivo:
    id = titulo = modo = ayuda = ''
    columnas: list = []

    def validar(self, con, df, rev):  # pragma: no cover - se implementa en cada tipo
        raise NotImplementedError

    def aplicar(self, con, ops, carga_id):  # pragma: no cover
        raise NotImplementedError


class Viajes(TipoArchivo):
    id = 'viajes'
    titulo = 'Tickets de camiones (CSV de la máquina)'
    modo = 'SUMA'
    ayuda = ('Formato de la máquina: TICKET;FECHA;HORA;PATENTE;VOLUMEN_M3;SECTOR;TIPO;ESTADO. '
             'Cada ticket se guarda una sola vez (se puede volver a subir el mismo archivo o uno acumulado). '
             'Las ANULACIONES restan su volumen. SECTOR = número de sitio; si viene vacío el viaje queda como '
             '"General" y se reparte proporcionalmente.')
    columnas = [
        Columna('ticket', ('n_ticket', 'numero_ticket', 'folio'), True, '1329'),
        Columna('fecha', ('fecha_salida',), True, '30/09/2026'),
        Columna('hora', ('hora_salida',), True, '08:42'),
        Columna('patente', ('placa', 'ppu'), True, 'GXVL25'),
        Columna('volumen_m3', ('volumen', 'm3', 'cantidad'), True, '22,0'),
        Columna('sector', ('sitio', 'terreno'), False, '12', 'Número de sitio (1 a 48); vacío = General'),
        Columna('tipo', ('actividad', 'trabajo'), False, 'CORTE', 'CORTE o DESCARPE'),
        Columna('estado', (), False, 'VALIDO', 'VALIDO o ANULACION (si falta, VALIDO)'),
    ]

    def validar(self, con, df, rev):
        terrenos = mapa_terrenos(con)
        existentes = {(r.ticket, r.estado) for r in con.execute(select(T.viaje.c.ticket, T.viaje.c.estado))}
        validos_bd = {t for t, e in existentes if e == 'VALIDO'}
        vistos, dup, sectores_raros = set(), 0, set()
        c = {x.campo: x for x in self.columnas}
        filas = df.to_dict('records')
        validos_archivo = {str(valor(f, c['ticket'])).strip() for f in filas
                           if texto(valor(f, c['estado'])) in ('', 'valido')}
        for f in filas:
            n = f['_fila']
            ticket = str(valor(f, c['ticket']) or '').strip()
            if ticket.endswith('.0'):
                ticket = ticket[:-2]
            fecha, hora = norm_fecha(valor(f, c['fecha'])), norm_hora(valor(f, c['hora']))
            patente, vol = norm_patente(valor(f, c['patente'])), norm_numero(valor(f, c['volumen_m3']))
            est_txt = texto(valor(f, c['estado'])) or 'valido'
            estado = 'ANULACION' if 'anula' in est_txt else 'VALIDO' if 'valid' in est_txt else None
            tipo = norm_actividad(valor(f, c['tipo']))
            sector_txt = '' if vacio(valor(f, c['sector'])) else str(valor(f, c['sector'])).strip()
            codigo = norm_terreno(sector_txt)
            if not ticket:
                rev.errores.append((n, 'Falta el número de ticket')); continue
            if fecha in (None, VACIO):
                rev.errores.append((n, f'Fecha inválida: "{valor(f, c["fecha"])}"')); continue
            if hora in (None, VACIO):
                rev.errores.append((n, f'Hora inválida: "{valor(f, c["hora"])}"')); continue
            if not patente:
                rev.errores.append((n, 'Falta la patente')); continue
            if vol in (None, VACIO):
                rev.errores.append((n, f'Volumen inválido: "{valor(f, c["volumen_m3"])}"')); continue
            if estado is None:
                rev.errores.append((n, f'Estado "{valor(f, c["estado"])}" no reconocido (VALIDO o ANULACION)')); continue
            if tipo is VACIO:
                rev.errores.append((n, f'Tipo "{valor(f, c["tipo"])}" no reconocido (CORTE o DESCARPE)')); continue
            if codigo is VACIO or (codigo and codigo not in terrenos):
                sectores_raros.add(sector_txt)
                codigo = None
            if (ticket, estado) in vistos or (ticket, estado) in existentes:
                dup += 1; continue
            vistos.add((ticket, estado))
            vol = -abs(vol) if estado == 'ANULACION' else abs(vol)
            if estado == 'ANULACION' and ticket not in validos_bd and ticket not in validos_archivo:
                rev.avisos.append((n, f'Anulación del ticket {ticket}, que no está cargado como válido'))
            rev.ops.append(dict(ticket=ticket, fecha=fecha, hora=hora, patente=patente, volumen_m3=vol,
                                sector=sector_txt or None, terreno_id=terrenos[codigo].id if codigo else None,
                                tipo=tipo, estado=estado))
        for s in sorted(sectores_raros):
            rev.avisos.append((None, f'Sector "{s}" no corresponde a un sitio: esos viajes quedan como General'))
        validos = [o for o in rev.ops if o['estado'] == 'VALIDO']
        rev.resumen = dict(tickets_nuevos=len(rev.ops), validos=len(validos),
                           anulaciones=len(rev.ops) - len(validos), repetidos_omitidos=dup,
                           m3_netos=round(sum(o['volumen_m3'] for o in rev.ops), 1))

    def aplicar(self, con, ops, carga_id):
        con.execute(insert(T.viaje), [dict(o, carga_id=carga_id) for o in ops])


class Gantt(TipoArchivo):
    id = 'gantt'
    titulo = 'Programa (carta Gantt) de movimiento de tierra'
    modo = 'REEMPLAZA'
    ayuda = ('Una fila por sitio con la fecha de inicio y término del movimiento de tierra. '
             'Opcional: actividad (escarpe / corte) para programarlas por separado, o zona '
             '(acceso / living / patio) para programar la entrega de una terraza. Reemplaza el programa anterior.')
    columnas = [
        Columna('sitio', SITIO, True, '15'),
        Columna('inicio', ('fecha_inicio', 'comienzo', 'desde'), True, '28/09/2026'),
        Columna('termino', ('fecha_termino', 'fin', 'hasta', 'fecha_fin'), True, '02/10/2026'),
        Columna('actividad', ('tipo', 'trabajo'), False, '', 'Opcional: escarpe o corte'),
        Columna('zona', ('terraza',), False, '', 'Opcional: acceso, living o patio'),
        Columna('tarea', ('descripcion', 'nombre'), False, 'Excavación a máquina', 'Texto libre'),
    ]

    def validar(self, con, df, rev):
        terrenos = mapa_terrenos(con)
        c = {x.campo: x for x in self.columnas}
        sin_fechas = []
        for f in df.to_dict('records'):
            n = f['_fila']
            codigo = norm_terreno(valor(f, c['sitio']))
            ini, fin = norm_fecha(valor(f, c['inicio'])), norm_fecha(valor(f, c['termino']))
            act, zon = norm_actividad(valor(f, c['actividad'])), norm_zona(valor(f, c['zona']))
            if codigo in (None, VACIO) or codigo not in terrenos:
                rev.errores.append((n, f'Sitio "{valor(f, c["sitio"])}" no existe')); continue
            if ini is None and fin is None:
                sin_fechas.append(codigo); continue
            if ini in (None, VACIO) or fin in (None, VACIO):
                rev.errores.append((n, 'Fechas de inicio o término inválidas')); continue
            if fin < ini:
                rev.errores.append((n, 'El término es anterior al inicio')); continue
            if act is VACIO or zon is VACIO:
                rev.errores.append((n, 'Actividad o zona no reconocida')); continue
            rev.ops.append(dict(terreno_id=terrenos[codigo].id, actividad=act, zona=zon, inicio=ini, termino=fin,
                                texto=None if vacio(valor(f, c['tarea'])) else str(valor(f, c['tarea']))[:200]))
        if sin_fechas:
            rev.avisos.append((None, f'{len(sin_fechas)} filas sin fechas quedan fuera del programa: '
                                     + ', '.join(sorted(set(sin_fechas)))))
        anteriores = con.execute(select(T.gantt.c.id)).all()
        rev.resumen = dict(tareas_nuevas=len(rev.ops), sitios=len({o['terreno_id'] for o in rev.ops}),
                           reemplaza_tareas_anteriores=len(anteriores))

    def aplicar(self, con, ops, carga_id):
        con.execute(delete(T.gantt))
        con.execute(insert(T.gantt), [dict(o, carga_id=carga_id) for o in ops])


class Volumenes(TipoArchivo):
    id = 'volumenes'
    titulo = 'Volúmenes proyectados y estado de escarpe / corte'
    modo = 'ACTUALIZA'
    ayuda = ('Volumen proyectado (m³) por sitio. Si se indica la actividad (escarpe o corte) se actualiza esa; '
             'si no, el volumen es el TOTAL del sitio (queda como corte y el escarpe en 0). '
             'Opcional: estado. Celdas vacías no se modifican.')
    columnas = [
        Columna('sitio', SITIO, True, '15'),
        Columna('volumen_proyectado_m3', ('volumen_proyectado', 'proyectado', 'volumen', 'volumen_m3', 'm3',
                                          'm3_proyectados', 'cubicacion', 'volumen_total', 'total_m3', 'total'),
                False, '180', 'Obligatoria salvo que solo se cambie el estado'),
        Columna('actividad', ('tipo', 'trabajo'), False, '', 'Opcional: escarpe o corte (vacío = total del sitio)'),
        Columna('estado', (), False, '', 'Opcional: sin intervenir / en proceso / terminado'),
    ]

    def validar(self, con, df, rev):
        terrenos = mapa_terrenos(con)
        acts = {(r.terreno_id, r.tipo): r for r in con.execute(select(T.actividad))}
        c = {x.campo: x for x in self.columnas}
        for f in df.to_dict('records'):
            n = f['_fila']
            codigo = norm_terreno(valor(f, c['sitio']))
            tipo = norm_actividad(valor(f, c['actividad']))
            vol = norm_numero(valor(f, c['volumen_proyectado_m3']))
            est = norm_estado(valor(f, c['estado']), 'terminado')
            if codigo in (None, VACIO) or codigo not in terrenos:
                rev.errores.append((n, f'Sitio "{valor(f, c["sitio"])}" no existe')); continue
            if tipo is VACIO:
                rev.errores.append((n, f'Actividad "{valor(f, c["actividad"])}" no reconocida (escarpe o corte)')); continue
            if vol is VACIO or (vol is not None and vol < 0):
                rev.errores.append((n, f'Volumen inválido: "{valor(f, c["volumen_proyectado_m3"])}"')); continue
            if est is VACIO:
                rev.errores.append((n, f'Estado "{valor(f, c["estado"])}" no reconocido')); continue
            if vol is None and est is None:
                rev.errores.append((n, 'Fila sin volumen ni estado')); continue
            tid = terrenos[codigo].id
            if tipo is None:  # total del sitio
                for t, v in (('corte', vol), ('escarpe', 0.0 if vol is not None else None)):
                    a = acts[(tid, t)]
                    rev.ops.append(dict(id=a.id, volumen=a.volumen_proyectado_m3 if v is None else v,
                                        estado=est or a.estado, cambio_estado=bool(est and est != a.estado)))
            else:
                a = acts[(tid, tipo)]
                rev.ops.append(dict(id=a.id, volumen=a.volumen_proyectado_m3 if vol is None else vol,
                                    estado=est or a.estado, cambio_estado=bool(est and est != a.estado)))
        terreno_de = {r.id: r.terreno_id for r in acts.values()}
        rev.resumen = dict(sitios=len({terreno_de[o['id']] for o in rev.ops}),
                           actividades_actualizadas=len(rev.ops),
                           m3_proyectados_en_archivo=round(sum(o['volumen'] for o in rev.ops), 1))

    def aplicar(self, con, ops, carga_id):
        for o in ops:
            con.execute(update(T.actividad).where(T.actividad.c.id == o['id'])
                        .values(volumen_proyectado_m3=o['volumen'], estado=o['estado']))
            if o['cambio_estado']:
                con.execute(insert(T.historial).values(tabla='actividad', ref_id=o['id'], estado=o['estado'],
                                                       fecha=hoy_chile()))


class Entregas(TipoArchivo):
    id = 'entregas'
    titulo = 'Estado de entregas de terrazas'
    modo = 'ACTUALIZA'
    ayuda = 'Estado de acceso, living y fondo de patio de cada sitio. Si se marca entregado sin fecha, se usa hoy.'
    columnas = [
        Columna('sitio', SITIO, True, '15'),
        Columna('zona', ('terraza',), True, 'acceso', 'acceso / living / patio (unica en edificios)'),
        Columna('estado', (), True, 'entregado', 'sin intervenir / en proceso / entregado'),
        Columna('fecha_entrega', ('fecha',), False, '29/09/2026'),
    ]

    def validar(self, con, df, rev):
        terrenos = mapa_terrenos(con)
        zonas = {(r.terreno_id, r.zona): r for r in con.execute(select(T.zona))}
        c = {x.campo: x for x in self.columnas}
        for f in df.to_dict('records'):
            n = f['_fila']
            codigo = norm_terreno(valor(f, c['sitio']))
            if codigo in (None, VACIO) or codigo not in terrenos:
                rev.errores.append((n, f'Sitio "{valor(f, c["sitio"])}" no existe')); continue
            t = terrenos[codigo]
            zon = norm_zona(valor(f, c['zona'])) or ('unica' if t.tipo != 'sitio' else None)
            est = norm_estado(valor(f, c['estado']))
            fecha = norm_fecha(valor(f, c['fecha_entrega']))
            if zon in (None, VACIO) or (t.id, zon) not in zonas:
                rev.errores.append((n, f'Zona "{valor(f, c["zona"])}" no válida para {codigo}')); continue
            if est in (None, VACIO):
                rev.errores.append((n, 'Estado no reconocido')); continue
            if fecha is VACIO:
                rev.errores.append((n, 'Fecha inválida')); continue
            z = zonas[(t.id, zon)]
            fecha = (fecha or z.fecha_entrega or hoy_chile()) if est == 'entregado' else None
            rev.ops.append(dict(id=z.id, estado=est, fecha=fecha, cambio=est != z.estado))
        rev.resumen = dict(terrazas_actualizadas=len(rev.ops), cambian_de_estado=sum(o['cambio'] for o in rev.ops))

    def aplicar(self, con, ops, carga_id):
        for o in ops:
            con.execute(update(T.zona).where(T.zona.c.id == o['id']).values(estado=o['estado'], fecha_entrega=o['fecha']))
            if o['cambio']:
                con.execute(insert(T.historial).values(tabla='zona', ref_id=o['id'], estado=o['estado'],
                                                       fecha=o['fecha'] or hoy_chile()))


class Avance(TipoArchivo):
    id = 'avance'
    titulo = 'Avance acumulado por sitio (sin tickets diarios)'
    modo = 'ACTUALIZA'
    ayuda = ('Para cuando no hay registros diarios: por cada sitio, cuánto se lleva movido A UNA FECHA, en % o en m³ '
             'acumulados. La página ajusta el volumen retirado del sitio para que quede exactamente en ese valor a esa '
             'fecha (no suma: si se informa 40 % y después 55 %, avanza 15 %). Conviene cargarlo cada semana con la '
             'fecha del corte para que la curva tenga varios puntos. Opcional: volumen proyectado en la misma planilla.')
    columnas = [
        Columna('sitio', SITIO, True, '15'),
        Columna('fecha', ('fecha_corte', 'fecha_avance', 'al'), False, '04/10/2026', 'Fecha del corte (vacío = hoy)'),
        Columna('avance_pct', ('avance', 'porcentaje', 'pct', 'avance_porcentaje', 'porcentaje_avance', 'avance_real'),
                False, '45', '% de avance del sitio (45, 45% o 0,45)'),
        Columna('m3_acumulados', ('m3_movidos', 'cantidad', 'cantidad_movida', 'volumen_movido', 'm3_a_la_fecha',
                                  'acumulado', 'movido', 'm3_ejecutados', 'ejecutado', 'trasladado_m3', 'trasladado'),
                False, '', 'Alternativa al %: m³ movidos a la fecha'),
        Columna('volumen_proyectado_m3', ('volumen_proyectado', 'volumen_total', 'proyectado', 'cubicacion', 'total_m3',
                                          'esponjado_m3', 'volumen_esponjado', 'adicional_a_botadero_m3'),
                False, '', 'Opcional: actualiza el volumen proyectado (esponjado, el que trasladan los camiones)'),
        Columna('actividad', ('tipo', 'trabajo'), False, '',
                'Opcional: escarpe, corte o adicional (botadero). Vacío = escarpe + corte del sitio'),
    ]

    def validar(self, con, df, rev):
        from .calculos import volumenes
        terrenos = mapa_terrenos(con)
        acts = pd.read_sql(select(T.actividad), con)
        viajes = pd.read_sql(select(T.viaje), con)
        ajustes = pd.read_sql(select(T.ajuste), con)
        c = {x.campo: x for x in self.columnas}
        filas = df.to_dict('records')
        # % como fracción (0,45) si todos los valores son <= 1 (típico de celdas Excel con formato %)
        pcts = [norm_numero(str(valor(f, c['avance_pct'])).replace('%', '')) for f in filas
                if not vacio(valor(f, c['avance_pct']))]
        fraccion = bool(pcts) and all(isinstance(x, float) and 0 <= x <= 1 for x in pcts) and \
            not any('%' in str(valor(f, c['avance_pct']) or '') for f in filas)
        hoy = hoy_chile()
        leidas, sin_avance = [], []
        for f in filas:
            n = f['_fila']
            codigo = norm_terreno(valor(f, c['sitio']))
            if codigo in (None, VACIO) or codigo not in terrenos:
                rev.errores.append((n, f'Sitio "{valor(f, c["sitio"])}" no existe')); continue
            fecha = norm_fecha(valor(f, c['fecha'])) or hoy
            if fecha is VACIO:
                rev.errores.append((n, f'Fecha inválida: "{valor(f, c["fecha"])}"')); continue
            pct_txt = valor(f, c['avance_pct'])
            pct = norm_numero(str(pct_txt).replace('%', '')) if not vacio(pct_txt) else None
            m3 = norm_numero(valor(f, c['m3_acumulados']))
            proy = norm_numero(valor(f, c['volumen_proyectado_m3']))
            tipo = norm_actividad(valor(f, c['actividad']))
            if VACIO in (pct, m3, proy) or tipo is VACIO:
                rev.errores.append((n, 'Valor no reconocido (revise %, m³, volumen o actividad)')); continue
            if pct is None and m3 is None and proy is None:
                rev.errores.append((n, 'Falta el avance (% o m³ acumulados)')); continue
            if pct is None and m3 is None:  # solo volumen: se carga el proyectado, sin avance
                sin_avance.append(codigo)
            if pct is not None and fraccion:
                pct *= 100
            if pct is not None and not 0 <= pct <= 150:
                rev.errores.append((n, f'Avance fuera de rango: {pct_txt}')); continue
            leidas.append((fecha, n, terrenos[codigo].id, tipo, pct, m3, proy))

        # volúmenes proyectados informados en el mismo archivo (se aplican antes de calcular el %)
        for fecha, n, tid, tipo, pct, m3, proy in leidas:
            if proy is None:
                continue
            filas_t = acts['terreno_id'] == tid
            if tipo:
                acts.loc[filas_t & (acts['tipo'] == tipo), 'volumen_proyectado_m3'] = proy
            else:
                acts.loc[filas_t & (acts['tipo'] == 'corte'), 'volumen_proyectado_m3'] = proy
                acts.loc[filas_t & (acts['tipo'] == 'escarpe'), 'volumen_proyectado_m3'] = 0.0
        cambios_proy = {}
        for _, a in acts.iterrows():
            cambios_proy[int(a['id'])] = float(a['volumen_proyectado_m3'])

        pendientes = []  # ajustes que este archivo va a crear (para encadenar varios cortes del mismo sitio)
        for fecha, n, tid, tipo, pct, m3, proy in sorted(leidas, key=lambda x: x[:2]):
            if pct is None and m3 is None:
                continue
            sel = acts[(acts['terreno_id'] == tid) & ((acts['tipo'] == tipo) if tipo else (acts['tipo'] != 'adicional'))]
            proy_total = float(sel['volumen_proyectado_m3'].sum())
            if m3 is None:
                if proy_total <= 0:
                    rev.errores.append((n, 'Para usar % el sitio necesita volumen proyectado (agregue la columna '
                                           'volumen_proyectado_m3 o cárguelo antes)')); continue
                m3 = pct / 100 * proy_total
            aj = pd.concat([ajustes, pd.DataFrame(pendientes, columns=['actividad_id', 'fecha', 'volumen_m3'])])
            actual = volumenes(acts, viajes, aj, hasta=fecha).set_index('id')['retirado_m3']
            pesos = sel['volumen_proyectado_m3'] if proy_total > 0 else (sel['tipo'] == 'corte').astype(float)
            for (_, a), peso in zip(sel.iterrows(), pesos):
                objetivo = m3 * peso / pesos.sum()
                delta = objetivo - float(actual[a['id']])
                if abs(delta) >= 0.05:
                    pendientes.append((int(a['id']), fecha, delta))
                    rev.ops.append(dict(tipo='ajuste', actividad_id=int(a['id']), fecha=fecha, volumen_m3=round(float(delta), 3),
                                        motivo=f'Avance informado al {fecha}: '
                                               + (f'{pct:.1f} %' if pct is not None else f'{m3:.1f} m³')))
        originales = {int(r.id): r.volumen_proyectado_m3 for r in con.execute(select(T.actividad))}
        for aid, v in cambios_proy.items():
            if abs(v - originales[aid]) > 1e-9:
                rev.ops.insert(0, dict(tipo='proyectado', id=aid, volumen=v))
        if sin_avance:
            rev.avisos.append((None, f'Sin dato de avance (solo se carga el volumen): {", ".join(sin_avance)}'))
        rev.resumen = dict(sitios=len({x[2] for x in leidas}), cortes_leidos=len(leidas) - len(sin_avance),
                           ajustes_de_volumen=sum(o['tipo'] == 'ajuste' for o in rev.ops),
                           m3_ajustados=float(round(sum(o['volumen_m3'] for o in rev.ops if o['tipo'] == 'ajuste'), 1)),
                           proyectados_actualizados=sum(o['tipo'] == 'proyectado' for o in rev.ops))

    def aplicar(self, con, ops, carga_id):
        for o in ops:
            if o['tipo'] == 'proyectado':
                con.execute(update(T.actividad).where(T.actividad.c.id == o['id']).values(volumen_proyectado_m3=o['volumen']))
        ajustes = [dict(actividad_id=o['actividad_id'], fecha=o['fecha'], volumen_m3=o['volumen_m3'], motivo=o['motivo'],
                        carga_id=carga_id) for o in ops if o['tipo'] == 'ajuste']
        if ajustes:
            con.execute(insert(T.ajuste), ajustes)


class Rellenos(TipoArchivo):
    id = 'rellenos'
    titulo = 'Rellenos compactados y densidades'
    modo = 'REEMPLAZA'
    ayuda = ('Rellenos en capas de ~0,25 m por sitio: m³ de corte y relleno, capas por zona (cada capa = una '
             'densidad) y entrega. "P" = pendiente. Un sitio puede tener varias filas. Reemplaza la carga anterior.')
    columnas = [
        Columna('sitio', SITIO, True, '30'),
        Columna('corte_m3', ('corte',), False, '287,9'),
        Columna('relleno_m3', ('relleno',), False, '287,9', 'm³ o P (pendiente)'),
        Columna('capas_acceso', (), False, '3'),
        Columna('capas_living', (), False, '2'),
        Columna('capas_calicata', (), False, ''),
        Columna('entrega', ('estado',), False, 'OK'),
    ]

    def validar(self, con, df, rev):
        terrenos = mapa_terrenos(con)
        c = {x.campo: x for x in self.columnas}
        for f in df.to_dict('records'):
            n = f['_fila']
            codigo = norm_terreno(valor(f, c['sitio']))
            if codigo in (None, VACIO) or codigo not in terrenos:
                rev.errores.append((n, f'Sitio "{valor(f, c["sitio"])}" no existe')); continue
            fila, pend_rel, pend_capas, malo = {}, False, False, None
            for campo in ('corte_m3', 'relleno_m3', 'capas_acceso', 'capas_living', 'capas_calicata'):
                v = valor(f, c[campo])
                if not vacio(v) and str(v).strip().upper() == 'P':
                    pend_rel |= campo == 'relleno_m3'
                    pend_capas |= campo.startswith('capas')
                    fila[campo] = None
                    continue
                x = norm_numero(v)
                if x is VACIO or (x is not None and x < 0):
                    malo = campo
                    break
                fila[campo] = int(round(x)) if campo.startswith('capas') and x is not None else x
            if malo:
                rev.errores.append((n, f'Valor inválido en {malo}: "{valor(f, c[malo])}"')); continue
            ent = valor(f, c['entrega'])
            rev.ops.append(dict(terreno_id=terrenos[codigo].id, relleno_pendiente=int(pend_rel),
                                capas_pendiente=int(pend_capas), entrega=None if vacio(ent) else str(ent).strip()[:20],
                                **fila))
        capas = sum((o.get(k) or 0) for o in rev.ops for k in ('capas_acceso', 'capas_living', 'capas_calicata'))
        rev.resumen = dict(registros=len(rev.ops), sitios=len({o['terreno_id'] for o in rev.ops}),
                           corte_m3=round(sum(o.get('corte_m3') or 0 for o in rev.ops), 1),
                           relleno_m3=round(sum(o.get('relleno_m3') or 0 for o in rev.ops), 1),
                           densidades=capas)

    def aplicar(self, con, ops, carga_id):
        con.execute(delete(T.relleno))
        con.execute(insert(T.relleno), [dict(o, carga_id=carga_id) for o in ops])


class Hitos(TipoArchivo):
    id = 'hitos'
    titulo = 'Hitos de la obra'
    modo = 'REEMPLAZA'
    ayuda = 'Fechas clave que se marcan en la curva de avance y en la carta Gantt. Reemplaza los hitos anteriores.'
    columnas = [
        Columna('hito', ('nombre', 'descripcion', 'evento'), True, 'Inicio obra gruesa casas'),
        Columna('fecha', ('semana', 'semana_del'), True, '02/11/2026'),
    ]

    def validar(self, con, df, rev):
        c = {x.campo: x for x in self.columnas}
        for f in df.to_dict('records'):
            fecha = norm_fecha(valor(f, c['fecha']))
            nombre = valor(f, c['hito'])
            if vacio(nombre) or fecha in (None, VACIO):
                rev.errores.append((f['_fila'], 'Falta el nombre o la fecha es inválida')); continue
            rev.ops.append(dict(nombre=str(nombre).strip()[:120], fecha=fecha))
        rev.resumen = dict(hitos=len(rev.ops))

    def aplicar(self, con, ops, carga_id):
        con.execute(delete(T.hito))
        con.execute(insert(T.hito), [dict(o, carga_id=carga_id) for o in ops])


class Ajustes(TipoArchivo):
    id = 'ajustes'
    titulo = 'Ajustes manuales de volumen (topografía)'
    modo = 'SUMA'
    ayuda = 'Suma (o resta con número negativo) m³ retirados a una actividad, por ejemplo tras una topografía.'
    columnas = [
        Columna('sitio', SITIO, True, '15'),
        Columna('actividad', ('tipo',), True, 'corte'),
        Columna('fecha', (), True, '30/09/2026'),
        Columna('volumen_m3', ('volumen', 'm3'), True, '35,5'),
        Columna('motivo', ('observacion', 'comentario'), False, 'Levantamiento topográfico'),
    ]

    def validar(self, con, df, rev):
        terrenos = mapa_terrenos(con)
        acts = {(r.terreno_id, r.tipo): r.id for r in con.execute(select(T.actividad))}
        c = {x.campo: x for x in self.columnas}
        for f in df.to_dict('records'):
            n = f['_fila']
            codigo = norm_terreno(valor(f, c['sitio']))
            tipo = norm_actividad(valor(f, c['actividad']))
            fecha, vol = norm_fecha(valor(f, c['fecha'])), norm_numero(valor(f, c['volumen_m3']))
            if codigo in (None, VACIO) or codigo not in terrenos:
                rev.errores.append((n, 'Sitio no existe')); continue
            if tipo in (None, VACIO):
                rev.errores.append((n, 'Actividad no reconocida')); continue
            if fecha in (None, VACIO) or vol in (None, VACIO):
                rev.errores.append((n, 'Fecha o volumen inválido')); continue
            rev.ops.append(dict(actividad_id=acts[(terrenos[codigo].id, tipo)], fecha=fecha, volumen_m3=vol,
                                motivo=None if vacio(valor(f, c['motivo'])) else str(valor(f, c['motivo']))[:200]))
        rev.resumen = dict(ajustes_nuevos=len(rev.ops), m3=round(sum(o['volumen_m3'] for o in rev.ops), 1))

    def aplicar(self, con, ops, carga_id):
        con.execute(insert(T.ajuste), [dict(o, carga_id=carga_id) for o in ops])


TIPOS = {t.id: t for t in (Viajes(), Avance(), Gantt(), Volumenes(), Entregas(), Ajustes(), Rellenos(), Hitos())}
DESHACIBLES = {'viajes': T.viaje, 'ajustes': T.ajuste, 'gantt': T.gantt, 'avance': T.ajuste,
               'rellenos': T.relleno, 'hitos': T.hito}


def revisar(motor, tipo, contenido, nombre=''):
    t = TIPOS[tipo]
    rev = Revision()
    try:
        df = leer_tabla(contenido, nombre, {k for c in t.columnas for k in (c.campo, *c.alias)})
    except Exception as e:  # archivo corrupto o formato desconocido
        rev.ok = False
        rev.errores.append((None, f'No se pudo leer el archivo: {e}'))
        return rev
    rev.filas = len(df)
    rev.columnas_encontradas = [c for c in df.columns if c != '_fila']
    rev.faltan_columnas = [c.campo for c in t.columnas
                           if c.requerido and not any(k in df.columns for k in (c.campo, *c.alias))]
    if rev.faltan_columnas:
        rev.ok = False
        return rev
    with motor.connect() as con:
        t.validar(con, df, rev)
    return rev


def aplicar(motor, tipo, rev: Revision, nombre=''):
    """Guarda en una sola transacción. Devuelve el id de la carga."""
    if not rev.ok or not rev.ops:
        return None
    resumen = dict(filas=rev.filas, **rev.resumen, errores=len(rev.errores))
    with motor.begin() as con:
        carga_id = con.execute(insert(T.carga).values(
            tipo=tipo, archivo=nombre[:200], resumen=json.dumps(resumen, ensure_ascii=False),
            creado_en=ahora_chile())).inserted_primary_key[0]
        TIPOS[tipo].aplicar(con, rev.ops, carga_id)
    return carga_id


def deshacer(motor, carga_id):
    with motor.begin() as con:
        c = con.execute(select(T.carga).where(T.carga.c.id == carga_id)).first()
        if c is None or c.tipo not in DESHACIBLES:
            return False
        tabla = DESHACIBLES[c.tipo]
        con.execute(delete(tabla).where(tabla.c.carga_id == carga_id))
        con.execute(delete(T.carga).where(T.carga.c.id == carga_id))
    return True


def plantilla(tipo) -> bytes:
    cols = TIPOS[tipo].columnas
    lineas = [';'.join(c.campo.upper() if tipo == 'viajes' else c.campo for c in cols),
              ';'.join(c.ejemplo for c in cols)]
    return ('﻿' + '\r\n'.join(lineas) + '\r\n').encode('utf-8')
