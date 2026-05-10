from __future__ import annotations

import csv
import json
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from services.plan_cuentas_maestro_service import asegurar_estructura_maestro


CSV_DEFAULT = Path("data/plan_cuentas_maestro_ff.csv")
VERSION_PLAN_DEFAULT = "FF-PDF-2026-01"


COLUMNAS_PLAN_MAESTRO = [
    "version_plan_id",
    "codigo",
    "nombre",
    "elemento",
    "clasificacion_corriente_no_corriente",
    "rubro",
    "cuenta",
    "subcuenta",
    "codigo_madre",
    "nivel",
    "orden",
    "imputable",
    "requiere_auxiliar",
    "tipo_auxiliar",
    "es_regularizadora",
    "cuenta_regularizada_codigo",
    "tipo_regularizadora",
    "saldo_normal",
    "significado_saldo_normal",
    "permite_saldo_deudor",
    "significado_saldo_deudor",
    "permite_saldo_acreedor",
    "significado_saldo_acreedor",
    "alertar_saldo_invertido",
    "tratamiento_saldo_invertido",
    "requiere_reclasificacion_saldo_invertido",
    "monetaria_no_monetaria",
    "criterio_medicion",
    "ajustable",
    "participa_recpam",
    "admite_moneda_extranjera",
    "requiere_tipo_cambio",
    "genera_diferencia_cambio",
    "es_cuenta_modelo",
    "permite_copiar_modelo",
    "uso_operativo_sistema",
    "modulo_sugerido",
    "presentacion_estado_contable",
    "orden_presentacion",
    "cuando_debitar",
    "cuando_acreditar",
    "errores_frecuentes",
    "observaciones",
    "estado",
    "vigencia_desde",
    "vigencia_hasta",
]

CAMPOS_ENTEROS = {
    "version_plan_id",
    "nivel",
    "orden",
    "imputable",
    "requiere_auxiliar",
    "es_regularizadora",
    "permite_saldo_deudor",
    "permite_saldo_acreedor",
    "alertar_saldo_invertido",
    "requiere_reclasificacion_saldo_invertido",
    "ajustable",
    "participa_recpam",
    "admite_moneda_extranjera",
    "requiere_tipo_cambio",
    "genera_diferencia_cambio",
    "es_cuenta_modelo",
    "permite_copiar_modelo",
    "orden_presentacion",
}

ESTADOS_VALIDOS = {"ACTIVA", "INACTIVA", "ANULADA", "BORRADOR"}
SALDOS_VALIDOS = {"DEUDOR", "ACREEDOR", "SEGUN_NATURALEZA", "NO_APLICA"}


USOS_OPERATIVOS_SEED_COMPLEMENTARIOS = [
    {
        "codigo": "FONDO_COMUN_INVERSION",
        "nombre": "Fondo común de inversión",
        "descripcion": "Cuenta modelo para inversiones en fondos comunes de inversión.",
        "tipo_uso": "INVERSIONES",
        "modulo_sugerido": "Banco/Caja",
        "requiere_cuenta_imputable": 1,
        "permite_multiples_cuentas_por_empresa": 1,
        "visible_en_ui": 0,
    },
    {
        "codigo": "BIENES_USO_INMUEBLES",
        "nombre": "Inmuebles",
        "descripcion": "Cuenta modelo para bienes de uso inmuebles específicos por empresa.",
        "tipo_uso": "ACTIVO",
        "modulo_sugerido": "Compras/Contabilidad",
        "requiere_cuenta_imputable": 1,
        "permite_multiples_cuentas_por_empresa": 1,
        "visible_en_ui": 0,
    },
]


@dataclass(frozen=True)
class ResultadoValidacionSeed:
    ok: bool
    errores: list[str]
    advertencias: list[str]
    total_filas: int
    codigos: list[str]


def _conectar_default() -> sqlite3.Connection:
    from database import conectar

    return conectar()


def _asegurar_row_factory(conn: sqlite3.Connection) -> None:
    if conn.row_factory is None:
        conn.row_factory = sqlite3.Row


def _limpiar(valor: Any) -> str:
    if valor is None:
        return ""
    return str(valor).strip()


def _upper(valor: Any) -> str:
    return _limpiar(valor).upper()


def _normalizar_ascii(valor: Any) -> str:
    texto = unicodedata.normalize("NFKD", _upper(valor))
    texto = "".join(ch for ch in texto if not unicodedata.combining(ch))
    texto = texto.replace("Ñ", "N")
    texto = re.sub(r"[^A-Z0-9]+", "_", texto)
    return re.sub(r"_+", "_", texto).strip("_")


def _to_int(valor: Any, default: int = 0) -> int:
    if valor is None:
        return default
    if isinstance(valor, bool):
        return int(valor)
    if isinstance(valor, (int, float)):
        return int(valor)

    texto = _upper(valor)
    if texto == "":
        return default
    if texto in {"S", "SI", "SÍ", "TRUE", "Y", "YES", "ACTIVO", "ACTIVA"}:
        return 1
    if texto in {"N", "NO", "FALSE", "INACTIVO", "INACTIVA", "ANULADO", "ANULADA"}:
        return 0

    try:
        return int(float(texto.replace(",", ".")))
    except Exception:
        return default


