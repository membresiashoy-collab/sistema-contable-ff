import streamlit as st
import pandas as pd
import unicodedata

from database import ejecutar_query

from services.datos_base_service import (
    obtener_estado_datos_base,
    inicializar_datos_base
)

from services.backups_service import crear_backup_sqlite

from services.actividades_service import (
    asegurar_tablas_actividades,
    contar_actividades,
    leer_nomenclador_actividades,
    cargar_nomenclador_actividades,
    buscar_actividades,
    obtener_empresas_para_actividades,
    obtener_actividades_empresa,
    asignar_actividad_empresa,
    marcar_actividad_principal,
    quitar_actividad_empresa
)


# ======================================================
# FUNCIONES AUXILIARES
# ======================================================

def preparar_vista(df):
    df_vista = df.copy()
    df_vista.index = range(1, len(df_vista) + 1)
    df_vista.index.name = "N°"
    return df_vista


def quitar_acentos(texto):
    texto = str(texto)
    texto = unicodedata.normalize("NFD", texto)
    texto = texto.encode("ascii", "ignore").decode("utf-8")
    return texto


def normalizar_nombre_columna(nombre):
    nombre = quitar_acentos(nombre)
    nombre = nombre.lower().strip()
    nombre = nombre.replace(".", "")
    nombre = nombre.replace("-", "_")
    nombre = nombre.replace("/", "_")
    nombre = nombre.replace(" ", "_")

    while "__" in nombre:
        nombre = nombre.replace("__", "_")

    return nombre


def normalizar_columnas(df):
    df = df.copy()
    df.columns = [normalizar_nombre_columna(c) for c in df.columns]
    return df


def leer_csv_configuracion(archivo):
    try:
        archivo.seek(0)
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


def limpiar_valor(v):
    try:
        if pd.isna(v):
            return ""
        return str(v).strip()
    except Exception:
        return ""


def normalizar_conceptos_fiscales_df(df):
    df = normalizar_columnas(df)

    renombres = {}

    if "concepto_fiscal" in df.columns and "concepto" not in df.columns:
        renombres["concepto_fiscal"] = "concepto"

    if "tratamiento_default" in df.columns and "tratamiento" not in df.columns:
        renombres["tratamiento_default"] = "tratamiento"

    if "cuenta" in df.columns and "cuenta_codigo" not in df.columns:
        renombres["cuenta"] = "cuenta_codigo"

    if "detalle" in df.columns and "cuenta_nombre" not in df.columns:
        renombres["detalle"] = "cuenta_nombre"

    df = df.rename(columns=renombres)

    if "concepto" not in df.columns:
        df["concepto"] = ""

    if "cuenta_codigo" not in df.columns:
        df["cuenta_codigo"] = ""

    if "cuenta_nombre" not in df.columns:
        df["cuenta_nombre"] = ""

    if "tratamiento" not in df.columns:
        df["tratamiento"] = ""

    return df


def normalizar_categorias_compra_df(df):
    df = normalizar_columnas(df)

    renombres = {}

    if "categoria_compra" in df.columns and "categoria" not in df.columns:
        renombres["categoria_compra"] = "categoria"

    if "cuenta_principal_codigo" in df.columns and "cuenta_codigo" not in df.columns:
        renombres["cuenta_principal_codigo"] = "cuenta_codigo"

    if "cuenta_principal_nombre" in df.columns and "cuenta_nombre" not in df.columns:
        renombres["cuenta_principal_nombre"] = "cuenta_nombre"

    if "proveedor_codigo" in df.columns and "cuenta_proveedor_codigo" not in df.columns:
        renombres["proveedor_codigo"] = "cuenta_proveedor_codigo"

    if "proveedor_nombre" in df.columns and "cuenta_proveedor_nombre" not in df.columns:
        renombres["proveedor_nombre"] = "cuenta_proveedor_nombre"

    df = df.rename(columns=renombres)

    columnas_necesarias = [
        "categoria",
        "cuenta_codigo",
        "cuenta_nombre",
        "cuenta_proveedor_codigo",
        "cuenta_proveedor_nombre",
        "tipo_categoria"
    ]

    for col in columnas_necesarias:
        if col not in df.columns:
            df[col] = ""

    return df


