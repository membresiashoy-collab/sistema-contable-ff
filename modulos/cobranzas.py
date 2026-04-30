import pandas as pd
import streamlit as st

from core.numeros import moneda
from core.ui import preparar_vista

from modulos.documentos_tesoreria_componentes import mostrar_recibos_emitidos_integrado

from services.cobranzas_service import (
    anular_cobranza,
    inicializar_cobranzas,
    obtener_clientes_con_saldo_pendiente,
    obtener_comprobantes_pendientes_cliente,
    obtener_cuentas_cobranza,
    obtener_historial_cobranzas,
    registrar_cobranza,
)

from services.tesoreria_service import (
    asegurar_medios_pago_basicos,
    crear_cuenta_tesoreria,
)


# ======================================================
# UTILIDADES
# ======================================================

MEDIOS_CUENTAS_COMPATIBLES = {
    "EFECTIVO": {"CAJA"},
    "TRANSFERENCIA": {"BANCO"},
    "DEBITO_AUTOMATICO": {"BANCO"},
    "TARJETA": {"BANCO", "TARJETA"},
    "BILLETERA": {"BANCO", "BILLETERA"},
    "CHEQUE": {"VALORES", "BANCO"},
    "ECHEQ": {"VALORES", "BANCO"},
    "OTRO": {"BANCO", "BILLETERA", "TARJETA", "VALORES", "OTRO"},
}


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


def _texto_upper(valor):
    return _texto(valor).upper()


def _etiqueta_cliente(row):
    cliente = _texto(row.get("cliente"))
    cuit = _texto(row.get("cuit"))
    saldo = _numero(row.get("saldo"))

    if cuit:
        return f"{cliente} | CUIT {cuit} | Saldo {moneda(saldo)}"

    return f"{cliente} | Saldo {moneda(saldo)}"


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


def _tipos_compatibles_por_medio(medio_codigo):
    codigo = _texto_upper(medio_codigo)
    return MEDIOS_CUENTAS_COMPATIBLES.get(
        codigo,
        {"BANCO", "BILLETERA", "TARJETA", "VALORES", "OTRO"},
    )


def _filtrar_cuentas_por_medio(cuentas, medio_codigo):
    if cuentas is None or cuentas.empty:
        return pd.DataFrame()

    if "tipo_cuenta" not in cuentas.columns:
        return pd.DataFrame()

    tipos_compatibles = _tipos_compatibles_por_medio(medio_codigo)

    return cuentas[
        cuentas["tipo_cuenta"].astype(str).str.upper().isin(tipos_compatibles)
    ].copy()


def _label_cuenta_destino_cobranza(medio_codigo):
    codigo = _texto_upper(medio_codigo)

    if codigo == "EFECTIVO":
        return "Caja / sucursal donde ingresó el efectivo"

    if codigo == "TRANSFERENCIA":
        return "Banco destino de la transferencia"

    if codigo == "DEBITO_AUTOMATICO":
        return "Banco donde se acreditó el débito automático"

    if codigo == "TARJETA":
        return "Banco de acreditación o cuenta puente de tarjetas"

    if codigo == "BILLETERA":
        return "Banco de acreditación o billetera / procesador"

    if codigo in {"CHEQUE", "ECHEQ"}:
        return "Cuenta de valores o banco receptor"

    return "Cuenta destino compatible"


def _label_importe_recibido_cobranza(medio_codigo):
    codigo = _texto_upper(medio_codigo)

    if codigo == "EFECTIVO":
        return "Importe recibido en efectivo"

    if codigo == "TRANSFERENCIA":
        return "Importe transferido / acreditado"

    if codigo == "DEBITO_AUTOMATICO":
        return "Importe debitado / acreditado"

    if codigo == "TARJETA":
        return "Importe cobrado con tarjeta"

    if codigo == "BILLETERA":
        return "Importe cobrado por billetera"

    if codigo in {"CHEQUE", "ECHEQ"}:
        return "Importe recibido en cheque / eCheq"

    return "Importe recibido"


