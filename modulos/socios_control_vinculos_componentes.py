from __future__ import annotations

from typing import Optional

import pandas as pd
import streamlit as st

from services.socios_control_vinculos_service import controlar_vinculos_socios


COLUMNAS_ALERTAS = [
    "nivel",
    "area",
    "codigo",
    "socio_nombre",
    "tipo_vinculo",
    "mensaje",
    "recomendacion",
    "bloqueante",
]

COLUMNAS_SOCIOS = [
    "socio_id",
    "socio_nombre",
    "rol_relacion",
    "condicion_fiscal",
    "cuenta_particular_habilitada",
    "proveedor_vinculado_referencia",
    "alertas",
    "criticas",
    "advertencias",
    "informativas",
]


def _texto(valor) -> str:
    if valor is None:
        return ""
    return str(valor).strip()


def _df(datos) -> pd.DataFrame:
    if isinstance(datos, pd.DataFrame):
        return datos
    return pd.DataFrame(datos or [])


def _mostrar_metricas(resultado: dict) -> None:
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Socios controlados", int(resultado.get("total_socios") or 0))
    col2.metric("Alertas", int(resultado.get("total_alertas") or 0))
    col3.metric("Críticas", int(resultado.get("criticas") or 0))
    col4.metric("Advertencias", int(resultado.get("advertencias") or 0))

    matriz = resultado.get("matriz") or {}
    st.caption(
        "Matriz contable: "
        f"{int(matriz.get('configuradas') or 0)} configuradas / "
        f"{int(matriz.get('total') or 0)} vínculos "
        f"({float(matriz.get('porcentaje_configurado') or 0):.0f}%)."
    )


def _mostrar_alertas(resultado: dict) -> None:
    alertas = _df(resultado.get("alertas"))
    if alertas.empty:
        st.success("No se detectaron alertas normativas u operativas en vínculos con socios.")
        return

    niveles = ["Todas"] + sorted([_texto(n) for n in alertas["nivel"].dropna().unique()]) if "nivel" in alertas.columns else ["Todas"]
    nivel = st.selectbox("Filtrar por nivel", options=niveles, key="control_vinculos_socios_nivel")
    visibles = alertas.copy()
    if nivel != "Todas" and "nivel" in visibles.columns:
        visibles = visibles[visibles["nivel"] == nivel]

    columnas = [col for col in COLUMNAS_ALERTAS if col in visibles.columns]
    st.dataframe(visibles[columnas], use_container_width=True, hide_index=True)


def _mostrar_por_socio(resultado: dict) -> None:
    detalle = _df(resultado.get("detalle_por_socio"))
    if detalle.empty:
        st.info("No hay socios activos para detallar.")
        return

    columnas = [col for col in COLUMNAS_SOCIOS if col in detalle.columns]
    st.dataframe(detalle[columnas], use_container_width=True, hide_index=True)


def _mostrar_estado_matriz(resultado: dict) -> None:
    estados = resultado.get("estados_matriz_relevantes") or {}
    if not estados:
        st.info("No hay estados de matriz disponibles.")
        return

    df = pd.DataFrame(
        [{"tipo_vinculo": clave, "estado_matriz": valor} for clave, valor in estados.items()]
    )
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.caption(
        "Este control usa la matriz como fuente preparatoria. No crea cuentas, no registra Caja/Banco "
        "y no genera asientos definitivos."
    )


def mostrar_control_normativo_vinculos_socios(
    empresa_id: int = 1,
    usuario: Optional[str] = None,
) -> None:
    st.markdown("#### Control normativo y operativo de vínculos con socios")

    try:
        resultado = controlar_vinculos_socios(empresa_id=empresa_id)

        if not resultado.get("ok"):
            st.warning(
                "No se pudo ejecutar el control normativo de socios. "
                "La ficha integral y la matriz contable siguen disponibles."
            )
            if resultado.get("error"):
                with st.expander("Detalle técnico", expanded=False):
                    st.code(_texto(resultado.get("error")))
            return

        st.info(
            "Este control cruza la ficha del socio con la matriz contable y el Plan Maestro FF. "
            "Sirve para prevenir errores antes de movimientos reales. No registra operaciones ni genera asientos."
        )

        if int(resultado.get("criticas") or 0) > 0:
            st.error("Hay controles críticos pendientes antes de habilitar movimientos reales con socios.")
        elif int(resultado.get("advertencias") or 0) > 0:
            st.warning("Hay advertencias de preparación para revisar antes de movimientos reales con socios.")
        else:
            st.success("La preparación normativa y operativa de vínculos con socios no presenta observaciones relevantes.")

        _mostrar_metricas(resultado)

        tab_alertas, tab_socios, tab_matriz = st.tabs(
            ["Alertas", "Por socio", "Estado de matriz"]
        )

        with tab_alertas:
            _mostrar_alertas(resultado)

        with tab_socios:
            _mostrar_por_socio(resultado)

        with tab_matriz:
            _mostrar_estado_matriz(resultado)

    except Exception as exc:
        st.warning(
            "No se pudo cargar el control normativo y operativo de vínculos con socios. "
            "Este bloque es auxiliar y no debe impedir operar el resto de Configuración."
        )
        with st.expander("Detalle técnico para diagnóstico", expanded=False):
            st.code(str(exc))