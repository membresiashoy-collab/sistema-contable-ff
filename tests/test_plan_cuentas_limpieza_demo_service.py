import sqlite3

import pytest

from services.plan_cuentas_limpieza_demo_service import (
    CONFIRMACION_LIMPIEZA_DEMO,
    limpiar_plan_cuentas_demo_desde_maestro,
    previsualizar_limpieza_plan_cuentas_demo,
)


def _crear_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    conn.executescript(
        """
        CREATE TABLE plan_cuentas_maestro (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT NOT NULL,
            nombre TEXT NOT NULL,
            codigo_madre TEXT,
            nivel INTEGER NOT NULL DEFAULT 1,
            orden INTEGER NOT NULL DEFAULT 0,
            imputable INTEGER NOT NULL DEFAULT 0,
            requiere_auxiliar INTEGER NOT NULL DEFAULT 0,
            tipo_auxiliar TEXT,
            ajustable INTEGER NOT NULL DEFAULT 0,
            estado TEXT NOT NULL DEFAULT 'ACTIVA',
            es_cuenta_modelo INTEGER NOT NULL DEFAULT 0,
            uso_operativo_sistema TEXT,
            vigencia_desde TEXT,
            vigencia_hasta TEXT
        );

        CREATE TABLE plan_cuentas_empresa (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER NOT NULL DEFAULT 1,
            cuenta_maestro_id INTEGER,
            codigo TEXT NOT NULL,
            nombre TEXT NOT NULL,
            codigo_madre TEXT,
            nivel INTEGER NOT NULL DEFAULT 1,
            orden INTEGER NOT NULL DEFAULT 0,
            imputable INTEGER NOT NULL DEFAULT 0,
            requiere_auxiliar INTEGER NOT NULL DEFAULT 0,
            tipo_auxiliar TEXT,
            ajustable INTEGER NOT NULL DEFAULT 0,
            estado TEXT NOT NULL DEFAULT 'ACTIVA',
            es_cuenta_modelo INTEGER NOT NULL DEFAULT 0,
            es_cuenta_especifica_empresa INTEGER NOT NULL DEFAULT 0,
            cuenta_modelo_origen_id INTEGER,
            banco_nombre TEXT,
            numero_cuenta TEXT,
            moneda TEXT,
            alias TEXT,
            cbu TEXT,
            uso_operativo_sistema TEXT,
            vigencia_desde TEXT,
            vigencia_hasta TEXT,
            motivo_estado TEXT,
            usuario_ultima_modificacion TEXT,
            fecha_ultima_modificacion TEXT,
            creado_en TEXT DEFAULT CURRENT_TIMESTAMP,
            actualizado_en TEXT
        );

        CREATE TABLE mapeos_contables_empresa (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER NOT NULL DEFAULT 1,
            uso_operativo_id INTEGER NOT NULL,
            cuenta_empresa_id INTEGER NOT NULL,
            modulo TEXT,
            evento_operativo TEXT,
            estado TEXT NOT NULL DEFAULT 'ACTIVO'
        );

        CREATE TABLE categorias_compra_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER NOT NULL DEFAULT 1,
            categoria TEXT NOT NULL,
            cuenta_sugerida_id INTEGER,
            cuenta_contrapartida_sugerida_id INTEGER,
            motivo_estado TEXT,
            usuario_ultima_modificacion TEXT,
            fecha_ultima_modificacion TEXT,
            actualizado_en TEXT
        );

        CREATE TABLE conceptos_fiscales_compra_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER NOT NULL DEFAULT 1,
            concepto TEXT NOT NULL,
            cuenta_sugerida_id INTEGER,
            motivo_estado TEXT,
            usuario_ultima_modificacion TEXT,
            fecha_ultima_modificacion TEXT,
            actualizado_en TEXT
        );

        CREATE TABLE auditoria_cambios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            usuario_id INTEGER,
            empresa_id INTEGER,
            modulo TEXT,
            accion TEXT,
            entidad TEXT,
            entidad_id TEXT,
            valor_anterior TEXT,
            valor_nuevo TEXT,
            motivo TEXT
        );
        """
    )

    conn.executemany(
        """
        INSERT INTO plan_cuentas_maestro
            (codigo, nombre, codigo_madre, nivel, orden, imputable, estado, es_cuenta_modelo, uso_operativo_sistema)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("1", "ACTIVO", None, 1, 1, 0, "ACTIVA", 0, None),
            ("1.1", "CAJA Y BANCOS", "1", 2, 2, 0, "ACTIVA", 0, None),
            ("1.1.01", "CAJA", "1.1", 3, 3, 1, "ACTIVA", 1, "CAJA"),
            ("9.9.99", "CUENTA ANULADA MAESTRO", None, 1, 99, 1, "ANULADA", 0, None),
        ],
    )

    conn.executemany(
        """
        INSERT INTO plan_cuentas_empresa
            (empresa_id, cuenta_maestro_id, codigo, nombre, codigo_madre, nivel, orden, imputable, estado)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (1, None, "100", "Cuenta heredada demo", None, 1, 1, 1, "ACTIVA"),
            (1, None, "101", "Otra cuenta heredada demo", None, 1, 2, 1, "ACTIVA"),
        ],
    )

    cuenta_ids = [
        int(row["id"])
        for row in conn.execute(
            """
            SELECT id
            FROM plan_cuentas_empresa
            WHERE empresa_id = 1
            ORDER BY id
            """
        ).fetchall()
    ]

    conn.execute(
        """
        INSERT INTO mapeos_contables_empresa
            (empresa_id, uso_operativo_id, cuenta_empresa_id, modulo, evento_operativo, estado)
        VALUES (1, 10, ?, 'TESORERIA', 'TEST', 'ACTIVO')
        """,
        (cuenta_ids[0],),
    )

    conn.execute(
        """
        INSERT INTO categorias_compra_config
            (empresa_id, categoria, cuenta_sugerida_id, cuenta_contrapartida_sugerida_id)
        VALUES (1, 'GASTOS DEMO', ?, ?)
        """,
        (cuenta_ids[0], cuenta_ids[1]),
    )

    conn.execute(
        """
        INSERT INTO conceptos_fiscales_compra_config
            (empresa_id, concepto, cuenta_sugerida_id)
        VALUES (1, 'IVA DEMO', ?)
        """,
        (cuenta_ids[0],),
    )

    conn.commit()
    return conn


