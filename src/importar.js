// Carga de archivos (CSV o Excel) para alimentar la plataforma.
// Cada tipo de archivo define sus columnas y si SUMA (agrega registros nuevos),
// ACTUALIZA (modifica los existentes) o REEMPLAZA (borra lo anterior y carga de nuevo).
const ExcelJS = require('exceljs');
const { parse } = require('csv-parse/sync');
const { hoyChile } = require('./calculos');

// ---------- lectura de archivos ----------

function normalizarClave(s) {
  return String(s ?? '')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[°º.#]/g, '')
    .trim()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_|_$/g, '');
}

function decodificar(buffer) {
  const utf8 = buffer.toString('utf8').replace(/^﻿/, '');
  // Si no es UTF-8 válido (típico de CSV exportados por Excel en Windows) se usa latin1
  return utf8.includes('�') ? buffer.toString('latin1') : utf8;
}

function leerCsv(buffer) {
  const texto = decodificar(buffer);
  const primera = texto.split(/\r?\n/, 1)[0];
  const delimitador = [';', ',', '\t'].sort(
    (a, b) => primera.split(b).length - primera.split(a).length
  )[0];
  return parse(texto, {
    delimiter: delimitador,
    skip_empty_lines: true,
    relax_column_count: true,
    trim: true,
  });
}

function valorCelda(v) {
  if (v == null) return '';
  if (v instanceof Date) return v;
  if (typeof v === 'object') {
    if ('result' in v) return valorCelda(v.result);
    if ('richText' in v) return v.richText.map((r) => r.text).join('');
    if ('text' in v) return v.text;
  }
  return v;
}

async function leerExcel(buffer) {
  const libro = new ExcelJS.Workbook();
  await libro.xlsx.load(buffer);
  const hoja = libro.worksheets.find((h) => h.actualRowCount > 0) || libro.worksheets[0];
  const filas = [];
  hoja.eachRow({ includeEmpty: false }, (fila) => {
    const valores = [];
    for (let c = 1; c <= fila.cellCount; c++) valores.push(valorCelda(fila.getCell(c).value));
    filas.push(valores);
  });
  return filas;
}

// Devuelve [{ _fila, campo: valor }] usando la primera fila con datos como encabezado
async function leerTabla(buffer, nombre = '') {
  const esExcel = /\.xlsx$/i.test(nombre) || buffer.slice(0, 2).toString() === 'PK';
  const filas = esExcel ? await leerExcel(buffer) : leerCsv(buffer);
  const inicio = filas.findIndex((f) => f.some((v) => String(v).trim() !== ''));
  if (inicio < 0) return { encabezados: [], filas: [] };
  const encabezados = filas[inicio].map(normalizarClave);
  const datos = [];
  for (let i = inicio + 1; i < filas.length; i++) {
    if (!filas[i].some((v) => String(v ?? '').trim() !== '')) continue;
    const obj = { _fila: i + 1 };
    encabezados.forEach((k, j) => k && (obj[k] = filas[i][j] ?? ''));
    datos.push(obj);
  }
  return { encabezados, filas: datos };
}

// ---------- normalización de valores ----------

const MESES = {
  enero: 1, febrero: 2, marzo: 3, abril: 4, mayo: 5, junio: 6, julio: 7,
  agosto: 8, septiembre: 9, setiembre: 9, octubre: 10, noviembre: 11, diciembre: 12,
};
const dos = (n) => String(n).padStart(2, '0');

function fechaDesdeExcel(serial) {
  const d = new Date(Math.round((serial - 25569) * 86400000));
  return d;
}

function normFecha(v) {
  if (v === '' || v == null) return null;
  if (typeof v === 'number') v = fechaDesdeExcel(v);
  if (v instanceof Date) {
    return `${v.getUTCFullYear()}-${dos(v.getUTCMonth() + 1)}-${dos(v.getUTCDate())}`;
  }
  const s = String(v).trim();
  let m = s.match(/^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})/);
  if (m) return `${m[1]}-${dos(m[2])}-${dos(m[3])}`;
  m = s.match(/^(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})/);
  if (m) {
    const anio = m[3].length === 2 ? '20' + m[3] : m[3];
    return `${anio}-${dos(m[2])}-${dos(m[1])}`;
  }
  return undefined; // inválida
}

