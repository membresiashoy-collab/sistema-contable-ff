from datetime import date
from typing import Any, Dict, Optional

import pandas as pd
import streamlit as st

from database import conectar
from services.capital_social_service import (
    anular_integracion_capital,
    configurar_capital_social_inicial,
    crear_socio_empresa,
    listar_capital_social_empresa,
    listar_eventos_capital,
    listar_movimientos_tesoreria_disponibles_para_integracion,
    listar_pendientes_integracion_por_socio,
    listar_socios_empresa,
    obtener_resumen_capital_socios,
)


def _texto(valor: Any, default: str = "") -> str:
    if valor is None:
        return default
    texto = str(valor).strip()
    return texto if texto else default


def _numero(valor: Any, default: float = 0.0) -> float:
    try:
        if valor is None:
            return default
        if isinstance(valor, str):
            valor = valor.replace(".", "").replace(",", ".") if "," in valor else valor
        return float(valor)
    except Exception:
        return default


def _moneda(valor: Any) -> str:
    return f"$ {_numero(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _fecha(valor: Any) -> str:
    if valor is None or valor == "":
        return ""
    try:
        return pd.to_datetime(valor).strftime("%d/%m/%Y")
    except Exception:
        return str(valor)


def _preparar_vista_default(df: Any) -> pd.DataFrame:
    if df is None:
        return pd.DataFrame()
    if not isinstance(df, pd.DataFrame):
        return pd.DataFrame(df)
    return df.copy()


def _df_no_vacio(df: Any) -> bool:
    return isinstance(df, pd.DataFrame) and not df.empty


def _rerun():
    if hasattr(st, "rerun"):
        st.rerun()
    elif hasattr(st, "experimental_rerun"):
        st.experimental_rerun()


def _usuario_actual(usuario: Optional[str] = None) -> Optional[str]:
    if usuario:
        return usuario
    try:
        datos_usuario = st.session_state.get("usuario")
        if isinstance(datos_usuario, dict):
            return datos_usuario.get("nombre") or datos_usuario.get("email") or datos_usuario.get("usuario")
        if datos_usuario:
            return str(datos_usuario)
    except Exception:
        pass
    return None


def _empresa_id_desde_perfil(perfil: Optional[Dict[str, Any]] = None, empresa_id: Optional[int] = None) -> Optional[int]:
    if empresa_id is not None:
        try:
            return int(empresa_id)
        except Exception:
            return None

    perfil = perfil or {}
    candidatos = [
        perfil.get("empresa_id"),
        perfil.get("id"),
    ]

    empresa = perfil.get("empresa")
    if isinstance(empresa, dict):
        candidatos.extend([empresa.get("id"), empresa.get("empresa_id")])

    for candidato in candidatos:
        try:
            if candidato is not None and str(candidato).strip() != "":
                return int(candidato)
        except Exception:
            continue

    try:
        empresa_session = st.session_state.get("empresa_actual")
        if isinstance(empresa_session, dict):
            for clave in ("id", "empresa_id"):
                valor = empresa_session.get(clave)
                if valor is not None:
                    return int(valor)
        if empresa_session is not None and str(empresa_session).strip().isdigit():
            return int(empresa_session)
    except Exception:
        pass

    return None


def _leer_sql_df(sql: str, params: tuple = ()) -> pd.DataFrame:
    conn = conectar()
    try:
        return pd.read_sql_query(sql, conn, params=params)
    finally:
        conn.close()


def _tabla_existe(nombre_tabla: str) -> bool:
    conn = conectar()
    try:
        fila = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
            (nombre_tabla,),
        ).fetchone()
        return fila is not None
    finally:
        conn.close()


def _listar_ejercicios_empresa(empresa_id: int) -> pd.DataFrame:
    if not _tabla_existe("ejercicios_contables"):
        return pd.DataFrame()

    return _leer_sql_df(
        """
        SELECT
            id,
            nombre,
            fecha_inicio,
            fecha_fin,
            estado
        FROM ejercicios_contables
        WHERE empresa_id = ?
          AND UPPER(COALESCE(estado, '')) <> 'ANULADO'
        ORDER BY fecha_inicio DESC, id DESC
        """,
        (int(empresa_id),),
    )


