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
    nombre_tipo_movimiento,
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


def empresa_actual_id():
    return int(st.session_state.get("empresa_id", 1))


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
            empresa_id=empresa_actual_id()
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
                    f"Asientos automáticos propuestos balanceados. "
                    f"Debe: {moneda(debe)} / Haber: {moneda(haber)}."
                )
            else:
                st.error(
                    f"Los asientos propuestos no cuadran. "
                    f"Debe: {moneda(debe)} / Haber: {moneda(haber)} / Diferencia: {moneda(diferencia)}."
                )

        por_tipo = resumen.get("por_tipo")

        if por_tipo is not None and not por_tipo.empty:
            with st.expander("Ver resumen por tipo detectado", expanded=False):
                vista = por_tipo.copy()
                vista = vista.rename(columns={
                    "tipo_visible": "Tipo detectado",
                    "movimientos": "Movimientos",
                    "debitos": "Débitos",
                    "creditos": "Créditos",
                    "neto": "Neto",
                })
                st.dataframe(preparar_vista(vista), use_container_width=True)

        asientos = resumen.get("asientos")

        if asientos is not None and not asientos.empty:
            with st.expander("Ver asientos automáticos propuestos", expanded=True):
                vista_asientos = asientos.copy()
                vista_asientos["tipo_visible"] = vista_asientos["tipo_movimiento_sugerido"].apply(nombre_tipo_movimiento)
                vista_asientos = vista_asientos.rename(columns={
                    "fecha": "Fecha",
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
                    "Fecha", "Concepto", "Tipo", "Cuenta", "Nombre cuenta",
                    "Debe", "Haber", "Glosa", "Estado"
                ]
                columnas = [c for c in columnas if c in vista_asientos.columns]
                st.dataframe(preparar_vista(vista_asientos[columnas]), use_container_width=True)

        pendientes = resumen.get("pendientes")

        if pendientes is not None and not pendientes.empty:
            st.info(
                "Los cobros, pagos, inversiones/rescates, movimientos de socios, transferencias entre cuentas "
                "y ARCA/AFIP a clasificar quedan para imputación o revisión asistida."
            )

    if st.button("Ocultar resultado de importación"):
        limpiar_resultado_importacion_banco()
        st.rerun()

    st.divider()




def preparar_movimientos_vista(df):
    if df.empty:
        return df

    vista = df.copy()

    if "tipo_movimiento_sugerido" in vista.columns:
        vista["tipo_visible"] = vista["tipo_movimiento_sugerido"].apply(nombre_tipo_movimiento)

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
    vista["tipo_visible"] = vista["tipo_movimiento_sugerido"].apply(nombre_tipo_movimiento)

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


def mostrar_metricas_importacion(resultado):
    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Detectados", resultado.get("detectados", 0))
    col2.metric("Importados", resultado.get("procesados", 0))
    col3.metric("Duplicados", resultado.get("duplicados", 0))
    col4.metric("Errores", resultado.get("errores", 0))


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
        "Importaciones"
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


def mostrar_importar_extracto():
    st.subheader("Importar extracto bancario")

    st.info(
        "Cargá el extracto. El sistema separa automáticamente lo rutinario de lo que requiere decisión: "
        "gastos bancarios, IVA crédito fiscal bancario, percepciones e impuesto débitos/créditos generan "
        "asientos propuestos; cobros, pagos, ARCA/AFIP, inversiones, socios y otros quedan para imputación."
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
                "Mapeo manual"
            ]
        )

    archivo = st.file_uploader(
        "Subir extracto bancario",
        type=["xls", "xlsx", "csv", "txt"],
        key=f"banco_extracto_uploader_{obtener_version_uploader_banco()}"
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
                use_container_width=True
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
            mapeo_manual=mapeo_manual
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
            step=0.01
        )

    with col2:
        st.metric("Créditos", moneda(total_creditos))

    with col3:
        st.metric("Débitos", moneda(total_debitos))

    with col4:
        saldo_final = st.number_input(
            "Saldo final extracto",
            value=saldo_final_default,
            step=0.01
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
            f"{moneda(saldo_inicial_sugerido)}. Revisá si el extracto está completo o si falta cargar saldo inicial."
        )

    df_tmp = df_movimientos.copy()
    df_tmp["tipo_visible"] = df_tmp["tipo_movimiento_sugerido"].apply(nombre_tipo_movimiento)

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

    resumen_tipo = (
        df_tmp
        .groupby(["tipo_movimiento_sugerido", "tipo_visible"], as_index=False)
        .agg(
            movimientos=("fecha", "count"),
            debitos=("debito", "sum"),
            creditos=("credito", "sum"),
            neto=("importe", "sum")
        )
        .sort_values(["movimientos", "debitos", "creditos"], ascending=False)
    )

    st.markdown("#### 1. Conceptos que irán a asientos propuestos")

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
                neto=("importe", "sum")
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
            use_container_width=True
        )

    st.markdown("#### 2. Conceptos que requieren revisión o imputación")

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
                neto=("importe", "sum")
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
            use_container_width=True
        )

    with st.expander("Ver detalle técnico del extracto", expanded=False):
        st.caption("Detalle técnico para auditoría. No hace falta revisarlo para operar normalmente.")
        st.dataframe(
            preparar_vista(preparar_previsualizacion(df_tmp.head(150))),
            use_container_width=True
        )

        st.markdown("##### Resumen completo por tipo")
        vista_resumen = resumen_tipo.rename(columns={
            "tipo_visible": "Tipo detectado",
            "movimientos": "Movimientos",
            "debitos": "Débitos",
            "creditos": "Créditos",
            "neto": "Neto",
        })
        st.dataframe(
            preparar_vista(vista_resumen[["Tipo detectado", "Movimientos", "Débitos", "Créditos", "Neto"]]),
            use_container_width=True
        )

    st.warning(
        "Al importar, el sistema guardará los movimientos, omitirá duplicados y preparará asientos propuestos "
        "para los conceptos rutinarios. Los asientos todavía no impactan en Libro Diario."
    )

    col1, col2 = st.columns([3, 1])

    with col1:
        importar = st.button(
            "Guardar importación y generar asientos propuestos",
            type="primary",
            use_container_width=True
        )

    with col2:
        cancelar = st.button(
            "Limpiar archivo",
            use_container_width=True
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
        saldo_final_extracto=saldo_final
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




def mostrar_pendientes_imputacion():
    st.subheader("Pendientes de imputación")

    st.info(
        "Acá queda solo lo que requiere decisión humana: cobros, pagos, ARCA/AFIP a clasificar, "
        "inversiones/rescates, socios, transferencias entre cuentas y otros movimientos a revisar."
    )

    empresa_id = empresa_actual_id()
    df = obtener_movimientos_pendientes_imputacion(empresa_id)

    if df.empty:
        st.success("No hay movimientos pendientes de imputación manual.")
        return

    df = df.copy()
    df["tipo_visible"] = df["tipo_movimiento_sugerido"].apply(nombre_tipo_movimiento)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Pendientes", len(df))
    col2.metric("Ingresos pendientes", moneda(float(df[df["importe"] > 0]["importe_pendiente"].sum())))
    col3.metric("Egresos pendientes", moneda(float(df[df["importe"] < 0]["importe_pendiente"].sum())))
    col4.metric("Total pendiente", moneda(float(df["importe_pendiente"].sum())))

    tipos = ["Todos"] + sorted(df["tipo_movimiento_sugerido"].dropna().unique().tolist())

    col1, col2 = st.columns([1.5, 2])

    with col1:
        tipo = st.selectbox(
            "Tipo pendiente",
            tipos,
            format_func=lambda x: "Todos" if x == "Todos" else nombre_tipo_movimiento(x),
            key="banco_pend_tipo"
        )

    with col2:
        buscar = st.text_input(
            "Buscar concepto / referencia / causal",
            key="banco_pend_buscar"
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
        "archivo"
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

    st.warning(
        "La imputación contra facturas de venta, compras, anticipos, socios o impuestos específicos "
        "se hará en el módulo de Conciliación. Esta pantalla deja limpio lo pendiente."
    )


def mostrar_asientos_propuestos():
    st.subheader("Asientos automáticos propuestos")

    st.info(
        "Estos asientos surgen de conceptos rutinarios detectados: gastos bancarios, IVA crédito fiscal bancario, "
        "percepciones e impuesto débitos/créditos bancarios. Todavía no impactan en Libro Diario."
    )

    empresa_id = empresa_actual_id()
    df = obtener_asientos_propuestos_banco(empresa_id=empresa_id)

    if df.empty:
        st.info("No hay asientos automáticos propuestos pendientes.")
        return

    df = df.copy()
    df["tipo_visible"] = df["tipo_movimiento_sugerido"].apply(nombre_tipo_movimiento)

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

    tipos = ["Todos"] + sorted(df["tipo_movimiento_sugerido"].dropna().unique().tolist())

    tipo = st.selectbox(
        "Filtrar por tipo",
        tipos,
        format_func=lambda x: "Todos" if x == "Todos" else nombre_tipo_movimiento(x),
        key="banco_asiento_tipo"
    )

    filtrado = df.copy()

    if tipo != "Todos":
        filtrado = filtrado[filtrado["tipo_movimiento_sugerido"] == tipo]

    vista = filtrado.rename(columns={
        "fecha": "Fecha",
        "banco": "Banco",
        "nombre_cuenta": "Cuenta",
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
        "Fecha", "Banco", "Cuenta", "Concepto", "Tipo",
        "Cuenta", "Nombre cuenta", "Debe", "Haber", "Glosa", "Estado"
    ]
    columnas = [c for c in columnas if c in vista.columns]

    st.dataframe(preparar_vista(vista[columnas]), use_container_width=True)

    st.warning(
        "Próximo paso: agregar botón de confirmación para enviar estos asientos al Libro Diario "
        "con auditoría y opción de reversión."
    )


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
            key="bancos_buscar_movimientos"
        ).strip().lower()

    with col2:
        tipos = ["Todos"] + sorted(df["tipo_movimiento_sugerido"].dropna().unique().tolist())
        tipo = st.selectbox(
            "Tipo sugerido",
            tipos,
            format_func=lambda x: "Todos" if x == "Todos" else nombre_tipo_movimiento(x)
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
        use_container_width=True
    )

    excel = exportar_excel({
        "Movimientos Bancarios": preparar_movimientos_vista(df_filtrado)
    })

    st.download_button(
        "Descargar movimientos bancarios Excel",
        data=excel,
        file_name="movimientos_bancarios.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


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
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


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
                format_func=lambda x: nombre_tipo_movimiento(x)
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
                    confianza=confianza
                )

                st.success("Regla creada.")

    st.divider()
    st.markdown("#### Reglas existentes")

    reglas = obtener_reglas_bancarias(empresa_id)

    if reglas.empty:
        st.info("No hay reglas bancarias cargadas.")
    else:
        st.dataframe(preparar_vista(reglas), use_container_width=True)


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


def mostrar_configuracion_contable():
    st.subheader("Configuración contable Banco / Caja")

    st.info(
        "Estas son las cuentas que usa Banco/Caja para sugerir asientos. "
        "La generación definitiva de asientos se hará más adelante desde Conciliación."
    )

    empresa_id = empresa_actual_id()
    df = obtener_configuracion_contable_bancos(empresa_id)

    if df.empty:
        st.warning("No hay configuración contable bancaria.")
        return

    vista = df.rename(columns={
        "clave": "Clave",
        "cuenta_codigo": "Cuenta código",
        "cuenta_nombre": "Cuenta nombre",
        "descripcion": "Descripción",
        "activo": "Activo",
    })

    st.dataframe(preparar_vista(vista), use_container_width=True)


def mostrar_resumen_bancario():
    st.subheader("Resumen Banco / Caja")

    empresa_id = empresa_actual_id()
    resumen = obtener_resumen_bancario(empresa_id)

    por_tipo = resumen["por_tipo"]
    por_mes = resumen["por_mes"]
    por_estado = resumen["por_estado"]

    if por_tipo.empty and por_mes.empty:
        st.info("No hay movimientos bancarios para resumir.")
        return

    indicadores = resumen.get("indicadores", {})

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Movimientos", indicadores.get("total_movimientos", 0))
    c2.metric("Conciliados", indicadores.get("conciliados", 0))
    c3.metric("Parciales", indicadores.get("parciales", 0))
    c4.metric("Pendientes", indicadores.get("pendientes", 0))

    c1, c2, c3 = st.columns(3)

    c1.metric("% importe conciliado", f"{indicadores.get('porcentaje_importe_conciliado', 0)}%")
    c2.metric("Importe conciliado", moneda(float(indicadores.get("total_conciliado", 0))))
    c3.metric("Importe pendiente", moneda(float(indicadores.get("total_pendiente", 0))))

    if not por_tipo.empty:
        st.subheader("Resumen por tipo sugerido")

        vista_tipo = por_tipo[[
            "tipo_visible",
            "movimientos",
            "debitos",
            "creditos",
            "neto",
            "conciliado",
            "pendiente",
        ]].rename(columns={
            "tipo_visible": "Tipo sugerido",
            "movimientos": "Movimientos",
            "debitos": "Débitos",
            "creditos": "Créditos",
            "neto": "Neto",
            "conciliado": "Conciliado",
            "pendiente": "Pendiente",
        })

        st.dataframe(preparar_vista(vista_tipo), use_container_width=True)

    if not por_mes.empty:
        st.subheader("Resumen mensual")

        vista_mes = por_mes.rename(columns={
            "anio": "Año",
            "mes": "Mes",
            "movimientos": "Movimientos",
            "debitos": "Débitos",
            "creditos": "Créditos",
            "neto": "Neto",
            "conciliado": "Conciliado",
            "pendiente": "Pendiente",
        })

        st.dataframe(preparar_vista(vista_mes), use_container_width=True)

    if not por_estado.empty:
        st.subheader("Resumen por estado de conciliación")

        vista_estado = por_estado.rename(columns={
            "estado_conciliacion": "Estado conciliación",
            "movimientos": "Movimientos",
            "debitos": "Débitos",
            "creditos": "Créditos",
            "neto": "Neto",
            "conciliado": "Conciliado",
            "pendiente": "Pendiente",
        })

        st.dataframe(preparar_vista(vista_estado), use_container_width=True)

    excel = exportar_excel({
        "Resumen Tipo": por_tipo,
        "Resumen Mensual": por_mes,
        "Resumen Estado": por_estado,
    })

    st.download_button(
        "Descargar resumen Banco / Caja Excel",
        data=excel,
        file_name="resumen_banco_caja.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


def mostrar_importaciones():
    st.subheader("Importaciones bancarias")

    empresa_id = empresa_actual_id()
    df = obtener_importaciones_bancarias(empresa_id)

    if df.empty:
        st.info("No hay importaciones bancarias registradas.")
        return

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
