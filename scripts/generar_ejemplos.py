"""Genera archivos de ejemplo en data/ejemplos/ con el formato de cada carga.

    python scripts/generar_ejemplos.py            # solo escribe los CSV
    python scripts/generar_ejemplos.py --cargar   # además los carga en la base local (data/obra.db)

La carta Gantt de ejemplo sale de la fila "Excavación a máquina zonas de arcilla bajo radieres"
del Gantt Casas Loma La Cruz (2 sitios por semana). Desde el sitio 39 las semanas son extrapoladas.
"""
import random
import sys
from datetime import date, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DIR = RAIZ / 'data' / 'ejemplos'

# (semana, lunes, viernes) según el encabezado del Gantt; la semana 14 (fiestas patrias) no tiene trabajo
SEMANAS = [
    (8, '2026-08-03', '2026-08-07'), (9, '2026-08-10', '2026-08-14'), (10, '2026-08-17', '2026-08-21'),
    (11, '2026-08-24', '2026-08-28'), (12, '2026-08-31', '2026-09-04'), (13, '2026-09-07', '2026-09-11'),
    (15, '2026-09-21', '2026-09-25'), (16, '2026-09-28', '2026-10-02'), (17, '2026-10-05', '2026-10-09'),
    (18, '2026-10-12', '2026-10-16'), (19, '2026-10-19', '2026-10-23'), (20, '2026-10-26', '2026-10-30'),
    (21, '2026-11-02', '2026-11-06'), (22, '2026-11-09', '2026-11-13'), (23, '2026-11-16', '2026-11-20'),
    (24, '2026-11-23', '2026-11-27'), (25, '2026-11-30', '2026-12-04'), (26, '2026-12-07', '2026-12-11'),
    (27, '2026-12-14', '2026-12-18'),
    # extrapoladas (fuera del pantallazo)
    (28, '2026-12-21', '2026-12-24'), (29, '2026-12-28', '2026-12-31'), (30, '2027-01-04', '2027-01-08'),
    (31, '2027-01-11', '2027-01-15'), (32, '2027-01-18', '2027-01-22'),
]


def cl(d):
    return date.fromisoformat(d).strftime('%d/%m/%Y') if isinstance(d, str) else d.strftime('%d/%m/%Y')


def escribir(nombre, filas):
    DIR.mkdir(parents=True, exist_ok=True)
    (DIR / nombre).write_text('﻿' + '\r\n'.join(';'.join(map(str, f)) for f in filas) + '\r\n', encoding='utf-8')


def gantt():
    filas = [['sitio', 'inicio', 'termino', 'actividad', 'tarea']]
    for i, (sem, ini, fin) in enumerate(SEMANAS):
        for sitio in (2 * i + 1, 2 * i + 2):
            nota = ' (extrapolado)' if sem >= 28 else ''
            filas.append([sitio, cl(ini), cl(fin), '', f'Excavación a máquina zonas de arcilla bajo radieres, semana {sem}{nota}'])
    return filas


def volumenes(rnd):
    filas = [['sitio', 'actividad', 'volumen_proyectado_m3', 'estado']]
    for s in range(1, 49):
        filas.append([s, 'escarpe', rnd.randint(60, 110), ''])
        filas.append([s, 'corte', rnd.randint(200, 300), ''])
    return filas


def tickets(rnd, hoy):
    """Tickets de la máquina para los días hábiles desde el 03/08/2026 hasta hoy."""
    patentes = {'GXVL25': 22, 'DZGW60': 22, 'TRSL61': 25, 'DFLK77': 14, 'LZRJ70': 24, 'KHPT12': 20, 'BWRS48': 14}
    activos = {}
    for i, (_, ini, fin) in enumerate(SEMANAS):
        d = date.fromisoformat(ini)
        while d <= date.fromisoformat(fin):
            activos[d] = (2 * i + 1, 2 * i + 2)
            d += timedelta(days=1)
    filas = [['TICKET', 'FECHA', 'HORA', 'PATENTE', 'VOLUMEN_M3', 'SECTOR', 'TIPO', 'ESTADO']]
    ticket = 1
    d = date(2026, 8, 3)
    while d <= hoy:
        if d in activos:
            for k in range(rnd.randint(8, 14)):
                pat = rnd.choice(list(patentes))
                minuto = 8 * 60 + int(k * 540 / 14) + rnd.randint(0, 15)
                sitio = rnd.choice(activos[d])
                sector = '' if rnd.random() < 0.15 else sitio
                tipo = 'DESCARPE' if d.weekday() == 0 else 'CORTE'
                vol = f'{patentes[pat]:.1f}'.replace('.', ',')
                filas.append([ticket, cl(d), f'{minuto // 60:02d}:{minuto % 60:02d}', pat, vol, sector, tipo, 'VALIDO'])
                if rnd.random() < 0.02:  # anulación del mismo ticket unos minutos después
                    m2 = minuto + 2
                    filas.append([ticket, cl(d), f'{m2 // 60:02d}:{m2 % 60:02d}', pat, '-' + vol, sector, tipo, 'ANULACION'])
                ticket += 1
        d += timedelta(days=1)
    return filas


def main():
    sys.path.insert(0, str(RAIZ))
    from obra.calculos import hoy_chile
    rnd = random.Random(7)
    hoy = date.fromisoformat(hoy_chile())
    escribir('gantt_movimiento_tierra.csv', gantt())
    escribir('volumenes_proyectados.csv', volumenes(rnd))
    escribir('tickets_maquina.csv', tickets(rnd, hoy))
    escribir('entregas.csv', [['sitio', 'zona', 'estado', 'fecha_entrega'],
                              [1, 'acceso', 'entregado', '15/09/2026'], [1, 'living', 'entregado', '22/09/2026'],
                              [1, 'patio', 'en proceso', ''], [2, 'acceso', 'entregado', '22/09/2026'],
                              [2, 'living', 'en proceso', '']])
    escribir('ajustes.csv', [['sitio', 'actividad', 'fecha', 'volumen_m3', 'motivo'],
                             [3, 'corte', '25/09/2026', '-12,5', 'Topografía: menor volumen que lo contado en tickets']])
    print(f'Ejemplos escritos en {DIR}')
    if '--cargar' in sys.argv:
        from obra import db, importar
        motor = db.crear_motor()
        for tipo, archivo in [('volumenes', 'volumenes_proyectados.csv'), ('gantt', 'gantt_movimiento_tierra.csv'),
                              ('viajes', 'tickets_maquina.csv'), ('entregas', 'entregas.csv'), ('ajustes', 'ajustes.csv')]:
            rev = importar.revisar(motor, tipo, (DIR / archivo).read_bytes(), archivo)
            importar.aplicar(motor, tipo, rev, archivo)
            print(tipo, rev.resumen, f'{len(rev.errores)} errores' if rev.errores else '')


if __name__ == '__main__':
    main()
