import json

from database import (
    ejecutar_transaccion,
    proximo_asiento,
    comprobante_ya_procesado,
    tipo_comprobante_existe,
    obtener_tipo_comprobante_config,
)

from core.numeros import limpiar_numero
from core.textos import limpiar_texto
from core.fechas import formatear_fecha, obtener_anio_mes
from core.comprobantes import (
    construir_numero_comprobante_desde_fila,
    tipo_desde_descripcion,
    aplicar_signo,
)
from core.reglas_contables import interpretar_importes_venta


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
            archivo,
        ),
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
            round(float(total), 2),
            archivo,
        ),
    )


def op_insert_venta(fecha, anio, mes, codigo, tipo, punto_venta, numero, cliente, cuit, neto, iva, total, archivo):
    return (
        """
        INSERT INTO ventas_comprobantes
        (fecha, anio, mes, codigo, tipo, punto_venta, numero, cliente, cuit, neto, iva, total, archivo)
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
            cliente,
            cuit,
            round(float(neto), 2),
            round(float(iva), 2),
            round(float(total), 2),
            archivo,
        ),
    )


def op_insert_cta_cte_cliente(fecha, cliente, cuit, tipo, numero, debe, haber, saldo, origen, archivo):
    return (
        """
        INSERT INTO cuenta_corriente_clientes
        (fecha, cliente, cuit, tipo, numero, debe, haber, saldo, origen, archivo)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            fecha,
            cliente,
            cuit,
            tipo,
            numero,
            round(float(debe), 2),
            round(float(haber), 2),
            round(float(saldo), 2),
            origen,
            archivo,
        ),
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
            int(registros),
        ),
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
            contenido_json,
        ),
    )


def construir_clave_comprobante(codigo, numero, cliente_clave):
    """
    Clave funcional usada para evitar duplicación contable.

    No se usa el nombre del archivo porque ARCA/AFIP puede descargar dos veces
    el mismo período con el mismo nombre o el usuario puede renombrar archivos.
    Lo relevante es no duplicar el comprobante ya procesado.
    """

    return (
        "VENTAS",
        limpiar_texto(codigo).upper(),
        limpiar_texto(numero).upper(),
        limpiar_texto(cliente_clave).upper(),
    )