def init_tablas_configuracion():
    ejecutar_query("""
        CREATE TABLE IF NOT EXISTS tipos_comprobantes (
            codigo TEXT PRIMARY KEY,
            descripcion TEXT,
            signo INTEGER
        )
    """)

    ejecutar_query("""
        CREATE TABLE IF NOT EXISTS plan_cuentas (
            codigo TEXT,
            nombre TEXT
        )
    """)

    ejecutar_query("""
        CREATE TABLE IF NOT EXISTS plan_cuentas_detallado (
            cuenta TEXT PRIMARY KEY,
            detalle TEXT,
            imputable TEXT,
            ajustable TEXT,
            tipo TEXT,
            madre TEXT,
            nivel INTEGER,
            orden INTEGER
        )
    """)

    ejecutar_query("""
        CREATE TABLE IF NOT EXISTS categorias_compra (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            categoria TEXT UNIQUE,
            cuenta_codigo TEXT,
            cuenta_nombre TEXT,
            cuenta_proveedor_codigo TEXT,
            cuenta_proveedor_nombre TEXT,
            tipo_categoria TEXT,
            activo INTEGER DEFAULT 1
        )
    """)

    ejecutar_query("""
        CREATE TABLE IF NOT EXISTS conceptos_fiscales_compra (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            concepto TEXT UNIQUE,
            cuenta_codigo TEXT,
            cuenta_nombre TEXT,
            tratamiento TEXT,
            activo INTEGER DEFAULT 1
        )
    """)

    asegurar_tablas_actividades()


# ======================================================
# PLAN DE CUENTAS
# ======================================================

def obtener_plan_simple():
    return ejecutar_query("""
        SELECT codigo, nombre
        FROM plan_cuentas
        ORDER BY codigo
    """, fetch=True)


def obtener_plan_detallado():
    return ejecutar_query("""
        SELECT cuenta, detalle, imputable, ajustable, tipo, madre, nivel, orden
        FROM plan_cuentas_detallado
        ORDER BY cuenta
    """, fetch=True)


def borrar_plan_cuentas():
    ejecutar_query("DELETE FROM plan_cuentas")
    ejecutar_query("DELETE FROM plan_cuentas_detallado")


def reemplazar_plan_simple(df):
    borrar_plan_cuentas()

    for _, fila in df.iterrows():
        codigo = limpiar_valor(fila.get("codigo", ""))
        nombre = limpiar_valor(fila.get("nombre", ""))

        if codigo and nombre:
            ejecutar_query("""
                INSERT INTO plan_cuentas (codigo, nombre)
                VALUES (?, ?)
            """, (codigo, nombre))


def reemplazar_plan_detallado(df):
    borrar_plan_cuentas()

    for _, fila in df.iterrows():
        cuenta = limpiar_valor(fila.get("cuenta", ""))
        detalle = limpiar_valor(fila.get("detalle", ""))

        imputable = limpiar_valor(fila.get("imputable", "S"))
        ajustable = limpiar_valor(fila.get("ajustable", "N"))
        tipo = limpiar_valor(fila.get("tipo", "D"))
        madre = limpiar_valor(fila.get("madre", ""))

        try:
            nivel = int(float(limpiar_valor(fila.get("nivel", 1)) or 1))
        except Exception:
            nivel = 1

        try:
            orden = int(float(limpiar_valor(fila.get("orden", 0)) or 0))
        except Exception:
            orden = 0

        if cuenta and detalle:
            ejecutar_query("""
                INSERT OR REPLACE INTO plan_cuentas_detallado
                (cuenta, detalle, imputable, ajustable, tipo, madre, nivel, orden)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (cuenta, detalle, imputable, ajustable, tipo, madre, nivel, orden))

            ejecutar_query("""
                INSERT INTO plan_cuentas (codigo, nombre)
                VALUES (?, ?)
            """, (cuenta, detalle))


def guardar_cuenta_manual(cuenta, detalle, imputable, ajustable, tipo, madre, nivel, orden):
    ejecutar_query("""
        INSERT OR REPLACE INTO plan_cuentas_detallado
        (cuenta, detalle, imputable, ajustable, tipo, madre, nivel, orden)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (cuenta, detalle, imputable, ajustable, tipo, madre, int(nivel), int(orden)))

    ejecutar_query("""
        DELETE FROM plan_cuentas
        WHERE codigo = ?
    """, (cuenta,))

    ejecutar_query("""
        INSERT INTO plan_cuentas (codigo, nombre)
        VALUES (?, ?)
    """, (cuenta, detalle))


