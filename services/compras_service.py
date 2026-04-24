import json
import unicodedata
from datetime import datetime

import pandas as pd

from database import (
    ejecutar_query,
    ejecutar_transaccion,
    proximo_asiento,
    archivo_ya_cargado,
    comprobante_ya_procesado,
    tipo_comprobante_existe,
    obtener_tipo_comprobante_config
)

from core.numeros import limpiar_numero
from core.textos import limpiar_texto
from core.fechas import formatear_fecha, obtener_anio_mes
from core.comprobantes import tipo_desde_descripcion


# ======================================================
# NORMALIZACIÓN
# ======================================================

def quitar_acentos(texto):
    texto = str(texto)
    texto = unicodedata.normalize("NFD", texto)
    texto = texto.encode("ascii", "ignore").decode("utf-8")
    return texto


def normalizar_nombre_columna(nombre):
    nombre = quitar_acentos(nombre)
    nombre = nombre.lower().strip()
    nombre = nombre.replace(".", "")
    nombre = nombre.replace("-", "_")
    nombre = nombre.replace("/", "_")
    nombre = nombre.replace("%", "")
    nombre = nombre.replace(",", "")
    nombre = nombre.replace(" ", "_")

    while "__" in nombre:
        nombre = nombre.replace("__", "_")

    return nombre


def normalizar_df(df):
    df = df.copy()
    df.columns = [normalizar_nombre_columna(c) for c in df.columns]
    return df


def valor(fila, columna, default=""):
    try:
        if columna in fila.index:
            return fila[columna]
        return default
    except Exception:
        return default


def numero(fila, columna):
    return limpiar_numero(valor(fila, columna, 0))


# ======================================================
# ESTRUCTURA COMPRAS V2
# ======================================================

