import pandas as pd
import streamlit as st

from core.numeros import moneda
from core.ui import preparar_vista

from services.conciliacion_service import (
    confirmar_conciliacion_tesoreria,
    desconciliar_conciliacion_tesoreria,
    generar_sugerencias_conciliacion,
    inicializar_conciliacion,
    obtener_conciliaciones_tesoreria,
    obtener_movimientos_bancarios_pendientes,
    obtener_operaciones_tesoreria_pendientes,
    obtener_resumen_conciliacion,
)


# ======================================================
# UTILIDADES UI
# ======================================================

def empresa_actual_id():
    return int(st.session_state.get("empresa_id", 1))


def usuario_actual_id():
    usuario = st.session_state.get("usuario") or {}
    return usuario.get("id")


def _texto(valor):
    if valor is None:
        return ""

    try:
        if pd.isna(valor):
            return ""
    except Exception:
        pass

    return str(valor).strip()


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


def _formatear_estado(valor):
    return _texto(valor).replace("_", " ").title()


def _etiqueta_movimiento(row):
    importe = _numero(row.get("importe"))
    pendiente = _numero(row.get("importe_pendiente"))
    fecha = _texto(row.get("fecha"))
    banco = _texto(row.get("banco"))
    concepto = _texto(row.get("concepto"))

    signo = "Ingreso" if importe > 0 else "Egreso"

    return (
        f"Banco #{int(row['id'])} | {fecha} | {banco} | {signo} "
        f"{moneda(abs(importe))} | Pendiente {moneda(pendiente)} | {concepto[:80]}"
    )


def _etiqueta_operacion(row):
    importe = _numero(row.get("importe"))
    pendiente = _numero(row.get("importe_pendiente"))
    fecha = _texto(row.get("fecha_operacion"))
    tipo = _formatear_estado(row.get("tipo_operacion"))
    tercero = _texto(row.get("tercero_nombre")) or _texto(row.get("descripcion"))
    referencia = _texto(row.get("referencia_externa"))

    return (
        f"Tesorería #{int(row['id'])} | {fecha} | {tipo} | "
        f"{moneda(abs(importe))} | Pendiente {moneda(pendiente)} | "
        f"{tercero[:60]} | Ref {referencia[:40]}"
    )


def _preparar_sugerencias_vista(df):
    if df.empty:
        return df

    vista = df.copy()

    columnas = [
        "score",
        "confianza",
        "fecha_banco",
        "banco",
        "concepto_banco",
        "importe_banco",
        "pendiente_banco",
        "fecha_tesoreria",
        "tipo_operacion",
        "tercero_nombre",
        "descripcion_tesoreria",
        "importe_tesoreria",
        "pendiente_tesoreria",
        "importe_sugerido",
        "diferencia_importe",
        "diferencia_dias",
        "motivo",
    ]

    columnas = [c for c in columnas if c in vista.columns]

    return vista[columnas].rename(columns={
        "score": "Puntaje",
        "confianza": "Confianza",
        "fecha_banco": "Fecha banco",
        "banco": "Banco",
        "concepto_banco": "Concepto banco",
        "importe_banco": "Importe banco",
        "pendiente_banco": "Pendiente banco",
        "fecha_tesoreria": "Fecha tesorería",
        "tipo_operacion": "Tipo operación",
        "tercero_nombre": "Tercero",
        "descripcion_tesoreria": "Descripción tesorería",
        "importe_tesoreria": "Importe tesorería",
        "pendiente_tesoreria": "Pendiente tesorería",
        "importe_sugerido": "Importe sugerido",
        "diferencia_importe": "Dif. importe",
        "diferencia_dias": "Dif. días",
        "motivo": "Motivo sugerencia",
    })


