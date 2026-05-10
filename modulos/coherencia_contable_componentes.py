from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from core.exportadores import exportar_excel
from core.ui import preparar_vista
from services.coherencia_contable_service import (
    aplicar_migracion_nucleo,
    diagnosticar_nucleo_coherencia,
    listar_comportamientos_contables,
    listar_origenes_economicos,
    resumen_diagnostico,
)


# ======================================================
# CONTABILIDAD PRO - CONTROL DE CONSISTENCIA CONTABLE
# ======================================================


ORDEN_SEVERIDAD = {
    "ERROR": 1,
    "ADVERTENCIA": 2,
    "INFO": 3,
    "OK": 4,
}

ETIQUETAS_SEVERIDAD = {
    "ERROR": "Error",
    "ADVERTENCIA": "Advertencia",
    "INFO": "Información",
    "OK": "Correcto",
}

COLUMNAS_DIAGNOSTICO = [
    "categoria_control",
    "area",
    "severidad",
    "codigo",
    "titulo",
    "detalle",
    "referencia_tipo",
    "referencia_id",
]

CATEGORIA_ALERTAS_ACCIONABLES = "Alertas accionables"
CATEGORIA_CUENTAS_HEREDADAS = "Cuentas heredadas a sanear"
CATEGORIA_PENDIENTES_ESTRUCTURALES = "Pendientes estructurales"
CATEGORIA_HISTORIAL_TECNICO = "Historial técnico / auditoría"
CATEGORIA_CORRECTOS = "Correctos"

ORDEN_CATEGORIA_CONTROL = {
    CATEGORIA_ALERTAS_ACCIONABLES: 1,
    CATEGORIA_CUENTAS_HEREDADAS: 2,
    CATEGORIA_PENDIENTES_ESTRUCTURALES: 3,
    CATEGORIA_HISTORIAL_TECNICO: 4,
    CATEGORIA_CORRECTOS: 5,
}

CODIGOS_CUENTAS_HEREDADAS = {
    "PLAN_CUENTAS_EMPRESA_IMPUTABLES_HEREDADAS_PENDIENTES",
    "PLAN_CUENTAS_EMPRESA_AGRUPADORAS_HEREDADAS_PENDIENTES",
    "PLAN_CUENTAS_EMPRESA_IMPUTABLES_SIN_VINCULO_MAESTRO",
    "PLAN_CUENTAS_EMPRESA_AGRUPADORAS_SIN_VINCULO_MAESTRO",
    "PLAN_CUENTAS_EMPRESA_HEREDADAS_PENDIENTES",  # compatibilidad con diagnósticos guardados antes de v2b
    "PLAN_CUENTAS_EMPRESA_SIN_VINCULO_MAESTRO",  # compatibilidad con diagnósticos guardados antes de v2b
}

CODIGOS_PENDIENTES_ESTRUCTURALES = {
    "PLAN_CUENTAS_SIN_COMPORTAMIENTO",
    "PLAN_COMPORTAMIENTO_POSIBLEMENTE_INCORRECTO",
    "PLAN_CUENTAS_EMPRESA_AGRUPADORAS_HEREDADAS_PENDIENTES",
    "PLAN_CUENTAS_EMPRESA_AGRUPADORAS_SIN_VINCULO_MAESTRO",
}

CODIGOS_HISTORIAL_TECNICO = {
    "LIBRO_ASIENTOS_SIN_ORIGEN",
    "LIBRO_ASIENTOS_TRAZABILIDAD_INCOMPLETA",  # compatibilidad con diagnósticos guardados antes de v2b
    "LIBRO_ASIENTOS_TRAZABILIDAD_HISTORICA_INCOMPLETA",
}


_original_error = st.error


def _texto(valor: Any) -> str:
    if valor is None:
        return ""
    try:
        if pd.isna(valor):
            return ""
    except Exception:
        pass
    return str(valor).strip()


def _categoria_control_diagnostico(item: dict[str, Any]) -> str:
    codigo = _texto(item.get("codigo")).upper()
    severidad = _texto(item.get("severidad")).upper()

    if codigo in CODIGOS_HISTORIAL_TECNICO:
        return CATEGORIA_HISTORIAL_TECNICO
    if codigo in CODIGOS_PENDIENTES_ESTRUCTURALES:
        return CATEGORIA_PENDIENTES_ESTRUCTURALES
    if codigo in CODIGOS_CUENTAS_HEREDADAS:
        return CATEGORIA_CUENTAS_HEREDADAS
    if severidad == "OK":
        return CATEGORIA_CORRECTOS
    return CATEGORIA_ALERTAS_ACCIONABLES


def _diagnosticos_dataframe(diagnosticos: list[dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(diagnosticos)
    for columna in COLUMNAS_DIAGNOSTICO:
        if columna not in df.columns:
            df[columna] = ""
    if df.empty:
        return pd.DataFrame(columns=COLUMNAS_DIAGNOSTICO)

    registros = df.to_dict(orient="records")
    df["categoria_control"] = [_categoria_control_diagnostico(item) for item in registros]
    df = df[COLUMNAS_DIAGNOSTICO].copy()
    df["orden_categoria"] = df["categoria_control"].map(ORDEN_CATEGORIA_CONTROL).fillna(99).astype(int)
    df["orden_severidad"] = df["severidad"].map(ORDEN_SEVERIDAD).fillna(99).astype(int)
    df = df.sort_values(["orden_categoria", "orden_severidad", "area", "codigo", "titulo"]).drop(
        columns=["orden_categoria", "orden_severidad"]
    )
    return df.reset_index(drop=True)


def _vista_diagnosticos(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    vista = df.copy()
    vista["severidad"] = vista["severidad"].map(ETIQUETAS_SEVERIDAD).fillna(vista["severidad"])
    vista = vista.rename(
        columns={
            "categoria_control": "Tipo de control",
            "area": "Área",
            "severidad": "Severidad",
            "codigo": "Código",
            "titulo": "Alerta / control",
            "detalle": "Detalle",
            "referencia_tipo": "Referencia",
            "referencia_id": "ID ref.",
        }
    )
    return vista


def _filtrar_diagnosticos(
    df: pd.DataFrame,
    severidades: list[str] | tuple[str, ...] | None = None,
    areas: list[str] | tuple[str, ...] | None = None,
    categorias: list[str] | tuple[str, ...] | None = None,
) -> pd.DataFrame:
    filtrado = df.copy()
    if categorias:
        filtrado = filtrado[filtrado["categoria_control"].isin(categorias)]
    if severidades:
        filtrado = filtrado[filtrado["severidad"].isin(severidades)]
    if areas:
        filtrado = filtrado[filtrado["area"].isin(areas)]
    return filtrado.reset_index(drop=True)


def _mostrar_metricas_resumen(resumen: dict[str, int]) -> None:
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Errores", resumen.get("ERROR", 0))
    c2.metric("Advertencias", resumen.get("ADVERTENCIA", 0))
    c3.metric("Información", resumen.get("INFO", 0))
    c4.metric("Correctos", resumen.get("OK", 0))
    c5.metric("Total", resumen.get("TOTAL", 0))

    if resumen.get("ERROR", 0) > 0:
        st.error("Hay controles críticos para revisar antes de cerrar etapas contables o automatizar nuevos pases.")
    elif resumen.get("ADVERTENCIA", 0) > 0:
        st.warning("No hay errores críticos, pero existen advertencias que conviene revisar.")
    else:
        st.success("No se detectaron controles críticos en la revisión actual.")


def _mostrar_metricas_por_tipo(df: pd.DataFrame) -> None:
    if df.empty or "categoria_control" not in df.columns:
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(CATEGORIA_ALERTAS_ACCIONABLES, int((df["categoria_control"] == CATEGORIA_ALERTAS_ACCIONABLES).sum()))
    c2.metric(CATEGORIA_CUENTAS_HEREDADAS, int((df["categoria_control"] == CATEGORIA_CUENTAS_HEREDADAS).sum()))
    c3.metric(CATEGORIA_PENDIENTES_ESTRUCTURALES, int((df["categoria_control"] == CATEGORIA_PENDIENTES_ESTRUCTURALES).sum()))
    c4.metric(CATEGORIA_HISTORIAL_TECNICO, int((df["categoria_control"] == CATEGORIA_HISTORIAL_TECNICO).sum()))


def _mostrar_tabla_diagnosticos(df: pd.DataFrame) -> None:
    if df.empty:
        st.info("No hay alertas ni controles para mostrar con los filtros actuales.")
        return

    vista = _vista_diagnosticos(df)
    st.dataframe(preparar_vista(vista), use_container_width=True, hide_index=True)


def _mostrar_detalle_por_area(df: pd.DataFrame) -> None:
    if df.empty:
        return

    for area in sorted(df["area"].dropna().unique()):
        bloque = df[df["area"] == area].copy()
        errores = int((bloque["severidad"] == "ERROR").sum())
        advertencias = int((bloque["severidad"] == "ADVERTENCIA").sum())
        etiqueta = f"{area} · {len(bloque)} control(es)"
        if errores:
            etiqueta += f" · {errores} error(es)"
        elif advertencias:
            etiqueta += f" · {advertencias} advertencia(s)"

        with st.expander(etiqueta, expanded=bool(errores)):
            for _, fila in bloque.iterrows():
                severidad = _texto(fila.get("severidad"))
                titulo = _texto(fila.get("titulo"))
                detalle = _texto(fila.get("detalle"))
                codigo = _texto(fila.get("codigo"))
                referencia = _texto(fila.get("referencia_tipo"))
                referencia_id = _texto(fila.get("referencia_id"))

                st.markdown(f"**{ETIQUETAS_SEVERIDAD.get(severidad, severidad)} · {titulo}**")
                st.caption(codigo)
                if detalle:
                    st.write(detalle)
                if referencia or referencia_id:
                    st.caption(f"Referencia técnica: {referencia} {referencia_id}".strip())
                st.divider()


def _mostrar_comportamientos_contables() -> None:
    comportamientos = pd.DataFrame(listar_comportamientos_contables())
    if comportamientos.empty:
        st.info("No hay usos operativos configurados.")
        return

    vista = comportamientos.rename(
        columns={
            "codigo": "Código",
            "nombre": "Nombre",
            "naturaleza": "Naturaleza",
            "descripcion": "Descripción",
        }
    )
    st.dataframe(preparar_vista(vista), use_container_width=True, hide_index=True)


def _mostrar_origenes_economicos() -> None:
    origenes = pd.DataFrame(listar_origenes_economicos())
    if origenes.empty:
        st.info("No hay tipos de origen operativo configurados.")
        return

    vista = origenes.rename(
        columns={
            "codigo": "Código",
            "nombre": "Nombre",
            "modulo": "Módulo sugerido",
            "descripcion": "Descripción",
        }
    )
    st.dataframe(preparar_vista(vista), use_container_width=True, hide_index=True)


def _mostrar_bloque_categoria(df: pd.DataFrame, categoria: str, ayuda: str) -> None:
    bloque = df[df["categoria_control"] == categoria].copy() if not df.empty else df
    st.caption(ayuda)
    _mostrar_tabla_diagnosticos(bloque)
    expandido = categoria == CATEGORIA_ALERTAS_ACCIONABLES and not bloque.empty and bool((bloque["severidad"] == "ERROR").any())
    with st.expander("Ver detalle", expanded=expandido):
        _mostrar_detalle_por_area(bloque)


def _descargar_excel_diagnostico(df: pd.DataFrame) -> None:
    comportamientos = pd.DataFrame(listar_comportamientos_contables())
    origenes = pd.DataFrame(listar_origenes_economicos())

    alertas = df[df["categoria_control"] == CATEGORIA_ALERTAS_ACCIONABLES].copy() if not df.empty else df
    heredadas = df[df["categoria_control"] == CATEGORIA_CUENTAS_HEREDADAS].copy() if not df.empty else df
    estructurales = df[df["categoria_control"] == CATEGORIA_PENDIENTES_ESTRUCTURALES].copy() if not df.empty else df
    historial = df[df["categoria_control"] == CATEGORIA_HISTORIAL_TECNICO].copy() if not df.empty else df

    excel = exportar_excel(
        {
            "Alertas accionables": _vista_diagnosticos(alertas),
            "Cuentas heredadas": _vista_diagnosticos(heredadas),
            "Pendientes estructurales": _vista_diagnosticos(estructurales),
            "Historial tecnico": _vista_diagnosticos(historial),
            "Vista completa": _vista_diagnosticos(df),
            "Usos operativos": comportamientos,
            "Origenes": origenes,
        }
    )

    st.download_button(
        "Descargar control de consistencia Excel",
        data=excel,
        file_name="control_consistencia_contable.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )


def mostrar_diagnostico_coherencia_contable_ui(
    empresa_id: int,
    usuario: str | None = None,
    key_prefix: str = "coherencia_contable",
) -> None:
    """
    Vista operativa de control.

    Esta pantalla es deliberadamente de solo lectura: no corrige ni contabiliza.
    Sirve para detectar alertas antes de avanzar con automatizaciones
    de Banco, Caja, Capital, Sueldos u otros módulos.
    """

    st.subheader("🧩 Control de consistencia contable")
    st.caption(
        "Control central de consistencia. Esta vista no modifica asientos ni datos operativos; "
        "revisa ejercicios, plan de cuentas, inicio contable/capital y Libro Diario."
    )

    aplicar_migracion_nucleo()

    col1, col2 = st.columns([2, 1])
    with col1:
        guardar_historial = st.checkbox(
            "Guardar este control en historial",
            value=False,
            key=f"{key_prefix}_guardar_historial",
            help="Guarda el resultado del control en contabilidad_diagnosticos_coherencia para auditoría interna.",
        )
    with col2:
        ejecutar = st.button(
            "Actualizar control",
            type="primary",
            use_container_width=True,
            key=f"{key_prefix}_actualizar",
        )

    if ejecutar:
        st.session_state[f"{key_prefix}_diagnosticos"] = diagnosticar_nucleo_coherencia(
            empresa_id=empresa_id,
            guardar=guardar_historial,
        )
        if guardar_historial:
            st.success("Control actualizado y guardado en historial.")
        else:
            st.success("Control actualizado.")

    if f"{key_prefix}_diagnosticos" not in st.session_state:
        st.session_state[f"{key_prefix}_diagnosticos"] = diagnosticar_nucleo_coherencia(
            empresa_id=empresa_id,
            guardar=False,
        )

    diagnosticos = st.session_state.get(f"{key_prefix}_diagnosticos") or []
    df = _diagnosticos_dataframe(diagnosticos)
    resumen = resumen_diagnostico(diagnosticos)

    _mostrar_metricas_resumen(resumen)
    _mostrar_metricas_por_tipo(df)

    st.divider()
    st.markdown("### Lectura ordenada del control")
    st.caption(
        "La pantalla separa problemas accionables, cuentas heredadas a sanear, pendientes estructurales "
        "e historial técnico. Esto evita que una cuenta agrupadora heredada tenga el mismo peso visual que una cuenta usada incorrectamente."
    )

    tab_alertas, tab_heredadas, tab_estructurales, tab_historial, tab_completa = st.tabs(
        [
            "Alertas accionables",
            "Cuentas heredadas",
            "Pendientes estructurales",
            "Historial técnico",
            "Vista completa",
        ]
    )

    with tab_alertas:
        _mostrar_bloque_categoria(
            df,
            CATEGORIA_ALERTAS_ACCIONABLES,
            "Controles que conviene resolver desde el módulo dueño antes de automatizar o cerrar etapas.",
        )
    with tab_heredadas:
        _mostrar_bloque_categoria(
            df,
            CATEGORIA_CUENTAS_HEREDADAS,
            "Cuentas heredadas que deben vincularse al Plan Maestro FF, convertirse en cuentas específicas o inactivarse lógicamente con auditoría.",
        )
    with tab_estructurales:
        _mostrar_bloque_categoria(
            df,
            CATEGORIA_PENDIENTES_ESTRUCTURALES,
            "Pendientes de ordenamiento que no necesariamente bloquean la operatoria, pero deben sanearse para reducir ruido.",
        )
    with tab_historial:
        _mostrar_bloque_categoria(
            df,
            CATEGORIA_HISTORIAL_TECNICO,
            "Información técnica o histórica útil para auditoría. No implica borrar ni alterar asientos históricos.",
        )
    with tab_completa:
        opciones_severidad = ["ERROR", "ADVERTENCIA", "INFO", "OK"]
        seleccion_severidad = st.multiselect(
            "Severidad",
            options=opciones_severidad,
            default=opciones_severidad,
            format_func=lambda x: ETIQUETAS_SEVERIDAD.get(x, x),
            key=f"{key_prefix}_severidades",
        )

        categorias = sorted([categoria for categoria in df["categoria_control"].dropna().unique()]) if not df.empty else []
        seleccion_categorias = st.multiselect(
            "Tipo de control",
            options=categorias,
            default=categorias,
            key=f"{key_prefix}_categorias",
        )

        areas = sorted([area for area in df["area"].dropna().unique()]) if not df.empty else []
        seleccion_areas = st.multiselect(
            "Área",
            options=areas,
            default=areas,
            key=f"{key_prefix}_areas",
        )

        filtrado = _filtrar_diagnosticos(df, seleccion_severidad, seleccion_areas, seleccion_categorias)
        _mostrar_tabla_diagnosticos(filtrado)

        with st.expander("Ver detalle por área", expanded=bool((filtrado["severidad"] == "ERROR").any()) if not filtrado.empty else False):
            _mostrar_detalle_por_area(filtrado)

    st.divider()
    with st.expander("Catálogos técnicos usados por el control", expanded=False):
        st.caption(
            "Estos catálogos son referencias internas del sistema. No son una pantalla de carga: "
            "las correcciones deben hacerse desde Configuración → Plan de Cuentas → Avanzado "
            "o desde el módulo dueño del dato."
        )

        tab1, tab2 = st.tabs(["Usos operativos del sistema", "Tipos de origen operativo"])
        with tab1:
            st.caption(
                "Clasificaciones técnicas usadas para validar Caja, Banco, Capital, Sueldos e IVA "
                "sin duplicar reglas contables en cada módulo."
            )
            _mostrar_comportamientos_contables()
        with tab2:
            st.caption(
                "Tipos de hechos económicos usados para distinguir cobros, aportes, préstamos, "
                "pagos fiscales y transferencias internas."
            )
            _mostrar_origenes_economicos()

    st.divider()
    _descargar_excel_diagnostico(df)


# Alias explícito para mantener el mismo criterio usado en otros componentes UI.
mostrar_diagnostico_coherencia_contable = mostrar_diagnostico_coherencia_contable_ui