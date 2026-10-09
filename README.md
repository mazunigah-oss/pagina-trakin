# Avance movimiento de tierra — Loma La Cruz

Aplicación web (Streamlit) para seguir el movimiento de tierra y las entregas de terrazas de
48 sitios (Etapas 1 y 2), cada uno dividido en **acceso, living y fondo de patio**, más 2 edificios.

- **Visita**: acceso libre, solo lectura.
- **Administrador**: barra lateral → "Acceso administrador" (contraseña = secreto `ADMIN_PASSWORD`).

Requerimientos y decisiones: [`docs/01-analisis-requerimientos.md`](docs/01-analisis-requerimientos.md).

## Pestañas

| Pestaña | Contenido |
|---|---|
| Resumen | Avance %, m³ retirados vs. los que deberían ir según la Gantt (+/− m³), mapa de sitios listos / en trabajos y camiones de hoy comparados con ayer |
| Curva de avance | Curvas programada, real y proyectada al ritmo actual: fecha estimada de término, % que se alcanzaría a la fecha de término programada y ritmo necesario para terminar a tiempo |
| Entregas | Plano con las 144 terrazas + edificios según su estado (sin intervenir / en proceso / entregado) |
| Programa | Dos mapas: a la izquierda cómo vamos (rojo atrasado, verde según Gantt, azul adelantado) y a la derecha cómo deberíamos ir (verde listo, amarillo en trabajos), con la explicación de colores abajo |
| Movimiento de tierra | % de avance (m³ retirados / proyectados) por sitio, con el detalle del cálculo |
| Tickets | Tickets de la máquina filtrables por fecha |
| Cargar datos *(admin)* | Subida de archivos con revisión previa, historial y deshacer |
| Editar estados *(admin)* | Tabla editable de estados de terrazas, escarpe/corte y volúmenes proyectados |

El selector **Ver al día** muestra la obra en cualquier fecha.

## Carga inicial Loma La Cruz Norte (datos al 04/10/2026)

En [`data/carga_inicial/`](data/carga_inicial) están los datos de obra listos para subir en **Cargar datos**, en este orden:

| # | Archivo | Tipo de carga |
|---|---|---|
| 1 | `1_sitios_volumen_avance_programa.csv` | Avance acumulado por sitio |
| 2 | `5_programa_gantt.csv` (carta Gantt nueva, 47 sitios) | Programa (carta Gantt) |
| 3 | `2_adicional_botadero.csv` | Avance acumulado por sitio |
| 4 | `3_rellenos_densidades.csv` | Rellenos compactados y densidades |
| 5 | `4_hitos.csv` | Hitos de la obra |

Volumen proyectado = esponjado (excavación × 1,43), que es lo que trasladan los camiones.

La carta Gantt en Excel (semanas en columnas, celdas como `6-5` = sitios 6 y 5) se convierte con
`python scripts/gantt_excel_a_csv.py Gantt.xlsx data/carga_inicial/5_programa_gantt.csv`. Cada sitio va del lunes
de su primera tarea ("Entrega de plataformas") al viernes de la última ("Relleno compactado").
`5_programa_gantt_detalle.csv` tiene cada tarea por semana, solo como respaldo (no se sube).

## Archivos que se cargan

Plantillas en la pestaña "Cargar datos" y ejemplos en [`data/ejemplos/`](data/ejemplos). CSV (`;` o `,`) o Excel.

| Archivo | Modo | Columnas |
|---|---|---|
| Tickets de la máquina | **SUMA** | `TICKET;FECHA;HORA;PATENTE;VOLUMEN_M3;SECTOR;TIPO;ESTADO` — tal como sale de la máquina |
| Avance acumulado por sitio | **ACTUALIZA** | `sitio;fecha;avance_pct` (o `m3_acumulados`; opcional `volumen_proyectado_m3`, `actividad`) — para cuando no hay tickets: deja el sitio en ese avance a esa fecha |
| Programa (Gantt) | **REEMPLAZA** | `sitio;inicio;termino` (+ opcional `actividad`, `zona`, `tarea`) |
| Volúmenes proyectados | **ACTUALIZA** | `sitio;actividad;volumen_proyectado_m3;estado` |
| Entregas de terrazas | **ACTUALIZA** | `sitio;zona;estado;fecha_entrega` |
| Rellenos y densidades | **REEMPLAZA** | `sitio;corte_m3;relleno_m3;capas_acceso;capas_living;capas_calicata;entrega` (`P` = pendiente) |
| Hitos | **REEMPLAZA** | `hito;fecha` |
| Ajustes (topografía) | **SUMA** | `sitio;actividad;fecha;volumen_m3;motivo` |

Tickets:
- Cada ticket se guarda una sola vez (clave = TICKET + ESTADO): se puede subir el CSV del día, uno acumulado o el
  mismo dos veces sin duplicar.
- `ANULACION` resta su volumen (y descuenta el viaje).
- `SECTOR` = número de sitio. Vacío u otro valor → "General", que se reparte entre las actividades en proceso según su
  volumen proyectado.
- `TIPO`: `CORTE` o `DESCARPE` (escarpe).

Un sitio se considera **terminado** si el administrador marca escarpe y corte como terminados, o si ya se retiró todo su
volumen proyectado.

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
