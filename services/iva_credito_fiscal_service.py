from database import ejecutar_query


MODOS_CREDITO_FISCAL = {
    "SIN_PRORRATEO",
    "ASIGNACION_DIRECTA",
    "PRORRATEO_GLOBAL",
    "MIXTO",
    "SEGUN_PORTAL_IVA"
}


TRATAMIENTOS_IVA_CATEGORIA = {
    "GRAVADO_100",
    "EXENTO_0",
    "PRORRATEO_GLOBAL",
    "APROPIACION_DIRECTA",
    "SEGUN_PORTAL_IVA",
    "SEGUN_CONFIG_PERIODO"
}


def _float(valor, default=0):
    try:
        if valor is None:
            return default
        return float(valor)
    except Exception:
        return default


def _texto(valor, default=""):
    try:
        if valor is None:
            return default
        return str(valor).strip()
    except Exception:
        return default


def _coeficiente(valor, default=1):
    """
    Convierte porcentajes o coeficientes.

    Acepta:
    0.70
    70
    70.00

    Devuelve:
    0.70
    """
    coef = _float(valor, default)

    if coef > 1:
        coef = coef / 100

    if coef < 0:
        coef = 0

    if coef > 1:
        coef = 1

    return round(coef, 6)


def calcular_coeficiente_global(
    ventas_gravadas=0,
    ventas_exentas=0,
    ventas_no_gravadas=0,
    exportaciones=0
):
    """
    Coeficiente inicial para prorrateo global.

    Criterio:
    Numerador: ventas gravadas + exportaciones.
    Denominador: ventas gravadas + exportaciones + ventas exentas + ventas no gravadas.

    Esto después se puede ajustar por cliente o actividad.
    """
    ventas_gravadas = _float(ventas_gravadas)
    ventas_exentas = _float(ventas_exentas)
    ventas_no_gravadas = _float(ventas_no_gravadas)
    exportaciones = _float(exportaciones)

    numerador = ventas_gravadas + exportaciones
    denominador = ventas_gravadas + exportaciones + ventas_exentas + ventas_no_gravadas

    if denominador <= 0:
        return 1

    return round(numerador / denominador, 6)


