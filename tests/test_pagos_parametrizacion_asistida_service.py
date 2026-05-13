import sqlite3
from pathlib import Path

from services.pagos_parametrizacion_asistida_service import (
    diagnosticar_parametrizacion_pagos,
    obtener_parametrizacion_asistida_pagos,
)


def crear_plan_empresa(conn):
    conn.executescript(
        """
        CREATE TABLE plan_cuentas_empresa (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER,
            codigo TEXT,
            nombre TEXT,
            uso_operativo TEXT,
            activa INTEGER
        );
        """
    )

    cuentas = [
        (1, 1, "2.1.01", "Proveedores", "proveedores", 1),
        (2, 1, "1.1.01", "Caja principal", "caja", 1),
        (3, 1, "1.1.02", "Banco principal", "banco", 1),
        (4, 1, "2.2.01", "Retenciones IIBB a depositar", "retencion_iibb", 1),
        (5, 1, "2.2.02", "Retenciones Ganancias a depositar", "retencion_ganancias", 1),
        (6, 1, "2.2.03", "Retenciones IVA a depositar", "retencion_iva", 1),
        (7, 1, "2.2.04", "Retenciones SUSS a depositar", "retencion_suss", 1),
        (8, 1, "2.2.05", "Otras retenciones a depositar", "otras_retenciones", 1),
        (9, 1, "1.3.09", "Anticipos a proveedores", "anticipos_proveedores", 1),
        (10, 1, "5.9.01", "Diferencias de pago", "diferencia_pago", 1),
    ]
    conn.executemany(
        """
        INSERT INTO plan_cuentas_empresa
            (id, empresa_id, codigo, nombre, uso_operativo, activa)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        cuentas,
    )


def crear_codigo_pagos(tmp_path: Path, service_text: str = "", modulo_text: str = ""):
    (tmp_path / "services").mkdir()
    (tmp_path / "modulos").mkdir()
    (tmp_path / "services" / "pagos_service.py").write_text(service_text, encoding="utf-8")
    (tmp_path / "modulos" / "pagos.py").write_text(modulo_text, encoding="utf-8")


def test_parametrizacion_no_rompe_sin_conexion(tmp_path):
    crear_codigo_pagos(tmp_path)

    resultado = obtener_parametrizacion_asistida_pagos(
        empresa_id=1,
        conn=None,
        base_path=tmp_path,
    )

    assert resultado["modulo"] == "Pagos PRO v2A"
    assert resultado["modo"] == "solo_lectura"
    assert resultado["cuentas_plan_detectadas"] == 0
    assert any(a["codigo"] == "PAGOS_PARAMETRIZACION_SIN_CONEXION_DB" for a in resultado["alertas"])


def test_sugiere_cuentas_desde_plan_empresa(tmp_path):
    conn = sqlite3.connect(":memory:")
    crear_plan_empresa(conn)
    crear_codigo_pagos(tmp_path)

    resultado = obtener_parametrizacion_asistida_pagos(
        empresa_id=1,
        conn=conn,
        base_path=tmp_path,
    )

    assert resultado["cuentas_plan_detectadas"] == 10
    assert resultado["fuente_cuentas"] == "plan_cuentas_empresa"

    matriz = {fila["codigo"]: fila for fila in resultado["matriz"]}

    assert matriz["PROVEEDORES"]["estado"] == "SUGERIDA"
    assert matriz["ANTICIPO_A_PROVEEDOR"]["estado"] == "SUGERIDA"
    assert matriz["RETENCION_IVA"]["estado"] == "SUGERIDA"
    assert matriz["DIFERENCIA_PAGO"]["estado"] == "SUGERIDA"
    assert matriz["ORDEN_DE_PAGO"]["estado"] == "INFORMATIVA"


def test_detecta_incompletas_si_faltan_anticipos_y_diferencias(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE plan_cuentas_empresa (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER,
            codigo TEXT,
            nombre TEXT,
            uso_operativo TEXT,
            activa INTEGER
        );

        INSERT INTO plan_cuentas_empresa
            (empresa_id, codigo, nombre, uso_operativo, activa)
        VALUES
            (1, '2.1.01', 'Proveedores', 'proveedores', 1),
            (1, '1.1.01', 'Caja principal', 'caja', 1),
            (1, '1.1.02', 'Banco principal', 'banco', 1);
        """
    )
    crear_codigo_pagos(tmp_path)

    resultado = diagnosticar_parametrizacion_pagos(
        empresa_id=1,
        conn=conn,
        base_path=tmp_path,
    )

    matriz = {fila["codigo"]: fila for fila in resultado["matriz"]}

    assert matriz["ANTICIPO_A_PROVEEDOR"]["estado"] == "INCOMPLETA"
    assert matriz["DIFERENCIA_PAGO"]["estado"] == "INCOMPLETA"
    assert resultado["estado"] == "REQUIERE_PARAMETRIZACION"