def _preparar_movimientos_vista(df):
    if df.empty:
        return df

    columnas = [
        "id",
        "fecha",
        "banco",
        "nombre_cuenta",
        "referencia",
        "causal",
        "concepto",
        "importe",
        "importe_conciliado",
        "importe_pendiente",
        "estado_conciliacion",
        "tipo_movimiento_sugerido",
        "archivo",
    ]

    columnas = [c for c in columnas if c in df.columns]

    return df[columnas].rename(columns={
        "id": "ID",
        "fecha": "Fecha",
        "banco": "Banco",
        "nombre_cuenta": "Cuenta bancaria",
        "referencia": "Referencia",
        "causal": "Causal",
        "concepto": "Concepto",
        "importe": "Importe",
        "importe_conciliado": "Conciliado",
        "importe_pendiente": "Pendiente",
        "estado_conciliacion": "Estado",
        "tipo_movimiento_sugerido": "Tipo sugerido",
        "archivo": "Archivo",
    })


def _preparar_operaciones_vista(df):
    if df.empty:
        return df

    columnas = [
        "id",
        "fecha_operacion",
        "tipo_operacion",
        "cuenta_tesoreria",
        "medio_pago",
        "tercero_nombre",
        "tercero_cuit",
        "descripcion",
        "referencia_externa",
        "importe",
        "importe_conciliado",
        "importe_pendiente",
        "estado_conciliacion",
        "origen_modulo",
    ]

    columnas = [c for c in columnas if c in df.columns]

    return df[columnas].rename(columns={
        "id": "ID",
        "fecha_operacion": "Fecha",
        "tipo_operacion": "Tipo",
        "cuenta_tesoreria": "Cuenta tesorería",
        "medio_pago": "Medio de pago",
        "tercero_nombre": "Tercero",
        "tercero_cuit": "CUIT",
        "descripcion": "Descripción",
        "referencia_externa": "Referencia externa",
        "importe": "Importe",
        "importe_conciliado": "Conciliado",
        "importe_pendiente": "Pendiente",
        "estado_conciliacion": "Estado",
        "origen_modulo": "Origen",
    })


def _preparar_conciliaciones_vista(df):
    if df.empty:
        return df

    columnas = [
        "conciliacion_id",
        "fecha",
        "estado",
        "banco",
        "nombre_cuenta",
        "concepto_banco",
        "importe_banco",
        "tipo_operacion",
        "tercero_nombre",
        "descripcion_tesoreria",
        "importe_tesoreria",
        "importe_imputado",
        "referencia_externa",
        "observacion",
    ]

    columnas = [c for c in columnas if c in df.columns]

    return df[columnas].rename(columns={
        "conciliacion_id": "Conciliación",
        "fecha": "Fecha banco",
        "estado": "Estado",
        "banco": "Banco",
        "nombre_cuenta": "Cuenta banco",
        "concepto_banco": "Concepto banco",
        "importe_banco": "Importe banco",
        "tipo_operacion": "Tipo operación",
        "tercero_nombre": "Tercero",
        "descripcion_tesoreria": "Descripción tesorería",
        "importe_tesoreria": "Importe tesorería",
        "importe_imputado": "Importe conciliado",
        "referencia_externa": "Referencia externa",
        "observacion": "Observación",
    })


# ======================================================
# MÓDULO PRINCIPAL
# ======================================================

def mostrar_conciliacion():
    inicializar_conciliacion()

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Tablero",
        "Sugerencias automáticas",
        "Conciliación manual",
        "Conciliaciones confirmadas",
        "Desconciliar",
    ])

    with tab1:
        mostrar_tablero_conciliacion()

    with tab2:
        mostrar_sugerencias_automaticas()

    with tab3:
        mostrar_conciliacion_manual()

    with tab4:
        mostrar_conciliaciones_confirmadas()

    with tab5:
        mostrar_desconciliacion()


# ======================================================
# TABLERO
# ======================================================

