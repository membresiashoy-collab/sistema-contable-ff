import streamlit as st
import pandas as pd
import database

def mostrar_ventas():
    st.title("📤 Ventas - Importación ARCA")
    
    if st.button("🗑️ Vaciar Módulo Ventas"):
        database.borrar_datos_modulo("VENTAS")
        st.success("Registros de ventas eliminados.")
        st.rerun()

    archivo = st.file_uploader("Subir CSV de Ventas", type=["csv"])
    if archivo:
        try:
            # Detección automática de separador
            df = pd.read_csv(archivo, sep=None, engine='python', encoding='latin-1')
            # Normalizar nombres de columnas
            df.columns = [c.strip().upper().replace('"', '') for c in df.columns]
            st.write("Vista previa de columnas detectadas:", list(df.columns))

            if st.button("🚀 Generar Asientos Contables"):
                nro = database.proximo_asiento()
                for _, r in df.iterrows():
                    try:
                        # Mapeo flexible de nombres de columna
                        f = r.get('FECHA DE EMISIÓN', r.get('FECHA', ''))
                        t = str(r.get('TIPO DE COMPROBANTE', 'Factura'))
                        cli = r.get('DENOMINACIÓN RECEPTOR', 'Consumidor Final')
                        tot = float(str(r['IMPORTE TOTAL']).replace(',', '.'))
                        iva = float(str(r.get('TOTAL IVA', 0)).replace(',', '.'))
                        neto = tot - iva
                        glosa = f"{t}: {cli}"

                        if database.es_comprobante_inverso(t):
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (nro, f, "VENTAS", neto, 0, glosa, "VENTAS"))
                            if iva > 0: database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (nro, f, "IVA DEBITO FISCAL", iva, 0, glosa, "VENTAS"))
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (nro, f, "DEUDORES POR VENTAS", 0, tot, glosa, "VENTAS"))
                        else:
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (nro, f, "DEUDORES POR VENTAS", tot, 0, glosa, "VENTAS"))
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (nro, f, "VENTAS", 0, neto, glosa, "VENTAS"))
                            if iva > 0: database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (nro, f, "IVA DEBITO FISCAL", 0, iva, glosa, "VENTAS"))
                        nro += 1
                    except: continue
                st.success("¡Ventas procesadas con éxito!")
        except Exception as e:
            st.error(f"Error de lectura: {e}")