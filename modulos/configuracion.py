import streamlit as st
import pandas as pd
import unicodedata

from database import ejecutar_query

from services.datos_base_service import (
    obtener_estado_datos_base,
    inicializar_datos_base
)

from services.empresas_service import (
    obtener_resumen_empresa_operativa,
    preparar_controles_empresa_para_vista,
    inicializar_empresa_operativa,
    obtener_recomendaciones_empresa,
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

from core.contabilidad_coherencia import COMPORTAMIENTOS_CONTABLES
from services.plan_cuentas_service import (
    MODULOS_ORIGEN_PREFERIDO,
    TIPOS_CUENTA,
    asegurar_estructura_plan_cuentas,
    borrar_plan_cuentas_completo,
    diagnosticar_plan_cuentas_pro,
    eliminar_cuenta_plan,
    guardar_cuenta_plan,
    limpiar_comportamiento_cuenta,
    listar_eventos_plan_cuentas,
    listar_plan_cuentas,
    listar_sugerencias_plan_cuentas,
    normalizar_metadata_plan_cuentas,
    obtener_cuenta_plan,
    reemplazar_plan_desde_dataframe,
    sugerir_comportamiento_plan,
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


def empresa_actual_id():
    empresa_id = st.session_state.get("empresa_id")

    if empresa_id is None:
        return None

    try:
        return int(empresa_id)
    except Exception:
        return None


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

    asegurar_estructura_plan_cuentas()
    asegurar_tablas_actividades()


# ======================================================
# PLAN DE CUENTAS
# ======================================================


def _empresa_id_actual():
    try:
        return int(st.session_state.get("empresa_id") or st.session_state.get("empresa_actual_id") or 1)
    except Exception:
        return 1


def _usuario_actual_nombre():
    usuario = st.session_state.get("usuario") or st.session_state.get("usuario_nombre") or "Administrador"
    if isinstance(usuario, dict):
        return usuario.get("usuario") or usuario.get("nombre") or "Administrador"
    return str(usuario or "Administrador")


def _catalogo_comportamientos_opciones():
    opciones = [""]
    opciones.extend(sorted(COMPORTAMIENTOS_CONTABLES.keys()))
    return opciones


def _formatear_comportamiento(codigo):
    codigo = str(codigo or "").strip()
    if not codigo:
        return "Sin uso operativo"
    datos = COMPORTAMIENTOS_CONTABLES.get(codigo, {})
    nombre = datos.get("nombre", codigo)
    return f"{codigo} — {nombre}"


def _codigo_desde_opcion_comportamiento(opcion):
    texto = str(opcion or "").strip()
    if not texto or texto == "Sin uso operativo":
        return ""
    return texto.split("—", 1)[0].strip()


def _preparar_plan_dataframe(cuentas):
    columnas = [
        "codigo",
        "nombre",
        "imputable",
        "tipo",
        "madre",
        "nivel",
        "orden",
        "comportamiento_contable",
        "permite_imputacion_operativa",
        "requiere_auxiliar",
        "modulo_origen_preferido",
        "estado_configuracion",
    ]
    df = pd.DataFrame(cuentas)
    if df.empty:
        return pd.DataFrame(columns=columnas)
    for col in columnas:
        if col not in df.columns:
            df[col] = ""
    return df[columnas]


def obtener_plan_simple():
    cuentas = listar_plan_cuentas(empresa_id=_empresa_id_actual())
    return pd.DataFrame([
        {"codigo": item["codigo"], "nombre": item["nombre"]}
        for item in cuentas
    ])


def obtener_plan_detallado():
    cuentas = listar_plan_cuentas(empresa_id=_empresa_id_actual())
    return pd.DataFrame([
        {
            "cuenta": item["codigo"],
            "detalle": item["nombre"],
            "imputable": item["imputable"],
            "ajustable": item["ajustable"],
            "tipo": item["tipo"],
            "madre": item["madre"],
            "nivel": item["nivel"],
            "orden": item["orden"],
        }
        for item in cuentas
    ])


def borrar_plan_cuentas():
    return borrar_plan_cuentas_completo(
        empresa_id=_empresa_id_actual(),
        usuario=_usuario_actual_nombre(),
        motivo="Borrado completo desde Configuración → Plan de Cuentas",
    )


def reemplazar_plan_simple(df):
    return reemplazar_plan_desde_dataframe(
        df,
        empresa_id=_empresa_id_actual(),
        formato="simple",
        usuario=_usuario_actual_nombre(),
        motivo="Reemplazo de plan simple desde Configuración",
    )


def reemplazar_plan_detallado(df):
    return reemplazar_plan_desde_dataframe(
        df,
        empresa_id=_empresa_id_actual(),
        formato="detallado",
        usuario=_usuario_actual_nombre(),
        motivo="Reemplazo de plan estructurado desde Configuración",
    )


def guardar_cuenta_manual(cuenta, detalle, imputable, ajustable, tipo, madre, nivel, orden):
    return guardar_cuenta_plan(
        empresa_id=_empresa_id_actual(),
        codigo=cuenta,
        nombre=detalle,
        imputable=imputable,
        ajustable=ajustable,
        tipo=tipo,
        madre=madre,
        nivel=int(nivel),
        orden=int(orden),
        comportamiento_contable="",
        permite_imputacion_operativa=1 if imputable == "S" else 0,
        requiere_auxiliar=0,
        modulo_origen_preferido="",
        usuario=_usuario_actual_nombre(),
        motivo="Alta/edición manual desde Configuración → Plan de Cuentas",
    )


def eliminar_cuenta(cuenta):
    return eliminar_cuenta_plan(
        cuenta,
        empresa_id=_empresa_id_actual(),
        usuario=_usuario_actual_nombre(),
        motivo="Eliminación desde Configuración → Plan de Cuentas",
    )


def _mostrar_alertas_plan_cuentas(empresa_id):
    diagnostico = diagnosticar_plan_cuentas_pro(empresa_id=empresa_id)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Cuentas", diagnostico["total_cuentas"])
    col2.metric("Imputables", diagnostico["imputables"])
    col3.metric("Con uso operativo", diagnostico["con_comportamiento"])
    col4.metric("Pendientes", diagnostico["pendientes"])

    errores = diagnostico.get("errores", [])
    advertencias = diagnostico.get("advertencias", [])
    faltantes = diagnostico.get("criticos_faltantes", [])

    if errores:
        st.error("Hay cuentas que no respetan la regla central del plan de cuentas.")
        st.caption("Una cuenta no imputable no puede tener uso operativo del sistema ni permitir imputación operativa.")
        st.dataframe(preparar_vista(pd.DataFrame(errores)), use_container_width=True)
        col_a, col_b = st.columns([1, 2])
        with col_a:
            if st.button("Normalizar reglas seguras del plan", key="normalizar_plan_cuentas_seguro"):
                resultado = normalizar_metadata_plan_cuentas(
                    empresa_id=empresa_id,
                    usuario=_usuario_actual_nombre(),
                    motivo="Corrección de cuentas no imputables con uso operativo/imputación operativa",
                )
                if resultado.get("ok"):
                    st.success(
                        f"Plan normalizado. Cuentas no imputables corregidas: {resultado.get('corregidas_no_imputables', 0)}."
                    )
                    st.rerun()
                else:
                    st.error("No se pudo normalizar el plan: " + "; ".join(resultado.get("errores", [resultado.get("error", "Error desconocido")])) )
    else:
        st.success("Reglas estructurales del plan: OK. Las cuentas no imputables no tienen uso operativo del sistema.")

    if advertencias:
        st.warning("Hay asignaciones que conviene revisar.")
        st.dataframe(preparar_vista(pd.DataFrame(advertencias)), use_container_width=True)

    if faltantes:
        st.info("Usos operativos críticos aún no cubiertos: " + ", ".join(faltantes))


def mostrar_plan_cuentas():
    st.subheader("Plan de Cuentas PRO")

    st.info(
        "El Plan de Cuentas es la fuente de verdad contable del sistema. "
        "Desde acá se crean y editan las cuentas, se define si son imputables y se informa, si corresponde, su uso operativo opcional para automatización y diagnóstico. "
        "Contabilidad → Uso operativo queda como tablero de control y diagnóstico, no como carga duplicada."
    )

    empresa_id = _empresa_id_actual()
    asegurar_estructura_plan_cuentas()

    _mostrar_alertas_plan_cuentas(empresa_id)

    tabs = st.tabs([
        "📘 Plan actual",
        "✏️ Crear / editar cuenta",
        "🧭 Sugerencias",
        "📥 Importar / borrar",
        "🕓 Auditoría",
    ])

    with tabs[0]:
        cuentas = listar_plan_cuentas(empresa_id=empresa_id)
        df = _preparar_plan_dataframe(cuentas)

        st.markdown("#### Plan actual")
        if df.empty:
            st.info("No hay plan de cuentas cargado.")
        else:
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                filtro_texto = st.text_input("Buscar cuenta", key="plan_buscar")
            with col2:
                filtro_imputable = st.selectbox("Imputable", ["Todas", "S", "N"], key="plan_filtro_imputable")
            with col3:
                comportamientos = ["Todos", "Sin comportamiento"] + sorted([c for c in df["comportamiento_contable"].dropna().unique() if str(c).strip()])
                filtro_comp = st.selectbox("Uso operativo del sistema", comportamientos, key="plan_filtro_comportamiento")
            with col4:
                tipos = ["Todos"] + sorted([t for t in df["tipo"].dropna().unique() if str(t).strip()])
                filtro_tipo = st.selectbox("Tipo", tipos, key="plan_filtro_tipo")

            vista = df.copy()
            if filtro_texto:
                patron = filtro_texto.lower().strip()
                vista = vista[
                    vista["codigo"].astype(str).str.lower().str.contains(patron, na=False)
                    | vista["nombre"].astype(str).str.lower().str.contains(patron, na=False)
                ]
            if filtro_imputable != "Todas":
                vista = vista[vista["imputable"] == filtro_imputable]
            if filtro_comp == "Sin comportamiento":
                vista = vista[vista["comportamiento_contable"].fillna("").astype(str).str.strip() == ""]
            elif filtro_comp != "Todos":
                vista = vista[vista["comportamiento_contable"] == filtro_comp]
            if filtro_tipo != "Todos":
                vista = vista[vista["tipo"] == filtro_tipo]

            columnas_vista = {
                "codigo": "Código",
                "nombre": "Cuenta",
                "imputable": "Imputable",
                "tipo": "Tipo",
                "madre": "Madre",
                "nivel": "Nivel",
                "orden": "Orden",
                "comportamiento_contable": "Uso operativo",
                "permite_imputacion_operativa": "Imputación operativa",
                "requiere_auxiliar": "Requiere auxiliar",
                "modulo_origen_preferido": "Módulo sugerido",
                "estado_configuracion": "Estado",
            }
            st.caption(f"Cuentas mostradas: {len(vista)} de {len(df)}")
            st.dataframe(preparar_vista(vista.rename(columns=columnas_vista)), use_container_width=True)

    with tabs[1]:
        st.markdown("#### Crear / editar cuenta")
        cuentas = listar_plan_cuentas(empresa_id=empresa_id)
        opciones = ["➕ Nueva cuenta"] + [f"{item['codigo']} — {item['nombre']}" for item in cuentas]
        seleccion = st.selectbox("Cuenta a editar", opciones, key="plan_editar_seleccion")
        cuenta_actual = None
        if not seleccion.startswith("➕"):
            codigo_actual = seleccion.split("—", 1)[0].strip()
            cuenta_actual = obtener_cuenta_plan(codigo_actual, empresa_id=empresa_id)

        with st.form("form_plan_cuentas_pro"):
            col1, col2 = st.columns([1, 3])
            with col1:
                codigo = st.text_input("Código", value=(cuenta_actual or {}).get("codigo", ""))
            with col2:
                nombre = st.text_input("Nombre / detalle", value=(cuenta_actual or {}).get("nombre", ""))

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                imputable = st.selectbox(
                    "Imputable",
                    ["S", "N"],
                    index=0 if (cuenta_actual or {}).get("imputable", "S") == "S" else 1,
                    help="Solo las cuentas imputables pueden recibir movimientos y uso operativo del sistema.",
                )
            with col2:
                ajustable = st.selectbox(
                    "Ajustable",
                    ["N", "S"],
                    index=0 if (cuenta_actual or {}).get("ajustable", "N") == "N" else 1,
                )
            with col3:
                tipos = list(TIPOS_CUENTA.keys())
                tipo_actual = (cuenta_actual or {}).get("tipo", "D") or "D"
                tipo = st.selectbox("Tipo", tipos, index=tipos.index(tipo_actual) if tipo_actual in tipos else tipos.index("D"))
            with col4:
                madre = st.text_input("Cuenta madre", value=(cuenta_actual or {}).get("madre", ""))

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                nivel = st.number_input("Nivel", min_value=1, max_value=20, value=int((cuenta_actual or {}).get("nivel", 1) or 1), step=1)
            with col2:
                orden = st.number_input("Orden", min_value=0, value=int((cuenta_actual or {}).get("orden", 0) or 0), step=1)
            with col3:
                permite_default = bool((cuenta_actual or {}).get("permite_imputacion_operativa", 1 if imputable == "S" else 0)) if imputable == "S" else False
                permite = st.checkbox("Permite imputación operativa", value=permite_default, disabled=imputable != "S")
            with col4:
                requiere_default = bool((cuenta_actual or {}).get("requiere_auxiliar", 0)) if imputable == "S" else False
                requiere_auxiliar = st.checkbox("Requiere auxiliar", value=requiere_default, disabled=imputable != "S")

            if imputable != "S":
                st.warning("Esta cuenta no es imputable: no puede tener uso operativo del sistema ni imputación operativa.")
                comportamiento = ""
                modulo = ""
            else:
                col1, col2 = st.columns(2)
                with col1:
                    comportamiento_actual = (cuenta_actual or {}).get("comportamiento_contable", "") or ""
                    opciones_comp = [_formatear_comportamiento("")] + [_formatear_comportamiento(c) for c in sorted(COMPORTAMIENTOS_CONTABLES.keys())]
                    valor_actual = _formatear_comportamiento(comportamiento_actual)
                    idx = opciones_comp.index(valor_actual) if valor_actual in opciones_comp else 0
                    comportamiento_opcion = st.selectbox("Uso operativo del sistema (opcional)", opciones_comp, index=idx, help="No define la estructura contable. Solo ayuda a automatizaciones, controles y diagnósticos.")
                    comportamiento = _codigo_desde_opcion_comportamiento(comportamiento_opcion)
                with col2:
                    modulo_actual = (cuenta_actual or {}).get("modulo_origen_preferido", "") or ""
                    modulo = st.selectbox(
                        "Módulo de origen preferido",
                        MODULOS_ORIGEN_PREFERIDO,
                        index=MODULOS_ORIGEN_PREFERIDO.index(modulo_actual) if modulo_actual in MODULOS_ORIGEN_PREFERIDO else 0,
                    )

                sugerencia = sugerir_comportamiento_plan(codigo, nombre, imputable)
                if sugerencia.get("comportamiento") and not comportamiento:
                    st.info(
                        f"Sugerencia: {sugerencia['comportamiento']} ({sugerencia['confianza']}). "
                        f"Motivo: {sugerencia['motivo']}"
                    )

            motivo = st.text_area(
                "Motivo / observación del cambio",
                value="Edición desde Plan de Cuentas PRO",
                help="Queda registrado en la auditoría del plan de cuentas.",
            )
            guardar = st.form_submit_button("Guardar cuenta en Plan de Cuentas")

            if guardar:
                resultado = guardar_cuenta_plan(
                    empresa_id=empresa_id,
                    codigo=codigo,
                    nombre=nombre,
                    imputable=imputable,
                    ajustable=ajustable,
                    tipo=tipo,
                    madre=madre,
                    nivel=int(nivel),
                    orden=int(orden),
                    comportamiento_contable=comportamiento,
                    permite_imputacion_operativa=1 if permite else 0,
                    requiere_auxiliar=1 if requiere_auxiliar else 0,
                    modulo_origen_preferido=modulo,
                    usuario=_usuario_actual_nombre(),
                    motivo=motivo,
                )
                if resultado.get("ok"):
                    st.success("Cuenta guardada correctamente en el Plan de Cuentas.")
                    st.rerun()
                else:
                    st.error("No se pudo guardar la cuenta: " + "; ".join(resultado.get("errores", [])))

        st.divider()
        st.markdown("#### Limpiar uso operativo de una cuenta")
        st.caption("Usar cuando una cuenta quedó con un uso operativo incorrecto. No borra la cuenta ni movimientos; solo limpia ese uso operativo y deja auditoría.")
        cuentas_con_comp = [item for item in listar_plan_cuentas(empresa_id=empresa_id) if item.get("comportamiento_contable")]
        if cuentas_con_comp:
            opcion_limpiar = st.selectbox(
                "Cuenta con uso operativo",
                [f"{item['codigo']} — {item['nombre']} ({item['comportamiento_contable']})" for item in cuentas_con_comp],
                key="plan_limpiar_comportamiento",
            )
            motivo_limpieza = st.text_input(
                "Motivo de limpieza",
                value="Corrección de uso operativo desde Plan de Cuentas PRO",
            )
            if st.button("Limpiar uso operativo seleccionado"):
                codigo_limpieza = opcion_limpiar.split("—", 1)[0].strip()
                resultado = limpiar_comportamiento_cuenta(
                    codigo_limpieza,
                    empresa_id=empresa_id,
                    usuario=_usuario_actual_nombre(),
                    motivo=motivo_limpieza,
                )
                if resultado.get("ok"):
                    st.success("Uso operativo limpiado con auditoría.")
                    st.rerun()
                else:
                    st.error("No se pudo limpiar: " + "; ".join(resultado.get("errores", [])))
        else:
            st.info("No hay cuentas con uso operativo asignado.")

    with tabs[2]:
        st.markdown("#### Sugerencias del Plan de Cuentas")
        st.caption("Las sugerencias se calculan sobre cuentas imputables sin uso operativo. La aplicación se realiza editando la cuenta desde la pestaña Crear / editar cuenta.")
        sugerencias = listar_sugerencias_plan_cuentas(empresa_id=empresa_id)
        if not sugerencias:
            st.success("No hay sugerencias pendientes sobre cuentas imputables sin uso operativo.")
        else:
            df_sug = pd.DataFrame(sugerencias)
            columnas = {
                "codigo": "Código",
                "nombre": "Cuenta",
                "comportamiento": "Sugerencia",
                "confianza": "Confianza",
                "motivo": "Motivo",
            }
            st.dataframe(preparar_vista(df_sug[["codigo", "nombre", "comportamiento", "confianza", "motivo"]].rename(columns=columnas)), use_container_width=True)
            st.info("Para aplicar una sugerencia, elegí la cuenta en Crear / editar cuenta y guardá el uso operativo en el Plan de Cuentas.")

    with tabs[3]:
        st.markdown("#### Importar plan de cuentas")
        st.info(
            "Podés cargar un CSV estructurado con columnas cuenta/detalle/imputable/ajustable/tipo/madre/nivel/orden, "
            "o uno simple con codigo/nombre. El reemplazo afecta solo al plan de cuentas, no borra movimientos operativos."
        )
        archivo = st.file_uploader("Cargar plan de cuentas CSV", type=["csv"], key="upload_plan_cuentas_pro")
        if archivo:
            df = leer_csv_configuracion(archivo)
            df = normalizar_columnas(df)
            st.write("Vista previa del archivo:")
            st.dataframe(preparar_vista(df.head(20)), use_container_width=True)
            columnas = set(df.columns)
            if {"cuenta", "detalle"}.issubset(columnas):
                tipo_plan = "detallado"
                st.success("Formato detectado: plan estructurado.")
            elif {"codigo", "nombre"}.issubset(columnas):
                tipo_plan = "simple"
                st.success("Formato detectado: plan simple.")
            else:
                tipo_plan = None
                st.error("No se reconoció el formato. Debe tener cuenta/detalle o codigo/nombre.")
            if tipo_plan and st.button("Reemplazar plan de cuentas con este archivo"):
                resultado = reemplazar_plan_desde_dataframe(
                    df,
                    empresa_id=empresa_id,
                    formato=tipo_plan,
                    usuario=_usuario_actual_nombre(),
                    motivo="Reemplazo desde Configuración → Plan de Cuentas PRO",
                )
                if resultado.get("ok"):
                    st.success(f"Plan reemplazado. Cuentas procesadas: {resultado.get('procesadas', 0)}.")
                    st.rerun()
                else:
                    st.error("No se pudo reemplazar el plan: " + "; ".join(resultado.get("errores", [])))

        st.divider()
        with st.expander("Borrar plan de cuentas actual", expanded=False):
            st.warning("Esto no borra Libro Diario, comprobantes ni movimientos; solo borra el catálogo del plan de cuentas.")
            confirmar = st.text_input("Para borrar escribí BORRAR PLAN", key="confirm_borrar_plan_pro")
            if st.button("Borrar plan de cuentas", disabled=confirmar != "BORRAR PLAN"):
                resultado = borrar_plan_cuentas_completo(
                    empresa_id=empresa_id,
                    usuario=_usuario_actual_nombre(),
                    motivo="Borrado confirmado desde Configuración → Plan de Cuentas PRO",
                )
                if resultado.get("ok"):
                    st.success("Plan de cuentas borrado.")
                    st.rerun()
                else:
                    st.error("No se pudo borrar el plan: " + "; ".join(resultado.get("errores", [])))

    with tabs[4]:
        st.markdown("#### Auditoría del Plan de Cuentas")
        eventos = listar_eventos_plan_cuentas(empresa_id=empresa_id, limite=300)
        if not eventos:
            st.info("Todavía no hay eventos registrados del Plan de Cuentas PRO.")
        else:
            st.dataframe(preparar_vista(pd.DataFrame(eventos)), use_container_width=True)

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


def mostrar_pasos_inicializacion(pasos):
    df_pasos = pd.DataFrame(pasos or [])

    if df_pasos.empty:
        st.info("No hay pasos de inicialización para mostrar.")
        return

    columnas = ["paso", "ok", "mensaje"]

    columnas = [c for c in columnas if c in df_pasos.columns]

    st.dataframe(
        preparar_vista(df_pasos[columnas]),
        use_container_width=True,
    )


# ======================================================
# PANTALLA PRINCIPAL
# ======================================================

def mostrar_configuracion():
    init_tablas_configuracion()

    tab0, tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "Estado de Empresa",
        "Tipos de Comprobantes",
        "Plan de Cuentas",
        "Categorías de Compra",
        "Conceptos Fiscales Compra",
        "Inicialización",
        "Actividades ARCA"
    ])

    with tab0:
        mostrar_estado_empresa_operativa()

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
# TAB 0 - ESTADO DE EMPRESA
# ======================================================