def _listar_integraciones_reales(empresa_id: int) -> pd.DataFrame:
    if not _tabla_existe("capital_integraciones"):
        return pd.DataFrame()

    try:
        return _leer_sql_df(
            """
            SELECT
                ci.id AS integracion_id,
                ci.empresa_id,
                ci.capital_id,
                ci.suscripcion_id,
                ci.socio_id,
                se.nombre AS socio_nombre,
                ci.fecha_integracion,
                ci.importe,
                ci.medio_integracion,
                ci.origen_modulo,
                ci.origen_tabla,
                ci.origen_id,
                ci.referencia,
                ci.observaciones,
                ci.asiento_propuesto_id,
                ci.estado,
                ci.fecha_anulacion,
                ci.motivo_anulacion
            FROM capital_integraciones ci
            LEFT JOIN socios_empresa se ON se.id = ci.socio_id
            WHERE ci.empresa_id = ?
            ORDER BY ci.fecha_integracion DESC, ci.id DESC
            """,
            (int(empresa_id),),
        )
    except Exception:
        return pd.DataFrame()


def _vista_socios(df: pd.DataFrame, preparar_vista) -> pd.DataFrame:
    if not _df_no_vacio(df):
        return pd.DataFrame()

    columnas = [
        col
        for col in [
            "id",
            "nombre",
            "cuit",
            "tipo_socio",
            "porcentaje_participacion",
            "estado",
            "observaciones",
        ]
        if col in df.columns
    ]
    vista = df[columnas].copy()
    renombres = {
        "id": "ID",
        "nombre": "Socio / accionista",
        "cuit": "CUIT",
        "tipo_socio": "Tipo",
        "porcentaje_participacion": "% participación",
        "estado": "Estado",
        "observaciones": "Observaciones",
    }
    vista = vista.rename(columns=renombres)
    return preparar_vista(vista)


def _vista_capitales(df: pd.DataFrame, preparar_vista) -> pd.DataFrame:
    if not _df_no_vacio(df):
        return pd.DataFrame()

    columnas = [
        col
        for col in [
            "id",
            "fecha_instrumento",
            "descripcion",
            "capital_social_total",
            "total_suscripto",
            "total_integrado",
            "total_pendiente_integracion",
            "estado",
        ]
        if col in df.columns
    ]
    vista = df[columnas].copy()
    for col in ["capital_social_total", "total_suscripto", "total_integrado", "total_pendiente_integracion"]:
        if col in vista.columns:
            vista[col] = vista[col].map(_moneda)
    if "fecha_instrumento" in vista.columns:
        vista["fecha_instrumento"] = vista["fecha_instrumento"].map(_fecha)

    vista = vista.rename(
        columns={
            "id": "ID",
            "fecha_instrumento": "Fecha instrumento",
            "descripcion": "Descripción",
            "capital_social_total": "Capital social",
            "total_suscripto": "Suscripto",
            "total_integrado": "Integrado",
            "total_pendiente_integracion": "Pendiente",
            "estado": "Estado",
        }
    )
    return preparar_vista(vista)


def _vista_pendientes(df: pd.DataFrame, preparar_vista) -> pd.DataFrame:
    if not _df_no_vacio(df):
        return pd.DataFrame()

    columnas = [
        col
        for col in [
            "capital_id",
            "socio_id",
            "socio_nombre",
            "socio_cuit",
            "porcentaje",
            "importe_suscripto",
            "importe_integrado",
            "importe_pendiente",
            "capital_descripcion",
        ]
        if col in df.columns
    ]
    vista = df[columnas].copy()
    for col in ["importe_suscripto", "importe_integrado", "importe_pendiente"]:
        if col in vista.columns:
            vista[col] = vista[col].map(_moneda)

    vista = vista.rename(
        columns={
            "capital_id": "Capital ID",
            "socio_id": "Socio ID",
            "socio_nombre": "Socio / accionista",
            "socio_cuit": "CUIT",
            "porcentaje": "%",
            "importe_suscripto": "Suscripto",
            "importe_integrado": "Integrado",
            "importe_pendiente": "Pendiente",
            "capital_descripcion": "Capital",
        }
    )
    return preparar_vista(vista)


