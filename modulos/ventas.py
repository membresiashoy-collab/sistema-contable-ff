import streamlit as st
import pandas as pd
import database

def mostrar_ventas():
    st.title("📤 Módulo de Ventas")
    
    # Botón de emergencia para asegurar que la tabla existe
    if st.button("🔄 Inicializar/Limpiar Sistema"):
        database.init_db()
        st.success("Sistema listo para recibir datos.")

    archivo = st.file_uploader("Subir CSV de AFIP", type=["csv"])
    
    if archivo:
        try:
            # Leemos el archivo asegurando que reconozca los separadores
            df = pd.read_csv(archivo, sep=None, engine='python', encoding='latin-1')
            df.columns = [c.strip().upper() for c in df.columns]
            
            # Identificamos columnas
            c_f = next(c for c in df.columns if "FECHA" in c)
            c_t = next(c for c in df.columns if "TIPO" in c and "COMPROBANTE" in c)
            c_tot = next(c for c in df.columns if "TOTAL" in c and "IVA" not in c)
            c_iva = next((c for c in df.columns if "TOTAL IVA" in c or "IVA 21%" in c), None)

            if st.button("🚀 Procesar y Generar Asientos"):
                # Buscamos el último asiento para no repetir
                res = database.ejecutar_query("SELECT MAX(id_asiento) FROM libro_diario", fetch=True)
                n_asiento = 1 if res.empty or res.iloc[0,0] is None else int(res.iloc[0,0]) + 1
                
                contador_exitos = 0
                for _, r in df.iterrows():
                    try:
                        f, t = r[c_f], str(r[c_t])
                        total = float(str(r[c_tot]).replace(',', '.'))
                        
                        # Cálculo de IVA (si no hay, es 0)
                        iva = 0
                        if c_iva and pd.notnull(r[c_iva]):
                            try: iva = float(str(r[c_iva]).replace(',', '.'))
                            except: iva = 0
                        
                        neto = total - iva # Si iva es 0, neto = total

                        # --- INSERCIÓN EN LIBRO DIARIO ---
                        # 1. DEUDORES POR VENTAS al DEBE
                        database.ejecutar_query(
                            "INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (n_asiento, f, "DEUDORES POR VENTAS", total, 0, f"Venta {t}", "VENTAS")
                        )
                        # 2. VENTAS al HABER
                        database.ejecutar_query(
                            "INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (n_asiento, f, "VENTAS", 0, neto, f"Venta {t}", "VENTAS")
                        )
                        # 3. IVA al HABER (Solo si es > 0)
                        if iva > 0:
                            database.ejecutar_query(
                                "INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?, ?, ?, ?, ?, ?, ?)",
                                (n_asiento, f, "IVA DEBITO FISCAL", 0, iva, f"Venta {t}", "VENTAS")
                            )
                        
                        n_asiento += 1
                        contador_exitos += 1
                    except:
                        continue
                
                if contador_exitos > 0:
                    st.success(f"✅ Se generaron {contador_exitos} asientos correctamente.")
                else:
                    st.error("No se pudo procesar ningún registro. Verificá el formato del CSV.")
                    
        except Exception as e:
            st.error(f"Error crítico al leer el archivo: {e}")