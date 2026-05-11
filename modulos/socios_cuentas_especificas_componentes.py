from __future__ import annotations

import pandas as pd
import streamlit as st

from services.socios_cuentas_especificas_service import (
    TIPOS_CUENTA_SOCIO,
    anular_vinculo_cuenta_socio,
    catalogo_tipos_cuentas_socios,
    crear_cuenta_especifica_socio,
    listar_cuentas_especificas_socios,
    listar_eventos_cuentas_especificas_socios,
    listar_modelos_socios,
    obtener_estado_preparacion_socios,
    vincular_cuenta_empresa_existente_socio,
)
from database import conectar


def _usuario_actual() -> str:
    try:
        usuario = st.session_state.get("usuario") or st.session_state.get("username") or "sistema"
        if isinstance(usuario, dict):
            return str(usuario.get("usuario") or usuario.get("email") or usuario.get("nombre") or "sistema")
        return str(usuario or "sistema")
    except Exception:
        return "sistema"


def _df_vacio(df: pd.DataFrame | None) -> bool:
    return df is None or not isinstance(df, pd.DataFrame) or df.empty


def _mostrar_resultado(resultado: dict) -> None:
    if resultado.get("ok"):
        st.success(resultado.get("mensaje") or "Operación realizada correctamente.")
    else:
        errores = resultado.get("errores") or ["No se pudo completar la operación."]
        for error in errores:
            st.error(error)


def _listar_cuentas_empresa_candidatas(empresa_id: int) -> pd.DataFrame:
    conn = conectar()
    try:
        conn.row_factory = None
        filas = conn.execute(
            """
            SELECT id, codigo, nombre, estado, uso_operativo_sistema
            FROM plan_cuentas_empresa
            WHERE empresa_id = ?
              AND estado = 'ACTIVA'
              AND imputable = 1
              AND (
                lower(nombre) LIKE '%socio%'
                OR lower(nombre) LIKE '%accionista%'
                OR lower(nombre) LIKE '%integracion%'
                OR lower(nombre) LIKE '%integración%'
                OR lower(nombre) LIKE '%prestamo%'
                OR lower(nombre) LIKE '%préstamo%'
                OR lower(nombre) LIKE '%retiro%'
                OR lower(nombre) LIKE '%reintegro%'
                OR lower(COALESCE(uso_operativo_sistema, '')) LIKE '%socio%'
              )
            ORDER BY codigo
            """,
            (int(empresa_id),),
        ).fetchall()
        return pd.DataFrame(
            filas,
            columns=["id", "codigo", "nombre", "estado", "uso_operativo_sistema"],
        )
    finally:
        conn.close()