def _vista_movimientos_tesoreria(df: pd.DataFrame, preparar_vista) -> pd.DataFrame:
    if not _df_no_vacio(df):
        return pd.DataFrame()

    columnas_preferidas = [
        "tesoreria_operacion_id",
        "fecha",
        "tipo_operacion",
        "subtipo",
        "cuenta_tesoreria_nombre",
        "cuenta_tesoreria_tipo",
        "concepto",
        "referencia",
        "importe",
        "estado",
    ]
    columnas = [col for col in columnas_preferidas if col in df.columns]
    vista = df[columnas].copy()

    if "fecha" in vista.columns:
        vista["fecha"] = vista["fecha"].map(_fecha)
    if "importe" in vista.columns:
        vista["importe"] = vista["importe"].map(_moneda)

    vista = vista.rename(
        columns={
            "tesoreria_operacion_id": "Movimiento Tesorería ID",
            "fecha": "Fecha",
            "tipo_operacion": "Tipo",
            "subtipo": "Subtipo",
            "cuenta_tesoreria_nombre": "Cuenta Tesorería",
            "cuenta_tesoreria_tipo": "Tipo cuenta",
            "concepto": "Concepto",
            "referencia": "Referencia",
            "importe": "Importe",
            "estado": "Estado",
        }
    )
    return preparar_vista(vista)


def _vista_integraciones(df: pd.DataFrame, preparar_vista) -> pd.DataFrame:
    if not _df_no_vacio(df):
        return pd.DataFrame()

    columnas = [
        col
        for col in [
            "integracion_id",
            "fecha_integracion",
            "socio_nombre",
            "importe",
            "medio_integracion",
            "origen_modulo",
            "origen_id",
            "referencia",
            "asiento_propuesto_id",
            "estado",
            "motivo_anulacion",
        ]
        if col in df.columns
    ]
    vista = df[columnas].copy()
    if "fecha_integracion" in vista.columns:
        vista["fecha_integracion"] = vista["fecha_integracion"].map(_fecha)
    if "importe" in vista.columns:
        vista["importe"] = vista["importe"].map(_moneda)

    vista = vista.rename(
        columns={
            "integracion_id": "Integración ID",
            "fecha_integracion": "Fecha",
            "socio_nombre": "Socio / accionista",
            "importe": "Importe",
            "medio_integracion": "Medio",
            "origen_modulo": "Origen",
            "origen_id": "Origen ID",
            "referencia": "Referencia",
            "asiento_propuesto_id": "Propuesta contable",
            "estado": "Estado",
            "motivo_anulacion": "Motivo anulación",
        }
    )
    return preparar_vista(vista)


def _selector_capital(capitales: pd.DataFrame, key: str, incluir_todos: bool = False) -> Optional[int]:
    if not _df_no_vacio(capitales):
        return None

    opciones = []
    if incluir_todos:
        opciones.append(("Todos los capitales vigentes", None))

    for _, fila in capitales.iterrows():
        capital_id = int(fila.get("id"))
        descripcion = _texto(fila.get("descripcion"), "Capital social")
        fecha = _fecha(fila.get("fecha_instrumento"))
        total = _moneda(fila.get("capital_social_total"))
        opciones.append((f"{capital_id} - {descripcion} - {fecha} - {total}", capital_id))

    etiqueta = st.selectbox(
        "Capital social",
        [opcion[0] for opcion in opciones],
        key=key,
    )
    for texto, valor in opciones:
        if texto == etiqueta:
            return valor

    return opciones[0][1] if opciones else None


