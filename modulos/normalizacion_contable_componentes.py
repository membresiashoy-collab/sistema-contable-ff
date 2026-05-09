from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from core.exportadores import exportar_excel
from core.ui import preparar_vista
from services.normalizacion_contable_service import (
    CONFIANZA_ALTA,
    anular_asignacion_comportamiento,
    aplicar_sugerencias_normalizacion,
    desactivar_asignacion_comportamiento,
    editar_asignacion_comportamiento,
    estimar_impacto_sugerencias,
    listar_asignaciones_normalizacion,
    listar_historial_normalizacion,
    listar_sugerencias_normalizacion,
    migrar_normalizacion_contable,
    obtener_resumen_normalizacion,
)
from services.comportamientos_contables_service import listar_catalogo_comportamientos


COLUMNAS_SUGERENCIAS_NORMALIZACION = [
    "aplicar",
    "codigo_cuenta",
    "nombre_cuenta",
    "comportamiento",
    "comportamiento_nombre",
    "confianza",
    "estado_sugerencia",
    "comportamiento_actual",
    "motivo",
]

COLUMNAS_ASIGNACIONES_NORMALIZACION = [
    "id",
    "codigo_cuenta",
    "cuenta_nombre",
    "comportamiento",
    "comportamiento_nombre",
    "origen",
    "activo",
    "estado",
    "observaciones",
]

COLUMNAS_HISTORIAL_NORMALIZACION = [
    "fecha_evento",
    "evento",
    "codigo_cuenta",
    "comportamiento",
    "detalle",
    "usuario",
]


