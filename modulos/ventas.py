import streamlit as st
import pandas as pd
import database

def mostrar_ventas():
    st.title("📤 Módulo de Ventas")
    
    # Historial visible mediante checkbox para no estorbar
    if st.checkbox("📂 Ver historial de cargas"):
        historial = database.ejecutar_query("SELECT fecha_proceso as 'Fecha', nombre_archivo as 'Archivo', registros as 'Asientos' FROM historial_archivos WHERE tipo='VENTAS' ORDER BY id DESC", fetch=True)
        if not historial.empty:
            st.table(historial)
        else:
            st.info("Sin registros previos.")

    archivo = st.file_uploader("Subir CSV de Ventas", type=["csv"])
    
    if archivo:
        try:
            df = pd.read_csv(archivo, sep=None, engine='python', encoding='latin-1')
            df.columns = [c.encode('latin-1', errors='ignore').decode('utf-8', errors='ignore').strip().upper() for c in df.columns]
            
            # Localización de columnas
            c_f = next(c for c in df.columns if "FECHA" in c)
            c_t = next(c for c in df.columns if "TIPO" in c and "COMPROBANTE" in c)
            c_tot = next(c for c in df.columns if "TOTAL" in c and "IVA" not in c)
            c_iva = next((c for c in df.columns if "TOTAL IVA" in c or "IVA 21%" in c), None)

            if st.button("🚀 Procesar Comprobantes"):
                asiento_id = database.proximo_asiento()
                exitos = 0
                
                for _, r in df.iterrows():
                    try:
                        f, t = r[c_f], str(r[c_t])
                        total = float(str(r[c_tot]).replace(',', '.'))
                        
                        # LÓGICA DE IMPORTE: Si no hay IVA o el neto es 0, usamos TOTAL
                        iva = 0
                        if c_iva and pd.notnull(r[c_iva]):
                            iva = float(str(r[c_iva]).replace(',', '.'))
                        
                        neto = total - iva
                        if neto <= 0 or iva == 0:
                            neto = total
                            iva = 0

                        if database.es_reverso(t):
                            # Nota de Crédito
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento_id, f, "VENTAS", neto, 0, f"NC {t}", "VENTAS"))
                            if iva > 0: database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento_id, f, "IVA DEBITO FISCAL", iva, 0, f"NC {t}", "VENTAS"))
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento_id, f, "DEUDORES POR VENTAS", 0, total, f"NC {t}", "VENTAS"))
                        else:
                            # Factura
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento_id, f, "DEUDORES POR VENTAS", total, 0, f"Venta {t}", "VENTAS"))
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento_id, f, "VENTAS", 0, neto, f"Venta {t}", "VENTAS"))
                            if iva > 0: database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento_id, f, "IVA DEBITO FISCAL", 0, iva, f"Venta {t}", "VENTAS"))
                        
                        asiento_id += 1
                        exitos += 1
                    except: continue
                
                if exitos > 0:
                    database.registrar_archivo(archivo.name, "VENTAS", exitos)
                    st.success(f"✅ Se procesaron {exitos} registros con éxito.")
                    st.info("Ya podés ver los asientos en el Libro Diario.")
                else:
                    st.warning("No se pudo procesar ningún registro.")

        except Exception as e:
            st.error(f"Error crítico: {e}")