def _mostrar_impacto_cobranza(medio_codigo, cuenta_row):
    codigo = _texto_upper(medio_codigo)
    nombre = _texto(cuenta_row.get("nombre"))
    tipo_cuenta = _texto_upper(cuenta_row.get("tipo_cuenta"))

    if codigo == "EFECTIVO":
        st.success(
            f"Impacto: esta cobranza ingresará a Caja ({nombre}) "
            "y aparecerá automáticamente en el módulo Caja como COBRANZA_EFECTIVO."
        )
        return

    if codigo == "TRANSFERENCIA":
        st.info(
            "Impacto: esta cobranza NO mueve Caja. "
            "Queda en Tesorería/Banco pendiente de conciliación bancaria."
        )
        return

    if codigo == "TARJETA":
        st.info(
            "Impacto: esta cobranza NO mueve Caja. "
            "Se registra el medio tarjeta y luego se controla la acreditación/liquidación."
        )
        return

    if codigo == "BILLETERA":
        st.info(
            "Impacto: esta cobranza NO mueve Caja. "
            "Se registra el medio billetera y luego se controla la acreditación bancaria."
        )
        return

    if codigo in {"CHEQUE", "ECHEQ"}:
        st.info(
            "Impacto: esta cobranza NO mueve Caja. "
            "Queda como valor o banco para depósito/acreditación posterior."
        )
        return

    if tipo_cuenta == "BANCO":
        st.info(
            "Impacto: esta cobranza queda en Tesorería/Banco y no genera movimiento de Caja."
        )
        return

    st.info("Impacto: esta cobranza queda registrada según la cuenta de Tesorería seleccionada.")


def _crear_cuenta_rapida_cobranza(empresa_id, medio_codigo):
    codigo = _texto_upper(medio_codigo)

    if codigo == "EFECTIVO":
        if st.button("Crear Caja principal", use_container_width=True, key="cobranzas_crear_caja"):
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

    if codigo in {"TRANSFERENCIA", "TARJETA", "BILLETERA", "DEBITO_AUTOMATICO"}:
        if st.button("Crear Banco principal", use_container_width=True, key="cobranzas_crear_banco"):
            crear_cuenta_tesoreria(
                empresa_id=empresa_id,
                tipo_cuenta="BANCO",
                nombre="Banco principal",
                entidad="Banco",
                moneda="ARS",
                cuenta_contable_nombre="Banco principal",
            )
            st.success("Banco principal creado.")
            st.rerun()
        return

    if codigo in {"CHEQUE", "ECHEQ"}:
        if st.button("Crear Valores a depositar", use_container_width=True, key="cobranzas_crear_valores"):
            crear_cuenta_tesoreria(
                empresa_id=empresa_id,
                tipo_cuenta="VALORES",
                nombre="Valores a depositar",
                moneda="ARS",
                cuenta_contable_nombre="Valores a depositar",
            )
            st.success("Cuenta de valores creada.")
            st.rerun()


def _preparar_pendientes_editor(df):
    if df.empty:
        return df

    editor = df.copy()

    editor["Seleccionar"] = False
    editor["Importe a cobrar"] = editor["saldo"].apply(_numero)

    columnas = [
        "Seleccionar",
        "fecha",
        "tipo_comprobante",
        "numero_comprobante",
        "debe",
        "haber",
        "saldo",
        "Importe a cobrar",
        "cuenta_corriente_id",
    ]

    columnas = [c for c in columnas if c in editor.columns]

    return editor[columnas]


# ======================================================
# PANTALLA PRINCIPAL
# ======================================================

def mostrar_cobranzas():
    inicializar_cobranzas()

    tab1, tab2, tab3, tab_recibos_emitidos = st.tabs([
        "Registrar cobranza",
        "Pendientes por cliente",
        "Historial / Anulación",
        "Recibos emitidos",
    ])

    with tab1:
        mostrar_registrar_cobranza()

    with tab2:
        mostrar_pendientes_clientes()

    with tab3:
        mostrar_historial_cobranzas()

    with tab_recibos_emitidos:
        mostrar_recibos_emitidos_integrado()


# ======================================================
# TAB 1 - REGISTRAR COBRANZA
# ======================================================