function normHora(v) {
  if (v === '' || v == null) return null;
  if (typeof v === 'number') {
    const min = Math.round((v % 1) * 1440);
    return `${dos(Math.floor(min / 60))}:${dos(min % 60)}`;
  }
  if (v instanceof Date) return `${dos(v.getUTCHours())}:${dos(v.getUTCMinutes())}`;
  const m = String(v).match(/(\d{1,2})[:.](\d{2})/);
  if (!m || +m[1] > 23 || +m[2] > 59) return undefined;
  return `${dos(m[1])}:${m[2]}`;
}

function normNumero(v) {
  if (v === '' || v == null) return null;
  if (typeof v === 'number') return v;
  const s = String(v).trim().replace(/\s/g, '');
  // "1.234,5" -> 1234.5 ; "12,5" -> 12.5 ; "12.5" -> 12.5
  const limpio = s.includes(',') ? s.replace(/\./g, '').replace(',', '.') : s;
  const n = Number(limpio);
  return Number.isFinite(n) ? n : undefined;
}

const normPatente = (v) => String(v ?? '').toUpperCase().replace(/[^A-Z0-9]/g, '');
const normTexto = (v) => normalizarClave(v).replace(/_/g, ' ');

function normZona(v) {
  const s = normTexto(v);
  if (!s) return null;
  if (/acceso/.test(s)) return 'acceso';
  if (/living|casa/.test(s)) return 'living';
  if (/patio|fondo/.test(s)) return 'fondo_patio';
  if (/unica|total|completo/.test(s)) return 'unica';
  return undefined;
}

function normEstado(v, final = 'entregado') {
  const s = normTexto(v);
  if (!s) return null;
  if (/sin|no inter|pendiente|no tocado/.test(s)) return 'sin_intervenir';
  if (/proceso|curso|ejecucion/.test(s)) return 'en_proceso';
  if (/entregad|listo|termina|complet/.test(s)) return final;
  return undefined;
}

function normActividad(v) {
  const s = normTexto(v);
  if (!s) return null;
  if (/escarpe/.test(s)) return 'escarpe';
  if (/corte|subterr|excav/.test(s)) return 'corte';
  return undefined;
}

// "15", "S-15", "Sitio 15", "ED-1", "Edificio 1" -> código de terreno
function normTerreno(v) {
  const s = normTexto(v);
  if (!s || s === 'general') return null;
  let m = s.match(/^(?:s|sitio|lote)?\s*(\d{1,2})$/);
  if (m) return `S-${dos(+m[1])}`;
  m = s.match(/^(?:ed|edificio)\s*(\d+)$/);
  if (m) return `ED-${+m[1]}`;
  return String(v).trim().toUpperCase();
}

// Busca "sitio 15", "edificio 2", zona y actividad dentro de un texto libre
function leerTextoTarea(texto) {
  const s = normTexto(texto);
  const sitio = s.match(/sitio\s*(\d{1,2})/);
  const edificio = s.match(/edificio\s*(\d+)/);
  return {
    terreno: sitio ? `S-${dos(+sitio[1])}` : edificio ? `ED-${+edificio[1]}` : null,
    zona: normZona(s.match(/acceso|living|casa|patio/)?.[0]) || null,
    actividad: normActividad(s.match(/escarpe|corte|subterr\w*|excav\w*/)?.[0]) || null,
  };
}

// "semana del 15 al 20 de septiembre" / "15 al 20 de septiembre de 2026"
// / "29 de septiembre al 3 de octubre"
function leerSemana(texto, anioBase = +hoyChile().slice(0, 4)) {
  const s = normTexto(texto);
  const m = s.match(/(\d{1,2})(?:\s+de\s+([a-z]+))?\s+(?:al|a)\s+(\d{1,2})\s+de\s+([a-z]+)(?:\s+(?:de|del)?\s*(\d{4}))?/);
  if (!m || !MESES[m[4]] || (m[2] && !MESES[m[2]])) return null;
  const anio = +(m[5] || anioBase);
  const mesFin = MESES[m[4]];
  const mesIni = m[2] ? MESES[m[2]] : mesFin;
  const anioIni = mesIni > mesFin ? anio - 1 : anio;
  return {
    inicio: `${anioIni}-${dos(mesIni)}-${dos(m[1])}`,
    termino: `${anio}-${dos(mesFin)}-${dos(m[3])}`,
  };
}