def asegurar_columnas_compras_v2():
    ejecutar_query("""
        CREATE TABLE IF NOT EXISTS compras_comprobantes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            anio INTEGER,
            mes INTEGER,
            codigo TEXT,
            tipo TEXT,
            punto_venta TEXT,
            numero TEXT,
            proveedor TEXT,
            cuit TEXT,
            neto REAL,
            iva REAL,
            total REAL,
            archivo TEXT,
            fecha_carga TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    columnas = {
        "categoria_compra": "TEXT",
        "cuenta_principal_codigo": "TEXT",
        "cuenta_principal_nombre": "TEXT",
        "cuenta_proveedor_codigo": "TEXT",
        "cuenta_proveedor_nombre": "TEXT",
        "importe_no_gravado": "REAL DEFAULT 0",
        "importe_exento": "REAL DEFAULT 0",
        "iva_total": "REAL DEFAULT 0",
        "credito_fiscal_computable": "REAL DEFAULT 0",
        "iva_no_computable": "REAL DEFAULT 0",
        "percepcion_iva": "REAL DEFAULT 0",
        "percepcion_iibb": "REAL DEFAULT 0",
        "percepcion_otros_imp_nac": "REAL DEFAULT 0",
        "impuestos_municipales": "REAL DEFAULT 0",
        "impuestos_internos": "REAL DEFAULT 0",
        "otros_tributos": "REAL DEFAULT 0",
        "moneda": "TEXT",
        "tipo_cambio": "REAL DEFAULT 1",
        "neto_iva_0": "REAL DEFAULT 0",
        "neto_iva_25": "REAL DEFAULT 0",
        "iva_25": "REAL DEFAULT 0",
        "neto_iva_5": "REAL DEFAULT 0",
        "iva_5": "REAL DEFAULT 0",
        "neto_iva_105": "REAL DEFAULT 0",
        "iva_105": "REAL DEFAULT 0",
        "neto_iva_21": "REAL DEFAULT 0",
        "iva_21": "REAL DEFAULT 0",
        "neto_iva_27": "REAL DEFAULT 0",
        "iva_27": "REAL DEFAULT 0",
        "origen_carga": "TEXT"
    }

    for columna, tipo in columnas.items():
        try:
            ejecutar_query(f"ALTER TABLE compras_comprobantes ADD COLUMN {columna} {tipo}")
        except Exception:
            pass


# ======================================================
# CONFIGURACIONES
# ======================================================

def obtener_categoria_compra(categoria):
    df = ejecutar_query("""
        SELECT 
            categoria,
            cuenta_codigo,
            cuenta_nombre,
            cuenta_proveedor_codigo,
            cuenta_proveedor_nombre,
            tipo_categoria
        FROM categorias_compra
        WHERE categoria = ?
          AND activo = 1
    """, (categoria,), fetch=True)

    if df.empty:
        return None

    fila = df.iloc[0]

    return {
        "categoria": str(fila["categoria"]),
        "cuenta_codigo": str(fila["cuenta_codigo"]),
        "cuenta_nombre": str(fila["cuenta_nombre"]),
        "cuenta_proveedor_codigo": str(fila["cuenta_proveedor_codigo"]),
        "cuenta_proveedor_nombre": str(fila["cuenta_proveedor_nombre"]),
        "tipo_categoria": str(fila["tipo_categoria"])
    }


def obtener_conceptos_fiscales():
    df = ejecutar_query("""
        SELECT concepto, cuenta_codigo, cuenta_nombre, tratamiento
        FROM conceptos_fiscales_compra
        WHERE activo = 1
    """, fetch=True)

    conceptos = {}

    for _, fila in df.iterrows():
        clave = str(fila["concepto"]).strip().upper()

        conceptos[clave] = {
            "concepto": clave,
            "cuenta_codigo": str(fila["cuenta_codigo"]).strip(),
            "cuenta_nombre": str(fila["cuenta_nombre"]).strip(),
            "tratamiento": str(fila["tratamiento"]).strip().upper()
        }

    return conceptos


def concepto_config(conceptos, clave):
    clave = str(clave).strip().upper()

    defaults = {
        "IVA_CREDITO_FISCAL": {
            "cuenta_codigo": "1122600000",
            "cuenta_nombre": "IVA CRÉDITO FISCAL",
            "tratamiento": "CREDITO_FISCAL"
        },
        "PERCEPCION_IVA": {
            "cuenta_codigo": "1122400000",
            "cuenta_nombre": "AFIP - RET. Y PER. IVA",
            "tratamiento": "PERCEPCION_COMPUTABLE"
        },
        "PERCEPCION_IIBB": {
            "cuenta_codigo": "1122300000",
            "cuenta_nombre": "DPR - RET. Y PER. IIBB",
            "tratamiento": "PERCEPCION_COMPUTABLE"
        },
        "PERCEPCION_GANANCIAS": {
            "cuenta_codigo": "1122500000",
            "cuenta_nombre": "AFIP - RET. GANANCIAS",
            "tratamiento": "PERCEPCION_COMPUTABLE"
        },
        "PERCEPCION_MUNICIPAL": {
            "cuenta_codigo": "1123200000",
            "cuenta_nombre": "PERCEPCIONES IMPUESTOS MUNICIPALES A COMPUTAR",
            "tratamiento": "PERCEPCION_COMPUTABLE"
        },
        "IMPUESTOS_INTERNOS_NO_RECUPERABLES": {
            "cuenta_codigo": "5122100000",
            "cuenta_nombre": "IMPUESTOS INTERNOS NO RECUPERABLES",
            "tratamiento": "MAYOR_COSTO_GASTO"
        },
        "OTROS_TRIBUTOS_NO_RECUPERABLES": {
            "cuenta_codigo": "5122200000",
            "cuenta_nombre": "OTROS TRIBUTOS NO RECUPERABLES",
            "tratamiento": "MAYOR_COSTO_GASTO"
        },
        "IVA_NO_COMPUTABLE": {
            "cuenta_codigo": "5122400000",
            "cuenta_nombre": "IVA NO COMPUTABLE / MAYOR COSTO",
            "tratamiento": "MAYOR_COSTO_GASTO"
        },
        "NO_GRAVADO": {
            "cuenta_codigo": "CUENTA_PRINCIPAL",
            "cuenta_nombre": "CUENTA_PRINCIPAL",
            "tratamiento": "MAYOR_COSTO"
        },
        "EXENTO": {
            "cuenta_codigo": "CUENTA_PRINCIPAL",
            "cuenta_nombre": "CUENTA_PRINCIPAL",
            "tratamiento": "MAYOR_COSTO"
        }
    }

    return conceptos.get(clave, defaults.get(clave))


def usa_cuenta_separada(config):
    if config is None:
        return False

    cuenta = str(config.get("cuenta_codigo", "")).strip().upper()

    if cuenta == "" or cuenta == "CUENTA_PRINCIPAL":
        return False

    return True


# ======================================================
# OPERACIONES SQL
# ======================================================

def op_insert_libro_diario(asiento, fecha, cuenta, debe, haber, glosa, origen, archivo):
    return (
        """
        INSERT INTO libro_diario
        (id_asiento, fecha, cuenta, debe, haber, glosa, origen, archivo)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            asiento,
            fecha,
            cuenta,
            round(float(debe), 2),
            round(float(haber), 2),
            glosa,
            origen,
            archivo
        )
    )


