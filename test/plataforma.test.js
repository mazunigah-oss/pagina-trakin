const test = require('node:test');
const assert = require('node:assert/strict');
const ExcelJS = require('exceljs');
const { abrir } = require('../src/db');
const { estadoGeneral } = require('../src/calculos');
const imp = require('../src/importar');
const { crearApp } = require('../src/server');

const csv = (lineas) => Buffer.from(lineas.join('\n'));

test('siembra 48 sitios con 3 zonas, 2 edificios y escarpe/corte para cada terreno', () => {
  const db = abrir(':memory:');
  assert.equal(db.prepare("select count(*) n from terreno where tipo='sitio'").get().n, 48);
  assert.equal(db.prepare("select count(*) n from terreno where tipo='edificio'").get().n, 2);
  assert.equal(db.prepare('select count(*) n from entrega').get().n, 48 * 3 + 2);
  assert.equal(db.prepare('select count(*) n from actividad').get().n, 50 * 2);
  const zonas = db.prepare(`select zona, count(*) n from entrega e join terreno t on t.id=e.terreno_id where t.tipo='sitio' group by zona`).all();
  assert.deepEqual(zonas.map((z) => [z.zona, z.n]), [['acceso', 48], ['fondo_patio', 48], ['living', 48]]);
});

test('normaliza fechas, horas, números y referencias', () => {
  assert.equal(imp.normFecha('29-09-2026'), '2026-09-29');
  assert.equal(imp.normFecha('29/9/26'), '2026-09-29');
  assert.equal(imp.normFecha('2026-09-29 08:10'), '2026-09-29');
  assert.equal(imp.normFecha(new Date(Date.UTC(2026, 8, 29))), '2026-09-29');
  assert.equal(imp.normFecha('ayer'), undefined);
  assert.equal(imp.normHora('8:05'), '08:05');
  assert.equal(imp.normHora(0.5), '12:00');
  assert.equal(imp.normNumero('12,5'), 12.5);
  assert.equal(imp.normNumero('1.234,5'), 1234.5);
  assert.equal(imp.normTerreno('15'), 'S-15');
  assert.equal(imp.normTerreno('Sitio 7'), 'S-07');
  assert.equal(imp.normTerreno('ED-1'), 'ED-1');
  assert.equal(imp.normTerreno(''), null);
  assert.equal(imp.normZona('Fondo de patio'), 'fondo_patio');
  assert.equal(imp.normEstado('En proceso'), 'en_proceso');
  assert.deepEqual(imp.leerTextoTarea('Entrega acceso sitio 15'), { terreno: 'S-15', zona: 'acceso', actividad: null });
  assert.deepEqual(imp.leerSemana('semana del 15 al 20 de septiembre', 2026), { inicio: '2026-09-15', termino: '2026-09-20' });
  assert.deepEqual(imp.leerSemana('29 de septiembre al 3 de octubre de 2026'), { inicio: '2026-09-29', termino: '2026-10-03' });
});

test('viajes: usa capacidad del camión, suma sin duplicar y se puede deshacer', async () => {
  const db = abrir(':memory:');
  await imp.importar(db, 'camiones', csv(['patente;capacidad_m3;tarjeta', 'ABCD12;14;T-1', 'XY-1234;20;T-2']), 'c.csv', { aplicar: true });

  const archivo = csv([
    'Fecha;Hora;Tarjeta;Sitio;Actividad',
    '29-09-2026;08:10;T-1;15;escarpe',
    '29-09-2026;09:00;T-2;;',
    '29-09-2026;09:30;T-9;;',
    '29-09-2026;25:00;T-1;;',
  ]);
  const previa = await imp.importar(db, 'viajes', archivo, 'v.csv');
  assert.equal(previa.resumen.nuevas, 2);
  assert.equal(previa.total_errores, 2);
  assert.equal(db.prepare('select count(*) n from viaje').get().n, 0, 'revisar no guarda');

  const r1 = await imp.importar(db, 'viajes', archivo, 'v.csv', { aplicar: true });
  assert.equal(r1.resumen.m3, 34);
  const r2 = await imp.importar(db, 'viajes', archivo, 'v.csv', { aplicar: true });
  assert.equal(r2.resumen.nuevas, 0);
  assert.equal(r2.resumen.duplicadas, 2);

  const e = estadoGeneral(db, '2026-09-29');
  assert.equal(e.resumen.viajes, 2);
  assert.equal(e.resumen.camiones, 2);
  assert.equal(e.resumen.m3, 34);
  assert.equal(e.resumen.acumulado_m3, 34);

  db.prepare('delete from carga where id = ?').run(r1.carga_id);
  assert.equal(db.prepare('select count(*) n from viaje').get().n, 0);
});

