'use strict';

const $ = (s) => document.querySelector(s);
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const num = (n, d = 0) => (n == null ? '—' : Number(n).toLocaleString('es-CL', { maximumFractionDigits: d, minimumFractionDigits: d }));
const fechaCl = (iso) => (iso ? iso.slice(0, 10).split('-').reverse().join('-') : '—');

const NOMBRE_ESTADO = { sin_intervenir: 'Sin intervenir', en_proceso: 'En proceso', entregado: 'Entregado', terminado: 'Terminado' };
const NOMBRE_ZONA = { acceso: 'Acceso', living: 'Living (casa)', fondo_patio: 'Fondo de patio', unica: 'Zona única' };
const NOMBRE_COMP = { atrasado: 'Atrasado', al_dia: 'Al día', adelantado: 'Adelantado' };
const COLOR_ESTADO = { sin_intervenir: 'var(--sin)', en_proceso: 'var(--proceso)', entregado: 'var(--listo)', terminado: 'var(--listo)' };
const COLOR_COMP = { atrasado: 'var(--atrasado)', al_dia: 'var(--listo)', adelantado: 'var(--adelantado)' };
const pastilla = (clave, nombres = NOMBRE_ESTADO) => `<span class="pastilla p-${clave}">${esc(nombres[clave] || clave)}</span>`;

const estado = { admin: false, datos: null, geo: null, vista: 'resumen', modoPrograma: 'programado', sel: {} };

async function api(url, opciones = {}) {
  const r = await fetch(url, { credentials: 'same-origin', ...opciones });
  const cuerpo = r.headers.get('content-type')?.includes('json') ? await r.json() : null;
  if (!r.ok) throw new Error(cuerpo?.error || `Error ${r.status}`);
  return cuerpo;
}

// ---------------- carga de datos ----------------

async function cargar() {
  const fecha = $('#fecha').value;
  const [geo, datos] = await Promise.all([
    estado.geo || api('/api/geometria'),
    api('/api/estado' + (fecha ? `?fecha=${fecha}` : '')),
  ]);
  estado.geo = geo;
  estado.datos = datos;
  if (!$('#fecha').value) $('#fecha').value = datos.hoy;
  $('#fecha-texto').textContent = fechaCl(datos.hoy);
  indexar();
  pintar();
}

function indexar() {
  const d = estado.datos;
  d.terrenoPorId = Object.fromEntries(d.terrenos.map((t) => [t.id, t]));
  d.entregasPorTerreno = {};
  for (const e of d.entregas) (d.entregasPorTerreno[e.terreno_id] ||= []).push(e);
  d.actividadesPorTerreno = {};
  for (const a of d.actividades) (d.actividadesPorTerreno[a.terreno_id] ||= []).push(a);
}

function pintar() {
  const v = estado.vista;
  if (v === 'resumen') pintarResumen();
  if (v === 'entregas') pintarEntregas();
  if (v === 'programa') pintarPrograma();
  if (v === 'tierra') pintarTierra();
  if (v === 'viajes') pintarViajes();
  if (v === 'cargar') pintarCargas();
}

// ---------------- resumen ----------------

