import streamlit as st
import pandas as pd
import database

def mostrar_ventas():
    st.title("📤 Ventas")
    
    archivo = st.file_uploader("Subir CSV Ventas", type=["csv"])
    if archivo:
        try:
            df = pd.read_csv(archivo, sep=None, engine='python', encoding='latin-1')
            # Limpiamos nombres de columnas (quita Ã³, etc)
            df.columns = [c.encode('latin-1', errors='ignore').decode('utf-8', errors='ignore').strip().upper() for c in df.columns]
            
            # Identificación de columnas clave
            c_f = next(c for c in df.columns if "FECHA" in c)
            c_t = next(c for c in df.columns if "TIPO DE COMPROBANTE" in c)
            c_total = next(c for c in df.columns if "IMP. TOTAL" in c or "TOTAL" in c)
            c_iva = next(c for c in df.columns if "TOTAL IVA" in c or "IVA 21%" in c)

            if st.button("🚀 Generar Asientos"):
                asiento_nro = database.proximo_asiento()
                for _, r in df.iterrows():
                    try:
                        f, t = r[c_f], str(r[c_t])
                        tot = float(str(r[c_total]).replace(',', '.'))
                        iva = float(str(r[c_iva]).replace(',', '.')) if pd.notnull(r[c_iva]) else 0
                        neto = tot - iva
                        
                        if database.es_comprobante_reverso(t):
                            # NC Venta: Reversa (Neto al Debe, IVA al Debe, Cliente al Haber)
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento_nro, f, "VENTAS", neto, 0, f"NC {t}", "VENTAS"))
                            if iva > 0: database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento_nro, f, "IVA DEBITO FISCAL", iva, 0, f"NC {t}", "VENTAS"))
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento_nro, f, "DEUDORES POR VENTAS", 0, tot, f"NC {t}", "VENTAS"))
                        else:
                            # Factura Venta: Normal (Cliente al Debe, Ventas/IVA al Haber)
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento_nro, f, "DEUDORES POR VENTAS", tot, 0, f"Fact {t}", "VENTAS"))
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento_nro, f, "VENTAS", 0, neto, f"Fact {t}", "VENTAS"))
                            if iva > 0: database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento_nro, f, "IVA DEBITO FISCAL", 0, iva, f"Fact {t}", "VENTAS"))
                        asiento_nro += 1
                    except: continue
                st.success("Proceso completado.")
        except Exception as e:
            st.error(f"Error: {e}")