import importlib

import config
import database


def preparar_db_temporal(monkeypatch, tmp_path):
    ruta = tmp_path / "test_sistema_contable.db"
    monkeypatch.setattr(config, "DB_PATH", str(ruta), raising=False)
    monkeypatch.setattr(database, "DB_PATH", str(ruta), raising=False)
    database.init_db()

    from services import ejercicios_contables_service as ejercicios_svc
    from services import asientos_origen_service as asientos_svc
    from services import capital_social_service as capital_svc
    from services import tesoreria_service as tesoreria_svc

    importlib.reload(ejercicios_svc)
    importlib.reload(asientos_svc)
    importlib.reload(tesoreria_svc)
    importlib.reload(capital_svc)

    ejercicios_svc.migrar_ejercicios_contables()
    asientos_svc.migrar_asientos_origen()
    tesoreria_svc.inicializar_tesoreria()
    capital_svc.migrar_capital_social()

    creado = ejercicios_svc.crear_ejercicio_contable(
        empresa_id=1,
        fecha_inicio="2025-01-01",
        fecha_cierre="2025-12-31",
        nombre="Ejercicio 2025",
        usuario="tester",
    )
    assert creado["ok"] is True

    return ejercicios_svc, asientos_svc, tesoreria_svc, capital_svc, creado["ejercicio_id"]


def socios_sin_integracion():
    return [
        {
            "nombre": "Socio A",
            "cuit": "20-11111111-1",
            "porcentaje": 60,
            "importe_suscripto": 600000,
            "importe_integrado": 0,
            "medio_integracion": "NO_INTEGRADO",
        },
        {
            "nombre": "Socio B",
            "cuit": "20-22222222-2",
            "porcentaje": 40,
            "importe_suscripto": 400000,
            "importe_integrado": 0,
            "medio_integracion": "NO_INTEGRADO",
        },
    ]


def crear_capital_base(capital_svc, ejercicio_id):
    resultado = capital_svc.configurar_capital_social_inicial(
        empresa_id=1,
        ejercicio_id=ejercicio_id,
        fecha_instrumento="2025-01-05",
        capital_social_total=1000000,
        socios=socios_sin_integracion(),
        descripcion="Constitución inicial",
        referencia="Acta constitutiva",
        cuenta_socios_integracion_codigo="1.3.99",
        cuenta_socios_integracion_nombre="Socios / accionistas por integración",
        cuenta_capital_codigo="3.1.01",
        cuenta_capital_nombre="Capital social",
        usuario="tester",
    )
    assert resultado["ok"] is True
    return resultado


def obtener_suscripcion_por_nombre(capital_svc, capital_id, nombre):
    capital = capital_svc.obtener_capital_social(capital_id)
    for suscripcion in capital["suscripciones"]:
        if suscripcion["socio_nombre"] == nombre:
            return suscripcion
    raise AssertionError(f"No se encontró la suscripción de {nombre}")


def crear_cuenta_tesoreria_banco():
    conn = database.conectar()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO tesoreria_cuentas
            (empresa_id, tipo_cuenta, nombre, entidad, numero_cuenta, moneda,
             cuenta_contable_codigo, cuenta_contable_nombre, activo, observacion)
            VALUES (1, 'BANCO', 'Banco Nación', 'Banco Nación', '0001', 'ARS',
                    '1.1.02', 'Banco Nación cuenta corriente', 1, 'Cuenta test')
            """
        )
        cuenta_id = int(cur.lastrowid)
        conn.commit()
        return cuenta_id
    finally:
        conn.close()


def crear_operacion_tesoreria(cuenta_id, importe=250000, referencia="TRX-001"):
    conn = database.conectar()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO tesoreria_operaciones
            (empresa_id, tipo_operacion, subtipo, fecha_operacion, fecha_contable,
             cuenta_tesoreria_id, medio_pago_id, tercero_tipo, tercero_id, tercero_nombre,
             tercero_cuit, descripcion, referencia_externa, importe, moneda, estado,
             estado_conciliacion, importe_conciliado, importe_pendiente, origen_modulo)
            VALUES (1, 'INGRESO', 'INTEGRACION_CAPITAL', '2025-01-10', '2025-01-10',
                    ?, NULL, 'SOCIO', NULL, 'Socio A',
                    '20-11111111-1', 'Transferencia de integración de capital', ?,
                    ?, 'ARS', 'CONFIRMADA', 'PENDIENTE', 0, ?, 'TEST')
            """,
            (cuenta_id, referencia, float(importe), float(importe)),
        )
        operacion_id = int(cur.lastrowid)
        conn.commit()
        return operacion_id
    finally:
        conn.close()


