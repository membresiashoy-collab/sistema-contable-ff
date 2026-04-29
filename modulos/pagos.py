import pandas as pd
import streamlit as st

from core.numeros import moneda
from core.ui import preparar_vista

from services.pagos_service import (
    anular_pago,
    inicializar_pagos,
    obtener_comprobantes_pendientes_proveedor,
    obtener_cuentas_pago,
    obtener_historial_pagos,
    obtener_proveedores_con_saldo_pendiente,
    registrar_pago,
)

from services.tesoreria_service import (
    asegurar_medios_pago_basicos,
    crear_cuenta_tesoreria,
)


# ======================================================
# UTILIDADES
# ======================================================

def empresa_actual_id():
    return int(st.session_state.get("empresa_id", 1))


def usuario_actual_id():
    usuario = st.session_state.get("usuario") or {}
    return usuario.get("id")


def usuario_es_administrador():
    usuario = st.session_state.get("usuario") or {}
    rol = str(usuario.get("rol", "")).strip().upper()
    return rol in {"ADMINISTRADOR", "ADMIN", "SUPERADMIN"}


def _numero(valor):
    try:
        if valor is None or pd.isna(valor):
            return 0.0
    except Exception:
        if valor is None:
            return 0.0

    try:
        return round(float(valor), 2)
    except Exception:
        return 0.0


def _texto(valor):
    if valor is None:
        return ""

    try:
        if pd.isna(valor):
            return ""
    except Exception:
        pass

    return str(valor).strip()


def _etiqueta_proveedor(row):
    proveedor = _texto(row.get("proveedor"))
    cuit = _texto(row.get("cuit"))
    saldo = _numero(row.get("saldo"))

    if cuit:
        return f"{proveedor} | CUIT {cuit} | Saldo {moneda(saldo)}"

    return f"{proveedor} | Saldo {moneda(saldo)}"


def _etiqueta_cuenta(row):
    tipo = _texto(row.get("tipo_cuenta"))
    nombre = _texto(row.get("nombre"))
    entidad = _texto(row.get("entidad"))
    moneda_cuenta = _texto(row.get("moneda")) or "ARS"

    if entidad:
        return f"{tipo} | {entidad} - {nombre} | {moneda_cuenta}"

    return f"{tipo} | {nombre} | {moneda_cuenta}"


def _etiqueta_medio(row):
    return f"{row.get('codigo')} | {row.get('nombre')}"


def _preparar_pendientes_editor(df):
    if df.empty:
        return df

    editor = df.copy()

    editor["Seleccionar"] = False
    editor["Importe a pagar"] = editor["saldo"].apply(_numero)

    columnas = [
        "Seleccionar",
        "fecha",
        "tipo_comprobante",
        "numero_comprobante",
        "debe",
        "haber",
        "saldo",
        "Importe a pagar",
        "cuenta_corriente_id",
    ]

    columnas = [c for c in columnas if c in editor.columns]

    return editor[columnas]


# ======================================================
# PANTALLA PRINCIPAL
# ======================================================

def mostrar_pagos():
    inicializar_pagos()

    tab1, tab2, tab3 = st.tabs([
        "Registrar pago",
        "Pendientes por proveedor",
        "Historial / Anulación",
    ])

    with tab1:
        mostrar_registrar_pago()

    with tab2:
        mostrar_pendientes_proveedores()

    with tab3:
        mostrar_historial_pagos()


# ======================================================
# TAB 1 - REGISTRAR PAGO
# ======================================================

