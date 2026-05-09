import streamlit as st
import pandas as pd
from datetime import date

from database import (
    ejecutar_query,
    eliminar_diferencias_redondeo,
)

from core.fechas import fecha_para_ordenar, formatear_fecha
from core.numeros import moneda
from core.ui import preparar_vista
from core.exportadores import exportar_excel

from services.admin_limpieza_service import (
    diagnosticar_datos_demo,
    limpiar_banco_demo_admin,
    limpiar_cobranzas_recibos_admin,
    limpiar_demo_operativa_admin,
    limpiar_libro_diario_admin,
    limpiar_pagos_ordenes_admin,
)

from services.ejercicios_contables_service import (
    anular_ejercicio_contable,
    cerrar_ejercicio_contable,
    crear_ejercicio_contable,
    listar_ejercicios_contables,
    listar_eventos_ejercicio,
    marcar_ejercicio_actual,
    migrar_ejercicios_contables,
    obtener_resumen_ejercicios,
    reabrir_ejercicio_contable,
)

from services.asientos_origen_service import (
    anular_asiento_origen,
    crear_asiento_origen,
    listar_asientos_origen,
    listar_asientos_propuestos,
    listar_eventos_asiento_origen,
    migrar_asientos_origen,
    obtener_asiento_origen,
    obtener_plan_cuentas_opciones,
    obtener_resumen_asientos_origen,
)

from services.capital_social_service import (
    configurar_capital_social_inicial,
    listar_capital_social_empresa,
    listar_socios_empresa,
    migrar_capital_social,
    obtener_capital_social,
    obtener_estado_inicio_contable,
)


from modulos.bandeja_asientos_componentes import mostrar_bandeja_asientos_propuestos_ui
from modulos.libro_diario_componentes import mostrar_trazabilidad_libro_diario_ui
from modulos.coherencia_contable_componentes import mostrar_diagnostico_coherencia_contable_ui

# ======================================================
# UTILIDADES
# ======================================================

def numero_seguro(valor):
    try:
        if pd.isna(valor):
            return 0.0
        return float(valor)
    except Exception:
        return 0.0


def fecha_orden_segura(valor):
    try:
        return fecha_para_ordenar(valor)
    except Exception:
        return pd.NaT


def fecha_formateada_segura(valor):
    try:
        return formatear_fecha(valor)
    except Exception:
        return valor


def fecha_iso_segura(valor):
    try:
        fecha = pd.to_datetime(valor, errors="coerce")
        if pd.isna(fecha):
            return None
        return fecha.strftime("%Y-%m-%d")
    except Exception:
        return None


def fecha_mostrar_argentina(valor):
    """
    Formato único de visualización para toda la UI: DD/MM/YYYY.

    La base sigue guardando fechas en ISO YYYY-MM-DD para ordenar, filtrar
    y evitar ambigüedades técnicas. Esta función solo cambia la presentación
    al usuario.
    """
    if valor is None:
        return ""

    try:
        if pd.isna(valor):
            return ""
    except Exception:
        pass

    try:
        fecha = pd.to_datetime(valor, errors="coerce")
        if pd.isna(fecha):
            return str(valor)
        return fecha.strftime("%d/%m/%Y")
    except Exception:
        return str(valor)


def rango_fechas_mostrar(fecha_desde, fecha_hasta):
    desde = fecha_mostrar_argentina(fecha_desde)
    hasta = fecha_mostrar_argentina(fecha_hasta)
    if desde and hasta:
        return f"{desde} al {hasta}"
    if desde:
        return f"Desde {desde}"
    if hasta:
        return f"Hasta {hasta}"
    return "Sin rango"


def date_input_argentino(*args, **kwargs):
    """
    st.date_input con formato argentino cuando la versión de Streamlit lo soporte.
    Si el entorno tuviera una versión anterior sin parámetro format, mantiene
    compatibilidad y usa el date_input estándar.
    """
    kwargs.setdefault("format", "DD/MM/YYYY")
    try:
        return st.date_input(*args, **kwargs)
    except TypeError:
        kwargs.pop("format", None)
        return st.date_input(*args, **kwargs)


def empresa_actual_id():
    return int(st.session_state.get("empresa_id", 1) or 1)


def usuario_actual_nombre():
    usuario = st.session_state.get("usuario") or {}
    nombre = usuario.get("nombre") or usuario.get("email") or usuario.get("usuario")
    return str(nombre).strip() if nombre else None


def usuario_es_administrador():
    usuario = st.session_state.get("usuario") or {}
    rol = str(usuario.get("rol", "")).strip().upper()
    return rol in {"ADMINISTRADOR", "ADMIN", "SUPERADMIN"}


def insertar_espacios_entre_asientos(df):
    filas = []

    for _, grupo in df.groupby("id_asiento", sort=False):
        filas.append(grupo)

        fila_vacia = pd.DataFrame([{
            "id_asiento": "",
            "fecha": "",
            "cuenta": "",
            "debe": "",
            "haber": "",
            "glosa": "",
            "origen": "",
            "archivo": ""
        }])

        filas.append(fila_vacia)

    if filas:
        return pd.concat(filas, ignore_index=True)

    return df


def _to_date(valor, default=None):
    try:
        if isinstance(valor, date):
            return valor
        if valor is None or pd.isna(valor):
            return default
        return pd.to_datetime(valor).date()
    except Exception:
        return default


def _normalizar_importe(valor):
    try:
        if valor is None or pd.isna(valor):
            return 0.0
        return round(float(valor), 2)
    except Exception:
        return 0.0


def _texto(valor):
    if valor is None:
        return ""
    try:
        if pd.isna(valor):
            return ""
    except Exception:
        pass
    return str(valor).strip()


def _mostrar_resultado_servicio(resultado):
    if resultado.get("ok"):
        st.success(resultado.get("mensaje", "Operación realizada correctamente."))
    else:
        st.error(resultado.get("mensaje", "No se pudo realizar la operación."))


def _opciones_ejercicios(empresa_id, incluir_anulados=False):
    df = listar_ejercicios_contables(
        empresa_id=empresa_id,
        incluir_anulados=incluir_anulados,
    )

    if df.empty:
        return [], {}

    opciones = []
    mapa = {}

    for _, fila in df.iterrows():
        ejercicio_id = int(fila["id"])
        etiqueta_actual = " · actual" if int(fila.get("es_actual") or 0) == 1 else ""
        etiqueta = (
            f"{fila.get('nombre')} · "
            f"{rango_fechas_mostrar(fila.get('fecha_inicio'), fila.get('fecha_cierre'))} "
            f"· {fila.get('estado')}{etiqueta_actual}"
        )
        opciones.append(ejercicio_id)
        mapa[ejercicio_id] = etiqueta

    return opciones, mapa


def _select_ejercicio(empresa_id, key, incluir_anulados=False, label="Ejercicio contable"):
    opciones, mapa = _opciones_ejercicios(empresa_id, incluir_anulados=incluir_anulados)

    if not opciones:
        return None

    return st.selectbox(
        label,
        opciones,
        format_func=lambda x: mapa.get(x, str(x)),
        key=key,
    )


# ======================================================
# CARGA DE DATOS CONTABLES
# ======================================================

def cargar_libro_diario():
    empresa_id = empresa_actual_id()

    df = ejecutar_query("""
        SELECT
            id,
            id_asiento,
            fecha,
            cuenta,
            debe,
            haber,
            glosa,
            origen,
            archivo,
            COALESCE(empresa_id, 1) AS empresa_id
        FROM libro_diario
        WHERE COALESCE(empresa_id, 1) = ?
    """, (empresa_id,), fetch=True)

    if df.empty:
        return df

    df = df.copy()

    df["debe"] = df["debe"].apply(numero_seguro)
    df["haber"] = df["haber"].apply(numero_seguro)

    df = df[df["cuenta"] != "DIFERENCIA POR REDONDEO"].copy()

    if df.empty:
        return df

    df["fecha_orden"] = df["fecha"].apply(fecha_orden_segura)
    df["fecha_mostrar"] = df["fecha"].apply(fecha_formateada_segura)
    df["fecha_iso"] = df["fecha_orden"].apply(fecha_iso_segura)

    return df


def mostrar_resultado_limpieza(resultado):
    if resultado.get("ok"):
        st.success(resultado.get("mensaje", "Operación realizada correctamente."))
    else:
        st.error(resultado.get("mensaje", "No se pudo realizar la operación."))

    backup = resultado.get("backup")

    if backup:
        st.caption(f"Backup creado: `{backup}`")

    detalle = resultado.get("detalle") or []

    if detalle:
        st.dataframe(
            preparar_vista(pd.DataFrame(detalle)),
            use_container_width=True,
        )


def mostrar_alerta_redondeo():
    empresa_id = empresa_actual_id()

    df = ejecutar_query("""
        SELECT
            id,
            id_asiento,
            fecha,
            cuenta,
            debe,
            haber,
            glosa,
            origen,
            archivo
        FROM libro_diario
        WHERE cuenta = 'DIFERENCIA POR REDONDEO'
          AND COALESCE(empresa_id, 1) = ?
    """, (empresa_id,), fetch=True)

    if df.empty:
        return

    st.error(
        f"Se detectaron {len(df)} movimientos antiguos en la cuenta "
        "'DIFERENCIA POR REDONDEO'. Estos movimientos corresponden a pruebas anteriores."
    )

    if "confirmar_eliminar_redondeo" not in st.session_state:
        st.session_state["confirmar_eliminar_redondeo"] = False

    if st.button("Eliminar movimientos de DIFERENCIA POR REDONDEO"):
        st.session_state["confirmar_eliminar_redondeo"] = True

    if st.session_state["confirmar_eliminar_redondeo"]:
        st.warning("¿Confirmás eliminar esos movimientos del Libro Diario?")

        c1, c2 = st.columns(2)

        with c1:
            if st.button("Sí, eliminar redondeos"):
                eliminar_diferencias_redondeo()
                st.success("Movimientos de diferencia por redondeo eliminados.")
                st.session_state["confirmar_eliminar_redondeo"] = False
                st.rerun()

        with c2:
            if st.button("Cancelar eliminación"):
                st.session_state["confirmar_eliminar_redondeo"] = False
                st.rerun()

    st.divider()