def _selector_pendiente(pendientes: pd.DataFrame, key: str) -> Optional[Dict[str, Any]]:
    if not _df_no_vacio(pendientes):
        return None

    filas = pendientes.to_dict("records")
    opciones = []
    for fila in filas:
        socio = _texto(fila.get("socio_nombre"), f"Socio ID {fila.get('socio_id')}")
        capital_id = fila.get("capital_id")
        pendiente = _moneda(fila.get("importe_pendiente"))
        opciones.append((f"Capital {capital_id} - {socio} - pendiente {pendiente}", fila))

    etiqueta = st.selectbox(
        "Socio con integración pendiente",
        [opcion[0] for opcion in opciones],
        key=key,
    )
    for texto, fila in opciones:
        if texto == etiqueta:
            return fila

    return opciones[0][1] if opciones else None


def _selector_movimiento(movimientos: pd.DataFrame, key: str) -> Optional[Dict[str, Any]]:
    if not _df_no_vacio(movimientos):
        return None

    filas = movimientos.to_dict("records")
    opciones = []
    for fila in filas:
        movimiento_id = fila.get("tesoreria_operacion_id") or fila.get("id")
        fecha = _fecha(fila.get("fecha") or fila.get("fecha_contable") or fila.get("fecha_operacion"))
        cuenta = _texto(fila.get("cuenta_tesoreria_nombre") or fila.get("cuenta_nombre") or fila.get("cuenta_tesoreria_tipo"))
        concepto = _texto(fila.get("concepto") or fila.get("descripcion") or fila.get("referencia"), "Sin concepto")
        importe = _moneda(fila.get("importe"))
        opciones.append((f"{movimiento_id} - {fecha} - {cuenta} - {concepto} - {importe}", fila))

    etiqueta = st.selectbox(
        "Movimiento real disponible de Tesorería",
        [opcion[0] for opcion in opciones],
        key=key,
    )
    for texto, fila in opciones:
        if texto == etiqueta:
            return fila

    return opciones[0][1] if opciones else None


def _mostrar_metricas_resumen(resumen: Dict[str, Any]) -> None:
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Socios activos", int(resumen.get("cantidad_socios") or 0))
    col2.metric("Capital suscripto", _moneda(resumen.get("total_suscripto")))
    col3.metric("Capital integrado", _moneda(resumen.get("total_integrado")))
    col4.metric("Pendiente de integración", _moneda(resumen.get("total_pendiente_integracion")))


def _mostrar_socios(empresa_id: int, preparar_vista, usuario: Optional[str]) -> pd.DataFrame:
    st.markdown("#### Socios / accionistas")

    socios = listar_socios_empresa(empresa_id=empresa_id, incluir_bajas=False)
    if _df_no_vacio(socios):
        st.dataframe(_vista_socios(socios, preparar_vista), use_container_width=True, hide_index=True)
    else:
        st.info("Todavía no hay socios o accionistas cargados para esta empresa.")

    with st.expander("Cargar socio / accionista", expanded=not _df_no_vacio(socios)):
        with st.form("form_inicio_societario_alta_socio"):
            nombre = st.text_input("Nombre o razón social del socio", key="inicio_societario_socio_nombre")
            cuit = st.text_input("CUIT", key="inicio_societario_socio_cuit")
            tipo_socio = st.selectbox(
                "Tipo",
                ["SOCIO", "ACCIONISTA", "SOCIO GERENTE", "APODERADO", "OTRO"],
                key="inicio_societario_socio_tipo",
            )
            porcentaje = st.number_input(
                "% participación informativo",
                min_value=0.0,
                max_value=100.0,
                value=0.0,
                step=0.01,
                key="inicio_societario_socio_porcentaje",
            )
            observaciones = st.text_area("Observaciones", key="inicio_societario_socio_obs")
            guardar = st.form_submit_button("Guardar socio")

        if guardar:
            resultado = crear_socio_empresa(
                empresa_id=empresa_id,
                nombre=nombre,
                cuit=cuit,
                tipo_socio=tipo_socio,
                porcentaje_participacion=porcentaje,
                observaciones=observaciones,
                usuario=usuario,
            )
            if resultado.get("ok"):
                st.success(resultado.get("mensaje", "Socio creado correctamente."))
                _rerun()
            else:
                st.error(resultado.get("mensaje", "No se pudo crear el socio."))

    return socios


