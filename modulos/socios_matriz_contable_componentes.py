from __future__ import annotations

from typing import Any, Optional

import pandas as pd
import streamlit as st

from services.socios_matriz_contable_service import (
    actualizar_vinculo_matriz_contable,
    diagnosticar_matriz_contable_socios,
    listar_candidatas_matriz_contable,
    listar_eventos_matriz_contable_socios,
    listar_matriz_contable_socios,
    obtener_vinculo_matriz_contable,
    restaurar_vinculo_matriz_contable,
)


COLUMNAS_MATRIZ = [
    "grupo",
    "tipo_vinculo",
    "nombre",
    "cuenta_principal_esperada",
    "cuenta_principal_referencia",
    "cuenta_contrapartida_esperada",
    "cuenta_contrapartida_referencia",
    "estado_configuracion_calculado",
    "modulo_origen_futuro",
]


def _texto(valor: Any) -> str:
    if valor is None:
        return ""
    return str(valor).strip()


def _opciones_vinculos(matriz: pd.DataFrame) -> list[tuple[str, str]]:
    if matriz.empty:
        return []
    opciones: list[tuple[str, str]] = []
    for _, fila in matriz.iterrows():
        codigo = _texto(fila.get("tipo_vinculo"))
        nombre = _texto(fila.get("nombre")) or codigo
        grupo = _texto(fila.get("grupo"))
        estado = _texto(fila.get("estado_configuracion_calculado")) or _texto(fila.get("estado_configuracion"))
        etiqueta = f"{grupo} · {nombre}"
        if estado:
            etiqueta += f" · {estado}"
        opciones.append((codigo, etiqueta))
    return opciones


def _mostrar_metricas_matriz(empresa_id: int) -> None:
    diagnostico = diagnosticar_matriz_contable_socios(empresa_id=empresa_id)
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Vínculos", int(diagnostico.get("total") or 0))
    col2.metric("Configurados", int(diagnostico.get("configuradas") or 0))
    col3.metric("Pendientes", int(diagnostico.get("pendientes") or 0))
    col4.metric("% configurado", f"{float(diagnostico.get('porcentaje_configurado') or 0):.0f}%")

    advertencias = diagnostico.get("advertencias") or []
    for advertencia in advertencias:
        st.warning(advertencia)


def _mostrar_tabla_matriz(matriz: pd.DataFrame) -> None:
    if matriz.empty:
        st.info("Todavía no hay vínculos contables preparados.")
        return

    visibles = [col for col in COLUMNAS_MATRIZ if col in matriz.columns]
    st.dataframe(matriz[visibles], use_container_width=True, hide_index=True)


def _mostrar_candidatas(tipo_vinculo: str, empresa_id: int) -> None:
    candidatas = listar_candidatas_matriz_contable(
        tipo_vinculo=tipo_vinculo,
        empresa_id=empresa_id,
        limite=12,
    )

    with st.expander("Cuentas candidatas detectadas", expanded=False):
        st.caption(
            "Estas sugerencias solo ayudan a elegir cuentas del Plan Maestro FF o del Plan de Cuentas de la empresa. "
            "No crean cuentas nuevas y no registran movimientos."
        )

        empresa = candidatas.get("empresa")
        maestro = candidatas.get("maestro")

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Plan de Cuentas de la empresa**")
            if isinstance(empresa, pd.DataFrame) and not empresa.empty:
                columnas = [col for col in ["codigo", "nombre", "uso_operativo_sistema", "puntaje"] if col in empresa.columns]
                st.dataframe(empresa[columnas], use_container_width=True, hide_index=True)
            else:
                st.info("No se detectaron candidatas en cuentas de empresa.")

        with col2:
            st.markdown("**Plan Maestro FF**")
            if isinstance(maestro, pd.DataFrame) and not maestro.empty:
                columnas = [col for col in ["codigo", "nombre", "elemento", "rubro", "saldo_normal", "puntaje"] if col in maestro.columns]
                st.dataframe(maestro[columnas], use_container_width=True, hide_index=True)
            else:
                st.info("No se detectaron candidatas en el Plan Maestro FF.")


