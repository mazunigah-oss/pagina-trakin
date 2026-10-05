import io
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import func, select

from obra import calculos as C
from obra import db as T
from obra import importar as I

RAIZ = Path(__file__).resolve().parent.parent

CSV_MAQUINA = """TICKET;FECHA;HORA;PATENTE;VOLUMEN_M3;SECTOR;TIPO;ESTADO
1329;30/09/2026;08:42;GXVL25;22,0;12;CORTE;VALIDO
1330;30/09/2026;08:51;DZGW60;22,0;12;CORTE;VALIDO
1331;30/09/2026;09:03;TRSL61;25,0;12;CORTE;VALIDO
1332;30/09/2026;09:14;DFLK77;14,0;7;DESCARPE;VALIDO
1332;30/09/2026;09:16;DFLK77;-14,0;7;DESCARPE;ANULACION
1333;30/09/2026;09:28;LZRJ70;24,0;7;DESCARPE;VALIDO
""".encode()


@pytest.fixture
def motor(tmp_path):
    return T.crear_motor(f'sqlite:///{tmp_path / "t.db"}')


def cargar(motor, tipo, contenido, nombre='x.csv'):
    rev = I.revisar(motor, tipo, contenido, nombre)
    I.aplicar(motor, tipo, rev, nombre)
    return rev


def tablas(motor):
    return {n: C.leer(motor, n) for n in ('terreno', 'zona', 'actividad', 'viaje', 'ajuste', 'gantt')}


def test_siembra_48_sitios_144_terrazas_y_etapas(motor):
    d = tablas(motor)
    sitios = d['terreno'][d['terreno']['tipo'] == 'sitio']
    assert len(sitios) == 48
    assert sorted(sitios['etapa'].value_counts().to_dict().items()) == [(1, 26), (2, 22)]
    z = d['zona'].merge(sitios[['id']], left_on='terreno_id', right_on='id')
    assert z['zona'].value_counts().to_dict() == {'acceso': 48, 'living': 48, 'fondo_patio': 48}
    assert len(d['actividad']) == 2 * len(d['terreno'])


def test_csv_de_la_maquina(motor):
    rev = I.revisar(motor, 'viajes', CSV_MAQUINA, 'maquina.csv')
    assert rev.ok and not rev.errores and not rev.avisos
    assert rev.resumen == dict(tickets_nuevos=6, validos=5, anulaciones=1, repetidos_omitidos=0, m3_netos=93.0)
    I.aplicar(motor, 'viajes', rev, 'maquina.csv')
    d = tablas(motor)
    r = C.resumen_dia(d['viaje'], d['terreno'], '2026-09-30')
    assert (r['viajes'], r['camiones'], r['m3'], r['anulaciones']) == (4, 4, 93.0, 1)
    origen = r['por_origen'].set_index('origen')
    assert origen.loc['Sitio 12', 'm3'] == 69 and origen.loc['Sitio 12', 'viajes'] == 3
    assert origen.loc['Sitio 7', 'm3'] == 24 and origen.loc['Sitio 7', 'viajes'] == 1
    acts = C.volumenes(d['actividad'], d['viaje'], d['ajuste'])
    s7 = acts[(acts['terreno_id'] == 7) & (acts['tipo'] == 'escarpe')].iloc[0]
    assert s7['retirado_m3'] == 24


def test_volver_a_subir_no_duplica_y_se_puede_deshacer(motor):
    cargar(motor, 'viajes', CSV_MAQUINA)
    acumulado = CSV_MAQUINA + b'1334;30/09/2026;10:02;GXVL25;22,0;;CORTE;VALIDO\n'
    rev = I.revisar(motor, 'viajes', acumulado, 'dia_completo.csv')
    assert rev.resumen['tickets_nuevos'] == 1 and rev.resumen['repetidos_omitidos'] == 6
    carga = I.aplicar(motor, 'viajes', rev, 'dia_completo.csv')
    with motor.connect() as con:
        assert con.execute(select(func.count()).select_from(T.viaje)).scalar() == 7
    assert I.deshacer(motor, carga)
    with motor.connect() as con:
        assert con.execute(select(func.count()).select_from(T.viaje)).scalar() == 6