def mostrar_tablero_conciliacion():
    st.subheader("Tablero de conciliación")

    st.info(
        "Este módulo cruza movimientos bancarios importados con operaciones reales de Tesorería. "
        "Banco conserva el extracto, Tesorería conserva el hecho financiero, y Conciliación deja el vínculo auditado."
    )

    empresa_id = empresa_actual_id()
    resumen = obtener_resumen_conciliacion(empresa_id)

    bancos = resumen.get("bancos", {})
    tesoreria = resumen.get("tesoreria", {})
    conciliaciones = resumen.get("conciliaciones", {})

    st.markdown("#### Banco")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Movimientos", int(bancos.get("movimientos", 0) or 0))
    c2.metric("Conciliados", int(bancos.get("conciliados", 0) or 0))
    c3.metric("Parciales", int(bancos.get("parciales", 0) or 0))
    c4.metric("Pendientes", int(bancos.get("pendientes", 0) or 0))

    c1, c2, c3 = st.columns(3)
    c1.metric("Importe banco", moneda(float(bancos.get("importe_total", 0) or 0)))
    c2.metric("Conciliado", moneda(float(bancos.get("importe_conciliado", 0) or 0)))
    c3.metric("Pendiente", moneda(float(bancos.get("importe_pendiente", 0) or 0)))

    st.markdown("#### Tesorería")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Operaciones", int(tesoreria.get("operaciones", 0) or 0))
    c2.metric("Conciliadas", int(tesoreria.get("conciliadas", 0) or 0))
    c3.metric("Parciales", int(tesoreria.get("parciales", 0) or 0))
    c4.metric("Pendientes", int(tesoreria.get("pendientes", 0) or 0))

    c1, c2, c3 = st.columns(3)
    c1.metric("Importe tesorería", moneda(float(tesoreria.get("importe_total", 0) or 0)))
    c2.metric("Conciliado", moneda(float(tesoreria.get("importe_conciliado", 0) or 0)))
    c3.metric("Pendiente", moneda(float(tesoreria.get("importe_pendiente", 0) or 0)))

    st.markdown("#### Vínculos Banco / Tesorería")

    c1, c2, c3 = st.columns(3)
    c1.metric("Conciliaciones", int(conciliaciones.get("conciliaciones", 0) or 0))
    c2.metric("Anuladas", int(conciliaciones.get("anuladas", 0) or 0))
    c3.metric("Importe activo", moneda(float(conciliaciones.get("importe_activo", 0) or 0)))

    st.warning(
        "Las imputaciones de clientes, proveedores y pagos fiscales que ya existen en Banco se desimputan desde Banco. "
        "Este módulo resuelve el vínculo Banco ↔ Tesorería para operaciones registradas por Cobranzas, Pagos, Caja y movimientos internos."
    )


# ======================================================
# SUGERENCIAS
# ======================================================