def op_insert_comprobante_procesado(modulo, fecha, codigo, numero, proveedor_clave, total, archivo):
    return (
        """
        INSERT INTO comprobantes_procesados
        (modulo, fecha, codigo, numero, cliente_proveedor, total, archivo)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            modulo,
            fecha,
            codigo,
            numero,
            proveedor_clave,
            total,
            archivo
        )
    )


def op_insert_historial(modulo, archivo, registros):
    return (
        """
        INSERT INTO historial_cargas
        (modulo, nombre_archivo, registros)
        VALUES (?, ?, ?)
        """,
        (
            modulo,
            archivo,
            registros
        )
    )


def op_insert_error(modulo, archivo, fila, motivo, contenido):
    try:
        contenido_json = json.dumps(contenido, ensure_ascii=False, default=str)
    except Exception:
        contenido_json = str(contenido)

    return (
        """
        INSERT INTO errores_carga
        (modulo, archivo, fila, motivo, contenido)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            modulo,
            archivo,
            fila,
            motivo,
            contenido_json
        )
    )


def op_insert_cta_cte_proveedor(fecha, proveedor, cuit, tipo, numero, debe, haber, saldo, origen, archivo):
    return (
        """
        INSERT INTO cuenta_corriente_proveedores
        (fecha, proveedor, cuit, tipo, numero, debe, haber, saldo, origen, archivo)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            fecha,
            proveedor,
            cuit,
            tipo,
            numero,
            debe,
            haber,
            saldo,
            origen,
            archivo
        )
    )


def op_insert_compra(datos):
    return (
        """
        INSERT INTO compras_comprobantes
        (
            fecha, anio, mes, codigo, tipo, punto_venta, numero,
            proveedor, cuit, neto, iva, total, archivo,
            categoria_compra, cuenta_principal_codigo, cuenta_principal_nombre,
            cuenta_proveedor_codigo, cuenta_proveedor_nombre,
            importe_no_gravado, importe_exento, iva_total,
            credito_fiscal_computable, iva_no_computable,
            percepcion_iva, percepcion_iibb, percepcion_otros_imp_nac,
            impuestos_municipales, impuestos_internos, otros_tributos,
            moneda, tipo_cambio,
            neto_iva_0, neto_iva_25, iva_25,
            neto_iva_5, iva_5,
            neto_iva_105, iva_105,
            neto_iva_21, iva_21,
            neto_iva_27, iva_27,
            origen_carga
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datos["fecha"],
            datos["anio"],
            datos["mes"],
            datos["codigo"],
            datos["tipo"],
            datos["punto_venta"],
            datos["numero"],
            datos["proveedor"],
            datos["cuit"],
            datos["neto"],
            datos["iva"],
            datos["total"],
            datos["archivo"],
            datos["categoria_compra"],
            datos["cuenta_principal_codigo"],
            datos["cuenta_principal_nombre"],
            datos["cuenta_proveedor_codigo"],
            datos["cuenta_proveedor_nombre"],
            datos["importe_no_gravado"],
            datos["importe_exento"],
            datos["iva_total"],
            datos["credito_fiscal_computable"],
            datos["iva_no_computable"],
            datos["percepcion_iva"],
            datos["percepcion_iibb"],
            datos["percepcion_otros_imp_nac"],
            datos["impuestos_municipales"],
            datos["impuestos_internos"],
            datos["otros_tributos"],
            datos["moneda"],
            datos["tipo_cambio"],
            datos["neto_iva_0"],
            datos["neto_iva_25"],
            datos["iva_25"],
            datos["neto_iva_5"],
            datos["iva_5"],
            datos["neto_iva_105"],
            datos["iva_105"],
            datos["neto_iva_21"],
            datos["iva_21"],
            datos["neto_iva_27"],
            datos["iva_27"],
            datos["origen_carga"]
        )
    )


