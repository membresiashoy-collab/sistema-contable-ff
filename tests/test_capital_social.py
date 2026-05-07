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

    ejercicios_svc.migrar_ejercicios_contables()
    asientos_svc.migrar_asientos_origen()
    capital_svc.migrar_capital_social()

    creado = ejercicios_svc.crear_ejercicio_contable(
        empresa_id=1,
        fecha_inicio="2025-01-01",
        fecha_cierre="2025-12-31",
        nombre="Ejercicio 2025",
        usuario="tester",
    )
    assert creado["ok"] is True
    return ejercicios_svc, asientos_svc, capital_svc, creado["ejercicio_id"]


def socios_base():
    return [
        {
            "nombre": "Socio A",
            "cuit": "20-11111111-1",
            "porcentaje": 60,
            "importe_suscripto": 600000,
            "importe_integrado": 300000,
            "medio_integracion": "BANCO",
            "cuenta_destino_codigo": "11102",
            "cuenta_destino_nombre": "Banco",
        },
        {
            "nombre": "Socio B",
            "cuit": "20-22222222-2",
            "porcentaje": 40,
            "importe_suscripto": 400000,
            "importe_integrado": 200000,
            "medio_integracion": "CAJA",
            "cuenta_destino_codigo": "11101",
            "cuenta_destino_nombre": "Caja",
        },
    ]


def test_configurar_capital_social_genera_socios_y_asientos_propuestos(monkeypatch, tmp_path):
    ejercicios_svc, asientos_svc, capital_svc, ejercicio_id = preparar_db_temporal(monkeypatch, tmp_path)
    resultado = capital_svc.configurar_capital_social_inicial(
        empresa_id=1,
        ejercicio_id=ejercicio_id,
        fecha_instrumento="2025-01-05",
        capital_social_total=1000000,
        socios=socios_base(),
        descripcion="Constitución inicial",
        referencia="Acta constitutiva",
        usuario="tester",
    )
    assert resultado["ok"] is True
    assert resultado["capital_id"] > 0
    assert resultado["asiento_suscripcion_propuesto_id"] > 0
    assert resultado["asiento_integracion_propuesto_id"] > 0

    socios = capital_svc.listar_socios_empresa(empresa_id=1)
    assert len(socios) == 2

    capital = capital_svc.obtener_capital_social(resultado["capital_id"])
    assert capital["capital_social_total"] == 1000000
    assert capital["total_suscripto"] == 1000000
    assert capital["total_integrado"] == 500000
    assert capital["total_pendiente_integracion"] == 500000
    assert len(capital["suscripciones"]) == 2
    assert len(capital["integraciones"]) == 2

    propuestos = asientos_svc.listar_asientos_propuestos(empresa_id=1, estado="PROPUESTO")
    assert len(propuestos) == 2
    libro = database.ejecutar_query("SELECT * FROM libro_diario", fetch=True)
    assert libro.empty


def test_rechaza_porcentaje_distinto_de_100(monkeypatch, tmp_path):
    ejercicios_svc, asientos_svc, capital_svc, ejercicio_id = preparar_db_temporal(monkeypatch, tmp_path)
    socios = socios_base()
    socios[1]["porcentaje"] = 20
    resultado = capital_svc.configurar_capital_social_inicial(
        empresa_id=1,
        ejercicio_id=ejercicio_id,
        fecha_instrumento="2025-01-05",
        capital_social_total=1000000,
        socios=socios,
        usuario="tester",
    )
    assert resultado["ok"] is False
    assert "100" in resultado["mensaje"]


def test_rechaza_integracion_mayor_a_suscripcion(monkeypatch, tmp_path):
    ejercicios_svc, asientos_svc, capital_svc, ejercicio_id = preparar_db_temporal(monkeypatch, tmp_path)
    socios = socios_base()
    socios[0]["importe_integrado"] = 700000
    resultado = capital_svc.configurar_capital_social_inicial(
        empresa_id=1,
        ejercicio_id=ejercicio_id,
        fecha_instrumento="2025-01-05",
        capital_social_total=1000000,
        socios=socios,
        usuario="tester",
    )
    assert resultado["ok"] is False
    assert "integrar más" in resultado["mensaje"]


def test_rechaza_capital_en_ejercicio_cerrado(monkeypatch, tmp_path):
    ejercicios_svc, asientos_svc, capital_svc, ejercicio_id = preparar_db_temporal(monkeypatch, tmp_path)
    cierre = ejercicios_svc.cerrar_ejercicio_contable(ejercicio_id=ejercicio_id, motivo="Cierre aprobado", usuario="tester")
    assert cierre["ok"] is True
    resultado = capital_svc.configurar_capital_social_inicial(
        empresa_id=1,
        ejercicio_id=ejercicio_id,
        fecha_instrumento="2025-01-05",
        capital_social_total=1000000,
        socios=socios_base(),
        usuario="tester",
    )
    assert resultado["ok"] is False
    assert resultado["bloqueada"] is True


def test_estado_inicio_contable(monkeypatch, tmp_path):
    ejercicios_svc, asientos_svc, capital_svc, ejercicio_id = preparar_db_temporal(monkeypatch, tmp_path)
    estado = capital_svc.obtener_estado_inicio_contable(empresa_id=1)
    assert estado["tiene_ejercicio"] is True
    assert estado["tiene_capital_social"] is False

    capital_svc.configurar_capital_social_inicial(
        empresa_id=1,
        ejercicio_id=ejercicio_id,
        fecha_instrumento="2025-01-05",
        capital_social_total=1000000,
        socios=socios_base(),
        usuario="tester",
    )
    estado = capital_svc.obtener_estado_inicio_contable(empresa_id=1)
    assert estado["tiene_capital_social"] is True
    assert estado["cantidad_socios"] == 2