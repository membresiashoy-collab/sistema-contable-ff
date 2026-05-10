import sqlite3

from services.plan_cuentas_service import (
    asegurar_estructura_plan_cuentas,
    diagnosticar_plan_cuentas_pro,
    guardar_cuenta_plan,
    limpiar_comportamiento_cuenta,
    listar_plan_cuentas,
    normalizar_metadata_plan_cuentas,
    sugerir_comportamiento_plan,
)


def nueva_conexion():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def test_plan_cuentas_es_fuente_de_verdad_y_bloquea_no_imputable():
    conn = nueva_conexion()
    asegurar_estructura_plan_cuentas(conn)

    resultado = guardar_cuenta_plan(
        empresa_id=1,
        codigo="1",
        nombre="ACTIVO",
        imputable="N",
        comportamiento_contable="IVA_DEBITO",
        permite_imputacion_operativa=1,
        usuario="tester",
        motivo="Prueba de bloqueo",
        conn=conn,
    )

    assert resultado["ok"] is False
    assert "no imputable" in " ".join(resultado["errores"]).lower()


def test_guardar_cuenta_imputable_con_comportamiento_y_auditoria():
    conn = nueva_conexion()
    asegurar_estructura_plan_cuentas(conn)

    resultado = guardar_cuenta_plan(
        empresa_id=1,
        codigo="2.2.01",
        nombre="IVA DEBITO FISCAL",
        imputable="S",
        tipo="P",
        madre="2.2",
        nivel=3,
        orden=340,
        comportamiento_contable="IVA_DEBITO",
        permite_imputacion_operativa=1,
        usuario="tester",
        motivo="Alta IVA débito",
        conn=conn,
    )

    assert resultado["ok"] is True
    cuentas = listar_plan_cuentas(empresa_id=1, conn=conn)
    cuenta = [item for item in cuentas if item["codigo"] == "2.2.01"][0]
    assert cuenta["comportamiento_contable"] == "IVA_DEBITO"
    assert cuenta["imputable"] == "S"

    eventos = conn.execute("SELECT evento, codigo_cuenta FROM plan_cuentas_eventos").fetchall()
    assert any(row[0] in {"CUENTA_CREADA", "CUENTA_EDITADA"} and row[1] == "2.2.01" for row in eventos)


def test_normalizar_metadata_limpia_cuentas_no_imputables_contaminadas():
    conn = nueva_conexion()
    asegurar_estructura_plan_cuentas(conn)
    conn.execute(
        "INSERT INTO plan_cuentas_detallado (cuenta, detalle, imputable, tipo, madre, nivel, orden, empresa_id) VALUES ('1','ACTIVO','N','A','',1,10,1)"
    )
    conn.execute(
        "INSERT INTO plan_cuentas (codigo, nombre, empresa_id, comportamiento_contable, permite_imputacion_operativa) VALUES ('1','ACTIVO',1,'IVA_DEBITO',1)"
    )

    diagnostico = diagnosticar_plan_cuentas_pro(empresa_id=1, conn=conn)
    assert diagnostico["errores"]

    resultado = normalizar_metadata_plan_cuentas(empresa_id=1, usuario="tester", conn=conn)
    assert resultado["ok"] is True

    cuenta = [item for item in listar_plan_cuentas(empresa_id=1, conn=conn) if item["codigo"] == "1"][0]
    assert cuenta["comportamiento_contable"] == ""
    assert cuenta["permite_imputacion_operativa"] == 0


def test_sugerencias_no_confunden_nacionales_con_banco():
    sugerencia = sugerir_comportamiento_plan(
        "1.3.06",
        "PERCEPCIONES OTROS IMPUESTOS NACIONALES",
        "S",
    )
    assert sugerencia["comportamiento"] != "BANCO"

    banco = sugerir_comportamiento_plan("1.1.02", "BANCO CUENTA CORRIENTE", "S")
    assert banco["comportamiento"] == "BANCO"


def test_limpiar_comportamiento_exige_motivo_y_registra():
    conn = nueva_conexion()
    guardar_cuenta_plan(
        empresa_id=1,
        codigo="1.1.01",
        nombre="CAJA",
        imputable="S",
        comportamiento_contable="CAJA",
        usuario="tester",
        motivo="Alta caja",
        conn=conn,
    )

    sin_motivo = limpiar_comportamiento_cuenta("1.1.01", empresa_id=1, usuario="tester", motivo="", conn=conn)
    assert sin_motivo["ok"] is False

    limpio = limpiar_comportamiento_cuenta(
        "1.1.01",
        empresa_id=1,
        usuario="tester",
        motivo="Corrección de prueba",
        conn=conn,
    )
    assert limpio["ok"] is True

    cuenta = [item for item in listar_plan_cuentas(empresa_id=1, conn=conn) if item["codigo"] == "1.1.01"][0]
    assert cuenta["comportamiento_contable"] == ""