# ======================================================
# FILTROS CONTABLES
# ======================================================

def aplicar_filtros_contables(df, key_prefix):
    if df.empty:
        return df

    empresa_id = empresa_actual_id()
    migrar_ejercicios_contables()

    st.subheader("Filtros")

    st.markdown("#### Período contable")

    modos = {
        "Todos los movimientos": "TODOS",
        "Ejercicio contable seleccionado": "EJERCICIO",
        "Hasta fecha de cierre contable": "HASTA_CIERRE",
        "Rango manual": "RANGO_MANUAL",
    }

    col_periodo_1, col_periodo_2, col_periodo_3 = st.columns([1.3, 1.7, 1.4])

    with col_periodo_1:
        modo_label = st.selectbox(
            "Período",
            list(modos.keys()),
            key=f"{key_prefix}_modo_periodo",
        )
        modo = modos[modo_label]

    fecha_desde = None
    fecha_hasta = None
    ejercicio_seleccionado = None

    if modo in {"EJERCICIO", "HASTA_CIERRE"}:
        with col_periodo_2:
            ejercicio_seleccionado = _select_ejercicio(
                empresa_id,
                key=f"{key_prefix}_ejercicio",
                incluir_anulados=False,
                label="Ejercicio",
            )

        if ejercicio_seleccionado is None:
            st.warning(
                "No hay ejercicios contables cargados. Podés crearlos desde la pestaña "
                "Ejercicios contables."
            )
        else:
            ejercicios = listar_ejercicios_contables(empresa_id=empresa_id)
            fila = ejercicios[ejercicios["id"].astype(int) == int(ejercicio_seleccionado)]

            if not fila.empty:
                fecha_desde = str(fila.iloc[0]["fecha_inicio"])
                fecha_hasta = str(fila.iloc[0]["fecha_cierre"])
                estado = str(fila.iloc[0]["estado"])

                with col_periodo_3:
                    st.caption("Corte aplicado")
                    st.code(f"{rango_fechas_mostrar(fecha_desde, fecha_hasta)}\nEstado: {estado}")

    elif modo == "RANGO_MANUAL":
        fecha_minima = _to_date(df["fecha_iso"].dropna().min(), date(date.today().year, 1, 1))
        fecha_maxima = _to_date(df["fecha_iso"].dropna().max(), date.today())

        with col_periodo_2:
            desde_input = date_input_argentino(
                "Desde",
                value=fecha_minima,
                key=f"{key_prefix}_fecha_desde",
            )

        with col_periodo_3:
            hasta_input = date_input_argentino(
                "Hasta",
                value=fecha_maxima,
                key=f"{key_prefix}_fecha_hasta",
            )

        fecha_desde = desde_input.isoformat()
        fecha_hasta = hasta_input.isoformat()

        if fecha_desde > fecha_hasta:
            st.error("La fecha desde no puede ser posterior a la fecha hasta.")
            return df.iloc[0:0].copy()

    else:
        with col_periodo_2:
            st.caption("Se muestran todos los movimientos contables de la empresa actual.")

    df_filtrado = df.copy()

    if fecha_desde and fecha_hasta:
        df_filtrado = df_filtrado[
            (df_filtrado["fecha_iso"].fillna("") >= fecha_desde)
            & (df_filtrado["fecha_iso"].fillna("") <= fecha_hasta)
        ].copy()

    st.markdown("#### Origen, archivo y cuenta")

    col1, col2, col3 = st.columns(3)

    with col1:
        origenes = ["Todos"] + sorted(df_filtrado["origen"].dropna().astype(str).unique().tolist())
        origen_seleccionado = st.selectbox(
            "Origen",
            origenes,
            key=f"{key_prefix}_origen"
        )

    with col2:
        archivos = ["Todos"] + sorted(df_filtrado["archivo"].dropna().astype(str).unique().tolist())
        archivo_seleccionado = st.selectbox(
            "Archivo",
            archivos,
            key=f"{key_prefix}_archivo"
        )

    with col3:
        cuentas = ["Todas"] + sorted(df_filtrado["cuenta"].dropna().astype(str).unique().tolist())
        cuenta_seleccionada = st.selectbox(
            "Cuenta",
            cuentas,
            key=f"{key_prefix}_cuenta"
        )

    if origen_seleccionado != "Todos":
        df_filtrado = df_filtrado[df_filtrado["origen"] == origen_seleccionado]

    if archivo_seleccionado != "Todos":
        df_filtrado = df_filtrado[df_filtrado["archivo"] == archivo_seleccionado]

    if cuenta_seleccionada != "Todas":
        df_filtrado = df_filtrado[df_filtrado["cuenta"] == cuenta_seleccionada]

    return df_filtrado


def mostrar_metricas_cuadre(df):
    total_debe = df["debe"].sum()
    total_haber = df["haber"].sum()
    diferencia = round(total_debe - total_haber, 2)

    c1, c2, c3 = st.columns(3)

    c1.metric("Total Debe", moneda(total_debe))
    c2.metric("Total Haber", moneda(total_haber))
    c3.metric("Diferencia", moneda(diferencia))

    if diferencia != 0:
        st.error("El reporte no está cuadrando.")
    else:
        st.success("El reporte está cuadrado.")


# ======================================================
# PANTALLA PRINCIPAL
# ======================================================

def mostrar_diario():
    st.caption(
        "Módulo de libros y reportes contables. "
        "Las cuentas corrientes de clientes y proveedores deben gestionarse desde Ventas y Compras."
    )

    migrar_ejercicios_contables()
    migrar_asientos_origen()
    migrar_capital_social()

    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10 = st.tabs([
        "🗓️ Ejercicios contables",
        "🚦 Inicio contable",
        "🧾 Bandeja de asientos",
        "📓 Libro Diario",
        "🔎 Trazabilidad Diario",
        "🧩 Coherencia contable",
        "📒 Libro Mayor",
        "📊 Balance de Sumas y Saldos",
        "🧭 Control por origen / archivo",
        "🧹 Limpieza admin/demo",
    ])

    with tab1:
        mostrar_ejercicios_contables()

    with tab2:
        mostrar_inicio_contable()

    with tab3:
        mostrar_bandeja_asientos_propuestos_ui(
            empresa_id=empresa_actual_id(),
            usuario=usuario_actual_nombre(),
            key_prefix="contabilidad_bandeja_asientos",
        )

    with tab4:
        mostrar_libro_diario()

    with tab5:
        mostrar_trazabilidad_libro_diario_ui(
            empresa_id=empresa_actual_id(),
            usuario=usuario_actual_nombre(),
            key_prefix="contabilidad_trazabilidad_diario",
        )

    with tab6:
        mostrar_diagnostico_coherencia_contable_ui(
            empresa_id=empresa_actual_id(),
            usuario=usuario_actual_nombre(),
            key_prefix="contabilidad_coherencia_contable",
        )

    with tab7:
        mostrar_libro_mayor()

    with tab8:
        mostrar_balance_sumas_saldos()

    with tab9:
        mostrar_control_origen_archivo()

    with tab10:
        mostrar_limpieza_admin_demo()


# ======================================================
# EJERCICIOS CONTABLES
# ======================================================

