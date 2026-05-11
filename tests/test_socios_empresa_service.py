import sqlite3

import pandas as pd
import pytest

import services.socios_empresa_service as servicio


def _crear_base_socios(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS socios_empresa (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER NOT NULL DEFAULT 1,
            nombre TEXT NOT NULL,
            cuit TEXT,
            tipo_socio TEXT NOT NULL DEFAULT 'SOCIO',
            porcentaje_participacion REAL NOT NULL DEFAULT 0,
            observaciones TEXT,
            estado TEXT NOT NULL DEFAULT 'ACTIVO',
            usuario_creacion TEXT,
            fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            usuario_actualizacion TEXT,
            fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            usuario_baja TEXT,
            fecha_baja TIMESTAMP,
            motivo_baja TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO socios_empresa
            (empresa_id, nombre, cuit, tipo_socio, porcentaje_participacion, estado)
        VALUES
            (1, 'Juan Socio', '20111111112', 'SOCIO', 50, 'ACTIVO'),
            (1, 'Ana Accionista', '27222222223', 'ACCIONISTA', 50, 'ACTIVO'),
            (1, 'Socio Baja', '20333333334', 'SOCIO', 0, 'INACTIVO')
        """
    )
    conn.commit()
    conn.close()


@pytest.fixture()
def db_socios(tmp_path, monkeypatch):
    db_path = tmp_path / "socios_pro.sqlite3"
    _crear_base_socios(db_path)

    def conectar_test():
        return sqlite3.connect(db_path)

    monkeypatch.setattr(servicio, "conectar", conectar_test)
    monkeypatch.setattr(servicio, "asegurar_estructura_inicio_societario_pro", lambda: None)
    return db_path


def test_asegurar_estructura_socios_pro_agrega_ficha_catalogo_y_eventos(db_socios):
    servicio.asegurar_estructura_socios_pro()

    conn = sqlite3.connect(db_socios)
    columnas = {fila[1] for fila in conn.execute("PRAGMA table_info(socios_empresa)").fetchall()}
    assert "rol_relacion" in columnas
    assert "cuenta_particular_habilitada" in columnas
    assert "cuenta_particular_codigo" in columnas
    assert "admite_prestamos" in columnas

    tablas = {
        fila[0]
        for fila in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "socios_empresa_ficha_eventos" in tablas
    assert "socios_conceptos_relacion" in tablas

    conceptos = pd.read_sql_query("SELECT codigo FROM socios_conceptos_relacion", conn)
    codigos = set(conceptos["codigo"])
    assert "CAPITAL_SUSCRIPTO" in codigos
    assert "INTEGRACION_CAPITAL" in codigos
    assert "PRESTAMO_SOCIO_EMPRESA" in codigos
    assert "RETIRO_SOCIO" in codigos
    assert "CUENTA_PARTICULAR_SOCIO" in codigos
    conn.close()


def test_actualizar_ficha_integral_prepara_cuenta_sin_movimientos(db_socios):
    servicio.asegurar_estructura_socios_pro()

    resultado = servicio.actualizar_ficha_integral_socio(
        socio_id=1,
        empresa_id=1,
        rol_relacion="SOCIO",
        condicion_fiscal="RESPONSABLE_INSCRIPTO",
        documento="DNI 11111111",
        email="socio@example.com",
        telefono="3880000000",
        domicilio="Calle 123",
        actividad_vinculada="Proveedor vinculado de servicios profesionales",
        proveedor_vinculado_referencia="Proveedor interno pendiente",
        cuenta_particular_habilitada=True,
        admite_prestamos=True,
        admite_retiros=True,
        admite_reintegros=True,
        admite_honorarios=True,
        admite_facturas_proveedor=True,
        observaciones_ficha="Ficha integral preparada.",
        usuario="tester",
    )

    assert resultado["ok"] is True

    ficha = servicio.obtener_ficha_socio(1, empresa_id=1)
    assert ficha["condicion_fiscal"] == "RESPONSABLE_INSCRIPTO"
    assert ficha["cuenta_particular_habilitada"] == 1
    assert ficha["cuenta_particular_codigo"] == "SOCIO-0001"
    assert "Cuenta particular" in ficha["cuenta_particular_nombre"]

    eventos = servicio.listar_eventos_ficha_socio(1, empresa_id=1)
    assert not eventos.empty
    assert "ACTUALIZACION_FICHA_INTEGRAL" in set(eventos["tipo_evento"])


def test_preparar_cuenta_particular_no_crea_asientos_ni_toca_banco_caja(db_socios):
    servicio.asegurar_estructura_socios_pro()

    resultado = servicio.preparar_cuenta_particular_socio(2, empresa_id=1, usuario="tester")

    assert resultado["ok"] is True
    assert resultado["cuenta_particular_codigo"] == "SOCIO-0002"

    conn = sqlite3.connect(db_socios)
    tablas = {
        fila[0]
        for fila in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "libro_diario" not in tablas
    assert "bancos_movimientos" not in tablas
    assert "caja_movimientos" not in tablas
    conn.close()


def test_no_permite_modificar_ficha_de_socio_dado_de_baja(db_socios):
    servicio.asegurar_estructura_socios_pro()

    resultado = servicio.actualizar_ficha_integral_socio(
        socio_id=3,
        empresa_id=1,
        rol_relacion="SOCIO",
        usuario="tester",
    )

    assert resultado["ok"] is False
    assert "dado de baja" in resultado["mensaje"]


def test_listar_fichas_respeta_incluir_bajas(db_socios):
    servicio.asegurar_estructura_socios_pro()

    activos = servicio.listar_fichas_socios_empresa(empresa_id=1, incluir_bajas=False)
    todos = servicio.listar_fichas_socios_empresa(empresa_id=1, incluir_bajas=True)

    assert len(activos) == 2
    assert len(todos) == 3