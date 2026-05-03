import re

import pandas as pd
import streamlit as st

from core.ui import preparar_vista

from services.seguridad_service import (
    actualizar_empresa,
    actualizar_estado_usuario,
    actualizar_rol_usuario,
    crear_empresa,
    crear_usuario,
    desactivar_empresa,
    eliminar_empresa_si_vacia,
    obtener_dependencias_empresa,
    obtener_empresas,
    obtener_permisos,
    obtener_roles,
    obtener_rol_permisos,
    obtener_usuarios,
    guardar_permisos_rol,
    reactivar_empresa,
    resetear_password_usuario,
)


# ======================================================
# UTILIDADES
# ======================================================

def usuario_actual_id():
    usuario = st.session_state.get("usuario") or {}
    return usuario.get("id")


def _texto(valor):
    if valor is None:
        return ""

    try:
        if pd.isna(valor):
            return ""
    except Exception:
        pass

    return str(valor).strip()


def _entero(valor, default=0):
    try:
        if valor is None or pd.isna(valor):
            return default
    except Exception:
        if valor is None:
            return default

    try:
        return int(valor)
    except Exception:
        return default


def _solo_digitos(valor):
    return re.sub(r"\D+", "", _texto(valor))


def _empresa_activa(fila):
    return _entero(fila.get("activo"), 0) == 1


def _empresa_datos_minimos_ok(nombre, cuit, razon_social, domicilio, actividad):
    cuit_norm = _solo_digitos(cuit)

    return (
        bool(_texto(nombre))
        and bool(cuit_norm)
        and len(cuit_norm) == 11
        and bool(_texto(razon_social))
        and bool(_texto(domicilio))
        and bool(_texto(actividad))
    )


def _mensaje_datos_empresa_faltantes(nombre, cuit, razon_social, domicilio, actividad):
    faltantes = []

    cuit_norm = _solo_digitos(cuit)

    if not _texto(nombre):
        faltantes.append("nombre interno")

    if not cuit_norm:
        faltantes.append("CUIT")

    if cuit_norm and len(cuit_norm) != 11:
        faltantes.append("CUIT válido de 11 dígitos")

    if not _texto(razon_social):
        faltantes.append("razón social")

    if not _texto(domicilio):
        faltantes.append("domicilio")

    if not _texto(actividad):
        faltantes.append("actividad")

    if not faltantes:
        return ""

    return "Para guardar la empresa falta completar: " + ", ".join(faltantes) + "."


def _mostrar_resultado_servicio(resultado, mensaje_ok_default="Operación realizada correctamente."):
    if isinstance(resultado, dict):
        if resultado.get("ok"):
            st.success(resultado.get("mensaje") or mensaje_ok_default)
            return True

        st.error(resultado.get("mensaje") or "No se pudo completar la operación.")

        conflicto = resultado.get("conflicto")
        if conflicto:
            st.warning(
                f"Conflicto detectado: {conflicto.get('campo', '')}. "
                f"Empresa existente: {conflicto.get('empresa_nombre', '')} "
                f"(ID {conflicto.get('empresa_id', '')})."
            )

        detalle = resultado.get("detalle")
        if isinstance(detalle, dict) and detalle.get("mensaje"):
            st.info(detalle.get("mensaje"))

        dependencias = resultado.get("dependencias")
        if isinstance(dependencias, pd.DataFrame) and not dependencias.empty:
            st.dataframe(preparar_vista(dependencias), use_container_width=True)

        return False

    st.success(mensaje_ok_default)
    return True


def _preparar_empresas_vista(df):
    if df.empty:
        return df

    vista = df.copy()

    if "activo" in vista.columns:
        vista["estado"] = vista["activo"].apply(lambda x: "Activa" if _entero(x) == 1 else "Inactiva")

    columnas = [
        "id",
        "estado",
        "nombre",
        "cuit",
        "razon_social",
        "domicilio",
        "actividad",
        "activo",
    ]

    columnas = [c for c in columnas if c in vista.columns]

    return vista[columnas].rename(columns={
        "id": "ID",
        "estado": "Estado",
        "nombre": "Nombre interno",
        "cuit": "CUIT",
        "razon_social": "Razón social",
        "domicilio": "Domicilio",
        "actividad": "Actividad",
        "activo": "Activo",
    })