test('viajes generales se prorratean entre actividades en proceso según volumen proyectado', async () => {
  const db = abrir(':memory:');
  await imp.importar(db, 'volumenes', csv([
    'sitio;actividad;volumen_proyectado_m3;estado',
    '1;escarpe;100;en proceso',
    '2;escarpe;300;en proceso',
  ]), 'vol.csv', { aplicar: true });
  await imp.importar(db, 'viajes', csv(['fecha;hora;patente;volumen_m3', '01-10-2026;10:00;ABCD12;40']), 'v.csv', { aplicar: true });
  await imp.importar(db, 'ajustes', csv(['sitio;actividad;fecha;volumen_m3', '1;escarpe;01-10-2026;5']), 'a.csv', { aplicar: true });
  const acts = estadoGeneral(db, '2026-10-01').actividades;
  const s1 = acts.find((a) => a.terreno_id === 1 && a.tipo === 'escarpe');
  const s2 = acts.find((a) => a.terreno_id === 2 && a.tipo === 'escarpe');
  assert.equal(s1.prorrateo_m3, 10);
  assert.equal(s1.retirado_m3, 15);
  assert.equal(s2.retirado_m3, 30);
  assert.equal(s1.avance, 0.15);
});

test('carta Gantt en Excel con texto libre y comparación real vs programado', async () => {
  const db = abrir(':memory:');
  const libro = new ExcelJS.Workbook();
  const hoja = libro.addWorksheet('Programa');
  hoja.addRow(['Tarea', 'Semana']);
  hoja.addRow(['Entrega acceso sitio 15', 'semana del 15 al 20 de septiembre de 2026']);
  hoja.addRow(['Entrega living sitio 15', 'semana del 5 al 10 de octubre de 2026']);
  hoja.addRow(['Escarpe edificio 1', '1 al 30 de septiembre de 2026']);
  hoja.addRow(['Algo sin sitio', '1 al 2 de octubre de 2026']);
  const buffer = Buffer.from(await libro.xlsx.writeBuffer());

  const r = await imp.importar(db, 'gantt', buffer, 'gantt.xlsx', { aplicar: true });
  assert.equal(r.resumen.nuevas, 3);
  assert.equal(r.total_errores, 1);

  await imp.importar(db, 'entregas', csv(['sitio;zona;estado', '15;living;entregado']), 'e.csv', { aplicar: true });
  const e = estadoGeneral(db, '2026-09-30');
  const s15 = e.entregas.filter((x) => x.terreno_id === 15);
  const acceso = s15.find((x) => x.zona === 'acceso');
  const living = s15.find((x) => x.zona === 'living');
  assert.equal(acceso.programado.estado, 'entregado');
  assert.equal(acceso.comparacion, 'atrasado');
  assert.equal(living.programado.estado, 'sin_intervenir');
  assert.equal(living.comparacion, 'adelantado');

  // Reemplaza: una segunda carga borra las tareas anteriores
  await imp.importar(db, 'gantt', csv(['tarea;inicio;termino', 'Entrega patio sitio 1;01-10-2026;03-10-2026']), 'g2.csv', { aplicar: true });
  assert.equal(db.prepare('select count(*) n from tarea_gantt').get().n, 1);
});

test('reporta columnas faltantes', async () => {
  const db = abrir(':memory:');
  const r = await imp.importar(db, 'viajes', csv(['dia_x;otra', '1;2']), 'x.csv');
  assert.equal(r.ok, false);
  assert.ok(r.faltan_columnas.includes('fecha'));
});

test('API: visita solo lee, administrador puede cargar', async () => {
  const app = crearApp({ db: abrir(':memory:'), clave: 'secreta' });
  const srv = app.listen(0);
  const base = `http://127.0.0.1:${srv.address().port}`;
  try {
    assert.equal((await fetch(`${base}/api/estado`)).status, 200);
    const fd = () => { const f = new FormData(); f.append('archivo', new Blob(['patente;capacidad_m3\nAB1234;10']), 'c.csv'); return f; };
    assert.equal((await fetch(`${base}/api/importar/camiones?aplicar=1`, { method: 'POST', body: fd() })).status, 401);
    assert.equal((await fetch(`${base}/api/entregas/1`, { method: 'PATCH' })).status, 401);
    assert.equal((await fetch(`${base}/api/login`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{"clave":"mala"}' })).status, 401);
    const login = await fetch(`${base}/api/login`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{"clave":"secreta"}' });
    const cookie = login.headers.get('set-cookie').split(';')[0];
    const r = await fetch(`${base}/api/importar/camiones?aplicar=1`, { method: 'POST', body: fd(), headers: { cookie } });
    assert.equal((await r.json()).resumen.nuevas, 1);
    const p = await fetch(`${base}/api/entregas/1`, { method: 'PATCH', headers: { cookie, 'Content-Type': 'application/json' }, body: '{"estado":"entregado"}' });
    assert.equal(p.status, 200);
  } finally {
    srv.close();
  }
});