def test_registra_integracion_real_desde_tesoreria_y_genera_propuesta(monkeypatch, tmp_path):
    ejercicios_svc, asientos_svc, tesoreria_svc, capital_svc, ejercicio_id = preparar_db_temporal(monkeypatch, tmp_path)
    capital_res = crear_capital_base(capital_svc, ejercicio_id)
    capital_id = capital_res["capital_id"]

    suscripcion = obtener_suscripcion_por_nombre(capital_svc, capital_id, "Socio A")
    cuenta_id = crear_cuenta_tesoreria_banco()
    operacion_id = crear_operacion_tesoreria(cuenta_id, importe=250000)

    resultado = capital_svc.registrar_integracion_capital_desde_tesoreria(
        empresa_id=1,
        capital_id=capital_id,
        socio_id=int(suscripcion["socio_id"]),
        tesoreria_operacion_id=operacion_id,
        importe=250000,
        usuario="tester",
    )

    assert resultado["ok"] is True
    assert resultado["integracion_id"] > 0
    assert resultado["asiento_propuesto_id"] > 0

    capital = capital_svc.obtener_capital_social(capital_id)
    assert capital["total_integrado"] == 250000
    assert capital["total_pendiente_integracion"] == 750000

    suscripcion_actual = obtener_suscripcion_por_nombre(capital_svc, capital_id, "Socio A")
    assert suscripcion_actual["importe_integrado"] == 250000
    assert suscripcion_actual["importe_pendiente"] == 350000

    integraciones = capital["integraciones"]
    assert len(integraciones) == 1
    integracion = integraciones[0]
    assert integracion["es_integracion_real"] == 1
    assert integracion["origen_modulo"] == "TESORERIA"
    assert integracion["origen_tabla"] == "tesoreria_operaciones"
    assert integracion["origen_id"] == operacion_id
    assert integracion["cuenta_destino_codigo"] == "1.1.02"

    propuestos = asientos_svc.listar_asientos_propuestos(empresa_id=1, estado="PROPUESTO")
    assert len(propuestos) == 2  # suscripción + integración real

    libro = database.ejecutar_query("SELECT * FROM libro_diario", fetch=True)
    assert libro.empty

    eventos = capital_svc.listar_eventos_capital(capital_id)
    assert "INTEGRACION_REAL_TESORERIA" in set(eventos["evento"])


def test_no_reutiliza_misma_operacion_tesoreria(monkeypatch, tmp_path):
    ejercicios_svc, asientos_svc, tesoreria_svc, capital_svc, ejercicio_id = preparar_db_temporal(monkeypatch, tmp_path)
    capital_res = crear_capital_base(capital_svc, ejercicio_id)
    capital_id = capital_res["capital_id"]

    suscripcion = obtener_suscripcion_por_nombre(capital_svc, capital_id, "Socio A")
    cuenta_id = crear_cuenta_tesoreria_banco()
    operacion_id = crear_operacion_tesoreria(cuenta_id, importe=250000)

    primero = capital_svc.registrar_integracion_capital_desde_tesoreria(
        empresa_id=1,
        capital_id=capital_id,
        socio_id=int(suscripcion["socio_id"]),
        tesoreria_operacion_id=operacion_id,
        importe=250000,
        usuario="tester",
    )
    assert primero["ok"] is True

    segundo = capital_svc.registrar_integracion_capital_desde_tesoreria(
        empresa_id=1,
        capital_id=capital_id,
        socio_id=int(suscripcion["socio_id"]),
        tesoreria_operacion_id=operacion_id,
        importe=100000,
        usuario="tester",
    )

    assert segundo["ok"] is False
    assert "ya fue aplicada" in segundo["mensaje"]


