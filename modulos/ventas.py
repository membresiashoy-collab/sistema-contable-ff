import streamlit as st
import pandas as pd
import io
from database import ejecutar_query

def limpiar_num(valor):
    """Limpia formatos regionales de moneda (ej: 1.250,50 -> 1250.50)"""
    if pd.isna(valor) or valor == "": return 0.0
    s = str(valor).replace('.', '').replace(',', '.')
    try: return float(s)
    except: return 0.0

def mostrar_ventas():
    st.title("📂 Procesamiento con Plan de Cuentas")
    archivo = st.file_uploader("Subir CSV de ARCA", type=["csv"])
    
    if archivo:
        try:
            # Leemos y limpiamos comillas dobles del archivo crudo
            contenido = archivo.read().decode('latin-1').replace('"', '')
            df = pd.read_csv(io.StringIO(contenido), sep=';')
            
            st.success("Archivo vinculado al Plan de Cuentas con éxito.")
            st.dataframe(df.head(3))

            if st.button("🚀 Generar Asientos Contables"):
                count = 0
                for _, fila in df.iterrows():
                    # Mapeo por posición fija (0: Fecha, 8: Receptor, 22: Neto, 26: IVA, 27: Total)
                    f = fila.iloc[0]
                    r = fila.iloc[8]
                    n = limpiar_num(fila.iloc[22])
                    i = limpiar_num(fila.iloc[26])
                    t = limpiar_num(fila.iloc[27])

                    glosa = f"Venta s/Fac. ARCA - {r}"
                    
                    # --- GENERACIÓN DE ASIENTOS (PARTIDA DOBLE) ---
                    
                    # 1. Al DEBE: Cuenta de Activo según Plan de Cuentas
                    ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?)", 
                                   (f, "DEUDORES POR VENTAS", t, 0, glosa))
                    
                    # 2. Al HABER: Cuenta de Ingresos
                    ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?)", 
                                   (f, "VENTAS GRAVADAS", 0, n, glosa))
                    
                    # 3. Al HABER: Cuenta de Pasivo Fiscal
                    if i > 0:
                        ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?)", 
                                       (f, "IVA DEBITO FISCAL", 0, i, glosa))
                    count += 1
                
                st.success(f"✅ ¡Proceso Completo! Se integraron {count} facturas al Libro Diario.")
        except Exception as e:
            st.error(f"Error al procesar el archivo: {e}")