def _mostrar_capital_social(empresa_id: int, socios: pd.DataFrame, preparar_vista, usuario: Optional[str]) -> pd.DataFrame:
    st.markdown("#### Capital social suscripto")

    capitales = listar_capital_social_empresa(empresa_id=empresa_id, incluir_anulados=False)
    if _df_no_vacio(capitales):
        st.dataframe(_vista_capitales(capitales, preparar_vista), use_container_width=True, hide_index=True)
    else:
        st.info("Todavía no hay capital social configurado para esta empresa.")

    with st.expander("Configurar capital social inicial", expanded=not _df_no_vacio(capitales)):
        if not _df_no_vacio(socios):
            st.warning("Primero cargá al menos un socio o accionista.")
            return capitales

        ejercicios = _listar_ejercicios_empresa(empresa_id)
        if not _df_no_vacio(ejercicios):
            st.warning("No hay ejercicios contables disponibles para esta empresa. Inicializá la empresa antes de configurar capital social.")
            return capitales

        with st.form("form_inicio_societario_capital_inicial"):
            etiquetas_ejercicios = []
            mapa_ejercicios = {}
            for _, fila in ejercicios.iterrows():
                ejercicio_id = int(fila.get("id"))
                etiqueta = (
                    f"{ejercicio_id} - {_texto(fila.get('nombre'), 'Ejercicio')} "
                    f"({_fecha(fila.get('fecha_inicio'))} a {_fecha(fila.get('fecha_fin'))})"
                )
                etiquetas_ejercicios.append(etiqueta)
                mapa_ejercicios[etiqueta] = ejercicio_id

            ejercicio_sel = st.selectbox("Ejercicio contable", etiquetas_ejercicios, key="inicio_societario_capital_ejercicio")
            fecha_instrumento = st.date_input(
                "Fecha del instrumento / inicio societario",
                value=date.today(),
                format="DD/MM/YYYY",
                key="inicio_societario_capital_fecha",
            )
            descripcion = st.text_input(
                "Descripción",
                value="Capital social inicial",
                key="inicio_societario_capital_descripcion",
            )
            referencia = st.text_input("Referencia / acta / contrato", key="inicio_societario_capital_referencia")
            capital_total = st.number_input(
                "Capital social total",
                min_value=0.0,
                value=0.0,
                step=1000.0,
                key="inicio_societario_capital_total",
            )

            st.caption("Distribución por socio. El total suscripto debe coincidir con el capital social total.")
            socios_payload = []
            cantidad_socios = max(1, len(socios))
            porcentaje_default = round(100.0 / cantidad_socios, 4)

            for _, socio in socios.iterrows():
                socio_id = int(socio.get("id"))
                nombre = _texto(socio.get("nombre"), f"Socio {socio_id}")
                porcentaje_base = _numero(socio.get("porcentaje_participacion"), porcentaje_default) or porcentaje_default

                c1, c2, c3 = st.columns([2, 1, 1])
                c1.write(nombre)
                porcentaje = c2.number_input(
                    f"% {nombre}",
                    min_value=0.0,
                    max_value=100.0,
                    value=float(round(porcentaje_base, 4)),
                    step=0.01,
                    key=f"inicio_societario_capital_pct_{socio_id}",
                )
                suscripto_sugerido = round(_numero(capital_total) * porcentaje / 100, 2) if capital_total else 0.0
                suscripto = c3.number_input(
                    f"Suscripto {nombre}",
                    min_value=0.0,
                    value=float(suscripto_sugerido),
                    step=1000.0,
                    key=f"inicio_societario_capital_suscripto_{socio_id}",
                )
                socios_payload.append(
                    {
                        "socio_id": socio_id,
                        "nombre": nombre,
                        "cuit": socio.get("cuit"),
                        "tipo_socio": socio.get("tipo_socio") or "SOCIO",
                        "porcentaje": porcentaje,
                        "importe_suscripto": suscripto,
                        "importe_integrado": 0.0,
                        "medio_integracion": "PENDIENTE",
                    }
                )

            generar_asiento = st.checkbox(
                "Generar propuesta contable por suscripción inicial",
                value=True,
                key="inicio_societario_capital_generar_asiento",
            )
            guardar = st.form_submit_button("Guardar capital social inicial")

        if guardar:
            resultado = configurar_capital_social_inicial(
                empresa_id=empresa_id,
                ejercicio_id=mapa_ejercicios[ejercicio_sel],
                fecha_instrumento=fecha_instrumento,
                capital_social_total=capital_total,
                socios=socios_payload,
                descripcion=descripcion,
                referencia=referencia,
                usuario=usuario,
                generar_asientos=generar_asiento,
            )
            if resultado.get("ok"):
                st.success(resultado.get("mensaje", "Capital social configurado correctamente."))
                _rerun()
            else:
                st.error(resultado.get("mensaje", "No se pudo configurar el capital social."))

    return capitales


