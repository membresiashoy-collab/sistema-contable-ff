import pandas as pd
import streamlit as st

from core.exportadores import exportar_excel
from core.numeros import moneda
from core.ui import preparar_vista

from services.bancos_service import (
    TIPOS_MOVIMIENTO_BANCO,
    analizar_archivo_extracto,
    crear_regla_bancaria,
    guardar_importacion_bancaria,
    inicializar_bancos,
    obtener_asientos_propuestos_banco,
    obtener_configuracion_contable_bancos,
    obtener_grupos_fiscales_bancarios,
    obtener_importaciones_bancarias,
    obtener_movimientos_bancarios,
    obtener_movimientos_pendientes_imputacion,
    obtener_patrones_recurrentes,
    obtener_reglas_bancarias,
    obtener_resumen_bancario,
    obtener_resumen_operativo_importacion,
)

from services.bancos_operaciones_service import (
    desimputar_conciliacion_bancaria,
    eliminar_importacion_bancaria,
    obtener_conciliaciones_bancarias,
    obtener_clientes_con_saldo_pendiente,
    obtener_facturas_cliente_pendientes,
    obtener_facturas_proveedor_pendientes,
    obtener_proveedores_con_saldo_pendiente,
    obtener_resumen_eliminacion_importacion_bancaria,
    registrar_imputacion_cobro,
    registrar_imputacion_pago,
    registrar_pago_fiscal,
    regenerar_asientos_bancarios_agrupados,
)


# ======================================================
# ETIQUETAS CONTABLES Y UTILIDADES
# ======================================================

TIPOS_MOVIMIENTO_BANCO_UI = {
    "COBRO_POSIBLE": "Cobro posible",
    "PAGO_POSIBLE": "Pago posible",
    "PAGO_IMPUESTOS": "Pago de impuestos",
    "GASTO_BANCARIO_GRAVADO": "Gasto bancario gravado",
    "IVA_CREDITO_FISCAL_BANCARIO": "IVA crédito fiscal bancario",
    "PERCEPCION_IVA_BANCARIA": "Percepción IVA bancaria",
    "RECAUDACION_IIBB": "Percepción IIBB bancaria",
    "IMPUESTO_DEBITOS_CREDITOS": "Impuesto sobre débitos y créditos bancarios",
    "INTERES_BANCARIO_POSIBLE_105": "Interés bancario a revisar",
    "INVERSION_RESCATE": "Inversión / rescate",
    "MOVIMIENTO_SOCIOS": "Movimiento de socios",
    "TRANSFERENCIA_ENTRE_CUENTAS": "Transferencia entre cuentas propias",
    "EFECTIVO_CAJA": "Efectivo / Caja",
    "OTRO_GASTO_A_REVISAR": "Otro gasto a revisar",
    "A_REVISAR": "A revisar",
}


def nombre_tipo_movimiento_ui(tipo):
    tipo = str(tipo or "").strip()
    return TIPOS_MOVIMIENTO_BANCO_UI.get(tipo, tipo.replace("_", " ").capitalize())


def empresa_actual_id():
    return int(st.session_state.get("empresa_id", 1))


def usuario_actual_id():
    usuario = st.session_state.get("usuario") or {}
    return usuario.get("id")


def usuario_es_administrador():
    usuario = st.session_state.get("usuario") or {}
    rol = str(usuario.get("rol", "")).strip().upper()
    return rol in {"ADMINISTRADOR", "ADMIN", "SUPERADMIN"}


def obtener_version_uploader_banco():
    if "banco_uploader_version" not in st.session_state:
        st.session_state["banco_uploader_version"] = 1

    return int(st.session_state["banco_uploader_version"])


def avanzar_version_uploader_banco():
    st.session_state["banco_uploader_version"] = obtener_version_uploader_banco() + 1


def guardar_resultado_importacion_banco(nombre_archivo, resultado):
    st.session_state["banco_ultimo_resultado_importacion"] = {
        "archivo": nombre_archivo,
        "resultado": resultado,
    }


def limpiar_resultado_importacion_banco():
    if "banco_ultimo_resultado_importacion" in st.session_state:
        del st.session_state["banco_ultimo_resultado_importacion"]


def _numero(valor):
    try:
        if valor is None or pd.isna(valor):
            return 0.0
    except Exception:
        if valor is None:
            return 0.0

    try:
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


def _etiqueta_movimiento(row):
    importe = _numero(row.get("importe"))
    fecha = _texto(row.get("fecha"))
    concepto = _texto(row.get("concepto"))
    tipo = nombre_tipo_movimiento_ui(_texto(row.get("tipo_movimiento_sugerido")))
    pendiente = _numero(row.get("importe_pendiente"))

    return (
        f"Movimiento #{int(row['id'])} | {fecha} | {tipo} | "
        f"{moneda(abs(importe))} | Pendiente {moneda(pendiente)} | {concepto[:80]}"
    )


def _etiqueta_tercero(row, campo_nombre):
    nombre = _texto(row.get(campo_nombre))
    cuit = _texto(row.get("cuit"))
    saldo = _numero(row.get("saldo"))

    if cuit:
        return f"{nombre} | CUIT {cuit} | Saldo {moneda(saldo)}"

    return f"{nombre} | Saldo {moneda(saldo)}"


def _etiqueta_importacion(row):
    importacion_id = int(row["id"])
    procesados = int(row.get("procesados", 0) or 0)
    duplicados = int(row.get("duplicados", 0) or 0)
    detectados = int(row.get("registros_detectados", 0) or 0)

    if procesados > 0:
        estado = "con movimientos importados"
    elif duplicados > 0 and procesados == 0:
        estado = "duplicada sin movimientos nuevos"
    else:
        estado = "sin movimientos importados"

    return (
        f"Carga #{importacion_id} | {row.get('fecha_carga', '')} | "
        f"{row.get('nombre_archivo', '')} | {row.get('banco', '')} | "
        f"{estado} | detectados: {detectados} | importados: {procesados} | duplicados: {duplicados}"
    )


def _preparar_facturas_para_vista(df):
    if df.empty:
        return df

    vista = df.copy()
    vista = vista.rename(columns={
        "fecha": "Fecha",
        "tipo": "Tipo",
        "numero": "Número",
        "debe": "Debe",
        "haber": "Haber",
        "pendiente": "Pendiente",
    })

    columnas = ["Fecha", "Tipo", "Número", "Debe", "Haber", "Pendiente"]
    columnas = [c for c in columnas if c in vista.columns]

    return vista[columnas]


# ======================================================
# RESULTADO DE IMPORTACIÓN
# ======================================================

def mostrar_resultado_importacion_banco():
    data = st.session_state.get("banco_ultimo_resultado_importacion")

    if not data:
        return

    archivo = data.get("archivo", "")
    resultado = data.get("resultado", {})
    importacion_id = resultado.get("importacion_id")

    st.subheader("Resultado de importación")

    detectados = int(resultado.get("detectados", 0) or 0)
    procesados = int(resultado.get("procesados", 0) or 0)
    duplicados = int(resultado.get("duplicados", 0) or 0)
    errores = int(resultado.get("errores", 0) or 0)

    if procesados == 0 and duplicados > 0:
        st.warning(
            f"El archivo **{archivo}** ya estaba importado o sus movimientos ya existían. "
            f"Se omitieron **{duplicados}** movimientos duplicados y no se agregaron movimientos nuevos."
        )
    else:
        st.success(f"Archivo procesado: **{archivo}**")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Detectados", detectados)
    col2.metric("Nuevos importados", procesados)
    col3.metric("Duplicados omitidos", duplicados)
    col4.metric("Errores", errores)

    if importacion_id:
        resumen = obtener_resumen_operativo_importacion(
            importacion_id=importacion_id,
            empresa_id=empresa_actual_id(),
        )

        totales = resumen.get("totales", {})

        st.markdown("#### Resumen operativo")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Automáticos propuestos", totales.get("automaticos", 0))
        c2.metric("Revisión asistida", totales.get("revision", 0))
        c3.metric("Pendientes de imputación", totales.get("pendientes", 0))
        c4.metric("Líneas de asiento", totales.get("lineas_asiento", 0))

        debe = float(totales.get("debe_asiento", 0) or 0)
        haber = float(totales.get("haber_asiento", 0) or 0)
        diferencia = round(debe - haber, 2)

        if totales.get("lineas_asiento", 0) > 0:
            if abs(diferencia) <= 0.01:
                st.success(
                    f"Asientos propuestos balanceados. "
                    f"Debe: {moneda(debe)} / Haber: {moneda(haber)}."
                )
            else:
                st.error(
                    f"Los asientos propuestos no cuadran. "
                    f"Debe: {moneda(debe)} / Haber: {moneda(haber)} / Diferencia: {moneda(diferencia)}."
                )

    if st.button("Ocultar resultado de importación"):
        limpiar_resultado_importacion_banco()
        st.rerun()

    st.divider()


# ======================================================
# PREPARADORES DE VISTA
# ======================================================

