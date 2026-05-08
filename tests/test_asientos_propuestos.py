import importlib


def _preparar_db(monkeypatch, tmp_path):
    db_path = tmp_path / "test_asientos_propuestos.sqlite3"

    import config
    import database

    monkeypatch.setattr(config, "DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(database, "DB_PATH", str(db_path), raising=False)

    importlib.reload(database)

    monkeypatch.setattr(database, "DB_PATH", str(db_path), raising=False)
    database.init_db()

    import services.asientos_origen_service as origen_svc
    import services.iva_cierre_service as iva_cierre_svc
    import services.asientos_propuestos_service as bandeja_svc

    importlib.reload(origen_svc)
    importlib.reload(iva_cierre_svc)
    importlib.reload(bandeja_svc)

    bandeja_svc.asegurar_estructura_bandeja_asientos()

    return database, bandeja_svc


def _crear_asiento_central(database):
    conn = database.conectar()

    try:
        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO asientos_propuestos
            (
                empresa_id,
                ejercicio_id,
                fecha,
                origen,
                origen_tabla,
                origen_id,
                tipo_asiento,
                referencia,
                descripcion,
                estado,
                total_debe,
                total_haber,
                diferencia,
                usuario_creacion
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'PROPUESTO', ?, ?, ?, ?)
            """,
            (
                1,
                None,
                "2025-01-01",
                "APERTURA",
                "asientos_origen",
                10,
                "APERTURA",
                "TEST-APERTURA",
                "Asiento apertura test",
                1000.0,
                1000.0,
                0.0,
                "pytest",
            ),
        )

        asiento_id = cur.lastrowid

        cur.execute(
            """
            INSERT INTO asientos_propuestos_detalle
            (
                asiento_propuesto_id,
                renglon,
                cuenta_codigo,
                cuenta_nombre,
                debe,
                haber,
                glosa
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                asiento_id,
                1,
                "1.1.01",
                "Caja",
                1000.0,
                0.0,
                "Apertura caja",
            ),
        )

        cur.execute(
            """
            INSERT INTO asientos_propuestos_detalle
            (
                asiento_propuesto_id,
                renglon,
                cuenta_codigo,
                cuenta_nombre,
                debe,
                haber,
                glosa
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                asiento_id,
                2,
                "3.1.01",
                "Capital social",
                0.0,
                1000.0,
                "Apertura capital",
            ),
        )

        conn.commit()
        return asiento_id

    finally:
        conn.close()


def _crear_asiento_iva(database):
    conn = database.conectar()

    try:
        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO iva_cierres_asientos_propuestos
            (
                cierre_id,
                pago_id,
                empresa_id,
                anio,
                mes,
                periodo,
                fecha,
                tipo_asiento,
                cuenta_codigo,
                cuenta_nombre,
                debe,
                haber,
                glosa,
                estado,
                usuario
            )
            VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PROPUESTO', ?)
            """,
            (
                20,
                1,
                2025,
                12,
                "2025-12",
                "2025-12-01",
                "LIQUIDACION_IVA",
                "2.1.01",
                "IVA débito fiscal",
                500.0,
                0.0,
                "Liquidación IVA test",
                "pytest",
            ),
        )

        cur.execute(
            """
            INSERT INTO iva_cierres_asientos_propuestos
            (
                cierre_id,
                pago_id,
                empresa_id,
                anio,
                mes,
                periodo,
                fecha,
                tipo_asiento,
                cuenta_codigo,
                cuenta_nombre,
                debe,
                haber,
                glosa,
                estado,
                usuario
            )
            VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PROPUESTO', ?)
            """,
            (
                20,
                1,
                2025,
                12,
                "2025-12",
                "2025-12-01",
                "LIQUIDACION_IVA",
                "2.1.20",
                "IVA a pagar",
                0.0,
                500.0,
                "Liquidación IVA test",
                "pytest",
            ),
        )

        conn.commit()

    finally:
        conn.close()


def test_bandeja_lista_central_e_iva(monkeypatch, tmp_path):
    database, svc = _preparar_db(monkeypatch, tmp_path)

    asiento_id = _crear_asiento_central(database)
    _crear_asiento_iva(database)

    df = svc.listar_bandeja_asientos_propuestos(
        empresa_id=1,
        estado="PROPUESTO",
    )

    claves = set(df["fuente_clave"].astype(str).tolist())

    assert f"CENTRAL:{asiento_id}" in claves
    assert "IVA:20:0:LIQUIDACION_IVA" in claves
    assert int((df["origen"] == "IVA_CIERRE").sum()) == 1


