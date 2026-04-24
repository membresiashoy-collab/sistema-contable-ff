import streamlit as st

from services.seguridad_service import (
    obtener_empresas,
    crear_empresa,
    obtener_usuarios,
    crear_usuario,
    resetear_password_usuario,
    actualizar_estado_usuario,
    actualizar_rol_usuario,
    obtener_roles,
    obtener_permisos,
    obtener_rol_permisos,
    guardar_permisos_rol
)

from core.ui import preparar_vista


def mostrar_seguridad():
    st.title("🔐 Seguridad y Multiempresa")

    tab1, tab2, tab3, tab4 = st.tabs([
        "Empresas",
        "Usuarios",
        "Roles y Permisos",
        "Ayuda"
    ])

    with tab1:
        mostrar_empresas()

    with tab2:
        mostrar_usuarios()

    with tab3:
        mostrar_roles_permisos()

    with tab4:
        mostrar_ayuda()


def mostrar_empresas():
    st.subheader("Empresas / Clientes")

    df = obtener_empresas()

    if df.empty:
        st.info("No hay empresas cargadas.")
    else:
        st.dataframe(preparar_vista(df), use_container_width=True)

    st.divider()

    with st.form("form_empresa"):
        st.subheader("Crear empresa")

        nombre = st.text_input("Nombre interno")
        cuit = st.text_input("CUIT")
        razon_social = st.text_input("Razón social")
        domicilio = st.text_input("Domicilio")
        actividad = st.text_input("Actividad")

        guardar = st.form_submit_button("Crear empresa")

        if guardar:
            if nombre.strip() == "":
                st.warning("Ingresá un nombre.")
            else:
                crear_empresa(
                    nombre.strip(),
                    cuit.strip(),
                    razon_social.strip(),
                    domicilio.strip(),
                    actividad.strip()
                )
                st.success("Empresa creada.")
                st.rerun()


def mostrar_usuarios():
    st.subheader("Usuarios")

    df_usuarios = obtener_usuarios()

    if df_usuarios.empty:
        st.info("No hay usuarios.")
    else:
        st.dataframe(preparar_vista(df_usuarios), use_container_width=True)

    st.divider()

    df_roles = obtener_roles()
    df_empresas = obtener_empresas()

    if df_roles.empty or df_empresas.empty:
        st.warning("Primero deben existir roles y empresas.")
        return

    with st.form("form_crear_usuario"):
        st.subheader("Crear usuario")

        col1, col2, col3 = st.columns(3)

        with col1:
            usuario = st.text_input("Usuario")
            nombre = st.text_input("Nombre")

        with col2:
            email = st.text_input("Email")
            password = st.text_input("Contraseña inicial", type="password")

        with col3:
            rol = st.selectbox("Rol", df_roles["rol"].tolist())
            empresas_sel = st.multiselect(
                "Empresas habilitadas",
                options=df_empresas["id"].tolist(),
                format_func=lambda x: df_empresas[df_empresas["id"] == x].iloc[0]["nombre"]
            )

        guardar = st.form_submit_button("Crear usuario")

        if guardar:
            if usuario.strip() == "" or password.strip() == "":
                st.warning("Usuario y contraseña son obligatorios.")
            elif not empresas_sel:
                st.warning("Seleccioná al menos una empresa.")
            else:
                crear_usuario(
                    usuario.strip(),
                    nombre.strip(),
                    email.strip(),
                    password,
                    rol,
                    empresas_sel
                )
                st.success("Usuario creado.")
                st.rerun()

    st.divider()

    if not df_usuarios.empty:
        st.subheader("Administrar usuario existente")

        usuario_id = st.selectbox(
            "Seleccionar usuario",
            df_usuarios["id"].tolist(),
            format_func=lambda x: df_usuarios[df_usuarios["id"] == x].iloc[0]["usuario"]
        )

        fila = df_usuarios[df_usuarios["id"] == usuario_id].iloc[0]

        col1, col2, col3 = st.columns(3)

        with col1:
            nuevo_rol = st.selectbox(
                "Rol",
                df_roles["rol"].tolist(),
                index=df_roles["rol"].tolist().index(fila["rol"]) if fila["rol"] in df_roles["rol"].tolist() else 0
            )

            if st.button("Actualizar rol"):
                actualizar_rol_usuario(usuario_id, nuevo_rol)
                st.success("Rol actualizado.")
                st.rerun()

        with col2:
            activo = st.selectbox(
                "Estado",
                [1, 0],
                index=0 if int(fila["activo"]) == 1 else 1,
                format_func=lambda x: "Activo" if x == 1 else "Inactivo"
            )

            if st.button("Actualizar estado"):
                actualizar_estado_usuario(usuario_id, activo)
                st.success("Estado actualizado.")
                st.rerun()

        with col3:
            nueva_pass = st.text_input("Nueva contraseña", type="password")

            if st.button("Resetear contraseña"):
                if nueva_pass.strip() == "":
                    st.warning("Ingresá una nueva contraseña.")
                else:
                    resetear_password_usuario(usuario_id, nueva_pass)
                    st.success("Contraseña reseteada. El usuario deberá cambiarla.")
                    st.rerun()


def mostrar_roles_permisos():
    st.subheader("Roles y Permisos")

    df_roles = obtener_roles()
    df_permisos = obtener_permisos()

    if df_roles.empty or df_permisos.empty:
        st.warning("No hay roles o permisos cargados.")
        return

    rol = st.selectbox("Rol a configurar", df_roles["rol"].tolist())

    permisos_actuales = obtener_rol_permisos(rol)

    st.write(f"Configurando rol: **{rol}**")

    permisos_seleccionados = []

    for modulo in sorted(df_permisos["modulo"].unique().tolist()):
        st.markdown(f"### {modulo}")

        df_modulo = df_permisos[df_permisos["modulo"] == modulo]

        for _, fila in df_modulo.iterrows():
            permiso = fila["permiso"]
            descripcion = fila["descripcion"]

            marcado = permiso in permisos_actuales

            valor = st.checkbox(
                f"{permiso} — {descripcion}",
                value=marcado,
                key=f"{rol}_{permiso}"
            )

            if valor:
                permisos_seleccionados.append(permiso)

    if st.button("Guardar permisos del rol"):
        guardar_permisos_rol(rol, permisos_seleccionados)
        st.success("Permisos actualizados.")
        st.rerun()


def mostrar_ayuda():
    st.subheader("Cómo usar Seguridad")

    st.write("""
    Recomendación inicial:

    1. Entrar con usuario `admin`.
    2. Contraseña inicial: `admin123`.
    3. Cambiar la contraseña del administrador.
    4. Crear empresas/clientes.
    5. Crear usuarios.
    6. Asignar roles.
    7. Revisar permisos por rol.

    Roles sugeridos:

    - ADMINISTRADOR: control total.
    - CONTADOR: contabilidad e impuestos.
    - AUXILIAR: carga de datos.
    - CLIENTE: consulta limitada.
    - LECTURA: solo lectura.
    """)