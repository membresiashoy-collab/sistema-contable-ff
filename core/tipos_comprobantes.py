def interpretar_tipo_comprobante(tipo_signo, neto, iva, total):

    # NOTA DE CRÉDITO
    if tipo_signo == -1:
        return {
            "neto": -abs(neto),
            "iva": -abs(iva),
            "total": -abs(total)
        }

    # NOTA DE DÉBITO
    if tipo_signo == 1 and "DEBITO" in str(tipo_signo):
        return {
            "neto": abs(neto),
            "iva": abs(iva),
            "total": abs(total)
        }

    # FACTURA NORMAL
    return {
        "neto": neto,
        "iva": iva,
        "total": total
    }