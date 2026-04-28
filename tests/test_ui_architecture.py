from pathlib import Path
import ast
import re


def leer_archivo(ruta):
    return Path(ruta).read_text(encoding="utf-8")


def test_modulos_no_deben_usar_st_title():
    """
    Regla de arquitectura UI:

    - El encabezado principal de cada módulo vive en main.py.
    - La composición visual reutilizable vive en core/ui.py.
    - Los archivos dentro de modulos/ no deben usar st.title().
    - Los módulos pueden usar st.subheader(), st.info(), st.tabs(), st.markdown(), etc.
    """

    errores = []

    for archivo in sorted(Path("modulos").glob("*.py")):
        if archivo.name == "__init__.py":
            continue

        contenido = archivo.read_text(encoding="utf-8")

        if re.search(r"\bst\.title\s*\(", contenido):
            errores.append(str(archivo))

    assert not errores, (
        "Los módulos no deben usar st.title(). "
        "El encabezado principal debe estar centralizado desde main.py/core.ui. "
        f"Archivos con st.title(): {errores}"
    )


def extraer_modulos_ui_desde_main():
    """
    Extrae el literal MODULOS_UI desde main.py usando AST.
    Así evitamos tests frágiles basados en el orden exacto del diccionario.
    """

    contenido = leer_archivo("main.py")
    arbol = ast.parse(contenido)

    for nodo in arbol.body:
        if isinstance(nodo, ast.Assign):
            for destino in nodo.targets:
                if isinstance(destino, ast.Name) and destino.id == "MODULOS_UI":
                    return ast.literal_eval(nodo.value)

    raise AssertionError("No se encontró MODULOS_UI en main.py.")


def test_main_contiene_configuracion_central_de_modulos():
    """
    main.py debe tener la configuración central de encabezados.
    Esto evita que cada módulo maneje su propio título.
    """

    contenido = leer_archivo("main.py")

    assert "MODULOS_UI" in contenido, "main.py debe definir MODULOS_UI."
    assert "def mostrar_encabezado_modulo" in contenido, (
        "main.py debe tener la función mostrar_encabezado_modulo()."
    )


def test_main_importa_capa_visual_desde_core_ui():
    """
    La UI visual reutilizable debe vivir en core/ui.py.
    main.py solo debe invocar esas funciones, no concentrar todo el CSS/HTML.
    """

    contenido = leer_archivo("main.py")

    assert "from core.ui import" in contenido, (
        "main.py debe importar la capa visual desde core.ui."
    )
    assert "aplicar_estilos_globales" in contenido, (
        "main.py debe aplicar estilos globales desde core.ui."
    )
    assert "mostrar_encabezado_modulo_visual" in contenido, (
        "main.py debe usar mostrar_encabezado_modulo_visual() para encabezados."
    )
    assert "mostrar_sidebar_marca" in contenido, (
        "main.py debe usar mostrar_sidebar_marca() para la identidad del menú lateral."
    )


def test_core_ui_contiene_html_controlado_y_estilos_globales():
    """
    El HTML/CSS controlado del sistema debe estar centralizado en core/ui.py.
    """

    contenido = leer_archivo("core/ui.py")

    assert "def aplicar_estilos_globales" in contenido, (
        "core/ui.py debe definir aplicar_estilos_globales()."
    )
    assert "def mostrar_encabezado_modulo_visual" in contenido, (
        "core/ui.py debe definir mostrar_encabezado_modulo_visual()."
    )
    assert "def mostrar_sidebar_marca" in contenido, (
        "core/ui.py debe definir mostrar_sidebar_marca()."
    )
    assert "st.markdown(" in contenido, (
        "core/ui.py debe renderizar componentes visuales con st.markdown()."
    )
    assert "unsafe_allow_html=True" in contenido, (
        "El HTML visual controlado debe declarar unsafe_allow_html=True en core/ui.py."
    )


def test_login_es_simple_y_solo_muestra_titulo_principal():
    """
    El login debe mantenerse simple:
    - mostrar solo el título principal del sistema,
    - no mostrar subtítulos redundantes.
    """

    contenido = leer_archivo("main.py")

    assert 'st.markdown("## Sistema Contable")' in contenido, (
        "El login debe mostrar solo el título principal 'Sistema Contable'."
    )
    assert "Ingreso al sistema" not in contenido, (
        "El login no debe mostrar el subtítulo 'Ingreso al sistema'."
    )
    assert "Usá tu usuario y contraseña para continuar." not in contenido, (
        "El login no debe mostrar texto redundante de ayuda."
    )


