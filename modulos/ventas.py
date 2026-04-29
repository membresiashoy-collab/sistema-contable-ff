import streamlit as st
import pandas as pd
from datetime import date

from database import ejecutar_query
from services.ventas_service import procesar_csv_ventas

from core.fechas import ordenar_dataframe_por_fecha, fecha_para_ordenar, formatear_fecha
from core.exportadores import exportar_excel
from core.ui import preparar_vista
from core.numeros import moneda


# ======================================================
# UTILIDADES GENERALES
# ======================================================

def numero_seguro(valor):
    try:
        if pd.isna(valor):
            return 0.0

        if isinstance(valor, str):
            valor = valor.strip()
            valor = valor.replace("$", "")
            valor = valor.replace(" ", "")

            if "," in valor and "." in valor:
                valor = valor.replace(".", "").replace(",", ".")
            elif "," in valor:
                valor = valor.replace(",", ".")

        return float(valor)

    except Exception:
        return 0.0


def convertir_numero(serie):
    return serie.apply(numero_seguro)


def texto_seguro(valor):
    if pd.isna(valor):
        return ""

    return str(valor).strip()


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


def calcular_dias_antiguedad(fecha_orden):
    try:
        fecha_dt = pd.to_datetime(fecha_orden, errors="coerce")

        if pd.isna(fecha_dt):
            return None

        return max((pd.Timestamp(date.today()) - fecha_dt).days, 0)

    except Exception:
        return None


def bucket_antiguedad(dias):
    if dias is None:
        return "Sin fecha"

    try:
        dias = int(dias)
    except Exception:
        return "Sin fecha"

    if dias <= 30:
        return "0 a 30 días"

    if dias <= 60:
        return "31 a 60 días"

    if dias <= 90:
        return "61 a 90 días"

    return "Más de 90 días"


def estado_saldo_cliente(saldo):
    saldo = numero_seguro(saldo)

    if abs(saldo) <= 0.01:
        return "Cancelado"

    if saldo > 0:
        return "Pendiente"

    return "Anticipo / saldo a favor"


def tipo_movimiento_cliente(debe, haber):
    debe = numero_seguro(debe)
    haber = numero_seguro(haber)

    if debe > 0 and haber == 0:
        return "Venta / deuda"

    if haber > 0 and debe == 0:
        return "Cobro / cancelación"

    if debe > 0 and haber > 0:
        return "Movimiento mixto"

    return "Sin importe"


# ======================================================
# PANTALLA PRINCIPAL
# ======================================================

def mostrar_ventas():

    tab1, tab2, tab3, tab4 = st.tabs([
        "Cargar CSV ARCA",
        "Libro IVA Ventas",
        "Resumen / Estadísticas",
        "Cuenta corriente clientes"
    ])

    with tab1:
        cargar_csv_ventas()

    with tab2:
        mostrar_libro_iva_ventas()

    with tab3:
        mostrar_resumen_ventas()

    with tab4:
        mostrar_cuenta_corriente_clientes()


# ======================================================
# TAB 1 - CARGA CSV
# ======================================================

