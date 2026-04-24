import streamlit as st
import pandas as pd
from core import database


def mostrar_compras():
    st.title("📥 Módulo de Compras")

    archivo = st.file_uploader("Subir CSV Compras", type=["csv"])

    if archivo:
        try:
            df = pd.read_csv(archivo, sep=None, engine="python", encoding="latin-1")
            st.dataframe(df.head(), use_container_width=True)

            if st.button("Procesar Compras"):
                asiento = database.proximo_asiento()
                cantidad = 0

                for _, fila in df.iterrows():
                    try:
                        fecha = str(fila.iloc[0])
                        proveedor = str(fila.iloc[1])
                        total = float(str(fila.iloc[2]).replace(",", "."))

                        database.ejecutar_query("""
                        INSERT INTO libro_diario
                        (id_asiento, fecha, cuenta, debe, haber, glosa, origen)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (
                            asiento,
                            fecha,
                            "COMPRAS",
                            total,
                            0,
                            f"Compra {proveedor}",
                            "COMPRAS"
                        ))

                        database.ejecutar_query("""
                        INSERT INTO libro_diario
                        (id_asiento, fecha, cuenta, debe, haber, glosa, origen)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (
                            asiento,
                            fecha,
                            "PROVEEDORES",
                            0,
                            total,
                            f"Compra {proveedor}",
                            "COMPRAS"
                        ))

                        asiento += 1
                        cantidad += 1

                    except:
                        continue

                database.registrar_archivo(
                    archivo.name,
                    "COMPRAS",
                    cantidad
                )

                st.success(f"Se cargaron {cantidad} compras.")

        except Exception as e:
            st.error(f"Error: {e}")