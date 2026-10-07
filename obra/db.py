"""Base de datos (SQLAlchemy Core): funciona con SQLite local o PostgreSQL en la nube."""
import json
from pathlib import Path

from sqlalchemy import (Column, Float, ForeignKey, Integer, MetaData, String, Table, Text, UniqueConstraint,
                        create_engine, event, func, insert, select)

RAIZ = Path(__file__).resolve().parent.parent
VERSION = '2026-10-07 c'  # se muestra en la app para saber qué versión está publicada
GEOMETRIA = RAIZ / 'data' / 'geometria.json'
# escarpe y corte (excavación) de cada sitio; adicional = volumen extra a botadero
TIPOS_ACTIVIDAD = ('escarpe', 'corte', 'adicional')

meta = MetaData()

terreno = Table(
    'terreno', meta,
    Column('id', Integer, primary_key=True),
    Column('codigo', String(10), unique=True, nullable=False),   # S-01..S-48, ED-1
    Column('tipo', String(12), nullable=False),                  # sitio | edificio
    Column('numero', Integer),
    Column('nombre', String(40)),
    Column('modelo', String(10)),
    Column('etapa', Integer),
    Column('area_m2', Float),
)

zona = Table(
    'zona', meta,  # terrazas que se entregan: acceso, living, fondo_patio (unica en edificios)
    Column('id', Integer, primary_key=True),
    Column('terreno_id', Integer, ForeignKey('terreno.id', ondelete='CASCADE'), nullable=False),
    Column('zona', String(12), nullable=False),
    Column('poligono', Text),
    Column('area_m2', Float),
    Column('estado', String(16), nullable=False, default='sin_intervenir'),  # sin_intervenir|en_proceso|entregado
    Column('fecha_entrega', String(10)),
    UniqueConstraint('terreno_id', 'zona'),
)

actividad = Table(
    'actividad', meta,  # escarpe y corte de cada terreno
    Column('id', Integer, primary_key=True),
    Column('terreno_id', Integer, ForeignKey('terreno.id', ondelete='CASCADE'), nullable=False),
    Column('tipo', String(10), nullable=False),  # escarpe | corte | adicional
    Column('volumen_proyectado_m3', Float, nullable=False, default=0),
    Column('estado', String(16), nullable=False, default='sin_intervenir'),  # sin_intervenir|en_proceso|terminado
    UniqueConstraint('terreno_id', 'tipo'),
)

carga = Table(
    'carga', meta,  # cada archivo subido
    Column('id', Integer, primary_key=True),
    Column('tipo', String(20), nullable=False),
    Column('archivo', String(200)),
    Column('resumen', Text),
    Column('creado_en', String(19), nullable=False),
)

viaje = Table(
    'viaje', meta,  # filas del CSV de la máquina de tickets
    Column('id', Integer, primary_key=True),
    Column('ticket', String(30), nullable=False),
    Column('fecha', String(10), nullable=False),     # YYYY-MM-DD
    Column('hora', String(5), nullable=False),
    Column('patente', String(12), nullable=False),
    Column('volumen_m3', Float, nullable=False),     # negativo en anulaciones
    Column('sector', String(20)),                    # texto original de la máquina
    Column('terreno_id', Integer, ForeignKey('terreno.id')),  # null = general (se prorratea)
    Column('tipo', String(10)),                      # escarpe | corte | null
    Column('estado', String(12), nullable=False),    # VALIDO | ANULACION
    Column('carga_id', Integer, ForeignKey('carga.id')),
    UniqueConstraint('ticket', 'estado'),
)

ajuste = Table(
    'ajuste', meta,
    Column('id', Integer, primary_key=True),
    Column('actividad_id', Integer, ForeignKey('actividad.id', ondelete='CASCADE'), nullable=False),
    Column('fecha', String(10), nullable=False),
    Column('volumen_m3', Float, nullable=False),
    Column('motivo', String(200)),
    Column('carga_id', Integer, ForeignKey('carga.id')),
)

gantt = Table(
    'gantt', meta,  # programa: movimiento de tierra por sitio (o entrega de una terraza)
    Column('id', Integer, primary_key=True),
    Column('terreno_id', Integer, ForeignKey('terreno.id', ondelete='CASCADE'), nullable=False),
    Column('actividad', String(10)),  # escarpe | corte | null = movimiento de tierra completo
    Column('zona', String(12)),       # si viene, es la entrega de esa terraza
    Column('inicio', String(10), nullable=False),
    Column('termino', String(10), nullable=False),
    Column('texto', String(200)),
    Column('carga_id', Integer, ForeignKey('carga.id')),
)

