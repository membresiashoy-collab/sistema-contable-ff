from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from core.exportadores import exportar_excel
from core.ui import preparar_vista
from services.plan_cuentas_service import (
    COMPORTAMIENTOS_OPERATIVOS,
    diagnosticar_plan_cuentas_pro,
    listar_eventos_plan_cuentas,
    listar_plan_cuentas,
    listar_sugerencias_plan_cuentas,
    normalizar_metadata_plan_cuentas,
)


COLUMNAS_CUENTAS = [
    "codigo_cuenta",
    "nombre_cuenta",
    "comportamientos_texto",
    "imputable",
    "requiere_auxiliar",
    "permite_imputacion_operativa",
    "estado_configuracion",
]

COLUMNAS_MAPEOS = [
    "id",
    "codigo_cuenta",
    "cuenta_nombre",
    "comportamiento",
    "comportamiento_nombre",
    "naturaleza",
    "origen",
    "observaciones",
    "creado_en",
]

COLUMNAS_SUGERENCIAS = [
    "codigo_cuenta",
    "nombre_cuenta",
    "comportamiento",
    "comportamiento_nombre",
    "confianza",
    "motivo",
]


# ======================================================
# Helpers compatibles con tests y componentes anteriores
# ======================================================


def _empresa_id_desde_session(default: int = 1) -> int:
    try:
        return int(st.session_state.get("empresa_id") or st.session_state.get("empresa_actual_id") or default)
    except Exception:
        return default


def _usuario_desde_session(default: str = "Administrador") -> str:
    usuario = st.session_state.get("usuario") or st.session_state.get("usuario_nombre") or default
    if isinstance(usuario, dict):
        return usuario.get("usuario") or usuario.get("nombre") or default
    return str(usuario or default)