def mostrar_registrar_cobranza():
    empresa_id = empresa_actual_id()

    st.info(
        "Primero elegí el medio de pago. El sistema muestra solo las cuentas compatibles "
        "y aclara si la operación impacta Caja o queda en Tesorería/Banco."
    )

    clientes = obtener_clientes_con_saldo_pendiente(empresa_id=empresa_id)

    if clientes.empty:
        st.success("No hay clientes con saldo pendiente de cobro.")
        return

    cuentas = obtener_cuentas_cobranza(empresa_id=empresa_id)
    medios = asegurar_medios_pago_basicos(empresa_id=empresa_id)

    if medios is None or medios.empty:
        st.error("No hay medios de pago configurados.")
        return

    clientes_labels = [_etiqueta_cliente(row) for _, row in clientes.iterrows()]
    cliente_sel = st.selectbox("Cliente", clientes_labels, key="cobranzas_cliente_select")

    idx_cliente = clientes_labels.index(cliente_sel)
    cliente_row = clientes.iloc[idx_cliente].to_dict()

    cliente = _texto(cliente_row.get("cliente"))
    cuit = _texto(cliente_row.get("cuit"))

    pendientes = obtener_comprobantes_pendientes_cliente(
        empresa_id=empresa_id,
        cliente=cliente,
        cuit=cuit,
    )

    st.subheader("Comprobantes pendientes")

    if pendientes.empty:
        st.info("El cliente no tiene comprobantes pendientes.")
        return

    editor = _preparar_pendientes_editor(pendientes)

    editado = st.data_editor(
        editor,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Seleccionar": st.column_config.CheckboxColumn("Seleccionar"),
            "Importe a cobrar": st.column_config.NumberColumn(
                "Importe a cobrar",
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
        key="cobranzas_editor_pendientes",
    )

    seleccionados = editado[editado["Seleccionar"] == True].copy()

    importe_imputado = 0.0

    if not seleccionados.empty:
        importe_imputado = round(seleccionados["Importe a cobrar"].apply(_numero).sum(), 2)

    col1, col2, col3 = st.columns(3)

    with col1:
        fecha_cobranza = st.date_input("Fecha de cobranza", format="DD/MM/YYYY", key="cobranzas_fecha")

    with col2:
        fecha_contable = st.date_input(
            "Fecha contable",
            value=fecha_cobranza,
            format="DD/MM/YYYY",
            key="cobranzas_fecha_contable",
        )

    with col3:
        referencia = st.text_input("Referencia / comprobante externo", key="cobranzas_referencia")

    st.subheader("Medio de cobro y cuenta destino")

    medios_labels = [_etiqueta_medio(row) for _, row in medios.iterrows()]
    medio_sel = st.selectbox("Medio de pago", medios_labels, key="cobranzas_medio_select")
    medio_codigo = str(medios.iloc[medios_labels.index(medio_sel)]["codigo"])

    cuentas_compatibles = _filtrar_cuentas_por_medio(cuentas, medio_codigo)

    if cuentas_compatibles.empty:
        st.warning(
            "No hay cuentas compatibles para el medio de pago seleccionado. "
            "Creá una cuenta adecuada para continuar."
        )
        _crear_cuenta_rapida_cobranza(empresa_id, medio_codigo)
        return

    cuentas_labels = [_etiqueta_cuenta(row) for _, row in cuentas_compatibles.iterrows()]
    cuenta_sel = st.selectbox(
        _label_cuenta_destino_cobranza(medio_codigo),
        cuentas_labels,
        key="cobranzas_cuenta_select",
    )

    cuenta_row = cuentas_compatibles.iloc[cuentas_labels.index(cuenta_sel)].to_dict()
    cuenta_id = int(cuenta_row["id"])

    _mostrar_impacto_cobranza(medio_codigo, cuenta_row)

    st.subheader("Importes")

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        importe_recibido = st.number_input(
            _label_importe_recibido_cobranza(medio_codigo),
            min_value=0.0,
            value=float(importe_imputado),
            step=0.01,
            key="cobranzas_importe_recibido",
        )

    with c2:
        ret_iibb = st.number_input("Retención IIBB sufrida", min_value=0.0, value=0.0, step=0.01, key="cobranzas_ret_iibb")

    with c3:
        ret_ganancias = st.number_input("Retención Ganancias sufrida", min_value=0.0, value=0.0, step=0.01, key="cobranzas_ret_ganancias")

    with c4:
        ret_iva = st.number_input("Retención IVA sufrida", min_value=0.0, value=0.0, step=0.01, key="cobranzas_ret_iva")

    retenciones_total = round(ret_iibb + ret_ganancias + ret_iva, 2)
    total_aplicado = round(importe_recibido + retenciones_total, 2)
    diferencia = round(total_aplicado - importe_imputado, 2)

    m1, m2, m3, m4 = st.columns(4)

    m1.metric("Imputado a comprobantes", moneda(importe_imputado))
    m2.metric("Importe recibido", moneda(importe_recibido))
    m3.metric("Retenciones", moneda(retenciones_total))
    m4.metric("A cuenta / diferencia", moneda(diferencia))

    descripcion = st.text_area(
        "Descripción",
        value=f"Cobranza cliente {cliente}",
        key="cobranzas_descripcion",
    )

    st.caption(
        "Si el total aplicado supera lo imputado, la diferencia queda como cobranza a cuenta "
        "del cliente. Si es menor, se registra una cobranza parcial."
    )

    if st.button("Confirmar cobranza", type="primary", use_container_width=True, key="cobranzas_confirmar"):
        imputaciones = []

        for _, row in seleccionados.iterrows():
            importe = _numero(row.get("Importe a cobrar"))

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
                "descripcion": "Retención IIBB sufrida",
                "importe": ret_iibb,
            })

        if ret_ganancias > 0:
            retenciones.append({
                "tipo_retencion": "GANANCIAS",
                "descripcion": "Retención Ganancias sufrida",
                "importe": ret_ganancias,
            })

        if ret_iva > 0:
            retenciones.append({
                "tipo_retencion": "IVA",
                "descripcion": "Retención IVA sufrida",
                "importe": ret_iva,
            })

        resultado = registrar_cobranza(
            empresa_id=empresa_id,
            fecha_cobranza=str(fecha_cobranza),
            fecha_contable=str(fecha_contable),
            cliente=cliente,
            cuit=cuit,
            cuenta_tesoreria_id=cuenta_id,
            medio_pago_codigo=medio_codigo,
            importe_recibido=importe_recibido,
            referencia_externa=referencia,
            descripcion=descripcion,
            imputaciones=imputaciones,
            retenciones=retenciones,
            usuario_id=usuario_actual_id(),
        )

        if resultado.get("ok") and resultado.get("creada"):
            st.success(resultado["mensaje"])
            st.write(f"Recibo: **{resultado['numero_recibo']}**")
            st.write(f"Asiento: **{resultado['asiento_id']}**")
            st.write(f"Operación Tesorería: **{resultado['tesoreria_operacion_id']}**")
            st.rerun()

        elif resultado.get("duplicada"):
            st.warning(resultado["mensaje"])

        else:
            st.error(resultado.get("mensaje", "No se pudo registrar la cobranza."))