def _df(filas: list[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(filas or [])


def _sugerencias_dataframe(filas: list[dict[str, Any]]) -> pd.DataFrame:
    df = _df(filas)
    if df.empty:
        return pd.DataFrame(columns=COLUMNAS_SUGERENCIAS_NORMALIZACION)
    df["aplicar"] = df.get("estado_sugerencia", "").eq("PENDIENTE") & df.get("confianza", "").isin([CONFIANZA_ALTA, "Media"])
    for columna in COLUMNAS_SUGERENCIAS_NORMALIZACION:
        if columna not in df.columns:
            df[columna] = False if columna == "aplicar" else ""
    return df[COLUMNAS_SUGERENCIAS_NORMALIZACION].copy()


def _asignaciones_dataframe(filas: list[dict[str, Any]]) -> pd.DataFrame:
    df = _df(filas)
    if df.empty:
        return pd.DataFrame(columns=COLUMNAS_ASIGNACIONES_NORMALIZACION)
    for columna in COLUMNAS_ASIGNACIONES_NORMALIZACION:
        if columna not in df.columns:
            df[columna] = ""
    if "estado" in df.columns:
        df["estado"] = df["estado"].fillna("")
    return df[COLUMNAS_ASIGNACIONES_NORMALIZACION].copy()


def _historial_dataframe(filas: list[dict[str, Any]]) -> pd.DataFrame:
    df = _df(filas)
    if df.empty:
        return pd.DataFrame(columns=COLUMNAS_HISTORIAL_NORMALIZACION)
    for columna in COLUMNAS_HISTORIAL_NORMALIZACION:
        if columna not in df.columns:
            df[columna] = ""
    return df[COLUMNAS_HISTORIAL_NORMALIZACION].copy()


def _vista_sugerencias(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["Aplicar", "Código", "Cuenta", "Sugerencia", "Nombre", "Confianza", "Estado", "Actual", "Motivo"])
    vista = df.rename(
        columns={
            "aplicar": "Aplicar",
            "codigo_cuenta": "Código",
            "nombre_cuenta": "Cuenta",
            "comportamiento": "Sugerencia",
            "comportamiento_nombre": "Nombre",
            "confianza": "Confianza",
            "estado_sugerencia": "Estado",
            "comportamiento_actual": "Actual",
            "motivo": "Motivo",
        }
    )
    return preparar_vista(vista)


def _vista_asignaciones(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["ID", "Código", "Cuenta", "Comportamiento", "Nombre", "Origen", "Activo", "Estado", "Observaciones"])
    vista = df.rename(
        columns={
            "id": "ID",
            "codigo_cuenta": "Código",
            "cuenta_nombre": "Cuenta",
            "comportamiento": "Comportamiento",
            "comportamiento_nombre": "Nombre",
            "origen": "Origen",
            "activo": "Activo",
            "estado": "Estado",
            "observaciones": "Observaciones",
        }
    )
    return preparar_vista(vista)


def _vista_historial(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["Fecha", "Evento", "Código", "Comportamiento", "Detalle", "Usuario"])
    vista = df.rename(
        columns={
            "fecha_evento": "Fecha",
            "evento": "Evento",
            "codigo_cuenta": "Código",
            "comportamiento": "Comportamiento",
            "detalle": "Detalle",
            "usuario": "Usuario",
        }
    )
    return preparar_vista(vista)


def _render_resumen(resumen: dict[str, Any]) -> None:
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Cuentas", resumen.get("total_cuentas", 0))
    c2.metric("Con comportamiento", resumen.get("cuentas_con_comportamiento", 0))
    c3.metric("Sugerencias", resumen.get("sugerencias_pendientes", 0))
    c4.metric("Alta confianza", resumen.get("sugerencias_alta", 0))
    c5.metric("Conflictos", resumen.get("conflictos", 0))

    st.caption(
        "Este asistente no modifica asientos ni datos operativos. Solo ayuda a clasificar cuentas del plan de cuentas "
        "para mejorar el diagnóstico de coherencia contable."
    )

    conflictos = resumen.get("conflictos", 0)
    if conflictos:
        st.warning(
            "Hay sugerencias que contradicen asignaciones existentes. Revisalas manualmente antes de reemplazar comportamientos."
        )


def _render_sugerencias(empresa_id: int | None, usuario: str | None, key_prefix: str) -> None:
    sugerencias = listar_sugerencias_normalizacion(empresa_id=empresa_id)
    df = _sugerencias_dataframe(sugerencias)

    if df.empty:
        st.info("No se detectaron sugerencias automáticas sobre el plan de cuentas actual.")
        return

    filtro_estado = st.multiselect(
        "Estado de sugerencia",
        options=sorted(df["estado_sugerencia"].dropna().unique().tolist()),
        default=[estado for estado in sorted(df["estado_sugerencia"].dropna().unique().tolist()) if estado in {"PENDIENTE", "CONFLICTO"}],
        key=f"{key_prefix}_estado_sugerencia",
    )
    df_vista = df.copy()
    if filtro_estado:
        df_vista = df_vista[df_vista["estado_sugerencia"].isin(filtro_estado)]

    editor = st.data_editor(
        _vista_sugerencias(df_vista),
        use_container_width=True,
        hide_index=True,
        key=f"{key_prefix}_editor_sugerencias",
        column_config={
            "Aplicar": st.column_config.CheckboxColumn("Aplicar"),
        },
        disabled=["Código", "Cuenta", "Sugerencia", "Nombre", "Confianza", "Estado", "Actual", "Motivo"],
    )

    seleccionadas: list[dict[str, Any]] = []
    if isinstance(editor, pd.DataFrame) and not editor.empty:
        codigos = set(editor.loc[editor["Aplicar"] == True, "Código"].astype(str).tolist())  # noqa: E712
        sugerencias_por_codigo = {str(item.get("codigo_cuenta")): item for item in sugerencias}
        seleccionadas = [sugerencias_por_codigo[codigo] for codigo in codigos if codigo in sugerencias_por_codigo]

    st.markdown("#### Impacto esperado")
    impacto = estimar_impacto_sugerencias(empresa_id=empresa_id, sugerencias=seleccionadas or sugerencias)
    col1, col2, col3 = st.columns(3)
    col1.metric("Aplicables", impacto.get("aplicables", 0))
    col2.metric("Críticos que resolvería", len(impacto.get("criticos_que_resolveria", [])))
    col3.metric("Críticos pendientes", len(impacto.get("criticos_que_seguirian_pendientes", [])))

    if impacto.get("criticos_que_resolveria"):
        st.success("Resolvería: " + ", ".join(impacto["criticos_que_resolveria"]))
    if impacto.get("criticos_que_seguirian_pendientes"):
        st.info("Seguirían pendientes: " + ", ".join(impacto["criticos_que_seguirian_pendientes"]))

    with st.expander("Aplicar sugerencias seleccionadas", expanded=False):
        motivo = st.text_area(
            "Motivo / referencia de aplicación",
            value="Normalización inicial asistida del plan de cuentas.",
            key=f"{key_prefix}_motivo_aplicar",
        )
        solo_alta = st.checkbox("Aplicar únicamente alta confianza", value=False, key=f"{key_prefix}_solo_alta")
        if st.button("Aplicar seleccionadas", key=f"{key_prefix}_btn_aplicar"):
            resultado = aplicar_sugerencias_normalizacion(
                empresa_id=empresa_id,
                sugerencias=seleccionadas,
                usuario=usuario,
                motivo=motivo,
                solo_alta_confianza=solo_alta,
            )
            if resultado.get("ok"):
                st.success(f"Sugerencias aplicadas: {resultado.get('procesadas', 0)}. Omitidas: {resultado.get('omitidas', 0)}.")
                st.rerun()
            else:
                st.error("No se pudieron aplicar todas las sugerencias: " + "; ".join(resultado.get("errores", [])))


def _opciones_asignaciones(df: pd.DataFrame) -> list[str]:
    if df.empty:
        return []
    opciones = []
    for _, row in df.iterrows():
        opciones.append(f"{int(row['id'])} — {row['codigo_cuenta']} — {row['comportamiento']} — {row.get('estado', '')}")
    return opciones


def _id_desde_opcion(opcion: str) -> int | None:
    try:
        return int(str(opcion).split("—", 1)[0].strip())
    except Exception:
        return None


def _codigo_comportamiento_desde_opcion(opcion: str) -> str:
    return str(opcion or "").split("—", 1)[0].strip()


def _render_correcciones(empresa_id: int | None, usuario: str | None, key_prefix: str) -> None:
    asignaciones = listar_asignaciones_normalizacion(empresa_id=empresa_id, incluir_inactivas=True)
    df = _asignaciones_dataframe(asignaciones)
    if df.empty:
        st.info("Todavía no hay asignaciones de comportamientos para corregir.")
        return

    st.dataframe(_vista_asignaciones(df), use_container_width=True, hide_index=True)
    opciones = _opciones_asignaciones(df)
    catalogo = listar_catalogo_comportamientos()
    opciones_comportamientos = [f"{item['codigo']} — {item['nombre']}" for item in catalogo]

    tab1, tab2, tab3 = st.tabs(["Editar", "Desactivar", "Anular por error"])

    with tab1:
        opcion = st.selectbox("Asignación a editar", options=opciones, key=f"{key_prefix}_editar_opcion")
        nuevo = st.selectbox("Nuevo comportamiento", options=opciones_comportamientos, key=f"{key_prefix}_editar_nuevo")
        motivo = st.text_area("Motivo obligatorio", key=f"{key_prefix}_editar_motivo")
        if st.button("Guardar corrección", key=f"{key_prefix}_btn_editar"):
            resultado = editar_asignacion_comportamiento(
                empresa_id=empresa_id,
                mapeo_id=_id_desde_opcion(opcion) or 0,
                nuevo_comportamiento=_codigo_comportamiento_desde_opcion(nuevo),
                usuario=usuario,
                motivo=motivo,
            )
            if resultado.get("ok"):
                st.success(resultado.get("mensaje"))
                st.rerun()
            else:
                st.error(resultado.get("mensaje"))

    with tab2:
        opcion = st.selectbox("Asignación a desactivar", options=opciones, key=f"{key_prefix}_desactivar_opcion")
        motivo = st.text_area("Motivo obligatorio", key=f"{key_prefix}_desactivar_motivo")
        if st.button("Desactivar asignación", key=f"{key_prefix}_btn_desactivar"):
            resultado = desactivar_asignacion_comportamiento(
                empresa_id=empresa_id,
                mapeo_id=_id_desde_opcion(opcion) or 0,
                usuario=usuario,
                motivo=motivo,
            )
            if resultado.get("ok"):
                st.success(resultado.get("mensaje"))
                st.rerun()
            else:
                st.error(resultado.get("mensaje"))

    with tab3:
        opcion = st.selectbox("Asignación a anular", options=opciones, key=f"{key_prefix}_anular_opcion")
        st.warning("La anulación es lógica: la asignación deja de operar, pero queda en auditoría.")
        motivo = st.text_area("Motivo obligatorio", key=f"{key_prefix}_anular_motivo")
        confirmar = st.checkbox("Confirmo que esta asignación fue cargada por error", key=f"{key_prefix}_anular_confirmar")
        if st.button("Anular asignación", key=f"{key_prefix}_btn_anular"):
            if not confirmar:
                st.error("Debés confirmar la anulación lógica.")
            else:
                resultado = anular_asignacion_comportamiento(
                    empresa_id=empresa_id,
                    mapeo_id=_id_desde_opcion(opcion) or 0,
                    usuario=usuario,
                    motivo=motivo,
                )
                if resultado.get("ok"):
                    st.success(resultado.get("mensaje"))
                    st.rerun()
                else:
                    st.error(resultado.get("mensaje"))


def _render_auditoria(empresa_id: int | None, key_prefix: str) -> None:
    eventos = listar_historial_normalizacion(empresa_id=empresa_id, limite=200)
    df = _historial_dataframe(eventos)
    if df.empty:
        st.info("Todavía no hay eventos de normalización para esta empresa.")
        return
    st.dataframe(_vista_historial(df), use_container_width=True, hide_index=True)
    with st.expander("Descargar auditoría", expanded=False):
        salida = exportar_excel({"Auditoria normalizacion": _vista_historial(df)}, nombre_base="auditoria_normalizacion_contable")
        st.download_button(
            "Descargar Excel",
            data=salida,
            file_name="auditoria_normalizacion_contable.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{key_prefix}_descargar_auditoria",
        )


def mostrar_asistente_normalizacion_contable_ui(
    empresa_id: int | None = None,
    usuario: str | None = None,
    key_prefix: str = "normalizacion_contable",
) -> None:
    st.subheader("🧭 Asistente de normalización contable")
    st.caption(
        "Sugerencias controladas para clasificar cuentas del plan de cuentas. "
        "Toda aplicación, edición, desactivación o anulación queda auditada."
    )

    migrar_normalizacion_contable()
    resumen = obtener_resumen_normalizacion(empresa_id=empresa_id)
    _render_resumen(resumen)

    st.divider()
    tab1, tab2, tab3 = st.tabs(["Sugerencias", "Corregir asignaciones", "Auditoría"])
    with tab1:
        _render_sugerencias(empresa_id, usuario, key_prefix)
    with tab2:
        _render_correcciones(empresa_id, usuario, key_prefix)
    with tab3:
        _render_auditoria(empresa_id, key_prefix)


# Alias corto para mantener la misma convención de otros componentes.
def mostrar_asistente_normalizacion_contable(
    empresa_id: int | None = None,
    usuario: str | None = None,
    key_prefix: str = "normalizacion_contable",
) -> None:
    mostrar_asistente_normalizacion_contable_ui(
        empresa_id=empresa_id,
        usuario=usuario,
        key_prefix=key_prefix,
    )