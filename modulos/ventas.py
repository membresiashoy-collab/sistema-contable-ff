import streamlit as st
import pandas as pd
import database

def mostrar_ventas():
    st.title("📤 Carga de Ventas")
    archivo = st.file_uploader("Subir CSV Ventas", type=["csv"])
    
    if archivo:
        try:
            df = pd.read_csv(archivo, sep=None, engine='python', encoding='latin-1')
            # Limpieza de nombres de columna para evitar errores de tildes
            df.columns = [c.encode('latin-1', errors='ignore').decode('utf-8', errors='ignore').strip().upper() for c in df.columns]
            
            # Identificamos columnas por palabras clave
            c_f = next(c for c in df.columns if "FECHA" in c)
            c_t = next(c for c in df.columns if "TIPO" in c and "COMPROBANTE" in c)
            c_tot = next(c for c in df.columns if "TOTAL" in c and "IVA" not in c)
            c_iva = next((c for c in df.columns if "TOTAL IVA" in c), None)

            if st.button("🚀 Procesar Asientos"):
                asiento_id = database.proximo_asiento()
                for _, r in df.iterrows():
                    try:
                        f, t = r[c_f], str(r[c_t])
                        tot = float(str(r[c_tot]).replace(',', '.'))
                        iva = float(str(r[c_iva]).replace(',', '.')) if c_iva and pd.notnull(r[c_iva]) else 0
                        neto = tot - iva
                        
                        # LOGICA PARTIDA DOBLE
                        if database.es_reverso(t):
                            # Nota de Crédito: Anula venta
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento_id, f, "VENTAS", neto, 0, f"NC {t}", "VENTAS"))
                            if iva > 0: database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento_id, f, "IVA DEBITO FISCAL", iva, 0, f"NC {t}", "VENTAS"))
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento_id, f, "DEUDORES POR VENTAS", 0, tot, f"NC {t}", "VENTAS"))
                        else:
                            # Factura: Venta normal
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento_id, f, "DEUDORES POR VENTAS", tot, 0, f"Fact {t}", "VENTAS"))
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento_id, f, "VENTAS", 0, neto, f"Fact {t}", "VENTAS"))
                            if iva > 0: database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento_id, f, "IVA DEBITO FISCAL", 0, iva, f"Fact {t}", "VENTAS"))
                        asiento_id += 1
                    except: continue
                st.success(f"Se procesaron los registros. Ve al Libro Diario.")
        except Exception as e:
            st.error(f"Error en el archivo: {e}")