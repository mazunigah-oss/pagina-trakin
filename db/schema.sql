-- Plataforma de seguimiento de movimiento de tierra
-- Esquema PostgreSQL (compatible con Supabase). Ver docs/01-analisis-requerimientos.md

create type tipo_terreno   as enum ('sitio', 'edificio', 'pasaje', 'tramo_calle');
create type tipo_actividad as enum ('escarpe', 'corte');
create type estado_avance  as enum ('sin_intervenir', 'en_proceso', 'terminado');
create type tipo_zona      as enum ('acceso', 'living', 'fondo_patio', 'unica');
create type estado_entrega as enum ('sin_intervenir', 'en_proceso', 'entregado');

-- Plano base (imagen subida por el admin)
create table plano (
  id          bigint generated always as identity primary key,
  imagen_url  text not null,
  ancho_px    int  not null,
  alto_px     int  not null,
  vigente     boolean not null default true,
  creado_en   timestamptz not null default now()
);

-- Sitios, edificios, pasajes y tramos de calle
create table terreno (
  id            bigint generated always as identity primary key,
  codigo        text unique not null,           -- S-01..S-48, ED-A, P-1, T-1
  tipo          tipo_terreno not null,
  nombre        text,
  poligono      jsonb,                          -- [[x,y], ...] en px del plano
  observaciones text
);

-- Escarpe y corte de cada terreno (en edificios, corte = subterráneo)
create table actividad (
  id                    bigint generated always as identity primary key,
  terreno_id            bigint not null references terreno on delete cascade,
  tipo                  tipo_actividad not null,
  volumen_proyectado_m3 numeric(12,2) not null default 0,
  estado                estado_avance not null default 'sin_intervenir',
  unique (terreno_id, tipo)
);

-- Entregas: 3 por sitio (acceso, living, fondo_patio), 1 ('unica') para el resto
create table entrega (
  id            bigint generated always as identity primary key,
  terreno_id    bigint not null references terreno on delete cascade,
  zona          tipo_zona not null,
  poligono      jsonb,
  estado        estado_entrega not null default 'sin_intervenir',
  fecha_entrega date,
  unique (terreno_id, zona)
);

-- Historial de cambios de estado (para ver la evolución en el tiempo)
create table historial_estado (
  id          bigint generated always as identity primary key,
  entrega_id  bigint references entrega on delete cascade,
  actividad_id bigint references actividad on delete cascade,
  estado      text not null,
  fecha       date not null default current_date,
  creado_en   timestamptz not null default now(),
  check (num_nonnulls(entrega_id, actividad_id) = 1)
);

-- Maestro de camiones
create table camion (
  id            bigint generated always as identity primary key,
  patente       text unique not null,
  id_tarjeta    text unique,
  capacidad_m3  numeric(6,2) not null,
  empresa       text,
  activo        boolean not null default true
);

-- Viajes de salida (importados del CSV diario de la máquina de tarjetas)
create table viaje (
  id              bigint generated always as identity primary key,
  salida_en       timestamptz not null,
  patente         text not null,
  camion_id       bigint references camion,
  volumen_m3      numeric(6,2) not null,         -- capacidad del camión al importar
  terreno_id      bigint references terreno,     -- null = viaje "general" (se prorratea)
  actividad       tipo_actividad,
  archivo_origen  text,
  unique (patente, salida_en)                    -- evita duplicados al re-subir un CSV
);
create index on viaje (salida_en);

-- Ajustes manuales de volumen (ej. topografía)
create table ajuste_volumen (
  id           bigint generated always as identity primary key,
  actividad_id bigint not null references actividad on delete cascade,
  fecha        date not null,
  volumen_m3   numeric(12,2) not null,           -- puede ser negativo
  motivo       text
);

-- Carta Gantt (importada desde Excel, por zona de cada sitio)
create table tarea_gantt (
  id            bigint generated always as identity primary key,
  texto         text not null,                   -- fila original del Excel
  terreno_id    bigint references terreno,
  entrega_id    bigint references entrega,
  actividad_id  bigint references actividad,
  inicio        date not null,
  termino       date not null,
  check (termino >= inicio)
);
