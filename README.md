# Avance movimiento de tierra — Loma La Cruz

Aplicación web (Streamlit) para seguir el movimiento de tierra y las entregas de terrazas de
48 sitios (Etapas 1 y 2), cada uno dividido en **acceso, living y fondo de patio**, más 2 edificios.

- **Visita**: acceso libre, solo lectura.
- **Administrador**: barra lateral → "Acceso administrador" (contraseña = secreto `ADMIN_PASSWORD`).

Requerimientos y decisiones: [`docs/01-analisis-requerimientos.md`](docs/01-analisis-requerimientos.md).

## Pestañas

| Pestaña | Contenido |
|---|---|
| Resumen | Movimiento de camiones del día anterior; avance de movimiento de tierra, extra y cumplimiento; **Mapa de intervención** (sitios al 100 % / con intervención, ⚠️ = movimiento extra) y **Mapa de entregas y cumplimiento** (acceso y living: ✅ entregada, ⚠️ debería estar entregada según la carta Gantt) |
| Entregas | Mapa de entregas y detalle por sitio: estado de cada terraza, fecha de la carta Gantt y cumplimiento |
| Programa | Dos mapas: cómo deberíamos ir según la carta Gantt (verde = 100 % y ✅ entregados, amarillo = con intervención) y qué está pasando (✅ entregados, verde = movimiento sobre 95 %, amarillo = con intervención) |
| Movimiento de tierra | Escarpe, corte y extra como en la hoja resumen; mapa por sitio (clic para ver el detalle) con notas 📌 (responsable, fecha y hora; el administrador agrega actualizaciones) |
| Tickets | Tickets de la máquina filtrables por fecha |
| Cargar datos *(admin)* | Subida de archivos con revisión previa, historial y deshacer |
| Editar estados *(admin)* | Tabla editable de estados de terrazas y volúmenes |

**Reglas:** el avance de movimiento de tierra es m³ retirados / m³ proyectados (no depende de la carta Gantt). Un sitio
**cumple la carta Gantt** cuando sus terrazas de **acceso y living** están entregadas; el fondo de patio no se considera.
Los mapas son imágenes fijas (sin zoom) con información al pasar el cursor.

## Carga inicial Loma La Cruz Norte (datos al 04/10/2026)

En [`data/carga_inicial/`](data/carga_inicial) están los datos de obra listos para subir en **Cargar datos**, en este orden:

| # | Archivo | Tipo de carga |
|---|---|---|
| 1 | `1_sitios_volumen_avance_programa.csv` | Avance acumulado por sitio |
| 2 | `5_programa_gantt.csv` (carta Gantt nueva, 47 sitios) | Programa (carta Gantt) |
| 3 | `2_adicional_botadero.csv` | Avance acumulado por sitio |
| 5 | `4_hitos.csv` | Hitos de la obra |

Volumen proyectado = esponjado (excavación × 1,43), que es lo que trasladan los camiones.

La carta Gantt en Excel (semanas en columnas, celdas como `6-5` = sitios 6 y 5) se convierte con
`python scripts/gantt_excel_a_csv.py Gantt.xlsx data/carga_inicial/5_programa_gantt.csv`. Cada sitio va del lunes
de su primera tarea ("Entrega de plataformas") al viernes de la última ("Relleno compactado").
`5_programa_gantt_detalle.csv` tiene cada tarea por semana, solo como respaldo (no se sube).

## Actualización al 19/10/2026

En [`data/carga_2026-10-19/`](data/carga_2026-10-19) está el avance al 16/10 (planilla *Resumen x Terraza*, sin
camino), los tickets del 19/10 y las terrazas entregadas (solo acceso y living), con el documento
[`avance_al_19-10-2026.md`](data/carga_2026-10-19/avance_al_19-10-2026.md) que explica los supuestos.
Se cargan sobre lo anterior en el orden indicado en ese documento.

## Archivos que se cargan