def mostrar_ejercicios_contables():
    st.subheader("🗓️ Ejercicios contables")

    empresa_id = empresa_actual_id()
    usuario = usuario_actual_nombre()

    st.caption(
        "Definí el ejercicio contable real de la empresa: fecha de inicio, fecha de cierre "
        "y estado operativo. Este corte será usado por Libro Diario, Mayor y Balance."
    )

    resumen = obtener_resumen_ejercicios(empresa_id)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ejercicios", resumen.get("total", 0))
    c2.metric("Abiertos", resumen.get("abiertos", 0))
    c3.metric("Cerrados", resumen.get("cerrados", 0))
    c4.metric("Reabiertos", resumen.get("reabiertos", 0))

    actual = resumen.get("actual")
    if actual:
        st.info(
            f"Ejercicio actual: **{actual.get('nombre')}** · "
            f"{rango_fechas_mostrar(actual.get('fecha_inicio'), actual.get('fecha_cierre'))} · "
            f"Estado: **{actual.get('estado')}**"
        )
    else:
        st.warning(
            "Todavía no hay ejercicio contable actual. Creá uno antes de cargar asientos de apertura, "
            "capital social o aportes."
        )

    st.divider()

    with st.expander("Crear nuevo ejercicio contable", expanded=not bool(actual)):
        hoy = date.today()
        inicio_default = date(hoy.year, 1, 1)
        cierre_default = date(hoy.year, 12, 31)

        with st.form("form_crear_ejercicio_contable"):
            col1, col2, col3 = st.columns(3)

            with col1:
                nombre = st.text_input(
                    "Nombre",
                    value=f"Ejercicio {hoy.year}",
                    key="ejercicio_nombre_nuevo",
                )

            with col2:
                fecha_inicio = date_input_argentino(
                    "Fecha de inicio",
                    value=inicio_default,
                    key="ejercicio_fecha_inicio_nuevo",
                )

            with col3:
                fecha_cierre = date_input_argentino(
                    "Fecha de cierre",
                    value=cierre_default,
                    key="ejercicio_fecha_cierre_nuevo",
                )

            observaciones = st.text_area(
                "Observaciones",
                key="ejercicio_observaciones_nuevo",
            )

            marcar_actual = st.checkbox(
                "Marcar como ejercicio actual",
                value=True,
                key="ejercicio_marcar_actual_nuevo",
            )

            enviar = st.form_submit_button("Crear ejercicio contable", type="primary")

        if enviar:
            resultado = crear_ejercicio_contable(
                empresa_id=empresa_id,
                fecha_inicio=fecha_inicio,
                fecha_cierre=fecha_cierre,
                nombre=nombre,
                observaciones=observaciones,
                usuario=usuario,
                marcar_actual=marcar_actual,
            )
            _mostrar_resultado_servicio(resultado)
            if resultado.get("ok"):
                st.rerun()

    st.divider()

    st.markdown("### Ejercicios cargados")

    ejercicios = listar_ejercicios_contables(empresa_id=empresa_id, incluir_anulados=True)

    if ejercicios.empty:
        st.info("No hay ejercicios contables cargados.")
        return

    vista = ejercicios[[
        "id",
        "nombre",
        "fecha_inicio",
        "fecha_cierre",
        "estado",
        "es_actual",
        "bloqueo_hasta",
        "usuario_creacion",
        "fecha_creacion",
    ]].copy()

    for columna_fecha in ["fecha_inicio", "fecha_cierre", "bloqueo_hasta", "fecha_creacion"]:
        if columna_fecha in vista.columns:
            vista[columna_fecha] = vista[columna_fecha].apply(fecha_mostrar_argentina)

    vista = vista.rename(columns={
        "id": "ID",
        "nombre": "Ejercicio",
        "fecha_inicio": "Inicio",
        "fecha_cierre": "Cierre",
        "estado": "Estado",
        "es_actual": "Actual",
        "bloqueo_hasta": "Bloqueado hasta",
        "usuario_creacion": "Usuario",
        "fecha_creacion": "Fecha carga",
    })

    st.dataframe(preparar_vista(vista), use_container_width=True)

    st.divider()

    st.markdown("### Gestión del ejercicio")

    ejercicio_id = _select_ejercicio(
        empresa_id,
        key="gestion_ejercicio_id",
        incluir_anulados=True,
        label="Seleccioná un ejercicio",
    )

    if not ejercicio_id:
        return

    seleccionado = ejercicios[ejercicios["id"].astype(int) == int(ejercicio_id)]

    if seleccionado.empty:
        st.info("No se encontró el ejercicio seleccionado.")
        return

    fila = seleccionado.iloc[0].to_dict()
    estado = str(fila.get("estado") or "").upper()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Estado", estado)
    c2.metric("Inicio", fecha_mostrar_argentina(fila.get("fecha_inicio")))
    c3.metric("Cierre", fecha_mostrar_argentina(fila.get("fecha_cierre")))
    c4.metric("Actual", "Sí" if int(fila.get("es_actual") or 0) == 1 else "No")

    acciones = st.columns(4)

    with acciones[0]:
        if st.button("Marcar como actual", use_container_width=True, key="btn_marcar_ejercicio_actual"):
            resultado = marcar_ejercicio_actual(ejercicio_id, usuario=usuario)
            _mostrar_resultado_servicio(resultado)
            if resultado.get("ok"):
                st.rerun()

    with acciones[1]:
        motivo_cierre = st.text_input(
            "Motivo cierre",
            key="motivo_cierre_ejercicio",
            placeholder="Ej.: cierre aprobado por administración",
        )
        if st.button("Cerrar ejercicio", use_container_width=True, key="btn_cerrar_ejercicio"):
            resultado = cerrar_ejercicio_contable(
                ejercicio_id=ejercicio_id,
                motivo=motivo_cierre,
                usuario=usuario,
            )
            _mostrar_resultado_servicio(resultado)
            if resultado.get("ok"):
                st.rerun()

    with acciones[2]:
        motivo_reapertura = st.text_input(
            "Motivo reapertura",
            key="motivo_reapertura_ejercicio",
            placeholder="Ej.: ajuste posterior documentado",
        )
        if st.button("Reabrir ejercicio", use_container_width=True, key="btn_reabrir_ejercicio"):
            resultado = reabrir_ejercicio_contable(
                ejercicio_id=ejercicio_id,
                motivo=motivo_reapertura,
                usuario=usuario,
            )
            _mostrar_resultado_servicio(resultado)
            if resultado.get("ok"):
                st.rerun()

    with acciones[3]:
        motivo_anulacion = st.text_input(
            "Motivo anulación",
            key="motivo_anulacion_ejercicio",
            placeholder="Solo si fue cargado por error",
        )
        if st.button("Anular ejercicio", use_container_width=True, key="btn_anular_ejercicio"):
            resultado = anular_ejercicio_contable(
                ejercicio_id=ejercicio_id,
                motivo=motivo_anulacion,
                usuario=usuario,
            )
            _mostrar_resultado_servicio(resultado)
            if resultado.get("ok"):
                st.rerun()

    with st.expander("Auditoría del ejercicio seleccionado"):
        eventos = listar_eventos_ejercicio(ejercicio_id)
        if eventos.empty:
            st.info("Sin eventos para este ejercicio.")
        else:
            st.dataframe(preparar_vista(eventos), use_container_width=True)



# ======================================================
# INICIO CONTABLE ASISTIDO
# ======================================================

def _mostrar_estado_inicio_contable(estado):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ejercicio", "Sí" if estado.get("tiene_ejercicio") else "No")
    c2.metric("Socios", estado.get("cantidad_socios", 0))
    c3.metric("Capital cargado", "Sí" if estado.get("tiene_capital_social") else "No")
    c4.metric("Asiento apertura", "Sí" if estado.get("tiene_asiento_apertura") else "No")

    if estado.get("cantidad_movimientos_libro_diario", 0) > 0 and estado.get("requiere_inicio_contable"):
        st.warning(
            "Ya existen movimientos en Libro Diario, pero el inicio contable todavía no está completo. "
            "Conviene revisar ejercicio, capital/socios y saldos iniciales para que la contabilidad tenga origen claro."
        )
    elif estado.get("requiere_inicio_contable"):
        st.info(
            "El sistema detecta que falta completar el inicio contable. Primero definí ejercicio, "
            "luego socios/capital y finalmente saldos iniciales si corresponde."
        )
    else:
        st.success("El inicio contable básico de la empresa está completo.")


def _default_socios_editor(cantidad, capital_total):
    cantidad = max(int(cantidad or 1), 1)
    capital_total = _normalizar_importe(capital_total)
    porcentaje = round(100 / cantidad, 2)
    suscripto = round(capital_total / cantidad, 2) if capital_total else 0.0
    filas = []
    for i in range(cantidad):
        filas.append({
            "nombre": f"Socio {i + 1}",
            "cuit": "",
            "porcentaje": porcentaje,
            "importe_suscripto": suscripto,
            "importe_integrado": 0.0,
            "medio_integracion": "NO_INTEGRADO",
            "cuenta_destino_codigo": "",
            "cuenta_destino_nombre": "Caja/Banco/Bienes aportados",
            "referencia": "",
        })
    if filas:
        diferencia_porcentaje = round(100 - sum(f["porcentaje"] for f in filas), 2)
        filas[-1]["porcentaje"] = round(filas[-1]["porcentaje"] + diferencia_porcentaje, 2)
        diferencia_capital = round(capital_total - sum(f["importe_suscripto"] for f in filas), 2)
        filas[-1]["importe_suscripto"] = round(filas[-1]["importe_suscripto"] + diferencia_capital, 2)
    return pd.DataFrame(filas)


def _socios_desde_editor(df_editor):
    socios = []
    if df_editor is None:
        return socios
    for _, fila in pd.DataFrame(df_editor).iterrows():
        nombre = _texto(fila.get("nombre"))
        if not nombre:
            continue
        socios.append({
            "nombre": nombre,
            "cuit": _texto(fila.get("cuit")),
            "porcentaje": _normalizar_importe(fila.get("porcentaje")),
            "importe_suscripto": _normalizar_importe(fila.get("importe_suscripto")),
            "importe_integrado": _normalizar_importe(fila.get("importe_integrado")),
            "medio_integracion": _texto(fila.get("medio_integracion")) or "NO_INTEGRADO",
            "cuenta_destino_codigo": _texto(fila.get("cuenta_destino_codigo")),
            "cuenta_destino_nombre": _texto(fila.get("cuenta_destino_nombre")) or "Caja/Banco/Bienes aportados",
            "referencia": _texto(fila.get("referencia")),
        })
    return socios