function pintarResumen() {
  const { resumen: r, entregas } = estado.datos;
  const pct = r.proyectado_m3 > 0 ? (100 * r.acumulado_m3) / r.proyectado_m3 : null;
  const esHoy = r.dia === estado.datos.hoy;
  $('#kpis').innerHTML = [
    ['Camiones', num(r.camiones), `distintos, ${fechaCl(r.dia)}`],
    ['Viajes', num(r.viajes), `salidas del ${fechaCl(r.dia)}`],
    ['m³ retirados', num(r.m3, 1), `del ${fechaCl(r.dia)}`],
    ['Acumulado obra', `${num(r.acumulado_m3)} m³`, pct == null ? 'sin volúmenes proyectados cargados' : `${num(pct, 1)} % de ${num(r.proyectado_m3)} m³ proyectados`],
  ].map(([e, v, n]) => `<div class="kpi"><div class="etiqueta">${e}</div><div class="valor">${v}</div><div class="nota">${esc(n)}</div></div>`).join('');

  $('#tabla-origen').innerHTML = r.por_origen.length
    ? `<table><thead><tr><th>Origen</th><th class="num">Viajes</th><th class="num">m³</th></tr></thead><tbody>${r.por_origen
        .map((f) => `<tr><td>${esc(nombreOrigen(f.origen))}</td><td class="num">${num(f.viajes)}</td><td class="num">${num(f.m3, 1)}</td></tr>`)
        .join('')}</tbody></table>
       ${r.por_origen.some((f) => f.origen === 'General') ? '<p class="vacio">"General": viajes sin sitio asignado; se reparten proporcionalmente entre los terrenos en proceso.</p>' : ''}`
    : `<p class="vacio">No hay salidas registradas el ${fechaCl(r.dia)}.${r.ultimo_dia_con_viajes ? ` Último día con registros: ${fechaCl(r.ultimo_dia_con_viajes)}.` : ''}</p>`;

  const dias = [];
  const fin = new Date(r.dia + 'T12:00:00');
  for (let i = 29; i >= 0; i--) {
    const d = new Date(fin); d.setDate(d.getDate() - i);
    dias.push(d.toISOString().slice(0, 10));
  }
  const porDia = Object.fromEntries(r.ultimos_30_dias.map((f) => [f.dia, f]));
  const max = Math.max(1, ...r.ultimos_30_dias.map((f) => f.m3));
  $('#grafico-dias').innerHTML = r.ultimos_30_dias.length
    ? `<div class="barras">${dias.map((d) => {
        const f = porDia[d];
        return `<div style="height:${f ? (100 * f.m3) / max : 0}%" title="${fechaCl(d)}: ${f ? `${num(f.m3, 1)} m³ · ${f.viajes} viajes` : 'sin viajes'}"></div>`;
      }).join('')}</div><div class="eje"><span>${fechaCl(dias[0])}</span><span>máx. ${num(max, 1)} m³/día</span><span>${fechaCl(dias.at(-1))}</span></div>`
    : '<p class="vacio">Sin viajes en los últimos 30 días.</p>';

  const cuenta = (campo, v) => entregas.filter((e) => e[campo] === v).length;
  const conPrograma = entregas.filter((e) => e.programado).length;
  $('#resumen-entregas').innerHTML = `<div class="contadores">
      <div><b>${cuenta('estado', 'entregado')}</b>${pastilla('entregado')}</div>
      <div><b>${cuenta('estado', 'en_proceso')}</b>${pastilla('en_proceso')}</div>
      <div><b>${cuenta('estado', 'sin_intervenir')}</b>${pastilla('sin_intervenir')}</div>
      <div><b>${cuenta('comparacion', 'atrasado')}</b>${pastilla('atrasado', NOMBRE_COMP)}</div>
      <div><b>${entregas.length}</b>zonas en total</div>
    </div>
    <p class="vacio">${conPrograma ? `${conPrograma} zonas tienen fechas en la carta Gantt.` : 'Aún no se ha cargado la carta Gantt.'}${esHoy ? '' : ' Fecha de consulta distinta a hoy.'}</p>`;
}

function nombreOrigen(codigo) {
  if (codigo === 'General') return 'General (sin sitio)';
  const t = estado.datos.terrenos.find((x) => x.codigo === codigo);
  return t ? t.nombre : codigo;
}

// ---------------- mapa ----------------

function centroide(puntos) {
  let a = 0, x = 0, y = 0;
  for (let i = 0; i < puntos.length; i++) {
    const [x0, y0] = puntos[i];
    const [x1, y1] = puntos[(i + 1) % puntos.length];
    const f = x0 * y1 - x1 * y0;
    a += f; x += (x0 + x1) * f; y += (y0 + y1) * f;
  }
  return a ? [x / (3 * a), y / (3 * a)] : puntos[0];
}

