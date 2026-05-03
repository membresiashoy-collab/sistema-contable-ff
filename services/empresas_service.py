import re
import unicodedata

import pandas as pd

from database import ejecutar_query


# ======================================================
# SERVICIO DE EMPRESAS
# ======================================================
# Este servicio NO reemplaza a seguridad_service.py.
#
# seguridad_service.py:
# - crea empresas
# - edita empresas
# - valida duplicados
# - activa / desactiva
# - elimina si está vacía
#
# empresas_service.py:
# - diagnostica si una empresa está lista para operar
# - inicializa datos base seguros
# - informa faltantes por empresa
# - centraliza validaciones operativas reutilizables
#
# Importante:
# - No borra datos.
# - No modifica movimientos.
# - No toca Caja/Cobranzas/Pagos/Conciliación.
# - Se puede ejecutar varias veces.
# ======================================================


# ======================================================
# UTILIDADES GENERALES
# ======================================================

def _texto(valor):
    if valor is None:
        return ""

    try:
        if pd.isna(valor):
            return ""
    except Exception:
        pass

    return str(valor).strip()


def _entero(valor, default=0):
    try:
        if valor is None or pd.isna(valor):
            return default
    except Exception:
        if valor is None:
            return default

    try:
        return int(valor)
    except Exception:
        return default


def _numero(valor, default=0.0):
    try:
        if valor is None or pd.isna(valor):
            return default
    except Exception:
        if valor is None:
            return default

    try:
        return float(valor)
    except Exception:
        return default


def _bool_activo(valor):
    return _entero(valor, 0) == 1


def _normalizar_clave(valor):
    texto = _texto(valor)

    if not texto:
        return ""

    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"\s+", " ", texto)
    texto = texto.upper().strip()

    return texto


def normalizar_cuit(cuit):
    return re.sub(r"\D+", "", _texto(cuit))


def _respuesta(ok, mensaje, **datos):
    resultado = {
        "ok": bool(ok),
        "mensaje": mensaje,
    }
    resultado.update(datos)
    return resultado


