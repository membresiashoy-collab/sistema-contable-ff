import sys
from pathlib import Path

import pandas as pd


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


from services import ventas_service


def _df_ventas(filas=1):
    datos = []

    for _ in range(filas):
        fila = [""] * 28
        fila[0] = "01/01/2026"
        fila[1] = "006"
        fila[7] = "20111111112"
        fila[8] = "Cliente Demo"
        fila[22] = "1000"
        fila[26] = "0"
        fila[27] = "1000"
        datos.append(fila)

    return pd.DataFrame(datos)


def _preparar_mocks_basicos(monkeypatch, operaciones_guardadas, duplicado_existente=False):
    monkeypatch.setattr(ventas_service, "proximo_asiento", lambda: 1)
    monkeypatch.setattr(ventas_service, "tipo_comprobante_existe", lambda codigo: True)

    monkeypatch.setattr(
        ventas_service,
        "obtener_tipo_comprobante_config",
        lambda codigo: {"descripcion": "Factura B", "signo": 1},
    )

    monkeypatch.setattr(
        ventas_service,
        "tipo_desde_descripcion",
        lambda descripcion: "FACTURA",
    )

    monkeypatch.setattr(
        ventas_service,
        "construir_numero_comprobante_desde_fila",
        lambda fila: ("0001", "0001-00000001"),
    )

    monkeypatch.setattr(
        ventas_service,
        "formatear_fecha",
        lambda fecha: "2026-01-01",
    )

    monkeypatch.setattr(
        ventas_service,
        "obtener_anio_mes",
        lambda fecha: (2026, 1),
    )

    monkeypatch.setattr(
        ventas_service,
        "interpretar_importes_venta",
        lambda neto, iva, total: {
            "ok": True,
            "motivo": "",
            "diferencia": 0,
            "ajuste_centavos": False,
            "neto": neto,
            "iva": iva,
            "total": total,
        },
    )

    monkeypatch.setattr(
        ventas_service,
        "aplicar_signo",
        lambda neto, iva, total, signo: {
            "neto": neto * signo,
            "iva": iva * signo,
            "total": total * signo,
        },
    )

    monkeypatch.setattr(
        ventas_service,
        "comprobante_ya_procesado",
        lambda modulo, codigo, numero, cliente_proveedor: duplicado_existente,
    )

    monkeypatch.setattr(
        ventas_service,
        "ejecutar_transaccion",
        lambda operaciones: operaciones_guardadas.extend(operaciones),
    )


def test_procesar_csv_ventas_no_bloquea_por_nombre_de_archivo(monkeypatch):
    operaciones_guardadas = []
    _preparar_mocks_basicos(
        monkeypatch,
        operaciones_guardadas,
        duplicado_existente=False,
    )

    resultado = ventas_service.procesar_csv_ventas(
        "comprobantes-pesos.csv",
        _df_ventas(filas=1),
    )

    assert resultado["procesados"] == 1
    assert resultado["errores"] == 0
    assert resultado["duplicados"] == 0
    assert resultado["facturas"] == 1
    assert operaciones_guardadas


def test_procesar_csv_ventas_omite_comprobante_ya_existente_sin_error_real(monkeypatch):
    operaciones_guardadas = []
    _preparar_mocks_basicos(
        monkeypatch,
        operaciones_guardadas,
        duplicado_existente=True,
    )

    resultado = ventas_service.procesar_csv_ventas(
        "comprobantes-pesos.csv",
        _df_ventas(filas=1),
    )

    assert resultado["procesados"] == 0
    assert resultado["errores"] == 0
    assert resultado["duplicados"] == 1

    assert any(
        "duplicado omitido" in op[1][3].lower()
        for op in operaciones_guardadas
    )


def test_procesar_csv_ventas_omite_duplicado_dentro_del_mismo_archivo(monkeypatch):
    operaciones_guardadas = []
    _preparar_mocks_basicos(
        monkeypatch,
        operaciones_guardadas,
        duplicado_existente=False,
    )

    resultado = ventas_service.procesar_csv_ventas(
        "comprobantes-pesos.csv",
        _df_ventas(filas=2),
    )

    assert resultado["procesados"] == 1
    assert resultado["errores"] == 0
    assert resultado["duplicados"] == 1
    assert resultado["facturas"] == 1