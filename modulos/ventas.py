import streamlit as st
import pandas as pd
import database

def mostrar_ventas():
    st.title("📤 Carga de Ventas")
    archivo = st.file_uploader("Seleccione CSV de Ventas", type=["csv"])
    
    if archivo:
        try:
            df = pd.read_csv(archivo, sep=None, engine='python', encoding='latin-1')
            # Limpiamos nombres de columnas de caracteres basura
            df.columns = [c.encode('latin-1', errors='ignore').decode('utf-8', errors='ignore').strip().upper() for c in df.columns]
            
            # Buscamos columnas clave por aproximacion
            c_f = next(c for c in df.columns if "FECHA" in c)
            c_t = next(c for c in df.columns if "TIPO" in c and "COMPROBANTE" in c)
            c_tot = next(c for c in df.columns if "TOTAL" in c and "IVA" not in c)
            c_iva = next((c for c in df.columns if "TOTAL IVA" in c), None)

            if st.button("🚀 Generar Asientos"):
                asiento = database.proximo_asiento()
                for _, r in df.iterrows():
                    try:
                        f, t = r[c_f], str(r[c_t])
                        total = float(str(r[c_tot]).replace(',', '.'))
                        iva = float(str(r[c_iva]).replace(',', '.')) if c_iva and pd.notnull(r[c_iva]) else 0
                        neto = total - iva
                        
                        # LOGICA: Factura vs Nota de Crédito
                        if database.es_comprobante_reverso(t):
                            # Reverso: Venta (D), IVA (D) a Deudores (H)
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento, f, "VENTAS", neto, 0, f"NC {t}", "VENTAS"))
                            if iva > 0: database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento, f, "IVA DEBITO FISCAL", iva, 0, f"NC {t}", "VENTAS"))
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento, f, "DEUDORES POR VENTAS", 0, total, f"NC {t}", "VENTAS"))
                        else:
                            # Directo: Deudores (D) a Ventas (H), IVA (H)
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento, f, "DEUDORES POR VENTAS", total, 0, f"Fact {t}", "VENTAS"))
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento, f, "VENTAS", 0, neto, f"Fact {t}", "VENTAS"))
                            if iva > 0: database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento, f, "IVA DEBITO FISCAL", 0, iva, f"Fact {t}", "VENTAS"))
                        asiento += 1
                    except: continue
                st.success("Asientos generados. Revise el Libro Diario.")
        except Exception as e:
            st.error(f"Error leyendo el CSV: {e}")