En **Cargar datos** (Excel o CSV; se revisa antes de guardar y se puede deshacer desde el historial):

| Carga | Modo | Qué se sube |
|---|---|---|
| **Movimiento de tierra por sitio** | ACTUALIZA | Se elige la fecha de los datos y se sube **la planilla de obra "Resumen x Terraza" tal cual** (lee escarpe, corte, esponjado, m³ a botadero y los extra; ignora el camino; reconoce sitios mal numerados por sus volúmenes) **o** una tabla simple `sitio;volumen_proyectado_m3;avance_pct` (o `m3_acumulados`). Cada sitio queda en el valor informado a esa fecha |
| **Tickets de camiones** | SUMA | CSV de la máquina: `TICKET;FECHA;HORA;PATENTE;VOLUMEN_M3;SECTOR;TIPO;ESTADO` |
| **Estado de entregas de terrazas** | ACTUALIZA | `sitio;zona;estado;fecha_entrega` |
| **Programa (carta Gantt)** | REEMPLAZA | `sitio;inicio;termino` (el Excel semanal se convierte con `scripts/gantt_excel_a_csv.py`) |
| Ajustes de volumen *(otras cargas)* | SUMA | `sitio;actividad;fecha;volumen_m3;motivo` |
| Hitos *(otras cargas)* | REEMPLAZA | `hito;fecha` |

## Publicar en Streamlit Community Cloud

1. Entrar a <https://share.streamlit.io> con la cuenta de GitHub que tiene acceso a este repositorio.
2. **Create app** → *Deploy a public app from GitHub*:
   - Repository: `mazunigah-oss/pagina-trakin`
   - Branch: la rama con este código (por ejemplo `main` después de unir los cambios)
   - Main file path: `streamlit_app.py`
3. **Advanced settings** → Python 3.12 y en **Secrets** pegar (ver `.streamlit/secrets.toml.example`):
   ```toml
   ADMIN_PASSWORD = "una-clave-segura"
   DATABASE_URL = "postgresql://..."
   ```
4. **Deploy**. La URL queda como `https://<nombre>.streamlit.app`.

**Importante — dónde se guardan los datos:** Streamlit Community Cloud borra los archivos de la app cada vez que se
reinicia (actualizaciones, inactividad). Para no perder lo cargado, use una base PostgreSQL gratuita
([Neon](https://neon.tech) o [Supabase](https://supabase.com)) y ponga su cadena de conexión en `DATABASE_URL`. Las tablas
se crean solas la primera vez. Sin `DATABASE_URL` la app funciona, pero con un archivo SQLite temporal.

## Ejecutar localmente

```bash
pip install -r requirements.txt
python scripts/generar_ejemplos.py --cargar   # opcional: datos de ejemplo
ADMIN_PASSWORD=demo streamlit run streamlit_app.py
```

Pruebas: `pip install pytest && pytest`.

## Plano

`data/geometria.json` se genera desde el DXF con `scripts/procesar_dxf.py` (acepta el formato de
[`docs/FORMATO_DXF.md`](docs/FORMATO_DXF.md) con polígonos cerrados, y también el plano actual hecho de líneas).
Si cambia el plano: `python scripts/procesar_dxf.py nuevo.dxf data/geometria.json` y reiniciar la base.

## Estructura

```
streamlit_app.py        la aplicación
obra/db.py              tablas (SQLite o PostgreSQL) y carga inicial de sitios/terrazas
obra/calculos.py        m³ retirados, prorrateo, programa vs. real, resumen diario
obra/importar.py        lectura y validación de archivos
obra/mapa.py            plano interactivo (Plotly)
scripts/                procesar DXF, generar ejemplos
data/                   geometría, DXF fuente, ejemplos
tests/                  pruebas (pytest)
```

## Proforma

El volumen adicional a botadero (actividad `adicional`) es volumen no considerado en la planificación inicial: se
muestra como **proforma** en el detalle de cada sitio y **no** entra al avance, al programa ni a las curvas.