def _mostrar_totales_socios(socios, capital_total):
    total_pct = round(sum(_normalizar_importe(s.get("porcentaje")) for s in socios), 2)
    total_suscripto = round(sum(_normalizar_importe(s.get("importe_suscripto")) for s in socios), 2)
    total_integrado = round(sum(_normalizar_importe(s.get("importe_integrado")) for s in socios), 2)
    pendiente = round(total_suscripto - total_integrado, 2)
    diferencia_capital = round(total_suscripto - _normalizar_importe(capital_total), 2)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Participación", f"{total_pct:.2f}%")
    c2.metric("Capital social", moneda(capital_total))
    c3.metric("Suscripto", moneda(total_suscripto))
    c4.metric("Integrado", moneda(total_integrado))
    c5.metric("Pendiente", moneda(pendiente))

    if abs(total_pct - 100) > 0.01:
        st.error("La participación de los socios debe sumar 100%.")
    if abs(diferencia_capital) > 0.01:
        st.error("La suma suscripta por socios debe coincidir con el capital social total.")
    if total_integrado - total_suscripto > 0.01:
        st.error("El capital integrado no puede superar al capital suscripto.")
    if abs(total_pct - 100) <= 0.01 and abs(diferencia_capital) <= 0.01 and total_integrado <= total_suscripto + 0.01:
        st.success("La composición de capital está validada para generar asientos propuestos.")


def mostrar_inicio_contable():
    st.subheader("🚦 Inicio contable")
    empresa_id = empresa_actual_id()
    usuario = usuario_actual_nombre()

    migrar_ejercicios_contables()
    migrar_asientos_origen()
    migrar_capital_social()

    st.caption(
        "El inicio contable no debería cargarse como un Debe/Haber aislado. "
        "Primero se define el ejercicio, luego socios/capital y después saldos iniciales si la empresa ya venía operando. "
        "Todo queda como asiento propuesto; todavía no impacta en Libro Diario."
    )

    estado = obtener_estado_inicio_contable(empresa_id)
    _mostrar_estado_inicio_contable(estado)

    tab_a, tab_b, tab_c, tab_d = st.tabs([
        "1 · Asistente de inicio",
        "2 · Capital y socios",
        "3 · Saldos iniciales",
        "4 · Asientos propuestos",
    ])

    with tab_a:
        st.markdown("### Guía del inicio contable")
        st.write(
            "El sistema debe saber si esta empresa nace ahora o si ya venía operando. "
            "Para una sociedad, primero se informa capital suscripto e integrado por socio. "
            "Si después ingresan nuevos aportes, deberían entrar por Caja/Banco y quedar como propuesta contable, no como asiento suelto."
        )
        actual = estado.get("ejercicio_actual")
        if not actual:
            st.warning("No hay ejercicio contable. Creá el primer ejercicio antes de cargar capital o saldos iniciales.")
            with st.form("form_inicio_crear_primer_ejercicio"):
                hoy = date.today()
                col1, col2, col3 = st.columns(3)
                with col1:
                    nombre = st.text_input("Nombre del ejercicio", value=f"Ejercicio {hoy.year}")
                with col2:
                    fecha_inicio = date_input_argentino("Inicio del ejercicio", value=date(hoy.year, 1, 1))
                with col3:
                    fecha_cierre = date_input_argentino("Cierre del ejercicio", value=date(hoy.year, 12, 31))
                obs = st.text_input("Observación", value="Primer ejercicio cargado desde Inicio contable")
                enviar = st.form_submit_button("Crear primer ejercicio", type="primary")
            if enviar:
                resultado = crear_ejercicio_contable(
                    empresa_id=empresa_id,
                    fecha_inicio=fecha_inicio,
                    fecha_cierre=fecha_cierre,
                    nombre=nombre,
                    observaciones=obs,
                    usuario=usuario,
                    marcar_actual=True,
                )
                _mostrar_resultado_servicio(resultado)
                if resultado.get("ok"):
                    st.rerun()
        else:
            st.success(
                f"Ejercicio actual: {actual.get('nombre')} · {rango_fechas_mostrar(actual.get('fecha_inicio'), actual.get('fecha_cierre'))} · {actual.get('estado')}"
            )

        st.markdown("#### Próximo paso sugerido")
        if not estado.get("tiene_capital_social"):
            st.info("Cargá la composición del capital y socios en la pestaña **Capital y socios**.")
        elif not estado.get("tiene_asiento_apertura"):
            st.info("Si la empresa ya venía operando antes del sistema, cargá saldos iniciales en **Saldos iniciales**.")
        else:
            st.success("Ya podés revisar asientos propuestos y avanzar luego a la bandeja central.")

    with tab_b:
        mostrar_capital_y_socios_inicio(empresa_id, usuario)

    with tab_c:
        st.markdown("### Saldos iniciales / asiento de apertura")
        st.caption(
            "Usá esta sección solo si la empresa ya venía operando y necesitás cargar saldos existentes: "
            "caja, bancos, clientes, proveedores, impuestos, bienes, deudas y patrimonio."
        )
        mostrar_nuevo_asiento_origen(empresa_id, usuario, solo_apertura=True)
        with st.expander("Ver asientos de origen cargados"):
            mostrar_listado_asientos_origen(empresa_id, usuario)

    with tab_d:
        mostrar_listado_asientos_propuestos(empresa_id)


def mostrar_capital_y_socios_inicio(empresa_id, usuario):
    st.markdown("### Capital social y socios")
    estado = obtener_estado_inicio_contable(empresa_id)
    ejercicio_id = _select_ejercicio(
        empresa_id,
        key="inicio_capital_ejercicio_id",
        incluir_anulados=False,
        label="Ejercicio contable",
    )
    if not ejercicio_id:
        st.warning("Primero creá un ejercicio contable.")
        return

    with st.expander("Cargar composición inicial de capital", expanded=not estado.get("tiene_capital_social")):
        st.info(
            "El sistema generará dos propuestas contables cuando corresponda: "
            "1) suscripción de capital, 2) integración del capital por caja/banco/bienes."
        )
        col1, col2, col3 = st.columns(3)
        with col1:
            fecha_instrumento = date_input_argentino("Fecha del instrumento / inicio", value=date.today(), key="capital_fecha_instrumento")
        with col2:
            capital_total = st.number_input("Capital social total", min_value=0.0, step=1000.0, value=0.0, key="capital_total_inicio")
        with col3:
            cantidad_socios = st.number_input("Cantidad de socios", min_value=1, max_value=20, step=1, value=1, key="capital_cantidad_socios")

        descripcion = st.text_input("Descripción", value="Capital social inicial", key="capital_descripcion_inicio")
        referencia = st.text_input("Referencia / respaldo", placeholder="Acta, contrato, estatuto, instrumento constitutivo", key="capital_referencia_inicio")

        cta1, cta2 = st.columns(2)
        with cta1:
            cuenta_socios_nombre = st.text_input("Cuenta puente por integración pendiente", value="Socios / Accionistas por integración", key="capital_cuenta_socios_nombre")
            cuenta_socios_codigo = st.text_input("Código cuenta puente", value="", key="capital_cuenta_socios_codigo")
        with cta2:
            cuenta_capital_nombre = st.text_input("Cuenta de capital", value="Capital social", key="capital_cuenta_capital_nombre")
            cuenta_capital_codigo = st.text_input("Código cuenta capital", value="", key="capital_cuenta_capital_codigo")

        st.markdown("#### Socios, suscripción e integración")
        st.caption(
            "La participación debe sumar 100%. El capital suscripto debe coincidir con el capital social total. "
            "El integrado no puede superar lo suscripto. Si no está integrado, queda pendiente contra socios por integración."
        )
        base_socios = _default_socios_editor(cantidad_socios, capital_total)
        df_socios = st.data_editor(
            base_socios,
            num_rows="dynamic",
            use_container_width=True,
            key=f"editor_socios_capital_{cantidad_socios}_{capital_total}",
            column_config={
                "nombre": st.column_config.TextColumn("Socio / accionista"),
                "cuit": st.column_config.TextColumn("CUIT opcional"),
                "porcentaje": st.column_config.NumberColumn("%", min_value=0.0, max_value=100.0, step=0.01),
                "importe_suscripto": st.column_config.NumberColumn("Capital suscripto", min_value=0.0, step=0.01),
                "importe_integrado": st.column_config.NumberColumn("Capital integrado", min_value=0.0, step=0.01),
                "medio_integracion": st.column_config.SelectboxColumn("Medio integración", options=["NO_INTEGRADO", "CAJA", "BANCO", "BIENES", "OTRO"]),
                "cuenta_destino_codigo": st.column_config.TextColumn("Código cuenta destino"),
                "cuenta_destino_nombre": st.column_config.TextColumn("Cuenta destino"),
                "referencia": st.column_config.TextColumn("Referencia"),
            },
        )
        socios = _socios_desde_editor(df_socios)
        _mostrar_totales_socios(socios, capital_total)

        confirmar = st.checkbox("Confirmo que revisé socios, capital suscripto e integrado", key="confirmar_capital_social_inicio")
        if st.button("Generar capital y asientos propuestos", type="primary", use_container_width=True, key="btn_generar_capital_inicio"):
            if not confirmar:
                st.error("Marcá la confirmación antes de generar.")
                return
            resultado = configurar_capital_social_inicial(
                empresa_id=empresa_id,
                ejercicio_id=ejercicio_id,
                fecha_instrumento=fecha_instrumento,
                capital_social_total=capital_total,
                socios=socios,
                descripcion=descripcion,
                referencia=referencia,
                cuenta_socios_integracion_codigo=cuenta_socios_codigo,
                cuenta_socios_integracion_nombre=cuenta_socios_nombre,
                cuenta_capital_codigo=cuenta_capital_codigo,
                cuenta_capital_nombre=cuenta_capital_nombre,
                usuario=usuario,
                generar_asientos=True,
            )
            _mostrar_resultado_servicio(resultado)
            if resultado.get("ok"):
                st.rerun()

    st.markdown("### Capital cargado")
    capitales = listar_capital_social_empresa(empresa_id=empresa_id, incluir_anulados=True)
    if capitales.empty:
        st.info("Todavía no hay configuración de capital social cargada.")
    else:
        vista = capitales[[
            "id", "fecha_instrumento", "descripcion", "capital_social_total",
            "total_suscripto", "total_integrado", "total_pendiente_integracion",
            "estado", "asiento_suscripcion_propuesto_id", "asiento_integracion_propuesto_id",
        ]].copy()
        vista["fecha_instrumento"] = vista["fecha_instrumento"].apply(fecha_mostrar_argentina)
        vista = vista.rename(columns={
            "id": "ID",
            "fecha_instrumento": "Fecha",
            "descripcion": "Descripción",
            "capital_social_total": "Capital social",
            "total_suscripto": "Suscripto",
            "total_integrado": "Integrado",
            "total_pendiente_integracion": "Pendiente",
            "estado": "Estado",
            "asiento_suscripcion_propuesto_id": "Propuesta suscripción",
            "asiento_integracion_propuesto_id": "Propuesta integración",
        })
        st.dataframe(preparar_vista(vista), use_container_width=True)
        capital_id = st.selectbox("Ver detalle de capital", capitales["id"].astype(int).tolist(), key="detalle_capital_id")
        capital = obtener_capital_social(int(capital_id))
        if capital:
            c1, c2, c3 = st.columns(3)
            c1.metric("Suscripto", moneda(capital.get("total_suscripto") or 0))
            c2.metric("Integrado", moneda(capital.get("total_integrado") or 0))
            c3.metric("Pendiente", moneda(capital.get("total_pendiente_integracion") or 0))
            suscripciones = pd.DataFrame(capital.get("suscripciones") or [])
            if not suscripciones.empty:
                st.markdown("#### Socios y suscripciones")
                columnas = ["socio_nombre", "socio_cuit", "porcentaje", "importe_suscripto", "importe_integrado", "importe_pendiente"]
                st.dataframe(preparar_vista(suscripciones[columnas]), use_container_width=True)
            integraciones = pd.DataFrame(capital.get("integraciones") or [])
            if not integraciones.empty:
                st.markdown("#### Integraciones registradas")
                columnas = ["fecha", "socio_nombre", "importe", "medio_integracion", "cuenta_destino_nombre", "estado"]
                st.dataframe(preparar_vista(integraciones[columnas]), use_container_width=True)

    with st.expander("Socios cargados"):
        socios_df = listar_socios_empresa(empresa_id=empresa_id, incluir_bajas=True)
        if socios_df.empty:
            st.info("No hay socios cargados.")
        else:
            columnas = ["id", "nombre", "cuit", "tipo_socio", "porcentaje_participacion", "estado"]
            st.dataframe(preparar_vista(socios_df[columnas]), use_container_width=True)