def test_errores_por_fila_y_sector_desconocido(motor):
    csv = ('TICKET;FECHA;HORA;PATENTE;VOLUMEN_M3;SECTOR;TIPO;ESTADO\n'
           '1;31/02/2026;08:00;AAAA11;10;1;CORTE;VALIDO\n'
           '2;01/10/2026;8:00;AAAA11;diez;1;CORTE;VALIDO\n'
           '3;01/10/2026;08:10;AAAA11;10;PASAJE 2;CORTE;VALIDO\n'
           '4;01/10/2026;08:20;AAAA11;10;1;RELLENO;VALIDO\n').encode()
    rev = I.revisar(motor, 'viajes', csv)
    assert [f for f, _ in rev.errores] == [2, 3, 5]
    assert rev.resumen['tickets_nuevos'] == 1
    assert any('PASAJE 2' in m for _, m in rev.avisos)


def test_faltan_columnas(motor):
    rev = I.revisar(motor, 'viajes', b'FECHA;PATENTE\n01/10/2026;AB1234\n')
    assert not rev.ok and 'ticket' in rev.faltan_columnas


def test_prorrateo_de_tickets_sin_sector(motor):
    cargar(motor, 'volumenes', b'sitio;actividad;volumen_proyectado_m3;estado\n1;corte;100;en proceso\n2;corte;300;en proceso\n')
    cargar(motor, 'viajes', b'TICKET;FECHA;HORA;PATENTE;VOLUMEN_M3;SECTOR;TIPO;ESTADO\n9;01/10/2026;10:00;AB1234;40;;CORTE;VALIDO\n')
    cargar(motor, 'ajustes', b'sitio;actividad;fecha;volumen_m3\n1;corte;01/10/2026;5\n')
    d = tablas(motor)
    acts = C.volumenes(d['actividad'], d['viaje'], d['ajuste']).set_index(['terreno_id', 'tipo'])
    assert acts.loc[(1, 'corte'), 'prorrateo_m3'] == pytest.approx(10)
    assert acts.loc[(1, 'corte'), 'retirado_m3'] == pytest.approx(15)
    assert acts.loc[(2, 'corte'), 'retirado_m3'] == pytest.approx(30)
    assert acts.loc[(1, 'corte'), 'avance'] == pytest.approx(0.15)


def test_gantt_programado_vs_real(motor):
    rev = cargar(motor, 'gantt', b'sitio;inicio;termino\n15;28/09/2026;02/10/2026\n16;28/09/2026;02/10/2026\n'
                                 b'1;03/08/2026;07/08/2026\n40;04/01/2027;08/01/2027\n99;01/10/2026;02/10/2026\n')
    assert rev.resumen['tareas_nuevas'] == 4 and len(rev.errores) == 1
    cargar(motor, 'viajes', b'TICKET;FECHA;HORA;PATENTE;VOLUMEN_M3;SECTOR;TIPO;ESTADO\n1;29/09/2026;09:00;AB1234;20;15;CORTE;VALIDO\n')
    d = tablas(motor)
    acts = C.volumenes(d['actividad'], d['viaje'], d['ajuste'], hasta='2026-09-30')
    p = C.programa_terrenos(d['terreno'], acts, d['gantt'], '2026-09-30').set_index('codigo')
    assert p.loc['S-15', 'programado'] == 'en_proceso' and p.loc['S-15', 'avance_programado'] == pytest.approx(3 / 5)
    assert p.loc['S-15', 'comparacion'] == 'al_dia'
    assert p.loc['S-16', 'comparacion'] == 'atrasado'  # debía estar en proceso y no tiene tickets
    assert p.loc['S-01', 'programado'] == 'terminado' and p.loc['S-01', 'comparacion'] == 'atrasado'
    assert p.loc['S-40', 'programado'] == 'sin_intervenir'
    assert p.loc['S-02', 'programado'] is None
    # retirar todo lo proyectado cuenta como terminado aunque no se haya marcado
    cargar(motor, 'volumenes', b'sitio;actividad;volumen_proyectado_m3\n1;escarpe;10\n1;corte;10\n')
    cargar(motor, 'viajes', b'TICKET;FECHA;HORA;PATENTE;VOLUMEN_M3;SECTOR;TIPO;ESTADO\n2;05/08/2026;09:00;AB1234;20;1;;VALIDO\n')
    d = tablas(motor)
    acts = C.volumenes(d['actividad'], d['viaje'], d['ajuste'], hasta='2026-09-30')
    p = C.programa_terrenos(d['terreno'], acts, d['gantt'], '2026-09-30').set_index('codigo')
    assert p.loc['S-01', 'real'] == 'terminado' and p.loc['S-01', 'comparacion'] == 'al_dia'
    # Reemplaza el programa anterior
    cargar(motor, 'gantt', b'sitio;inicio;termino\n3;10/08/2026;14/08/2026\n')
    assert len(C.leer(motor, 'gantt')) == 1


