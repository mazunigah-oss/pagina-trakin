# Plataforma de seguimiento de movimiento de tierra — Análisis de requerimientos

Versión 0.1 · 30-09-2026 · Documento de levantamiento (sin código aún)

## 1. Objetivo

Página web, accesible desde cualquier computador o celular con navegador, para registrar y visualizar el avance del movimiento de tierra de una obra compuesta por **48 sitios**, **edificios**, **pasajes** y una **calle dividida en tramos**.

- **Administrador**: sube y edita toda la información.
- **Visita**: solo visualiza (sin botones de edición).

## 2. Roles y acceso

| Variable | Tipo | Nota |
|---|---|---|
| usuario / email | texto | único |
| contraseña | hash | nunca se guarda en texto plano |
| rol | `admin` \| `visita` | define permisos |
| activo | sí/no | para quitar acceso sin borrar |

Los permisos se validan en el servidor (no basta con ocultar botones).

## 3. Mapa base

| Variable | Tipo | Nota |
|---|---|---|
| imagen del plano | archivo PNG/JPG/PDF→imagen | la sube el admin; se puede reemplazar |
| ancho / alto (px) | número | para ubicar las áreas sobre la imagen |
| fecha de carga | fecha | versión del plano |

Sobre la imagen, el admin **dibuja un polígono** por cada elemento (una sola vez). Así la imagen se vuelve interactiva: clic en un sitio → ver su información y color según estado.

## 4. Elementos de la obra

Un solo catálogo de "elementos" con un tipo:

| Variable | Tipo | Nota |
|---|---|---|
| código | texto | ej. `S-01`…`S-48`, `ED-A`, `P-1`, `T-1` |
| tipo | `sitio` \| `edificio` \| `pasaje` \| `tramo_calle` | |
| nombre | texto | |
| sector | texto | agrupación (ver preguntas abiertas) |
| polígono en el mapa | lista de puntos (x,y) | dibujado por el admin |
| volumen proyectado (m³) | número | total a retirar según proyecto |
| volumen retirado (m³) | **calculado** | suma de los viajes de camión con ese origen |
| % avance | **calculado** | retirado / proyectado |
| estado | `sin intervenir` \| `en proceso` \| `listo y entregado` | lo fija el admin |
| fecha de entrega | fecha | cuando pasa a entregado |
| observaciones | texto | |

### 4.1 Subdivisión de cada sitio (48 × 3 = 144 zonas)

| Variable | Tipo | Nota |
|---|---|---|
| sitio | referencia | S-01 … S-48 |
| zona | `acceso` \| `living` \| `fondo de patio` | |
| polígono en el mapa | puntos (x,y) | |
| estado | `entregado` \| `no entregado` (opcionalmente `en proceso`) | |
| fecha de entrega | fecha | |

## 5. Registro de camiones (salidas)

Cada registro es **un viaje de salida** de la obra.

| Variable | Tipo | Obligatorio | Nota |
|---|---|---|---|
| fecha | fecha | sí | |
| hora de salida | hora | sí | zona horaria Chile |
| patente | texto | sí | validar formato chileno (`ABCD12` / `AB1234`) |
| cantidad (m³) | número | sí | volumen del viaje |
| origen | elemento (y zona si es sitio) | sí | necesario para saber "de qué sitios" salió la tierra |
| destino / botadero | texto | opcional | |
| empresa / conductor | texto | opcional | |
| registrado por | usuario | automático | trazabilidad |

Opcional: maestro de camiones (patente → empresa, capacidad nominal en m³) para autocompletar la cantidad.
También: carga masiva desde Excel/CSV para no digitar viaje por viaje.

## 6. Carta Gantt (programa)

| Variable | Tipo | Nota |
|---|---|---|
| tarea / actividad | texto | |
| elemento (y zona) asociada | referencia | para pintar el mapa "programado" |
| fecha inicio | fecha | |
| fecha término | fecha | |
| volumen planificado (m³) | número | opcional, para curva programado vs. real |

