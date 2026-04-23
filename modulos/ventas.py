import streamlit as st
import pandas as pd
import database

def mostrar_ventas():
    st.title("📤 Procesamiento de Ventas")
    
    if st.button("🗑️ Limpiar Datos de Ventas"):
        database.borrar_datos_modulo("VENTAS")
        st.success("Registros de ventas eliminados.")
        st.rerun()

    archivo = st.file_uploader("Subir CSV de Ventas", type=["csv"])
    if archivo:
        try:
            # Ventas suele venir con coma o punto y coma
            df = pd.read_csv(archivo, sep=None, engine='python', encoding='latin-1')
            df.columns = [c.strip().replace('"', '') for c in df.columns]
            
            if st.button("🚀 Generar Asientos Contables"):
                nro_asiento = database.proximo_asiento()
                for _, r in df.iterrows():
                    try:
                        fecha = r.get('Fecha de Emisión', r.get('Fecha'))
                        tipo = str(r.get('Tipo de Comprobante', 'Factura'))
                        cli = r.get('Denominación Receptor', 'C. Final')
                        tot = float(str(r['Importe Total']).replace(',', '.'))
                        iva = float(str(r.get('Total IVA', 0)).replace(',', '.'))
                        neto = tot - iva
                        glosa = f"{tipo}: {cli}"

                        if database.es_comprobante_inverso(tipo):
                            # Reverso: Venta (D), IVA (D) a Deudores (H)
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (nro_asiento, fecha, "VENTAS", neto, 0, glosa, "VENTAS"))
                            if iva > 0: database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (nro_asiento, fecha, "IVA DEBITO FISCAL", iva, 0, glosa, "VENTAS"))
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (nro_asiento, fecha, "DEUDORES POR VENTAS", 0, tot, glosa, "VENTAS"))
                        else:
                            # Normal: Deudores (D) a Venta (H), IVA (H)
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (nro_asiento, fecha, "DEUDORES POR VENTAS", tot, 0, glosa, "VENTAS"))
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (nro_asiento, fecha, "VENTAS", 0, neto, glosa, "VENTAS"))
                            if iva > 0: database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (nro_asiento, fecha, "IVA DEBITO FISCAL", 0, iva, glosa, "VENTAS"))
                        nro_asiento += 1
                    except: continue
                st.success("Asientos de Ventas generados correctamente.")
        except Exception as e:
            st.error(f"Error al leer archivo: {e}")