def mostrar_registrar_pago():
    empresa_id = empresa_actual_id()

    st.info(
        "Registrá pagos a proveedores contra Caja, Banco o Billetera. "
        "El pago cancela cuenta corriente y deja una operación pendiente de conciliación en Tesorería."
    )

    proveedores = obtener_proveedores_con_saldo_pendiente(empresa_id=empresa_id)

    if proveedores.empty:
        st.success("No hay proveedores con saldo pendiente de pago.")
        return

    cuentas = obtener_cuentas_pago(empresa_id=empresa_id)

    if cuentas.empty:
        st.warning(
            "Todavía no hay cuentas de Tesorería para realizar pagos. "
            "Podés crear una Caja principal rápida para empezar."
        )

        if st.button("Crear Caja principal para pagos", use_container_width=True):
            crear_cuenta_tesoreria(
                empresa_id=empresa_id,
                tipo_cuenta="CAJA",
                nombre="Caja principal",
                moneda="ARS",
                cuenta_contable_nombre="Caja principal",
            )
            st.success("Caja principal creada.")
            st.rerun()

        return

    medios = asegurar_medios_pago_basicos(empresa_id=empresa_id)

    proveedores_labels = [_etiqueta_proveedor(row) for _, row in proveedores.iterrows()]
    proveedor_sel = st.selectbox("Proveedor", proveedores_labels, key="pagos_proveedor_select")

    idx_proveedor = proveedores_labels.index(proveedor_sel)
    proveedor_row = proveedores.iloc[idx_proveedor].to_dict()

    proveedor = _texto(proveedor_row.get("proveedor"))
    cuit = _texto(proveedor_row.get("cuit"))

    pendientes = obtener_comprobantes_pendientes_proveedor(
        empresa_id=empresa_id,
        proveedor=proveedor,
        cuit=cuit,
    )

    st.subheader("Comprobantes pendientes")

    if pendientes.empty:
        st.info("El proveedor no tiene comprobantes pendientes.")
        return

    editor = _preparar_pendientes_editor(pendientes)

    editado = st.data_editor(
        editor,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Seleccionar": st.column_config.CheckboxColumn("Seleccionar"),
            "Importe a pagar": st.column_config.NumberColumn(
                "Importe a pagar",
                min_value=0.0,
                step=0.01,
            ),
        },
        disabled=[
            "fecha",
            "tipo_comprobante",
            "numero_comprobante",
            "debe",
            "haber",
            "saldo",
            "cuenta_corriente_id",
        ],
        key="pagos_editor_pendientes",
    )

    seleccionados = editado[editado["Seleccionar"] == True].copy()

    importe_imputado = 0.0

    if not seleccionados.empty:
        importe_imputado = round(seleccionados["Importe a pagar"].apply(_numero).sum(), 2)

    col1, col2, col3 = st.columns(3)

    with col1:
        fecha_pago = st.date_input("Fecha de pago", key="pagos_fecha_pago")

    with col2:
        fecha_contable = st.date_input("Fecha contable", value=fecha_pago, key="pagos_fecha_contable")

    with col3:
        referencia = st.text_input("Referencia / comprobante externo", key="pagos_referencia")

    cuentas_labels = [_etiqueta_cuenta(row) for _, row in cuentas.iterrows()]
    cuenta_sel = st.selectbox("Cuenta origen", cuentas_labels, key="pagos_cuenta_select")
    cuenta_id = int(cuentas.iloc[cuentas_labels.index(cuenta_sel)]["id"])

    medios_labels = [_etiqueta_medio(row) for _, row in medios.iterrows()]
    medio_sel = st.selectbox("Medio de pago", medios_labels, key="pagos_medio_select")
    medio_codigo = str(medios.iloc[medios_labels.index(medio_sel)]["codigo"])

    st.subheader("Importes")

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        importe_pagado = st.number_input(
            "Importe pagado desde Caja/Banco",
            min_value=0.0,
            value=float(importe_imputado),
            step=0.01,
            key="pagos_importe_pagado",
        )

    with c2:
        ret_iibb = st.number_input("Retención IIBB practicada", min_value=0.0, value=0.0, step=0.01, key="pagos_ret_iibb")

    with c3:
        ret_ganancias = st.number_input("Retención Ganancias practicada", min_value=0.0, value=0.0, step=0.01, key="pagos_ret_ganancias")

    with c4:
        ret_iva = st.number_input("Retención IVA practicada", min_value=0.0, value=0.0, step=0.01, key="pagos_ret_iva")

    ret_suss = st.number_input("Retención SUSS practicada", min_value=0.0, value=0.0, step=0.01, key="pagos_ret_suss")

    retenciones_total = round(ret_iibb + ret_ganancias + ret_iva + ret_suss, 2)
    total_aplicado = round(importe_pagado + retenciones_total, 2)
    diferencia = round(total_aplicado - importe_imputado, 2)

    m1, m2, m3, m4 = st.columns(4)

    m1.metric("Imputado a comprobantes", moneda(importe_imputado))
    m2.metric("Importe pagado", moneda(importe_pagado))
    m3.metric("Retenciones", moneda(retenciones_total))
    m4.metric("A cuenta / diferencia", moneda(diferencia))

    descripcion = st.text_area(
        "Descripción",
        value=f"Pago proveedor {proveedor}",
        key="pagos_descripcion",
    )

    st.caption(
        "Si el total aplicado supera lo imputado, la diferencia queda como pago a cuenta "
        "del proveedor. Si es menor, se registra un pago parcial."
    )

    if st.button("Confirmar pago", type="primary", use_container_width=True, key="pagos_confirmar"):
        imputaciones = []

        for _, row in seleccionados.iterrows():
            importe = _numero(row.get("Importe a pagar"))

            if importe <= 0:
                continue

            imputaciones.append({
                "cuenta_corriente_id": int(row["cuenta_corriente_id"]) if not pd.isna(row["cuenta_corriente_id"]) else None,
                "tipo_comprobante": _texto(row.get("tipo_comprobante")),
                "numero_comprobante": _texto(row.get("numero_comprobante")),
                "importe_imputado": importe,
            })

        retenciones = []

        if ret_iibb > 0:
            retenciones.append({
                "tipo_retencion": "IIBB",
                "descripcion": "Retención IIBB practicada",
                "importe": ret_iibb,
            })

        if ret_ganancias > 0:
            retenciones.append({
                "tipo_retencion": "GANANCIAS",
                "descripcion": "Retención Ganancias practicada",
                "importe": ret_ganancias,
            })

        if ret_iva > 0:
            retenciones.append({
                "tipo_retencion": "IVA",
                "descripcion": "Retención IVA practicada",
                "importe": ret_iva,
            })

        if ret_suss > 0:
            retenciones.append({
                "tipo_retencion": "SUSS",
                "descripcion": "Retención SUSS practicada",
                "importe": ret_suss,
            })

        resultado = registrar_pago(
            empresa_id=empresa_id,
            fecha_pago=str(fecha_pago),
            fecha_contable=str(fecha_contable),
            proveedor=proveedor,
            cuit=cuit,
            cuenta_tesoreria_id=cuenta_id,
            medio_pago_codigo=medio_codigo,
            importe_pagado=importe_pagado,
            referencia_externa=referencia,
            descripcion=descripcion,
            imputaciones=imputaciones,
            retenciones=retenciones,
            usuario_id=usuario_actual_id(),
        )

        if resultado.get("ok") and resultado.get("creada"):
            st.success(resultado["mensaje"])
            st.write(f"Orden de pago: **{resultado['numero_orden_pago']}**")
            st.write(f"Asiento: **{resultado['asiento_id']}**")
            st.write(f"Operación Tesorería: **{resultado['tesoreria_operacion_id']}**")
            st.rerun()

        elif resultado.get("duplicada"):
            st.warning(resultado["mensaje"])

        else:
            st.error(resultado.get("mensaje", "No se pudo registrar el pago."))


