import streamlit as st
import pandas as pd
import database

def mostrar_ventas():
    st.title("📤 Módulo de Ventas")
    
    archivo = st.file_uploader("Subir CSV de AFIP", type=["csv"])
    
    if archivo:
        try:
            df = pd.read_csv(archivo, sep=None, engine='python', encoding='latin-1')
            df.columns = [c.strip().upper() for c in df.columns]
            
            # Buscador de columnas
            c_f = next(c for c in df.columns if "FECHA" in c)
            c_t = next(c for c in df.columns if "TIPO" in c and "COMPROBANTE" in c)
            c_tot = next(c for c in df.columns if "TOTAL" in c and "IVA" not in c)
            c_iva = next((c for c in df.columns if "TOTAL IVA" in c or "IVA 21%" in c), None)

            if st.button("🚀 Procesar"):
                # Obtenemos el último ID de asiento
                res = database.ejecutar_query("SELECT MAX(id_asiento) FROM libro_diario", fetch=True)
                n_asiento = 1 if res.empty or res.iloc[0,0] is None else int(res.iloc[0,0]) + 1
                
                for _, r in df.iterrows():
                    f, t = r[c_f], str(r[c_t])
                    total = float(str(r[c_tot]).replace(',', '.'))
                    iva = 0
                    if c_iva and pd.notnull(r[c_iva]):
                        try: iva = float(str(r[c_iva]).replace(',', '.'))
                        except: iva = 0
                    
                    neto = total - iva if iva > 0 else total

                    # ASIENTO CONTABLE (6 valores + origen)
                    # DEUDORES AL DEBE
                    database.ejecutar_query(
                        "INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (n_asiento, f, "DEUDORES POR VENTAS", total, 0, f"Venta {t}", "VENTAS")
                    )
                    # VENTAS AL HABER
                    database.ejecutar_query(
                        "INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (n_asiento, f, "VENTAS", 0, neto, f"Venta {t}", "VENTAS")
                    )
                    # IVA AL HABER (si existe)
                    if iva > 0:
                        database.ejecutar_query(
                            "INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (n_asiento, f, "IVA DEBITO FISCAL", 0, iva, f"Venta {t}", "VENTAS")
                        )
                    n_asiento += 1
                st.success("Asientos generados correctamente.")
        except Exception as e:
            st.error(f"Error: {e}")