// colorear(entrega) -> { color, alerta, titulo }
function dibujarMapa(contenedor, colorear, alClic, seleccion) {
  const g = estado.geo;
  const d = estado.datos;
  const fondo = g.fondo.map((l) => 'M' + l.map((p) => p.join(',')).join('L')).join('');
  const zonas = d.entregas.map((e) => {
    const c = colorear(e);
    const t = d.terrenoPorId[e.terreno_id];
    const sel = seleccion === e.terreno_id ? ' sel' : '';
    return `<polygon class="zona${c.alerta ? ' alerta' : ''}${sel}" data-terreno="${e.terreno_id}" fill="${c.color}"
      points="${e.poligono.map((p) => p.join(',')).join(' ')}"><title>${esc(t.nombre)} · ${esc(NOMBRE_ZONA[e.zona])}${c.titulo ? ' · ' + esc(c.titulo) : ''}</title></polygon>`;
  });
  const etiquetas = d.terrenos.map((t) => {
    const es = d.entregasPorTerreno[t.id] || [];
    const base = es.find((e) => e.zona === 'living' || e.zona === 'unica');
    if (!base) return '';
    const [x, y] = centroide(base.poligono);
    return `<text class="etiqueta" x="${x.toFixed(1)}" y="${y.toFixed(1)}">${t.tipo === 'sitio' ? +t.codigo.slice(2) : esc(t.codigo)}</text>`;
  });
  contenedor.innerHTML = `<svg viewBox="0 0 ${g.ancho} ${g.alto}" role="img" aria-label="Plano de la urbanización">
    <path class="fondo" d="${fondo}"/>${zonas.join('')}${etiquetas.join('')}</svg>`;
  contenedor.querySelector('svg').addEventListener('click', (ev) => {
    const z = ev.target.closest('.zona');
    if (z) alClic(+z.dataset.terreno);
  });
}

function leyenda(el, items) {
  el.innerHTML = items.map(([color, texto]) => `<span><i style="background:${color}"></i>${esc(texto)}</span>`).join('');
}

// ---------------- entregas ----------------

function pintarEntregas() {
  leyenda($('#leyenda-entregas'), [['var(--sin)', 'Sin intervenir'], ['var(--proceso)', 'En proceso'], ['var(--listo)', 'Entregado']]);
  dibujarMapa($('#mapa-entregas'), (e) => ({ color: COLOR_ESTADO[e.estado], titulo: NOMBRE_ESTADO[e.estado] }),
    (id) => { estado.sel.entregas = id; pintarEntregas(); }, estado.sel.entregas);
  panelEntregas($('#panel-entregas'), estado.sel.entregas);
}

function encabezadoTerreno(t) {
  return `<h3>${esc(t.nombre)}</h3><div class="meta">${esc(t.codigo)}${t.modelo ? ` · Modelo ${esc(t.modelo)}` : ''}</div>`;
}

function panelEntregas(panel, id) {
  if (!id) return;
  const d = estado.datos;
  const t = d.terrenoPorId[id];
  const es = d.entregasPorTerreno[id] || [];
  panel.innerHTML = encabezadoTerreno(t) + es.map((e) => `
    <div class="bloque">
      <b>${esc(NOMBRE_ZONA[e.zona])}</b> <span class="vacio">${num(e.area_m2)} m²</span><br>
      ${pastilla(e.estado)} ${e.fecha_entrega ? `<span class="vacio">el ${fechaCl(e.fecha_entrega)}</span>` : ''}
      ${e.programado ? `<div class="vacio">Programa: ${fechaCl(e.programado.inicio)} → ${fechaCl(e.programado.termino)} ${pastilla(e.comparacion, NOMBRE_COMP)}</div>` : ''}
      ${estado.admin ? `<label>Cambiar estado
          <select data-entrega="${e.id}">${Object.entries(NOMBRE_ESTADO).filter(([k]) => k !== 'terminado')
            .map(([k, v]) => `<option value="${k}"${k === e.estado ? ' selected' : ''}>${v}</option>`).join('')}</select></label>
        <label>Fecha de entrega <input type="date" data-fecha="${e.id}" value="${e.fecha_entrega || ''}"></label>` : ''}
    </div>`).join('');
  panel.querySelectorAll('select[data-entrega]').forEach((s) => s.addEventListener('change', () => guardarEntrega(s.dataset.entrega)));
  panel.querySelectorAll('input[data-fecha]').forEach((i) => i.addEventListener('change', () => guardarEntrega(i.dataset.fecha)));
}