def asegurar_estructura_iva_credito_fiscal():
    """
    Crea la estructura necesaria para determinar crédito fiscal computable
    según configuración del período y categoría de compra.
    """

    ejecutar_query("""
        CREATE TABLE IF NOT EXISTS iva_config_periodo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER DEFAULT 1,
            anio INTEGER,
            mes INTEGER,
            modo_credito_fiscal TEXT DEFAULT 'SEGUN_PORTAL_IVA',
            ventas_gravadas REAL DEFAULT 0,
            ventas_exentas REAL DEFAULT 0,
            ventas_no_gravadas REAL DEFAULT 0,
            exportaciones REAL DEFAULT 0,
            coeficiente_credito_fiscal REAL DEFAULT 1,
            usar_credito_fiscal TEXT DEFAULT 'SISTEMA',
            observacion TEXT,
            fecha_carga TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    columnas_categorias = {
        "tratamiento_iva": "TEXT DEFAULT 'SEGUN_CONFIG_PERIODO'",
        "porcentaje_iva_computable": "REAL DEFAULT NULL"
    }

    for columna, tipo in columnas_categorias.items():
        try:
            ejecutar_query(f"ALTER TABLE categorias_compra ADD COLUMN {columna} {tipo}")
        except Exception:
            pass

    columnas_compras = {
        "metodo_credito_fiscal": "TEXT",
        "coeficiente_iva_aplicado": "REAL DEFAULT 1",
        "iva_computable_sistema": "REAL DEFAULT 0",
        "iva_no_computable_sistema": "REAL DEFAULT 0",
        "iva_computable_csv": "REAL DEFAULT 0",
        "diferencia_iva_csv_sistema": "REAL DEFAULT 0"
    }

    for columna, tipo in columnas_compras.items():
        try:
            ejecutar_query(f"ALTER TABLE compras_comprobantes ADD COLUMN {columna} {tipo}")
        except Exception:
            pass


def guardar_config_iva_periodo(
    anio,
    mes,
    empresa_id=1,
    modo_credito_fiscal="SEGUN_PORTAL_IVA",
    ventas_gravadas=0,
    ventas_exentas=0,
    ventas_no_gravadas=0,
    exportaciones=0,
    coeficiente_credito_fiscal=None,
    usar_credito_fiscal="SISTEMA",
    observacion=""
):
    asegurar_estructura_iva_credito_fiscal()

    modo_credito_fiscal = _texto(modo_credito_fiscal, "SEGUN_PORTAL_IVA").upper()

    if modo_credito_fiscal not in MODOS_CREDITO_FISCAL:
        modo_credito_fiscal = "SEGUN_PORTAL_IVA"

    usar_credito_fiscal = _texto(usar_credito_fiscal, "SISTEMA").upper()

    if usar_credito_fiscal not in {"SISTEMA", "PORTAL_IVA", "COMPARAR"}:
        usar_credito_fiscal = "SISTEMA"

    ventas_gravadas = _float(ventas_gravadas)
    ventas_exentas = _float(ventas_exentas)
    ventas_no_gravadas = _float(ventas_no_gravadas)
    exportaciones = _float(exportaciones)

    if coeficiente_credito_fiscal is None:
        coeficiente_credito_fiscal = calcular_coeficiente_global(
            ventas_gravadas=ventas_gravadas,
            ventas_exentas=ventas_exentas,
            ventas_no_gravadas=ventas_no_gravadas,
            exportaciones=exportaciones
        )
    else:
        coeficiente_credito_fiscal = _coeficiente(coeficiente_credito_fiscal, 1)

    df = ejecutar_query("""
        SELECT id
        FROM iva_config_periodo
        WHERE empresa_id = ?
          AND anio = ?
          AND mes = ?
        ORDER BY id DESC
        LIMIT 1
    """, (empresa_id, anio, mes), fetch=True)

    if df.empty:
        ejecutar_query("""
            INSERT INTO iva_config_periodo
            (
                empresa_id,
                anio,
                mes,
                modo_credito_fiscal,
                ventas_gravadas,
                ventas_exentas,
                ventas_no_gravadas,
                exportaciones,
                coeficiente_credito_fiscal,
                usar_credito_fiscal,
                observacion
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            empresa_id,
            anio,
            mes,
            modo_credito_fiscal,
            ventas_gravadas,
            ventas_exentas,
            ventas_no_gravadas,
            exportaciones,
            coeficiente_credito_fiscal,
            usar_credito_fiscal,
            observacion
        ))
    else:
        id_config = int(df.iloc[0]["id"])

        ejecutar_query("""
            UPDATE iva_config_periodo
            SET
                modo_credito_fiscal = ?,
                ventas_gravadas = ?,
                ventas_exentas = ?,
                ventas_no_gravadas = ?,
                exportaciones = ?,
                coeficiente_credito_fiscal = ?,
                usar_credito_fiscal = ?,
                observacion = ?
            WHERE id = ?
        """, (
            modo_credito_fiscal,
            ventas_gravadas,
            ventas_exentas,
            ventas_no_gravadas,
            exportaciones,
            coeficiente_credito_fiscal,
            usar_credito_fiscal,
            observacion,
            id_config
        ))

    return obtener_config_iva_periodo(anio, mes, empresa_id)


