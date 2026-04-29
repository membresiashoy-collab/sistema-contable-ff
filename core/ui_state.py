"""
core/ui_state.py

Aislamiento de estado visual entre módulos Streamlit.

Objetivo:
- Evitar que al cambiar de módulo queden widgets, tabs, selectbox,
  data_editor o estados temporales del módulo anterior.
- No borrar sesión, usuario, empresa, permisos ni datos persistentes.
- Forzar un rerun limpio cuando se detecta cambio de módulo.
"""

from __future__ import annotations

import re
from typing import Any, MutableMapping


# ======================================================
# CLAVES QUE NUNCA DEBEN BORRARSE AL CAMBIAR DE MÓDULO
# ======================================================

CLAVES_PERSISTENTES = {
    # autenticación / sesión
    "autenticado",
    "usuario",
    "permisos",
    "session_token",

    # empresa activa
    "empresa_id",
    "empresa_nombre",

    # navegación principal
    "menu_actual",
    "ui_modulo_activo",
    "ui_modulo_anterior",
    "ui_limpieza_ultima",
    "ui_estado_version",

    # widgets del sidebar general
    "radio_menu_principal",
    "selector_empresa_activa",
}


# ======================================================
# UTILIDADES DE NORMALIZACIÓN
# ======================================================

def normalizar_nombre_modulo(nombre: str) -> str:
    """
    Convierte un nombre de módulo visible en una clave técnica estable.

    Ejemplo:
    - "Banco / Caja" -> "banco_caja"
    - "Estado de Cargas" -> "estado_de_cargas"
    """

    texto = str(nombre or "").strip().lower()
    texto = texto.replace("/", " ")
    texto = re.sub(r"[^a-z0-9áéíóúñü]+", "_", texto, flags=re.IGNORECASE)
    texto = texto.strip("_")

    reemplazos = {
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ú": "u",
        "ñ": "n",
        "ü": "u",
    }

    for viejo, nuevo in reemplazos.items():
        texto = texto.replace(viejo, nuevo)

    return texto or "modulo"


def key_modulo(modulo: str, nombre: str) -> str:
    """
    Genera keys únicas por módulo.

    Uso recomendado:
    key=key_modulo("Cobranzas", "cliente_select")
    """

    modulo_key = normalizar_nombre_modulo(modulo)
    nombre_key = normalizar_nombre_modulo(nombre)

    return f"{modulo_key}__{nombre_key}"


def es_clave_interna_streamlit(clave: str) -> bool:
    """
    Evita borrar claves internas que Streamlit pueda usar.
    """

    clave = str(clave)

    return (
        clave.startswith("_")
        or clave.startswith("$$")
        or clave.startswith("FormSubmitter:")
    )


def es_clave_persistente(clave: str) -> bool:
    return str(clave) in CLAVES_PERSISTENTES


def es_clave_temporal_borrable(clave: str) -> bool:
    """
    Define qué claves se pueden limpiar al cambiar de módulo.

    Criterio:
    - Conservamos claves persistentes.
    - Conservamos claves internas de Streamlit.
    - Todo lo demás se considera estado visual/transitorio.
    """

    clave = str(clave)

    if es_clave_persistente(clave):
        return False

    if es_clave_interna_streamlit(clave):
        return False

    return True


# ======================================================
# LIMPIEZA DE ESTADO
# ======================================================

def limpiar_estado_visual_temporal(
    session_state: MutableMapping[str, Any],
) -> list[str]:
    """
    Limpia estado visual/transitorio.

    No borra:
    - usuario
    - permisos
    - empresa activa
    - sesión
    - menú activo
    - widgets del sidebar general
    """

    eliminadas = []

    for clave in list(session_state.keys()):
        if es_clave_temporal_borrable(clave):
            try:
                del session_state[clave]
                eliminadas.append(str(clave))
            except Exception:
                pass

    return eliminadas


def preparar_cambio_modulo(
    session_state: MutableMapping[str, Any],
    menu_nuevo: str,
) -> bool:
    """
    Detecta cambio de módulo.

    Retorna True si:
    - el módulo cambió;
    - se limpió estado temporal;
    - conviene ejecutar st.rerun() antes de renderizar.

    Retorna False si:
    - es el primer render;
    - el módulo no cambió.
    """

    menu_nuevo = str(menu_nuevo)

    modulo_activo = session_state.get("ui_modulo_activo")

    if not modulo_activo:
        session_state["ui_modulo_activo"] = menu_nuevo
        session_state["menu_actual"] = menu_nuevo
        session_state["ui_estado_version"] = 1
        return False

    if str(modulo_activo) == menu_nuevo:
        session_state["menu_actual"] = menu_nuevo
        return False

    modulo_anterior = str(modulo_activo)

    eliminadas = limpiar_estado_visual_temporal(session_state)

    session_state["ui_modulo_anterior"] = modulo_anterior
    session_state["ui_modulo_activo"] = menu_nuevo
    session_state["menu_actual"] = menu_nuevo
    session_state["ui_estado_version"] = int(session_state.get("ui_estado_version", 1) or 1) + 1
    session_state["ui_limpieza_ultima"] = {
        "desde": modulo_anterior,
        "hacia": menu_nuevo,
        "cantidad": len(eliminadas),
        "claves": eliminadas[:120],
    }

    return True


def obtener_resumen_limpieza(
    session_state: MutableMapping[str, Any],
) -> dict[str, Any]:
    """
    Devuelve información de diagnóstico sobre la última limpieza de UI.
    """

    data = session_state.get("ui_limpieza_ultima")

    if isinstance(data, dict):
        return data

    return {}