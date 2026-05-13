import sqlite3
from pathlib import Path

from services.pagos_diagnostico_service import diagnosticar_pagos


def crear_schema_base(conn):
    conn.executescript(
        """
        CREATE TABLE pagos (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER,
            fecha_pago TEXT,
            numero_orden_pago TEXT,
            proveedor TEXT,
            cuit TEXT,
            importe_pagado REAL,
            importe_retenciones REAL,
            importe_total_aplicado REAL,
            medio_pago TEXT,
            cuenta_tesoreria_id INTEGER,
            tesoreria_operacion_id INTEGER,
            asiento_id INTEGER,
            estado TEXT,
            motivo_anulacion TEXT
        );

        CREATE TABLE pagos_imputaciones (
            id INTEGER PRIMARY KEY,
            pago_id INTEGER,
            cuenta_corriente_id INTEGER,
            tipo TEXT,
            numero TEXT,
            importe_imputado REAL
        );

        CREATE TABLE pagos_retenciones (
            id INTEGER PRIMARY KEY,
            pago_id INTEGER,
            tipo_retencion TEXT,
            descripcion TEXT,
            importe REAL,
            cuenta_contable_nombre TEXT
        );

        CREATE TABLE pagos_auditoria (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER,
            pago_id INTEGER,
            accion TEXT,
            detalle TEXT
        );

        CREATE TABLE cuenta_corriente_proveedores (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER,
            proveedor TEXT,
            cuit TEXT,
            tipo TEXT,
            numero TEXT,
            debe REAL,
            haber REAL,
            saldo REAL,
            origen TEXT,
            origen_id INTEGER
        );

        CREATE TABLE tesoreria_operaciones (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER,
            fecha TEXT,
            tipo_operacion TEXT,
            tercero_tipo TEXT,
            tercero_nombre TEXT,
            importe REAL,
            estado TEXT,
            origen TEXT,
            origen_id INTEGER
        );

        CREATE TABLE tesoreria_operaciones_componentes (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER,
            operacion_id INTEGER,
            tipo_componente TEXT,
            importe REAL
        );

        CREATE TABLE caja_movimientos (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER,
            referencia TEXT,
            importe REAL,
            estado TEXT
        );

        CREATE TABLE libro_diario (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER,
            fecha TEXT,
            cuenta TEXT,
            debe REAL,
            haber REAL,
            descripcion TEXT,
            origen TEXT,
            origen_id INTEGER
        );
        """
    )


def crear_codigo_pagos(tmp_path: Path, contenido_service: str = "", contenido_modulo: str = ""):
    (tmp_path / "services").mkdir()
    (tmp_path / "modulos").mkdir()
    (tmp_path / "services" / "pagos_service.py").write_text(contenido_service, encoding="utf-8")
    (tmp_path / "modulos" / "pagos.py").write_text(contenido_modulo, encoding="utf-8")


def test_diagnostico_no_rompe_sin_conexion(tmp_path):
    crear_codigo_pagos(tmp_path)

    resultado = diagnosticar_pagos(empresa_id=1, conn=None, base_path=tmp_path)

    assert resultado["modulo"] == "Pagos PRO v1"
    assert resultado["estado"] in {"CRITICO", "REQUIERE_REVISION", "REQUIERE_PARAMETRIZACION", "OK"}
    assert resultado["estructura"]["conexion_disponible"] is False
    assert any(a["codigo"] == "PAGOS_DIAGNOSTICO_SIN_CONEXION_DB" for a in resultado["alertas"])


def test_detecta_estructura_base_de_pagos(tmp_path):
    conn = sqlite3.connect(":memory:")
    crear_schema_base(conn)
    crear_codigo_pagos(
        tmp_path,
        contenido_service="""
CUENTA_PROVEEDORES = "PROVEEDORES"
CUENTAS_RETENCIONES_DEFAULT = {"IVA": "RETENCIONES IVA A DEPOSITAR"}
cur.execute("INSERT INTO pagos VALUES (...)")
cur.execute("INSERT INTO pagos_imputaciones VALUES (...)")
cur.execute("INSERT INTO pagos_retenciones VALUES (...)")
cur.execute("INSERT INTO cuenta_corriente_proveedores VALUES (...)")
cur.execute("INSERT INTO tesoreria_operaciones VALUES (...)")
cur.execute("INSERT INTO libro_diario VALUES (...)")
def anular_pago(): pass
numero_orden_pago = "OP-00000001"
""",
    )

    resultado = diagnosticar_pagos(empresa_id=1, conn=conn, base_path=tmp_path)

    assert resultado["estructura"]["conexion_disponible"] is True
    assert resultado["estructura"]["tablas_relevantes"]["pagos"]["existe"] is True
    assert resultado["estructura"]["tablas_relevantes"]["pagos_retenciones"]["existe"] is True
    assert resultado["resumen"]["casos_requeridos"] >= 10


