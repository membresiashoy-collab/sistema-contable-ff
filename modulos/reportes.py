import streamlit as st
import pandas as pd

from database import (
    ejecutar_query,
    eliminar_todo_diario,
    eliminar_diferencias_redondeo
)

from core.fechas import fecha_para_ordenar, formatear_fecha
from core.numeros import moneda
from core.ui import preparar_vista
from core.exportadores import exportar_excel


# ======================================================
# UTILIDADES
# ======================================================

def numero_seguro(valor):
    try:
        if pd.isna(valor):
            return 0.0
        return float(valor)
    except Exception:
        return 0.0


def fecha_orden_segura(valor):
    try:
        return fecha_para_ordenar(valor)
    except Exception:
        return pd.NaT


def fecha_formateada_segura(valor):
    try:
        return formatear_fecha(valor)
    except Exception:
        return valor


def insertar_espacios_entre_asientos(df):
    filas = []

    for _, grupo in df.groupby("id_asiento", sort=False):
        filas.append(grupo)

        fila_vacia = pd.DataFrame([{
            "id_asiento": "",
            "fecha": "",
            "cuenta": "",
            "debe": "",
            "haber": "",
            "glosa": "",
            "origen": "",
            "archivo": ""
        }])

        filas.append(fila_vacia)

    if filas:
        return pd.concat(filas, ignore_index=True)

    return df


def cargar_libro_diario():
    df = ejecutar_query("""
        SELECT 
            id,
            id_asiento,
            fecha,
            cuenta,
            debe,
            haber,
            glosa,
            origen,
            archivo
        FROM libro_diario
    """, fetch=True)

    if df.empty:
        return df

    df = df.copy()

    df["debe"] = df["debe"].apply(numero_seguro)
    df["haber"] = df["haber"].apply(numero_seguro)

    df = df[df["cuenta"] != "DIFERENCIA POR REDONDEO"].copy()

    if df.empty:
        return df

    df["fecha_orden"] = df["fecha"].apply(fecha_orden_segura)
    df["fecha_mostrar"] = df["fecha"].apply(fecha_formateada_segura)

    return df


def mostrar_alerta_redondeo():
    df = ejecutar_query("""
        SELECT 
            id,
            id_asiento,
            fecha,
            cuenta,
            debe,
            haber,
            glosa,
            origen,
            archivo
        FROM libro_diario
        WHERE cuenta = 'DIFERENCIA POR REDONDEO'
    """, fetch=True)

    if df.empty:
        return

    st.error(
        f"Se detectaron {len(df)} movimientos antiguos en la cuenta "
        "'DIFERENCIA POR REDONDEO'. Estos movimientos corresponden a pruebas anteriores."
    )

    if "confirmar_eliminar_redondeo" not in st.session_state:
        st.session_state["confirmar_eliminar_redondeo"] = False

    if st.button("Eliminar movimientos de DIFERENCIA POR REDONDEO"):
        st.session_state["confirmar_eliminar_redondeo"] = True

    if st.session_state["confirmar_eliminar_redondeo"]:
        st.warning("¿Confirmás eliminar esos movimientos del Libro Diario?")

        c1, c2 = st.columns(2)

        with c1:
            if st.button("Sí, eliminar redondeos"):
                eliminar_diferencias_redondeo()
                st.success("Movimientos de diferencia por redondeo eliminados.")
                st.session_state["confirmar_eliminar_redondeo"] = False
                st.rerun()

        with c2:
            if st.button("Cancelar eliminación"):
                st.session_state["confirmar_eliminar_redondeo"] = False
                st.rerun()

    st.divider()


def aplicar_filtros_contables(df, key_prefix):
    if df.empty:
        return df

    st.subheader("Filtros")

    col1, col2, col3 = st.columns(3)

    with col1:
        origenes = ["Todos"] + sorted(df["origen"].dropna().astype(str).unique().tolist())
        origen_seleccionado = st.selectbox(
            "Origen",
            origenes,
            key=f"{key_prefix}_origen"
        )

    with col2:
        archivos = ["Todos"] + sorted(df["archivo"].dropna().astype(str).unique().tolist())
        archivo_seleccionado = st.selectbox(
            "Archivo",
            archivos,
            key=f"{key_prefix}_archivo"
        )

    with col3:
        cuentas = ["Todas"] + sorted(df["cuenta"].dropna().astype(str).unique().tolist())
        cuenta_seleccionada = st.selectbox(
            "Cuenta",
            cuentas,
            key=f"{key_prefix}_cuenta"
        )

    df_filtrado = df.copy()

    if origen_seleccionado != "Todos":
        df_filtrado = df_filtrado[df_filtrado["origen"] == origen_seleccionado]

    if archivo_seleccionado != "Todos":
        df_filtrado = df_filtrado[df_filtrado["archivo"] == archivo_seleccionado]

    if cuenta_seleccionada != "Todas":
        df_filtrado = df_filtrado[df_filtrado["cuenta"] == cuenta_seleccionada]

    return df_filtrado


