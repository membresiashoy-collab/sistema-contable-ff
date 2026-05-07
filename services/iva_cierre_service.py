import json
from datetime import date, datetime

import pandas as pd

from database import conectar, ejecutar_query
from services.iva_service import calcular_posicion_iva_periodo, obtener_periodos_disponibles_iva

try:
    from services.iva_movimientos_fiscales_service import (
        ESTADO_BORRADOR,
        ESTADO_CONFIRMADO,
        asegurar_estructura_iva_movimientos_fiscales,
        listar_movimientos_fiscales,
        registrar_movimiento_fiscal,
        anular_movimiento_fiscal,
    )
except Exception:  # pragma: no cover - compatibilidad con bases parciales
    ESTADO_BORRADOR = "BORRADOR"
    ESTADO_CONFIRMADO = "CONFIRMADO"
    asegurar_estructura_iva_movimientos_fiscales = None
    listar_movimientos_fiscales = None
    registrar_movimiento_fiscal = None
    anular_movimiento_fiscal = None


# ======================================================
# IVA PRO - CIERRE MENSUAL OPERATIVO V3
# ======================================================
#
# Este servicio NO presenta IVA en ARCA.
# Este servicio NO genera TXT Portal IVA ni Libro IVA Digital.
# Este servicio NO impacta automáticamente Libro Diario.
#
# Objetivo v3:
# - Guardar cierres versionados: Original / Rectificativa 1 / Rectificativa 2.
# - Mantener cierre cronológico y trazabilidad.
# - Determinar saldo a pagar, saldo a favor y saldo técnico trasladable.
# - Registrar pagos posteriores del saldo IVA a pagar.
# - Generar asientos contables propuestos de liquidación, pago y ajuste.
# - Mostrar impacto de rectificativas sobre saldos trasladados.
# - No recalcular silenciosamente períodos posteriores: se marcan para revisión.
# - Dejar obligaciones IVA consultables para reportes y futuro asistente IA.

TABLA_CIERRES = "iva_cierres_periodos"
TABLA_EVENTOS = "iva_cierres_periodos_eventos"
TABLA_PAGOS = "iva_cierres_pagos"
TABLA_ASIENTOS = "iva_cierres_asientos_propuestos"

ESTADO_CIERRE_ABIERTO = "ABIERTO"
ESTADO_CIERRE_CERRADO = "CERRADO"
ESTADO_CIERRE_REABIERTO = "REABIERTO"
ESTADO_CIERRE_RECTIFICADO = "RECTIFICADO"
ESTADO_CIERRE_REQUIERE_REVISION = "REQUIERE_REVISION"
ESTADO_CIERRE_ANULADO_TECNICO = "ANULADO_TECNICO"

VERSION_TIPO_ORIGINAL = "ORIGINAL"
VERSION_TIPO_RECTIFICATIVA = "RECTIFICATIVA"

RESULTADO_A_PAGAR = "A_PAGAR"
RESULTADO_A_FAVOR = "A_FAVOR"
RESULTADO_CERO = "CERO"

ESTADO_PAGO_NO_APLICA = "NO_APLICA"
ESTADO_PAGO_PENDIENTE = "PENDIENTE"
ESTADO_PAGO_PARCIAL = "PARCIAL"
ESTADO_PAGO_PAGADO = "PAGADO"

ESTADO_PAGO_REGISTRADO = "REGISTRADO"
ESTADO_PAGO_ANULADO = "ANULADO"
ESTADO_PAGO_RECTIFICADO = "RECTIFICADO"

TIPO_ASIENTO_LIQUIDACION = "LIQUIDACION_IVA"
TIPO_ASIENTO_PAGO = "PAGO_IVA"
TIPO_ASIENTO_RECTIFICATIVA = "AJUSTE_RECTIFICATIVA_IVA"

TOLERANCIA = 0.05

CUENTAS_IVA_DEFAULT = {
    "iva_debito_fiscal": ("2.1.01", "IVA débito fiscal"),
    "credito_fiscal_computable": ("1.1.21", "IVA crédito fiscal"),
    "percepciones_iva_sufridas": ("1.1.22", "Percepciones IVA sufridas"),
    "retenciones_iva_sufridas": ("1.1.23", "Retenciones IVA sufridas"),
    "saldo_tecnico_anterior": ("1.1.24", "IVA saldo técnico anterior aplicado"),
    "saldo_libre_disponibilidad": ("1.1.25", "IVA saldo libre disponibilidad aplicado"),
    "pago_a_cuenta": ("1.1.26", "IVA pagos a cuenta aplicados"),
    "iva_a_pagar": ("2.1.20", "IVA a pagar"),
    "saldo_a_favor_iva": ("1.1.27", "Saldo a favor IVA"),
    "ajuste_rectificativa_iva": ("5.9.90", "Ajuste fiscal por rectificativa IVA"),
    "caja": ("1.1.01", "Caja"),
    "banco": ("1.1.02", "Banco"),
    "tesoreria_puente": ("1.1.99", "Tesorería / cuenta puente"),
}

MEDIOS_PAGO_CUENTA_DEFAULT = {
    "BANCO": CUENTAS_IVA_DEFAULT["banco"],
    "TRANSFERENCIA": CUENTAS_IVA_DEFAULT["banco"],
    "DEBITO_AUTOMATICO": CUENTAS_IVA_DEFAULT["banco"],
    "EFECTIVO": CUENTAS_IVA_DEFAULT["caja"],
    "CAJA": CUENTAS_IVA_DEFAULT["caja"],
    "MANUAL": CUENTAS_IVA_DEFAULT["tesoreria_puente"],
    "OTRO": CUENTAS_IVA_DEFAULT["tesoreria_puente"],
}


def _int(valor, default=0):
    try:
        if valor is None:
            return default
        if isinstance(valor, str) and valor.strip() == "":
            return default
        return int(float(valor))
    except Exception:
        return default


def _float(valor, default=0.0):
    try:
        if valor is None:
            return default
        if isinstance(valor, str) and valor.strip() == "":
            return default
        return round(float(valor), 2)
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


def _periodo_texto(anio, mes):
    anio = _int(anio)
    mes = _int(mes)
    if anio <= 0 or mes <= 0:
        return ""
    return f"{anio}-{mes:02d}"


def _periodo_orden(anio, mes):
    return _int(anio) * 100 + _int(mes)


def _siguiente_periodo(anio, mes):
    anio = _int(anio)
    mes = _int(mes)
    if mes >= 12:
        return anio + 1, 1
    return anio, mes + 1


def _fecha_texto(valor=None):
    if valor is None:
        return date.today().isoformat()
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    texto = _texto(valor)
    return texto or date.today().isoformat()


def _resultado_a_dataframe(resultado):
    if isinstance(resultado, pd.DataFrame):
        return resultado.copy()
    if resultado is None:
        return pd.DataFrame()
    try:
        return pd.DataFrame(resultado)
    except Exception:
        return pd.DataFrame()


def _json_seguro(valor):
    if isinstance(valor, pd.DataFrame):
        valor = valor.to_dict(orient="records")
    try:
        return json.dumps(valor, ensure_ascii=False, default=str)
    except Exception:
        return json.dumps(str(valor), ensure_ascii=False)


def _desde_json(valor, default=None):
    if default is None:
        default = []
    if not valor:
        return default
    try:
        return json.loads(valor)
    except Exception:
        return default


def _columnas_lista(conn, tabla):
    try:
        df = pd.read_sql_query(f"PRAGMA table_info({tabla})", conn)
        if df.empty or "name" not in df.columns:
            return []
        return df["name"].astype(str).tolist()
    except Exception:
        return []


def _columnas_tabla(conn, tabla):
    return set(_columnas_lista(conn, tabla))


def _tabla_existe_conn(conn, tabla):
    try:
        df = pd.read_sql_query(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name = ?
            """,
            conn,
            params=(tabla,),
        )
        return not df.empty
    except Exception:
        return False


def _tiene_unique_periodo_viejo(conn):
    if not _tabla_existe_conn(conn, TABLA_CIERRES):
        return False
    try:
        idxs = pd.read_sql_query(f"PRAGMA index_list({TABLA_CIERRES})", conn)
        if idxs.empty:
            return False
        for _, idx in idxs.iterrows():
            if _int(idx.get("unique")) != 1:
                continue
            nombre_idx = idx.get("name")
            info = pd.read_sql_query(f"PRAGMA index_info({nombre_idx})", conn)
            cols = info["name"].astype(str).tolist() if not info.empty and "name" in info.columns else []
            if cols == ["empresa_id", "anio", "mes"]:
                return True
        return False
    except Exception:
        return False


def _crear_tabla_cierres_base(cur):
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLA_CIERRES} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER NOT NULL,
            anio INTEGER NOT NULL,
            mes INTEGER NOT NULL,
            periodo TEXT NOT NULL,

            estado TEXT NOT NULL DEFAULT 'CERRADO',
            version_tipo TEXT NOT NULL DEFAULT 'ORIGINAL',
            numero_rectificativa INTEGER NOT NULL DEFAULT 0,
            version_etiqueta TEXT NOT NULL DEFAULT 'Original',
            es_version_vigente INTEGER NOT NULL DEFAULT 1,
            cierre_anterior_id INTEGER,
            motivo_rectificativa TEXT,

            requiere_revision_por_rectificativa INTEGER NOT NULL DEFAULT 0,
            cierre_origen_revision_id INTEGER,
            motivo_revision TEXT,

            iva_debito_fiscal REAL NOT NULL DEFAULT 0,
            credito_fiscal_computable REAL NOT NULL DEFAULT 0,
            iva_no_computable REAL NOT NULL DEFAULT 0,
            percepciones_iva_sufridas REAL NOT NULL DEFAULT 0,
            retenciones_iva_sufridas REAL NOT NULL DEFAULT 0,
            saldo_tecnico_anterior REAL NOT NULL DEFAULT 0,
            saldo_libre_disponibilidad REAL NOT NULL DEFAULT 0,
            pago_a_cuenta REAL NOT NULL DEFAULT 0,
            saldo_tecnico_iva REAL NOT NULL DEFAULT 0,
            saldo_preliminar_periodo REAL NOT NULL DEFAULT 0,

            saldo_tecnico_a_favor_trasladable REAL NOT NULL DEFAULT 0,
            saldo_trasladado_al_siguiente REAL NOT NULL DEFAULT 0,
            saldo_trasladado_original REAL NOT NULL DEFAULT 0,
            saldo_trasladado_rectificado REAL NOT NULL DEFAULT 0,
            diferencia_saldo_trasladado REAL NOT NULL DEFAULT 0,
            periodo_siguiente_afectado TEXT,
            impacto_rectificativa_json TEXT,

            resultado_saldo TEXT NOT NULL DEFAULT 'CERO',
            saldo_a_pagar REAL NOT NULL DEFAULT 0,
            saldo_a_favor REAL NOT NULL DEFAULT 0,
            importe_pagado REAL NOT NULL DEFAULT 0,
            saldo_pendiente_pago REAL NOT NULL DEFAULT 0,
            estado_pago TEXT NOT NULL DEFAULT 'NO_APLICA',
            fecha_ultimo_pago TEXT,

            neto_ventas REAL NOT NULL DEFAULT 0,
            total_ventas REAL NOT NULL DEFAULT 0,
            neto_compras REAL NOT NULL DEFAULT 0,
            total_compras REAL NOT NULL DEFAULT 0,
            total_movimientos_fiscales REAL NOT NULL DEFAULT 0,

            cantidad_ventas INTEGER NOT NULL DEFAULT 0,
            cantidad_compras INTEGER NOT NULL DEFAULT 0,
            cantidad_movimientos_fiscales INTEGER NOT NULL DEFAULT 0,

            posicion_json TEXT,
            resumen_origenes_json TEXT,
            alertas_json TEXT,
            indicadores_json TEXT,

            observacion_cierre TEXT,
            usuario_cierre TEXT,
            fecha_cierre TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            motivo_reapertura TEXT,
            usuario_reapertura TEXT,
            fecha_reapertura TIMESTAMP,

            fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _reconstruir_tabla_cierres_si_esquema_viejo(conn, cur):
    if not _tabla_existe_conn(conn, TABLA_CIERRES):
        return
    if not _tiene_unique_periodo_viejo(conn):
        return

    sufijo = datetime.now().strftime("%Y%m%d%H%M%S")
    legacy = f"{TABLA_CIERRES}_legacy_{sufijo}"
    cur.execute(f"ALTER TABLE {TABLA_CIERRES} RENAME TO {legacy}")
    _crear_tabla_cierres_base(cur)

    old_cols = _columnas_lista(conn, legacy)
    new_cols = _columnas_lista(conn, TABLA_CIERRES)
    comunes = [c for c in old_cols if c in new_cols]

    if comunes:
        cols = ", ".join(comunes)
        cur.execute(f"INSERT INTO {TABLA_CIERRES} ({cols}) SELECT {cols} FROM {legacy}")


def _registrar_evento_cierre(cur, cierre_id, empresa_id, anio, mes, evento, detalle="", usuario="sistema"):
    periodo = _periodo_texto(anio, mes)
    cur.execute(
        f"""
        INSERT INTO {TABLA_EVENTOS}
        (cierre_id, empresa_id, anio, mes, periodo, evento, detalle, usuario, fecha_evento)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (cierre_id, int(empresa_id), int(anio), int(mes), periodo, _texto(evento), _texto(detalle), _texto(usuario, "sistema")),
    )