def _mostrar_pendientes(empresa_id: int, capitales: pd.DataFrame, preparar_vista) -> pd.DataFrame:
    st.markdown("#### Integración pendiente por socio")

    capital_id = _selector_capital(capitales, "inicio_societario_pendientes_capital", incluir_todos=True)
    pendientes = listar_pendientes_integracion_por_socio(empresa_id=empresa_id, capital_id=capital_id)

    if _df_no_vacio(pendientes):
        st.dataframe(_vista_pendientes(pendientes, preparar_vista), use_container_width=True, hide_index=True)
    else:
        st.success("No hay saldos pendientes de integración para el capital seleccionado.")

    return pendientes


def _mostrar_integracion_real(empresa_id: int, pendientes: pd.DataFrame, preparar_vista, usuario: Optional[str]) -> None:
    st.markdown("#### Integración real desde Tesorería")

    st.caption(
        "La integración real se vincula con un movimiento disponible de Tesorería. "
        "El mismo movimiento no puede reutilizarse en otra integración."
    )

    movimientos = listar_movimientos_tesoreria_disponibles_para_integracion(empresa_id=empresa_id, limite=200)

    if _df_no_vacio(movimientos):
        with st.expander("Movimientos disponibles de Tesorería", expanded=False):
            st.dataframe(_vista_movimientos_tesoreria(movimientos, preparar_vista), use_container_width=True, hide_index=True)
    else:
        st.info("No hay movimientos de Tesorería disponibles para integrar capital.")

    pendientes_utiles = pendientes.copy() if _df_no_vacio(pendientes) else pd.DataFrame()
    if _df_no_vacio(pendientes_utiles) and "importe_pendiente" in pendientes_utiles.columns:
        pendientes_utiles = pendientes_utiles[pendientes_utiles["importe_pendiente"].astype(float) > 0]

    with st.expander("Registrar integración real", expanded=False):
        if not _df_no_vacio(pendientes_utiles):
            st.warning("No hay socios con integración pendiente.")
            return
        if not _df_no_vacio(movimientos):
            st.warning("No hay movimientos de Tesorería disponibles.")
            return

        with st.form("form_inicio_societario_integracion_real"):
            pendiente = _selector_pendiente(pendientes_utiles, "inicio_societario_integracion_pendiente")
            movimiento = _selector_movimiento(movimientos, "inicio_societario_integracion_movimiento")

            pendiente_importe = _numero((pendiente or {}).get("importe_pendiente"))
            movimiento_importe = _numero((movimiento or {}).get("importe"))
            importe_maximo = min(pendiente_importe, movimiento_importe) if pendiente_importe and movimiento_importe else 0.0

            importe = st.number_input(
                "Importe a integrar",
                min_value=0.0,
                max_value=float(importe_maximo) if importe_maximo > 0 else None,
                value=float(importe_maximo) if importe_maximo > 0 else 0.0,
                step=1000.0,
                key="inicio_societario_integracion_importe",
            )
            fecha_integracion = st.date_input(
                "Fecha de integración",
                value=date.today(),
                format="DD/MM/YYYY",
                key="inicio_societario_integracion_fecha",
            )
            referencia = st.text_input("Referencia", key="inicio_societario_integracion_referencia")
            observaciones = st.text_area("Observaciones", key="inicio_societario_integracion_obs")
            generar_asiento = st.checkbox(
                "Generar propuesta contable a Bandeja",
                value=True,
                key="inicio_societario_integracion_generar_asiento",
            )
            guardar = st.form_submit_button("Registrar integración real")

        if guardar:
            if not pendiente or not movimiento:
                st.error("Debe seleccionarse socio pendiente y movimiento de Tesorería.")
                return

            operacion_id = movimiento.get("tesoreria_operacion_id") or movimiento.get("id")
            resultado = registrar_integracion_capital_desde_tesoreria(
                empresa_id=empresa_id,
                capital_id=int(pendiente.get("capital_id")),
                socio_id=int(pendiente.get("socio_id")),
                tesoreria_operacion_id=int(operacion_id),
                importe=importe,
                fecha_integracion=fecha_integracion,
                referencia=referencia,
                observaciones=observaciones,
                usuario=usuario,
                generar_asiento=generar_asiento,
            )
            if resultado.get("ok"):
                st.success(resultado.get("mensaje", "Integración registrada correctamente."))
                if resultado.get("asiento_propuesto_id"):
                    st.caption(f"Propuesta contable generada: {resultado.get('asiento_propuesto_id')}")
                _rerun()
            else:
                st.error(resultado.get("mensaje", "No se pudo registrar la integración."))


