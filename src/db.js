const path = require('node:path');
const fs = require('node:fs');
const Database = require('better-sqlite3');

const GEOMETRIA = path.join(__dirname, '..', 'data', 'geometria.json');

const ESQUEMA = `
create table if not exists terreno (
  id            integer primary key,
  codigo        text unique not null,
  tipo          text not null check (tipo in ('sitio','edificio','pasaje','tramo_calle')),
  nombre        text,
  modelo        text,
  observaciones text
);

create table if not exists actividad (
  id                    integer primary key,
  terreno_id            integer not null references terreno on delete cascade,
  tipo                  text not null check (tipo in ('escarpe','corte')),
  volumen_proyectado_m3 real not null default 0,
  estado                text not null default 'sin_intervenir'
                        check (estado in ('sin_intervenir','en_proceso','terminado')),
  unique (terreno_id, tipo)
);

create table if not exists entrega (
  id            integer primary key,
  terreno_id    integer not null references terreno on delete cascade,
  zona          text not null check (zona in ('acceso','living','fondo_patio','unica')),
  poligono      text,
  area_m2       real,
  estado        text not null default 'sin_intervenir'
                check (estado in ('sin_intervenir','en_proceso','entregado')),
  fecha_entrega text,
  unique (terreno_id, zona)
);

create table if not exists camion (
  id           integer primary key,
  patente      text unique not null,
  id_tarjeta   text unique,
  capacidad_m3 real not null,
  empresa      text,
  activo       integer not null default 1
);

-- Cada archivo subido queda registrado; viajes y ajustes guardan de qué carga vienen
-- para poder deshacer una carga completa.
create table if not exists carga (
  id        integer primary key,
  tipo      text not null,
  archivo   text,
  resumen   text,
  creado_en text not null default (datetime('now'))
);

create table if not exists viaje (
  id          integer primary key,
  salida_en   text not null,               -- 'YYYY-MM-DD HH:MM' hora local de Chile
  patente     text not null,
  camion_id   integer references camion,
  volumen_m3  real not null,               -- capacidad del camión al importar
  terreno_id  integer references terreno,  -- null = viaje general (se prorratea)
  actividad   text check (actividad in ('escarpe','corte')),
  carga_id    integer references carga on delete cascade,
  unique (patente, salida_en)
);
create index if not exists viaje_salida on viaje (salida_en);

create table if not exists ajuste_volumen (
  id           integer primary key,
  actividad_id integer not null references actividad on delete cascade,
  fecha        text not null,
  volumen_m3   real not null,
  motivo       text,
  carga_id     integer references carga on delete cascade
);

create table if not exists tarea_gantt (
  id          integer primary key,
  texto       text not null,
  entrega_id  integer references entrega on delete cascade,
  actividad_id integer references actividad on delete cascade,
  inicio      text not null,
  termino     text not null,
  carga_id    integer references carga on delete cascade
);

create table if not exists historial_estado (
  id           integer primary key,
  entrega_id   integer references entrega on delete cascade,
  actividad_id integer references actividad on delete cascade,
  estado       text not null,
  fecha        text not null,
  creado_en    text not null default (datetime('now'))
);
`;

function sembrar(db) {
  if (db.prepare('select count(*) n from terreno').get().n > 0) return;
  const geo = JSON.parse(fs.readFileSync(GEOMETRIA, 'utf8'));
  const insTerreno = db.prepare(
    'insert into terreno (codigo, tipo, nombre, modelo) values (@codigo, @tipo, @nombre, @modelo)'
  );
  const insActividad = db.prepare('insert into actividad (terreno_id, tipo) values (?, ?)');
  const insEntrega = db.prepare(
    'insert into entrega (terreno_id, zona, poligono, area_m2) values (?, ?, ?, ?)'
  );
  db.transaction(() => {
    const ids = {};
    for (const t of geo.terrenos) {
      ids[t.codigo] = insTerreno.run(t).lastInsertRowid;
      insActividad.run(ids[t.codigo], 'escarpe');
      insActividad.run(ids[t.codigo], 'corte');
    }
    for (const z of geo.zonas) {
      insEntrega.run(ids[z.terreno], z.zona, JSON.stringify(z.puntos), z.area_m2);
    }
  })();
}

function abrir(archivo = process.env.DB_PATH || path.join(__dirname, '..', 'data', 'obra.db')) {
  const db = new Database(archivo);
  db.pragma('journal_mode = WAL');
  db.pragma('foreign_keys = ON');
  db.exec(ESQUEMA);
  sembrar(db);
  return db;
}

module.exports = { abrir, GEOMETRIA };