def preparar_movimientos_vista(df):
    if df.empty:
        return df

    vista = df.copy()

    if "tipo_movimiento_sugerido" in vista.columns:
        vista["tipo_visible"] = vista["tipo_movimiento_sugerido"].apply(nombre_tipo_movimiento_ui)

    columnas = [
        "id",
        "fecha",
        "banco",
        "nombre_cuenta",
        "referencia",
        "causal",
        "concepto",
        "importe",
        "debito",
        "credito",
        "saldo",
        "importe_conciliado",
        "importe_pendiente",
        "porcentaje_conciliado",
        "tipo_visible",
        "confianza_sugerencia",
        "cuenta_debe_codigo",
        "cuenta_debe_nombre",
        "cuenta_haber_codigo",
        "cuenta_haber_nombre",
        "tratamiento_fiscal",
        "estado_conciliacion",
        "estado_contable",
        "archivo",
    ]

    columnas = [c for c in columnas if c in vista.columns]
    vista = vista[columnas].copy()

    return vista.rename(columns={
        "id": "ID",
        "fecha": "Fecha",
        "banco": "Banco",
        "nombre_cuenta": "Cuenta",
        "referencia": "Referencia",
        "causal": "Causal",
        "concepto": "Concepto",
        "importe": "Importe",
        "debito": "Débito",
        "credito": "Crédito",
        "saldo": "Saldo",
        "importe_conciliado": "Conciliado",
        "importe_pendiente": "Pendiente",
        "porcentaje_conciliado": "% conciliado",
        "tipo_visible": "Tipo sugerido",
        "confianza_sugerencia": "Confianza",
        "cuenta_debe_codigo": "Debe cód.",
        "cuenta_debe_nombre": "Debe cuenta",
        "cuenta_haber_codigo": "Haber cód.",
        "cuenta_haber_nombre": "Haber cuenta",
        "tratamiento_fiscal": "Tratamiento fiscal",
        "estado_conciliacion": "Estado conciliación",
        "estado_contable": "Estado contable",
        "archivo": "Archivo",
    })


def preparar_previsualizacion(df):
    if df.empty:
        return df

    vista = df.copy()
    vista["tipo_visible"] = vista["tipo_movimiento_sugerido"].apply(nombre_tipo_movimiento_ui)

    columnas = [
        "fecha",
        "referencia",
        "causal",
        "concepto",
        "importe",
        "debito",
        "credito",
        "saldo",
        "importe_pendiente",
        "tipo_visible",
        "confianza_sugerencia",
        "motivo_sugerencia",
        "cuenta_debe_codigo",
        "cuenta_debe_nombre",
        "cuenta_haber_codigo",
        "cuenta_haber_nombre",
    ]

    columnas = [c for c in columnas if c in vista.columns]
    vista = vista[columnas].copy()

    return vista.rename(columns={
        "fecha": "Fecha",
        "referencia": "Referencia",
        "causal": "Causal",
        "concepto": "Concepto",
        "importe": "Importe",
        "debito": "Débito",
        "credito": "Crédito",
        "saldo": "Saldo",
        "importe_pendiente": "Pendiente conciliación",
        "tipo_visible": "Tipo sugerido",
        "confianza_sugerencia": "Confianza",
        "motivo_sugerencia": "Motivo",
        "cuenta_debe_codigo": "Debe cód.",
        "cuenta_debe_nombre": "Debe cuenta",
        "cuenta_haber_codigo": "Haber cód.",
        "cuenta_haber_nombre": "Haber cuenta",
    })


# ======================================================
# MÓDULO PRINCIPAL
# ======================================================

def mostrar_bancos():
    inicializar_bancos()

    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
        "Importar extracto",
        "Pendientes de imputación",
        "Asientos propuestos",
        "Movimientos bancarios",
        "Control fiscal bancario",
        "Reglas recurrentes",
        "Control de saldos",
        "Importaciones",
    ])

    with tab1:
        mostrar_importar_extracto()

    with tab2:
        mostrar_pendientes_imputacion()

    with tab3:
        mostrar_asientos_propuestos()

    with tab4:
        mostrar_movimientos_bancarios()

    with tab5:
        mostrar_control_fiscal_bancario()

    with tab6:
        mostrar_reglas_recurrentes()

    with tab7:
        mostrar_control_saldos()

    with tab8:
        mostrar_importaciones()


# ======================================================
# IMPORTACIÓN DE EXTRACTO
# ======================================================

