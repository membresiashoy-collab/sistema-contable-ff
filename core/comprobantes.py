from core.textos import limpiar_texto


def tipo_desde_descripcion(descripcion):
    descripcion = str(descripcion).upper()

    if "CREDITO" in descripcion or "CRÉDITO" in descripcion:
        return "NC"

    if "DEBITO" in descripcion or "DÉBITO" in descripcion:
        return "ND"

    return "FACTURA"


def construir_numero_comprobante_desde_fila(fila):
    """
    CSV ARCA/AFIP Ventas:
    columna 2 = punto de venta
    columna 3 = número desde
    columna 4 = número hasta
    """
    punto_venta = limpiar_texto(fila.iloc[2])
    numero_desde = limpiar_texto(fila.iloc[3])
    numero_hasta = limpiar_texto(fila.iloc[4])

    numero = f"{punto_venta}-{numero_desde}"

    if numero_hasta not in ["", "nan", "None"] and numero_hasta != numero_desde:
        numero = f"{punto_venta}-{numero_desde}/{numero_hasta}"

    return punto_venta, numero


def aplicar_signo(neto, iva, total, signo):
    return {
        "neto": round(float(neto) * int(signo), 2),
        "iva": round(float(iva) * int(signo), 2),
        "total": round(float(total) * int(signo), 2)
    }