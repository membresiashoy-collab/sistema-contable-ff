from io import BytesIO
import unicodedata

import pandas as pd

from database import ejecutar_query


try:
    from services.iva_movimientos_fiscales_service import (
        asegurar_estructura_iva_movimientos_fiscales as _asegurar_movimientos_fiscales,
        listar_movimientos_fiscales as _listar_movimientos_fiscales,
        obtener_impacto_posicion_iva_periodo as _obtener_impacto_movimientos_fiscales,
        obtener_resumen_movimientos_fiscales_por_origen as _obtener_resumen_movimientos_fiscales_origen,
    )
except Exception:
    _asegurar_movimientos_fiscales = None
    _listar_movimientos_fiscales = None
    _obtener_impacto_movimientos_fiscales = None
    _obtener_resumen_movimientos_fiscales_origen = None


# ======================================================
# MÓDULO IVA PRO - SERVICIO BASE
# Etapa 1: Posición mensual IVA
# Etapa 2: Integración de movimientos fiscales adicionales
# ======================================================
#
# Criterio de diseño:
# - Este servicio NO modifica Ventas.
# - Este servicio NO modifica Compras.
# - Este servicio NO modifica Banco/Caja ni Conciliación.
# - Lee información fiscal ya persistida.
# - Calcula una posición mensual IVA confiable.
# - Integra movimientos fiscales adicionales CONFIRMADOS.
#
# Orígenes actuales:
# - VENTAS
# - COMPRAS
# - MOVIMIENTOS_FISCALES
#
# Orígenes posibles dentro de movimientos fiscales:
# - BANCO
# - MANUAL
# - TARJETA
# - ACREDITADORA
# - RETENCION
# - PERCEPCION
# - SALDO_ANTERIOR
# - AJUSTE_TECNICO


# ======================================================
# CONSTANTES
# ======================================================

ORIGEN_VENTAS = "VENTAS"
ORIGEN_COMPRAS = "COMPRAS"
ORIGEN_MOVIMIENTOS_FISCALES = "MOVIMIENTOS_FISCALES"
ORIGEN_BANCO = "BANCO"
ORIGEN_AJUSTE_MANUAL = "AJUSTE_MANUAL"

TOLERANCIA_IMPORTES = 0.05

CODIGOS_NOTAS_CREDITO = {
    "3", "8", "13", "53",
    "203", "208", "213",
    "003", "008", "013", "053",
    "0203", "0208", "0213",
}

CODIGOS_NOTAS_DEBITO = {
    "2", "7", "12", "52",
    "202", "207", "212",
    "002", "007", "012", "052",
    "0202", "0207", "0212",
}

COLUMNAS_POSICION = [
    "empresa_id",
    "anio",
    "mes",
    "periodo",

    "neto_ventas",
    "iva_debito_fiscal_ventas",
    "total_ventas",

    "neto_compras",
    "iva_total_compras",
    "credito_fiscal_computable_compras",
    "iva_no_computable_compras",
    "percepciones_iva_compras",
    "percepciones_iibb_compras_informativas",
    "total_compras",

    "neto_movimientos_fiscales",
    "iva_debito_adicional",
    "credito_fiscal_computable_adicional",
    "iva_no_computable_adicional",
    "percepciones_iva_adicionales",
    "retenciones_iva_sufridas",
    "percepciones_iibb_adicionales_informativas",
    "saldo_tecnico_anterior",
    "saldo_libre_disponibilidad",
    "pago_a_cuenta",
    "otros_tributos_adicionales",
    "total_movimientos_fiscales",

    "iva_debito_fiscal",
    "credito_fiscal_computable",
    "iva_no_computable",
    "percepciones_iva",
    "percepciones_iibb_informativas",

    "saldo_tecnico_iva",
    "percepciones_iva_sufridas",
    "saldo_preliminar_periodo",

    "cantidad_ventas",
    "cantidad_compras",
    "cantidad_movimientos_fiscales",
]


# ======================================================
# HELPERS GENERALES
# ======================================================

def _float(valor, default=0.0):
    try:
        if valor is None:
            return default

        if isinstance(valor, str):
            texto = valor.strip()
            if texto == "":
                return default

            # Soporta formatos simples con coma decimal.
            texto = texto.replace(".", "").replace(",", ".") if "," in texto else texto
            return float(texto)

        return float(valor)
    except Exception:
        return default


def _int(valor, default=0):
    try:
        if valor is None:
            return default
        if isinstance(valor, str) and valor.strip() == "":
            return default
        return int(float(valor))
    except Exception:
        return default


def _round2(valor):
    return round(_float(valor), 2)


def _texto(valor, default=""):
    try:
        if valor is None:
            return default
        return str(valor).strip()
    except Exception:
        return default


def _normalizar_texto(valor):
    texto = _texto(valor).upper()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = " ".join(texto.split())
    return texto


def _normalizar_codigo(valor):
    codigo = _texto(valor)

    if codigo == "":
        return ""

    try:
        return str(int(float(codigo)))
    except Exception:
        return codigo.strip().upper()


def _periodo_texto(anio, mes):
    anio = _int(anio)
    mes = _int(mes)

    if anio <= 0 or mes <= 0:
        return ""

    return f"{anio}-{mes:02d}"


def _resultado_a_dataframe(resultado):
    if isinstance(resultado, pd.DataFrame):
        return resultado.copy()

    if resultado is None:
        return pd.DataFrame()

    try:
        return pd.DataFrame(resultado)
    except Exception:
        return pd.DataFrame()


def _nombre_tabla_seguro(nombre_tabla):
    nombre = _texto(nombre_tabla)

    if not nombre:
        raise ValueError("Nombre de tabla vacío.")

    permitido = all(c.isalnum() or c == "_" for c in nombre)

    if not permitido:
        raise ValueError(f"Nombre de tabla inválido: {nombre}")

    return nombre


