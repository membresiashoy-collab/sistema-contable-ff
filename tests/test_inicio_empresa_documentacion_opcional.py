import pytest

from database import conectar
from services import inicio_empresa_service as s


def _primer_empresa_id():
    conn = conectar()
    try:
        fila = conn.execute("SELECT id FROM empresas ORDER BY id LIMIT 1").fetchone()
        return int(fila[0]) if fila else None
    finally:
        conn.close()


def test_asegurar_estructura_inicio_empresa_crea_tablas_opcionales():
    s.asegurar_estructura_inicio_empresa()

    conn = conectar()
    try:
        tablas = {
            fila[0]
            for fila in conn.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                """
            ).fetchall()
        }
    finally:
        conn.close()

    assert "empresa_documentacion_respaldo" in tablas
    assert "empresa_inicio_eventos" in tablas
    assert "inicio_empresa_onboarding" in tablas


def test_documentacion_respaldo_opcional_no_bloquea_listado():
    s.asegurar_estructura_inicio_empresa()

    empresa_id = _primer_empresa_id()
    if empresa_id is None:
        pytest.skip("No hay empresas cargadas para probar documentación opcional.")

    df = s.documentacion_respaldo_listar(empresa_id)

    assert list(df.columns) == [
        "id",
        "empresa_id",
        "tipo_documento",
        "descripcion",
        "referencia",
        "fecha_documento",
        "archivo_nombre",
        "archivo_ruta",
        "observaciones",
        "estado",
        "usuario_creacion",
        "fecha_creacion",
        "usuario_anulacion",
        "fecha_anulacion",
        "motivo_anulacion",
    ]


def test_perfil_inicio_empresa_no_falla_por_documentacion_ni_eventos():
    s.asegurar_estructura_inicio_empresa()

    empresa_id = _primer_empresa_id()
    if empresa_id is None:
        pytest.skip("No hay empresas cargadas para probar perfil de inicio.")

    perfil = s.obtener_perfil_inicio_empresa(empresa_id)

    assert perfil["empresa_id"] == empresa_id
    assert "tipo_sujeto" in perfil
    assert "tipo_sujeto_etiqueta" in perfil