# ======================================================
# ASIENTOS
# ======================================================

def agregar_movimiento(operaciones, asiento, fecha, cuenta, importe_signed, glosa, archivo):
    importe_signed = round(float(importe_signed), 2)

    if abs(importe_signed) < 0.005:
        return

    debe = importe_signed if importe_signed > 0 else 0
    haber = abs(importe_signed) if importe_signed < 0 else 0

    operaciones.append(
        op_insert_libro_diario(
            asiento,
            fecha,
            cuenta,
            debe,
            haber,
            glosa,
            "COMPRAS",
            archivo
        )
    )


def agregar_concepto_fiscal(lista_componentes, conceptos, clave, importe):
    importe = round(float(importe), 2)

    if importe <= 0:
        return 0

    config = concepto_config(conceptos, clave)

    if usa_cuenta_separada(config):
        lista_componentes.append({
            "clave": clave,
            "cuenta": config["cuenta_nombre"],
            "importe": importe
        })
        return importe

    return 0


# ======================================================
# DETECCIÓN CSV ARCA
# ======================================================

def es_csv_arca_compras(df):
    columnas = set(normalizar_df(df).columns)

    requeridas = {
        "fecha_de_emision",
        "tipo_de_comprobante",
        "punto_de_venta",
        "numero_de_comprobante",
        "nro_doc_vendedor",
        "denominacion_vendedor",
        "importe_total"
    }

    return requeridas.issubset(columnas)


# ======================================================
# PROCESAMIENTO PRINCIPAL
# ======================================================