def _tabla_existe(nombre_tabla):
    nombre_tabla = _nombre_tabla_seguro(nombre_tabla)

    try:
        df = ejecutar_query(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name = ?
            """,
            (nombre_tabla,),
            fetch=True,
        )
        df = _resultado_a_dataframe(df)
        return not df.empty
    except Exception:
        return False


def _obtener_columnas_tabla(nombre_tabla):
    nombre_tabla = _nombre_tabla_seguro(nombre_tabla)

    if not _tabla_existe(nombre_tabla):
        return set()

    try:
        df = ejecutar_query(f"PRAGMA table_info({nombre_tabla})", fetch=True)
        df = _resultado_a_dataframe(df)

        if df.empty or "name" not in df.columns:
            return set()

        return set(df["name"].astype(str).tolist())
    except Exception:
        return set()


def _serie_numerica(df, columna, default=0.0):
    if df is None:
        return pd.Series(dtype=float)

    if df.empty or columna not in df.columns:
        return pd.Series([default] * len(df), index=df.index)

    return df[columna].apply(lambda x: _float(x, default))


def _primer_importe_no_cero(fila, columnas):
    for columna in columnas:
        if columna in fila.index:
            valor = _float(fila.get(columna, 0))
            if abs(valor) > TOLERANCIA_IMPORTES:
                return valor

    return 0.0


def _asegurar_columnas_periodo(df):
    if df.empty:
        return df

    df = df.copy()

    if "anio" not in df.columns:
        df["anio"] = 0

    if "mes" not in df.columns:
        df["mes"] = 0

    df["anio"] = df["anio"].apply(_int)
    df["mes"] = df["mes"].apply(_int)

    if "fecha" in df.columns:
        fechas = pd.to_datetime(df["fecha"], errors="coerce", dayfirst=True)

        df.loc[df["anio"] <= 0, "anio"] = fechas.dt.year.fillna(0).astype(int)
        df.loc[df["mes"] <= 0, "mes"] = fechas.dt.month.fillna(0).astype(int)

    return df


# ======================================================
# SIGNO FISCAL
# ======================================================

def es_nota_credito(codigo=None, tipo=None):
    codigo_norm = _normalizar_codigo(codigo)
    tipo_norm = _normalizar_texto(tipo)

    if codigo_norm in CODIGOS_NOTAS_CREDITO:
        return True

    patrones = [
        "NOTA DE CREDITO",
        "NOTA CREDITO",
        "NC ",
        " NC",
    ]

    if tipo_norm == "NC":
        return True

    return any(patron in tipo_norm for patron in patrones)


def es_nota_debito(codigo=None, tipo=None):
    codigo_norm = _normalizar_codigo(codigo)
    tipo_norm = _normalizar_texto(tipo)

    if codigo_norm in CODIGOS_NOTAS_DEBITO:
        return True

    patrones = [
        "NOTA DE DEBITO",
        "NOTA DEBITO",
        "ND ",
        " ND",
    ]

    if tipo_norm == "ND":
        return True

    return any(patron in tipo_norm for patron in patrones)


def signo_fiscal_comprobante(codigo=None, tipo=None):
    """
    Devuelve el signo fiscal esperado del comprobante.

    Facturas y notas de débito: positivo.
    Notas de crédito: negativo.

    Se usa para evitar que una nota de crédito importada con importes positivos
    aumente indebidamente el débito o crédito fiscal.
    """
    if es_nota_credito(codigo=codigo, tipo=tipo):
        return -1

    return 1


def importe_con_signo_fiscal(valor, codigo=None, tipo=None):
    signo = signo_fiscal_comprobante(codigo=codigo, tipo=tipo)
    valor = _float(valor)

    if abs(valor) <= TOLERANCIA_IMPORTES:
        return 0.0

    return signo * abs(valor)


# ======================================================
# LECTURA DE DATOS BASE
# ======================================================

def leer_tabla_periodo(nombre_tabla, empresa_id=1, anio=None, mes=None):
    """
    Lee una tabla por empresa/período de forma defensiva.
    No modifica datos.
    """
    nombre_tabla = _nombre_tabla_seguro(nombre_tabla)

    if not _tabla_existe(nombre_tabla):
        return pd.DataFrame()

    columnas = _obtener_columnas_tabla(nombre_tabla)

    condiciones = []
    parametros = []

    if empresa_id is not None and "empresa_id" in columnas:
        condiciones.append("empresa_id = ?")
        parametros.append(int(empresa_id))

    if anio is not None and "anio" in columnas:
        condiciones.append("anio = ?")
        parametros.append(int(anio))

    if mes is not None and "mes" in columnas:
        condiciones.append("mes = ?")
        parametros.append(int(mes))

    sql = f"SELECT * FROM {nombre_tabla}"

    if condiciones:
        sql += " WHERE " + " AND ".join(condiciones)

    orden = []

    for columna in ["anio", "mes", "fecha", "id"]:
        if columna in columnas:
            orden.append(columna)

    if orden:
        sql += " ORDER BY " + ", ".join(orden)

    try:
        df = ejecutar_query(sql, tuple(parametros), fetch=True)
        df = _resultado_a_dataframe(df)
        return _asegurar_columnas_periodo(df)
    except Exception:
        return pd.DataFrame()


def leer_ventas_periodo(empresa_id=1, anio=None, mes=None):
    return leer_tabla_periodo(
        "ventas_comprobantes",
        empresa_id=empresa_id,
        anio=anio,
        mes=mes,
    )


def leer_compras_periodo(empresa_id=1, anio=None, mes=None):
    return leer_tabla_periodo(
        "compras_comprobantes",
        empresa_id=empresa_id,
        anio=anio,
        mes=mes,
    )


# ======================================================
# MOVIMIENTOS FISCALES ADICIONALES
# ======================================================

def _impacto_movimientos_fiscales_cero():
    return {
        "cantidad_movimientos_fiscales": 0,
        "neto_gravado_movimientos_fiscales": 0.0,
        "iva_debito_adicional": 0.0,
        "credito_fiscal_computable_adicional": 0.0,
        "iva_no_computable_adicional": 0.0,
        "percepcion_iva_adicional": 0.0,
        "retencion_iva_adicional": 0.0,
        "percepcion_iibb_informativa_adicional": 0.0,
        "saldo_tecnico_anterior": 0.0,
        "saldo_libre_disponibilidad": 0.0,
        "pago_a_cuenta": 0.0,
        "otros_tributos_adicionales": 0.0,
        "total_movimientos_fiscales": 0.0,
        "deducciones_saldo_preliminar": 0.0,
    }


def obtener_impacto_movimientos_fiscales_periodo(empresa_id=1, anio=None, mes=None):
    """
    Obtiene impacto fiscal adicional del período.

    Si el servicio todavía no está disponible, devuelve cero.
    """
    if _obtener_impacto_movimientos_fiscales is None:
        return _impacto_movimientos_fiscales_cero()

    try:
        if _asegurar_movimientos_fiscales is not None:
            _asegurar_movimientos_fiscales()

        impacto = _obtener_impacto_movimientos_fiscales(
            empresa_id=empresa_id,
            anio=anio,
            mes=mes,
        )

        base = _impacto_movimientos_fiscales_cero()
        base.update(impacto or {})

        for clave, valor in base.items():
            if clave == "cantidad_movimientos_fiscales":
                base[clave] = _int(valor)
            else:
                base[clave] = _round2(valor)

        return base

    except Exception:
        return _impacto_movimientos_fiscales_cero()


def leer_movimientos_fiscales_periodo(empresa_id=1, anio=None, mes=None):
    """
    Lee movimientos fiscales adicionales del período.

    Solo lista no anulados.
    La posición IVA solo suma los confirmados.
    """
    if _listar_movimientos_fiscales is None:
        return pd.DataFrame()

    try:
        if _asegurar_movimientos_fiscales is not None:
            _asegurar_movimientos_fiscales()

        df = _listar_movimientos_fiscales(
            empresa_id=empresa_id,
            anio=anio,
            mes=mes,
            incluir_anulados=False,
        )

        return _resultado_a_dataframe(df)

    except Exception:
        return pd.DataFrame()


def leer_resumen_movimientos_fiscales_origen(empresa_id=1, anio=None, mes=None):
    if _obtener_resumen_movimientos_fiscales_origen is None:
        return pd.DataFrame()

    try:
        if _asegurar_movimientos_fiscales is not None:
            _asegurar_movimientos_fiscales()

        df = _obtener_resumen_movimientos_fiscales_origen(
            empresa_id=empresa_id,
            anio=anio,
            mes=mes,
        )

        return _resultado_a_dataframe(df)

    except Exception:
        return pd.DataFrame()


# ======================================================
# DETALLE VENTAS
# ======================================================

def preparar_detalle_ventas(df_ventas):
    """
    Devuelve detalle de ventas con importes fiscales normalizados.
    """
    if df_ventas is None or df_ventas.empty:
        return pd.DataFrame(columns=[
            "origen",
            "id",
            "fecha",
            "anio",
            "mes",
            "codigo",
            "tipo",
            "punto_venta",
            "numero",
            "cliente",
            "cuit",
            "neto_original",
            "iva_original",
            "total_original",
            "signo_fiscal",
            "neto_ventas",
            "iva_debito_fiscal",
            "total_ventas",
            "archivo",
        ])

    df = df_ventas.copy()
    df = _asegurar_columnas_periodo(df)

    for columna in [
        "id",
        "fecha",
        "anio",
        "mes",
        "codigo",
        "tipo",
        "punto_venta",
        "numero",
        "cliente",
        "cuit",
        "neto",
        "iva",
        "total",
        "archivo",
    ]:
        if columna not in df.columns:
            df[columna] = ""

    df["origen"] = ORIGEN_VENTAS
    df["signo_fiscal"] = df.apply(
        lambda row: signo_fiscal_comprobante(row.get("codigo"), row.get("tipo")),
        axis=1,
    )

    df["neto_original"] = df["neto"].apply(_float)
    df["iva_original"] = df["iva"].apply(_float)
    df["total_original"] = df["total"].apply(_float)

    df["neto_ventas"] = df.apply(
        lambda row: importe_con_signo_fiscal(
            row.get("neto_original"),
            row.get("codigo"),
            row.get("tipo"),
        ),
        axis=1,
    )

    df["iva_debito_fiscal"] = df.apply(
        lambda row: importe_con_signo_fiscal(
            row.get("iva_original"),
            row.get("codigo"),
            row.get("tipo"),
        ),
        axis=1,
    )

    df["total_ventas"] = df.apply(
        lambda row: importe_con_signo_fiscal(
            row.get("total_original"),
            row.get("codigo"),
            row.get("tipo"),
        ),
        axis=1,
    )

    columnas = [
        "origen",
        "id",
        "fecha",
        "anio",
        "mes",
        "codigo",
        "tipo",
        "punto_venta",
        "numero",
        "cliente",
        "cuit",
        "neto_original",
        "iva_original",
        "total_original",
        "signo_fiscal",
        "neto_ventas",
        "iva_debito_fiscal",
        "total_ventas",
        "archivo",
    ]

    return df[columnas].copy()


def resumir_ventas(detalle_ventas):
    if detalle_ventas is None or detalle_ventas.empty:
        return {
            "cantidad_ventas": 0,
            "neto_ventas": 0.0,
            "iva_debito_fiscal": 0.0,
            "total_ventas": 0.0,
        }

    return {
        "cantidad_ventas": int(len(detalle_ventas)),
        "neto_ventas": _round2(detalle_ventas["neto_ventas"].sum()),
        "iva_debito_fiscal": _round2(detalle_ventas["iva_debito_fiscal"].sum()),
        "total_ventas": _round2(detalle_ventas["total_ventas"].sum()),
    }


# ======================================================
# DETALLE COMPRAS
# ======================================================

def _calcular_credito_fiscal_computable_compra(row):
    """
    Determina el crédito fiscal computable con prioridad:

    1. credito_fiscal_computable
    2. iva_computable_sistema
    3. iva_computable_csv
    4. iva_total - iva_no_computable
    5. iva_total como respaldo controlado

    La normalización de signo se hace según tipo/código del comprobante.
    """
    codigo = row.get("codigo")
    tipo = row.get("tipo")
    signo = signo_fiscal_comprobante(codigo=codigo, tipo=tipo)

    iva_total_abs = abs(_float(row.get("iva_total_calculado", 0)))
    iva_no_computable_abs = abs(_float(row.get("iva_no_computable_calculado", 0)))

    candidatos = [
        row.get("credito_fiscal_computable", 0),
        row.get("iva_computable_sistema", 0),
        row.get("iva_computable_csv", 0),
    ]

    for candidato in candidatos:
        valor = abs(_float(candidato))
        if valor > TOLERANCIA_IMPORTES:
            return signo * valor

    if iva_total_abs > TOLERANCIA_IMPORTES and iva_no_computable_abs > TOLERANCIA_IMPORTES:
        return signo * max(iva_total_abs - iva_no_computable_abs, 0.0)

    if iva_total_abs > TOLERANCIA_IMPORTES:
        return signo * iva_total_abs

    return 0.0


def _calcular_iva_no_computable_compra(row):
    codigo = row.get("codigo")
    tipo = row.get("tipo")
    signo = signo_fiscal_comprobante(codigo=codigo, tipo=tipo)

    candidatos = [
        row.get("iva_no_computable", 0),
        row.get("iva_no_computable_sistema", 0),
    ]

    for candidato in candidatos:
        valor = abs(_float(candidato))
        if valor > TOLERANCIA_IMPORTES:
            return signo * valor

    iva_total_abs = abs(_float(row.get("iva_total_calculado", 0)))
    credito_abs = abs(_float(row.get("credito_fiscal_computable_calculado", 0)))

    if iva_total_abs > TOLERANCIA_IMPORTES and credito_abs <= iva_total_abs:
        diferencia = iva_total_abs - credito_abs

        if diferencia > TOLERANCIA_IMPORTES:
            return signo * diferencia

    return 0.0


def preparar_detalle_compras(df_compras):
    """
    Devuelve detalle de compras con importes fiscales normalizados.
    """
    if df_compras is None or df_compras.empty:
        return pd.DataFrame(columns=[
            "origen",
            "id",
            "fecha",
            "anio",
            "mes",
            "codigo",
            "tipo",
            "punto_venta",
            "numero",
            "proveedor",
            "cuit",
            "categoria_compra",
            "neto_original",
            "iva_original",
            "iva_total_original",
            "credito_fiscal_computable_original",
            "iva_no_computable_original",
            "percepcion_iva_original",
            "percepcion_iibb_original",
            "total_original",
            "signo_fiscal",
            "neto_compras",
            "iva_total_compras",
            "credito_fiscal_computable",
            "iva_no_computable",
            "percepciones_iva",
            "percepciones_iibb_informativas",
            "total_compras",
            "archivo",
        ])

    df = df_compras.copy()
    df = _asegurar_columnas_periodo(df)

    columnas_base = [
        "id",
        "fecha",
        "anio",
        "mes",
        "codigo",
        "tipo",
        "punto_venta",
        "numero",
        "proveedor",
        "cuit",
        "categoria_compra",
        "neto",
        "iva",
        "iva_total",
        "credito_fiscal_computable",
        "iva_computable_sistema",
        "iva_computable_csv",
        "iva_no_computable",
        "iva_no_computable_sistema",
        "percepcion_iva",
        "percepcion_iibb",
        "total",
        "archivo",
    ]

    for columna in columnas_base:
        if columna not in df.columns:
            df[columna] = 0 if columna not in {
                "id",
                "fecha",
                "anio",
                "mes",
                "codigo",
                "tipo",
                "punto_venta",
                "numero",
                "proveedor",
                "cuit",
                "categoria_compra",
                "archivo",
            } else ""

    df["origen"] = ORIGEN_COMPRAS

    df["signo_fiscal"] = df.apply(
        lambda row: signo_fiscal_comprobante(row.get("codigo"), row.get("tipo")),
        axis=1,
    )

    df["neto_original"] = df["neto"].apply(_float)
    df["iva_original"] = df["iva"].apply(_float)

    df["iva_total_original"] = df.apply(
        lambda row: _primer_importe_no_cero(row, ["iva_total", "iva"]),
        axis=1,
    )

    df["credito_fiscal_computable_original"] = df["credito_fiscal_computable"].apply(_float)
    df["iva_no_computable_original"] = df["iva_no_computable"].apply(_float)
    df["percepcion_iva_original"] = df["percepcion_iva"].apply(_float)
    df["percepcion_iibb_original"] = df["percepcion_iibb"].apply(_float)
    df["total_original"] = df["total"].apply(_float)

    df["neto_compras"] = df.apply(
        lambda row: importe_con_signo_fiscal(
            row.get("neto_original"),
            row.get("codigo"),
            row.get("tipo"),
        ),
        axis=1,
    )

    df["iva_total_compras"] = df.apply(
        lambda row: importe_con_signo_fiscal(
            row.get("iva_total_original"),
            row.get("codigo"),
            row.get("tipo"),
        ),
        axis=1,
    )

    df["iva_total_calculado"] = df["iva_total_compras"]

    df["iva_no_computable_calculado"] = df.apply(
        lambda row: importe_con_signo_fiscal(
            _primer_importe_no_cero(row, ["iva_no_computable", "iva_no_computable_sistema"]),
            row.get("codigo"),
            row.get("tipo"),
        ),
        axis=1,
    )

    df["credito_fiscal_computable_calculado"] = df.apply(
        _calcular_credito_fiscal_computable_compra,
        axis=1,
    )

    df["iva_no_computable_calculado"] = df.apply(
        _calcular_iva_no_computable_compra,
        axis=1,
    )

    df["percepciones_iva"] = df.apply(
        lambda row: importe_con_signo_fiscal(
            row.get("percepcion_iva_original"),
            row.get("codigo"),
            row.get("tipo"),
        ),
        axis=1,
    )

    df["percepciones_iibb_informativas"] = df.apply(
        lambda row: importe_con_signo_fiscal(
            row.get("percepcion_iibb_original"),
            row.get("codigo"),
            row.get("tipo"),
        ),
        axis=1,
    )

    df["total_compras"] = df.apply(
        lambda row: importe_con_signo_fiscal(
            row.get("total_original"),
            row.get("codigo"),
            row.get("tipo"),
        ),
        axis=1,
    )

    df["credito_fiscal_computable"] = df["credito_fiscal_computable_calculado"]
    df["iva_no_computable"] = df["iva_no_computable_calculado"]

    columnas = [
        "origen",
        "id",
        "fecha",
        "anio",
        "mes",
        "codigo",
        "tipo",
        "punto_venta",
        "numero",
        "proveedor",
        "cuit",
        "categoria_compra",
        "neto_original",
        "iva_original",
        "iva_total_original",
        "credito_fiscal_computable_original",
        "iva_no_computable_original",
        "percepcion_iva_original",
        "percepcion_iibb_original",
        "total_original",
        "signo_fiscal",
        "neto_compras",
        "iva_total_compras",
        "credito_fiscal_computable",
        "iva_no_computable",
        "percepciones_iva",
        "percepciones_iibb_informativas",
        "total_compras",
        "archivo",
    ]

    return df[columnas].copy()


def resumir_compras(detalle_compras):
    if detalle_compras is None or detalle_compras.empty:
        return {
            "cantidad_compras": 0,
            "neto_compras": 0.0,
            "iva_total_compras": 0.0,
            "credito_fiscal_computable": 0.0,
            "iva_no_computable": 0.0,
            "percepciones_iva": 0.0,
            "percepciones_iibb_informativas": 0.0,
            "total_compras": 0.0,
        }

    return {
        "cantidad_compras": int(len(detalle_compras)),
        "neto_compras": _round2(detalle_compras["neto_compras"].sum()),
        "iva_total_compras": _round2(detalle_compras["iva_total_compras"].sum()),
        "credito_fiscal_computable": _round2(detalle_compras["credito_fiscal_computable"].sum()),
        "iva_no_computable": _round2(detalle_compras["iva_no_computable"].sum()),
        "percepciones_iva": _round2(detalle_compras["percepciones_iva"].sum()),
        "percepciones_iibb_informativas": _round2(
            detalle_compras["percepciones_iibb_informativas"].sum()
        ),
        "total_compras": _round2(detalle_compras["total_compras"].sum()),
    }


# ======================================================
# ALERTAS Y CONTROLES
# ======================================================

def _agregar_alerta(alertas, nivel, titulo, detalle):
    alertas.append({
        "nivel": nivel,
        "titulo": titulo,
        "detalle": detalle,
    })


def generar_alertas_control(
    anio,
    mes,
    detalle_ventas,
    detalle_compras,
    detalle_movimientos_fiscales,
    posicion,
):
    alertas = []

    cantidad_ventas = int(posicion.get("cantidad_ventas", 0))
    cantidad_compras = int(posicion.get("cantidad_compras", 0))
    cantidad_movimientos_fiscales = int(posicion.get("cantidad_movimientos_fiscales", 0))

    if cantidad_ventas == 0 and cantidad_compras == 0 and cantidad_movimientos_fiscales == 0:
        _agregar_alerta(
            alertas,
            "INFO",
            "Período sin movimientos",
            "No se encontraron ventas, compras ni movimientos fiscales adicionales para el período seleccionado.",
        )

    if cantidad_ventas == 0 and cantidad_compras > 0:
        _agregar_alerta(
            alertas,
            "INFO",
            "Período con compras pero sin ventas",
            "La posición mensual tiene crédito fiscal potencial, pero no registra débito fiscal de ventas.",
        )

    if cantidad_ventas > 0 and cantidad_compras == 0:
        _agregar_alerta(
            alertas,
            "INFO",
            "Período con ventas pero sin compras",
            "La posición mensual tiene débito fiscal, pero no registra crédito fiscal de compras.",
        )

    if detalle_ventas is not None and not detalle_ventas.empty:
        ventas_nc = detalle_ventas[detalle_ventas["signo_fiscal"] < 0]

        if not ventas_nc.empty:
            _agregar_alerta(
                alertas,
                "INFO",
                "Notas de crédito de ventas normalizadas",
                (
                    f"Se detectaron {len(ventas_nc)} comprobante(s) de ventas con signo fiscal negativo. "
                    "El cálculo las resta de la posición mensual."
                ),
            )

    if detalle_compras is not None and not detalle_compras.empty:
        compras_nc = detalle_compras[detalle_compras["signo_fiscal"] < 0]

        if not compras_nc.empty:
            _agregar_alerta(
                alertas,
                "INFO",
                "Notas de crédito de compras normalizadas",
                (
                    f"Se detectaron {len(compras_nc)} comprobante(s) de compras con signo fiscal negativo. "
                    "El cálculo las resta del crédito fiscal y de las percepciones."
                ),
            )

        compras_credito_mayor_iva = detalle_compras[
            detalle_compras["credito_fiscal_computable"].abs()
            > detalle_compras["iva_total_compras"].abs() + TOLERANCIA_IMPORTES
        ]

        if not compras_credito_mayor_iva.empty:
            _agregar_alerta(
                alertas,
                "ADVERTENCIA",
                "Crédito fiscal computable mayor al IVA total",
                (
                    f"Hay {len(compras_credito_mayor_iva)} compra(s) donde el crédito fiscal computable "
                    "supera el IVA total del comprobante. Revisar clasificación fiscal."
                ),
            )

        compras_con_iva_sin_credito = detalle_compras[
            (detalle_compras["iva_total_compras"].abs() > TOLERANCIA_IMPORTES)
            & (detalle_compras["credito_fiscal_computable"].abs() <= TOLERANCIA_IMPORTES)
            & (detalle_compras["iva_no_computable"].abs() <= TOLERANCIA_IMPORTES)
        ]

        if not compras_con_iva_sin_credito.empty:
            _agregar_alerta(
                alertas,
                "ADVERTENCIA",
                "Compras con IVA sin tratamiento fiscal claro",
                (
                    f"Hay {len(compras_con_iva_sin_credito)} compra(s) con IVA informado, "
                    "pero sin crédito fiscal computable ni IVA no computable. "
                    "Revisar categoría/tratamiento de IVA."
                ),
            )

    if cantidad_movimientos_fiscales > 0:
        _agregar_alerta(
            alertas,
            "INFO",
            "Movimientos fiscales adicionales incorporados",
            (
                f"Se incorporaron {cantidad_movimientos_fiscales} movimiento(s) fiscal(es) adicional(es) "
                "confirmado(s) a la posición IVA del período."
            ),
        )

    if detalle_movimientos_fiscales is not None and not detalle_movimientos_fiscales.empty:
        if "estado" in detalle_movimientos_fiscales.columns:
            borradores = detalle_movimientos_fiscales[
                detalle_movimientos_fiscales["estado"] == "BORRADOR"
            ]
        else:
            borradores = pd.DataFrame()

        if not borradores.empty:
            _agregar_alerta(
                alertas,
                "INFO",
                "Movimientos fiscales en borrador",
                (
                    f"Existen {len(borradores)} movimiento(s) fiscal(es) en borrador. "
                    "No impactan la posición IVA hasta ser confirmados."
                ),
            )

    return alertas


# ======================================================
# RESUMEN POR ORIGEN
# ======================================================

def resumen_por_origen(posicion):
    """
    Devuelve una tabla simple por origen fiscal.
    """
    filas = [
        {
            "origen": ORIGEN_VENTAS,
            "neto": _round2(posicion.get("neto_ventas", 0)),
            "iva_debito": _round2(posicion.get("iva_debito_fiscal_ventas", 0)),
            "iva_credito": 0.0,
            "iva_no_computable": 0.0,
            "percepcion_iva": 0.0,
            "retencion_iva": 0.0,
            "percepcion_iibb_informativa": 0.0,
            "total": _round2(posicion.get("total_ventas", 0)),
            "estado": "Operativo",
        },
        {
            "origen": ORIGEN_COMPRAS,
            "neto": _round2(posicion.get("neto_compras", 0)),
            "iva_debito": 0.0,
            "iva_credito": _round2(posicion.get("credito_fiscal_computable_compras", 0)),
            "iva_no_computable": _round2(posicion.get("iva_no_computable_compras", 0)),
            "percepcion_iva": _round2(posicion.get("percepciones_iva_compras", 0)),
            "retencion_iva": 0.0,
            "percepcion_iibb_informativa": _round2(
                posicion.get("percepciones_iibb_compras_informativas", 0)
            ),
            "total": _round2(posicion.get("total_compras", 0)),
            "estado": "Operativo",
        },
        {
            "origen": ORIGEN_MOVIMIENTOS_FISCALES,
            "neto": _round2(posicion.get("neto_movimientos_fiscales", 0)),
            "iva_debito": _round2(posicion.get("iva_debito_adicional", 0)),
            "iva_credito": _round2(posicion.get("credito_fiscal_computable_adicional", 0)),
            "iva_no_computable": _round2(posicion.get("iva_no_computable_adicional", 0)),
            "percepcion_iva": _round2(posicion.get("percepciones_iva_adicionales", 0)),
            "retencion_iva": _round2(posicion.get("retenciones_iva_sufridas", 0)),
            "percepcion_iibb_informativa": _round2(
                posicion.get("percepciones_iibb_adicionales_informativas", 0)
            ),
            "total": _round2(posicion.get("total_movimientos_fiscales", 0)),
            "estado": "Operativo si existen confirmados",
        },
    ]

    return pd.DataFrame(filas)


# ======================================================
# POSICIÓN MENSUAL
# ======================================================

def calcular_posicion_iva_periodo(empresa_id=1, anio=None, mes=None):
    """
    Calcula la posición IVA mensual para una empresa/período.

    Devuelve:
    {
        "posicion": dict,
        "detalle_ventas": DataFrame,
        "detalle_compras": DataFrame,
        "detalle_movimientos_fiscales": DataFrame,
        "resumen_origenes": DataFrame,
        "resumen_movimientos_fiscales_origen": DataFrame,
        "alertas": list[dict],
    }
    """
    anio = _int(anio)
    mes = _int(mes)

    if anio <= 0 or mes <= 0:
        posicion_vacia = {
            columna: 0 for columna in COLUMNAS_POSICION
        }
        posicion_vacia.update({
            "empresa_id": empresa_id,
            "anio": anio,
            "mes": mes,
            "periodo": _periodo_texto(anio, mes),
        })

        return {
            "posicion": posicion_vacia,
            "detalle_ventas": preparar_detalle_ventas(pd.DataFrame()),
            "detalle_compras": preparar_detalle_compras(pd.DataFrame()),
            "detalle_movimientos_fiscales": pd.DataFrame(),
            "resumen_origenes": resumen_por_origen(posicion_vacia),
            "resumen_movimientos_fiscales_origen": pd.DataFrame(),
            "alertas": [{
                "nivel": "ERROR",
                "titulo": "Período inválido",
                "detalle": "Debe seleccionarse un año y mes válidos para calcular la posición IVA.",
            }],
        }

    df_ventas = leer_ventas_periodo(
        empresa_id=empresa_id,
        anio=anio,
        mes=mes,
    )

    df_compras = leer_compras_periodo(
        empresa_id=empresa_id,
        anio=anio,
        mes=mes,
    )

    detalle_ventas = preparar_detalle_ventas(df_ventas)
    detalle_compras = preparar_detalle_compras(df_compras)

    detalle_movimientos_fiscales = leer_movimientos_fiscales_periodo(
        empresa_id=empresa_id,
        anio=anio,
        mes=mes,
    )

    resumen_movimientos_fiscales_origen = leer_resumen_movimientos_fiscales_origen(
        empresa_id=empresa_id,
        anio=anio,
        mes=mes,
    )

    resumen_ventas = resumir_ventas(detalle_ventas)
    resumen_compras = resumir_compras(detalle_compras)

    impacto_movimientos = obtener_impacto_movimientos_fiscales_periodo(
        empresa_id=empresa_id,
        anio=anio,
        mes=mes,
    )

    iva_debito_ventas = _round2(resumen_ventas["iva_debito_fiscal"])
    credito_compras = _round2(resumen_compras["credito_fiscal_computable"])
    iva_no_computable_compras = _round2(resumen_compras["iva_no_computable"])
    percepciones_iva_compras = _round2(resumen_compras["percepciones_iva"])
    percepciones_iibb_compras = _round2(resumen_compras["percepciones_iibb_informativas"])

    iva_debito_adicional = _round2(impacto_movimientos["iva_debito_adicional"])
    credito_adicional = _round2(impacto_movimientos["credito_fiscal_computable_adicional"])
    iva_no_computable_adicional = _round2(impacto_movimientos["iva_no_computable_adicional"])
    percepcion_iva_adicional = _round2(impacto_movimientos["percepcion_iva_adicional"])
    retencion_iva_adicional = _round2(impacto_movimientos["retencion_iva_adicional"])
    percepcion_iibb_adicional = _round2(
        impacto_movimientos["percepcion_iibb_informativa_adicional"]
    )

    saldo_tecnico_anterior = _round2(impacto_movimientos["saldo_tecnico_anterior"])
    saldo_libre_disponibilidad = _round2(impacto_movimientos["saldo_libre_disponibilidad"])
    pago_a_cuenta = _round2(impacto_movimientos["pago_a_cuenta"])

    iva_debito_total = _round2(iva_debito_ventas + iva_debito_adicional)
    credito_fiscal_total = _round2(credito_compras + credito_adicional)
    iva_no_computable_total = _round2(iva_no_computable_compras + iva_no_computable_adicional)

    percepciones_iva_total = _round2(percepciones_iva_compras + percepcion_iva_adicional)
    percepciones_iibb_total = _round2(percepciones_iibb_compras + percepcion_iibb_adicional)

    saldo_tecnico = _round2(iva_debito_total - credito_fiscal_total)

    # Criterio:
    # - saldo_tecnico_anterior se carga positivo cuando es saldo a favor aplicable.
    # - saldo_libre_disponibilidad se carga positivo cuando se aplica contra IVA.
    # - pago_a_cuenta se carga positivo cuando reduce saldo del período.
    # - retenciones/percepciones IVA sufridas reducen saldo preliminar.
    saldo_preliminar = _round2(
        saldo_tecnico
        - percepciones_iva_total
        - retencion_iva_adicional
        - saldo_tecnico_anterior
        - saldo_libre_disponibilidad
        - pago_a_cuenta
    )

    posicion = {
        "empresa_id": int(empresa_id) if empresa_id is not None else None,
        "anio": anio,
        "mes": mes,
        "periodo": _periodo_texto(anio, mes),

        "neto_ventas": _round2(resumen_ventas["neto_ventas"]),
        "iva_debito_fiscal_ventas": iva_debito_ventas,
        "total_ventas": _round2(resumen_ventas["total_ventas"]),

        "neto_compras": _round2(resumen_compras["neto_compras"]),
        "iva_total_compras": _round2(resumen_compras["iva_total_compras"]),
        "credito_fiscal_computable_compras": credito_compras,
        "iva_no_computable_compras": iva_no_computable_compras,
        "percepciones_iva_compras": percepciones_iva_compras,
        "percepciones_iibb_compras_informativas": percepciones_iibb_compras,
        "total_compras": _round2(resumen_compras["total_compras"]),

        "neto_movimientos_fiscales": _round2(
            impacto_movimientos["neto_gravado_movimientos_fiscales"]
        ),
        "iva_debito_adicional": iva_debito_adicional,
        "credito_fiscal_computable_adicional": credito_adicional,
        "iva_no_computable_adicional": iva_no_computable_adicional,
        "percepciones_iva_adicionales": percepcion_iva_adicional,
        "retenciones_iva_sufridas": retencion_iva_adicional,
        "percepciones_iibb_adicionales_informativas": percepcion_iibb_adicional,
        "saldo_tecnico_anterior": saldo_tecnico_anterior,
        "saldo_libre_disponibilidad": saldo_libre_disponibilidad,
        "pago_a_cuenta": pago_a_cuenta,
        "otros_tributos_adicionales": _round2(impacto_movimientos["otros_tributos_adicionales"]),
        "total_movimientos_fiscales": _round2(impacto_movimientos["total_movimientos_fiscales"]),

        "iva_debito_fiscal": iva_debito_total,
        "credito_fiscal_computable": credito_fiscal_total,
        "iva_no_computable": iva_no_computable_total,
        "percepciones_iva": percepciones_iva_total,
        "percepciones_iibb_informativas": percepciones_iibb_total,

        "saldo_tecnico_iva": saldo_tecnico,
        "percepciones_iva_sufridas": percepciones_iva_total,
        "saldo_preliminar_periodo": saldo_preliminar,

        "cantidad_ventas": int(resumen_ventas["cantidad_ventas"]),
        "cantidad_compras": int(resumen_compras["cantidad_compras"]),
        "cantidad_movimientos_fiscales": int(
            impacto_movimientos["cantidad_movimientos_fiscales"]
        ),
    }

    resumen_origenes = resumen_por_origen(posicion)

    alertas = generar_alertas_control(
        anio=anio,
        mes=mes,
        detalle_ventas=detalle_ventas,
        detalle_compras=detalle_compras,
        detalle_movimientos_fiscales=detalle_movimientos_fiscales,
        posicion=posicion,
    )

    return {
        "posicion": posicion,
        "detalle_ventas": detalle_ventas,
        "detalle_compras": detalle_compras,
        "detalle_movimientos_fiscales": detalle_movimientos_fiscales,
        "resumen_origenes": resumen_origenes,
        "resumen_movimientos_fiscales_origen": resumen_movimientos_fiscales_origen,
        "alertas": alertas,
    }


# ======================================================
# PERIODOS DISPONIBLES
# ======================================================

def obtener_periodos_disponibles_iva(empresa_id=1):
    """
    Devuelve períodos con movimientos en ventas, compras o movimientos fiscales.
    """
    ventas = leer_ventas_periodo(empresa_id=empresa_id)
    compras = leer_compras_periodo(empresa_id=empresa_id)

    filas = []

    if ventas is not None and not ventas.empty:
        ventas = _asegurar_columnas_periodo(ventas)
        ventas_validas = ventas[(ventas["anio"] > 0) & (ventas["mes"] > 0)]

        for (anio, mes), grupo in ventas_validas.groupby(["anio", "mes"]):
            filas.append({
                "anio": int(anio),
                "mes": int(mes),
                "periodo": _periodo_texto(anio, mes),
                "origen": ORIGEN_VENTAS,
                "cantidad_ventas": int(len(grupo)),
                "cantidad_compras": 0,
                "cantidad_movimientos_fiscales": 0,
            })

    if compras is not None and not compras.empty:
        compras = _asegurar_columnas_periodo(compras)
        compras_validas = compras[(compras["anio"] > 0) & (compras["mes"] > 0)]

        for (anio, mes), grupo in compras_validas.groupby(["anio", "mes"]):
            filas.append({
                "anio": int(anio),
                "mes": int(mes),
                "periodo": _periodo_texto(anio, mes),
                "origen": ORIGEN_COMPRAS,
                "cantidad_ventas": 0,
                "cantidad_compras": int(len(grupo)),
                "cantidad_movimientos_fiscales": 0,
            })

    try:
        if _listar_movimientos_fiscales is not None:
            movimientos = _listar_movimientos_fiscales(
                empresa_id=empresa_id,
                incluir_anulados=False,
            )
            movimientos = _resultado_a_dataframe(movimientos)

            if not movimientos.empty:
                movimientos = _asegurar_columnas_periodo(movimientos)
                movimientos_validos = movimientos[
                    (movimientos["anio"] > 0)
                    & (movimientos["mes"] > 0)
                    & (movimientos["estado"] == "CONFIRMADO")
                ]

                for (anio, mes), grupo in movimientos_validos.groupby(["anio", "mes"]):
                    filas.append({
                        "anio": int(anio),
                        "mes": int(mes),
                        "periodo": _periodo_texto(anio, mes),
                        "origen": ORIGEN_MOVIMIENTOS_FISCALES,
                        "cantidad_ventas": 0,
                        "cantidad_compras": 0,
                        "cantidad_movimientos_fiscales": int(len(grupo)),
                    })
    except Exception:
        pass

    if not filas:
        return pd.DataFrame(columns=[
            "anio",
            "mes",
            "periodo",
            "cantidad_ventas",
            "cantidad_compras",
            "cantidad_movimientos_fiscales",
            "cantidad_total",
        ])

    df = pd.DataFrame(filas)

    resumen = (
        df.groupby(["anio", "mes", "periodo"], as_index=False)
        .agg({
            "cantidad_ventas": "sum",
            "cantidad_compras": "sum",
            "cantidad_movimientos_fiscales": "sum",
        })
    )

    resumen["cantidad_total"] = (
        resumen["cantidad_ventas"]
        + resumen["cantidad_compras"]
        + resumen["cantidad_movimientos_fiscales"]
    )

    resumen = resumen.sort_values(["anio", "mes"], ascending=[False, False])

    return resumen.reset_index(drop=True)


def obtener_resumen_posiciones_iva(empresa_id=1):
    """
    Calcula resumen de posición para todos los períodos disponibles.
    """
    periodos = obtener_periodos_disponibles_iva(empresa_id=empresa_id)

    if periodos.empty:
        return pd.DataFrame(columns=COLUMNAS_POSICION)

    filas = []

    for _, row in periodos.iterrows():
        resultado = calcular_posicion_iva_periodo(
            empresa_id=empresa_id,
            anio=int(row["anio"]),
            mes=int(row["mes"]),
        )
        filas.append(resultado["posicion"])

    df = pd.DataFrame(filas)

    for columna in COLUMNAS_POSICION:
        if columna not in df.columns:
            df[columna] = 0

    df = df[COLUMNAS_POSICION]
    df = df.sort_values(["anio", "mes"], ascending=[False, False])

    return df.reset_index(drop=True)


# ======================================================
# FORMATOS PARA UI
# ======================================================

def formato_moneda(valor):
    valor = _float(valor)
    return f"$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def etiqueta_resultado_saldo(valor):
    valor = _round2(valor)

    if valor > TOLERANCIA_IMPORTES:
        return "Saldo preliminar a ingresar"

    if valor < -TOLERANCIA_IMPORTES:
        return "Saldo preliminar a favor"

    return "Posición preliminar en cero"


def preparar_dataframe_posicion_para_mostrar(df):
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()

    columnas_monetarias = [
        "neto_ventas",
        "iva_debito_fiscal_ventas",
        "total_ventas",
        "neto_compras",
        "iva_total_compras",
        "credito_fiscal_computable_compras",
        "iva_no_computable_compras",
        "percepciones_iva_compras",
        "percepciones_iibb_compras_informativas",
        "total_compras",
        "neto_movimientos_fiscales",
        "iva_debito_adicional",
        "credito_fiscal_computable_adicional",
        "iva_no_computable_adicional",
        "percepciones_iva_adicionales",
        "retenciones_iva_sufridas",
        "percepciones_iibb_adicionales_informativas",
        "saldo_tecnico_anterior",
        "saldo_libre_disponibilidad",
        "pago_a_cuenta",
        "otros_tributos_adicionales",
        "total_movimientos_fiscales",
        "iva_debito_fiscal",
        "credito_fiscal_computable",
        "iva_no_computable",
        "percepciones_iva",
        "percepciones_iibb_informativas",
        "saldo_tecnico_iva",
        "percepciones_iva_sufridas",
        "saldo_preliminar_periodo",
    ]

    for columna in columnas_monetarias:
        if columna in df.columns:
            df[columna] = df[columna].apply(_round2)

    return df


# ======================================================
# EXPORTACIÓN EXCEL - PAPEL DE TRABAJO
# ======================================================

def _ajustar_hoja_excel(ws):
    try:
        ws.freeze_panes = "A2"

        for cell in ws[1]:
            cell.font = cell.font.copy(bold=True)

        for column_cells in ws.columns:
            max_length = 0
            column_letter = column_cells[0].column_letter

            for cell in column_cells:
                try:
                    value = "" if cell.value is None else str(cell.value)
                    max_length = max(max_length, len(value))
                except Exception:
                    pass

            ws.column_dimensions[column_letter].width = min(max(max_length + 2, 12), 42)

        for row in ws.iter_rows(min_row=2):
            for cell in row:
                if isinstance(cell.value, (int, float)):
                    cell.number_format = '#,##0.00'
    except Exception:
        pass


def generar_papel_trabajo_excel_iva(empresa_id=1, anio=None, mes=None):
    """
    Genera un Excel en memoria con el papel de trabajo mensual.

    Devuelve bytes.
    """
    resultado = calcular_posicion_iva_periodo(
        empresa_id=empresa_id,
        anio=anio,
        mes=mes,
    )

    posicion = resultado["posicion"]
    detalle_ventas = resultado["detalle_ventas"]
    detalle_compras = resultado["detalle_compras"]
    detalle_movimientos_fiscales = resultado.get("detalle_movimientos_fiscales", pd.DataFrame())
    resumen_origenes = resultado["resumen_origenes"]
    resumen_movimientos_fiscales_origen = resultado.get(
        "resumen_movimientos_fiscales_origen",
        pd.DataFrame(),
    )
    alertas = pd.DataFrame(resultado["alertas"])

    df_posicion = pd.DataFrame([posicion])

    buffer = BytesIO()

    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df_posicion.to_excel(writer, sheet_name="Posicion IVA", index=False)
        resumen_origenes.to_excel(writer, sheet_name="Resumen origenes", index=False)
        detalle_ventas.to_excel(writer, sheet_name="Libro IVA Ventas", index=False)
        detalle_compras.to_excel(writer, sheet_name="Libro IVA Compras", index=False)

        if detalle_movimientos_fiscales is not None and not detalle_movimientos_fiscales.empty:
            detalle_movimientos_fiscales.to_excel(
                writer,
                sheet_name="Movimientos fiscales",
                index=False,
            )
        else:
            pd.DataFrame(columns=[
                "id",
                "fecha",
                "origen",
                "tipo_concepto",
                "descripcion",
                "estado",
            ]).to_excel(writer, sheet_name="Movimientos fiscales", index=False)

        if (
            resumen_movimientos_fiscales_origen is not None
            and not resumen_movimientos_fiscales_origen.empty
        ):
            resumen_movimientos_fiscales_origen.to_excel(
                writer,
                sheet_name="Resumen mov fiscales",
                index=False,
            )

        alertas.to_excel(writer, sheet_name="Alertas", index=False)

        workbook = writer.book

        for worksheet in workbook.worksheets:
            _ajustar_hoja_excel(worksheet)

    buffer.seek(0)
    return buffer.getvalue()


def nombre_archivo_papel_trabajo_iva(empresa_id=1, anio=None, mes=None):
    anio = _int(anio)
    mes = _int(mes)

    if anio <= 0 or mes <= 0:
        return f"papel_trabajo_iva_empresa_{empresa_id}.xlsx"

    return f"papel_trabajo_iva_empresa_{empresa_id}_{anio}_{mes:02d}.xlsx"


# ======================================================
# API PÚBLICA DEL SERVICIO
# ======================================================

__all__ = [
    "ORIGEN_VENTAS",
    "ORIGEN_COMPRAS",
    "ORIGEN_MOVIMIENTOS_FISCALES",
    "ORIGEN_BANCO",
    "ORIGEN_AJUSTE_MANUAL",
    "es_nota_credito",
    "es_nota_debito",
    "signo_fiscal_comprobante",
    "leer_ventas_periodo",
    "leer_compras_periodo",
    "leer_movimientos_fiscales_periodo",
    "leer_resumen_movimientos_fiscales_origen",
    "preparar_detalle_ventas",
    "preparar_detalle_compras",
    "obtener_impacto_movimientos_fiscales_periodo",
    "calcular_posicion_iva_periodo",
    "obtener_periodos_disponibles_iva",
    "obtener_resumen_posiciones_iva",
    "formato_moneda",
    "etiqueta_resultado_saldo",
    "preparar_dataframe_posicion_para_mostrar",
    "generar_papel_trabajo_excel_iva",
    "nombre_archivo_papel_trabajo_iva",
]