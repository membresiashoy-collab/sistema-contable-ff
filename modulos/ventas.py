import streamlit as st
import pandas as pd
import io
from database import ejecutar_query

def limpiar_num(valor):
    if pd.isna(valor) or valor == "": return 0.0
    s = str(valor).replace('.', '').replace(',', '.')
    try: return float(s)
    except: return 0.0

def buscar_cuenta(lista_cuentas, palabra_clave):
    """Busca en el PDC una cuenta que contenga la palabra clave"""
    for cuenta in lista_cuentas:
        if palabra_clave.upper() in cuenta.upper():
            return cuenta
    return None

def mostrar_ventas():
    st.title("📂 Procesamiento Vinculado al Plan de Cuentas")
    archivo = st.file_uploader("Subir CSV de ARCA", type=["csv"])
    
    if archivo:
        # 1. Obtenemos el Plan de Cuentas actualizado
        pdc = ejecutar_query("SELECT nombre FROM plan_cuentas", fetch=True)
        if pdc.empty:
            st.error("❌ No hay Plan de Cuentas. Cárguelo en Configuración.")
            return
        
        lista_ctas = pdc['nombre'].tolist()

        # 2. MAPEAMOS DINÁMICAMENTE (El sistema busca según tu Plan)
        cta_deudores = buscar_cuenta(lista_ctas, "DEUDORES") or buscar_cuenta(lista_ctas, "CLIENTES")
        cta_ventas = buscar_cuenta(lista_ctas, "VENTAS")
        cta_iva = buscar_cuenta(lista_ctas, "IVA D") or buscar_cuenta(lista_ctas, "IVA DF")

        # Verificación de seguridad
        if not all([cta_deudores, cta_ventas, cta_iva]):
            st.warning("⚠️ No se encontraron coincidencias exactas en el Plan de Cuentas.")
            st.write(f"Detectadas: {cta_deudores} | {cta_ventas} | {cta_iva}")

        contenido = archivo.read().decode('latin-1').replace('"', '')
        df = pd.read_csv(io.StringIO(contenido), sep=';')

        if st.button("🚀 Generar Asientos "):
            count = 0
            for _, fila in df.iterrows():
                f, r = fila.iloc[0], fila.iloc[8]
                n, i, t = limpiar_num(fila.iloc[22]), limpiar_num(fila.iloc[26]), limpiar_num(fila.iloc[27])
                glosa = f"Venta s/Fac. ARCA - {r}"
                
                # USAMOS LAS CUENTAS ENCONTRADAS EN TU PLAN
                ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?)", 
                               (f, cta_deudores, t, 0, glosa))
                
                ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?)", 
                               (f, cta_ventas, 0, n, glosa))
                
                if i > 0:
                    ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?)", 
                                   (f, cta_iva, 0, i, glosa))
                count += 1
            st.success(f"✅ Se generaron {count} asientos usando nombres de TU Plan de Cuentas.")