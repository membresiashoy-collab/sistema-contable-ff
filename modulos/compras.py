import streamlit as st
import pandas as pd
from core.database import ejecutar_query, registrar_carga, proximo_asiento
from core.reglas_contables import interpretar_comprobante


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

            st.dataframe(df.head(), use_container_width=True)

            if st.button("Procesar Compras"):
                asiento = proximo_asiento()
                cantidad = 0

                for _, fila in df.iterrows():
                    try:
                        fecha = str(fila.iloc[0])
                        tipo = fila.iloc[1]

                        total = float(str(fila.iloc[2]).replace(",", "."))
                        iva = float(str(fila.iloc[3]).replace(",", ".")) if len(fila) > 3 else 0

                        datos = interpretar_comprobante(tipo, 0, iva, total)

                        neto = datos["neto"]
                        iva = datos["iva"]

                        # GASTOS / COMPRAS
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
                            f"Compra {tipo}",
                            "COMPRAS"
                        ))

                        # IVA CREDITO
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
                                f"Compra {tipo}",
                                "COMPRAS"
                            ))

                        # PROVEEDORES
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
                            f"Compra {tipo}",
                            "COMPRAS"
                        ))

                        asiento += 1
                        cantidad += 1

                    except:
                        continue

                registrar_carga("COMPRAS", archivo.name, cantidad)
                st.success(f"Se procesaron {cantidad} compras.")

        except Exception as e:
            st.error(f"Error: {e}")