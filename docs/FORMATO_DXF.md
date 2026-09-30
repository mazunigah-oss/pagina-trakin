# Especificación del DXF — Proyecto Lomas (control de movimiento de tierra)

Este documento define **cómo debe estar estructurado el archivo DXF** para que un
programa (o un asistente) pueda extraer automáticamente la geometría de la obra:
**48 sitios**, y dentro de cada sitio sus **3 terrazas** (Acceso, Living, Patio) →
**48 accesos + 48 living + 48 fondos de patio = 144 terrazas**.

## 1. Concepto general
- La obra son **48 sitios** (lotes/casas), numerados del 1 al 48.
- Cada sitio se subdivide en **3 terrazas**, con una convención espacial fija:
  - **Acceso**: la franja **colindante con la calle**.
  - **Living**: la franja **central** del sitio.
  - **Patio** (fondo de patio): la franja del **lado opuesto a la calle** (el fondo).
- Todo se dibuja en **planta** (vista superior), en un solo archivo `.dxf`.

## 2. Capas (layers) — esto es lo esencial
Cada tipo de elemento va en su propia capa. **Todos los elementos del mismo tipo
van juntos en UNA capa** (no una capa por casa).

| Capa            | Contenido                                   | Cantidad | Geometría                 |
|-----------------|---------------------------------------------|----------|---------------------------|
| `1` … `48`      | Contorno de cada sitio (uno por capa)       | 48 capas | 1 polígono cerrado c/u    |
| `Acceso`        | Todos los accesos                           | 48       | 48 polígonos cerrados     |
| `Living`        | Todos los living                            | 48       | 48 polígonos cerrados     |
| `Patio`         | Todos los fondos de patio                   | 48       | 48 polígonos cerrados     |
| `A-AREA-____-IDEN` | Rótulos de texto (`SITIO 1` … `SITIO 48`) | 48       | MTEXT, uno por sitio      |
| `Etapa1`        | Contorno/límite de la Etapa 1               | 1        | líneas/polilínea          |
| `Etapa2`        | Contorno/límite de la Etapa 2               | 1        | líneas/polilínea          |
| `Edificios`     | Huella de edificios (si aplica)             | —        | polígonos cerrados        |
| `Calles` / `Pasaje N` | Vialidad y pasajes (contexto, opcional) | —      | polígonos cerrados        |

> **Nota sobre el Patio:** puede entregarse dibujado (48 polígonos en la capa
> `Patio`) **o** omitirse y calcularse como el **resto** del sitio:
> `Patio = sitio − Acceso − Living`. Si se dibuja, debe cumplir las mismas reglas
> que Acceso y Living. Este documento asume que **sí se dibuja** (los 48).

## 3. Reglas obligatorias (para que la lectura sea automática)
1. **Todo polígono debe estar CERRADO** (polilínea cerrada; el último vértice
   coincide con el primero). Un contorno con una abertura no se detecta.
2. **Cada terraza debe quedar dentro del contorno de su sitio.** La asignación
   terraza → sitio se hace por *punto-en-polígono* (el centroide de la terraza
   cae dentro del polígono del sitio).
3. **Un tipo por capa:** todos los accesos en `Acceso`, todos los living en
   `Living`, todos los patios en `Patio`. No una capa por casa.
4. **Un rótulo `SITIO N` por sitio**, ubicado dentro del polígono del sitio.
   El texto debe decir exactamente `SITIO ` + número (ej. `SITIO 12`).
5. **Las 3 terrazas de un sitio deben cubrir el sitio sin traslape** entre ellas
   (Acceso + Living + Patio ≈ área del sitio).
6. Recomendado: usar `LINE`, `ARC`, `LWPOLYLINE` o `POLYLINE`. Evitar bloques
   (INSERT) para los contornos; si se usan, deben poder explotarse.

## 4. Tolerancia y unidades
- Unidades del dibujo: **milímetros** (el área se convierte a m² dividiendo por 1e6).
- El extractor **"pega" micro-aberturas menores a 10 cm** (snap de 100 mm) antes de
  cerrar los polígonos, por lo que gaps < 10 cm se toleran. Aun así, lo ideal es
  cerrar bien las polilíneas.
- Todo debe estar en el **mismo sistema de coordenadas** (mismo origen); no mezclar
  bloques desplazados ni copias en otras posiciones.

## 5. Qué se obtiene al leer el DXF (salida esperada)
- `terrenos_geom.json`: por cada sitio → `terreno_id` (SITIO N), `etapa`, `area_m2`,
  el anillo del polígono y su centroide.
- `terrazas_geom.json`: por cada terraza → `terreno_id`, `terraza`
  (Acceso/Living/Patio), el anillo del polígono, centroide y `area_m2`.
- Verificación de completitud esperada: **48 sitios, 48 Acceso, 48 Living,
  48 Patio**. Si falta alguno, casi siempre es un polígono **no cerrado** o una
  terraza dibujada **fuera** de su sitio.

## 6. Convención espacial (para ubicar bien cada terraza)
Dentro de cada sitio, mirando desde la calle hacia el fondo:
`Acceso` (junto a la calle) → `Living` (centro) → `Patio` (fondo, lado opuesto a la calle).

## 7. Checklist rápido antes de exportar
- [ ] 48 contornos de sitio, uno por capa `1`…`48`, todos cerrados.
- [ ] 48 polígonos cerrados en `Acceso`, dentro de su sitio.
- [ ] 48 polígonos cerrados en `Living`, dentro de su sitio.
- [ ] 48 polígonos cerrados en `Patio` (o dejarlo para calcular como resto).
- [ ] 48 rótulos `SITIO N` (texto exacto), uno dentro de cada sitio.
- [ ] Capas `Etapa1` y `Etapa2` presentes.
- [ ] Todo en las mismas coordenadas, sin bloques desplazados.
- [ ] Exportar como **DXF** (no DWG); versión R2013 o superior, ASCII.
