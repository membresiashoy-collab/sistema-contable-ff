def interpretar_comprobante(tipo, neto, iva, total):

    tipo = str(tipo).upper().strip()

    try:
        neto = float(neto)
    except:
        neto = 0.0

    try:
        iva = float(iva)
    except:
        iva = 0.0

    try:
        total = float(total)
    except:
        total = 0.0

    # -------------------------------------------------
    # CASO SIN IVA DETALLADO (regla que definiste)
    # -------------------------------------------------
    if neto == 0 and iva == 0:
        return {
            "neto": total,
            "iva": 0.0,
            "modo": "SIN_IVA_DETALLADO"
        }

    # -------------------------------------------------
    # CASO NORMAL
    # -------------------------------------------------
    return {
        "neto": neto,
        "iva": iva,
        "modo": "IVA_DETALLADO"
    }