def interpretar_comprobante(descripcion, neto, iva, total):
    desc = str(descripcion).upper()

    tipo = "FACTURA"
    signo = 1

    if "NOTA DE CREDITO" in desc:
        tipo = "NC"
        signo = -1

    elif "NOTA DE DEBITO" in desc:
        tipo = "ND"
        signo = 1

    # Si no hay IVA informado
    if iva == 0:
        neto = total

    return {
        "tipo": tipo,
        "signo": signo,
        "neto": neto * signo,
        "iva": iva * signo,
        "total": total * signo
    }