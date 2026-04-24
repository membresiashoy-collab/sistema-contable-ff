import streamlit as st
import pandas as pd

from database import (
    ejecutar_query,
    registrar_carga,
    proximo_asiento,
    archivo_ya_cargado,
    comprobante_ya_procesado,
    registrar_comprobante,
    registrar_error,
    tipo_comprobante_existe
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
        fecha_convertida = pd.to_datetime(fecha, dayfirst=True, errors="coerce")

        if pd.isna(fecha_convertida):
            return str(fecha)

        return fecha_convertida.strftime("%d/%m/%Y")

    except Exception:
        return str(fecha)


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


def mostrar_ventas():
    st.title("📤 Ventas PRO V3")

    st.info(
        "Este módulo procesa ventas desde CSV ARCA/AFIP, genera asientos, "
        "controla duplicados, valida IVA y guarda errores de auditoría."
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

        # Orden cronológico antes de procesar
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

        for indice, fila in df.iterrows():
            numero_fila = indice + 2

            try:
                fecha = formatear_fecha(fila.iloc[0])
                codigo = str(fila.iloc[1]).strip()
                numero = str(fila.iloc[2]).strip()

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
                else:
                    diferencia = abs((neto + iva) - total)

                    if diferencia > 1:
                        errores += 1
                        errores_matematicos += 1
                        registrar_error(
                            "VENTAS",
                            archivo.name,
                            numero_fila,
                            f"No cuadra neto + IVA con total. Neto: {neto}, IVA: {iva}, Total: {total}, Diferencia: {round(diferencia, 2)}",
                            contenido_fila
                        )
                        continue

                neto *= signo
                iva *= signo
                total *= signo

                glosa = f"{tipo} {numero} - {cliente}"

                insertar_movimiento(
                    asiento,
                    fecha,
                    "DEUDORES POR VENTAS",
                    total if total > 0 else 0,
                    abs(total) if total < 0 else 0,
                    glosa,
                    archivo.name
                )

                insertar_movimiento(
                    asiento,
                    fecha,
                    "VENTAS",
                    abs(neto) if neto < 0 else 0,
                    neto if neto > 0 else 0,
                    glosa,
                    archivo.name
                )

                if iva != 0:
                    insertar_movimiento(
                        asiento,
                        fecha,
                        "IVA DEBITO FISCAL",
                        abs(iva) if iva < 0 else 0,
                        iva if iva > 0 else 0,
                        glosa,
                        archivo.name
                    )

                registrar_comprobante(
                    "VENTAS",
                    fecha,
                    codigo,
                    numero,
                    cliente,
                    total,
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

        if errores > 0:
            st.warning(
                "Se detectaron errores. Podés revisarlos desde el módulo Estado de Cargas / Auditoría."
            )

    except Exception as e:
        st.error(f"No se pudo leer el archivo: {str(e)}")