def _preparar_usuarios_vista(df):
    if df.empty:
        return df

    vista = df.copy()

    if "activo" in vista.columns:
        vista["estado"] = vista["activo"].apply(lambda x: "Activo" if _entero(x) == 1 else "Inactivo")

    if "debe_cambiar_password" in vista.columns:
        vista["cambia_password"] = vista["debe_cambiar_password"].apply(
            lambda x: "Sí" if _entero(x) == 1 else "No"
        )

    columnas = [
        "id",
        "usuario",
        "nombre",
        "email",
        "rol",
        "estado",
        "cambia_password",
        "ultimo_login",
    ]

    columnas = [c for c in columnas if c in vista.columns]

    return vista[columnas].rename(columns={
        "id": "ID",
        "usuario": "Usuario",
        "nombre": "Nombre",
        "email": "Email",
        "rol": "Rol",
        "estado": "Estado",
        "cambia_password": "Debe cambiar contraseña",
        "ultimo_login": "Último login",
    })


def _filtrar_empresas(df, texto_busqueda="", solo_activas=False):
    if df.empty:
        return df

    filtrado = df.copy()

    if solo_activas and "activo" in filtrado.columns:
        filtrado = filtrado[filtrado["activo"].astype(int) == 1].copy()

    buscar = _texto(texto_busqueda).lower()

    if buscar:
        campos = []
        for col in ["nombre", "cuit", "razon_social", "domicilio", "actividad"]:
            if col in filtrado.columns:
                campos.append(filtrado[col].astype(str))

        if campos:
            texto = campos[0]
            for campo in campos[1:]:
                texto = texto + " " + campo

            filtrado = filtrado[texto.str.lower().str.contains(buscar, na=False)].copy()

    return filtrado


def _etiqueta_empresa(df_empresas, empresa_id):
    fila = df_empresas[df_empresas["id"].astype(int) == int(empresa_id)].iloc[0]

    estado = "Activa" if _empresa_activa(fila) else "Inactiva"
    cuit = _texto(fila.get("cuit")) or "Sin CUIT"
    razon = _texto(fila.get("razon_social")) or "Sin razón social"

    return f"#{int(fila['id'])} | {estado} | {_texto(fila.get('nombre'))} | {cuit} | {razon}"


def _separar_dependencias(dependencias):
    if dependencias is None or dependencias.empty:
        return (
            pd.DataFrame(columns=["tabla", "cantidad", "tipo", "bloquea_borrado"]),
            pd.DataFrame(columns=["tabla", "cantidad", "tipo", "bloquea_borrado"]),
        )

    df = dependencias.copy()

    if "bloquea_borrado" not in df.columns:
        df["bloquea_borrado"] = 1

    operativas = df[df["bloquea_borrado"].astype(int) == 1].copy()
    administrativas = df[df["bloquea_borrado"].astype(int) == 0].copy()

    return operativas, administrativas


# ======================================================
# MÓDULO PRINCIPAL
# ======================================================

def mostrar_seguridad():
    tab1, tab2, tab3, tab4 = st.tabs([
        "Empresas",
        "Usuarios",
        "Roles y Permisos",
        "Ayuda",
    ])

    with tab1:
        mostrar_empresas()

    with tab2:
        mostrar_usuarios()

    with tab3:
        mostrar_roles_permisos()

    with tab4:
        mostrar_ayuda()


# ======================================================
# EMPRESAS
# ======================================================