def _resultado_saldo_desde_importe(saldo_preliminar):
    saldo = _round2(saldo_preliminar)
    if saldo > TOLERANCIA:
        return {"resultado_saldo": RESULTADO_A_PAGAR, "saldo_a_pagar": saldo, "saldo_a_favor": 0.0, "estado_pago": ESTADO_PAGO_PENDIENTE, "saldo_pendiente_pago": saldo}
    if saldo < -TOLERANCIA:
        return {"resultado_saldo": RESULTADO_A_FAVOR, "saldo_a_pagar": 0.0, "saldo_a_favor": abs(saldo), "estado_pago": ESTADO_PAGO_NO_APLICA, "saldo_pendiente_pago": 0.0}
    return {"resultado_saldo": RESULTADO_CERO, "saldo_a_pagar": 0.0, "saldo_a_favor": 0.0, "estado_pago": ESTADO_PAGO_NO_APLICA, "saldo_pendiente_pago": 0.0}


def _estado_pago_desde_importes(saldo_a_pagar, importe_pagado):
    saldo_a_pagar = _round2(saldo_a_pagar)
    importe_pagado = _round2(importe_pagado)
    if saldo_a_pagar <= TOLERANCIA:
        return ESTADO_PAGO_NO_APLICA, 0.0
    pendiente = max(round(saldo_a_pagar - importe_pagado, 2), 0.0)
    if pendiente <= TOLERANCIA:
        return ESTADO_PAGO_PAGADO, 0.0
    if importe_pagado > TOLERANCIA:
        return ESTADO_PAGO_PARCIAL, pendiente
    return ESTADO_PAGO_PENDIENTE, pendiente


