import json
from datetime import date

import pandas as pd
import streamlit as st

from database import ejecutar_query, archivo_ya_cargado
from services.compras_service import (
    procesar_csv_compras_arca,
    procesar_compra_manual,
    es_csv_arca_compras,
    asegurar_columnas_compras_v2
)

from services.clasificacion_compras_service import (
    construir_detalle_preclasificacion,
    construir_resumen_por_proveedor,
    aplicar_categorias_y_excepciones,
    resumen_final_por_categoria,
    guardar_categoria_habitual_proveedores,
    nombre_archivo_interno,
    key_segura
)

from core.fechas import ordenar_dataframe_por_fecha, fecha_para_ordenar, formatear_fecha
from core.exportadores import exportar_excel
from core.ui import preparar_vista
from core.numeros import moneda


# ======================================================
# CONSULTAS AUXILIARES
# ======================================================

def obtener_categorias_activas():
    try:
        return ejecutar_query("""
            SELECT 
                categoria,
                cuenta_codigo,
                cuenta_nombre,
                cuenta_proveedor_codigo,
                cuenta_proveedor_nombre,
                tipo_categoria,
                tratamiento_iva,
                porcentaje_iva_computable
            FROM categorias_compra
            WHERE activo = 1
            ORDER BY categoria
        """, fetch=True)
    except Exception:
        return ejecutar_query("""
            SELECT 
                categoria,
                cuenta_codigo,
                cuenta_nombre,
                cuenta_proveedor_codigo,
                cuenta_proveedor_nombre,
                tipo_categoria
            FROM categorias_compra
            WHERE activo = 1
            ORDER BY categoria
        """, fetch=True)


def obtener_tipos_comprobantes():
    return ejecutar_query("""
        SELECT codigo, descripcion, signo
        FROM tipos_comprobantes
        ORDER BY CAST(codigo AS INTEGER)
    """, fetch=True)


def archivo_preclasificado_ya_cargado(nombre_archivo):
    try:
        df = ejecutar_query("""
            SELECT id
            FROM historial_cargas
            WHERE nombre_archivo = ?
               OR nombre_archivo LIKE ?
            LIMIT 1
        """, (nombre_archivo, f"{nombre_archivo}__%"), fetch=True)

        return not df.empty
    except Exception:
        return archivo_ya_cargado(nombre_archivo)


def rerun_app():
    try:
        st.rerun()
    except Exception:
        try:
            st.experimental_rerun()
        except Exception:
            pass


# ======================================================
# ESTADO STREAMLIT
# ======================================================

def obtener_claves_estado(nombre_archivo):
    base_key = f"compras_clasificacion_{key_segura(nombre_archivo)}"

    return {
        "base_key": base_key,
        "categorias_key": f"{base_key}_categorias",
        "confirmados_key": f"{base_key}_confirmados",
        "excepciones_key": f"{base_key}_excepciones",
        "abiertos_key": f"{base_key}_abiertos",
        "seleccionados_key": f"{base_key}_seleccionados",
    }


def reset_flag_key(nombre_archivo):
    return f"reset_clasificacion_compras_{key_segura(nombre_archivo)}"


def limpiar_estado_clasificacion(nombre_archivo):
    estado = obtener_claves_estado(nombre_archivo)
    base_key = estado["base_key"]

    claves_a_borrar = []

    for clave in list(st.session_state.keys()):
        clave_texto = str(clave)

        if clave_texto.startswith(base_key):
            claves_a_borrar.append(clave)

        if clave_texto.startswith(f"categoria_proveedor_{base_key}_"):
            claves_a_borrar.append(clave)

        if clave_texto.startswith(f"categoria_factura_{base_key}_"):
            claves_a_borrar.append(clave)

        if clave_texto.startswith(f"ver_facturas_{base_key}_"):
            claves_a_borrar.append(clave)

        if clave_texto.startswith(f"confirmar_proveedor_{base_key}_"):
            claves_a_borrar.append(clave)

        if clave_texto.startswith(f"modificar_confirmado_{base_key}_"):
            claves_a_borrar.append(clave)

    for clave in set(claves_a_borrar):
        try:
            del st.session_state[clave]
        except Exception:
            pass


def aplicar_reset_pendiente(nombre_archivo):
    """
    Este reset no aparece como botón visible.
    Se activa automáticamente cuando Estado de Cargas elimina ese archivo.
    Sirve para evitar que Streamlit mantenga en memoria una clasificación vieja
    del mismo archivo recién eliminado.
    """

    flag = reset_flag_key(nombre_archivo)

    if st.session_state.get(flag, False):
        limpiar_estado_clasificacion(nombre_archivo)

        try:
            del st.session_state[flag]
        except Exception:
            pass


# ======================================================
# RESULTADOS / AUDITORÍA
# ======================================================