# ======================================================
# ASIENTOS DE APERTURA / CAPITAL / APORTES
# ======================================================

TIPOS_ASIENTOS_INICIALES = {
    "Asiento de apertura / saldos iniciales": {
        "codigo": "APERTURA",
        "titulo": "Asiento de apertura / saldos iniciales",
        "uso": "Usalo cuando empezás a usar el sistema con saldos que ya existían antes: caja, bancos, clientes, proveedores, IVA, patrimonio, etc.",
        "ejemplo": "Ejemplo: Debe Caja/Banco/Clientes y Haber Proveedores/Patrimonio, según el balance o papel de trabajo inicial.",
        "descripcion": "Asiento de apertura del ejercicio",
        "referencia": "Balance anterior / papel de trabajo inicial",
        "lineas": [
            {"cuenta_codigo": "", "cuenta_nombre": "Caja / Banco / Clientes / Bienes", "debe": 0.0, "haber": 0.0, "glosa": "Saldo inicial activo"},
            {"cuenta_codigo": "", "cuenta_nombre": "Proveedores / Deudas / Patrimonio", "debe": 0.0, "haber": 0.0, "glosa": "Saldo inicial pasivo o patrimonio"},
        ],
    },
    "Capital social": {
        "codigo": "CAPITAL_SOCIAL",
        "titulo": "Capital social",
        "uso": "Usalo cuando querés registrar la constitución o integración de capital social de la empresa.",
        "ejemplo": "Ejemplo típico: Debe Banco/Caja y Haber Capital social.",
        "descripcion": "Integración de capital social",
        "referencia": "Acta / contrato / estatuto",
        "lineas": [
            {"cuenta_codigo": "", "cuenta_nombre": "Banco / Caja", "debe": 0.0, "haber": 0.0, "glosa": "Ingreso de fondos"},
            {"cuenta_codigo": "", "cuenta_nombre": "Capital social", "debe": 0.0, "haber": 0.0, "glosa": "Integración de capital"},
        ],
    },
    "Aporte de socio": {
        "codigo": "APORTE_SOCIO",
        "titulo": "Aporte de socio",
        "uso": "Usalo para dinero o bienes aportados por socios que no querés registrar directamente como capital social.",
        "ejemplo": "Ejemplo: Debe Banco/Caja y Haber Aportes de socios / Cuenta particular socio, según el criterio contable elegido.",
        "descripcion": "Aporte de socio para financiar operatoria",
        "referencia": "Comprobante / transferencia / acta interna",
        "lineas": [
            {"cuenta_codigo": "", "cuenta_nombre": "Banco / Caja", "debe": 0.0, "haber": 0.0, "glosa": "Ingreso de fondos"},
            {"cuenta_codigo": "", "cuenta_nombre": "Aportes de socios / Cuenta particular socio", "debe": 0.0, "haber": 0.0, "glosa": "Aporte del socio"},
        ],
    },
    "Aporte irrevocable": {
        "codigo": "APORTE_IRREVOCABLE",
        "titulo": "Aporte irrevocable",
        "uso": "Usalo cuando el aporte queda identificado como aporte irrevocable pendiente de tratamiento societario/contable.",
        "ejemplo": "Ejemplo: Debe Banco/Caja y Haber Aportes irrevocables.",
        "descripcion": "Aporte irrevocable recibido",
        "referencia": "Acta / documentación societaria",
        "lineas": [
            {"cuenta_codigo": "", "cuenta_nombre": "Banco / Caja", "debe": 0.0, "haber": 0.0, "glosa": "Ingreso de fondos"},
            {"cuenta_codigo": "", "cuenta_nombre": "Aportes irrevocables", "debe": 0.0, "haber": 0.0, "glosa": "Aporte irrevocable"},
        ],
    },
    "Préstamo de socio": {
        "codigo": "PRESTAMO_SOCIO",
        "titulo": "Préstamo de socio",
        "uso": "Usalo cuando el socio entrega fondos como deuda a devolver, no como capital ni aporte patrimonial.",
        "ejemplo": "Ejemplo: Debe Banco/Caja y Haber Préstamo de socios / Cuenta particular socio.",
        "descripcion": "Préstamo de socio recibido",
        "referencia": "Contrato / transferencia / comprobante",
        "lineas": [
            {"cuenta_codigo": "", "cuenta_nombre": "Banco / Caja", "debe": 0.0, "haber": 0.0, "glosa": "Ingreso de fondos"},
            {"cuenta_codigo": "", "cuenta_nombre": "Préstamo de socios", "debe": 0.0, "haber": 0.0, "glosa": "Deuda con socio"},
        ],
    },
    "Ajuste inicial": {
        "codigo": "AJUSTE_INICIAL",
        "titulo": "Ajuste inicial",
        "uso": "Usalo para ajustes de arranque documentados que no correspondan a capital ni apertura pura.",
        "ejemplo": "Ejemplo: corrección de saldo inicial contra una cuenta patrimonial definida por el contador.",
        "descripcion": "Ajuste inicial documentado",
        "referencia": "Papel de trabajo / documentación respaldatoria",
        "lineas": [
            {"cuenta_codigo": "", "cuenta_nombre": "Cuenta a ajustar", "debe": 0.0, "haber": 0.0, "glosa": "Ajuste inicial"},
            {"cuenta_codigo": "", "cuenta_nombre": "Contrapartida del ajuste", "debe": 0.0, "haber": 0.0, "glosa": "Contrapartida"},
        ],
    },
}


def _lineas_desde_editor(df_editor):
    lineas = []

    if df_editor is None or len(df_editor) == 0:
        return lineas

    for _, fila in pd.DataFrame(df_editor).iterrows():
        cuenta_codigo = _texto(fila.get("cuenta_codigo"))
        cuenta_nombre = _texto(fila.get("cuenta_nombre"))
        debe = _normalizar_importe(fila.get("debe"))
        haber = _normalizar_importe(fila.get("haber"))
        glosa = _texto(fila.get("glosa"))

        if not cuenta_codigo and not cuenta_nombre and debe == 0 and haber == 0 and not glosa:
            continue

        lineas.append({
            "cuenta_codigo": cuenta_codigo,
            "cuenta_nombre": cuenta_nombre,
            "debe": debe,
            "haber": haber,
            "glosa": glosa,
        })

    return lineas


def _totales_lineas(lineas):
    total_debe = round(sum(_normalizar_importe(linea.get("debe")) for linea in lineas), 2)
    total_haber = round(sum(_normalizar_importe(linea.get("haber")) for linea in lineas), 2)
    diferencia = round(total_debe - total_haber, 2)
    return total_debe, total_haber, diferencia


