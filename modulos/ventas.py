import streamlit as st
import pandas as pd
import database

def mostrar_ventas():
    st.title("📤 Módulo de Ventas")
    
    if st.checkbox("📂 Ver Historial de Archivos"):
        hist = database.ejecutar_query("SELECT fecha_proceso, nombre_archivo, registros FROM historial_archivos WHERE tipo='VENTAS' ORDER BY id DESC", fetch=True)
        st.table(hist)

    archivo = st.file_uploader("Cargar CSV Ventas AFIP", type=["csv"])
    
    if archivo:
        try:
            df = pd.read_csv(archivo, sep=None, engine='python', encoding='latin-1')
            df.columns = [c.strip().upper() for c in df.columns]
            
            # Identificación de columnas (Fecha, Tipo, Total, IVA)
            c_f = next(c for c in df.columns if "FECHA" in c)
            c_t = next(c for c in df.columns if "TIPO" in c and "COMPROBANTE" in c)
            c_tot = next(c for c in df.columns if "TOTAL" in c and "IVA" not in c)
            c_iva = next((c for c in df.columns if "TOTAL IVA" in c or "IVA 21%" in c), None)

            if st.button("🚀 Procesar Asientos"):
                asiento_id = database.proximo_asiento()
                exitos = 0
                
                for _, r in df.iterrows():
                    try:
                        f, t = r[c_f], str(r[c_t])
                        total = float(str(r[c_tot]).replace(',', '.'))
                        
                        # --- NUEVA LÓGICA CONTABLE ---
                        # Si existe columna IVA y tiene valor, lo restamos. Si no, Neto = Total.
                        iva = 0
                        if c_iva and pd.notnull(r[c_iva]):
                            try:
                                iva = float(str(r[c_iva]).replace(',', '.'))
                            except:
                                iva = 0
                        
                        # Si la operación no tiene IVA discriminado (Monotributo/Exento), Neto es el Total.
                        neto = total - iva if iva > 0 else total
                        # -----------------------------

                        reverso = database.es_reverso(t)
                        
                        if reverso: # Nota de Crédito
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento_id, f, "VENTAS", neto, 0, f"NC {t}", "VENTAS"))
                            if iva > 0: database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento_id, f, "IVA DEBITO FISCAL", iva, 0, f"NC {t}", "VENTAS"))
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento_id, f, "DEUDORES POR VENTAS", 0, total, f"NC {t}", "VENTAS"))
                        else: # Factura
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento_id, f, "DEUDORES POR VENTAS", total, 0, f"Venta {t}", "VENTAS"))
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento_id, f, "VENTAS", 0, neto, f"Venta {t}", "VENTAS"))
                            if iva > 0: database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento_id, f, "IVA DEBITO FISCAL", 0, iva, f"Venta {t}", "VENTAS"))
                        
                        asiento_id += 1
                        exitos += 1
                    except: continue
                
                if exitos > 0:
                    database.registrar_archivo(archivo.name, "VENTAS", exitos)
                    st.success(f"✅ Procesado: {exitos} asientos creados con éxito.")
                else:
                    st.error("No se pudo procesar ningún registro.")
        except Exception as e:
            st.error(f"Error en archivo: {e}")