def asegurar_estructura_iva_cierres():
    conn = conectar()
    cur = conn.cursor()
    try:
        _crear_tabla_cierres_base(cur)
        _reconstruir_tabla_cierres_si_esquema_viejo(conn, cur)

        columnas = _columnas_tabla(conn, TABLA_CIERRES)
        columnas_necesarias = {
            "version_tipo": "TEXT NOT NULL DEFAULT 'ORIGINAL'",
            "numero_rectificativa": "INTEGER NOT NULL DEFAULT 0",
            "version_etiqueta": "TEXT NOT NULL DEFAULT 'Original'",
            "es_version_vigente": "INTEGER NOT NULL DEFAULT 1",
            "cierre_anterior_id": "INTEGER",
            "motivo_rectificativa": "TEXT",
            "requiere_revision_por_rectificativa": "INTEGER NOT NULL DEFAULT 0",
            "cierre_origen_revision_id": "INTEGER",
            "motivo_revision": "TEXT",
            "iva_no_computable": "REAL NOT NULL DEFAULT 0",
            "saldo_tecnico_anterior": "REAL NOT NULL DEFAULT 0",
            "saldo_libre_disponibilidad": "REAL NOT NULL DEFAULT 0",
            "pago_a_cuenta": "REAL NOT NULL DEFAULT 0",
            "saldo_tecnico_a_favor_trasladable": "REAL NOT NULL DEFAULT 0",
            "saldo_trasladado_al_siguiente": "REAL NOT NULL DEFAULT 0",
            "saldo_trasladado_original": "REAL NOT NULL DEFAULT 0",
            "saldo_trasladado_rectificado": "REAL NOT NULL DEFAULT 0",
            "diferencia_saldo_trasladado": "REAL NOT NULL DEFAULT 0",
            "periodo_siguiente_afectado": "TEXT",
            "impacto_rectificativa_json": "TEXT",
            "resultado_saldo": "TEXT NOT NULL DEFAULT 'CERO'",
            "saldo_a_pagar": "REAL NOT NULL DEFAULT 0",
            "saldo_a_favor": "REAL NOT NULL DEFAULT 0",
            "importe_pagado": "REAL NOT NULL DEFAULT 0",
            "saldo_pendiente_pago": "REAL NOT NULL DEFAULT 0",
            "estado_pago": "TEXT NOT NULL DEFAULT 'NO_APLICA'",
            "fecha_ultimo_pago": "TEXT",
            "neto_ventas": "REAL NOT NULL DEFAULT 0",
            "total_ventas": "REAL NOT NULL DEFAULT 0",
            "neto_compras": "REAL NOT NULL DEFAULT 0",
            "total_compras": "REAL NOT NULL DEFAULT 0",
            "total_movimientos_fiscales": "REAL NOT NULL DEFAULT 0",
            "posicion_json": "TEXT",
            "resumen_origenes_json": "TEXT",
            "alertas_json": "TEXT",
            "indicadores_json": "TEXT",
            "fecha_actualizacion": "TIMESTAMP",
        }
        for columna, definicion in columnas_necesarias.items():
            if columna not in columnas:
                cur.execute(f"ALTER TABLE {TABLA_CIERRES} ADD COLUMN {columna} {definicion}")
                columnas.add(columna)

        cur.execute(f"CREATE INDEX IF NOT EXISTS idx_iva_cierres_empresa_periodo ON {TABLA_CIERRES} (empresa_id, anio, mes)")
        cur.execute(f"CREATE INDEX IF NOT EXISTS idx_iva_cierres_vigente ON {TABLA_CIERRES} (empresa_id, anio, mes, es_version_vigente)")
        cur.execute(f"CREATE INDEX IF NOT EXISTS idx_iva_cierres_estado ON {TABLA_CIERRES} (empresa_id, estado)")
        cur.execute(f"CREATE INDEX IF NOT EXISTS idx_iva_cierres_estado_pago ON {TABLA_CIERRES} (empresa_id, estado_pago)")

        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {TABLA_EVENTOS} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cierre_id INTEGER,
                empresa_id INTEGER NOT NULL,
                anio INTEGER NOT NULL,
                mes INTEGER NOT NULL,
                periodo TEXT NOT NULL,
                evento TEXT NOT NULL,
                detalle TEXT,
                usuario TEXT,
                fecha_evento TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cur.execute(f"CREATE INDEX IF NOT EXISTS idx_iva_cierres_eventos_cierre ON {TABLA_EVENTOS} (cierre_id, fecha_evento)")
        cur.execute(f"CREATE INDEX IF NOT EXISTS idx_iva_cierres_eventos_periodo ON {TABLA_EVENTOS} (empresa_id, anio, mes, fecha_evento)")

        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {TABLA_PAGOS} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cierre_id INTEGER NOT NULL,
                empresa_id INTEGER NOT NULL,
                anio INTEGER NOT NULL,
                mes INTEGER NOT NULL,
                periodo TEXT NOT NULL,
                fecha_pago TEXT NOT NULL,
                importe REAL NOT NULL DEFAULT 0,
                medio_pago TEXT NOT NULL DEFAULT 'MANUAL',
                cuenta_codigo TEXT,
                cuenta_nombre TEXT,
                referencia TEXT,
                observacion TEXT,
                estado TEXT NOT NULL DEFAULT 'REGISTRADO',
                pago_original_id INTEGER,
                motivo_correccion TEXT,
                usuario_correccion TEXT,
                fecha_correccion TIMESTAMP,
                usuario TEXT,
                fecha_carga TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                fecha_anulacion TIMESTAMP,
                motivo_anulacion TEXT,
                fecha_actualizacion TIMESTAMP
            )
            """
        )
        columnas_pagos = _columnas_tabla(conn, TABLA_PAGOS)
        columnas_pagos_necesarias = {
            "pago_original_id": "INTEGER",
            "motivo_correccion": "TEXT",
            "usuario_correccion": "TEXT",
            "fecha_correccion": "TIMESTAMP",
            "fecha_actualizacion": "TIMESTAMP",
        }
        for columna, definicion in columnas_pagos_necesarias.items():
            if columna not in columnas_pagos:
                cur.execute(f"ALTER TABLE {TABLA_PAGOS} ADD COLUMN {columna} {definicion}")
                columnas_pagos.add(columna)

        cur.execute(f"CREATE INDEX IF NOT EXISTS idx_iva_cierres_pagos_cierre ON {TABLA_PAGOS} (cierre_id, estado)")
        cur.execute(f"CREATE INDEX IF NOT EXISTS idx_iva_cierres_pagos_periodo ON {TABLA_PAGOS} (empresa_id, anio, mes, fecha_pago)")
        cur.execute(f"CREATE INDEX IF NOT EXISTS idx_iva_cierres_pagos_original ON {TABLA_PAGOS} (empresa_id, pago_original_id, estado)")

        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {TABLA_ASIENTOS} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cierre_id INTEGER NOT NULL,
                pago_id INTEGER,
                empresa_id INTEGER NOT NULL,
                anio INTEGER NOT NULL,
                mes INTEGER NOT NULL,
                periodo TEXT NOT NULL,
                fecha TEXT NOT NULL,
                tipo_asiento TEXT NOT NULL,
                cuenta_codigo TEXT NOT NULL,
                cuenta_nombre TEXT NOT NULL,
                debe REAL NOT NULL DEFAULT 0,
                haber REAL NOT NULL DEFAULT 0,
                glosa TEXT,
                estado TEXT NOT NULL DEFAULT 'PROPUESTO',
                usuario TEXT,
                fecha_carga TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cur.execute(f"CREATE INDEX IF NOT EXISTS idx_iva_cierres_asientos_cierre ON {TABLA_ASIENTOS} (cierre_id, tipo_asiento, estado)")
        cur.execute(f"CREATE INDEX IF NOT EXISTS idx_iva_cierres_asientos_periodo ON {TABLA_ASIENTOS} (empresa_id, anio, mes, tipo_asiento)")

        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _enriquecer_cierre_dict(row):
    if not row:
        return {}
    row = dict(row)
    row["posicion"] = _desde_json(row.get("posicion_json"), default={})
    row["resumen_origenes"] = _desde_json(row.get("resumen_origenes_json"), default=[])
    row["alertas"] = _desde_json(row.get("alertas_json"), default=[])
    row["indicadores"] = _desde_json(row.get("indicadores_json"), default={})
    row["impacto_rectificativa"] = _desde_json(row.get("impacto_rectificativa_json"), default={})
    return row


def obtener_cierre_periodo(empresa_id=1, anio=None, mes=None, solo_vigente=True):
    asegurar_estructura_iva_cierres()
    anio = _int(anio)
    mes = _int(mes)
    if anio <= 0 or mes <= 0:
        return {}

    where_vigente = "AND es_version_vigente = 1" if solo_vigente else ""
    df = ejecutar_query(
        f"""
        SELECT *
        FROM {TABLA_CIERRES}
        WHERE empresa_id = ?
          AND anio = ?
          AND mes = ?
          {where_vigente}
        ORDER BY es_version_vigente DESC, numero_rectificativa DESC, id DESC
        LIMIT 1
        """,
        (int(empresa_id), anio, mes),
        fetch=True,
    )
    df = _resultado_a_dataframe(df)
    if df.empty:
        return {}
    return _enriquecer_cierre_dict(df.iloc[0].to_dict())


def listar_cierres_iva(empresa_id=1, incluir_reabiertos=True, solo_vigentes=False):
    asegurar_estructura_iva_cierres()
    condiciones = ["empresa_id = ?"]
    params = [int(empresa_id)]
    if not incluir_reabiertos:
        condiciones.append("estado = ?")
        params.append(ESTADO_CIERRE_CERRADO)
    if solo_vigentes:
        condiciones.append("es_version_vigente = 1")
    where = " AND ".join(condiciones)
    df = ejecutar_query(
        f"""
        SELECT *
        FROM {TABLA_CIERRES}
        WHERE {where}
        ORDER BY anio DESC, mes DESC, numero_rectificativa DESC, id DESC
        """,
        tuple(params),
        fetch=True,
    )
    return _resultado_a_dataframe(df)


def listar_versiones_periodo(empresa_id=1, anio=None, mes=None):
    asegurar_estructura_iva_cierres()
    df = ejecutar_query(
        f"""
        SELECT *
        FROM {TABLA_CIERRES}
        WHERE empresa_id = ? AND anio = ? AND mes = ?
        ORDER BY numero_rectificativa ASC, id ASC
        """,
        (int(empresa_id), _int(anio), _int(mes)),
        fetch=True,
    )
    return _resultado_a_dataframe(df)


def listar_eventos_cierre(cierre_id=None, empresa_id=1, anio=None, mes=None):
    asegurar_estructura_iva_cierres()
    condiciones = ["empresa_id = ?"]
    params = [int(empresa_id)]
    if cierre_id is not None:
        condiciones.append("cierre_id = ?")
        params.append(int(cierre_id))
    if anio is not None:
        condiciones.append("anio = ?")
        params.append(_int(anio))
    if mes is not None:
        condiciones.append("mes = ?")
        params.append(_int(mes))
    df = ejecutar_query(
        f"SELECT * FROM {TABLA_EVENTOS} WHERE {' AND '.join(condiciones)} ORDER BY fecha_evento DESC, id DESC",
        tuple(params),
        fetch=True,
    )
    return _resultado_a_dataframe(df)


def listar_pagos_cierre(cierre_id=None, empresa_id=1, anio=None, mes=None, incluir_anulados=False):
    asegurar_estructura_iva_cierres()
    condiciones = ["empresa_id = ?"]
    params = [int(empresa_id)]
    if cierre_id is not None:
        condiciones.append("cierre_id = ?")
        params.append(int(cierre_id))
    if anio is not None:
        condiciones.append("anio = ?")
        params.append(_int(anio))
    if mes is not None:
        condiciones.append("mes = ?")
        params.append(_int(mes))
    if not incluir_anulados:
        condiciones.append("estado = ?")
        params.append(ESTADO_PAGO_REGISTRADO)
    df = ejecutar_query(
        f"SELECT * FROM {TABLA_PAGOS} WHERE {' AND '.join(condiciones)} ORDER BY fecha_pago DESC, id DESC",
        tuple(params),
        fetch=True,
    )
    return _resultado_a_dataframe(df)


def listar_asientos_cierre(cierre_id=None, empresa_id=1, anio=None, mes=None, tipo_asiento=None):
    asegurar_estructura_iva_cierres()
    condiciones = ["empresa_id = ?"]
    params = [int(empresa_id)]
    if cierre_id is not None:
        condiciones.append("cierre_id = ?")
        params.append(int(cierre_id))
    if anio is not None:
        condiciones.append("anio = ?")
        params.append(_int(anio))
    if mes is not None:
        condiciones.append("mes = ?")
        params.append(_int(mes))
    if tipo_asiento is not None:
        condiciones.append("tipo_asiento = ?")
        params.append(_texto(tipo_asiento))
    df = ejecutar_query(
        f"SELECT * FROM {TABLA_ASIENTOS} WHERE {' AND '.join(condiciones)} ORDER BY tipo_asiento, pago_id, id",
        tuple(params),
        fetch=True,
    )
    return _resultado_a_dataframe(df)


def _leer_movimientos_periodo_para_control(empresa_id, anio, mes):
    if listar_movimientos_fiscales is None:
        return pd.DataFrame()
    try:
        if asegurar_estructura_iva_movimientos_fiscales is not None:
            asegurar_estructura_iva_movimientos_fiscales()
        df = listar_movimientos_fiscales(empresa_id=empresa_id, anio=anio, mes=mes, incluir_anulados=False)
        return _resultado_a_dataframe(df)
    except Exception:
        return pd.DataFrame()


def _serie_numerica(df, columna):
    if df is None or df.empty or columna not in df.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(df[columna], errors="coerce").fillna(0.0)


def _importe_relevante_movimientos(df):
    if df is None or df.empty:
        return 0.0
    columnas = ["iva_debito", "credito_fiscal_computable", "iva_no_computable", "percepcion_iva", "retencion_iva", "saldo_tecnico_anterior", "saldo_libre_disponibilidad", "pago_a_cuenta"]
    return round(sum(float(_serie_numerica(df, c).sum()) for c in columnas), 2)


def _obtener_periodos_anteriores_abiertos(empresa_id, anio, mes):
    try:
        periodos = obtener_periodos_disponibles_iva(empresa_id=empresa_id)
        periodos = _resultado_a_dataframe(periodos)
    except Exception:
        return []
    if periodos.empty:
        return []
    faltantes = []
    actual = _periodo_orden(anio, mes)
    for _, row in periodos.iterrows():
        pa = _int(row.get("anio"))
        pm = _int(row.get("mes"))
        if pa <= 0 or pm <= 0 or _periodo_orden(pa, pm) >= actual:
            continue
        if _int(row.get("cantidad_total", 0)) <= 0:
            continue
        cierre = obtener_cierre_periodo(empresa_id=empresa_id, anio=pa, mes=pm)
        if not cierre or cierre.get("estado") != ESTADO_CIERRE_CERRADO:
            faltantes.append({"anio": pa, "mes": pm, "periodo": _periodo_texto(pa, pm)})
    return sorted(faltantes, key=lambda x: (x["anio"], x["mes"]))


def _obtener_periodos_posteriores_cerrados(empresa_id, anio, mes):
    asegurar_estructura_iva_cierres()
    actual = _periodo_orden(anio, mes)
    df = ejecutar_query(
        f"""
        SELECT *
        FROM {TABLA_CIERRES}
        WHERE empresa_id = ?
          AND es_version_vigente = 1
          AND estado = ?
        ORDER BY anio, mes
        """,
        (int(empresa_id), ESTADO_CIERRE_CERRADO),
        fetch=True,
    )
    df = _resultado_a_dataframe(df)
    if df.empty:
        return []
    posteriores = []
    for _, row in df.iterrows():
        pa = _int(row.get("anio"))
        pm = _int(row.get("mes"))
        if _periodo_orden(pa, pm) > actual:
            posteriores.append(dict(row))
    return posteriores


def _version_siguiente(cierre_actual):
    if not cierre_actual:
        return VERSION_TIPO_ORIGINAL, 0, "Original", None
    numero = _int(cierre_actual.get("numero_rectificativa"), 0) + 1
    return VERSION_TIPO_RECTIFICATIVA, numero, f"Rectificativa {numero}", _int(cierre_actual.get("id"))


def _calcular_impacto_rectificativa(cierre_anterior, payload):
    if not cierre_anterior:
        return {}
    original = _round2(cierre_anterior.get("saldo_trasladado_al_siguiente", cierre_anterior.get("saldo_tecnico_a_favor_trasladable", 0)))
    rectificado = _round2(payload.get("saldo_tecnico_a_favor_trasladable", 0))
    diferencia = _round2(original - rectificado)
    anio_sig, mes_sig = _siguiente_periodo(payload.get("anio"), payload.get("mes"))
    periodo_sig = _periodo_texto(anio_sig, mes_sig)

    if abs(diferencia) <= TOLERANCIA:
        tipo = "SIN_IMPACTO_RELEVANTE"
        mensaje = "La rectificativa no cambia de forma relevante el saldo técnico trasladado al período siguiente."
    elif diferencia > 0:
        tipo = "REDUCE_SALDO_TRASLADADO"
        mensaje = (
            f"El cierre anterior trasladó {original:.2f} al período {periodo_sig}, "
            f"pero la rectificativa solo permite trasladar {rectificado:.2f}. "
            f"Diferencia a regularizar/revisar: {diferencia:.2f}."
        )
    else:
        tipo = "AUMENTA_SALDO_TRASLADADO"
        mensaje = (
            f"La rectificativa aumenta el saldo técnico trasladable respecto del cierre anterior. "
            f"Diferencia a favor adicional: {abs(diferencia):.2f}."
        )

    return {
        "tipo_impacto": tipo,
        "saldo_trasladado_original": original,
        "saldo_trasladado_rectificado": rectificado,
        "diferencia_saldo_trasladado": diferencia,
        "periodo_siguiente_afectado": periodo_sig,
        "mensaje": mensaje,
    }


def obtener_control_cierre_periodo(empresa_id=1, anio=None, mes=None):
    asegurar_estructura_iva_cierres()
    anio = _int(anio)
    mes = _int(mes)
    periodo = _periodo_texto(anio, mes)

    resultado = calcular_posicion_iva_periodo(empresa_id=empresa_id, anio=anio, mes=mes)
    posicion = dict(resultado.get("posicion", {}) or {})
    alertas = list(resultado.get("alertas", []) or [])
    resumen_origenes = resultado.get("resumen_origenes", pd.DataFrame())

    movimientos = _leer_movimientos_periodo_para_control(empresa_id, anio, mes)
    if not movimientos.empty and "estado" in movimientos.columns:
        estados = movimientos["estado"].fillna("").astype(str).str.upper()
        borradores = movimientos[estados == ESTADO_BORRADOR].copy()
        confirmados = movimientos[estados == ESTADO_CONFIRMADO].copy()
    else:
        borradores = pd.DataFrame()
        confirmados = pd.DataFrame()

    if not confirmados.empty and "incluido_en_posicion" in confirmados.columns:
        incluido = pd.to_numeric(confirmados["incluido_en_posicion"], errors="coerce").fillna(0).astype(int)
        confirmados_no_incluidos = confirmados[incluido == 0].copy()
    else:
        confirmados_no_incluidos = pd.DataFrame()

    cierre = obtener_cierre_periodo(empresa_id=empresa_id, anio=anio, mes=mes)
    estado_cierre = cierre.get("estado") or ESTADO_CIERRE_ABIERTO
    version_tipo, numero_rect, version_etiqueta, cierre_anterior_id = _version_siguiente(cierre)

    saldo_info = _resultado_saldo_desde_importe(posicion.get("saldo_preliminar_periodo"))
    saldo_tecnico_a_favor_trasladable = max(round(-_float(posicion.get("saldo_tecnico_iva", 0)), 2), 0.0)

    bloqueos = []
    advertencias = []

    if cierre and estado_cierre == ESTADO_CIERRE_CERRADO:
        bloqueos.append("El período ya está cerrado internamente. Para cambiarlo debe generarse una rectificativa o reabrirse con motivo administrativo.")

    if cierre and _int(cierre.get("requiere_revision_por_rectificativa")) == 1:
        advertencias.append(_texto(cierre.get("motivo_revision"), "Este período requiere revisión por una rectificativa anterior."))

    if not borradores.empty:
        texto = f"Hay {len(borradores)} movimiento(s) fiscal(es) en borrador. No impactan IVA hasta confirmarse."
        bloqueos.append(texto)
        alertas.append({"nivel": "ADVERTENCIA", "titulo": "Movimientos fiscales pendientes", "detalle": texto})

    if not confirmados_no_incluidos.empty:
        texto = f"Hay {len(confirmados_no_incluidos)} movimiento(s) fiscal(es) confirmados pero no incluidos en la posición."
        bloqueos.append(texto)
        alertas.append({"nivel": "INFO", "titulo": "Movimientos fiscales no tomados", "detalle": texto})

    anteriores_abiertos = _obtener_periodos_anteriores_abiertos(empresa_id, anio, mes)
    if anteriores_abiertos:
        texto = "Cierre cronológico requerido. Hay períodos anteriores con movimientos sin cierre vigente: " + ", ".join(p["periodo"] for p in anteriores_abiertos[:8])
        bloqueos.append(texto)
        alertas.append({"nivel": "ADVERTENCIA", "titulo": "Cierre cronológico", "detalle": texto})

    posteriores_cerrados = _obtener_periodos_posteriores_cerrados(empresa_id, anio, mes)
    if posteriores_cerrados and cierre:
        advertencias.append(
            "Existen períodos posteriores cerrados. Si generás una rectificativa, esos períodos pueden requerir revisión: "
            + ", ".join(_texto(p.get("periodo")) for p in posteriores_cerrados[:8])
        )

    cantidad_total = _int(posicion.get("cantidad_ventas")) + _int(posicion.get("cantidad_compras")) + _int(posicion.get("cantidad_movimientos_fiscales"))

    payload_estimado = {
        "anio": anio,
        "mes": mes,
        "saldo_tecnico_a_favor_trasladable": saldo_tecnico_a_favor_trasladable,
    }
    impacto_estimado = _calcular_impacto_rectificativa(cierre, payload_estimado) if cierre else {}

    indicadores = {
        "periodo": periodo,
        "estado_cierre": estado_cierre,
        "version_actual": cierre.get("version_etiqueta") if cierre else "Sin cierre",
        "version_tipo_proxima": version_tipo,
        "numero_rectificativa_proxima": numero_rect,
        "version_etiqueta_proxima": version_etiqueta,
        "cierre_anterior_id": cierre_anterior_id,
        "resultado_saldo": saldo_info["resultado_saldo"],
        "saldo_a_pagar": saldo_info["saldo_a_pagar"],
        "saldo_a_favor": saldo_info["saldo_a_favor"],
        "saldo_tecnico_a_favor_trasladable": saldo_tecnico_a_favor_trasladable,
        "estado_pago_estimado": saldo_info["estado_pago"],
        "saldo_pendiente_pago_estimado": saldo_info["saldo_pendiente_pago"],
        "cantidad_ventas": _int(posicion.get("cantidad_ventas")),
        "cantidad_compras": _int(posicion.get("cantidad_compras")),
        "cantidad_movimientos_fiscales": _int(posicion.get("cantidad_movimientos_fiscales")),
        "cantidad_total": cantidad_total,
        "movimientos_borrador": int(len(borradores)),
        "movimientos_confirmados_no_incluidos": int(len(confirmados_no_incluidos)),
        "importe_borrador": _importe_relevante_movimientos(borradores),
        "importe_confirmado_no_incluido": _importe_relevante_movimientos(confirmados_no_incluidos),
        "saldo_preliminar_periodo": _float(posicion.get("saldo_preliminar_periodo")),
        "tiene_datos_periodo": cantidad_total > 0,
        "bloqueos": len(bloqueos),
        "advertencias": len(advertencias),
        "impacto_rectificativa_estimado": impacto_estimado,
    }

    puede_cerrar = estado_cierre != ESTADO_CIERRE_CERRADO and len(bloqueos) == 0

    return {
        "ok": True,
        "empresa_id": int(empresa_id),
        "anio": anio,
        "mes": mes,
        "periodo": periodo,
        "posicion": posicion,
        "resumen_origenes": resumen_origenes,
        "alertas": alertas,
        "indicadores": indicadores,
        "bloqueos": bloqueos,
        "advertencias": advertencias,
        "cierre": cierre,
        "puede_cerrar": puede_cerrar,
    }


def _linea_asiento(cuenta_clave, debe=0.0, haber=0.0, cuenta=None):
    if cuenta is None:
        cuenta = CUENTAS_IVA_DEFAULT[cuenta_clave]
    cuenta_codigo, cuenta_nombre = cuenta
    debe = _round2(debe)
    haber = _round2(haber)
    if abs(debe) <= TOLERANCIA and abs(haber) <= TOLERANCIA:
        return None
    return {"cuenta_codigo": cuenta_codigo, "cuenta_nombre": cuenta_nombre, "debe": debe, "haber": haber}


def armar_asiento_liquidacion_iva(posicion):
    saldo_info = _resultado_saldo_desde_importe(posicion.get("saldo_preliminar_periodo"))
    lineas = []
    candidatos = [
        _linea_asiento("iva_debito_fiscal", debe=posicion.get("iva_debito_fiscal", 0)),
        _linea_asiento("saldo_a_favor_iva", debe=saldo_info["saldo_a_favor"]),
        _linea_asiento("credito_fiscal_computable", haber=posicion.get("credito_fiscal_computable", 0)),
        _linea_asiento("percepciones_iva_sufridas", haber=posicion.get("percepciones_iva_sufridas", 0)),
        _linea_asiento("retenciones_iva_sufridas", haber=posicion.get("retenciones_iva_sufridas", 0)),
        _linea_asiento("saldo_tecnico_anterior", haber=posicion.get("saldo_tecnico_anterior", 0)),
        _linea_asiento("saldo_libre_disponibilidad", haber=posicion.get("saldo_libre_disponibilidad", 0)),
        _linea_asiento("pago_a_cuenta", haber=posicion.get("pago_a_cuenta", 0)),
        _linea_asiento("iva_a_pagar", haber=saldo_info["saldo_a_pagar"]),
    ]
    for linea in candidatos:
        if linea is not None:
            lineas.append(linea)
    debe = _round2(sum(l["debe"] for l in lineas))
    haber = _round2(sum(l["haber"] for l in lineas))
    diferencia = _round2(debe - haber)
    return {"lineas": lineas, "debe": debe, "haber": haber, "diferencia": diferencia, "balanceado": abs(diferencia) <= TOLERANCIA}


def armar_asiento_ajuste_rectificativa(impacto):
    diferencia = _round2((impacto or {}).get("diferencia_saldo_trasladado"))
    if abs(diferencia) <= TOLERANCIA:
        return {"lineas": [], "debe": 0.0, "haber": 0.0, "diferencia": 0.0, "balanceado": True}
    if diferencia > 0:
        lineas = [
            _linea_asiento("ajuste_rectificativa_iva", debe=diferencia),
            _linea_asiento("saldo_a_favor_iva", haber=diferencia),
        ]
    else:
        valor = abs(diferencia)
        lineas = [
            _linea_asiento("saldo_a_favor_iva", debe=valor),
            _linea_asiento("ajuste_rectificativa_iva", haber=valor),
        ]
    lineas = [l for l in lineas if l is not None]
    debe = _round2(sum(l["debe"] for l in lineas))
    haber = _round2(sum(l["haber"] for l in lineas))
    return {"lineas": lineas, "debe": debe, "haber": haber, "diferencia": _round2(debe - haber), "balanceado": abs(_round2(debe - haber)) <= TOLERANCIA}


def _insertar_asiento_lineas(cur, cierre_id, pago_id, empresa_id, anio, mes, fecha, tipo_asiento, lineas, glosa, usuario):
    periodo = _periodo_texto(anio, mes)
    for linea in lineas:
        cur.execute(
            f"""
            INSERT INTO {TABLA_ASIENTOS}
            (cierre_id, pago_id, empresa_id, anio, mes, periodo, fecha, tipo_asiento, cuenta_codigo, cuenta_nombre, debe, haber, glosa, estado, usuario, fecha_carga)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PROPUESTO', ?, CURRENT_TIMESTAMP)
            """,
            (int(cierre_id), pago_id, int(empresa_id), int(anio), int(mes), periodo, _fecha_texto(fecha), _texto(tipo_asiento), _texto(linea["cuenta_codigo"]), _texto(linea["cuenta_nombre"]), _round2(linea.get("debe")), _round2(linea.get("haber")), _texto(glosa), _texto(usuario, "sistema")),
        )


def _regenerar_asientos_cierre(cur, cierre_id, empresa_id, anio, mes, posicion, impacto, usuario):
    cur.execute(f"DELETE FROM {TABLA_ASIENTOS} WHERE cierre_id = ? AND empresa_id = ? AND pago_id IS NULL", (int(cierre_id), int(empresa_id)))
    asiento = armar_asiento_liquidacion_iva(posicion)
    if asiento["lineas"]:
        _insertar_asiento_lineas(cur, cierre_id, None, empresa_id, anio, mes, f"{int(anio):04d}-{int(mes):02d}-01", TIPO_ASIENTO_LIQUIDACION, asiento["lineas"], f"Liquidación IVA período {_periodo_texto(anio, mes)}", usuario)
    ajuste = armar_asiento_ajuste_rectificativa(impacto)
    if ajuste["lineas"]:
        _insertar_asiento_lineas(cur, cierre_id, None, empresa_id, anio, mes, f"{int(anio):04d}-{int(mes):02d}-01", TIPO_ASIENTO_RECTIFICATIVA, ajuste["lineas"], f"Ajuste por rectificativa IVA período {_periodo_texto(anio, mes)}", usuario)
    return {"liquidacion": asiento, "ajuste_rectificativa": ajuste}


def _armar_asiento_pago_iva(importe, medio_pago, cuenta_codigo=None, cuenta_nombre=None):
    medio = _texto(medio_pago, "MANUAL").upper()
    if cuenta_codigo or cuenta_nombre:
        cuenta_pago = (_texto(cuenta_codigo, CUENTAS_IVA_DEFAULT["tesoreria_puente"][0]), _texto(cuenta_nombre, CUENTAS_IVA_DEFAULT["tesoreria_puente"][1]))
    else:
        cuenta_pago = MEDIOS_PAGO_CUENTA_DEFAULT.get(medio, CUENTAS_IVA_DEFAULT["tesoreria_puente"])
    importe = _round2(importe)
    lineas = [_linea_asiento("iva_a_pagar", debe=importe), _linea_asiento("tesoreria_puente", haber=importe, cuenta=cuenta_pago)]
    lineas = [l for l in lineas if l is not None]
    debe = _round2(sum(l["debe"] for l in lineas))
    haber = _round2(sum(l["haber"] for l in lineas))
    return {"lineas": lineas, "debe": debe, "haber": haber, "diferencia": _round2(debe - haber), "balanceado": abs(_round2(debe - haber)) <= TOLERANCIA}


def _payload_cierre_desde_control(control, usuario, observacion, version_tipo, numero_rectificativa, version_etiqueta, cierre_anterior_id=None, motivo_rectificativa=""):
    posicion = dict(control.get("posicion", {}) or {})
    indicadores = dict(control.get("indicadores", {}) or {})
    resumen_origenes = control.get("resumen_origenes", pd.DataFrame())
    alertas = control.get("alertas", []) or []
    saldo_info = _resultado_saldo_desde_importe(posicion.get("saldo_preliminar_periodo"))
    saldo_tecnico_trasladable = max(round(-_float(posicion.get("saldo_tecnico_iva", 0)), 2), 0.0)
    return {
        "empresa_id": _int(control.get("empresa_id")),
        "anio": _int(control.get("anio")),
        "mes": _int(control.get("mes")),
        "periodo": control.get("periodo") or _periodo_texto(control.get("anio"), control.get("mes")),
        "estado": ESTADO_CIERRE_CERRADO,
        "version_tipo": version_tipo,
        "numero_rectificativa": _int(numero_rectificativa),
        "version_etiqueta": version_etiqueta,
        "es_version_vigente": 1,
        "cierre_anterior_id": cierre_anterior_id,
        "motivo_rectificativa": _texto(motivo_rectificativa),
        "iva_debito_fiscal": _float(posicion.get("iva_debito_fiscal")),
        "credito_fiscal_computable": _float(posicion.get("credito_fiscal_computable")),
        "iva_no_computable": _float(posicion.get("iva_no_computable")),
        "percepciones_iva_sufridas": _float(posicion.get("percepciones_iva_sufridas")),
        "retenciones_iva_sufridas": _float(posicion.get("retenciones_iva_sufridas")),
        "saldo_tecnico_anterior": _float(posicion.get("saldo_tecnico_anterior")),
        "saldo_libre_disponibilidad": _float(posicion.get("saldo_libre_disponibilidad")),
        "pago_a_cuenta": _float(posicion.get("pago_a_cuenta")),
        "saldo_tecnico_iva": _float(posicion.get("saldo_tecnico_iva")),
        "saldo_preliminar_periodo": _float(posicion.get("saldo_preliminar_periodo")),
        "saldo_tecnico_a_favor_trasladable": saldo_tecnico_trasladable,
        "resultado_saldo": saldo_info["resultado_saldo"],
        "saldo_a_pagar": saldo_info["saldo_a_pagar"],
        "saldo_a_favor": saldo_info["saldo_a_favor"],
        "importe_pagado": 0.0,
        "saldo_pendiente_pago": saldo_info["saldo_pendiente_pago"],
        "estado_pago": saldo_info["estado_pago"],
        "neto_ventas": _float(posicion.get("neto_ventas")),
        "total_ventas": _float(posicion.get("total_ventas")),
        "neto_compras": _float(posicion.get("neto_compras")),
        "total_compras": _float(posicion.get("total_compras")),
        "total_movimientos_fiscales": _float(posicion.get("total_movimientos_fiscales")),
        "cantidad_ventas": _int(posicion.get("cantidad_ventas")),
        "cantidad_compras": _int(posicion.get("cantidad_compras")),
        "cantidad_movimientos_fiscales": _int(posicion.get("cantidad_movimientos_fiscales")),
        "posicion_json": _json_seguro(posicion),
        "resumen_origenes_json": _json_seguro(resumen_origenes),
        "alertas_json": _json_seguro(alertas),
        "indicadores_json": _json_seguro(indicadores),
        "observacion_cierre": _texto(observacion),
        "usuario_cierre": _texto(usuario, "sistema"),
        "posicion": posicion,
    }


def _insertar_cierre(cur, payload, impacto):
    cur.execute(
        f"""
        INSERT INTO {TABLA_CIERRES}
        (
            empresa_id, anio, mes, periodo, estado,
            version_tipo, numero_rectificativa, version_etiqueta, es_version_vigente, cierre_anterior_id, motivo_rectificativa,
            iva_debito_fiscal, credito_fiscal_computable, iva_no_computable, percepciones_iva_sufridas, retenciones_iva_sufridas,
            saldo_tecnico_anterior, saldo_libre_disponibilidad, pago_a_cuenta, saldo_tecnico_iva, saldo_preliminar_periodo,
            saldo_tecnico_a_favor_trasladable, saldo_trasladado_al_siguiente, saldo_trasladado_original, saldo_trasladado_rectificado,
            diferencia_saldo_trasladado, periodo_siguiente_afectado, impacto_rectificativa_json,
            resultado_saldo, saldo_a_pagar, saldo_a_favor, importe_pagado, saldo_pendiente_pago, estado_pago,
            neto_ventas, total_ventas, neto_compras, total_compras, total_movimientos_fiscales,
            cantidad_ventas, cantidad_compras, cantidad_movimientos_fiscales,
            posicion_json, resumen_origenes_json, alertas_json, indicadores_json,
            observacion_cierre, usuario_cierre, fecha_cierre, fecha_actualizacion
        )
        VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        )
        """,
        (
            payload["empresa_id"], payload["anio"], payload["mes"], payload["periodo"], payload["estado"],
            payload["version_tipo"], payload["numero_rectificativa"], payload["version_etiqueta"], 1, payload["cierre_anterior_id"], payload["motivo_rectificativa"],
            payload["iva_debito_fiscal"], payload["credito_fiscal_computable"], payload["iva_no_computable"], payload["percepciones_iva_sufridas"], payload["retenciones_iva_sufridas"],
            payload["saldo_tecnico_anterior"], payload["saldo_libre_disponibilidad"], payload["pago_a_cuenta"], payload["saldo_tecnico_iva"], payload["saldo_preliminar_periodo"],
            payload["saldo_tecnico_a_favor_trasladable"], impacto.get("saldo_trasladado_rectificado", payload["saldo_tecnico_a_favor_trasladable"]), impacto.get("saldo_trasladado_original", 0.0), impacto.get("saldo_trasladado_rectificado", payload["saldo_tecnico_a_favor_trasladable"]),
            impacto.get("diferencia_saldo_trasladado", 0.0), impacto.get("periodo_siguiente_afectado", ""), _json_seguro(impacto),
            payload["resultado_saldo"], payload["saldo_a_pagar"], payload["saldo_a_favor"], payload["importe_pagado"], payload["saldo_pendiente_pago"], payload["estado_pago"],
            payload["neto_ventas"], payload["total_ventas"], payload["neto_compras"], payload["total_compras"], payload["total_movimientos_fiscales"],
            payload["cantidad_ventas"], payload["cantidad_compras"], payload["cantidad_movimientos_fiscales"],
            payload["posicion_json"], payload["resumen_origenes_json"], payload["alertas_json"], payload["indicadores_json"],
            payload["observacion_cierre"], payload["usuario_cierre"],
        ),
    )
    return int(cur.lastrowid)


def _registrar_evento_movimiento_fiscal_conn(cur, movimiento_id, empresa_id, evento, detalle, usuario):
    """
    Registra auditoría del movimiento fiscal usando la misma conexión abierta.

    No debe abrir otra conexión mientras el cierre IVA está en transacción, porque
    SQLite puede bloquear escrituras concurrentes y dejar el cierre como si hubiera
    trasladado saldo cuando en realidad no creó el movimiento del mes siguiente.
    """
    try:
        cur.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name = 'iva_movimientos_fiscales_eventos'
            """
        )
        if cur.fetchone() is None:
            return

        cur.execute(
            """
            INSERT INTO iva_movimientos_fiscales_eventos
            (
                movimiento_id,
                empresa_id,
                evento,
                detalle,
                usuario,
                fecha_evento
            )
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                int(movimiento_id),
                int(empresa_id),
                _texto(evento),
                _texto(detalle),
                _texto(usuario),
            ),
        )
    except Exception:
        # La auditoría del movimiento no debe romper el cierre si la tabla de eventos
        # no existe en una base parcial de pruebas, pero la inserción principal sí debe
        # fallar si no pudo crearse el movimiento de traslado.
        return


def _registrar_traslado_saldo_tecnico_conn(cur, cierre_id, empresa_id, anio, mes, saldo, usuario):
    """
    Crea el movimiento fiscal SALDO_TECNICO_ANTERIOR del período siguiente.

    Regla de diseño:
    - No usa registrar_movimiento_fiscal(), porque esa función abre otra conexión.
    - El cierre y el traslado deben grabarse en la misma transacción.
    - Si no puede grabarse el traslado, el cierre completo debe fallar y hacer rollback.
    """
    saldo = _round2(saldo)
    if saldo <= TOLERANCIA:
        return None

    anio_sig, mes_sig = _siguiente_periodo(anio, mes)
    periodo_sig = _periodo_texto(anio_sig, mes_sig)

    cur.execute(
        """
        SELECT id
        FROM iva_movimientos_fiscales
        WHERE empresa_id = ?
          AND anio = ?
          AND mes = ?
          AND IFNULL(estado, '') <> 'ANULADO'
          AND IFNULL(origen_tabla, '') = ?
          AND IFNULL(origen_id, 0) = ?
          AND UPPER(IFNULL(tipo_concepto, '')) = 'SALDO_TECNICO_ANTERIOR'
        ORDER BY id DESC
        LIMIT 1
        """,
        (int(empresa_id), anio_sig, mes_sig, TABLA_CIERRES, int(cierre_id)),
    )
    existente = cur.fetchone()
    if existente:
        return int(existente[0])

    descripcion = f"Saldo técnico IVA trasladado desde cierre {_periodo_texto(anio, mes)}"
    observacion = (
        "Generado automáticamente por cierre mensual IVA. "
        "Si el período origen se rectifica, revisar impacto y período posterior."
    )

    cur.execute(
        """
        INSERT INTO iva_movimientos_fiscales
        (
            empresa_id,
            anio,
            mes,
            periodo,
            fecha,
            origen,
            tipo_concepto,
            descripcion,
            contraparte,
            cuit,
            comprobante_codigo,
            comprobante_tipo,
            punto_venta,
            numero,
            neto_gravado,
            iva_debito,
            credito_fiscal_computable,
            iva_no_computable,
            percepcion_iva,
            retencion_iva,
            percepcion_iibb_informativa,
            saldo_tecnico_anterior,
            saldo_libre_disponibilidad,
            pago_a_cuenta,
            otros_tributos,
            total,
            estado,
            incluido_en_posicion,
            incluido_en_portal_iva,
            periodo_declaracion,
            motivo_no_inclusion,
            fecha_inclusion_posicion,
            usuario_inclusion_posicion,
            fecha_declaracion_portal,
            usuario_declaracion_portal,
            origen_tabla,
            origen_id,
            observacion,
            usuario,
            fecha_carga,
            fecha_confirmacion,
            fecha_anulacion,
            motivo_anulacion
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, NULL, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, NULL, '')
        """,
        (
            int(empresa_id),
            anio_sig,
            mes_sig,
            periodo_sig,
            f"{anio_sig:04d}-{mes_sig:02d}-01",
            "SALDO_ANTERIOR",
            "SALDO_TECNICO_ANTERIOR",
            descripcion,
            "Cierre IVA",
            "",
            "",
            "",
            "",
            "",
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            saldo,
            0.0,
            0.0,
            0.0,
            saldo,
            ESTADO_CONFIRMADO,
            1,
            0,
            "",
            "",
            _texto(usuario),
            "",
            TABLA_CIERRES,
            int(cierre_id),
            observacion,
            _texto(usuario),
        ),
    )

    movimiento_id = int(cur.lastrowid)
    _registrar_evento_movimiento_fiscal_conn(
        cur,
        movimiento_id=movimiento_id,
        empresa_id=empresa_id,
        evento="CREACION",
        detalle=f"Saldo técnico anterior generado por cierre IVA #{cierre_id} del período {_periodo_texto(anio, mes)}.",
        usuario=usuario,
    )
    _registrar_evento_movimiento_fiscal_conn(
        cur,
        movimiento_id=movimiento_id,
        empresa_id=empresa_id,
        evento="CONFIRMACION",
        detalle="Movimiento fiscal confirmado automáticamente para impactar la posición IVA del período siguiente.",
        usuario=usuario,
    )

    return movimiento_id


def _marcar_periodo_siguiente_requiere_revision(cur, empresa_id, anio, mes, cierre_origen_id, impacto, usuario):
    diferencia = _round2((impacto or {}).get("diferencia_saldo_trasladado"))
    if abs(diferencia) <= TOLERANCIA:
        return
    anio_sig, mes_sig = _siguiente_periodo(anio, mes)
    periodo_sig = _periodo_texto(anio_sig, mes_sig)
    motivo = (impacto or {}).get("mensaje") or "Período afectado por rectificativa anterior."
    cur.execute(
        f"""
        UPDATE {TABLA_CIERRES}
        SET requiere_revision_por_rectificativa = 1,
            cierre_origen_revision_id = ?,
            motivo_revision = ?,
            fecha_actualizacion = CURRENT_TIMESTAMP
        WHERE empresa_id = ?
          AND anio = ?
          AND mes = ?
          AND es_version_vigente = 1
        """,
        (int(cierre_origen_id), motivo, int(empresa_id), anio_sig, mes_sig),
    )
    _registrar_evento_cierre(cur, cierre_origen_id, empresa_id, anio, mes, "PERIODO_POSTERIOR_REQUIERE_REVISION", f"{periodo_sig}: {motivo}", usuario)


def cerrar_periodo_iva(empresa_id=1, anio=None, mes=None, usuario="sistema", observacion="", permitir_con_pendientes=False, permitir_salto_cronologico=False, generar_rectificativa=False, motivo_rectificativa="", permitir_con_periodos_posteriores=True):
    asegurar_estructura_iva_cierres()
    anio = _int(anio)
    mes = _int(mes)
    if anio <= 0 or mes <= 0:
        return {"ok": False, "mensaje": "Debe indicarse un período válido para cerrar IVA."}

    control = obtener_control_cierre_periodo(empresa_id=empresa_id, anio=anio, mes=mes)
    cierre_actual = control.get("cierre") or {}

    if cierre_actual and cierre_actual.get("estado") == ESTADO_CIERRE_CERRADO and not generar_rectificativa:
        return {"ok": False, "mensaje": "El período IVA ya está cerrado internamente. Para modificarlo debe generarse una rectificativa.", "cierre": cierre_actual, "control": control}

    if generar_rectificativa and cierre_actual and not _texto(motivo_rectificativa):
        return {"ok": False, "mensaje": "Debe indicarse motivo para generar una rectificativa IVA.", "cierre": cierre_actual, "control": control}

    bloqueos = list(control.get("bloqueos", []) or [])
    bloqueos_filtrados = []
    for b in bloqueos:
        texto = str(b)
        if "ya está cerrado" in texto:
            continue
        if "Cierre cronológico" in texto and permitir_salto_cronologico:
            continue
        bloqueos_filtrados.append(b)

    if bloqueos_filtrados and not permitir_con_pendientes:
        return {"ok": False, "mensaje": "El período tiene pendientes de control. Revise o confirme cierre con pendientes.", "bloqueos": bloqueos_filtrados, "control": control}

    version_tipo, numero_rect, version_etiqueta, cierre_anterior_id = _version_siguiente(cierre_actual)
    if cierre_actual and cierre_actual.get("estado") == ESTADO_CIERRE_REABIERTO:
        version_tipo, numero_rect, version_etiqueta, cierre_anterior_id = _version_siguiente(cierre_actual)
    if not cierre_actual:
        version_tipo, numero_rect, version_etiqueta, cierre_anterior_id = VERSION_TIPO_ORIGINAL, 0, "Original", None

    payload = _payload_cierre_desde_control(control, usuario, observacion, version_tipo, numero_rect, version_etiqueta, cierre_anterior_id, motivo_rectificativa)
    impacto = _calcular_impacto_rectificativa(cierre_actual, payload) if cierre_actual else {}

    # En rectificativas, considerar pagos ya registrados en la versión anterior como pagos históricos del mismo período.
    if cierre_actual:
        payload["importe_pagado"] = _round2(cierre_actual.get("importe_pagado", 0))
        estado_pago, pendiente = _estado_pago_desde_importes(payload["saldo_a_pagar"], payload["importe_pagado"])
        payload["estado_pago"] = estado_pago
        payload["saldo_pendiente_pago"] = pendiente

    # Si corresponde trasladar saldo técnico, la estructura de movimientos fiscales
    # debe existir antes de abrir la transacción principal del cierre. No se llama
    # dentro de la transacción para evitar conexiones de escritura anidadas en SQLite.
    if payload.get("saldo_tecnico_a_favor_trasladable", 0) > TOLERANCIA:
        if asegurar_estructura_iva_movimientos_fiscales is None:
            return {
                "ok": False,
                "mensaje": "No se puede cerrar el período con saldo técnico a favor porque no está disponible la estructura de movimientos fiscales para trasladarlo al mes siguiente.",
                "control": control,
            }
        asegurar_estructura_iva_movimientos_fiscales()

    conn = conectar()
    cur = conn.cursor()
    try:
        if cierre_actual:
            cur.execute(
                f"""
                UPDATE {TABLA_CIERRES}
                SET es_version_vigente = 0,
                    estado = ?,
                    fecha_actualizacion = CURRENT_TIMESTAMP
                WHERE empresa_id = ?
                  AND anio = ?
                  AND mes = ?
                  AND es_version_vigente = 1
                """,
                (ESTADO_CIERRE_RECTIFICADO, int(empresa_id), anio, mes),
            )

        cierre_id = _insertar_cierre(cur, payload, impacto)
        asientos = _regenerar_asientos_cierre(cur, cierre_id, empresa_id, anio, mes, payload["posicion"], impacto, usuario)

        _registrar_evento_cierre(cur, cierre_id, empresa_id, anio, mes, "CIERRE", (observacion or "Cierre mensual operativo IVA.") + f" Versión: {version_etiqueta}. Resultado: {payload['resultado_saldo']}.", usuario)

        if version_tipo == VERSION_TIPO_ORIGINAL:
            mov_id = _registrar_traslado_saldo_tecnico_conn(
                cur,
                cierre_id,
                empresa_id,
                anio,
                mes,
                payload["saldo_tecnico_a_favor_trasladable"],
                usuario,
            )
            if mov_id:
                cur.execute(
                    f"UPDATE {TABLA_CIERRES} SET saldo_trasladado_al_siguiente = ?, fecha_actualizacion = CURRENT_TIMESTAMP WHERE id = ?",
                    (payload["saldo_tecnico_a_favor_trasladable"], cierre_id),
                )
                _registrar_evento_cierre(cur, cierre_id, empresa_id, anio, mes, "SALDO_TECNICO_TRASLADADO", f"Saldo técnico trasladado al período {_periodo_texto(*_siguiente_periodo(anio, mes))}: {payload['saldo_tecnico_a_favor_trasladable']:.2f}. Movimiento fiscal #{mov_id}.", usuario)
        else:
            _registrar_evento_cierre(cur, cierre_id, empresa_id, anio, mes, "RECTIFICATIVA", f"{version_etiqueta}. Motivo: {motivo_rectificativa}. {impacto.get('mensaje', '')}", usuario)
            _marcar_periodo_siguiente_requiere_revision(cur, empresa_id, anio, mes, cierre_id, impacto, usuario)

        if payload["resultado_saldo"] == RESULTADO_A_PAGAR:
            _registrar_evento_cierre(cur, cierre_id, empresa_id, anio, mes, "OBLIGACION_GENERADA", f"Saldo IVA a pagar generado por {payload['saldo_a_pagar']:.2f}.", usuario)
        elif payload["resultado_saldo"] == RESULTADO_A_FAVOR:
            _registrar_evento_cierre(cur, cierre_id, empresa_id, anio, mes, "SALDO_A_FAVOR_GENERADO", f"Saldo a favor IVA generado por {payload['saldo_a_favor']:.2f}. Saldo técnico trasladable: {payload['saldo_tecnico_a_favor_trasladable']:.2f}.", usuario)

        for tipo, asiento in asientos.items():
            if not asiento.get("balanceado", True):
                _registrar_evento_cierre(cur, cierre_id, empresa_id, anio, mes, "ADVERTENCIA_ASIENTO", f"El asiento propuesto {tipo} no balancea. Diferencia: {asiento.get('diferencia', 0):.2f}.", usuario)

        conn.commit()
        cierre = obtener_cierre_periodo(empresa_id=empresa_id, anio=anio, mes=mes)
        return {"ok": True, "mensaje": f"Período IVA cerrado internamente como {version_etiqueta}.", "cierre": cierre, "control": control, "asientos": asientos, "impacto_rectificativa": impacto}
    except Exception as e:
        conn.rollback()
        return {"ok": False, "mensaje": f"No se pudo cerrar el período IVA: {e}", "control": control}
    finally:
        conn.close()


def reabrir_periodo_iva(empresa_id=1, anio=None, mes=None, usuario="sistema", motivo="", permitir_con_pagos=False, permitir_con_periodos_posteriores=False):
    asegurar_estructura_iva_cierres()
    anio = _int(anio)
    mes = _int(mes)
    motivo = _texto(motivo)
    if anio <= 0 or mes <= 0:
        return {"ok": False, "mensaje": "Debe indicarse un período válido para reabrir IVA."}
    if not motivo:
        return {"ok": False, "mensaje": "Debe indicarse un motivo para reabrir el período IVA."}
    cierre = obtener_cierre_periodo(empresa_id=empresa_id, anio=anio, mes=mes)
    if not cierre:
        return {"ok": False, "mensaje": "No existe cierre interno para el período indicado."}
    if cierre.get("estado") != ESTADO_CIERRE_CERRADO:
        return {"ok": False, "mensaje": "El período no está cerrado. No requiere reapertura.", "cierre": cierre}
    pagos = listar_pagos_cierre(cierre_id=int(cierre["id"]), empresa_id=empresa_id, incluir_anulados=False)
    if not pagos.empty and not permitir_con_pagos:
        return {"ok": False, "mensaje": "El período tiene pagos IVA registrados. Para reabrirlo debe confirmarse reapertura administrativa con pagos existentes.", "cierre": cierre, "pagos": pagos}
    posteriores = _obtener_periodos_posteriores_cerrados(empresa_id, anio, mes)
    if posteriores and not permitir_con_periodos_posteriores:
        return {"ok": False, "mensaje": "Existen períodos posteriores cerrados. Para reabrir debe confirmarse acción administrativa porque puede afectar saldos trasladados.", "cierre": cierre, "periodos_posteriores": posteriores}

    conn = conectar()
    cur = conn.cursor()
    try:
        cierre_id = int(cierre["id"])
        cur.execute(
            f"""
            UPDATE {TABLA_CIERRES}
            SET estado = ?, motivo_reapertura = ?, usuario_reapertura = ?, fecha_reapertura = CURRENT_TIMESTAMP, fecha_actualizacion = CURRENT_TIMESTAMP
            WHERE id = ? AND empresa_id = ?
            """,
            (ESTADO_CIERRE_REABIERTO, motivo, _texto(usuario, "sistema"), cierre_id, int(empresa_id)),
        )
        _registrar_evento_cierre(cur, cierre_id, empresa_id, anio, mes, "REAPERTURA", motivo, usuario)
        conn.commit()
        return {"ok": True, "mensaje": "Período IVA reabierto para corrección. El próximo cierre quedará como rectificativa.", "cierre": obtener_cierre_periodo(empresa_id=empresa_id, anio=anio, mes=mes)}
    except Exception as e:
        conn.rollback()
        return {"ok": False, "mensaje": f"No se pudo reabrir el período IVA: {e}", "cierre": cierre}
    finally:
        conn.close()


def _obtener_pago_dict(cur, pago_id, empresa_id=1):
    cur.execute(
        f"SELECT * FROM {TABLA_PAGOS} WHERE empresa_id = ? AND id = ? LIMIT 1",
        (int(empresa_id), int(pago_id)),
    )
    fila = cur.fetchone()
    if fila is None:
        return {}
    columnas = [c[0] for c in cur.description]
    return dict(zip(columnas, fila))


def _sumar_pagos_vigentes(cur, cierre_id, empresa_id=1):
    cur.execute(
        f"""
        SELECT
            COALESCE(SUM(importe), 0) AS importe_pagado,
            MAX(fecha_pago) AS fecha_ultimo_pago
        FROM {TABLA_PAGOS}
        WHERE empresa_id = ?
          AND cierre_id = ?
          AND estado = ?
        """,
        (int(empresa_id), int(cierre_id), ESTADO_PAGO_REGISTRADO),
    )
    fila = cur.fetchone()
    importe_pagado = _round2(fila[0] if fila else 0)
    fecha_ultimo_pago = fila[1] if fila else None
    return importe_pagado, fecha_ultimo_pago


def _actualizar_estado_pago_cierre(cur, cierre_id, empresa_id=1):
    cur.execute(
        f"SELECT saldo_a_pagar FROM {TABLA_CIERRES} WHERE empresa_id = ? AND id = ? LIMIT 1",
        (int(empresa_id), int(cierre_id)),
    )
    fila = cur.fetchone()
    if fila is None:
        raise ValueError("No se encontró el cierre IVA asociado al pago.")

    saldo_a_pagar = _round2(fila[0])
    importe_pagado, fecha_ultimo_pago = _sumar_pagos_vigentes(cur, cierre_id, empresa_id=empresa_id)
    estado_pago, pendiente = _estado_pago_desde_importes(saldo_a_pagar, importe_pagado)

    cur.execute(
        f"""
        UPDATE {TABLA_CIERRES}
        SET importe_pagado = ?,
            saldo_pendiente_pago = ?,
            estado_pago = ?,
            fecha_ultimo_pago = ?,
            fecha_actualizacion = CURRENT_TIMESTAMP
        WHERE id = ? AND empresa_id = ?
        """,
        (importe_pagado, pendiente, estado_pago, fecha_ultimo_pago, int(cierre_id), int(empresa_id)),
    )
    return {
        "importe_pagado": importe_pagado,
        "saldo_pendiente_pago": pendiente,
        "estado_pago": estado_pago,
        "fecha_ultimo_pago": fecha_ultimo_pago,
    }


def actualizar_datos_administrativos_pago_iva(
    pago_id,
    empresa_id=1,
    referencia=None,
    observacion=None,
    usuario="sistema",
    motivo="",
):
    """
    Corrige datos administrativos del pago IVA sin modificar importes ni asiento.

    Usar para errores de VEP/referencia/comprobante u observación. Deja evento
    de auditoría, pero no recalcula saldos ni asientos porque no cambia dinero.
    """
    asegurar_estructura_iva_cierres()
    pago_id = _int(pago_id)
    motivo = _texto(motivo)
    if pago_id <= 0:
        return {"ok": False, "mensaje": "Debe indicarse un pago válido."}
    if not motivo:
        return {"ok": False, "mensaje": "Debe indicarse motivo de corrección administrativa."}

    conn = conectar()
    cur = conn.cursor()
    try:
        pago = _obtener_pago_dict(cur, pago_id, empresa_id=empresa_id)
        if not pago:
            return {"ok": False, "mensaje": "No se encontró el pago IVA indicado."}
        if pago.get("estado") != ESTADO_PAGO_REGISTRADO:
            return {"ok": False, "mensaje": "Solo se pueden corregir pagos IVA vigentes.", "pago": pago}

        nueva_referencia = pago.get("referencia") if referencia is None else _texto(referencia)
        nueva_observacion = pago.get("observacion") if observacion is None else _texto(observacion)

        cur.execute(
            f"""
            UPDATE {TABLA_PAGOS}
            SET referencia = ?,
                observacion = ?,
                motivo_correccion = ?,
                usuario_correccion = ?,
                fecha_correccion = CURRENT_TIMESTAMP,
                fecha_actualizacion = CURRENT_TIMESTAMP
            WHERE empresa_id = ? AND id = ?
            """,
            (nueva_referencia, nueva_observacion, motivo, _texto(usuario, "sistema"), int(empresa_id), pago_id),
        )
        _registrar_evento_cierre(
            cur,
            int(pago["cierre_id"]),
            empresa_id,
            pago.get("anio"),
            pago.get("mes"),
            "PAGO_CORREGIDO_ADMIN",
            f"Pago IVA #{pago_id} corregido administrativamente. Motivo: {motivo}.",
            usuario,
        )
        conn.commit()
        return {
            "ok": True,
            "mensaje": "Datos administrativos del pago IVA actualizados correctamente.",
            "cierre": obtener_cierre_periodo(empresa_id=empresa_id, anio=pago.get("anio"), mes=pago.get("mes")),
        }
    except Exception as e:
        conn.rollback()
        return {"ok": False, "mensaje": f"No se pudo actualizar el pago IVA: {e}"}
    finally:
        conn.close()


def rectificar_pago_iva(
    pago_id,
    empresa_id=1,
    fecha_pago=None,
    importe=None,
    medio_pago=None,
    cuenta_codigo=None,
    cuenta_nombre=None,
    referencia=None,
    observacion=None,
    usuario="sistema",
    motivo="",
):
    """
    Rectifica un pago IVA con impacto económico/contable.

    No pisa el pago original: lo marca como RECTIFICADO, anula su asiento
    propuesto, crea un nuevo pago vigente y recalcula saldo pagado, saldo
    pendiente, estado de pago y asiento propuesto de pago.
    """
    asegurar_estructura_iva_cierres()
    pago_id = _int(pago_id)
    motivo = _texto(motivo)
    if pago_id <= 0:
        return {"ok": False, "mensaje": "Debe indicarse un pago válido."}
    if not motivo:
        return {"ok": False, "mensaje": "Debe indicarse motivo de rectificación del pago IVA."}

    conn = conectar()
    cur = conn.cursor()
    try:
        pago_original = _obtener_pago_dict(cur, pago_id, empresa_id=empresa_id)
        if not pago_original:
            return {"ok": False, "mensaje": "No se encontró el pago IVA indicado."}
        if pago_original.get("estado") != ESTADO_PAGO_REGISTRADO:
            return {"ok": False, "mensaje": "Solo se pueden rectificar pagos IVA vigentes.", "pago": pago_original}

        cierre_id = int(pago_original["cierre_id"])
        anio = _int(pago_original.get("anio"))
        mes = _int(pago_original.get("mes"))
        periodo = _periodo_texto(anio, mes)

        cur.execute(
            f"SELECT saldo_a_pagar FROM {TABLA_CIERRES} WHERE empresa_id = ? AND id = ? LIMIT 1",
            (int(empresa_id), cierre_id),
        )
        fila_cierre = cur.fetchone()
        if fila_cierre is None:
            return {"ok": False, "mensaje": "No se encontró el cierre IVA asociado al pago."}
        saldo_a_pagar = _round2(fila_cierre[0])

        nuevo_importe = _round2(pago_original.get("importe") if importe is None else importe)
        if nuevo_importe <= TOLERANCIA:
            return {"ok": False, "mensaje": "El importe rectificado del pago IVA debe ser mayor a cero."}

        # Capacidad de pago: saldo a pagar menos otros pagos vigentes distintos del original.
        cur.execute(
            f"""
            SELECT COALESCE(SUM(importe), 0)
            FROM {TABLA_PAGOS}
            WHERE empresa_id = ?
              AND cierre_id = ?
              AND estado = ?
              AND id <> ?
            """,
            (int(empresa_id), cierre_id, ESTADO_PAGO_REGISTRADO, pago_id),
        )
        otros_pagos = _round2(cur.fetchone()[0])
        disponible = max(round(saldo_a_pagar - otros_pagos, 2), 0.0)
        if nuevo_importe - disponible > TOLERANCIA:
            return {"ok": False, "mensaje": f"El pago rectificado supera el saldo disponible de IVA ({disponible:.2f})."}

        nuevo_medio = _texto(medio_pago, pago_original.get("medio_pago") or "MANUAL").upper()
        cuenta_default = MEDIOS_PAGO_CUENTA_DEFAULT.get(nuevo_medio, CUENTAS_IVA_DEFAULT["tesoreria_puente"])
        nuevo_cuenta_codigo = _texto(cuenta_codigo, pago_original.get("cuenta_codigo") or cuenta_default[0])
        nuevo_cuenta_nombre = _texto(cuenta_nombre, pago_original.get("cuenta_nombre") or cuenta_default[1])
        nueva_fecha = _fecha_texto(fecha_pago or pago_original.get("fecha_pago"))
        nueva_referencia = _texto(referencia, pago_original.get("referencia") or "")
        nueva_observacion = _texto(observacion, pago_original.get("observacion") or "")

        cur.execute(
            f"""
            UPDATE {TABLA_PAGOS}
            SET estado = ?,
                motivo_correccion = ?,
                usuario_correccion = ?,
                fecha_correccion = CURRENT_TIMESTAMP,
                fecha_actualizacion = CURRENT_TIMESTAMP
            WHERE empresa_id = ? AND id = ?
            """,
            (ESTADO_PAGO_RECTIFICADO, motivo, _texto(usuario, "sistema"), int(empresa_id), pago_id),
        )
        cur.execute(
            f"UPDATE {TABLA_ASIENTOS} SET estado = 'ANULADO' WHERE empresa_id = ? AND pago_id = ?",
            (int(empresa_id), pago_id),
        )

        cur.execute(
            f"""
            INSERT INTO {TABLA_PAGOS}
            (cierre_id, empresa_id, anio, mes, periodo, fecha_pago, importe, medio_pago, cuenta_codigo, cuenta_nombre,
             referencia, observacion, estado, pago_original_id, motivo_correccion, usuario_correccion, fecha_correccion,
             usuario, fecha_carga, fecha_actualizacion)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                cierre_id, int(empresa_id), anio, mes, periodo, nueva_fecha, nuevo_importe, nuevo_medio,
                nuevo_cuenta_codigo, nuevo_cuenta_nombre, nueva_referencia, nueva_observacion,
                ESTADO_PAGO_REGISTRADO, pago_id, motivo, _texto(usuario, "sistema"), _texto(usuario, "sistema"),
            ),
        )
        nuevo_pago_id = int(cur.lastrowid)

        asiento_pago = _armar_asiento_pago_iva(nuevo_importe, nuevo_medio, nuevo_cuenta_codigo, nuevo_cuenta_nombre)
        _insertar_asiento_lineas(
            cur,
            cierre_id,
            nuevo_pago_id,
            empresa_id,
            anio,
            mes,
            nueva_fecha,
            TIPO_ASIENTO_PAGO,
            asiento_pago["lineas"],
            f"Pago IVA rectificado período {periodo}",
            usuario,
        )
        estado_actualizado = _actualizar_estado_pago_cierre(cur, cierre_id, empresa_id=empresa_id)
        _registrar_evento_cierre(
            cur,
            cierre_id,
            empresa_id,
            anio,
            mes,
            "PAGO_RECTIFICADO",
            f"Pago IVA #{pago_id} rectificado por pago #{nuevo_pago_id}. Motivo: {motivo}. Pendiente: {estado_actualizado['saldo_pendiente_pago']:.2f}.",
            usuario,
        )
        conn.commit()
        return {
            "ok": True,
            "mensaje": "Pago IVA rectificado correctamente.",
            "pago_id": nuevo_pago_id,
            "pago_original_id": pago_id,
            "cierre": obtener_cierre_periodo(empresa_id=empresa_id, anio=anio, mes=mes),
            "asiento_pago": asiento_pago,
        }
    except Exception as e:
        conn.rollback()
        return {"ok": False, "mensaje": f"No se pudo rectificar el pago IVA: {e}"}
    finally:
        conn.close()


