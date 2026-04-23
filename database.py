def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Creamos la tabla base si no existe
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS libro_diario (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            cuenta TEXT,
            debe REAL,
            haber REAL,
            glosa TEXT
        )
    """)
    
    # LÓGICA DE ACTUALIZACIÓN: Agregamos id_asiento si no está presente
    try:
        cursor.execute("ALTER TABLE libro_diario ADD COLUMN id_asiento INTEGER")
    except sqlite3.OperationalError:
        # Si ya existe la columna, ignora el error
        pass

    cursor.execute("CREATE TABLE IF NOT EXISTS plan_cuentas (codigo TEXT PRIMARY KEY, nombre TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS tipos_comprobantes (codigo INTEGER PRIMARY KEY, descripcion TEXT, signo INTEGER)")
    
    conn.commit()
    conn.close()