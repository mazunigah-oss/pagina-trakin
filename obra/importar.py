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


def leer_tabla(contenido: bytes, nombre: str = '') -> pd.DataFrame:
    """Lee CSV (; , o tab; UTF-8 o Latin-1) o Excel. Devuelve texto sin convertir, con columnas normalizadas."""
    if nombre.lower().endswith(('.xlsx', '.xls')) or contenido[:2] == b'PK':
        df = pd.read_excel(io.BytesIO(contenido), dtype=object)
    else:
        try:
            texto = contenido.decode('utf-8-sig')
        except UnicodeDecodeError:
            texto = contenido.decode('latin-1')
        primera = texto.splitlines()[0] if texto.strip() else ''
        sep = max([';', ',', '\t'], key=primera.count)
        df = pd.read_csv(io.StringIO(texto), sep=sep, dtype=str, keep_default_na=False, skip_blank_lines=True)
    df.columns = [clave(c) for c in df.columns]
    df = df.dropna(how='all')
    df = df[~df.apply(lambda f: all(str(v).strip() in ('', 'nan', 'None', 'NaT') for v in f), axis=1)]
    df.insert(0, '_fila', df.index + 2)  # número de fila como se ve en Excel (encabezado = fila 1)
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
    s = str(v).strip().replace(' ', '')
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
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
        Columna('sitio', ('sector', 'terreno'), True, '15'),
        Columna('inicio', ('fecha_inicio', 'comienzo', 'desde'), True, '28/09/2026'),
        Columna('termino', ('fecha_termino', 'fin', 'hasta', 'fecha_fin'), True, '02/10/2026'),
        Columna('actividad', ('tipo', 'trabajo'), False, '', 'Opcional: escarpe o corte'),
        Columna('zona', ('terraza',), False, '', 'Opcional: acceso, living o patio'),
        Columna('tarea', ('descripcion', 'nombre'), False, 'Excavación a máquina', 'Texto libre'),
    ]

    def validar(self, con, df, rev):
        terrenos = mapa_terrenos(con)
        c = {x.campo: x for x in self.columnas}
        for f in df.to_dict('records'):
            n = f['_fila']
            codigo = norm_terreno(valor(f, c['sitio']))
            ini, fin = norm_fecha(valor(f, c['inicio'])), norm_fecha(valor(f, c['termino']))
            act, zon = norm_actividad(valor(f, c['actividad'])), norm_zona(valor(f, c['zona']))
            if codigo in (None, VACIO) or codigo not in terrenos:
                rev.errores.append((n, f'Sitio "{valor(f, c["sitio"])}" no existe')); continue
            if ini in (None, VACIO) or fin in (None, VACIO):
                rev.errores.append((n, 'Fechas de inicio o término inválidas')); continue
            if fin < ini:
                rev.errores.append((n, 'El término es anterior al inicio')); continue
            if act is VACIO or zon is VACIO:
                rev.errores.append((n, 'Actividad o zona no reconocida')); continue
            rev.ops.append(dict(terreno_id=terrenos[codigo].id, actividad=act, zona=zon, inicio=ini, termino=fin,
                                texto=None if vacio(valor(f, c['tarea'])) else str(valor(f, c['tarea']))[:200]))
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
    ayuda = 'Actualiza el volumen proyectado (m³) y/o el estado de cada actividad. Celdas vacías no se modifican.'
    columnas = [
        Columna('sitio', ('sector', 'terreno'), True, '15'),
        Columna('actividad', ('tipo',), True, 'corte', 'escarpe o corte'),
        Columna('volumen_proyectado_m3', ('proyectado', 'volumen', 'm3'), False, '180'),
        Columna('estado', (), False, 'en proceso', 'sin intervenir / en proceso / terminado'),
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
            if tipo in (None, VACIO):
                rev.errores.append((n, 'Actividad no reconocida (escarpe o corte)')); continue
            if vol is VACIO or (vol is not None and vol < 0):
                rev.errores.append((n, 'Volumen inválido')); continue
            if est is VACIO:
                rev.errores.append((n, 'Estado no reconocido')); continue
            a = acts[(terrenos[codigo].id, tipo)]
            rev.ops.append(dict(id=a.id, volumen=a.volumen_proyectado_m3 if vol is None else vol,
                                estado=est or a.estado, cambio_estado=bool(est and est != a.estado)))
        rev.resumen = dict(actividades_actualizadas=len(rev.ops),
                           m3_proyectados=round(sum(o['volumen'] for o in rev.ops), 1))

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
        Columna('sitio', ('sector', 'terreno'), True, '15'),
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


class Ajustes(TipoArchivo):
    id = 'ajustes'
    titulo = 'Ajustes manuales de volumen (topografía)'
    modo = 'SUMA'
    ayuda = 'Suma (o resta con número negativo) m³ retirados a una actividad, por ejemplo tras una topografía.'
    columnas = [
        Columna('sitio', ('sector', 'terreno'), True, '15'),
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


TIPOS = {t.id: t for t in (Viajes(), Gantt(), Volumenes(), Entregas(), Ajustes())}
DESHACIBLES = {'viajes': T.viaje, 'ajustes': T.ajuste, 'gantt': T.gantt}


def revisar(motor, tipo, contenido, nombre=''):
    t = TIPOS[tipo]
    rev = Revision()
    try:
        df = leer_tabla(contenido, nombre)
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
