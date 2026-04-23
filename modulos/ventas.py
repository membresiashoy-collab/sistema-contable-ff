import streamlit as st
import pandas as pd
import io
from database import ejecutar_query

def limpiar_num(valor):
    if pd.isna(valor) or valor == "": return 0.0
    s = str(valor).replace('.', '').replace(',', '.')
    try: return float(s)
    except: return 0.0

def mostrar_ventas():
    st.title("📂 Carga de Ventas con Lógica de Comprobantes")
    archivo = st.file_uploader("Subir Ventas ARCA", type=["csv"])
    
    if archivo:
        # Cargamos Plan y Tipos para validar
        pdc = ejecutar_query("SELECT nombre FROM plan_cuentas", fetch=True)
        tipos = ejecutar_query("SELECT * FROM tipos_comprobantes", fetch=True)
        
        if pdc.empty or tipos.empty:
            st.error("Falta cargar el Plan de Cuentas o la Tabla de Comprobantes en Configuración.")
            return

        # Buscamos cuentas en tu plan
        lista_ctas = pdc['nombre'].tolist()
        cta_deudores = next((c for c in lista_ctas if "DEUDORES" in c), "DEUDORES POR VENTAS")
        cta_ventas = next((c for c in lista_ctas if "VENTAS" in c and "IVA" not in c), "VENTAS")
        cta_iva = next((c for c in lista_ctas if "IVA" in c and ("DF" in c or "DEBITO" in c)), "IVA DF")

        contenido = archivo.read().decode('latin-1').replace('"', '')
        df = pd.read_csv(io.StringIO(contenido), sep=';')

        if st.button("🚀 Procesar con Lógica ARCA"):
            for _, fila in df.iterrows():
                cod_tipo = int(fila.iloc[1]) # Código de comprobante ARCA
                f, r = fila.iloc[0], fila.iloc[8]
                n, i, t = limpiar_num(fila.iloc[22]), limpiar_num(fila.iloc[26]), limpiar_num(fila.iloc[27])
                
                # Buscamos el signo
                res_tipo = tipos[tipos['codigo'] == cod_tipo]
                signo = res_tipo['signo'].values[0] if not res_tipo.empty else 1
                desc_tipo = res_tipo['descripcion'].values[0] if not res_tipo.empty else "COMPROBANTE"
                
                glosa = f"{desc_tipo} - {r}"

                if signo == 1: # FACTURAS / DÉBITOS
                    ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?)", (f, cta_deudores, t, 0, glosa))
                    ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?)", (f, cta_ventas, 0, n, glosa))
                    if i > 0: ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?)", (f, cta_iva, 0, i, glosa))
                else: # NOTAS DE CRÉDITO (Invertido)
                    ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?)", (f, cta_deudores, 0, t, glosa))
                    ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?)", (f, cta_ventas, n, 0, glosa))
                    if i > 0: ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?)", (f, cta_iva, i, 0, glosa))
            st.success("Procesamiento finalizado con éxito.")