def test_detecta_hardcodes_legacy_de_pagos(tmp_path):
    conn = sqlite3.connect(":memory:")
    crear_plan_empresa(conn)
    crear_codigo_pagos(
        tmp_path,
        service_text="""
CUENTA_PROVEEDORES = "PROVEEDORES"
CUENTAS_RETENCIONES_DEFAULT = {
    "IVA": "RETENCIONES IVA A DEPOSITAR"
}
cur.execute("INSERT INTO libro_diario VALUES (...)")
""",
    )

    resultado = obtener_parametrizacion_asistida_pagos(
        empresa_id=1,
        conn=conn,
        base_path=tmp_path,
    )

    codigos = {alerta["codigo"] for alerta in resultado["alertas"]}

    assert "PAGOS_LEGACY_CUENTAS_HARDCODEADAS" in codigos
    assert "PAGOS_LEGACY_ASIENTO_DIRECTO" in codigos


def test_detecta_falta_de_bandeja_explicita(tmp_path):
    conn = sqlite3.connect(":memory:")
    crear_plan_empresa(conn)
    crear_codigo_pagos(tmp_path, service_text="def registrar_pago(): pass")

    resultado = obtener_parametrizacion_asistida_pagos(
        empresa_id=1,
        conn=conn,
        base_path=tmp_path,
    )

    assert any(a["codigo"] == "PAGOS_SIN_BANDEJA_EXPLICITA" for a in resultado["alertas"])


def test_no_alerta_falta_bandeja_si_codigo_la_menciona(tmp_path):
    conn = sqlite3.connect(":memory:")
    crear_plan_empresa(conn)
    crear_codigo_pagos(tmp_path, service_text="# futura integracion con asientos_propuestos / bandeja")

    resultado = obtener_parametrizacion_asistida_pagos(
        empresa_id=1,
        conn=conn,
        base_path=tmp_path,
    )

    assert not any(a["codigo"] == "PAGOS_SIN_BANDEJA_EXPLICITA" for a in resultado["alertas"])


def test_servicio_es_de_solo_lectura(tmp_path):
    conn = sqlite3.connect(":memory:")
    crear_plan_empresa(conn)
    crear_codigo_pagos(tmp_path)

    filas_antes = conn.execute("SELECT COUNT(*) FROM plan_cuentas_empresa").fetchone()[0]

    obtener_parametrizacion_asistida_pagos(
        empresa_id=1,
        conn=conn,
        base_path=tmp_path,
    )

    filas_despues = conn.execute("SELECT COUNT(*) FROM plan_cuentas_empresa").fetchone()[0]

    assert filas_despues == filas_antes


def test_ignora_cuentas_inactivas(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE plan_cuentas_empresa (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER,
            codigo TEXT,
            nombre TEXT,
            uso_operativo TEXT,
            activa INTEGER
        );

        INSERT INTO plan_cuentas_empresa
            (empresa_id, codigo, nombre, uso_operativo, activa)
        VALUES
            (1, '2.1.01', 'Proveedores', 'proveedores', 0),
            (1, '1.3.09', 'Anticipos a proveedores', 'anticipos_proveedores', 0);
        """
    )
    crear_codigo_pagos(tmp_path)

    resultado = obtener_parametrizacion_asistida_pagos(
        empresa_id=1,
        conn=conn,
        base_path=tmp_path,
    )

    assert resultado["cuentas_plan_detectadas"] == 0
    assert any(a["codigo"] == "PAGOS_PLAN_EMPRESA_NO_DETECTADO" for a in resultado["alertas"])
