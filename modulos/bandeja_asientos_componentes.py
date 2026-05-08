import streamlit as st
import pandas as pd

from core.exportadores import exportar_excel
from core.numeros import moneda
from core.ui import preparar_vista

from services.asientos_propuestos_service import (
    ESTADO_CONTABILIZADO,
    ESTADO_PROPUESTO,
    ESTADO_RECHAZADO,
    ESTADO_REVERSADO,
    asegurar_estructura_bandeja_asientos,
    contabilizar_asiento_bandeja,
    contabilizar_asientos_bandeja_masivo,
    listar_bandeja_asientos_propuestos,
    listar_eventos_bandeja,
    listar_lotes_bandeja,
    obtener_asiento_bandeja,
    obtener_resumen_bandeja_asientos,
    prevalidar_asientos_bandeja,
    rechazar_asiento_bandeja,
    reversar_asiento_bandeja,
)


# ======================================================
# CONTABILIDAD PRO - COMPONENTE UI
# Bandeja de asientos propuestos
# ======================================================
#
# Este componente pertenece a modulos/ porque es pantalla Streamlit.
# La lógica de negocio queda en services/asientos_propuestos_service.py.
#
# Criterio contable:
# - Nada pasa a Libro Diario sin revisión.
# - Una propuesta pendiente puede contabilizarse o rechazarse con motivo.
# - Un asiento ya contabilizado no se borra: se reversa con asiento inverso.
# - Se muestran fuentes centrales e IVA sin duplicarlas.
# ======================================================


ORIGENES_BANDEJA_ASIENTOS = [
    "Todos",
    "APERTURA",
    "CAPITAL_SOCIAL",
    "SUSCRIPCION_CAPITAL",
    "INTEGRACION_CAPITAL",
    "APORTE_SOCIO",
    "APORTE_IRREVOCABLE",
    "PRESTAMO_SOCIO",
    "AJUSTE_INICIAL",
    "IVA_CIERRE",
    "IVA_PAGO",
    "COBRANZA",
    "PAGO_PROVEEDOR",
    "BANCO",
    "CAJA",
    "CONCILIACION",
    "SUELDOS",
]


def _texto(valor):
    if valor is None:
        return ""
    try:
        if pd.isna(valor):
            return ""
    except Exception:
        pass
    return str(valor).strip()


def _normalizar_importe(valor):
    try:
        if valor is None or pd.isna(valor):
            return 0.0
        return round(float(valor), 2)
    except Exception:
        return 0.0


def _fecha_mostrar_argentina(valor):
    if valor is None:
        return ""

    try:
        if pd.isna(valor):
            return ""
    except Exception:
        pass

    texto = str(valor).strip()
    if not texto:
        return ""

    try:
        fecha = pd.to_datetime(texto, errors="coerce")
        if pd.isna(fecha):
            return texto
        return fecha.strftime("%d/%m/%Y")
    except Exception:
        return texto


def _empresa_actual_id_default():
    return int(st.session_state.get("empresa_id", 1) or 1)


def _usuario_actual_nombre_default():
    usuario = st.session_state.get("usuario") or {}
    nombre = usuario.get("nombre") or usuario.get("email") or usuario.get("usuario")
    return str(nombre).strip() if nombre else None


def _formatear_fuente_asiento(fuente_clave):
    texto = str(fuente_clave or "")

    if texto.startswith("CENTRAL:"):
        return f"Asiento origen #{texto.split(':', 1)[1]}"

    if texto.startswith("IVA:"):
        partes = texto.split(":")
        if len(partes) >= 4:
            cierre = partes[1]
            pago = partes[2]
            tipo = ":".join(partes[3:])
            if pago and pago != "0":
                return f"IVA pago #{pago} · {tipo}"
            return f"IVA cierre #{cierre} · {tipo}"

    return texto