def cargar_csv_ventas():
    st.info(
        "Carga CSV ARCA/AFIP, genera asientos contables, guarda Libro IVA Ventas "
        "y actualiza cuenta corriente de clientes."
    )

    archivo = st.file_uploader("Subir CSV Ventas ARCA/AFIP", type=["csv"])

    if not archivo:
        return

    st.caption(
        "Podés volver a cargar un archivo con el mismo nombre. "
        "El sistema no duplica comprobantes: importa solo operaciones nuevas "
        "y omite las que ya estén registradas."
    )

    try:
        df = pd.read_csv(
            archivo,
            sep=None,
            engine="python",
            encoding="latin-1",
            dtype=str
        )

        df = ordenar_dataframe_por_fecha(df, columna_indice=0)

        st.subheader("Vista previa")
        st.dataframe(preparar_vista(df.head(20)), use_container_width=True)

        st.caption(f"Registros detectados: {len(df)}")

        if not st.button("Procesar Ventas"):
            return

        resultado = procesar_csv_ventas(archivo.name, df)

        if resultado["procesados"] > 0:
            st.success("Proceso finalizado. Se importaron operaciones nuevas.")
        elif resultado["duplicados"] > 0 and resultado["errores"] == 0:
            st.info(
                "Proceso finalizado. No se importaron operaciones nuevas porque "
                "los comprobantes del archivo ya estaban registrados."
            )
        else:
            st.success("Proceso finalizado")

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Procesados", resultado["procesados"])
            st.metric("Facturas", resultado["facturas"])

        with col2:
            st.metric("Notas de Crédito", resultado["notas_credito"])
            st.metric("Notas de Débito", resultado["notas_debito"])

        with col3:
            st.metric("Errores reales", resultado["errores"])
            st.metric("Duplicados omitidos", resultado["duplicados"])

        st.divider()

        st.subheader("Detalle de auditoría")
        st.write(f"Errores matemáticos: {resultado['errores_matematicos']}")
        st.write(f"Códigos inexistentes: {resultado['errores_codigo']}")
        st.write(f"Duplicados omitidos: {resultado['duplicados']}")
        st.write(f"Ajustes técnicos de centavos sobre neto: {resultado['ajustes_centavos']}")

        if resultado["duplicados"] > 0:
            st.info(
                "Los duplicados fueron omitidos para evitar repetir comprobantes, "
                "asientos, Libro IVA Ventas y cuenta corriente de clientes."
            )

        if resultado["errores"] > 0:
            st.warning("Se detectaron errores reales. Revisar Estado de Cargas / Auditoría.")

    except Exception as e:
        st.error(f"No se pudo leer el archivo: {str(e)}")


# ======================================================
# TAB 2 - LIBRO IVA VENTAS
# ======================================================

def mostrar_libro_iva_ventas():
    st.subheader("📘 Libro IVA Ventas")

    df = ejecutar_query("""
        SELECT 
            fecha,
            anio,
            mes,
            tipo,
            numero,
            cliente,
            cuit,
            neto,
            iva,
            total,
            archivo
        FROM ventas_comprobantes
    """, fetch=True)

    if df.empty:
        st.info("No hay ventas cargadas.")
        return

    df = df.copy()

    df["neto"] = convertir_numero(df["neto"])
    df["iva"] = convertir_numero(df["iva"])
    df["total"] = convertir_numero(df["total"])

    df["fecha_orden"] = df["fecha"].apply(fecha_orden_segura)
    df["fecha"] = df["fecha"].apply(fecha_formateada_segura)

    df = df.sort_values(
        by=["anio", "mes", "fecha_orden", "numero"],
        ascending=True,
        na_position="last"
    )

    col1, col2, col3 = st.columns(3)

    anios = ["Todos"] + sorted(df["anio"].dropna().unique().tolist())
    meses = ["Todos"] + sorted(df["mes"].dropna().unique().tolist())
    clientes = ["Todos"] + sorted(df["cliente"].dropna().unique().tolist())

    with col1:
        anio = st.selectbox("Año", anios, key="iva_ventas_anio")

    with col2:
        mes = st.selectbox("Mes", meses, key="iva_ventas_mes")

    with col3:
        cliente = st.selectbox("Cliente", clientes, key="iva_ventas_cliente")

    if anio != "Todos":
        df = df[df["anio"] == anio]

    if mes != "Todos":
        df = df[df["mes"] == mes]

    if cliente != "Todos":
        df = df[df["cliente"] == cliente]

    df_vista = df.drop(columns=["fecha_orden"])

    st.dataframe(preparar_vista(df_vista), use_container_width=True)

    c1, c2, c3 = st.columns(3)

    c1.metric("Neto", moneda(df["neto"].sum()))
    c2.metric("IVA Débito Fiscal", moneda(df["iva"].sum()))
    c3.metric("Total", moneda(df["total"].sum()))

    excel = exportar_excel({
        "Libro IVA Ventas": df_vista
    })

    st.download_button(
        "Descargar Libro IVA Ventas Excel",
        data=excel,
        file_name="libro_iva_ventas.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


# ======================================================
# TAB 3 - RESUMEN / ESTADÍSTICAS
# ======================================================

def mostrar_resumen_ventas():
    st.subheader("📊 Resumen / Estadísticas de Ventas")

    df = ejecutar_query("""
        SELECT 
            fecha,
            anio,
            mes,
            tipo,
            cliente,
            cuit,
            neto,
            iva,
            total,
            archivo
        FROM ventas_comprobantes
    """, fetch=True)

    if df.empty:
        st.info("No hay ventas cargadas.")
        return

    df = df.copy()

    df["neto"] = convertir_numero(df["neto"])
    df["iva"] = convertir_numero(df["iva"])
    df["total"] = convertir_numero(df["total"])
    df["fecha"] = df["fecha"].apply(fecha_formateada_segura)

    resumen_mensual = df.groupby(["anio", "mes"], as_index=False).agg({
        "neto": "sum",
        "iva": "sum",
        "total": "sum",
        "tipo": "count"
    })

    resumen_mensual = resumen_mensual.rename(columns={
        "tipo": "cantidad_comprobantes"
    })

    resumen_tipo = df.groupby(["tipo"], as_index=False).agg({
        "neto": "sum",
        "iva": "sum",
        "total": "sum",
        "cliente": "count"
    })

    resumen_tipo = resumen_tipo.rename(columns={
        "cliente": "cantidad"
    })

    ranking_clientes = df.groupby(["cliente", "cuit"], as_index=False).agg({
        "total": "sum",
        "tipo": "count"
    })

    ranking_clientes = ranking_clientes.rename(columns={
        "tipo": "cantidad_comprobantes"
    })

    ranking_clientes = ranking_clientes.sort_values(by="total", ascending=False)

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Total Neto", moneda(df["neto"].sum()))
    col2.metric("IVA Débito", moneda(df["iva"].sum()))
    col3.metric("Total Facturado", moneda(df["total"].sum()))
    col4.metric("Comprobantes", len(df))

    st.divider()

    st.subheader("Resumen mensual")
    st.dataframe(preparar_vista(resumen_mensual), use_container_width=True)

    st.subheader("Resumen por tipo de comprobante")
    st.dataframe(preparar_vista(resumen_tipo), use_container_width=True)

    st.subheader("Ranking de clientes")
    st.dataframe(preparar_vista(ranking_clientes), use_container_width=True)

    excel = exportar_excel({
        "Resumen Mensual": resumen_mensual,
        "Resumen Tipo": resumen_tipo,
        "Ranking Clientes": ranking_clientes
    })

    st.download_button(
        "Descargar Estadísticas Excel",
        data=excel,
        file_name="estadisticas_ventas.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


# ======================================================
# TAB 4 - CUENTA CORRIENTE CLIENTES PRO
# ======================================================

def leer_cuenta_corriente_clientes():
    try:
        return ejecutar_query("""
            SELECT 
                id,
                fecha,
                cliente,
                cuit,
                tipo,
                numero,
                debe,
                haber,
                origen,
                archivo
            FROM cuenta_corriente_clientes
            ORDER BY cliente, fecha, id
        """, fetch=True)

    except Exception:
        return pd.DataFrame()


def preparar_cuenta_corriente_clientes(df_raw):
    if df_raw.empty:
        return pd.DataFrame()

    df = df_raw.copy()

    df["id"] = convertir_numero(df["id"])
    df["fecha_original"] = df["fecha"].apply(texto_seguro)
    df["fecha_orden"] = df["fecha_original"].apply(fecha_orden_segura)
    df["fecha"] = df["fecha_original"].apply(fecha_formateada_segura)

    df["cliente"] = df["cliente"].apply(texto_seguro)
    df["cuit"] = df["cuit"].apply(texto_seguro)
    df["tipo"] = df["tipo"].apply(texto_seguro)
    df["numero"] = df["numero"].apply(texto_seguro)
    df["origen"] = df["origen"].apply(texto_seguro)
    df["archivo"] = df["archivo"].apply(texto_seguro)

    df["debe"] = convertir_numero(df["debe"])
    df["haber"] = convertir_numero(df["haber"])

    df["comprobante"] = (
        df["tipo"].astype(str).str.strip()
        + " "
        + df["numero"].astype(str).str.strip()
    ).str.strip()

    df.loc[df["comprobante"] == "", "comprobante"] = (
        "Movimiento " + df["id"].astype(int).astype(str)
    )

    df["comprobante_key"] = (
        df["cliente"].astype(str).str.upper().str.strip()
        + "|"
        + df["cuit"].astype(str).str.upper().str.strip()
        + "|"
        + df["tipo"].astype(str).str.upper().str.strip()
        + "|"
        + df["numero"].astype(str).str.upper().str.strip()
    )

    df["impacto_saldo"] = df["debe"] - df["haber"]
    df["tipo_movimiento"] = df.apply(
        lambda fila: tipo_movimiento_cliente(fila["debe"], fila["haber"]),
        axis=1
    )

    df["dias_antiguedad"] = df["fecha_orden"].apply(calcular_dias_antiguedad)
    df["antiguedad"] = df["dias_antiguedad"].apply(bucket_antiguedad)

    df = df.sort_values(
        by=["cliente", "cuit", "fecha_orden", "id"],
        ascending=True,
        na_position="last"
    )

    df["saldo_acumulado_cliente"] = (
        df
        .groupby(["cliente", "cuit"], dropna=False)["impacto_saldo"]
        .cumsum()
    )

    return df


def construir_resumen_clientes(df):
    if df.empty:
        return pd.DataFrame()

    resumen = (
        df
        .groupby(["cliente", "cuit"], dropna=False)
        .agg(
            movimientos=("id", "count"),
            debe=("debe", "sum"),
            haber=("haber", "sum"),
            saldo=("impacto_saldo", "sum"),
            primer_fecha=("fecha_orden", "min"),
            ultima_fecha=("fecha_orden", "max")
        )
        .reset_index()
    )

    resumen["estado"] = resumen["saldo"].apply(estado_saldo_cliente)
    resumen["dias_antiguedad"] = resumen["primer_fecha"].apply(calcular_dias_antiguedad)
    resumen["antiguedad"] = resumen["dias_antiguedad"].apply(bucket_antiguedad)
    resumen["primer_fecha"] = resumen["primer_fecha"].apply(fecha_formateada_segura)
    resumen["ultima_fecha"] = resumen["ultima_fecha"].apply(fecha_formateada_segura)

    resumen = resumen.sort_values(
        by=["estado", "saldo", "cliente"],
        ascending=[False, False, True]
    )

    return resumen


def construir_resumen_comprobantes_clientes(df):
    if df.empty:
        return pd.DataFrame()

    resumen = (
        df
        .groupby(["cliente", "cuit", "comprobante_key", "comprobante"], dropna=False)
        .agg(
            movimientos=("id", "count"),
            debe=("debe", "sum"),
            haber=("haber", "sum"),
            saldo=("impacto_saldo", "sum"),
            fecha=("fecha_orden", "min"),
            archivo=("archivo", "first"),
            origen=("origen", "first")
        )
        .reset_index()
    )

    resumen["estado"] = resumen["saldo"].apply(estado_saldo_cliente)
    resumen["dias_antiguedad"] = resumen["fecha"].apply(calcular_dias_antiguedad)
    resumen["antiguedad"] = resumen["dias_antiguedad"].apply(bucket_antiguedad)
    resumen["fecha"] = resumen["fecha"].apply(fecha_formateada_segura)

    resumen = resumen.sort_values(
        by=["estado", "saldo", "fecha", "cliente"],
        ascending=[False, False, True, True]
    )

    return resumen


def construir_alertas_cuenta_corriente_clientes(df, resumen_comprobantes):
    alertas = []

    if df.empty:
        return pd.DataFrame(columns=["tipo", "cantidad", "detalle"])

    sin_cliente = df[df["cliente"].astype(str).str.strip() == ""]

    if not sin_cliente.empty:
        alertas.append({
            "tipo": "Datos incompletos",
            "cantidad": len(sin_cliente),
            "detalle": "Movimientos sin cliente identificado."
        })

    sin_cuit = df[df["cuit"].astype(str).str.strip() == ""]

    if not sin_cuit.empty:
        alertas.append({
            "tipo": "Datos incompletos",
            "cantidad": len(sin_cuit),
            "detalle": "Movimientos sin CUIT. No bloquea, pero dificulta conciliación bancaria futura."
        })

    sin_fecha = df[df["fecha_orden"].isna()]

    if not sin_fecha.empty:
        alertas.append({
            "tipo": "Fecha no interpretable",
            "cantidad": len(sin_fecha),
            "detalle": "Movimientos con fecha vacía o no interpretable."
        })

    sin_numero = resumen_comprobantes[
        resumen_comprobantes["comprobante"].astype(str).str.startswith("Movimiento ")
    ]

    if not sin_numero.empty:
        alertas.append({
            "tipo": "Comprobante incompleto",
            "cantidad": len(sin_numero),
            "detalle": "Movimientos sin tipo o número de comprobante."
        })

    saldos_a_favor = resumen_comprobantes[resumen_comprobantes["saldo"] < -0.01]

    if not saldos_a_favor.empty:
        alertas.append({
            "tipo": "Anticipos / saldos a favor",
            "cantidad": len(saldos_a_favor),
            "detalle": "Hay comprobantes o movimientos con saldo negativo. Puede ser anticipo, cobro duplicado o imputación futura."
        })

    pendientes_90 = resumen_comprobantes[
        (resumen_comprobantes["saldo"] > 0.01)
        & (resumen_comprobantes["dias_antiguedad"].fillna(0) > 90)
    ]

    if not pendientes_90.empty:
        alertas.append({
            "tipo": "Pendientes antiguos",
            "cantidad": len(pendientes_90),
            "detalle": "Hay saldos pendientes con más de 90 días según fecha del comprobante."
        })

    if df["haber"].sum() == 0:
        alertas.append({
            "tipo": "Sin cobranzas registradas",
            "cantidad": 0,
            "detalle": "La cuenta corriente tiene deudas pero no registra cobros. Es normal si todavía no implementamos Banco/Caja."
        })

    if not alertas:
        alertas.append({
            "tipo": "Sin alertas críticas",
            "cantidad": 0,
            "detalle": "No se detectaron inconsistencias básicas en la cuenta corriente filtrada."
        })

    return pd.DataFrame(alertas)


def aplicar_filtros_cuenta_corriente_clientes(df):
    st.subheader("Filtros")

    col1, col2, col3, col4 = st.columns([2, 1, 1, 1])

    with col1:
        busqueda = st.text_input(
            "Buscar cliente por nombre, CUIT, comprobante o archivo",
            key="cc_clientes_busqueda"
        ).strip().lower()

    with col2:
        tipos = ["Todos"] + sorted(df["tipo_movimiento"].dropna().unique().tolist())
        tipo_sel = st.selectbox(
            "Tipo movimiento",
            tipos,
            key="cc_clientes_tipo_mov"
        )

    with col3:
        antiguedades = [
            "Todas",
            "0 a 30 días",
            "31 a 60 días",
            "61 a 90 días",
            "Más de 90 días",
            "Sin fecha"
        ]

        antiguedad_sel = st.selectbox(
            "Antigüedad",
            antiguedades,
            key="cc_clientes_antiguedad"
        )

    with col4:
        archivos = ["Todos"] + sorted(
            df["archivo"]
            .dropna()
            .astype(str)
            .replace("", "Sin archivo")
            .unique()
            .tolist()
        )

        archivo_sel = st.selectbox(
            "Archivo",
            archivos,
            key="cc_clientes_archivo"
        )

    df_filtrado = df.copy()

    if busqueda:
        texto_busqueda = (
            df_filtrado["cliente"].astype(str)
            + " "
            + df_filtrado["cuit"].astype(str)
            + " "
            + df_filtrado["comprobante"].astype(str)
            + " "
            + df_filtrado["archivo"].astype(str)
        ).str.lower()

        df_filtrado = df_filtrado[texto_busqueda.str.contains(busqueda, na=False)]

    if tipo_sel != "Todos":
        df_filtrado = df_filtrado[df_filtrado["tipo_movimiento"] == tipo_sel]

    if antiguedad_sel != "Todas":
        df_filtrado = df_filtrado[df_filtrado["antiguedad"] == antiguedad_sel]

    if archivo_sel != "Todos":
        if archivo_sel == "Sin archivo":
            df_filtrado = df_filtrado[df_filtrado["archivo"].astype(str).str.strip() == ""]
        else:
            df_filtrado = df_filtrado[df_filtrado["archivo"] == archivo_sel]

    return df_filtrado


def mostrar_metricas_cuenta_corriente_clientes(df, resumen_clientes, resumen_comprobantes):
    saldo_total = resumen_comprobantes["saldo"].sum() if not resumen_comprobantes.empty else 0.0

    saldo_a_cobrar = resumen_comprobantes[
        resumen_comprobantes["saldo"] > 0.01
    ]["saldo"].sum() if not resumen_comprobantes.empty else 0.0

    saldo_a_favor = resumen_comprobantes[
        resumen_comprobantes["saldo"] < -0.01
    ]["saldo"].sum() if not resumen_comprobantes.empty else 0.0

    comprobantes_pendientes = len(
        resumen_comprobantes[resumen_comprobantes["saldo"] > 0.01]
    ) if not resumen_comprobantes.empty else 0

    clientes = resumen_clientes["cliente"].nunique() if not resumen_clientes.empty else 0
    movimientos = len(df)

    c1, c2, c3, c4, c5 = st.columns(5)

    c1.metric("Clientes", clientes)
    c2.metric("Movimientos", movimientos)
    c3.metric("Comprobantes pendientes", comprobantes_pendientes)
    c4.metric("Saldo a cobrar", moneda(saldo_a_cobrar))
    c5.metric("Anticipos / saldos a favor", moneda(abs(saldo_a_favor)))

    st.caption(
        f"Saldo neto técnico filtrado: **{moneda(saldo_total)}**. "
        "Los saldos negativos se muestran separados para no mezclar deuda real con anticipos o cobros a cuenta."
    )


def mostrar_cuenta_corriente_clientes():
    st.subheader("💰 Cuenta corriente clientes PRO")

    st.info(
        "Esta vista muestra saldos de clientes por entidad y comprobante. "
        "Es la base para la futura imputación de cobros, caja y conciliación bancaria."
    )

    df_raw = leer_cuenta_corriente_clientes()

    if df_raw.empty:
        st.info("No hay movimientos de cuenta corriente de clientes.")
        return

    df = preparar_cuenta_corriente_clientes(df_raw)

    if df.empty:
        st.info("No hay movimientos preparados para mostrar.")
        return

    df_filtrado = aplicar_filtros_cuenta_corriente_clientes(df)

    if df_filtrado.empty:
        st.info("No hay movimientos con los filtros seleccionados.")
        return

    resumen_clientes = construir_resumen_clientes(df_filtrado)
    resumen_comprobantes = construir_resumen_comprobantes_clientes(df_filtrado)

    mostrar_metricas_cuenta_corriente_clientes(
        df_filtrado,
        resumen_clientes,
        resumen_comprobantes
    )

    st.divider()

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Resumen por cliente",
        "Comprobantes pendientes",
        "Detalle de movimientos",
        "Antigüedad",
        "Alertas"
    ])

    with tab1:
        st.subheader("Resumen por cliente")

        vista = resumen_clientes[[
            "cliente",
            "cuit",
            "movimientos",
            "debe",
            "haber",
            "saldo",
            "estado",
            "antiguedad",
            "primer_fecha",
            "ultima_fecha"
        ]].copy()

        vista = vista.rename(columns={
            "cliente": "Cliente",
            "cuit": "CUIT",
            "movimientos": "Movimientos",
            "debe": "Facturado / Debe",
            "haber": "Cobrado / Haber",
            "saldo": "Saldo a cobrar",
            "estado": "Estado",
            "antiguedad": "Antigüedad",
            "primer_fecha": "Primer movimiento",
            "ultima_fecha": "Último movimiento"
        })

        st.dataframe(preparar_vista(vista), use_container_width=True)

    with tab2:
        st.subheader("Comprobantes pendientes / saldos abiertos")

        pendientes = resumen_comprobantes[
            resumen_comprobantes["estado"] != "Cancelado"
        ].copy()

        if pendientes.empty:
            st.success("No hay comprobantes pendientes con los filtros seleccionados.")
        else:
            vista = pendientes[[
                "fecha",
                "cliente",
                "cuit",
                "comprobante",
                "debe",
                "haber",
                "saldo",
                "estado",
                "antiguedad",
                "archivo",
                "origen"
            ]].copy()

            vista = vista.rename(columns={
                "fecha": "Fecha",
                "cliente": "Cliente",
                "cuit": "CUIT",
                "comprobante": "Comprobante",
                "debe": "Facturado / Debe",
                "haber": "Cobrado / Haber",
                "saldo": "Saldo a cobrar",
                "estado": "Estado",
                "antiguedad": "Antigüedad",
                "archivo": "Archivo",
                "origen": "Origen"
            })

            st.dataframe(preparar_vista(vista), use_container_width=True)

    with tab3:
        st.subheader("Detalle de movimientos")

        detalle = df_filtrado[[
            "fecha",
            "cliente",
            "cuit",
            "comprobante",
            "tipo_movimiento",
            "debe",
            "haber",
            "impacto_saldo",
            "saldo_acumulado_cliente",
            "antiguedad",
            "origen",
            "archivo"
        ]].copy()

        detalle = detalle.rename(columns={
            "fecha": "Fecha",
            "cliente": "Cliente",
            "cuit": "CUIT",
            "comprobante": "Comprobante",
            "tipo_movimiento": "Tipo movimiento",
            "debe": "Facturado / Debe",
            "haber": "Cobrado / Haber",
            "impacto_saldo": "Impacto saldo",
            "saldo_acumulado_cliente": "Saldo acumulado cliente",
            "antiguedad": "Antigüedad",
            "origen": "Origen",
            "archivo": "Archivo"
        })

        st.dataframe(preparar_vista(detalle), use_container_width=True)

    with tab4:
        st.subheader("Análisis por antigüedad")

        pendientes = resumen_comprobantes[
            resumen_comprobantes["saldo"] > 0.01
        ].copy()

        if pendientes.empty:
            st.success("No hay saldos pendientes para analizar por antigüedad.")
        else:
            aging = (
                pendientes
                .groupby("antiguedad", dropna=False)
                .agg(
                    comprobantes=("comprobante", "count"),
                    saldo=("saldo", "sum")
                )
                .reset_index()
            )

            orden = {
                "0 a 30 días": 1,
                "31 a 60 días": 2,
                "61 a 90 días": 3,
                "Más de 90 días": 4,
                "Sin fecha": 5
            }

            aging["_orden"] = aging["antiguedad"].map(orden).fillna(99)
            aging = aging.sort_values("_orden").drop(columns=["_orden"])

            aging = aging.rename(columns={
                "antiguedad": "Antigüedad",
                "comprobantes": "Comprobantes",
                "saldo": "Saldo a cobrar"
            })

            st.dataframe(preparar_vista(aging), use_container_width=True)

            st.caption(
                "La antigüedad se calcula por fecha del comprobante. "
                "Más adelante, al incorporar vencimientos, se podrá calcular mora real."
            )

    with tab5:
        st.subheader("Alertas de calidad de datos")

        alertas = construir_alertas_cuenta_corriente_clientes(
            df_filtrado,
            resumen_comprobantes
        )

        st.dataframe(preparar_vista(alertas), use_container_width=True)

    st.divider()

    pendientes_exportar = resumen_comprobantes[
        resumen_comprobantes["estado"] != "Cancelado"
    ].copy()

    detalle_exportar = df_filtrado[[
        "fecha",
        "cliente",
        "cuit",
        "comprobante",
        "tipo_movimiento",
        "debe",
        "haber",
        "impacto_saldo",
        "saldo_acumulado_cliente",
        "antiguedad",
        "origen",
        "archivo"
    ]].copy()

    alertas_exportar = construir_alertas_cuenta_corriente_clientes(
        df_filtrado,
        resumen_comprobantes
    )

    excel = exportar_excel({
        "Resumen clientes": resumen_clientes,
        "Comprobantes": resumen_comprobantes,
        "Pendientes": pendientes_exportar,
        "Movimientos": detalle_exportar,
        "Alertas": alertas_exportar
    })

    st.download_button(
        "Descargar Cuenta Corriente Clientes PRO Excel",
        data=excel,
        file_name="cuenta_corriente_clientes_pro.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )