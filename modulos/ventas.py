import streamlit as st
import pandas as pd
from database import ejecutar_query, registrar_carga

def limpiar_num(v):
    if pd.isna(v) or v == "": return 0.0
    try:
        s = str(v).replace('.', '').replace(',', '.')
        return round(float(s), 2)
    except: return 0.0

def mostrar_ventas():
    st.title("📂 Carga de Ventas")
    archivo = st.file_uploader("Subir CSV de ARCA", type=["csv"])
    
    if archivo:
        tipos = ejecutar_query("SELECT * FROM tipos_comprobantes", fetch=True)
        df_csv = pd.read_csv(archivo, sep=';', encoding='latin-1')

        if st.button("🔍 Analizar Archivo"):
            asientos_lista = []
            for _, fila in df_csv.iterrows():
                total = limpiar_num(fila.iloc[27])
                iva = limpiar_num(fila.iloc[26])
                neto = total if iva == 0 else limpiar_num(fila.iloc[22])

                asientos_lista.append({
                    "fecha": fila.iloc[0], # Formato DD/MM/YYYY del CSV
                    "comprobante": fila.iloc[2],
                    "cliente": fila.iloc[8],
                    "cod_arca": int(fila.iloc[1]),
                    "neto": neto, "iva": iva, "total": total,
                    "cta_d": "DEUDORES POR VENTAS",
                    "cta_v": "VENTAS" # Cambio de cuenta solicitado
                })
            st.session_state['pendientes'] = asientos_lista

        if 'pendientes' in st.session_state:
            if st.button(f"✅ Procesar {len(st.session_state['pendientes'])} Facturas"):
                res_u = ejecutar_query("SELECT MAX(id_asiento) as u FROM libro_diario", fetch=True)
                prox_id = (int(res_u.iloc[0]['u']) if not res_u.empty and pd.notna(res_u.iloc[0]['u']) else 0) + 1
                
                for a in st.session_state['pendientes']:
                    t_info = tipos[tipos['codigo'] == a['cod_arca']]
                    signo = t_info['signo'].values[0] if not t_info.empty else 1
                    glosa = f"Venta {a['comprobante']} - {a['cliente']}"

                    if signo == 1:
                        ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (prox_id, a['fecha'], a['cta_d'], a['total'], 0, glosa))
                        if a['neto'] > 0: ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (prox_id, a['fecha'], a['cta_v'], 0, a['neto'], glosa))
                        if a['iva'] > 0: ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (prox_id, a['fecha'], "IVA DF", 0, a['iva'], glosa))
                    else:
                        # Notas de Crédito
                        ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (prox_id, a['fecha'], a['cta_v'], a['neto'], 0, glosa))
                        if a['iva'] > 0: ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (prox_id, a['fecha'], "IVA DF", a['iva'], 0, glosa))
                        ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (prox_id, a['fecha'], a['cta_d'], 0, a['total'], glosa))
                    prox_id += 1
                
                registrar_carga("Ventas", archivo.name, len(st.session_state['pendientes']))
                st.success("Diario actualizado correctamente.")
                st.session_state.clear()
                st.rerun()