def test_detecta_libro_diario_directo_y_hardcodes(tmp_path):
    conn = sqlite3.connect(":memory:")
    crear_schema_base(conn)
    crear_codigo_pagos(
        tmp_path,
        contenido_service="""
CUENTA_PROVEEDORES = "PROVEEDORES"
CUENTAS_RETENCIONES_DEFAULT = {"IIBB": "RETENCIONES IIBB A DEPOSITAR"}
cur.execute("INSERT INTO libro_diario VALUES (...)")
""",
    )

    resultado = diagnosticar_pagos(empresa_id=1, conn=conn, base_path=tmp_path)
    codigos = {alerta["codigo"] for alerta in resultado["alertas"]}

    assert "PAGOS_GENERA_LIBRO_DIARIO_DIRECTO" in codigos
    assert "PAGOS_CUENTAS_CONTABLES_HARDCODEADAS" in codigos


def test_detecta_anticipos_incompletos_si_no_aparecen_en_codigo(tmp_path):
    conn = sqlite3.connect(":memory:")
    crear_schema_base(conn)
    crear_codigo_pagos(tmp_path, contenido_service="cur.execute('INSERT INTO pagos VALUES (...)')")

    resultado = diagnosticar_pagos(empresa_id=1, conn=conn, base_path=tmp_path)

    caso_anticipo = next(c for c in resultado["casos"] if c["codigo"] == "ANTICIPO_A_PROVEEDOR")
    assert caso_anticipo["estado"] == "INCOMPLETO"
    assert any(a["codigo"] == "PAGOS_ANTICIPOS_PROVEEDORES_NO_DETECTADOS" for a in resultado["alertas"])


def test_detecta_anticipos_a_revisar_si_aparecen_en_codigo(tmp_path):
    conn = sqlite3.connect(":memory:")
    crear_schema_base(conn)
    crear_codigo_pagos(
        tmp_path,
        contenido_service="""
# anticipo a proveedor pendiente de aplicar
def registrar_anticipo_proveedor(): pass
cur.execute("INSERT INTO pagos_imputaciones VALUES (...)")
""",
    )

    resultado = diagnosticar_pagos(empresa_id=1, conn=conn, base_path=tmp_path)

    caso_anticipo = next(c for c in resultado["casos"] if c["codigo"] == "ANTICIPO_A_PROVEEDOR")
    assert caso_anticipo["estado"] == "A_REVISAR"


def test_detecta_falta_de_bandeja_si_hay_libro_directo(tmp_path):
    conn = sqlite3.connect(":memory:")
    crear_schema_base(conn)
    crear_codigo_pagos(
        tmp_path,
        contenido_service="""
cur.execute("INSERT INTO libro_diario VALUES (...)")
""",
    )

    resultado = diagnosticar_pagos(empresa_id=1, conn=conn, base_path=tmp_path)

    caso = next(c for c in resultado["casos"] if c["codigo"] == "PROPUESTA_ASIENTO_FUTURA")
    assert caso["estado"] == "A_REVISAR"
    assert any(a["codigo"] == "PAGOS_SIN_BANDEJA_ASIENTOS" for a in resultado["alertas"])


def test_detecta_ui_que_crea_caja_banco_basicos(tmp_path):
    conn = sqlite3.connect(":memory:")
    crear_schema_base(conn)
    crear_codigo_pagos(
        tmp_path,
        contenido_modulo="""
st.button("Crear Caja principal para pagos")
st.button("Crear Banco principal para pagos")
""",
    )

    resultado = diagnosticar_pagos(empresa_id=1, conn=conn, base_path=tmp_path)

    assert any(a["codigo"] == "PAGOS_UI_CREA_CUENTAS_TESORERIA_BASICAS" for a in resultado["alertas"])


def test_servicio_es_de_solo_lectura_sobre_la_base(tmp_path):
    conn = sqlite3.connect(":memory:")
    crear_schema_base(conn)
    crear_codigo_pagos(tmp_path)

    tablas_antes = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'").fetchone()[0]
    filas_pagos_antes = conn.execute("SELECT COUNT(*) FROM pagos").fetchone()[0]

    diagnosticar_pagos(empresa_id=1, conn=conn, base_path=tmp_path)

    tablas_despues = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'").fetchone()[0]
    filas_pagos_despues = conn.execute("SELECT COUNT(*) FROM pagos").fetchone()[0]

    assert tablas_despues == tablas_antes
    assert filas_pagos_despues == filas_pagos_antes