def mostrar_importar_extracto():
    st.subheader("Importar extracto bancario")

    st.info(
        "Cargá el extracto. El sistema separa automáticamente lo rutinario de lo que requiere decisión: "
        "gastos bancarios, IVA crédito fiscal bancario, percepciones e impuesto sobre débitos y créditos "
        "generan asientos propuestos; cobros, pagos, ARCA/AFIP, inversiones, socios y otros quedan para imputación."
    )

    mostrar_resultado_importacion_banco()

    empresa_id = empresa_actual_id()

    col1, col2, col3 = st.columns([1.2, 1.4, 1])

    with col1:
        banco = st.text_input("Banco", value="Banco Macro")

    with col2:
        nombre_cuenta = st.text_input("Nombre de cuenta", value="Cuenta corriente principal")

    with col3:
        formato = st.selectbox(
            "Formato",
            [
                "Detección automática",
                "Banco Macro",
                "CSV genérico importe único",
                "CSV genérico débito/crédito",
                "Mapeo manual",
            ],
        )

    archivo = st.file_uploader(
        "Subir extracto bancario",
        type=["xls", "xlsx", "csv", "txt"],
        key=f"banco_extracto_uploader_{obtener_version_uploader_banco()}",
    )

    if not archivo:
        st.caption(
            "Después de procesar un archivo, el cargador se limpia para evitar confusión. "
            "Si necesitás revisar una importación anterior, usá la pestaña Importaciones."
        )
        return

    contenido = archivo.getvalue()
    analisis = analizar_archivo_extracto(archivo.name, contenido)

    if not analisis["ok"] or formato == "Mapeo manual":
        st.warning("El sistema necesita revisar o confirmar el mapeo de columnas.")

        columnas = analisis.get("columnas_detectadas", [])

        if not columnas:
            st.error("No se pudieron detectar columnas en el archivo.")
            return

        with st.expander("Ver archivo original detectado", expanded=False):
            st.dataframe(
                preparar_vista(analisis.get("df_preview", pd.DataFrame()).head(40)),
                use_container_width=True,
            )

        st.subheader("Mapeo manual de columnas")
        st.caption(
            "Asigná al menos Fecha, Concepto e Importe. Si el banco trae Débito y Crédito separados, "
            "podés dejar Importe en 'No usar' y asignar Débito/Crédito."
        )

        opciones = ["No usar"] + columnas
        mapeo_manual = {}

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            mapeo_manual["fecha"] = st.selectbox("Fecha", opciones, index=_indice_sugerido(opciones, analisis, "fecha"))
            mapeo_manual["referencia"] = st.selectbox("Referencia", opciones, index=_indice_sugerido(opciones, analisis, "referencia"))

        with col2:
            mapeo_manual["causal"] = st.selectbox("Causal / código", opciones, index=_indice_sugerido(opciones, analisis, "causal"))
            mapeo_manual["concepto"] = st.selectbox("Concepto", opciones, index=_indice_sugerido(opciones, analisis, "concepto"))

        with col3:
            mapeo_manual["importe"] = st.selectbox("Importe único", opciones, index=_indice_sugerido(opciones, analisis, "importe"))
            mapeo_manual["saldo"] = st.selectbox("Saldo", opciones, index=_indice_sugerido(opciones, analisis, "saldo"))

        with col4:
            mapeo_manual["debito"] = st.selectbox("Débito", opciones, index=_indice_sugerido(opciones, analisis, "debito"))
            mapeo_manual["credito"] = st.selectbox("Crédito", opciones, index=_indice_sugerido(opciones, analisis, "credito"))

        if not st.button("Aplicar mapeo y analizar extracto", type="primary"):
            return

        analisis = analizar_archivo_extracto(
            archivo.name,
            contenido,
            mapeo_manual=mapeo_manual,
        )

    if not analisis["ok"]:
        st.error(analisis["mensaje"])
        return

    df_movimientos = analisis["df_movimientos"]

    if df_movimientos.empty:
        st.warning("No se detectaron movimientos válidos en el archivo.")
        return

    st.success("Extracto interpretado correctamente.")

    control = analisis.get("control_saldo", {})

    st.subheader("Control del extracto")

    total_creditos = float(control.get("total_creditos", 0))
    total_debitos = float(control.get("total_debitos", 0))
    saldo_inicial_default = float(control.get("saldo_inicial_estimado", 0))
    saldo_final_default = float(control.get("saldo_final_extracto", 0))

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        saldo_inicial = st.number_input(
            "Saldo inicial extracto",
            value=saldo_inicial_default,
            step=0.01,
        )

    with col2:
        st.metric("Créditos", moneda(total_creditos))

    with col3:
        st.metric("Débitos", moneda(total_debitos))

    with col4:
        saldo_final = st.number_input(
            "Saldo final extracto",
            value=saldo_final_default,
            step=0.01,
        )

    saldo_final_calculado = saldo_inicial + total_creditos - total_debitos
    diferencia = round(saldo_final - saldo_final_calculado, 2)

    if abs(diferencia) <= 0.01:
        st.success("El control de saldo cierra correctamente.")
    else:
        saldo_inicial_sugerido = saldo_final - total_creditos + total_debitos
        st.warning(
            f"El control de saldo muestra diferencia de {moneda(diferencia)}. "
            f"Para cerrar con este saldo final, el saldo inicial debería ser aproximadamente "
            f"{moneda(saldo_inicial_sugerido)}."
        )

    df_tmp = df_movimientos.copy()
    df_tmp["tipo_visible"] = df_tmp["tipo_movimiento_sugerido"].apply(nombre_tipo_movimiento_ui)

    tipos_automaticos = [
        "GASTO_BANCARIO_GRAVADO",
        "IVA_CREDITO_FISCAL_BANCARIO",
        "PERCEPCION_IVA_BANCARIA",
        "RECAUDACION_IIBB",
        "IMPUESTO_DEBITOS_CREDITOS",
    ]

    tipos_revision = [
        "PAGO_IMPUESTOS",
        "INTERES_BANCARIO_POSIBLE_105",
        "INVERSION_RESCATE",
        "MOVIMIENTO_SOCIOS",
        "TRANSFERENCIA_ENTRE_CUENTAS",
        "EFECTIVO_CAJA",
        "OTRO_GASTO_A_REVISAR",
        "A_REVISAR",
    ]

    tipos_pendientes = [
        "COBRO_POSIBLE",
        "PAGO_POSIBLE",
        "PAGO_IMPUESTOS",
        "INTERES_BANCARIO_POSIBLE_105",
        "INVERSION_RESCATE",
        "MOVIMIENTO_SOCIOS",
        "TRANSFERENCIA_ENTRE_CUENTAS",
        "EFECTIVO_CAJA",
        "OTRO_GASTO_A_REVISAR",
        "A_REVISAR",
    ]

    df_automaticos = df_tmp[df_tmp["tipo_movimiento_sugerido"].isin(tipos_automaticos)].copy()
    df_revision = df_tmp[df_tmp["tipo_movimiento_sugerido"].isin(tipos_revision)].copy()
    df_pendientes = df_tmp[df_tmp["tipo_movimiento_sugerido"].isin(tipos_pendientes)].copy()

    st.subheader("Resultado esperado de la importación")

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Movimientos detectados", len(df_tmp))
    col2.metric("Asiento automático propuesto", len(df_automaticos))
    col3.metric("Revisión asistida", len(df_revision))
    col4.metric("Pendientes de imputación", len(df_pendientes))

    st.markdown("#### Conceptos que irán a asientos propuestos")

    if df_automaticos.empty:
        st.info("No se detectaron conceptos automáticos para asiento propuesto.")
    else:
        resumen_auto = (
            df_automaticos
            .groupby(["tipo_movimiento_sugerido", "tipo_visible"], as_index=False)
            .agg(
                movimientos=("fecha", "count"),
                debitos=("debito", "sum"),
                creditos=("credito", "sum"),
                neto=("importe", "sum"),
            )
            .sort_values(["movimientos", "debitos"], ascending=False)
        )

        vista_auto = resumen_auto.rename(columns={
            "tipo_visible": "Concepto",
            "movimientos": "Movimientos",
            "debitos": "Débitos",
            "creditos": "Créditos",
            "neto": "Neto",
        })

        st.dataframe(
            preparar_vista(vista_auto[["Concepto", "Movimientos", "Débitos", "Créditos", "Neto"]]),
            use_container_width=True,
        )

    st.markdown("#### Conceptos que requieren revisión o imputación")

    if df_pendientes.empty:
        st.success("No se detectaron movimientos pendientes de imputación manual.")
    else:
        resumen_pend = (
            df_pendientes
            .groupby(["tipo_movimiento_sugerido", "tipo_visible"], as_index=False)
            .agg(
                movimientos=("fecha", "count"),
                debitos=("debito", "sum"),
                creditos=("credito", "sum"),
                neto=("importe", "sum"),
            )
            .sort_values(["movimientos", "debitos", "creditos"], ascending=False)
        )

        vista_pend = resumen_pend.rename(columns={
            "tipo_visible": "Concepto",
            "movimientos": "Movimientos",
            "debitos": "Débitos",
            "creditos": "Créditos",
            "neto": "Neto",
        })

        st.dataframe(
            preparar_vista(vista_pend[["Concepto", "Movimientos", "Débitos", "Créditos", "Neto"]]),
            use_container_width=True,
        )

    with st.expander("Ver detalle técnico del extracto", expanded=False):
        st.caption("Detalle técnico para auditoría.")
        st.dataframe(
            preparar_vista(preparar_previsualizacion(df_tmp.head(150))),
            use_container_width=True,
        )

    st.warning(
        "Al importar, el sistema guardará los movimientos, omitirá duplicados y preparará asientos propuestos. "
        "Los asientos todavía no impactan en Libro Diario."
    )

    col1, col2 = st.columns([3, 1])

    with col1:
        importar = st.button(
            "Guardar importación y generar asientos propuestos",
            type="primary",
            use_container_width=True,
        )

    with col2:
        cancelar = st.button(
            "Limpiar archivo",
            use_container_width=True,
        )

    if cancelar:
        avanzar_version_uploader_banco()
        st.rerun()

    if not importar:
        return

    resultado = guardar_importacion_bancaria(
        empresa_id=empresa_id,
        banco=banco.strip() or "Banco",
        nombre_cuenta=nombre_cuenta.strip() or "Cuenta bancaria",
        nombre_archivo=archivo.name,
        formato_archivo=formato,
        df_movimientos=df_movimientos,
        saldo_inicial_extracto=saldo_inicial,
        saldo_final_extracto=saldo_final,
    )

    importacion_id = resultado.get("importacion_id")

    if importacion_id:
        regenerar_asientos_bancarios_agrupados(
            importacion_id=int(importacion_id),
            empresa_id=empresa_id,
            usuario_id=usuario_actual_id(),
        )

    guardar_resultado_importacion_banco(archivo.name, resultado)
    avanzar_version_uploader_banco()
    st.rerun()


def _indice_sugerido(opciones, analisis, canonica):
    mapeo = analisis.get("mapeo_detectado", {})
    sugerida = mapeo.get(canonica)

    if sugerida in opciones:
        return opciones.index(sugerida)

    return 0


# ======================================================
# PENDIENTES DE IMPUTACIÓN
# ======================================================

def mostrar_pendientes_imputacion():
    st.subheader("Pendientes de imputación")

    st.info(
        "Acá se resuelven los movimientos que requieren decisión humana: "
        "cobros contra clientes/facturas, pagos contra proveedores/facturas, pagos fiscales "
        "y desimputaciones por errores humanos."
    )

    empresa_id = empresa_actual_id()
    df = obtener_movimientos_pendientes_imputacion(empresa_id)

    if df.empty:
        st.success("No hay movimientos pendientes de imputación manual.")
    else:
        df = df.copy()
        df["tipo_visible"] = df["tipo_movimiento_sugerido"].apply(nombre_tipo_movimiento_ui)

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Pendientes", len(df))
        col2.metric("Ingresos pendientes", moneda(float(df[df["importe"] > 0]["importe_pendiente"].sum())))
        col3.metric("Egresos pendientes", moneda(float(df[df["importe"] < 0]["importe_pendiente"].sum())))
        col4.metric("Total pendiente", moneda(float(df["importe_pendiente"].sum())))

    tab_cobros, tab_pagos, tab_fiscales, tab_desimputar, tab_todos = st.tabs([
        "Imputar cobros",
        "Imputar pagos",
        "Pagos fiscales",
        "Desimputar",
        "Todos los pendientes",
    ])

    with tab_cobros:
        if df.empty:
            st.info("No hay cobros pendientes.")
        else:
            mostrar_imputacion_cobros(df)

    with tab_pagos:
        if df.empty:
            st.info("No hay pagos pendientes.")
        else:
            mostrar_imputacion_pagos(df)

    with tab_fiscales:
        if df.empty:
            st.info("No hay pagos fiscales pendientes.")
        else:
            mostrar_imputacion_fiscal(df)

    with tab_desimputar:
        mostrar_desimputaciones()

    with tab_todos:
        if df.empty:
            st.info("No hay movimientos pendientes.")
        else:
            mostrar_pendientes_todos(df)