def _estado_previo_lineas(lineas):
    total_debe, total_haber, diferencia = _totales_lineas(lineas)
    cantidad_validas = sum(
        1
        for linea in lineas
        if _texto(linea.get("cuenta_nombre"))
        and (_normalizar_importe(linea.get("debe")) > 0 or _normalizar_importe(linea.get("haber")) > 0)
    )

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Líneas completas", cantidad_validas)
    col2.metric("Total Debe", moneda(total_debe))
    col3.metric("Total Haber", moneda(total_haber))
    col4.metric("Diferencia", moneda(diferencia))

    if cantidad_validas < 2:
        st.warning("Para generar el asiento necesitás al menos dos líneas completas: una al Debe y otra al Haber.")
    elif abs(diferencia) <= 0.01:
        st.success("El asiento está cuadrado y puede generarse como propuesta.")
    else:
        st.error("El asiento todavía no está cuadrado. El total Debe debe ser igual al total Haber.")


def _mostrar_ayuda_tipo_asiento(config_tipo):
    st.info(
        f"**{config_tipo['titulo']}**\n\n"
        f"{config_tipo['uso']}\n\n"
        f"{config_tipo['ejemplo']}"
    )

    st.caption(
        "Importante: este registro no pasa directo al Libro Diario. Primero queda como asiento propuesto "
        "para revisar y confirmar en la futura bandeja central."
    )


def _mostrar_plan_cuentas_referencia(empresa_id):
    with st.expander("Ayuda opcional: buscar cuenta del plan de cuentas", expanded=False):
        st.caption(
            "Este listado viene de Configuración → Plan de cuentas. "
            "Solo sirve como ayuda para copiar el código y nombre de la cuenta en el detalle del asiento; "
            "no carga nada automáticamente."
        )

        plan = obtener_plan_cuentas_opciones(empresa_id)
        if plan.empty:
            st.info("No hay plan de cuentas cargado. Podés cargarlo desde Configuración → Plan de cuentas.")
            return

        buscador = st.text_input(
            "Buscar cuenta por código o nombre",
            key="buscador_plan_cuentas_asiento_origen",
            placeholder="Ej.: caja, banco, capital, proveedores, IVA",
        )

        vista = plan.copy()
        for columna in ["cuenta_codigo", "cuenta_nombre", "imputable", "tipo"]:
            if columna not in vista.columns:
                vista[columna] = ""

        if buscador:
            patron = buscador.strip().lower()
            mascara = (
                vista["cuenta_codigo"].fillna("").astype(str).str.lower().str.contains(patron, na=False)
                | vista["cuenta_nombre"].fillna("").astype(str).str.lower().str.contains(patron, na=False)
            )
            vista = vista[mascara]

        columnas = ["cuenta_codigo", "cuenta_nombre", "imputable", "tipo"]
        columnas = [col for col in columnas if col in vista.columns]

        st.dataframe(
            preparar_vista(vista[columnas].head(80)),
            use_container_width=True,
        )

        if len(vista) > 80:
            st.caption("Se muestran las primeras 80 cuentas. Usá el buscador para afinar el resultado.")


def _mostrar_detalle_asiento(asiento):
    if not asiento:
        st.info("No se encontró el asiento.")
        return

    detalle = pd.DataFrame(asiento.get("detalle") or [])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Estado", asiento.get("estado"))
    c2.metric("Tipo", asiento.get("tipo_origen", asiento.get("origen", "")))
    c3.metric("Total Debe", moneda(asiento.get("total_debe") or 0))
    c4.metric("Total Haber", moneda(asiento.get("total_haber") or 0))

    st.caption(asiento.get("descripcion") or "")

    if detalle.empty:
        st.info("Sin detalle.")
    else:
        vista_detalle = detalle[[
            "renglon",
            "cuenta_codigo",
            "cuenta_nombre",
            "debe",
            "haber",
            "glosa",
        ]].rename(columns={
            "renglon": "Renglón",
            "cuenta_codigo": "Código",
            "cuenta_nombre": "Cuenta",
            "debe": "Debe",
            "haber": "Haber",
            "glosa": "Glosa",
        })
        st.dataframe(preparar_vista(vista_detalle), use_container_width=True)


def mostrar_asientos_apertura_aportes():
    st.subheader("🧾 Asientos de origen")

    empresa_id = empresa_actual_id()
    usuario = usuario_actual_nombre()

    migrar_ejercicios_contables()
    migrar_asientos_origen()

    st.caption(
        "Acá cargás la base contable de origen de la empresa: apertura, capital social, aportes y ajustes iniciales. "
        "No impactan directo en Libro Diario; quedan como asientos propuestos para revisión."
    )

    resumen = obtener_resumen_asientos_origen(empresa_id)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Cargados", resumen.get("asientos_origen_total", 0))
    c2.metric("Pendientes de revisión", resumen.get("asientos_propuestos_pendientes", 0))
    c3.metric("Contabilizados", resumen.get("asientos_propuestos_contabilizados", 0))
    c4.metric("Anulados", resumen.get("asientos_origen_anulados", 0))

    st.info(
        "Flujo de trabajo: 1) cargás el asiento inicial, 2) el sistema valida que Debe = Haber, "
        "3) se genera una propuesta, 4) más adelante se confirmará desde la Bandeja de Asientos Propuestos."
    )

    subtab1, subtab2, subtab3 = st.tabs([
        "Cargar asiento inicial",
        "Ver asientos cargados",
        "Ver propuestas pendientes",
    ])

    with subtab1:
        mostrar_nuevo_asiento_origen(empresa_id, usuario)

    with subtab2:
        mostrar_listado_asientos_origen(empresa_id, usuario)

    with subtab3:
        mostrar_listado_asientos_propuestos(empresa_id)


def mostrar_nuevo_asiento_origen(empresa_id, usuario, solo_apertura=False):
    ejercicios = listar_ejercicios_contables(empresa_id=empresa_id)

    if ejercicios.empty:
        st.warning("Primero cargá un ejercicio contable en la pestaña Ejercicios contables.")
        return

    st.markdown("### Cargar asiento inicial")

    opciones_tipo = list(TIPOS_ASIENTOS_INICIALES.keys())
    if solo_apertura:
        opciones_tipo = ["Asiento de apertura / saldos iniciales"]

    tipo_label = st.radio(
        "¿Qué querés registrar?",
        opciones_tipo,
        key="nuevo_asiento_origen_tipo_radio_apertura" if solo_apertura else "nuevo_asiento_origen_tipo_radio",
        horizontal=False,
    )

    config_tipo = TIPOS_ASIENTOS_INICIALES[tipo_label]
    _mostrar_ayuda_tipo_asiento(config_tipo)

    col_ejercicio, col_fecha = st.columns([2, 1])

    with col_ejercicio:
        ejercicio_id = _select_ejercicio(
            empresa_id,
            key="nuevo_asiento_origen_ejercicio",
            incluir_anulados=False,
            label="Ejercicio donde se registra",
        )

    with col_fecha:
        fecha = date_input_argentino(
            "Fecha del asiento",
            value=date.today(),
            key="nuevo_asiento_origen_fecha",
        )

    descripcion = st.text_input(
        "Descripción visible del asiento",
        value=config_tipo.get("descripcion", ""),
        key=f"nuevo_asiento_origen_descripcion_{config_tipo['codigo']}",
        placeholder="Ej.: Asiento de apertura al inicio del ejercicio",
    )

    col_ref1, col_ref2 = st.columns(2)

    with col_ref1:
        referencia = st.text_input(
            "Referencia / respaldo",
            value=config_tipo.get("referencia", ""),
            key=f"nuevo_asiento_origen_referencia_{config_tipo['codigo']}",
            placeholder="Ej.: acta, balance anterior, transferencia, papel de trabajo",
        )

    with col_ref2:
        observaciones = st.text_input(
            "Observaciones internas",
            key=f"nuevo_asiento_origen_observaciones_{config_tipo['codigo']}",
        )

    st.markdown("#### Detalle contable")
    st.caption(
        "Cargá las cuentas manualmente. Usá Debe para lo que entra o aumenta activo/gasto; "
        "usá Haber para capital, deudas, ingresos o la contrapartida. El asiento debe cuadrar."
    )

    base_editor = pd.DataFrame(config_tipo["lineas"])

    df_lineas = st.data_editor(
        base_editor,
        num_rows="dynamic",
        use_container_width=True,
        key=f"nuevo_asiento_origen_lineas_{config_tipo['codigo']}",
        column_config={
            "cuenta_codigo": st.column_config.TextColumn("Código cuenta", help="Código del plan de cuentas. Podés buscarlo abajo en la ayuda opcional."),
            "cuenta_nombre": st.column_config.TextColumn("Cuenta", help="Nombre de la cuenta contable."),
            "debe": st.column_config.NumberColumn("Debe", min_value=0.0, step=0.01),
            "haber": st.column_config.NumberColumn("Haber", min_value=0.0, step=0.01),
            "glosa": st.column_config.TextColumn("Detalle / glosa"),
        },
    )

    lineas = _lineas_desde_editor(df_lineas)
    _estado_previo_lineas(lineas)

    _mostrar_plan_cuentas_referencia(empresa_id)

    st.divider()

    confirmar = st.checkbox(
        "Confirmo que revisé el asiento y quiero generarlo como propuesta contable",
        key=f"confirmar_generar_asiento_origen_{config_tipo['codigo']}",
    )

    if st.button("Generar propuesta contable", type="primary", use_container_width=True, key=f"btn_generar_asiento_origen_{config_tipo['codigo']}"):
        if not confirmar:
            st.error("Marcá la confirmación antes de generar la propuesta.")
            return

        resultado = crear_asiento_origen(
            empresa_id=empresa_id,
            fecha=fecha,
            tipo_origen=config_tipo["codigo"],
            descripcion=descripcion,
            lineas=lineas,
            ejercicio_id=ejercicio_id,
            referencia=referencia,
            observaciones=observaciones,
            usuario=usuario,
            generar_propuesta=True,
        )
        _mostrar_resultado_servicio(resultado)
        if resultado.get("ok"):
            st.success("La propuesta quedó pendiente para revisión. Todavía no impactó en Libro Diario.")
            asiento = resultado.get("asiento")
            _mostrar_detalle_asiento(asiento)

