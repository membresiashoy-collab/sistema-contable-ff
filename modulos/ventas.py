import streamlit as st
import pandas as pd
import database

def mostrar_ventas():
    st.title("📤 Módulo de Ventas")
    
    if st.checkbox("📂 Ver Historial de Cargas"):
        hist = database.ejecutar_query("SELECT fecha_proceso, nombre_archivo, registros FROM historial_archivos WHERE tipo='VENTAS' ORDER BY id DESC", fetch=True)
        if not hist.empty:
            st.table(hist)

    archivo = st.file_uploader("Subir CSV de Ventas", type=["csv"])
    
    if archivo:
        try:
            df = pd.read_csv(archivo, sep=None, engine='python', encoding='latin-1')
            df.columns = [c.strip().upper() for c in df.columns]
            
            c_f = next(c for c in df.columns if "FECHA" in c)
            c_t = next(c for c in df.columns if "TIPO" in c and "COMPROBANTE" in c)
            c_tot = next(c for c in df.columns if "TOTAL" in c and "IVA" not in c)
            c_iva = next((c for c in df.columns if "TOTAL IVA" in c or "IVA 21%" in c), None)

            if st.button("🚀 Procesar"):
                n_asiento = database.proximo_asiento()
                cont = 0
                
                for _, r in df.iterrows():
                    try:
                        f, t = r[c_f], str(r[c_t])
                        total = float(str(r[c_tot]).replace(',', '.'))
                        
                        # Lógica: Si no hay IVA, Neto es el Total
                        iva = 0
                        if c_iva and pd.notnull(r[c_iva]):
                            try:
                                iva = float(str(r[c_iva]).replace(',', '.'))
                            except:
                                iva = 0
                        
                        neto = total - iva if iva > 0 else total
                        rev = database.es_reverso(t)
                        
                        if rev: # NOTA DE CRÉDITO
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (n_asiento, f, "VENTAS", neto, 0, f"NC {t}", "VENTAS"))
                            if iva > 0: database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (n_asiento, f, "IVA DEBITO FISCAL", iva, 0, f"NC {t}", "VENTAS"))
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (n_asiento, f, "DEUDORES POR VENTAS", 0, total, f"NC {t}", "VENTAS"))
                        else: # FACTURA (VENTAS AL HABER)
                            # Deudores al Debe
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (n_asiento, f, "DEUDORES POR VENTAS", total, 0, f"Venta {t}", "VENTAS"))
                            # Ventas al Haber
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (n_asiento, f, "VENTAS", 0, neto, f"Venta {t}", "VENTAS"))
                            # IVA al Haber
                            if iva > 0:
                                database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, gl