def test_entregas_y_excel(motor, tmp_path):
    df = pd.DataFrame({'Sitio': [15, 15, 'ED-1'], 'Zona': ['Acceso', 'Fondo de patio', ''],
                       'Estado': ['Entregado', 'En proceso', 'entregado'],
                       'Fecha entrega': [pd.Timestamp('2026-09-20'), None, None]})
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    rev = cargar(motor, 'entregas', buf.getvalue(), 'entregas.xlsx')
    assert rev.resumen['terrazas_actualizadas'] == 3 and not rev.errores
    z = tablas(motor)['zona'].set_index(['terreno_id', 'zona'])
    assert z.loc[(15, 'acceso'), 'estado'] == 'entregado' and z.loc[(15, 'acceso'), 'fecha_entrega'] == '2026-09-20'
    assert z.loc[(15, 'fondo_patio'), 'estado'] == 'en_proceso'


def test_ejemplos_se_cargan_sin_errores(motor):
    ej = RAIZ / 'data' / 'ejemplos'
    for tipo, archivo in [('volumenes', 'volumenes_proyectados.csv'), ('gantt', 'gantt_movimiento_tierra.csv'),
                          ('viajes', 'tickets_maquina.csv'), ('entregas', 'entregas.csv'), ('ajustes', 'ajustes.csv')]:
        rev = I.revisar(motor, tipo, (ej / archivo).read_bytes(), archivo)
        assert rev.ok and not rev.errores, (archivo, rev.errores[:3])


def test_plantillas_se_pueden_releer(motor):
    for tipo in I.TIPOS:
        rev = I.revisar(motor, tipo, I.plantilla(tipo), 'plantilla.csv')
        assert rev.ok, (tipo, rev.faltan_columnas)


def test_app_streamlit_arranca(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{tmp_path / "app.db"}')
    monkeypatch.setenv('ADMIN_PASSWORD', 'clave')
    at = AppTest.from_file(str(RAIZ / 'streamlit_app.py'), default_timeout=60).run()
    assert not at.exception
    assert [t.label for t in at.tabs][:6] == ['Resumen', 'Curva de avance', 'Entregas', 'Programa',
                                              'Movimiento de tierra', 'Tickets']
    at.sidebar.text_input[0].input('mala')
    at.sidebar.button[0].click().run()
    assert 'Cargar datos' not in [t.label for t in at.tabs]
    at.sidebar.text_input[0].input('clave')
    at.sidebar.button[0].click().run()
    assert not at.exception
    assert 'Cargar datos' in [t.label for t in at.tabs]


def test_curva_de_avance_y_proyeccion(motor):
    cargar(motor, 'volumenes', b'sitio;actividad;volumen_proyectado_m3\n1;corte;100\n2;corte;100\n')
    cargar(motor, 'gantt', b'sitio;inicio;termino\n1;01/10/2026;10/10/2026\n2;11/10/2026;20/10/2026\n')
    filas = ['TICKET;FECHA;HORA;PATENTE;VOLUMEN_M3;SECTOR;TIPO;ESTADO']
    filas += [f'{d};{d:02d}/10/2026;09:00;AB1234;10;1;CORTE;VALIDO' for d in range(1, 11)]
    cargar(motor, 'viajes', '\n'.join(filas).encode())
    d = tablas(motor)
    prog = C.curva_programada(d['gantt'], d['actividad']).set_index('fecha')['pct']
    assert prog[pd.Timestamp('2026-10-10')] == pytest.approx(50)
    assert prog[pd.Timestamp('2026-10-20')] == pytest.approx(100)
    real = C.curva_real(d['viaje'], d['ajuste'], 200, '2026-10-10')
    assert real['pct'].iloc[-1] == pytest.approx(50)

    p = C.proyeccion(real, C.curva_programada(d['gantt'], d['actividad']), '2026-10-10', ventana_dias=7)
    assert p['avance_real'] == pytest.approx(50) and p['avance_programado'] == pytest.approx(50)
    assert p['ritmo'] == pytest.approx(5)          # (50 % - 15 %) / 7 días
    assert p['ritmo_necesario'] == pytest.approx(5)
    assert p['fecha_termino_estimada'] == pd.Timestamp('2026-10-20')
    assert p['dias_desfase'] == 0 and p['pct_a_termino_programado'] == pytest.approx(100)

    # Si el ritmo baja a la mitad: termina 10 días tarde y al término programado llega a 75 %
    real_lento = real.assign(pct=real['pct'] / 2)
    p = C.proyeccion(real_lento, C.curva_programada(d['gantt'], d['actividad']), '2026-10-10', ventana_dias=7)
    assert p['pct_a_termino_programado'] == pytest.approx(25 + 2.5 * 10)
    assert p['fecha_termino_estimada'] == pd.Timestamp('2026-10-10') + pd.Timedelta(days=30)
    assert p['dias_desfase'] == 20


def test_proyeccion_sin_avance_no_inventa_fecha():
    real = pd.DataFrame({'fecha': pd.date_range('2026-10-01', '2026-10-20'), 'pct': [10.0] * 20, 'm3': [10.0] * 20})
    p = C.proyeccion(real, pd.DataFrame(columns=['fecha', 'pct']), '2026-10-20', 14)
    assert p['ritmo'] == 0 and p['fecha_termino_estimada'] is None and p['serie'].empty


def test_volumen_total_por_sitio_sin_actividad(motor):
    rev = cargar(motor, 'volumenes', 'N° Sitio;VOLUMEN_M3\n1;1.250\n2;980,5\nSitio 3;300\n'.encode())
    assert not rev.errores and rev.resumen['sitios'] == 3
    a = tablas(motor)['actividad'].set_index(['terreno_id', 'tipo'])['volumen_proyectado_m3']
    assert a[(1, 'corte')] == 1250 and a[(1, 'escarpe')] == 0
    assert a[(2, 'corte')] == 980.5 and a[(3, 'corte')] == 300


def test_excel_con_titulo_sobre_los_encabezados(motor):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf) as w:
        pd.DataFrame([['CUBICACIÓN LOMA LA CRUZ', None], [None, None], ['Sitio', 'Cubicación'], [15, 210.5], [16, 199]]
                     ).to_excel(w, index=False, header=False)
    rev = cargar(motor, 'volumenes', buf.getvalue(), 'cubicacion.xlsx')
    assert rev.ok and not rev.errores, rev.errores
    a = tablas(motor)['actividad'].set_index(['terreno_id', 'tipo'])['volumen_proyectado_m3']
    assert a[(15, 'corte')] == 210.5 and a[(16, 'corte')] == 199


def test_volumen_por_actividad_sigue_funcionando(motor):
    rev = cargar(motor, 'volumenes', b'sitio;actividad;volumen_proyectado_m3\n1;escarpe;80\n1;corte;200\n1;relleno;5\n')
    assert [f for f, _ in rev.errores] == [4]
    a = tablas(motor)['actividad'].set_index(['terreno_id', 'tipo'])['volumen_proyectado_m3']
    assert a[(1, 'escarpe')] == 80 and a[(1, 'corte')] == 200
