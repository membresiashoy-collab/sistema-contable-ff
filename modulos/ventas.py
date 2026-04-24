import streamlit as st
import pandas as pd
from io import BytesIO

from database import (
    ejecutar_query,
    registrar_carga,
    proximo_asiento,
    archivo_ya_cargado,
    comprobante_ya_procesado,
    registrar_comprobante,
    registrar_error,
    tipo_comprobante_existe,
    registrar_venta,
    registrar_cta_cte_cliente
)


def limpiar_num(v):
    try:
        if pd.isna(v):
            return 0.0
        valor = str(v).strip()
        if valor == "":
            return 0.0
        valor = valor.replace(".", "").replace(",", ".")
        return float(valor)
    except Exception:
        return 0.0


def formatear_fecha(fecha):
    try:
        f = pd.to_datetime(fecha, dayfirst=True, errors="coerce")
        if pd.isna(f):
            return str(fecha)
        return f.strftime("%d/%m/%Y")
    except Exception:
        return str(fecha)


def obtener_anio_mes(fecha):
    try:
        f = pd.to_datetime(fecha, dayfirst=True, errors="coerce")
        if pd.isna(f):
            return None, None
        return int(f.year), int(f.month)
    except Exception:
        return None, None


def obtener_tipo_comprobante(codigo):
    df = ejecutar_query("""
        SELECT descripcion, signo
        FROM tipos_comprobantes
        WHERE codigo = ?
    """, (str(codigo).strip(),), fetch=True)

    if df.empty:
        return None, None

    descripcion = str(df.iloc[0]["descripcion"]).upper()
    signo = int(df.iloc[0]["signo"])

    if "CREDITO" in descripcion or "CRÉDITO" in descripcion:
        return "NC", signo

    if "DEBITO" in descripcion or "DÉBITO" in descripcion:
        return "ND", signo

    return "FACTURA", signo


