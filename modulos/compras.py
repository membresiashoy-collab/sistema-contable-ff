import streamlit as st
import pandas as pd
import io
from database import ejecutar_query, obtener_proximo_asiento

def mostrar_compras():
    st.title("📥 Módulo de Compras")
    st.info("Subí el archivo 'comprobantes_compras.csv' descargado del portal IVA.")

    archivo = st.file_uploader("Seleccionar CSV", type=["csv"])

    if archivo:
        # Lectura configurada para tu archivo específico
        df = pd.read_csv(archivo, sep=';', decimal=',', encoding='utf-8')
        
        # Limpieza de columnas (quitar comillas si las hay)
        df.columns = [c.strip('"') for c in df.columns]

        st.subheader("Pre-visualización de Datos")
        st.dataframe(df[['Fecha de Emisión', 'Denominación Vendedor', 'Importe Total', 'Total IVA']].head())

        if st.button("Confirmar y Grabar en Diario"):
            prox_asiento = obtener_proximo_asiento()
            cont_exito = 0

            for _, row in df.iterrows():
                fecha = row['Fecha de Emisión']
                proveedor = str(row['Denominación Vendedor']).strip('"')
                total = float(row['Importe Total'])
                iva = float(row['Total IVA'])
                neto = total - iva
                glosa = f"Compra: {proveedor}"

                # 1. Asiento Contable
                # DEBE: Compras (Neto)
                ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)",
                               (prox_asiento, fecha, "COMPRAS", neto, 0, glosa))
                # DEBE: IVA Crédito Fiscal
                ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)",
                               (prox_asiento, fecha, "IVA CREDITO FISCAL", iva, 0, glosa))
                # HABER: Proveedores (Total)
                ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)",
                               (prox_asiento, fecha, "PROVEEDORES", 0, total, glosa))
                
                # 2. Registrar en tabla compras para estadísticas
                ejecutar_query("INSERT INTO compras (fecha, proveedor, neto_gravado, iva_total, total) VALUES (?,?,?,?,?)",
                               (fecha, proveedor, neto, iva, total))
                
                prox_asiento += 1
                cont_exito += 1

            st.success(f"Se registraron {cont_exito} comprobantes y sus asientos correspondientes.")