def mostrar_empresas():
    st.subheader("Empresas / Clientes")

    st.info(
        "Antes de operar con ventas, compras, banco, caja o impuestos, la empresa debe estar bien creada. "
        "El sistema no permite duplicados por CUIT, nombre interno o razón social activa."
    )

    df_empresas = obtener_empresas()

    if df_empresas.empty:
        st.warning("No hay empresas cargadas.")
    else:
        col1, col2 = st.columns([2, 1])

        with col1:
            busqueda = st.text_input(
                "Buscar empresa",
                placeholder="Nombre, CUIT, razón social, domicilio o actividad",
                key="seguridad_empresas_busqueda",
            )

        with col2:
            solo_activas = st.checkbox(
                "Mostrar solo activas",
                value=False,
                key="seguridad_empresas_solo_activas",
            )

        df_filtrado = _filtrar_empresas(
            df_empresas,
            texto_busqueda=busqueda,
            solo_activas=solo_activas,
        )

        if df_filtrado.empty:
            st.warning("No hay empresas que coincidan con el filtro.")
        else:
            st.dataframe(
                preparar_vista(_preparar_empresas_vista(df_filtrado)),
                use_container_width=True,
            )

    st.divider()

    tab_alta, tab_edicion, tab_estado, tab_eliminacion = st.tabs([
        "Crear empresa",
        "Editar empresa",
        "Activar / Desactivar",
        "Eliminar si está vacía",
    ])

    with tab_alta:
        mostrar_crear_empresa()

    with tab_edicion:
        mostrar_editar_empresa(df_empresas)

    with tab_estado:
        mostrar_estado_empresa(df_empresas)

    with tab_eliminacion:
        mostrar_eliminar_empresa_vacia(df_empresas)


def mostrar_crear_empresa():
    st.markdown("### Crear empresa")

    st.caption(
        "El alta exige datos mínimos completos. El botón no se ejecuta con Enter desde un formulario; "
        "se guarda solo al presionar Crear empresa y el servicio vuelve a validar antes de insertar."
    )

    col1, col2 = st.columns(2)

    with col1:
        nombre = st.text_input("Nombre interno *", key="empresa_crear_nombre")
        cuit = st.text_input(
            "CUIT *",
            key="empresa_crear_cuit",
            placeholder="11 dígitos. Ejemplo: 30712345678",
        )
        razon_social = st.text_input("Razón social *", key="empresa_crear_razon_social")

    with col2:
        domicilio = st.text_input("Domicilio *", key="empresa_crear_domicilio")
        actividad = st.text_input("Actividad *", key="empresa_crear_actividad")

    datos_ok = _empresa_datos_minimos_ok(nombre, cuit, razon_social, domicilio, actividad)

    mensaje_faltantes = _mensaje_datos_empresa_faltantes(
        nombre=nombre,
        cuit=cuit,
        razon_social=razon_social,
        domicilio=domicilio,
        actividad=actividad,
    )

    if mensaje_faltantes:
        st.warning(mensaje_faltantes)
    else:
        st.success("Datos mínimos completos. Podés crear la empresa.")

    if st.button(
        "Crear empresa",
        type="primary",
        disabled=not datos_ok,
        use_container_width=True,
        key="empresa_crear_boton",
    ):
        resultado = crear_empresa(
            nombre=nombre,
            cuit=cuit,
            razon_social=razon_social,
            domicilio=domicilio,
            actividad=actividad,
            usuario_id=usuario_actual_id(),
        )

        if _mostrar_resultado_servicio(resultado, "Empresa creada correctamente."):
            st.rerun()


