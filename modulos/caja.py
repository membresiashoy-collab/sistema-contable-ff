import pandas as pd
import streamlit as st

from core.numeros import moneda
from core.ui import preparar_vista

from services.cajas_service import (
    anular_movimiento_caja,
    crear_caja,
    inicializar_cajas,
    listar_arqueos_caja,
    listar_asientos_caja,
    listar_cajas,
    listar_cuentas_banco_tesoreria,
    listar_movimientos_caja,
    listar_operaciones_tesoreria_caja,
    obtener_resumen_caja,
    obtener_saldos_cajas,
    registrar_arqueo_caja,
    registrar_deposito_caja_a_banco,
    registrar_movimiento_manual_caja,
    registrar_retiro_banco_a_caja,
    registrar_transferencia_interna,
)


# ======================================================
# UTILIDADES UI
# ======================================================

def empresa_actual_id():
    return int(st.session_state.get("empresa_id", 1))


def usuario_actual_id():
    usuario = st.session_state.get("usuario") or {}
    return usuario.get("id")


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


def _opciones_cuentas(df):
    opciones = []

    if df is None or df.empty:
        return opciones

    for _, fila in df.iterrows():
        cuenta_id = int(fila["id"])
        nombre = _texto(fila.get("nombre"))
        moneda = _texto(fila.get("moneda") or "ARS")
        codigo = _texto(fila.get("cuenta_contable_codigo"))
        nombre_contable = _texto(fila.get("cuenta_contable_nombre"))

        etiqueta = f"{nombre} | {moneda}"

        if codigo or nombre_contable:
            etiqueta += f" | {codigo} {nombre_contable}".strip()

        opciones.append((etiqueta, cuenta_id))

    return opciones


def _select_cuenta(label, opciones, key):
    if not opciones:
        st.warning(f"No hay cuentas disponibles para: {label}.")
        return None

    etiquetas = [op[0] for op in opciones]
    seleccion = st.selectbox(label, etiquetas, key=key)
    return dict(opciones).get(seleccion)


def _mostrar_dataframe(df, mensaje_vacio, height=360):
    if df is None or df.empty:
        st.info(mensaje_vacio)
        return

    st.dataframe(
        preparar_vista(df),
        use_container_width=True,
        height=height,
    )


def _preparar_saldos(df):
    if df is None or df.empty:
        return df

    vista = df.copy()

    if "saldo" in vista.columns:
        vista["saldo_visible"] = vista["saldo"].apply(moneda)

    columnas = [
        "id",
        "nombre",
        "moneda",
        "cuenta_contable_codigo",
        "cuenta_contable_nombre",
        "saldo_visible",
    ]

    columnas = [col for col in columnas if col in vista.columns]
    vista = vista[columnas].copy()

    return vista.rename(columns={
        "id": "ID",
        "nombre": "Caja",
        "moneda": "Moneda",
        "cuenta_contable_codigo": "Cuenta cód.",
        "cuenta_contable_nombre": "Cuenta contable",
        "saldo_visible": "Saldo",
    })


def _preparar_movimientos(df):
    if df is None or df.empty:
        return df

    vista = df.copy()

    if "importe" in vista.columns:
        vista["importe_visible"] = vista["importe"].apply(moneda)

    columnas = [
        "id",
        "fecha",
        "tipo_movimiento",
        "caja_nombre_origen",
        "caja_nombre_destino",
        "cuenta_banco_nombre",
        "concepto",
        "referencia",
        "importe_visible",
        "sentido_caja_origen",
        "estado",
        "motivo_anulacion",
        "tesoreria_operacion_id",
        "tesoreria_operacion_banco_id",
    ]

    columnas = [col for col in columnas if col in vista.columns]
    vista = vista[columnas].copy()

    return vista.rename(columns={
        "id": "ID",
        "fecha": "Fecha",
        "tipo_movimiento": "Tipo",
        "caja_nombre_origen": "Caja origen",
        "caja_nombre_destino": "Caja destino",
        "cuenta_banco_nombre": "Banco",
        "concepto": "Concepto",
        "referencia": "Referencia",
        "importe_visible": "Importe",
        "sentido_caja_origen": "Sentido caja origen",
        "estado": "Estado",
        "motivo_anulacion": "Motivo anulación",
        "tesoreria_operacion_id": "Tesorería op.",
        "tesoreria_operacion_banco_id": "Tesorería banco op.",
    })