def mostrar_sugerencias_automaticas():
    st.subheader("Sugerencias automáticas")

    st.info(
        "El sistema propone coincidencias por signo, importe, fecha, referencia, tercero y descripción. "
        "Nada se confirma solo: la decisión final queda en el usuario."
    )

    empresa_id = empresa_actual_id()

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        tolerancia = st.number_input(
            "Tolerancia de importe",
            min_value=0.0,
            max_value=10000.0,
            value=1.0,
            step=0.5,
        )

    with col2:
        dias = st.number_input(
            "Días de diferencia",
            min_value=0,
            max_value=60,
            value=7,
            step=1,
        )

    with col3:
        confianza = st.selectbox("Confianza mínima", ["Alta", "Media", "Baja"], index=1)

    with col4:
        limite = st.number_input("Máximo sugerencias", min_value=10, max_value=1000, value=200, step=10)

    sugerencias = generar_sugerencias_conciliacion(
        empresa_id=empresa_id,
        tolerancia_importe=float(tolerancia),
        dias_maximos=int(dias),
        limite=int(limite),
        confianza_minima=confianza,
    )

    if sugerencias.empty:
        st.warning("No se encontraron sugerencias con los criterios seleccionados.")
        return

    col1, col2, col3 = st.columns(3)
    col1.metric("Sugerencias", len(sugerencias))
    col2.metric("Alta confianza", len(sugerencias[sugerencias["confianza"] == "Alta"]))
    col3.metric("Importe sugerido", moneda(float(sugerencias["importe_sugerido"].sum())))

    st.dataframe(
        preparar_vista(_preparar_sugerencias_vista(sugerencias)),
        use_container_width=True,
    )

    st.divider()
    st.markdown("#### Confirmar una sugerencia")

    idx = st.selectbox(
        "Sugerencia a confirmar",
        list(range(len(sugerencias))),
        format_func=lambda i: (
            f"Score {int(sugerencias.iloc[int(i)]['score'])} | "
            f"{sugerencias.iloc[int(i)]['confianza']} | "
            f"Banco #{int(sugerencias.iloc[int(i)]['movimiento_banco_id'])} ↔ "
            f"Tesorería #{int(sugerencias.iloc[int(i)]['operacion_tesoreria_id'])} | "
            f"{moneda(_numero(sugerencias.iloc[int(i)]['importe_sugerido']))}"
        ),
        key="conciliacion_sugerencia_idx",
    )

    sugerencia = sugerencias.iloc[int(idx)]

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Banco**")
        st.write(f"Fecha: {_texto(sugerencia.get('fecha_banco'))}")
        st.write(f"Banco: {_texto(sugerencia.get('banco'))}")
        st.write(f"Concepto: {_texto(sugerencia.get('concepto_banco'))}")
        st.write(f"Importe: {moneda(_numero(sugerencia.get('importe_banco')))}")
        st.write(f"Pendiente: {moneda(_numero(sugerencia.get('pendiente_banco')))}")

    with col2:
        st.markdown("**Tesorería**")
        st.write(f"Fecha: {_texto(sugerencia.get('fecha_tesoreria'))}")
        st.write(f"Tipo: {_formatear_estado(sugerencia.get('tipo_operacion'))}")
        st.write(f"Tercero: {_texto(sugerencia.get('tercero_nombre'))}")
        st.write(f"Descripción: {_texto(sugerencia.get('descripcion_tesoreria'))}")
        st.write(f"Importe: {moneda(_numero(sugerencia.get('importe_tesoreria')))}")
        st.write(f"Pendiente: {moneda(_numero(sugerencia.get('pendiente_tesoreria')))}")

    importe = st.number_input(
        "Importe a conciliar",
        min_value=0.0,
        max_value=float(min(_numero(sugerencia.get("pendiente_banco")), _numero(sugerencia.get("pendiente_tesoreria")))),
        value=float(_numero(sugerencia.get("importe_sugerido"))),
        step=0.01,
        key="conciliacion_sugerencia_importe",
    )

    observacion = st.text_area(
        "Observación",
        value=f"Conciliación sugerida por sistema. Motivo: {_texto(sugerencia.get('motivo'))}",
        key="conciliacion_sugerencia_observacion",
    )

    aceptar = st.checkbox(
        "Confirmo que revisé la sugerencia y quiero conciliar Banco contra Tesorería.",
        key="conciliacion_sugerencia_aceptar",
    )

    if st.button(
        "Confirmar conciliación sugerida",
        type="primary",
        disabled=not aceptar,
        use_container_width=True,
    ):
        resultado = confirmar_conciliacion_tesoreria(
            empresa_id=empresa_id,
            movimiento_banco_id=int(sugerencia["movimiento_banco_id"]),
            operacion_tesoreria_id=int(sugerencia["operacion_tesoreria_id"]),
            importe_conciliar=float(importe),
            usuario_id=usuario_actual_id(),
            observacion=observacion,
        )

        if resultado.get("ok"):
            st.success(resultado.get("mensaje"))
            st.rerun()
        else:
            st.error(resultado.get("mensaje", "No se pudo confirmar la conciliación."))


# ======================================================
# MANUAL
# ======================================================

