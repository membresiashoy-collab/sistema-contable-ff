from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd
import streamlit as st

from modulos.socios_matriz_contable_componentes import mostrar_matriz_contable_socios
from modulos.socios_control_vinculos_componentes import mostrar_control_normativo_vinculos_socios
from services.socios_empresa_service import (
    actualizar_ficha_integral_socio,
    catalogo_conceptos_relacion_socios,
    listar_eventos_ficha_socio,
    listar_fichas_socios_empresa,
    obtener_ficha_socio,
    obtener_resumen_socios_pro,
    preparar_cuenta_particular_socio,
)


TIPOS_RELACION = [
    "SOCIO",
    "ACCIONISTA",
    "ASOCIADO",
    "COOPERATIVISTA",
    "TITULAR",
    "TERCERO_RELACIONADO",
]

CONDICIONES_FISCALES = [
    "NO_INFORMADA",
    "RESPONSABLE_INSCRIPTO",
    "MONOTRIBUTO",
    "EXENTO",
    "CONSUMIDOR_FINAL",
    "SUJETO_NO_CATEGORIZADO",
]


def _bool(valor: Any) -> bool:
    try:
        return bool(int(valor or 0))
    except Exception:
        return bool(valor)


def _texto(valor: Any) -> str:
    if valor is None:
        return ""
    return str(valor).strip()


def _indice_opcion(opciones: list[str], valor: Any, default: str) -> int:
    texto = _texto(valor).upper().replace(" ", "_")
    elegido = texto if texto in opciones else default
    return opciones.index(elegido)


def _refrescar(preparar_vista=None) -> None:
    if callable(preparar_vista):
        preparar_vista()


def _mostrar_metricas_resumen(empresa_id: int) -> None:
    resumen = obtener_resumen_socios_pro(empresa_id=empresa_id)
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Socios activos", int(resumen.get("socios_activos") or 0))
    col2.metric("Cuentas particulares", int(resumen.get("cuentas_preparadas") or 0))
    col3.metric("Admiten préstamos", int(resumen.get("admiten_prestamos") or 0))
    col4.metric("Admiten retiros", int(resumen.get("admiten_retiros") or 0))


def _mostrar_tabla_fichas(fichas: pd.DataFrame) -> None:
    columnas = [
        "nombre",
        "cuit",
        "tipo_socio",
        "rol_relacion",
        "porcentaje_participacion",
        "condicion_fiscal",
        "cuenta_particular_habilitada",
        "cuenta_particular_codigo",
        "cuenta_particular_nombre",
        "estado",
    ]
    visibles = [col for col in columnas if col in fichas.columns]
    if visibles:
        st.dataframe(fichas[visibles], use_container_width=True, hide_index=True)


def _mostrar_catalogo_conceptos() -> None:
    with st.expander("Conceptos preparados para futuros movimientos con socios", expanded=False):
        st.caption(
            "Este catálogo solo clasifica la naturaleza futura de los movimientos. "
            "En esta etapa no registra Caja, Banco, compras, pagos ni asientos definitivos."
        )
        catalogo = catalogo_conceptos_relacion_socios()
        if catalogo.empty:
            st.info("Todavía no hay conceptos preparados.")
        else:
            st.dataframe(catalogo, use_container_width=True, hide_index=True)


def _opciones_socios(fichas: pd.DataFrame) -> list[tuple[int, str]]:
    opciones: list[tuple[int, str]] = []
    if fichas.empty:
        return opciones

    for _, fila in fichas.iterrows():
        socio_id = int(fila.get("id"))
        nombre = _texto(fila.get("nombre")) or f"Socio #{socio_id}"
        cuit = _texto(fila.get("cuit"))
        estado = _texto(fila.get("estado"))
        etiqueta = f"{nombre}"
        if cuit:
            etiqueta += f" - CUIT {cuit}"
        if estado and estado != "ACTIVO":
            etiqueta += f" ({estado})"
        opciones.append((socio_id, etiqueta))
    return opciones


