import config
import database


def preparar_db_temporal(monkeypatch, tmp_path):
    ruta = tmp_path / "test_sistema_contable.db"
    monkeypatch.setattr(config, "DB_PATH", str(ruta), raising=False)
    monkeypatch.setattr(database, "DB_PATH", str(ruta), raising=False)
    database.init_db()

    from services import ejercicios_contables_service as ejercicios_svc
    from services import asientos_origen_service as asientos_svc

    ejercicios_svc.migrar_ejercicios_contables()
    asientos_svc.migrar_asientos_origen()

    creado = ejercicios_svc.crear_ejercicio_contable(
        empresa_id=1,
        fecha_inicio="2025-01-01",
        fecha_cierre="2025-12-31",
        nombre="Ejercicio 2025",
        usuario="tester",
    )
    assert creado["ok"] is True
    return ejercicios_svc, asientos_svc, creado["ejercicio_id"]


def lineas_apertura():
    return [
        {"cuenta_codigo": "11101", "cuenta_nombre": "Caja", "debe": 100000, "haber": 0, "glosa": "Saldo inicial de caja"},
        {"cuenta_codigo": "31101", "cuenta_nombre": "Capital social", "debe": 0, "haber": 100000, "glosa": "Capital inicial"},
    ]


def test_crear_asiento_apertura_genera_propuesta_sin_libro_diario(monkeypatch, tmp_path):
    ejercicios_svc, asientos_svc, ejercicio_id = preparar_db_temporal(monkeypatch, tmp_path)
    resultado = asientos_svc.crear_asiento_apertura(
        empresa_id=1,
        ejercicio_id=ejercicio_id,
        fecha="2025-01-01",
        descripcion="Asiento de apertura",
        lineas=lineas_apertura(),
        usuario="tester",
    )
    assert resultado["ok"] is True
    assert resultado["asiento_origen_id"] > 0
    assert resultado["asiento_propuesto_id"] > 0

    asiento = asientos_svc.obtener_asiento_origen(resultado["asiento_origen_id"])
    assert asiento["tipo_origen"] == "APERTURA"
    assert asiento["estado"] == "PROPUESTO"
    assert round(asiento["total_debe"], 2) == 100000
    assert round(asiento["total_haber"], 2) == 100000
    assert len(asiento["detalle"]) == 2

    propuesta = asientos_svc.obtener_asiento_propuesto(resultado["asiento_propuesto_id"])
    assert propuesta["estado"] == "PROPUESTO"
    assert propuesta["origen"] == "APERTURA"
    assert propuesta["origen_tabla"] == "asientos_origen"
    assert propuesta["origen_id"] == resultado["asiento_origen_id"]
    assert len(propuesta["detalle"]) == 2

    libro = database.ejecutar_query("SELECT * FROM libro_diario", fetch=True)
    assert libro.empty


def test_no_permite_asiento_descuadrado(monkeypatch, tmp_path):
    ejercicios_svc, asientos_svc, ejercicio_id = preparar_db_temporal(monkeypatch, tmp_path)
    resultado = asientos_svc.crear_asiento_apertura(
        empresa_id=1,
        ejercicio_id=ejercicio_id,
        fecha="2025-01-01",
        descripcion="Asiento descuadrado",
        lineas=[
            {"cuenta_codigo": "11101", "cuenta_nombre": "Caja", "debe": 100000, "haber": 0},
            {"cuenta_codigo": "31101", "cuenta_nombre": "Capital social", "debe": 0, "haber": 90000},
        ],
        usuario="tester",
    )
    assert resultado["ok"] is False
    assert "cuadrado" in resultado["mensaje"]
    assert asientos_svc.listar_asientos_origen(empresa_id=1).empty


def test_crear_capital_social_manual_sigue_disponible(monkeypatch, tmp_path):
    ejercicios_svc, asientos_svc, ejercicio_id = preparar_db_temporal(monkeypatch, tmp_path)
    resultado = asientos_svc.crear_asiento_capital_social(
        empresa_id=1,
        ejercicio_id=ejercicio_id,
        fecha="2025-01-10",
        descripcion="Integración de capital social",
        referencia="Acta constitutiva",
        lineas=[
            {"cuenta_codigo": "11102", "cuenta_nombre": "Banco", "debe": 500000, "haber": 0},
            {"cuenta_codigo": "31101", "cuenta_nombre": "Capital social", "debe": 0, "haber": 500000},
        ],
        usuario="tester",
    )
    assert resultado["ok"] is True
    asiento = asientos_svc.obtener_asiento_origen(resultado["asiento_origen_id"])
    assert asiento["tipo_origen"] == "CAPITAL_SOCIAL"
    assert asiento["referencia"] == "Acta constitutiva"


