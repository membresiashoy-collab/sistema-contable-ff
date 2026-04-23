import streamlit as st
import pandas as pd
import database

def mostrar_ventas():
    st.title("📤 Módulo de Ventas")
    
    # Historial de cargas
    if st.checkbox("📂 Ver archivos procesados"):
        hist = database.ejecutar_query("SELECT fecha_proceso, nombre_archivo, registros FROM historial_archivos WHERE tipo='VENTAS' ORDER BY id DESC", fetch=True)
        if not hist.empty: st.table(hist)

    archivo = st.file_uploader("Subir CSV de Ventas", type=["csv"])
    
    if archivo:
        try:
            df = pd.read_csv(archivo, sep=None, engine='python', encoding='latin-1')
            df.columns = [c.strip().upper() for c in df.columns]
            
            # Detectar columnas clave
            col_fecha = next(c for c in df.columns if "FECHA" in c)
            col_tipo = next(c for c in df.columns if "TIPO" in c and "COMPROBANTE" in c)
            col_total = next(c for c in df.columns if "TOTAL" in c and "IVA" not in c)
            col_iva = next((c for c in df.columns if "TOTAL IVA" in c or "IVA 21%" in c), None)

            if st.button("🚀 Procesar"):
                n_asiento = database.proximo_asiento()
                cont = 0
                
                for _, r in df.iterrows():
                    try:
                        f, t = r[col_fecha], str(r[col_tipo])
                        total = float(str(r[col_total]).replace(',', '.'))
                        
                        # --- LÓGICA SOLICITADA ---
                        iva = 0
                        if col_iva and pd.notnull(r[col_iva]):
                            try: iva = float(str(r[col_iva]).replace(',', '.'))
                            except: iva = 0
                        
                        # SI NO HAY IVA (o es 0), LA VENTA ES EL TOTAL
                        neto = total - iva if iva > 0 else total
                        # -------------------------

                        rev = database.es_reverso(t)
                        
                        if rev: # Nota de Crédito (Invierte Debe/Haber)
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (n_asiento, f, "VENTAS", neto, 0, f"NC {t}", "VENTAS"))
                            if iva > 0: database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (n_asiento, f, "IVA DEBITO FISCAL", iva, 0, f"NC {t}", "VENTAS"))
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (n_asiento, f, "DEUDORES POR VENTAS", 0, total, f"NC {t}", "VENTAS"))
                        else: # Factura Normal
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (n_asiento, f, "DEUDORES POR VENTAS", total, 0, f"Venta {t}", "VENTAS"))
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (n_asiento, f, "VENTAS", 0, neto, f"Venta {t}", "VENTAS"))
                            if iva > 0: database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (n_asiento, f, "IVA DEBITO FISCAL", 0, iva, f"Venta {t}", "VENTAS"))
                        
                        n_asiento += 1
                        cont += 1
                    except: continue
                
                if cont > 0:
                    database.registrar_archivo(archivo.name, "VENTAS", cont)
                    st.success(f"✅ Se generaron {cont} asientos correctamente.")
                else:
                    st.error("No se encontraron registros válidos.")
        except Exception as e:
            st.error(f"Error: {e}")