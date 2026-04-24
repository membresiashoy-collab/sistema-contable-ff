import streamlit as st
import pandas as pd

from database import (
    ejecutar_query,
    obtener_plan_cuentas_simple,
    obtener_plan_cuentas_detallado,
    reemplazar_plan_cuentas_simple,
    reemplazar_plan_cuentas_detallado,
    guardar_cuenta_detallada,
    eliminar_cuenta,
    obtener_categorias_compra,
    reemplazar_categorias_compra,
    guardar_categoria_compra,
    eliminar_categoria_compra,
    obtener_conceptos_fiscales_compra,
    reemplazar_conceptos_fiscales_compra,
    guardar_concepto_fiscal_compra,
    eliminar_concepto_fiscal_compra
)

from core.ui import preparar_vista


def leer_csv_configuracion(archivo):
    try:
        return pd.read_csv(
            archivo,
            sep=None,
            engine="python",
            encoding="utf-8",
            dtype=str
        )
    except Exception:
        archivo.seek(0)
        return pd.read_csv(
            archivo,
            sep=None,
            engine="python",
            encoding="latin-1",
            dtype=str
        )


def normalizar_columnas(df):
    df = df.copy()
    df.columns = [
        str(c).strip().lower().replace(" ", "_")
        for c in df.columns
    ]
    return df


def seleccionar_cuenta(label, df_plan, key):
    if df_plan.empty:
        st.warning("Primero cargá el plan de cuentas.")
        return "", ""

    opciones = [
        f"{row['codigo']} - {row['nombre']}"
        for _, row in df_plan.iterrows()
    ]

    seleccion = st.selectbox(label, opciones, key=key)

    codigo = seleccion.split(" - ")[0].strip()
    nombre = seleccion.split(" - ", 1)[1].strip()

    return codigo, nombre


def mostrar_configuracion():
    st.title("⚙️ Configuración")

    tab1, tab2, tab3, tab4 = st.tabs([
        "Tipos de Comprobantes",
        "Plan de Cuentas",
        "Categorías de Compra",
        "Conceptos Fiscales Compra"
    ])

    with tab1:
        mostrar_tipos_comprobantes()

    with tab2:
        mostrar_plan_cuentas()

    with tab3:
        mostrar_categorias_compra()

    with tab4:
        mostrar_conceptos_fiscales_compra()


def mostrar_tipos_comprobantes():
    st.subheader("Tipos de Comprobantes")

    df = ejecutar_query("""
        SELECT *
        FROM tipos_comprobantes
        ORDER BY codigo
    """, fetch=True)

    if df.empty:
        st.info("Sin datos cargados.")
    else:
        st.dataframe(preparar_vista(df), use_container_width=True)

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
                st.warning("Completar todos los campos.")
            else:
                ejecutar_query("""
                    INSERT OR REPLACE INTO tipos_comprobantes
                    (codigo, descripcion, signo)
                    VALUES (?, ?, ?)
                """, (codigo.strip(), descripcion.strip(), signo))

                st.success("Comprobante guardado.")
                st.rerun()

    with col2:
        if st.button("Eliminar comprobante"):
            if codigo == "":
                st.warning("Indicá el código a eliminar.")
            else:
                ejecutar_query("""
                    DELETE FROM tipos_comprobantes
                    WHERE codigo = ?
                """, (codigo.strip(),))

                st.success("Comprobante eliminado.")
                st.rerun()


