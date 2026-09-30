const ZONA_HORARIA = 'America/Santiago';

// Fecha local de Chile en formato YYYY-MM-DD
function hoyChile(fecha = new Date()) {
  return new Intl.DateTimeFormat('en-CA', { timeZone: ZONA_HORARIA }).format(fecha);
}

// Reparte `volumen` entre `candidatas` en proporción a su volumen proyectado
// (en partes iguales si ninguna tiene proyectado).
function repartir(volumen, candidatas, acumulado) {
  if (!candidatas.length || !volumen) return;
  const total = candidatas.reduce((s, a) => s + a.volumen_proyectado_m3, 0);
  for (const a of candidatas) {
    const peso = total > 0 ? a.volumen_proyectado_m3 / total : 1 / candidatas.length;
    acumulado[a.id] = (acumulado[a.id] || 0) + volumen * peso;
  }
}

// Volumen retirado por actividad = viajes directos + viajes del terreno sin actividad
// + prorrateo de viajes generales + ajustes manuales.
// Viajes generales: se reparten entre las actividades en proceso; si no hay,
// entre las no terminadas; si todas están terminadas, entre todas.
function volumenesRetirados(db) {
  const actividades = db.prepare('select * from actividad').all();
  const porTerreno = {};
  for (const a of actividades) (porTerreno[a.terreno_id] ||= []).push(a);

  const directo = {};
  const prorrateo = {};
  const filas = db
    .prepare(
      `select terreno_id, actividad, sum(volumen_m3) m3 from viaje
       group by terreno_id, actividad`
    )
    .all();

  let general = 0;
  for (const f of filas) {
    if (f.terreno_id == null) {
      general += f.m3;
    } else if (f.actividad) {
      const a = porTerreno[f.terreno_id].find((x) => x.tipo === f.actividad);
      directo[a.id] = (directo[a.id] || 0) + f.m3;
    } else {
      repartir(f.m3, porTerreno[f.terreno_id], directo);
    }
  }

  let candidatas = actividades.filter((a) => a.estado === 'en_proceso');
  if (!candidatas.length) candidatas = actividades.filter((a) => a.estado !== 'terminado');
  if (!candidatas.length) candidatas = actividades;
  repartir(general, candidatas, prorrateo);

  const ajustes = {};
  for (const f of db
    .prepare('select actividad_id, sum(volumen_m3) m3 from ajuste_volumen group by actividad_id')
    .all()) {
    ajustes[f.actividad_id] = f.m3;
  }

  const redondo = (x) => Math.round((x || 0) * 10) / 10;
  return actividades.map((a) => {
    const retirado = (directo[a.id] || 0) + (prorrateo[a.id] || 0) + (ajustes[a.id] || 0);
    return {
      ...a,
      directo_m3: redondo(directo[a.id]),
      prorrateo_m3: redondo(prorrateo[a.id]),
      ajustes_m3: redondo(ajustes[a.id]),
      retirado_m3: redondo(retirado),
      avance: a.volumen_proyectado_m3 > 0 ? Math.min(retirado / a.volumen_proyectado_m3, 9.99) : null,
    };
  });
}

const RANGO = { sin_intervenir: 0, en_proceso: 1, entregado: 2, terminado: 2 };

// Estado que debería tener un elemento a la fecha `hoy` según sus tareas Gantt.
function estadoProgramado(tareas, hoy, estadoFinal = 'entregado') {
  if (!tareas.length) return null;
  const inicio = tareas.map((t) => t.inicio).sort()[0];
  const termino = tareas.map((t) => t.termino).sort().at(-1);
  if (hoy < inicio) return { estado: 'sin_intervenir', inicio, termino };
  if (hoy > termino) return { estado: estadoFinal, inicio, termino };
  return { estado: 'en_proceso', inicio, termino };
}

function comparar(real, programado) {
  if (!programado) return null;
  const d = RANGO[real] - RANGO[programado];
  return d < 0 ? 'atrasado' : d > 0 ? 'adelantado' : 'al_dia';
}

function estadoGeneral(db, hoy = hoyChile()) {
  const terrenos = db.prepare('select * from terreno order by id').all();
  const actividades = volumenesRetirados(db);
  const tareas = db.prepare('select * from tarea_gantt').all();
  const tareasPor = (campo, id) => tareas.filter((t) => t[campo] === id);

  const entregas = db
    .prepare('select * from entrega order by terreno_id, id')
    .all()
    .map((e) => {
      const prog = estadoProgramado(tareasPor('entrega_id', e.id), hoy, 'entregado');
      return {
        ...e,
        poligono: JSON.parse(e.poligono || '[]'),
        programado: prog,
        comparacion: comparar(e.estado, prog?.estado),
      };
    });

  for (const a of actividades) {
    a.programado = estadoProgramado(tareasPor('actividad_id', a.id), hoy, 'terminado');
    a.comparacion = comparar(a.estado, a.programado?.estado);
  }

  return { hoy, terrenos, actividades, entregas, resumen: resumenDia(db, hoy, actividades) };
}

function resumenDia(db, dia, actividades) {
  const viajesHoy = db
    .prepare(
      `select coalesce(t.codigo, 'General') origen, count(*) viajes, sum(v.volumen_m3) m3
       from viaje v left join terreno t on t.id = v.terreno_id
       where substr(v.salida_en, 1, 10) = ?
       group by origen order by m3 desc`
    )
    .all(dia);
  const camiones = db
    .prepare(`select count(distinct patente) n from viaje where substr(salida_en,1,10) = ?`)
    .get(dia).n;
  const porDia = db
    .prepare(
      `select substr(salida_en,1,10) dia, count(*) viajes, sum(volumen_m3) m3
       from viaje where substr(salida_en,1,10) > date(?, '-30 day') and substr(salida_en,1,10) <= ?
       group by dia order by dia`
    )
    .all(dia, dia);
  const ultimoDia = db.prepare('select max(substr(salida_en,1,10)) d from viaje').get().d;
  const total = actividades.reduce((s, a) => s + a.retirado_m3, 0);
  const proyectado = actividades.reduce((s, a) => s + a.volumen_proyectado_m3, 0);
  return {
    dia,
    ultimo_dia_con_viajes: ultimoDia,
    viajes: viajesHoy.reduce((s, f) => s + f.viajes, 0),
    camiones,
    m3: viajesHoy.reduce((s, f) => s + f.m3, 0),
    por_origen: viajesHoy,
    ultimos_30_dias: porDia,
    acumulado_m3: Math.round(total * 10) / 10,
    proyectado_m3: proyectado,
  };
}

module.exports = { hoyChile, volumenesRetirados, estadoProgramado, comparar, estadoGeneral, resumenDia };