def test_previsualiza_limpieza_demo_sin_modificar_datos():
    conn = _crear_conn()

    preview = previsualizar_limpieza_plan_cuentas_demo(empresa_id=1, conn=conn)

    assert preview["ok"] is True
    assert preview["total_plan_empresa_actual"] == 2
    assert preview["total_plan_maestro_activo"] == 3
    assert preview["cuentas_no_vinculadas"] == 2
    assert preview["confirmacion_requerida"] == CONFIRMACION_LIMPIEZA_DEMO

    total_empresa = conn.execute("SELECT COUNT(*) FROM plan_cuentas_empresa").fetchone()[0]
    assert total_empresa == 2


def test_limpieza_demo_exige_confirmacion_fuerte():
    conn = _crear_conn()

    with pytest.raises(ValueError, match="Confirmación inválida"):
        limpiar_plan_cuentas_demo_desde_maestro(
            empresa_id=1,
            confirmacion="SI",
            usuario="tester",
            conn=conn,
        )


def test_limpieza_demo_exige_motivo():
    conn = _crear_conn()

    with pytest.raises(ValueError, match="motivo es obligatorio"):
        limpiar_plan_cuentas_demo_desde_maestro(
            empresa_id=1,
            confirmacion=CONFIRMACION_LIMPIEZA_DEMO,
            usuario="tester",
            motivo="",
            conn=conn,
        )


def test_limpieza_demo_borra_plan_empresa_y_reconstruye_desde_maestro():
    conn = _crear_conn()

    resultado = limpiar_plan_cuentas_demo_desde_maestro(
        empresa_id=1,
        confirmacion=CONFIRMACION_LIMPIEZA_DEMO,
        usuario="tester",
        motivo="Limpieza demo test",
        conn=conn,
    )

    assert resultado["ok"] is True
    assert resultado["modo"] == "DEMO_RADICAL"
    assert resultado["cuentas_antes"] == 2
    assert resultado["cuentas_eliminadas"] == 2
    assert resultado["cuentas_reconstruidas"] == 3

    cuentas = conn.execute(
        """
        SELECT codigo, nombre, cuenta_maestro_id, estado
        FROM plan_cuentas_empresa
        WHERE empresa_id = 1
        ORDER BY codigo
        """
    ).fetchall()

    assert [row["codigo"] for row in cuentas] == ["1", "1.1", "1.1.01"]
    assert all(row["cuenta_maestro_id"] is not None for row in cuentas)
    assert all(row["estado"] == "ACTIVA" for row in cuentas)