Carga: planilla Excel/CSV (o exportada desde MS Project) con esas columnas, o edición manual.

**Estado programado a hoy** (calculado para cada elemento):
- hoy < inicio → debería estar *sin intervenir*
- inicio ≤ hoy ≤ término → debería estar *en proceso* (avance esperado lineal = días transcurridos / duración)
- hoy > término → debería estar *entregado*

Comparando con el estado real se marca **atrasado / al día / adelantado**.

## 7. Qué muestra el visualizador (Visita)

1. **Resumen del día** (tarjetas):
   - N° de camiones (viajes) hoy
   - m³ retirados hoy
   - Sitios/elementos de origen hoy (tabla con m³ por origen)
   - Acumulado total vs. proyectado (%)
2. **Mapa de estado real**: elementos coloreados por estado (sin intervenir / en proceso / entregado); clic para ver m³ proyectado, retirado y avance.
3. **Mapa interactivo de sitios**: los 48 sitios con sus 3 zonas (acceso, living, fondo de patio) coloreadas entregado / no entregado.
4. **Mapa programado (Gantt)**: cómo debería verse la obra hoy según la carta Gantt, y diferencias contra lo real.
5. (Opcional) tabla de viajes filtrable por fecha, patente u origen; exportar a Excel.

## 8. Qué hace el Administrador

- Subir / reemplazar el plano y dibujar los polígonos.
- Crear y editar elementos, volúmenes proyectados y estados.
- Marcar zonas de los sitios como entregadas.
- Registrar, editar y eliminar viajes de camión (manual o por Excel).
- Cargar / editar la carta Gantt.
- Gestionar usuarios (crear visitas, desactivar accesos).

## 9. Factibilidad

**Sí es factible** como aplicación web estándar, accesible desde cualquier computador (y celular) con un navegador, sin instalar nada.

Arquitectura propuesta:

| Pieza | Propuesta | Por qué |
|---|---|---|
| Frontend | Next.js (React) | una sola app para admin y visita |
| Mapa interactivo | Leaflet con imagen del plano (`CRS.Simple`) + polígonos, o SVG sobre la imagen | zoom, clic, colores por estado |
| Base de datos | PostgreSQL (Supabase) | datos relacionales, consultas por fecha |
| Autenticación y roles | Supabase Auth + reglas por rol | login admin / visita |
| Archivos (plano) | Supabase Storage | imágenes del mapa |
| Hosting | Vercel + Supabase | plan gratuito suficiente para este volumen; HTTPS incluido |

Volumen de datos esperado: bajo (≈200 elementos/zonas, algunos cientos de viajes al día como máximo), sin problemas de rendimiento.

Único trabajo manual relevante: **dibujar una vez los polígonos** de los 48 sitios, 144 zonas, pasajes y tramos sobre el plano (se hace con una herramienta de dibujo dentro del panel admin).

## 10. Preguntas abiertas (a definir antes de programar)

1. **"Sector"**: ¿es una agrupación de varios sitios (ej. Sector A = sitios 1–12) o se refiere a las zonas acceso/living/fondo de patio?
2. **Edificios**: ¿se controlan igual que los sitios (m³ y estado) y también se subdividen?
3. **m³ por viaje**: ¿se mide/estima por viaje o se usa la capacidad nominal del camión?
4. **Volumen por sitio**: ¿se calcula solo desde los viajes de camión, o el admin también puede ingresarlo directo (ej. por topografía)?
5. **Zonas de sitio**: ¿solo entregado / no entregado, o también "en proceso"?
6. **Quién registra camiones**: ¿solo el administrador, o un controlador en portería desde el celular (tercer rol "registrador")?
7. **Visitas**: ¿una cuenta compartida o una cuenta por persona?
8. **Carta Gantt**: ¿en qué formato la tienen hoy (Excel, MS Project, PDF)? ¿La tarea está a nivel de sitio o de zona?
9. **Plano**: ¿un solo plano, o puede haber varios (etapas)?