def resultado_vacio():
    return {
        "procesados": 0,
        "errores": 0,
        "advertencias": 0,
        "facturas": 0,
        "notas_credito": 0,
        "notas_debito": 0,
        "duplicados": 0,
        "errores_matematicos": 0,
        "errores_codigo": 0,
        "ajustes_centavos": 0,
        "iva_no_computable": 0,
        "diferencias_iva_csv_sistema": 0,
        "comprobantes_sin_iva_discriminado": 0
    }


def acumular_resultado(total, parcial):
    for clave, valor in parcial.items():
        if isinstance(valor, (int, float)):
            total[clave] = total.get(clave, 0) + valor

    return total


def asegurar_tabla_advertencias():
    try:
        ejecutar_query("""
            CREATE TABLE IF NOT EXISTS advertencias_carga (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                modulo TEXT,
                archivo TEXT,
                fila INTEGER,
                motivo TEXT,
                contenido TEXT,
                fecha_carga TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    except Exception:
        pass


def obtener_auditoria_archivo(nombre_archivo):
    asegurar_tabla_advertencias()

    errores = ejecutar_query("""
        SELECT fecha, modulo, archivo, fila, motivo, contenido
        FROM errores_carga
        WHERE archivo = ?
           OR archivo LIKE ?
        ORDER BY id DESC
    """, (nombre_archivo, f"{nombre_archivo}__%"), fetch=True)

    try:
        advertencias = ejecutar_query("""
            SELECT fecha_carga AS fecha, modulo, archivo, fila, motivo, contenido
            FROM advertencias_carga
            WHERE archivo = ?
               OR archivo LIKE ?
            ORDER BY id DESC
        """, (nombre_archivo, f"{nombre_archivo}__%"), fetch=True)
    except Exception:
        advertencias = pd.DataFrame(columns=["fecha", "modulo", "archivo", "fila", "motivo", "contenido"])

    return errores, advertencias


def preparar_auditoria_vista(df):
    if df.empty:
        return df

    filas = []

    for _, row in df.iterrows():
        contenido = row.get("contenido", "")
        normalizado = {}

        try:
            data = json.loads(contenido)
            normalizado = data.get("_normalizado", {})
        except Exception:
            normalizado = {}

        filas.append({
            "fecha": row.get("fecha", ""),
            "archivo": row.get("archivo", ""),
            "fila": row.get("fila", ""),
            "motivo": row.get("motivo", ""),
            "codigo": normalizado.get("codigo", ""),
            "numero": normalizado.get("numero", ""),
            "proveedor": normalizado.get("proveedor", ""),
            "cuit": normalizado.get("cuit", ""),
            "total": normalizado.get("total", ""),
            "categoria": normalizado.get("categoria_compra", "")
        })

    return pd.DataFrame(filas)


def mostrar_auditoria_archivo(nombre_archivo):
    errores, advertencias = obtener_auditoria_archivo(nombre_archivo)

    st.subheader("Auditoría de la carga")

    col1, col2 = st.columns(2)
    col1.metric("Errores detallados", len(errores))
    col2.metric("Advertencias detalladas", len(advertencias))

    if errores.empty and advertencias.empty:
        st.success("No hay errores ni advertencias registradas para esta carga.")
        return

    if not errores.empty:
        with st.expander("Ver errores detectados", expanded=True):
            st.dataframe(
                preparar_vista(preparar_auditoria_vista(errores)),
                use_container_width=True
            )

    if not advertencias.empty:
        with st.expander("Ver advertencias detectadas", expanded=True):
            st.dataframe(
                preparar_vista(preparar_auditoria_vista(advertencias)),
                use_container_width=True
            )


def mostrar_resumen_resultado(resultado):
    st.success("Proceso finalizado")

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Procesados", resultado.get("procesados", 0))
    col2.metric("Errores", resultado.get("errores", 0))
    col3.metric("Advertencias", resultado.get("advertencias", 0))
    col4.metric("Duplicados omitidos", resultado.get("duplicados", 0))

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Facturas", resultado.get("facturas", 0))
    col2.metric("Notas Crédito", resultado.get("notas_credito", 0))
    col3.metric("Notas Débito", resultado.get("notas_debito", 0))
    col4.metric("Ajustes centavos", resultado.get("ajustes_centavos", 0))

    with st.expander("Detalle técnico del proceso", expanded=False):
        st.write(f"Errores matemáticos: {resultado.get('errores_matematicos', 0)}")
        st.write(f"Códigos inexistentes: {resultado.get('errores_codigo', 0)}")
        st.write(f"IVA no computable detectado: {resultado.get('iva_no_computable', 0)}")
        st.write(f"Diferencias IVA Portal/Sistema: {resultado.get('diferencias_iva_csv_sistema', 0)}")
        st.write(
            "Comprobantes sin IVA discriminado: "
            f"{resultado.get('comprobantes_sin_iva_discriminado', 0)}"
        )

    if resultado.get("errores", 0) > 0:
        st.warning("Se detectaron errores. Abajo se muestra el detalle.")

    if resultado.get("advertencias", 0) > 0:
        st.info("Se generaron advertencias. Abajo se muestra el detalle.")


# ======================================================
# CLASIFICACIÓN
# ======================================================

def inicializar_estado_clasificacion(nombre_archivo, df_detalle_base):
    estado = obtener_claves_estado(nombre_archivo)

    if estado["categorias_key"] not in st.session_state:
        resumen = construir_resumen_por_proveedor(df_detalle_base)

        st.session_state[estado["categorias_key"]] = {
            str(fila["clave_proveedor"]): str(fila["categoria_compra"])
            for _, fila in resumen.iterrows()
        }

    if estado["confirmados_key"] not in st.session_state:
        st.session_state[estado["confirmados_key"]] = set()

    if estado["excepciones_key"] not in st.session_state:
        st.session_state[estado["excepciones_key"]] = {}

    if estado["abiertos_key"] not in st.session_state:
        st.session_state[estado["abiertos_key"]] = {}

    if estado["seleccionados_key"] not in st.session_state:
        st.session_state[estado["seleccionados_key"]] = []

    return estado


def obtener_df_final_clasificado(df_detalle_base, estado):
    categorias_por_proveedor = st.session_state[estado["categorias_key"]]
    excepciones = st.session_state[estado["excepciones_key"]]

    return aplicar_categorias_y_excepciones(
        df_detalle_base,
        categorias_por_proveedor,
        excepciones
    )


def mostrar_facturas_de_proveedor(
    clave,
    df_detalle_base,
    estado,
    categorias_disponibles
):
    categorias_por_proveedor = st.session_state[estado["categorias_key"]]
    excepciones = st.session_state[estado["excepciones_key"]]

    categoria_general = categorias_por_proveedor.get(clave, categorias_disponibles[0])

    df_actual = obtener_df_final_clasificado(df_detalle_base, estado)
    df_proveedor = df_actual[df_actual["clave_proveedor"].astype(str) == clave].copy()

    if df_proveedor.empty:
        st.info("Este proveedor no tiene comprobantes para mostrar.")
        return

    st.caption("Facturas del proveedor. Cambiá solo las excepciones.")

    for _, factura in df_proveedor.iterrows():
        idx_original = int(factura["idx_original"])
        idx_key = str(idx_original)

        categoria_actual = excepciones.get(idx_key, categoria_general)

        if categoria_actual not in categorias_disponibles:
            categoria_actual = categoria_general

        col1, col2, col3, col4 = st.columns([1.1, 1.4, 1.2, 2.1])

        with col1:
            st.write(f"**{factura['fecha']}**")
            st.caption(f"Cód. {factura['codigo']}")

        with col2:
            st.write(factura["numero"])

        with col3:
            st.write(moneda(float(factura["total"])))

        with col4:
            nueva_categoria = st.selectbox(
                "Categoría factura",
                categorias_disponibles,
                index=categorias_disponibles.index(categoria_actual),
                key=f"categoria_factura_{estado['base_key']}_{idx_original}",
                label_visibility="collapsed"
            )

            if nueva_categoria != categoria_general:
                excepciones[idx_key] = nueva_categoria
            else:
                if idx_key in excepciones:
                    del excepciones[idx_key]


def mostrar_acciones_masivas(
    pendientes,
    estado,
    categorias_disponibles
):
    categorias_por_proveedor = st.session_state[estado["categorias_key"]]
    confirmados = st.session_state[estado["confirmados_key"]]

    if pendientes.empty:
        return

    opciones = {}
    etiquetas = []

    for _, fila in pendientes.iterrows():
        clave = str(fila["clave_proveedor"])
        etiqueta = (
            f"{fila['proveedor']} | CUIT {fila['cuit']} | "
            f"{int(fila['comprobantes'])} comp. | {moneda(float(fila['total']))}"
        )
        opciones[etiqueta] = clave
        etiquetas.append(etiqueta)

    seleccionados_key = estado["seleccionados_key"]

    if seleccionados_key not in st.session_state:
        st.session_state[seleccionados_key] = []

    st.session_state[seleccionados_key] = [
        item for item in st.session_state[seleccionados_key]
        if item in etiquetas
    ]

    st.subheader("Acciones rápidas")

    b1, b2, b3 = st.columns(3)

    with b1:
        if st.button("Seleccionar todos visibles"):
            st.session_state[seleccionados_key] = etiquetas
            rerun_app()

    with b2:
        if st.button("Limpiar selección"):
            st.session_state[seleccionados_key] = []
            rerun_app()

    with b3:
        if st.button("Confirmar todos visibles"):
            for etiqueta in etiquetas:
                clave = opciones[etiqueta]
                confirmados.add(clave)
            rerun_app()

    col1, col2 = st.columns([2, 1])

    with col1:
        seleccionados = st.multiselect(
            "Proveedores seleccionados",
            etiquetas,
            key=seleccionados_key
        )

    with col2:
        categoria_masiva = st.selectbox(
            "Categoría para selección",
            categorias_disponibles,
            key=f"categoria_masiva_{estado['base_key']}"
        )

    claves_seleccionadas = [opciones[e] for e in seleccionados]

    c1, c2, c3 = st.columns(3)

    with c1:
        if st.button("Aplicar categoría"):
            if not claves_seleccionadas:
                st.warning("Seleccioná al menos un proveedor.")
            else:
                for clave in claves_seleccionadas:
                    categorias_por_proveedor[clave] = categoria_masiva
                st.success("Categoría aplicada.")
                rerun_app()

    with c2:
        if st.button("Aplicar y confirmar"):
            if not claves_seleccionadas:
                st.warning("Seleccioná al menos un proveedor.")
            else:
                for clave in claves_seleccionadas:
                    categorias_por_proveedor[clave] = categoria_masiva
                    confirmados.add(clave)
                st.success("Categoría aplicada y proveedores confirmados.")
                rerun_app()

    with c3:
        if st.button("Confirmar alta confianza"):
            cantidad = 0
            for _, fila in pendientes.iterrows():
                clave = str(fila["clave_proveedor"])
                confianza = str(fila.get("confianza_sugerencia", ""))
                origen = str(fila.get("origen_sugerencia", ""))

                if confianza == "ALTA" and origen != "SIN HISTORIAL":
                    confirmados.add(clave)
                    cantidad += 1

            if cantidad == 0:
                st.info("No hay proveedores con sugerencia de alta confianza pendientes.")
            else:
                st.success(f"Se confirmaron {cantidad} proveedores.")
                rerun_app()


def aplicar_filtros_pendientes(pendientes):
    if pendientes.empty:
        return pendientes

    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        buscar = st.text_input("Buscar proveedor o CUIT", placeholder="Ej: AMERICAN, 3071...")

    with col2:
        origenes = ["Todos"] + sorted(pendientes["origen_sugerencia"].dropna().unique().tolist())
        origen = st.selectbox("Origen", origenes)

    with col3:
        confianzas = ["Todas"] + sorted(pendientes["confianza_sugerencia"].dropna().unique().tolist())
        confianza = st.selectbox("Confianza", confianzas)

    df = pendientes.copy()

    if buscar.strip():
        b = buscar.strip().upper()
        df = df[
            df["proveedor"].astype(str).str.upper().str.contains(b, na=False)
            | df["cuit"].astype(str).str.upper().str.contains(b, na=False)
        ]

    if origen != "Todos":
        df = df[df["origen_sugerencia"] == origen]

    if confianza != "Todas":
        df = df[df["confianza_sugerencia"] == confianza]

    return df


def mostrar_panel_clasificacion_proveedores(
    df_detalle_base,
    df_categorias,
    categorias_disponibles,
    nombre_archivo
):
    estado = inicializar_estado_clasificacion(nombre_archivo, df_detalle_base)

    categorias_por_proveedor = st.session_state[estado["categorias_key"]]
    confirmados = st.session_state[estado["confirmados_key"]]
    abiertos = st.session_state[estado["abiertos_key"]]

    df_actual = obtener_df_final_clasificado(df_detalle_base, estado)
    resumen = construir_resumen_por_proveedor(df_actual)

    total_proveedores = len(resumen)
    total_confirmados = len(confirmados)
    total_pendientes = max(total_proveedores - total_confirmados, 0)
    total_comprobantes = int(resumen["comprobantes"].sum()) if not resumen.empty else 0
    total_importe = float(resumen["total"].sum()) if not resumen.empty else 0

    pendientes = resumen[
        ~resumen["clave_proveedor"].astype(str).isin(confirmados)
    ].copy()

    st.subheader("Clasificación rápida de proveedores")
    st.caption(
        "Primero resolvé pendientes. El resumen de preclasificación queda al final para controlar antes de procesar."
    )

    if not pendientes.empty:
        pendientes_filtrados = aplicar_filtros_pendientes(pendientes)

        mostrar_acciones_masivas(
            pendientes_filtrados,
            estado,
            categorias_disponibles
        )

        st.markdown("#### Proveedores pendientes")

        if pendientes_filtrados.empty:
            st.info("No hay proveedores para los filtros seleccionados.")
        else:
            for _, fila in pendientes_filtrados.iterrows():
                clave = str(fila["clave_proveedor"])
                clave_key = key_segura(clave)

                proveedor = str(fila["proveedor"])
                cuit = str(fila["cuit"])
                comprobantes = int(fila["comprobantes"])
                total = float(fila["total"])

                origen = str(fila.get("origen_sugerencia", "SIN HISTORIAL"))
                confianza = str(fila.get("confianza_sugerencia", "BAJA"))
                sugerida = str(fila.get("categoria_sugerida", ""))
                veces = int(fila.get("veces_usada", 0) or 0)

                categoria_actual = categorias_por_proveedor.get(clave, categorias_disponibles[0])

                if categoria_actual not in categorias_disponibles:
                    categoria_actual = categorias_disponibles[0]

                st.markdown("<hr style='margin: 0.35rem 0;'>", unsafe_allow_html=True)

                col_info, col_hist, col_categoria, col_facturas, col_confirmar = st.columns(
                    [2.6, 2.0, 2.2, 1.25, 1.0]
                )

                with col_info:
                    st.write(f"**{proveedor}**")
                    st.caption(f"CUIT: {cuit} | {comprobantes} comp. | {moneda(total)}")

                with col_hist:
                    st.caption(f"Sugerida: **{sugerida}**")
                    st.caption(f"{origen} | {confianza} | Usos {veces}")

                with col_categoria:
                    categoria_seleccionada = st.selectbox(
                        "Categoría",
                        categorias_disponibles,
                        index=categorias_disponibles.index(categoria_actual),
                        key=f"categoria_proveedor_{estado['base_key']}_{clave_key}",
                        label_visibility="collapsed"
                    )
                    categorias_por_proveedor[clave] = categoria_seleccionada

                with col_facturas:
                    if st.button(
                        f"Ver ({comprobantes})",
                        key=f"ver_facturas_{estado['base_key']}_{clave_key}"
                    ):
                        abiertos[clave] = not abiertos.get(clave, False)
                        rerun_app()

                with col_confirmar:
                    if st.button(
                        "OK",
                        key=f"confirmar_proveedor_{estado['base_key']}_{clave_key}"
                    ):
                        confirmados.add(clave)
                        abiertos[clave] = False
                        rerun_app()

                if abiertos.get(clave, False):
                    mostrar_facturas_de_proveedor(
                        clave,
                        df_detalle_base,
                        estado,
                        categorias_disponibles
                    )
    else:
        st.success("Todos los proveedores fueron confirmados.")

    if confirmados:
        with st.expander("Proveedores confirmados", expanded=False):
            confirmados_df = resumen[
                resumen["clave_proveedor"].astype(str).isin(confirmados)
            ].copy()

            for _, fila in confirmados_df.iterrows():
                clave = str(fila["clave_proveedor"])
                clave_key = key_segura(clave)

                col1, col2, col3, col4 = st.columns([3, 2, 1, 1])

                with col1:
                    st.write(f"**{fila['proveedor']}**")
                    st.caption(f"CUIT: {fila['cuit']}")

                with col2:
                    st.write(str(fila["categoria_compra"]))

                with col3:
                    st.write(f"{int(fila['comprobantes'])} comp.")

                with col4:
                    if st.button(
                        "Modificar",
                        key=f"modificar_confirmado_{estado['base_key']}_{clave_key}"
                    ):
                        confirmados.discard(clave)
                        rerun_app()

    df_final = obtener_df_final_clasificado(df_detalle_base, estado)

    st.divider()
    st.subheader("Resumen final de preclasificación")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Proveedores", total_proveedores)
    col2.metric("Pendientes", total_pendientes)
    col3.metric("Confirmados", total_confirmados)
    col4.metric("Comprobantes", total_comprobantes)

    st.caption(f"Importe total del archivo: {moneda(total_importe)}")

    resumen_categoria = resumen_final_por_categoria(df_final)
    st.dataframe(preparar_vista(resumen_categoria), use_container_width=True)

    return df_final, total_pendientes


# ======================================================
# PANTALLA PRINCIPAL
# ======================================================

def mostrar_compras():
    asegurar_columnas_compras_v2()

    st.title("📥 Compras")

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Cargar CSV ARCA",
        "Carga Manual",
        "Libro IVA Compras",
        "Resumen / Estadísticas",
        "Cuenta corriente proveedores"
    ])

    with tab1:
        cargar_csv_compras_arca()

    with tab2:
        cargar_compra_manual()

    with tab3:
        mostrar_libro_iva_compras()

    with tab4:
        mostrar_resumen_compras()

    with tab5:
        mostrar_cuenta_corriente_proveedores()


# ======================================================
# TAB 1 - CSV ARCA
# ======================================================

def cargar_csv_compras_arca():
    st.info(
        "Este módulo procesa CSV ARCA/AFIP Compras. "
        "La clasificación se realiza por proveedor, aprende del historial vigente y permite excepciones por comprobante."
    )

    df_categorias = obtener_categorias_activas()

    if df_categorias.empty:
        st.error(
            "Primero cargá las Categorías de Compra desde Configuración. "
            "Sin categoría no se puede determinar la cuenta contable principal."
        )
        return

    categorias_disponibles = df_categorias["categoria"].tolist()

    archivo = st.file_uploader("Subir CSV Compras ARCA/AFIP", type=["csv"])

    if not archivo:
        return

    aplicar_reset_pendiente(archivo.name)

    if archivo_preclasificado_ya_cargado(archivo.name):
        st.info(
            "Este archivo ya tiene cargas anteriores. "
            "El sistema permitirá continuar y procesará solamente comprobantes nuevos. "
            "Los comprobantes ya existentes serán omitidos como duplicados."
        )

    try:
        df = pd.read_csv(
            archivo,
            sep=None,
            engine="python",
            encoding="latin-1",
            dtype=str
        )

        try:
            df = ordenar_dataframe_por_fecha(df, columna_indice=0)
        except Exception:
            pass

        with st.expander("Vista previa del CSV", expanded=False):
            st.dataframe(preparar_vista(df.head(20)), use_container_width=True)
            st.caption(f"Registros detectados: {len(df)}")

        if es_csv_arca_compras(df):
            st.success("Formato detectado: CSV ARCA/AFIP Compras.")
        else:
            st.error(
                "El archivo no parece tener el formato ARCA/AFIP Compras esperado. "
                "Revisá que tenga columnas como Fecha de Emisión, Tipo de Comprobante, "
                "Punto de Venta, Número de Comprobante, Importe Total."
            )
            return

        st.divider()

        df_detalle_base = construir_detalle_preclasificacion(df, df_categorias)

        df_final, pendientes = mostrar_panel_clasificacion_proveedores(
            df_detalle_base,
            df_categorias,
            categorias_disponibles,
            archivo.name
        )

        st.divider()

        st.subheader("Procesamiento")

        if pendientes > 0:
            st.warning("Todavía hay proveedores pendientes de confirmar.")
            return

        if df_final["categoria_compra"].isna().any() or (
            df_final["categoria_compra"].astype(str).str.strip() == ""
        ).any():
            st.warning("Hay comprobantes sin categoría. Completá todas las categorías antes de procesar.")
            return

        if not st.button("Procesar Compras ARCA"):
            return

        resultado_total = resultado_vacio()

        for categoria, df_grupo_final in df_final.groupby("categoria_compra"):
            indices = df_grupo_final["idx_original"].tolist()
            df_grupo = df.loc[indices].copy()

            nombre_interno = nombre_archivo_interno(archivo.name, categoria)

            resultado_grupo = procesar_csv_compras_arca(
                nombre_interno,
                df_grupo,
                categoria
            )

            resultado_total = acumular_resultado(resultado_total, resultado_grupo)

        guardar_categoria_habitual_proveedores(df_final, df_categorias)

        mostrar_resumen_resultado(resultado_total)
        mostrar_auditoria_archivo(archivo.name)

    except Exception as e:
        st.error(f"No se pudo leer o procesar el archivo: {str(e)}")


# ======================================================
# TAB 2 - CARGA MANUAL
# ======================================================

def cargar_compra_manual():
    st.info(
        "Carga manual de comprobantes de compra. Útil para casos puntuales, "
        "bienes de uso, servicios específicos o comprobantes no incluidos en CSV."
    )

    df_categorias = obtener_categorias_activas()

    if df_categorias.empty:
        st.error("Primero cargá las Categorías de Compra desde Configuración.")
        return

    df_tipos = obtener_tipos_comprobantes()

    if df_tipos.empty:
        st.error("Primero cargá los Tipos de Comprobantes desde Configuración.")
        return

    with st.form("form_compra_manual"):
        st.subheader("Datos del comprobante")

        col1, col2, col3 = st.columns(3)

        with col1:
            fecha = st.date_input("Fecha de emisión", value=date.today())

        with col2:
            opciones_tipo = [
                f"{row['codigo']} - {row['descripcion']}"
                for _, row in df_tipos.iterrows()
            ]
            tipo_sel = st.selectbox("Tipo de comprobante", opciones_tipo)

        with col3:
            categoria = st.selectbox(
                "Categoría contable",
                df_categorias["categoria"].tolist()
            )

        codigo = tipo_sel.split(" - ")[0].strip()

        col1, col2, col3 = st.columns(3)

        with col1:
            punto_venta = st.text_input("Punto de venta", value="1")

        with col2:
            numero_comprobante = st.text_input("Número de comprobante")

        with col3:
            moneda_original = st.text_input("Moneda", value="PES")

        col1, col2, col3 = st.columns(3)

        with col1:
            cuit = st.text_input("CUIT proveedor")

        with col2:
            proveedor = st.text_input("Proveedor / Razón social")

        with col3:
            tipo_cambio = st.number_input("Tipo de cambio", min_value=0.0, value=1.0, step=0.01)

        st.divider()

        st.subheader("Importes fiscales")

        col1, col2, col3 = st.columns(3)

        with col1:
            total_neto_gravado = st.number_input("Total Neto Gravado", value=0.0, step=0.01)
            importe_no_gravado = st.number_input("Importe No Gravado", value=0.0, step=0.01)
            importe_exento = st.number_input("Importe Exento", value=0.0, step=0.01)

        with col2:
            iva_total = st.number_input("Total IVA facturado", value=0.0, step=0.01)
            credito_fiscal = st.number_input("Crédito Fiscal Computable", value=0.0, step=0.01)
            percepcion_iva = st.number_input("Percepción IVA", value=0.0, step=0.01)

        with col3:
            percepcion_iibb = st.number_input("Percepción IIBB", value=0.0, step=0.01)
            percepcion_otros = st.number_input("Percepción otros imp. nacionales", value=0.0, step=0.01)
            impuestos_municipales = st.number_input("Impuestos municipales", value=0.0, step=0.01)

        col1, col2, col3 = st.columns(3)

        with col1:
            impuestos_internos = st.number_input("Impuestos internos", value=0.0, step=0.01)

        with col2:
            otros_tributos = st.number_input("Otros tributos", value=0.0, step=0.01)

        with col3:
            total = st.number_input("Importe Total", value=0.0, step=0.01)

        total_sugerido = (
            total_neto_gravado
            + importe_no_gravado
            + importe_exento
            + iva_total
            + percepcion_iva
            + percepcion_iibb
            + percepcion_otros
            + impuestos_municipales
            + impuestos_internos
            + otros_tributos
        )

        st.caption(f"Total sugerido según componentes: {moneda(total_sugerido)}")

        guardar = st.form_submit_button("Guardar compra manual")

        if guardar:
            if numero_comprobante == "" or proveedor == "":
                st.warning("Completá número de comprobante y proveedor.")
            elif total <= 0:
                st.warning("El total debe ser mayor a cero.")
            else:
                datos = {
                    "fecha": fecha.strftime("%Y-%m-%d"),
                    "codigo": codigo,
                    "punto_venta": punto_venta,
                    "numero_comprobante": numero_comprobante,
                    "cuit": cuit,
                    "proveedor": proveedor,
                    "categoria_compra": categoria,
                    "total_neto_gravado": total_neto_gravado,
                    "importe_no_gravado": importe_no_gravado,
                    "importe_exento": importe_exento,
                    "iva_total": iva_total,
                    "credito_fiscal_computable": credito_fiscal,
                    "percepcion_iva": percepcion_iva,
                    "percepcion_iibb": percepcion_iibb,
                    "percepcion_otros_imp_nac": percepcion_otros,
                    "impuestos_municipales": impuestos_municipales,
                    "impuestos_internos": impuestos_internos,
                    "otros_tributos": otros_tributos,
                    "total": total,
                    "moneda": moneda_original,
                    "tipo_cambio": tipo_cambio
                }

                resultado = procesar_compra_manual(datos)
                mostrar_resumen_resultado(resultado)


# ======================================================
# TAB 3 - LIBRO IVA COMPRAS
# ======================================================

def mostrar_libro_iva_compras():
    st.subheader("📘 Libro IVA Compras")

    df = ejecutar_query("""
        SELECT 
            fecha,
            anio,
            mes,
            tipo,
            numero,
            proveedor,
            cuit,
            categoria_compra,
            cuenta_principal_nombre,
            neto,
            importe_no_gravado,
            importe_exento,
            iva_total,
            credito_fiscal_computable,
            iva_no_computable,
            metodo_credito_fiscal,
            coeficiente_iva_aplicado,
            iva_computable_sistema,
            iva_no_computable_sistema,
            iva_computable_csv,
            diferencia_iva_csv_sistema,
            percepcion_iva,
            percepcion_iibb,
            percepcion_otros_imp_nac,
            impuestos_municipales,
            impuestos_internos,
            otros_tributos,
            total,
            archivo
        FROM compras_comprobantes
    """, fetch=True)

    if df.empty:
        st.info("No hay compras cargadas.")
        return

    df["fecha_orden"] = df["fecha"].apply(fecha_para_ordenar)
    df["fecha"] = df["fecha"].apply(formatear_fecha)

    df = df.sort_values(
        by=["anio", "mes", "fecha_orden", "numero"],
        ascending=True
    )

    col1, col2, col3 = st.columns(3)

    anios = ["Todos"] + sorted(df["anio"].dropna().unique().tolist())
    meses = ["Todos"] + sorted(df["mes"].dropna().unique().tolist())
    proveedores = ["Todos"] + sorted(df["proveedor"].dropna().unique().tolist())

    with col1:
        anio = st.selectbox("Año", anios)

    with col2:
        mes = st.selectbox("Mes", meses)

    with col3:
        proveedor = st.selectbox("Proveedor", proveedores)

    if anio != "Todos":
        df = df[df["anio"] == anio]

    if mes != "Todos":
        df = df[df["mes"] == mes]

    if proveedor != "Todos":
        df = df[df["proveedor"] == proveedor]

    df_vista = df.drop(columns=["fecha_orden"])

    st.dataframe(preparar_vista(df_vista), use_container_width=True)

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Neto Gravado", moneda(df["neto"].sum()))
    c2.metric("IVA Total", moneda(df["iva_total"].sum()))
    c3.metric("Crédito Fiscal Computable", moneda(df["credito_fiscal_computable"].sum()))
    c4.metric("Total Compras", moneda(df["total"].sum()))

    excel = exportar_excel({
        "Libro IVA Compras": df_vista
    })

    st.download_button(
        "Descargar Libro IVA Compras Excel",
        data=excel,
        file_name="libro_iva_compras.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


# ======================================================
# TAB 4 - RESUMEN
# ======================================================

def mostrar_resumen_compras():
    st.subheader("📊 Resumen / Estadísticas de Compras")

    df = ejecutar_query("""
        SELECT 
            fecha,
            anio,
            mes,
            tipo,
            proveedor,
            cuit,
            categoria_compra,
            neto,
            iva_total,
            credito_fiscal_computable,
            iva_no_computable,
            total
        FROM compras_comprobantes
    """, fetch=True)

    if df.empty:
        st.info("No hay compras cargadas.")
        return

    resumen_mensual = df.groupby(["anio", "mes"], as_index=False).agg({
        "neto": "sum",
        "iva_total": "sum",
        "credito_fiscal_computable": "sum",
        "iva_no_computable": "sum",
        "total": "sum",
        "tipo": "count"
    })

    resumen_mensual = resumen_mensual.rename(columns={
        "tipo": "cantidad_comprobantes"
    })

    resumen_categoria = df.groupby(["categoria_compra"], as_index=False).agg({
        "neto": "sum",
        "iva_total": "sum",
        "credito_fiscal_computable": "sum",
        "iva_no_computable": "sum",
        "total": "sum",
        "tipo": "count"
    })

    resumen_categoria = resumen_categoria.rename(columns={
        "tipo": "cantidad"
    })

    ranking_proveedores = df.groupby(["proveedor", "cuit"], as_index=False).agg({
        "total": "sum",
        "tipo": "count"
    })

    ranking_proveedores = ranking_proveedores.rename(columns={
        "tipo": "cantidad_comprobantes"
    })

    ranking_proveedores = ranking_proveedores.sort_values(by="total", ascending=False)

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Total Neto", moneda(df["neto"].sum()))
    col2.metric("IVA Total", moneda(df["iva_total"].sum()))
    col3.metric("Crédito Fiscal Computable", moneda(df["credito_fiscal_computable"].sum()))
    col4.metric("Total Compras", moneda(df["total"].sum()))

    st.divider()

    st.subheader("Resumen mensual")
    st.dataframe(preparar_vista(resumen_mensual), use_container_width=True)

    st.subheader("Resumen por categoría")
    st.dataframe(preparar_vista(resumen_categoria), use_container_width=True)

    st.subheader("Ranking de proveedores")
    st.dataframe(preparar_vista(ranking_proveedores), use_container_width=True)

    excel = exportar_excel({
        "Resumen Mensual": resumen_mensual,
        "Resumen Categoria": resumen_categoria,
        "Ranking Proveedores": ranking_proveedores
    })

    st.download_button(
        "Descargar Estadísticas Compras Excel",
        data=excel,
        file_name="estadisticas_compras.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


# ======================================================
# TAB 5 - CUENTA CORRIENTE PROVEEDORES
# ======================================================

def mostrar_cuenta_corriente_proveedores():
    st.subheader("💰 Cuenta corriente de proveedores")

    df = ejecutar_query("""
        SELECT 
            id,
            fecha,
            proveedor,
            cuit,
            tipo,
            numero,
            debe,
            haber,
            origen,
            archivo
        FROM cuenta_corriente_proveedores
        ORDER BY proveedor, fecha, id
    """, fetch=True)

    if df.empty:
        st.info("No hay movimientos de cuenta corriente de proveedores.")
        return

    df["fecha_orden"] = df["fecha"].apply(fecha_para_ordenar)
    df["fecha"] = df["fecha"].apply(formatear_fecha)

    resumen = df.groupby(["proveedor", "cuit"], as_index=False).agg({
        "debe": "sum",
        "haber": "sum"
    })

    resumen["saldo"] = resumen["haber"] - resumen["debe"]
    resumen = resumen.sort_values(by="saldo", ascending=False)

    st.subheader("Resumen de deuda con proveedores")
    st.dataframe(preparar_vista(resumen), use_container_width=True)

    proveedor = st.selectbox(
        "Ver detalle de proveedor",
        ["Todos"] + sorted(df["proveedor"].dropna().unique().tolist())
    )

    if proveedor != "Todos":
        df = df[df["proveedor"] == proveedor]

    df = df.copy()
    df = df.sort_values(by=["proveedor", "fecha_orden", "id"])

    df["saldo_acumulado"] = (
        df.groupby("proveedor")["haber"].cumsum()
        - df.groupby("proveedor")["debe"].cumsum()
    )

    df_vista = df.drop(columns=["fecha_orden"])

    st.subheader("Detalle de movimientos")
    st.dataframe(preparar_vista(df_vista), use_container_width=True)

    excel = exportar_excel({
        "Resumen Cta Cte": resumen,
        "Detalle Cta Cte": df_vista
    })

    st.download_button(
        "Descargar Cuenta Corriente Proveedores Excel",
        data=excel,
        file_name="cuenta_corriente_proveedores.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )