import streamlit as st
import pandas as pd
from database import ejecutar_query

def limpiar_monto(valor):
    """Convierte formatos de moneda ARCA (1.234,56) a números reales (1234.56)"""
    if pd.isna(valor) or valor == "": return 0.0
    # Convertimos a string y quitamos símbolos de moneda o espacios
    s = str(valor).replace("$", "").strip()
    # TRUCO CLAVE: Quitamos el punto de miles y cambiamos la coma decimal por punto
    if "," in s and "." in s: # Caso 1.234,56
        s = s.replace(".", "").replace(",", ".")
    elif "," in s: # Caso 1234,56
        s = s.replace(",", ".")
    
    try:
        return float(s)
    except:
        return 0.0

def mostrar_ventas():
    st.title("📂 Procesamiento de Ventas ARCA")
    archivo = st.file_uploader("Subir CSV de ARCA", type=["csv"])
    
    if archivo:
        try:
            df = pd.read_csv(archivo, encoding='latin-1', sep=None, engine='python')
            df.columns = df.columns.str.strip() # Limpiar nombres de columnas
            
            st.write("### 🔍 Datos detectados en el archivo:")
            st.dataframe(df.head(5))

            if st.button("🚀 Generar Asientos Contables"):
                count = 0
                for _, fila in df.iterrows():
                    # Mapeo flexible de columnas (Busca por nombre o posición)
                    fecha = fila.get('Fecha de Emisión') or fila.get('Fecha') or fila.iloc[0]
                    total = limpiar_monto(fila.get('Importe Total') or fila.iloc[15])
                    neto = limpiar_monto(fila.get('Importe Neto Gravado') or fila.iloc[11])
                    iva = limpiar_monto(fila.get('Importe IVA') or fila.iloc[13])
                    receptor = fila.get('Denominación del Receptor') or fila.get('Nombre o Razón Social Receptor') or fila.iloc[7]

                    glosa = f"Venta s/Fac. ARCA - {receptor}"
                    
                    # 1. Caja/Clientes (DEBE)
                    ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?, ?, ?, ?, ?)", 
                                   (str(fecha), "Caja/Clientes", total, 0.0, glosa))
                    
                    # 2. Ventas Gravadas (HABER)
                    ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?, ?, ?, ?, ?)", 
                                   (str(fecha), "Ventas Gravadas", 0.0, neto, glosa))
                    
                    # 3. IVA Débito Fiscal (HABER)
                    if iva > 0:
                        ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?, ?, ?, ?, ?)", 
                                       (str(fecha), "IVA Débito Fiscal", 0.0, iva, glosa))
                    count += 1
                
                st.success(f"✅ ¡Éxito! Se procesaron {count} facturas con importes reales.")
        except Exception as e:
            st.error(f"Error al procesar: {e}")