def mostrar_editar_empresa(df_empresas):
    st.markdown("### Editar empresa")

    if df_empresas.empty:
        st.warning("No hay empresas para editar.")
        return

    empresa_id = st.selectbox(
        "Empresa a editar",
        df_empresas["id"].astype(int).tolist(),
        format_func=lambda x: _etiqueta_empresa(df_empresas, x),
        key="empresa_editar_id",
    )

    fila = df_empresas[df_empresas["id"].astype(int) == int(empresa_id)].iloc[0]

    if not _empresa_activa(fila):
        st.warning(
            "La empresa seleccionada está inactiva. Podés corregir sus datos, pero para operar debe reactivarse."
        )

    col1, col2 = st.columns(2)

    with col1:
        nombre = st.text_input(
            "Nombre interno *",
            value=_texto(fila.get("nombre")),
            key="empresa_editar_nombre",
        )
        cuit = st.text_input(
            "CUIT *",
            value=_texto(fila.get("cuit")),
            key="empresa_editar_cuit",
        )
        razon_social = st.text_input(
            "Razón social *",
            value=_texto(fila.get("razon_social")),
            key="empresa_editar_razon_social",
        )

    with col2:
        domicilio = st.text_input(
            "Domicilio *",
            value=_texto(fila.get("domicilio")),
            key="empresa_editar_domicilio",
        )
        actividad = st.text_input(
            "Actividad *",
            value=_texto(fila.get("actividad")),
            key="empresa_editar_actividad",
        )
        motivo = st.text_input(
            "Motivo / observación de cambio",
            value="Corrección de datos de empresa.",
            key="empresa_editar_motivo",
        )

    datos_ok = _empresa_datos_minimos_ok(nombre, cuit, razon_social, domicilio, actividad)

    mensaje_faltantes = _mensaje_datos_empresa_faltantes(
        nombre=nombre,
        cuit=cuit,
        razon_social=razon_social,
        domicilio=domicilio,
        actividad=actividad,
    )

    if mensaje_faltantes:
        st.warning(mensaje_faltantes)

    if st.button(
        "Guardar cambios",
        type="primary",
        disabled=not datos_ok,
        use_container_width=True,
        key="empresa_editar_boton",
    ):
        resultado = actualizar_empresa(
            empresa_id=int(empresa_id),
            nombre=nombre,
            cuit=cuit,
            razon_social=razon_social,
            domicilio=domicilio,
            actividad=actividad,
            usuario_id=usuario_actual_id(),
            motivo=motivo,
        )

        if _mostrar_resultado_servicio(resultado, "Empresa actualizada correctamente."):
            st.rerun()


def mostrar_estado_empresa(df_empresas):
    st.markdown("### Activar / Desactivar empresa")

    if df_empresas.empty:
        st.warning("No hay empresas para administrar.")
        return

    empresa_id = st.selectbox(
        "Empresa",
        df_empresas["id"].astype(int).tolist(),
        format_func=lambda x: _etiqueta_empresa(df_empresas, x),
        key="empresa_estado_id",
    )

    fila = df_empresas[df_empresas["id"].astype(int) == int(empresa_id)].iloc[0]
    activa = _empresa_activa(fila)

    st.write(f"Estado actual: **{'Activa' if activa else 'Inactiva'}**")

    if activa:
        st.warning(
            "Desactivar una empresa no borra sus datos. Solo evita que se use como empresa operativa. "
            "Es la opción segura cuando la empresa tiene movimientos."
        )

        motivo = st.text_area(
            "Motivo de desactivación",
            value="Baja lógica de empresa desde Seguridad.",
            key="empresa_desactivar_motivo",
        )

        aceptar = st.checkbox(
            "Confirmo desactivar esta empresa sin borrar sus movimientos ni registros históricos.",
            key="empresa_desactivar_aceptar",
        )

        if st.button(
            "Desactivar empresa",
            type="primary",
            disabled=not aceptar,
            use_container_width=True,
            key="empresa_desactivar_boton",
        ):
            resultado = desactivar_empresa(
                empresa_id=int(empresa_id),
                usuario_id=usuario_actual_id(),
                motivo=motivo,
            )

            if _mostrar_resultado_servicio(resultado, "Empresa desactivada correctamente."):
                st.rerun()

    else:
        st.info(
            "Reactivar vuelve a dejar la empresa disponible para operar. Antes de reactivar, "
            "el sistema valida que tenga datos completos y que no choque con otra empresa."
        )

        motivo = st.text_area(
            "Motivo de reactivación",
            value="Reactivación de empresa desde Seguridad.",
            key="empresa_reactivar_motivo",
        )

        aceptar = st.checkbox(
            "Confirmo reactivar esta empresa.",
            key="empresa_reactivar_aceptar",
        )

        if st.button(
            "Reactivar empresa",
            type="primary",
            disabled=not aceptar,
            use_container_width=True,
            key="empresa_reactivar_boton",
        ):
            resultado = reactivar_empresa(
                empresa_id=int(empresa_id),
                usuario_id=usuario_actual_id(),
                motivo=motivo,
            )

            if _mostrar_resultado_servicio(resultado, "Empresa reactivada correctamente."):
                st.rerun()