def _mostrar_integraciones_y_anulacion(empresa_id: int, preparar_vista, usuario: Optional[str]) -> None:
    st.markdown("#### Integraciones registradas y anulación controlada")

    integraciones = _listar_integraciones_reales(empresa_id)
    if not _df_no_vacio(integraciones):
        st.info("Todavía no hay integraciones reales registradas.")
        return

    st.dataframe(_vista_integraciones(integraciones, preparar_vista), use_container_width=True, hide_index=True)

    activas = integraciones[integraciones["estado"].astype(str).str.upper() != "ANULADO"].copy() if "estado" in integraciones.columns else integraciones.copy()
    if not _df_no_vacio(activas):
        return

    with st.expander("Anular integración no contabilizada", expanded=False):
        opciones = []
        for _, fila in activas.iterrows():
            integracion_id = int(fila.get("integracion_id"))
            socio = _texto(fila.get("socio_nombre"), "Sin socio")
            fecha = _fecha(fila.get("fecha_integracion"))
            importe = _moneda(fila.get("importe"))
            opciones.append((f"{integracion_id} - {fecha} - {socio} - {importe}", integracion_id))

        etiqueta = st.selectbox(
            "Integración a anular",
            [opcion[0] for opcion in opciones],
            key="inicio_societario_anular_integracion_id",
        )
        integracion_id = next(valor for texto, valor in opciones if texto == etiqueta)
        motivo = st.text_area(
            "Motivo obligatorio",
            key="inicio_societario_anular_integracion_motivo",
        )

        if st.button("Anular integración", type="secondary", key="inicio_societario_anular_integracion_btn"):
            resultado = anular_integracion_capital(
                integracion_id=integracion_id,
                motivo=motivo,
                usuario=usuario,
                anular_asiento_vinculado=True,
            )
            if resultado.get("ok"):
                st.success(resultado.get("mensaje", "Integración anulada correctamente."))
                _rerun()
            else:
                st.error(resultado.get("mensaje", "No se pudo anular la integración."))


