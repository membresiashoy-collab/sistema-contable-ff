import sqlite3

from services.normalizacion_contable_service import (
    anular_asignacion_comportamiento,
    aplicar_sugerencias_normalizacion,
    desactivar_asignacion_comportamiento,
    editar_asignacion_comportamiento,
    estimar_impacto_sugerencias,
    listar_asignaciones_normalizacion,
    listar_historial_normalizacion,
    listar_sugerencias_normalizacion,
    migrar_normalizacion_contable,
    obtener_resumen_normalizacion,
    sugerir_normalizacion_para_cuenta,
)
from services.comportamientos_contables_service import guardar_comportamiento_cuenta, listar_mapeos_comportamientos


def nueva_conexion():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def crear_plan_normalizacion(conn):
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
        ('11301', 'Clientes por ventas', 1, 1),
        ('21102', 'Proveedores comerciales', 1, 1),
        ('31101', 'Capital Social', 1, 1),
        ('11302', 'Socios por integración', 1, 1),
        ('51101', 'Sueldos y Jornales', 1, 1),
        ('21201', 'Cargas sociales a pagar', 1, 1);
        """
    )


def test_sugerencias_detectan_cuentas_operativas_y_comerciales():
    assert sugerir_normalizacion_para_cuenta("11101", "Caja")["comportamiento"] == "CAJA"
    assert sugerir_normalizacion_para_cuenta("11102", "Banco Nación")["comportamiento"] == "BANCO"
    assert sugerir_normalizacion_para_cuenta("11201", "IVA Crédito Fiscal")["comportamiento"] == "IVA_CREDITO"
    assert sugerir_normalizacion_para_cuenta("21101", "IVA Débito Fiscal")["comportamiento"] == "IVA_DEBITO"
    assert sugerir_normalizacion_para_cuenta("11301", "Clientes por ventas")["comportamiento"] == "CLIENTES"
    assert sugerir_normalizacion_para_cuenta("21102", "Proveedores comerciales")["comportamiento"] == "PROVEEDORES"
    assert sugerir_normalizacion_para_cuenta("31101", "Capital Social")["comportamiento"] == "CAPITAL_SOCIAL"


def test_migracion_agrega_columnas_de_correccion_controlada():
    conn = nueva_conexion()
    crear_plan_normalizacion(conn)

    migrar_normalizacion_contable(conn)

    columnas = {row[1] for row in conn.execute("PRAGMA table_info(contabilidad_cuentas_comportamiento)").fetchall()}
    assert "estado" in columnas
    assert "motivo_anulacion" in columnas
    assert "motivo_edicion" in columnas


def test_listar_y_aplicar_sugerencias_no_pisa_asignaciones_existentes():
    conn = nueva_conexion()
    crear_plan_normalizacion(conn)

    previo = guardar_comportamiento_cuenta(
        empresa_id=1,
        codigo_cuenta="11201",
        comportamiento="BANCO",
        usuario="tester",
        conn=conn,
    )
    assert previo["ok"] is True

    sugerencias = listar_sugerencias_normalizacion(empresa_id=1, conn=conn)
    conflicto = [item for item in sugerencias if item["codigo_cuenta"] == "11201"][0]
    assert conflicto["estado_sugerencia"] == "CONFLICTO"
    assert conflicto["aplicable"] is False

    resultado = aplicar_sugerencias_normalizacion(
        empresa_id=1,
        sugerencias=sugerencias,
        usuario="tester",
        motivo="Prueba asistente",
        conn=conn,
    )
    assert resultado["procesadas"] >= 6

    mapeos_iva = [item for item in listar_mapeos_comportamientos(empresa_id=1, conn=conn) if item["codigo_cuenta"] == "11201"]
    assert len(mapeos_iva) == 1
    assert mapeos_iva[0]["comportamiento"] == "BANCO"


def test_editar_desactivar_y_anular_asignacion_exigen_motivo_y_auditan():
    conn = nueva_conexion()
    crear_plan_normalizacion(conn)

    alta = guardar_comportamiento_cuenta(
        empresa_id=1,
        codigo_cuenta="11201",
        comportamiento="BANCO",
        usuario="tester",
        conn=conn,
    )
    mapeo_id = alta["mapeo_id"]

    sin_motivo = editar_asignacion_comportamiento(
        empresa_id=1,
        mapeo_id=mapeo_id,
        nuevo_comportamiento="IVA_CREDITO",
        usuario="tester",
        motivo="",
        conn=conn,
    )
    assert sin_motivo["ok"] is False

    editado = editar_asignacion_comportamiento(
        empresa_id=1,
        mapeo_id=mapeo_id,
        nuevo_comportamiento="IVA_CREDITO",
        usuario="tester",
        motivo="Corrección de asignación humana",
        conn=conn,
    )
    assert editado["ok"] is True

    desactivado = desactivar_asignacion_comportamiento(
        empresa_id=1,
        mapeo_id=mapeo_id,
        usuario="tester",
        motivo="La cuenta ya no se usará como comportamiento operativo",
        conn=conn,
    )
    assert desactivado["ok"] is True

    alta2 = guardar_comportamiento_cuenta(
        empresa_id=1,
        codigo_cuenta="11101",
        comportamiento="CAJA",
        usuario="tester",
        conn=conn,
    )
    anulado = anular_asignacion_comportamiento(
        empresa_id=1,
        mapeo_id=alta2["mapeo_id"],
        usuario="tester",
        motivo="Carga equivocada de prueba",
        conn=conn,
    )
    assert anulado["ok"] is True

    eventos = listar_historial_normalizacion(empresa_id=1, conn=conn)
    eventos_codigos = {item["evento"] for item in eventos}
    assert "EDITADO" in eventos_codigos
    assert "DESACTIVADO" in eventos_codigos
    assert "ANULADO" in eventos_codigos


def test_resumen_e_impacto_muestran_criticos_que_resolveria():
    conn = nueva_conexion()
    crear_plan_normalizacion(conn)

    sugerencias = listar_sugerencias_normalizacion(empresa_id=1, conn=conn)
    impacto = estimar_impacto_sugerencias(empresa_id=1, sugerencias=sugerencias, conn=conn)

    assert "CAJA" in impacto["criticos_que_resolveria"]
    assert "BANCO" in impacto["criticos_que_resolveria"]

    resumen = obtener_resumen_normalizacion(empresa_id=1, conn=conn)
    assert resumen["sugerencias_pendientes"] >= 8
    assert resumen["conflictos"] == 0


def test_listar_asignaciones_incluye_inactivas_para_correccion():
    conn = nueva_conexion()
    crear_plan_normalizacion(conn)

    alta = guardar_comportamiento_cuenta(
        empresa_id=1,
        codigo_cuenta="11101",
        comportamiento="CAJA",
        usuario="tester",
        conn=conn,
    )
    desactivar_asignacion_comportamiento(
        empresa_id=1,
        mapeo_id=alta["mapeo_id"],
        usuario="tester",
        motivo="Prueba de baja lógica",
        conn=conn,
    )

    asignaciones = listar_asignaciones_normalizacion(empresa_id=1, incluir_inactivas=True, conn=conn)
    assert len(asignaciones) == 1
    assert asignaciones[0]["activo"] == 0