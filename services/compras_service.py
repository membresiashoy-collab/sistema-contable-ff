import json

from database import (
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
from core.comprobantes import tipo_desde_descripcion, aplicar_signo
from core.reglas_contables import interpretar_importes_compra


def valor_fila(fila, columna):
    if columna is None or columna == "No usar":
        return ""

    try:
        return fila[columna]
    except Exception:
        return ""


def construir_numero_comprobante_compra(fila, columnas):
    punto_venta = limpiar_texto(valor_fila(fila, columnas["punto_venta"]))
    numero_desde = limpiar_texto(valor_fila(fila, columnas["numero_desde"]))
    numero_hasta = limpiar_texto(valor_fila(fila, columnas.get("numero_hasta")))

    numero = f"{punto_venta}-{numero_desde}"

    if numero_hasta not in ["", "nan", "None"] and numero_hasta != numero_desde:
        numero = f"{punto_venta}-{numero_desde}/{numero_hasta}"

    return punto_venta, numero


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


def op_insert_comprobante_procesado(modulo, fecha, codigo, numero, cliente_proveedor, total, archivo):
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
            cliente_proveedor,
            total,
            archivo
        )
    )


def op_insert_compra(fecha, anio, mes, codigo, tipo, punto_venta, numero, proveedor, cuit, neto, iva, total, archivo):
    return (
        """
        INSERT INTO compras_comprobantes
        (fecha, anio, mes, codigo, tipo, punto_venta, numero, proveedor, cuit, neto, iva, total, archivo)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            fecha,
            anio,
            mes,
            codigo,
            tipo,
            punto_venta,
            numero,
            proveedor,
            cuit,
            neto,
            iva,
            total,
            archivo
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


def procesar_csv_compras(nombre_archivo, df, columnas):
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

    asiento = proximo_asiento()

    for numero_fila, (_, fila) in enumerate(df.iterrows(), start=2):

        try:
            fecha_original = valor_fila(fila, columnas["fecha"])
            fecha = formatear_fecha(fecha_original)
            anio, mes = obtener_anio_mes(fecha_original)

            codigo = limpiar_texto(valor_fila(fila, columnas["codigo"]))
            punto_venta, numero = construir_numero_comprobante_compra(fila, columnas)

            cuit = limpiar_texto(valor_fila(fila, columnas["cuit"]))
            proveedor = limpiar_texto(valor_fila(fila, columnas["proveedor"]))

            if proveedor == "":
                proveedor = "PROVEEDOR SIN NOMBRE"

            proveedor_clave = cuit if cuit != "" else proveedor

            neto = limpiar_numero(valor_fila(fila, columnas["neto"]))
            iva = limpiar_numero(valor_fila(fila, columnas["iva"]))
            total = limpiar_numero(valor_fila(fila, columnas["total"]))

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

            clave = ("COMPRAS", codigo, numero, proveedor_clave)

            if clave in claves_archivo or comprobante_ya_procesado("COMPRAS", codigo, numero, proveedor_clave):
                resultado["errores"] += 1
                resultado["duplicados"] += 1

                operaciones.append(
                    op_insert_error(
                        "COMPRAS",
                        nombre_archivo,
                        numero_fila,
                        f"Comprobante duplicado: código {codigo}, número {numero}, proveedor/CUIT {proveedor_clave}",
                        contenido_fila
                    )
                )
                continue

            claves_archivo.add(clave)

            importes = interpretar_importes_compra(neto, iva, total)

            if not importes["ok"]:
                resultado["errores"] += 1
                resultado["errores_matematicos"] += 1

                operaciones.append(
                    op_insert_error(
                        "COMPRAS",
                        nombre_archivo,
                        numero_fila,
                        (
                            f"{importes['motivo']}. "
                            f"Neto: {neto}, IVA: {iva}, Total: {total}, "
                            f"Diferencia: {importes['diferencia']}"
                        ),
                        contenido_fila
                    )
                )
                continue

            if importes["ajuste_centavos"]:
                resultado["ajustes_centavos"] += 1

            importes_con_signo = aplicar_signo(
                importes["neto"],
                importes["iva"],
                importes["total"],
                signo
            )

            neto_s = importes_con_signo["neto"]
            iva_s = importes_con_signo["iva"]
            total_s = importes_con_signo["total"]

            glosa = f"{tipo} {numero} - {proveedor}"

            # Factura / ND:
            #   Debe: Compras
            #   Debe: IVA Crédito Fiscal
            #   Haber: Proveedores
            #
            # NC:
            #   Debe: Proveedores
            #   Haber: Compras
            #   Haber: IVA Crédito Fiscal

            debe_compra = neto_s if neto_s > 0 else 0
            haber_compra = abs(neto_s) if neto_s < 0 else 0

            debe_iva = iva_s if iva_s > 0 else 0
            haber_iva = abs(iva_s) if iva_s < 0 else 0

            debe_proveedor = abs(total_s) if total_s < 0 else 0
            haber_proveedor = total_s if total_s > 0 else 0

            operaciones.append(
                op_insert_libro_diario(
                    asiento,
                    fecha,
                    "COMPRAS",
                    debe_compra,
                    haber_compra,
                    glosa,
                    "COMPRAS",
                    nombre_archivo
                )
            )

            if iva_s != 0:
                operaciones.append(
                    op_insert_libro_diario(
                        asiento,
                        fecha,
                        "IVA CREDITO FISCAL",
                        debe_iva,
                        haber_iva,
                        glosa,
                        "COMPRAS",
                        nombre_archivo
                    )
                )

            operaciones.append(
                op_insert_libro_diario(
                    asiento,
                    fecha,
                    "PROVEEDORES",
                    debe_proveedor,
                    haber_proveedor,
                    glosa,
                    "COMPRAS",
                    nombre_archivo
                )
            )

            operaciones.append(
                op_insert_comprobante_procesado(
                    "COMPRAS",
                    fecha,
                    codigo,
                    numero,
                    proveedor_clave,
                    total_s,
                    nombre_archivo
                )
            )

            operaciones.append(
                op_insert_compra(
                    fecha,
                    anio,
                    mes,
                    codigo,
                    tipo,
                    punto_venta,
                    numero,
                    proveedor,
                    cuit,
                    neto_s,
                    iva_s,
                    total_s,
                    nombre_archivo
                )
            )

            operaciones.append(
                op_insert_cta_cte_proveedor(
                    fecha,
                    proveedor,
                    cuit,
                    tipo,
                    numero,
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