def mostrar_conciliacion_manual():
    st.subheader("Conciliación manual asistida")

    st.info(
        "Usá esta opción cuando el sistema no encuentre una sugerencia suficiente, pero vos puedas identificar "
        "el vínculo correcto entre el banco y la operación registrada en Tesorería."
    )

    empresa_id = empresa_actual_id()
    movimientos = obtener_movimientos_bancarios_pendientes(empresa_id=empresa_id)
    operaciones = obtener_operaciones_tesoreria_pendientes(empresa_id=empresa_id)

    if movimientos.empty:
        st.warning("No hay movimientos bancarios pendientes de conciliación.")
        return

    if operaciones.empty:
        st.warning("No hay operaciones de Tesorería pendientes de conciliación.")
        return

    col1, col2 = st.columns(2)

    with col1:
        movimiento_id = st.selectbox(
            "Movimiento bancario",
            movimientos["id"].astype(int).tolist(),
            format_func=lambda x: _etiqueta_movimiento(
                movimientos[movimientos["id"].astype(int) == int(x)].iloc[0]
            ),
            key="conciliacion_manual_movimiento_id",
        )

    movimiento = movimientos[movimientos["id"].astype(int) == int(movimiento_id)].iloc[0]
    signo_mov = 1 if _numero(movimiento.get("importe")) > 0 else -1

    operaciones_compatibles = operaciones[
        operaciones["importe"].apply(lambda x: 1 if _numero(x) > 0 else -1) == signo_mov
    ].copy()

    if operaciones_compatibles.empty:
        st.warning("No hay operaciones de Tesorería con signo compatible para este movimiento.")
        return

    with col2:
        operacion_id = st.selectbox(
            "Operación de Tesorería",
            operaciones_compatibles["id"].astype(int).tolist(),
            format_func=lambda x: _etiqueta_operacion(
                operaciones_compatibles[operaciones_compatibles["id"].astype(int) == int(x)].iloc[0]
            ),
            key="conciliacion_manual_operacion_id",
        )

    operacion = operaciones_compatibles[operaciones_compatibles["id"].astype(int) == int(operacion_id)].iloc[0]

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### Movimiento bancario")
        st.dataframe(
            preparar_vista(_preparar_movimientos_vista(pd.DataFrame([movimiento.to_dict()]))),
            use_container_width=True,
        )

    with col2:
        st.markdown("#### Operación Tesorería")
        st.dataframe(
            preparar_vista(_preparar_operaciones_vista(pd.DataFrame([operacion.to_dict()]))),
            use_container_width=True,
        )

    pendiente_banco = _numero(movimiento.get("importe_pendiente"))
    pendiente_tesoreria = _numero(operacion.get("importe_pendiente"))
    maximo = min(pendiente_banco, pendiente_tesoreria)

    importe = st.number_input(
        "Importe a conciliar",
        min_value=0.0,
        max_value=float(maximo),
        value=float(maximo),
        step=0.01,
        key="conciliacion_manual_importe",
    )

    observacion = st.text_area(
        "Observación",
        value="Conciliación manual asistida entre movimiento bancario y operación de Tesorería.",
        key="conciliacion_manual_observacion",
    )

    aceptar = st.checkbox(
        "Confirmo que el vínculo Banco/Tesorería es correcto.",
        key="conciliacion_manual_aceptar",
    )

    if st.button(
        "Confirmar conciliación manual",
        type="primary",
        disabled=not aceptar,
        use_container_width=True,
    ):
        resultado = confirmar_conciliacion_tesoreria(
            empresa_id=empresa_id,
            movimiento_banco_id=int(movimiento_id),
            operacion_tesoreria_id=int(operacion_id),
            importe_conciliar=float(importe),
            usuario_id=usuario_actual_id(),
            observacion=observacion,
        )

        if resultado.get("ok"):
            st.success(resultado.get("mensaje"))
            st.rerun()
        else:
            st.error(resultado.get("mensaje", "No se pudo confirmar la conciliación."))


# ======================================================
# CONFIRMADAS
# ======================================================