async function guardarEntrega(id) {
  const estadoNuevo = document.querySelector(`select[data-entrega="${id}"]`).value;
  const fecha = document.querySelector(`input[data-fecha="${id}"]`).value || null;
  try {
    await api(`/api/entregas/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ estado: estadoNuevo, fecha_entrega: fecha }) });
    await cargar();
  } catch (e) { alert(e.message); }
}

// ---------------- programa ----------------

function pintarPrograma() {
  const modo = estado.modoPrograma;
  document.querySelectorAll('#modo-programa button').forEach((b) => b.classList.toggle('activo', b.dataset.modo === modo));
  if (modo === 'programado') {
    leyenda($('#leyenda-programa'), [['var(--sin)', 'Sin intervenir'], ['var(--proceso)', 'En proceso'], ['var(--listo)', 'Entregado'], ['var(--sin-dato)', 'Sin programa']]);
  } else {
    leyenda($('#leyenda-programa'), [['var(--atrasado)', 'Atrasado'], ['var(--listo)', 'Al día'], ['var(--adelantado)', 'Adelantado'], ['var(--sin-dato)', 'Sin programa']]);
  }
  dibujarMapa($('#mapa-programa'), (e) => {
    if (!e.programado) return { color: 'var(--sin-dato)', titulo: 'Sin programa' };
    if (modo === 'programado') {
      return { color: COLOR_ESTADO[e.programado.estado], alerta: e.comparacion === 'atrasado', titulo: `Debería estar: ${NOMBRE_ESTADO[e.programado.estado]}` };
    }
    return { color: COLOR_COMP[e.comparacion], titulo: NOMBRE_COMP[e.comparacion] };
  }, (id) => { estado.sel.programa = id; pintarPrograma(); }, estado.sel.programa);

  const panel = $('#panel-programa');
  const id = estado.sel.programa;
  if (!id) {
    const sinGantt = !estado.datos.entregas.some((e) => e.programado);
    panel.innerHTML = sinGantt
      ? '<p class="vacio">Aún no se ha cargado la carta Gantt. El administrador puede subirla en "Cargar datos".</p>'
      : '<p class="vacio">Haga clic en un sitio del mapa para ver el detalle. Las zonas con borde rojo están atrasadas.</p>';
    return;
  }
  const t = estado.datos.terrenoPorId[id];
  panel.innerHTML = encabezadoTerreno(t) + (estado.datos.entregasPorTerreno[id] || []).map((e) => `
    <div class="bloque"><b>${esc(NOMBRE_ZONA[e.zona])}</b><br>
      ${e.programado
        ? `Programa: ${fechaCl(e.programado.inicio)} → ${fechaCl(e.programado.termino)}<br>
           Debería estar ${pastilla(e.programado.estado)} · Real ${pastilla(e.estado)}<br>${pastilla(e.comparacion, NOMBRE_COMP)}`
        : `<span class="vacio">Sin tarea en la carta Gantt</span> · Real ${pastilla(e.estado)}`}
    </div>`).join('');
}

// ---------------- movimiento de tierra ----------------

function avanceTerreno(id) {
  const as = estado.datos.actividadesPorTerreno[id] || [];
  const proy = as.reduce((s, a) => s + a.volumen_proyectado_m3, 0);
  const ret = as.reduce((s, a) => s + a.retirado_m3, 0);
  return { proy, ret, avance: proy > 0 ? ret / proy : null, actividades: as };
}

const ESCALA = ['#e6f2ea', '#b9dcc6', '#84c2a0', '#4fa379', '#2a7f57', '#17583b'];
function colorAvance(av) {
  if (av == null) return 'var(--sin-dato)';
  return ESCALA[Math.min(ESCALA.length - 1, Math.floor(Math.min(av, 1) * (ESCALA.length - 1) + 0.0001))];
}

function pintarTierra() {
  leyenda($('#leyenda-tierra'), [['var(--sin-dato)', 'Sin volumen proyectado'], [ESCALA[0], '0 %'], [ESCALA[2], '40 %'], [ESCALA[4], '80 %'], [ESCALA[5], '100 %']]);
  dibujarMapa($('#mapa-tierra'), (e) => {
    const { avance, ret, proy } = avanceTerreno(e.terreno_id);
    return { color: colorAvance(avance), titulo: avance == null ? `${num(ret, 1)} m³ retirados` : `${num(100 * avance)} % (${num(ret, 1)} de ${num(proy)} m³)` };
  }, (id) => { estado.sel.tierra = id; pintarTierra(); }, estado.sel.tierra);

  const id = estado.sel.tierra;
  if (!id) return;
  const t = estado.datos.terrenoPorId[id];
  const { actividades } = avanceTerreno(id);
  const panel = $('#panel-tierra');
  panel.innerHTML = encabezadoTerreno(t) + actividades.map((a) => `
    <div class="bloque">
      <b>${a.tipo === 'escarpe' ? 'Escarpe' : t.tipo === 'edificio' ? 'Corte (subterráneo)' : 'Corte'}</b> ${pastilla(a.estado)}
      <table>
        <tr><td>Proyectado</td><td class="num">${num(a.volumen_proyectado_m3, 1)} m³</td></tr>
        <tr><td>Viajes asignados</td><td class="num">${num(a.directo_m3, 1)} m³</td></tr>
        <tr><td>Prorrateo general</td><td class="num">${num(a.prorrateo_m3, 1)} m³</td></tr>
        <tr><td>Ajustes</td><td class="num">${num(a.ajustes_m3, 1)} m³</td></tr>
        <tr><th>Retirado</th><th class="num">${num(a.retirado_m3, 1)} m³</th></tr>
      </table>
      ${a.avance != null ? `<div class="barra-avance"><div style="width:${Math.min(100, 100 * a.avance)}%"></div></div><span class="vacio">${num(100 * a.avance, 1)} %</span>` : ''}
      ${a.programado ? `<div class="vacio">Programa: ${fechaCl(a.programado.inicio)} → ${fechaCl(a.programado.termino)} ${pastilla(a.comparacion, NOMBRE_COMP)}</div>` : ''}
      ${estado.admin ? `<label>Volumen proyectado (m³) <input type="number" min="0" step="0.1" data-vol="${a.id}" value="${a.volumen_proyectado_m3}"></label>
        <label>Estado <select data-act="${a.id}">${['sin_intervenir', 'en_proceso', 'terminado']
          .map((k) => `<option value="${k}"${k === a.estado ? ' selected' : ''}>${NOMBRE_ESTADO[k]}</option>`).join('')}</select></label>` : ''}
    </div>`).join('');
  panel.querySelectorAll('[data-vol],[data-act]').forEach((el) => el.addEventListener('change', async () => {
    const aid = el.dataset.vol || el.dataset.act;
    try {
      await api(`/api/actividades/${aid}`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          volumen_proyectado_m3: Number(panel.querySelector(`[data-vol="${aid}"]`).value || 0),
          estado: panel.querySelector(`[data-act="${aid}"]`).value,
        }),
      });
      await cargar();
    } catch (e) { alert(e.message); }
  }));
}

// ---------------- viajes ----------------

async function pintarViajes() {
  if (!$('#viajes-desde').value) $('#viajes-desde').value = $('#viajes-hasta').value = estado.datos.hoy;
  const filas = await api(`/api/viajes?desde=${$('#viajes-desde').value}&hasta=${$('#viajes-hasta').value}`);
  const total = filas.reduce((s, f) => s + f.volumen_m3, 0);
  $('#tabla-viajes').innerHTML = filas.length
    ? `<p>${filas.length} viajes · ${new Set(filas.map((f) => f.patente)).size} camiones · <b>${num(total, 1)} m³</b></p>
       <div class="tabla-scroll"><table><thead><tr><th>Fecha</th><th>Hora</th><th>Patente</th><th>Empresa</th><th>Origen</th><th>Actividad</th><th class="num">m³</th></tr></thead>
       <tbody>${filas.map((f) => `<tr><td>${fechaCl(f.salida_en)}</td><td>${esc(f.salida_en.slice(11))}</td><td>${esc(f.patente)}</td>
         <td>${esc(f.empresa || '')}</td><td>${esc(nombreOrigen(f.origen))}</td><td>${esc(f.actividad || '')}</td><td class="num">${num(f.volumen_m3, 1)}</td></tr>`).join('')}</tbody></table></div>`
    : '<p class="vacio">No hay salidas registradas en el período.</p>';
}

// ---------------- carga de archivos ----------------

let tiposCarga = null;
async function pintarCargas() {
  if (!estado.admin) return;
  tiposCarga ||= await api('/api/importar/tipos');
  const cont = $('#tipos-carga');
  if (!cont.children.length) {
    cont.innerHTML = tiposCarga.map((t) => `
      <div class="tarjeta" data-tipo="${t.id}">
        <h2>${esc(t.titulo)}<span class="modo modo-${t.modo}">${t.modo.toUpperCase()}</span></h2>
        <p class="ayuda">${esc(t.ayuda)}</p>
        <ul class="columnas">${t.columnas.map((c) => `<li><code>${esc(c.campo)}</code>${c.requerido ? ' (obligatoria)' : ''}${c.descripcion ? ` — ${esc(c.descripcion)}` : ''}</li>`).join('')}</ul>
        <div class="fila-botones">
          <a class="btn chico" href="/api/plantillas/${t.id}">Descargar plantilla</a>
          <input type="file" accept=".csv,.txt,.xlsx">
        </div>
        <div class="fila-botones">
          <button class="btn" data-accion="revisar" disabled>Revisar archivo</button>
          <button class="btn primario" data-accion="aplicar" disabled>Confirmar carga</button>
        </div>
        <div class="resultado" hidden></div>
      </div>`).join('');
    cont.querySelectorAll('[data-tipo]').forEach(prepararTarjetaCarga);
  }
  const cargas = await api('/api/cargas');
  const deshacible = new Set(['viajes', 'ajustes', 'gantt']);
  $('#historial-cargas').innerHTML = cargas.length
    ? `<div class="tabla-scroll"><table><thead><tr><th>Fecha</th><th>Tipo</th><th>Archivo</th><th>Resultado</th><th></th></tr></thead><tbody>${cargas.map((c) => `
        <tr><td>${esc(c.creado_en)} UTC</td><td>${esc(c.tipo)}</td><td>${esc(c.archivo)}</td>
        <td>${esc(Object.entries(c.resumen).map(([k, v]) => `${k.replace(/_/g, ' ')}: ${v}`).join(' · '))}</td>
        <td>${deshacible.has(c.tipo) ? `<button class="btn chico" data-deshacer="${c.id}">Deshacer</button>` : ''}</td></tr>`).join('')}</tbody></table></div>`
    : '<p class="vacio">Todavía no se han cargado archivos.</p>';
  $('#historial-cargas').querySelectorAll('[data-deshacer]').forEach((b) => b.addEventListener('click', async () => {
    if (!confirm('¿Deshacer esta carga? Se eliminarán los registros que agregó.')) return;
    try { await api(`/api/cargas/${b.dataset.deshacer}`, { method: 'DELETE' }); await cargar(); } catch (e) { alert(e.message); }
  }));
}

function prepararTarjetaCarga(tarjeta) {
  const tipo = tarjeta.dataset.tipo;
  const input = tarjeta.querySelector('input[type=file]');
  const revisar = tarjeta.querySelector('[data-accion=revisar]');
  const aplicar = tarjeta.querySelector('[data-accion=aplicar]');
  const salida = tarjeta.querySelector('.resultado');
  input.addEventListener('change', () => { revisar.disabled = !input.files.length; aplicar.disabled = true; salida.hidden = true; });

  async function enviar(confirmar) {
    const fd = new FormData();
    fd.append('archivo', input.files[0]);
    revisar.disabled = aplicar.disabled = true;
    salida.hidden = false;
    salida.innerHTML = 'Procesando…';
    try {
      const r = await api(`/api/importar/${tipo}${confirmar ? '?aplicar=1' : ''}`, { method: 'POST', body: fd });
      salida.innerHTML = describirResultado(r, confirmar);
      aplicar.disabled = confirmar || !r.ok || !hayCambios(r);
      if (confirmar) { input.value = ''; await cargar(); }
    } catch (e) {
      salida.innerHTML = `<span class="error">${esc(e.message)}</span>`;
    }
    revisar.disabled = !input.files.length;
  }
  revisar.addEventListener('click', () => enviar(false));
  aplicar.addEventListener('click', () => enviar(true));
}

const hayCambios = (r) => Object.entries(r.resumen).some(([k, v]) => ['nuevas', 'actualizadas'].includes(k) && v > 0);

function describirResultado(r, confirmado) {
  if (!r.ok) {
    return `<span class="error">Faltan columnas: <b>${esc(r.faltan_columnas.join(', '))}</b>.</span><br>
      Columnas encontradas: ${esc(r.encabezados.filter(Boolean).join(', ') || '(ninguna)')}. Revise la plantilla.`;
  }
  const res = Object.entries(r.resumen).map(([k, v]) => `${k.replace(/_/g, ' ')}: <b>${esc(v)}</b>`).join(' · ');
  const titulo = confirmado
    ? (r.aplicado ? '<b class="ok">Carga guardada.</b>' : '<b>No había filas válidas para guardar.</b>')
    : `<b>Revisión (${r.filas} filas leídas, aún no se guarda nada)</b>`;
  const errores = r.total_errores
    ? `<div class="error">${r.total_errores} filas con problemas (se omitirán):</div><ul>${r.errores.map((e) => `<li>Fila ${e.fila}: ${esc(e.mensaje)}</li>`).join('')}</ul>`
    : '';
  return `${titulo}<br>${res}${errores}`;
}

// ---------------- sesión y navegación ----------------

function aplicarSesion(admin) {
  estado.admin = admin;
  document.body.classList.toggle('admin', admin);
  $('#btn-sesion').textContent = admin ? 'Salir (administrador)' : 'Ingresar';
  if (!admin && estado.vista === 'cargar') cambiarVista('resumen');
}

function cambiarVista(v) {
  estado.vista = v;
  document.querySelectorAll('#pestanas button').forEach((b) => b.classList.toggle('activa', b.dataset.vista === v));
  document.querySelectorAll('.vista').forEach((s) => s.classList.toggle('activa', s.id === `vista-${v}`));
  if (estado.datos) pintar();
}

$('#pestanas').addEventListener('click', (ev) => { const b = ev.target.closest('button'); if (b) cambiarVista(b.dataset.vista); });
$('#modo-programa').addEventListener('click', (ev) => { const b = ev.target.closest('button'); if (b) { estado.modoPrograma = b.dataset.modo; pintarPrograma(); } });
$('#fecha').addEventListener('change', cargar);
['#viajes-desde', '#viajes-hasta'].forEach((s) => $(s).addEventListener('change', pintarViajes));

$('#btn-sesion').addEventListener('click', async () => {
  if (estado.admin) {
    await api('/api/logout', { method: 'POST' });
    aplicarSesion(false);
    pintar();
  } else {
    $('#login-error').textContent = '';
    $('#dlg-login').showModal();
    $('#clave').focus();
  }
});
$('#login-cancelar').addEventListener('click', () => $('#dlg-login').close());
$('#form-login').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  try {
    await api('/api/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ clave: $('#clave').value }) });
    $('#clave').value = '';
    $('#dlg-login').close();
    aplicarSesion(true);
    pintar();
  } catch (e) {
    $('#login-error').textContent = e.message;
  }
});

(async () => {
  const s = await api('/api/sesion');
  aplicarSesion(s.admin);
  await cargar();
})().catch((e) => { document.querySelector('main').innerHTML = `<p class="error">No se pudo cargar la información: ${esc(e.message)}</p>`; });
