import sqlite3
from pathlib import Path

from services.plan_cuentas_maestro_service import aplicar_migracion_021
from services.plan_cuentas_maestro_seed_service import aplicar_seed_plan_maestro
from services.plan_cuentas_service import (
    asegurar_estructura_plan_cuentas,
    crear_cuenta_empresa_desde_modelo,
    diagnosticar_plan_cuentas_unificado,
    guardar_cuenta_plan,
    listar_cuentas_empresa_unificadas,
    listar_estructura_maestra_plan_cuentas,
    listar_modelos_copiables_plan_cuentas,
    listar_plan_cuentas,
    normalizar_metadata_plan_cuentas,
    vincular_plan_empresa_con_maestro_seguro,
)


CSV_PATH = Path("data/plan_cuentas_maestro_ff.csv")


def nueva_conexion():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def preparar_maestro(conn):
    aplicar_migracion_021(conn=conn)
    resultado = aplicar_seed_plan_maestro(
        ruta_csv=CSV_PATH,
        usuario="pytest",
        conn=conn,
    )
    assert resultado["ok"] is True


def test_plan_de_cuentas_unificado_usa_maestro_como_base():
    conn = nueva_conexion()
    preparar_maestro(conn)

    cuentas = listar_estructura_maestra_plan_cuentas(
        version="FF-PDF-2026-01",
        texto="IVA",
        elemento="ACTIVO",
        conn=conn,
    )

    assert cuentas
    assert all(cuenta["elemento"] == "ACTIVO" for cuenta in cuentas)
    assert any("IVA" in cuenta["nombre"].upper() for cuenta in cuentas)

    modelos = listar_modelos_copiables_plan_cuentas(
        version="FF-PDF-2026-01",
        conn=conn,
    )

    usos_modelo = {item["uso_operativo_sistema"] for item in modelos}
    assert "BANCO_CUENTA_CORRIENTE" in usos_modelo
    assert "BILLETERA_VIRTUAL" in usos_modelo
    assert "FONDO_FIJO" in usos_modelo


def test_plan_empresa_se_vincula_al_maestro_sin_crear_ni_borrar():
    conn = nueva_conexion()
    preparar_maestro(conn)

    conn.executescript(
        """
        INSERT INTO plan_cuentas_empresa
        (empresa_id, codigo, nombre, codigo_madre, nivel, orden, imputable, estado, uso_operativo_sistema)
        VALUES
        (1, '1.1.01.01', 'Caja', '1.1.01.00', 4, 10, 1, 'ACTIVA', 'CAJA_GENERAL'),
        (1, '1.1.02.00', 'Banco cuenta corriente', '1.1.01.00', 4, 20, 0, 'ACTIVA', 'BANCO_CUENTA_CORRIENTE'),
        (1, '9.9.99.99', 'Cuenta propia empresa', '', 1, 999, 1, 'ACTIVA', '')
        """
    )

    antes = conn.execute(
        "SELECT COUNT(*) FROM plan_cuentas_empresa WHERE empresa_id = 1"
    ).fetchone()[0]

    diagnostico = diagnosticar_plan_cuentas_unificado(
        empresa_id=1,
        version="FF-PDF-2026-01",
        conn=conn,
    )

    assert diagnostico["ok"] is True
    assert diagnostico["total_maestro"] >= 380
    assert diagnostico["total_empresa"] == 3
    assert diagnostico["pendientes_vincular_count"] == 2
    assert diagnostico["propias_empresa_count"] == 1

    resultado = vincular_plan_empresa_con_maestro_seguro(
        empresa_id=1,
        version="FF-PDF-2026-01",
        usuario="pytest",
        conn=conn,
    )

    despues = conn.execute(
        "SELECT COUNT(*) FROM plan_cuentas_empresa WHERE empresa_id = 1"
    ).fetchone()[0]

    assert resultado["ok"] is True
    assert resultado["cuentas_vinculadas"] == 2
    assert despues == antes

    cuentas = listar_cuentas_empresa_unificadas(
        empresa_id=1,
        version="FF-PDF-2026-01",
        solo_activas=False,
        conn=conn,
    )

    estados = {item["codigo"]: item["estado_origen_plan"] for item in cuentas}
    assert estados["1.1.01.01"] == "VINCULADA_AL_MAESTRO"
    assert estados["1.1.02.00"] == "VINCULADA_AL_MAESTRO"
    assert estados["9.9.99.99"] == "HEREDADA_SIN_VINCULO"


def test_compatibilidad_heredada_bloquea_no_imputable_con_uso_tecnico():
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