def _mostrar_formulario_configuracion(
    tipo_vinculo: str,
    empresa_id: int,
    usuario: Optional[str] = None,
) -> None:
    vinculo = obtener_vinculo_matriz_contable(
        tipo_vinculo=tipo_vinculo,
        empresa_id=empresa_id,
    )
    if not vinculo:
        st.error("No se pudo obtener el vínculo seleccionado.")
        return

    st.markdown(f"##### Configuración preparatoria: {vinculo.get('nombre')}")

    col_a, col_b = st.columns(2)
    with col_a:
        st.caption("Naturaleza económica")
        st.write(_texto(vinculo.get("naturaleza_economica")) or "Sin definición.")
    with col_b:
        st.caption("Tratamiento contable esperado")
        st.write(_texto(vinculo.get("tratamiento_contable")) or "Sin definición.")

    st.info(
        "Esta matriz solo define la relación contable esperada para etapas futuras. "
        "No registra Caja/Banco, no carga compras, no genera pagos y no impacta Libro Diario."
    )

    _mostrar_candidatas(tipo_vinculo=tipo_vinculo, empresa_id=empresa_id)

    with st.form(f"form_matriz_contable_socios_{tipo_vinculo}"):
        st.markdown("**Cuenta principal**")
        col1, col2 = st.columns(2)
        with col1:
            cuenta_maestro_principal_codigo = st.text_input(
                "Código Plan Maestro FF - cuenta principal",
                value=_texto(vinculo.get("cuenta_maestro_principal_codigo")),
                placeholder="Ej.: código del Plan Maestro FF",
            )
        with col2:
            cuenta_empresa_principal_codigo = st.text_input(
                "Código cuenta empresa - cuenta principal",
                value=_texto(vinculo.get("cuenta_empresa_principal_codigo")),
                placeholder="Opcional si ya existe cuenta de empresa",
            )

        st.markdown("**Cuenta relacionada / contrapartida esperada**")
        col3, col4 = st.columns(2)
        with col3:
            cuenta_maestro_contrapartida_codigo = st.text_input(
                "Código Plan Maestro FF - cuenta relacionada",
                value=_texto(vinculo.get("cuenta_maestro_contrapartida_codigo")),
                placeholder="Opcional",
            )
        with col4:
            cuenta_empresa_contrapartida_codigo = st.text_input(
                "Código cuenta empresa - cuenta relacionada",
                value=_texto(vinculo.get("cuenta_empresa_contrapartida_codigo")),
                placeholder="Opcional",
            )

        observaciones = st.text_area(
            "Observaciones de configuración",
            value=_texto(vinculo.get("observaciones")),
            height=90,
            placeholder="Ej.: usar esta cuenta solo para préstamos documentados; revisar con respaldo societario.",
        )

        guardar = st.form_submit_button("Guardar configuración de matriz")

    if guardar:
        resultado = actualizar_vinculo_matriz_contable(
            empresa_id=empresa_id,
            tipo_vinculo=tipo_vinculo,
            cuenta_maestro_principal_codigo=cuenta_maestro_principal_codigo,
            cuenta_empresa_principal_codigo=cuenta_empresa_principal_codigo,
            cuenta_maestro_contrapartida_codigo=cuenta_maestro_contrapartida_codigo,
            cuenta_empresa_contrapartida_codigo=cuenta_empresa_contrapartida_codigo,
            observaciones=observaciones,
            usuario=usuario,
        )
        if resultado.get("ok"):
            st.success(resultado.get("mensaje", "Matriz actualizada correctamente."))
            st.rerun()
        else:
            st.error(resultado.get("mensaje", "No se pudo actualizar la matriz."))

    with st.expander("Restaurar este vínculo a pendiente", expanded=False):
        st.caption(
            "Usar solo si la cuenta fue elegida por error. La acción no borra historia: registra evento de auditoría."
        )
        if st.button("Limpiar cuentas configuradas", key=f"restaurar_matriz_{tipo_vinculo}"):
            resultado = restaurar_vinculo_matriz_contable(
                empresa_id=empresa_id,
                tipo_vinculo=tipo_vinculo,
                usuario=usuario,
            )
            if resultado.get("ok"):
                st.success(resultado.get("mensaje", "Vínculo restaurado."))
                st.rerun()
            else:
                st.error(resultado.get("mensaje", "No se pudo restaurar el vínculo."))


def _mostrar_eventos_matriz(empresa_id: int) -> None:
    eventos = listar_eventos_matriz_contable_socios(empresa_id=empresa_id, limite=200)
    with st.expander("Auditoría de la matriz contable de socios", expanded=False):
        if eventos.empty:
            st.info("Todavía no hay eventos de matriz.")
        else:
            columnas = [col for col in ["fecha_evento", "tipo_vinculo", "evento", "detalle", "usuario"] if col in eventos.columns]
            st.dataframe(eventos[columnas], use_container_width=True, hide_index=True)


def mostrar_matriz_contable_socios(
    empresa_id: int = 1,
    usuario: Optional[str] = None,
) -> None:
    st.markdown("#### Matriz contable de vínculos con socios")

    try:
        st.info(
            "Esta sección prepara la relación entre cada vínculo económico con socios y las cuentas del Plan Maestro FF "
            "o del Plan de Cuentas de la empresa. No registra operaciones ni genera asientos definitivos."
        )

        _mostrar_metricas_matriz(empresa_id=empresa_id)

        matriz = listar_matriz_contable_socios(empresa_id=empresa_id, incluir_inactivas=False)
        _mostrar_tabla_matriz(matriz)

        opciones = _opciones_vinculos(matriz)
        if not opciones:
            _mostrar_eventos_matriz(empresa_id=empresa_id)
            return

        tipo_vinculo = st.selectbox(
            "Seleccionar vínculo para configurar",
            options=[opcion[0] for opcion in opciones],
            format_func=lambda valor: dict(opciones).get(valor, valor),
            key="socios_matriz_contable_tipo_vinculo",
        )

        _mostrar_formulario_configuracion(
            tipo_vinculo=tipo_vinculo,
            empresa_id=empresa_id,
            usuario=usuario,
        )

        _mostrar_eventos_matriz(empresa_id=empresa_id)

    except Exception as exc:
        st.warning(
            "No se pudo cargar la matriz contable de vínculos con socios. "
            "La ficha integral del socio y el resto de Configuración siguen disponibles."
        )
        st.caption(
            "Este bloque es auxiliar y preparatorio. Si falla por datos incompletos del Plan Maestro FF "
            "o del Plan de Cuentas de la empresa, no debe impedir operar el resto del sistema."
        )
        with st.expander("Detalle técnico para diagnóstico", expanded=False):
            st.code(str(exc))
