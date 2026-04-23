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
    st.title("📂 Procesamiento de Ventas con Validación")

    # 1. Carga de archivos
    archivo = st.file_uploader("Subir Ventas ARCA", type=["csv"])
    
    if archivo:
        # Obtenemos Plan de Cuentas y Mapeos guardados
        pdc_df = ejecutar_query("SELECT nombre FROM plan_cuentas", fetch=True)
        if pdc_df.empty:
            st.error("❌ No hay Plan de Cuentas. Cárguelo en Configuración.")
            return
        
        lista_cuentas = pdc_df['nombre'].tolist()
        tipos = ejecutar_query("SELECT * FROM tipos_comprobantes", fetch=True)
        
        df_csv = pd.read_csv(archivo, sep=';', encoding='latin-1')

        # --- ETAPA DE PREPARACIÓN ---
        if st.button("🔍 Analizar y Validar Asientos"):
            asientos_previa = []
            for _, fila in df_csv.iterrows():
                neto = limpiar_num(fila.iloc[22])
                iva = limpiar_num(fila.iloc[26])
                total = limpiar_num(fila.iloc[27])
                
                # Ajuste automático de partida doble si hay error de centavos
                if round(neto + iva, 2) != total:
                    neto = round(total - iva, 2)

                asientos_previa.append({
                    "fecha": fila.iloc[0],
                    "comprobante": fila.iloc[2],
                    "cliente": fila.iloc[8],
                    "cod_arca": int(fila.iloc[1]),
                    "neto": neto,
                    "iva": iva,
                    "total": total,
                    "cta_deudores": "DEUDORES POR VENTAS", # Valor por defecto
                    "cta_ventas": "VENTAS" # Valor por defecto
                })
            st.session_state['asientos_pendientes'] = asientos_previa

        # --- ETAPA DE EDICIÓN MANUAL (Aquí está el botón/desplegable que faltaba) ---
        if 'asientos_pendientes' in st.session_state:
            st.subheader("📝 Revisión de Partida Doble")
            st.warning("Verifique las cuentas y montos antes de confirmar.")
            
            asientos_finales = []
            
            for i, asis in enumerate(st.session_state['asientos_pendientes']):
                with st.expander(f"Asiento {asis['comprobante']} - {asis['cliente']}", expanded=False):
                    col1, col2, col3 = st.columns(3)
                    
                    # Desplegables para cambiar cuentas manualmente
                    # Intentamos pre-seleccionar la cuenta si existe en el PDC
                    idx_d = lista_cuentas.index(asis['cta_deudores']) if asis['cta_deudores'] in lista_cuentas else 0
                    idx_v = lista_cuentas.index(asis['cta_ventas']) if asis['cta_ventas'] in lista_cuentas else 0
                    
                    c_deudores = col1.selectbox(f"Cuenta Deudores", lista_cuentas, index=idx_d, key=f"d_{i}")
                    c_ventas = col2.selectbox(f"Cuenta Ventas", lista_cuentas, index=idx_v, key=f"v_{i}")
                    
                    # Verificación visual de partida doble
                    suma_debe = asis['total']
                    suma_haber = round(asis['neto'] + asis['iva'], 2)
                    
                    col3.metric("Balance", f"$ {suma_debe}", delta=f"Haber: {suma_haber}")
                    
                    if suma_debe != suma_haber:
                        st.error("⚠️ Este asiento NO CUADRA. Revise los importes.")
                    
                    # Guardamos la elección del usuario
                    asientos_finales.append({**asis, "cta_deudores": c_deudores, "cta_ventas": c_ventas})

            # --- ETAPA DE GRABACIÓN FINAL ---
            if st.button("✅ Confirmar y Grabar Todo en el Libro Diario"):
                res_u = ejecutar_query("SELECT MAX(id_asiento) as u FROM libro_diario", fetch=True)
                prox_id = (int(res_u.iloc[0]['u']) if not res_u.empty and pd.notna(res_u.iloc[0]['u']) else 0) + 1
                
                for a in asientos_finales:
                    glosa = f"Venta {a['comprobante']} - {a['cliente']}"
                    
                    # Determinar signo (Factura vs Nota de Crédito)
                    t_info = tipos[tipos['codigo'] == a['cod_arca']]
                    signo = t_info['signo'].values[0] if not t_info.empty else 1
                    
                    if signo == 1:
                        # DEUDORES (Debe) contra VENTAS e IVA (Haber)
                        ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (prox_id, a['fecha'], a['cta_deudores'], a['total'], 0, glosa))
                        ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (prox_id, a['fecha'], a['cta_ventas'], 0, a['neto'], glosa))
                        if a['iva'] > 0:
                            ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (prox_id, a['fecha'], "IVA DF", 0, a['iva'], glosa))
                    else:
                        # NOTA DE CRÉDITO (Inverso)
                        ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (prox_id, a['fecha'], a['cta_ventas'], a['neto'], 0, glosa))
                        if a['iva'] > 0:
                            ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (prox_id, a['fecha'], "IVA DF", a['iva'], 0, glosa))
                        ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (prox_id, a['fecha'], a['cta_deudores'], 0, a['total'], glosa))
                    
                    prox_id += 1
                
                st.success(f"✅ {len(asientos_finales)} asientos grabados correctamente.")
                del st.session_state['asientos_pendientes']
                st.balloons()