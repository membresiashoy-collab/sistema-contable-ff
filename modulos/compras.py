import streamlit as st
import pandas as pd
import database

def mostrar_compras():
    st.title("📥 Módulo de Compras")
    
    if st.checkbox("📂 Ver Historial de Compras"):
        hist = database.ejecutar_query("SELECT fecha_proceso, nombre_archivo, registros FROM historial_archivos WHERE tipo='COMPRAS' ORDER BY id DESC", fetch=True)
        if not hist.empty:
            st.table(hist)

    archivo = st.file_uploader("Subir CSV de Compras (AFIP)", type=["csv"])
    
    if archivo:
        try:
            # Lectura del CSV
            df = pd.read_csv(archivo, sep=None, engine='python', encoding='latin-1')
            df.columns = [c.strip().upper() for c in df.columns]
            
            # Identificación de columnas (Fecha, Tipo, Total, IVA)
            c_f = next(c for c in df.columns if "FECHA" in c)
            c_t = next(c for c in df.columns if "TIPO" in c and "COMPROBANTE" in c)
            c_tot = next(c for c in df.columns if "TOTAL" in c and "IVA" not in c)
            # Buscamos IVA (puede ser Crédito Fiscal en compras)
            c_iva = next((c for c in df.columns if "IVA" in c and "TOTAL" in c), None)

            if st.button("🚀 Procesar Compras"):
                n_asiento = database.proximo_asiento()
                cont = 0
                
                for _, r in df.iterrows():
                    try:
                        f, t = r[c_f], str(r[c_t])
                        total = float(str(r[c_tot]).replace(',', '.'))
                        
                        # --- LÓGICA CONTABLE DE COMPRAS ---
                        iva = 0
                        if c_iva and pd.notnull(r[c_iva]):
                            try: iva = float(str(r[c_iva]).replace(',', '.'))
                            except: iva = 0
                        
                        # Si no hay IVA, el costo neto es el TOTAL
                        neto = total - iva if iva > 0 else total
                        
                        # Las compras aumentan por el DEBE
                        # 1. La cuenta de Gasto/Compra (NETO) va al DEBE (Columna 4)
                        database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (n_asiento, f, "COMPRAS", neto, 0, f"Compra {t}", "COMPRAS"))
                        
                        # 2. El IVA CRÉDITO FISCAL va al DEBE (si existe)
                        if iva > 0:
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (n_asiento, f, "IVA CREDITO FISCAL", iva, 0, f"Compra {t}", "COMPRAS"))
                        
                        # 3. La contrapartida (PROVEEDORES) va al HABER (Columna 5)
                        database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (n_asiento, f, "PROVEEDORES", 0, total, f"Compra {t}", "COMPRAS"))
                        
                        n_asiento += 1
                        cont += 1
                    except:
                        continue
                
                if cont > 0:
                    database.registrar_archivo(archivo.name, "COMPRAS", cont)
                    st.success(f"✅ Se procesaron {cont} asientos de compras.")
                else:
                    st.warning("No se detectaron registros válidos.")
                    
        except Exception as e:
            st.error(f"Error en módulo de compras: {e}")