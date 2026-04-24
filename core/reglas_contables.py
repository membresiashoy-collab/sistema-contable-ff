def interpretar_factura(tipo, neto, iva, total):

    tipo = str(tipo).upper().strip()

    # CASO SIN DISCRIMINACIÓN DE IVA
    if float(neto) == 0 and float(iva) == 0:
        return {
            "neto": float(total),
            "iva": 0,
            "modo": "SIN_IVA_DETALLADO"
        }

    # CASO NORMAL
    return {
        "neto": float(neto),
        "iva": float(iva),
        "modo": "IVA_DETALLADO"
    }