from pathlib import Path
import sqlite3

from services.plan_cuentas_maestro_service import aplicar_migracion_021
from services.plan_cuentas_maestro_seed_service import (
    VERSION_PLAN_DEFAULT,
    aplicar_seed_plan_maestro,
    diagnosticar_plan_maestro_seed,
    listar_plan_maestro_seed,
    validar_csv_plan_maestro,
    vincular_plan_empresa_con_maestro,
)


CSV_PATH = Path("data/plan_cuentas_maestro_ff.csv")


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def test_csv_plan_maestro_es_valido_y_completo():
    validacion = validar_csv_plan_maestro(CSV_PATH)

    assert validacion.ok is True
    assert validacion.errores == []
    assert validacion.total_filas >= 380

    codigos = set(validacion.codigos)
    requeridos = {
        "1.1.03.00",  # Fondo fijo
        "1.1.05.00",  # Moneda extranjera
        "1.1.07.00",  # Recaudaciones a depositar
        "1.1.30.01",  # Deudores por ventas
        "1.1.30.07",  # Documentos a cobrar
        "1.1.40.09",  # IVA crédito fiscal
        "1.1.40.30",  # Percepciones IVA
        "2.1.01.01",  # Proveedores
        "2.1.03.03",  # Cargas sociales a pagar
        "2.1.04.01",  # IVA débito fiscal
        "3.1.02.00",  # Capital suscripto
        "4.1.00.00",  # Compras
        "5.1.01.00",  # Ventas
        "6.1.10.22",  # RECPAM
    }
    assert requeridos.issubset(codigos)


def test_seed_plan_maestro_inserta_e_idempotente():
    conn = _conn()
    aplicar_migracion_021(conn=conn)

    primera = aplicar_seed_plan_maestro(
        ruta_csv=CSV_PATH,
        usuario="pytest",
        conn=conn,
    )
    segunda = aplicar_seed_plan_maestro(
        ruta_csv=CSV_PATH,
        usuario="pytest",
        conn=conn,
    )

    assert primera["ok"] is True
    assert primera["filas_csv"] >= 380
    assert primera["insertadas"] == primera["filas_csv"]
    assert primera["actualizadas"] == 0

    assert segunda["ok"] is True
    assert segunda["filas_csv"] == primera["filas_csv"]
    assert segunda["insertadas"] == 0
    assert segunda["actualizadas"] == primera["filas_csv"]

    total = conn.execute(
        """
        SELECT COUNT(*)
        FROM plan_cuentas_maestro p
        JOIN versiones_plan_cuentas v ON v.id = p.version_plan_id
        WHERE v.version = ?
        """,
        (VERSION_PLAN_DEFAULT,),
    ).fetchone()[0]
    assert total == primera["filas_csv"]


def test_seed_completa_campos_contables_clave():
    conn = _conn()
    aplicar_migracion_021(conn=conn)
    resultado = aplicar_seed_plan_maestro(ruta_csv=CSV_PATH, usuario="pytest", conn=conn)
    assert resultado["ok"] is True

    cuentas = {item["codigo"]: item for item in listar_plan_maestro_seed(conn=conn)}

    caja = cuentas["1.1.01.01"]
    banco_modelo = cuentas["1.1.02.00"]
    moneda_ext = cuentas["1.1.05.00"]
    proveedores = cuentas["2.1.01.01"]
    amortizacion = cuentas["1.2.04.20"]
    recpam = cuentas["6.1.10.22"]

    assert caja["saldo_normal"] == "DEUDOR"
    assert caja["alertar_saldo_invertido"] == 1
    assert caja["permite_saldo_acreedor"] == 0
    assert caja["uso_operativo_sistema"] == "CAJA_GENERAL"

    assert banco_modelo["es_cuenta_modelo"] == 1
    assert banco_modelo["permite_copiar_modelo"] == 1
    assert banco_modelo["uso_operativo_sistema"] == "BANCO_CUENTA_CORRIENTE"
    assert banco_modelo["permite_saldo_acreedor"] == 1
    assert banco_modelo["tratamiento_saldo_invertido"] == "ADVERTIR_RECLASIFICAR"

    assert moneda_ext["admite_moneda_extranjera"] == 1
    assert moneda_ext["genera_diferencia_cambio"] == 1

    assert proveedores["saldo_normal"] == "ACREEDOR"
    assert proveedores["permite_saldo_deudor"] == 1
    assert proveedores["requiere_reclasificacion_saldo_invertido"] == 1

    assert amortizacion["es_regularizadora"] == 1
    assert amortizacion["saldo_normal"] == "ACREEDOR"

    assert recpam["saldo_normal"] == "SEGUN_NATURALEZA"
    assert recpam["permite_saldo_deudor"] == 1
    assert recpam["permite_saldo_acreedor"] == 1
    assert recpam["uso_operativo_sistema"] == "RECPAM"

    assert cuentas["1.1.20.08"]["uso_operativo_sistema"] == "FONDO_COMUN_INVERSION"
    assert cuentas["1.2.04.11"]["uso_operativo_sistema"] == "BIENES_USO_INMUEBLES"
    assert cuentas["1.2.04.20"]["cuenta_regularizada_codigo"] == "1.2.04.00"
    assert cuentas["2.2.08.01"]["es_regularizadora"] == 0


def test_diagnostico_seed_no_deja_madres_faltantes_ni_imputables_con_hijos():
    conn = _conn()
    aplicar_migracion_021(conn=conn)
    resultado = aplicar_seed_plan_maestro(ruta_csv=CSV_PATH, usuario="pytest", conn=conn)
    assert resultado["ok"] is True

    diagnostico = diagnosticar_plan_maestro_seed(conn=conn)

    assert diagnostico["ok"] is True
    assert diagnostico["cuentas_sin_madre_existente"] == []
    assert diagnostico["cuentas_imputables_con_hijos"] == []

    totales = {item["elemento"]: item["cantidad"] for item in diagnostico["totales_elemento"]}
    assert totales["ACTIVO"] > 100
    assert totales["PASIVO"] > 70
    assert totales["PATRIMONIO_NETO"] >= 10
    assert totales["INGRESOS_GANANCIAS"] >= 15
    assert totales["EGRESOS_GASTOS_PERDIDAS"] >= 40

    assert diagnostico["regularizadoras_sin_cuenta_regularizada"] == []

    modelos = {item["uso_operativo_sistema"] for item in diagnostico["cuentas_modelo"]}
    assert "BANCO_CUENTA_CORRIENTE" in modelos
    assert "BANCO_CAJA_AHORRO" in modelos
    assert "BANCO_PLAZO_FIJO" in modelos
    assert "BILLETERA_VIRTUAL" in modelos
    assert "FONDO_FIJO" in modelos
    assert "FONDO_COMUN_INVERSION" in modelos
    assert "BIENES_USO_INMUEBLES" in modelos
    assert None not in modelos


def test_vincular_plan_empresa_con_maestro_no_crea_ni_borra_cuentas_empresa():
    conn = _conn()
    aplicar_migracion_021(conn=conn)
    resultado = aplicar_seed_plan_maestro(ruta_csv=CSV_PATH, usuario="pytest", conn=conn)
    assert resultado["ok"] is True

    conn.executescript(
        """
        INSERT INTO plan_cuentas_empresa
        (empresa_id, codigo, nombre, codigo_madre, nivel, orden, imputable, estado, uso_operativo_sistema)
        VALUES
        (1, '1.1.01.01', 'Caja', '1.1.01.00', 4, 10, 1, 'ACTIVA', 'CAJA_GENERAL'),
        (1, '1.1.02.00', 'Banco Cta. Cte.', '1.1.01.00', 4, 20, 0, 'ACTIVA', 'BANCO_CUENTA_CORRIENTE'),
        (1, '9.9.99.99', 'Cuenta propia sin maestro', '', 1, 999, 1, 'ACTIVA', '')
        """
    )
    antes = conn.execute("SELECT COUNT(*) FROM plan_cuentas_empresa WHERE empresa_id = 1").fetchone()[0]

    vinculacion = vincular_plan_empresa_con_maestro(
        empresa_id=1,
        usuario="pytest",
        conn=conn,
    )
    despues = conn.execute("SELECT COUNT(*) FROM plan_cuentas_empresa WHERE empresa_id = 1").fetchone()[0]

    assert vinculacion["ok"] is True
    assert vinculacion["cuentas_vinculadas"] == 2
    assert despues == antes

    vinculadas = conn.execute(
        """
        SELECT codigo, cuenta_maestro_id
        FROM plan_cuentas_empresa
        WHERE empresa_id = 1
        ORDER BY codigo
        """
    ).fetchall()
    por_codigo = {row["codigo"]: row["cuenta_maestro_id"] for row in vinculadas}

    assert por_codigo["1.1.01.01"] is not None
    assert por_codigo["1.1.02.00"] is not None
    assert por_codigo["9.9.99.99"] is None