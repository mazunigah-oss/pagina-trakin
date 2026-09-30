# Plataforma de seguimiento de movimiento de tierra — Análisis de requerimientos

Versión 0.4 · 30-09-2026 · Aplicación en Streamlit, formato real de tickets de la máquina (ver README).

## 1. Objetivo

Página web, accesible desde cualquier computador o celular con navegador, para registrar y visualizar el avance del movimiento de tierra de una obra compuesta por **48 sitios**, **edificios**, **pasajes** y una **calle dividida en tramos**.

- **Administrador**: sube y edita toda la información.
- **Visita**: solo visualiza (sin botones de edición).

## 2. Roles y acceso

- **Administrador**: cuenta con usuario y contraseña. Es el único que puede modificar.
- **Visita**: acceso **libre, sin contraseña** (solo lectura). Cualquiera con el enlace puede ver.

Los permisos de escritura se validan en el servidor (no basta con ocultar botones).

## 3. Mapa base

| Variable | Tipo | Nota |
|---|---|---|
| imagen del plano | archivo PNG/JPG/PDF→imagen | la sube el admin; se puede reemplazar |
| ancho / alto (px) | número | para ubicar las áreas sobre la imagen |
| fecha de carga | fecha | versión del plano |

Sobre la imagen, el admin **dibuja un polígono** por cada elemento (una sola vez). Así la imagen se vuelve interactiva: clic en un sitio → ver su información y color según estado.

## 4. Terrenos (elementos de la obra)

Un solo catálogo de "terrenos" con un tipo:

| Variable | Tipo | Nota |
|---|---|---|
| código | texto | ej. `S-01`…`S-48`, `ED-A`, `P-1`, `T-1` |
| tipo | `sitio` \| `edificio` \| `pasaje` \| `tramo_calle` | |
| nombre | texto | |
| polígono en el mapa | lista de puntos (x,y) | dibujado por el admin |
| observaciones | texto | |

### 4.1 Actividades de movimiento de tierra (todos los terrenos)

Cada terreno tiene **dos actividades**: **escarpe** y **corte** (en edificios, el corte es la excavación del **subterráneo**).

| Variable | Tipo | Nota |
|---|---|---|
| terreno | referencia | |
| actividad | `escarpe` \| `corte` | |
| volumen proyectado (m³) | número | según proyecto |
| volumen retirado (m³) | **calculado** | ver §5.3 |
| % avance | **calculado** | retirado / proyectado |
| estado | `sin intervenir` \| `en proceso` \| `terminado` | |

### 4.2 Entregas

- **Sitio**: el terreno se divide en 3 partes y cada una se entrega por separado → **48 × 3 = 144 entregas**:
  `acceso` (por donde se entra), `living` (donde se emplaza la casa) y `fondo de patio`.
- **Edificio**: una sola zona → 1 entrega.
- **Pasaje / tramo de calle**: 1 entrega (supuesto, a confirmar).

| Variable | Tipo | Nota |
|---|---|---|
| terreno | referencia | |
| zona | `acceso` \| `living` \| `fondo_patio` \| `unica` | |
| polígono en el mapa | puntos (x,y) | |
| estado | `sin intervenir` \| `en proceso` \| `entregado` | |
| fecha de entrega | fecha | se llena al pasar a entregado |

## 5. Camiones y viajes

### 5.1 Maestro de camiones

| Variable | Tipo | Nota |
|---|---|---|
| patente | texto | formato chileno |
| id tarjeta | texto | lo que registra la máquina lectora |
| capacidad (m³) | número | **el volumen de cada viaje = capacidad del camión** |
| empresa | texto | opcional |
| activo | sí/no | |

### 5.2 Viajes (importados del CSV diario)

La máquina lectora de tarjetas entrega un **CSV diario**. El admin lo sube y la página:

1. Lee cada fila (fecha, hora de salida, tarjeta/patente).
2. Busca el camión y asigna m³ = capacidad del camión (se guarda la capacidad del momento, por si luego cambia).
3. Descarta filas ya importadas (no se duplican si se sube dos veces el mismo archivo).
4. Avisa de tarjetas/patentes desconocidas para darlas de alta.

| Variable | Tipo | Nota |
|---|---|---|
| fecha y hora de salida | fecha-hora | del CSV |
| patente / tarjeta | texto | del CSV |
| volumen (m³) | número | capacidad del camión |
| terreno | referencia, **opcional** | si se sabe de dónde salió |
| actividad | `escarpe` \| `corte`, opcional | |
| archivo de origen | texto | trazabilidad |

### 5.3 Cómo se calcula el volumen retirado por terreno

```
retirado(terreno, actividad) =
    viajes asignados a ese terreno
  + prorrateo de los viajes "generales" (sin terreno)
  + ajustes manuales del admin (ej. topografía)
```

- **Viajes generales**: los viajes sin terreno se reparten **proporcionalmente** entre los terrenos.
  Regla propuesta (a confirmar): cada día, el volumen general se reparte entre los terrenos/actividades
  que estaban *en proceso* ese día, en proporción a su volumen proyectado. Si ninguno estaba en proceso,
  entre todos los que no están terminados.
