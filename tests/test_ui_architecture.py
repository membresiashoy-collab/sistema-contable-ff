from pathlib import Path
import re


def test_modulos_no_deben_usar_st_title():
    """
    Regla de arquitectura UI:

    - El encabezado principal de cada módulo vive en main.py.
    - Los archivos dentro de modulos/ no deben usar st.title().
    - Los módulos pueden usar st.subheader(), st.info(), st.tabs(), etc.
    """

    errores = []

    for archivo in sorted(Path("modulos").glob("*.py")):
        if archivo.name == "__init__.py":
            continue

        contenido = archivo.read_text(encoding="utf-8")

        if re.search(r'\bst\.title\s*\(', contenido):
            errores.append(str(archivo))

    assert not errores, (
        "Los módulos no deben usar st.title(). "
        "El encabezado principal debe estar centralizado en main.py. "
        f"Archivos con st.title(): {errores}"
    )


def test_main_contiene_encabezados_centrales():
    """
    Control mínimo para asegurar que main.py siga teniendo
    los encabezados principales del sistema.
    """

    contenido = Path("main.py").read_text(encoding="utf-8")

    encabezados_requeridos = [
        "📤 Ventas",
        "📥 Compras",
        "🧾 IVA",
        "📚 Contabilidad",
        "📋 Estado de Cargas y Auditoría",
        "⚙️ Configuración",
        "🔐 Seguridad",
    ]

    faltantes = [
        encabezado
        for encabezado in encabezados_requeridos
        if encabezado not in contenido
    ]

    assert not faltantes, f"Faltan encabezados centrales en main.py: {faltantes}"