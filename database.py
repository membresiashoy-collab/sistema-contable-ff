def es_reverso(tipo_str):
    """Busca en la tabla cargada si el nombre coincide con un comprobante de reverso"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        # Buscamos por coincidencia parcial para evitar errores de tildes en el nombre
        t_clean = str(tipo_str).upper().replace("Ó", "O").replace("É", "E")
        cursor.execute("SELECT es_reverso FROM tabla_comprobantes WHERE descripcion LIKE ?", (f'%{t_clean}%',))
        res = cursor.fetchone()
        if res: return res[0] == 1
        # Fallback manual si la tabla no tiene el dato
        return any(x in t_clean for x in ["CREDITO", "NC-", "DEVOLUCION"])