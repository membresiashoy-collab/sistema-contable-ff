with tab2:
        st.subheader("🔍 Libro Mayor")
        cuentas_query = "SELECT DISTINCT cuenta FROM libro_diario"
        cuentas = ejecutar_query(cuentas_query, fetch=True)
        
        if not cuentas.empty:
            cuenta_sel = st.selectbox("Seleccione una cuenta:", cuentas['cuenta'])
            mayor = ejecutar_query("SELECT fecha, glosa, debe, haber FROM libro_diario WHERE cuenta = ?", (cuenta_sel,), fetch=True)
            st.table(mayor)
            
            total_debe = mayor['debe'].sum()
            total_haber = mayor['haber'].sum()
            saldo = total_debe - total_haber
            
            col1, col2 = st.columns(2)
            # AQUÍ ESTABA EL ERROR: ahora tiene la 'f' de float
            col1.metric("Total Debe", f"$ {total_debe:,.2f}")
            col2.metric("Saldo Actual", f"$ {saldo:,.2f}")
        else:
            st.info("No hay movimientos para mostrar.")