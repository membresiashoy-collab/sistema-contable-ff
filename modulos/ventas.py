import streamlit as st
import pandas as pd
import database

def mostrar_ventas():
    st.title("📤 Módulo de Ventas")
    
    # 1. SECCIÓN DE HISTORIAL (Visible arriba para control)
    if st.checkbox("📂 Ver Historial de Archivos Cargados"):
        st.subheader("Registros de Procesamiento")
        historial = database.ejecutar_query("SELECT fecha_proceso as 'Fecha', nombre_archivo as 'Archivo', registros as 'Asientos' FROM historial_archivos WHERE tipo='VENTAS' ORDER BY id DESC", fetch=True)
        if not historial.empty:
            st.dataframe(historial, use_container_width=True, hide_index=True)
        else:
            st.info("No hay archivos registrados en el historial.")

    archivo = st.file_uploader("Subir CSV de Ventas (AFIP)", type=["csv"])
    
    if archivo:
        try:
            df = pd.read_csv(archivo, sep=None, engine='python', encoding='latin-1')
            df.columns = [c.encode('latin-1', errors='ignore').decode('utf-8', errors='ignore').strip().upper() for c in df.columns]
            
            # Mapeo flexible de columnas para evitar errores de tildes
            c_f = next(c for c in df.columns if "FECHA" in c)
            c_t = next(c for c in df.columns if "TIPO" in c and "COMPROBANTE" in c)
            c_tot = next(c for c in df.columns if "TOTAL" in c and "IVA" not in c)
            c_iva = next((c for c in df.columns if "TOTAL IVA" in c or "IVA 21%" in c), None)

            if st.button("🚀 Procesar y Generar Asientos"):
                asiento_id = database.proximo_asiento()
                contador_exitos = 0
                
                for _, r in df.iterrows():
                    try:
                        f, t = r[c_f], str(r[c_t])
                        total = float(str(r[c_tot]).replace(',', '.'))
                        
                        # --- LÓGICA DE IMPORTE DEFINITIVA ---
                        # Intentamos obtener el IVA, si no existe o es 0, el neto es el TOTAL
                        iva = 0
                        if c_iva and pd.notnull(r[c_iva]):
                            try:
                                iva = float(str(r[c_iva]).replace(',', '.'))
                            except:
                                iva = 0
                        
                        # Si el neto calculado es 0 o el IVA es 0, usamos el TOTAL como base
                        neto = total - iva
                        if neto <= 0 or iva == 0:
                            neto = total
                            iva = 0 # Aseguramos que no haya basura en el IVA si usamos el total
                        
                        reverso = database.es_reverso(t)
                        glosa = f"{t}"
                        
                        if reverso:
                            # NOTA DE CRÉDITO: Reversa (Neto y IVA al Debe, Deudores al Haber)
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento_id, f, "VENTAS", neto, 0, f"NC {glosa}", "VENTAS"))
                            if iva > 0: database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento_id, f, "IVA DEBITO FISCAL", iva, 0, f"NC {glosa}", "VENTAS"))
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento_id, f, "DEUDORES POR VENTAS", 0, total, f"NC {glosa}", "VENTAS"))
                        else:
                            # FACTURA: Directo (Deudores al Debe, Ventas e IVA al Haber)
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento_id, f, "DEUDORES POR VENTAS", total, 0, f"Fact {glosa}", "VENTAS"))
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento_id, f, "VENTAS", 0, neto, f"Fact {glosa}", "VENTAS"))
                            if iva > 0: database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento_id, f, "IVA DEBITO FISCAL", 0, iva, f"Fact {glosa}", "VENTAS"))
                        
                        asiento_id += 1
                        contador_exitos += 1
                    except:
                        continue
                
                # Registro en historial y aviso al usuario
                if contador_exitos > 0:
                    database.registrar_archivo(archivo.name, "VENTAS", contador_exitos)
                    # Usamos st.success SIN st.rerun inmediato para que el usuario vea el mensaje
                    st.success(f"✅ ¡Proceso Exitoso! Se registraron {contador_exitos} asientos contables.")
                    st.balloons() # Efecto visual para confirmar que terminó
                else:
                    st.warning("No se procesaron registros. Verifique el formato del archivo.")
                    
        except Exception as e:
            st.error(f"Error crítico al leer el archivo: {e}")