def _preparar_arqueos(df):
    if df is None or df.empty:
        return df

    vista = df.copy()

    for columna in ["saldo_sistema", "efectivo_contado", "diferencia"]:
        if columna in vista.columns:
            vista[f"{columna}_visible"] = vista[columna].apply(moneda)

    columnas = [
        "id",
        "fecha",
        "caja_nombre",
        "saldo_sistema_visible",
        "efectivo_contado_visible",
        "diferencia_visible",
        "tipo_diferencia",
        "estado",
        "movimiento_ajuste_id",
        "observacion",
    ]

    columnas = [col for col in columnas if col in vista.columns]
    vista = vista[columnas].copy()

    return vista.rename(columns={
        "id": "ID",
        "fecha": "Fecha",
        "caja_nombre": "Caja",
        "saldo_sistema_visible": "Saldo sistema",
        "efectivo_contado_visible": "Efectivo contado",
        "diferencia_visible": "Diferencia",
        "tipo_diferencia": "Tipo diferencia",
        "estado": "Estado",
        "movimiento_ajuste_id": "Movimiento ajuste",
        "observacion": "Observación",
    })


def _preparar_asientos(df):
    if df is None or df.empty:
        return df

    vista = df.copy()

    for columna in ["debe", "haber"]:
        if columna in vista.columns:
            vista[f"{columna}_visible"] = vista[columna].apply(moneda)

    columnas = [
        "id",
        "movimiento_caja_id",
        "arqueo_id",
        "fecha",
        "cuenta_codigo",
        "cuenta_nombre",
        "debe_visible",
        "haber_visible",
        "glosa",
        "estado",
    ]

    columnas = [col for col in columnas if col in vista.columns]
    vista = vista[columnas].copy()

    return vista.rename(columns={
        "id": "ID",
        "movimiento_caja_id": "Mov. caja",
        "arqueo_id": "Arqueo",
        "fecha": "Fecha",
        "cuenta_codigo": "Cuenta cód.",
        "cuenta_nombre": "Cuenta",
        "debe_visible": "Debe",
        "haber_visible": "Haber",
        "glosa": "Glosa",
        "estado": "Estado",
    })


def _etiqueta_movimiento(row):
    return (
        f"Movimiento #{int(row['id'])} | {row.get('fecha', '')} | "
        f"{row.get('tipo_movimiento', '')} | {moneda(_numero(row.get('importe')))} | "
        f"{row.get('concepto', '')}"
    )


# ======================================================
# TAB: RESUMEN
# ======================================================

def mostrar_resumen():
    resumen = obtener_resumen_caja(empresa_id=empresa_actual_id())

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Cajas activas", resumen.get("cantidad_cajas", 0))
    c2.metric("Saldo total en caja", moneda(resumen.get("saldo_total", 0)))
    c3.metric("Movimientos", resumen.get("cantidad_movimientos", 0))
    c4.metric("Pendientes conciliación", resumen.get("pendientes_conciliacion", 0))

    st.markdown("#### Saldos por caja")
    saldos = obtener_saldos_cajas(empresa_id=empresa_actual_id())
    _mostrar_dataframe(
        _preparar_saldos(saldos),
        "Todavía no hay saldos de caja para mostrar.",
    )

    st.info(
        "Caja trabaja separado de Banco. Un depósito de efectivo Caja → Banco "
        "se registra como transferencia interna y queda pendiente de conciliación bancaria, "
        "pero no crea una nueva cobranza."
    )


# ======================================================
# TAB: CONFIGURACIÓN
# ======================================================

def mostrar_configuracion_cajas():
    st.subheader("Cajas configurables")

    with st.form("form_crear_caja"):
        col1, col2 = st.columns(2)

        with col1:
            nombre = st.text_input("Nombre de la caja", placeholder="Ej.: Caja Local, Caja Administración")
            moneda_sel = st.selectbox("Moneda", ["ARS", "USD"], index=0)

        with col2:
            cuenta_codigo = st.text_input("Cuenta contable código", value="1.1.01.01")
            cuenta_nombre = st.text_input("Cuenta contable nombre", value="Caja")

        observacion = st.text_area("Observación", height=80)

        crear = st.form_submit_button("Crear caja", use_container_width=True)

        if crear:
            try:
                resultado = crear_caja(
                    empresa_id=empresa_actual_id(),
                    nombre=nombre,
                    moneda=moneda_sel,
                    cuenta_contable_codigo=cuenta_codigo,
                    cuenta_contable_nombre=cuenta_nombre,
                    observacion=observacion,
                )
                st.success(resultado.get("mensaje", "Caja creada."))
                st.rerun()

            except Exception as e:
                st.error(f"No se pudo crear la caja: {e}")

    st.divider()

    cajas = listar_cajas(empresa_id=empresa_actual_id(), incluir_inactivas=True)
    _mostrar_dataframe(
        cajas,
        "Todavía no hay cajas configuradas.",
    )