def mostrar_eliminar_empresa_vacia(df_empresas):
    st.markdown("### Eliminar empresa si está vacía")

    st.warning(
        "La eliminación física solo corresponde cuando la empresa fue creada por error, está inactiva "
        "y no tiene movimientos operativos. La auditoría administrativa no bloquea el borrado; ventas, compras, bancos, "
        "caja, tesorería, asientos u otros registros operativos sí lo bloquean."
    )

    if df_empresas.empty:
        st.warning("No hay empresas para evaluar.")
        return

    empresa_id = st.selectbox(
        "Empresa a evaluar",
        df_empresas["id"].astype(int).tolist(),
        format_func=lambda x: _etiqueta_empresa(df_empresas, x),
        key="empresa_eliminar_id",
    )

    fila = df_empresas[df_empresas["id"].astype(int) == int(empresa_id)].iloc[0]
    activa = _empresa_activa(fila)

    dependencias = obtener_dependencias_empresa(
        int(empresa_id),
        incluir_administrativas=True,
    )

    dependencias_operativas, dependencias_administrativas = _separar_dependencias(dependencias)

    if activa:
        st.error(
            "Esta empresa está activa. Para eliminar físicamente una empresa creada por error, primero debe desactivarse."
        )
    else:
        st.success("La empresa está inactiva. Puede evaluarse para eliminación física segura.")

    if not dependencias_operativas.empty:
        st.error(
            "La empresa tiene registros operativos asociados. No se puede borrar físicamente; debe permanecer inactiva."
        )
        st.dataframe(
            preparar_vista(dependencias_operativas),
            use_container_width=True,
        )
    else:
        st.success("No se detectaron registros operativos asociados.")

    if not dependencias_administrativas.empty:
        st.info(
            "Se detectaron registros administrativos no bloqueantes. El servicio los limpiará o desvinculará si corresponde."
        )
        st.dataframe(
            preparar_vista(dependencias_administrativas),
            use_container_width=True,
        )

    motivo = st.text_area(
        "Motivo",
        value="Eliminación física de empresa creada por error, inactiva y sin movimientos operativos.",
        key="empresa_eliminar_motivo",
    )

    puede_eliminar = (
        not activa
        and dependencias_operativas.empty
    )

    if not puede_eliminar:
        st.caption(
            "El botón de eliminación queda bloqueado hasta que la empresa esté inactiva y no tenga dependencias operativas."
        )

    aceptar = st.checkbox(
        "Confirmo que esta eliminación física solo debe ejecutarse si el servicio verifica nuevamente que la empresa está inactiva y sin movimientos operativos.",
        key="empresa_eliminar_aceptar",
    )

    st.caption(
        f"Empresa seleccionada: #{int(fila['id'])} — {_texto(fila.get('nombre'))}"
    )

    if st.button(
        "Eliminar definitivamente solo si está inactiva y vacía",
        type="primary",
        disabled=not aceptar or not puede_eliminar,
        use_container_width=True,
        key="empresa_eliminar_boton",
    ):
        resultado = eliminar_empresa_si_vacia(
            empresa_id=int(empresa_id),
            usuario_id=usuario_actual_id(),
            motivo=motivo,
        )

        if _mostrar_resultado_servicio(resultado, "Empresa vacía eliminada correctamente."):
            st.rerun()


