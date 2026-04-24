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

            st.subheader("Vista previa")
            st.dataframe(df.head(), use_container_width=True)

            if st.button("Procesar Ventas"):

                asiento = proximo_asiento()
                procesados = 0

                for _, fila in df.iterrows():
                    try:
                        fecha = str(fila.iloc[0])
                        cliente = str(fila.iloc[1])

                        neto = limpiar_num(fila.iloc[22])
                        iva = limpiar_num(fila.iloc[26])
                        total = limpiar_num(fila.iloc[27])

                        # Si neto e iva son cero, usar total
                        if neto == 0 and iva == 0:
                            neto = total

                        # Debe
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

                        # Haber ventas
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

                        # IVA si existe
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
                        procesados += 1

                    except:
                        continue

                registrar_carga("VENTAS", archivo.name, procesados)
                st.success(f"Se procesaron {procesados} ventas.")

        except Exception as e:
            st.error(f"Error: {e}")