def mostrar_socios_cuentas_especificas(empresa_id: int = 1) -> None:
    st.subheader("Cuentas específicas por socio")
    st.caption(
        "Prepara y vincula cuentas específicas de empresa por socio desde el Plan Maestro FF. "
        "No registra movimientos, no genera asientos y no toca Caja/Banco."
    )

    estado_df = obtener_estado_preparacion_socios(empresa_id=empresa_id)
    modelos_df = listar_modelos_socios(empresa_id=empresa_id)
    vinculos_df = listar_cuentas_especificas_socios(empresa_id=empresa_id)

    total_socios = 0 if _df_vacio(estado_df) else int(estado_df["socio_id"].nunique())
    vinculadas = 0 if _df_vacio(estado_df) else int((estado_df["estado_preparacion"] == "CUENTA_VINCULADA").sum())
    listas = 0 if _df_vacio(estado_df) else int((estado_df["estado_preparacion"] == "LISTA_PARA_CREAR").sum())
    bloqueadas = 0 if _df_vacio(estado_df) else int(estado_df["estado_preparacion"].isin(["MODELO_NO_HABILITADO", "SIN_MODELO"]).sum())

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Socios activos", total_socios)
    col2.metric("Cuentas vinculadas", vinculadas)
    col3.metric("Listas para crear", listas)
    col4.metric("A revisar", bloqueadas)

    if _df_vacio(modelos_df):
        st.warning(
            "No se detectaron cuentas del Plan Maestro FF relacionadas con socios. "
            "Primero debe revisarse el Plan Maestro."
        )
    elif not ((modelos_df["es_cuenta_modelo"].fillna(0).astype(int) == 1) & (modelos_df["permite_copiar_modelo"].fillna(0).astype(int) == 1)).any():
        st.warning(
            "Se detectaron cuentas relacionadas con socios, pero ninguna está habilitada como modelo copiable. "
            "Por seguridad, el sistema no creará cuentas específicas hasta que una cuenta modelo esté marcada como copiable."
        )

    tab_estado, tab_crear, tab_vincular, tab_auditoria = st.tabs(
        [
            "Estado por socio",
            "Crear desde modelo",
            "Vincular existente",
            "Auditoría",
        ]
    )

    with tab_estado:
        st.markdown("#### Preparación por socio")
        if _df_vacio(estado_df):
            st.info("No hay socios activos para preparar cuentas específicas.")
        else:
            columnas = [
                "socio_nombre",
                "socio_cuit",
                "cuenta_requerida",
                "estado_preparacion",
                "cuenta_empresa_codigo",
                "cuenta_empresa_nombre",
                "cuenta_modelo_codigo",
                "cuenta_modelo_nombre",
            ]
            st.dataframe(estado_df[columnas], use_container_width=True, hide_index=True)

        with st.expander("Modelos detectados en Plan Maestro FF", expanded=False):
            if _df_vacio(modelos_df):
                st.info("Sin modelos detectados.")
            else:
                columnas_modelos = [
                    "codigo",
                    "nombre",
                    "tipo_cuenta_sugerida",
                    "es_cuenta_modelo",
                    "permite_copiar_modelo",
                    "estado_modelo",
                ]
                st.dataframe(modelos_df[columnas_modelos], use_container_width=True, hide_index=True)

        with st.expander("Catálogo funcional de cuentas por socio", expanded=False):
            st.dataframe(catalogo_tipos_cuentas_socios(), use_container_width=True, hide_index=True)

    with tab_crear:
        st.markdown("#### Crear cuenta específica desde una cuenta modelo copiable")
        st.info(
            "Esta acción crea una cuenta en el Plan de Cuentas Empresa y la vincula al socio. "
            "No modifica el Plan Maestro y no registra movimientos."
        )

        if _df_vacio(estado_df):
            st.info("No hay socios activos disponibles.")
        else:
            socios_df = estado_df[["socio_id", "socio_nombre", "socio_cuit"]].drop_duplicates().copy()
            socios_df["label"] = socios_df.apply(
                lambda r: f"{r['socio_nombre']} - CUIT {r['socio_cuit'] or 'sin informar'}",
                axis=1,
            )
            socio_label = st.selectbox(
                "Socio/accionista",
                socios_df["label"].tolist(),
                key="socios_ce_socio_crear",
            )
            socio_id = int(socios_df.loc[socios_df["label"] == socio_label, "socio_id"].iloc[0])

            tipo_labels = {datos["nombre"]: tipo for tipo, datos in TIPOS_CUENTA_SOCIO.items()}
            tipo_label = st.selectbox(
                "Cuenta a preparar",
                list(tipo_labels.keys()),
                key="socios_ce_tipo_crear",
            )
            tipo_cuenta = tipo_labels[tipo_label]

            modelos_tipo = modelos_df[modelos_df["tipo_cuenta_sugerida"] == tipo_cuenta] if not _df_vacio(modelos_df) else pd.DataFrame()
            cuenta_modelo_id = None
            if _df_vacio(modelos_tipo):
                st.warning("No hay cuenta del Plan Maestro detectada para este concepto.")
            else:
                modelos_tipo = modelos_tipo.copy()
                modelos_tipo["label"] = modelos_tipo.apply(
                    lambda r: f"{r['codigo']} - {r['nombre']} ({r['estado_modelo']})",
                    axis=1,
                )
                modelo_label = st.selectbox(
                    "Cuenta modelo del Plan Maestro FF",
                    modelos_tipo["label"].tolist(),
                    key="socios_ce_modelo_crear",
                )
                cuenta_modelo_id = int(modelos_tipo.loc[modelos_tipo["label"] == modelo_label, "id"].iloc[0])

            codigo_nuevo = st.text_input(
                "Código nuevo sugerido/opcional",
                value="",
                help="Si se deja vacío, el sistema genera uno desde el código modelo y el CUIT/ID del socio.",
                key="socios_ce_codigo_nuevo",
            )
            nombre_nuevo = st.text_input(
                "Nombre nuevo opcional",
                value="",
                help="Si se deja vacío, el sistema genera un nombre con el socio seleccionado.",
                key="socios_ce_nombre_nuevo",
            )
            motivo = st.text_area(
                "Motivo obligatorio",
                value="Preparación de cuenta específica por socio desde Plan Maestro FF.",
                key="socios_ce_motivo_crear",
            )

            if st.button("Crear y vincular cuenta específica", key="socios_ce_btn_crear"):
                resultado = crear_cuenta_especifica_socio(
                    empresa_id=empresa_id,
                    socio_id=socio_id,
                    tipo_cuenta=tipo_cuenta,
                    cuenta_modelo_id=cuenta_modelo_id,
                    codigo_nuevo=codigo_nuevo,
                    nombre_nuevo=nombre_nuevo,
                    motivo=motivo,
                    usuario=_usuario_actual(),
                )
                _mostrar_resultado(resultado)
                if resultado.get("ok"):
                    st.rerun()

    with tab_vincular:
        st.markdown("#### Vincular una cuenta empresa existente")
        st.caption(
            "Uso controlado para cuentas ya existentes en el Plan de Cuentas Empresa. "
            "No crea cuentas nuevas y no modifica movimientos."
        )
        cuentas_df = _listar_cuentas_empresa_candidatas(empresa_id)
        if _df_vacio(estado_df) or _df_vacio(cuentas_df):
            st.info("No hay socios activos o cuentas candidatas para vincular.")
        else:
            socios_df = estado_df[["socio_id", "socio_nombre", "socio_cuit"]].drop_duplicates().copy()
            socios_df["label"] = socios_df.apply(
                lambda r: f"{r['socio_nombre']} - CUIT {r['socio_cuit'] or 'sin informar'}",
                axis=1,
            )
            socio_label_v = st.selectbox(
                "Socio/accionista",
                socios_df["label"].tolist(),
                key="socios_ce_socio_vincular",
            )
            socio_id_v = int(socios_df.loc[socios_df["label"] == socio_label_v, "socio_id"].iloc[0])

            tipo_labels = {datos["nombre"]: tipo for tipo, datos in TIPOS_CUENTA_SOCIO.items()}
            tipo_label_v = st.selectbox(
                "Concepto de cuenta",
                list(tipo_labels.keys()),
                key="socios_ce_tipo_vincular",
            )
            tipo_cuenta_v = tipo_labels[tipo_label_v]

            cuentas_df = cuentas_df.copy()
            cuentas_df["label"] = cuentas_df.apply(lambda r: f"{r['codigo']} - {r['nombre']}", axis=1)
            cuenta_label = st.selectbox(
                "Cuenta empresa existente",
                cuentas_df["label"].tolist(),
                key="socios_ce_cuenta_existente",
            )
            cuenta_empresa_id = int(cuentas_df.loc[cuentas_df["label"] == cuenta_label, "id"].iloc[0])
            motivo_v = st.text_area(
                "Motivo obligatorio",
                value="Vinculación controlada de cuenta empresa existente a socio.",
                key="socios_ce_motivo_vincular",
            )
            if st.button("Vincular cuenta existente", key="socios_ce_btn_vincular"):
                resultado = vincular_cuenta_empresa_existente_socio(
                    empresa_id=empresa_id,
                    socio_id=socio_id_v,
                    tipo_cuenta=tipo_cuenta_v,
                    cuenta_empresa_id=cuenta_empresa_id,
                    motivo=motivo_v,
                    usuario=_usuario_actual(),
                )
                _mostrar_resultado(resultado)
                if resultado.get("ok"):
                    st.rerun()

        st.markdown("#### Vínculos activos")
        if _df_vacio(vinculos_df):
            st.info("Todavía no hay cuentas específicas vinculadas a socios.")
        else:
            columnas_v = [
                "id",
                "socio_nombre",
                "tipo_cuenta",
                "cuenta_empresa_codigo",
                "cuenta_empresa_nombre",
                "origen",
                "estado",
            ]
            st.dataframe(vinculos_df[columnas_v], use_container_width=True, hide_index=True)
            with st.expander("Anular vínculo por error", expanded=False):
                vinculos_df = vinculos_df.copy()
                vinculos_df["label"] = vinculos_df.apply(
                    lambda r: f"{r['id']} - {r['socio_nombre']} - {r['tipo_cuenta']} - {r['cuenta_empresa_codigo']}",
                    axis=1,
                )
                vinculo_label = st.selectbox(
                    "Vínculo a anular",
                    vinculos_df["label"].tolist(),
                    key="socios_ce_vinculo_anular",
                )
                vinculo_id = int(vinculos_df.loc[vinculos_df["label"] == vinculo_label, "id"].iloc[0])
                motivo_anulacion = st.text_area(
                    "Motivo de anulación obligatorio",
                    value="Corrección de vínculo de cuenta específica por socio.",
                    key="socios_ce_motivo_anular",
                )
                if st.button("Anular vínculo seleccionado", key="socios_ce_btn_anular"):
                    resultado = anular_vinculo_cuenta_socio(
                        empresa_id=empresa_id,
                        vinculo_id=vinculo_id,
                        motivo=motivo_anulacion,
                        usuario=_usuario_actual(),
                    )
                    _mostrar_resultado(resultado)
                    if resultado.get("ok"):
                        st.rerun()

    with tab_auditoria:
        st.markdown("#### Auditoría de cuentas específicas por socio")
        eventos_df = listar_eventos_cuentas_especificas_socios(empresa_id=empresa_id)
        if _df_vacio(eventos_df):
            st.info("Sin eventos registrados para cuentas específicas por socio.")
        else:
            columnas_eventos = [
                "fecha_evento",
                "socio_id",
                "tipo_cuenta",
                "evento",
                "detalle",
                "motivo",
                "usuario",
            ]
            st.dataframe(eventos_df[columnas_eventos], use_container_width=True, hide_index=True)