def test_main_tiene_todos_los_modulos_con_titulo_correcto():
    """
    Controla que cada menú tenga icono, título y descripción propios.

    Esto evita errores como:
    - Compras mostrando Ventas.
    - Banco / Caja mostrando otro módulo.
    - Contabilidad mostrando IVA.
    - Estado de Cargas mostrando otro encabezado.
    """

    modulos_ui = extraer_modulos_ui_desde_main()

    esperados = {
        "Ventas": {
            "icono": "📤",
            "titulo": "Ventas",
            "texto_descripcion": "Carga de ventas"
        },
        "Compras": {
            "icono": "📥",
            "titulo": "Compras",
            "texto_descripcion": "Carga de compras"
        },
        "Banco / Caja": {
            "icono": "🏦",
            "titulo": "Banco / Caja",
            "texto_descripcion": "Importación flexible de extractos bancarios"
        },
        "IVA": {
            "icono": "🧾",
            "titulo": "IVA",
            "texto_descripcion": "Control de posición mensual de IVA"
        },
        "Contabilidad": {
            "icono": "📚",
            "titulo": "Contabilidad",
            "texto_descripcion": "Libros y reportes contables"
        },
        "Estado de Cargas": {
            "icono": "📋",
            "titulo": "Estado de Cargas y Auditoría",
            "texto_descripcion": "Auditoría de archivos procesados"
        },
        "Configuración": {
            "icono": "⚙️",
            "titulo": "Configuración",
            "texto_descripcion": "Parámetros base del sistema"
        },
        "Seguridad": {
            "icono": "🔐",
            "titulo": "Seguridad",
            "texto_descripcion": "Usuarios, roles, permisos"
        },
    }

    for menu, datos in esperados.items():
        assert menu in modulos_ui, f"Falta el menú {menu} en MODULOS_UI."

        bloque = modulos_ui[menu]

        assert bloque.get("icono") == datos["icono"], (
            f"El menú {menu} debe tener icono {datos['icono']}."
        )
        assert bloque.get("titulo") == datos["titulo"], (
            f"El menú {menu} debe tener título {datos['titulo']}."
        )
        assert datos["texto_descripcion"] in bloque.get("descripcion", ""), (
            f"El menú {menu} debe tener una descripción propia."
        )


def test_main_no_debe_repetir_titulos_cruzados_en_modulos_ui():
    """
    Control específico contra errores de encabezado cruzado:
    cada módulo debe mostrar su propio título.
    """

    modulos_ui = extraer_modulos_ui_desde_main()

    assert modulos_ui["Ventas"]["titulo"] == "Ventas"
    assert modulos_ui["Compras"]["titulo"] == "Compras"
    assert modulos_ui["Banco / Caja"]["titulo"] == "Banco / Caja"
    assert modulos_ui["IVA"]["titulo"] == "IVA"
    assert modulos_ui["Contabilidad"]["titulo"] == "Contabilidad"
    assert modulos_ui["Estado de Cargas"]["titulo"] == "Estado de Cargas y Auditoría"
    assert modulos_ui["Configuración"]["titulo"] == "Configuración"
    assert modulos_ui["Seguridad"]["titulo"] == "Seguridad"

    assert modulos_ui["Compras"]["titulo"] != modulos_ui["Ventas"]["titulo"], (
        "Compras no puede mostrar el título de Ventas."
    )
    assert modulos_ui["Banco / Caja"]["titulo"] != modulos_ui["Compras"]["titulo"], (
        "Banco / Caja no puede mostrar el título de Compras."
    )


def test_main_renderiza_encabezado_sin_st_title_en_modulos():
    """
    El encabezado principal se coordina desde main.py, pero el HTML/CSS visual
    vive en core/ui.py para que sea reutilizable y portable.
    """

    contenido_main = leer_archivo("main.py")
    contenido_ui = leer_archivo("core/ui.py")

    assert "def mostrar_encabezado_modulo" in contenido_main
    assert "mostrar_encabezado_modulo_visual(" in contenido_main, (
        "mostrar_encabezado_modulo() debe delegar el render visual a core.ui."
    )
    assert "st.markdown(" in contenido_ui, (
        "core/ui.py debe renderizar el encabezado visual con st.markdown()."
    )
    assert "unsafe_allow_html=True" in contenido_ui, (
        "El encabezado visual usa HTML controlado en core/ui.py."
    )


def test_main_sintaxis_python_valida():
    """
    Control rápido para asegurar que main.py sea parseable por Python.
    """

    contenido = leer_archivo("main.py")
    ast.parse(contenido)


def test_core_ui_sintaxis_python_valida():
    """
    Control rápido para asegurar que core/ui.py sea parseable por Python.
    """

    contenido = leer_archivo("core/ui.py")
    ast.parse(contenido)