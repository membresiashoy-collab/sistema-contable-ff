from pathlib import Path
import ast
import re


def leer_archivo(ruta):
    return Path(ruta).read_text(encoding="utf-8")


def test_modulos_no_deben_usar_st_title():
    """
    Regla de arquitectura UI:

    - El encabezado principal de cada módulo vive en main.py.
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
        "El encabezado principal debe estar centralizado en main.py. "
        f"Archivos con st.title(): {errores}"
    )


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


def test_main_tiene_todos_los_modulos_con_titulo_correcto():
    """
    Controla que cada menú tenga icono, título y descripción propios.

    Esto evita errores como:
    - Compras mostrando Ventas.
    - Contabilidad mostrando IVA.
    - Estado de Cargas mostrando otro encabezado.
    """

    contenido = leer_archivo("main.py")

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
        assert f'"{menu}"' in contenido, f"Falta el menú {menu} en MODULOS_UI."
        assert f'"icono": "{datos["icono"]}"' in contenido, (
            f"El menú {menu} debe tener icono {datos['icono']}."
        )
        assert f'"titulo": "{datos["titulo"]}"' in contenido, (
            f"El menú {menu} debe tener título {datos['titulo']}."
        )
        assert datos["texto_descripcion"] in contenido, (
            f"El menú {menu} debe tener una descripción propia."
        )


def test_main_no_debe_repetir_titulos_cruzados_en_modulos_ui():
    """
    Control específico contra el error que tuvimos:
    el menú seleccionado era Compras pero el encabezado mostraba Ventas.
    """

    contenido = leer_archivo("main.py")

    bloque_compras = re.search(
        r'"Compras"\s*:\s*\{(?P<bloque>.*?)\n\s*\},\n\s*"IVA"',
        contenido,
        flags=re.DOTALL
    )

    assert bloque_compras, "No se pudo encontrar el bloque de configuración de Compras."

    bloque = bloque_compras.group("bloque")

    assert '"titulo": "Compras"' in bloque, (
        "El bloque de Compras debe tener título Compras."
    )

    assert '"titulo": "Ventas"' not in bloque, (
        "El bloque de Compras no puede tener título Ventas."
    )


def test_main_renderiza_encabezado_sin_st_title_en_modulos():
    """
    El encabezado principal se renderiza desde main.py con markdown/HTML controlado.

    Permitimos st.title() en main.py para login/cambio de contraseña,
    pero el encabezado de módulos debe pasar por mostrar_encabezado_modulo().
    """

    contenido = leer_archivo("main.py")

    assert "def mostrar_encabezado_modulo" in contenido
    assert "st.markdown(" in contenido, (
        "mostrar_encabezado_modulo debe renderizar el encabezado con st.markdown()."
    )
    assert "unsafe_allow_html=True" in contenido, (
        "El encabezado central usa HTML controlado y debe declarar unsafe_allow_html=True."
    )


def test_main_sintaxis_python_valida():
    """
    Control rápido para asegurar que main.py sea parseable por Python.
    """

    contenido = leer_archivo("main.py")
    ast.parse(contenido)