def mostrar_conciliaciones_confirmadas():
    st.subheader("Conciliaciones confirmadas")

    empresa_id = empresa_actual_id()
    conciliaciones = obtener_conciliaciones_tesoreria(empresa_id=empresa_id, incluir_anuladas=False)

    if conciliaciones.empty:
        st.info("Todavía no hay conciliaciones Banco/Tesorería confirmadas.")
        return

    col1, col2, col3 = st.columns(3)
    col1.metric("Conciliaciones", len(conciliaciones))
    col2.metric("Importe conciliado", moneda(float(conciliaciones["importe_imputado"].sum())))
    col3.metric("Operaciones únicas", conciliaciones["operacion_tesoreria_id"].nunique())

    buscar = st.text_input(
        "Buscar por banco, concepto, tercero, referencia u observación",
        key="conciliacion_confirmadas_buscar",
    ).strip().lower()

    filtrado = conciliaciones.copy()

    if buscar:
        texto = (
            filtrado["banco"].astype(str)
            + " "
            + filtrado["concepto_banco"].astype(str)
            + " "
            + filtrado["tercero_nombre"].astype(str)
            + " "
            + filtrado["referencia_externa"].astype(str)
            + " "
            + filtrado["observacion"].astype(str)
        ).str.lower()

        filtrado = filtrado[texto.str.contains(buscar, na=False)]

    if filtrado.empty:
        st.warning("No hay conciliaciones con ese filtro.")
        return

    st.dataframe(
        preparar_vista(_preparar_conciliaciones_vista(filtrado)),
        use_container_width=True,
    )


# ======================================================
# DESCONCILIAR
# ======================================================

def mostrar_desconciliacion():
    st.subheader("Desconciliar Banco / Tesorería")

    st.info(
        "La desconciliación no borra el movimiento bancario ni la operación de Tesorería. "
        "Marca la conciliación como anulada, revierte los importes conciliados y deja auditoría."
    )

    empresa_id = empresa_actual_id()
    conciliaciones = obtener_conciliaciones_tesoreria(empresa_id=empresa_id, incluir_anuladas=False)

    if conciliaciones.empty:
        st.success("No hay conciliaciones Banco/Tesorería activas para desconciliar.")
        return

    idx = st.selectbox(
        "Conciliación a desconciliar",
        list(range(len(conciliaciones))),
        format_func=lambda i: (
            f"Conciliación #{int(conciliaciones.iloc[int(i)]['conciliacion_id'])} | "
            f"{conciliaciones.iloc[int(i)]['fecha']} | "
            f"{moneda(_numero(conciliaciones.iloc[int(i)]['importe_imputado']))} | "
            f"Banco #{int(conciliaciones.iloc[int(i)]['movimiento_banco_id'])} ↔ "
            f"Tesorería #{int(conciliaciones.iloc[int(i)]['operacion_tesoreria_id'])}"
        ),
        key="conciliacion_desconciliar_idx",
    )

    fila = conciliaciones.iloc[int(idx)]

    st.dataframe(
        preparar_vista(_preparar_conciliaciones_vista(pd.DataFrame([fila.to_dict()]))),
        use_container_width=True,
    )

    motivo = st.text_area(
        "Motivo de desconciliación",
        value="Corrección de conciliación Banco/Tesorería realizada por error.",
        key="conciliacion_desconciliar_motivo",
    )

    aceptar = st.checkbox(
        f"Confirmo que quiero desconciliar la conciliación #{int(fila['conciliacion_id'])}.",
        key="conciliacion_desconciliar_aceptar",
    )

    if st.button(
        "Desconciliar operación seleccionada",
        type="primary",
        disabled=not aceptar,
        use_container_width=True,
    ):
        resultado = desconciliar_conciliacion_tesoreria(
            conciliacion_id=int(fila["conciliacion_id"]),
            empresa_id=empresa_id,
            usuario_id=usuario_actual_id(),
            motivo=motivo,
        )

        if resultado.get("ok"):
            st.success(resultado.get("mensaje"))
            st.rerun()
        else:
            st.error(resultado.get("mensaje", "No se pudo desconciliar."))