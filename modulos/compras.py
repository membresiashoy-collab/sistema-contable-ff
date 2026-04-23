import streamlit as st
import pandas as pd
import database

def mostrar_compras():
    st.title("📥 Procesamiento de Compras")

    if st.button("🗑️ Limpiar Datos de Compras"):
        database.borrar_datos_modulo("COMPRAS")
        st.success("Registros de compras eliminados.")
        st.rerun()

    archivo = st.file_uploader("Subir CSV de Compras", type=["csv"])
    if archivo:
        try:
            # Compras Portal IVA usa ';' y ',' para decimales
            df = pd.read_csv(archivo, sep=';', decimal=',', encoding='latin-1')
            df.columns = [c.strip().replace('"', '') for c in df.columns]

            if st.button("🚀 Generar Asientos Contables"):
                nro_asiento = database.proximo_asiento()
                for _, r in df.iterrows():
                    try:
                        fecha = r['Fecha de Emisión']
                        tipo = str(r['Tipo de Comprobante'])
                        prov = r['Denominación Vendedor']
                        tot = float(str(r['Importe Total']).replace(',', '.'))
                        iva = float(str(r.get('Total IVA', 0)).replace(',', '.'))
                        neto = tot - iva
                        glosa = f"{tipo}: {prov}"

                        if database.es_comprobante_inverso(tipo):
                            # NC Compras: Proveedor (D) a Compra (H), IVA (H)
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (nro_asiento, fecha, "PROVEEDORES", tot, 0, glosa, "COMPRAS"))
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (nro_asiento, fecha, "COMPRAS", 0, neto, glosa, "COMPRAS"))
                            if iva > 0: database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (nro_asiento, fecha, "IVA CREDITO FISCAL", 0, iva, glosa, "COMPRAS"))
                        else:
                            # Factura Compras: Compra (D), IVA (D) a Proveedor (H)
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (nro_asiento, fecha, "COMPRAS", neto, 0, glosa, "COMPRAS"))
                            if iva > 0: database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (nro_asiento, fecha, "IVA CREDITO FISCAL", iva, 0, glosa, "COMPRAS"))
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (nro_asiento, fecha, "PROVEEDORES", 0, tot, glosa, "COMPRAS"))
                        nro_asiento += 1
                    except: continue
                st.success("Asientos de Compras generados correctamente.")
        except Exception as e:
            st.error(f"Error al leer archivo: {e}")