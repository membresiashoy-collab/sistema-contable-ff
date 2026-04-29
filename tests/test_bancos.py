from pathlib import Path
import ast


def leer_archivo(ruta):
    return Path(ruta).read_text(encoding="utf-8")


def obtener_funciones(ruta):
    contenido = leer_archivo(ruta)
    arbol = ast.parse(contenido)

    return {
        nodo.name
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.FunctionDef)
    }


def obtener_codigo_funcion(ruta, nombre_funcion):
    contenido = leer_archivo(ruta)
    arbol = ast.parse(contenido)

    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.FunctionDef) and nodo.name == nombre_funcion:
            return ast.get_source_segment(contenido, nodo)

    raise AssertionError(f"No se encontró la función {nombre_funcion} en {ruta}.")


def test_bancos_operaciones_service_existe_y_tiene_funciones_clave():
    funciones = obtener_funciones("services/bancos_operaciones_service.py")

    assert "obtener_resumen_eliminacion_importacion_bancaria" in funciones
    assert "eliminar_importacion_bancaria" in funciones
    assert "registrar_imputacion_cobro" in funciones
    assert "registrar_imputacion_pago" in funciones
    assert "registrar_pago_fiscal" in funciones
    assert "regenerar_asientos_bancarios_agrupados" in funciones
    assert "desimputar_conciliacion_bancaria" in funciones
    assert "obtener_conciliaciones_bancarias" in funciones


def test_bancos_ui_importa_operaciones_pro():
    contenido = leer_archivo("modulos/bancos.py")

    assert "from services.bancos_operaciones_service import" in contenido
    assert "eliminar_importacion_bancaria" in contenido
    assert "registrar_imputacion_cobro" in contenido
    assert "registrar_imputacion_pago" in contenido
    assert "registrar_pago_fiscal" in contenido
    assert "regenerar_asientos_bancarios_agrupados" in contenido
    assert "desimputar_conciliacion_bancaria" in contenido


def test_bancos_ui_tiene_eliminacion_de_importaciones_con_confirmacion_simple():
    contenido = leer_archivo("modulos/bancos.py")

    assert "Eliminar importación cargada por error" in contenido
    assert "Confirmo que quiero eliminar la carga" in contenido
    assert "bancos_acepta_eliminar_importacion" in contenido
    assert "Eliminar importación seleccionada" in contenido
    assert "BORRAR" not in contenido
    assert "bancos_confirmar_eliminar_importacion" not in contenido


def test_bancos_ui_tiene_eliminacion_administrativa_completa():
    contenido = leer_archivo("modulos/bancos.py")

    assert "Eliminar archivo completo como administrador" in contenido
    assert "forzar_eliminacion_admin=True" in contenido
    assert "usuario_es_administrador" in contenido
    assert "reversión automática" in contenido


def test_bancos_ui_tiene_desimputacion_individual():
    contenido = leer_archivo("modulos/bancos.py")

    assert "Desimputar" in contenido
    assert "Desimputar conciliación seleccionada" in contenido
    assert "desimputar_conciliacion_bancaria" in contenido
    assert "banco_acepta_desimputar" in contenido


def test_bancos_ui_corrige_titulos_y_ortografia_contable():
    contenido = leer_archivo("modulos/bancos.py")

    assert "Asientos propuestos de Banco / Caja" in contenido
    assert "Pendientes de imputación" in contenido
    assert "Resumen / Estadísticas de Ventas" not in contenido
    assert "Libro IVA Ventas" not in contenido
    assert "Gasto bancario gravado" in contenido
    assert "grabado" not in contenido.lower()
    assert "Impuesto sobre débitos y créditos bancarios" in contenido


def test_bancos_ui_mejora_nombre_de_asientos_agrupados():
    contenido = leer_archivo("modulos/bancos.py")

    assert "Operaciones bancarias agrupadas para contabilizar" in contenido
    assert "Operación bancaria agrupada" in contenido
    assert "Vista por asiento agrupado" not in contenido
    assert "Cada opción representa una operación bancaria agrupada" in contenido


def test_bancos_ui_filtra_asientos_agrupados_solo_con_movimientos():
    contenido = leer_archivo("modulos/bancos.py")

    assert "df_con_movimientos" in contenido
    assert "procesados" in contenido
    assert "Importación con movimientos" in contenido
    assert "Las cargas duplicadas sin movimientos no generan asientos" in contenido


def test_bancos_ui_tiene_imputacion_manual_cobros_pagos_fiscales():
    contenido = leer_archivo("modulos/bancos.py")

    assert "Imputar cobros" in contenido
    assert "Imputar pagos" in contenido
    assert "Pagos fiscales" in contenido
    assert "Confirmar imputación de cobro" in contenido
    assert "Confirmar imputación de pago" in contenido
    assert "Confirmar pago fiscal" in contenido


def test_bancos_tiene_asientos_agrupados_por_operacion():
    contenido_service = leer_archivo("services/bancos_operaciones_service.py")
    contenido_ui = leer_archivo("modulos/bancos.py")

    assert "regenerar_asientos_bancarios_agrupados" in contenido_service
    assert "Asiento agrupado Banco/Caja" in contenido_service
    assert "fecha, referencia, causal, banco, nombre_cuenta" in contenido_service
    assert "Regenerar asientos agrupados de esta importación" in contenido_ui


def test_asientos_usan_nombre_real_de_banco_en_lugar_de_nombre_generico():
    contenido_service = leer_archivo("services/bancos_operaciones_service.py")

    assert "_nombre_cuenta_banco_desde_movimiento" in contenido_service
    assert 'f"{banco} - {nombre_cuenta}"' in contenido_service
    assert "cuenta_banco_nombre" in contenido_service


def test_eliminacion_bancaria_no_borra_tablas_ajenas():
    funcion = obtener_codigo_funcion(
        "services/bancos_operaciones_service.py",
        "eliminar_importacion_bancaria"
    ).lower()

    tablas_ajenas = [
        "ventas_comprobantes",
        "compras_comprobantes",
        "compras_detalle",
        "libro_diario",
        "diario_asientos",
        "iva_ventas",
        "iva_compras",
    ]

    for tabla in tablas_ajenas:
        assert f"delete from {tabla}" not in funcion


def test_eliminacion_bancaria_borra_solo_tablas_banco_relacionadas():
    funcion = obtener_codigo_funcion(
        "services/bancos_operaciones_service.py",
        "eliminar_importacion_bancaria"
    ).lower()

    assert "delete from bancos_asientos_propuestos" in funcion
    assert "delete from bancos_grupos_fiscales" in funcion
    assert "delete from bancos_movimientos" in funcion
    assert "delete from bancos_importaciones" in funcion


def test_desimputacion_revierte_cuentas_corrientes_y_asientos_propuestos():
    contenido = leer_archivo("services/bancos_operaciones_service.py")

    assert "_revertir_detalles_cuenta_corriente" in contenido
    assert "BANCO_DESIMPUTACION" in contenido
    assert "DELETE FROM bancos_asientos_propuestos" in contenido
    assert "UPDATE bancos_movimientos" in contenido