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
    crear_cuenta_empresa_desde_modelo,
    diagnosticar_plan_cuentas_unificado,
    listar_cuentas_empresa_unificadas,
    listar_estructura_maestra_plan_cuentas,
    listar_modelos_copiables_plan_cuentas,
    listar_versiones_plan_unificado,
    obtener_detalle_cuenta_maestra,
    vincular_plan_empresa_con_maestro_seguro,
    sugerir_comportamiento_plan,
)

from services.plan_cuentas_limpieza_demo_service import (
    CONFIRMACION_LIMPIEZA_DEMO,
    limpiar_plan_cuentas_demo_desde_maestro,
    previsualizar_limpieza_plan_cuentas_demo,
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


def _selector_version_plan_cuentas():
    versiones_todas = listar_versiones_plan_unificado()
    versiones = [
        item for item in versiones_todas
        if int(item.get("cuentas") or 0) > 0
    ]

    if not versiones:
        versiones = versiones_todas

    if not versiones:
        return "FF-PDF-2026-01"

    opciones = [
        f"{item['version']} — {item.get('estado') or ''} — {int(item.get('cuentas') or 0)} cuentas"
        for item in versiones
    ]

    indice = 0
    for i, item in enumerate(versiones):
        if str(item.get("version")) == "FF-PDF-2026-01":
            indice = i
            break

    seleccion = st.selectbox(
        "Versión estructural",
        opciones,
        index=indice,
        key="plan_unificado_version",
        help="Versión de la estructura madre del Plan de Cuentas.",
    )

    return seleccion.split("—", 1)[0].strip()


def _si_no(valor):
    try:
        return "Sí" if int(valor or 0) == 1 else "No"
    except Exception:
        return "No"


def _df_plan(filas):
    df = pd.DataFrame(filas or [])
    if df.empty:
        return df
    return df


def _mostrar_resumen_plan_unificado(empresa_id, version):
    diagnostico = diagnosticar_plan_cuentas_unificado(
        empresa_id=empresa_id,
        version=version,
    )

    if not diagnostico.get("ok"):
        st.error(diagnostico.get("error", "No se pudo diagnosticar el Plan de Cuentas."))
        return diagnostico

    total_empresa = int(diagnostico.get("total_empresa") or 0)
    vinculadas = int(diagnostico.get("vinculadas") or 0)
    creadas_modelo = int(diagnostico.get("creadas_desde_modelo_count") or 0)
    heredadas = int(diagnostico.get("heredadas_pendientes_count") or 0)

    col1, col2, col3, col4, col5, col6 = st.columns(6)
    col1.metric("Estructura maestra", diagnostico.get("total_maestro", 0))
    col2.metric("Catálogo actual", total_empresa)
    col3.metric("Desde modelos", creadas_modelo)
    col4.metric("Vinculadas", vinculadas)
    col5.metric("Heredadas / revisar", heredadas)
    col6.metric("Modelos copiables", diagnostico.get("modelos_copiables", 0))

    if heredadas:
        st.warning(
            "Hay cuentas heredadas pendientes de revisión. "
            "Deben vincularse al Plan Maestro, reemplazarse por cuentas creadas desde modelos "
            "o mantenerse solo como compatibilidad hasta analizar movimientos."
        )

    return diagnostico

def _mostrar_estructura_contable_maestra(version):
    st.markdown("#### Estructura contable")

    col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
    with col1:
        texto = st.text_input(
            "Buscar cuenta",
            key="plan_unificado_buscar_maestro",
            placeholder="Código, cuenta, rubro, subcuenta...",
        )
    with col2:
        elemento = st.selectbox(
            "Elemento",
            ["Todos", "ACTIVO", "PASIVO", "PATRIMONIO_NETO", "INGRESOS_GANANCIAS", "EGRESOS_GASTOS_PERDIDAS", "CUENTAS_MOVIMIENTO"],
            key="plan_unificado_elemento",
        )
    with col3:
        imputable = st.selectbox(
            "Imputable",
            ["Todas", "Sí", "No"],
            key="plan_unificado_imputable",
        )
    with col4:
        estado = st.selectbox(
            "Estado",
            ["Todas", "ACTIVA", "INACTIVA", "ANULADA", "BORRADOR"],
            key="plan_unificado_estado",
        )

    col1, col2 = st.columns([1, 1])
    with col1:
        regularizadora = st.selectbox(
            "Regularizadora",
            ["Todas", "Sí", "No"],
            key="plan_unificado_regularizadora",
        )
    with col2:
        solo_modelos = st.checkbox(
            "Solo cuentas modelo copiables",
            value=False,
            key="plan_unificado_solo_modelos",
        )

    filas = listar_estructura_maestra_plan_cuentas(
        version=version,
        texto=texto,
        elemento="" if elemento == "Todos" else elemento,
        imputable="" if imputable == "Todas" else imputable,
        estado="" if estado == "Todas" else estado,
        regularizadora="" if regularizadora == "Todas" else regularizadora,
        solo_modelos=solo_modelos,
    )

    df = _df_plan(filas)

    if df.empty:
        st.info("No hay cuentas para los filtros seleccionados.")
        return

    columnas = [
        "codigo",
        "nombre",
        "elemento",
        "rubro",
        "cuenta",
        "subcuenta",
        "codigo_madre",
        "nivel",
        "imputable",
        "saldo_normal",
        "es_regularizadora",
        "estado",
    ]
    for col in columnas:
        if col not in df.columns:
            df[col] = ""

    vista = df[columnas].copy()
    vista["imputable"] = vista["imputable"].apply(_si_no)
    vista["es_regularizadora"] = vista["es_regularizadora"].apply(_si_no)

    vista = vista.rename(
        columns={
            "codigo": "Código",
            "nombre": "Nombre de cuenta",
            "elemento": "Elemento",
            "rubro": "Rubro",
            "cuenta": "Cuenta contable",
            "subcuenta": "Subcuenta",
            "codigo_madre": "Código madre",
            "nivel": "Nivel",
            "imputable": "Imputable",
            "saldo_normal": "Saldo normal",
            "es_regularizadora": "Regularizadora",
            "estado": "Estado",
        }
    )

    st.caption(f"Cuentas mostradas: {len(vista)}")
    st.dataframe(preparar_vista(vista), use_container_width=True)

    with st.expander("Ver detalle técnico de las cuentas filtradas", expanded=False):
        cols_tecnicas = [
            "codigo",
            "nombre",
            "uso_operativo_sistema",
            "modulo_sugerido",
            "presentacion_estado_contable",
            "monetaria_no_monetaria",
            "criterio_medicion",
            "ajustable",
            "participa_recpam",
            "admite_moneda_extranjera",
            "requiere_tipo_cambio",
            "genera_diferencia_cambio",
        ]
        cols_tecnicas = [c for c in cols_tecnicas if c in df.columns]
        st.dataframe(preparar_vista(df[cols_tecnicas]), use_container_width=True)


def _mostrar_detalle_cuenta_maestra(version):
    st.markdown("#### Detalle contable de cuenta")

    texto = st.text_input(
        "Buscar cuenta para detalle",
        key="plan_unificado_detalle_buscar",
        placeholder="Ej.: Caja, Banco, IVA crédito fiscal, RECPAM...",
    )

    filas = listar_estructura_maestra_plan_cuentas(
        version=version,
        texto=texto,
        estado="ACTIVA",
    )

    if not filas:
        st.info("No hay cuentas para seleccionar.")
        return

    opciones = [f"{item['codigo']} — {item['nombre']}" for item in filas[:300]]
    seleccion = st.selectbox(
        "Cuenta",
        opciones,
        key="plan_unificado_detalle_cuenta",
    )

    codigo = seleccion.split("—", 1)[0].strip()
    cuenta = obtener_detalle_cuenta_maestra(
        codigo=codigo,
        version=version,
    )

    if not cuenta:
        st.warning("No se pudo obtener el detalle de la cuenta.")
        return

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Código", cuenta.get("codigo", ""))
    col2.metric("Elemento", cuenta.get("elemento", ""))
    col3.metric("Saldo normal", cuenta.get("saldo_normal", ""))
    col4.metric("Imputable", _si_no(cuenta.get("imputable")))

    st.markdown("##### Clasificación")
    c1, c2, c3 = st.columns(3)
    c1.write(f"**Rubro:** {cuenta.get('rubro') or '-'}")
    c2.write(f"**Cuenta:** {cuenta.get('cuenta') or '-'}")
    c3.write(f"**Subcuenta:** {cuenta.get('subcuenta') or '-'}")

    st.markdown("##### Significado del saldo")
    st.write(f"**Saldo normal:** {cuenta.get('significado_saldo_normal') or '-'}")
    st.write(f"**Saldo deudor:** {cuenta.get('significado_saldo_deudor') or '-'}")
    st.write(f"**Saldo acreedor:** {cuenta.get('significado_saldo_acreedor') or '-'}")

    c1, c2, c3 = st.columns(3)
    c1.write(f"**Permite saldo deudor:** {_si_no(cuenta.get('permite_saldo_deudor'))}")
    c2.write(f"**Permite saldo acreedor:** {_si_no(cuenta.get('permite_saldo_acreedor'))}")
    c3.write(f"**Alerta saldo invertido:** {_si_no(cuenta.get('alertar_saldo_invertido'))}")

    if int(cuenta.get("alertar_saldo_invertido") or 0) == 1:
        st.warning(
            "Tratamiento del saldo invertido: "
            f"{cuenta.get('tratamiento_saldo_invertido') or 'Revisar'}"
        )

    st.markdown("##### Regularizadora, medición y ajuste")
    c1, c2, c3, c4 = st.columns(4)
    c1.write(f"**Regularizadora:** {_si_no(cuenta.get('es_regularizadora'))}")
    c2.write(f"**Cuenta regularizada:** {cuenta.get('cuenta_regularizada_codigo') or '-'}")
    c3.write(f"**Ajustable:** {_si_no(cuenta.get('ajustable'))}")
    c4.write(f"**Participa RECPAM:** {_si_no(cuenta.get('participa_recpam'))}")

    st.write(f"**Criterio de medición:** {cuenta.get('criterio_medicion') or '-'}")

    with st.expander("Uso operativo técnico / automatización", expanded=False):
        st.caption("Este dato no define la estructura contable. Solo ayuda a automatización, mapeos, plantillas y diagnósticos.")
        st.write(f"**Uso operativo técnico:** {cuenta.get('uso_operativo_sistema') or '-'}")
        st.write(f"**Módulo sugerido:** {cuenta.get('modulo_sugerido') or '-'}")
        st.write(f"**Presentación estado contable:** {cuenta.get('presentacion_estado_contable') or '-'}")
        st.write(f"**Cuándo debitar:** {cuenta.get('cuando_debitar') or '-'}")
        st.write(f"**Cuándo acreditar:** {cuenta.get('cuando_acreditar') or '-'}")
        st.write(f"**Errores frecuentes:** {cuenta.get('errores_frecuentes') or '-'}")


def _mostrar_cuentas_empresa_unificadas(empresa_id, version):
    st.markdown("#### Cuentas de empresa / catálogo actual")

    st.caption(
        "Esta vista muestra el catálogo actual de la empresa. "
        "Las cuentas heredadas no son el destino final: deben revisarse y apuntarse al Plan Maestro FF."
    )

    filas = listar_cuentas_empresa_unificadas(
        empresa_id=empresa_id,
        version=version,
        solo_activas=False,
    )

    df = _df_plan(filas)

    if df.empty:
        st.info("La empresa todavía no tiene cuentas en el catálogo empresa.")
        return

    col1, col2 = st.columns([2, 1])
    with col1:
        texto = st.text_input("Buscar cuenta de empresa", key="plan_unificado_buscar_empresa")
    with col2:
        origenes = ["Todos"] + sorted([str(v) for v in df["estado_origen_plan"].dropna().unique()])
        origen = st.selectbox("Origen / estado", origenes, key="plan_unificado_origen_cuenta_empresa")

    vista = df.copy()

    if texto:
        patron = texto.lower().strip()
        vista = vista[
            vista["codigo"].astype(str).str.lower().str.contains(patron, na=False)
            | vista["nombre"].astype(str).str.lower().str.contains(patron, na=False)
        ]

    if origen != "Todos":
        vista = vista[vista["estado_origen_plan"] == origen]

    columnas = [
        "codigo",
        "nombre",
        "estado_origen_plan",
        "cuenta_maestro_vinculada",
        "elemento",
        "rubro",
        "saldo_normal",
        "imputable",
        "estado",
        "es_cuenta_especifica_empresa",
        "banco_nombre",
        "numero_cuenta",
        "moneda",
    ]
    for col in columnas:
        if col not in vista.columns:
            vista[col] = ""

    vista = vista[columnas].rename(
        columns={
            "codigo": "Código",
            "nombre": "Cuenta empresa",
            "estado_origen_plan": "Origen / estado",
            "cuenta_maestro_vinculada": "Cuenta maestra vinculada",
            "elemento": "Elemento",
            "rubro": "Rubro",
            "saldo_normal": "Saldo normal",
            "imputable": "Imputable",
            "estado": "Estado",
            "es_cuenta_especifica_empresa": "Específica empresa",
            "banco_nombre": "Banco",
            "numero_cuenta": "N° cuenta",
            "moneda": "Moneda",
        }
    )

    st.caption(f"Cuentas mostradas: {len(vista)}")
    st.dataframe(preparar_vista(vista), use_container_width=True)

    with st.expander("Qué significa cada origen", expanded=False):
        st.markdown(
            """
            - **CREADA_DESDE_MODELO:** cuenta nueva de la empresa creada desde una cuenta modelo del Plan Maestro.
            - **VINCULADA_AL_MAESTRO:** cuenta empresa relacionada con una cuenta del Plan Maestro.
            - **HEREDADA_MISMO_CODIGO_PENDIENTE:** cuenta heredada cuyo código coincide con una cuenta maestra, pendiente de vincular.
            - **HEREDADA_SIN_VINCULO:** cuenta heredada del sistema anterior sin vínculo directo con el nuevo Plan Maestro.
            - **VINCULO_INCONSISTENTE:** cuenta con vínculo roto o apuntando a una versión no válida.
            """
        )

def _sugerir_codigo_desde_modelo(codigo_modelo):
    codigo = str(codigo_modelo or "").strip()
    if not codigo:
        return ""

    partes = codigo.split(".")
    if partes and partes[-1].isdigit():
        partes[-1] = str(int(partes[-1]) + 1).zfill(len(partes[-1]))
        return ".".join(partes)

    return f"{codigo}.01"


def _mostrar_modelos_copiables(empresa_id, version):
    st.markdown("#### Modelos copiables")

    modelos = listar_modelos_copiables_plan_cuentas(version=version)
    df = _df_plan(modelos)

    if df.empty:
        st.info("No hay cuentas modelo copiables configuradas.")
        return

    columnas = [
        "codigo",
        "nombre",
        "elemento",
        "rubro",
        "saldo_normal",
        "uso_operativo_sistema",
        "permite_copiar_modelo",
        "estado",
    ]
    for col in columnas:
        if col not in df.columns:
            df[col] = ""

    vista = df[columnas].rename(
        columns={
            "codigo": "Código modelo",
            "nombre": "Cuenta modelo",
            "elemento": "Elemento",
            "rubro": "Rubro",
            "saldo_normal": "Saldo normal",
            "uso_operativo_sistema": "Uso técnico",
            "permite_copiar_modelo": "Permite copiar",
            "estado": "Estado",
        }
    )

    st.dataframe(preparar_vista(vista), use_container_width=True)

    st.markdown("##### Crear cuenta específica de empresa desde modelo")

    opciones = [
        f"{item['codigo']} — {item['nombre']}"
        for item in modelos
    ]

    seleccion = st.selectbox(
        "Cuenta modelo",
        opciones,
        key="plan_modelo_copiable_seleccion",
        help="La cuenta modelo define estructura, naturaleza, saldo normal y uso técnico. La nueva cuenta pertenece solo a la empresa activa.",
    )

    codigo_modelo = seleccion.split("—", 1)[0].strip()
    modelo = next((item for item in modelos if str(item.get("codigo")) == codigo_modelo), {})

    with st.form("form_crear_cuenta_desde_modelo"):
        st.caption(
            "Esta acción no modifica el Plan Maestro. Crea una cuenta propia de la empresa activa "
            "vinculada al modelo seleccionado."
        )

        col1, col2 = st.columns(2)

        with col1:
            codigo_nuevo = st.text_input(
                "Código nuevo para la empresa",
                value=_sugerir_codigo_desde_modelo(codigo_modelo),
                key="plan_modelo_codigo_nuevo",
                help="Debe ser único dentro de la empresa.",
            )
            nombre_nuevo = st.text_input(
                "Nombre de la cuenta específica",
                value="",
                placeholder="Ej.: Banco Macro Cta. Cte. 1234",
                key="plan_modelo_nombre_nuevo",
            )
            moneda = st.selectbox(
                "Moneda",
                ["ARS", "USD", "EUR", "OTRA"],
                key="plan_modelo_moneda",
            )

        with col2:
            banco_nombre = st.text_input(
                "Banco / entidad",
                value="",
                placeholder="Ej.: Banco Macro",
                key="plan_modelo_banco",
            )
            numero_cuenta = st.text_input(
                "Número de cuenta",
                value="",
                placeholder="Ej.: 1234",
                key="plan_modelo_numero_cuenta",
            )
            alias = st.text_input(
                "Alias / referencia",
                value="",
                key="plan_modelo_alias",
            )

        cbu = st.text_input(
            "CBU / CVU",
            value="",
            key="plan_modelo_cbu",
        )

        motivo = st.text_area(
            "Motivo",
            value="Alta de cuenta específica de empresa desde modelo del Plan Maestro.",
            key="plan_modelo_motivo",
        )

        crear = st.form_submit_button(
            "Crear cuenta de empresa desde modelo",
            use_container_width=True,
        )

        if crear:
            resultado = crear_cuenta_empresa_desde_modelo(
                empresa_id=empresa_id,
                codigo_modelo=codigo_modelo,
                codigo_nuevo=codigo_nuevo,
                nombre_nuevo=nombre_nuevo,
                banco_nombre=banco_nombre,
                numero_cuenta=numero_cuenta,
                moneda=moneda,
                alias=alias,
                cbu=cbu,
                motivo=motivo,
                usuario=_usuario_actual_nombre(),
                version=version,
            )

            if resultado.get("ok"):
                st.success(
                    "Cuenta creada correctamente para la empresa. "
                    f"Código: {resultado.get('codigo')}."
                )
                st.rerun()
            else:
                st.error("No se pudo crear la cuenta: " + "; ".join(resultado.get("errores", [])))

    with st.expander("Detalle del modelo seleccionado", expanded=False):
        if modelo:
            st.write(f"**Código modelo:** {modelo.get('codigo')}")
            st.write(f"**Cuenta modelo:** {modelo.get('nombre')}")
            st.write(f"**Elemento:** {modelo.get('elemento')}")
            st.write(f"**Rubro:** {modelo.get('rubro')}")
            st.write(f"**Saldo normal:** {modelo.get('saldo_normal')}")
            st.write(f"**Uso técnico:** {modelo.get('uso_operativo_sistema') or '-'}")
            st.write(f"**Significado del saldo:** {modelo.get('significado_saldo_normal') or '-'}")

def _mostrar_vinculacion_plan(empresa_id, version):
    st.markdown("#### Vinculación maestro ↔ empresa")

    diagnostico = diagnosticar_plan_cuentas_unificado(
        empresa_id=empresa_id,
        version=version,
    )

    if not diagnostico.get("ok"):
        st.error(diagnostico.get("error", "No se pudo diagnosticar la vinculación."))
        return

    pendientes = diagnostico.get("pendientes_vincular", [])
    propias = diagnostico.get("propias_empresa", [])

    st.caption(
        "La vinculación segura solo completa la relación entre cuentas de empresa y cuentas maestras "
        "cuando el código coincide exactamente. No crea, no borra, no renombra y no modifica asientos."
    )

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("##### Pendientes de vincular por código exacto")
        if pendientes:
            st.dataframe(preparar_vista(pd.DataFrame(pendientes)), use_container_width=True)
        else:
            st.success("No hay cuentas pendientes de vincular por código exacto.")

    with col2:
        st.markdown("##### Cuentas propias de empresa")
        if propias:
            st.dataframe(preparar_vista(pd.DataFrame(propias)), use_container_width=True)
        else:
            st.success("No hay cuentas propias de empresa fuera del maestro.")

    if pendientes:
        confirmar = st.checkbox(
            "Confirmo vincular solo cuentas con código exacto",
            value=False,
            key="plan_unificado_confirmar_vincular",
        )

        if st.button(
            "Vincular cuentas por código exacto",
            disabled=not confirmar,
            use_container_width=True,
            key="plan_unificado_boton_vincular",
        ):
            resultado = vincular_plan_empresa_con_maestro_seguro(
                empresa_id=empresa_id,
                version=version,
                usuario=_usuario_actual_nombre(),
            )

            if resultado.get("ok"):
                st.success(
                    "Vinculación aplicada. "
                    f"Cuentas vinculadas: {resultado.get('cuentas_vinculadas', 0)}."
                )
                st.rerun()
            else:
                st.error(resultado.get("error", "No se pudo aplicar la vinculación."))


def _mostrar_uso_tecnico_plan(empresa_id):
    st.markdown("#### Uso operativo técnico y mapeos")

    st.caption(
        "Esta sección es avanzada. No define la estructura contable visible; "
        "solo muestra vínculos técnicos que usan automatizaciones, diagnósticos y plantillas."
    )

    try:
        from services.plan_cuentas_maestro_service import listar_mapeos_empresa
        mapeos = listar_mapeos_empresa(empresa_id=empresa_id, solo_activos=True)
    except Exception as exc:
        st.error(f"No se pudieron leer los mapeos técnicos: {exc}")
        return

    if not mapeos:
        st.info("No hay mapeos técnicos activos para esta empresa.")
        return

    df = pd.DataFrame(mapeos)
    st.dataframe(preparar_vista(df), use_container_width=True)


def _mostrar_herramientas_compatibilidad_plan(empresa_id):
    st.markdown("#### Herramientas de compatibilidad temporal")

    st.warning(
        "Estas opciones son heredadas. Se mantienen para no romper el sistema actual, "
        "pero no son el flujo principal del Plan de Cuentas definitivo."
    )

    with st.expander("Importar o reemplazar catálogo heredado", expanded=False):
        archivo = st.file_uploader(
            "CSV de plan de cuentas",
            type=["csv"],
            key="plan_unificado_upload_compatibilidad",
        )

        if archivo is not None:
            df = leer_csv_configuracion(archivo)
            df = normalizar_columnas(df)
            st.dataframe(preparar_vista(df.head(30)), use_container_width=True)

            columnas = set(df.columns)
            if {"cuenta", "detalle"}.issubset(columnas):
                tipo_plan = "detallado"
                st.success("Formato detectado: estructurado.")
            elif {"codigo", "nombre"}.issubset(columnas):
                tipo_plan = "simple"
                st.success("Formato detectado: simple.")
            else:
                tipo_plan = None
                st.error("No se reconoció el formato. Debe tener cuenta/detalle o codigo/nombre.")

            confirmar = st.checkbox(
                "Confirmo que quiero reemplazar el catálogo heredado de la empresa",
                value=False,
                key="plan_unificado_confirmar_reemplazo_heredado",
            )

            if tipo_plan and st.button(
                "Reemplazar catálogo heredado",
                disabled=not confirmar,
                use_container_width=True,
                key="plan_unificado_reemplazar_heredado",
            ):
                resultado = reemplazar_plan_desde_dataframe(
                    df,
                    empresa_id=empresa_id,
                    formato=tipo_plan,
                    usuario=_usuario_actual_nombre(),
                    motivo="Reemplazo de catálogo heredado desde Plan de Cuentas unificado",
                )

                if resultado.get("ok"):
                    st.success(f"Catálogo reemplazado. Cuentas procesadas: {resultado.get('procesadas', 0)}.")
                    st.rerun()
                else:
                    st.error("No se pudo reemplazar: " + "; ".join(resultado.get("errores", [])))

    with st.expander("Borrar catálogo heredado", expanded=False):
        st.error(
            "No usar salvo limpieza administrativa controlada. "
            "No borra Libro Diario ni movimientos, pero sí borra el catálogo heredado de la empresa."
        )

        confirmar = st.text_input(
            "Para borrar escribí BORRAR PLAN",
            key="plan_unificado_confirmar_borrar_heredado",
        )

        if st.button(
            "Borrar catálogo heredado",
            disabled=confirmar != "BORRAR PLAN",
            use_container_width=True,
            key="plan_unificado_borrar_heredado",
        ):
            resultado = borrar_plan_cuentas_completo(
                empresa_id=empresa_id,
                usuario=_usuario_actual_nombre(),
                motivo="Borrado de catálogo heredado desde Plan de Cuentas unificado",
            )

            if resultado.get("ok"):
                st.success("Catálogo heredado borrado.")
                st.rerun()
            else:
                st.error("No se pudo borrar: " + "; ".join(resultado.get("errores", [])))


def _mostrar_limpieza_demo_plan(empresa_id):
    st.markdown("#### Limpieza demo del Plan de Cuentas")

    st.error(
        "Herramienta exclusiva para demo/base de prueba. "
        "Elimina el catálogo actual de cuentas de empresa y lo reconstruye desde el Plan Maestro FF. "
        "No debe usarse sobre una base productiva real."
    )

    st.caption(
        "Esta acción apunta a sacar de raíz las cuentas heredadas del demo. "
        "Antes de ejecutar crea backups internos de las tablas afectadas y limpia referencias técnicas "
        "en mapeos, categorías de compra y conceptos fiscales de compra."
    )

    resultado_key = f"plan_limpieza_demo_resultado_{empresa_id}"

    if st.session_state.get(resultado_key):
        resultado_anterior = st.session_state[resultado_key]
        st.success("Última limpieza demo ejecutada correctamente.")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Cuentas antes", resultado_anterior.get("cuentas_antes", 0))
        c2.metric("Eliminadas", resultado_anterior.get("cuentas_eliminadas", 0))
        c3.metric("Reconstruidas", resultado_anterior.get("cuentas_reconstruidas", 0))
        c4.metric("Backups", len(resultado_anterior.get("backups", [])))

        with st.expander("Ver resultado técnico de la última limpieza", expanded=False):
            st.json(resultado_anterior)

        if st.button(
            "Ocultar resultado anterior",
            key="plan_limpieza_demo_ocultar_resultado",
            use_container_width=True,
        ):
            st.session_state.pop(resultado_key, None)
            st.rerun()

    st.divider()

    try:
        preview = previsualizar_limpieza_plan_cuentas_demo(empresa_id=empresa_id)
    except Exception as exc:
        st.error("No se pudo previsualizar la limpieza demo del Plan de Cuentas.")
        st.exception(exc)
        return

    if not preview.get("ok"):
        st.error(preview.get("error", "No se pudo previsualizar la limpieza demo."))
        return

    st.markdown("##### Previsualización")

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Catálogo empresa actual", preview.get("total_plan_empresa_actual", 0))
    col2.metric("Plan Maestro activo", preview.get("total_plan_maestro_activo", 0))
    col3.metric("Vinculadas", preview.get("cuentas_vinculadas_al_maestro", 0))
    col4.metric("No vinculadas", preview.get("cuentas_no_vinculadas", 0))
    col5.metric("Específicas empresa", preview.get("cuentas_especificas_empresa", 0))

    st.warning(
        "Al ejecutar, el catálogo actual de cuentas de esta empresa se eliminará y se reconstruirá "
        "desde las cuentas activas del Plan Maestro FF. "
        "También se limpiarán referencias técnicas que apunten a las cuentas eliminadas."
    )

    with st.expander("Qué tablas se afectan", expanded=False):
        st.markdown(
            """
            - `plan_cuentas_empresa`: se elimina y reconstruye para la empresa activa.
            - `mapeos_contables_empresa`: se eliminan mapeos vinculados al catálogo anterior.
            - `categorias_compra_config`: se limpian cuentas sugeridas anteriores.
            - `conceptos_fiscales_compra_config`: se limpian cuentas sugeridas anteriores.
            - `auditoria_cambios`: se registra el evento de limpieza.
            """
        )

    st.divider()

    st.markdown("##### Confirmación de limpieza demo")

    motivo = st.text_area(
        "Motivo obligatorio",
        value="Limpieza radical demo: reconstrucción desde Plan Maestro FF",
        key="plan_limpieza_demo_motivo",
        help="Queda registrado en auditoría.",
    )

    confirmacion = st.text_input(
        f"Para ejecutar escribí exactamente: {CONFIRMACION_LIMPIEZA_DEMO}",
        key="plan_limpieza_demo_confirmacion",
    )

    crear_backup = st.checkbox(
        "Crear backup interno antes de limpiar",
        value=True,
        key="plan_limpieza_demo_crear_backup",
    )

    puede_ejecutar = (
        confirmacion == CONFIRMACION_LIMPIEZA_DEMO
        and bool(str(motivo or "").strip())
    )

    if st.button(
        "Ejecutar limpieza demo y reconstruir desde Plan Maestro FF",
        type="primary",
        disabled=not puede_ejecutar,
        use_container_width=True,
        key="plan_limpieza_demo_ejecutar",
    ):
        try:
            resultado = limpiar_plan_cuentas_demo_desde_maestro(
                empresa_id=empresa_id,
                confirmacion=confirmacion,
                usuario=_usuario_actual_nombre(),
                motivo=motivo,
                crear_backup=crear_backup,
            )
        except Exception as exc:
            st.error("No se pudo ejecutar la limpieza demo del Plan de Cuentas.")
            st.exception(exc)
            return

        st.session_state[resultado_key] = resultado
        st.rerun()


def _mostrar_auditoria_plan_unificado(empresa_id):
    st.markdown("#### Auditoría del Plan de Cuentas")

    eventos = listar_eventos_plan_cuentas(empresa_id=empresa_id, limite=300)

    if not eventos:
        st.info("Todavía no hay eventos registrados para el Plan de Cuentas de esta empresa.")
        return

    st.dataframe(preparar_vista(pd.DataFrame(eventos)), use_container_width=True)


def mostrar_plan_cuentas():
    st.subheader("Plan de Cuentas")

    st.info(
        "El Plan de Cuentas es una sola estructura: el Plan Maestro FF actúa como base contable madre "
        "y las cuentas de empresa son su adaptación operativa. "
        "El uso operativo queda como dato técnico avanzado para automatización, mapeos y plantillas."
    )

    empresa_id = _empresa_id_actual()
    asegurar_estructura_plan_cuentas()
    version = _selector_version_plan_cuentas()

    diagnostico = _mostrar_resumen_plan_unificado(empresa_id, version)

    if diagnostico and diagnostico.get("pendientes_vincular_count", 0):
        st.warning(
            "Hay cuentas de empresa con el mismo código que el maestro pendientes de vincular. "
            "Podés revisarlas en la pestaña Vinculación."
        )

    tabs = st.tabs([
        "📚 Estructura contable",
        "🔎 Detalle de cuenta",
        "🏢 Cuentas de empresa",
        "🧩 Modelos copiables",
        "🔗 Vinculación",
        "🕓 Auditoría",
        "🧹 Limpieza demo",
        "🧰 Avanzado",
    ])

    with tabs[0]:
        _mostrar_estructura_contable_maestra(version)

    with tabs[1]:
        _mostrar_detalle_cuenta_maestra(version)

    with tabs[2]:
        _mostrar_cuentas_empresa_unificadas(empresa_id, version)

    with tabs[3]:
        _mostrar_modelos_copiables(empresa_id, version)

    with tabs[4]:
        _mostrar_vinculacion_plan(empresa_id, version)

    with tabs[5]:
        _mostrar_auditoria_plan_unificado(empresa_id)

    with tabs[6]:
        _mostrar_limpieza_demo_plan(empresa_id)

    with tabs[7]:
        st.markdown("#### Administración avanzada")
        st.caption(
            "Estas opciones no forman parte de la estructura contable visible. "
            "Se reservan para automatización, compatibilidad y mantenimiento controlado."
        )
        with st.expander("Uso operativo técnico y mapeos", expanded=False):
            _mostrar_uso_tecnico_plan(empresa_id)
        with st.expander("Compatibilidad temporal", expanded=False):
            _mostrar_herramientas_compatibilidad_plan(empresa_id)



def obtener_plan_simple():
    """
    Adaptador interno para pantallas de configuración que todavía necesitan
    un selector simple de cuentas.

    Fuente principal:
    - cuentas de empresa vinculadas al Plan Maestro;
    - cuentas creadas desde modelos.

    Fuente temporal:
    - cuentas heredadas, solo si todavía no existen cuentas nuevas/vinculadas.
    """
    empresa_id = _empresa_id_actual()

    try:
        cuentas_empresa = listar_cuentas_empresa_unificadas(
            empresa_id=empresa_id,
            solo_activas=False,
        )
    except Exception:
        cuentas_empresa = []

    filas_nuevas = []
    filas_heredadas = []

    for cuenta in cuentas_empresa or []:
        codigo = str(cuenta.get("codigo") or "").strip()
        nombre = str(cuenta.get("nombre") or "").strip()

        if not codigo or not nombre:
            continue

        estado = str(cuenta.get("estado") or "").strip().upper()
        if estado == "ANULADA":
            continue

        origen = str(cuenta.get("estado_origen_plan") or "").strip().upper()

        fila = {
            "codigo": codigo,
            "nombre": nombre,
            "cuenta": codigo,
            "detalle": nombre,
            "imputable": "S" if int(cuenta.get("imputable") or 0) == 1 else "N",
            "estado": estado or "ACTIVA",
            "origen": origen or "SIN_CLASIFICAR",
        }

        if origen in {"CREADA_DESDE_MODELO", "VINCULADA_AL_MAESTRO"}:
            filas_nuevas.append(fila)
        else:
            filas_heredadas.append(fila)

    filas = filas_nuevas if filas_nuevas else filas_heredadas

    if not filas:
        try:
            cuentas_heredadas = listar_plan_cuentas(empresa_id=empresa_id)
        except Exception:
            cuentas_heredadas = []

        for cuenta in cuentas_heredadas or []:
            codigo = str(cuenta.get("codigo") or "").strip()
            nombre = str(cuenta.get("nombre") or "").strip()

            if not codigo or not nombre:
                continue

            filas.append(
                {
                    "codigo": codigo,
                    "nombre": nombre,
                    "cuenta": codigo,
                    "detalle": nombre,
                    "imputable": str(cuenta.get("imputable") or "S").strip().upper(),
                    "estado": "ACTIVA",
                    "origen": "CATALOGO_HEREDADO",
                }
            )

    columnas = ["codigo", "nombre", "cuenta", "detalle", "imputable", "estado", "origen"]
    df = pd.DataFrame(filas)

    if df.empty:
        return pd.DataFrame(columns=columnas)

    for columna in columnas:
        if columna not in df.columns:
            df[columna] = ""

    df = df[columnas].drop_duplicates(subset=["codigo"], keep="first")
    df = df.sort_values("codigo").reset_index(drop=True)

    return df

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
    from modulos.inicio_empresa_componentes import mostrar_estado_empresa_operativa_adaptativo

    mostrar_estado_empresa_operativa_adaptativo(
        empresa_actual_id=empresa_actual_id,
        obtener_resumen_empresa_operativa=obtener_resumen_empresa_operativa,
        preparar_controles_empresa_para_vista=preparar_controles_empresa_para_vista,
        obtener_recomendaciones_empresa=obtener_recomendaciones_empresa,
        inicializar_empresa_operativa=inicializar_empresa_operativa,
        crear_backup_sqlite=crear_backup_sqlite,
        preparar_vista=preparar_vista,
        mostrar_pasos_inicializacion=mostrar_pasos_inicializacion,
    )


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
