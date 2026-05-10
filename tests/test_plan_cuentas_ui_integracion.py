from pathlib import Path


def test_configuracion_muestra_un_solo_plan_de_cuentas_unificado():
    texto = Path("modulos/configuracion.py").read_text(encoding="utf-8")

    assert "def mostrar_plan_cuentas" in texto
    assert "Plan de Cuentas" in texto
    assert "Plan Maestro FF actúa como base contable madre" in texto
    assert "cuentas de empresa son su adaptación operativa" in texto
    assert "Plan de Cuentas PRO" not in texto


def test_configuracion_no_crea_pestana_plan_maestro_separada():
    texto = Path("modulos/configuracion.py").read_text(encoding="utf-8")

    assert '"Plan Maestro FF"' not in texto
    assert '"Plan de Cuentas",' in texto


def test_configuracion_no_usa_st_title_en_modulo():
    texto = Path("modulos/configuracion.py").read_text(encoding="utf-8")
    assert "st.title(" not in texto


def test_configuracion_deja_uso_operativo_como_tecnico_avanzado():
    texto = Path("modulos/configuracion.py").read_text(encoding="utf-8")

    assert "Uso operativo técnico" in texto
    assert "no define la estructura contable" in texto
    assert "automatización, mapeos y plantillas" in texto




def test_configuracion_mantiene_adaptador_plan_simple_para_configuraciones():
    texto = Path("modulos/configuracion.py").read_text(encoding="utf-8")

    assert "def obtener_plan_simple" in texto
    assert "CREADA_DESDE_MODELO" in texto
    assert "VINCULADA_AL_MAESTRO" in texto
    assert "HEREDADA_SIN_VINCULO" in texto
    assert "CATALOGO_HEREDADO" in texto


def test_configuracion_permite_crear_cuenta_empresa_desde_modelo():
    texto = Path("modulos/configuracion.py").read_text(encoding="utf-8")

    assert "Crear cuenta de empresa desde modelo" in texto
    assert "crear_cuenta_empresa_desde_modelo" in texto
    assert "Esta acción no modifica el Plan Maestro" in texto


def test_configuracion_mueve_uso_tecnico_y_compatibilidad_a_avanzado():
    texto = Path("modulos/configuracion.py").read_text(encoding="utf-8")

    assert '"🧰 Avanzado"' in texto
    assert '"⚙️ Uso técnico"' not in texto
    assert '"🧰 Compatibilidad"' not in texto
    assert "Uso operativo técnico y mapeos" in texto
    assert "Compatibilidad temporal" in texto



def test_configuracion_muestra_cuentas_heredadas_como_revision_no_definitivas():
    texto = Path("modulos/configuracion.py").read_text(encoding="utf-8")

    assert "Heredadas / revisar" in texto
    assert "HEREDADA_SIN_VINCULO" in texto
    assert "HEREDADA_MISMO_CODIGO_PENDIENTE" in texto
    assert "CREADA_DESDE_MODELO" in texto
    assert "Las cuentas heredadas no son el destino final" in texto


def test_configuracion_obtener_plan_simple_prioriza_cuentas_nuevas():
    texto = Path("modulos/configuracion.py").read_text(encoding="utf-8")

    assert "filas_nuevas if filas_nuevas else filas_heredadas" in texto
    assert "cuentas creadas desde modelos" in texto
    assert "cuentas heredadas, solo si todavía no existen cuentas nuevas" in texto
