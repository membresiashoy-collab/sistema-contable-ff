import streamlit as st
import pandas as pd
import database

def mostrar_ventas():
    st.title("📤 Módulo de Ventas")
    
    # Botón de historial arriba
    if st.button("📂 Ver Historial de Archivos Cargados"):
        st.subheader("Registros de Procesamiento")
        historial = database.ejecutar_query("SELECT fecha_proceso as 'Fecha', nombre_archivo as 'Archivo', registros as 'Asientos' FROM historial_archivos WHERE tipo='VENTAS' ORDER BY id DESC", fetch=True)
        if not historial.empty:
            st.table(historial)
        else:
            st.info("No hay archivos registrados en el historial.")

    archivo = st.file_uploader("Subir CSV de Ventas", type=["csv"])
    
    if archivo:
        try:
            # Leemos el archivo detectando el separador automáticamente
            df = pd.read_csv(archivo, sep=None, engine='python', encoding='latin-1')
            df.columns = [c.encode('latin-1', errors='ignore').decode('utf-8', errors='ignore').strip().upper() for c in df.columns]
            
            # Buscamos columnas de forma flexible
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
                        
                        # SOLUCIÓN AL ASIENTO EN 0:
                        # Si la columna IVA no existe o está vacía, el neto es el TOTAL
                        iva = 0
                        if c_iva and pd.notnull(r[c_iva]):
                            iva = float(str(r[c_iva]).replace(',', '.'))
                        
                        neto = total - iva if iva != 0 else total
                        
                        # Decidimos si es asiento directo o reverso (NC)
                        reverso = database.es_reverso(t)
                        
                        if reverso:
                            # NOTA DE CRÉDITO (Invertimos Debe y Haber)
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento_id, f, "VENTAS", neto, 0, f"NC {t}", "VENTAS"))
                            if iva > 0: database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento_id, f, "IVA DEBITO FISCAL", iva, 0, f"NC {t}", "VENTAS"))
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento_id, f, "DEUDORES POR VENTAS", 0, total, f"NC {t}", "VENTAS"))
                        else:
                            # FACTURA (Asiento estándar)
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento_id, f, "DEUDORES POR VENTAS", total, 0, f"Venta {t}", "VENTAS"))
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento_id, f, "VENTAS", 0, neto, f"Venta {t}", "VENTAS"))
                            if iva > 0: database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento_id, f, "IVA DEBITO FISCAL", 0, iva, f"Venta {t}", "VENTAS"))
                        
                        asiento_id += 1
                        contador += 1
                    except:
                        continue
                
                database.registrar_archivo(archivo.name, "VENTAS", contador)
                st.success(f"Se generaron {contador} asientos exitosamente.")
                st.rerun()
        except Exception as e:
            st.error(f"Error procesando el archivo: {e}")