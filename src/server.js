const path = require('node:path');
const fs = require('node:fs');
const crypto = require('node:crypto');
const express = require('express');
const multer = require('multer');
const { abrir, GEOMETRIA } = require('./db');
const { estadoGeneral, hoyChile } = require('./calculos');
const { importar, plantilla, describirTipos } = require('./importar');

const ESTADOS_ENTREGA = ['sin_intervenir', 'en_proceso', 'entregado'];
const ESTADOS_ACTIVIDAD = ['sin_intervenir', 'en_proceso', 'terminado'];

function crearApp({ db = abrir(), clave = process.env.ADMIN_PASSWORD, secreto = process.env.SESSION_SECRET } = {}) {
  if (!clave) {
    clave = 'admin';
    console.warn('ADVERTENCIA: ADMIN_PASSWORD no definido, se usa "admin". Defínalo antes de publicar la página.');
  }
  secreto ||= crypto.createHash('sha256').update('trakin:' + clave).digest('hex');

  // Sesión de administrador: cookie firmada con vencimiento (12 horas)
  const firmar = (v) => crypto.createHmac('sha256', secreto).update(v).digest('hex');
  const crearToken = () => {
    const vence = String(Date.now() + 12 * 3600 * 1000);
    return `${vence}.${firmar(vence)}`;
  };
  const tokenValido = (t = '') => {
    const [vence, firma] = t.split('.');
    if (!vence || !firma || +vence < Date.now()) return false;
    const esperado = firmar(vence);
    return firma.length === esperado.length && crypto.timingSafeEqual(Buffer.from(firma), Buffer.from(esperado));
  };
  const leerCookie = (req) =>
    Object.fromEntries((req.headers.cookie || '').split(';').map((c) => c.trim().split('=')).filter((p) => p[0]))
      .admin;
  const esAdmin = (req) => tokenValido(leerCookie(req));
  const soloAdmin = (req, res, next) =>
    esAdmin(req) ? next() : res.status(401).json({ error: 'Debe ingresar como administrador' });

  const app = express();
  app.use(express.json());
  const subir = multer({ storage: multer.memoryStorage(), limits: { fileSize: 20 * 1024 * 1024 } });

  // ---- sesión ----
  app.post('/api/login', (req, res) => {
    const dada = Buffer.from(String(req.body?.clave || ''));
    const real = Buffer.from(clave);
    if (dada.length !== real.length || !crypto.timingSafeEqual(dada, real)) {
      return res.status(401).json({ error: 'Contraseña incorrecta' });
    }
    const seguro = req.secure || req.headers['x-forwarded-proto'] === 'https' ? '; Secure' : '';
    res.setHeader('Set-Cookie', `admin=${crearToken()}; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200${seguro}`);
    res.json({ admin: true });
  });
  app.post('/api/logout', (req, res) => {
    res.setHeader('Set-Cookie', 'admin=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0');
    res.json({ admin: false });
  });
  app.get('/api/sesion', (req, res) => res.json({ admin: esAdmin(req) }));

  // ---- lectura (acceso libre) ----
  app.get('/api/geometria', (req, res) => res.sendFile(GEOMETRIA));
  app.get('/api/estado', (req, res) => {
    const hoy = /^\d{4}-\d{2}-\d{2}$/.test(req.query.fecha) ? req.query.fecha : hoyChile();
    res.json(estadoGeneral(db, hoy));
  });
  app.get('/api/viajes', (req, res) => {
    const desde = req.query.desde || hoyChile();
    const hasta = req.query.hasta || desde;
    res.json(
      db.prepare(
        `select v.id, v.salida_en, v.patente, v.volumen_m3, v.actividad, coalesce(t.codigo, 'General') origen, c.empresa
         from viaje v left join terreno t on t.id = v.terreno_id left join camion c on c.id = v.camion_id
         where substr(v.salida_en, 1, 10) between ? and ? order by v.salida_en desc limit 2000`
      ).all(desde, hasta)
    );
  });
  app.get('/api/gantt', (req, res) => {
    res.json(
      db.prepare(
        `select g.*, coalesce(te.codigo, ta.codigo) terreno, e.zona, a.tipo actividad
         from tarea_gantt g
         left join entrega e on e.id = g.entrega_id left join terreno te on te.id = e.terreno_id
         left join actividad a on a.id = g.actividad_id left join terreno ta on ta.id = a.terreno_id
         order by g.inicio, terreno`
      ).all()
    );
  });

  // ---- edición (solo administrador) ----
  app.patch('/api/entregas/:id', soloAdmin, (req, res) => {
    const e = db.prepare('select * from entrega where id = ?').get(req.params.id);
    if (!e) return res.status(404).json({ error: 'No existe' });
    const estado = req.body.estado ?? e.estado;
    if (!ESTADOS_ENTREGA.includes(estado)) return res.status(400).json({ error: 'Estado inválido' });
    const fecha = estado === 'entregado' ? req.body.fecha_entrega || e.fecha_entrega || hoyChile() : null;
    db.transaction(() => {
      db.prepare('update entrega set estado = ?, fecha_entrega = ? where id = ?').run(estado, fecha, e.id);
      if (estado !== e.estado) {
        db.prepare('insert into historial_estado (entrega_id, estado, fecha) values (?, ?, ?)').run(e.id, estado, fecha || hoyChile());
      }
    })();
    res.json({ ok: true });
  });

  app.patch('/api/actividades/:id', soloAdmin, (req, res) => {
    const a = db.prepare('select * from actividad where id = ?').get(req.params.id);
    if (!a) return res.status(404).json({ error: 'No existe' });
    const estado = req.body.estado ?? a.estado;
    const vol = req.body.volumen_proyectado_m3 ?? a.volumen_proyectado_m3;
    if (!ESTADOS_ACTIVIDAD.includes(estado)) return res.status(400).json({ error: 'Estado inválido' });
    if (!(Number(vol) >= 0)) return res.status(400).json({ error: 'Volumen inválido' });
    db.transaction(() => {
      db.prepare('update actividad set estado = ?, volumen_proyectado_m3 = ? where id = ?').run(estado, Number(vol), a.id);
      if (estado !== a.estado) {
        db.prepare('insert into historial_estado (actividad_id, estado, fecha) values (?, ?, ?)').run(a.id, estado, hoyChile());
      }
    })();
    res.json({ ok: true });
  });

  // ---- carga de archivos ----
  app.get('/api/importar/tipos', (req, res) => res.json(describirTipos()));
  app.get('/api/plantillas/:tipo', (req, res) => {
    const csv = plantilla(req.params.tipo);
    if (!csv) return res.status(404).end();
    res.setHeader('Content-Type', 'text/csv; charset=utf-8');
    res.setHeader('Content-Disposition', `attachment; filename="plantilla_${req.params.tipo}.csv"`);
    res.send(csv);
  });
  app.post('/api/importar/:tipo', soloAdmin, subir.single('archivo'), async (req, res) => {
    if (!req.file) return res.status(400).json({ error: 'Falta el archivo' });
    try {
      const nombre = Buffer.from(req.file.originalname, 'latin1').toString('utf8');
      res.json(await importar(db, req.params.tipo, req.file.buffer, nombre, { aplicar: req.query.aplicar === '1' }));
    } catch (e) {
      res.status(400).json({ error: `No se pudo leer el archivo: ${e.message}` });
    }
  });
  app.get('/api/cargas', soloAdmin, (req, res) => {
    res.json(db.prepare('select * from carga order by id desc limit 100').all().map((c) => ({ ...c, resumen: JSON.parse(c.resumen || '{}') })));
  });
  // Deshacer una carga que SUMA o REEMPLAZA (borra sus viajes, ajustes o tareas)
  app.delete('/api/cargas/:id', soloAdmin, (req, res) => {
    const c = db.prepare('select * from carga where id = ?').get(req.params.id);
    if (!c) return res.status(404).json({ error: 'No existe' });
    if (!['viajes', 'ajustes', 'gantt'].includes(c.tipo)) {
      return res.status(400).json({ error: 'Las cargas que actualizan datos no se pueden deshacer; suba un archivo corregido.' });
    }
    db.prepare('delete from carga where id = ?').run(c.id);
    res.json({ ok: true });
  });

  app.use(express.static(path.join(__dirname, '..', 'public')));
  return app;
}

if (require.main === module) {
  const puerto = process.env.PORT || 3000;
  fs.mkdirSync(path.join(__dirname, '..', 'data'), { recursive: true });
  crearApp().listen(puerto, () => console.log(`Plataforma de movimiento de tierra en http://localhost:${puerto}`));
}

module.exports = { crearApp };
