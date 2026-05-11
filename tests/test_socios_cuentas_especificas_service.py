import sqlite3

import pandas as pd

import services.socios_cuentas_especificas_service as service


def _conn_base():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE socios_empresa (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER NOT NULL DEFAULT 1,
            nombre TEXT NOT NULL,
            cuit TEXT,
            tipo_socio TEXT DEFAULT 'SOCIO',
            porcentaje_participacion REAL DEFAULT 0,
            estado TEXT DEFAULT 'ACTIVO',
            cuenta_particular_habilitada INTEGER,
            cuenta_particular_codigo TEXT,
            cuenta_particular_nombre TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE plan_cuentas_maestro (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT,
            nombre TEXT,
            codigo_madre TEXT,
            nivel INTEGER DEFAULT 1,
            imputable INTEGER DEFAULT 1,
            es_cuenta_modelo INTEGER DEFAULT 0,
            permite_copiar_modelo INTEGER DEFAULT 0,
            uso_operativo_sistema TEXT,
            rubro TEXT,
            cuenta TEXT,
            subcuenta TEXT,
            observaciones TEXT,
            estado TEXT DEFAULT 'ACTIVA'
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE plan_cuentas_empresa (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER NOT NULL DEFAULT 1,
            cuenta_maestro_id INTEGER,
            codigo TEXT,
            nombre TEXT,
            codigo_madre TEXT,
            nivel INTEGER DEFAULT 1,
            imputable INTEGER DEFAULT 1,
            estado TEXT DEFAULT 'ACTIVA',
            es_cuenta_modelo INTEGER DEFAULT 0,
            es_cuenta_especifica_empresa INTEGER DEFAULT 0,
            cuenta_modelo_origen_id INTEGER,
            uso_operativo_sistema TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO socios_empresa (empresa_id, nombre, cuit, estado)
        VALUES (1, 'Socio Uno', '20-11111111-1', 'ACTIVO')
        """
    )
    conn.commit()
    return conn


def test_asegura_estructura_crea_tablas_propias():
    conn = _conn_base()
    service.asegurar_estructura_socios_cuentas_especificas(conn)
    tablas = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert "socios_cuentas_especificas" in tablas
    assert "socios_cuentas_especificas_eventos" in tablas


def test_estado_muestra_modelo_no_habilitado_si_plan_maestro_no_permite_copia():
    conn = _conn_base()
    conn.execute(
        """
        INSERT INTO plan_cuentas_maestro
        (codigo, nombre, codigo_madre, nivel, imputable, es_cuenta_modelo, permite_copiar_modelo, estado)
        VALUES ('1.1.40.25', 'Socio X Cuenta Particular', '1.1.40.00', 4, 0, 0, 0, 'ACTIVA')
        """
    )
    conn.commit()

    df = service.obtener_estado_preparacion_socios(empresa_id=1, conn=conn)
    fila = df[df["tipo_cuenta"] == "CUENTA_PARTICULAR_SOCIO"].iloc[0]

    assert fila["estado_preparacion"] == "MODELO_NO_HABILITADO"
    assert fila["modelo_permite_copia"] == 0


def test_crear_bloquea_si_modelo_no_es_copiable():
    conn = _conn_base()
    conn.execute(
        """
        INSERT INTO plan_cuentas_maestro
        (id, codigo, nombre, codigo_madre, nivel, imputable, es_cuenta_modelo, permite_copiar_modelo, estado)
        VALUES (10, '1.1.40.25', 'Socio X Cuenta Particular', '1.1.40.00', 4, 0, 0, 0, 'ACTIVA')
        """
    )
    conn.commit()

    resultado = service.crear_cuenta_especifica_socio(
        empresa_id=1,
        socio_id=1,
        tipo_cuenta="CUENTA_PARTICULAR_SOCIO",
        cuenta_modelo_id=10,
        motivo="Preparar cuenta específica",
        usuario="tester",
        conn=conn,
    )

    assert resultado["ok"] is False
    assert "no está habilitada como modelo copiable" in resultado["errores"][0]


def test_vincular_cuenta_empresa_existente_crea_vinculo_y_evento():
    conn = _conn_base()
    conn.execute(
        """
        INSERT INTO plan_cuentas_empresa
        (empresa_id, cuenta_maestro_id, codigo, nombre, estado, imputable)
        VALUES (1, 10, '1.1.40.25.0001', 'Cuenta particular - Socio Uno', 'ACTIVA', 1)
        """
    )
    conn.commit()

    resultado = service.vincular_cuenta_empresa_existente_socio(
        empresa_id=1,
        socio_id=1,
        tipo_cuenta="CUENTA_PARTICULAR_SOCIO",
        cuenta_empresa_id=1,
        motivo="Vinculación inicial",
        usuario="tester",
        conn=conn,
    )

    assert resultado["ok"] is True
    assert resultado["codigo"] == "1.1.40.25.0001"

    vinculos = service.listar_cuentas_especificas_socios(empresa_id=1, conn=conn)
    assert len(vinculos) == 1
    assert vinculos.iloc[0]["origen"] == "VINCULADA_EXISTENTE"

    eventos = service.listar_eventos_cuentas_especificas_socios(empresa_id=1, conn=conn)
    assert len(eventos) == 1
    assert eventos.iloc[0]["evento"] == "CUENTA_SOCIO_VINCULADA_EXISTENTE"


def test_crear_desde_modelo_copiable_vincula_resultado(monkeypatch):
    conn = _conn_base()
    conn.execute(
        """
        INSERT INTO plan_cuentas_maestro
        (id, codigo, nombre, codigo_madre, nivel, imputable, es_cuenta_modelo, permite_copiar_modelo, estado)
        VALUES (20, '1.1.40.25', 'Socio X Cuenta Particular', '1.1.40.00', 4, 0, 1, 1, 'ACTIVA')
        """
    )
    conn.commit()

    def fake_crear_cuenta_empresa_desde_modelo(**kwargs):
        conn_local = kwargs["conn"]
        conn_local.execute(
            """
            INSERT INTO plan_cuentas_empresa
            (empresa_id, cuenta_maestro_id, codigo, nombre, estado, imputable, es_cuenta_especifica_empresa)
            VALUES (?, ?, ?, ?, 'ACTIVA', 1, 1)
            """,
            (
                kwargs["empresa_id"],
                kwargs["cuenta_maestro_id"],
                kwargs["codigo_nuevo"],
                kwargs["nombre_nuevo"],
            ),
        )
        return {
            "ok": True,
            "cuenta_empresa_id": int(conn_local.execute("SELECT last_insert_rowid()").fetchone()[0]),
            "codigo": kwargs["codigo_nuevo"],
            "nombre": kwargs["nombre_nuevo"],
            "cuenta_maestro_id": kwargs["cuenta_maestro_id"],
        }

    monkeypatch.setattr(service, "crear_cuenta_empresa_desde_modelo", fake_crear_cuenta_empresa_desde_modelo)

    resultado = service.crear_cuenta_especifica_socio(
        empresa_id=1,
        socio_id=1,
        tipo_cuenta="CUENTA_PARTICULAR_SOCIO",
        cuenta_modelo_id=20,
        motivo="Crear desde modelo copiable",
        usuario="tester",
        conn=conn,
    )

    assert resultado["ok"] is True
    assert resultado["codigo"].startswith("1.1.40.25.")

    vinculos = service.listar_cuentas_especificas_socios(empresa_id=1, conn=conn)
    assert len(vinculos) == 1
    assert vinculos.iloc[0]["origen"] == "CREADA_DESDE_MODELO"
    assert vinculos.iloc[0]["cuenta_modelo_id"] == 20


def test_anular_vinculo_no_borra_cuenta_empresa():
    conn = _conn_base()
    conn.execute(
        """
        INSERT INTO plan_cuentas_empresa
        (empresa_id, cuenta_maestro_id, codigo, nombre, estado, imputable)
        VALUES (1, 10, '1.1.40.25.0001', 'Cuenta particular - Socio Uno', 'ACTIVA', 1)
        """
    )
    conn.commit()
    creado = service.vincular_cuenta_empresa_existente_socio(
        empresa_id=1,
        socio_id=1,
        tipo_cuenta="CUENTA_PARTICULAR_SOCIO",
        cuenta_empresa_id=1,
        motivo="Vinculación inicial",
        usuario="tester",
        conn=conn,
    )

    resultado = service.anular_vinculo_cuenta_socio(
        empresa_id=1,
        vinculo_id=creado["vinculo_id"],
        motivo="Error de vinculación",
        usuario="tester",
        conn=conn,
    )

    assert resultado["ok"] is True
    assert conn.execute("SELECT estado FROM plan_cuentas_empresa WHERE id = 1").fetchone()[0] == "ACTIVA"
    assert conn.execute("SELECT estado FROM socios_cuentas_especificas WHERE id = ?", (creado["vinculo_id"],)).fetchone()[0] == "ANULADA"