def _df(filas: list[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(filas or [])


def _cuentas_desde_plan(filas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    salida: list[dict[str, Any]] = []
    for item in filas or []:
        salida.append(
            {
                "codigo_cuenta": item.get("codigo", item.get("codigo_cuenta", "")),
                "nombre_cuenta": item.get("nombre", item.get("nombre_cuenta", "")),
                "comportamientos_texto": item.get("comportamiento_contable") or item.get("comportamientos_texto") or "",
                "imputable": item.get("imputable", ""),
                "requiere_auxiliar": item.get("requiere_auxiliar", ""),
                "permite_imputacion_operativa": item.get("permite_imputacion_operativa", ""),
                "estado_configuracion": item.get("estado_configuracion", ""),
            }
        )
    return salida


def _cuentas_dataframe(filas: list[dict[str, Any]]) -> pd.DataFrame:
    normalizadas = _cuentas_desde_plan(filas)
    df = _df(normalizadas)
    if df.empty:
        return pd.DataFrame(columns=COLUMNAS_CUENTAS)
    for columna in COLUMNAS_CUENTAS:
        if columna not in df.columns:
            df[columna] = ""
    return df[COLUMNAS_CUENTAS].copy()


def _mapeos_dataframe(filas: list[dict[str, Any]]) -> pd.DataFrame:
    df = _df(filas)
    if df.empty:
        return pd.DataFrame(columns=COLUMNAS_MAPEOS)
    for columna in COLUMNAS_MAPEOS:
        if columna not in df.columns:
            df[columna] = ""
    return df[COLUMNAS_MAPEOS].copy()


def _sugerencias_dataframe(filas: list[dict[str, Any]]) -> pd.DataFrame:
    normalizadas = []
    for item in filas or []:
        normalizadas.append(
            {
                "codigo_cuenta": item.get("codigo", item.get("codigo_cuenta", "")),
                "nombre_cuenta": item.get("nombre", item.get("nombre_cuenta", "")),
                "comportamiento": item.get("comportamiento", ""),
                "comportamiento_nombre": item.get("comportamiento_nombre", item.get("comportamiento", "")),
                "confianza": item.get("confianza", ""),
                "motivo": item.get("motivo", ""),
            }
        )
    df = _df(normalizadas)
    if df.empty:
        return pd.DataFrame(columns=COLUMNAS_SUGERENCIAS)
    for columna in COLUMNAS_SUGERENCIAS:
        if columna not in df.columns:
            df[columna] = ""
    return df[COLUMNAS_SUGERENCIAS].copy()


def _vista_cuentas(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["Código", "Cuenta", "Uso operativo", "Imputable", "Auxiliar", "Imputación operativa", "Estado"])
    vista = df.rename(
        columns={
            "codigo_cuenta": "Código",
            "nombre_cuenta": "Cuenta",
            "comportamientos_texto": "Uso operativo",
            "imputable": "Imputable",
            "requiere_auxiliar": "Auxiliar",
            "permite_imputacion_operativa": "Imputación operativa",
            "estado_configuracion": "Estado",
        }
    )
    return preparar_vista(vista)


def _vista_mapeos(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["ID", "Código", "Cuenta", "Uso operativo", "Nombre", "Naturaleza", "Origen", "Observaciones"])
    vista = df.rename(
        columns={
            "id": "ID",
            "codigo_cuenta": "Código",
            "cuenta_nombre": "Cuenta",
            "comportamiento": "Uso operativo",
            "comportamiento_nombre": "Nombre",
            "naturaleza": "Naturaleza",
            "origen": "Origen",
            "observaciones": "Observaciones",
            "creado_en": "Creado",
        }
    )
    return preparar_vista(vista)


def _vista_sugerencias(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["Código", "Cuenta", "Sugerencia", "Confianza", "Motivo"])
    vista = df.rename(
        columns={
            "codigo_cuenta": "Código",
            "nombre_cuenta": "Cuenta",
            "comportamiento": "Sugerencia",
            "comportamiento_nombre": "Nombre",
            "confianza": "Confianza",
            "motivo": "Motivo",
        }
    )
    columnas = [col for col in ["Código", "Cuenta", "Sugerencia", "Nombre", "Confianza", "Motivo"] if col in vista.columns]
    return preparar_vista(vista[columnas])


# ======================================================
# UI
# ======================================================


def mostrar_configuracion_comportamientos_contables_ui(
    empresa_id: int | None = None,
    usuario: str | None = None,
    key_prefix: str = "comp",
) -> None:
    empresa_id = empresa_id or _empresa_id_desde_session()
    usuario = usuario or _usuario_desde_session()
    key_prefix = str(key_prefix or "comp")

    st.subheader("⚙️ Uso operativo del sistema en el Plan de Cuentas")
    st.info(
        "El Plan de Cuentas es la fuente de verdad. "
        "El uso operativo del sistema se crea o edita desde Configuración → Plan de Cuentas, como dato secundario y opcional de cada cuenta. "
        "Esta pantalla queda como tablero de control, diagnóstico y auditoría, no como carga duplicada del plan."
    )

    diagnostico = diagnosticar_plan_cuentas_pro(empresa_id=empresa_id)
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Cuentas", diagnostico.get("total_cuentas", 0))
    col2.metric("Imputables", diagnostico.get("imputables", 0))
    col3.metric("Con uso operativo", diagnostico.get("con_comportamiento", 0))
    col4.metric("Pendientes", diagnostico.get("pendientes", 0))

    errores = diagnostico.get("errores", [])
    advertencias = diagnostico.get("advertencias", [])
    faltantes = diagnostico.get("criticos_faltantes", [])

    if errores:
        st.error("Hay errores de configuración que deben corregirse desde Configuración → Plan de Cuentas.")
        st.dataframe(preparar_vista(pd.DataFrame(errores)), use_container_width=True)
        if st.button("Normalizar reglas seguras del Plan de Cuentas", key=f"{key_prefix}_normalizar_plan"):
            resultado = normalizar_metadata_plan_cuentas(
                empresa_id=empresa_id,
                usuario=usuario,
                motivo="Normalización segura desde tablero de comportamientos",
            )
            if resultado.get("ok"):
                st.success("Plan normalizado. Volvé a actualizar el diagnóstico de coherencia contable.")
                st.rerun()
            else:
                st.error("No se pudo normalizar el plan.")
    else:
        st.success("No hay cuentas no imputables con uso operativo asignado.")

    if advertencias:
        st.warning("Hay usos operativos que conviene revisar desde el Plan de Cuentas.")
        st.dataframe(preparar_vista(pd.DataFrame(advertencias)), use_container_width=True)

    if faltantes:
        st.info("Usos operativos críticos pendientes en el Plan de Cuentas: " + ", ".join(faltantes))

    tabs = st.tabs(["📘 Mapa desde Plan de Cuentas", "🧭 Sugerencias", "🕓 Auditoría"])

    with tabs[0]:
        st.markdown("### Uso operativo vigente desde Plan de Cuentas")
        cuentas = listar_plan_cuentas(empresa_id=empresa_id)
        df_cuentas = _cuentas_dataframe(cuentas)
        if df_cuentas.empty:
            st.info("No hay plan de cuentas cargado.")
        else:
            col1, col2 = st.columns(2)
            with col1:
                filtro = st.text_input("Buscar", key=f"{key_prefix}_buscar_plan")
            with col2:
                estado = st.selectbox(
                    "Ver",
                    ["Todas", "Con uso operativo", "Pendientes", "No imputables"],
                    key=f"{key_prefix}_estado_plan",
                )
            vista = df_cuentas.copy()
            if filtro:
                patron = filtro.lower().strip()
                vista = vista[
                    vista["codigo_cuenta"].astype(str).str.lower().str.contains(patron, na=False)
                    | vista["nombre_cuenta"].astype(str).str.lower().str.contains(patron, na=False)
                ]
            if estado == "Con uso operativo":
                vista = vista[vista["comportamientos_texto"].astype(str).str.strip() != ""]
            elif estado == "Pendientes":
                vista = vista[(vista["imputable"] == "S") & (vista["comportamientos_texto"].astype(str).str.strip() == "")]
            elif estado == "No imputables":
                vista = vista[vista["imputable"] != "S"]
            st.dataframe(_vista_cuentas(vista), use_container_width=True)
            st.caption("Para editar la estructura contable o el uso operativo de una cuenta, ir a Configuración → Plan de Cuentas → Crear / editar cuenta.")

    with tabs[1]:
        st.markdown("### Sugerencias sobre cuentas imputables sin uso operativo")
        sugerencias = listar_sugerencias_plan_cuentas(empresa_id=empresa_id)
        df_sugerencias = _sugerencias_dataframe(sugerencias)
        if df_sugerencias.empty:
            st.success("No hay sugerencias pendientes.")
        else:
            st.dataframe(_vista_sugerencias(df_sugerencias), use_container_width=True)
            st.info("Las sugerencias se aplican editando la cuenta desde Configuración → Plan de Cuentas. No se guardan desde esta pantalla para evitar duplicar la fuente de verdad.")

    with tabs[2]:
        st.markdown("### Auditoría del Plan de Cuentas")
        eventos = listar_eventos_plan_cuentas(empresa_id=empresa_id, limite=300)
        if not eventos:
            st.info("No hay eventos registrados todavía.")
        else:
            df_eventos = pd.DataFrame(eventos)
            st.dataframe(preparar_vista(df_eventos), use_container_width=True)
            try:
                excel = exportar_excel({"auditoria_plan_cuentas": df_eventos})
                st.download_button(
                    "Descargar auditoría Excel",
                    data=excel,
                    file_name="auditoria_plan_cuentas.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            except Exception:
                pass


def mostrar_configuracion_comportamientos_contables() -> None:
    mostrar_configuracion_comportamientos_contables_ui()