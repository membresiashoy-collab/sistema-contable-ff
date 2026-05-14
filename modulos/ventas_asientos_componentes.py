from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from services.ventas_asientos_propuestos_service import (
    generar_asientos_propuestos_ventas_importadas,
    listar_ventas_pendientes_asiento,
)


def _empresa_id_actual(empresa_id: int | None = None) -> int:
    if empresa_id is not None:
        try:
            return max(int(empresa_id), 1)
        except Exception:
            return 1

    for clave in ("empresa_id", "empresa_actual_id", "id_empresa"):
        valor = st.session_state.get(clave)
        if valor:
            try:
                return max(int(valor), 1)
            except Exception:
                continue
    return 1


def _usuario_actual(usuario: str | None = None) -> str:
    if usuario:
        return str(usuario)
    for clave in ("usuario", "username", "usuario_actual", "email_usuario"):
        valor = st.session_state.get(clave)
        if valor:
            return str(valor)
    return "sistema"


def _columnas_visibles_pendientes(df: pd.DataFrame) -> list[str]:
    preferidas = [
        "id",
        "fecha",
        "tipo",
        "punto_venta",
        "numero",
        "cliente",
        "cuit",
        "actividad_venta_nombre",
        "tipo_venta",
        "tratamiento_iva_venta",
        "neto",
        "iva",
        "total",
        "archivo",
    ]
    return [col for col in preferidas if col in df.columns]


def _preparar_vista_pendientes(df: pd.DataFrame) -> pd.DataFrame:
    columnas = _columnas_visibles_pendientes(df)
    vista = df[columnas].copy() if columnas else df.copy()
    return vista.rename(
        columns={
            "actividad_venta_nombre": "agrupacion_interna",
            "tipo_venta": "tipo_fiscal_contable",
            "tratamiento_iva_venta": "tratamiento_iva",
        }
    )


def _vista_resultados(resultados: list[dict[str, Any]]) -> pd.DataFrame:
    if not resultados:
        return pd.DataFrame(
            columns=[
                "venta_id",
                "estado",
                "ok",
                "asiento_propuesto_id",
                "mensaje",
            ]
        )

    filas = []
    for resultado in resultados:
        filas.append(
            {
                "venta_id": resultado.get("venta_id"),
                "estado": resultado.get("estado"),
                "ok": resultado.get("ok"),
                "asiento_propuesto_id": resultado.get("asiento_propuesto_id"),
                "mensaje": resultado.get("mensaje"),
            }
        )
    return pd.DataFrame(filas)


def mostrar_generacion_asientos_ventas_importadas(
    empresa_id: int | None = None,
    usuario: str | None = None,
) -> None:
    empresa_id_final = _empresa_id_actual(empresa_id)
    usuario_final = _usuario_actual(usuario)

    st.divider()
    st.subheader("🧾 Asientos propuestos de ventas importadas/manuales")

    st.caption(
        "Esta acción toma ventas con agrupación interna y tipo fiscal/contable asignados, "
        "resuelve cuentas desde Plan Empresa / Plan Maestro FF y genera propuestas en Bandeja. "
        "La agrupación comercial no define la cuenta contable. No escribe directo en Libro Diario."
    )

    try:
        pendientes = listar_ventas_pendientes_asiento(empresa_id=empresa_id_final)
    except Exception as exc:
        st.error(f"No se pudieron consultar ventas pendientes de asiento: {exc}")
        return

    cantidad = int(len(pendientes)) if isinstance(pendientes, pd.DataFrame) else 0

    col1, col2, col3 = st.columns(3)
    col1.metric("Pendientes", cantidad)
    col2.metric("Destino", "Bandeja")
    col3.metric("Diario directo", "No")

    if cantidad == 0:
        st.success("No hay ventas con tipo fiscal/contable pendiente de asiento propuesto.")
        st.info("Si hay ventas cargadas sin agrupación, asigná primero una agrupación interna de venta.")
        return

    st.dataframe(_preparar_vista_pendientes(pendientes), use_container_width=True, hide_index=True)

    st.warning(
        "Revisá que la agrupación, el tipo fiscal/contable y el tratamiento de IVA sean correctos. "
        "Si una venta fue mal clasificada, corregila antes de enviarla a Bandeja."
    )

    confirmar = st.checkbox(
        "Confirmo que deseo generar asientos propuestos para las ventas pendientes",
        key=f"confirmar_asientos_ventas_importadas_{empresa_id_final}",
    )

    if not confirmar:
        st.info("Marcá la confirmación para habilitar la generación.")
        return

    if st.button(
        "Generar asientos propuestos de Ventas en Bandeja",
        type="primary",
        use_container_width=True,
        key=f"generar_asientos_ventas_importadas_{empresa_id_final}",
    ):
        with st.spinner("Generando asientos propuestos de ventas importadas/manuales..."):
            resultado = generar_asientos_propuestos_ventas_importadas(
                empresa_id=empresa_id_final,
                usuario=usuario_final,
            )

        if resultado.get("ok"):
            st.success(
                "Proceso finalizado: "
                f"{resultado.get('generados', 0)} generados, "
                f"{resultado.get('ya_existentes', 0)} ya existentes, "
                f"{resultado.get('errores', 0)} errores."
            )
        else:
            st.error(
                "El proceso finalizó con errores: "
                f"{resultado.get('generados', 0)} generados, "
                f"{resultado.get('errores', 0)} errores."
            )

        vista = _vista_resultados(resultado.get("resultados", []))
        st.dataframe(vista, use_container_width=True, hide_index=True)

        if resultado.get("errores", 0):
            st.info(
                "Las ventas con error no se contabilizaron ni se enviaron a Libro Diario. "
                "Corregí tipo fiscal, tratamiento IVA o cuentas del Plan Empresa y volvé a generar."
            )
        else:
            st.info("Revisá las propuestas generadas en Contabilidad → Bandeja de asientos.")