import streamlit as st
import pandas as pd
from database import ejecutar_query

def mostrar_ventas():
    st.title("📂 Procesamiento Individual de Comprobantes")
    
    # 1. Obtener el último número de asiento para continuar la correlatividad
    res_asiento = ejecutar_query("SELECT MAX(id_asiento) as ultimo FROM libro_diario", fetch=True)
    prox_asiento = (res_asiento.iloc[0]['ultimo'] or 0) + 1

    archivo = st.file_uploader("Subir Ventas ARCA (CSV)", type=["csv"])
    
    if archivo:
        # Cargamos el Plan de Cuentas y Tipos para la lógica
        pdc = ejecutar_query("SELECT nombre FROM plan_cuentas", fetch=True)
        tipos = ejecutar_query("SELECT * FROM tipos_comprobantes", fetch=True)
        
        if pdc.empty or tipos.empty:
            st.error("⚠️ Error: Configure el Plan de Cuentas y la Tabla de Comprobantes primero.")
            return

        df = pd.read_csv(archivo, sep=';', encoding='latin-1')

        if st.button(f"🚀 Procesar desde Asiento N° {prox_asiento}"):
            asiento_actual = prox_asiento
            
            for _, fila in df.iterrows():
                # Datos del Comprobante
                f = fila.iloc[0]          # Fecha
                cod_tipo = int(fila.iloc[1]) # Código ARCA
                nro_comp = fila.iloc[2]   # Número de comprobante
                cliente = fila.iloc[8]    # Nombre Cliente
                neto = limpiar_num(fila.iloc[22])
                iva = limpiar_num(fila.iloc[26])
                total = limpiar_num(fila.iloc[27])
                
                # Buscar signo (1 = Factura, -1 = Nota de Crédito)
                info = tipos[tipos['codigo'] == cod_tipo]
                signo = info['signo'].values[0] if not info.empty else 1
                desc = info['descripcion'].values[0] if not info.empty else "COMP."
                
                glosa = f"{desc} {nro_comp} - {cliente}"

                # REGISTRO POR PARTIDA DOBLE INDIVIDUAL
                if signo == 1:
                    # FACTURAS: Activo (Debe) contra Ingreso e IVA (Haber)
                    registrar_linea(asiento_actual, f, "DEUDORES", total, 0, glosa)
                    registrar_linea(asiento_actual, f, "VENTAS", 0, neto, glosa)
                    if iva > 0:
                        registrar_linea(asiento_actual, f, "IVA DF", 0, iva, glosa)
                else:
                    # NOTAS DE CRÉDITO: Reversa del asiento
                    registrar_linea(asiento_actual, f, "VENTAS", neto, 0, glosa)
                    if iva > 0:
                        registrar_linea(asiento_actual, f, "IVA DF", iva, 0, glosa)
                    registrar_linea(asiento_actual, f, "DEUDORES", 0, total, glosa)
                
                asiento_actual += 1 # Saltamos al siguiente asiento para el próximo comprobante
            
            st.success(f"✅ Se generaron {asiento_actual - prox_asiento} asientos individuales.")

def registrar_linea(asiento, fecha, cuenta_keyword, debe, haber, glosa):
    """Busca la cuenta real en el PDC y graba la línea del asiento"""
    pdc = ejecutar_query("SELECT nombre FROM plan_cuentas", fetch=True)['nombre'].tolist()
    cuenta_real = next((c for c in pdc if cuenta_keyword in c), cuenta_keyword)
    
    query = """INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) 
               VALUES (?, ?, ?, ?, ?, ?)"""
    ejecutar_query(query, (asiento, fecha, cuenta_real, debe, haber, glosa))

def limpiar_num(v):
    try: return float(str(v).replace('.', '').replace(',', '.'))
    except: return 0.0