relleno = Table(
    'relleno', meta,  # rellenos compactados en capas de ~0,25 m y sus densidades
    Column('id', Integer, primary_key=True),
    Column('terreno_id', Integer, ForeignKey('terreno.id', ondelete='CASCADE'), nullable=False),
    Column('corte_m3', Float),
    Column('relleno_m3', Float),
    Column('relleno_pendiente', Integer, nullable=False, default=0),  # registrado como "P"
    Column('capas_acceso', Integer),
    Column('capas_living', Integer),
    Column('capas_calicata', Integer),
    Column('capas_pendiente', Integer, nullable=False, default=0),
    Column('entrega', String(20)),
    Column('carga_id', Integer, ForeignKey('carga.id')),
)

hito = Table(
    'hito', meta,
    Column('id', Integer, primary_key=True),
    Column('nombre', String(120), nullable=False),
    Column('fecha', String(10), nullable=False),
    Column('carga_id', Integer, ForeignKey('carga.id')),
)

historial = Table(
    'historial', meta,
    Column('id', Integer, primary_key=True),
    Column('tabla', String(12), nullable=False),
    Column('ref_id', Integer, nullable=False),
    Column('estado', String(16), nullable=False),
    Column('fecha', String(10), nullable=False),
)


def _adaptar_numpy():
    """psycopg2 no entiende los números de numpy/pandas: np.float64 se envía como el texto
    'np.float64(1.5)' (PostgreSQL responde 'schema "np" does not exist') y np.int64 no se puede enviar.
    Se registran para que se envíen como números normales."""
    try:
        import numpy as np
        from psycopg2.extensions import AsIs, register_adapter
    except ImportError:
        return

    def numero(v):
        return AsIs('NULL') if v != v else AsIs(repr(v.item()))

    for tipo in (np.float64, np.float32, np.int64, np.int32, np.int16, np.int8, np.uint64, np.uint32):
        register_adapter(tipo, numero)
    register_adapter(np.bool_, lambda v: AsIs('TRUE' if v else 'FALSE'))


_adaptar_numpy()


def _normalizar_url(url):
    # Supabase/Neon/Heroku entregan postgres:// ; SQLAlchemy necesita postgresql+psycopg2://
    if url.startswith('postgres://'):
        url = 'postgresql://' + url[len('postgres://'):]
    if url.startswith('postgresql://'):
        url = 'postgresql+psycopg2://' + url[len('postgresql://'):]
    return url


def crear_motor(url=None):
    url = _normalizar_url(url) if url else f"sqlite:///{RAIZ / 'data' / 'obra.db'}"
    motor = create_engine(url, pool_pre_ping=True, future=True)
    if motor.dialect.name == 'postgresql':
        _adaptar_numpy()
    if motor.dialect.name == 'sqlite':
        @event.listens_for(motor, 'connect')
        def _fk(con, _):
            con.execute('pragma foreign_keys = on')
    meta.create_all(motor)
    sembrar(motor)
    return motor


def sembrar(motor):
    """Carga inicial de sitios, terrazas y actividades desde data/geometria.json."""
    with motor.begin() as con:
        if con.execute(select(func.count()).select_from(terreno)).scalar():
            # bases ya creadas: agregar los tipos de actividad nuevos que falten
            existentes = {(r.terreno_id, r.tipo) for r in con.execute(select(actividad.c.terreno_id, actividad.c.tipo))}
            faltan = [dict(terreno_id=tid, tipo=x, volumen_proyectado_m3=0, estado='sin_intervenir')
                      for (tid,) in con.execute(select(terreno.c.id)) for x in TIPOS_ACTIVIDAD
                      if (tid, x) not in existentes]
            if faltan:
                con.execute(insert(actividad), faltan)
            return
        geo = json.loads(GEOMETRIA.read_text())
        ids = {}
        for t in geo['terrenos']:
            numero = int(t['codigo'].split('-')[1])
            r = con.execute(insert(terreno).values(
                codigo=t['codigo'], tipo=t['tipo'], numero=numero, nombre=t['nombre'],
                modelo=t.get('modelo'), etapa=t.get('etapa'), area_m2=t.get('area_m2')))
            ids[t['codigo']] = r.inserted_primary_key[0]
            con.execute(insert(actividad), [dict(terreno_id=ids[t['codigo']], tipo=x, volumen_proyectado_m3=0,
                                                 estado='sin_intervenir') for x in TIPOS_ACTIVIDAD])
        con.execute(insert(zona), [dict(terreno_id=ids[z['terreno']], zona=z['zona'], poligono=json.dumps(z['puntos']),
                                        area_m2=z['area_m2'], estado='sin_intervenir') for z in geo['zonas']])


def cargar_geometria():
    return json.loads(GEOMETRIA.read_text())
