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
                tipo = "NC"

            elif "DEBITO" in descripcion:
                tipo = "ND"

            else:
                tipo = "FACTURA"

            return tipo, signo

    except:
        pass

    return "FACTURA", 1


def mostrar_ventas():
    st.title("📤 Ventas PRO V2")

    archivo = st.file_uploader(
        "Subir archivo CSV Ventas",
        type=["csv"]
    )

    if archivo:

        # Control archivo duplicado
        if archivo_ya_cargado(archivo.name):
            st.error("⚠️ Ese archivo ya fue procesado anteriormente.")
            return

        try:
            df = pd.read_csv(
                archivo,
                sep=None,
                engine="python",
                encoding="latin-1"
            )

            # Vista previa
            preview = df.head().reset_index(drop=True)
            preview.index = preview.index + 1

            st.subheader("Vista previa")
            st.dataframe(preview, use_container_width=True)

            if st.button("Procesar Ventas"):

                asiento = proximo_asiento()

                procesados = 0
                errores = 0
                facturas = 0
                nc = 0
                nd = 0

                for _, fila in df.iterrows():

                    try:
                        fecha = str(fila.iloc[0])
                        codigo = str(fila.iloc[1]).strip()
                        numero = str(fila.iloc[2])

                        cliente = str(fila.iloc[8]).strip()
                        cuit = str(fila.iloc[6]).strip()

                        if cliente == "" or cliente.lower() == "nan":
                            cliente = "CONSUMIDOR FINAL"

                        if cuit == "" or cuit.lower() == "nan":
                            cuit = "S/CUIT"

                        neto = limpiar_num(fila.iloc[22])
                        iva = limpiar_num(fila.iloc[26])
                        total = limpiar_num(fila.iloc[27])

                        tipo, signo = obtener_tipo_comprobante(codigo)

                        if tipo == "FACTURA":
                            facturas += 1
                        elif tipo == "NC":
                            nc += 1
                        elif tipo == "ND":
                            nd += 1

                        # Sin IVA discriminado
                        if iva == 0:
                            neto = total

                        neto *= signo
                        iva *= signo
                        total *= signo

                        glosa = f"{tipo} {numero} - {cliente}"

                        # Cliente / deudores
                        ejecutar_query("""
                            INSERT INTO libro_diario
                            (id_asiento, fecha, cuenta, debe, haber, glosa, origen, archivo)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            asiento,
                            fecha,
                            "DEUDORES POR VENTAS",
                            total if total > 0 else 0,
                            abs(total) if total < 0 else 0,
                            glosa,
                            "VENTAS",
                            archivo.name
                        ))

                        # Ventas
                        ejecutar_query("""
                            INSERT INTO libro_diario
                            (id_asiento, fecha, cuenta, debe, haber, glosa, origen, archivo)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            asiento,
                            fecha,
                            "VENTAS",
                            abs(neto) if neto < 0 else 0,
                            neto if neto > 0 else 0,
                            glosa,
                            "VENTAS",
                            archivo.name
                        ))

                        # IVA
                        if iva != 0:
                            ejecutar_query("""
                                INSERT INTO libro_diario
                                (id_asiento, fecha, cuenta, debe, haber, glosa, origen, archivo)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                asiento,
                                fecha,
                                "IVA DEBITO FISCAL",
                                abs(iva) if iva < 0 else 0,
                                iva if iva > 0 else 0,
                                glosa,
                                "VENTAS",
                                archivo.name
                            ))

                        asiento += 1
                        procesados += 1

                    except:
                        errores += 1
                        continue

                registrar_carga(
                    "VENTAS",
                    archivo.name,
                    procesados
                )

                st.success("✅ Proceso Finalizado")

                c1, c2, c3, c4 = st.columns(4)

                c1.metric("Procesados", procesados)
                c2.metric("Facturas", facturas)
                c3.metric("Notas Crédito", nc)
                c4.metric("Notas Débito", nd)

                if errores > 0:
                    st.warning(f"⚠️ Registros con error: {errores}")

        except Exception as e:
            st.error(f"Error general: {e}")