def procesar_csv_compras_arca(nombre_archivo, df_original, categoria_compra):
    asegurar_columnas_compras_v2()

    resultado = {
        "procesados": 0,
        "errores": 0,
        "facturas": 0,
        "notas_credito": 0,
        "notas_debito": 0,
        "duplicados": 0,
        "errores_matematicos": 0,
        "errores_codigo": 0,
        "ajustes_centavos": 0
    }

    operaciones = []
    claves_archivo = set()

    if archivo_ya_cargado(nombre_archivo):
        resultado["errores"] += 1
        operaciones.append(
            op_insert_error(
                "COMPRAS",
                nombre_archivo,
                0,
                "El archivo ya fue cargado anteriormente.",
                {}
            )
        )
        ejecutar_transaccion(operaciones)
        return resultado

    categoria = obtener_categoria_compra(categoria_compra)

    if categoria is None:
        resultado["errores"] += 1
        operaciones.append(
            op_insert_error(
                "COMPRAS",
                nombre_archivo,
                0,
                f"No existe la categoría de compra seleccionada: {categoria_compra}",
                {}
            )
        )
        ejecutar_transaccion(operaciones)
        return resultado

    conceptos = obtener_conceptos_fiscales()

    df = normalizar_df(df_original)

    if not es_csv_arca_compras(df_original):
        resultado["errores"] += 1
        operaciones.append(
            op_insert_error(
                "COMPRAS",
                nombre_archivo,
                0,
                "El archivo no parece ser un CSV ARCA/AFIP Compras.",
                {"columnas": list(df_original.columns)}
            )
        )
        ejecutar_transaccion(operaciones)
        return resultado

    asiento = proximo_asiento()

    for numero_fila, (_, fila) in enumerate(df.iterrows(), start=2):

        try:
            fecha_original = valor(fila, "fecha_de_emision")
            fecha = formatear_fecha(fecha_original)
            anio, mes = obtener_anio_mes(fecha_original)

            codigo = limpiar_texto(valor(fila, "tipo_de_comprobante"))
            punto_venta = limpiar_texto(valor(fila, "punto_de_venta"))
            numero_comp = limpiar_texto(valor(fila, "numero_de_comprobante"))
            numero_full = f"{punto_venta}-{numero_comp}"

            cuit = limpiar_texto(valor(fila, "nro_doc_vendedor"))
            proveedor = limpiar_texto(valor(fila, "denominacion_vendedor"))

            if proveedor == "":
                proveedor = "PROVEEDOR SIN NOMBRE"

            proveedor_clave = cuit if cuit else proveedor

            total = numero(fila, "importe_total")
            moneda = limpiar_texto(valor(fila, "moneda_original"))
            tipo_cambio = numero(fila, "tipo_de_cambio") or 1

            importe_no_gravado = numero(fila, "importe_no_gravado")
            importe_exento = numero(fila, "importe_exento")

            credito_fiscal = numero(fila, "credito_fiscal_computable")
            iva_total = numero(fila, "total_iva")
            iva_no_computable = max(round(iva_total - credito_fiscal, 2), 0)

            percepcion_otros_imp_nac = numero(fila, "importe_de_per_o_pagos_a_cta_de_otros_imp_nac")
            percepcion_iibb = numero(fila, "importe_de_percepciones_de_ingresos_brutos")
            impuestos_municipales = numero(fila, "importe_de_impuestos_municipales")
            percepcion_iva = numero(fila, "importe_de_percepciones_o_pagos_a_cuenta_de_iva")
            impuestos_internos = numero(fila, "importe_de_impuestos_internos")
            otros_tributos = numero(fila, "importe_otros_tributos")

            neto_iva_0 = numero(fila, "neto_gravado_iva_0")
            neto_iva_25 = numero(fila, "neto_gravado_iva_25")
            iva_25 = numero(fila, "importe_iva_25")
            neto_iva_5 = numero(fila, "neto_gravado_iva_5")
            iva_5 = numero(fila, "importe_iva_5")
            neto_iva_105 = numero(fila, "neto_gravado_iva_105")
            iva_105 = numero(fila, "importe_iva_105")
            neto_iva_21 = numero(fila, "neto_gravado_iva_21")
            iva_21 = numero(fila, "importe_iva_21")
            neto_iva_27 = numero(fila, "neto_gravado_iva_27")
            iva_27 = numero(fila, "importe_iva_27")

            total_neto_gravado = numero(fila, "total_neto_gravado")

            contenido_fila = fila.to_dict()

            if not tipo_comprobante_existe(codigo):
                resultado["errores"] += 1
                resultado["errores_codigo"] += 1

                operaciones.append(
                    op_insert_error(
                        "COMPRAS",
                        nombre_archivo,
                        numero_fila,
                        f"Código de comprobante inexistente: {codigo}",
                        contenido_fila
                    )
                )
                continue

            config = obtener_tipo_comprobante_config(codigo)

            if config is None:
                resultado["errores"] += 1
                resultado["errores_codigo"] += 1

                operaciones.append(
                    op_insert_error(
                        "COMPRAS",
                        nombre_archivo,
                        numero_fila,
                        f"No se pudo interpretar el comprobante: {codigo}",
                        contenido_fila
                    )
                )
                continue

            tipo = tipo_desde_descripcion(config["descripcion"])
            signo = int(config["signo"])

            clave = ("COMPRAS", codigo, numero_full, proveedor_clave)

            if clave in claves_archivo or comprobante_ya_procesado("COMPRAS", codigo, numero_full, proveedor_clave):
                resultado["errores"] += 1
                resultado["duplicados"] += 1

                operaciones.append(
                    op_insert_error(
                        "COMPRAS",
                        nombre_archivo,
                        numero_fila,
                        f"Comprobante duplicado: código {codigo}, número {numero_full}, proveedor/CUIT {proveedor_clave}",
                        contenido_fila
                    )
                )
                continue

            claves_archivo.add(clave)

            componentes_separados = []

            agregar_concepto_fiscal(componentes_separados, conceptos, "IVA_CREDITO_FISCAL", credito_fiscal)
            agregar_concepto_fiscal(componentes_separados, conceptos, "IVA_NO_COMPUTABLE", iva_no_computable)
            agregar_concepto_fiscal(componentes_separados, conceptos, "PERCEPCION_IVA", percepcion_iva)
            agregar_concepto_fiscal(componentes_separados, conceptos, "PERCEPCION_IIBB", percepcion_iibb)
            agregar_concepto_fiscal(componentes_separados, conceptos, "PERCEPCION_GANANCIAS", percepcion_otros_imp_nac)
            agregar_concepto_fiscal(componentes_separados, conceptos, "PERCEPCION_MUNICIPAL", impuestos_municipales)
            agregar_concepto_fiscal(componentes_separados, conceptos, "IMPUESTOS_INTERNOS_NO_RECUPERABLES", impuestos_internos)
            agregar_concepto_fiscal(componentes_separados, conceptos, "OTROS_TRIBUTOS_NO_RECUPERABLES", otros_tributos)

            suma_componentes_separados = round(sum(c["importe"] for c in componentes_separados), 2)

            cuenta_principal_importe = round(total - suma_componentes_separados, 2)

            if cuenta_principal_importe < -0.01:
                resultado["errores"] += 1
                resultado["errores_matematicos"] += 1

                operaciones.append(
                    op_insert_error(
                        "COMPRAS",
                        nombre_archivo,
                        numero_fila,
                        (
                            "La suma de componentes fiscales supera el total del comprobante. "
                            f"Total: {total}, componentes separados: {suma_componentes_separados}"
                        ),
                        contenido_fila
                    )
                )
                continue

            total_s = round(total * signo, 2)
            cuenta_principal_s = round(cuenta_principal_importe * signo, 2)

            glosa = f"{tipo} {numero_full} - {proveedor}"

            agregar_movimiento(
                operaciones,
                asiento,
                fecha,
                categoria["cuenta_nombre"],
                cuenta_principal_s,
                glosa,
                nombre_archivo
            )

            for comp in componentes_separados:
                agregar_movimiento(
                    operaciones,
                    asiento,
                    fecha,
                    comp["cuenta"],
                    round(comp["importe"] * signo, 2),
                    glosa,
                    nombre_archivo
                )

            agregar_movimiento(
                operaciones,
                asiento,
                fecha,
                categoria["cuenta_proveedor_nombre"],
                -total_s,
                glosa,
                nombre_archivo
            )

            operaciones.append(
                op_insert_comprobante_procesado(
                    "COMPRAS",
                    fecha,
                    codigo,
                    numero_full,
                    proveedor_clave,
                    total_s,
                    nombre_archivo
                )
            )

            datos_compra = {
                "fecha": fecha,
                "anio": anio,
                "mes": mes,
                "codigo": codigo,
                "tipo": tipo,
                "punto_venta": punto_venta,
                "numero": numero_full,
                "proveedor": proveedor,
                "cuit": cuit,
                "neto": round(total_neto_gravado * signo, 2),
                "iva": round(credito_fiscal * signo, 2),
                "total": total_s,
                "archivo": nombre_archivo,
                "categoria_compra": categoria["categoria"],
                "cuenta_principal_codigo": categoria["cuenta_codigo"],
                "cuenta_principal_nombre": categoria["cuenta_nombre"],
                "cuenta_proveedor_codigo": categoria["cuenta_proveedor_codigo"],
                "cuenta_proveedor_nombre": categoria["cuenta_proveedor_nombre"],
                "importe_no_gravado": round(importe_no_gravado * signo, 2),
                "importe_exento": round(importe_exento * signo, 2),
                "iva_total": round(iva_total * signo, 2),
                "credito_fiscal_computable": round(credito_fiscal * signo, 2),
                "iva_no_computable": round(iva_no_computable * signo, 2),
                "percepcion_iva": round(percepcion_iva * signo, 2),
                "percepcion_iibb": round(percepcion_iibb * signo, 2),
                "percepcion_otros_imp_nac": round(percepcion_otros_imp_nac * signo, 2),
                "impuestos_municipales": round(impuestos_municipales * signo, 2),
                "impuestos_internos": round(impuestos_internos * signo, 2),
                "otros_tributos": round(otros_tributos * signo, 2),
                "moneda": moneda,
                "tipo_cambio": tipo_cambio,
                "neto_iva_0": round(neto_iva_0 * signo, 2),
                "neto_iva_25": round(neto_iva_25 * signo, 2),
                "iva_25": round(iva_25 * signo, 2),
                "neto_iva_5": round(neto_iva_5 * signo, 2),
                "iva_5": round(iva_5 * signo, 2),
                "neto_iva_105": round(neto_iva_105 * signo, 2),
                "iva_105": round(iva_105 * signo, 2),
                "neto_iva_21": round(neto_iva_21 * signo, 2),
                "iva_21": round(iva_21 * signo, 2),
                "neto_iva_27": round(neto_iva_27 * signo, 2),
                "iva_27": round(iva_27 * signo, 2),
                "origen_carga": "CSV_ARCA"
            }

            operaciones.append(op_insert_compra(datos_compra))

            operaciones.append(
                op_insert_cta_cte_proveedor(
                    fecha,
                    proveedor,
                    cuit,
                    tipo,
                    numero_full,
                    abs(total_s) if total_s < 0 else 0,
                    total_s if total_s > 0 else 0,
                    0,
                    "COMPRAS",
                    nombre_archivo
                )
            )

            resultado["procesados"] += 1

            if tipo == "FACTURA":
                resultado["facturas"] += 1
            elif tipo == "NC":
                resultado["notas_credito"] += 1
            elif tipo == "ND":
                resultado["notas_debito"] += 1

            asiento += 1

        except Exception as e:
            resultado["errores"] += 1

            operaciones.append(
                op_insert_error(
                    "COMPRAS",
                    nombre_archivo,
                    numero_fila,
                    f"Error inesperado: {str(e)}",
                    fila.to_dict()
                )
            )

    if resultado["procesados"] > 0:
        operaciones.append(
            op_insert_historial(
                "COMPRAS",
                nombre_archivo,
                resultado["procesados"]
            )
        )

    if operaciones:
        ejecutar_transaccion(operaciones)

    return resultado


