import streamlit as st
import pandas as pd
from core.database import ejecutar_query, registrar_carga, proximo_asiento


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
                    # -------------------------
                    # DATOS BASE
                    # -------------------------
                    fecha = str(fila.iloc[0])
                    cliente = str(fila.iloc[1])

                    cod_comprobante = fila.iloc[2]

                    neto = limpiar_num(fila.iloc[22])
                    iva = limpiar_num(fila.iloc[26])
                    total = limpiar_num(fila.iloc[27])

                    # -------------------------
                    # TRAER TIPO COMPROBANTE
                    # -------------------------
                    tipo_df = ejecutar_query(
                        "SELECT signo, descripcion FROM tipos_comprobantes WHERE codigo=?",
                        (cod_comprobante,),
                        fetch=True
                    )

                    signo = 1
                    desc = ""

                    if not tipo_df.empty:
                        signo = int(tipo_df.iloc[0]["signo"])
                        desc = str(tipo_df.iloc[0]["descripcion"])

                    # -------------------------
                    # REGLA CONTABLE BASE
                    # -------------------------
                    # Si no hay IVA detallado → usar total como base
                    if neto == 0 and iva == 0:
                        neto = total
                        iva = 0

                    # aplicar signo contable (NC = negativo)
                    neto *= signo
                    iva *= signo
                    total *= signo

                    # -------------------------
                    # ASIENTO CONTABLE
                    # -------------------------

                    # 1. Cliente / Deudores
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
                        f"{desc} - {cliente}",
                        "VENTAS"
                    ))

                    # 2. Ventas
                    ejecutar_query("""
                        INSERT INTO libro_diario
                        (id_asiento, fecha, cuenta, debe, haber, glosa, origen)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        asiento,
                        fecha,
                        "VENTAS",
                        0 if neto > 0 else abs(neto),
                        neto if neto > 0 else 0,
                        f"{desc} - {cliente}",
                        "VENTAS"
                    ))

                    # 3. IVA solo si existe
                    if iva != 0:
                        ejecutar_query("""
                            INSERT INTO libro_diario
                            (id_asiento, fecha, cuenta, debe, haber, glosa, origen)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (
                            asiento,
                            fecha,
                            "IVA DEBITO FISCAL",
                            0 if iva > 0 else abs(iva),
                            iva if iva > 0 else 0,
                            f"{desc} - {cliente}",
                            "VENTAS"
                        ))

                    asiento += 1
                    procesados += 1

                except Exception as e:
                    st.warning(f"Error fila: {e}")
                    continue

            # -------------------------
            # REGISTRO HISTORIAL
            # -------------------------
            registrar_carga(
                "VENTAS",
                archivo.name,
                procesados
            )

            st.success(f"Procesados {procesados} registros correctamente.")