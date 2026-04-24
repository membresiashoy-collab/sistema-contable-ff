def interpretar_importes_venta(neto, iva, total):
    """
    Regla base de ventas:
    - Si IVA = 0, el total se toma como neto.
    - Si hay diferencia menor o igual a $5, se respeta el IVA y el total,
      y se ajusta el neto técnico.
    - Si la diferencia supera $5, se marca como error.
    """

    if iva == 0:
        neto = total

    diferencia = round(total - (neto + iva), 2)

    if abs(diferencia) > 5:
        return {
            "ok": False,
            "neto": neto,
            "iva": iva,
            "total": total,
            "diferencia": diferencia,
            "ajuste_centavos": False,
            "motivo": "Diferencia matemática mayor a $5"
        }

    ajuste_centavos = False

    if diferencia != 0:
        neto = round(total - iva, 2)
        ajuste_centavos = True

    return {
        "ok": True,
        "neto": neto,
        "iva": iva,
        "total": total,
        "diferencia": diferencia,
        "ajuste_centavos": ajuste_centavos,
        "motivo": ""
    }