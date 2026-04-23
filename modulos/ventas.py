import streamlit as st
import pandas as pd
import io
from database import ejecutar_query

def limpiar_num(valor):
    if pd.isna(valor) or valor == "": return 0.0
    # Quitamos cualquier carácter que no sea número, coma o punto
    s = str(valor).replace('.', '').replace(',', '.')
    try: return float(s)
    except: return 0.0

def mostrar_ventas():
    st.title("📂 Carga Profesional de Ventas")
    archivo = st.file_uploader("Subir CSV de ARCA", type=["csv"])
    
    if archivo:
        try:
            # LEER ARCHIVO COMO TEXTO PARA LIMPIARLO
            contenido = archivo.read().decode('latin-1')
            # Quitamos las comillas dobles que causan el error de claves
            contenido_limpio = contenido.replace('"', '')
            
            # Convertimos el texto limpio de nuevo a un formato que Pandas entienda
            df = pd.read_csv(io.StringIO(contenido_limpio), sep=';')
            
            st.write("### ✅ Archivo interpretado correctamente")
            st.dataframe(df.head(3))

            if st.button("🚀 Procesar Asientos Contables"):
                count = 0
                for _, fila in df.iterrows():
                    # Usamos ILOC (posición) para que no importe cómo se llame la columna
                    # 0=Fecha, 8=Receptor, 22=Neto, 26=IVA, 27=Total
                    f = fila.iloc[0]
                    r = fila.iloc[8]
                    n = limpiar_num(fila.iloc[22])
                    i = limpiar_num(fila.iloc[26])
                    t = limpiar_num(fila.iloc[27])

                    glosa = f"Venta s/Fac. ARCA - {r}"
                    
                    # Partida Doble
                    ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?)", (f, "Caja/Clientes", t, 0, glosa))
                    ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?)", (f, "Ventas Gravadas", 0, n, glosa))
                    if i > 0:
                        ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?)", (f, "IVA Débito Fiscal", 0, i, glosa))
                    count += 1
                st.success(f"✅ Se generaron {count} asientos con éxito.")
        except Exception as e:
            st.error(f"Error crítico de lectura: {e}")