def test_no_permite_integrar_mas_que_pendiente(monkeypatch, tmp_path):
    ejercicios_svc, asientos_svc, tesoreria_svc, capital_svc, ejercicio_id = preparar_db_temporal(monkeypatch, tmp_path)
    capital_res = crear_capital_base(capital_svc, ejercicio_id)
    capital_id = capital_res["capital_id"]

    suscripcion = obtener_suscripcion_por_nombre(capital_svc, capital_id, "Socio B")
    cuenta_id = crear_cuenta_tesoreria_banco()
    operacion_id = crear_operacion_tesoreria(cuenta_id, importe=600000)

    resultado = capital_svc.registrar_integracion_capital_desde_tesoreria(
        empresa_id=1,
        capital_id=capital_id,
        socio_id=int(suscripcion["socio_id"]),
        tesoreria_operacion_id=operacion_id,
        importe=500000,
        usuario="tester",
    )

    assert resultado["ok"] is False
    assert "saldo pendiente" in resultado["mensaje"]


def test_lista_movimientos_disponibles_excluye_los_ya_aplicados(monkeypatch, tmp_path):
    ejercicios_svc, asientos_svc, tesoreria_svc, capital_svc, ejercicio_id = preparar_db_temporal(monkeypatch, tmp_path)
    capital_res = crear_capital_base(capital_svc, ejercicio_id)
    capital_id = capital_res["capital_id"]

    suscripcion = obtener_suscripcion_por_nombre(capital_svc, capital_id, "Socio A")
    cuenta_id = crear_cuenta_tesoreria_banco()
    op_1 = crear_operacion_tesoreria(cuenta_id, importe=250000, referencia="TRX-001")
    op_2 = crear_operacion_tesoreria(cuenta_id, importe=100000, referencia="TRX-002")

    disponibles_antes = capital_svc.listar_movimientos_tesoreria_disponibles_para_integracion(empresa_id=1)
    assert set(disponibles_antes["tesoreria_operacion_id"]) == {op_1, op_2}

    resultado = capital_svc.registrar_integracion_capital_desde_tesoreria(
        empresa_id=1,
        capital_id=capital_id,
        socio_id=int(suscripcion["socio_id"]),
        tesoreria_operacion_id=op_1,
        importe=250000,
        usuario="tester",
    )
    assert resultado["ok"] is True

    disponibles_despues = capital_svc.listar_movimientos_tesoreria_disponibles_para_integracion(empresa_id=1)
    assert set(disponibles_despues["tesoreria_operacion_id"]) == {op_2}


def test_anula_integracion_y_restaura_pendiente(monkeypatch, tmp_path):
    ejercicios_svc, asientos_svc, tesoreria_svc, capital_svc, ejercicio_id = preparar_db_temporal(monkeypatch, tmp_path)
    capital_res = crear_capital_base(capital_svc, ejercicio_id)
    capital_id = capital_res["capital_id"]

    suscripcion = obtener_suscripcion_por_nombre(capital_svc, capital_id, "Socio A")
    cuenta_id = crear_cuenta_tesoreria_banco()
    operacion_id = crear_operacion_tesoreria(cuenta_id, importe=250000)

    registrado = capital_svc.registrar_integracion_capital_desde_tesoreria(
        empresa_id=1,
        capital_id=capital_id,
        socio_id=int(suscripcion["socio_id"]),
        tesoreria_operacion_id=operacion_id,
        importe=250000,
        usuario="tester",
    )
    assert registrado["ok"] is True

    anulado = capital_svc.anular_integracion_capital(
        integracion_id=registrado["integracion_id"],
        motivo="Carga errónea de prueba",
        usuario="tester",
    )
    assert anulado["ok"] is True

    capital = capital_svc.obtener_capital_social(capital_id)
    assert capital["total_integrado"] == 0
    assert capital["total_pendiente_integracion"] == 1000000

    suscripcion_actual = obtener_suscripcion_por_nombre(capital_svc, capital_id, "Socio A")
    assert suscripcion_actual["importe_integrado"] == 0
    assert suscripcion_actual["importe_pendiente"] == 600000

    integracion = [i for i in capital["integraciones"] if i["id"] == registrado["integracion_id"]][0]
    assert integracion["estado"] == "ANULADO"

    movimientos_disponibles = capital_svc.listar_movimientos_tesoreria_disponibles_para_integracion(empresa_id=1)
    assert operacion_id in set(movimientos_disponibles["tesoreria_operacion_id"])