def test_crear_aporte_socio(monkeypatch, tmp_path):
    ejercicios_svc, asientos_svc, ejercicio_id = preparar_db_temporal(monkeypatch, tmp_path)
    resultado = asientos_svc.crear_aporte_socio(
        empresa_id=1,
        ejercicio_id=ejercicio_id,
        fecha="2025-02-15",
        descripcion="Aporte de socio para financiar operatoria",
        lineas=[
            {"cuenta_codigo": "11101", "cuenta_nombre": "Caja", "debe": 250000, "haber": 0},
            {"cuenta_codigo": "32101", "cuenta_nombre": "Aportes de socios", "debe": 0, "haber": 250000},
        ],
        usuario="tester",
    )
    assert resultado["ok"] is True
    asiento = asientos_svc.obtener_asiento_origen(resultado["asiento_origen_id"])
    assert asiento["tipo_origen"] == "APORTE_SOCIO"


def test_no_permite_asiento_en_ejercicio_cerrado(monkeypatch, tmp_path):
    ejercicios_svc, asientos_svc, ejercicio_id = preparar_db_temporal(monkeypatch, tmp_path)
    cierre = ejercicios_svc.cerrar_ejercicio_contable(ejercicio_id=ejercicio_id, motivo="Cierre aprobado", usuario="tester")
    assert cierre["ok"] is True
    resultado = asientos_svc.crear_asiento_apertura(
        empresa_id=1,
        ejercicio_id=ejercicio_id,
        fecha="2025-01-01",
        descripcion="Asiento posterior a cierre",
        lineas=lineas_apertura(),
        usuario="tester",
    )
    assert resultado["ok"] is False
    assert resultado["bloqueada"] is True


def test_anular_asiento_origen_anula_propuesta(monkeypatch, tmp_path):
    ejercicios_svc, asientos_svc, ejercicio_id = preparar_db_temporal(monkeypatch, tmp_path)
    creado = asientos_svc.crear_asiento_apertura(
        empresa_id=1,
        ejercicio_id=ejercicio_id,
        fecha="2025-01-01",
        descripcion="Asiento de apertura",
        lineas=lineas_apertura(),
        usuario="tester",
    )
    assert creado["ok"] is True
    anulacion = asientos_svc.anular_asiento_origen(
        asiento_origen_id=creado["asiento_origen_id"],
        motivo="Carga incorrecta",
        usuario="tester",
    )
    assert anulacion["ok"] is True
    assert anulacion["asiento"]["estado"] == "ANULADO"
    propuesta = asientos_svc.obtener_asiento_propuesto(creado["asiento_propuesto_id"])
    assert propuesta["estado"] == "ANULADO"


def test_listar_asientos_propuestos_pendientes(monkeypatch, tmp_path):
    ejercicios_svc, asientos_svc, ejercicio_id = preparar_db_temporal(monkeypatch, tmp_path)
    asientos_svc.crear_asiento_apertura(
        empresa_id=1,
        ejercicio_id=ejercicio_id,
        fecha="2025-01-01",
        descripcion="Asiento de apertura",
        lineas=lineas_apertura(),
        usuario="tester",
    )
    propuestos = asientos_svc.listar_asientos_propuestos(empresa_id=1, estado="PROPUESTO")
    assert len(propuestos) == 1
    assert propuestos.iloc[0]["origen"] == "APERTURA"


def test_resumen_asientos_origen(monkeypatch, tmp_path):
    ejercicios_svc, asientos_svc, ejercicio_id = preparar_db_temporal(monkeypatch, tmp_path)
    asientos_svc.crear_asiento_apertura(
        empresa_id=1,
        ejercicio_id=ejercicio_id,
        fecha="2025-01-01",
        descripcion="Asiento de apertura",
        lineas=lineas_apertura(),
        usuario="tester",
    )
    resumen = asientos_svc.obtener_resumen_asientos_origen(empresa_id=1)
    assert resumen["asientos_origen_total"] == 1
    assert resumen["asientos_origen_propuestos"] == 1
    assert resumen["asientos_propuestos_pendientes"] == 1