def _mostrar_eventos_ficha(socio_id: int, empresa_id: int) -> None:
    eventos = listar_eventos_ficha_socio(socio_id=socio_id, empresa_id=empresa_id)
    with st.expander("Trazabilidad de la ficha integral", expanded=False):
        if eventos.empty:
            st.info("Todavía no hay eventos registrados para esta ficha.")
        else:
            st.dataframe(eventos, use_container_width=True, hide_index=True)


def _mostrar_formulario_ficha(
    ficha: Dict[str, Any],
    empresa_id: int,
    preparar_vista=None,
    usuario: Optional[str] = None,
) -> None:
    socio_id = int(ficha.get("id"))
    nombre = _texto(ficha.get("nombre")) or f"Socio #{socio_id}"

    st.markdown(f"##### Ficha integral: {nombre}")

    with st.form(f"form_ficha_integral_socio_{socio_id}"):
        col1, col2 = st.columns(2)
        with col1:
            rol_relacion = st.selectbox(
                "Rol dentro de la empresa",
                TIPOS_RELACION,
                index=_indice_opcion(TIPOS_RELACION, ficha.get("rol_relacion") or ficha.get("tipo_socio"), "SOCIO"),
            )
            condicion_fiscal = st.selectbox(
                "Condición fiscal del socio",
                CONDICIONES_FISCALES,
                index=_indice_opcion(CONDICIONES_FISCALES, ficha.get("condicion_fiscal"), "NO_INFORMADA"),
            )
            documento = st.text_input("Documento / identificación", value=_texto(ficha.get("documento")))
            actividad_vinculada = st.text_input(
                "Actividad o vínculo económico con la empresa",
                value=_texto(ficha.get("actividad_vinculada")),
                placeholder="Ej.: socio gerente, proveedor vinculado, prestador de servicios",
            )

        with col2:
            email = st.text_input("Email", value=_texto(ficha.get("email")))
            telefono = st.text_input("Teléfono", value=_texto(ficha.get("telefono")))
            domicilio = st.text_input("Domicilio", value=_texto(ficha.get("domicilio")))
            proveedor_vinculado_referencia = st.text_input(
                "Referencia de proveedor vinculado",
                value=_texto(ficha.get("proveedor_vinculado_referencia")),
                placeholder="Opcional. No vincula compras todavía.",
            )

        st.markdown("###### Cuenta particular y usos futuros")
        st.caption(
            "La cuenta particular queda preparada para clasificar préstamos, retiros, reintegros, "
            "honorarios o facturas vinculadas en etapas futuras. No genera movimientos ni asientos."
        )

        cuenta_particular_habilitada = st.checkbox(
            "Preparar cuenta particular del socio",
            value=_bool(ficha.get("cuenta_particular_habilitada")),
        )

        col3, col4 = st.columns(2)
        with col3:
            cuenta_particular_codigo = st.text_input(
                "Referencia interna de cuenta particular",
                value=_texto(ficha.get("cuenta_particular_codigo")),
                placeholder=f"SOCIO-{socio_id:04d}",
            )
        with col4:
            cuenta_particular_nombre = st.text_input(
                "Nombre sugerido de cuenta particular",
                value=_texto(ficha.get("cuenta_particular_nombre")),
                placeholder=f"Cuenta particular - {nombre}",
            )

        cuenta_particular_significado = st.text_area(
            "Significado del saldo / uso de control",
            value=_texto(ficha.get("cuenta_particular_significado")),
            height=90,
        )

        col5, col6, col7 = st.columns(3)
        with col5:
            admite_prestamos = st.checkbox("Puede registrar préstamos de socio", value=_bool(ficha.get("admite_prestamos", 1)))
            admite_retiros = st.checkbox("Puede registrar retiros de socio", value=_bool(ficha.get("admite_retiros", 1)))
        with col6:
            admite_reintegros = st.checkbox("Puede registrar reintegros", value=_bool(ficha.get("admite_reintegros", 1)))
            admite_honorarios = st.checkbox("Puede registrar honorarios/servicios", value=_bool(ficha.get("admite_honorarios", 1)))
        with col7:
            admite_facturas_proveedor = st.checkbox(
                "Puede vincular facturas de proveedor",
                value=_bool(ficha.get("admite_facturas_proveedor", 1)),
            )

        observaciones_ficha = st.text_area(
            "Observaciones de ficha integral",
            value=_texto(ficha.get("observaciones_ficha")),
            height=100,
        )

        guardar = st.form_submit_button("Guardar ficha integral")

    if guardar:
        resultado = actualizar_ficha_integral_socio(
            socio_id=socio_id,
            empresa_id=empresa_id,
            rol_relacion=rol_relacion,
            condicion_fiscal=condicion_fiscal,
            documento=documento,
            email=email,
            telefono=telefono,
            domicilio=domicilio,
            actividad_vinculada=actividad_vinculada,
            proveedor_vinculado_referencia=proveedor_vinculado_referencia,
            cuenta_particular_habilitada=cuenta_particular_habilitada,
            cuenta_particular_codigo=cuenta_particular_codigo,
            cuenta_particular_nombre=cuenta_particular_nombre,
            cuenta_particular_significado=cuenta_particular_significado,
            admite_prestamos=admite_prestamos,
            admite_retiros=admite_retiros,
            admite_reintegros=admite_reintegros,
            admite_honorarios=admite_honorarios,
            admite_facturas_proveedor=admite_facturas_proveedor,
            observaciones_ficha=observaciones_ficha,
            usuario=usuario,
        )
        if resultado.get("ok"):
            st.success(resultado.get("mensaje"))
            _refrescar(preparar_vista)
        else:
            st.error(resultado.get("mensaje", "No se pudo actualizar la ficha integral."))

    col_accion, col_info = st.columns([1, 2])
    with col_accion:
        if st.button("Preparar cuenta particular", key=f"preparar_cuenta_particular_{socio_id}"):
            resultado = preparar_cuenta_particular_socio(
                socio_id=socio_id,
                empresa_id=empresa_id,
                usuario=usuario,
            )
            if resultado.get("ok"):
                st.success(resultado.get("mensaje"))
                _refrescar(preparar_vista)
            else:
                st.error(resultado.get("mensaje", "No se pudo preparar la cuenta particular."))
    with col_info:
        st.caption(
            "Esta acción solo deja preparada una referencia interna. "
            "No crea cuentas contables en el Plan de Cuentas y no registra movimientos."
        )

    _mostrar_eventos_ficha(socio_id=socio_id, empresa_id=empresa_id)


