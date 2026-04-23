import streamlit as st
import pandas as pd
from database import ejecutar_query

def limpiar_num(v):
    if pd.isna(v) or v == "": return 0.0
    try:
        s = str(v).replace('.', '').replace(',', '.')
        return round(float(s), 2)
    except:
        return 0.0

def mostrar_ventas():
    st.title("📂 Procesamiento Inteligente de Ventas")

    archivo = st.file_uploader("Subir Ventas ARCA", type=["csv"])
    
    if archivo:
        pdc_df = ejecutar_query("SELECT nombre FROM plan_cuentas", fetch=True)
        if pdc_df.empty:
            st.error("❌ Carga el Plan de Cuentas en Configuración primero.")
            return
        
        lista_cuentas = pdc_df['nombre'].tolist()
        tipos = ejecutar_query("SELECT * FROM tipos_comprobantes", fetch=True)
        df_csv = pd.read_csv(archivo, sep=';', encoding='latin-1')

        if st.button("🔍 Analizar Lógica Contable"):
            automáticos = []
            para_revision = []
            
            for _, fila in df_csv.iterrows():
                neto = limpiar_num(fila.iloc[22])
                iva = limpiar_num(fila.iloc[26])
                total = limpiar_num(fila.iloc[27])
                
                datos = {
                    "fecha": fila.iloc[0], "comprobante": fila.iloc[2],
                    "cliente": fila.iloc[8], "cod_arca": int(fila.iloc[1]),
                    "neto": neto, "iva": iva, "total": total,
                    "cta_d": "DEUDORES POR VENTAS", "cta_v": "VENTAS"
                }

                # CRITERIO DE EXCEPCIÓN:
                # Si no hay IVA o si la suma no es exacta, va a REVISIÓN
                if iva == 0 or round(neto + iva, 2) != total:
                    para_revision.append(datos)
                else:
                    automáticos.append(datos)
            
            st.session_state['asientos_auto'] = automáticos
            st.session_state['asientos_manual'] = para_revision

        # --- SECCIÓN 1: OPERACIONES ESPECIALES (REVISIÓN) ---
        if 'asientos_manual' in st.session_state and st.session_state['asientos_manual']:
            st.subheader("⚠️ Operaciones sin IVA o Especiales (Requieren Revisión)")
            
            for i, asis in enumerate(st.session_state['asientos_manual']):
                with st.expander(f"Revisar: {asis['comprobante']} - {asis['cliente']}", expanded=True):
                    col1, col2 = st.columns(2)
                    # Aquí podés elegir "CREDITOS POR VENTAS" o cualquier otra
                    asis['cta_d'] = col1.selectbox("Cuenta Deudora", lista_cuentas, key=f"md_{i}")
                    asis['cta_v'] = col2.selectbox("Cuenta Venta/Ingreso", lista_cuentas, key=f"mv_{i}")
                    st.caption(f"Total: {asis['total']} | Neto: {asis['neto']} | IVA: {asis['iva']}")

        # --- SECCIÓN 2: CONFIRMACIÓN FINAL ---
        if 'asientos_auto' in st.session_state:
            total_asientos = len(st.session_state.get('asientos_auto', [])) + len(st.session_state.get('asientos_manual', []))
            
            if st.button(f"✅ Procesar {total_asientos} Asientos"):
                res_u = ejecutar_query("SELECT MAX(id_asiento) as u FROM libro_diario", fetch=True)
                prox_id = (int(res_u.iloc[0]['u']) if not res_u.empty and pd.notna(res_u.iloc[0]['u']) else 0) + 1
                
                todos = st.session_state['asientos_auto'] + st.session_state['asientos_manual']
                
                for a in todos:
                    t_info = tipos[tipos['codigo'] == a['cod_arca']]
                    signo = t_info['signo'].values[0] if not t_info.empty else 1
                    glosa = f"Venta {a['comprobante']} - {a['cliente']}"

                    if signo == 1:
                        ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (prox_id, a['fecha'], a['cta_d'], a['total'], 0, glosa))
                        ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (prox_id, a['fecha'], a['cta_v'], 0, a['neto'], glosa))
                        if a['iva'] > 0:
                            ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (prox_id, a['fecha'], "IVA DF", 0, a['iva'], glosa))
                    else:
                        # Lógica para Notas de Crédito
                        ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (prox_id, a['fecha'], a['cta_v'], a['neto'], 0, glosa))
                        if a['iva'] > 0:
                            ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (prox_id, a['fecha'], "IVA DF", a['iva'], 0, glosa))
                        ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (prox_id, a['fecha'], a['cta_d'], 0, a['total'], glosa))
                    
                    prox_id += 1
                
                st.success("¡Asientos grabados!")
                st.session_state.clear()
                st.rerun()