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
    st.title("📂 Procesamiento de Ventas (Libro Diario)")
    
    with st.expander("⚠️ Mantenimiento"):
        if st.button("🗑️ Vaciar Libro Diario"):
            ejecutar_query("DELETE FROM libro_diario")
            st.success("Diario vaciado.")

    archivo = st.file_uploader("Subir Ventas ARCA", type=["csv"])
    
    if archivo:
        pdc = ejecutar_query("SELECT nombre FROM plan_cuentas", fetch=True)
        tipos = ejecutar_query("SELECT * FROM tipos_comprobantes", fetch=True)
        
        if pdc.empty or tipos.empty:
            st.error("❌ Configure Plan de Cuentas y Tabla de Comprobantes.")
            return

        lista_ctas = pdc['nombre'].tolist()
        cta_deudores = next((c for c in lista_ctas if "DEUDORES" in c), "DEUDORES POR VENTAS")
        cta_ventas = next((c for c in lista_ctas if "VENTAS" in c and "IVA" not in c), "VENTAS")
        cta_iva = next((c for c in lista_ctas if "IVA" in c and ("DF" in c or "DEBITO" in c)), "IVA DF")

        df = pd.read_csv(archivo, sep=';', encoding='latin-1')

        if st.button("🚀 Generar Asientos Individuales"):
            for _, fila in df.iterrows():
                # Extracción de datos
                cod_arca = int(fila.iloc[1])
                f, r = fila.iloc[0], fila.iloc[8]
                n, i, t = limpiar_num(fila.iloc[22]), limpiar_num(fila.iloc[26]), limpiar_num(fila.iloc[27])
                
                res_tipo = tipos[tipos['codigo'] == cod_arca]
                signo = res_tipo['signo'].values[0] if not res_tipo.empty else 1
                desc_tipo = res_tipo['descripcion'].values[0] if not res_tipo.empty else "FACTURA"
                
                # Glosa única por comprobante para identificarlo en el Diario
                glosa = f"{desc_tipo} Nro {fila.iloc[2]} - {r}"

                if signo == 1: # FACTURA (Activo sube por el Debe)
                    ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?)", (f, cta_deudores, t, 0, glosa))
                    ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?)", (f, cta_ventas, 0, n, glosa))
                    if i > 0:
                        ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?)", (f, cta_iva, 0, i, glosa))
                else: # NOTA DE CRÉDITO (Inversión del asiento)
                    ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?)", (f, cta_ventas, n, 0, glosa))
                    if i > 0:
                        ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?)", (f, cta_iva, i, 0, glosa))
                    ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?)", (f, cta_deudores, 0, t, glosa))
            
            st.success("✅ Asientos generados individualmente por comprobante.")