def mostrar_socios_empresa_pro(
    empresa_id: int = 1,
    preparar_vista=None,
    usuario: Optional[str] = None,
) -> None:
    st.markdown("#### Ficha integral y cuenta particular")
    st.info(
        "Esta sección amplía la ficha del socio para futuros movimientos societarios y económicos. "
        "No registra Caja/Banco, no carga compras, no emite pagos y no genera asientos definitivos."
    )

    _mostrar_metricas_resumen(empresa_id)

    fichas = listar_fichas_socios_empresa(empresa_id=empresa_id, incluir_bajas=True)

    if fichas.empty:
        st.warning("Primero cargá socios/accionistas en la sección Socios.")
        _mostrar_catalogo_conceptos()
        mostrar_matriz_contable_socios(empresa_id=empresa_id, usuario=usuario)
        mostrar_control_normativo_vinculos_socios(empresa_id=empresa_id, usuario=usuario)
        return

    _mostrar_tabla_fichas(fichas)
    _mostrar_catalogo_conceptos()
    mostrar_matriz_contable_socios(empresa_id=empresa_id, usuario=usuario)

    activos = fichas[fichas["estado"] == "ACTIVO"] if "estado" in fichas.columns else fichas
    opciones = _opciones_socios(activos)

    if not opciones:
        st.warning("No hay socios activos disponibles para editar la ficha integral.")
        return

    socio_id = st.selectbox(
        "Seleccionar socio para completar ficha integral",
        options=[opcion[0] for opcion in opciones],
        format_func=lambda valor: dict(opciones).get(valor, f"Socio #{valor}"),
    )

    ficha = obtener_ficha_socio(socio_id=int(socio_id), empresa_id=empresa_id)
    if not ficha:
        st.error("No se pudo obtener la ficha del socio seleccionado.")
        return

    _mostrar_formulario_ficha(
        ficha=ficha,
        empresa_id=empresa_id,
        preparar_vista=preparar_vista,
        usuario=usuario,
    )