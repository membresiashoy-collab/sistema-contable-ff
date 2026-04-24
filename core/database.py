def init_db():
    import sqlite3

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS libro_diario (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        id_asiento INTEGER,
        fecha TEXT,
        cuenta TEXT,
        debe REAL,
        haber REAL,
        glosa TEXT,
        origen TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS plan_cuentas (
        codigo TEXT,
        nombre TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tipos_comprobantes (
        codigo TEXT,
        descripcion TEXT,
        signo INTEGER
    )
    """)

    # 🔥 CORREGIDO (IMPORTANTE)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS historial_cargas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        modulo TEXT,
        nombre_archivo TEXT,
        registros INTEGER
    )
    """)

    conn.commit()
    conn.close()