def _json(valor: Any) -> str:
    try:
        return json.dumps(valor, ensure_ascii=False, default=str, sort_keys=True)
    except Exception:
        return str(valor)


def _fetch_dicts(
    conn: sqlite3.Connection,
    sql: str,
    params: tuple[Any, ...] = (),
) -> list[dict[str, Any]]:
    cur = conn.execute(sql, params)
    filas = cur.fetchall()
    if not filas:
        return []
    if isinstance(filas[0], sqlite3.Row):
        return [dict(fila) for fila in filas]
    columnas = [col[0] for col in cur.description]
    return [dict(zip(columnas, fila)) for fila in filas]


def _tabla_existe(conn: sqlite3.Connection, tabla: str) -> bool:
    return conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
        LIMIT 1
        """,
        (tabla,),
    ).fetchone() is not None


def _columnas(conn: sqlite3.Connection, tabla: str) -> set[str]:
    if not _tabla_existe(conn, tabla):
        return set()
    return {str(fila[1]) for fila in conn.execute(f"PRAGMA table_info({tabla})").fetchall()}


def _leer_csv(ruta_csv: str | Path = CSV_DEFAULT) -> list[dict[str, Any]]:
    ruta = Path(ruta_csv)
    if not ruta.exists():
        raise FileNotFoundError(f"No existe el archivo CSV del Plan Maestro FF: {ruta}")

    texto = ruta.read_text(encoding="utf-8-sig")
    muestra = texto[:4096]
    dialecto = csv.Sniffer().sniff(muestra) if muestra.strip() else csv.excel

    with ruta.open("r", encoding="utf-8-sig", newline="") as archivo:
        reader = csv.DictReader(archivo, dialect=dialecto)
        filas = []
        for numero, fila in enumerate(reader, start=2):
            fila_limpia = {str(k or "").strip(): _limpiar(v) for k, v in fila.items()}
            fila_limpia["__linea_csv"] = numero
            if any(v for k, v in fila_limpia.items() if not k.startswith("__")):
                filas.append(fila_limpia)
        return filas


def _inferir_elemento(codigo: str, nombre: str = "") -> str:
    if codigo.startswith("1."):
        return "ACTIVO"
    if codigo.startswith("2."):
        return "PASIVO"
    if codigo.startswith("3."):
        return "PATRIMONIO_NETO"
    if codigo.startswith("4."):
        return "CUENTAS_MOVIMIENTO"
    if codigo.startswith("5."):
        return "INGRESOS_GANANCIAS"
    if codigo.startswith("6."):
        return "EGRESOS_GASTOS_PERDIDAS"
    if "RECPAM" in _normalizar_ascii(nombre):
        return "RECPAM"
    return "SIN_CLASIFICAR"


def _inferir_clasificacion(codigo: str, elemento: str) -> str:
    if codigo.startswith(("1.10", "1.1.")):
        return "CORRIENTE"
    if codigo.startswith(("1.20", "1.2.")):
        return "NO_CORRIENTE"
    if codigo.startswith(("2.10", "2.1.")):
        return "CORRIENTE"
    if codigo.startswith(("2.20", "2.2.")):
        return "NO_CORRIENTE"
    if elemento in {"ACTIVO", "PASIVO"}:
        return "SIN_CLASIFICAR"
    return "NO_APLICA"


def _es_regularizadora(nombre: str, valor_csv: Any = None) -> int:
    valor_limpio = _limpiar(valor_csv)
    if valor_limpio != "":
        return _to_int(valor_limpio, 0)

    nombre_norm = _normalizar_ascii(nombre)
    if nombre.strip().startswith("(-)"):
        return 1

    patrones = [
        "AMORTIZACION_ACUM",
        "INTERESES_POSITIVOS_A_DEVENGAR",
        "INTERESES_NEGATIVOS_A_DEVENGAR",
        "COMISIONES_NEGATIVAS_A_DEVENGAR",
    ]
    return 1 if any(p in nombre_norm for p in patrones) else 0


def _inferir_saldo_normal(elemento: str, nombre: str, es_regularizadora: int) -> str:
    nombre_norm = _normalizar_ascii(nombre)
    if "RECPAM" in nombre_norm:
        return "SEGUN_NATURALEZA"
    if elemento == "ACTIVO":
        return "ACREEDOR" if es_regularizadora else "DEUDOR"
    if elemento == "PASIVO":
        return "DEUDOR" if es_regularizadora else "ACREEDOR"
    if elemento in {"PATRIMONIO_NETO", "INGRESOS_GANANCIAS"}:
        return "ACREEDOR"
    if elemento in {"CUENTAS_MOVIMIENTO", "EGRESOS_GASTOS_PERDIDAS"}:
        return "DEUDOR"
    return "NO_APLICA"


def _significados_saldo(elemento: str, nombre: str, saldo_normal: str) -> dict[str, Any]:
    nombre_norm = _normalizar_ascii(nombre)

    base = {
        "significado_saldo_normal": "Naturaleza contable de la cuenta según su elemento y rubro.",
        "permite_saldo_deudor": 1 if saldo_normal in {"DEUDOR", "SEGUN_NATURALEZA"} else 0,
        "significado_saldo_deudor": "Saldo deudor según movimientos registrados.",
        "permite_saldo_acreedor": 1 if saldo_normal in {"ACREEDOR", "SEGUN_NATURALEZA"} else 0,
        "significado_saldo_acreedor": "Saldo acreedor según movimientos registrados.",
        "alertar_saldo_invertido": 0,
        "tratamiento_saldo_invertido": "PERMITIR",
        "requiere_reclasificacion_saldo_invertido": 0,
    }

    if "CAJA" in nombre_norm or "FONDO_FIJO" in nombre_norm:
        base.update(
            significado_saldo_normal="Representa dinero físico, fondos fijos o valores disponibles bajo custodia.",
            permite_saldo_deudor=1,
            significado_saldo_deudor="Disponibilidades existentes.",
            permite_saldo_acreedor=0,
            significado_saldo_acreedor="Indicaría egresos no respaldados, error de carga o falta de registración de ingresos.",
            alertar_saldo_invertido=1,
            tratamiento_saldo_invertido="BLOQUEAR_O_REVISAR",
        )
    elif "BANCO" in nombre_norm or "CUENTA_CORRIENTE" in nombre_norm or "BILLETERA" in nombre_norm:
        base.update(
            significado_saldo_normal="Representa fondos disponibles en bancos, cuentas bancarias o billeteras virtuales.",
            permite_saldo_deudor=1,
            significado_saldo_deudor="Fondos disponibles.",
            permite_saldo_acreedor=1,
            significado_saldo_acreedor="Puede representar giro en descubierto, sobregiro o deuda bancaria a reclasificar.",
            alertar_saldo_invertido=1,
            tratamiento_saldo_invertido="ADVERTIR_RECLASIFICAR",
            requiere_reclasificacion_saldo_invertido=1,
        )
    elif "DEUDORES_POR_VENTAS" in nombre_norm or "CLIENTES" in nombre_norm:
        base.update(
            significado_saldo_normal="Representa créditos pendientes de cobro por ventas.",
            permite_saldo_deudor=1,
            significado_saldo_deudor="Importes a cobrar a clientes.",
            permite_saldo_acreedor=1,
            significado_saldo_acreedor="Puede representar anticipos de clientes, cobros en exceso o notas de crédito pendientes.",
            alertar_saldo_invertido=1,
            tratamiento_saldo_invertido="ADVERTIR_RECLASIFICAR",
            requiere_reclasificacion_saldo_invertido=1,
        )
    elif "PROVEEDORES" in nombre_norm:
        base.update(
            significado_saldo_normal="Representa deudas comerciales pendientes de pago.",
            permite_saldo_deudor=1,
            significado_saldo_deudor="Puede representar anticipos a proveedores, pagos en exceso o notas de crédito pendientes.",
            permite_saldo_acreedor=1,
            significado_saldo_acreedor="Deuda comercial pendiente.",
            alertar_saldo_invertido=1,
            tratamiento_saldo_invertido="ADVERTIR_RECLASIFICAR",
            requiere_reclasificacion_saldo_invertido=1,
        )
    elif "IVA_CREDITO" in nombre_norm:
        base.update(
            significado_saldo_normal="Representa crédito fiscal computable a favor de la empresa.",
            permite_saldo_deudor=1,
            significado_saldo_deudor="Crédito fiscal computable disponible.",
            permite_saldo_acreedor=1,
            significado_saldo_acreedor="Puede indicar ajuste, rectificativa, compensación mal aplicada o error de imputación.",
            alertar_saldo_invertido=1,
            tratamiento_saldo_invertido="ALERTA_FISCAL",
        )
    elif "IVA_DEBITO" in nombre_norm:
        base.update(
            significado_saldo_normal="Representa débito fiscal generado por ventas gravadas.",
            permite_saldo_deudor=1,
            significado_saldo_deudor="Puede surgir por notas de crédito, rectificativas o ajustes fiscales.",
            permite_saldo_acreedor=1,
            significado_saldo_acreedor="Débito fiscal devengado.",
            alertar_saldo_invertido=1,
            tratamiento_saldo_invertido="ADVERTIR",
        )
    elif "RECPAM" in nombre_norm:
        base.update(
            significado_saldo_normal="Resultado por exposición al cambio en el poder adquisitivo de la moneda.",
            permite_saldo_deudor=1,
            significado_saldo_deudor="Pérdida por exposición al cambio en el poder adquisitivo de la moneda.",
            permite_saldo_acreedor=1,
            significado_saldo_acreedor="Ganancia por exposición al cambio en el poder adquisitivo de la moneda.",
            alertar_saldo_invertido=0,
            tratamiento_saldo_invertido="PERMITIR",
        )
    elif saldo_normal == "DEUDOR":
        base.update(
            permite_saldo_deudor=1,
            significado_saldo_deudor="Saldo propio de una cuenta de naturaleza deudora.",
            permite_saldo_acreedor=1,
            significado_saldo_acreedor="Saldo invertido que debe analizarse según la operación que lo originó.",
            alertar_saldo_invertido=1,
            tratamiento_saldo_invertido="ADVERTIR",
        )
    elif saldo_normal == "ACREEDOR":
        base.update(
            permite_saldo_deudor=1,
            significado_saldo_deudor="Saldo invertido que debe analizarse según la operación que lo originó.",
            permite_saldo_acreedor=1,
            significado_saldo_acreedor="Saldo propio de una cuenta de naturaleza acreedora.",
            alertar_saldo_invertido=1,
            tratamiento_saldo_invertido="ADVERTIR",
        )

    return base


def _inferir_monetaria(nombre: str, elemento: str) -> str:
    nombre_norm = _normalizar_ascii(nombre)
    if elemento not in {"ACTIVO", "PASIVO", "PATRIMONIO_NETO"}:
        return "NO_APLICA"
    no_monetaria = [
        "BIENES_DE_CAMBIO",
        "MERCADERIAS",
        "MATERIAS_PRIMAS",
        "BIENES_DE_USO",
        "RODADOS",
        "INSTALACIONES",
        "MUEBLES",
        "MAQUINARIAS",
        "INMUEBLES",
        "INTANGIBLES",
        "MARCAS",
        "PATENTES",
        "LLAVE_DE_NEGOCIO",
        "CAPITAL",
        "RESERVA",
    ]
    if any(p in nombre_norm for p in no_monetaria):
        return "NO_MONETARIA"
    return "MONETARIA"


def _inferir_criterio_medicion(nombre: str, elemento: str, monetaria: str) -> str:
    nombre_norm = _normalizar_ascii(nombre)
    if elemento in {"INGRESOS_GANANCIAS", "EGRESOS_GASTOS_PERDIDAS", "CUENTAS_MOVIMIENTO"}:
        return "DEVENGADO"
    if "MONEDA_EXTRANJERA" in nombre_norm or "DOLARES" in nombre_norm or "EUROS" in nombre_norm:
        return "VALOR_NOMINAL_MONEDA_EXTRANJERA_TIPO_CAMBIO_CIERRE"
    if "TITULOS" in nombre_norm or "ACCIONES" in nombre_norm or "FONDO_COMUN" in nombre_norm:
        return "VALOR_RAZONABLE_O_COSTO_SEGUN_NORMATIVA"
    if monetaria == "MONETARIA":
        return "VALOR_NOMINAL"
    if monetaria == "NO_MONETARIA":
        return "COSTO_AJUSTADO_AMORTIZADO_O_VALOR_RECUPERABLE_SEGUN_CORRESPONDA"
    return "SEGUN_NORMATIVA_CONTABLE"


def _inferir_presentacion(elemento: str, clasificacion: str, nombre: str) -> str:
    nombre_norm = _normalizar_ascii(nombre)
    if "RECPAM" in nombre_norm:
        return "ESTADO_RESULTADOS_RECPAM"
    if elemento == "ACTIVO":
        return "ESTADO_SITUACION_PATRIMONIAL_ACTIVO_CORRIENTE" if clasificacion == "CORRIENTE" else "ESTADO_SITUACION_PATRIMONIAL_ACTIVO_NO_CORRIENTE"
    if elemento == "PASIVO":
        return "ESTADO_SITUACION_PATRIMONIAL_PASIVO_CORRIENTE" if clasificacion == "CORRIENTE" else "ESTADO_SITUACION_PATRIMONIAL_PASIVO_NO_CORRIENTE"
    if elemento == "PATRIMONIO_NETO":
        return "ESTADO_SITUACION_PATRIMONIAL_PATRIMONIO_NETO"
    if elemento in {"INGRESOS_GANANCIAS", "EGRESOS_GASTOS_PERDIDAS"}:
        return "ESTADO_RESULTADOS"
    if elemento == "CUENTAS_MOVIMIENTO":
        return "CUENTAS_DE_MOVIMIENTO"
    return ""


def _normalizar_fila(fila: dict[str, Any], codigos_con_hijos: set[str]) -> dict[str, Any]:
    codigo = _limpiar(fila.get("codigo"))
    nombre = _limpiar(fila.get("nombre"))
    codigo_madre = _limpiar(fila.get("codigo_madre"))

    elemento = _upper(fila.get("elemento")) or _inferir_elemento(codigo, nombre)
    clasificacion = _upper(fila.get("clasificacion_corriente_no_corriente")) or _inferir_clasificacion(codigo, elemento)
    regularizadora = _es_regularizadora(nombre, fila.get("es_regularizadora"))
    saldo_normal = _upper(fila.get("saldo_normal")) or _inferir_saldo_normal(elemento, nombre, regularizadora)
    if saldo_normal not in SALDOS_VALIDOS:
        saldo_normal = _inferir_saldo_normal(elemento, nombre, regularizadora)

    significados = _significados_saldo(elemento, nombre, saldo_normal)
    monetaria = _upper(fila.get("monetaria_no_monetaria")) or _inferir_monetaria(nombre, elemento)

    admite_me = _to_int(fila.get("admite_moneda_extranjera"), -1)
    nombre_norm = _normalizar_ascii(nombre)
    if admite_me < 0:
        admite_me = 1 if any(p in nombre_norm for p in ["MONEDA_EXTRANJERA", "DOLARES", "EUROS", "EXTERIOR"]) else 0
    requiere_tc = _to_int(fila.get("requiere_tipo_cambio"), admite_me)
    genera_dc = _to_int(fila.get("genera_diferencia_cambio"), admite_me)

    ajustable_csv = fila.get("ajustable")
    ajustable = _to_int(ajustable_csv, 1 if monetaria == "NO_MONETARIA" and elemento in {"ACTIVO", "PATRIMONIO_NETO"} else 0)
    participa_recpam = _to_int(
        fila.get("participa_recpam"),
        1 if elemento in {"ACTIVO", "PASIVO", "PATRIMONIO_NETO"} else 0,
    )

    imputable_default = 0 if codigo in codigos_con_hijos else 1

    normalizada = {
        "codigo": codigo,
        "nombre": nombre,
        "elemento": elemento,
        "clasificacion_corriente_no_corriente": clasificacion,
        "rubro": _limpiar(fila.get("rubro")),
        "cuenta": _limpiar(fila.get("cuenta")),
        "subcuenta": _limpiar(fila.get("subcuenta")),
        "codigo_madre": codigo_madre,
        "nivel": _to_int(fila.get("nivel"), max(1, codigo.count(".") + 1)),
        "orden": _to_int(fila.get("orden"), 0),
        "imputable": _to_int(fila.get("imputable"), imputable_default),
        "requiere_auxiliar": _to_int(fila.get("requiere_auxiliar"), 0),
        "tipo_auxiliar": _limpiar(fila.get("tipo_auxiliar")),
        "es_regularizadora": regularizadora,
        "cuenta_regularizada_codigo": _limpiar(fila.get("cuenta_regularizada_codigo")) or (codigo_madre if regularizadora else ""),
        "tipo_regularizadora": _limpiar(fila.get("tipo_regularizadora")),
        "saldo_normal": saldo_normal,
        "significado_saldo_normal": _limpiar(fila.get("significado_saldo_normal")) or significados["significado_saldo_normal"],
        "permite_saldo_deudor": _to_int(fila.get("permite_saldo_deudor"), int(significados["permite_saldo_deudor"])),
        "significado_saldo_deudor": _limpiar(fila.get("significado_saldo_deudor")) or str(significados["significado_saldo_deudor"]),
        "permite_saldo_acreedor": _to_int(fila.get("permite_saldo_acreedor"), int(significados["permite_saldo_acreedor"])),
        "significado_saldo_acreedor": _limpiar(fila.get("significado_saldo_acreedor")) or str(significados["significado_saldo_acreedor"]),
        "alertar_saldo_invertido": _to_int(fila.get("alertar_saldo_invertido"), int(significados["alertar_saldo_invertido"])),
        "tratamiento_saldo_invertido": _limpiar(fila.get("tratamiento_saldo_invertido")) or str(significados["tratamiento_saldo_invertido"]),
        "requiere_reclasificacion_saldo_invertido": _to_int(
            fila.get("requiere_reclasificacion_saldo_invertido"),
            int(significados["requiere_reclasificacion_saldo_invertido"]),
        ),
        "monetaria_no_monetaria": monetaria,
        "criterio_medicion": _limpiar(fila.get("criterio_medicion")) or _inferir_criterio_medicion(nombre, elemento, monetaria),
        "ajustable": ajustable,
        "participa_recpam": participa_recpam,
        "admite_moneda_extranjera": admite_me,
        "requiere_tipo_cambio": requiere_tc,
        "genera_diferencia_cambio": genera_dc,
        "es_cuenta_modelo": _to_int(fila.get("es_cuenta_modelo"), 0),
        "permite_copiar_modelo": _to_int(fila.get("permite_copiar_modelo"), 0),
        "uso_operativo_sistema": _normalizar_ascii(fila.get("uso_operativo_sistema")),
        "modulo_sugerido": _limpiar(fila.get("modulo_sugerido")),
        "presentacion_estado_contable": _limpiar(fila.get("presentacion_estado_contable")) or _inferir_presentacion(elemento, clasificacion, nombre),
        "orden_presentacion": _to_int(fila.get("orden_presentacion"), _to_int(fila.get("orden"), 0)),
        "cuando_debitar": _limpiar(fila.get("cuando_debitar")),
        "cuando_acreditar": _limpiar(fila.get("cuando_acreditar")),
        "errores_frecuentes": _limpiar(fila.get("errores_frecuentes")),
        "observaciones": _limpiar(fila.get("observaciones")),
        "estado": _upper(fila.get("estado")) or "ACTIVA",
        "vigencia_desde": _limpiar(fila.get("vigencia_desde")),
        "vigencia_hasta": _limpiar(fila.get("vigencia_hasta")),
    }

    if normalizada["estado"] not in ESTADOS_VALIDOS:
        normalizada["estado"] = "ACTIVA"

    return normalizada


def validar_csv_plan_maestro(
    ruta_csv: str | Path = CSV_DEFAULT,
) -> ResultadoValidacionSeed:
    errores: list[str] = []
    advertencias: list[str] = []

    filas = _leer_csv(ruta_csv)
    codigos: list[str] = []
    vistos: set[str] = set()
    madres: set[str] = set()

    for fila in filas:
        linea = int(fila.get("__linea_csv") or 0)
        codigo = _limpiar(fila.get("codigo"))
        nombre = _limpiar(fila.get("nombre"))
        madre = _limpiar(fila.get("codigo_madre"))

        if not codigo:
            errores.append(f"Línea {linea}: falta código.")
            continue
        if not nombre:
            errores.append(f"Línea {linea}: falta nombre para código {codigo}.")
            continue
        if codigo in vistos:
            errores.append(f"Línea {linea}: código duplicado {codigo}.")
        vistos.add(codigo)
        codigos.append(codigo)
        if madre:
            madres.add(madre)

        saldo = _upper(fila.get("saldo_normal"))
        if saldo and saldo not in SALDOS_VALIDOS:
            errores.append(f"Línea {linea}: saldo_normal inválido {saldo} en {codigo}.")

        estado = _upper(fila.get("estado"))
        if estado and estado not in ESTADOS_VALIDOS:
            errores.append(f"Línea {linea}: estado inválido {estado} en {codigo}.")

    for madre in sorted(madres):
        if madre not in vistos:
            advertencias.append(f"Código madre no incluido en CSV: {madre}.")

    return ResultadoValidacionSeed(
        ok=not errores,
        errores=errores,
        advertencias=advertencias,
        total_filas=len(filas),
        codigos=codigos,
    )


def _obtener_o_crear_version_plan(
    conn: sqlite3.Connection,
    *,
    version: str,
    descripcion: str,
    estado: str = "BORRADOR",
) -> int:
    conn.execute(
        """
        INSERT INTO versiones_plan_cuentas
        (version, descripcion, estado, vigencia_desde)
        VALUES (?, ?, ?, date('now'))
        ON CONFLICT(version) DO UPDATE SET
            descripcion = excluded.descripcion,
            actualizado_en = CURRENT_TIMESTAMP
        """,
        (version, descripcion, estado),
    )
    fila = conn.execute(
        """
        SELECT id
        FROM versiones_plan_cuentas
        WHERE version = ?
        LIMIT 1
        """,
        (version,),
    ).fetchone()
    return int(fila["id"] if isinstance(fila, sqlite3.Row) else fila[0])


def _registrar_auditoria_seed(
    conn: sqlite3.Connection,
    *,
    cuenta_maestro_id: int | None,
    evento: str,
    valor_anterior: Any = None,
    valor_nuevo: Any = None,
    motivo: str = "",
    usuario: str | None = None,
) -> None:
    if not _tabla_existe(conn, "auditoria_plan_cuentas"):
        return
    conn.execute(
        """
        INSERT INTO auditoria_plan_cuentas
        (empresa_id, cuenta_empresa_id, cuenta_maestro_id, evento,
         valor_anterior, valor_nuevo, motivo, usuario)
        VALUES (NULL, NULL, ?, ?, ?, ?, ?, ?)
        """,
        (
            cuenta_maestro_id,
            evento,
            "" if valor_anterior is None else _json(valor_anterior),
            "" if valor_nuevo is None else _json(valor_nuevo),
            motivo,
            usuario,
        ),
    )


def _asegurar_usos_operativos_seed(conn: sqlite3.Connection) -> None:
    if not _tabla_existe(conn, "usos_operativos_contables"):
        return

    for uso in USOS_OPERATIVOS_SEED_COMPLEMENTARIOS:
        conn.execute(
            """
            INSERT INTO usos_operativos_contables
            (codigo, nombre, descripcion, tipo_uso, modulo_sugerido,
             requiere_cuenta_imputable, permite_multiples_cuentas_por_empresa,
             visible_en_ui, activo)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(codigo) DO UPDATE SET
                nombre = excluded.nombre,
                descripcion = excluded.descripcion,
                tipo_uso = excluded.tipo_uso,
                modulo_sugerido = excluded.modulo_sugerido,
                requiere_cuenta_imputable = excluded.requiere_cuenta_imputable,
                permite_multiples_cuentas_por_empresa = excluded.permite_multiples_cuentas_por_empresa,
                visible_en_ui = excluded.visible_en_ui,
                activo = 1,
                actualizado_en = CURRENT_TIMESTAMP
            """,
            (
                uso["codigo"],
                uso["nombre"],
                uso["descripcion"],
                uso["tipo_uso"],
                uso["modulo_sugerido"],
                int(uso["requiere_cuenta_imputable"]),
                int(uso["permite_multiples_cuentas_por_empresa"]),
                int(uso["visible_en_ui"]),
            ),
        )


def aplicar_seed_plan_maestro(
    *,
    ruta_csv: str | Path = CSV_DEFAULT,
    version: str = VERSION_PLAN_DEFAULT,
    descripcion: str = "Plan Maestro FF definitivo basado en PDF estructural y compatibilidad operativa del sistema.",
    usuario: str | None = None,
    actualizar_existentes: bool = True,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """
    Carga el Plan de Cuentas Maestro FF desde CSV.

    Características:
    - idempotente por version_plan_id + codigo;
    - no borra cuentas;
    - no toca módulos operativos;
    - no usa comportamiento_contable;
    - deja auditoría en auditoria_plan_cuentas;
    - permite completar campos técnicos cuando el CSV los deja vacíos.
    """
    validacion = validar_csv_plan_maestro(ruta_csv)
    if not validacion.ok:
        return {
            "ok": False,
            "error": "El CSV del Plan Maestro FF tiene errores.",
            "errores": validacion.errores,
            "advertencias": validacion.advertencias,
        }

    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)

    try:
        asegurar_estructura_maestro(conn)
        _asegurar_usos_operativos_seed(conn)

        version_plan_id = _obtener_o_crear_version_plan(
            conn,
            version=version,
            descripcion=descripcion,
            estado="BORRADOR",
        )

        filas_originales = _leer_csv(ruta_csv)
        codigos_con_hijos = {
            _limpiar(fila.get("codigo_madre"))
            for fila in filas_originales
            if _limpiar(fila.get("codigo_madre"))
        }

        insertadas = 0
        actualizadas = 0
        omitidas = 0
        errores: list[str] = []

        for fila_original in filas_originales:
            fila = _normalizar_fila(fila_original, codigos_con_hijos)
            fila["version_plan_id"] = version_plan_id

            existente = conn.execute(
                """
                SELECT *
                FROM plan_cuentas_maestro
                WHERE version_plan_id = ?
                  AND codigo = ?
                LIMIT 1
                """,
                (version_plan_id, fila["codigo"]),
            ).fetchone()

            if existente and not actualizar_existentes:
                omitidas += 1
                continue

            columnas = [c for c in COLUMNAS_PLAN_MAESTRO if c in fila or c == "version_plan_id"]
            valores = []
            for columna in columnas:
                valor = fila.get(columna)
                if columna in CAMPOS_ENTEROS:
                    valor = _to_int(valor, 0)
                elif valor == "":
                    valor = None
                valores.append(valor)

            placeholders = ", ".join(["?"] * len(columnas))
            columnas_sql = ", ".join(columnas)
            update_sql = ",\n                    ".join(
                f"{columna} = excluded.{columna}"
                for columna in columnas
                if columna not in {"version_plan_id", "codigo"}
            )

            conn.execute(
                f"""
                INSERT INTO plan_cuentas_maestro
                ({columnas_sql})
                VALUES ({placeholders})
                ON CONFLICT(version_plan_id, codigo) DO UPDATE SET
                    {update_sql},
                    actualizado_en = CURRENT_TIMESTAMP
                """,
                tuple(valores),
            )

            cuenta_id_row = conn.execute(
                """
                SELECT id
                FROM plan_cuentas_maestro
                WHERE version_plan_id = ?
                  AND codigo = ?
                LIMIT 1
                """,
                (version_plan_id, fila["codigo"]),
            ).fetchone()
            cuenta_maestro_id = int(cuenta_id_row["id"])

            if existente:
                actualizadas += 1
                evento = "PLAN_MAESTRO_SEED_ACTUALIZADO"
                valor_anterior = dict(existente) if isinstance(existente, sqlite3.Row) else None
            else:
                insertadas += 1
                evento = "PLAN_MAESTRO_SEED_INSERTADO"
                valor_anterior = None

            _registrar_auditoria_seed(
                conn,
                cuenta_maestro_id=cuenta_maestro_id,
                evento=evento,
                valor_anterior=valor_anterior,
                valor_nuevo={"codigo": fila["codigo"], "nombre": fila["nombre"], "version": version},
                motivo="Carga seed Plan Maestro FF desde PDF y compatibilidad operativa.",
                usuario=usuario,
            )

        if propia:
            conn.commit()

        return {
            "ok": True,
            "version": version,
            "version_plan_id": version_plan_id,
            "filas_csv": len(filas_originales),
            "insertadas": insertadas,
            "actualizadas": actualizadas,
            "omitidas": omitidas,
            "errores": errores,
            "advertencias": validacion.advertencias,
        }
    except Exception as exc:
        if propia:
            conn.rollback()
        return {"ok": False, "error": str(exc)}
    finally:
        if propia:
            conn.close()


def listar_plan_maestro_seed(
    *,
    version: str = VERSION_PLAN_DEFAULT,
    solo_activas: bool = True,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)

    try:
        asegurar_estructura_maestro(conn)
        where_estado = "AND p.estado = 'ACTIVA'" if solo_activas else ""
        return _fetch_dicts(
            conn,
            f"""
            SELECT
                p.id,
                v.version,
                p.codigo,
                p.nombre,
                p.elemento,
                p.clasificacion_corriente_no_corriente,
                p.rubro,
                p.cuenta,
                p.subcuenta,
                p.codigo_madre,
                p.nivel,
                p.orden,
                p.imputable,
                p.es_regularizadora,
                p.cuenta_regularizada_codigo,
                p.tipo_regularizadora,
                p.saldo_normal,
                p.significado_saldo_normal,
                p.permite_saldo_deudor,
                p.permite_saldo_acreedor,
                p.alertar_saldo_invertido,
                p.tratamiento_saldo_invertido,
                p.requiere_reclasificacion_saldo_invertido,
                p.monetaria_no_monetaria,
                p.criterio_medicion,
                p.ajustable,
                p.participa_recpam,
                p.admite_moneda_extranjera,
                p.requiere_tipo_cambio,
                p.genera_diferencia_cambio,
                p.es_cuenta_modelo,
                p.permite_copiar_modelo,
                p.uso_operativo_sistema,
                p.estado
            FROM plan_cuentas_maestro p
            JOIN versiones_plan_cuentas v ON v.id = p.version_plan_id
            WHERE v.version = ?
            {where_estado}
            ORDER BY p.orden, p.codigo
            """,
            (version,),
        )
    finally:
        if propia:
            conn.close()


def diagnosticar_plan_maestro_seed(
    *,
    version: str = VERSION_PLAN_DEFAULT,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)

    try:
        asegurar_estructura_maestro(conn)
        version_row = conn.execute(
            "SELECT id FROM versiones_plan_cuentas WHERE version = ? LIMIT 1",
            (version,),
        ).fetchone()
        if not version_row:
            return {"ok": False, "error": f"No existe la versión {version}."}
        version_id = int(version_row["id"])

        totales_elemento = _fetch_dicts(
            conn,
            """
            SELECT elemento, COUNT(*) AS cantidad
            FROM plan_cuentas_maestro
            WHERE version_plan_id = ?
            GROUP BY elemento
            ORDER BY elemento
            """,
            (version_id,),
        )
        sin_madre = _fetch_dicts(
            conn,
            """
            SELECT codigo, nombre, codigo_madre
            FROM plan_cuentas_maestro
            WHERE version_plan_id = ?
              AND COALESCE(codigo_madre, '') <> ''
              AND codigo_madre NOT IN (
                  SELECT codigo
                  FROM plan_cuentas_maestro
                  WHERE version_plan_id = ?
              )
            ORDER BY codigo
            """,
            (version_id, version_id),
        )
        imputables_con_hijos = _fetch_dicts(
            conn,
            """
            SELECT p.codigo, p.nombre
            FROM plan_cuentas_maestro p
            WHERE p.version_plan_id = ?
              AND p.imputable = 1
              AND EXISTS (
                  SELECT 1
                  FROM plan_cuentas_maestro h
                  WHERE h.version_plan_id = p.version_plan_id
                    AND h.codigo_madre = p.codigo
              )
            ORDER BY p.codigo
            """,
            (version_id,),
        )
        regularizadoras_sin_vinculo = _fetch_dicts(
            conn,
            """
            SELECT codigo, nombre
            FROM plan_cuentas_maestro
            WHERE version_plan_id = ?
              AND es_regularizadora = 1
              AND COALESCE(cuenta_regularizada_codigo, '') = ''
            ORDER BY codigo
            """,
            (version_id,),
        )
        modelos = _fetch_dicts(
            conn,
            """
            SELECT codigo, nombre, uso_operativo_sistema
            FROM plan_cuentas_maestro
            WHERE version_plan_id = ?
              AND es_cuenta_modelo = 1
            ORDER BY codigo
            """,
            (version_id,),
        )

        return {
            "ok": not sin_madre and not imputables_con_hijos,
            "version": version,
            "totales_elemento": totales_elemento,
            "cuentas_sin_madre_existente": sin_madre,
            "cuentas_imputables_con_hijos": imputables_con_hijos,
            "regularizadoras_sin_cuenta_regularizada": regularizadoras_sin_vinculo,
            "cuentas_modelo": modelos,
        }
    finally:
        if propia:
            conn.close()


def vincular_plan_empresa_con_maestro(
    *,
    empresa_id: int = 1,
    version: str = VERSION_PLAN_DEFAULT,
    usuario: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """
    Vincula cuentas ya existentes de plan_cuentas_empresa con el Plan Maestro.

    No crea, no borra y no renombra cuentas empresa.
    Solo completa cuenta_maestro_id cuando encuentra el mismo código en el maestro.
    """
    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)

    try:
        asegurar_estructura_maestro(conn)
        version_row = conn.execute(
            "SELECT id FROM versiones_plan_cuentas WHERE version = ? LIMIT 1",
            (version,),
        ).fetchone()
        if not version_row:
            return {"ok": False, "error": f"No existe la versión {version}. Primero cargá el seed."}

        version_id = int(version_row["id"])
        vinculables = _fetch_dicts(
            conn,
            """
            SELECT e.id AS cuenta_empresa_id, e.codigo, e.nombre, m.id AS cuenta_maestro_id
            FROM plan_cuentas_empresa e
            JOIN plan_cuentas_maestro m
              ON m.codigo = e.codigo
             AND m.version_plan_id = ?
            WHERE e.empresa_id = ?
              AND (e.cuenta_maestro_id IS NULL OR e.cuenta_maestro_id <> m.id)
            ORDER BY e.codigo
            """,
            (version_id, empresa_id),
        )

        for item in vinculables:
            conn.execute(
                """
                UPDATE plan_cuentas_empresa
                   SET cuenta_maestro_id = ?,
                       usuario_ultima_modificacion = ?,
                       fecha_ultima_modificacion = CURRENT_TIMESTAMP,
                       actualizado_en = CURRENT_TIMESTAMP
                 WHERE id = ?
                """,
                (int(item["cuenta_maestro_id"]), usuario, int(item["cuenta_empresa_id"])),
            )
            _registrar_auditoria_seed(
                conn,
                cuenta_maestro_id=int(item["cuenta_maestro_id"]),
                evento="CUENTA_EMPRESA_VINCULADA_A_PLAN_MAESTRO",
                valor_nuevo={
                    "empresa_id": empresa_id,
                    "cuenta_empresa_id": int(item["cuenta_empresa_id"]),
                    "codigo": item["codigo"],
                    "version": version,
                },
                motivo="Vinculación idempotente de cuenta empresa existente con Plan Maestro FF.",
                usuario=usuario,
            )

        if propia:
            conn.commit()

        return {
            "ok": True,
            "empresa_id": empresa_id,
            "version": version,
            "cuentas_vinculadas": len(vinculables),
        }
    except Exception as exc:
        if propia:
            conn.rollback()
        return {"ok": False, "error": str(exc)}
    finally:
        if propia:
            conn.close()