import streamlit as st
import pandas as pd
from database import ejecutar_query

def obtener_cuenta_inteligente(concepto, cuenta_defecto):
    """Busca si el usuario ya asignó una cuenta específica para este concepto."""
    res = ejecutar_query("SELECT cuenta_asignada FROM mapeo_cuentas WHERE concepto = ?", (concepto,), fetch=True)
    if not res.empty:
        return res.iloc[0]['cuenta_asignada']
    return cuenta_defecto

def mostrar_ventas():
    st.title("📂 Carga de Ventas Inteligente")
    
    # --- INTERFAZ DE APRENDIZAJE ---
    with st.expander("🧠 Memoria del Sistema (Mapeo de Cuentas)"):
        st.write("Aquí puedes ver qué cuentas ha aprendido el sistema.")
        mapeos = ejecutar_query("SELECT * FROM mapeo_cuentas", fetch=True)
        st.dataframe(mapeos, use_container_width=True)
        if st.button("Limpiar Memoria"):
            ejecutar_query("DELETE FROM mapeo_cuentas")
            st.rerun()

    archivo = st.file_uploader("Subir Ventas ARCA", type=["csv"])
    
    if archivo:
        df = pd.read_csv(archivo, sep=';', encoding='latin-1')
        tipos = ejecutar_query("SELECT * FROM tipos_comprobantes", fetch=True)
        pdc = ejecutar_query("SELECT nombre FROM plan_cuentas", fetch=True)['nombre'].tolist()

        if st.button("🚀 Pre-visualizar Asientos"):
            # Usamos un estado de sesión para permitir correcciones antes de grabar
            registros_temp = []
            
            for _, fila in df.iterrows():
                f = fila.iloc[0]
                nro = fila.iloc[2]
                cliente = fila.iloc[8]
                neto = round(float(str(fila.iloc[22]).replace('.','').replace(',','.')), 2)
                iva = round(float(str(fila.iloc[26]).replace('.','').replace(',','.')), 2)
                total = round(float(str(fila.iloc[27]).replace('.','').replace(',','.')), 2)
                
                # Buscamos cuentas aprendidas o defectos
                cta_v = obtener_cuenta_inteligente("VENTAS", "VENTAS")
                cta_d = obtener_cuenta_inteligente("DEUDORES", "DEUDORES POR VENTAS")
                
                # Lógica de Partida Doble
                if round(neto + iva, 2) != total:
                    neto = round(total - iva, 2) # Ajuste automático

                registros_temp.append({
                    "Fecha": f, "Comprobante": nro, "Cliente": cliente,
                    "Cuenta_D": cta_d, "Cuenta_V": cta_v,
                    "Neto": neto, "IVA": iva, "Total": total
                })
            
            st.session_state['temp_ventas'] = registros_temp

        if 'temp_ventas' in st.session_state:
            st.subheader("📝 Revisión y Corrección Manual")
            for i, reg in enumerate(st.session_state['temp_ventas']):
                with st.expander(f"Asiento: {reg['Comprobante']} - {reg['Cliente']}"):
                    col1, col2 = st.columns(2)
                    nueva_d = col1.selectbox(f"Cuenta Deudores ({i})", pdc, index=pdc.index(reg['Cuenta_D']) if reg['Cuenta_D'] in pdc else 0)
                    nueva_v = col2.selectbox(f"Cuenta Ventas ({i})", pdc, index=pdc.index(reg['Cuenta_V']) if reg['Cuenta_V'] in pdc else 0)
                    
                    # Si el usuario cambia la cuenta, la aprendemos
                    if nueva_d != reg['Cuenta_D']:
                        ejecutar_query("INSERT OR REPLACE INTO mapeo_cuentas VALUES (?,?)", ("DEUDORES", nueva_d))
                    if nueva_v != reg['Cuenta_V']:
                        ejecutar_query("INSERT OR REPLACE INTO mapeo_cuentas VALUES (?,?)", ("VENTAS", nueva_v))

            if st.button("✅ Confirmar y Grabar en Diario"):
                res_a = ejecutar_query("SELECT MAX(id_asiento) as u FROM libro_diario", fetch=True)
                asiento_id = (int(res_a.iloc[0]['u']) if not res_a.empty and pd.notna(res_a.iloc[0]['u']) else 0) + 1
                
                for reg in st.session_state['temp_ventas']:
                    glosa = f"Venta {reg['Comprobante']} - {reg['Cliente']}"
                    # Línea Deudores
                    ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", 
                                   (asiento_id, reg['Fecha'], reg['Cuenta_D'], reg['Total'], 0, glosa))
                    # Línea Ventas
                    ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", 
                                   (asiento_id, reg['Fecha'], reg['Cuenta_V'], 0, reg['Neto'], glosa))
                    # Línea IVA (Solo si existe)
                    if reg['IVA'] > 0:
                        ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", 
                                       (asiento_id, reg['Fecha'], "IVA DF", 0, reg['IVA'], glosa))
                    asiento_id += 1
                
                st.success("Asientos grabados con éxito.")
                del st.session_state['temp_ventas']