def mostrar_plan_cuentas():
    st.subheader("Plan de Cuentas")

    st.info(
        "Acá cargás el archivo Plan_de_Cuenta_Mejorado_Estructurado.csv. "
        "Ese archivo reemplaza el plan anterior."
    )

    archivo = st.file_uploader(
        "Cargar plan de cuentas CSV",
        type=["csv"],
        key="upload_plan_cuentas"
    )

    if archivo:
        df = leer_csv_configuracion(archivo)
        df = normalizar_columnas(df)

        st.write("Vista previa del archivo:")
        st.dataframe(preparar_vista(df.head(20)), use_container_width=True)

        columnas = set(df.columns)

        if {"cuenta", "detalle"}.issubset(columnas):
            tipo_plan = "estructurado"
            st.success("Formato detectado: Plan de cuentas estructurado.")
        elif {"codigo", "nombre"}.issubset(columnas):
            tipo_plan = "simple"
            st.success("Formato detectado: Plan de cuentas simple.")
        else:
            tipo_plan = None
            st.error(
                "No se reconoció el formato. Debe tener columnas "
                "'cuenta' y 'detalle' o 'codigo' y 'nombre'."
            )

        if tipo_plan and st.button("Reemplazar plan de cuentas"):
            if tipo_plan == "estructurado":
                reemplazar_plan_cuentas_detallado(df)
            else:
                reemplazar_plan_cuentas_simple(df)

            st.success("Plan de cuentas cargado correctamente.")
            st.rerun()

    st.divider()

    df_detallado = obtener_plan_cuentas_detallado()
    df_simple = obtener_plan_cuentas_simple()

    st.subheader("Plan actual")

    if not df_detallado.empty:
        st.dataframe(preparar_vista(df_detallado), use_container_width=True)
    elif not df_simple.empty:
        st.dataframe(preparar_vista(df_simple), use_container_width=True)
    else:
        st.info("No hay plan de cuentas cargado.")

    st.divider()

    st.subheader("Crear / Actualizar cuenta manualmente")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        cuenta = st.text_input("Código cuenta", key="manual_cuenta")

    with col2:
        detalle = st.text_input("Nombre / detalle", key="manual_detalle")

    with col3:
        imputable = st.selectbox("Imputable", ["S", "N"], key="manual_imputable")

    with col4:
        tipo = st.selectbox("Tipo", ["D", "A", "N"], key="manual_tipo")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        ajustable = st.selectbox("Ajustable", ["N", "S"], key="manual_ajustable")

    with col2:
        madre = st.text_input("Cuenta madre", key="manual_madre")

    with col3:
        nivel = st.number_input("Nivel", min_value=1, max_value=10, value=1, step=1)

    with col4:
        orden = st.number_input("Orden", min_value=0, value=0, step=1)

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Guardar cuenta manual"):
            if cuenta == "" or detalle == "":
                st.warning("Completar código y nombre de cuenta.")
            else:
                guardar_cuenta_detallada(
                    cuenta.strip(),
                    detalle.strip(),
                    imputable,
                    ajustable,
                    tipo,
                    madre.strip(),
                    int(nivel),
                    int(orden)
                )

                st.success("Cuenta guardada.")
                st.rerun()

    with col2:
        if st.button("Eliminar cuenta manual"):
            if cuenta == "":
                st.warning("Indicá el código de cuenta a eliminar.")
            else:
                eliminar_cuenta(cuenta.strip())
                st.success("Cuenta eliminada.")
                st.rerun()