// ---------- definición de cada tipo de archivo ----------

function campos(fila, definicion) {
  const out = {};
  for (const col of definicion.columnas) {
    const clave = [col.campo, ...(col.alias || [])].find((a) => a in fila);
    out[col.campo] = clave ? fila[clave] : '';
  }
  return out;
}

function mapaTerrenos(db) {
  return Object.fromEntries(db.prepare('select id, codigo, tipo from terreno').all().map((t) => [t.codigo, t]));
}

const TIPOS = {
  viajes: {
    titulo: 'Salidas de camiones (CSV diario de la máquina de tarjetas)',
    modo: 'suma',
    ayuda:
      'Cada fila es un viaje de salida. El volumen es la capacidad del camión registrada en el maestro de camiones. ' +
      'Las filas que ya estaban cargadas (misma patente, fecha y hora) se omiten, así que se puede subir el mismo archivo dos veces sin duplicar. ' +
      'Si no se indica sitio, el viaje queda como "General" y se reparte proporcionalmente.',
    columnas: [
      { campo: 'fecha', alias: ['fecha_salida', 'dia', 'fecha_hora', 'fechahora'], requerido: true, ejemplo: '29-09-2026' },
      { campo: 'hora', alias: ['hora_salida', 'hora_de_salida'], ejemplo: '08:15', descripcion: 'Opcional si la fecha ya incluye la hora' },
      { campo: 'patente', alias: ['placa', 'ppu', 'camion'], ejemplo: 'ABCD12', descripcion: 'Patente o tarjeta (al menos una)' },
      { campo: 'tarjeta', alias: ['id_tarjeta', 'n_tarjeta', 'codigo_tarjeta', 'tag'], ejemplo: '000123' },
      { campo: 'sitio', alias: ['terreno', 'origen'], ejemplo: '15', descripcion: 'Opcional: 15, S-15, ED-1 o vacío = General' },
      { campo: 'actividad', alias: ['trabajo'], ejemplo: 'escarpe', descripcion: 'Opcional: escarpe o corte' },
      { campo: 'volumen_m3', alias: ['m3', 'volumen', 'cantidad'], ejemplo: '', descripcion: 'Opcional: si viene, reemplaza la capacidad del camión' },
    ],
    validar(db, filas) {
      const terrenos = mapaTerrenos(db);
      const porPatente = Object.fromEntries(db.prepare('select * from camion').all().map((c) => [c.patente, c]));
      const porTarjeta = Object.fromEntries(
        db.prepare('select * from camion where id_tarjeta is not null').all().map((c) => [normPatente(c.id_tarjeta), c])
      );
      const existe = db.prepare('select 1 from viaje where patente = ? and salida_en = ?');
      const vistos = new Set();
      const ops = [], errores = [];
      let duplicadas = 0;
      for (const fila of filas) {
        const c = campos(fila, this);
        const err = (m) => errores.push({ fila: fila._fila, mensaje: m });
        const fecha = normFecha(c.fecha);
        let hora = normHora(c.hora);
        if (!hora && c.fecha instanceof Date && (c.fecha.getUTCHours() || c.fecha.getUTCMinutes())) hora = normHora(c.fecha);
        if (!hora && typeof c.fecha === 'string') hora = normHora(c.fecha.match(/\d{1,2}:\d{2}/)?.[0]);
        if (!fecha) { err(`Fecha inválida: "${c.fecha}"`); continue; }
        if (!hora) { err(`Hora inválida: "${c.hora}"`); continue; }
        const camion = porPatente[normPatente(c.patente)] || porTarjeta[normPatente(c.tarjeta)];
        const patente = camion?.patente || normPatente(c.patente);
        if (!patente) { err(`Tarjeta "${c.tarjeta}" no registrada en el maestro de camiones`); continue; }
        let volumen = normNumero(c.volumen_m3);
        if (volumen === undefined) { err(`Volumen inválido: "${c.volumen_m3}"`); continue; }
        if (volumen == null) volumen = camion?.capacidad_m3;
        if (volumen == null) { err(`Camión ${patente} no está en el maestro de camiones (sin capacidad)`); continue; }
        const codigo = normTerreno(c.sitio);
        if (codigo && !terrenos[codigo]) { err(`Sitio "${c.sitio}" no existe`); continue; }
        const actividad = normActividad(c.actividad);
        if (actividad === undefined) { err(`Actividad "${c.actividad}" no reconocida (escarpe o corte)`); continue; }
        const salida = `${fecha} ${hora}`;
        const clave = `${patente}|${salida}`;
        if (vistos.has(clave) || existe.get(patente, salida)) { duplicadas++; continue; }
        vistos.add(clave);
        ops.push({ salida, patente, camion_id: camion?.id ?? null, volumen, terreno_id: codigo ? terrenos[codigo].id : null, actividad });
      }
      const m3 = ops.reduce((s, o) => s + o.volumen, 0);
      return { ops, errores, resumen: { nuevas: ops.length, duplicadas, m3: Math.round(m3 * 10) / 10 } };
    },
    aplicar(db, ops, cargaId) {
      const ins = db.prepare(
        `insert into viaje (salida_en, patente, camion_id, volumen_m3, terreno_id, actividad, carga_id)
         values (?, ?, ?, ?, ?, ?, ?)`
      );
      for (const o of ops) ins.run(o.salida, o.patente, o.camion_id, o.volumen, o.terreno_id, o.actividad, cargaId);
    },
  },

  camiones: {
    titulo: 'Maestro de camiones',
    modo: 'actualiza',
    ayuda: 'Crea los camiones nuevos y actualiza los existentes (se identifican por patente).',
    columnas: [
      { campo: 'patente', alias: ['placa', 'ppu'], requerido: true, ejemplo: 'ABCD12' },
      { campo: 'capacidad_m3', alias: ['capacidad', 'm3', 'volumen'], requerido: true, ejemplo: '14' },
      { campo: 'tarjeta', alias: ['id_tarjeta', 'n_tarjeta', 'codigo_tarjeta', 'tag'], ejemplo: '000123' },
      { campo: 'empresa', alias: ['contratista', 'transportista'], ejemplo: 'Transportes Ejemplo' },
    ],
    validar(db, filas) {
      const existe = db.prepare('select id from camion where patente = ?');
      const ops = [], errores = [];
      let nuevas = 0, actualizadas = 0;
      for (const fila of filas) {
        const c = campos(fila, this);
        const patente = normPatente(c.patente);
        const capacidad = normNumero(c.capacidad_m3);
        if (!patente) { errores.push({ fila: fila._fila, mensaje: 'Falta la patente' }); continue; }
        if (!capacidad || capacidad <= 0) { errores.push({ fila: fila._fila, mensaje: `Capacidad inválida: "${c.capacidad_m3}"` }); continue; }
        existe.get(patente) ? actualizadas++ : nuevas++;
        ops.push({ patente, capacidad, tarjeta: String(c.tarjeta).trim() || null, empresa: String(c.empresa).trim() || null });
      }
      return { ops, errores, resumen: { nuevas, actualizadas } };
    },
    aplicar(db, ops) {
      const up = db.prepare(
        `insert into camion (patente, capacidad_m3, id_tarjeta, empresa) values (@patente, @capacidad, @tarjeta, @empresa)
         on conflict (patente) do update set capacidad_m3 = excluded.capacidad_m3,
           id_tarjeta = coalesce(excluded.id_tarjeta, id_tarjeta), empresa = coalesce(excluded.empresa, empresa)`
      );
      for (const o of ops) up.run(o);
    },
  },

  volumenes: {
    titulo: 'Volúmenes proyectados y estado de escarpe / corte',
    modo: 'actualiza',
    ayuda: 'Actualiza el volumen proyectado (m³) y/o el estado de cada actividad. Las celdas vacías no se modifican.',
    columnas: [
      { campo: 'sitio', alias: ['terreno'], requerido: true, ejemplo: '15' },
      { campo: 'actividad', alias: ['trabajo'], requerido: true, ejemplo: 'escarpe' },
      { campo: 'volumen_proyectado_m3', alias: ['volumen_proyectado', 'proyectado', 'm3', 'volumen'], ejemplo: '120' },
      { campo: 'estado', ejemplo: 'en proceso', descripcion: 'sin intervenir / en proceso / terminado' },
    ],
    validar(db, filas) {
      const terrenos = mapaTerrenos(db);
      const buscar = db.prepare('select * from actividad where terreno_id = ? and tipo = ?');
      const ops = [], errores = [];
      for (const fila of filas) {
        const c = campos(fila, this);
        const err = (m) => errores.push({ fila: fila._fila, mensaje: m });
        const t = terrenos[normTerreno(c.sitio)];
        const tipo = normActividad(c.actividad);
        const vol = normNumero(c.volumen_proyectado_m3);
        const estado = normEstado(c.estado, 'terminado');
        if (!t) { err(`Sitio "${c.sitio}" no existe`); continue; }
        if (!tipo) { err(`Actividad "${c.actividad}" no reconocida (escarpe o corte)`); continue; }
        if (vol === undefined || vol < 0) { err(`Volumen inválido: "${c.volumen_proyectado_m3}"`); continue; }
        if (estado === undefined) { err(`Estado "${c.estado}" no reconocido`); continue; }
        const a = buscar.get(t.id, tipo);
        ops.push({ id: a.id, vol: vol ?? a.volumen_proyectado_m3, estado: estado ?? a.estado, cambioEstado: estado && estado !== a.estado });
      }
      return { ops, errores, resumen: { actualizadas: ops.length } };
    },
    aplicar(db, ops) {
      const up = db.prepare('update actividad set volumen_proyectado_m3 = ?, estado = ? where id = ?');
      const hist = db.prepare('insert into historial_estado (actividad_id, estado, fecha) values (?, ?, ?)');
      for (const o of ops) {
        up.run(o.vol, o.estado, o.id);
        if (o.cambioEstado) hist.run(o.id, o.estado, hoyChile());
      }
    },
  },

  entregas: {
    titulo: 'Estado de entregas (acceso, living, fondo de patio)',
    modo: 'actualiza',
    ayuda: 'Actualiza el estado de cada zona. Para edificios la zona es "unica". Si se marca entregado sin fecha, se usa la fecha de hoy.',
    columnas: [
      { campo: 'sitio', alias: ['terreno'], requerido: true, ejemplo: '15' },
      { campo: 'zona', requerido: true, ejemplo: 'acceso', descripcion: 'acceso / living / fondo de patio / unica' },
      { campo: 'estado', requerido: true, ejemplo: 'entregado', descripcion: 'sin intervenir / en proceso / entregado' },
      { campo: 'fecha_entrega', alias: ['fecha'], ejemplo: '29-09-2026' },
    ],
    validar(db, filas) {
      const terrenos = mapaTerrenos(db);
      const buscar = db.prepare('select * from entrega where terreno_id = ? and zona = ?');
      const ops = [], errores = [];
      for (const fila of filas) {
        const c = campos(fila, this);
        const err = (m) => errores.push({ fila: fila._fila, mensaje: m });
        const t = terrenos[normTerreno(c.sitio)];
        if (!t) { err(`Sitio "${c.sitio}" no existe`); continue; }
        const zona = normZona(c.zona) || (t.tipo !== 'sitio' ? 'unica' : null);
        const estado = normEstado(c.estado);
        const fecha = normFecha(c.fecha_entrega);
        if (!zona) { err(`Zona "${c.zona}" no reconocida`); continue; }
        if (!estado) { err(`Estado "${c.estado}" no reconocido`); continue; }
        if (fecha === undefined) { err(`Fecha inválida: "${c.fecha_entrega}"`); continue; }
        const e = buscar.get(t.id, zona);
        if (!e) { err(`${t.codigo} no tiene zona "${zona}"`); continue; }
        ops.push({
          id: e.id, estado,
          fecha: estado === 'entregado' ? fecha || e.fecha_entrega || hoyChile() : null,
          cambio: estado !== e.estado,
        });
      }
      return { ops, errores, resumen: { actualizadas: ops.length, con_cambio_de_estado: ops.filter((o) => o.cambio).length } };
    },
    aplicar(db, ops) {
      const up = db.prepare('update entrega set estado = ?, fecha_entrega = ? where id = ?');
      const hist = db.prepare('insert into historial_estado (entrega_id, estado, fecha) values (?, ?, ?)');
      for (const o of ops) {
        up.run(o.estado, o.fecha, o.id);
        if (o.cambio) hist.run(o.id, o.estado, o.fecha || hoyChile());
      }
    },
  },

  ajustes: {
    titulo: 'Ajustes manuales de volumen (ej. topografía)',
    modo: 'suma',
    ayuda: 'Suma (o resta, con número negativo) m³ al volumen retirado de una actividad.',
    columnas: [
      { campo: 'sitio', alias: ['terreno'], requerido: true, ejemplo: '15' },
      { campo: 'actividad', requerido: true, ejemplo: 'corte' },
      { campo: 'fecha', requerido: true, ejemplo: '29-09-2026' },
      { campo: 'volumen_m3', alias: ['m3', 'volumen'], requerido: true, ejemplo: '35,5' },
      { campo: 'motivo', alias: ['observacion', 'comentario'], ejemplo: 'Levantamiento topográfico' },
    ],
    validar(db, filas) {
      const terrenos = mapaTerrenos(db);
      const buscar = db.prepare('select id from actividad where terreno_id = ? and tipo = ?');
      const ops = [], errores = [];
      for (const fila of filas) {
        const c = campos(fila, this);
        const err = (m) => errores.push({ fila: fila._fila, mensaje: m });
        const t = terrenos[normTerreno(c.sitio)];
        const tipo = normActividad(c.actividad);
        const fecha = normFecha(c.fecha);
        const vol = normNumero(c.volumen_m3);
        if (!t) { err(`Sitio "${c.sitio}" no existe`); continue; }
        if (!tipo) { err(`Actividad "${c.actividad}" no reconocida`); continue; }
        if (!fecha) { err(`Fecha inválida: "${c.fecha}"`); continue; }
        if (vol == null) { err(`Volumen inválido: "${c.volumen_m3}"`); continue; }
        ops.push({ actividad_id: buscar.get(t.id, tipo).id, fecha, vol, motivo: String(c.motivo).trim() || null });
      }
      return { ops, errores, resumen: { nuevas: ops.length, m3: ops.reduce((s, o) => s + o.vol, 0) } };
    },
    aplicar(db, ops, cargaId) {
      const ins = db.prepare('insert into ajuste_volumen (actividad_id, fecha, volumen_m3, motivo, carga_id) values (?, ?, ?, ?, ?)');
      for (const o of ops) ins.run(o.actividad_id, o.fecha, o.vol, o.motivo, cargaId);
    },
  },

  gantt: {
    titulo: 'Carta Gantt (programa por zona de cada sitio)',
    modo: 'reemplaza',
    ayuda:
      'Reemplaza el programa completo. El sitio y la zona se pueden indicar en columnas propias o dentro del texto de la tarea ' +
      '(ej. "Entrega acceso sitio 15"). Las fechas pueden venir en columnas inicio/término o en una columna "semana" ' +
      '(ej. "semana del 15 al 20 de septiembre").',
    columnas: [
      { campo: 'tarea', alias: ['actividad_gantt', 'nombre', 'nombre_de_tarea', 'descripcion'], requerido: true, ejemplo: 'Entrega acceso sitio 15' },
      { campo: 'inicio', alias: ['fecha_inicio', 'comienzo'], ejemplo: '15-09-2026' },
      { campo: 'termino', alias: ['fecha_termino', 'fin', 'final', 'fecha_fin'], ejemplo: '20-09-2026' },
      { campo: 'semana', alias: ['periodo', 'plazo'], ejemplo: '', descripcion: 'Alternativa a inicio/término' },
      { campo: 'sitio', alias: ['terreno'], ejemplo: '', descripcion: 'Opcional si está en el texto' },
      { campo: 'zona', ejemplo: '', descripcion: 'Opcional si está en el texto' },
    ],
    validar(db, filas) {
      const terrenos = mapaTerrenos(db);
      const entrega = db.prepare('select id from entrega where terreno_id = ? and zona = ?');
      const actividad = db.prepare('select id from actividad where terreno_id = ? and tipo = ?');
      const ops = [], errores = [];
      for (const fila of filas) {
        const c = campos(fila, this);
        const err = (m) => errores.push({ fila: fila._fila, mensaje: m });
        const texto = String(c.tarea).trim();
        const delTexto = leerTextoTarea(texto);
        const codigo = normTerreno(c.sitio) || delTexto.terreno;
        const t = terrenos[codigo];
        if (!t) { err(`No se reconoce el sitio en "${texto}"`); continue; }
        const zona = normZona(c.zona) || delTexto.zona || (t.tipo !== 'sitio' && !delTexto.actividad ? 'unica' : null);
        let inicio = normFecha(c.inicio), termino = normFecha(c.termino);
        if (!inicio || !termino) {
          const sem = leerSemana(c.semana) || leerSemana(texto);
          if (sem) ({ inicio, termino } = sem);
        }
        if (!inicio || !termino) { err(`Faltan fechas de inicio y término en "${texto}"`); continue; }
        if (termino < inicio) { err(`El término es anterior al inicio en "${texto}"`); continue; }
        if (zona) {
          const e = entrega.get(t.id, zona);
          if (!e) { err(`${t.codigo} no tiene zona "${zona}"`); continue; }
          ops.push({ texto, entrega_id: e.id, actividad_id: null, inicio, termino });
        } else if (delTexto.actividad) {
          ops.push({ texto, entrega_id: null, actividad_id: actividad.get(t.id, delTexto.actividad).id, inicio, termino });
        } else {
          err(`No se reconoce la zona (acceso, living, patio) ni la actividad en "${texto}"`);
        }
      }
      const anteriores = db.prepare('select count(*) n from tarea_gantt').get().n;
      return { ops, errores, resumen: { nuevas: ops.length, reemplaza_tareas_anteriores: anteriores } };
    },
    aplicar(db, ops, cargaId) {
      db.prepare('delete from tarea_gantt').run();
      const ins = db.prepare(
        'insert into tarea_gantt (texto, entrega_id, actividad_id, inicio, termino, carga_id) values (?, ?, ?, ?, ?, ?)'
      );
      for (const o of ops) ins.run(o.texto, o.entrega_id, o.actividad_id, o.inicio, o.termino, cargaId);
    },
  },
};