def obtener_config_iva_periodo(anio, mes, empresa_id=1):
    asegurar_estructura_iva_credito_fiscal()

    df = ejecutar_query("""
        SELECT
            id,
            empresa_id,
            anio,
            mes,
            modo_credito_fiscal,
            ventas_gravadas,
            ventas_exentas,
            ventas_no_gravadas,
            exportaciones,
            coeficiente_credito_fiscal,
            usar_credito_fiscal,
            observacion
        FROM iva_config_periodo
        WHERE empresa_id = ?
          AND anio = ?
          AND mes = ?
        ORDER BY id DESC
        LIMIT 1
    """, (empresa_id, anio, mes), fetch=True)

    if df.empty:
        guardar_config_iva_periodo(
            anio=anio,
            mes=mes,
            empresa_id=empresa_id,
            modo_credito_fiscal="SEGUN_PORTAL_IVA",
            ventas_gravadas=0,
            ventas_exentas=0,
            ventas_no_gravadas=0,
            exportaciones=0,
            coeficiente_credito_fiscal=1,
            usar_credito_fiscal="SISTEMA",
            observacion="Configuración creada automáticamente. Usa crédito fiscal según Portal IVA hasta configurar el período."
        )

        return obtener_config_iva_periodo(anio, mes, empresa_id)

    fila = df.iloc[0]

    modo = _texto(fila["modo_credito_fiscal"], "SEGUN_PORTAL_IVA").upper()

    if modo not in MODOS_CREDITO_FISCAL:
        modo = "SEGUN_PORTAL_IVA"

    usar_credito_fiscal = _texto(fila["usar_credito_fiscal"], "SISTEMA").upper()

    if usar_credito_fiscal not in {"SISTEMA", "PORTAL_IVA", "COMPARAR"}:
        usar_credito_fiscal = "SISTEMA"

    return {
        "id": int(fila["id"]),
        "empresa_id": int(fila["empresa_id"]),
        "anio": int(fila["anio"]),
        "mes": int(fila["mes"]),
        "modo_credito_fiscal": modo,
        "ventas_gravadas": _float(fila["ventas_gravadas"]),
        "ventas_exentas": _float(fila["ventas_exentas"]),
        "ventas_no_gravadas": _float(fila["ventas_no_gravadas"]),
        "exportaciones": _float(fila["exportaciones"]),
        "coeficiente_credito_fiscal": _coeficiente(fila["coeficiente_credito_fiscal"], 1),
        "usar_credito_fiscal": usar_credito_fiscal,
        "observacion": _texto(fila["observacion"])
    }


def obtener_tratamiento_iva_categoria(categoria):
    asegurar_estructura_iva_credito_fiscal()

    try:
        df = ejecutar_query("""
            SELECT
                categoria,
                tratamiento_iva,
                porcentaje_iva_computable
            FROM categorias_compra
            WHERE categoria = ?
              AND activo = 1
            LIMIT 1
        """, (categoria,), fetch=True)
    except Exception:
        return {
            "tratamiento_iva": "SEGUN_CONFIG_PERIODO",
            "porcentaje_iva_computable": None
        }

    if df.empty:
        return {
            "tratamiento_iva": "SEGUN_CONFIG_PERIODO",
            "porcentaje_iva_computable": None
        }

    fila = df.iloc[0]

    tratamiento = _texto(fila["tratamiento_iva"], "SEGUN_CONFIG_PERIODO").upper()

    if tratamiento not in TRATAMIENTOS_IVA_CATEGORIA:
        tratamiento = "SEGUN_CONFIG_PERIODO"

    porcentaje = fila["porcentaje_iva_computable"]

    return {
        "tratamiento_iva": tratamiento,
        "porcentaje_iva_computable": porcentaje
    }