def _vista_bandeja_asientos(df):
    if df is None or df.empty:
        return pd.DataFrame()

    vista = df.copy()

    for columna in [
        "fecha",
        "fecha_creacion",
        "fecha_contabilizacion",
        "fecha_reversion",
    ]:
        if columna in vista.columns:
            vista[columna] = vista[columna].apply(_fecha_mostrar_argentina)

    columnas_base = [
        "fuente_clave",
        "fecha",
        "origen",
        "tipo_asiento",
        "descripcion",
        "estado",
        "total_debe",
        "total_haber",
        "diferencia",
        "id_asiento_libro_diario",
        "id_asiento_reversion_libro_diario",
        "fecha_contabilizacion",
    ]

    for columna in columnas_base:
        if columna not in vista.columns:
            vista[columna] = ""

    vista = vista[columnas_base].rename(columns={
        "fuente_clave": "Clave",
        "fecha": "Fecha",
        "origen": "Origen",
        "tipo_asiento": "Tipo",
        "descripcion": "Descripción",
        "estado": "Estado",
        "total_debe": "Debe",
        "total_haber": "Haber",
        "diferencia": "Diferencia",
        "id_asiento_libro_diario": "Asiento Libro Diario",
        "id_asiento_reversion_libro_diario": "Asiento reverso",
        "fecha_contabilizacion": "Fecha contabilización",
    })

    vista["Clave"] = vista["Clave"].apply(_formatear_fuente_asiento)

    return vista


def _detalle_asiento_dataframe(asiento):
    detalle = pd.DataFrame((asiento or {}).get("detalle") or [])

    if detalle.empty:
        return detalle

    for columna in [
        "renglon",
        "cuenta_codigo",
        "cuenta_nombre",
        "debe",
        "haber",
        "glosa",
    ]:
        if columna not in detalle.columns:
            detalle[columna] = ""

    detalle = detalle[[
        "renglon",
        "cuenta_codigo",
        "cuenta_nombre",
        "debe",
        "haber",
        "glosa",
    ]].rename(columns={
        "renglon": "Renglón",
        "cuenta_codigo": "Código",
        "cuenta_nombre": "Cuenta",
        "debe": "Debe",
        "haber": "Haber",
        "glosa": "Glosa",
    })

    return detalle


def _mostrar_resumen_bandeja(resumen):
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Total propuestas", resumen.get("total", 0))
    c2.metric("Pendientes de pase", resumen.get("pendientes", 0))
    c3.metric("Contabilizados", resumen.get("contabilizados", 0))
    c4.metric("Anulados", resumen.get("anulados", 0))
    c5.metric("Rechazados", resumen.get("rechazados", 0))
    c6.metric("Revertidos", resumen.get("reversados", 0))

    c1.metric("Total", resumen.get("total", 0))
    c2.metric("Pendientes de pase", resumen.get("pendientes", 0))
    c3.metric("Contabilizados", resumen.get("contabilizados", 0))
    c4.metric("Rechazados", resumen.get("rechazados", 0))
    c5.metric("Reversados", resumen.get("reversados", 0))


def _mostrar_resultado_prevalidacion(resultado):
    if not resultado:
        return

    if resultado.get("ok"):
        st.success(resultado.get("mensaje", "Prevalidación correcta."))
    else:
        st.warning(resultado.get("mensaje", "La prevalidación detectó observaciones."))

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Solicitados", resultado.get("cantidad_solicitada", 0))
    c2.metric("Válidos", resultado.get("cantidad_valida", 0))
    c3.metric("Con error", resultado.get("cantidad_error", 0))
    c4.metric("Total Debe", moneda(resultado.get("total_debe", 0)))
    c5.metric("Total Haber", moneda(resultado.get("total_haber", 0)))

    diferencia = _normalizar_importe(resultado.get("diferencia"))
    if abs(diferencia) > 0.01:
        st.error(f"Diferencia global: {moneda(diferencia)}")
    else:
        st.caption("Diferencia global: $ 0,00")

    origenes = resultado.get("origenes") or []
    periodos = resultado.get("periodos") or []
    fuentes = resultado.get("fuentes") or []

    if origenes or periodos or fuentes:
        st.caption(
            " · ".join([
                f"Orígenes: {', '.join(origenes)}" if origenes else "",
                f"Fuentes: {', '.join(fuentes)}" if fuentes else "",
                f"Períodos: {', '.join(periodos)}" if periodos else "",
            ]).strip(" · ")
        )

    errores = pd.DataFrame(resultado.get("errores") or [])
    if not errores.empty:
        with st.expander("Ver asientos con error", expanded=True):
            st.dataframe(preparar_vista(errores), use_container_width=True)


