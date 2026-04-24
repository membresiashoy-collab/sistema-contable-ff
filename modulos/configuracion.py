import streamlit as st
from database import ejecutar_query


def mostrar_configuracion():
    st.title("⚙️ Configuración")

    tab1, tab2 = st.tabs(["Tipos de Comprobantes", "Plan de Cuentas"])

    # ==============================
    # TAB 1 - COMPROBANTES
    # ==============================
    with tab1:
        st.subheader("Tipos de Comprobantes")

        df = ejecutar_query("""
            SELECT *
            FROM tipos_comprobantes
            ORDER BY codigo
        """, fetch=True)

        if df.empty:
            st.info("Sin datos cargados.")
        else:
            st.dataframe(df, use_container_width=True)

        st.divider()

        st.subheader("Agregar / Actualizar comprobante")

        col1, col2, col3 = st.columns(3)

        with col1:
            codigo = st.text_input("Código")

        with col2:
            descripcion = st.text_input("Descripción")

        with col3:
            signo = st.selectbox("Signo", [1, -1])

        col1, col2 = st.columns(2)

        with col1:
            if st.button("Guardar comprobante"):
                if codigo == "" or descripcion == "":
                    st.warning("Completar todos los campos")
                else:
                    ejecutar_query("""
                        INSERT OR REPLACE INTO tipos_comprobantes
                        (codigo, descripcion, signo)
                        VALUES (?, ?, ?)
                    """, (codigo.strip(), descripcion.strip(), signo))

                    st.success("Comprobante guardado")
                    st.rerun()

        with col2:
            if st.button("Eliminar comprobante"):
                ejecutar_query("""
                    DELETE FROM tipos_comprobantes
                    WHERE codigo = ?
                """, (codigo.strip(),))

                st.success("Comprobante eliminado")
                st.rerun()

    # ==============================
    # TAB 2 - PLAN DE CUENTAS
    # ==============================
    with tab2:
        st.subheader("Plan de Cuentas")

        df2 = ejecutar_query("""
            SELECT *
            FROM plan_cuentas
            ORDER BY codigo
        """, fetch=True)

        if df2.empty:
            st.info("Sin plan cargado.")
        else:
            st.dataframe(df2, use_container_width=True)

        st.divider()

        st.subheader("Agregar / Actualizar cuenta")

        col1, col2 = st.columns(2)

        with col1:
            codigo_cuenta = st.text_input("Código cuenta")

        with col2:
            nombre_cuenta = st.text_input("Nombre cuenta")

        col1, col2 = st.columns(2)

        with col1:
            if st.button("Guardar cuenta"):
                if codigo_cuenta == "" or nombre_cuenta == "":
                    st.warning("Completar todos los campos")
                else:
                    ejecutar_query("""
                        INSERT INTO plan_cuentas (codigo, nombre)
                        VALUES (?, ?)
                    """, (codigo_cuenta.strip(), nombre_cuenta.strip()))

                    st.success("Cuenta guardada")
                    st.rerun()

        with col2:
            if st.button("Eliminar cuenta"):
                ejecutar_query("""
                    DELETE FROM plan_cuentas
                    WHERE codigo = ?
                """, (codigo_cuenta.strip(),))

                st.success("Cuenta eliminada")
                st.rerun()