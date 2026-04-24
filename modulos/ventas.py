import streamlit as st
import pandas as pd

from database import ejecutar_query, registrar_carga, proximo_asiento


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
    st.title("📤 Módulo Ventas")

    archivo = st.file_uploader(
        "Subir archivo CSV Ventas",
        type=["csv"]
    )

    if archivo:

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

                for _, fila in df.iterrows():

                    try:
                        fecha = str(fila.iloc[0])
                        codigo = str(fila.iloc[1]).strip()
                        numero = str(fila.iloc[2])
                        cliente = str(fila.iloc[8])

                        neto = limpiar_num(fila.iloc[22])
                        iva = limpiar_num(fila.iloc[26])
                        total = limpiar_num(fila.iloc[27])

                        tipo, signo = obtener_tipo_comprobante(codigo)

                        # Si no discrimina IVA
                        if iva == 0:
                            neto = total

                        neto = neto * signo
                        iva = iva * signo
                        total = total * signo

                        glosa = f"{tipo} {numero} - {cliente}"

                        # CLIENTE / DEUDORES
                        ejecutar_query("""
                            INSERT INTO libro_diario
                            (id_asiento, fecha, cuenta, debe, haber, glosa, origen)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (
                            asiento,
                            fecha,
                            "DEUDORES POR VENTAS",
                            total if total > 0 else 0,
                            abs(total) if total < 0 else 0,
                            glosa,
                            "VENTAS"
                        ))

                        # VENTAS
                        ejecutar_query("""
                            INSERT INTO libro_diario
                            (id_asiento, fecha, cuenta, debe, haber, glosa, origen)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (
                            asiento,
                            fecha,
                            "VENTAS",
                            abs(neto) if neto < 0 else 0,
                            neto if neto > 0 else 0,
                            glosa,
                            "VENTAS"
                        ))

                        # IVA
                        if iva != 0:
                            ejecutar_query("""
                                INSERT INTO libro_diario
                                (id_asiento, fecha, cuenta, debe, haber, glosa, origen)
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                            """, (
                                asiento,
                                fecha,
                                "IVA DEBITO FISCAL",
                                abs(iva) if iva < 0 else 0,
                                iva if iva > 0 else 0,
                                glosa,
                                "VENTAS"
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

                st.success(f"✅ Procesados: {procesados}")

                if errores > 0:
                    st.warning(f"⚠️ Errores omitidos: {errores}")

        except Exception as e:
            st.error(f"Error general: {e}")