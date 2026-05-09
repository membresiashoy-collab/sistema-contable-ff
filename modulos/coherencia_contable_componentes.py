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
# CONTABILIDAD PRO - DIAGNÓSTICO DE COHERENCIA CONTABLE
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
    "area",
    "severidad",
    "codigo",
    "titulo",
    "detalle",
    "referencia_tipo",
    "referencia_id",
]


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


def _diagnosticos_dataframe(diagnosticos: list[dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(diagnosticos)
    for columna in COLUMNAS_DIAGNOSTICO:
        if columna not in df.columns:
            df[columna] = ""
    if df.empty:
        return pd.DataFrame(columns=COLUMNAS_DIAGNOSTICO)
    df = df[COLUMNAS_DIAGNOSTICO].copy()
    df["orden_severidad"] = df["severidad"].map(ORDEN_SEVERIDAD).fillna(99).astype(int)
    df = df.sort_values(["orden_severidad", "area", "codigo", "titulo"]).drop(columns=["orden_severidad"])
    return df.reset_index(drop=True)


def _vista_diagnosticos(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    vista = df.copy()
    vista["severidad"] = vista["severidad"].map(ETIQUETAS_SEVERIDAD).fillna(vista["severidad"])
    vista = vista.rename(
        columns={
            "area": "Área",
            "severidad": "Severidad",
            "codigo": "Código",
            "titulo": "Diagnóstico",
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
) -> pd.DataFrame:
    filtrado = df.copy()
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
        st.error("Hay incoherencias críticas para revisar antes de cerrar etapas contables o automatizar nuevos pases.")
    elif resumen.get("ADVERTENCIA", 0) > 0:
        st.warning("No hay errores críticos, pero existen advertencias que conviene revisar.")
    else:
        st.success("No se detectaron incoherencias críticas en el diagnóstico actual.")


def _mostrar_tabla_diagnosticos(df: pd.DataFrame) -> None:
    if df.empty:
        st.info("No hay diagnósticos para mostrar con los filtros actuales.")
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
        etiqueta = f"{area} · {len(bloque)} diagnóstico(s)"
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
        st.info("No hay comportamientos contables configurados.")
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
        st.info("No hay orígenes económicos configurados.")
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


def _descargar_excel_diagnostico(df: pd.DataFrame) -> None:
    comportamientos = pd.DataFrame(listar_comportamientos_contables())
    origenes = pd.DataFrame(listar_origenes_economicos())

    excel = exportar_excel(
        {
            "Diagnostico": _vista_diagnosticos(df),
            "Comportamientos": comportamientos,
            "Origenes economicos": origenes,
        }
    )

    st.download_button(
        "Descargar diagnóstico Excel",
        data=excel,
        file_name="diagnostico_coherencia_contable.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )


def mostrar_diagnostico_coherencia_contable_ui(
    empresa_id: int,
    usuario: str | None = None,
    key_prefix: str = "coherencia_contable",
) -> None:
    """
    Vista operativa de diagnóstico.

    Esta pantalla es deliberadamente de solo lectura: no corrige ni contabiliza.
    Sirve para detectar incoherencias antes de avanzar con automatizaciones
    de Banco, Caja, Capital, Sueldos u otros módulos.
    """

    st.subheader("🧩 Diagnóstico de coherencia contable")
    st.caption(
        "Control central de consistencia. Esta vista no modifica asientos ni datos operativos; "
        "solo diagnostica ejercicios, plan de cuentas, inicio contable/capital y Libro Diario."
    )

    aplicar_migracion_nucleo()

    col1, col2 = st.columns([2, 1])
    with col1:
        guardar_historial = st.checkbox(
            "Guardar esta corrida en historial de diagnósticos",
            value=False,
            key=f"{key_prefix}_guardar_historial",
            help="Guarda el resultado en contabilidad_diagnosticos_coherencia para auditoría interna.",
        )
    with col2:
        ejecutar = st.button(
            "Actualizar diagnóstico",
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
            st.success("Diagnóstico actualizado y guardado en historial.")
        else:
            st.success("Diagnóstico actualizado.")

    if f"{key_prefix}_diagnosticos" not in st.session_state:
        st.session_state[f"{key_prefix}_diagnosticos"] = diagnosticar_nucleo_coherencia(
            empresa_id=empresa_id,
            guardar=False,
        )

    diagnosticos = st.session_state.get(f"{key_prefix}_diagnosticos") or []
    df = _diagnosticos_dataframe(diagnosticos)
    resumen = resumen_diagnostico(diagnosticos)

    _mostrar_metricas_resumen(resumen)

    st.divider()
    st.markdown("### Diagnósticos detectados")

    opciones_severidad = ["ERROR", "ADVERTENCIA", "INFO", "OK"]
    seleccion_severidad = st.multiselect(
        "Severidad",
        options=opciones_severidad,
        default=opciones_severidad,
        format_func=lambda x: ETIQUETAS_SEVERIDAD.get(x, x),
        key=f"{key_prefix}_severidades",
    )

    areas = sorted([area for area in df["area"].dropna().unique()]) if not df.empty else []
    seleccion_areas = st.multiselect(
        "Área",
        options=areas,
        default=areas,
        key=f"{key_prefix}_areas",
    )

    filtrado = _filtrar_diagnosticos(df, seleccion_severidad, seleccion_areas)
    _mostrar_tabla_diagnosticos(filtrado)

    with st.expander("Ver detalle por área", expanded=bool((filtrado["severidad"] == "ERROR").any()) if not filtrado.empty else False):
        _mostrar_detalle_por_area(filtrado)

    st.divider()
    st.markdown("### Reglas centrales disponibles")

    tab1, tab2 = st.tabs(["Comportamientos contables", "Orígenes económicos"])
    with tab1:
        st.caption("Clasificaciones comunes que más adelante permitirán validar Caja, Banco, Capital, Sueldos e IVA sin duplicar reglas.")
        _mostrar_comportamientos_contables()
    with tab2:
        st.caption("Tipos de hechos económicos que evitan confundir cobros, aportes, préstamos, pagos fiscales y transferencias internas.")
        _mostrar_origenes_economicos()

    st.divider()
    _descargar_excel_diagnostico(filtrado)


# Alias explícito para mantener el mismo criterio usado en otros componentes UI.
mostrar_diagnostico_coherencia_contable = mostrar_diagnostico_coherencia_contable_ui