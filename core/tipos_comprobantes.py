def clasificar_tipo_comprobante(descripcion):
    descripcion = str(descripcion).upper()

    if "CREDITO" in descripcion or "CRÉDITO" in descripcion:
        return "NC"

    if "DEBITO" in descripcion or "DÉBITO" in descripcion:
        return "ND"

    return "FACTURA"