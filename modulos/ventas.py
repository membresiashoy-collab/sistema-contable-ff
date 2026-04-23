import streamlit as st
import pandas as pd
from database import ejecutar_query

def limpiar_arca(valor):
    if pd.isna(valor) or valor == "": return 0.0
    # Quitamos puntos de miles y cambiamos coma por punto
    s = str(valor).replace('.', '').replace(',', '.')
    try: return float(s)
    except: return 0.0

def mostrar_ventas():
    st.title("📂 Procesar Ventas ARCA")
    archivo = st.file_uploader("Subir CSV de ARCA", type=["csv"])
    
    if archivo:
        try:
            # Leemos con el separador detectado en tu archivo
            df = pd.read_csv(archivo, sep=';', encoding='latin-1')
            
            # LIMPIEZA CRUCIAL: Quitamos comillas dobles y espacios de los nombres de columnas
            df.columns = df.columns.str.replace('"', '').str.strip()
            
            st.write("### 🔍 Vista previa de datos limpios:")
            st.dataframe(df.head(3))

            if st.button("🚀 Generar Contabilidad Real"):
                count = 0
                for _, fila in df.iterrows():
                    # Usamos los nombres exactos del CSV de ARCA
                    fecha = fila['Fecha de Emisión']
                    neto = limpiar_arca(fila['Imp. Neto Gravado Total'])
                    iva = limpiar_arca(fila['Total IVA'])
                    total = limpiar_arca(fila['Imp. Total'])
                    receptor = fila['Denominación Receptor']

                    glosa = f"Venta s/Fac. - {receptor}"
                    
                    # Asiento de Partida Doble
                    ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?)",
                                   (str(fecha), "Caja/Clientes", total, 0, glosa))
                    ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?)",
                                   (str(fecha), "Ventas Gravadas", 0, neto, glosa))
                    if iva > 0:
                        ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?)",
                                       (str(fecha), "IVA Débito Fiscal", 0, iva, glosa))
                    count += 1
                
                st.success(f"✅ ¡Éxito! Se procesaron {count} facturas con importes reales.")
        except Exception as e:
            st.error(f"Error al procesar columnas: {e}")
            st.info("Nota: Si el error persiste, verifica que el archivo no esté abierto en Excel.")