def _mostrar_lotes_recientes(empresa_id):
    with st.expander("Lotes recientes de contabilización", expanded=False):
        lotes = listar_lotes_bandeja(empresa_id=empresa_id, limite=20)

        if lotes.empty:
            st.info("Todavía no hay lotes de contabilización masiva.")
            return

        vista = lotes.copy()
        if "fecha_lote" in vista.columns:
            vista["fecha_lote"] = vista["fecha_lote"].apply(_fecha_mostrar_argentina)

        st.dataframe(preparar_vista(vista), use_container_width=True)


def _mostrar_acciones_masivas(df, empresa_id, usuario, estado, origen, fuente, key_prefix):
    pendientes = df[df["estado"].fillna("").astype(str).str.upper() == ESTADO_PROPUESTO].copy()

    with st.expander("Acciones masivas controladas", expanded=False):
        st.caption(
            "Usá esta sección cuando haya muchos asientos propuestos. "
            "El sistema prevalidará que cada asiento cuadre individualmente antes de pasarlo al Libro Diario."
        )

        if pendientes.empty:
            st.info("Con los filtros actuales no hay asientos pendientes de pase para contabilizar masivamente.")
            return

        opciones = pendientes["fuente_clave"].dropna().astype(str).tolist()

        c1, c2, c3 = st.columns(3)
        c1.metric("Pendientes visibles", len(opciones))
        c2.metric("Debe visible", moneda(pendientes["total_debe"].sum()))
        c3.metric("Haber visible", moneda(pendientes["total_haber"].sum()))

        modo = st.radio(
            "Alcance de la acción",
            ["Seleccionados manualmente", "Todos los propuestos filtrados"],
            horizontal=True,
            key=f"{key_prefix}_masivo_modo",
        )

        seleccionados = []
        todos_los_filtrados = modo == "Todos los propuestos filtrados"

        if todos_los_filtrados:
            st.warning(
                "Vas a operar sobre todos los asientos pendientes de pase que cumplen los filtros actuales. "
                "No se incluyen contabilizados, rechazados, anulados ni reversados."
            )
            seleccionados = opciones
        else:
            seleccionados = st.multiselect(
                "Asientos a contabilizar",
                opciones,
                format_func=_formatear_fuente_asiento,
                key=f"{key_prefix}_masivo_seleccion",
            )

        requiere_texto = len(seleccionados) >= 50
        texto_confirmacion = ""
        confirmar = st.checkbox(
            "Confirmo que revisé el resumen y quiero avanzar con esta acción masiva",
            key=f"{key_prefix}_masivo_confirmar",
        )

        if requiere_texto:
            texto_confirmacion = st.text_input(
                "Por seguridad, escribí CONTABILIZAR",
                key=f"{key_prefix}_masivo_texto_confirmacion",
            )

        col_prevalidar, col_contabilizar = st.columns(2)

        with col_prevalidar:
            if st.button(
                "Prevalidar selección",
                use_container_width=True,
                key=f"{key_prefix}_masivo_prevalidar",
            ):
                resultado = prevalidar_asientos_bandeja(
                    fuente_claves=seleccionados,
                    empresa_id=empresa_id,
                    todos_los_filtrados=False,
                )
                st.session_state[f"{key_prefix}_ultima_prevalidacion"] = resultado

        with col_contabilizar:
            if st.button(
                "Contabilizar selección",
                type="primary",
                use_container_width=True,
                key=f"{key_prefix}_masivo_contabilizar",
            ):
                if not confirmar:
                    st.error("Marcá la confirmación antes de contabilizar masivamente.")
                else:
                    resultado = contabilizar_asientos_bandeja_masivo(
                        fuente_claves=seleccionados,
                        empresa_id=empresa_id,
                        usuario=usuario,
                        todos_los_filtrados=False,
                        confirmar_texto=texto_confirmacion,
                    )
                    if resultado.get("ok"):
                        st.success(resultado.get("mensaje", "Lote contabilizado correctamente."))
                        st.rerun()
                    else:
                        st.error(resultado.get("mensaje", "No se pudo contabilizar el lote."))
                        st.session_state[f"{key_prefix}_ultima_prevalidacion"] = resultado

        ultima = st.session_state.get(f"{key_prefix}_ultima_prevalidacion")
        if ultima:
            _mostrar_resultado_prevalidacion(ultima)