- **Ajustes manuales**: terreno, actividad, fecha, m³ (+/−), motivo.

## 6. Carta Gantt (programa)

Se carga desde **Excel**. Está **por zona de cada sitio**, ej.:
*"Entrega acceso sitio 15 — semana del 15 al 20 de septiembre"*.

| Variable | Tipo | Nota |
|---|---|---|
| tarea | texto | texto original de la fila |
| terreno | referencia | se reconoce del texto (ej. "sitio 15") |
| zona o actividad | `acceso` / `living` / `fondo_patio` / `escarpe` / `corte` … | se reconoce del texto |
| fecha inicio / término | fecha | la semana indicada |

**Estado programado a hoy** para cada entrega:
- hoy < inicio → *sin intervenir*
- inicio ≤ hoy ≤ término → *en proceso*
- hoy > término → *entregado*

Comparado con el estado real → **atrasado / al día / adelantado**.

## 7. Qué muestra el visualizador (acceso libre, sin contraseña)

1. **Resumen del día**: N° de camiones (viajes) hoy, m³ hoy, m³ por terreno de origen (incluye "general"),
   acumulado total vs. proyectado.
2. **Mapa de movimiento de tierra**: terrenos coloreados por estado de escarpe/corte y % avance.
3. **Mapa de entregas**: 48 sitios × 3 zonas + edificios/pasajes/tramos, coloreados
   sin intervenir / en proceso / entregado.
4. **Mapa programado (Gantt)**: cómo debería verse la obra hoy, y atrasos.
5. **Evolución en el tiempo**: curva de m³ acumulados y entregas acumuladas, real vs. programado
   (la página se sigue alimentando día a día y guarda el historial).

## 8. Qué hace el Administrador (con contraseña)

- Subir / reemplazar el plano y dibujar los polígonos.
- Mantener terrenos, volúmenes proyectados y estados.
- Marcar entregas (sin intervenir / en proceso / entregado).
- Subir el CSV diario de camiones, asignar viajes a terrenos, ajustes manuales.
- Mantener el maestro de camiones (patente, tarjeta, capacidad).
- Subir / reemplazar la carta Gantt en Excel.

## 9. Factibilidad e implementación

Implementado como aplicación **Streamlit** (Python), publicable en Streamlit Community Cloud (ver README).

| Pieza | Implementación |
|---|---|
| App | Streamlit + Plotly (plano interactivo con hover y zoom) |
| Datos | SQLAlchemy: PostgreSQL en la nube (`DATABASE_URL`, ej. Neon/Supabase) o SQLite local |
| Acceso | Visita libre; administrador con contraseña (`ADMIN_PASSWORD` en Secrets) |
| Cargas | CSV/Excel con revisión previa, modos SUMA / ACTUALIZA / REEMPLAZA, historial y deshacer |
| Plano | `scripts/procesar_dxf.py`: 144 terrazas desde el DXF, sin intervención manual |

## 10. Decisiones tomadas (respuestas del 30-09-2026)

| Tema | Decisión |
|---|---|
| Sector | Cada sitio se divide en 3 entregas: acceso, living (casa), fondo de patio |
| Edificios | Una sola zona; actividades subterráneo (corte) y escarpe |
| Actividades | Todos los terrenos tienen corte y escarpe |
| m³ por viaje | Capacidad del camión |
| m³ por terreno | Viajes asignados + prorrateo de viajes generales + ajustes manuales |
| Estados de zona | Sin intervenir / en proceso / entregado |
| Registro de camiones | CSV de la máquina: `TICKET;FECHA;HORA;PATENTE;VOLUMEN_M3;SECTOR;TIPO;ESTADO`. El volumen viene en el ticket (no se necesita maestro de camiones). Las anulaciones restan |
| Visitas | Acceso libre, sin cuenta |
| Carta Gantt | Por ahora CSV con inicio y término del movimiento de tierra por sitio (2 sitios por semana según el Gantt real) |
| Horizonte | La página se seguirá alimentando para seguir el avance de la urbanización |

## 11. Pendiente

1. **Base de datos permanente** para Streamlit Cloud (Neon o Supabase) y contraseña de administrador.
2. **Carta Gantt completa**: hoy el ejemplo usa la fila "Excavación a máquina zonas de arcilla bajo radieres";
   desde el sitio 39 las semanas son extrapoladas. Se puede agregar lectura directa del Excel del Gantt
   (celdas "3-4" por semana).
3. **DXF según `FORMATO_DXF.md`**: el `Lomas3.dxf` recibido es idéntico al plano anterior (solo líneas, sin capa
   `Patio`); el procesador igual lo lee correctamente.
4. **Pasajes y calle**: sin polígonos en el DXF.
5. **Regla de prorrateo**: proporcional al volumen proyectado de las actividades *actualmente* en proceso.