# ======================================================
# TAB: MOVIMIENTOS MANUALES
# ======================================================

def mostrar_movimientos_manuales():
    st.subheader("Movimientos manuales de caja")

    cajas = listar_cajas(empresa_id=empresa_actual_id())
    opciones_cajas = _opciones_cuentas(cajas)

    with st.form("form_movimiento_manual_caja"):
        col1, col2, col3 = st.columns(3)

        with col1:
            caja_id = _select_cuenta("Caja", opciones_cajas, "manual_caja_id")
            fecha = st.date_input("Fecha")

        with col2:
            tipo = st.selectbox("Tipo", ["INGRESO", "EGRESO"])
            importe = st.number_input("Importe", min_value=0.0, step=100.0, format="%.2f")

        with col3:
            referencia = st.text_input("Referencia interna", placeholder="Opcional")

        concepto = st.text_input("Concepto", placeholder="Ej.: Fondo fijo, gasto menor, aporte a caja")
        observacion = st.text_area("Observación", height=90)

        confirmar = st.form_submit_button("Registrar movimiento manual", use_container_width=True)

        if confirmar:
            try:
                resultado = registrar_movimiento_manual_caja(
                    empresa_id=empresa_actual_id(),
                    caja_id=caja_id,
                    fecha=str(fecha),
                    tipo=tipo,
                    importe=importe,
                    concepto=concepto,
                    referencia=referencia,
                    observacion=observacion,
                    usuario_id=usuario_actual_id(),
                )
                st.success(resultado.get("mensaje", "Movimiento registrado."))
                st.rerun()

            except Exception as e:
                st.error(f"No se pudo registrar el movimiento: {e}")

    st.divider()

    movimientos = listar_movimientos_caja(empresa_id=empresa_actual_id(), limite=200)
    _mostrar_dataframe(
        _preparar_movimientos(movimientos),
        "Todavía no hay movimientos de caja.",
    )


# ======================================================
# TAB: TRANSFERENCIAS
# ======================================================