def mostrar_listado_asientos_origen(empresa_id, usuario):
    st.markdown("### Asientos de origen cargados")

    col1, col2, col3 = st.columns(3)

    with col1:
        estado = st.selectbox(
            "Estado",
            ["Todos", "BORRADOR", "PROPUESTO", "CONTABILIZADO", "ANULADO"],
            key="listado_asientos_origen_estado",
        )

    with col2:
        tipo = st.selectbox(
            "Tipo",
            [
                "Todos",
                "APERTURA",
                "CAPITAL_SOCIAL",
                "APORTE_SOCIO",
                "APORTE_IRREVOCABLE",
                "PRESTAMO_SOCIO",
                "AJUSTE_INICIAL",
            ],
            key="listado_asientos_origen_tipo",
        )

    with col3:
        ejercicio_id = _select_ejercicio(
            empresa_id,
            key="listado_asientos_origen_ejercicio",
            incluir_anulados=False,
            label="Ejercicio",
        )

    df = listar_asientos_origen(
        empresa_id=empresa_id,
        estado=None if estado == "Todos" else estado,
        tipo_origen=None if tipo == "Todos" else tipo,
        ejercicio_id=ejercicio_id,
        incluir_anulados=True,
    )

    if df.empty:
        st.info("No hay asientos de origen con esos filtros.")
        return

    vista = df[[
        "id",
        "fecha",
        "tipo_origen",
        "descripcion",
        "estado",
        "total_debe",
        "total_haber",
        "diferencia",
        "asiento_propuesto_id",
        "usuario_creacion",
        "fecha_creacion",
    ]].rename(columns={
        "id": "ID",
        "fecha": "Fecha",
        "tipo_origen": "Tipo",
        "descripcion": "Descripción",
        "estado": "Estado",
        "total_debe": "Debe",
        "total_haber": "Haber",
        "diferencia": "Diferencia",
        "asiento_propuesto_id": "Asiento propuesto",
        "usuario_creacion": "Usuario",
        "fecha_creacion": "Fecha carga",
    })

    st.dataframe(preparar_vista(vista), use_container_width=True)

    st.divider()

    ids = df["id"].astype(int).tolist()
    asiento_id = st.selectbox(
        "Ver detalle / gestionar asiento",
        ids,
        key="detalle_asiento_origen_id",
    )

    asiento = obtener_asiento_origen(asiento_id)
    _mostrar_detalle_asiento(asiento)

    with st.expander("Auditoría del asiento de origen"):
        eventos = listar_eventos_asiento_origen(asiento_id)
        if eventos.empty:
            st.info("Sin eventos para este asiento.")
        else:
            st.dataframe(preparar_vista(eventos), use_container_width=True)

    st.markdown("#### Anulación controlada")
    st.caption("Solo se puede anular si todavía no fue contabilizado. La propuesta vinculada se anula junto con el origen.")

    motivo = st.text_input(
        "Motivo de anulación",
        key="motivo_anular_asiento_origen",
    )

    if st.button("Anular asiento de origen", use_container_width=True, key="btn_anular_asiento_origen"):
        resultado = anular_asiento_origen(
            asiento_origen_id=asiento_id,
            motivo=motivo,
            usuario=usuario,
        )
        _mostrar_resultado_servicio(resultado)
        if resultado.get("ok"):
            st.rerun()


def mostrar_listado_asientos_propuestos(empresa_id):
    st.markdown("### Asientos propuestos")

    st.info(
        "Esta sección usa la Bandeja central de asientos propuestos. "
        "Desde acá se puede revisar el detalle, contabilizar en Libro Diario, "
        "rechazar propuestas pendientes o generar reversos controlados de asientos ya contabilizados."
    )

    mostrar_bandeja_asientos_propuestos_ui(
        empresa_id=empresa_id,
        usuario=usuario_actual_nombre(),
        key_prefix="inicio_contable_bandeja_asientos",
    )


# ======================================================
# LIBRO DIARIO
# ======================================================

