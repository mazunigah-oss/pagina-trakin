# Plataforma de avance de movimiento de tierra

Página web para seguir el movimiento de tierra y las entregas de una urbanización de 48 sitios
(cada uno dividido en acceso, living y fondo de patio) y 2 edificios.

- **Visita**: acceso libre, solo lectura.
- **Administrador**: botón "Ingresar" con contraseña; puede editar estados y cargar archivos.

Requerimientos y decisiones: [`docs/01-analisis-requerimientos.md`](docs/01-analisis-requerimientos.md).

## Qué muestra

| Pestaña | Contenido |
|---|---|
| Resumen | Camiones, viajes y m³ del día; origen de la tierra por sitio; m³ de los últimos 30 días; conteo de entregas y atrasos |
| Entregas | Plano con las 146 zonas coloreadas por estado real (sin intervenir / en proceso / entregado) |
| Programa (Gantt) | Cómo deberíamos ir a la fecha según la carta Gantt, y real vs. programado (atrasado / al día / adelantado) |
| Movimiento de tierra | % de avance escarpe + corte por terreno (m³ retirados / proyectados), con detalle del cálculo |
| Camiones | Listado de salidas filtrable por fechas |
| Cargar datos | (admin) Subida de archivos CSV/Excel con revisión previa e historial |

El selector "Ver al día" permite ver cualquier fecha pasada o futura.

## Cargar información con archivos

Cada tipo de archivo tiene una plantilla (botón "Descargar plantilla" en la página, o ejemplos en
[`data/ejemplos/`](data/ejemplos)). Se aceptan `.csv` (separado por `;` o `,`) y `.xlsx`.
Los encabezados no distinguen mayúsculas ni tildes y aceptan sinónimos (ej. `placa` = `patente`).

| Archivo | Modo | Qué hace |
|---|---|---|
| Salidas de camiones | **SUMA** | Agrega viajes. m³ = capacidad del camión. Omite los que ya estaban (misma patente + fecha + hora), así que se puede subir el mismo archivo dos veces. Sin sitio → "General" (se prorratea). |
| Maestro de camiones | **ACTUALIZA** | Crea o modifica camiones por patente (capacidad, tarjeta, empresa). |
| Volúmenes proyectados | **ACTUALIZA** | m³ proyectados y estado de escarpe / corte por terreno. |
| Estado de entregas | **ACTUALIZA** | Estado y fecha de entrega de acceso / living / fondo de patio. |
| Ajustes de volumen | **SUMA** | Suma o resta m³ a una actividad (ej. por topografía). |
| Carta Gantt | **REEMPLAZA** | Borra el programa anterior y carga el nuevo. Reconoce textos como "Entrega acceso sitio 15" y "semana del 15 al 20 de septiembre". |

Flujo: elegir archivo → **Revisar** (muestra cuántas filas se agregan o actualizan y los errores por fila, sin guardar) →
**Confirmar carga**. Las cargas que suman o reemplazan se pueden **deshacer** desde el historial.

### Cómo se calculan los m³ retirados

```
retirado = viajes asignados al terreno (y actividad)
         + prorrateo de viajes "General" (proporcional al volumen proyectado de las actividades en proceso)
         + ajustes manuales
```

## Ejecutar

Requiere Node.js 20 o superior.

```bash
npm install
ADMIN_PASSWORD='una-clave-segura' npm start        # http://localhost:3000
```

Variables de entorno:

| Variable | Uso |
|---|---|
| `ADMIN_PASSWORD` | Contraseña del administrador (obligatoria al publicar; si falta se usa `admin`) |
| `PORT` | Puerto (por defecto 3000) |
| `DB_PATH` | Archivo de la base de datos SQLite (por defecto `data/obra.db`) |
| `SESSION_SECRET` | Opcional, clave para firmar la sesión |

Para ver la página con datos de ejemplo: `node scripts/generar_ejemplos.js --cargar` (antes de `npm start`).

Pruebas: `npm test`.

## Publicar en internet

Es un solo proceso Node con una base SQLite en un archivo, así que sirve cualquier servidor con disco persistente:
Railway, Render (con disco), Fly.io (con volumen) o un VPS. Configurar `ADMIN_PASSWORD`, apuntar `DB_PATH`
al disco persistente y respaldar ese archivo periódicamente.

## Plano

`data/geometria.json` contiene los polígonos (en metros) generados desde el DXF con
`scripts/procesar_dxf.py` (ver instrucciones en el script). Si cambia el plano, se vuelve a ejecutar el script
y se reinicia la base de datos.

## Estructura

```
src/server.js      API y servidor web
src/db.js          esquema SQLite y carga inicial de terrenos/zonas
src/calculos.js    volúmenes, prorrateo, estado programado vs real, resumen del día
src/importar.js    lectura y validación de archivos CSV/Excel
public/            página (HTML, CSS, JS sin dependencias)
data/geometria.json, data/fuente/   plano procesado y archivos fuente (DXF, PNG)
data/ejemplos/     archivos de ejemplo con el formato de cada carga
```
