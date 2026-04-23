import streamlit as st
import pandas as pd
from database import ejecutar_query

def mostrar_ventas():
    st.title("📂 Procesar Ventas ARCA (CSV)")
    archivo = st.file_uploader("Subir CSV de ARCA", type=["csv"])
    
    if archivo:
        try:
            # 1. Leer y limpiar datos
            df = pd.read_csv(archivo, encoding='latin-1', sep=None, engine='python')
            df.columns = df.columns.str.strip()
            
            st.write("### 🔍 Vista previa del archivo:")
            st.dataframe(df.head(5))

            # Botón para confirmar el procesamiento contable
            if st.button("🚀 Generar Asientos Contables"):
                count = 0
                for index, fila in df.iterrows():
                    # Extraer datos (ajustar nombres según tu CSV si fallan)
                    fecha = fila.get('Fecha de Emisión') or fila.iloc[0]
                    total = float(fila.get('Importe Total') or fila.iloc[15])
                    neto = float(fila.get('Importe Neto Gravado') or fila.iloc[11])
                    iva = float(fila.get('Importe IVA') or fila.iloc[13])
                    receptor = fila.get('Denominación del Receptor') or fila.iloc[7]

                    # --- LÓGICA CONTABLE (GENERACIÓN DE ASIENTO) ---
                    glosa = f"Venta s/Fac. ARCA - {receptor}"
                    
                    # 1. Registro al Debe (Deudores por Ventas)
                    ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?, ?, ?, ?, ?)",
                                   (str(fecha), "Deudores por Ventas", total, 0, glosa))
                    
                    # 2. Registro al Haber (Ventas Netas)
                    ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?, ?, ?, ?, ?)",
                                   (str(fecha), "Ventas Gravadas", 0, neto, glosa))
                    
                    # 3. Registro al Haber (IVA Débito Fiscal)
                    if iva > 0:
                        ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?, ?, ?, ?, ?)",
                                       (str(fecha), "IVA Débito Fiscal", 0, iva, glosa))
                    
                    count += 1
                
                st.success(f"✅ ¡Proceso Completo! Se generaron {count} asientos contables.")
                
                # --- VISUALIZACIÓN DE ASIENTOS ---
                st.write("### 📝 Asientos Generados en el Libro Diario:")
                asientos = ejecutar_query("SELECT * FROM libro_diario ORDER BY id DESC LIMIT ?", (count * 3,), fetch=True)
                st.table(asientos)

        except Exception as e:
            st.error(f"Error técnico: {e}")