def mostrar_estado_empresa_operativa():
    st.subheader("Estado operativo de la empresa")

    st.info(
        "Esta vista controla si la empresa activa tiene la base mínima para operar: "
        "datos fiscales, tipos de comprobantes, plan de cuentas, categorías, conceptos fiscales, "
        "actividad, tesorería, caja y bancos. No borra datos ni modifica movimientos."
    )

    empresa_id = empresa_actual_id()

    if empresa_id is None:
        st.warning(
            "No hay empresa activa seleccionada. Revisá Seguridad o el selector de empresa."
        )
        return

    try:
        resumen = obtener_resumen_empresa_operativa(empresa_id)
        controles = preparar_controles_empresa_para_vista(empresa_id)
        recomendaciones = obtener_recomendaciones_empresa(empresa_id)
    except Exception as e:
        st.error("No se pudo obtener el diagnóstico operativo de la empresa.")
        st.exception(e)
        return

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Empresa", resumen.get("nombre") or "Sin nombre")
    col2.metric("CUIT", resumen.get("cuit") or "Sin CUIT")
    col3.metric("Preparación", f"{resumen.get('porcentaje_preparacion', 0)}%")
    col4.metric("Faltantes críticos", int(resumen.get("faltantes_criticos", 0) or 0))

    if resumen.get("lista_para_operar"):
        st.success(resumen.get("mensaje", "La empresa tiene la base crítica para operar."))
    else:
        st.warning(resumen.get("mensaje", "La empresa todavía tiene faltantes críticos antes de operar."))

    st.divider()

    st.markdown("### Controles de preparación")

    if controles.empty:
        st.info("No hay controles para mostrar.")
    else:
        st.dataframe(
            preparar_vista(controles),
            use_container_width=True,
        )

    st.divider()

    st.markdown("### Recomendaciones")

    if not recomendaciones:
        st.success("No hay recomendaciones pendientes.")
    else:
        for recomendacion in recomendaciones:
            st.write(f"- {recomendacion}")

    st.divider()

    st.markdown("### Inicialización segura de empresa")

    st.warning(
        "Esta acción completa catálogos y configuraciones base faltantes. "
        "No borra datos, no elimina movimientos, no imputa comprobantes y no concilia bancos."
    )

    incluir_tesoreria = st.checkbox(
        "Incluir inicialización de Tesorería / Banco recomendada",
        value=True,
        help=(
            "Usa servicios existentes para asegurar medios de pago, cuentas bancarias recomendadas "
            "y configuración contable bancaria default cuando corresponda."
        ),
        key="config_estado_empresa_incluir_tesoreria",
    )

    if "confirmar_inicializar_empresa_operativa" not in st.session_state:
        st.session_state["confirmar_inicializar_empresa_operativa"] = False

    if st.button(
        "Inicializar / completar base operativa de esta empresa",
        type="primary",
        use_container_width=True,
        key="btn_inicializar_empresa_operativa",
    ):
        st.session_state["confirmar_inicializar_empresa_operativa"] = True

    if st.session_state["confirmar_inicializar_empresa_operativa"]:
        st.warning(
            "¿Confirmás inicializar datos base de la empresa activa? "
            "Se creará un backup antes de ejecutar."
        )

        c1, c2 = st.columns(2)

        with c1:
            if st.button(
                "Sí, inicializar empresa",
                type="primary",
                use_container_width=True,
                key="confirmar_si_inicializar_empresa",
            ):
                crear_backup_sqlite("antes_inicializar_empresa_operativa")

                resultado = inicializar_empresa_operativa(
                    empresa_id=empresa_id,
                    incluir_tesoreria=bool(incluir_tesoreria),
                )

                if resultado.get("ok"):
                    st.success(resultado.get("mensaje", "Empresa inicializada correctamente."))
                else:
                    st.warning(resultado.get("mensaje", "Inicialización parcial. Revisar detalle."))

                mostrar_pasos_inicializacion(resultado.get("pasos", []))

                st.session_state["confirmar_inicializar_empresa_operativa"] = False

                st.rerun()

        with c2:
            if st.button(
                "Cancelar",
                use_container_width=True,
                key="cancelar_inicializar_empresa",
            ):
                st.session_state["confirmar_inicializar_empresa_operativa"] = False
                st.rerun()


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
# La función mostrar_plan_cuentas() queda definida en la sección de servicio/plan PRO.

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