async function importar(db, tipo, buffer, nombre, { aplicar = false } = {}) {
  const def = TIPOS[tipo];
  if (!def) throw new Error(`Tipo de archivo desconocido: ${tipo}`);
  const { encabezados, filas } = await leerTabla(buffer, nombre);
  const faltan = def.columnas
    .filter((c) => c.requerido && ![c.campo, ...(c.alias || [])].some((a) => encabezados.includes(a)))
    .map((c) => c.campo);
  if (tipo === 'viajes' && !['patente', 'placa', 'ppu', 'camion', 'tarjeta', 'id_tarjeta', 'n_tarjeta', 'codigo_tarjeta', 'tag'].some((a) => encabezados.includes(a))) {
    faltan.push('patente o tarjeta');
  }
  if (faltan.length) {
    return { ok: false, faltan_columnas: faltan, encabezados, errores: [], resumen: {} };
  }
  const { ops, errores, resumen } = def.validar(db, filas);
  const resultado = { ok: true, tipo, modo: def.modo, filas: filas.length, resumen, errores: errores.slice(0, 200), total_errores: errores.length };
  if (aplicar && ops.length) {
    db.transaction(() => {
      const carga = db
        .prepare('insert into carga (tipo, archivo, resumen) values (?, ?, ?)')
        .run(tipo, nombre, JSON.stringify({ filas: filas.length, ...resumen, errores: errores.length }));
      def.aplicar(db, ops, carga.lastInsertRowid);
      resultado.carga_id = carga.lastInsertRowid;
    })();
    resultado.aplicado = true;
  }
  return resultado;
}

function plantilla(tipo) {
  const def = TIPOS[tipo];
  if (!def) return null;
  const sep = ';';
  const lineas = [def.columnas.map((c) => c.campo).join(sep), def.columnas.map((c) => c.ejemplo ?? '').join(sep)];
  return '﻿' + lineas.join('\r\n') + '\r\n';
}

function describirTipos() {
  return Object.entries(TIPOS).map(([id, d]) => ({
    id, titulo: d.titulo, modo: d.modo, ayuda: d.ayuda,
    columnas: d.columnas.map(({ campo, requerido, descripcion, ejemplo }) => ({ campo, requerido: !!requerido, descripcion, ejemplo })),
  }));
}

module.exports = {
  importar, plantilla, describirTipos, leerTabla,
  normFecha, normHora, normNumero, normTerreno, normZona, normEstado, leerTextoTarea, leerSemana,
};