def _mostrar_estado_asiento(asiento):
    estado = str((asiento or {}).get("estado") or "").upper()

    if estado == ESTADO_PROPUESTO:
        st.warning("Este asiento está pendiente de pase. Todavía no impactó en Libro Diario.")
    elif estado == ESTADO_CONTABILIZADO:
        st.success("Este asiento ya fue pasado al Libro Diario.")
    elif estado == ESTADO_REVERSADO:
        st.info("Este asiento fue contabilizado y luego reversado con trazabilidad.")
    elif estado == ESTADO_RECHAZADO:
        st.error("Este asiento fue rechazado. No impacta en Libro Diario.")
    elif estado == "ANULADO":
        st.error("Este asiento está anulado. No impacta en Libro Diario.")
    else:
        st.caption(f"Estado actual: {estado or 'sin estado'}")


def _mostrar_auditoria_asiento(fuente_clave):
    with st.expander("Auditoría de la bandeja / eventos técnicos", expanded=False):
        eventos = listar_eventos_bandeja(fuente_clave)

        if eventos.empty:
            st.info("Sin eventos registrados para este asiento.")
            return

        vista_eventos = eventos.copy()

        if "fecha_evento" in vista_eventos.columns:
            vista_eventos["fecha_evento"] = vista_eventos["fecha_evento"].apply(_fecha_mostrar_argentina)

        st.dataframe(
            preparar_vista(vista_eventos),
            use_container_width=True,
        )


def _mostrar_acciones_pendiente(fuente_clave, usuario, key_prefix):
    st.markdown("### Decisión contable")

    st.caption(
        "La contabilización genera el asiento definitivo en Libro Diario y marca esta propuesta como contabilizada. "
        "El rechazo corresponde solo cuando la propuesta no debe pasar a contabilidad."
    )

    confirmar = st.checkbox(
        "Confirmo que revisé el asiento y quiero tomar una decisión",
        key=f"{key_prefix}_confirmar_decision_{fuente_clave}",
    )

    col1, col2 = st.columns(2)

    with col1:
        if st.button(
            "Contabilizar en Libro Diario",
            type="primary",
            use_container_width=True,
            key=f"{key_prefix}_contabilizar_{fuente_clave}",
        ):
            if not confirmar:
                st.error("Marcá la confirmación antes de contabilizar.")
            else:
                resultado = contabilizar_asiento_bandeja(
                    fuente_clave=fuente_clave,
                    usuario=usuario,
                )
                if resultado.get("ok"):
                    st.success(resultado.get("mensaje", "Asiento contabilizado correctamente."))
                    st.rerun()
                else:
                    st.error(resultado.get("mensaje", "No se pudo contabilizar el asiento."))

    with col2:
        motivo_rechazo = st.text_input(
            "Motivo de rechazo",
            key=f"{key_prefix}_motivo_rechazo_{fuente_clave}",
            placeholder="Ej.: generado por error / corresponde corregir origen",
        )

        if st.button(
            "Rechazar propuesta",
            use_container_width=True,
            key=f"{key_prefix}_rechazar_{fuente_clave}",
        ):
            if not confirmar:
                st.error("Marcá la confirmación antes de rechazar.")
            else:
                resultado = rechazar_asiento_bandeja(
                    fuente_clave=fuente_clave,
                    motivo=motivo_rechazo,
                    usuario=usuario,
                )
                if resultado.get("ok"):
                    st.success(resultado.get("mensaje", "Asiento rechazado correctamente."))
                    st.rerun()
                else:
                    st.error(resultado.get("mensaje", "No se pudo rechazar el asiento."))


