import streamlit as st
import pandas as pd

from database import (
    ejecutar_query,
    registrar_carga,
    proximo_asiento,
    archivo_ya_cargado
)


def limpiar_num(v):
    try:
        if pd.isna(v):
            return 0.0
        return float(str(v).replace(".", "").replace(",", "."))
    except:
        return 0.0


def obtener_tipo_comprobante(codigo):
    try:
        df = ejecutar_query("""
            SELECT descripcion, signo
            FROM tipos_comprobantes
            WHERE codigo = ?
        """, (str(codigo),), fetch=True)

        if not df.empty:
            descripcion = str(df.iloc[0]["descripcion"]).upper()
            signo = int(df.iloc[0]["signo"])

            if "CREDITO" in descripcion:
                return "NC", signo
            elif "DEBITO" in descripcion:
                return "ND", signo
            else:
                return "FACTURA", signo

    except:
        pass

    return "FACTURA", 1


def mostrar_ventas():
    st.title("📤 Ventas")

    archivo = st.file_uploader("Subir CSV Ventas", type=["csv"])

    if archivo:

        if archivo_ya_cargado(archivo.name):
            st.error("Ese archivo ya fue cargado.")
            return

        try:
            df = pd.read_csv(
                archivo,
                sep=None,
                engine="python",
                encoding="latin-1"
            )

            st.dataframe(df.head(), use_container_width=True)

            if st.button("Procesar Ventas"):

                asiento = proximo_asiento()

                procesados = 0
                errores = 0
                detalle_errores = []

                for i, fila in df.iterrows():

                    try:
                        fecha = str(fila.iloc[0])
                        codigo = str(fila.iloc[1]).strip()
                        numero = str(fila.iloc[2]).strip()

                        cliente = str(fila.iloc[8]).strip()

                        if cliente == "" or cliente.lower() == "nan":
                            cliente = "CONSUMIDOR FINAL"

                        neto = limpiar_num(fila.iloc[22])
                        iva = limpiar_num(fila.iloc[26])
                        total = limpiar_num(fila.iloc[27])

                        tipo, signo = obtener_tipo_comprobante(codigo)

                        if iva == 0:
                            neto = total

                        neto *= signo
                        iva *= signo
                        total *= signo

                        glosa = f"{tipo} {numero} - {cliente}"

                        ejecutar_query("""
                            INSERT INTO libro_diario
                            (id_asiento,fecha,cuenta,debe,haber,glosa,origen,archivo)
                            VALUES (?,?,?,?,?,?,?,?)
                        """, (
                            asiento, fecha,
                            "DEUDORES POR VENTAS",
                            total if total > 0 else 0,
                            abs(total) if total < 0 else 0,
                            glosa, "VENTAS", archivo.name
                        ))

                        ejecutar_query("""
                            INSERT INTO libro_diario
                            (id_asiento,fecha,cuenta,debe,haber,glosa,origen,archivo)
                            VALUES (?,?,?,?,?,?,?,?)
                        """, (
                            asiento, fecha,
                            "VENTAS",
                            abs(neto) if neto < 0 else 0,
                            neto if neto > 0 else 0,
                            glosa, "VENTAS", archivo.name
                        ))

                        if iva != 0:
                            ejecutar_query("""
                                INSERT INTO libro_diario
                                (id_asiento,fecha,cuenta,debe,haber,glosa,origen,archivo)
                                VALUES (?,?,?,?,?,?,?,?)
                            """, (
                                asiento, fecha,
                                "IVA DEBITO FISCAL",
                                abs(iva) if iva < 0 else 0,
                                iva if iva > 0 else 0,
                                glosa, "VENTAS", archivo.name
                            ))

                        asiento += 1
                        procesados += 1

                    except Exception as e:
                        errores += 1
                        detalle_errores.append(f"Fila {i+1}: {str(e)}")

                if procesados > 0:
                    registrar_carga("VENTAS", archivo.name, procesados)

                st.success(f"Procesados: {procesados}")

                if errores > 0:
                    st.warning(f"Errores detectados: {errores}")

                    with st.expander("Ver detalle errores"):
                        for x in detalle_errores[:50]:
                            st.write(x)

        except Exception as e:
            st.error(str(e))