def insertar_movimiento(asiento, fecha, cuenta, debe, haber, glosa, archivo):
    ejecutar_query("""
        INSERT INTO libro_diario
        (id_asiento, fecha, cuenta, debe, haber, glosa, origen, archivo)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        asiento,
        fecha,
        cuenta,
        round(debe, 2),
        round(haber, 2),
        glosa,
        "VENTAS",
        archivo
    ))


def exportar_excel(diccionario_df):
    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for nombre_hoja, df in diccionario_df.items():
            df.to_excel(writer, index=False, sheet_name=nombre_hoja[:31])

    output.seek(0)
    return output


def mostrar_ventas():
    st.title("📤 Ventas PRO V4")

    tab1, tab2, tab3, tab4 = st.tabs([
        "Cargar CSV",
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


def cargar_csv_ventas():
    st.info(
        "Carga CSV ARCA/AFIP, genera asientos, guarda Libro IVA Ventas "
        "y actualiza cuenta corriente de clientes."
    )

    archivo = st.file_uploader("Subir CSV Ventas", type=["csv"])

    if not archivo:
        return

    if archivo_ya_cargado(archivo.name):
        st.error("Ese archivo ya fue cargado anteriormente.")
        return

    try:
        df = pd.read_csv(
            archivo,
            sep=None,
            engine="python",
            encoding="latin-1"
        )

        df["_fecha_orden"] = pd.to_datetime(df.iloc[:, 0], dayfirst=True, errors="coerce")
        df = df.sort_values(by="_fecha_orden").drop(columns=["_fecha_orden"])

        st.subheader("Vista previa")
        df_vista = df.head(20).copy()
        df_vista.index = range(1, len(df_vista) + 1)
        df_vista.index.name = "N°"
        st.dataframe(df_vista, use_container_width=True)

        st.caption(f"Registros detectados: {len(df)}")

        if not st.button("Procesar Ventas"):
            return

        asiento = proximo_asiento()

        procesados = 0
        errores = 0
        facturas = 0
        notas_credito = 0
        notas_debito = 0
        duplicados = 0
        errores_matematicos = 0
        errores_codigo = 0
        diferencias_redondeo = 0

        for indice, fila in df.iterrows():
            numero_fila = indice + 2

            try:
                fecha = formatear_fecha(fila.iloc[0])
                anio, mes = obtener_anio_mes(fila.iloc[0])

                codigo = str(fila.iloc[1]).strip()
                punto_venta = str(fila.iloc[2]).strip()
                numero_desde = str(fila.iloc[3]).strip()
                numero_hasta = str(fila.iloc[4]).strip()

                numero = f"{punto_venta}-{numero_desde}"

                if numero_hasta not in ["", "nan", "None"] and numero_hasta != numero_desde:
                    numero = f"{punto_venta}-{numero_desde}/{numero_hasta}"

                cuit = str(fila.iloc[7]).strip()
                cliente = str(fila.iloc[8]).strip()

                if cliente == "" or cliente.lower() == "nan":
                    cliente = "CONSUMIDOR FINAL"

                neto = limpiar_num(fila.iloc[22])
                iva = limpiar_num(fila.iloc[26])
                total = limpiar_num(fila.iloc[27])

                contenido_fila = fila.to_dict()

                if not tipo_comprobante_existe(codigo):
                    errores += 1
                    errores_codigo += 1
                    registrar_error(
                        "VENTAS",
                        archivo.name,
                        numero_fila,
                        f"Código de comprobante inexistente: {codigo}",
                        contenido_fila
                    )
                    continue

                tipo, signo = obtener_tipo_comprobante(codigo)

                if tipo is None:
                    errores += 1
                    errores_codigo += 1
                    registrar_error(
                        "VENTAS",
                        archivo.name,
                        numero_fila,
                        f"No se pudo interpretar el comprobante: {codigo}",
                        contenido_fila
                    )
                    continue

                if comprobante_ya_procesado("VENTAS", codigo, numero, cliente):
                    errores += 1
                    duplicados += 1
                    registrar_error(
                        "VENTAS",
                        archivo.name,
                        numero_fila,
                        f"Comprobante duplicado: código {codigo}, número {numero}, cliente {cliente}",
                        contenido_fila
                    )
                    continue

                if iva == 0:
                    neto = total

                diferencia_original = round(total - (neto + iva), 2)

                if abs(diferencia_original) > 5:
                    errores += 1
                    errores_matematicos += 1
                    registrar_error(
                        "VENTAS",
                        archivo.name,
                        numero_fila,
                        f"Diferencia matemática mayor a $5. Neto: {neto}, IVA: {iva}, Total: {total}, Diferencia: {diferencia_original}",
                        contenido_fila
                    )
                    continue

                neto_s = round(neto * signo, 2)
                iva_s = round(iva * signo, 2)
                total_s = round(total * signo, 2)

                glosa = f"{tipo} {numero} - {cliente}"

                debe_total = total_s if total_s > 0 else 0
                haber_total = abs(total_s) if total_s < 0 else 0

                debe_venta = abs(neto_s) if neto_s < 0 else 0
                haber_venta = neto_s if neto_s > 0 else 0

                debe_iva = abs(iva_s) if iva_s < 0 else 0
                haber_iva = iva_s if iva_s > 0 else 0

                insertar_movimiento(
                    asiento,
                    fecha,
                    "DEUDORES POR VENTAS",
                    debe_total,
                    haber_total,
                    glosa,
                    archivo.name
                )

                insertar_movimiento(
                    asiento,
                    fecha,
                    "VENTAS",
                    debe_venta,
                    haber_venta,
                    glosa,
                    archivo.name
                )

                if iva_s != 0:
                    insertar_movimiento(
                        asiento,
                        fecha,
                        "IVA DEBITO FISCAL",
                        debe_iva,
                        haber_iva,
                        glosa,
                        archivo.name
                    )

                total_debe = debe_total + debe_venta + debe_iva
                total_haber = haber_total + haber_venta + haber_iva
                diferencia_asiento = round(total_debe - total_haber, 2)

                if diferencia_asiento != 0:
                    diferencias_redondeo += 1

                    insertar_movimiento(
                        asiento,
                        fecha,
                        "DIFERENCIA POR REDONDEO",
                        abs(diferencia_asiento) if diferencia_asiento < 0 else 0,
                        diferencia_asiento if diferencia_asiento > 0 else 0,
                        glosa,
                        archivo.name
                    )

                registrar_comprobante(
                    "VENTAS",
                    fecha,
                    codigo,
                    numero,
                    cliente,
                    total_s,
                    archivo.name
                )

                registrar_venta(
                    fecha,
                    anio,
                    mes,
                    codigo,
                    tipo,
                    punto_venta,
                    numero,
                    cliente,
                    cuit,
                    neto_s,
                    iva_s,
                    total_s,
                    archivo.name
                )

                registrar_cta_cte_cliente(
                    fecha,
                    cliente,
                    cuit,
                    tipo,
                    numero,
                    total_s if total_s > 0 else 0,
                    abs(total_s) if total_s < 0 else 0,
                    0,
                    "VENTAS",
                    archivo.name
                )

                asiento += 1
                procesados += 1

                if tipo == "FACTURA":
                    facturas += 1
                elif tipo == "NC":
                    notas_credito += 1
                elif tipo == "ND":
                    notas_debito += 1

            except Exception as e:
                errores += 1
                registrar_error(
                    "VENTAS",
                    archivo.name,
                    numero_fila,
                    f"Error inesperado: {str(e)}",
                    fila.to_dict()
                )

        if procesados > 0:
            registrar_carga("VENTAS", archivo.name, procesados)

        st.success("Proceso finalizado")

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Procesados", procesados)
            st.metric("Facturas", facturas)

        with col2:
            st.metric("Notas de Crédito", notas_credito)
            st.metric("Notas de Débito", notas_debito)

        with col3:
            st.metric("Errores", errores)
            st.metric("Duplicados", duplicados)

        st.divider()

        st.subheader("Detalle de auditoría")
        st.write(f"Errores matemáticos: {errores_matematicos}")
        st.write(f"Códigos inexistentes: {errores_codigo}")
        st.write(f"Duplicados detectados: {duplicados}")
        st.write(f"Asientos con diferencia por redondeo: {diferencias_redondeo}")

        if errores > 0:
            st.warning("Se detectaron errores. Revisar Estado de Cargas / Auditoría.")

    except Exception as e:
        st.error(f"No se pudo leer el archivo: {str(e)}")


def mostrar_libro_iva_ventas():
    st.subheader("📘 Libro IVA Ventas")

    df = ejecutar_query("""
        SELECT fecha, anio, mes, tipo, numero, cliente, cuit, neto, iva, total, archivo
        FROM ventas_comprobantes
        ORDER BY anio, mes, fecha, numero
    """, fetch=True)

    if df.empty:
        st.info("No hay ventas cargadas.")
        return

    col1, col2, col3 = st.columns(3)

    anios = ["Todos"] + sorted(df["anio"].dropna().unique().tolist())
    meses = ["Todos"] + sorted(df["mes"].dropna().unique().tolist())
    clientes = ["Todos"] + sorted(df["cliente"].dropna().unique().tolist())

    with col1:
        anio = st.selectbox("Año", anios)

    with col2:
        mes = st.selectbox("Mes", meses)

    with col3:
        cliente = st.selectbox("Cliente", clientes)

    if anio != "Todos":
        df = df[df["anio"] == anio]

    if mes != "Todos":
        df = df[df["mes"] == mes]

    if cliente != "Todos":
        df = df[df["cliente"] == cliente]

    df_vista = df.copy()
    df_vista.index = range(1, len(df_vista) + 1)
    df_vista.index.name = "N°"

    st.dataframe(df_vista, use_container_width=True)

    c1, c2, c3 = st.columns(3)
    c1.metric("Neto", f"$ {df['neto'].sum():,.2f}")
    c2.metric("IVA Débito Fiscal", f"$ {df['iva'].sum():,.2f}")
    c3.metric("Total", f"$ {df['total'].sum():,.2f}")

    excel = exportar_excel({"Libro IVA Ventas": df})
    st.download_button(
        "Descargar Libro IVA Ventas Excel",
        data=excel,
        file_name="libro_iva_ventas.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


def mostrar_resumen_ventas():
    st.subheader("📊 Resumen / Estadísticas de Ventas")

    df = ejecutar_query("""
        SELECT fecha, anio, mes, tipo, cliente, cuit, neto, iva, total, archivo
        FROM ventas_comprobantes
    """, fetch=True)

    if df.empty:
        st.info("No hay ventas cargadas.")
        return

    resumen_mensual = df.groupby(["anio", "mes"], as_index=False).agg({
        "neto": "sum",
        "iva": "sum",
        "total": "sum",
        "tipo": "count"
    })

    resumen_mensual = resumen_mensual.rename(columns={"tipo": "cantidad_comprobantes"})

    ranking_clientes = df.groupby(["cliente", "cuit"], as_index=False).agg({
        "total": "sum",
        "tipo": "count"
    })

    ranking_clientes = ranking_clientes.rename(columns={"tipo": "cantidad_comprobantes"})
    ranking_clientes = ranking_clientes.sort_values(by="total", ascending=False)

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Total Neto", f"$ {df['neto'].sum():,.2f}")
    col2.metric("IVA Débito", f"$ {df['iva'].sum():,.2f}")
    col3.metric("Total Facturado", f"$ {df['total'].sum():,.2f}")
    col4.metric("Comprobantes", len(df))

    st.divider()

    st.subheader("Resumen mensual")
    st.dataframe(resumen_mensual, use_container_width=True)

    st.subheader("Ranking de clientes")
    st.dataframe(ranking_clientes, use_container_width=True)

    excel = exportar_excel({
        "Resumen Mensual": resumen_mensual,
        "Ranking Clientes": ranking_clientes
    })

    st.download_button(
        "Descargar Estadísticas Excel",
        data=excel,
        file_name="estadisticas_ventas.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


def mostrar_cuenta_corriente_clientes():
    st.subheader("💰 Cuenta corriente de clientes")

    df = ejecutar_query("""
        SELECT fecha, cliente, cuit, tipo, numero, debe, haber, origen, archivo
        FROM cuenta_corriente_clientes
        ORDER BY cliente, fecha, id
    """, fetch=True)

    if df.empty:
        st.info("No hay movimientos de cuenta corriente.")
        return

    resumen = df.groupby(["cliente", "cuit"], as_index=False).agg({
        "debe": "sum",
        "haber": "sum"
    })

    resumen["saldo"] = resumen["debe"] - resumen["haber"]
    resumen = resumen.sort_values(by="saldo", ascending=False)

    st.subheader("Resumen de deuda por cliente")
    st.dataframe(resumen, use_container_width=True)

    cliente = st.selectbox(
        "Ver detalle de cliente",
        ["Todos"] + sorted(df["cliente"].dropna().unique().tolist())
    )

    if cliente != "Todos":
        df = df[df["cliente"] == cliente]

    df = df.copy()
    df["saldo_acumulado"] = df.groupby("cliente")["debe"].cumsum() - df.groupby("cliente")["haber"].cumsum()

    df.index = range(1, len(df) + 1)
    df.index.name = "N°"

    st.subheader("Detalle de movimientos")
    st.dataframe(df, use_container_width=True)

    excel = exportar_excel({
        "Resumen Cta Cte": resumen,
        "Detalle Cta Cte": df
    })

    st.download_button(
        "Descargar Cuenta Corriente Excel",
        data=excel,
        file_name="cuenta_corriente_clientes.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )