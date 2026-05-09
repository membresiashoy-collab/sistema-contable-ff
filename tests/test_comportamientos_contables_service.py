import sqlite3

from services.comportamientos_contables_service import (
    aplicar_sugerencias_comportamientos,
    desactivar_comportamiento_cuenta,
    guardar_comportamiento_cuenta,
    listar_cuentas_plan,
    listar_eventos_comportamientos,
    listar_mapeos_comportamientos,
    listar_sugerencias_comportamientos,
    migrar_configuracion_comportamientos,
    obtener_resumen_configuracion_comportamientos,
    sugerir_comportamiento_para_cuenta,
)
from services.coherencia_contable_service import diagnosticar_plan_cuentas


def nueva_conexion():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def crear_plan_basico(conn):
    conn.executescript(
        """
        CREATE TABLE plan_cuentas (
            codigo TEXT,
            nombre TEXT,
            empresa_id INTEGER DEFAULT 1,
            imputable INTEGER DEFAULT 1
        );
        INSERT INTO plan_cuentas (codigo, nombre, empresa_id, imputable) VALUES
        ('11101', 'Caja', 1, 1),
        ('11102', 'Banco Nación cuenta corriente', 1, 1),
        ('11201', 'IVA Crédito Fiscal', 1, 1),
        ('21101', 'IVA Débito Fiscal', 1, 1),
        ('31101', 'Capital Social', 1, 1),
        ('11301', 'Socios por integración', 1, 1),
        ('31201', 'Aportes irrevocables', 1, 1),
        ('21301', 'Préstamos de socios', 1, 1),
        ('11302', 'Cuenta particular socios', 1, 1),
        ('51101', 'Sueldos y Jornales', 1, 1),
        ('21201', 'Sueldos a pagar', 1, 1),
        ('51102', 'Cargas sociales', 1, 1),
        ('21202', 'Cargas sociales a pagar', 1, 1),
        ('21203', 'ART a pagar', 1, 1),
        ('21204', 'Obra social a pagar', 1, 1),
        ('21205', 'Sindicato a pagar', 1, 1);
        """
    )


def test_migracion_extiende_tablas_y_plan_cuentas():
    conn = nueva_conexion()
    crear_plan_basico(conn)

    migrar_configuracion_comportamientos(conn)

    tablas = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }
    assert "contabilidad_cuentas_comportamiento" in tablas
    assert "contabilidad_cuentas_comportamiento_eventos" in tablas

    columnas_plan = {row[1] for row in conn.execute("PRAGMA table_info(plan_cuentas)").fetchall()}
    assert "comportamiento_contable" in columnas_plan


def test_sugerencias_detectan_cuentas_por_nombre():
    assert sugerir_comportamiento_para_cuenta("11101", "Caja") ["comportamiento"] == "CAJA"
    assert sugerir_comportamiento_para_cuenta("11102", "Banco Nación") ["comportamiento"] == "BANCO"
    assert sugerir_comportamiento_para_cuenta("11201", "IVA Crédito Fiscal") ["comportamiento"] == "IVA_CREDITO"
    assert sugerir_comportamiento_para_cuenta("21101", "IVA Débito Fiscal") ["comportamiento"] == "IVA_DEBITO"


def test_guardar_y_desactivar_comportamiento_sin_duplicar():
    conn = nueva_conexion()
    crear_plan_basico(conn)

    resultado = guardar_comportamiento_cuenta(
        empresa_id=1,
        codigo_cuenta="11101",
        comportamiento="CAJA",
        usuario="tester",
        conn=conn,
    )
    assert resultado["ok"] is True

    repetido = guardar_comportamiento_cuenta(
        empresa_id=1,
        codigo_cuenta="11101",
        comportamiento="CAJA",
        usuario="tester",
        conn=conn,
    )
    assert repetido["ok"] is True
    assert repetido.get("sin_cambios") is True

    mapeos = listar_mapeos_comportamientos(empresa_id=1, conn=conn)
    assert len(mapeos) == 1
    assert mapeos[0]["comportamiento"] == "CAJA"

    cuenta = listar_cuentas_plan(empresa_id=1, conn=conn)[0]
    assert "CAJA" in cuenta["comportamientos"]

    baja = desactivar_comportamiento_cuenta(
        empresa_id=1,
        mapeo_id=mapeos[0]["id"],
        usuario="tester",
        motivo="Prueba",
        conn=conn,
    )
    assert baja["ok"] is True
    assert listar_mapeos_comportamientos(empresa_id=1, conn=conn) == []
    assert len(listar_eventos_comportamientos(empresa_id=1, conn=conn)) >= 2


def test_aplicar_sugerencias_cubre_criticos_y_diagnostico_plan_ok():
    conn = nueva_conexion()
    crear_plan_basico(conn)

    sugerencias = listar_sugerencias_comportamientos(empresa_id=1, conn=conn)
    assert len(sugerencias) >= 10

    resultado = aplicar_sugerencias_comportamientos(
        empresa_id=1,
        sugerencias=sugerencias,
        usuario="tester",
        conn=conn,
    )
    assert resultado["procesadas"] >= 10

    resumen = obtener_resumen_configuracion_comportamientos(empresa_id=1, conn=conn)
    assert resumen["criticos_faltantes"] == []
    assert resumen["criticos_cubiertos"] == resumen["criticos_total"]

    diagnosticos = diagnosticar_plan_cuentas(empresa_id=1, conn=conn)
    codigos = {item["codigo"] for item in diagnosticos}
    assert "PLAN_COMPORTAMIENTOS_CRITICOS_FALTANTES" not in codigos