def _mostrar_acciones_contabilizado(fuente_clave, usuario, key_prefix):
    st.markdown("### Reverso controlado")

    st.warning(
        "Este asiento ya impactó en Libro Diario. No se borra ni se pisa: "
        "si fue un error, corresponde generar un reverso contable."
    )

    motivo_reverso = st.text_input(
        "Motivo del reverso",
        key=f"{key_prefix}_motivo_reverso_{fuente_clave}",
        placeholder="Ej.: contabilizado por error / rectificación documentada",
    )

    confirmar_reverso = st.checkbox(
        "Confirmo que quiero generar un reverso contable",
        key=f"{key_prefix}_confirmar_reverso_{fuente_clave}",
    )

    if st.button(
        "Generar reverso controlado",
        type="primary",
        use_container_width=True,
        key=f"{key_prefix}_reversar_{fuente_clave}",
    ):
        if not confirmar_reverso:
            st.error("Marcá la confirmación antes de reversar.")
        else:
            resultado = reversar_asiento_bandeja(
                fuente_clave=fuente_clave,
                motivo=motivo_reverso,
                usuario=usuario,
            )
            if resultado.get("ok"):
                st.success(resultado.get("mensaje", "Asiento reversado correctamente."))
                st.rerun()
            else:
                st.error(resultado.get("mensaje", "No se pudo reversar el asiento."))


def _mostrar_detalle_y_decision(fuente_clave, usuario, key_prefix):
    asiento = obtener_asiento_bandeja(fuente_clave)

    if not asiento:
        st.error("No se encontró el asiento seleccionado.")
        return

    estado = str(asiento.get("estado") or "").upper()
    descripcion = asiento.get("descripcion") or ""
    origen = asiento.get("origen") or ""
    tipo = asiento.get("tipo_asiento") or ""

    st.markdown("### Revisión del asiento seleccionado")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Estado", estado)
    c2.metric("Origen", origen)
    c3.metric("Debe", moneda(asiento.get("total_debe") or 0))
    c4.metric("Haber", moneda(asiento.get("total_haber") or 0))

    st.caption(
        f"Fuente: **{asiento.get('fuente')}** · Tipo: **{tipo}** · "
        f"Fecha: **{_fecha_mostrar_argentina(asiento.get('fecha'))}**"
    )

    if descripcion:
        st.info(descripcion)

    detalle = _detalle_asiento_dataframe(asiento)

    if detalle.empty:
        st.warning("El asiento no tiene detalle contable.")
    else:
        st.dataframe(
            preparar_vista(detalle),
            use_container_width=True,
        )

    diferencia = round(
        _normalizar_importe(asiento.get("total_debe")) - _normalizar_importe(asiento.get("total_haber")),
        2,
    )

    if abs(diferencia) > 0.01:
        st.error(f"El asiento no está cuadrado. Diferencia: {moneda(diferencia)}")
    else:
        st.success("Control de cuadre correcto: Debe = Haber.")

    _mostrar_estado_asiento(asiento)
    _mostrar_auditoria_asiento(fuente_clave)

    st.divider()

    if estado == ESTADO_PROPUESTO:
        _mostrar_acciones_pendiente(fuente_clave, usuario, key_prefix)
    elif estado == ESTADO_CONTABILIZADO:
        _mostrar_acciones_contabilizado(fuente_clave, usuario, key_prefix)
    else:
        st.info("Este estado no permite acciones operativas desde la bandeja.")


