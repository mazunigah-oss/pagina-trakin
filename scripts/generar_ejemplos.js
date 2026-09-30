// Genera archivos de ejemplo en data/ejemplos/ (sirven como modelo de formato)
// y, con --cargar, los carga en la base de datos para ver la página con datos.
//   node scripts/generar_ejemplos.js [--cargar]
const fs = require('node:fs');
const path = require('node:path');
const { hoyChile } = require('../src/calculos');

const dir = path.join(__dirname, '..', 'data', 'ejemplos');
fs.mkdirSync(dir, { recursive: true });

let semilla = 7;
const azar = () => ((semilla = (semilla * 16807) % 2147483647) / 2147483647);
const dos = (n) => String(n).padStart(2, '0');
const cl = (iso) => iso.split('-').reverse().join('-');
const sumarDias = (iso, n) => {
  const d = new Date(iso + 'T12:00:00Z');
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
};
const escribir = (nombre, filas) => {
  fs.writeFileSync(path.join(dir, nombre), '﻿' + filas.map((f) => f.join(';')).join('\r\n') + '\r\n');
};

const hoy = hoyChile();
const camiones = [
  ['ABCD12', 14, '100231', 'Transportes Andes'],
  ['BCDF34', 14, '100232', 'Transportes Andes'],
  ['CDFG56', 20, '100233', 'Áridos del Sur'],
  ['DFGH78', 20, '100234', 'Áridos del Sur'],
  ['FGHJ90', 12, '100235', 'Fletes Maipo'],
];
escribir('camiones.csv', [['patente', 'capacidad_m3', 'tarjeta', 'empresa'], ...camiones]);

// Volúmenes proyectados: sitios ~ 60-110 m³ escarpe y 120-220 m³ corte; edificios más grandes
const vol = [['sitio', 'actividad', 'volumen_proyectado_m3', 'estado']];
for (let s = 1; s <= 48; s++) {
  const estadoEsc = s <= 20 ? 'terminado' : s <= 30 ? 'en proceso' : 'sin intervenir';
  const estadoCor = s <= 12 ? 'terminado' : s <= 24 ? 'en proceso' : 'sin intervenir';
  vol.push([s, 'escarpe', 60 + Math.round(azar() * 50), estadoEsc]);
  vol.push([s, 'corte', 120 + Math.round(azar() * 100), estadoCor]);
}
vol.push(['ED-1', 'escarpe', 900, 'en proceso'], ['ED-1', 'corte', 4200, 'sin intervenir']);
vol.push(['ED-2', 'escarpe', 800, 'sin intervenir'], ['ED-2', 'corte', 3600, 'sin intervenir']);
escribir('volumenes.csv', vol);

// Gantt por zona: cada semana se entregan ~3 sitios (acceso → living → patio)
const gantt = [['tarea', 'inicio', 'termino']];
const lunes = sumarDias(hoy, -((new Date(hoy + 'T12:00:00Z').getUTCDay() + 6) % 7) - 7 * 8);
const zonas = ['acceso', 'living', 'patio'];
for (let s = 1; s <= 48; s++) {
  zonas.forEach((z, i) => {
    const ini = sumarDias(lunes, 7 * (Math.floor((s - 1) / 3) + i));
    gantt.push([`Entrega ${z} sitio ${s}`, cl(ini), cl(sumarDias(ini, 5))]);
  });
}
gantt.push(['Escarpe edificio 1', cl(sumarDias(lunes, 14)), cl(sumarDias(lunes, 60))]);
escribir('gantt.csv', gantt);

// Estado real de entregas
const ent = [['sitio', 'zona', 'estado', 'fecha_entrega']];
for (let s = 1; s <= 48; s++) {
  zonas.forEach((z, i) => {
    const avance = 16 - Math.floor((s - 1) / 3) - i;
    if (avance >= 2 || (s <= 9 && avance >= 1)) ent.push([s, z, 'entregado', cl(sumarDias(hoy, -3 * avance))]);
    else if (avance >= 0) ent.push([s, z, 'en proceso', '']);
  });
}
escribir('entregas.csv', ent);

// Salidas de camiones de los últimos 20 días (formato tipo máquina de tarjetas)
const viajes = [['fecha', 'hora', 'tarjeta', 'sitio', 'actividad']];
for (let d = 19; d >= 0; d--) {
  const dia = sumarDias(hoy, -d);
  if (new Date(dia + 'T12:00:00Z').getUTCDay() === 0) continue;
  const n = 18 + Math.floor(azar() * 16);
  for (let k = 0; k < n; k++) {
    const c = camiones[Math.floor(azar() * camiones.length)];
    const min = 8 * 60 + Math.floor((k / n) * 540) + Math.floor(azar() * 20);
    const sitio = azar() < 0.25 ? '' : 13 + Math.floor(azar() * 18);
    viajes.push([cl(dia), `${dos(Math.floor(min / 60))}:${dos(min % 60)}`, c[2], sitio, '']);
  }
}
escribir('viajes.csv', viajes);
console.log(`Ejemplos escritos en ${dir}`);

if (process.argv.includes('--cargar')) {
  const { abrir } = require('../src/db');
  const { importar } = require('../src/importar');
  const db = abrir();
  (async () => {
    for (const tipo of ['camiones', 'volumenes', 'entregas', 'gantt', 'viajes']) {
      const r = await importar(db, tipo, fs.readFileSync(path.join(dir, `${tipo}.csv`)), `${tipo}.csv`, { aplicar: true });
      console.log(tipo, JSON.stringify(r.resumen), r.total_errores ? `${r.total_errores} errores` : '');
    }
  })();
}