def mostrar_imputacion_cobros(df):
    empresa_id = empresa_actual_id()

    cobros = df[
        (df["importe"] > 0)
        & (df["estado_conciliacion"].isin(["PENDIENTE", "PARCIAL"]))
        & (df["tipo_movimiento_sugerido"].isin(["COBRO_POSIBLE", "A_REVISAR"]))
    ].copy()

    if cobros.empty:
        st.info("No hay cobros pendientes para imputar.")
        return

    movimiento_id = st.selectbox(
        "Movimiento bancario de cobro",
        cobros["id"].astype(int).tolist(),
        format_func=lambda x: _etiqueta_movimiento(cobros[cobros["id"].astype(int) == int(x)].iloc[0]),
        key="banco_cobro_movimiento",
    )

    movimiento = cobros[cobros["id"].astype(int) == int(movimiento_id)].iloc[0]
    disponible = _numero(movimiento.get("importe_pendiente")) or abs(_numero(movimiento.get("importe")))

    st.metric("Importe disponible del movimiento", moneda(disponible))

    clientes = obtener_clientes_con_saldo_pendiente(empresa_id)

    if clientes.empty:
        st.warning("No hay clientes con saldo pendiente en cuenta corriente.")
        return

    cliente_idx = st.selectbox(
        "Cliente",
        list(range(len(clientes))),
        format_func=lambda i: _etiqueta_tercero(clientes.iloc[int(i)], "cliente"),
        key="banco_cobro_cliente",
    )

    cliente_row = clientes.iloc[int(cliente_idx)]
    cliente = _texto(cliente_row.get("cliente"))
    cuit = _texto(cliente_row.get("cuit"))

    facturas = obtener_facturas_cliente_pendientes(cliente, cuit, empresa_id)

    if facturas.empty:
        st.warning("El cliente seleccionado no tiene facturas pendientes.")
        return

    st.dataframe(
        preparar_vista(_preparar_facturas_para_vista(facturas)),
        use_container_width=True,
    )

    opciones = list(range(len(facturas)))

    seleccionadas = st.multiselect(
        "Facturas a imputar",
        opciones,
        format_func=lambda i: (
            f"{facturas.iloc[int(i)]['tipo']} {facturas.iloc[int(i)]['numero']} "
            f"| Pendiente {moneda(_numero(facturas.iloc[int(i)]['pendiente']))}"
        ),
        key="banco_cobro_facturas",
    )

    detalles = []
    restante = disponible

    for i in seleccionadas:
        fila = facturas.iloc[int(i)]
        pendiente = _numero(fila.get("pendiente"))
        sugerido = min(pendiente, restante) if restante > 0 else 0.0

        importe = st.number_input(
            f"Importe a imputar - {fila.get('tipo')} {fila.get('numero')}",
            min_value=0.0,
            max_value=float(pendiente),
            value=float(sugerido),
            step=0.01,
            key=f"banco_cobro_importe_{i}",
        )

        restante = round(restante - importe, 2)

        detalles.append({
            "tipo": _texto(fila.get("tipo")),
            "numero": _texto(fila.get("numero")),
            "pendiente": pendiente,
            "importe_imputado": importe,
        })

    observacion = st.text_area(
        "Observación",
        value="Imputación manual de cobro contra factura de cliente.",
        key="banco_cobro_observacion",
    )

    if st.button("Confirmar imputación de cobro", type="primary", use_container_width=True):
        resultado = registrar_imputacion_cobro(
            empresa_id=empresa_id,
            movimiento_id=int(movimiento_id),
            cliente=cliente,
            cuit=cuit,
            detalles=detalles,
            usuario_id=usuario_actual_id(),
            observacion=observacion,
        )

        if resultado.get("ok"):
            st.success(resultado.get("mensaje"))
            st.rerun()
        else:
            st.error(resultado.get("mensaje", "No se pudo imputar el cobro."))


def mostrar_imputacion_pagos(df):
    empresa_id = empresa_actual_id()

    pagos = df[
        (df["importe"] < 0)
        & (df["estado_conciliacion"].isin(["PENDIENTE", "PARCIAL"]))
        & (df["tipo_movimiento_sugerido"].isin(["PAGO_POSIBLE", "A_REVISAR", "OTRO_GASTO_A_REVISAR"]))
    ].copy()

    if pagos.empty:
        st.info("No hay pagos pendientes para imputar.")
        return

    movimiento_id = st.selectbox(
        "Movimiento bancario de pago",
        pagos["id"].astype(int).tolist(),
        format_func=lambda x: _etiqueta_movimiento(pagos[pagos["id"].astype(int) == int(x)].iloc[0]),
        key="banco_pago_movimiento",
    )

    movimiento = pagos[pagos["id"].astype(int) == int(movimiento_id)].iloc[0]
    disponible = _numero(movimiento.get("importe_pendiente")) or abs(_numero(movimiento.get("importe")))

    st.metric("Importe disponible del movimiento", moneda(disponible))

    proveedores = obtener_proveedores_con_saldo_pendiente(empresa_id)

    if proveedores.empty:
        st.warning("No hay proveedores con saldo pendiente en cuenta corriente.")
        return

    proveedor_idx = st.selectbox(
        "Proveedor",
        list(range(len(proveedores))),
        format_func=lambda i: _etiqueta_tercero(proveedores.iloc[int(i)], "proveedor"),
        key="banco_pago_proveedor",
    )

    proveedor_row = proveedores.iloc[int(proveedor_idx)]
    proveedor = _texto(proveedor_row.get("proveedor"))
    cuit = _texto(proveedor_row.get("cuit"))

    facturas = obtener_facturas_proveedor_pendientes(proveedor, cuit, empresa_id)

    if facturas.empty:
        st.warning("El proveedor seleccionado no tiene facturas pendientes.")
        return

    st.dataframe(
        preparar_vista(_preparar_facturas_para_vista(facturas)),
        use_container_width=True,
    )

    opciones = list(range(len(facturas)))

    seleccionadas = st.multiselect(
        "Facturas a pagar",
        opciones,
        format_func=lambda i: (
            f"{facturas.iloc[int(i)]['tipo']} {facturas.iloc[int(i)]['numero']} "
            f"| Pendiente {moneda(_numero(facturas.iloc[int(i)]['pendiente']))}"
        ),
        key="banco_pago_facturas",
    )

    detalles = []
    restante = disponible

    for i in seleccionadas:
        fila = facturas.iloc[int(i)]
        pendiente = _numero(fila.get("pendiente"))
        sugerido = min(pendiente, restante) if restante > 0 else 0.0

        importe = st.number_input(
            f"Importe a imputar - {fila.get('tipo')} {fila.get('numero')}",
            min_value=0.0,
            max_value=float(pendiente),
            value=float(sugerido),
            step=0.01,
            key=f"banco_pago_importe_{i}",
        )

        restante = round(restante - importe, 2)

        detalles.append({
            "tipo": _texto(fila.get("tipo")),
            "numero": _texto(fila.get("numero")),
            "pendiente": pendiente,
            "importe_imputado": importe,
        })

    observacion = st.text_area(
        "Observación",
        value="Imputación manual de pago contra factura de proveedor.",
        key="banco_pago_observacion",
    )

    if st.button("Confirmar imputación de pago", type="primary", use_container_width=True):
        resultado = registrar_imputacion_pago(
            empresa_id=empresa_id,
            movimiento_id=int(movimiento_id),
            proveedor=proveedor,
            cuit=cuit,
            detalles=detalles,
            usuario_id=usuario_actual_id(),
            observacion=observacion,
        )

        if resultado.get("ok"):
            st.success(resultado.get("mensaje"))
            st.rerun()
        else:
            st.error(resultado.get("mensaje", "No se pudo imputar el pago."))


def mostrar_imputacion_fiscal(df):
    empresa_id = empresa_actual_id()

    fiscales = df[
        (df["importe"] < 0)
        & (df["estado_conciliacion"].isin(["PENDIENTE", "PARCIAL"]))
        & (
            df["tipo_movimiento_sugerido"].isin(["PAGO_IMPUESTOS", "A_REVISAR", "OTRO_GASTO_A_REVISAR"])
            | df["concepto"].astype(str).str.upper().str.contains("AFIP|ARCA|IVA|IIBB|SUSS|AUTONOMO|GANANCIAS", na=False)
        )
    ].copy()

    if fiscales.empty:
        st.info("No hay pagos fiscales pendientes detectados.")
        return

    movimiento_id = st.selectbox(
        "Movimiento fiscal",
        fiscales["id"].astype(int).tolist(),
        format_func=lambda x: _etiqueta_movimiento(fiscales[fiscales["id"].astype(int) == int(x)].iloc[0]),
        key="banco_fiscal_movimiento",
    )

    movimiento = fiscales[fiscales["id"].astype(int) == int(movimiento_id)].iloc[0]
    disponible = _numero(movimiento.get("importe_pendiente")) or abs(_numero(movimiento.get("importe")))

    st.metric("Importe disponible del movimiento", moneda(disponible))

    impuestos = [
        "IVA",
        "Ingresos Brutos",
        "ARCA / AFIP",
        "Ganancias",
        "Seguridad Social / SUSS",
        "Autónomos",
        "Monotributo",
        "Otros impuestos",
    ]

    impuesto = st.selectbox("Impuesto / concepto fiscal", impuestos)
    periodo = st.text_input("Período fiscal", placeholder="Ej: 2026-04")
    jurisdiccion = st.text_input("Jurisdicción", value="Nacional")

    cuentas = {
        "IVA": ("2.2.01", "IVA saldo a pagar"),
        "Ingresos Brutos": ("2.2.02", "Ingresos Brutos a pagar"),
        "ARCA / AFIP": ("2.2.03", "ARCA / AFIP a pagar"),
        "Ganancias": ("2.2.04", "Ganancias a pagar"),
        "Seguridad Social / SUSS": ("2.2.05", "Cargas sociales a pagar"),
        "Autónomos": ("6.1.15", "Impuestos, tasas y contribuciones"),
        "Monotributo": ("6.1.15", "Impuestos, tasas y contribuciones"),
        "Otros impuestos": ("6.1.15", "Impuestos, tasas y contribuciones"),
    }

    cuenta_codigo, cuenta_nombre = cuentas.get(impuesto, cuentas["Otros impuestos"])

    col1, col2 = st.columns([1, 2])

    with col1:
        importe = st.number_input(
            "Importe a imputar",
            min_value=0.0,
            max_value=float(disponible),
            value=float(disponible),
            step=0.01,
        )

    with col2:
        cuenta_visible = st.text_input(
            "Cuenta contable sugerida",
            value=f"{cuenta_codigo} - {cuenta_nombre}",
        )

    if " - " in cuenta_visible:
        cuenta_codigo_final, cuenta_nombre_final = cuenta_visible.split(" - ", 1)
    else:
        cuenta_codigo_final = cuenta_codigo
        cuenta_nombre_final = cuenta_visible.strip() or cuenta_nombre

    observacion = st.text_area(
        "Observación",
        value=f"Pago fiscal {impuesto} período {periodo} jurisdicción {jurisdiccion}.",
        key="banco_fiscal_observacion",
    )

    if st.button("Confirmar pago fiscal", type="primary", use_container_width=True):
        if periodo.strip() == "":
            st.warning("Indicá el período fiscal.")
            return

        resultado = registrar_pago_fiscal(
            empresa_id=empresa_id,
            movimiento_id=int(movimiento_id),
            impuesto=impuesto,
            periodo=periodo.strip(),
            jurisdiccion=jurisdiccion.strip(),
            cuenta_codigo=cuenta_codigo_final.strip(),
            cuenta_nombre=cuenta_nombre_final.strip(),
            importe=importe,
            usuario_id=usuario_actual_id(),
            observacion=observacion,
        )

        if resultado.get("ok"):
            st.success(resultado.get("mensaje"))
            st.rerun()
        else:
            st.error(resultado.get("mensaje", "No se pudo imputar el pago fiscal."))


def mostrar_desimputaciones():
    empresa_id = empresa_actual_id()
    conciliaciones = obtener_conciliaciones_bancarias(empresa_id)

    st.subheader("Desimputar conciliaciones")

    st.info(
        "Usá esta opción cuando un cobro, pago o pago fiscal fue imputado por error. "
        "La desimputación revierte cuenta corriente, borra asientos propuestos de esa conciliación "
        "y devuelve el movimiento bancario a pendiente o parcial."
    )

    if conciliaciones.empty:
        st.success("No hay conciliaciones bancarias para desimputar.")
        return

    conciliaciones = conciliaciones.copy()
    conciliaciones["tipo_visible"] = conciliaciones["tipo_conciliacion"].astype(str).str.replace("_", " ").str.title()

    def etiqueta_conciliacion(i):
        fila = conciliaciones.iloc[int(i)]
        return (
            f"Conciliación #{int(fila['id'])} | {fila.get('fecha', '')} | "
            f"{fila.get('tipo_visible', '')} | {moneda(_numero(fila.get('importe_imputado')))} | "
            f"{fila.get('banco', '')} | {str(fila.get('concepto', ''))[:70]}"
        )

    idx = st.selectbox(
        "Conciliación a desimputar",
        list(range(len(conciliaciones))),
        format_func=etiqueta_conciliacion,
        key="banco_desimputar_idx",
    )

    fila = conciliaciones.iloc[int(idx)]

    col1, col2, col3 = st.columns(3)
    col1.metric("Importe imputado", moneda(_numero(fila.get("importe_imputado"))))
    col2.metric("Estado", _texto(fila.get("estado")))
    col3.metric("Movimiento banco", f"#{int(fila.get('movimiento_banco_id'))}")

    with st.expander("Ver detalle de la conciliación seleccionada", expanded=False):
        detalle = {
            "Conciliación": int(fila.get("id")),
            "Fecha": fila.get("fecha"),
            "Tipo": fila.get("tipo_visible"),
            "Estado": fila.get("estado"),
            "Importe total": fila.get("importe_total"),
            "Importe imputado": fila.get("importe_imputado"),
            "Importe pendiente": fila.get("importe_pendiente"),
            "Banco": fila.get("banco"),
            "Cuenta": fila.get("nombre_cuenta"),
            "Concepto banco": fila.get("concepto"),
            "Referencia": fila.get("referencia"),
            "Causal": fila.get("causal"),
            "Archivo": fila.get("archivo"),
            "Importación": fila.get("importacion_id"),
            "Observación": fila.get("observacion"),
        }
        st.json(detalle)

    motivo = st.text_area(
        "Motivo de desimputación",
        value="Corrección de imputación bancaria realizada por error.",
        key="banco_motivo_desimputar",
    )

    acepta = st.checkbox(
        f"Confirmo que quiero desimputar la conciliación #{int(fila['id'])}.",
        key="banco_acepta_desimputar",
    )

    if st.button(
        "Desimputar conciliación seleccionada",
        type="primary",
        disabled=not acepta,
        use_container_width=True,
    ):
        resultado = desimputar_conciliacion_bancaria(
            conciliacion_id=int(fila["id"]),
            empresa_id=empresa_id,
            usuario_id=usuario_actual_id(),
            motivo=motivo,
        )

        if resultado.get("ok"):
            st.success(resultado.get("mensaje"))
            st.rerun()
        else:
            st.error(resultado.get("mensaje", "No se pudo desimputar la conciliación."))


def mostrar_pendientes_todos(df):
    tipos = ["Todos"] + sorted(df["tipo_movimiento_sugerido"].dropna().unique().tolist())

    col1, col2 = st.columns([1.5, 2])

    with col1:
        tipo = st.selectbox(
            "Tipo pendiente",
            tipos,
            format_func=lambda x: "Todos" if x == "Todos" else nombre_tipo_movimiento_ui(x),
            key="banco_pend_tipo",
        )

    with col2:
        buscar = st.text_input(
            "Buscar concepto / referencia / causal",
            key="banco_pend_buscar",
        ).strip().lower()

    filtrado = df.copy()

    if tipo != "Todos":
        filtrado = filtrado[filtrado["tipo_movimiento_sugerido"] == tipo]

    if buscar:
        texto = (
            filtrado["concepto"].astype(str)
            + " "
            + filtrado["referencia"].astype(str)
            + " "
            + filtrado["causal"].astype(str)
        ).str.lower()

        filtrado = filtrado[texto.str.contains(buscar, na=False)]

    vista = filtrado[[
        "id",
        "fecha",
        "banco",
        "nombre_cuenta",
        "referencia",
        "causal",
        "concepto",
        "importe",
        "importe_pendiente",
        "tipo_visible",
        "confianza_sugerencia",
        "motivo_sugerencia",
        "estado_conciliacion",
        "archivo",
    ]].copy()

    vista = vista.rename(columns={
        "id": "ID",
        "fecha": "Fecha",
        "banco": "Banco",
        "nombre_cuenta": "Cuenta",
        "referencia": "Referencia",
        "causal": "Causal",
        "concepto": "Concepto",
        "importe": "Importe",
        "importe_pendiente": "Pendiente",
        "tipo_visible": "Tipo",
        "confianza_sugerencia": "Confianza",
        "motivo_sugerencia": "Motivo",
        "estado_conciliacion": "Estado",
        "archivo": "Archivo",
    })

    st.dataframe(preparar_vista(vista), use_container_width=True)


# ======================================================
# ASIENTOS PROPUESTOS
# ======================================================