def _identificador_sql_seguro(nombre):
    return bool(re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", _texto(nombre)))


def _tabla_existe(tabla):
    if not _identificador_sql_seguro(tabla):
        return False

    df = ejecutar_query("""
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
    """, (tabla,), fetch=True)

    return not df.empty


def _columnas_tabla(tabla):
    if not _identificador_sql_seguro(tabla):
        return []

    if not _tabla_existe(tabla):
        return []

    try:
        df = ejecutar_query(f"PRAGMA table_info({tabla})", fetch=True)
    except Exception:
        return []

    if df.empty or "name" not in df.columns:
        return []

    return df["name"].astype(str).tolist()


def _tabla_tiene_columna(tabla, columna):
    return _texto(columna) in _columnas_tabla(tabla)


def _contar_tabla(tabla):
    if not _identificador_sql_seguro(tabla):
        return 0

    if not _tabla_existe(tabla):
        return 0

    try:
        df = ejecutar_query(f"SELECT COUNT(*) AS cantidad FROM {tabla}", fetch=True)
    except Exception:
        return 0

    if df.empty or "cantidad" not in df.columns:
        return 0

    return _entero(df.iloc[0]["cantidad"], 0)


def _contar_tabla_empresa(tabla, empresa_id):
    if not _identificador_sql_seguro(tabla):
        return 0

    if not _tabla_existe(tabla):
        return 0

    if not _tabla_tiene_columna(tabla, "empresa_id"):
        return 0

    try:
        df = ejecutar_query(
            f"SELECT COUNT(*) AS cantidad FROM {tabla} WHERE empresa_id = ?",
            (int(empresa_id),),
            fetch=True,
        )
    except Exception:
        return 0

    if df.empty or "cantidad" not in df.columns:
        return 0

    return _entero(df.iloc[0]["cantidad"], 0)


def _contar_tabla_activos(tabla, empresa_id=None):
    if not _identificador_sql_seguro(tabla):
        return 0

    if not _tabla_existe(tabla):
        return 0

    condiciones = []
    params = []

    if _tabla_tiene_columna(tabla, "activo"):
        condiciones.append("activo = 1")

    if empresa_id is not None and _tabla_tiene_columna(tabla, "empresa_id"):
        condiciones.append("empresa_id = ?")
        params.append(int(empresa_id))

    where = ""
    if condiciones:
        where = "WHERE " + " AND ".join(condiciones)

    try:
        df = ejecutar_query(
            f"SELECT COUNT(*) AS cantidad FROM {tabla} {where}",
            tuple(params),
            fetch=True,
        )
    except Exception:
        return 0

    if df.empty or "cantidad" not in df.columns:
        return 0

    return _entero(df.iloc[0]["cantidad"], 0)


def _leer_tabla(tabla, columnas="*", where="", params=(), order_by=""):
    if not _identificador_sql_seguro(tabla):
        return pd.DataFrame()

    if not _tabla_existe(tabla):
        return pd.DataFrame()

    sql = f"SELECT {columnas} FROM {tabla}"

    if where:
        sql += f" WHERE {where}"

    if order_by:
        sql += f" ORDER BY {order_by}"

    try:
        return ejecutar_query(sql, params, fetch=True)
    except Exception:
        return pd.DataFrame()


# ======================================================
# EMPRESA
# ======================================================

def obtener_empresa(empresa_id, solo_activa=False):
    """
    Devuelve una empresa por ID.
    """

    if empresa_id is None:
        return None

    if not _tabla_existe("empresas"):
        return None

    where = "id = ?"
    params = [int(empresa_id)]

    if solo_activa and _tabla_tiene_columna("empresas", "activo"):
        where += " AND activo = 1"

    df = _leer_tabla(
        "empresas",
        columnas="*",
        where=where,
        params=tuple(params),
    )

    if df.empty:
        return None

    return df.iloc[0].to_dict()


def obtener_empresas_activas():
    """
    Lista empresas activas.
    """

    if not _tabla_existe("empresas"):
        return pd.DataFrame()

    columnas = _columnas_tabla("empresas")
    order_by = "nombre" if "nombre" in columnas else "id"

    if "activo" in columnas:
        return _leer_tabla(
            "empresas",
            columnas="*",
            where="activo = 1",
            order_by=order_by,
        )

    return _leer_tabla(
        "empresas",
        columnas="*",
        order_by=order_by,
    )


def empresa_esta_activa(empresa_id):
    empresa = obtener_empresa(empresa_id)

    if not empresa:
        return False

    if "activo" not in empresa:
        return True

    return _bool_activo(empresa.get("activo"))


def validar_empresa_basica(empresa):
    """
    Valida datos mínimos para que una empresa pueda operar.
    No valida duplicados; eso corresponde a seguridad_service.py.
    """

    if not empresa:
        return _respuesta(False, "La empresa no existe.")

    faltantes = []

    nombre = _texto(empresa.get("nombre"))
    cuit = normalizar_cuit(empresa.get("cuit"))
    razon_social = _texto(empresa.get("razon_social"))
    domicilio = _texto(empresa.get("domicilio"))
    actividad = _texto(empresa.get("actividad"))

    if not nombre:
        faltantes.append("nombre interno")

    if not cuit:
        faltantes.append("CUIT")

    if cuit and len(cuit) != 11:
        faltantes.append("CUIT válido de 11 dígitos")

    if not razon_social:
        faltantes.append("razón social")

    if not domicilio:
        faltantes.append("domicilio")

    if not actividad:
        faltantes.append("actividad")

    if faltantes:
        return _respuesta(
            False,
            "Faltan datos mínimos de empresa: " + ", ".join(faltantes) + ".",
            faltantes=faltantes,
        )

    if "activo" in empresa and not _bool_activo(empresa.get("activo")):
        return _respuesta(
            False,
            "La empresa está inactiva. Debe reactivarse desde Seguridad antes de operar.",
            faltantes=["empresa activa"],
        )

    return _respuesta(True, "La empresa tiene los datos mínimos para operar.", faltantes=[])


# ======================================================
# DIAGNÓSTICOS DE DATOS BASE
# ======================================================

def diagnosticar_plan_cuentas():
    """
    Diagnostica plan de cuentas global/base.
    Actualmente el plan de cuentas del sistema es base común.
    """

    total_simple = _contar_tabla("plan_cuentas")
    total_detallado = _contar_tabla("plan_cuentas_detallado")

    ok = total_simple > 0 and total_detallado > 0

    return {
        "codigo": "PLAN_CUENTAS",
        "area": "Contabilidad",
        "control": "Plan de cuentas base",
        "estado": "OK" if ok else "FALTA",
        "ok": ok,
        "critico": True,
        "cantidad": total_detallado,
        "detalle": (
            f"Plan detallado: {total_detallado} cuentas. "
            f"Plan simple: {total_simple} cuentas."
        ),
        "recomendacion": (
            "Correcto."
            if ok
            else "Inicializar datos base para cargar el plan de cuentas."
        ),
    }


def diagnosticar_tipos_comprobantes():
    total = _contar_tabla("tipos_comprobantes")
    ok = total > 0

    return {
        "codigo": "TIPOS_COMPROBANTES",
        "area": "Comprobantes",
        "control": "Tipos de comprobantes ARCA/AFIP",
        "estado": "OK" if ok else "FALTA",
        "ok": ok,
        "critico": True,
        "cantidad": total,
        "detalle": f"Tipos de comprobantes cargados: {total}.",
        "recomendacion": (
            "Correcto."
            if ok
            else "Inicializar datos base para cargar tipos de comprobantes."
        ),
    }


def diagnosticar_categorias_compra(empresa_id=None):
    """
    Diagnostica categorías de compra.
    Por compatibilidad actual, las categorías pueden estar como catálogo global.
    """

    total_global = _contar_tabla_activos("categorias_compra")
    total_empresa = 0

    if empresa_id is not None and _tabla_tiene_columna("categorias_compra", "empresa_id"):
        total_empresa = _contar_tabla_activos("categorias_compra", empresa_id=empresa_id)

    ok = total_global > 0

    return {
        "codigo": "CATEGORIAS_COMPRA",
        "area": "Compras",
        "control": "Categorías de compra",
        "estado": "OK" if ok else "FALTA",
        "ok": ok,
        "critico": True,
        "cantidad": total_global,
        "cantidad_empresa": total_empresa,
        "detalle": (
            f"Categorías activas disponibles: {total_global}. "
            f"Categorías propias de empresa: {total_empresa}."
        ),
        "recomendacion": (
            "Correcto."
            if ok
            else "Inicializar datos base para cargar categorías de compra."
        ),
    }


def diagnosticar_conceptos_fiscales_compra(empresa_id=None):
    """
    Diagnostica conceptos fiscales de compra.
    Por compatibilidad actual, pueden estar como catálogo global.
    """

    total_global = _contar_tabla_activos("conceptos_fiscales_compra")
    total_empresa = 0

    if empresa_id is not None and _tabla_tiene_columna("conceptos_fiscales_compra", "empresa_id"):
        total_empresa = _contar_tabla_activos("conceptos_fiscales_compra", empresa_id=empresa_id)

    ok = total_global > 0

    return {
        "codigo": "CONCEPTOS_FISCALES_COMPRA",
        "area": "Compras / IVA",
        "control": "Conceptos fiscales de compra",
        "estado": "OK" if ok else "FALTA",
        "ok": ok,
        "critico": True,
        "cantidad": total_global,
        "cantidad_empresa": total_empresa,
        "detalle": (
            f"Conceptos fiscales activos disponibles: {total_global}. "
            f"Conceptos propios de empresa: {total_empresa}."
        ),
        "recomendacion": (
            "Correcto."
            if ok
            else "Inicializar datos base para cargar conceptos fiscales de compra."
        ),
    }


def diagnosticar_actividades(empresa_id):
    """
    Diagnostica actividad base.
    No bloquea si no hay empresas_actividades, porque la empresa también tiene campo actividad.
    """

    empresa = obtener_empresa(empresa_id)
    actividad_texto = _texto((empresa or {}).get("actividad"))
    total_catalogo = _contar_tabla_activos("actividades_arca")
    total_asignadas = 0

    if _tabla_existe("empresas_actividades") and _tabla_tiene_columna("empresas_actividades", "empresa_id"):
        total_asignadas = _contar_tabla_activos("empresas_actividades", empresa_id=empresa_id)

    ok = bool(actividad_texto) or total_asignadas > 0

    return {
        "codigo": "ACTIVIDAD_EMPRESA",
        "area": "Empresa",
        "control": "Actividad económica",
        "estado": "OK" if ok else "REVISAR",
        "ok": ok,
        "critico": False,
        "cantidad": total_asignadas,
        "cantidad_catalogo": total_catalogo,
        "detalle": (
            f"Actividad declarada en empresa: {actividad_texto or 'sin informar'}. "
            f"Actividades asignadas: {total_asignadas}. "
            f"Catálogo ARCA disponible: {total_catalogo}."
        ),
        "recomendacion": (
            "Correcto."
            if ok
            else "Informar actividad en la empresa o asignar una actividad desde Configuración."
        ),
    }


def diagnosticar_tesoreria(empresa_id):
    """
    Diagnóstico operativo de Tesorería.
    No crea nada; solo informa si hay estructuras y datos básicos.
    """

    cuentas = 0
    medios = 0

    for tabla in ["cuentas_tesoreria", "tesoreria_cuentas"]:
        if _tabla_existe(tabla):
            if _tabla_tiene_columna(tabla, "empresa_id"):
                cuentas = max(cuentas, _contar_tabla_activos(tabla, empresa_id=empresa_id))
            else:
                cuentas = max(cuentas, _contar_tabla_activos(tabla))

    for tabla in ["medios_pago", "tesoreria_medios_pago"]:
        if _tabla_existe(tabla):
            if _tabla_tiene_columna(tabla, "empresa_id"):
                medios = max(medios, _contar_tabla_activos(tabla, empresa_id=empresa_id))
            else:
                medios = max(medios, _contar_tabla_activos(tabla))

    ok = cuentas > 0 and medios > 0

    return {
        "codigo": "TESORERIA_BASE",
        "area": "Tesorería",
        "control": "Cuentas y medios de pago",
        "estado": "OK" if ok else "REVISAR",
        "ok": ok,
        "critico": False,
        "cantidad": cuentas,
        "cantidad_medios": medios,
        "detalle": (
            f"Cuentas de tesorería detectadas: {cuentas}. "
            f"Medios de pago detectados: {medios}."
        ),
        "recomendacion": (
            "Correcto."
            if ok
            else "Inicializar o revisar cuentas de tesorería y medios de pago para la empresa."
        ),
    }


def diagnosticar_caja(empresa_id):
    """
    Diagnóstico informativo de Caja.
    No modifica caja visual ni movimientos.
    """

    cajas = 0

    for tabla in ["cajas", "caja_cuentas"]:
        if _tabla_existe(tabla):
            if _tabla_tiene_columna(tabla, "empresa_id"):
                cajas = max(cajas, _contar_tabla_activos(tabla, empresa_id=empresa_id))
            else:
                cajas = max(cajas, _contar_tabla_activos(tabla))

    ok = cajas > 0

    return {
        "codigo": "CAJA_BASE",
        "area": "Caja",
        "control": "Cajas configuradas",
        "estado": "OK" if ok else "REVISAR",
        "ok": ok,
        "critico": False,
        "cantidad": cajas,
        "detalle": f"Cajas activas detectadas: {cajas}.",
        "recomendacion": (
            "Correcto."
            if ok
            else "Crear o inicializar una caja para registrar operaciones en efectivo."
        ),
    }


def diagnosticar_bancos(empresa_id):
    """
    Diagnóstico informativo de cuentas bancarias.
    """

    cuentas_bancarias = 0

    for tabla in ["cuentas_bancarias", "bancos_cuentas", "bancos_configuracion_cuentas"]:
        if _tabla_existe(tabla):
            if _tabla_tiene_columna(tabla, "empresa_id"):
                cuentas_bancarias = max(
                    cuentas_bancarias,
                    _contar_tabla_activos(tabla, empresa_id=empresa_id),
                )
            else:
                cuentas_bancarias = max(cuentas_bancarias, _contar_tabla_activos(tabla))

    ok = cuentas_bancarias > 0

    return {
        "codigo": "BANCOS_BASE",
        "area": "Banco",
        "control": "Cuentas bancarias configuradas",
        "estado": "OK" if ok else "REVISAR",
        "ok": ok,
        "critico": False,
        "cantidad": cuentas_bancarias,
        "detalle": f"Cuentas bancarias activas detectadas: {cuentas_bancarias}.",
        "recomendacion": (
            "Correcto."
            if ok
            else "Configurar cuenta bancaria si la empresa va a operar con extractos o transferencias."
        ),
    }


# ======================================================
# DIAGNÓSTICO INTEGRAL
# ======================================================

def obtener_diagnostico_empresa(empresa_id):
    """
    Devuelve un diagnóstico integral de preparación operativa.
    """

    empresa = obtener_empresa(empresa_id)

    controles = []

    validacion_empresa = validar_empresa_basica(empresa)

    controles.append({
        "codigo": "DATOS_EMPRESA",
        "area": "Empresa",
        "control": "Datos mínimos de empresa",
        "estado": "OK" if validacion_empresa.get("ok") else "FALTA",
        "ok": bool(validacion_empresa.get("ok")),
        "critico": True,
        "cantidad": 1 if validacion_empresa.get("ok") else 0,
        "detalle": validacion_empresa.get("mensaje", ""),
        "recomendacion": (
            "Correcto."
            if validacion_empresa.get("ok")
            else "Completar datos desde Seguridad: nombre, CUIT, razón social, domicilio y actividad."
        ),
    })

    controles.append(diagnosticar_tipos_comprobantes())
    controles.append(diagnosticar_plan_cuentas())
    controles.append(diagnosticar_categorias_compra(empresa_id=empresa_id))
    controles.append(diagnosticar_conceptos_fiscales_compra(empresa_id=empresa_id))
    controles.append(diagnosticar_actividades(empresa_id=empresa_id))
    controles.append(diagnosticar_tesoreria(empresa_id=empresa_id))
    controles.append(diagnosticar_caja(empresa_id=empresa_id))
    controles.append(diagnosticar_bancos(empresa_id=empresa_id))

    df = pd.DataFrame(controles)

    if df.empty:
        criticos_ok = False
        advertencias = 0
        faltantes_criticos = 0
        porcentaje = 0
    else:
        criticos = df[df["critico"].astype(bool)].copy()
        faltantes_criticos = int((~criticos["ok"].astype(bool)).sum()) if not criticos.empty else 0
        criticos_ok = faltantes_criticos == 0
        advertencias = int((~df["ok"].astype(bool)).sum())
        porcentaje = round((int(df["ok"].astype(bool).sum()) / len(df)) * 100, 2)

    return {
        "ok": criticos_ok,
        "empresa": empresa,
        "empresa_id": int(empresa_id) if empresa_id is not None else None,
        "porcentaje_preparacion": porcentaje,
        "faltantes_criticos": faltantes_criticos,
        "advertencias": advertencias,
        "controles": df,
        "mensaje": (
            "La empresa tiene la base crítica para operar."
            if criticos_ok
            else "La empresa todavía tiene faltantes críticos antes de operar."
        ),
    }


def obtener_controles_empresa_df(empresa_id):
    diagnostico = obtener_diagnostico_empresa(empresa_id)
    return diagnostico.get("controles", pd.DataFrame())


def empresa_lista_para_operar(empresa_id):
    diagnostico = obtener_diagnostico_empresa(empresa_id)
    return bool(diagnostico.get("ok"))


def obtener_resumen_empresa_operativa(empresa_id):
    """
    Resumen compacto para UI.
    """

    diagnostico = obtener_diagnostico_empresa(empresa_id)
    empresa = diagnostico.get("empresa") or {}

    return {
        "empresa_id": diagnostico.get("empresa_id"),
        "nombre": _texto(empresa.get("nombre")),
        "cuit": normalizar_cuit(empresa.get("cuit")),
        "razon_social": _texto(empresa.get("razon_social")),
        "activa": _bool_activo(empresa.get("activo", 1)),
        "lista_para_operar": bool(diagnostico.get("ok")),
        "porcentaje_preparacion": diagnostico.get("porcentaje_preparacion", 0),
        "faltantes_criticos": diagnostico.get("faltantes_criticos", 0),
        "advertencias": diagnostico.get("advertencias", 0),
        "mensaje": diagnostico.get("mensaje", ""),
    }


# ======================================================
# INICIALIZACIÓN SEGURA DE EMPRESA
# ======================================================

def _ejecutar_paso_seguro(nombre, funcion, *args, **kwargs):
    try:
        resultado = funcion(*args, **kwargs)

        return {
            "paso": nombre,
            "ok": True,
            "mensaje": "Ejecutado correctamente.",
            "resultado": resultado,
        }

    except Exception as e:
        return {
            "paso": nombre,
            "ok": False,
            "mensaje": str(e),
            "resultado": None,
        }


def inicializar_datos_base_empresa(empresa_id):
    """
    Inicializa catálogos generales necesarios para que una empresa opere.
    No borra datos.
    """

    empresa = obtener_empresa(empresa_id)

    if not empresa:
        return _respuesta(False, "La empresa no existe.")

    pasos = []

    try:
        from services.datos_base_service import inicializar_datos_base

        pasos.append(
            _ejecutar_paso_seguro(
                "Datos base generales",
                inicializar_datos_base,
            )
        )
    except Exception as e:
        pasos.append({
            "paso": "Datos base generales",
            "ok": False,
            "mensaje": f"No se pudo importar datos_base_service: {e}",
            "resultado": None,
        })

    return _respuesta(
        all(p["ok"] for p in pasos),
        "Inicialización de datos base procesada.",
        pasos=pasos,
        diagnostico=obtener_diagnostico_empresa(empresa_id),
    )


def inicializar_tesoreria_empresa(empresa_id):
    """
    Inicializa componentes básicos relacionados con Tesorería/Banco/Caja,
    usando servicios existentes cuando están disponibles.
    No modifica movimientos.
    """

    empresa = obtener_empresa(empresa_id)

    if not empresa:
        return _respuesta(False, "La empresa no existe.")

    pasos = []

    try:
        from services.tesoreria_service import asegurar_medios_pago_basicos

        pasos.append(
            _ejecutar_paso_seguro(
                "Medios de pago básicos",
                asegurar_medios_pago_basicos,
                empresa_id=int(empresa_id),
            )
        )
    except Exception as e:
        pasos.append({
            "paso": "Medios de pago básicos",
            "ok": False,
            "mensaje": f"No se pudo ejecutar tesoreria_service.asegurar_medios_pago_basicos: {e}",
            "resultado": None,
        })

    try:
        from services.bancos_service import asegurar_cuentas_bancarias_recomendadas

        pasos.append(
            _ejecutar_paso_seguro(
                "Cuentas bancarias recomendadas",
                asegurar_cuentas_bancarias_recomendadas,
                empresa_id=int(empresa_id),
            )
        )
    except Exception as e:
        pasos.append({
            "paso": "Cuentas bancarias recomendadas",
            "ok": False,
            "mensaje": f"No se pudo ejecutar bancos_service.asegurar_cuentas_bancarias_recomendadas: {e}",
            "resultado": None,
        })

    try:
        from services.bancos_service import crear_configuracion_contable_default

        pasos.append(
            _ejecutar_paso_seguro(
                "Configuración contable bancaria default",
                crear_configuracion_contable_default,
                empresa_id=int(empresa_id),
            )
        )
    except Exception as e:
        pasos.append({
            "paso": "Configuración contable bancaria default",
            "ok": False,
            "mensaje": f"No se pudo ejecutar bancos_service.crear_configuracion_contable_default: {e}",
            "resultado": None,
        })

    return _respuesta(
        all(p["ok"] for p in pasos),
        "Inicialización de Tesorería/Banco procesada.",
        pasos=pasos,
        diagnostico=obtener_diagnostico_empresa(empresa_id),
    )


def inicializar_empresa_operativa(empresa_id, incluir_tesoreria=True):
    """
    Inicialización integral segura de empresa.

    No borra datos.
    No toca movimientos.
    No concilia.
    No imputa.
    No modifica ventas/compras/caja existentes.
    """

    empresa = obtener_empresa(empresa_id)

    if not empresa:
        return _respuesta(False, "La empresa no existe.")

    if not _bool_activo(empresa.get("activo", 1)):
        return _respuesta(
            False,
            "La empresa está inactiva. Debe reactivarse antes de inicializarla como operativa.",
        )

    validacion = validar_empresa_basica(empresa)

    if not validacion.get("ok"):
        return _respuesta(
            False,
            "La empresa no tiene datos mínimos completos.",
            detalle=validacion,
            diagnostico=obtener_diagnostico_empresa(empresa_id),
        )

    pasos = []

    resultado_datos_base = inicializar_datos_base_empresa(empresa_id)
    pasos.extend(resultado_datos_base.get("pasos", []))

    if incluir_tesoreria:
        resultado_tesoreria = inicializar_tesoreria_empresa(empresa_id)
        pasos.extend(resultado_tesoreria.get("pasos", []))

    diagnostico = obtener_diagnostico_empresa(empresa_id)

    return _respuesta(
        bool(diagnostico.get("ok")),
        (
            "Empresa inicializada y lista para operar."
            if diagnostico.get("ok")
            else "Empresa inicializada parcialmente. Revisar faltantes antes de operar."
        ),
        empresa_id=int(empresa_id),
        pasos=pasos,
        diagnostico=diagnostico,
    )


# ======================================================
# FORMATEO PARA UI
# ======================================================

def preparar_controles_empresa_para_vista(empresa_id):
    """
    Devuelve DataFrame listo para mostrar en Streamlit.
    """

    df = obtener_controles_empresa_df(empresa_id)

    if df.empty:
        return df

    vista = df.copy()

    columnas = [
        "area",
        "control",
        "estado",
        "critico",
        "cantidad",
        "detalle",
        "recomendacion",
    ]

    columnas = [c for c in columnas if c in vista.columns]

    return vista[columnas].rename(columns={
        "area": "Área",
        "control": "Control",
        "estado": "Estado",
        "critico": "Crítico",
        "cantidad": "Cantidad",
        "detalle": "Detalle",
        "recomendacion": "Recomendación",
    })


def obtener_recomendaciones_empresa(empresa_id):
    df = obtener_controles_empresa_df(empresa_id)

    if df.empty:
        return []

    pendientes = df[df["ok"].astype(bool) == False].copy()

    if pendientes.empty:
        return ["La empresa no tiene faltantes detectados en el diagnóstico actual."]

    recomendaciones = []

    for _, fila in pendientes.iterrows():
        recomendaciones.append(
            f"{_texto(fila.get('area'))} / {_texto(fila.get('control'))}: "
            f"{_texto(fila.get('recomendacion'))}"
        )

    return recomendaciones