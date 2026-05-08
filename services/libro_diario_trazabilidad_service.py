from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from database import conectar


# ======================================================
# CONTABILIDAD PRO - TRAZABILIDAD DEL LIBRO DIARIO
# ======================================================
#
# Este servicio es una capa de lectura/control.
# No borra datos.
# No cambia estados.
# No genera asientos.
# No migra Ventas, Compras, Banco, Caja, Cobranzas ni Pagos.
#
# Objetivo:
# - Entender de dónde viene cada asiento ya registrado en libro_diario.
# - Distinguir asientos directos/históricos de asientos pasados por Bandeja.
# - Mostrar propuesta vinculada, lote, reversos y posibles descuadres.
# ======================================================

TABLA_LIBRO = "libro_diario"
TABLA_PROPUESTOS = "asientos_propuestos"
TABLA_IVA_PROPUESTOS = "iva_cierres_asientos_propuestos"
TABLA_LOTES = "asientos_bandeja_lotes"
TABLA_EVENTOS_BANDEJA = "asientos_bandeja_eventos"

TIPO_CONTROLADO_BANDEJA = "Controlado por Bandeja"
TIPO_REVERSO_BANDEJA = "Reverso de Bandeja"
TIPO_DIRECTO_TECNICO = "Directo con trazabilidad técnica"
TIPO_DIRECTO_HISTORICO = "Directo / histórico"

TOLERANCIA_CUADRE = 0.01

COLUMNAS_LIBRO_BASE = [
    "id",
    "id_asiento",
    "fecha",
    "cuenta",
    "debe",
    "haber",
    "glosa",
    "origen",
    "archivo",
    "empresa_id",
    "origen_tabla",
    "origen_id",
    "comprobante_clave",
    "estado",
    "usuario_creacion",
    "fecha_creacion",
]

COLUMNAS_TRAZABILIDAD = [
    "empresa_id",
    "id_asiento",
    "fecha",
    "fecha_orden",
    "tipo_trazabilidad",
    "estado_trazabilidad",
    "origen_funcional",
    "origen_tecnico",
    "origen_tabla",
    "origen_id",
    "comprobante_clave",
    "archivo",
    "glosa_resumen",
    "movimientos",
    "cuentas",
    "debe",
    "haber",
    "diferencia",
    "cuadrado",
    "fuente_propuesta",
    "fuente_clave",
    "propuesta_id",
    "propuesta_estado",
    "propuesta_descripcion",
    "propuesta_referencia",
    "propuesta_tipo_asiento",
    "lote_id",
    "lote_accion",
    "lote_estado",
    "lote_fecha",
    "lote_usuario",
    "id_asiento_referenciado",
    "alerta",
]


def _texto(valor: Any, default: str = "") -> str:
    try:
        if valor is None:
            return default
        if isinstance(valor, float) and pd.isna(valor):
            return default
        texto = str(valor).strip()
        return texto if texto else default
    except Exception:
        return default


def _texto_upper(valor: Any, default: str = "") -> str:
    return _texto(valor, default).upper()


def _int(valor: Any, default: int = 0) -> int:
    try:
        if valor is None:
            return default
        if isinstance(valor, str) and valor.strip() == "":
            return default
        if pd.isna(valor):
            return default
        return int(float(valor))
    except Exception:
        return default


def _float(valor: Any, default: float = 0.0) -> float:
    try:
        if valor is None:
            return default
        if isinstance(valor, str) and valor.strip() == "":
            return default
        if pd.isna(valor):
            return default
        return round(float(valor), 2)
    except Exception:
        return default


def _fecha_para_ordenar(valor: Any) -> pd.Timestamp:
    try:
        fecha = pd.to_datetime(valor, errors="coerce", dayfirst=True)
        if pd.isna(fecha):
            return pd.NaT
        return fecha
    except Exception:
        return pd.NaT


def _fecha_iso(valor: Any) -> str:
    if valor is None:
        return ""

    if isinstance(valor, datetime):
        return valor.date().isoformat()

    if isinstance(valor, date):
        return valor.isoformat()

    texto = _texto(valor)
    if not texto:
        return ""

    try:
        fecha = pd.to_datetime(texto, errors="coerce", dayfirst=True)
        if pd.isna(fecha):
            return texto[:10]
        return fecha.strftime("%Y-%m-%d")
    except Exception:
        return texto[:10]