# ======================================================
# TAB 2 - PENDIENTES
# ======================================================

def mostrar_pendientes_proveedores():
    empresa_id = empresa_actual_id()

    st.subheader("Proveedores con saldo pendiente")

    proveedores = obtener_proveedores_con_saldo_pendiente(empresa_id=empresa_id)

    if proveedores.empty:
        st.success("No hay saldos pendientes de proveedores.")
        return

    st.dataframe(preparar_vista(proveedores), use_container_width=True)

    st.divider()

    labels = [_etiqueta_proveedor(row) for _, row in proveedores.iterrows()]
    seleccionado = st.selectbox("Ver detalle de proveedor", labels, key="pagos_detalle_proveedor")

    idx = labels.index(seleccionado)
    row = proveedores.iloc[idx].to_dict()

    pendientes = obtener_comprobantes_pendientes_proveedor(
        empresa_id=empresa_id,
        proveedor=_texto(row.get("proveedor")),
        cuit=_texto(row.get("cuit")),
    )

    st.subheader("Comprobantes pendientes del proveedor")
    st.dataframe(preparar_vista(pendientes), use_container_width=True)


# ======================================================
# TAB 3 - HISTORIAL
# ======================================================

def mostrar_historial_pagos():
    empresa_id = empresa_actual_id()

    st.subheader("Historial de pagos")

    incluir_anulados = st.checkbox("Incluir anulados", value=True, key="pagos_incluir_anulados")

    historial = obtener_historial_pagos(
        empresa_id=empresa_id,
        incluir_anulados=incluir_anulados,
    )

    if historial.empty:
        st.info("Todavía no hay pagos registrados.")
        return

    st.dataframe(preparar_vista(historial), use_container_width=True)

    st.divider()

    st.subheader("Anulación controlada")

    st.caption(
        "Las anulaciones no borran datos: generan reverso en cuenta corriente y asiento contable. "
        "Si la operación ya está conciliada, solo un administrador debería permitir la anulación."
    )

    opciones = []

    for _, row in historial[historial["estado"] != "ANULADO"].iterrows():
        opciones.append(
            (
                int(row["id"]),
                f"{row['numero_orden_pago']} | {row['fecha_pago']} | {row['proveedor']} | {moneda(row['importe_total_aplicado'])}"
            )
        )

    if not opciones:
        st.info("No hay pagos activos para anular.")
        return

    labels = [label for _, label in opciones]
    seleccionado = st.selectbox("Pago a anular", labels, key="pagos_anular_select")

    pago_id = opciones[labels.index(seleccionado)][0]

    motivo = st.text_input("Motivo de anulación", key="pagos_motivo_anulacion")

    permitir_conciliado = False

    if usuario_es_administrador():
        permitir_conciliado = st.checkbox(
            "Permitir anulación aunque esté conciliado",
            value=False,
            key="pagos_permitir_conciliado",
        )

    if st.button("Anular pago", use_container_width=True, key="pagos_anular_boton"):
        resultado = anular_pago(
            pago_id=pago_id,
            empresa_id=empresa_id,
            usuario_id=usuario_actual_id(),
            motivo=motivo,
            permitir_conciliado=permitir_conciliado,
        )

        if resultado.get("ok") and resultado.get("anulado"):
            st.success(resultado["mensaje"])
            st.write(f"Asiento reverso: **{resultado['asiento_reverso']}**")
            st.rerun()

        else:
            st.warning(resultado.get("mensaje", "No se pudo anular el pago."))