def mostrar_transferencias():
    st.subheader("Transferencias internas")

    cajas = listar_cajas(empresa_id=empresa_actual_id())
    bancos = listar_cuentas_banco_tesoreria(empresa_id=empresa_actual_id())

    opciones_cajas = _opciones_cuentas(cajas)
    opciones_bancos = _opciones_cuentas(bancos)

    st.info(
        "Depósito de efectivo Caja → Banco: genera una operación bancaria pendiente "
        "de conciliación como transferencia interna. No se trata como cobranza nueva."
    )

    tab1, tab2, tab3 = st.tabs([
        "Depósito Caja → Banco",
        "Retiro Banco → Caja",
        "Transferencia Caja ↔ Caja",
    ])

    with tab1:
        with st.form("form_deposito_caja_banco"):
            c1, c2, c3 = st.columns(3)

            with c1:
                caja_id = _select_cuenta("Caja origen", opciones_cajas, "deposito_caja_id")
                fecha = st.date_input("Fecha", key="deposito_fecha")

            with c2:
                banco_id = _select_cuenta("Banco destino", opciones_bancos, "deposito_banco_id")
                importe = st.number_input("Importe", min_value=0.0, step=100.0, format="%.2f", key="deposito_importe")

            with c3:
                referencia = st.text_input("Referencia", key="deposito_referencia")

            concepto = st.text_input(
                "Concepto",
                value="Depósito de efectivo en banco",
                key="deposito_concepto",
            )
            observacion = st.text_area("Observación", height=80, key="deposito_observacion")

            confirmar = st.form_submit_button("Registrar depósito Caja → Banco", use_container_width=True)

            if confirmar:
                try:
                    resultado = registrar_deposito_caja_a_banco(
                        empresa_id=empresa_actual_id(),
                        caja_id=caja_id,
                        banco_cuenta_id=banco_id,
                        fecha=str(fecha),
                        importe=importe,
                        concepto=concepto,
                        referencia=referencia,
                        observacion=observacion,
                        usuario_id=usuario_actual_id(),
                    )
                    st.success(resultado.get("mensaje", "Depósito registrado."))
                    st.rerun()

                except Exception as e:
                    st.error(f"No se pudo registrar el depósito: {e}")

    with tab2:
        with st.form("form_retiro_banco_caja"):
            c1, c2, c3 = st.columns(3)

            with c1:
                banco_id = _select_cuenta("Banco origen", opciones_bancos, "retiro_banco_id")
                fecha = st.date_input("Fecha", key="retiro_fecha")

            with c2:
                caja_id = _select_cuenta("Caja destino", opciones_cajas, "retiro_caja_id")
                importe = st.number_input("Importe", min_value=0.0, step=100.0, format="%.2f", key="retiro_importe")

            with c3:
                referencia = st.text_input("Referencia", key="retiro_referencia")

            concepto = st.text_input(
                "Concepto",
                value="Retiro de efectivo del banco",
                key="retiro_concepto",
            )
            observacion = st.text_area("Observación", height=80, key="retiro_observacion")

            confirmar = st.form_submit_button("Registrar retiro Banco → Caja", use_container_width=True)

            if confirmar:
                try:
                    resultado = registrar_retiro_banco_a_caja(
                        empresa_id=empresa_actual_id(),
                        banco_cuenta_id=banco_id,
                        caja_id=caja_id,
                        fecha=str(fecha),
                        importe=importe,
                        concepto=concepto,
                        referencia=referencia,
                        observacion=observacion,
                        usuario_id=usuario_actual_id(),
                    )
                    st.success(resultado.get("mensaje", "Retiro registrado."))
                    st.rerun()

                except Exception as e:
                    st.error(f"No se pudo registrar el retiro: {e}")

    with tab3:
        with st.form("form_transferencia_caja_caja"):
            c1, c2, c3 = st.columns(3)

            with c1:
                caja_origen_id = _select_cuenta("Caja origen", opciones_cajas, "transfer_caja_origen_id")
                fecha = st.date_input("Fecha", key="transfer_caja_fecha")

            with c2:
                caja_destino_id = _select_cuenta("Caja destino", opciones_cajas, "transfer_caja_destino_id")
                importe = st.number_input("Importe", min_value=0.0, step=100.0, format="%.2f", key="transfer_caja_importe")

            with c3:
                referencia = st.text_input("Referencia", key="transfer_caja_referencia")

            concepto = st.text_input(
                "Concepto",
                value="Transferencia entre cajas",
                key="transfer_caja_concepto",
            )
            observacion = st.text_area("Observación", height=80, key="transfer_caja_observacion")

            confirmar = st.form_submit_button("Registrar transferencia Caja ↔ Caja", use_container_width=True)

            if confirmar:
                try:
                    resultado = registrar_transferencia_interna(
                        empresa_id=empresa_actual_id(),
                        cuenta_origen_id=caja_origen_id,
                        cuenta_destino_id=caja_destino_id,
                        fecha=str(fecha),
                        importe=importe,
                        concepto=concepto,
                        referencia=referencia,
                        observacion=observacion,
                        usuario_id=usuario_actual_id(),
                    )
                    st.success(resultado.get("mensaje", "Transferencia registrada."))
                    st.rerun()

                except Exception as e:
                    st.error(f"No se pudo registrar la transferencia: {e}")

    st.divider()

    pendientes = listar_operaciones_tesoreria_caja(
        empresa_id=empresa_actual_id(),
        solo_pendientes=True,
    )

    st.markdown("#### Operaciones de Caja pendientes de conciliación bancaria")
    _mostrar_dataframe(
        pendientes,
        "No hay operaciones de Caja pendientes de conciliación bancaria.",
    )


# ======================================================
# TAB: ARQUEOS
# ======================================================

def mostrar_arqueos():
    st.subheader("Arqueos de caja")

    cajas = listar_cajas(empresa_id=empresa_actual_id())
    opciones_cajas = _opciones_cuentas(cajas)

    with st.form("form_arqueo_caja"):
        c1, c2, c3 = st.columns(3)

        with c1:
            caja_id = _select_cuenta("Caja", opciones_cajas, "arqueo_caja_id")
            fecha = st.date_input("Fecha de arqueo")

        with c2:
            efectivo_contado = st.number_input(
                "Efectivo contado",
                min_value=0.0,
                step=100.0,
                format="%.2f",
            )

        with c3:
            st.caption("El sistema compara el efectivo contado contra el saldo teórico.")
            st.caption("Si hay diferencia, genera ajuste y asiento controlado.")

        observacion = st.text_area("Observación del arqueo", height=90)

        confirmar = st.form_submit_button("Registrar arqueo", use_container_width=True)

        if confirmar:
            try:
                resultado = registrar_arqueo_caja(
                    empresa_id=empresa_actual_id(),
                    caja_id=caja_id,
                    fecha=str(fecha),
                    efectivo_contado=efectivo_contado,
                    observacion=observacion,
                    usuario_id=usuario_actual_id(),
                )

                diferencia = _numero(resultado.get("diferencia", 0))

                if abs(diferencia) <= 0.01:
                    st.success("Arqueo cuadrado sin diferencias.")
                else:
                    st.warning(
                        f"Arqueo registrado con diferencia {moneda(diferencia)}. "
                        "Se generó ajuste y asiento controlado."
                    )

                st.rerun()

            except Exception as e:
                st.error(f"No se pudo registrar el arqueo: {e}")

    st.divider()

    arqueos = listar_arqueos_caja(empresa_id=empresa_actual_id(), limite=200)
    _mostrar_dataframe(
        _preparar_arqueos(arqueos),
        "Todavía no hay arqueos registrados.",
    )


# ======================================================
# TAB: ANULACIONES
# ======================================================

def mostrar_anulaciones():
    st.subheader("Anulación de movimientos de caja")

    movimientos = listar_movimientos_caja(
        empresa_id=empresa_actual_id(),
        estado="CONFIRMADO",
        limite=500,
    )

    if movimientos.empty:
        st.info("No hay movimientos confirmados para anular.")
        return

    opciones = []

    for _, fila in movimientos.iterrows():
        opciones.append((_etiqueta_movimiento(fila), int(fila["id"])))

    with st.form("form_anular_movimiento_caja"):
        etiquetas = [op[0] for op in opciones]
        seleccion = st.selectbox("Movimiento a anular", etiquetas)
        movimiento_id = dict(opciones).get(seleccion)

        motivo = st.text_area(
            "Motivo de anulación",
            placeholder="Ej.: carga duplicada, error de caja, importe mal ingresado.",
            height=110,
        )

        acepta = st.checkbox("Confirmo que quiero anular este movimiento y dejar trazabilidad del motivo.")

        confirmar = st.form_submit_button("Anular movimiento de caja", use_container_width=True)

        if confirmar:
            if not acepta:
                st.warning("Marcá la confirmación antes de anular.")
                return

            try:
                resultado = anular_movimiento_caja(
                    empresa_id=empresa_actual_id(),
                    movimiento_id=movimiento_id,
                    motivo=motivo,
                    usuario_id=usuario_actual_id(),
                )
                st.success(resultado.get("mensaje", "Movimiento anulado."))
                st.rerun()

            except Exception as e:
                st.error(f"No se pudo anular el movimiento: {e}")


# ======================================================
# TAB: CONSULTAS
# ======================================================

def mostrar_consultas():
    st.subheader("Movimientos, Tesorería y asientos")

    tab1, tab2, tab3 = st.tabs([
        "Movimientos",
        "Tesorería",
        "Asientos Caja",
    ])

    with tab1:
        movimientos = listar_movimientos_caja(empresa_id=empresa_actual_id(), limite=500)
        _mostrar_dataframe(
            _preparar_movimientos(movimientos),
            "Todavía no hay movimientos de caja.",
            height=460,
        )

    with tab2:
        operaciones = listar_operaciones_tesoreria_caja(
            empresa_id=empresa_actual_id(),
            solo_pendientes=False,
            limite=500,
        )
        _mostrar_dataframe(
            operaciones,
            "Todavía no hay operaciones de Tesorería generadas desde Caja.",
            height=460,
        )

    with tab3:
        asientos = listar_asientos_caja(empresa_id=empresa_actual_id(), limite=1000)
        _mostrar_dataframe(
            _preparar_asientos(asientos),
            "Todavía no hay asientos de Caja.",
            height=460,
        )


# ======================================================
# MÓDULO PRINCIPAL
# ======================================================

def mostrar_caja():
    inicializar_cajas()

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "Resumen",
        "Configuración",
        "Movimientos manuales",
        "Transferencias",
        "Arqueos",
        "Anulación / Consultas",
    ])

    with tab1:
        mostrar_resumen()

    with tab2:
        mostrar_configuracion_cajas()

    with tab3:
        mostrar_movimientos_manuales()

    with tab4:
        mostrar_transferencias()

    with tab5:
        mostrar_arqueos()

    with tab6:
        sub1, sub2 = st.tabs(["Anulación", "Consultas"])
        with sub1:
            mostrar_anulaciones()
        with sub2:
            mostrar_consultas()