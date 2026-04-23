import streamlit as st
import pandas as pd
import database

def mostrar_ventas():
    st.title("📤 Módulo de Ventas")
    
    # Historial de Cargas
    if st.checkbox("📂 Ver Historial de Archivos Cargados"):
        hist = database.ejecutar_query("SELECT fecha_proceso as 'Fecha', nombre_archivo as 'Archivo', registros as 'Asientos' FROM historial_archivos WHERE tipo='VENTAS' ORDER BY id DESC", fetch=True)
        if not hist.empty:
            st.dataframe(hist, use_container_width=True, hide_index=True)
        else:
            st.info("No hay registros previos.")

    archivo = st.file_uploader("Subir CSV de Ventas (AFIP)", type=["csv"])
    
    if archivo:
        try:
            df = pd.read_csv(archivo, sep=None, engine='python', encoding='latin-1')
            df.columns = [c.strip().upper() for c in df.columns]
            
            # Identificación de columnas clave
            c_f = next(c for c in df.columns if "FECHA" in c)
            c_t = next(c for c in df.columns if "TIPO" in c and "COMPROBANTE" in c)
            c_tot = next(c for c in df.columns if "TOTAL" in c and "IVA" not in c)
            c_iva = next((c for c in df.columns if "TOTAL IVA" in c or "IVA 21%" in c), None)

            if st.button("🚀 Generar Asientos Contables"):
                asiento_id = database.proximo_asiento()
                exitos = 0
                
                for _, r in df.iterrows():
                    try:
                        f, t = r[c_f], str(r[c_t])
                        total = float(str(r[c_tot]).replace(',', '.'))
                        
                        # --- LÓGICA DE IVA Y NETO ---
                        iva = 0
                        if c_iva and pd.notnull(r[c_iva]):
                            try: iva = float(str(r[c_iva]).replace(',', '.'))
                            except: iva = 0
                        
                        # SI NO HAY IVA (Factura C / Monotributo), VENTAS = TOTAL
                        neto = total - iva if iva > 0 else total
                        # ----------------------------

                        # Determinamos si es Factura o Nota de Crédito (Reverso)
                        reverso = database.es_reverso(t)
                        
                        if reverso:
                            # NOTA DE CRÉDITO: Reversa la operación
                            # Ventas (D) a Deudores (H)
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento_id, f, "VENTAS", neto, 0, f"NC {t}", "VENTAS"))
                            if iva > 0: database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento_id, f, "IVA DEBITO FISCAL", iva, 0, f"NC {t}", "VENTAS"))
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento_id, f, "DEUDORES POR VENTAS", 0, total, f"NC {t}", "VENTAS"))
                        else:
                            # FACTURA: Operación normal
                            # Deudores (D) a Ventas (H) e IVA (H)
                            # 1. El cliente nos debe el TOTAL al DEBE
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento_id, f, "DEUDORES POR VENTAS", total, 0, f"Venta {t}", "VENTAS"))
                            
                            # 2. El