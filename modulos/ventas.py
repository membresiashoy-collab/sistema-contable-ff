import streamlit as st
import pandas as pd

from database import ejecutar_query, registrar_carga, proximo_asiento
from motor_contable import interpretar_comprobante


def limpiar_num(v):
    try:
        if pd.isna(v):
            return 0
        return float(str(v).replace(".", "").replace(",", "."))
    except:
        return 0


def mostrar_ventas():
    st.title("📤 Ventas")

    archivo = st.file_uploader("Subir CSV Ventas", type=["csv"])

    if archivo:

        df = pd.read_csv(
            archivo,
            sep=None,
            engine="python",
            encoding="latin-1"
        )

        st.dataframe(df.head().reset_index(drop=True) + 0)

        if st.button("Procesar Ventas"):

            asiento = proximo_asiento()
            procesados = 0

            for _, fila in df.iterrows():

                try:
                    fecha = str(fila.iloc[0])
                    cliente = str(fila.iloc[8])

                    descripcion = str(fila.iloc[2])

                    neto = limpiar_num(fila.iloc[22])
                    iva = limpiar_num(fila.iloc[26])
                    total = limpiar_num(fila.iloc[27])

                    mov = interpretar_comprobante(
                        descripcion,
                        neto,
                        iva,
                        total
                    )

                    neto = mov["neto"]
                    iva = mov["iva"]
                    total = mov["total"]

                    glosa = f"{mov['tipo']} - {cliente}"

                    # Cliente
                    ejecutar_query("""
                    INSERT INTO libro_diario
                    (id_asiento,fecha,cuenta,debe,haber,glosa,origen)
                    VALUES (?,?,?,?,?,?,?)
                    """, (
                        asiento,
                        fecha,
                        "DEUDORES POR VENTAS",
                        total if total > 0 else 0,
                        abs(total) if total < 0 else 0,
                        glosa,
                        "VENTAS"
                    ))

                    # Ventas
                    ejecutar_query("""
                    INSERT INTO libro_diario
                    (id_asiento,fecha,cuenta,debe,haber,glosa,origen)
                    VALUES (?,?,?,?,?,?,?)
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
                        (id_asiento,fecha,cuenta,debe,haber,glosa,origen)
                        VALUES (?,?,?,?,?,?,?)
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
                    continue

            registrar_carga(
                "VENTAS",
                archivo.name,
                procesados
            )

            st.success(f"{procesados} comprobantes procesados.")