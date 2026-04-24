import streamlit as st


def mostrar_iva():
    st.title("🧾 IVA")

    st.info(
        "Este módulo estará destinado a controlar la posición mensual de IVA "
        "por empresa, tomando información desde Ventas, Compras, percepciones, "
        "retenciones y otros conceptos fiscales."
    )

    tab1, tab2, tab3, tab4 = st.tabs([
        "Posición IVA",
        "Libro IVA Ventas",
        "Libro IVA Compras",
        "Portal IVA / Exportación"
    ])

    with tab1:
        st.subheader("Posición mensual de IVA")

        st.warning(
            "Módulo pendiente de desarrollo. "
            "Primero debemos reconstruir la configuración base y consolidar Compras PRO."
        )

        st.markdown("""
        Este módulo debería mostrar:

        - IVA Débito Fiscal de ventas
        - IVA Crédito Fiscal de compras
        - Percepciones de IVA
        - Retenciones sufridas
        - Saldo técnico
        - Saldo de libre disponibilidad, si correspondiera
        - Posición mensual por empresa
        """)

    with tab2:
        st.subheader("Libro IVA Ventas")

        st.info(
            "El Libro IVA Ventas se alimentará desde el módulo Ventas. "
            "Actualmente la información se consulta desde Ventas → Libro IVA Ventas."
        )

    with tab3:
        st.subheader("Libro IVA Compras")

        st.info(
            "El Libro IVA Compras se alimentará desde el módulo Compras. "
            "Debe contemplar crédito fiscal computable, percepciones, impuestos internos "
            "y otros tributos."
        )

    with tab4:
        st.subheader("Portal IVA / Exportación")

        st.info(
            "Más adelante este módulo preparará reportes y archivos de trabajo "
            "para Portal IVA / Libro IVA Digital, según la estructura que definamos."
        )


# Alias de compatibilidad por si main.py llama con otro nombre
def mostrar_modulo_iva():
    mostrar_iva()