import streamlit as st
import pandas as pd
from database import ejecutar_query

def limpiar_num(v):
    if pd.isna(v) or v == "": return 0.0
    try:
        # Maneja formatos con puntos de miles y comas decimales
        s = str(v).replace('.', '').replace(',', '.')
        return float(s)
    except:
        return 0.0

def mostrar_ventas():
    st.title("📂 Procesamiento Individual de Comprobantes")
    
    # --- LÓGICA DE NUMERACIÓN DE ASIENTOS ---
    res_asiento = ejecutar_query("SELECT MAX(id_asiento) as ultimo FROM libro_diario", fetch=True)
    
    # CORRECCIÓN: Validamos si el DataFrame tiene datos antes de usar iloc[0]
    if not res_asiento.empty and pd.notna(res_asiento.iloc[0]['ultimo']):
        prox_asiento = int(res_asiento.iloc[0]['ultimo']) + 1
    else:
        prox_asiento = 1

    with st.expander("⚠️ Mantenimiento"):
        if st.button("🗑️ Vaciar Libro Diario"):
            ejecutar_query("DELETE FROM libro_diario")
            st.success("Diario vaciado correctamente.")
            st.rerun()

    archivo = st.file_uploader("Subir Ventas ARCA (CSV)", type=["csv"])
    
    if archivo:
        pdc = ejecutar_query("SELECT nombre FROM plan_cuentas", fetch=True)
        tipos = ejecutar_query("SELECT * FROM tipos_comprobantes", fetch=True)
        
        if pdc.empty or tipos.empty:
            st.error("❌ Configure el Plan de Cuentas y la Tabla de Comprobantes primero.")
            return

        # Cargamos las cuentas del PDC para mapeo
        lista_ctas = pdc['nombre'].tolist()
        cta_deudores = next((c for c in lista_ctas if "DEUDORES" in c), "DEUDORES POR VENTAS")
        cta_ventas = next((c for c in lista_ctas if "VENTAS" in c and "IVA" not in c), "VENTAS")
        cta_iva = next((c for c in lista_ctas if "IVA" in c and ("DF" in c or "DEBITO" in c)), "IVA DF")

        df = pd.read_csv(archivo, sep=';', encoding='latin-1')

        if st.button(f"🚀 Generar Asientos Individuales (Desde N° {prox_asiento})"):
            asiento_actual = prox_asiento
            
            for _, fila in df.iterrows():
                # Extraer datos por posición según el CSV de ARCA
                f = fila.iloc[0]          # Fecha
                cod_arca = int(fila.iloc[1]) # Código de Comprobante
                nro_comp = fila.iloc[2]   # Punto de Venta y Nro
                razon_social = fila.iloc[8]
                neto = limpiar_num(fila.iloc[22])
                iva = limpiar_num(fila.iloc[26])
                total = limpiar_num(fila.iloc[27])
                
                # Buscar lógica de signo según TABLACOMPROBANTES
                info_tipo = tipos[tipos['codigo'] == cod_arca]
                signo = info_tipo['signo'].values[0] if not info_tipo.empty else 1
                desc_tipo = info_tipo['descripcion'].values[0] if not info_tipo.empty else "COMPROBANTE"
                
                glosa = f"{desc_tipo} {nro_comp} - {razon_social}"

                if signo == 1: # FACTURAS / DÉBITOS
                    ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (asiento_actual, f, cta_deudores, total, 0, glosa))
                    ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (asiento_actual, f, cta_ventas, 0, neto, glosa))
                    if iva > 0:
                        ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (asiento_actual, f, cta_iva, 0, iva, glosa))
                else: # NOTAS DE CRÉDITO (Invertido)
                    ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (asiento_actual, f, cta_ventas, neto, 0, glosa))
                    if iva > 0:
                        ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (asiento_actual, f, cta_iva, iva, 0, glosa))
                    ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (asiento_actual, f, cta_deudores, 0, total, glosa))
                
                asiento_actual += 1 # Incrementar para el siguiente comprobante
            
            st.success(f"✅ Se procesaron {asiento_actual - prox_asiento} comprobantes como asientos individuales.")