def test_compatibilidad_normaliza_cuentas_no_imputables_contaminadas():
    conn = nueva_conexion()
    asegurar_estructura_plan_cuentas(conn)

    conn.execute(
        "INSERT INTO plan_cuentas_detallado (cuenta, detalle, imputable, tipo, madre, nivel, orden, empresa_id) VALUES ('1','ACTIVO','N','A','',1,10,1)"
    )
    conn.execute(
        "INSERT INTO plan_cuentas (codigo, nombre, empresa_id, comportamiento_contable, permite_imputacion_operativa) VALUES ('1','ACTIVO',1,'IVA_DEBITO',1)"
    )

    resultado = normalizar_metadata_plan_cuentas(
        empresa_id=1,
        usuario="tester",
        conn=conn,
    )

    assert resultado["ok"] is True

    cuenta = [
        item for item in listar_plan_cuentas(empresa_id=1, conn=conn)
        if item["codigo"] == "1"
    ][0]

    assert cuenta["comportamiento_contable"] == ""
    assert cuenta["permite_imputacion_operativa"] == 0



def test_crear_cuenta_empresa_desde_modelo_crea_cuenta_especifica_auditada():
    conn = nueva_conexion()
    preparar_maestro(conn)

    modelo = conn.execute(
        """
        SELECT codigo
        FROM plan_cuentas_maestro
        WHERE es_cuenta_modelo = 1
          AND permite_copiar_modelo = 1
          AND uso_operativo_sistema = 'BANCO_CUENTA_CORRIENTE'
        LIMIT 1
        """
    ).fetchone()

    assert modelo is not None

    resultado = crear_cuenta_empresa_desde_modelo(
        empresa_id=1,
        codigo_modelo=modelo["codigo"],
        codigo_nuevo="1.99.01.01",
        nombre_nuevo="Banco Macro Cta. Cte. 1234",
        banco_nombre="Banco Macro",
        numero_cuenta="1234",
        moneda="ARS",
        motivo="Alta de cuenta bancaria específica de prueba",
        usuario="pytest",
        conn=conn,
    )

    assert resultado["ok"] is True

    cuenta = conn.execute(
        """
        SELECT e.*, m.codigo AS codigo_modelo, m.uso_operativo_sistema
        FROM plan_cuentas_empresa e
        JOIN plan_cuentas_maestro m ON m.id = e.cuenta_maestro_id
        WHERE e.empresa_id = 1
          AND e.codigo = '1.99.01.01'
        LIMIT 1
        """
    ).fetchone()

    assert cuenta is not None
    assert cuenta["nombre"] == "Banco Macro Cta. Cte. 1234"
    assert cuenta["banco_nombre"] == "Banco Macro"
    assert cuenta["numero_cuenta"] == "1234"
    assert cuenta["moneda"] == "ARS"
    assert cuenta["es_cuenta_especifica_empresa"] == 1
    assert cuenta["uso_operativo_sistema"] == "BANCO_CUENTA_CORRIENTE"

    auditoria = conn.execute(
        """
        SELECT COUNT(*)
        FROM plan_cuentas_eventos
        WHERE evento = 'CUENTA_EMPRESA_CREADA_DESDE_MODELO'
          AND codigo_cuenta = '1.99.01.01'
        """
    ).fetchone()[0]

    assert auditoria == 1

    duplicado = crear_cuenta_empresa_desde_modelo(
        empresa_id=1,
        codigo_modelo=modelo["codigo"],
        codigo_nuevo="1.99.01.01",
        nombre_nuevo="Banco Macro duplicado",
        motivo="Intento duplicado",
        usuario="pytest",
        conn=conn,
    )

    assert duplicado["ok"] is False



def test_diagnostico_diferencia_heredadas_de_cuentas_desde_modelo():
    conn = nueva_conexion()
    preparar_maestro(conn)

    conn.executescript(
        """
        INSERT INTO plan_cuentas_empresa
        (empresa_id, codigo, nombre, codigo_madre, nivel, orden, imputable, estado, uso_operativo_sistema)
        VALUES
        (1, '9.9.99.99', 'Cuenta heredada sin maestro', '', 1, 999, 1, 'ACTIVA', '')
        """
    )

    modelo = conn.execute(
        """
        SELECT codigo
        FROM plan_cuentas_maestro
        WHERE es_cuenta_modelo = 1
          AND permite_copiar_modelo = 1
        LIMIT 1
        """
    ).fetchone()

    resultado = crear_cuenta_empresa_desde_modelo(
        empresa_id=1,
        codigo_modelo=modelo["codigo"],
        codigo_nuevo="1.99.01.01",
        nombre_nuevo="Cuenta específica desde modelo",
        motivo="Prueba desde modelo",
        usuario="pytest",
        conn=conn,
    )

    assert resultado["ok"] is True

    diagnostico = diagnosticar_plan_cuentas_unificado(
        empresa_id=1,
        version="FF-PDF-2026-01",
        conn=conn,
    )

    assert diagnostico["creadas_desde_modelo_count"] == 1
    assert diagnostico["heredadas_pendientes_count"] == 1
    assert diagnostico["no_vinculadas_count"] == 1

    cuentas = listar_cuentas_empresa_unificadas(
        empresa_id=1,
        version="FF-PDF-2026-01",
        solo_activas=False,
        conn=conn,
    )

    origenes = {item["codigo"]: item["estado_origen_plan"] for item in cuentas}
    assert origenes["1.99.01.01"] == "CREADA_DESDE_MODELO"
    assert origenes["9.9.99.99"] == "HEREDADA_SIN_VINCULO"
