import streamlit as st
import pandas as pd
import sys
import os

# Asegurar que encuentre la raíz del proyecto para database.py
ruta_raiz = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ruta_raiz not in sys.path:
    sys.path.append(ruta_raiz)

from database import ejecutar_query, registrar_carga

def limpiar_num(v):
    if pd.isna(v) or v == "": return 0.0
    try: return round(float(str(v).replace('.', '').replace(',', '.')), 2)
    except: return 0.0

def mostrar_ventas():
    st.title("📂 Procesamiento de Ventas")
    archivo = st.file_uploader("Subir CSV de ARCA", type=["csv"])
    
    if archivo:
        # 1. Carga de datos base
        pdc_df = ejecutar_query("SELECT nombre FROM plan_cuentas", fetch=True)
        pdc = pdc_df['nombre'].tolist() if not pdc_df.empty else ["VENTAS", "DEUDORES POR VENTAS"]
        tipos = ejecutar_query("SELECT * FROM tipos_comprobantes", fetch=True)
        
        df_csv = pd.read_csv(archivo, sep=';', encoding='latin-1')

        # 2. Análisis del archivo
        if st.button("🔍 Analizar Archivo"):
            auto, revision = [], []
            for _, f in df_csv.iterrows():
                t, i, n = limpiar_num(f.iloc[27]), limpiar_num(f.iloc[26]), limpiar_num(f.iloc[22])
                
                # Datos estructurados (Fecha forzada DD/MM/YYYY)
                datos = {
                    "fecha": str(f.iloc[0]), 
                    "comprobante": str(f.iloc[2]), 
                    "cliente": str(f.iloc[8]), 
                    "cod_arca": int(f.iloc[1]), 
                    "neto": n if i > 0 else t, 
                    "iva": i, 
                    "total": t,
                    "cta_d": "DEUDORES POR VENTAS", 
                    "cta_v": "VENTAS"
                }
                
                if i == 0:
                    revision.append(datos)
                else:
                    auto.append(datos)
            
            st.session_state['v_auto'] = auto
            st.session_state['v_rev'] = revision
            st.session_state['analizado'] = True

        # 3. Mostrar resultados y validación si es necesario
        if st.session_state.get('analizado'):
            hay_exentas = len(st.session_state.get('v_rev', [])) > 0
            
            if hay_exentas:
                st.warning(f"⚠️ Se detectaron {len(st.session_state['v_rev'])} operaciones SIN IVA. Verifique las cuentas:")
                for idx, asis in enumerate(st.session_state['v_rev']):
                    with st.expander(f"Validar: {asis['comprobante']} - {asis['cliente']}"):
                        c1, c2 = st.columns(2)
                        asis['cta_d'] = c1.selectbox("Cuenta Debe", pdc, index=pdc.index(asis['cta_d']) if asis['cta_d'] in pdc else 0, key=f"d_{idx}")
                        asis['cta_v'] = c2.selectbox("Cuenta Haber", pdc, index=pdc.index(asis['cta_v']) if asis['cta_v'] in pdc else 0, key=f"h_{idx}")
            else:
                st.success("✅ Todas las operaciones tienen IVA. Listo para grabar.")

            # 4. Botón Grabar (Funciona para ambos casos)
            if st.button("💾 Grabar en Libro Diario"):
                res_u = ejecutar_query("SELECT MAX(id_asiento) as u FROM libro_diario", fetch=True)
                prox_id = (int(res_u.iloc[0]['u']) if not res_u.empty and pd.notna(res_u.iloc[0]['u']) else 0) + 1
                
                todo = st.session_state['v_auto'] + st.session_state['v_rev']
                
                for a in todo:
                    t_info = tipos[tipos['codigo'] == a['cod_arca']] if not tipos.empty else pd.DataFrame()
                    s = t_info['signo'].values[0] if not t_info.empty else 1
                    glo = f"Venta {a['comprobante']} - {a['cliente']}"
                    
                    if s == 1: # Facturas / Notas de Débito
                        ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (prox_id, a['fecha'], a['cta_d'], a['total'], 0, glo))
                        if a['neto'] > 0: ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (prox_id, a['fecha'], a['cta_v'], 0, a['neto'], glo))
                        if a['iva'] > 0: ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (prox_id, a['fecha'], "IVA DF", 0, a['iva'], glo))
                    else: # Notas de Crédito
                        ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (prox_id, a['fecha'], a['cta_v'], a['neto'], 0, glo))
                        if a['iva'] > 0: ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (prox_id, a['fecha'], "IVA DF", a['iva'], 0, glo))
                        ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (prox_id, a['fecha'], a['cta_d'], 0, a['total'], glo))
                    prox_id += 1
                
                registrar_carga("Ventas", archivo.name, len(todo))
                st.success(f"🔥 Se grabaron {len(todo)} asientos correctamente.")
                # Limpiar estado para nueva carga
                for key in ['v_auto', 'v_rev', 'analizado']:
                    if key in st.session_state: del st.session_state[key]
                st.rerun()