# ======================================================
# CARGA MANUAL
# ======================================================

def procesar_compra_manual(datos):
    nombre_archivo = (
        f"COMPRA_MANUAL_"
        f"{datos['codigo']}_{datos['punto_venta']}_{datos['numero_comprobante']}_"
        f"{datetime.now().strftime('%Y%m%d%H%M%S')}"
    )

    fila = {
        "Fecha de Emisión": datos["fecha"],
        "Tipo de Comprobante": datos["codigo"],
        "Punto de Venta": datos["punto_venta"],
        "Número de Comprobante": datos["numero_comprobante"],
        "Tipo Doc. Vendedor": "80",
        "Nro. Doc. Vendedor": datos["cuit"],
        "Denominación Vendedor": datos["proveedor"],
        "Importe Total": datos["total"],
        "Moneda Original": datos.get("moneda", "PES"),
        "Tipo de Cambio": datos.get("tipo_cambio", 1),
        "Importe No Gravado": datos.get("importe_no_gravado", 0),
        "Importe Exento": datos.get("importe_exento", 0),
        "Crédito Fiscal Computable": datos.get("credito_fiscal_computable", 0),
        "Importe de Per. o Pagos a Cta. de Otros Imp. Nac.": datos.get("percepcion_otros_imp_nac", 0),
        "Importe de Percepciones de Ingresos Brutos": datos.get("percepcion_iibb", 0),
        "Importe de Impuestos Municipales": datos.get("impuestos_municipales", 0),
        "Importe de Percepciones o Pagos a Cuenta de IVA": datos.get("percepcion_iva", 0),
        "Importe de Impuestos Internos": datos.get("impuestos_internos", 0),
        "Importe Otros Tributos": datos.get("otros_tributos", 0),
        "Neto Gravado IVA 0%": 0,
        "Neto Gravado IVA 2,5%": 0,
        "Importe IVA 2,5%": 0,
        "Neto Gravado IVA 5%": 0,
        "Importe IVA 5%": 0,
        "Neto Gravado IVA 10,5%": 0,
        "Importe IVA 10,5%": 0,
        "Neto Gravado IVA 21%": datos.get("total_neto_gravado", 0),
        "Importe IVA 21%": datos.get("iva_total", 0),
        "Neto Gravado IVA 27%": 0,
        "Importe IVA 27%": 0,
        "Total Neto Gravado": datos.get("total_neto_gravado", 0),
        "Total IVA": datos.get("iva_total", 0)
    }

    df = pd.DataFrame([fila])

    return procesar_csv_compras_arca(
        nombre_archivo,
        df,
        datos["categoria_compra"]
    )