# ======================================================
# TAB 2 - PENDIENTES
# ======================================================

def mostrar_pendientes_clientes():
    empresa_id = empresa_actual_id()

    st.subheader("Clientes con saldo pendiente")

    clientes = obtener_clientes_con_saldo_pendiente(empresa_id=empresa_id)

    if clientes.empty:
        st.success("No hay saldos pendientes de clientes.")
        return

    st.dataframe(preparar_vista(clientes), use_container_width=True)

    st.divider()

    labels = [_etiqueta_cliente(row) for _, row in clientes.iterrows()]
    seleccionado = st.selectbox("Ver detalle de cliente", labels, key="cobranzas_detalle_cliente")

    idx = labels.index(seleccionado)
    row = clientes.iloc[idx].to_dict()

    pendientes = obtener_comprobantes_pendientes_cliente(
        empresa_id=empresa_id,
        cliente=_texto(row.get("cliente")),
        cuit=_texto(row.get("cuit")),
    )

    st.subheader("Comprobantes pendientes del cliente")
    st.dataframe(preparar_vista(pendientes), use_container_width=True)


# ======================================================
# TAB 3 - HISTORIAL
# ======================================================

def mostrar_historial_cobranzas():
    empresa_id = empresa_actual_id()

    st.subheader("Historial de cobranzas")

    incluir_anuladas = st.checkbox("Incluir anuladas", value=True, key="cobranzas_incluir_anuladas")

    historial = obtener_historial_cobranzas(
        empresa_id=empresa_id,
        incluir_anuladas=incluir_anuladas,
    )

    if historial.empty:
        st.info("Todavía no hay cobranzas registradas.")
        return

    st.dataframe(preparar_vista(historial), use_container_width=True)

    st.divider()

    st.subheader("Anulación controlada")

    st.caption(
        "Las anulaciones no borran datos: generan reverso en cuenta corriente y asiento contable. "
        "Si la operación ya está conciliada, solo un administrador debería permitir la anulación."
    )

    opciones = []

    for _, row in historial[historial["estado"] != "ANULADA"].iterrows():
        opciones.append(
            (
                int(row["id"]),
                f"{row['numero_recibo']} | {row['fecha_cobranza']} | {row['cliente']} | {moneda(row['importe_total_aplicado'])}"
            )
        )

    if not opciones:
        st.info("No hay cobranzas activas para anular.")
        return

    labels = [label for _, label in opciones]
    seleccionado = st.selectbox("Cobranza a anular", labels, key="cobranzas_anular_select")

    cobranza_id = opciones[labels.index(seleccionado)][0]

    motivo = st.text_input("Motivo de anulación", key="cobranzas_motivo_anulacion")

    permitir_conciliada = False

    if usuario_es_administrador():
        permitir_conciliada = st.checkbox(
            "Permitir anulación aunque esté conciliada",
            value=False,
            key="cobranzas_permitir_conciliada",
        )

    if st.button("Anular cobranza", use_container_width=True, key="cobranzas_anular_boton"):
        resultado = anular_cobranza(
            cobranza_id=cobranza_id,
            empresa_id=empresa_id,
            usuario_id=usuario_actual_id(),
            motivo=motivo,
            permitir_conciliada=permitir_conciliada,
        )

        if resultado.get("ok") and resultado.get("anulada"):
            st.success(resultado["mensaje"])
            st.write(f"Asiento reverso: **{resultado['asiento_reverso']}**")
            st.rerun()

        else:
            st.warning(resultado.get("mensaje", "No se pudo anular la cobranza."))