def eliminar_cuenta(cuenta):
    ejecutar_query("""
        DELETE FROM plan_cuentas_detallado
        WHERE cuenta = ?
    """, (cuenta,))

    ejecutar_query("""
        DELETE FROM plan_cuentas
        WHERE codigo = ?
    """, (cuenta,))


# ======================================================
# CATEGORÍAS DE COMPRA
# ======================================================

def obtener_categorias_compra():
    return ejecutar_query("""
        SELECT 
            categoria,
            cuenta_codigo,
            cuenta_nombre,
            cuenta_proveedor_codigo,
            cuenta_proveedor_nombre,
            tipo_categoria,
            activo
        FROM categorias_compra
        ORDER BY categoria
    """, fetch=True)


def borrar_categorias_compra():
    ejecutar_query("DELETE FROM categorias_compra")


def reemplazar_categorias_compra(df):
    df = normalizar_categorias_compra_df(df)

    borrar_categorias_compra()

    for _, fila in df.iterrows():
        categoria = limpiar_valor(fila.get("categoria", ""))
        cuenta_codigo = limpiar_valor(fila.get("cuenta_codigo", ""))
        cuenta_nombre = limpiar_valor(fila.get("cuenta_nombre", ""))
        cuenta_proveedor_codigo = limpiar_valor(fila.get("cuenta_proveedor_codigo", ""))
        cuenta_proveedor_nombre = limpiar_valor(fila.get("cuenta_proveedor_nombre", ""))
        tipo_categoria = limpiar_valor(fila.get("tipo_categoria", ""))

        if categoria:
            ejecutar_query("""
                INSERT OR REPLACE INTO categorias_compra
                (categoria, cuenta_codigo, cuenta_nombre,
                 cuenta_proveedor_codigo, cuenta_proveedor_nombre,
                 tipo_categoria, activo)
                VALUES (?, ?, ?, ?, ?, ?, 1)
            """, (
                categoria,
                cuenta_codigo,
                cuenta_nombre,
                cuenta_proveedor_codigo,
                cuenta_proveedor_nombre,
                tipo_categoria
            ))


