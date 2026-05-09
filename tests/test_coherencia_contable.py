import sqlite3

from core.contabilidad_coherencia import (
    formatear_fecha_argentina,
    normalizar_fecha_iso,
    rangos_superpuestos,
    validar_comportamiento_contable,
)
from services.coherencia_contable_service import (
    aplicar_migracion_nucleo,
    diagnosticar_ejercicios_contables,
    diagnosticar_nucleo_coherencia,
    diagnosticar_plan_cuentas,
    guardar_diagnosticos,
    resumen_diagnostico,
)


def nueva_conexion():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def test_formato_fecha_argentino_y_guardado_iso():
    assert normalizar_fecha_iso("31/12/2025") == "2025-12-31"
    assert normalizar_fecha_iso("2025-12-31") == "2025-12-31"
    assert formatear_fecha_argentina("2025-12-31") == "31/12/2025"


def test_rangos_superpuestos():
    assert rangos_superpuestos("2025-01-01", "2025-12-31", "2025-06-01", "2026-05-31") is True
    assert rangos_superpuestos("2025-01-01", "2025-12-31", "2026-01-01", "2026-12-31") is False


def test_comportamientos_contables_basicos():
    assert validar_comportamiento_contable("CAJA") is True
    assert validar_comportamiento_contable("Banco") is True
    assert validar_comportamiento_contable("concepto libre") is False


def test_migracion_crea_tablas_base():
    conn = nueva_conexion()
    aplicar_migracion_nucleo(conn)

    tablas = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }
    assert "contabilidad_cuentas_comportamiento" in tablas
    assert "contabilidad_origenes_economicos" in tablas
    assert "contabilidad_diagnosticos_coherencia" in tablas

    total_origenes = conn.execute("SELECT COUNT(*) FROM contabilidad_origenes_economicos").fetchone()[0]
    assert total_origenes >= 10


def test_diagnostica_ejercicios_superpuestos_y_multiples_actuales():
    conn = nueva_conexion()
    conn.executescript(
        """
        CREATE TABLE ejercicios_contables (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER,
            fecha_inicio TEXT,
            fecha_fin TEXT,
            es_actual INTEGER,
            estado TEXT
        );
        INSERT INTO ejercicios_contables (empresa_id, fecha_inicio, fecha_fin, es_actual, estado)
        VALUES
        (1, '2025-01-01', '2025-12-31', 1, 'ABIERTO'),
        (1, '2025-07-01', '2026-06-30', 1, 'ABIERTO');
        """
    )

    diagnosticos = diagnosticar_ejercicios_contables(empresa_id=1, conn=conn)
    codigos = {item["codigo"] for item in diagnosticos}
    assert "EJERCICIOS_SUPERPUESTOS" in codigos
    assert "EJERCICIOS_MULTIPLES_ACTUALES" in codigos


def test_plan_cuentas_detecta_comportamientos_faltantes():
    conn = nueva_conexion()
    conn.executescript(
        """
        CREATE TABLE plan_cuentas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER,
            codigo TEXT,
            nombre TEXT,
            imputable INTEGER
        );
        INSERT INTO plan_cuentas (empresa_id, codigo, nombre, imputable)
        VALUES (1, '11101', 'Caja', 1);
        """
    )

    diagnosticos = diagnosticar_plan_cuentas(empresa_id=1, conn=conn)
    codigos = {item["codigo"] for item in diagnosticos}
    assert "PLAN_COMPORTAMIENTOS_CRITICOS_FALTANTES" in codigos
    assert "PLAN_CUENTAS_SIN_COMPORTAMIENTO" in codigos


def test_nucleo_guarda_diagnosticos_y_resumen():
    conn = nueva_conexion()
    conn.executescript(
        """
        CREATE TABLE ejercicios_contables (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER,
            fecha_inicio TEXT,
            fecha_fin TEXT,
            es_actual INTEGER,
            estado TEXT
        );
        CREATE TABLE plan_cuentas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER,
            codigo TEXT,
            nombre TEXT,
            imputable INTEGER,
            comportamiento_contable TEXT
        );
        CREATE TABLE libro_diario (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER,
            fecha TEXT,
            origen TEXT
        );
        INSERT INTO ejercicios_contables (empresa_id, fecha_inicio, fecha_fin, es_actual, estado)
        VALUES (1, '2025-01-01', '2025-12-31', 1, 'ABIERTO');
        INSERT INTO plan_cuentas (empresa_id, codigo, nombre, imputable, comportamiento_contable)
        VALUES
        (1, '11101', 'Caja', 1, 'CAJA'),
        (1, '11102', 'Banco', 1, 'BANCO'),
        (1, '11201', 'IVA crédito fiscal', 1, 'IVA_CREDITO'),
        (1, '21101', 'IVA débito fiscal', 1, 'IVA_DEBITO'),
        (1, '31101', 'Capital social', 1, 'CAPITAL_SOCIAL'),
        (1, '11301', 'Socios por integración', 1, 'SOCIOS_INTEGRACION'),
        (1, '31201', 'Aportes irrevocables', 1, 'APORTE_IRREVOCABLE'),
        (1, '21301', 'Préstamos de socios', 1, 'PRESTAMO_SOCIO'),
        (1, '11302', 'Cuenta particular socios', 1, 'CUENTA_PARTICULAR_SOCIO'),
        (1, '51101', 'Sueldos y jornales', 1, 'SUELDOS_GASTO'),
        (1, '21201', 'Sueldos a pagar', 1, 'SUELDOS_A_PAGAR'),
        (1, '51102', 'Cargas sociales', 1, 'CARGAS_SOCIALES_GASTO'),
        (1, '21202', 'Cargas sociales a pagar', 1, 'CARGAS_SOCIALES_A_PAGAR'),
        (1, '21203', 'ART a pagar', 1, 'ART_A_PAGAR'),
        (1, '21204', 'Obra social a pagar', 1, 'OBRA_SOCIAL_A_PAGAR'),
        (1, '21205', 'Sindicato a pagar', 1, 'SINDICATO_A_PAGAR');
        INSERT INTO libro_diario (empresa_id, fecha, origen)
        VALUES (1, '2025-05-10', 'TEST');
        """
    )

    diagnosticos = diagnosticar_nucleo_coherencia(empresa_id=1, conn=conn, guardar=True)
    resumen = resumen_diagnostico(diagnosticos)

    assert resumen["TOTAL"] >= 1
    assert conn.execute("SELECT COUNT(*) FROM contabilidad_diagnosticos_coherencia").fetchone()[0] == len(diagnosticos)

    guardar_diagnosticos(diagnosticos, empresa_id=1, conn=conn)
    activos = conn.execute(
        "SELECT COUNT(*) FROM contabilidad_diagnosticos_coherencia WHERE resuelto = 0"
    ).fetchone()[0]
    assert activos == len(diagnosticos)