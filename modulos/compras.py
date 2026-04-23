import streamlit as st
import pandas as pd
import database

def mostrar_compras():
    st.title("📥 Compras - Importación Portal IVA")

    if st.button("🗑️ Vaciar Módulo Compras"):
        database.borrar_datos_modulo("COMPRAS")
        st.success("Registros de compras eliminados.")
        st.rerun()

    archivo = st.file_uploader("Subir CSV de Compras", type=["csv"])
    if archivo:
        try:
            df = pd.read_csv(archivo, sep=';', decimal=',', encoding='latin-1')
            df.columns = [c.strip().upper() for c in df.columns]

            if st.button("🚀 Generar Asientos Contables"):
                nro = database.proximo_asiento()
                for _, r in df.iterrows():
                    try:
                        f = r['FECHA DE EMISIÓN']
                        t = str(r['TIPO DE COMPROBANTE'])
                        prov = r['DENOMINACIÓN VENDEDOR']
                        tot = float(str(r['IMPORTE TOTAL']).replace(',', '.'))
                        iva = float(str(r.get('TOTAL IVA', 0)).replace(',', '.'))
                        neto = tot - iva
                        glosa = f"{t}: {prov}"

                        if database.es_comprobante_inverso(t):
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (nro, f, "PROVEEDORES", tot, 0, glosa, "COMPRAS"))
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (nro, f, "COMPRAS", 0, neto, glosa, "COMPRAS"))
                            if iva > 0: database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (nro, f, "IVA CREDITO FISCAL", 0, iva, glosa, "COMPRAS"))
                        else:
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (nro, f, "COMPRAS", neto, 0, glosa, "COMPRAS"))
                            if iva > 0: database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (nro, f, "IVA CREDITO FISCAL", iva, 0, glosa, "COMPRAS"))
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (nro, f, "PROVEEDORES", 0, tot, glosa, "COMPRAS"))
                        nro += 1
                    except: continue
                st.success("¡Compras procesadas con éxito!")
        except Exception as e:
            st.error(f"Error: Verifique que el CSV sea el de Compras de AFIP. {e}")