def mostrar_asientos_propuestos():
    st.subheader("Asientos propuestos de Banco / Caja")

    st.info(
        "Incluye asientos automáticos agrupados por operación bancaria y asientos generados por imputaciones manuales. "
        "Todavía no impactan en Libro Diario."
    )

    empresa_id = empresa_actual_id()
    df = obtener_asientos_propuestos_banco(empresa_id=empresa_id)

    if df.empty:
        st.info("No hay asientos propuestos pendientes.")
        return

    df = df.copy()
    df["tipo_visible"] = df["tipo_movimiento_sugerido"].apply(nombre_tipo_movimiento_ui)

    total_debe = float(df["debe"].sum())
    total_haber = float(df["haber"].sum())
    diferencia = round(total_debe - total_haber, 2)

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Líneas", len(df))
    col2.metric("Debe", moneda(total_debe))
    col3.metric("Haber", moneda(total_haber))
    col4.metric("Diferencia", moneda(diferencia))

    if abs(diferencia) <= 0.01:
        st.success("Los asientos propuestos están balanceados.")
    else:
        st.error("Los asientos propuestos no cuadran. Revisar antes de confirmar.")

    st.markdown("#### Operaciones bancarias agrupadas para contabilizar")
    st.caption(
        "Cada opción representa una operación bancaria agrupada con sus líneas de Debe y Haber. "
        "Sirve para revisar rápidamente que la propuesta contable esté balanceada antes de confirmarla."
    )

    df["grupo_asiento"] = (
        df["fecha"].astype(str)
        + " | "
        + df["glosa"].fillna("").astype(str)
    )

    grupos = (
        df
        .groupby("grupo_asiento", as_index=False)
        .agg(
            fecha=("fecha", "first"),
            glosa=("glosa", "first"),
            lineas=("cuenta_codigo", "count"),
            debe=("debe", "sum"),
            haber=("haber", "sum"),
        )
    )

    grupos["diferencia"] = (grupos["debe"] - grupos["haber"]).round(2)
    grupos["estado"] = grupos["diferencia"].apply(lambda x: "Balanceado" if abs(x) <= 0.01 else "Con diferencia")

    if not grupos.empty:
        grupo_idx = st.selectbox(
            "Operación bancaria agrupada",
            list(range(len(grupos))),
            format_func=lambda i: (
                f"{grupos.iloc[int(i)]['fecha']} | "
                f"{grupos.iloc[int(i)]['estado']} | "
                f"Debe {moneda(_numero(grupos.iloc[int(i)]['debe']))} / "
                f"Haber {moneda(_numero(grupos.iloc[int(i)]['haber']))} | "
                f"{str(grupos.iloc[int(i)]['glosa'])[:90]}"
            ),
            key="banco_asiento_grupo_idx",
        )

        grupo = grupos.iloc[int(grupo_idx)]
        detalle_grupo = df[df["grupo_asiento"] == grupo["grupo_asiento"]].copy()

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Líneas de la operación", int(grupo["lineas"]))
        c2.metric("Debe", moneda(_numero(grupo["debe"])))
        c3.metric("Haber", moneda(_numero(grupo["haber"])))
        c4.metric("Diferencia", moneda(_numero(grupo["diferencia"])))

        vista_grupo = detalle_grupo.rename(columns={
            "fecha": "Fecha",
            "banco": "Banco",
            "nombre_cuenta": "Cuenta bancaria",
            "concepto": "Concepto",
            "tipo_visible": "Tipo",
            "cuenta_codigo": "Cuenta",
            "cuenta_nombre": "Nombre cuenta",
            "debe": "Debe",
            "haber": "Haber",
            "glosa": "Glosa",
            "estado": "Estado",
        })

        columnas_grupo = [
            "Fecha", "Banco", "Cuenta bancaria", "Concepto", "Tipo",
            "Cuenta", "Nombre cuenta", "Debe", "Haber", "Estado"
        ]
        columnas_grupo = [c for c in columnas_grupo if c in vista_grupo.columns]

        st.dataframe(preparar_vista(vista_grupo[columnas_grupo]), use_container_width=True)

    st.divider()
    st.markdown("#### Detalle técnico de líneas propuestas")
    st.caption(
        "Este detalle muestra cada línea contable propuesta. Es útil para auditoría, revisión contable "
        "y futura confirmación contra Libro Diario."
    )

    tipos = ["Todos"] + sorted(df["tipo_movimiento_sugerido"].dropna().unique().tolist())

    tipo = st.selectbox(
        "Filtrar por tipo",
        tipos,
        format_func=lambda x: "Todos" if x == "Todos" else nombre_tipo_movimiento_ui(x),
        key="banco_asiento_tipo",
    )

    filtrado = df.copy()

    if tipo != "Todos":
        filtrado = filtrado[filtrado["tipo_movimiento_sugerido"] == tipo]

    vista = filtrado.rename(columns={
        "fecha": "Fecha",
        "banco": "Banco",
        "nombre_cuenta": "Cuenta bancaria",
        "concepto": "Concepto",
        "tipo_visible": "Tipo",
        "cuenta_codigo": "Cuenta",
        "cuenta_nombre": "Nombre cuenta",
        "debe": "Debe",
        "haber": "Haber",
        "glosa": "Glosa",
        "estado": "Estado",
    })

    columnas = [
        "Fecha", "Banco", "Cuenta bancaria", "Concepto", "Tipo",
        "Cuenta", "Nombre cuenta", "Debe", "Haber", "Glosa", "Estado"
    ]
    columnas = [c for c in columnas if c in vista.columns]

    st.dataframe(preparar_vista(vista[columnas]), use_container_width=True)

    st.warning(
        "Próximo paso futuro: confirmar estos asientos contra Libro Diario con auditoría, reversión "
        "y control de saldos banco-contabilidad."
    )


# ======================================================
# MOVIMIENTOS
# ======================================================

