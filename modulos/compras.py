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


def mostrar_compras():
    st.title("📥 Módulo de Compras")

    archivo = st.file_uploader("Subir CSV de Compras", type=["csv"])

    if archivo:
        try:
            df = pd.read_csv(
                archivo,
                sep=None,
                engine="python",
                encoding="latin-1"
            )

            st.subheader("Vista previa")
            st.dataframe(df.head(), use_container_width=True)

            if st.button("Procesar Compras"):

                asiento = proximo_asiento()
                procesados = 0

                for _, fila in df.iterrows():
                    try:
                        fecha = str(fila.iloc[0])

                        total = limpiar_num(fila.iloc[2])
                        iva = limpiar_num(fila.iloc[3]) if len(fila) > 3 else 0

                        neto = total - iva if iva > 0 else total

                        ejecutar_query("""
                        INSERT INTO libro_diario
                        (id_asiento, fecha, cuenta, debe, haber, glosa, origen)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (
                            asiento,
                            fecha,
                            "COMPRAS",
                            neto,
                            0,
                            "Compra",
                            "COMPRAS"
                        ))

                        if iva > 0:
                            ejecutar_query("""
                            INSERT INTO libro_diario
                            (id_asiento, fecha, cuenta, debe, haber, glosa, origen)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                            """, (
                                asiento,
                                fecha,
                                "IVA CREDITO FISCAL",
                                iva,
                                0,
                                "Compra",
                                "COMPRAS"
                            ))

                        ejecutar_query("""
                        INSERT INTO libro_diario
                        (id_asiento, fecha, cuenta, debe, haber, glosa, origen)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (
                            asiento,
                            fecha,
                            "PROVEEDORES",
                            0,
                            total,
                            "Compra",
                            "COMPRAS"
                        ))

                        asiento += 1
                        procesados += 1

                    except:
                        continue

                registrar_carga("COMPRAS", archivo.name, procesados)
                st.success(f"Se procesaron {procesados} compras.")

        except Exception as e:
            st.error(f"Error: {e}")