def mostrar_bandeja_asientos_propuestos(
    empresa_id=None,
    usuario=None,
    compacta=False,
    key_prefix="bandeja_asientos",
):
    """
    Pantalla reutilizable de bandeja de asientos propuestos.

    Puede usarse:
    - como pestaña propia de Contabilidad;
    - dentro de Inicio Contable;
    - en futuras pantallas de control contable.
    """
    empresa_id = int(empresa_id or _empresa_actual_id_default())
    usuario = usuario or _usuario_actual_nombre_default()

    asegurar_estructura_bandeja_asientos()

    if not compacta:
        st.subheader("🧾 Bandeja de asientos propuestos")

    st.caption(
        "Centro de control contable: las propuestas se revisan acá antes de pasar al Libro Diario. "
        "Incluye asientos de Inicio Contable / Capital y asientos propuestos de IVA Cierre / IVA Pago."
    )

    resumen = obtener_resumen_bandeja_asientos(empresa_id=empresa_id)
    _mostrar_resumen_bandeja(resumen)

    st.divider()

    col1, col2, col3 = st.columns(3)

    with col1:
        estado = st.selectbox(
            "Estado",
            ["PROPUESTO", "Todos", "CONTABILIZADO", "RECHAZADO", "ANULADO", "REVERSADO"],
            key=f"{key_prefix}_estado",
        )

    with col2:
        origen = st.selectbox(
            "Origen",
            ORIGENES_BANDEJA_ASIENTOS,
            key=f"{key_prefix}_origen",
        )

    with col3:
        fuente = st.selectbox(
            "Fuente",
            ["Todas", "CENTRAL", "IVA"],
            key=f"{key_prefix}_fuente",
        )

    df = listar_bandeja_asientos_propuestos(
        empresa_id=empresa_id,
        estado=None if estado == "Todos" else estado,
        origen=None if origen == "Todos" else origen,
        fuente=None if fuente == "Todas" else fuente,
        incluir_anulados=True,
    )

    if df.empty:
        st.info("No hay asientos propuestos con esos filtros.")
        return

    vista = _vista_bandeja_asientos(df)

    st.dataframe(
        preparar_vista(vista),
        use_container_width=True,
    )

    excel = exportar_excel({"Bandeja asientos": vista})

    st.download_button(
        "Descargar bandeja Excel",
        data=excel,
        file_name="bandeja_asientos_propuestos.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=f"{key_prefix}_descargar_excel",
    )

    _mostrar_acciones_masivas(
        df=df,
        empresa_id=empresa_id,
        usuario=usuario,
        estado=estado,
        origen=None if origen == "Todos" else origen,
        fuente=None if fuente == "Todas" else fuente,
        key_prefix=key_prefix,
    )

    _mostrar_lotes_recientes(empresa_id)

    st.divider()

    opciones = df["fuente_clave"].dropna().astype(str).tolist()

    if not opciones:
        st.info("No hay claves de asiento para revisar.")
        return

    seleccion = st.selectbox(
        "Seleccioná un asiento para revisar / decidir",
        opciones,
        format_func=_formatear_fuente_asiento,
        key=f"{key_prefix}_fuente_clave",
    )

    _mostrar_detalle_y_decision(
        fuente_clave=seleccion,
        usuario=usuario,
        key_prefix=key_prefix,
    )


def mostrar_bandeja_asientos_propuestos_ui(empresa_id=None, usuario=None, key_prefix="bandeja_asientos"):
    """
    Alias explícito para usar desde modulos/reportes.py.

    Mantiene estable el nombre público del componente aunque internamente
    la función principal se llame mostrar_bandeja_asientos_propuestos().
    """
    return mostrar_bandeja_asientos_propuestos(
        empresa_id=empresa_id,
        usuario=usuario,
        key_prefix=key_prefix,
    )