def mostrar_libro_diario():
    st.subheader("📓 Libro Diario")

    mostrar_alerta_redondeo()

    df = cargar_libro_diario()

    if df.empty:
        st.info("Sin movimientos contables.")
        return

    df = aplicar_filtros_contables(df, "diario")

    if df.empty:
        st.info("No hay movimientos con los filtros seleccionados.")
        return

    df = df.sort_values(
        by=["fecha_orden", "id_asiento", "id"],
        ascending=True,
        na_position="last"
    )

    df_vista = df[[
        "id_asiento",
        "fecha_mostrar",
        "cuenta",
        "debe",
        "haber",
        "glosa",
        "origen",
        "archivo"
    ]].copy()

    df_vista = df_vista.rename(columns={
        "id_asiento": "Asiento",
        "fecha_mostrar": "Fecha",
        "cuenta": "Cuenta",
        "debe": "Debe",
        "haber": "Haber",
        "glosa": "Glosa",
        "origen": "Origen",
        "archivo": "Archivo"
    })

    df_vista_con_espacios = insertar_espacios_entre_asientos(
        df_vista.rename(columns={
            "Asiento": "id_asiento",
            "Fecha": "fecha",
            "Cuenta": "cuenta",
            "Debe": "debe",
            "Haber": "haber",
            "Glosa": "glosa",
            "Origen": "origen",
            "Archivo": "archivo"
        })
    )

    df_vista_con_espacios = df_vista_con_espacios.rename(columns={
        "id_asiento": "Asiento",
        "fecha": "Fecha",
        "cuenta": "Cuenta",
        "debe": "Debe",
        "haber": "Haber",
        "glosa": "Glosa",
        "origen": "Origen",
        "archivo": "Archivo"
    })

    st.dataframe(
        preparar_vista(df_vista_con_espacios),
        use_container_width=True
    )

    st.divider()

    mostrar_metricas_cuadre(df)

    excel = exportar_excel({
        "Libro Diario": df_vista
    })

    st.download_button(
        "Descargar Libro Diario Excel",
        data=excel,
        file_name="libro_diario.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    st.divider()

    st.warning(
        "La limpieza del Libro Diario ahora está en la pestaña "
        "'Limpieza admin/demo', con conteo real y confirmación fuerte."
    )


# ======================================================
# LIBRO MAYOR
# ======================================================

def mostrar_libro_mayor():
    st.subheader("📒 Libro Mayor")

    df = cargar_libro_diario()

    if df.empty:
        st.info("Sin movimientos contables.")
        return

    df = aplicar_filtros_contables(df, "mayor")

    if df.empty:
        st.info("No hay movimientos con los filtros seleccionados.")
        return

    resumen_cuentas = (
        df
        .groupby("cuenta", dropna=False)
        .agg(
            movimientos=("id", "count"),
            debe=("debe", "sum"),
            haber=("haber", "sum")
        )
        .reset_index()
    )

    resumen_cuentas["saldo"] = resumen_cuentas["debe"] - resumen_cuentas["haber"]
    resumen_cuentas["saldo_deudor"] = resumen_cuentas["saldo"].apply(lambda x: x if x > 0 else 0)
    resumen_cuentas["saldo_acreedor"] = resumen_cuentas["saldo"].apply(lambda x: abs(x) if x < 0 else 0)

    resumen_cuentas = resumen_cuentas.sort_values("cuenta")

    vista_resumen = resumen_cuentas.rename(columns={
        "cuenta": "Cuenta",
        "movimientos": "Movimientos",
        "debe": "Debe",
        "haber": "Haber",
        "saldo": "Saldo",
        "saldo_deudor": "Saldo Deudor",
        "saldo_acreedor": "Saldo Acreedor"
    })

    st.subheader("Resumen por cuenta")
    st.dataframe(
        preparar_vista(vista_resumen),
        use_container_width=True
    )

    st.divider()

    cuentas = sorted(df["cuenta"].dropna().astype(str).unique().tolist())

    cuenta_detalle = st.selectbox(
        "Ver detalle de cuenta",
        cuentas,
        key="mayor_detalle_cuenta"
    )

    df_detalle = df[df["cuenta"] == cuenta_detalle].copy()

    df_detalle = df_detalle.sort_values(
        by=["fecha_orden", "id_asiento", "id"],
        ascending=True,
        na_position="last"
    )

    df_detalle["saldo_movimiento"] = df_detalle["debe"] - df_detalle["haber"]
    df_detalle["saldo_acumulado"] = df_detalle["saldo_movimiento"].cumsum()

    vista_detalle = df_detalle[[
        "fecha_mostrar",
        "id_asiento",
        "glosa",
        "debe",
        "haber",
        "saldo_acumulado",
        "origen",
        "archivo"
    ]].copy()

    vista_detalle = vista_detalle.rename(columns={
        "fecha_mostrar": "Fecha",
        "id_asiento": "Asiento",
        "glosa": "Glosa",
        "debe": "Debe",
        "haber": "Haber",
        "saldo_acumulado": "Saldo acumulado",
        "origen": "Origen",
        "archivo": "Archivo"
    })

    st.subheader(f"Detalle mayor: {cuenta_detalle}")
    st.dataframe(
        preparar_vista(vista_detalle),
        use_container_width=True
    )

    excel = exportar_excel({
        "Mayor resumen": vista_resumen,
        "Mayor detalle": vista_detalle
    })

    st.download_button(
        "Descargar Libro Mayor Excel",
        data=excel,
        file_name="libro_mayor.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


# ======================================================
# BALANCE DE SUMAS Y SALDOS
# ======================================================

def mostrar_balance_sumas_saldos():
    st.subheader("📊 Balance de Sumas y Saldos")

    df = cargar_libro_diario()

    if df.empty:
        st.info("Sin movimientos contables.")
        return

    df = aplicar_filtros_contables(df, "balance")

    if df.empty:
        st.info("No hay movimientos con los filtros seleccionados.")
        return

    balance = (
        df
        .groupby("cuenta", dropna=False)
        .agg(
            debe=("debe", "sum"),
            haber=("haber", "sum")
        )
        .reset_index()
    )

    balance["saldo"] = balance["debe"] - balance["haber"]
    balance["saldo_deudor"] = balance["saldo"].apply(lambda x: x if x > 0 else 0)
    balance["saldo_acreedor"] = balance["saldo"].apply(lambda x: abs(x) if x < 0 else 0)

    balance = balance.sort_values("cuenta")

    total_debe = balance["debe"].sum()
    total_haber = balance["haber"].sum()
    total_saldo_deudor = balance["saldo_deudor"].sum()
    total_saldo_acreedor = balance["saldo_acreedor"].sum()

    vista_balance = balance.rename(columns={
        "cuenta": "Cuenta",
        "debe": "Sumas Debe",
        "haber": "Sumas Haber",
        "saldo": "Saldo técnico",
        "saldo_deudor": "Saldo Deudor",
        "saldo_acreedor": "Saldo Acreedor"
    })

    st.dataframe(
        preparar_vista(vista_balance),
        use_container_width=True
    )

    st.divider()

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Total Sumas Debe", moneda(total_debe))
    c2.metric("Total Sumas Haber", moneda(total_haber))
    c3.metric("Total Saldo Deudor", moneda(total_saldo_deudor))
    c4.metric("Total Saldo Acreedor", moneda(total_saldo_acreedor))

    diferencia_sumas = round(total_debe - total_haber, 2)
    diferencia_saldos = round(total_saldo_deudor - total_saldo_acreedor, 2)

    if diferencia_sumas != 0:
        st.error(f"Las sumas no cuadran. Diferencia: {moneda(diferencia_sumas)}")
    else:
        st.success("Las sumas Debe y Haber cuadran.")

    if diferencia_saldos != 0:
        st.error(f"Los saldos no cuadran. Diferencia: {moneda(diferencia_saldos)}")
    else:
        st.success("Los saldos deudores y acreedores cuadran.")

    excel = exportar_excel({
        "Balance Sumas y Saldos": vista_balance
    })

    st.download_button(
        "Descargar Balance de Sumas y Saldos Excel",
        data=excel,
        file_name="balance_sumas_saldos.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


# ======================================================
# CONTROL POR ORIGEN / ARCHIVO
# ======================================================

def mostrar_control_origen_archivo():
    st.subheader("🧭 Control por origen / archivo")

    df = cargar_libro_diario()

    if df.empty:
        st.info("Sin movimientos contables.")
        return

    df = aplicar_filtros_contables(df, "control")

    if df.empty:
        st.info("No hay movimientos con los filtros seleccionados.")
        return

    resumen_origen = (
        df
        .groupby("origen", dropna=False)
        .agg(
            movimientos=("id", "count"),
            debe=("debe", "sum"),
            haber=("haber", "sum")
        )
        .reset_index()
    )

    resumen_origen["diferencia"] = resumen_origen["debe"] - resumen_origen["haber"]

    resumen_archivo = (
        df
        .groupby(["origen", "archivo"], dropna=False)
        .agg(
            movimientos=("id", "count"),
            debe=("debe", "sum"),
            haber=("haber", "sum")
        )
        .reset_index()
    )

    resumen_archivo["diferencia"] = resumen_archivo["debe"] - resumen_archivo["haber"]

    st.subheader("Resumen por origen")
    st.dataframe(
        preparar_vista(resumen_origen),
        use_container_width=True
    )

    st.divider()

    st.subheader("Resumen por archivo")
    st.dataframe(
        preparar_vista(resumen_archivo),
        use_container_width=True
    )

    st.divider()

    descuadres = resumen_archivo[resumen_archivo["diferencia"].round(2) != 0].copy()

    if descuadres.empty:
        st.success("No se detectan archivos descuadrados en el Libro Diario.")
    else:
        st.error("Se detectan archivos con diferencia entre Debe y Haber.")
        st.dataframe(
            preparar_vista(descuadres),
            use_container_width=True
        )

    excel = exportar_excel({
        "Resumen por Origen": resumen_origen,
        "Resumen por Archivo": resumen_archivo,
        "Archivos Descuadrados": descuadres
    })

    st.download_button(
        "Descargar Control Contable Excel",
        data=excel,
        file_name="control_contable_origen_archivo.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


# ======================================================
# LIMPIEZA ADMIN / DEMO
# ======================================================

def mostrar_limpieza_admin_demo():
    st.subheader("🧹 Limpieza administrativa / demo")

    if not usuario_es_administrador():
        st.error("Solo un administrador puede acceder a la limpieza administrativa.")
        return

    st.warning(
        "Esta pantalla es para demo, pruebas y correcciones administrativas. "
        "En operación real se debe usar anulación/reversión, no borrado físico."
    )

    empresa_id = empresa_actual_id()

    st.markdown("### Diagnóstico actual")

    diagnostico = diagnosticar_datos_demo(empresa_id)

    if diagnostico.empty:
        st.info("No se pudo obtener diagnóstico.")
    else:
        st.dataframe(
            preparar_vista(diagnostico),
            use_container_width=True,
        )

    st.divider()

    st.markdown("### Acciones puntuales")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### Limpiar solo Libro Diario")
        st.caption("Borra únicamente asientos contables. No borra recibos, pagos, tesorería ni banco.")

        texto_diario = st.text_input(
            "Escribí LIMPIAR DIARIO",
            key="admin_limpieza_texto_diario",
        )

        if st.button("Limpiar Libro Diario", use_container_width=True):
            resultado = limpiar_libro_diario_admin(
                empresa_id=empresa_id,
                confirmar_texto=texto_diario,
            )
            mostrar_resultado_limpieza(resultado)
            if resultado.get("ok"):
                st.rerun()

    with col2:
        st.markdown("#### Limpiar Banco demo")
        st.caption("Borra movimientos bancarios, importaciones y conciliaciones bancarias de prueba.")

        texto_banco = st.text_input(
            "Escribí BORRAR BANCO",
            key="admin_limpieza_texto_banco",
        )

        if st.button("Borrar Banco demo", use_container_width=True):
            resultado = limpiar_banco_demo_admin(
                empresa_id=empresa_id,
                confirmar_texto=texto_banco,
            )
            mostrar_resultado_limpieza(resultado)
            if resultado.get("ok"):
                st.rerun()

    st.divider()

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### Borrar Recibos / Cobranzas demo")
        st.caption("Borra cobranzas, recibos, imputaciones, cuenta corriente, tesorería y asientos vinculados.")

        texto_recibos = st.text_input(
            "Escribí BORRAR RECIBOS",
            key="admin_limpieza_texto_recibos",
        )

        if st.button("Borrar Recibos / Cobranzas", use_container_width=True):
            resultado = limpiar_cobranzas_recibos_admin(
                empresa_id=empresa_id,
                confirmar_texto=texto_recibos,
            )
            mostrar_resultado_limpieza(resultado)
            if resultado.get("ok"):
                st.rerun()

    with col2:
        st.markdown("#### Borrar Órdenes / Pagos demo")
        st.caption("Borra pagos, órdenes, imputaciones, cuenta corriente, tesorería y asientos vinculados.")

        texto_ordenes = st.text_input(
            "Escribí BORRAR ORDENES",
            key="admin_limpieza_texto_ordenes",
        )

        if st.button("Borrar Órdenes / Pagos", use_container_width=True):
            resultado = limpiar_pagos_ordenes_admin(
                empresa_id=empresa_id,
                confirmar_texto=texto_ordenes,
            )
            mostrar_resultado_limpieza(resultado)
            if resultado.get("ok"):
                st.rerun()

    st.divider()

    st.markdown("### Limpieza demo completa")

    st.error(
        "Esta acción borra la operatoria demo: banco, cobranzas, pagos, tesorería, cuentas corrientes, "
        "libro diario, ventas/compras cargadas e historial de cargas. "
        "No borra usuarios, empresas, plan de cuentas ni configuraciones base."
    )

    texto_demo = st.text_input(
        "Escribí LIMPIAR DEMO",
        key="admin_limpieza_texto_demo",
    )

    if st.button("LIMPIAR DEMO OPERATIVA COMPLETA", type="primary", use_container_width=True):
        resultado = limpiar_demo_operativa_admin(
            empresa_id=empresa_id,
            confirmar_texto=texto_demo,
        )
        mostrar_resultado_limpieza(resultado)
        if resultado.get("ok"):
            st.rerun()