def mostrar_metricas_cuadre(df):
    total_debe = df["debe"].sum()
    total_haber = df["haber"].sum()
    diferencia = round(total_debe - total_haber, 2)

    c1, c2, c3 = st.columns(3)

    c1.metric("Total Debe", moneda(total_debe))
    c2.metric("Total Haber", moneda(total_haber))
    c3.metric("Diferencia", moneda(diferencia))

    if diferencia != 0:
        st.error("El reporte no está cuadrando.")
    else:
        st.success("El reporte está cuadrado.")


# ======================================================
# PANTALLA PRINCIPAL
# ======================================================

def mostrar_diario():

    st.caption(
        "Módulo de libros y reportes contables. "
        "Las cuentas corrientes de clientes y proveedores deben gestionarse desde Ventas y Compras."
    )

    tab1, tab2, tab3, tab4 = st.tabs([
        "📓 Libro Diario",
        "📒 Libro Mayor",
        "📊 Balance de Sumas y Saldos",
        "🧭 Control por origen / archivo"
    ])

    with tab1:
        mostrar_libro_diario()

    with tab2:
        mostrar_libro_mayor()

    with tab3:
        mostrar_balance_sumas_saldos()

    with tab4:
        mostrar_control_origen_archivo()


# ======================================================
# LIBRO DIARIO
# ======================================================

def mostrar_libro_diario():
    st.subheader("📓 Libro Diario")

    mostrar_alerta_redondeo()

    df = cargar_libro_diario()

    if df.empty:
        st.info("Sin movimientos contables.")
        return

    df = aplicar_filtros_contables(df, "diario")

    if df.empty:
        st.info("No hay movimientos con los filtros seleccionados.")
        return

    df = df.sort_values(
        by=["fecha_orden", "id_asiento", "id"],
        ascending=True,
        na_position="last"
    )

    df_vista = df[[
        "id_asiento",
        "fecha_mostrar",
        "cuenta",
        "debe",
        "haber",
        "glosa",
        "origen",
        "archivo"
    ]].copy()

    df_vista = df_vista.rename(columns={
        "id_asiento": "Asiento",
        "fecha_mostrar": "Fecha",
        "cuenta": "Cuenta",
        "debe": "Debe",
        "haber": "Haber",
        "glosa": "Glosa",
        "origen": "Origen",
        "archivo": "Archivo"
    })

    df_vista_con_espacios = insertar_espacios_entre_asientos(
        df_vista.rename(columns={
            "Asiento": "id_asiento",
            "Fecha": "fecha",
            "Cuenta": "cuenta",
            "Debe": "debe",
            "Haber": "haber",
            "Glosa": "glosa",
            "Origen": "origen",
            "Archivo": "archivo"
        })
    )

    df_vista_con_espacios = df_vista_con_espacios.rename(columns={
        "id_asiento": "Asiento",
        "fecha": "Fecha",
        "cuenta": "Cuenta",
        "debe": "Debe",
        "haber": "Haber",
        "glosa": "Glosa",
        "origen": "Origen",
        "archivo": "Archivo"
    })

    st.dataframe(
        preparar_vista(df_vista_con_espacios),
        use_container_width=True
    )

    st.divider()

    mostrar_metricas_cuadre(df)

    excel = exportar_excel({
        "Libro Diario": df_vista
    })

    st.download_button(
        "Descargar Libro Diario Excel",
        data=excel,
        file_name="libro_diario.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    st.divider()

    if "confirmar_limpiar_diario" not in st.session_state:
        st.session_state["confirmar_limpiar_diario"] = False

    if st.button("🧹 Limpiar Libro Diario"):
        st.session_state["confirmar_limpiar_diario"] = True

    if st.session_state["confirmar_limpiar_diario"]:
        st.warning("¿Confirmás eliminar todos los movimientos del Libro Diario?")

        col1, col2 = st.columns(2)

        with col1:
            if st.button("Sí, limpiar libro diario"):
                eliminar_todo_diario()
                st.success("Libro Diario limpiado.")
                st.session_state["confirmar_limpiar_diario"] = False
                st.rerun()

        with col2:
            if st.button("Cancelar"):
                st.session_state["confirmar_limpiar_diario"] = False
                st.rerun()


# ======================================================
# LIBRO MAYOR
# ======================================================

def mostrar_libro_mayor():
    st.subheader("📒 Libro Mayor")

    df = cargar_libro_diario()

    if df.empty:
        st.info("Sin movimientos contables.")
        return

    df = aplicar_filtros_contables(df, "mayor")

    if df.empty:
        st.info("No hay movimientos con los filtros seleccionados.")
        return

    resumen_cuentas = (
        df
        .groupby("cuenta", dropna=False)
        .agg(
            movimientos=("id", "count"),
            debe=("debe", "sum"),
            haber=("haber", "sum")
        )
        .reset_index()
    )

    resumen_cuentas["saldo"] = resumen_cuentas["debe"] - resumen_cuentas["haber"]
    resumen_cuentas["saldo_deudor"] = resumen_cuentas["saldo"].apply(lambda x: x if x > 0 else 0)
    resumen_cuentas["saldo_acreedor"] = resumen_cuentas["saldo"].apply(lambda x: abs(x) if x < 0 else 0)

    resumen_cuentas = resumen_cuentas.sort_values("cuenta")

    vista_resumen = resumen_cuentas.rename(columns={
        "cuenta": "Cuenta",
        "movimientos": "Movimientos",
        "debe": "Debe",
        "haber": "Haber",
        "saldo": "Saldo",
        "saldo_deudor": "Saldo Deudor",
        "saldo_acreedor": "Saldo Acreedor"
    })

    st.subheader("Resumen por cuenta")
    st.dataframe(
        preparar_vista(vista_resumen),
        use_container_width=True
    )

    st.divider()

    cuentas = sorted(df["cuenta"].dropna().astype(str).unique().tolist())

    cuenta_detalle = st.selectbox(
        "Ver detalle de cuenta",
        cuentas,
        key="mayor_detalle_cuenta"
    )

    df_detalle = df[df["cuenta"] == cuenta_detalle].copy()

    df_detalle = df_detalle.sort_values(
        by=["fecha_orden", "id_asiento", "id"],
        ascending=True,
        na_position="last"
    )

    df_detalle["saldo_movimiento"] = df_detalle["debe"] - df_detalle["haber"]
    df_detalle["saldo_acumulado"] = df_detalle["saldo_movimiento"].cumsum()

    vista_detalle = df_detalle[[
        "fecha_mostrar",
        "id_asiento",
        "glosa",
        "debe",
        "haber",
        "saldo_acumulado",
        "origen",
        "archivo"
    ]].copy()

    vista_detalle = vista_detalle.rename(columns={
        "fecha_mostrar": "Fecha",
        "id_asiento": "Asiento",
        "glosa": "Glosa",
        "debe": "Debe",
        "haber": "Haber",
        "saldo_acumulado": "Saldo acumulado",
        "origen": "Origen",
        "archivo": "Archivo"
    })

    st.subheader(f"Detalle mayor: {cuenta_detalle}")
    st.dataframe(
        preparar_vista(vista_detalle),
        use_container_width=True
    )

    excel = exportar_excel({
        "Mayor resumen": vista_resumen,
        "Mayor detalle": vista_detalle
    })

    st.download_button(
        "Descargar Libro Mayor Excel",
        data=excel,
        file_name="libro_mayor.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


# ======================================================
# BALANCE DE SUMAS Y SALDOS
# ======================================================

def mostrar_balance_sumas_saldos():
    st.subheader("📊 Balance de Sumas y Saldos")

    df = cargar_libro_diario()

    if df.empty:
        st.info("Sin movimientos contables.")
        return

    df = aplicar_filtros_contables(df, "balance")

    if df.empty:
        st.info("No hay movimientos con los filtros seleccionados.")
        return

    balance = (
        df
        .groupby("cuenta", dropna=False)
        .agg(
            debe=("debe", "sum"),
            haber=("haber", "sum")
        )
        .reset_index()
    )

    balance["saldo"] = balance["debe"] - balance["haber"]
    balance["saldo_deudor"] = balance["saldo"].apply(lambda x: x if x > 0 else 0)
    balance["saldo_acreedor"] = balance["saldo"].apply(lambda x: abs(x) if x < 0 else 0)

    balance = balance.sort_values("cuenta")

    total_debe = balance["debe"].sum()
    total_haber = balance["haber"].sum()
    total_saldo_deudor = balance["saldo_deudor"].sum()
    total_saldo_acreedor = balance["saldo_acreedor"].sum()

    vista_balance = balance.rename(columns={
        "cuenta": "Cuenta",
        "debe": "Sumas Debe",
        "haber": "Sumas Haber",
        "saldo": "Saldo técnico",
        "saldo_deudor": "Saldo Deudor",
        "saldo_acreedor": "Saldo Acreedor"
    })

    st.dataframe(
        preparar_vista(vista_balance),
        use_container_width=True
    )

    st.divider()

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Total Sumas Debe", moneda(total_debe))
    c2.metric("Total Sumas Haber", moneda(total_haber))
    c3.metric("Total Saldo Deudor", moneda(total_saldo_deudor))
    c4.metric("Total Saldo Acreedor", moneda(total_saldo_acreedor))

    diferencia_sumas = round(total_debe - total_haber, 2)
    diferencia_saldos = round(total_saldo_deudor - total_saldo_acreedor, 2)

    if diferencia_sumas != 0:
        st.error(f"Las sumas no cuadran. Diferencia: {moneda(diferencia_sumas)}")
    else:
        st.success("Las sumas Debe y Haber cuadran.")

    if diferencia_saldos != 0:
        st.error(f"Los saldos no cuadran. Diferencia: {moneda(diferencia_saldos)}")
    else:
        st.success("Los saldos deudores y acreedores cuadran.")

    excel = exportar_excel({
        "Balance Sumas y Saldos": vista_balance
    })

    st.download_button(
        "Descargar Balance de Sumas y Saldos Excel",
        data=excel,
        file_name="balance_sumas_saldos.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


# ======================================================
# CONTROL POR ORIGEN / ARCHIVO
# ======================================================

def mostrar_control_origen_archivo():
    st.subheader("🧭 Control por origen / archivo")

    df = cargar_libro_diario()

    if df.empty:
        st.info("Sin movimientos contables.")
        return

    df = aplicar_filtros_contables(df, "control")

    if df.empty:
        st.info("No hay movimientos con los filtros seleccionados.")
        return

    resumen_origen = (
        df
        .groupby("origen", dropna=False)
        .agg(
            movimientos=("id", "count"),
            debe=("debe", "sum"),
            haber=("haber", "sum")
        )
        .reset_index()
    )

    resumen_origen["diferencia"] = resumen_origen["debe"] - resumen_origen["haber"]

    resumen_archivo = (
        df
        .groupby(["origen", "archivo"], dropna=False)
        .agg(
            movimientos=("id", "count"),
            debe=("debe", "sum"),
            haber=("haber", "sum")
        )
        .reset_index()
    )

    resumen_archivo["diferencia"] = resumen_archivo["debe"] - resumen_archivo["haber"]

    st.subheader("Resumen por origen")
    st.dataframe(
        preparar_vista(resumen_origen),
        use_container_width=True
    )

    st.divider()

    st.subheader("Resumen por archivo")
    st.dataframe(
        preparar_vista(resumen_archivo),
        use_container_width=True
    )

    st.divider()

    descuadres = resumen_archivo[resumen_archivo["diferencia"].round(2) != 0].copy()

    if descuadres.empty:
        st.success("No se detectan archivos descuadrados en el Libro Diario.")
    else:
        st.error("Se detectan archivos con diferencia entre Debe y Haber.")
        st.dataframe(
            preparar_vista(descuadres),
            use_container_width=True
        )

    excel = exportar_excel({
        "Resumen por Origen": resumen_origen,
        "Resumen por Archivo": resumen_archivo,
        "Archivos Descuadrados": descuadres
    })

    st.download_button(
        "Descargar Control Contable Excel",
        data=excel,
        file_name="control_contable_origen_archivo.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )