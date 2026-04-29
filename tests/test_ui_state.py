from core.ui_state import (
    key_modulo,
    limpiar_estado_visual_temporal,
    normalizar_nombre_modulo,
    preparar_cambio_modulo,
)


def test_normalizar_nombre_modulo():
    assert normalizar_nombre_modulo("Banco / Caja") == "banco_caja"
    assert normalizar_nombre_modulo("Estado de Cargas") == "estado_de_cargas"
    assert normalizar_nombre_modulo("Cobranzas") == "cobranzas"


def test_key_modulo_genera_clave_aislada():
    assert key_modulo("Cobranzas", "cliente select") == "cobranzas__cliente_select"
    assert key_modulo("Banco / Caja", "archivo uploader") == "banco_caja__archivo_uploader"


def test_limpiar_estado_visual_temporal_conserva_claves_persistentes():
    estado = {
        "autenticado": True,
        "usuario": {"id": 1},
        "permisos": {"ADMIN"},
        "empresa_id": 1,
        "empresa_nombre": "Empresa Demo",
        "session_token": "abc",
        "menu_actual": "Ventas",
        "ui_modulo_activo": "Ventas",
        "radio_menu_principal": "Ventas",
        "selector_empresa_activa": "Empresa Demo",
        "ventas_tab_activa": "Resumen",
        "banco_ultimo_resultado_importacion": {"x": 1},
        "confirmar_limpiar_diario": True,
        "_streamlit_interno": "no borrar",
    }

    eliminadas = limpiar_estado_visual_temporal(estado)

    assert "ventas_tab_activa" in eliminadas
    assert "banco_ultimo_resultado_importacion" in eliminadas
    assert "confirmar_limpiar_diario" in eliminadas

    assert estado["autenticado"] is True
    assert estado["usuario"] == {"id": 1}
    assert estado["empresa_id"] == 1
    assert estado["empresa_nombre"] == "Empresa Demo"
    assert estado["session_token"] == "abc"
    assert estado["radio_menu_principal"] == "Ventas"
    assert estado["_streamlit_interno"] == "no borrar"


def test_preparar_cambio_modulo_primer_render_no_limpia():
    estado = {
        "menu_actual": "Ventas",
        "usuario": {"id": 1},
        "empresa_id": 1,
        "ventas_estado": "x",
    }

    cambio = preparar_cambio_modulo(estado, "Ventas")

    assert cambio is False
    assert estado["ui_modulo_activo"] == "Ventas"
    assert estado["menu_actual"] == "Ventas"
    assert estado["ventas_estado"] == "x"


def test_preparar_cambio_modulo_limpia_y_pide_rerun():
    estado = {
        "autenticado": True,
        "usuario": {"id": 1},
        "permisos": {"ADMIN"},
        "empresa_id": 1,
        "empresa_nombre": "Empresa Demo",
        "session_token": "abc",
        "menu_actual": "Ventas",
        "ui_modulo_activo": "Ventas",
        "radio_menu_principal": "Banco / Caja",
        "ventas_estado": "quedo viejo",
        "banco_ultimo_resultado_importacion": {"x": 1},
    }

    cambio = preparar_cambio_modulo(estado, "Banco / Caja")

    assert cambio is True
    assert estado["ui_modulo_anterior"] == "Ventas"
    assert estado["ui_modulo_activo"] == "Banco / Caja"
    assert estado["menu_actual"] == "Banco / Caja"
    assert "ventas_estado" not in estado
    assert "banco_ultimo_resultado_importacion" not in estado

    assert estado["usuario"] == {"id": 1}
    assert estado["empresa_id"] == 1
    assert estado["session_token"] == "abc"
    assert estado["radio_menu_principal"] == "Banco / Caja"

    assert estado["ui_limpieza_ultima"]["desde"] == "Ventas"
    assert estado["ui_limpieza_ultima"]["hacia"] == "Banco / Caja"
    assert estado["ui_limpieza_ultima"]["cantidad"] >= 2