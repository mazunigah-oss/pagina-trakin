# Avance movimiento de tierra — Loma La Cruz

Aplicación web (Streamlit) para seguir el movimiento de tierra y las entregas de terrazas de
48 sitios (Etapas 1 y 2), cada uno dividido en **acceso, living y fondo de patio**, más 2 edificios.

- **Visita**: acceso libre, solo lectura.
- **Administrador**: barra lateral → "Acceso administrador" (contraseña = secreto `ADMIN_PASSWORD`).

Requerimientos y decisiones: [`docs/01-analisis-requerimientos.md`](docs/01-analisis-requerimientos.md).

## Pestañas

| Pestaña | Contenido |
|---|---|
| Resumen | Camiones, viajes y m³ del día; origen de la tierra por sitio; m³ de los últimos 30 días; entregas y sitios atrasados |
| Curva de avance | Curvas programada, real y proyectada al ritmo actual: fecha estimada de término, % que se alcanzaría a la fecha de término programada y ritmo necesario para terminar a tiempo |
| Entregas | Plano con las 144 terrazas + edificios según su estado (sin intervenir / en proceso / entregado) |
| Programa | Cómo deberíamos ir a la fecha según la carta Gantt, real vs. programado y la carta Gantt |
| Movimiento de tierra | % de avance (m³ retirados / proyectados) por sitio, con el detalle del cálculo |
| Tickets | Tickets de la máquina filtrables por fecha |
| Cargar datos *(admin)* | Subida de archivos con revisión previa, historial y deshacer |
| Editar estados *(admin)* | Tabla editable de estados de terrazas, escarpe/corte y volúmenes proyectados |

El selector **Ver al día** muestra la obra en cualquier fecha.

## Archivos que se cargan

Plantillas en la pestaña "Cargar datos" y ejemplos en [`data/ejemplos/`](data/ejemplos). CSV (`;` o `,`) o Excel.

| Archivo | Modo | Columnas |
|---|---|---|
| Tickets de la máquina | **SUMA** | `TICKET;FECHA;HORA;PATENTE;VOLUMEN_M3;SECTOR;TIPO;ESTADO` — tal como sale de la máquina |
| Avance acumulado por sitio | **ACTUALIZA** | `sitio;fecha;avance_pct` (o `m3_acumulados`; opcional `volumen_proyectado_m3`, `actividad`) — para cuando no hay tickets: deja el sitio en ese avance a esa fecha |
| Programa (Gantt) | **REEMPLAZA** | `sitio;inicio;termino` (+ opcional `actividad`, `zona`, `tarea`) |
| Volúmenes proyectados | **ACTUALIZA** | `sitio;actividad;volumen_proyectado_m3;estado` |
| Entregas de terrazas | **ACTUALIZA** | `sitio;zona;estado;fecha_entrega` |
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
