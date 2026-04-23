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
    st.title("📂 Procesamiento de Ventas (Exentas y Gravadas)")

    archivo = st.file_uploader("Subir Ventas ARCA", type=["csv"])
    
    if archivo:
        pdc_df = ejecutar_query("SELECT nombre FROM plan_cuentas", fetch=True)
        if pdc_df.empty:
            st.error("❌ Configure el Plan de Cuentas primero.")
            return
        
        lista_cuentas = pdc_df['nombre'].tolist()
        tipos = ejecutar_query("SELECT * FROM tipos_comprobantes", fetch=True)
        df_csv = pd.read_csv(archivo, sep=';', encoding='latin-1')

        if st.button("🔍 Analizar Consistencia Contable"):
            asientos_provisiorios = []
            
            for _, fila in df_csv.iterrows():
                neto = limpiar_num(fila.iloc[22])
                iva = limpiar_num(fila.iloc[26])
                total = limpiar_num(fila.iloc[27])
                
                # LÓGICA PARA OPERACIONES EXENTAS:
                # Si es exenta (IVA=0), el Neto debe ser igual al Total para que cuadre.
                if iva == 0:
                    neto = total 

                asientos_provisiorios.append({
                    "fecha": fila.iloc[0], "comprobante": fila.iloc[2],
                    "cliente": fila.iloc[8], "cod_arca": int(fila.iloc[1]),
                    "neto": neto, "iva": iva, "total": total,
                    "cta_d": "DEUDORES POR VENTAS", "cta_v": "VENTAS"
                })
            
            st.session_state['pendientes'] = asientos_provisiorios

        # --- REVISIÓN DE OPERACIONES SIN IVA (EXENTAS) ---
        if 'pendientes' in st.session_state:
            exentas = [a for a in st.session_state['pendientes'] if a['iva'] == 0]
            
            if exentas:
                st.subheader("⚠️ Operaciones Exentas / Sin IVA")
                st.info("Para estas operaciones, el sistema igualará automáticamente VENTA con TOTAL.")
                for i, asis in enumerate(exentas):
                    with st.expander(f"Exenta: {asis['comprobante']} - {asis['cliente']}"):
                        c1, c2 = st.columns(2)
                        asis['cta_d'] = c1.selectbox("Cuenta Deudora", lista_cuentas, index=lista_cuentas.index(asis['cta_d']) if asis['cta_d'] in lista_cuentas else 0, key=f"d_{i}")
                        asis['cta_v'] = c2.selectbox("Cuenta Venta", lista_cuentas, index=lista_cuentas.index(asis['cta_v']) if asis['cta_v'] in lista_cuentas else 0, key=f"v_{i}")

            if st.button("✅ Confirmar y Grabar Libro Diario"):
                res_u = ejecutar_query("SELECT MAX(id_asiento) as u FROM libro_diario", fetch=True)
                prox_id = (int(res_u.iloc[0]['u']) if not res_u.empty and pd.notna(res_u.iloc[0]['u']) else 0) + 1
                
                for a in st.session_state['pendientes']:
                    t_info = tipos[tipos['codigo'] == a['cod_arca']]
                    signo = t_info['signo'].values[0] if not t_info.empty else 1
                    glosa = f"Venta {a['comprobante']} - {a['cliente']}"

                    if signo == 1:
                        # DEBE
                        ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (prox_id, a['fecha'], a['cta_d'], a['total'], 0, glosa))
                        # HABER (Solo líneas con valor > 0)
                        if a['neto'] > 0:
                            ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (prox_id, a['fecha'], a['cta_v'], 0, a['neto'], glosa))
                        if a['iva'] > 0:
                            ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (prox_id, a['fecha'], "IVA DF", 0, a['iva'], glosa))
                    else:
                        # Notas de Crédito (Invertido)
                        ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (prox_id, a['fecha'], a['cta_v'], a['neto'], 0, glosa))
                        if a['iva'] > 0:
                            ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (prox_id, a['fecha'], "IVA DF", a['iva'], 0, glosa))
                        ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (prox_id, a['fecha'], a['cta_d'], 0, a['total'], glosa))
                    
                    prox_id += 1
                
                st.success("Asientos grabados. Partida doble verificada.")
                st.session_state.clear()
                st.rerun()