def _aplicar_tratamiento_categoria(
    iva_total,
    credito_fiscal_csv,
    tratamiento_iva,
    porcentaje_iva_computable,
    coeficiente_global
):
    iva_total = round(_float(iva_total), 2)
    credito_fiscal_csv = round(_float(credito_fiscal_csv), 2)
    coeficiente_global = _coeficiente(coeficiente_global, 1)

    if iva_total <= 0:
        return 0, 0, "SIN_IVA"

    if tratamiento_iva == "GRAVADO_100":
        return iva_total, 1, "GRAVADO_100"

    if tratamiento_iva == "EXENTO_0":
        return 0, 0, "EXENTO_0"

    if tratamiento_iva == "PRORRATEO_GLOBAL":
        iva_computable = round(iva_total * coeficiente_global, 2)
        return iva_computable, coeficiente_global, "PRORRATEO_GLOBAL"

    if tratamiento_iva == "APROPIACION_DIRECTA":
        coef = _coeficiente(porcentaje_iva_computable, 1)
        iva_computable = round(iva_total * coef, 2)
        return iva_computable, coef, "APROPIACION_DIRECTA"

    if tratamiento_iva == "SEGUN_PORTAL_IVA":
        iva_computable = min(max(credito_fiscal_csv, 0), iva_total)
        coef = round(iva_computable / iva_total, 6) if iva_total else 0
        return iva_computable, coef, "SEGUN_PORTAL_IVA"

    iva_computable = min(max(credito_fiscal_csv, 0), iva_total)
    coef = round(iva_computable / iva_total, 6) if iva_total else 0

    return iva_computable, coef, "SEGUN_PORTAL_IVA"


