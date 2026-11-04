# Prompt para reparar el Excel de seguimiento (Loma La Cruz)

> **Historial.** 03/11/2026: la causa del aviso era que las 5 tablas se escribían con columnas `Column1`,
> `Column2`… (openpyxl `_initialise_columns()`), distintas de los encabezados. Corregido en `construir.py`
> (`TableColumn` con el nombre del encabezado) y comprobado en Excel para Mac: abre sin aviso, con macros.

Copiar desde aquí:

---

Tengo un archivo Excel con macros, `data/excel/Seguimiento_Loma_La_Cruz.xlsm`, generado **sin Excel** por un script
Python del repositorio `mazunigah-oss/pagina-trakin` (rama `claude/earth-movement-web-app-buwlpk`). Al abrirlo,
Excel dice que encontró un problema y que **eliminó o reparó partes** del archivo. Necesito que lo dejes abriendo
sin errores, sin perder funciones.

**Qué es el archivo.** Un panel de seguimiento de movimiento de tierra y entregas de terrazas de 48 sitios
(+2 edificios). Se genera con `python scripts/excel/construir.py`. No se edita el `.xlsm` a mano, sino el generador:
- `scripts/excel/construir.py`: crea el libro con openpyxl. Contiene:
  - hojas de datos como **tablas de Excel** (`tblMovimiento`, `tblCamiones`, `tblEntregas`, `tblGantt`,
    `tblNotas`) con columnas calculadas (`[#This Row]`);
  - la hoja `Sitios` con fórmulas (`_xlfn.AGGREGATE`, `SUMIFS` sobre las tablas);
  - el Panel con indicadores, 4 gráficos y botones (celdas con vínculo a sí mismas);
  - nombres definidos (`FechaPanel`, `Vista`, `CajaMapa1/2`, `Btn*`).
- `scripts/excel/dibujo.py`: agrega al dibujo del Panel ~196 **figuras DrawingML** (`xdr:twoCellAnchor` +
  `xdr:sp` con `a:custGeom`, nombre `I_<sitio>` o `E_<sitio>_<acceso|living|fondo|unica>`, atributo
  `macro="[0]!ClicMapa"`). Son los dos mapas.
- `scripts/excel/vba_proyecto.py`: escribe `xl/vbaProject.bin` según MS-OVBA (solo código fuente, `_VBA_PROJECT`
  versión 0xFFFF para que Excel compile al abrir). Los módulos están en `scripts/excel/vba/`: `Botones.bas`,
  `Panel.cls`, `Ficha.cls`, `Geometria.cls` y `ThisWorkbook.cls`. Los nombres internos de las hojas (`codeName`)
  coinciden con los módulos.
- `scripts/excel/xlsm.py`: convierte el .xlsx en .xlsm (tipo de contenido macroEnabled y relación vbaProject).
- Las **tablas dinámicas** ya no se escriben en el XML: la macro `CrearTablasDinamicas` (en `Botones.bas`) las crea
  con `PivotCaches.Create` al abrir (`Workbook_Open`) si no existen.

**Cómo diagnosticar.**
1. Pedir al usuario el texto exacto del aviso de reparación de Excel. Excel lista las partes: *"Registros
   quitados: …"* o *"Elemento quitado: /xl/…"*. Ahí está la parte culpable: dibujo, tabla, formato condicional,
   validación de datos, nombres, vbaProject, etc.
2. Generar variantes para aislar el problema y pedir al usuario que las abra en Excel:
   - (a) sin las figuras (no llamar a `dibujo.agregar`);
   - (b) sin el proyecto VBA (guardar como .xlsx);
   - (c) sin las columnas calculadas (`calculatedColumnFormula`);
   - (d) sin los formatos condicionales del Panel y de Programa.
   La primera variante que abra sin aviso indica la parte culpable.
3. Revisar con criterios de Excel las partes sospechosas:
   - en las figuras: orden de los elementos del esquema, `id` únicos en `cNvPr`, que `xdr:to` quede después de
     `xdr:from`, `textlink`, nombres con espacios o caracteres especiales, `a:path` con `w` y `h` mayores que 0;
   - en las tablas: nombres de columna únicos, sin saltos de línea, que el `ref` de la tabla coincida con los
     encabezados escritos y que **cada `tableColumn name` sea idéntico a su celda de encabezado** (si no, Excel
     repara la tabla y borra todas las fórmulas `tblX[Columna]`; `tests/test_excel.py` lo revisa);
   - en las validaciones: `formula1` de lista sin `=`.
   LibreOffice (`soffice`) abre todo sin quejarse, así que **no sirve para validar el esquema estricto de Excel**:
   hay que validar contra el esquema OOXML o con el aviso real de Excel.

**Reglas que no se pueden romper.**
- Avance = m³ retirados / m³ proyectados (esponjados).
- El extra (proforma) no entra al avance.
- Un sitio cumple la carta Gantt cuando su acceso y su living están entregados.
- Una planilla nueva reemplaza a la anterior: se usa la fecha más reciente por sitio.
- Datos al 30/10/2026: 36.196 de 45.250 m³ (80,0 %) y 4.568 m³ extra.

Al terminar, regenerar con `python scripts/excel/construir.py`, confirmar que `pytest` sigue pasando, hacer commit
y push a la misma rama, y entregar el archivo.

---