def test_limpieza_demo_limpia_referencias_dependientes():
    conn = _crear_conn()

    resultado = limpiar_plan_cuentas_demo_desde_maestro(
        empresa_id=1,
        confirmacion=CONFIRMACION_LIMPIEZA_DEMO,
        usuario="tester",
        motivo="Limpieza demo test",
        conn=conn,
    )

    assert resultado["mapeos_eliminados"] == 1
    assert resultado["categorias_cuenta_sugerida_limpiadas"] == 1
    assert resultado["categorias_contrapartida_limpiadas"] == 1
    assert resultado["conceptos_fiscales_limpiados"] == 1

    assert conn.execute("SELECT COUNT(*) FROM mapeos_contables_empresa").fetchone()[0] == 0

    categoria = conn.execute(
        """
        SELECT cuenta_sugerida_id, cuenta_contrapartida_sugerida_id, motivo_estado
        FROM categorias_compra_config
        WHERE empresa_id = 1
        """
    ).fetchone()

    assert categoria["cuenta_sugerida_id"] is None
    assert categoria["cuenta_contrapartida_sugerida_id"] is None
    assert categoria["motivo_estado"] == "Limpieza demo test"

    concepto = conn.execute(
        """
        SELECT cuenta_sugerida_id, motivo_estado
        FROM conceptos_fiscales_compra_config
        WHERE empresa_id = 1
        """
    ).fetchone()

    assert concepto["cuenta_sugerida_id"] is None
    assert concepto["motivo_estado"] == "Limpieza demo test"


def test_limpieza_demo_crea_backups_de_tablas_afectadas():
    conn = _crear_conn()

    resultado = limpiar_plan_cuentas_demo_desde_maestro(
        empresa_id=1,
        confirmacion=CONFIRMACION_LIMPIEZA_DEMO,
        usuario="tester",
        motivo="Limpieza demo test",
        crear_backup=True,
        conn=conn,
    )

    assert resultado["backups"]

    tablas_backup = {
        row["name"]
        for row in conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name LIKE 'backup_demo_%'
            """
        ).fetchall()
    }

    assert any(nombre.startswith("backup_demo_plan_cuentas_empresa_") for nombre in tablas_backup)
    assert any(nombre.startswith("backup_demo_mapeos_contables_empresa_") for nombre in tablas_backup)


def test_limpieza_demo_registra_auditoria():
    conn = _crear_conn()

    limpiar_plan_cuentas_demo_desde_maestro(
        empresa_id=1,
        confirmacion=CONFIRMACION_LIMPIEZA_DEMO,
        usuario="tester",
        motivo="Limpieza demo test",
        conn=conn,
    )

    auditoria = conn.execute(
        """
        SELECT modulo, accion, entidad, entidad_id, motivo
        FROM auditoria_cambios
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()

    assert auditoria is not None
    assert auditoria["modulo"] == "Plan de Cuentas"
    assert auditoria["accion"] == "LIMPIEZA_DEMO_PLAN_CUENTAS"
    assert auditoria["entidad"] == "plan_cuentas_empresa"
    assert auditoria["entidad_id"] == "1"
    assert auditoria["motivo"] == "Limpieza demo test"


def test_limpieza_demo_es_idempotente_en_estructura_resultante():
    conn = _crear_conn()

    limpiar_plan_cuentas_demo_desde_maestro(
        empresa_id=1,
        confirmacion=CONFIRMACION_LIMPIEZA_DEMO,
        usuario="tester",
        motivo="Primera limpieza demo",
        conn=conn,
    )

    limpiar_plan_cuentas_demo_desde_maestro(
        empresa_id=1,
        confirmacion=CONFIRMACION_LIMPIEZA_DEMO,
        usuario="tester",
        motivo="Segunda limpieza demo",
        conn=conn,
    )

    cuentas = conn.execute(
        """
        SELECT codigo, cuenta_maestro_id
        FROM plan_cuentas_empresa
        WHERE empresa_id = 1
        ORDER BY codigo
        """
    ).fetchall()

    assert [row["codigo"] for row in cuentas] == ["1", "1.1", "1.1.01"]
    assert all(row["cuenta_maestro_id"] is not None for row in cuentas)

def test_limpieza_demo_limpia_referencias_fk_genericas_a_plan_empresa():
    conn = _crear_conn()

    cuenta_id = conn.execute(
        """
        SELECT id
        FROM plan_cuentas_empresa
        WHERE empresa_id = 1
        ORDER BY id
        LIMIT 1
        """
    ).fetchone()["id"]

    conn.execute(
        """
        CREATE TABLE referencias_extra_demo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cuenta_empresa_id INTEGER REFERENCES plan_cuentas_empresa(id),
            detalle TEXT
        )
        """
    )

    conn.execute(
        """
        INSERT INTO referencias_extra_demo (cuenta_empresa_id, detalle)
        VALUES (?, 'referencia demo')
        """,
        (cuenta_id,),
    )

    conn.commit()

    resultado = limpiar_plan_cuentas_demo_desde_maestro(
        empresa_id=1,
        confirmacion=CONFIRMACION_LIMPIEZA_DEMO,
        usuario="tester",
        motivo="Limpieza demo test con FK genérica",
        conn=conn,
    )

    assert resultado["ok"] is True
    assert resultado["referencias_fk_genericas_limpiadas"] == 1

    referencia = conn.execute(
        """
        SELECT cuenta_empresa_id
        FROM referencias_extra_demo
        LIMIT 1
        """
    ).fetchone()

    assert referencia["cuenta_empresa_id"] is None
