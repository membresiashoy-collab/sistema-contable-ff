# --- SECCIÓN 2: TABLA DE COMPROBANTES (ARCA) ---
    st.subheader("2. Tabla de Comprobantes (ARCA)")
    archivo_tipos = st.file_uploader("Subir TABLACOMPROBANTES.csv", type=["csv"], key="tipos")
    
    if archivo_tipos:
        try:
            # 1. Leemos el archivo completo como texto para tener control total
            raw_data = archivo_tipos.read().decode('latin-1')
            lineas = raw_data.splitlines()
            
            datos_validos = []
            for linea in lineas:
                # Limpiamos espacios y separamos por coma
                partes = [p.strip() for p in linea.split(',')]
                
                # REGLA DE FILTRADO: 
                # Solo aceptamos líneas donde el primer elemento sea un número (Código)
                # y el segundo elemento tenga texto (Descripción)
                if len(partes) >= 2:
                    try:
                        codigo_limpio = float(partes[0])
                        descripcion_limpia = partes[1]
                        if descripcion_limpia != "":
                            datos_validos.append({
                                "Código": int(codigo_limpio),
                                "Descripción": descripcion_limpia
                            })
                    except ValueError:
                        continue # Si no es número, es un encabezado o basura, lo ignoramos

            # 2. Creamos el DataFrame desde nuestra lista limpia
            df_tipos = pd.DataFrame(datos_validos)
            
            st.write("### ✅ Tabla detectada y purificada:")
            st.dataframe(df_tipos)
            
            if st.button("Confirmar y Cargar Lógica"):
                ejecutar_query("DELETE FROM tipos_comprobantes")
                for _, fila in df_tipos.iterrows():
                    desc = str(fila['Descripción']).upper()
                    # Definimos el signo contable
                    signo = -1 if "NOTA DE CREDITO" in desc or "NOTA DE CRÉDITO" in desc else 1
                    ejecutar_query("INSERT INTO tipos_comprobantes VALUES (?, ?, ?)", 
                                   (int(fila['Código']), desc, signo))
                st.success(f"Se cargaron {len(df_tipos)} comprobantes correctamente.")
                
        except Exception as e:
            st.error(f"Error al procesar el archivo: {e}")