def procesar_csv_ventas(nombre_archivo, df):
    """
    Procesa un DataFrame de ventas ARCA/AFIP.

    Genera:
    - Libro Diario
    - Libro IVA Ventas
    - Cuenta Corriente Clientes
    - Historial
    - Errores de auditoría

    Regla importante:
    - El nombre del archivo NO bloquea la carga.
    - Los comprobantes ya importados se omiten para evitar duplicar asientos,
      Libro IVA Ventas y cuenta corriente de clientes.
    - Los duplicados se informan como advertencia operativa, no como error real.
    """

    resultado = {
        "procesados": 0,
        "errores": 0,
        "facturas": 0,
        "notas_credito": 0,
        "notas_debito": 0,
        "duplicados": 0,
        "errores_matematicos": 0,
        "errores_codigo": 0,
        "ajustes_centavos": 0,
    }

    operaciones = []
    claves_archivo = set()
    asiento = proximo_asiento()

    for numero_fila, (_, fila) in enumerate(df.iterrows(), start=2):
        try:
            fecha = formatear_fecha(fila.iloc[0])
            anio, mes = obtener_anio_mes(fila.iloc[0])

            codigo = limpiar_texto(fila.iloc[1])
            punto_venta, numero = construir_numero_comprobante_desde_fila(fila)

            cuit = limpiar_texto(fila.iloc[7])
            cliente = limpiar_texto(fila.iloc[8])

            if cliente == "":
                cliente = "CONSUMIDOR FINAL"

            cliente_clave = cuit if cuit != "" else cliente

            neto = limpiar_numero(fila.iloc[22])
            iva = limpiar_numero(fila.iloc[26])
            total = limpiar_numero(fila.iloc[27])

            contenido_fila = fila.to_dict()

            if not tipo_comprobante_existe(codigo):
                resultado["errores"] += 1
                resultado["errores_codigo"] += 1

                operaciones.append(
                    op_insert_error(
                        "VENTAS",
                        nombre_archivo,
                        numero_fila,
                        f"Código de comprobante inexistente: {codigo}",
                        contenido_fila,
                    )
                )
                continue

            config = obtener_tipo_comprobante_config(codigo)

            if config is None:
                resultado["errores"] += 1
                resultado["errores_codigo"] += 1

                operaciones.append(
                    op_insert_error(
                        "VENTAS",
                        nombre_archivo,
                        numero_fila,
                        f"No se pudo interpretar el comprobante: {codigo}",
                        contenido_fila,
                    )
                )
                continue

            tipo = tipo_desde_descripcion(config["descripcion"])
            signo = int(config["signo"])

            clave = construir_clave_comprobante(codigo, numero, cliente_clave)

            if clave in claves_archivo or comprobante_ya_procesado("VENTAS", codigo, numero, cliente_clave):
                resultado["duplicados"] += 1

                operaciones.append(
                    op_insert_error(
                        "VENTAS",
                        nombre_archivo,
                        numero_fila,
                        (
                            "ADVERTENCIA - Comprobante duplicado omitido. "
                            f"Código {codigo}, número {numero}, cliente/CUIT {cliente_clave}. "
                            "No se generaron asientos ni movimientos duplicados."
                        ),
                        contenido_fila,
                    )
                )
                continue

            claves_archivo.add(clave)

            importes = interpretar_importes_venta(neto, iva, total)

            if not importes["ok"]:
                resultado["errores"] += 1
                resultado["errores_matematicos"] += 1

                operaciones.append(
                    op_insert_error(
                        "VENTAS",
                        nombre_archivo,
                        numero_fila,
                        (
                            f"{importes['motivo']}. "
                            f"Neto: {neto}, IVA: {iva}, Total: {total}, "
                            f"Diferencia: {importes['diferencia']}"
                        ),
                        contenido_fila,
                    )
                )
                continue

            if importes["ajuste_centavos"]:
                resultado["ajustes_centavos"] += 1

            importes_con_signo = aplicar_signo(
                importes["neto"],
                importes["iva"],
                importes["total"],
                signo,
            )

            neto_s = importes_con_signo["neto"]
            iva_s = importes_con_signo["iva"]
            total_s = importes_con_signo["total"]

            glosa = f"{tipo} {numero} - {cliente}"

            debe_total = total_s if total_s > 0 else 0
            haber_total = abs(total_s) if total_s < 0 else 0

            debe_venta = abs(neto_s) if neto_s < 0 else 0
            haber_venta = neto_s if neto_s > 0 else 0

            debe_iva = abs(iva_s) if iva_s < 0 else 0
            haber_iva = iva_s if iva_s > 0 else 0

            operaciones.append(
                op_insert_libro_diario(
                    asiento,
                    fecha,
                    "DEUDORES POR VENTAS",
                    debe_total,
                    haber_total,
                    glosa,
                    "VENTAS",
                    nombre_archivo,
                )
            )

            operaciones.append(
                op_insert_libro_diario(
                    asiento,
                    fecha,
                    "VENTAS",
                    debe_venta,
                    haber_venta,
                    glosa,
                    "VENTAS",
                    nombre_archivo,
                )
            )

            if iva_s != 0:
                operaciones.append(
                    op_insert_libro_diario(
                        asiento,
                        fecha,
                        "IVA DEBITO FISCAL",
                        debe_iva,
                        haber_iva,
                        glosa,
                        "VENTAS",
                        nombre_archivo,
                    )
                )

            operaciones.append(
                op_insert_comprobante_procesado(
                    "VENTAS",
                    fecha,
                    codigo,
                    numero,
                    cliente_clave,
                    total_s,
                    nombre_archivo,
                )
            )

            operaciones.append(
                op_insert_venta(
                    fecha,
                    anio,
                    mes,
                    codigo,
                    tipo,
                    punto_venta,
                    numero,
                    cliente,
                    cuit,
                    neto_s,
                    iva_s,
                    total_s,
                    nombre_archivo,
                )
            )

            operaciones.append(
                op_insert_cta_cte_cliente(
                    fecha,
                    cliente,
                    cuit,
                    tipo,
                    numero,
                    total_s if total_s > 0 else 0,
                    abs(total_s) if total_s < 0 else 0,
                    0,
                    "VENTAS",
                    nombre_archivo,
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
                    "VENTAS",
                    nombre_archivo,
                    numero_fila,
                    f"Error inesperado: {str(e)}",
                    fila.to_dict(),
                )
            )

    if resultado["procesados"] > 0:
        operaciones.append(
            op_insert_historial(
                "VENTAS",
                nombre_archivo,
                resultado["procesados"],
            )
        )

    if operaciones:
        ejecutar_transaccion(operaciones)

    return resultado