def _mostrar_trazabilidad(capitales: pd.DataFrame, preparar_vista) -> None:
    st.markdown("#### Trazabilidad societaria")

    capital_id = _selector_capital(capitales, "inicio_societario_trazabilidad_capital", incluir_todos=False)
    if capital_id is None:
        st.info("No hay capital social disponible para consultar trazabilidad.")
        return

    eventos = listar_eventos_capital(capital_id)
    if not _df_no_vacio(eventos):
        st.info("No hay eventos de trazabilidad para el capital seleccionado.")
        return

    vista = eventos.copy()
    if "fecha_evento" in vista.columns:
        vista["fecha_evento"] = vista["fecha_evento"].map(_fecha)
    renombres = {
        "id": "ID",
        "fecha_evento": "Fecha",
        "evento": "Evento",
        "detalle": "Detalle",
        "usuario": "Usuario",
        "capital_id": "Capital ID",
        "socio_id": "Socio ID",
    }
    vista = vista.rename(columns={k: v for k, v in renombres.items() if k in vista.columns})
    st.dataframe(preparar_vista(vista), use_container_width=True, hide_index=True)


def mostrar_panel_inicio_societario(
    empresa_id: Optional[int] = None,
    perfil: Optional[Dict[str, Any]] = None,
    preparar_vista=None,
    usuario: Optional[str] = None,
) -> None:
    preparar_vista = preparar_vista or _preparar_vista_default
    usuario = _usuario_actual(usuario)
    empresa_id_resuelto = _empresa_id_desde_perfil(perfil=perfil, empresa_id=empresa_id)

    st.divider()
    st.subheader("Inicio societario PRO")

    st.caption(
        "Panel operativo independiente para socios, capital suscripto, integración pendiente, "
        "integraciones reales desde Tesorería y trazabilidad. No registra movimientos directos en Caja/Banco "
        "ni impacta el Libro Diario sin pasar por Bandeja."
    )

    if empresa_id_resuelto is None:
        st.warning("No se pudo identificar la empresa activa para mostrar el panel societario.")
        return

    try:
        resumen = obtener_resumen_capital_socios(empresa_id=empresa_id_resuelto)
        socios = listar_socios_empresa(empresa_id=empresa_id_resuelto, incluir_bajas=False)
        capitales = listar_capital_social_empresa(empresa_id=empresa_id_resuelto, incluir_anulados=False)
        pendientes = listar_pendientes_integracion_por_socio(empresa_id=empresa_id_resuelto)
    except Exception as exc:
        st.error("No se pudo cargar el panel societario.")
        st.exception(exc)
        return

    _mostrar_metricas_resumen(resumen)

    tab_resumen, tab_socios, tab_capital, tab_integraciones, tab_trazabilidad = st.tabs(
        [
            "Resumen",
            "Socios",
            "Capital social",
            "Integraciones reales",
            "Trazabilidad",
        ]
    )

    with tab_resumen:
        st.markdown("#### Estado societario")
        if int(resumen.get("cantidad_socios") or 0) == 0:
            st.warning("Falta cargar socios o accionistas.")
        elif int(resumen.get("cantidad_capitales") or 0) == 0:
            st.warning("Falta configurar capital social inicial.")
        elif _numero(resumen.get("total_pendiente_integracion")) > 0:
            st.info("Hay capital pendiente de integración por socio.")
        else:
            st.success("El capital social no registra pendientes de integración.")

        if _df_no_vacio(pendientes):
            st.dataframe(_vista_pendientes(pendientes, preparar_vista), use_container_width=True, hide_index=True)

    with tab_socios:
        socios = _mostrar_socios(empresa_id_resuelto, preparar_vista, usuario)

    with tab_capital:
        capitales = _mostrar_capital_social(empresa_id_resuelto, socios, preparar_vista, usuario)

    with tab_integraciones:
        pendientes = _mostrar_pendientes(empresa_id_resuelto, capitales, preparar_vista)
        _mostrar_integracion_real(empresa_id_resuelto, pendientes, preparar_vista, usuario)
        _mostrar_integraciones_y_anulacion(empresa_id_resuelto, preparar_vista, usuario)

    with tab_trazabilidad:
        _mostrar_trazabilidad(capitales, preparar_vista)