def calcular_credito_fiscal_compra(
    anio,
    mes,
    categoria_compra,
    iva_total,
    credito_fiscal_csv,
    comprobante_sin_iva=False,
    empresa_id=1
):
    """
    Determina:
    - IVA computable según sistema.
    - IVA no computable.
    - Método aplicado.
    - Diferencia contra Portal IVA.
    """

    asegurar_estructura_iva_credito_fiscal()

    iva_total = round(_float(iva_total), 2)
    credito_fiscal_csv = round(_float(credito_fiscal_csv), 2)

    advertencias = []

    if comprobante_sin_iva:
        iva_computable = 0
        iva_no_computable = 0
        diferencia = round(credito_fiscal_csv - iva_computable, 2)

        if abs(credito_fiscal_csv) > 0.05:
            advertencias.append(
                "El comprobante no discrimina IVA, pero el CSV informa crédito fiscal computable."
            )

        return {
            "metodo_credito_fiscal": "COMPROBANTE_SIN_IVA_DISCRIMINADO",
            "coeficiente_iva_aplicado": 0,
            "iva_computable_sistema": iva_computable,
            "iva_no_computable_sistema": iva_no_computable,
            "iva_computable_csv": credito_fiscal_csv,
            "diferencia_iva_csv_sistema": diferencia,
            "advertencias": advertencias
        }

    if iva_total <= 0:
        return {
            "metodo_credito_fiscal": "SIN_IVA",
            "coeficiente_iva_aplicado": 0,
            "iva_computable_sistema": 0,
            "iva_no_computable_sistema": 0,
            "iva_computable_csv": credito_fiscal_csv,
            "diferencia_iva_csv_sistema": round(credito_fiscal_csv, 2),
            "advertencias": advertencias
        }

    config = obtener_config_iva_periodo(anio, mes, empresa_id)
    categoria = obtener_tratamiento_iva_categoria(categoria_compra)

    modo = config["modo_credito_fiscal"]
    usar_credito_fiscal = config["usar_credito_fiscal"]
    coeficiente_global = config["coeficiente_credito_fiscal"]

    tratamiento_categoria = categoria["tratamiento_iva"]
    porcentaje_categoria = categoria["porcentaje_iva_computable"]

    if usar_credito_fiscal == "PORTAL_IVA" or modo == "SEGUN_PORTAL_IVA":
        iva_computable = min(max(credito_fiscal_csv, 0), iva_total)
        coef = round(iva_computable / iva_total, 6) if iva_total else 0
        metodo = "SEGUN_PORTAL_IVA"

    elif modo == "SIN_PRORRATEO":
        if tratamiento_categoria in {
            "GRAVADO_100",
            "EXENTO_0",
            "APROPIACION_DIRECTA",
            "PRORRATEO_GLOBAL",
            "SEGUN_PORTAL_IVA"
        }:
            iva_computable, coef, metodo = _aplicar_tratamiento_categoria(
                iva_total,
                credito_fiscal_csv,
                tratamiento_categoria,
                porcentaje_categoria,
                coeficiente_global
            )
        else:
            iva_computable = iva_total
            coef = 1
            metodo = "SIN_PRORRATEO"

    elif modo == "ASIGNACION_DIRECTA":
        if tratamiento_categoria == "SEGUN_CONFIG_PERIODO":
            iva_computable = min(max(credito_fiscal_csv, 0), iva_total)
            coef = round(iva_computable / iva_total, 6) if iva_total else 0
            metodo = "ASIGNACION_DIRECTA_SIN_CATEGORIA_USA_PORTAL_IVA"
            advertencias.append(
                f"La categoría '{categoria_compra}' no tiene tratamiento de IVA definido. "
                "Se usó el crédito fiscal informado por Portal IVA."
            )
        else:
            iva_computable, coef, metodo = _aplicar_tratamiento_categoria(
                iva_total,
                credito_fiscal_csv,
                tratamiento_categoria,
                porcentaje_categoria,
                coeficiente_global
            )

    elif modo == "PRORRATEO_GLOBAL":
        if tratamiento_categoria in {
            "GRAVADO_100",
            "EXENTO_0",
            "APROPIACION_DIRECTA",
            "SEGUN_PORTAL_IVA"
        }:
            iva_computable, coef, metodo = _aplicar_tratamiento_categoria(
                iva_total,
                credito_fiscal_csv,
                tratamiento_categoria,
                porcentaje_categoria,
                coeficiente_global
            )
        else:
            iva_computable = round(iva_total * coeficiente_global, 2)
            coef = coeficiente_global
            metodo = "PRORRATEO_GLOBAL"

    elif modo == "MIXTO":
        if tratamiento_categoria in {
            "GRAVADO_100",
            "EXENTO_0",
            "APROPIACION_DIRECTA",
            "SEGUN_PORTAL_IVA"
        }:
            iva_computable, coef, metodo = _aplicar_tratamiento_categoria(
                iva_total,
                credito_fiscal_csv,
                tratamiento_categoria,
                porcentaje_categoria,
                coeficiente_global
            )
        else:
            iva_computable = round(iva_total * coeficiente_global, 2)
            coef = coeficiente_global
            metodo = "MIXTO_PRORRATEO_GLOBAL"

    else:
        iva_computable = min(max(credito_fiscal_csv, 0), iva_total)
        coef = round(iva_computable / iva_total, 6) if iva_total else 0
        metodo = "SEGUN_PORTAL_IVA"

    iva_computable = round(min(max(iva_computable, 0), iva_total), 2)
    iva_no_computable = round(iva_total - iva_computable, 2)
    diferencia = round(credito_fiscal_csv - iva_computable, 2)

    if abs(diferencia) > 0.05:
        advertencias.append(
            "Diferencia entre crédito fiscal del Portal IVA y crédito fiscal calculado por el sistema. "
            f"Portal IVA: {credito_fiscal_csv}. "
            f"Sistema: {iva_computable}. "
            f"Diferencia: {diferencia}."
        )

    if iva_no_computable > 0.05:
        advertencias.append(
            f"IVA no computable determinado por el sistema: {iva_no_computable}."
        )

    return {
        "metodo_credito_fiscal": metodo,
        "coeficiente_iva_aplicado": coef,
        "iva_computable_sistema": iva_computable,
        "iva_no_computable_sistema": iva_no_computable,
        "iva_computable_csv": credito_fiscal_csv,
        "diferencia_iva_csv_sistema": diferencia,
        "advertencias": advertencias
    }