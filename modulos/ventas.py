import streamlit as st
import pandas as pd
import database

def mostrar_ventas():
    st.title("📤 Módulo de Ventas")
    
    col1, col2 = st.columns([2, 1])
    with col2:
        ver_historial = st.button("📂 Ver Historial de Archivos")

    if ver_historial:
        st.subheader("Archivos Cargados Anteriormente")
        historial = database.ejecutar_query("SELECT fecha_proceso as 'Fecha', nombre_archivo as 'Archivo', registros as 'Filas' FROM historial_archivos WHERE tipo='VENTAS' ORDER BY id DESC", fetch=True)
        if not historial.empty:
            st.table(historial)
        else:
            st.info("No hay registros de archivos cargados.")

    archivo = st.file_uploader("Subir CSV de Ventas (AFIP)", type=["csv"])
    
    if archivo:
        try:
            df = pd.read_csv(archivo, sep=None, engine='python', encoding='latin-1')
            df.columns = [c.encode('latin-1', errors='ignore').decode('utf-8', errors='ignore').strip().upper() for c in df.columns]
            
            # Mapeo flexible de columnas
            c_f = next(c for c in df.columns if "FECHA" in c)
            c_t = next(c for c in df.columns if "TIPO" in c and "COMPROBANTE" in c)
            c_tot = next(c for c in df.columns if "TOTAL" in c and "IVA" not in c)
            c_iva = next((c for c in df.columns if "TOTAL IVA" in c or "IVA 21%" in c), None)

            if st.button("🚀 Procesar y Generar Asientos"):
                asiento_id = database.proximo_asiento()
                contador = 0
                
                for _, r in df.iterrows():
                    try:
                        f, t = r[c_f], str(r[c_t])
                        total = float(str(r[c_tot]).replace(',', '.'))
                        # Si no hay IVA o es 0, el neto es el total
                        iva = float(str(r[c_iva]).replace(',', '.')) if c_iva and pd.notnull(r[c_iva]) else 0
                        neto = total - iva if iva > 0 else total
                        
                        glosa = f"Venta: {t}"
                        
                        if database.es_reverso(t):
                            # NOTA DE CRÉDITO: Reversa el asiento
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento_id, f, "VENTAS", neto, 0, f"Anula {glosa}", "VENTAS"))
                            if iva > 0: database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento_id, f, "IVA DEBITO FISCAL", iva, 0, f"Anula {glosa}", "VENTAS"))
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento_id, f, "DEUDORES POR VENTAS", 0, total, f"Anula {glosa}", "VENTAS"))
                        else:
                            # FACTURA: Asiento directo
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento_id, f, "DEUDORES POR VENTAS", total, 0, glosa, "VENTAS"))
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento_id, f, "VENTAS", 0, neto, glosa, "VENTAS"))
                            if iva > 0: database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento_id, f, "IVA DEBITO FISCAL", 0, iva, glosa, "VENTAS"))
                        
                        asiento_id += 1
                        contador += 1
                    except Exception as row_err:
                        continue
                
                database.registrar_archivo(archivo.name, "VENTAS", contador)
                st.success(f"Éxito: {contador} asientos generados correctamente.")
        except Exception as e:
            st.error(f"Error crítico: {e}")