def test_contabiliza_asiento_central_y_evita_duplicado(monkeypatch, tmp_path):
    database, svc = _preparar_db(monkeypatch, tmp_path)

    asiento_id = _crear_asiento_central(database)

    resultado = svc.contabilizar_asiento_bandeja(
        f"CENTRAL:{asiento_id}",
        usuario="pytest",
    )

    assert resultado["ok"] is True
    assert resultado["id_asiento"] == 1

    libro = database.ejecutar_query(
        "SELECT * FROM libro_diario ORDER BY id",
        fetch=True,
    )

    assert len(libro) == 2
    assert round(libro["debe"].sum(), 2) == 1000.0
    assert round(libro["haber"].sum(), 2) == 1000.0

    propuesta = database.ejecutar_query(
        """
        SELECT estado, id_asiento_libro_diario
        FROM asientos_propuestos
        WHERE id = ?
        """,
        (asiento_id,),
        fetch=True,
    )

    assert propuesta.iloc[0]["estado"] == "CONTABILIZADO"
    assert int(propuesta.iloc[0]["id_asiento_libro_diario"]) == 1

    duplicado = svc.contabilizar_asiento_bandeja(
        f"CENTRAL:{asiento_id}",
        usuario="pytest",
    )

    assert duplicado["ok"] is False
    assert "Solo se pueden contabilizar" in duplicado["mensaje"]


def test_rechaza_asiento_pendiente_con_motivo(monkeypatch, tmp_path):
    database, svc = _preparar_db(monkeypatch, tmp_path)

    asiento_id = _crear_asiento_central(database)

    resultado = svc.rechazar_asiento_bandeja(
        f"CENTRAL:{asiento_id}",
        motivo="No corresponde",
        usuario="pytest",
    )

    assert resultado["ok"] is True

    propuesta = database.ejecutar_query(
        """
        SELECT estado, motivo_anulacion
        FROM asientos_propuestos
        WHERE id = ?
        """,
        (asiento_id,),
        fetch=True,
    )

    assert propuesta.iloc[0]["estado"] == "RECHAZADO"
    assert "No corresponde" in propuesta.iloc[0]["motivo_anulacion"]

    libro = database.ejecutar_query(
        "SELECT * FROM libro_diario",
        fetch=True,
    )

    assert libro.empty


def test_contabiliza_asiento_iva_agrupado(monkeypatch, tmp_path):
    database, svc = _preparar_db(monkeypatch, tmp_path)

    _crear_asiento_iva(database)

    resultado = svc.contabilizar_asiento_bandeja(
        "IVA:20:0:LIQUIDACION_IVA",
        usuario="pytest",
    )

    assert resultado["ok"] is True
    assert resultado["id_asiento"] == 1

    libro = database.ejecutar_query(
        "SELECT * FROM libro_diario ORDER BY id",
        fetch=True,
    )

    assert len(libro) == 2
    assert round(libro["debe"].sum(), 2) == 500.0
    assert round(libro["haber"].sum(), 2) == 500.0
    assert set(libro["origen"].astype(str)) == {"IVA_CIERRE"}

    iva = database.ejecutar_query(
        """
        SELECT estado, id_asiento_libro_diario
        FROM iva_cierres_asientos_propuestos
        """,
        fetch=True,
    )

    assert set(iva["estado"].astype(str)) == {"CONTABILIZADO"}
    assert set(iva["id_asiento_libro_diario"].astype(int)) == {1}


def test_reversa_asiento_contabilizado(monkeypatch, tmp_path):
    database, svc = _preparar_db(monkeypatch, tmp_path)

    asiento_id = _crear_asiento_central(database)

    contabilizado = svc.contabilizar_asiento_bandeja(
        f"CENTRAL:{asiento_id}",
        usuario="pytest",
    )

    assert contabilizado["ok"] is True

    reverso = svc.reversar_asiento_bandeja(
        f"CENTRAL:{asiento_id}",
        motivo="Error de prueba",
        usuario="pytest",
    )

    assert reverso["ok"] is True
    assert reverso["id_asiento_reverso"] == 2

    libro = database.ejecutar_query(
        """
        SELECT id_asiento, debe, haber, origen
        FROM libro_diario
        ORDER BY id
        """,
        fetch=True,
    )

    assert len(libro) == 4
    assert set(libro["id_asiento"].astype(int)) == {1, 2}
    assert "REVERSO_APERTURA" in set(libro["origen"].astype(str))

    propuesta = database.ejecutar_query(
        """
        SELECT estado, id_asiento_reversion_libro_diario
        FROM asientos_propuestos
        WHERE id = ?
        """,
        (asiento_id,),
        fetch=True,
    )

    assert propuesta.iloc[0]["estado"] == "REVERSADO"
    assert int(propuesta.iloc[0]["id_asiento_reversion_libro_diario"]) == 2

    doble = svc.reversar_asiento_bandeja(
        f"CENTRAL:{asiento_id}",
        motivo="Segundo intento",
        usuario="pytest",
    )

    assert doble["ok"] is False