# ======================================================
# USUARIOS
# ======================================================

def mostrar_usuarios():
    st.subheader("Usuarios")

    df_usuarios = obtener_usuarios()

    if df_usuarios.empty:
        st.info("No hay usuarios.")
    else:
        st.dataframe(
            preparar_vista(_preparar_usuarios_vista(df_usuarios)),
            use_container_width=True,
        )

    st.divider()

    df_roles = obtener_roles()
    df_empresas = obtener_empresas()

    if not df_empresas.empty and "activo" in df_empresas.columns:
        df_empresas_activas = df_empresas[df_empresas["activo"].astype(int) == 1].copy()
    else:
        df_empresas_activas = df_empresas.copy()

    if df_roles.empty or df_empresas_activas.empty:
        st.warning("Primero deben existir roles y empresas activas.")
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
                options=df_empresas_activas["id"].astype(int).tolist(),
                format_func=lambda x: df_empresas_activas[
                    df_empresas_activas["id"].astype(int) == int(x)
                ].iloc[0]["nombre"],
            )

        guardar = st.form_submit_button("Crear usuario")

        if guardar:
            if usuario.strip() == "" or password.strip() == "":
                st.warning("Usuario y contraseña son obligatorios.")
            elif not empresas_sel:
                st.warning("Seleccioná al menos una empresa activa.")
            else:
                crear_usuario(
                    usuario.strip(),
                    nombre.strip(),
                    email.strip(),
                    password,
                    rol,
                    empresas_sel,
                )
                st.success("Usuario creado.")
                st.rerun()

    st.divider()

    if not df_usuarios.empty:
        st.subheader("Administrar usuario existente")

        usuario_id = st.selectbox(
            "Seleccionar usuario",
            df_usuarios["id"].tolist(),
            format_func=lambda x: df_usuarios[df_usuarios["id"] == x].iloc[0]["usuario"],
        )

        fila = df_usuarios[df_usuarios["id"] == usuario_id].iloc[0]

        col1, col2, col3 = st.columns(3)

        with col1:
            nuevo_rol = st.selectbox(
                "Rol",
                df_roles["rol"].tolist(),
                index=df_roles["rol"].tolist().index(fila["rol"]) if fila["rol"] in df_roles["rol"].tolist() else 0,
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
                format_func=lambda x: "Activo" if x == 1 else "Inactivo",
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


# ======================================================
# ROLES Y PERMISOS
# ======================================================

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
                key=f"{rol}_{permiso}",
            )

            if valor:
                permisos_seleccionados.append(permiso)

    if st.button("Guardar permisos del rol"):
        guardar_permisos_rol(rol, permisos_seleccionados)
        st.success("Permisos actualizados.")
        st.rerun()


# ======================================================
# AYUDA
# ======================================================

def mostrar_ayuda():
    st.subheader("Cómo usar Seguridad")

    st.write("""
    Recomendación inicial:

    1. Entrar con usuario `admin`.
    2. Contraseña inicial: `admin123`.
    3. Cambiar la contraseña del administrador.
    4. Crear empresas/clientes con datos completos: nombre, CUIT, razón social, domicilio y actividad.
    5. No duplicar CUIT, nombre interno ni razón social.
    6. Crear usuarios.
    7. Asignar roles.
    8. Revisar permisos por rol.
    9. Si una empresa fue cargada mal pero ya tiene movimientos, desactivarla en vez de borrarla.
    10. Usar eliminación física únicamente para empresas inactivas y sin movimientos operativos.

    Roles sugeridos:

    - ADMINISTRADOR: control total.
    - CONTADOR: contabilidad e impuestos.
    - AUXILIAR: carga de datos.
    - CLIENTE: consulta limitada.
    - LECTURA: solo lectura.
    """)