def registrar_pago_iva(empresa_id=1, anio=None, mes=None, fecha_pago=None, importe=0.0, medio_pago="MANUAL", cuenta_codigo=None, cuenta_nombre=None, referencia="", observacion="", usuario="sistema"):
    asegurar_estructura_iva_cierres()
    anio = _int(anio)
    mes = _int(mes)
    importe = _round2(importe)
    if anio <= 0 or mes <= 0:
        return {"ok": False, "mensaje": "Debe indicarse período válido para registrar pago IVA."}
    if importe <= TOLERANCIA:
        return {"ok": False, "mensaje": "El importe del pago IVA debe ser mayor a cero."}
    cierre = obtener_cierre_periodo(empresa_id=empresa_id, anio=anio, mes=mes)
    if not cierre:
        return {"ok": False, "mensaje": "No existe cierre IVA para registrar el pago."}
    if cierre.get("estado") != ESTADO_CIERRE_CERRADO:
        return {"ok": False, "mensaje": "Solo puede registrarse pago sobre un período IVA cerrado."}
    saldo_a_pagar = _round2(cierre.get("saldo_a_pagar"))
    importe_pagado_actual = _round2(cierre.get("importe_pagado"))
    pendiente_actual = max(round(saldo_a_pagar - importe_pagado_actual, 2), 0.0)
    if saldo_a_pagar <= TOLERANCIA:
        return {"ok": False, "mensaje": "El período no tiene saldo IVA a pagar."}
    if importe - pendiente_actual > TOLERANCIA:
        return {"ok": False, "mensaje": f"El pago supera el saldo pendiente de IVA ({pendiente_actual:.2f}).", "cierre": cierre}

    medio = _texto(medio_pago, "MANUAL").upper()
    cuenta_default = MEDIOS_PAGO_CUENTA_DEFAULT.get(medio, CUENTAS_IVA_DEFAULT["tesoreria_puente"])
    cuenta_codigo = _texto(cuenta_codigo, cuenta_default[0])
    cuenta_nombre = _texto(cuenta_nombre, cuenta_default[1])
    fecha_pago = _fecha_texto(fecha_pago)

    conn = conectar()
    cur = conn.cursor()
    try:
        cierre_id = int(cierre["id"])
        periodo = _periodo_texto(anio, mes)
        cur.execute(
            f"""
            INSERT INTO {TABLA_PAGOS}
            (cierre_id, empresa_id, anio, mes, periodo, fecha_pago, importe, medio_pago, cuenta_codigo, cuenta_nombre, referencia, observacion, estado, usuario, fecha_carga)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (cierre_id, int(empresa_id), anio, mes, periodo, fecha_pago, importe, medio, cuenta_codigo, cuenta_nombre, _texto(referencia), _texto(observacion), ESTADO_PAGO_REGISTRADO, _texto(usuario, "sistema")),
        )
        pago_id = int(cur.lastrowid)
        nuevo_pagado = _round2(importe_pagado_actual + importe)
        estado_pago, pendiente = _estado_pago_desde_importes(saldo_a_pagar, nuevo_pagado)
        cur.execute(
            f"""
            UPDATE {TABLA_CIERRES}
            SET importe_pagado = ?, saldo_pendiente_pago = ?, estado_pago = ?, fecha_ultimo_pago = ?, fecha_actualizacion = CURRENT_TIMESTAMP
            WHERE id = ? AND empresa_id = ?
            """,
            (nuevo_pagado, pendiente, estado_pago, fecha_pago, cierre_id, int(empresa_id)),
        )
        asiento_pago = _armar_asiento_pago_iva(importe, medio, cuenta_codigo, cuenta_nombre)
        _insertar_asiento_lineas(cur, cierre_id, pago_id, empresa_id, anio, mes, fecha_pago, TIPO_ASIENTO_PAGO, asiento_pago["lineas"], f"Pago IVA período {periodo}", usuario)
        _registrar_evento_cierre(cur, cierre_id, empresa_id, anio, mes, "PAGO_REGISTRADO", f"Pago IVA registrado por {importe:.2f}. Medio: {medio}. Pendiente: {pendiente:.2f}.", usuario)
        conn.commit()
        return {"ok": True, "mensaje": "Pago IVA registrado correctamente.", "pago_id": pago_id, "cierre": obtener_cierre_periodo(empresa_id=empresa_id, anio=anio, mes=mes), "asiento_pago": asiento_pago}
    except Exception as e:
        conn.rollback()
        return {"ok": False, "mensaje": f"No se pudo registrar el pago IVA: {e}", "cierre": cierre}
    finally:
        conn.close()


def anular_pago_iva(pago_id, empresa_id=1, usuario="sistema", motivo=""):
    asegurar_estructura_iva_cierres()
    pago_id = _int(pago_id)
    motivo = _texto(motivo)
    if pago_id <= 0:
        return {"ok": False, "mensaje": "Debe indicarse un pago válido."}
    if not motivo:
        return {"ok": False, "mensaje": "Debe indicarse motivo para anular el pago IVA."}
    conn = conectar()
    cur = conn.cursor()
    try:
        pago = _obtener_pago_dict(cur, pago_id, empresa_id=empresa_id)
        if not pago:
            return {"ok": False, "mensaje": "No se encontró el pago IVA indicado."}
        if pago.get("estado") == ESTADO_PAGO_ANULADO:
            return {"ok": False, "mensaje": "El pago IVA ya está anulado.", "pago": pago}
        if pago.get("estado") != ESTADO_PAGO_REGISTRADO:
            return {"ok": False, "mensaje": "Solo se pueden anular pagos IVA vigentes.", "pago": pago}

        cierre_id = int(pago["cierre_id"])
        cur.execute(
            f"""
            UPDATE {TABLA_PAGOS}
            SET estado = ?,
                fecha_anulacion = CURRENT_TIMESTAMP,
                motivo_anulacion = ?,
                usuario_correccion = ?,
                fecha_correccion = CURRENT_TIMESTAMP,
                fecha_actualizacion = CURRENT_TIMESTAMP
            WHERE empresa_id = ? AND id = ?
            """,
            (ESTADO_PAGO_ANULADO, motivo, _texto(usuario, "sistema"), int(empresa_id), pago_id),
        )
        cur.execute(
            f"UPDATE {TABLA_ASIENTOS} SET estado = 'ANULADO' WHERE empresa_id = ? AND pago_id = ?",
            (int(empresa_id), pago_id),
        )
        estado_actualizado = _actualizar_estado_pago_cierre(cur, cierre_id, empresa_id=empresa_id)
        _registrar_evento_cierre(
            cur,
            cierre_id,
            empresa_id,
            pago.get("anio"),
            pago.get("mes"),
            "PAGO_ANULADO",
            f"Pago IVA #{pago_id} anulado. Motivo: {motivo}. Pendiente: {estado_actualizado['saldo_pendiente_pago']:.2f}.",
            usuario,
        )
        conn.commit()
        return {"ok": True, "mensaje": "Pago IVA anulado correctamente.", "cierre": obtener_cierre_periodo(empresa_id=empresa_id, anio=pago.get("anio"), mes=pago.get("mes"))}
    except Exception as e:
        conn.rollback()
        return {"ok": False, "mensaje": f"No se pudo anular el pago IVA: {e}"}
    finally:
        conn.close()


# ======================================================
# CONSULTAS OPERATIVAS PARA REPORTES Y FUTURO ASISTENTE IA
# ======================================================

def _columnas_obligaciones_iva():
    return [
        "id",
        "empresa_id",
        "anio",
        "mes",
        "periodo",
        "concepto",
        "version_etiqueta",
        "estado",
        "estado_pago",
        "resultado_saldo",
        "saldo_a_pagar",
        "importe_pagado",
        "saldo_pendiente_pago",
        "fecha_cierre",
        "fecha_ultimo_pago",
        "usuario_cierre",
        "requiere_revision_por_rectificativa",
        "motivo_revision",
    ]


def listar_obligaciones_iva_pendientes(empresa_id=1, incluir_revision=True):
    """
    Devuelve obligaciones IVA pendientes de pago, una fila por cierre vigente.

    Esta función está pensada para:
    - tablero de IVA;
    - reportes de obligaciones fiscales;
    - futuro asistente IA/chatbot.

    No interpreta textos ni recorre tablas sueltas: expone una salida estable
    y controlada para responder preguntas como:
    "¿qué IVA tengo pendiente?", "¿cuánto debo?" o
    "¿qué períodos tienen pago parcial?".
    """
    asegurar_estructura_iva_cierres()

    columnas = _columnas_obligaciones_iva()
    try:
        df = ejecutar_query(
            f"""
            SELECT
                id,
                empresa_id,
                anio,
                mes,
                periodo,
                'IVA mensual' AS concepto,
                version_etiqueta,
                estado,
                estado_pago,
                resultado_saldo,
                saldo_a_pagar,
                importe_pagado,
                saldo_pendiente_pago,
                fecha_cierre,
                fecha_ultimo_pago,
                usuario_cierre,
                requiere_revision_por_rectificativa,
                motivo_revision
            FROM {TABLA_CIERRES}
            WHERE empresa_id = ?
              AND es_version_vigente = 1
              AND estado = ?
              AND saldo_pendiente_pago > ?
              AND estado_pago IN (?, ?)
            ORDER BY anio ASC, mes ASC, id ASC
            """,
            (
                int(empresa_id),
                ESTADO_CIERRE_CERRADO,
                TOLERANCIA,
                ESTADO_PAGO_PENDIENTE,
                ESTADO_PAGO_PARCIAL,
            ),
            fetch=True,
        )
        df = _resultado_a_dataframe(df)
    except Exception:
        df = pd.DataFrame(columns=columnas)

    if df.empty:
        return pd.DataFrame(columns=columnas)

    if not incluir_revision and "requiere_revision_por_rectificativa" in df.columns:
        df = df[pd.to_numeric(df["requiere_revision_por_rectificativa"], errors="coerce").fillna(0).astype(int) == 0].copy()

    for columna in ["saldo_a_pagar", "importe_pagado", "saldo_pendiente_pago"]:
        if columna in df.columns:
            df[columna] = pd.to_numeric(df[columna], errors="coerce").fillna(0.0).round(2)

    for columna in columnas:
        if columna not in df.columns:
            df[columna] = "" if columna not in {"saldo_a_pagar", "importe_pagado", "saldo_pendiente_pago"} else 0.0

    return df[columnas].copy()


def obtener_resumen_deuda_fiscal_iva(empresa_id=1):
    """
    Resumen ejecutivo de deuda IVA pendiente.

    Devuelve un dict estable para pantallas, reportes y futuro chatbot.
    """
    obligaciones = listar_obligaciones_iva_pendientes(empresa_id=empresa_id)

    if obligaciones.empty:
        return {
            "ok": True,
            "empresa_id": int(empresa_id),
            "cantidad_obligaciones": 0,
            "total_saldo_a_pagar": 0.0,
            "total_pagado": 0.0,
            "total_pendiente": 0.0,
            "periodos": [],
            "obligaciones": [],
            "mensaje": "No hay IVA pendiente de pago registrado en cierres vigentes.",
        }

    total_saldo = _round2(obligaciones["saldo_a_pagar"].sum())
    total_pagado = _round2(obligaciones["importe_pagado"].sum())
    total_pendiente = _round2(obligaciones["saldo_pendiente_pago"].sum())
    periodos = obligaciones["periodo"].astype(str).tolist()

    return {
        "ok": True,
        "empresa_id": int(empresa_id),
        "cantidad_obligaciones": int(len(obligaciones)),
        "total_saldo_a_pagar": total_saldo,
        "total_pagado": total_pagado,
        "total_pendiente": total_pendiente,
        "periodos": periodos,
        "obligaciones": obligaciones.to_dict(orient="records"),
        "mensaje": (
            f"Hay {len(obligaciones)} obligación(es) IVA pendiente(s) "
            f"por un total de {total_pendiente:.2f}."
        ),
    }


def listar_periodos_iva_requieren_revision(empresa_id=1):
    """
    Lista períodos vigentes que requieren revisión por rectificativas o ajustes.
    Sirve como base para alertas, reportes y futuro asistente IA.
    """
    asegurar_estructura_iva_cierres()
    columnas = [
        "id",
        "empresa_id",
        "anio",
        "mes",
        "periodo",
        "version_etiqueta",
        "estado",
        "requiere_revision_por_rectificativa",
        "motivo_revision",
        "cierre_origen_revision_id",
        "saldo_trasladado_original",
        "saldo_trasladado_rectificado",
        "diferencia_saldo_trasladado",
        "periodo_siguiente_afectado",
        "fecha_actualizacion",
    ]
    try:
        df = ejecutar_query(
            f"""
            SELECT
                id,
                empresa_id,
                anio,
                mes,
                periodo,
                version_etiqueta,
                estado,
                requiere_revision_por_rectificativa,
                motivo_revision,
                cierre_origen_revision_id,
                saldo_trasladado_original,
                saldo_trasladado_rectificado,
                diferencia_saldo_trasladado,
                periodo_siguiente_afectado,
                fecha_actualizacion
            FROM {TABLA_CIERRES}
            WHERE empresa_id = ?
              AND es_version_vigente = 1
              AND (
                    IFNULL(requiere_revision_por_rectificativa, 0) = 1
                    OR estado = ?
                  )
            ORDER BY anio ASC, mes ASC, id ASC
            """,
            (int(empresa_id), ESTADO_CIERRE_REQUIERE_REVISION),
            fetch=True,
        )
        df = _resultado_a_dataframe(df)
    except Exception:
        df = pd.DataFrame(columns=columnas)

    if df.empty:
        return pd.DataFrame(columns=columnas)

    for columna in columnas:
        if columna not in df.columns:
            df[columna] = ""

    return df[columnas].copy()


__all__ = [
    "TABLA_CIERRES", "TABLA_EVENTOS", "TABLA_PAGOS", "TABLA_ASIENTOS",
    "ESTADO_CIERRE_ABIERTO", "ESTADO_CIERRE_CERRADO", "ESTADO_CIERRE_REABIERTO", "ESTADO_CIERRE_RECTIFICADO", "ESTADO_CIERRE_REQUIERE_REVISION", "ESTADO_CIERRE_ANULADO_TECNICO",
    "VERSION_TIPO_ORIGINAL", "VERSION_TIPO_RECTIFICATIVA",
    "RESULTADO_A_PAGAR", "RESULTADO_A_FAVOR", "RESULTADO_CERO",
    "ESTADO_PAGO_NO_APLICA", "ESTADO_PAGO_PENDIENTE", "ESTADO_PAGO_PARCIAL", "ESTADO_PAGO_PAGADO", "ESTADO_PAGO_REGISTRADO", "ESTADO_PAGO_ANULADO",
    "TIPO_ASIENTO_LIQUIDACION", "TIPO_ASIENTO_PAGO", "TIPO_ASIENTO_RECTIFICATIVA",
    "asegurar_estructura_iva_cierres", "obtener_cierre_periodo", "listar_cierres_iva", "listar_versiones_periodo", "listar_eventos_cierre", "listar_pagos_cierre", "listar_asientos_cierre",
    "obtener_control_cierre_periodo", "armar_asiento_liquidacion_iva", "armar_asiento_ajuste_rectificativa",
    "cerrar_periodo_iva", "reabrir_periodo_iva", "registrar_pago_iva", "actualizar_datos_administrativos_pago_iva", "rectificar_pago_iva", "anular_pago_iva",
    "listar_obligaciones_iva_pendientes", "obtener_resumen_deuda_fiscal_iva", "listar_periodos_iva_requieren_revision",
]