def mostrar_categorias_compra():
    st.subheader("Categorías de Compra")

    st.info(
        "Acá cargás Categorias_Compra_Sugeridas.csv. "
        "Esto le dice al sistema qué cuenta usar según el tipo de compra."
    )

    archivo = st.file_uploader(
        "Cargar categorías de compra CSV",
        type=["csv"],
        key="upload_categorias_compra"
    )

    if archivo:
        df = leer_csv_configuracion(archivo)
        df = normalizar_columnas(df)

        st.write("Vista previa del archivo:")
        st.dataframe(preparar_vista(df.head(20)), use_container_width=True)

        if "categoria" not in df.columns:
            st.error("El archivo debe tener al menos la columna 'categoria'.")
        else:
            if st.button("Reemplazar categorías de compra"):
                reemplazar_categorias_compra(df)
                st.success("Categorías de compra cargadas correctamente.")
                st.rerun()

    st.divider()

    df_cat = obtener_categorias_compra()

    st.subheader("Categorías actuales")

    if df_cat.empty:
        st.info("No hay categorías cargadas.")
    else:
        st.dataframe(preparar_vista(df_cat), use_container_width=True)

    st.divider()

    st.subheader("Crear / Actualizar categoría manual")

    df_plan = obtener_plan_cuentas_simple()

    categoria = st.text_input("Nombre categoría", key="cat_nombre")

    tipo_categoria = st.selectbox(
        "Tipo categoría",
        [
            "BIENES / MERCADERÍAS",
            "SERVICIOS / GASTOS",
            "BIENES DE USO",
            "IMPUESTOS / TASAS",
            "OTROS"
        ],
        key="cat_tipo"
    )

    col1, col2 = st.columns(2)

    with col1:
        cuenta_codigo, cuenta_nombre = seleccionar_cuenta(
            "Cuenta principal de la compra",
            df_plan,
            "cat_cuenta_principal"
        )

    with col2:
        proveedor_codigo, proveedor_nombre = seleccionar_cuenta(
            "Cuenta proveedor / acreedor",
            df_plan,
            "cat_cuenta_proveedor"
        )

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Guardar categoría"):
            if categoria == "":
                st.warning("Ingresá el nombre de la categoría.")
            else:
                guardar_categoria_compra(
                    categoria.strip(),
                    cuenta_codigo,
                    cuenta_nombre,
                    proveedor_codigo,
                    proveedor_nombre,
                    tipo_categoria,
                    1
                )

                st.success("Categoría guardada.")
                st.rerun()

    with col2:
        if st.button("Eliminar categoría"):
            if categoria == "":
                st.warning("Ingresá la categoría a eliminar.")
            else:
                eliminar_categoria_compra(categoria.strip())
                st.success("Categoría eliminada.")
                st.rerun()


def mostrar_conceptos_fiscales_compra():
    st.subheader("Conceptos Fiscales de Compra")

    st.info(
        "Acá cargás Conceptos_Fiscales_Compra_Sugeridos.csv. "
        "Esto define a qué cuenta van IVA, percepciones, impuestos internos y otros tributos."
    )

    archivo = st.file_uploader(
        "Cargar conceptos fiscales de compra CSV",
        type=["csv"],
        key="upload_conceptos_fiscales"
    )

    if archivo:
        df = leer_csv_configuracion(archivo)
        df = normalizar_columnas(df)

        st.write("Vista previa del archivo:")
        st.dataframe(preparar_vista(df.head(20)), use_container_width=True)

        if "concepto" not in df.columns:
            st.error("El archivo debe tener al menos la columna 'concepto'.")
        else:
            if st.button("Reemplazar conceptos fiscales de compra"):
                reemplazar_conceptos_fiscales_compra(df)
                st.success("Conceptos fiscales cargados correctamente.")
                st.rerun()

    st.divider()

    df_conceptos = obtener_conceptos_fiscales_compra()

    st.subheader("Conceptos actuales")

    if df_conceptos.empty:
        st.info("No hay conceptos fiscales cargados.")
    else:
        st.dataframe(preparar_vista(df_conceptos), use_container_width=True)

    st.divider()

    st.subheader("Crear / Actualizar concepto fiscal manual")

    df_plan = obtener_plan_cuentas_simple()

    concepto = st.text_input("Concepto fiscal", key="concepto_nombre")

    tratamiento = st.selectbox(
        "Tratamiento",
        [
            "CREDITO_FISCAL",
            "PERCEPCION_COMPUTABLE",
            "MAYOR_COSTO",
            "GASTO",
            "NO_COMPUTABLE",
            "OTROS"
        ],
        key="concepto_tratamiento"
    )

    cuenta_codigo, cuenta_nombre = seleccionar_cuenta(
        "Cuenta contable asociada",
        df_plan,
        "concepto_cuenta"
    )

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Guardar concepto fiscal"):
            if concepto == "":
                st.warning("Ingresá el nombre del concepto fiscal.")
            else:
                guardar_concepto_fiscal_compra(
                    concepto.strip(),
                    cuenta_codigo,
                    cuenta_nombre,
                    tratamiento,
                    1
                )

                st.success("Concepto fiscal guardado.")
                st.rerun()

    with col2:
        if st.button("Eliminar concepto fiscal"):
            if concepto == "":
                st.warning("Ingresá el concepto fiscal a eliminar.")
            else:
                eliminar_concepto_fiscal_compra(concepto.strip())
                st.success("Concepto fiscal eliminado.")
                st.rerun()