def guardar_categoria_compra(
    categoria,
    cuenta_codigo,
    cuenta_nombre,
    cuenta_proveedor_codigo,
    cuenta_proveedor_nombre,
    tipo_categoria,
    activo=1
):
    ejecutar_query("""
        INSERT OR REPLACE INTO categorias_compra
        (categoria, cuenta_codigo, cuenta_nombre,
         cuenta_proveedor_codigo, cuenta_proveedor_nombre,
         tipo_categoria, activo)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        categoria,
        cuenta_codigo,
        cuenta_nombre,
        cuenta_proveedor_codigo,
        cuenta_proveedor_nombre,
        tipo_categoria,
        activo
    ))


def eliminar_categoria_compra(categoria):
    ejecutar_query("""
        DELETE FROM categorias_compra
        WHERE categoria = ?
    """, (categoria,))


# ======================================================
# CONCEPTOS FISCALES COMPRA
# ======================================================

def obtener_conceptos_fiscales_compra():
    return ejecutar_query("""
        SELECT 
            concepto,
            cuenta_codigo,
            cuenta_nombre,
            tratamiento,
            activo
        FROM conceptos_fiscales_compra
        ORDER BY concepto
    """, fetch=True)


def borrar_conceptos_fiscales_compra():
    ejecutar_query("DELETE FROM conceptos_fiscales_compra")


def reemplazar_conceptos_fiscales_compra(df):
    df = normalizar_conceptos_fiscales_df(df)

    borrar_conceptos_fiscales_compra()

    for _, fila in df.iterrows():
        concepto = limpiar_valor(fila.get("concepto", ""))
        cuenta_codigo = limpiar_valor(fila.get("cuenta_codigo", ""))
        cuenta_nombre = limpiar_valor(fila.get("cuenta_nombre", ""))
        tratamiento = limpiar_valor(fila.get("tratamiento", ""))

        if concepto:
            ejecutar_query("""
                INSERT OR REPLACE INTO conceptos_fiscales_compra
                (concepto, cuenta_codigo, cuenta_nombre, tratamiento, activo)
                VALUES (?, ?, ?, ?, 1)
            """, (concepto, cuenta_codigo, cuenta_nombre, tratamiento))


def guardar_concepto_fiscal_compra(concepto, cuenta_codigo, cuenta_nombre, tratamiento, activo=1):
    ejecutar_query("""
        INSERT OR REPLACE INTO conceptos_fiscales_compra
        (concepto, cuenta_codigo, cuenta_nombre, tratamiento, activo)
        VALUES (?, ?, ?, ?, ?)
    """, (concepto, cuenta_codigo, cuenta_nombre, tratamiento, activo))


def eliminar_concepto_fiscal_compra(concepto):
    ejecutar_query("""
        DELETE FROM conceptos_fiscales_compra
        WHERE concepto = ?
    """, (concepto,))


# ======================================================
# UI AUXILIAR
# ======================================================

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


# ======================================================
# PANTALLA PRINCIPAL
# ======================================================

def mostrar_configuracion():
    init_tablas_configuracion()


    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "Tipos de Comprobantes",
        "Plan de Cuentas",
        "Categorías de Compra",
        "Conceptos Fiscales Compra",
        "Inicialización",
        "Actividades ARCA"
    ])

    with tab1:
        mostrar_tipos_comprobantes()

    with tab2:
        mostrar_plan_cuentas()

    with tab3:
        mostrar_categorias_compra()

    with tab4:
        mostrar_conceptos_fiscales_compra()

    with tab5:
        mostrar_inicializacion_sistema()

    with tab6:
        mostrar_actividades_arca()


# ======================================================
# TAB 1 - TIPOS DE COMPROBANTES
# ======================================================

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

    with st.form("form_comprobante"):
        st.subheader("Agregar / Actualizar comprobante")

        col1, col2, col3 = st.columns(3)

        with col1:
            codigo = st.text_input("Código")

        with col2:
            descripcion = st.text_input("Descripción")

        with col3:
            signo = st.selectbox("Signo", [1, -1])

        guardar = st.form_submit_button("Guardar comprobante")

        if guardar:
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

    st.divider()

    with st.form("form_eliminar_comprobante"):
        codigo_eliminar = st.text_input("Código de comprobante a eliminar")
        eliminar = st.form_submit_button("Eliminar comprobante")

        if eliminar:
            if codigo_eliminar == "":
                st.warning("Indicá el código.")
            else:
                ejecutar_query("""
                    DELETE FROM tipos_comprobantes
                    WHERE codigo = ?
                """, (codigo_eliminar.strip(),))

                st.success("Comprobante eliminado.")
                st.rerun()


# ======================================================
# TAB 2 - PLAN DE CUENTAS
# ======================================================

def mostrar_plan_cuentas():
    st.subheader("Plan de Cuentas")

    st.info(
        "Cargá acá el archivo Plan_de_Cuenta_Mejorado_Estructurado.csv. "
        "También podés borrar el plan actual y crear cuentas manualmente."
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
            st.success("Formato detectado: plan de cuentas estructurado.")
        elif {"codigo", "nombre"}.issubset(columnas):
            tipo_plan = "simple"
            st.success("Formato detectado: plan de cuentas simple.")
        else:
            tipo_plan = None
            st.error(
                "No se reconoció el formato. El archivo debe tener columnas "
                "'cuenta' y 'detalle' o 'codigo' y 'nombre'."
            )

        if tipo_plan:
            if st.button("Reemplazar plan de cuentas con este archivo"):
                if tipo_plan == "estructurado":
                    reemplazar_plan_detallado(df)
                else:
                    reemplazar_plan_simple(df)

                st.success("Plan de cuentas cargado correctamente.")
                st.rerun()

    st.divider()

    st.subheader("Plan actual")

    df_detallado = obtener_plan_detallado()
    df_simple = obtener_plan_simple()

    if not df_detallado.empty:
        st.caption(f"Cuentas cargadas: {len(df_detallado)}")
        st.dataframe(preparar_vista(df_detallado), use_container_width=True)

    elif not df_simple.empty:
        st.caption(f"Cuentas cargadas: {len(df_simple)}")
        st.dataframe(preparar_vista(df_simple), use_container_width=True)

    else:
        st.info("No hay plan de cuentas cargado.")

    st.divider()

    st.subheader("Borrar plan de cuentas actual")

    if "confirmar_borrar_plan" not in st.session_state:
        st.session_state["confirmar_borrar_plan"] = False

    if st.button("🧹 Borrar plan de cuentas actual"):
        st.session_state["confirmar_borrar_plan"] = True

    if st.session_state["confirmar_borrar_plan"]:
        st.warning(
            "¿Confirmás borrar todo el plan de cuentas actual? "
            "Esto no borra Libro Diario ni comprobantes cargados."
        )

        col1, col2 = st.columns(2)

        with col1:
            if st.button("Sí, borrar plan"):
                borrar_plan_cuentas()
                st.success("Plan de cuentas borrado.")
                st.session_state["confirmar_borrar_plan"] = False
                st.rerun()

        with col2:
            if st.button("Cancelar borrado"):
                st.session_state["confirmar_borrar_plan"] = False
                st.rerun()

    st.divider()

    st.subheader("Crear / Actualizar cuenta manualmente")

    with st.form("form_cuenta_manual"):
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            cuenta = st.text_input("Código cuenta")

        with col2:
            detalle = st.text_input("Nombre / detalle")

        with col3:
            imputable = st.selectbox("Imputable", ["S", "N"])

        with col4:
            tipo = st.selectbox("Tipo", ["D", "A", "N"])

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            ajustable = st.selectbox("Ajustable", ["N", "S"])

        with col2:
            madre = st.text_input("Cuenta madre")

        with col3:
            nivel = st.number_input("Nivel", min_value=1, max_value=20, value=1, step=1)

        with col4:
            orden = st.number_input("Orden", min_value=0, value=0, step=1)

        guardar = st.form_submit_button("Guardar cuenta")

        if guardar:
            if cuenta == "" or detalle == "":
                st.warning("Completar código y nombre de cuenta.")
            else:
                guardar_cuenta_manual(
                    cuenta.strip(),
                    detalle.strip(),
                    imputable,
                    ajustable,
                    tipo,
                    madre.strip(),
                    int(nivel),
                    int(orden)
                )

                st.success("Cuenta guardada correctamente.")
                st.rerun()

    st.divider()

    with st.form("form_eliminar_cuenta"):
        cuenta_eliminar = st.text_input("Código de cuenta a eliminar")
        eliminar = st.form_submit_button("Eliminar cuenta")

        if eliminar:
            if cuenta_eliminar == "":
                st.warning("Indicá el código de cuenta.")
            else:
                eliminar_cuenta(cuenta_eliminar.strip())
                st.success("Cuenta eliminada.")
                st.rerun()


# ======================================================
# TAB 3 - CATEGORÍAS DE COMPRA
# ======================================================

def mostrar_categorias_compra():
    st.subheader("Categorías de Compra")

    st.info(
        "Cargá acá Categorias_Compra_Sugeridas.csv. "
        "Esto define qué cuenta usar según el tipo de compra."
    )

    archivo = st.file_uploader(
        "Cargar categorías de compra CSV",
        type=["csv"],
        key="upload_categorias_compra"
    )

    if archivo:
        df = leer_csv_configuracion(archivo)
        df = normalizar_categorias_compra_df(df)

        st.write("Vista previa del archivo:")
        st.dataframe(preparar_vista(df.head(20)), use_container_width=True)

        if "categoria" not in df.columns or df["categoria"].fillna("").astype(str).str.strip().eq("").all():
            st.error("El archivo debe tener una columna de categoría. Se acepta 'categoria' o 'categoria_compra'.")
        else:
            if st.button("Reemplazar categorías de compra"):
                reemplazar_categorias_compra(df)
                st.success("Categorías cargadas correctamente.")
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

    df_plan = obtener_plan_simple()

    with st.form("form_categoria_compra"):
        categoria = st.text_input("Nombre categoría")

        tipo_categoria = st.selectbox(
            "Tipo categoría",
            [
                "BIENES / MERCADERÍAS",
                "SERVICIOS / GASTOS",
                "BIENES DE USO",
                "IMPUESTOS / TASAS",
                "OTROS"
            ]
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

        guardar = st.form_submit_button("Guardar categoría")

        if guardar:
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

    st.divider()

    with st.form("form_eliminar_categoria"):
        categoria_eliminar = st.text_input("Categoría a eliminar")
        eliminar = st.form_submit_button("Eliminar categoría")

        if eliminar:
            if categoria_eliminar == "":
                st.warning("Ingresá la categoría a eliminar.")
            else:
                eliminar_categoria_compra(categoria_eliminar.strip())
                st.success("Categoría eliminada.")
                st.rerun()


# ======================================================
# TAB 4 - CONCEPTOS FISCALES DE COMPRA
# ======================================================

def mostrar_conceptos_fiscales_compra():
    st.subheader("Conceptos Fiscales de Compra")

    st.info(
        "Cargá acá Conceptos_Fiscales_Compra_Sugeridos.csv. "
        "Define a qué cuenta van IVA, percepciones, impuestos internos y otros tributos."
    )

    archivo = st.file_uploader(
        "Cargar conceptos fiscales de compra CSV",
        type=["csv"],
        key="upload_conceptos_fiscales"
    )

    if archivo:
        df = leer_csv_configuracion(archivo)
        df = normalizar_conceptos_fiscales_df(df)

        st.write("Vista previa del archivo:")
        st.dataframe(preparar_vista(df.head(20)), use_container_width=True)

        if "concepto" not in df.columns or df["concepto"].fillna("").astype(str).str.strip().eq("").all():
            st.error("El archivo debe tener una columna de concepto. Se acepta 'concepto' o 'concepto_fiscal'.")
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

    df_plan = obtener_plan_simple()

    with st.form("form_concepto_fiscal"):
        concepto = st.text_input("Concepto fiscal")

        tratamiento = st.selectbox(
            "Tratamiento",
            [
                "CREDITO_FISCAL",
                "PERCEPCION_COMPUTABLE",
                "MAYOR_COSTO",
                "GASTO",
                "NO_COMPUTABLE",
                "OTROS"
            ]
        )

        cuenta_codigo, cuenta_nombre = seleccionar_cuenta(
            "Cuenta contable asociada",
            df_plan,
            "concepto_cuenta"
        )

        guardar = st.form_submit_button("Guardar concepto fiscal")

        if guardar:
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

    st.divider()

    with st.form("form_eliminar_concepto"):
        concepto_eliminar = st.text_input("Concepto fiscal a eliminar")
        eliminar = st.form_submit_button("Eliminar concepto fiscal")

        if eliminar:
            if concepto_eliminar == "":
                st.warning("Ingresá el concepto fiscal a eliminar.")
            else:
                eliminar_concepto_fiscal_compra(concepto_eliminar.strip())
                st.success("Concepto fiscal eliminado.")
                st.rerun()


# ======================================================
# TAB 5 - INICIALIZACIÓN DEL SISTEMA
# ======================================================

def mostrar_inicializacion_sistema():
    st.subheader("Inicialización del sistema")

    st.info(
        "Esta opción carga una configuración base mínima para comenzar a trabajar. "
        "No reemplaza datos existentes: solo completa datos faltantes."
    )

    estado = obtener_estado_datos_base()

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Tipos comprobantes", estado["tipos_comprobantes"])
    col2.metric("Plan cuentas", estado["plan_cuentas_detallado"])
    col3.metric("Categorías compra", estado["categorias_compra"])
    col4.metric("Conceptos fiscales", estado["conceptos_fiscales_compra"])

    st.divider()

    st.warning(
        "Usá esta opción cuando la base esté vacía o cuando quieras completar "
        "configuraciones faltantes. El sistema creará un backup antes de cargar."
    )

    if "confirmar_inicializar_datos_base" not in st.session_state:
        st.session_state["confirmar_inicializar_datos_base"] = False

    if st.button("Cargar / completar datos base"):
        st.session_state["confirmar_inicializar_datos_base"] = True

    if st.session_state["confirmar_inicializar_datos_base"]:
        st.warning("¿Confirmás cargar la configuración base del sistema?")

        c1, c2 = st.columns(2)

        with c1:
            if st.button("Sí, cargar datos base"):
                crear_backup_sqlite("antes_cargar_datos_base")

                resultado = inicializar_datos_base()

                st.success("Datos base cargados correctamente.")
                st.write("Resultado:")
                st.json(resultado)

                st.session_state["confirmar_inicializar_datos_base"] = False
                st.rerun()

        with c2:
            if st.button("Cancelar"):
                st.session_state["confirmar_inicializar_datos_base"] = False
                st.rerun()


# ======================================================
# TAB 6 - ACTIVIDADES ARCA
# ======================================================

def mostrar_actividades_arca():
    st.subheader("Actividades Económicas ARCA")

    st.info(
        "Desde esta pantalla podés cargar el nomenclador de actividades económicas "
        "y vincular una o varias actividades a cada empresa."
    )

    total_actividades = contar_actividades()

    st.metric("Actividades cargadas", total_actividades)

    st.divider()

    st.subheader("Cargar nomenclador desde TXT / CSV")

    archivo = st.file_uploader(
        "Subir archivo ACTIVIDADES_ECONOMICAS_F883.txt",
        type=["txt", "csv"],
        key="upload_actividades_arca"
    )

    if archivo:
        try:
            df_actividades = leer_nomenclador_actividades(archivo)

            st.success(f"Archivo leído correctamente. Actividades detectadas: {len(df_actividades)}")
            st.dataframe(preparar_vista(df_actividades.head(50)), use_container_width=True)

            reemplazar = st.checkbox(
                "Reemplazar nomenclador actual",
                value=False,
                help="Si está marcado, borra el nomenclador actual antes de cargar el nuevo."
            )

            if "confirmar_cargar_actividades" not in st.session_state:
                st.session_state["confirmar_cargar_actividades"] = False

            if st.button("Cargar nomenclador ARCA"):
                st.session_state["confirmar_cargar_actividades"] = True

            if st.session_state["confirmar_cargar_actividades"]:
                st.warning("¿Confirmás cargar el nomenclador de actividades?")

                c1, c2 = st.columns(2)

                with c1:
                    if st.button("Sí, cargar actividades"):
                        crear_backup_sqlite("antes_cargar_actividades_arca")

                        resultado = cargar_nomenclador_actividades(
                            df_actividades,
                            reemplazar=reemplazar
                        )

                        st.success("Nomenclador cargado correctamente.")
                        st.json(resultado)

                        st.session_state["confirmar_cargar_actividades"] = False
                        st.rerun()

                with c2:
                    if st.button("Cancelar carga actividades"):
                        st.session_state["confirmar_cargar_actividades"] = False
                        st.rerun()

        except Exception as e:
            st.error(f"No se pudo leer el archivo: {str(e)}")

    st.divider()

    st.subheader("Buscar actividades")

    filtro = st.text_input(
        "Buscar por código o descripción",
        key="buscar_actividad_arca"
    )

    df_busqueda = buscar_actividades(filtro, limite=300)

    if df_busqueda.empty:
        st.info("No hay actividades para mostrar.")
    else:
        st.dataframe(preparar_vista(df_busqueda), use_container_width=True)

    st.divider()

    st.subheader("Asignar actividades a empresas")

    df_empresas = obtener_empresas_para_actividades()

    if df_empresas.empty:
        st.warning("No hay empresas activas cargadas.")
        return

    empresas_opciones = df_empresas["id"].tolist()

    empresa_id = st.selectbox(
        "Empresa",
        empresas_opciones,
        format_func=lambda x: df_empresas[df_empresas["id"] == x].iloc[0]["nombre"],
        key="empresa_actividades_select"
    )

    fila_empresa = df_empresas[df_empresas["id"] == empresa_id].iloc[0]
    st.caption(f"Empresa seleccionada: {fila_empresa['nombre']}")

    df_asignadas = obtener_actividades_empresa(empresa_id)

    st.subheader("Actividades asignadas")

    if df_asignadas.empty:
        st.info("Esta empresa todavía no tiene actividades asignadas.")
    else:
        st.dataframe(preparar_vista(df_asignadas), use_container_width=True)

    st.divider()

    st.subheader("Agregar actividad a la empresa")

    filtro_asignar = st.text_input(
        "Buscar actividad para asignar",
        key="filtro_asignar_actividad"
    )

    df_opciones = buscar_actividades(filtro_asignar, limite=200)

    if df_opciones.empty:
        st.info("Buscá una actividad para asignarla.")
    else:
        opciones_actividades = df_opciones["codigo"].tolist()

        codigo_seleccionado = st.selectbox(
            "Actividad",
            opciones_actividades,
            format_func=lambda x: (
                f"{x} - "
                f"{df_opciones[df_opciones['codigo'] == x].iloc[0]['descripcion']}"
            ),
            key="actividad_a_asignar"
        )

        principal = st.checkbox(
            "Marcar como actividad principal",
            value=df_asignadas.empty,
            key="actividad_principal_check"
        )

        if st.button("Asignar actividad a empresa"):
            resultado = asignar_actividad_empresa(
                empresa_id,
                codigo_seleccionado,
                principal=principal
            )

            if resultado["ok"]:
                st.success(resultado["mensaje"])
            else:
                st.error(resultado["mensaje"])

            st.rerun()

    if not df_asignadas.empty:
        st.divider()

        st.subheader("Administrar actividades asignadas")

        codigos_asignados = df_asignadas["codigo_actividad"].tolist()

        codigo_admin = st.selectbox(
            "Actividad asignada",
            codigos_asignados,
            format_func=lambda x: (
                f"{x} - "
                f"{df_asignadas[df_asignadas['codigo_actividad'] == x].iloc[0]['descripcion']}"
            ),
            key="actividad_admin"
        )

        col1, col2 = st.columns(2)

        with col1:
            if st.button("Marcar como principal"):
                resultado = marcar_actividad_principal(
                    empresa_id,
                    codigo_admin
                )

                if resultado["ok"]:
                    st.success(resultado["mensaje"])
                else:
                    st.error(resultado["mensaje"])

                st.rerun()

        with col2:
            if st.button("Quitar actividad"):
                resultado = quitar_actividad_empresa(
                    empresa_id,
                    codigo_admin
                )

                if resultado["ok"]:
                    st.success(resultado["mensaje"])
                else:
                    st.error(resultado["mensaje"])

                st.rerun()