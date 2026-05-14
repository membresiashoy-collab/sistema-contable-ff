import sqlite3

from services import compras_asientos_propuestos_service as svc


def _crear_schema(conn):
    conn.execute(
        """
        CREATE TABLE plan_cuentas_empresa (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER DEFAULT 1,
            codigo TEXT,
            nombre TEXT,
            estado TEXT DEFAULT 'ACTIVA',
            imputable INTEGER DEFAULT 1,
            uso_operativo_sistema TEXT
        )
        """
    )
    cuentas = [
        (1, "6.1.26", "OTROS GASTOS A REVISAR", "ACTIVA", 1, ""),
        (1, "2.1.01", "Proveedores", "ACTIVA", 1, "PROVEEDORES"),
        (1, "1.1.04.01", "IVA Crédito Fiscal", "ACTIVA", 1, "IVA_CREDITO_FISCAL"),
    ]
    conn.executemany(
        """
        INSERT INTO plan_cuentas_empresa
            (empresa_id, codigo, nombre, estado, imputable, uso_operativo_sistema)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        cuentas,
    )


def test_otros_gastos_a_revisar_resuelve_cuenta_y_no_rompe_asiento():
    conn = sqlite3.connect(":memory:")
    _crear_schema(conn)

    compra = {
        "id": 1,
        "fecha": "2025-08-01",
        "tipo": "FACTURA",
        "punto_venta": "00001",
        "numero": "00000001",
        "proveedor": "Proveedor Demo",
        "cuit": "30111111119",
        "categoria_compra": "OTROS GASTOS A REVISAR",
        "neto": 1000,
        "iva_total": 210,
        "iva_computable_sistema": 210,
        "total": 1210,
    }

    preparado = svc.preparar_lineas_asiento_compra(compra, empresa_id=1, conn=conn)

    assert preparado["ok"] is True
    assert preparado["cuenta_principal_resuelta"]["nombre"] == "OTROS GASTOS A REVISAR"
    assert any(linea["cuenta_nombre"] == "OTROS GASTOS A REVISAR" for linea in preparado["lineas"])
    assert any(linea["cuenta_nombre"] == "IVA Crédito Fiscal" for linea in preparado["lineas"])
    assert any(linea["cuenta_nombre"] == "Proveedores" for linea in preparado["lineas"])
    assert round(preparado["total_debe"] - preparado["total_haber"], 2) == 0