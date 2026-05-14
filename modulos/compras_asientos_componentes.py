from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from services.compras_asientos_propuestos_service import (
    generar_asientos_propuestos_compras_importadas,
    listar_compras_pendientes_asiento,
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
        "proveedor",
        "cuit",
        "categoria_compra",
        "neto",
        "iva_total",
        "credito_fiscal_computable",
        "percepcion_iva",
        "percepcion_iibb",
        "total",
    ]
    return [col for col in preferidas if col in df.columns]


def _vista_resultados(resultados: list[dict[str, Any]]) -> pd.DataFrame:
    if not resultados:
        return pd.DataFrame(
            columns=[
                "compra_id",
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
                "compra_id": resultado.get("compra_id"),
                "estado": resultado.get("estado"),
                "ok": resultado.get("ok"),
                "asiento_propuesto_id": resultado.get("asiento_propuesto_id"),
                "mensaje": resultado.get("mensaje"),
            }
        )
    return pd.DataFrame(filas)


def mostrar_generacion_asientos_compras_importadas(
    empresa_id: int | None = None,
    usuario: str | None = None,
) -> None:
    empresa_id_final = _empresa_id_actual(empresa_id)
    usuario_final = _usuario_actual(usuario)

    st.divider()
    st.subheader("🧾 Asientos propuestos de compras importadas")

    st.caption(
        "Esta acción toma compras ARCA ya importadas y clasificadas, resuelve cuentas desde "
        "Plan Empresa / Plan Maestro FF y genera propuestas en Bandeja. No escribe directo en Libro Diario."
    )

    try:
        pendientes = listar_compras_pendientes_asiento(empresa_id=empresa_id_final)
    except Exception as exc:
        st.error(f"No se pudieron consultar compras pendientes de asiento: {exc}")
        return

    cantidad = int(len(pendientes)) if isinstance(pendientes, pd.DataFrame) else 0

    col1, col2, col3 = st.columns(3)
    col1.metric("Pendientes", cantidad)
    col2.metric("Destino", "Bandeja")
    col3.metric("Diario directo", "No")

    if cantidad == 0:
        st.success("No hay compras importadas y clasificadas pendientes de asiento propuesto.")
        return

    columnas = _columnas_visibles_pendientes(pendientes)
    if columnas:
        st.dataframe(pendientes[columnas], use_container_width=True, hide_index=True)
    else:
        st.dataframe(pendientes, use_container_width=True, hide_index=True)

    st.warning(
        "Revise que la categoría de compra sea correcta antes de generar propuestas. "
        "Si una compra fue mal clasificada, corrija la categoría antes de enviarla a Bandeja."
    )

    confirmar = st.checkbox(
        "Confirmo que deseo generar asientos propuestos para las compras pendientes",
        key=f"confirmar_asientos_compras_importadas_{empresa_id_final}",
    )

    if not confirmar:
        st.info("Marque la confirmación para habilitar la generación.")
        return

    if st.button(
        "Generar asientos propuestos en Bandeja",
        type="primary",
        use_container_width=True,
        key=f"generar_asientos_compras_importadas_{empresa_id_final}",
    ):
        with st.spinner("Generando asientos propuestos de compras importadas..."):
            resultado = generar_asientos_propuestos_compras_importadas(
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
                "Las compras con error no se contabilizaron ni se enviaron a Libro Diario. "
                "Corrija categoría/cuentas del Plan Empresa y vuelva a generar."
            )
        else:
            st.info("Revise las propuestas generadas en Contabilidad → Bandeja de asientos.")