def _tabla_existe(conn, tabla: str) -> bool:
    try:
        fila = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name = ?
            LIMIT 1
            """,
            (tabla,),
        ).fetchone()
        return fila is not None
    except Exception:
        return False


def _columnas_tabla(conn, tabla: str) -> List[str]:
    try:
        filas = conn.execute(f"PRAGMA table_info({tabla})").fetchall()
        return [fila[1] for fila in filas]
    except Exception:
        return []


def _asegurar_columnas(df: pd.DataFrame, columnas: List[str]) -> pd.DataFrame:
    df = pd.DataFrame() if df is None else df.copy()

    for columna in columnas:
        if columna not in df.columns:
            df[columna] = None

    return df


def _leer_tabla_segura(conn, tabla: str, empresa_id: int, columnas_preferidas: Optional[List[str]] = None) -> pd.DataFrame:
    if not _tabla_existe(conn, tabla):
        return pd.DataFrame()

    columnas_disponibles = _columnas_tabla(conn, tabla)
    if not columnas_disponibles:
        return pd.DataFrame()

    if columnas_preferidas:
        columnas = [col for col in columnas_preferidas if col in columnas_disponibles]
    else:
        columnas = columnas_disponibles

    if not columnas:
        return pd.DataFrame()

    where = ""
    params: tuple[Any, ...] = ()

    if "empresa_id" in columnas_disponibles:
        where = "WHERE COALESCE(empresa_id, 1) = ?"
        params = (int(empresa_id),)

    sql = f"SELECT {', '.join(columnas)} FROM {tabla} {where}"
    return pd.read_sql_query(sql, conn, params=params)


def _leer_libro_diario(conn, empresa_id: int) -> pd.DataFrame:
    if not _tabla_existe(conn, TABLA_LIBRO):
        return pd.DataFrame(columns=COLUMNAS_LIBRO_BASE)

    columnas_disponibles = _columnas_tabla(conn, TABLA_LIBRO)
    columnas = [col for col in COLUMNAS_LIBRO_BASE if col in columnas_disponibles]

    if not columnas:
        return pd.DataFrame(columns=COLUMNAS_LIBRO_BASE)

    where = ""
    params: tuple[Any, ...] = ()

    if "empresa_id" in columnas_disponibles:
        where = "WHERE COALESCE(empresa_id, 1) = ?"
        params = (int(empresa_id),)

    sql = f"SELECT {', '.join(columnas)} FROM {TABLA_LIBRO} {where}"
    df = pd.read_sql_query(sql, conn, params=params)
    df = _asegurar_columnas(df, COLUMNAS_LIBRO_BASE)

    if df.empty:
        return df

    df["empresa_id"] = df["empresa_id"].apply(lambda x: _int(x, int(empresa_id)) or int(empresa_id))
    df["id_asiento"] = df["id_asiento"].apply(_int)
    df["debe"] = df["debe"].apply(_float)
    df["haber"] = df["haber"].apply(_float)
    df["fecha_orden"] = df["fecha"].apply(_fecha_para_ordenar)

    return df


def _leer_lotes(conn, empresa_id: int) -> pd.DataFrame:
    columnas = [
        "id",
        "empresa_id",
        "accion",
        "estado",
        "cantidad_solicitada",
        "cantidad_procesada",
        "cantidad_error",
        "total_debe",
        "total_haber",
        "diferencia",
        "detalle",
        "usuario",
        "fecha_lote",
    ]
    df = _leer_tabla_segura(conn, TABLA_LOTES, empresa_id, columnas)
    df = _asegurar_columnas(df, columnas)

    if not df.empty:
        df["id"] = df["id"].apply(_int)

    return df


def _lote_por_id(lotes: pd.DataFrame, lote_id: Any) -> Dict[str, Any]:
    lid = _int(lote_id)
    if lid <= 0 or lotes is None or lotes.empty or "id" not in lotes.columns:
        return {}

    fila = lotes[lotes["id"].apply(_int) == lid]
    if fila.empty:
        return {}

    return fila.iloc[0].to_dict()


def _normalizar_propuestas_centrales(conn, empresa_id: int, lotes: pd.DataFrame) -> pd.DataFrame:
    columnas = [
        "id",
        "empresa_id",
        "ejercicio_id",
        "fecha",
        "origen",
        "origen_tabla",
        "origen_id",
        "tipo_asiento",
        "referencia",
        "descripcion",
        "estado",
        "total_debe",
        "total_haber",
        "diferencia",
        "id_asiento_libro_diario",
        "id_asiento_reversion_libro_diario",
        "fecha_contabilizacion",
        "fecha_reversion",
        "usuario_contabilizacion",
        "usuario_reversion",
        "lote_contabilizacion_id",
        "lote_reversion_id",
    ]

    df = _leer_tabla_segura(conn, TABLA_PROPUESTOS, empresa_id, columnas)
    df = _asegurar_columnas(df, columnas)

    if df.empty:
        return pd.DataFrame()

    registros: List[Dict[str, Any]] = []

    for _, fila in df.iterrows():
        propuesta_id = _int(fila.get("id"))
        fuente_clave = f"CENTRAL:{propuesta_id}"
        comun = {
            "fuente_propuesta": "CENTRAL",
            "fuente_clave": fuente_clave,
            "propuesta_id": propuesta_id,
            "propuesta_estado": _texto_upper(fila.get("estado")),
            "propuesta_descripcion": _texto(fila.get("descripcion")),
            "propuesta_referencia": _texto(fila.get("referencia")),
            "propuesta_tipo_asiento": _texto_upper(fila.get("tipo_asiento")),
            "origen_bandeja": _texto_upper(fila.get("origen")),
            "origen_tabla_bandeja": _texto(fila.get("origen_tabla")),
            "origen_id_bandeja": _int(fila.get("origen_id")),
        }

        id_asiento = _int(fila.get("id_asiento_libro_diario"))
        if id_asiento > 0:
            lote_id = _int(fila.get("lote_contabilizacion_id"))
            lote = _lote_por_id(lotes, lote_id)
            registros.append({
                **comun,
                "id_asiento": id_asiento,
                "tipo_vinculo_bandeja": "CONTABILIZACION",
                "lote_id": lote_id or None,
                "lote_accion": _texto(lote.get("accion")),
                "lote_estado": _texto(lote.get("estado")),
                "lote_fecha": lote.get("fecha_lote"),
                "lote_usuario": _texto(lote.get("usuario")),
                "id_asiento_referenciado": None,
            })

        id_reversion = _int(fila.get("id_asiento_reversion_libro_diario"))
        if id_reversion > 0:
            lote_id = _int(fila.get("lote_reversion_id"))
            lote = _lote_por_id(lotes, lote_id)
            registros.append({
                **comun,
                "id_asiento": id_reversion,
                "tipo_vinculo_bandeja": "REVERSO",
                "lote_id": lote_id or None,
                "lote_accion": _texto(lote.get("accion")),
                "lote_estado": _texto(lote.get("estado")),
                "lote_fecha": lote.get("fecha_lote"),
                "lote_usuario": _texto(lote.get("usuario")),
                "id_asiento_referenciado": id_asiento or None,
            })

    return pd.DataFrame(registros)


def _normalizar_propuestas_iva(conn, empresa_id: int, lotes: pd.DataFrame) -> pd.DataFrame:
    columnas = [
        "id",
        "empresa_id",
        "cierre_id",
        "pago_id",
        "anio",
        "mes",
        "periodo",
        "fecha",
        "tipo_asiento",
        "estado",
        "debe",
        "haber",
        "id_asiento_libro_diario",
        "id_asiento_reversion_libro_diario",
        "fecha_contabilizacion",
        "fecha_reversion",
        "usuario_contabilizacion",
        "usuario_reversion",
        "lote_contabilizacion_id",
        "lote_reversion_id",
    ]

    df = _leer_tabla_segura(conn, TABLA_IVA_PROPUESTOS, empresa_id, columnas)
    df = _asegurar_columnas(df, columnas)

    if df.empty:
        return pd.DataFrame()

    registros: List[Dict[str, Any]] = []
    df = df.copy()
    df["pago_id_norm"] = df["pago_id"].apply(_int)
    df["tipo_asiento_norm"] = df["tipo_asiento"].apply(_texto_upper)
    df["cierre_id_norm"] = df["cierre_id"].apply(_int)

    grupos = df.groupby(["cierre_id_norm", "pago_id_norm", "tipo_asiento_norm"], dropna=False)

    for (cierre_id, pago_id, tipo_asiento), grupo in grupos:
        primera = grupo.iloc[0].to_dict()
        cierre_id = _int(cierre_id)
        pago_id = _int(pago_id)
        tipo_asiento = _texto_upper(tipo_asiento)
        fuente_clave = f"IVA:{cierre_id}:{pago_id}:{tipo_asiento}"
        periodo = _texto(primera.get("periodo"))
        origen = "IVA_PAGO" if pago_id > 0 or "PAGO" in tipo_asiento else "IVA_CIERRE"
        estados = grupo["estado"].fillna("").astype(str).str.upper().unique().tolist()
        estado = estados[0] if len(estados) == 1 else "MIXTO"

        comun = {
            "fuente_propuesta": "IVA",
            "fuente_clave": fuente_clave,
            "propuesta_id": _int(primera.get("id")),
            "propuesta_estado": estado,
            "propuesta_descripcion": f"{'Pago IVA' if origen == 'IVA_PAGO' else 'Liquidación / ajuste IVA'} período {periodo}",
            "propuesta_referencia": f"{'Pago IVA' if origen == 'IVA_PAGO' else 'Cierre IVA'} #{pago_id if origen == 'IVA_PAGO' else cierre_id}",
            "propuesta_tipo_asiento": tipo_asiento,
            "origen_bandeja": origen,
            "origen_tabla_bandeja": TABLA_IVA_PROPUESTOS,
            "origen_id_bandeja": cierre_id,
        }

        id_asientos = sorted({_int(v) for v in grupo["id_asiento_libro_diario"].tolist() if _int(v) > 0})
        for id_asiento in id_asientos:
            fila_lote = grupo[group_mask_int(grupo, "id_asiento_libro_diario", id_asiento)].iloc[0].to_dict()
            lote_id = _int(fila_lote.get("lote_contabilizacion_id"))
            lote = _lote_por_id(lotes, lote_id)
            registros.append({
                **comun,
                "id_asiento": id_asiento,
                "tipo_vinculo_bandeja": "CONTABILIZACION",
                "lote_id": lote_id or None,
                "lote_accion": _texto(lote.get("accion")),
                "lote_estado": _texto(lote.get("estado")),
                "lote_fecha": lote.get("fecha_lote"),
                "lote_usuario": _texto(lote.get("usuario")),
                "id_asiento_referenciado": None,
            })

        id_reversiones = sorted({_int(v) for v in grupo["id_asiento_reversion_libro_diario"].tolist() if _int(v) > 0})
        id_original = id_asientos[0] if id_asientos else None
        for id_asiento in id_reversiones:
            fila_lote = grupo[group_mask_int(grupo, "id_asiento_reversion_libro_diario", id_asiento)].iloc[0].to_dict()
            lote_id = _int(fila_lote.get("lote_reversion_id"))
            lote = _lote_por_id(lotes, lote_id)
            registros.append({
                **comun,
                "id_asiento": id_asiento,
                "tipo_vinculo_bandeja": "REVERSO",
                "lote_id": lote_id or None,
                "lote_accion": _texto(lote.get("accion")),
                "lote_estado": _texto(lote.get("estado")),
                "lote_fecha": lote.get("fecha_lote"),
                "lote_usuario": _texto(lote.get("usuario")),
                "id_asiento_referenciado": id_original,
            })

    return pd.DataFrame(registros)


def group_mask_int(df: pd.DataFrame, columna: str, valor: int) -> pd.Series:
    if columna not in df.columns:
        return pd.Series([False] * len(df), index=df.index)
    return df[columna].apply(_int) == int(valor)


def _mapa_vinculos_bandeja(conn, empresa_id: int) -> Dict[int, Dict[str, Any]]:
    lotes = _leer_lotes(conn, empresa_id)
    partes = [
        _normalizar_propuestas_centrales(conn, empresa_id, lotes),
        _normalizar_propuestas_iva(conn, empresa_id, lotes),
    ]

    partes_validas = [p for p in partes if p is not None and not p.empty]
    if not partes_validas:
        return {}

    df = pd.concat(partes_validas, ignore_index=True)

    if df.empty:
        return {}

    mapa: Dict[int, Dict[str, Any]] = {}

    for _, fila in df.iterrows():
        id_asiento = _int(fila.get("id_asiento"))
        if id_asiento <= 0:
            continue

        actual = mapa.get(id_asiento)
        registro = {k: (None if pd.isna(v) else v) for k, v in fila.to_dict().items()}

        if actual is None:
            mapa[id_asiento] = registro
            continue

        if actual.get("tipo_vinculo_bandeja") != "REVERSO" and registro.get("tipo_vinculo_bandeja") == "REVERSO":
            mapa[id_asiento] = registro

    return mapa


def _origen_funcional(origen: Any, origen_tabla: Any, comprobante_clave: Any, archivo: Any) -> str:
    texto = " ".join([
        _texto(origen),
        _texto(origen_tabla),
        _texto(comprobante_clave),
        _texto(archivo),
    ]).upper()

    reglas = [
        ("VENTA", "Ventas"),
        ("COMPR", "Compras"),
        ("COBRAN", "Cobranzas"),
        ("RECIBO", "Cobranzas"),
        ("PAGO", "Pagos"),
        ("BANCO", "Banco/Caja"),
        ("BANC", "Banco/Caja"),
        ("CAJA", "Caja"),
        ("TESOR", "Tesorería"),
        ("CONCILI", "Conciliación"),
        ("IVA", "IVA"),
        ("CAPITAL", "Inicio contable"),
        ("APERTURA", "Inicio contable"),
        ("ASIENTOS_ORIGEN", "Inicio contable"),
        ("CENTRAL:", "Bandeja"),
    ]

    for patron, etiqueta in reglas:
        if patron in texto:
            return etiqueta

    if _texto(origen) or _texto(origen_tabla):
        return "Origen técnico"

    return "Histórico / manual"


def _tipo_trazabilidad(grupo: pd.DataFrame, vinculo: Optional[Dict[str, Any]]) -> str:
    if vinculo:
        if _texto_upper(vinculo.get("tipo_vinculo_bandeja")) == "REVERSO":
            return TIPO_REVERSO_BANDEJA
        return TIPO_CONTROLADO_BANDEJA

    claves = grupo.get("comprobante_clave")
    if claves is not None:
        texto_claves = " ".join(claves.dropna().astype(str).tolist()).upper()
        if texto_claves.startswith("REVERSO:") or "REVERSO:" in texto_claves:
            return TIPO_DIRECTO_TECNICO

    origen_tabla = " ".join(grupo.get("origen_tabla", pd.Series(dtype=str)).dropna().astype(str).tolist())
    comprobante = " ".join(grupo.get("comprobante_clave", pd.Series(dtype=str)).dropna().astype(str).tolist())
    origen_id = [_int(v) for v in grupo.get("origen_id", pd.Series(dtype=object)).tolist()]

    if _texto(origen_tabla) or _texto(comprobante) or any(v > 0 for v in origen_id):
        return TIPO_DIRECTO_TECNICO

    return TIPO_DIRECTO_HISTORICO


def _estado_trazabilidad(tipo: str, diferencia: float) -> str:
    if abs(diferencia) > TOLERANCIA_CUADRE:
        return "REVISAR_DESCUADRE"
    if tipo == TIPO_CONTROLADO_BANDEJA:
        return "TRAZABLE_BANDEJA"
    if tipo == TIPO_REVERSO_BANDEJA:
        return "REVERSO_TRAZABLE"
    if tipo == TIPO_DIRECTO_TECNICO:
        return "DIRECTO_CON_ORIGEN"
    return "DIRECTO_HISTORICO"


def _alerta_trazabilidad(tipo: str, diferencia: float, movimientos: int, tiene_fecha: bool) -> str:
    alertas = []

    if abs(diferencia) > TOLERANCIA_CUADRE:
        alertas.append("Asiento descuadrado")
    if movimientos < 2:
        alertas.append("Asiento con una sola línea")
    if not tiene_fecha:
        alertas.append("Sin fecha válida")
    if tipo == TIPO_DIRECTO_HISTORICO:
        alertas.append("Sin vínculo de origen controlado")

    return " · ".join(alertas)


def _armar_resumen_asientos(libro: pd.DataFrame, vinculos: Dict[int, Dict[str, Any]]) -> pd.DataFrame:
    if libro.empty:
        return pd.DataFrame(columns=COLUMNAS_TRAZABILIDAD)

    registros: List[Dict[str, Any]] = []

    for id_asiento, grupo in libro.groupby("id_asiento", dropna=False, sort=False):
        id_asiento_int = _int(id_asiento)
        if id_asiento_int <= 0:
            continue

        grupo = grupo.copy()
        grupo["debe"] = grupo["debe"].apply(_float)
        grupo["haber"] = grupo["haber"].apply(_float)

        total_debe = round(float(grupo["debe"].sum()), 2)
        total_haber = round(float(grupo["haber"].sum()), 2)
        diferencia = round(total_debe - total_haber, 2)
        fecha_orden = grupo["fecha_orden"].dropna().min() if "fecha_orden" in grupo.columns else pd.NaT
        fecha = _fecha_iso(fecha_orden) if not pd.isna(fecha_orden) else _fecha_iso(grupo["fecha"].dropna().iloc[0] if not grupo["fecha"].dropna().empty else "")

        origenes = sorted({v for v in grupo["origen"].fillna("").astype(str).str.strip().tolist() if v})
        origen_tablas = sorted({v for v in grupo["origen_tabla"].fillna("").astype(str).str.strip().tolist() if v})
        origen_ids = sorted({_int(v) for v in grupo["origen_id"].tolist() if _int(v) > 0})
        comprobantes = sorted({v for v in grupo["comprobante_clave"].fillna("").astype(str).str.strip().tolist() if v})
        archivos = sorted({v for v in grupo["archivo"].fillna("").astype(str).str.strip().tolist() if v})
        glosas = [v for v in grupo["glosa"].fillna("").astype(str).str.strip().tolist() if v]
        cuentas = sorted({v for v in grupo["cuenta"].fillna("").astype(str).str.strip().tolist() if v})

        vinculo = vinculos.get(id_asiento_int)
        tipo = _tipo_trazabilidad(grupo, vinculo)
        origen_funcional = _origen_funcional(
            " | ".join(origenes),
            " | ".join(origen_tablas),
            " | ".join(comprobantes),
            " | ".join(archivos),
        )

        if vinculo and _texto(vinculo.get("origen_bandeja")):
            origen_funcional = _origen_funcional(
                vinculo.get("origen_bandeja"),
                vinculo.get("origen_tabla_bandeja"),
                vinculo.get("fuente_clave"),
                "",
            )

        registro = {
            "empresa_id": _int(grupo["empresa_id"].iloc[0], 1),
            "id_asiento": id_asiento_int,
            "fecha": fecha,
            "fecha_orden": fecha_orden,
            "tipo_trazabilidad": tipo,
            "estado_trazabilidad": _estado_trazabilidad(tipo, diferencia),
            "origen_funcional": origen_funcional,
            "origen_tecnico": " | ".join(origenes),
            "origen_tabla": " | ".join(origen_tablas),
            "origen_id": " | ".join(str(v) for v in origen_ids),
            "comprobante_clave": " | ".join(comprobantes),
            "archivo": " | ".join(archivos),
            "glosa_resumen": glosas[0] if glosas else "",
            "movimientos": int(len(grupo)),
            "cuentas": int(len(cuentas)),
            "debe": total_debe,
            "haber": total_haber,
            "diferencia": diferencia,
            "cuadrado": abs(diferencia) <= TOLERANCIA_CUADRE,
            "fuente_propuesta": "",
            "fuente_clave": "",
            "propuesta_id": None,
            "propuesta_estado": "",
            "propuesta_descripcion": "",
            "propuesta_referencia": "",
            "propuesta_tipo_asiento": "",
            "lote_id": None,
            "lote_accion": "",
            "lote_estado": "",
            "lote_fecha": None,
            "lote_usuario": "",
            "id_asiento_referenciado": None,
        }

        if vinculo:
            for campo in [
                "fuente_propuesta",
                "fuente_clave",
                "propuesta_id",
                "propuesta_estado",
                "propuesta_descripcion",
                "propuesta_referencia",
                "propuesta_tipo_asiento",
                "lote_id",
                "lote_accion",
                "lote_estado",
                "lote_fecha",
                "lote_usuario",
                "id_asiento_referenciado",
            ]:
                registro[campo] = vinculo.get(campo)

        registro["alerta"] = _alerta_trazabilidad(
            tipo,
            diferencia,
            int(len(grupo)),
            bool(fecha),
        )

        registros.append(registro)

    df = pd.DataFrame(registros)
    df = _asegurar_columnas(df, COLUMNAS_TRAZABILIDAD)

    if df.empty:
        return df[COLUMNAS_TRAZABILIDAD].copy()

    return df.sort_values(
        ["fecha_orden", "id_asiento"],
        ascending=[False, False],
        na_position="last",
    ).reset_index(drop=True)[COLUMNAS_TRAZABILIDAD].copy()


def _aplicar_filtros(
    df: pd.DataFrame,
    *,
    fecha_desde: Optional[Any] = None,
    fecha_hasta: Optional[Any] = None,
    origen_funcional: Optional[str] = None,
    tipo_trazabilidad: Optional[str] = None,
    solo_descuadrados: bool = False,
    busqueda: Optional[str] = None,
) -> pd.DataFrame:
    if df.empty:
        return df

    resultado = df.copy()

    desde = _fecha_iso(fecha_desde)
    hasta = _fecha_iso(fecha_hasta)

    if desde:
        resultado = resultado[resultado["fecha"].fillna("") >= desde].copy()

    if hasta:
        resultado = resultado[resultado["fecha"].fillna("") <= hasta].copy()

    if origen_funcional and _texto(origen_funcional).upper() not in {"TODOS", "TODAS"}:
        resultado = resultado[resultado["origen_funcional"].fillna("").astype(str) == _texto(origen_funcional)].copy()

    if tipo_trazabilidad and _texto(tipo_trazabilidad).upper() not in {"TODOS", "TODAS"}:
        resultado = resultado[resultado["tipo_trazabilidad"].fillna("").astype(str) == _texto(tipo_trazabilidad)].copy()

    if solo_descuadrados:
        resultado = resultado[resultado["cuadrado"] == False].copy()

    patron = _texto(busqueda).lower()
    if patron:
        columnas_busqueda = [
            "id_asiento",
            "origen_funcional",
            "origen_tecnico",
            "origen_tabla",
            "comprobante_clave",
            "archivo",
            "glosa_resumen",
            "fuente_clave",
            "propuesta_descripcion",
            "propuesta_referencia",
        ]
        mascara = pd.Series(False, index=resultado.index)
        for columna in columnas_busqueda:
            if columna in resultado.columns:
                mascara = mascara | resultado[columna].fillna("").astype(str).str.lower().str.contains(patron, na=False)
        resultado = resultado[mascara].copy()

    return resultado.reset_index(drop=True)


def listar_trazabilidad_libro_diario(
    empresa_id: int = 1,
    fecha_desde: Optional[Any] = None,
    fecha_hasta: Optional[Any] = None,
    origen_funcional: Optional[str] = None,
    tipo_trazabilidad: Optional[str] = None,
    solo_descuadrados: bool = False,
    busqueda: Optional[str] = None,
) -> pd.DataFrame:
    conn = conectar()

    try:
        libro = _leer_libro_diario(conn, int(empresa_id))
        vinculos = _mapa_vinculos_bandeja(conn, int(empresa_id))
    finally:
        conn.close()

    resumen = _armar_resumen_asientos(libro, vinculos)

    return _aplicar_filtros(
        resumen,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        origen_funcional=origen_funcional,
        tipo_trazabilidad=tipo_trazabilidad,
        solo_descuadrados=solo_descuadrados,
        busqueda=busqueda,
    )


def obtener_resumen_trazabilidad_libro_diario(empresa_id: int = 1) -> Dict[str, Any]:
    df = listar_trazabilidad_libro_diario(empresa_id=int(empresa_id))

    if df.empty:
        return {
            "empresa_id": int(empresa_id),
            "total_asientos": 0,
            "total_lineas": 0,
            "controlados_bandeja": 0,
            "reversos_bandeja": 0,
            "directos_tecnicos": 0,
            "directos_historicos": 0,
            "descuadrados": 0,
            "total_debe": 0.0,
            "total_haber": 0.0,
            "diferencia": 0.0,
        }

    def contar_tipo(tipo: str) -> int:
        return int((df["tipo_trazabilidad"].fillna("").astype(str) == tipo).sum())

    total_debe = round(float(pd.to_numeric(df["debe"], errors="coerce").fillna(0.0).sum()), 2)
    total_haber = round(float(pd.to_numeric(df["haber"], errors="coerce").fillna(0.0).sum()), 2)

    return {
        "empresa_id": int(empresa_id),
        "total_asientos": int(len(df)),
        "total_lineas": int(pd.to_numeric(df["movimientos"], errors="coerce").fillna(0).sum()),
        "controlados_bandeja": contar_tipo(TIPO_CONTROLADO_BANDEJA),
        "reversos_bandeja": contar_tipo(TIPO_REVERSO_BANDEJA),
        "directos_tecnicos": contar_tipo(TIPO_DIRECTO_TECNICO),
        "directos_historicos": contar_tipo(TIPO_DIRECTO_HISTORICO),
        "descuadrados": int((df["cuadrado"] == False).sum()),
        "total_debe": total_debe,
        "total_haber": total_haber,
        "diferencia": round(total_debe - total_haber, 2),
    }


def obtener_detalle_asiento_libro_diario(empresa_id: int, id_asiento: int) -> Dict[str, Any]:
    conn = conectar()

    try:
        libro = _leer_libro_diario(conn, int(empresa_id))
        vinculos = _mapa_vinculos_bandeja(conn, int(empresa_id))

        detalle = libro[libro["id_asiento"].apply(_int) == int(id_asiento)].copy()
        resumen = _armar_resumen_asientos(detalle, vinculos)

        eventos = pd.DataFrame()
        fuente_clave = ""
        if not resumen.empty:
            fuente_clave = _texto(resumen.iloc[0].get("fuente_clave"))

        if fuente_clave and _tabla_existe(conn, TABLA_EVENTOS_BANDEJA):
            eventos = pd.read_sql_query(
                f"""
                SELECT *
                FROM {TABLA_EVENTOS_BANDEJA}
                WHERE fuente_clave = ?
                ORDER BY fecha_evento DESC, id DESC
                """,
                conn,
                params=(fuente_clave,),
            )

    finally:
        conn.close()

    if detalle.empty:
        return {
            "ok": False,
            "mensaje": "No se encontró el asiento en Libro Diario.",
            "resumen": {},
            "detalle": pd.DataFrame(),
            "eventos": pd.DataFrame(),
        }

    detalle = detalle.sort_values(["id_asiento", "id"], ascending=[True, True]).reset_index(drop=True)

    return {
        "ok": True,
        "mensaje": "Asiento encontrado.",
        "resumen": resumen.iloc[0].to_dict() if not resumen.empty else {},
        "detalle": detalle,
        "eventos": eventos,
    }


def listar_opciones_origen_funcional(empresa_id: int = 1) -> List[str]:
    df = listar_trazabilidad_libro_diario(empresa_id=int(empresa_id))
    if df.empty or "origen_funcional" not in df.columns:
        return []
    return sorted({v for v in df["origen_funcional"].dropna().astype(str).tolist() if v})


def listar_opciones_tipo_trazabilidad(empresa_id: int = 1) -> List[str]:
    df = listar_trazabilidad_libro_diario(empresa_id=int(empresa_id))
    if df.empty or "tipo_trazabilidad" not in df.columns:
        return []
    orden = [
        TIPO_CONTROLADO_BANDEJA,
        TIPO_REVERSO_BANDEJA,
        TIPO_DIRECTO_TECNICO,
        TIPO_DIRECTO_HISTORICO,
    ]
    existentes = {v for v in df["tipo_trazabilidad"].dropna().astype(str).tolist() if v}
    return [tipo for tipo in orden if tipo in existentes] + sorted(existentes.difference(orden))


__all__ = [
    "TIPO_CONTROLADO_BANDEJA",
    "TIPO_REVERSO_BANDEJA",
    "TIPO_DIRECTO_TECNICO",
    "TIPO_DIRECTO_HISTORICO",
    "listar_trazabilidad_libro_diario",
    "obtener_resumen_trazabilidad_libro_diario",
    "obtener_detalle_asiento_libro_diario",
    "listar_opciones_origen_funcional",
    "listar_opciones_tipo_trazabilidad",
]