def mostrar_movimientos_bancarios():
    st.subheader("Movimientos bancarios")

    empresa_id = empresa_actual_id()
    df = obtener_movimientos_bancarios(empresa_id)

    if df.empty:
        st.info("No hay movimientos bancarios importados.")
        return

    df = df.copy()

    col1, col2, col3 = st.columns([1.5, 1.2, 1.2])

    with col1:
        buscar = st.text_input(
            "Buscar por concepto, referencia, causal o archivo",
            key="bancos_buscar_movimientos",
        ).strip().lower()

    with col2:
        tipos = ["Todos"] + sorted(df["tipo_movimiento_sugerido"].dropna().unique().tolist())
        tipo = st.selectbox(
            "Tipo sugerido",
            tipos,
            format_func=lambda x: "Todos" if x == "Todos" else nombre_tipo_movimiento_ui(x),
        )

    with col3:
        estados = ["Todos"] + sorted(df["estado_conciliacion"].dropna().unique().tolist())
        estado = st.selectbox("Estado conciliación", estados)

    col1, col2, col3 = st.columns(3)

    with col1:
        anios = ["Todos"] + sorted(df["anio"].dropna().astype(int).unique().tolist())
        anio = st.selectbox("Año", anios)

    with col2:
        meses = ["Todos"] + sorted(df["mes"].dropna().astype(int).unique().tolist())
        mes = st.selectbox("Mes", meses)

    with col3:
        bancos = ["Todos"] + sorted(df["banco"].dropna().unique().tolist())
        banco = st.selectbox("Banco", bancos)

    df_filtrado = df.copy()

    if buscar:
        texto = (
            df_filtrado["concepto"].astype(str)
            + " "
            + df_filtrado["referencia"].astype(str)
            + " "
            + df_filtrado["causal"].astype(str)
            + " "
            + df_filtrado["archivo"].astype(str)
        ).str.lower()

        df_filtrado = df_filtrado[texto.str.contains(buscar, na=False)]

    if tipo != "Todos":
        df_filtrado = df_filtrado[df_filtrado["tipo_movimiento_sugerido"] == tipo]

    if estado != "Todos":
        df_filtrado = df_filtrado[df_filtrado["estado_conciliacion"] == estado]

    if anio != "Todos":
        df_filtrado = df_filtrado[df_filtrado["anio"] == int(anio)]

    if mes != "Todos":
        df_filtrado = df_filtrado[df_filtrado["mes"] == int(mes)]

    if banco != "Todos":
        df_filtrado = df_filtrado[df_filtrado["banco"] == banco]

    if df_filtrado.empty:
        st.info("No hay movimientos con los filtros seleccionados.")
        return

    col1, col2, col3, col4, col5 = st.columns(5)

    col1.metric("Movimientos", len(df_filtrado))
    col2.metric("Créditos", moneda(float(df_filtrado["credito"].sum())))
    col3.metric("Débitos", moneda(float(df_filtrado["debito"].sum())))
    col4.metric("Pendiente", moneda(float(df_filtrado["importe_pendiente"].sum())))
    col5.metric("Neto", moneda(float(df_filtrado["importe"].sum())))

    st.dataframe(
        preparar_vista(preparar_movimientos_vista(df_filtrado)),
        use_container_width=True,
    )

    excel = exportar_excel({
        "Movimientos Bancarios": preparar_movimientos_vista(df_filtrado)
    })

    st.download_button(
        "Descargar movimientos bancarios Excel",
        data=excel,
        file_name="movimientos_bancarios.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ======================================================
# CONTROL FISCAL
# ======================================================

def mostrar_control_fiscal_bancario():
    st.subheader("Control fiscal bancario")

    st.info(
        "Agrupa gastos bancarios, IVA crédito fiscal bancario, percepciones e impuestos. "
        "El objetivo es detectar base gravada, IVA 21%, posible IVA 10,5% y conceptos que requieren revisión."
    )

    empresa_id = empresa_actual_id()
    df = obtener_grupos_fiscales_bancarios(empresa_id)

    if df.empty:
        st.info("Todavía no hay grupos fiscales bancarios generados. Importá un extracto primero.")
        return

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Base gastos bancarios", moneda(float(df["base_gasto_bancario"].sum())))
    col2.metric("IVA crédito 21%", moneda(float(df["iva_credito_21"].sum())))
    col3.metric("IVA posible 10,5%", moneda(float(df["iva_credito_105"].sum())))
    col4.metric("IVA sin base", moneda(float(df["iva_sin_base"].sum())))

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Percepción IVA", moneda(float(df["percepcion_iva"].sum())))
    col2.metric("Percepción IIBB", moneda(float(df["percepcion_iibb"].sum())))
    col3.metric("Ley 25.413", moneda(float(df["impuesto_debitos_creditos"].sum())))
    col4.metric("Total debitado banco", moneda(float(df["total_banco"].sum())))

    vista = df.rename(columns={
        "fecha": "Fecha",
        "referencia": "Referencia",
        "causal": "Causal",
        "banco": "Banco",
        "nombre_cuenta": "Cuenta",
        "base_gasto_bancario": "Base gastos bancarios",
        "iva_credito_21": "IVA crédito 21%",
        "iva_credito_105": "IVA crédito posible 10,5%",
        "iva_sin_base": "IVA sin base",
        "percepcion_iva": "Percepción IVA",
        "percepcion_iibb": "Percepción IIBB",
        "impuesto_debitos_creditos": "Ley 25.413",
        "total_banco": "Total banco",
        "alicuota_detectada": "Alícuota detectada",
        "confianza": "Confianza",
        "estado_revision": "Estado revisión",
        "motivo": "Motivo",
        "importacion_id": "Importación",
    })

    st.dataframe(preparar_vista(vista), use_container_width=True)

    st.warning(
        "Los grupos fiscales son propuestas de control. Antes de computar IVA o generar asiento, "
        "conviene confirmar si la empresa es Responsable Inscripto, si corresponde prorrateo y si el concepto tiene respaldo suficiente."
    )

    excel = exportar_excel({
        "Control fiscal bancario": vista
    })

    st.download_button(
        "Descargar control fiscal bancario Excel",
        data=excel,
        file_name="control_fiscal_bancario.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ======================================================
# REGLAS
# ======================================================

def mostrar_reglas_recurrentes():
    st.subheader("Reglas recurrentes")

    st.info(
        "El sistema detecta conceptos repetidos. Si se repiten mes a mes y los confirmás, "
        "podés crear reglas para reducir conciliación manual futura."
    )

    empresa_id = empresa_actual_id()

    st.markdown("#### Patrones recurrentes detectados")

    minimo = st.number_input("Mínimo de repeticiones", min_value=2, max_value=20, value=3, step=1)

    patrones = obtener_patrones_recurrentes(empresa_id, minimo=int(minimo))

    if patrones.empty:
        st.info("Todavía no hay patrones recurrentes con ese mínimo.")
    else:
        vista = patrones.rename(columns={
            "patron_normalizado": "Patrón",
            "tipo_visible": "Tipo sugerido",
            "veces": "Veces",
            "debito_total": "Débitos",
            "credito_total": "Créditos",
            "importe_promedio": "Importe promedio",
            "primera_fecha": "Primera fecha",
            "ultima_fecha": "Última fecha",
            "ejemplo": "Ejemplo",
            "causal": "Causal",
            "confianza": "Confianza",
        })

        st.dataframe(preparar_vista(vista), use_container_width=True)

    st.divider()
    st.markdown("#### Crear regla manual")

    cuentas_config = obtener_configuracion_contable_bancos(empresa_id)

    opciones_cuenta = [
        f"{row['cuenta_codigo']} - {row['cuenta_nombre']}"
        for _, row in cuentas_config.iterrows()
    ]

    if not opciones_cuenta:
        st.warning("No hay configuración contable bancaria.")
        return

    with st.form("form_crear_regla_bancaria"):
        col1, col2 = st.columns(2)

        with col1:
            nombre_regla = st.text_input("Nombre de regla")
            patron = st.text_input("Patrón en concepto", placeholder="Ej: COMISION TRANSFERE")
            causal = st.text_input("Causal / código bancario opcional")

        with col2:
            tipo_movimiento = st.selectbox(
                "Tipo movimiento",
                list(TIPOS_MOVIMIENTO_BANCO.keys()),
                format_func=lambda x: nombre_tipo_movimiento_ui(x),
            )
            subtipo = st.text_input("Subtipo", value="")
            confianza = st.selectbox("Confianza", ["Alta", "Media", "Baja"], index=1)

        col1, col2, col3 = st.columns(3)

        with col1:
            cuenta_debe = st.selectbox("Cuenta Debe", opciones_cuenta)

        with col2:
            cuenta_haber = st.selectbox("Cuenta Haber", opciones_cuenta)

        with col3:
            tratamiento = st.text_input("Tratamiento fiscal", value="")
            alicuota = st.number_input("Alícuota IVA sugerida", value=0.0, step=0.5)

        automatizar = st.checkbox("Automatizar asiento en el futuro", value=False)
        requiere_confirmacion = st.checkbox("Requiere confirmación", value=True)

        guardar = st.form_submit_button("Crear regla")

        if guardar:
            if nombre_regla.strip() == "" or patron.strip() == "":
                st.warning("Completá nombre de regla y patrón.")
            else:
                debe_codigo, debe_nombre = cuenta_debe.split(" - ", 1)
                haber_codigo, haber_nombre = cuenta_haber.split(" - ", 1)

                crear_regla_bancaria(
                    empresa_id=empresa_id,
                    nombre_regla=nombre_regla.strip(),
                    patron=patron.strip(),
                    causal=causal.strip(),
                    tipo_movimiento=tipo_movimiento,
                    subtipo=subtipo.strip(),
                    cuenta_debe_codigo=debe_codigo.strip(),
                    cuenta_debe_nombre=debe_nombre.strip(),
                    cuenta_haber_codigo=haber_codigo.strip(),
                    cuenta_haber_nombre=haber_nombre.strip(),
                    tratamiento_fiscal=tratamiento.strip(),
                    alicuota_iva=alicuota if alicuota > 0 else None,
                    automatizar_asiento=automatizar,
                    requiere_confirmacion=requiere_confirmacion,
                    confianza=confianza,
                )

                st.success("Regla creada.")

    st.divider()
    st.markdown("#### Reglas existentes")

    reglas = obtener_reglas_bancarias(empresa_id)

    if reglas.empty:
        st.info("No hay reglas bancarias cargadas.")
    else:
        st.dataframe(preparar_vista(reglas), use_container_width=True)


# ======================================================
# CONTROL DE SALDOS
# ======================================================

def mostrar_control_saldos():
    st.subheader("Control de saldos")

    empresa_id = empresa_actual_id()
    importaciones = obtener_importaciones_bancarias(empresa_id)
    resumen = obtener_resumen_bancario(empresa_id)
    indicadores = resumen.get("indicadores", {})

    if importaciones.empty:
        st.info("No hay importaciones bancarias para controlar.")
        return

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Movimientos", indicadores.get("total_movimientos", 0))
    c2.metric("% importe conciliado", f"{indicadores.get('porcentaje_importe_conciliado', 0)}%")
    c3.metric("% movimientos conciliados", f"{indicadores.get('porcentaje_movimientos_conciliados', 0)}%")
    c4.metric("Pendiente", moneda(float(indicadores.get("total_pendiente", 0))))

    st.subheader("Control por importación")

    vista = importaciones[[
        "fecha_carga",
        "banco",
        "nombre_cuenta",
        "nombre_archivo",
        "registros_detectados",
        "procesados",
        "duplicados",
        "errores",
        "saldo_inicial_extracto",
        "total_creditos",
        "total_debitos",
        "saldo_final_extracto",
        "saldo_final_calculado",
        "diferencia_saldo",
    ]].copy()

    vista = vista.rename(columns={
        "fecha_carga": "Fecha carga",
        "banco": "Banco",
        "nombre_cuenta": "Cuenta",
        "nombre_archivo": "Archivo",
        "registros_detectados": "Detectados",
        "procesados": "Importados",
        "duplicados": "Duplicados",
        "errores": "Errores",
        "saldo_inicial_extracto": "Saldo inicial",
        "total_creditos": "Créditos",
        "total_debitos": "Débitos",
        "saldo_final_extracto": "Saldo final extracto",
        "saldo_final_calculado": "Saldo final calculado",
        "diferencia_saldo": "Diferencia",
    })

    st.dataframe(preparar_vista(vista), use_container_width=True)

    diferencias = importaciones[importaciones["diferencia_saldo"].abs() > 0.01]

    if diferencias.empty:
        st.success("Las importaciones no muestran diferencias relevantes de saldo.")
    else:
        st.warning("Hay importaciones con diferencias de saldo. Revisar archivo, saldo inicial/final o movimientos faltantes.")


# ======================================================
# IMPORTACIONES
# ======================================================

def mostrar_importaciones():
    st.subheader("Importaciones bancarias")

    empresa_id = empresa_actual_id()
    df = obtener_importaciones_bancarias(empresa_id)

    if df.empty:
        st.info("No hay importaciones bancarias registradas.")
        return

    df = df.copy()

    vista = df.rename(columns={
        "id": "ID",
        "fecha_carga": "Fecha carga",
        "banco": "Banco",
        "nombre_cuenta": "Cuenta",
        "nombre_archivo": "Archivo",
        "formato_archivo": "Formato",
        "registros_detectados": "Detectados",
        "procesados": "Importados",
        "duplicados": "Duplicados",
        "errores": "Errores",
        "saldo_inicial_extracto": "Saldo inicial",
        "total_debitos": "Débitos",
        "total_creditos": "Créditos",
        "saldo_final_extracto": "Saldo final extracto",
        "saldo_final_calculado": "Saldo final calculado",
        "diferencia_saldo": "Diferencia saldo",
        "observacion": "Observación",
    })

    st.dataframe(preparar_vista(vista), use_container_width=True)

    opciones = df["id"].astype(int).tolist()

    st.divider()
    st.subheader("Asientos agrupados por operación bancaria")

    st.info(
        "Los conceptos bancarios rutinarios se agrupan por fecha, referencia, causal, banco y cuenta. "
        "Esto evita generar un asiento aislado por cada línea cuando corresponde a una misma operación."
    )

    df_con_movimientos = df[df["procesados"].fillna(0).astype(int) > 0].copy()

    if df_con_movimientos.empty:
        st.warning(
            "No hay importaciones con movimientos nuevos para regenerar asientos agrupados. "
            "Las cargas duplicadas sin movimientos no generan asientos."
        )
    else:
        opciones_asientos = df_con_movimientos["id"].astype(int).tolist()

        importacion_asientos_id = st.selectbox(
            "Importación con movimientos",
            opciones_asientos,
            format_func=lambda x: _etiqueta_importacion(
                df_con_movimientos[df_con_movimientos["id"].astype(int) == int(x)].iloc[0]
            ),
            key="bancos_importacion_asientos_agrupados_id",
        )

        if st.button("Regenerar asientos agrupados de esta importación", use_container_width=True):
            resultado = regenerar_asientos_bancarios_agrupados(
                importacion_id=int(importacion_asientos_id),
                empresa_id=empresa_id,
                usuario_id=usuario_actual_id(),
            )

            if resultado.get("ok"):
                st.success(
                    f"{resultado.get('mensaje')} "
                    f"Grupos: {resultado.get('grupos', 0)} | Líneas: {resultado.get('lineas', 0)}"
                )
                st.rerun()
            else:
                st.error(resultado.get("mensaje", "No se pudieron regenerar los asientos agrupados."))

    st.divider()
    st.subheader("Eliminar importación cargada por error")

    st.warning(
        "Usá esta opción solo si cargaste un extracto incorrecto o duplicado. "
        "No toca Ventas, Compras, IVA ni Libro Diario. Si hay imputaciones, la eliminación administrativa "
        "revierte automáticamente las conciliaciones antes de borrar."
    )

    importacion_id = st.selectbox(
        "Importación a eliminar",
        opciones,
        format_func=lambda x: _etiqueta_importacion(
            df[df["id"].astype(int) == int(x)].iloc[0]
        ),
        key="bancos_importacion_eliminar_id",
    )

    resumen = obtener_resumen_eliminacion_importacion_bancaria(
        importacion_id=int(importacion_id),
        empresa_id=empresa_id,
    )

    if not resumen.get("ok"):
        st.error(resumen.get("mensaje", "No se pudo obtener el resumen de eliminación."))
        return

    importacion = resumen.get("importacion", {})
    movimientos_a_borrar = int(resumen.get("movimientos", 0) or 0)
    asientos_a_borrar = int(resumen.get("asientos_propuestos", 0) or 0)
    grupos_a_borrar = int(resumen.get("grupos_fiscales", 0) or 0)
    conciliaciones = int(resumen.get("conciliaciones", 0) or 0)
    conciliaciones_bloqueantes = int(resumen.get("conciliaciones_bloqueantes", 0) or 0)
    diario_confirmado = int(resumen.get("movimientos_diario_confirmado", 0) or 0)

    procesados = int(importacion.get("procesados", 0) or 0)
    duplicados = int(importacion.get("duplicados", 0) or 0)

    if procesados == 0 and duplicados > 0:
        st.info(
            "La importación seleccionada parece ser una carga duplicada sin movimientos nuevos. "
            "Al eliminarla se borrará el registro de importación, pero no movimientos bancarios."
        )
    elif movimientos_a_borrar > 0:
        st.info(
            "La importación seleccionada tiene movimientos asociados. "
            "Si la eliminás, también se borrarán esos movimientos, sus grupos fiscales y asientos propuestos."
        )
    else:
        st.info(
            "La importación seleccionada no tiene movimientos asociados. "
            "Solo se eliminará el registro de importación."
        )

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Movimientos", movimientos_a_borrar)
    col2.metric("Asientos", asientos_a_borrar)
    col3.metric("Grupos fiscales", grupos_a_borrar)
    col4.metric("Conciliaciones", conciliaciones)
    col5.metric("Diario confirmado", diario_confirmado)

    if diario_confirmado > 0:
        st.error(
            "Esta importación ya tiene movimientos con impacto contable confirmado. "
            "No corresponde borrado físico; debe resolverse con reversión contable."
        )
        return

    with st.expander("Ver detalle de la importación seleccionada", expanded=False):
        detalle = {
            "Carga": f"#{importacion.get('id')}",
            "Fecha carga": importacion.get("fecha_carga"),
            "Banco": importacion.get("banco"),
            "Cuenta": importacion.get("nombre_cuenta"),
            "Archivo": importacion.get("nombre_archivo"),
            "Formato": importacion.get("formato_archivo"),
            "Detectados": importacion.get("registros_detectados"),
            "Importados": importacion.get("procesados"),
            "Duplicados": importacion.get("duplicados"),
            "Errores": importacion.get("errores"),
            "Saldo inicial": importacion.get("saldo_inicial_extracto"),
            "Débitos": importacion.get("total_debitos"),
            "Créditos": importacion.get("total_creditos"),
            "Saldo final extracto": importacion.get("saldo_final_extracto"),
            "Saldo final calculado": importacion.get("saldo_final_calculado"),
            "Diferencia saldo": importacion.get("diferencia_saldo"),
        }

        st.json(detalle)

    if conciliaciones_bloqueantes > 0:
        if usuario_es_administrador():
            st.error(
                "Esta importación tiene conciliaciones confirmadas. Como administrador podés eliminar "
                "el archivo completo con reversión automática de imputaciones."
            )

            motivo_admin = st.text_area(
                "Motivo de eliminación administrativa",
                value="Eliminación administrativa de importación bancaria cargada por error.",
                key="banco_motivo_eliminar_admin",
            )

            acepta_admin = st.checkbox(
                f"Confirmo eliminación administrativa completa de la carga #{int(importacion_id)}.",
                key="bancos_acepta_eliminar_importacion_admin",
            )

            if st.button(
                "Eliminar archivo completo como administrador",
                type="primary",
                disabled=not acepta_admin,
                use_container_width=True,
            ):
                resultado = eliminar_importacion_bancaria(
                    importacion_id=int(importacion_id),
                    empresa_id=empresa_id,
                    usuario_id=usuario_actual_id(),
                    motivo=motivo_admin,
                    forzar_eliminacion_admin=True,
                )

                if resultado.get("ok"):
                    eliminados = resultado.get("eliminados", {})

                    st.success(
                        "Importación eliminada administrativamente. "
                        f"Movimientos: {eliminados.get('movimientos', 0)} | "
                        f"Conciliaciones desimputadas: {eliminados.get('conciliaciones_desimputadas', 0)} | "
                        f"Asientos eliminados: {eliminados.get('asientos_propuestos', 0)}"
                    )
                    st.rerun()
                else:
                    st.error(resultado.get("mensaje", "No se pudo eliminar administrativamente la importación."))

        else:
            st.error(
                "Esta importación tiene conciliaciones confirmadas. Solo un usuario administrador puede "
                "eliminar el archivo completo con reversión automática."
            )

        return

    acepta = st.checkbox(
        f"Confirmo que quiero eliminar la carga #{int(importacion_id)} y entiendo el impacto indicado arriba.",
        key="bancos_acepta_eliminar_importacion",
    )

    if st.button(
        "Eliminar importación seleccionada",
        type="primary",
        disabled=not acepta,
        use_container_width=True,
    ):
        resultado = eliminar_importacion_bancaria(
            importacion_id=int(importacion_id),
            empresa_id=empresa_id,
            usuario_id=usuario_actual_id(),
            motivo="Eliminación desde Banco / Caja > Importaciones.",
            forzar_eliminacion_admin=False,
        )

        if resultado.get("ok"):
            eliminados = resultado.get("eliminados", {})

            st.success(
                "Importación eliminada correctamente. "
                f"Importaciones: {eliminados.get('importaciones', 0)} | "
                f"Movimientos: {eliminados.get('movimientos', 0)} | "
                f"Asientos propuestos: {eliminados.get('asientos_propuestos', 0)} | "
                f"Grupos fiscales: {eliminados.get('grupos_fiscales', 0)}"
            )

            st.rerun()

        else:
            st.error(resultado.get("mensaje", "No se pudo eliminar la importación."))