import streamlit as st
import pandas as pd
from core.database import ejecutar_query, registrar_carga, proximo_asiento
from core.reglas_contables import interpretar_comprobante


def limpiar_num(valor):
    try:
        if pd.isna(valor):
            return 0.0
        return float(str(valor).replace(".", "").replace(",", "."))
    except:
        return 0.0


def mostrar_ventas():
    st.title("📤 Módulo de Ventas")

    archivo = st.file_uploader("Subir CSV de Ventas", type=["csv"])

    if archivo:
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
                cantidad = 0

                for _, fila in df.iterrows():
                    try:
                        fecha = str(fila.iloc[0])
                        cliente = str(fila.iloc[1])

                        tipo = fila.iloc[2]
                        neto = limpiar_num(fila.iloc[22])
                        iva = limpiar_num(fila.iloc[26])
                        total = limpiar_num(fila.iloc[27])

                        datos = interpretar_comprobante(tipo, neto, iva, total)

                        neto = datos["neto"]
                        iva = datos["iva"]

                        # DEUDORES
                        ejecutar_query("""
                        INSERT INTO libro_diario
                        (id_asiento, fecha, cuenta, debe, haber, glosa, origen)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (
                            asiento,
                            fecha,
                            "DEUDORES POR VENTAS",
                            total,
                            0,
                            f"Venta {cliente}",
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
                            0,
                            neto,
                            f"Venta {cliente}",
                            "VENTAS"
                        ))

                        # IVA solo si corresponde
                        if iva > 0:
                            ejecutar_query("""
                            INSERT INTO libro_diario
                            (id_asiento, fecha, cuenta, debe, haber, glosa, origen)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                            """, (
                                asiento,
                                fecha,
                                "IVA DEBITO FISCAL",
                                0,
                                iva,
                                f"Venta {cliente}",
                                "VENTAS"
                            ))

                        asiento += 1
                        cantidad += 1

                    except:
                        continue

                registrar_carga("VENTAS", archivo.name, cantidad)
                st.success(f"Se procesaron {cantidad} ventas.")

        except Exception as e:
            st.error(f"Error: {e}")