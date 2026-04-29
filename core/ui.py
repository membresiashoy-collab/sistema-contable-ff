from html import escape
from textwrap import dedent

import streamlit as st


def preparar_vista(df):
    df_vista = df.copy()
    df_vista.index = range(1, len(df_vista) + 1)
    df_vista.index.name = "N°"
    return df_vista


def aplicar_estilos_globales():
    st.markdown(
        dedent(
            """
            <style>
                :root {
                    --ff-bg-page: #0b1220;
                    --ff-bg-panel: #111827;
                    --ff-bg-panel-2: #162033;
                    --ff-bg-input: #0f172a;
                    --ff-border: #334155;
                    --ff-border-soft: #243044;
                    --ff-text: #f8fafc;
                    --ff-muted: #cbd5e1;
                    --ff-muted-2: #94a3b8;
                    --ff-primary: #38bdf8;
                    --ff-primary-2: #2563eb;
                    --ff-danger: #ef4444;
                    --ff-radius-lg: 22px;
                    --ff-radius-md: 16px;
                    --ff-shadow-soft: 0 10px 28px rgba(0, 0, 0, 0.28);
                }

                html,
                body,
                .stApp {
                    color: var(--ff-text) !important;
                    text-rendering: optimizeLegibility;
                    -webkit-font-smoothing: antialiased;
                    -moz-osx-font-smoothing: grayscale;
                    filter: none !important;
                    backdrop-filter: none !important;
                    -webkit-backdrop-filter: none !important;
                }

                .stApp {
                    background: linear-gradient(135deg, #07101d 0%, #0b1220 48%, #111827 100%) !important;
                    color: var(--ff-text) !important;
                }

                .block-container {
                    padding-top: 1.35rem;
                    padding-bottom: 3rem;
                    max-width: 1480px;
                }

                h1, h2, h3, h4, h5, h6 {
                    color: var(--ff-text) !important;
                    letter-spacing: -0.025em;
                    text-shadow: none !important;
                }

                p, span, label, div {
                    text-shadow: none !important;
                }

                /*
                ======================================================
                SIDEBAR
                ======================================================
                */

                section[data-testid="stSidebar"] {
                    background: #080f1d !important;
                    border-right: 1px solid var(--ff-border-soft) !important;
                    filter: none !important;
                    backdrop-filter: none !important;
                    -webkit-backdrop-filter: none !important;
                }

                section[data-testid="stSidebar"] * {
                    text-shadow: none !important;
                    filter: none !important;
                    backdrop-filter: none !important;
                    -webkit-backdrop-filter: none !important;
                }

                section[data-testid="stSidebar"] div[data-testid="stMarkdownContainer"] p,
                section[data-testid="stSidebar"] label,
                section[data-testid="stSidebar"] span {
                    color: var(--ff-muted) !important;
                }

                div[data-testid="stSidebarUserContent"] {
                    padding-top: 1rem;
                }

                /*
                ======================================================
                MÉTRICAS / TABLAS / TABS
                ======================================================
                */

                div[data-testid="stMetric"] {
                    background: #111827 !important;
                    border: 1px solid var(--ff-border) !important;
                    border-radius: var(--ff-radius-md) !important;
                    padding: 0.85rem 1rem !important;
                    box-shadow: none !important;
                    filter: none !important;
                    backdrop-filter: none !important;
                    -webkit-backdrop-filter: none !important;
                }

                div[data-testid="stMetric"] label {
                    color: var(--ff-muted-2) !important;
                    font-size: 0.82rem !important;
                }

                div[data-testid="stMetric"] div {
                    color: var(--ff-text) !important;
                    text-shadow: none !important;
                }

                div[data-testid="stDataFrame"] {
                    border: 1px solid var(--ff-border) !important;
                    border-radius: var(--ff-radius-md) !important;
                    overflow: hidden !important;
                    filter: none !important;
                    backdrop-filter: none !important;
                    -webkit-backdrop-filter: none !important;
                }

                .stTabs [data-baseweb="tab-list"] {
                    gap: 0.35rem;
                    background: #0f172a !important;
                    border: 1px solid var(--ff-border) !important;
                    border-radius: 999px;
                    padding: 0.35rem;
                }

                .stTabs [data-baseweb="tab"] {
                    border-radius: 999px;
                    padding: 0.45rem 0.9rem;
                    color: var(--ff-muted) !important;
                }

                .stTabs [aria-selected="true"] {
                    background: #0c4a6e !important;
                    color: var(--ff-text) !important;
                    border: 1px solid #0284c7 !important;
                }

                /*
                ======================================================
                BOTONES
                ======================================================
                */

                div.stButton > button,
                div.stDownloadButton > button,
                button[kind="secondary"] {
                    border-radius: 999px !important;
                    border: 1px solid var(--ff-border) !important;
                    background: #111827 !important;
                    color: var(--ff-text) !important;
                    box-shadow: none !important;
                    transition: border-color 0.14s ease-in-out, background 0.14s ease-in-out;
                }

                div.stButton > button:hover,
                div.stDownloadButton > button:hover {
                    border-color: #38bdf8 !important;
                    background: #162033 !important;
                }

                div.stButton > button[kind="primary"] {
                    background: #075985 !important;
                    border: 1px solid #38bdf8 !important;
                    color: white !important;
                    font-weight: 700 !important;
                }

                div.stButton > button:disabled,
                div.stButton > button[disabled] {
                    opacity: 0.48 !important;
                    cursor: not-allowed !important;
                    box-shadow: none !important;
                }

                /*
                ======================================================
                INPUTS, SELECTBOX, MULTISELECT Y POPOVERS
                ======================================================
                */

                div[data-baseweb="select"] > div,
                div[data-baseweb="input"] > div,
                div[data-baseweb="textarea"] textarea,
                textarea,
                input {
                    border-radius: 14px !important;
                    border-color: var(--ff-border) !important;
                    background: #0f172a !important;
                    color: var(--ff-text) !important;
                    box-shadow: none !important;
                    filter: none !important;
                    backdrop-filter: none !important;
                    -webkit-backdrop-filter: none !important;
                    opacity: 1 !important;
                }

                div[data-baseweb="select"] *,
                div[data-baseweb="input"] *,
                div[data-baseweb="textarea"] *,
                textarea,
                input {
                    color: var(--ff-text) !important;
                    text-shadow: none !important;
                    filter: none !important;
                    backdrop-filter: none !important;
                    -webkit-backdrop-filter: none !important;
                    opacity: 1 !important;
                }

                div[data-baseweb="select"] svg,
                div[data-baseweb="input"] svg {
                    color: var(--ff-muted) !important;
                    fill: var(--ff-muted) !important;
                }

                [data-testid="stSelectbox"],
                [data-testid="stMultiSelect"],
                [data-testid="stTextInput"],
                [data-testid="stNumberInput"],
                [data-testid="stTextArea"] {
                    filter: none !important;
                    backdrop-filter: none !important;
                    -webkit-backdrop-filter: none !important;
                    opacity: 1 !important;
                }

                [data-testid="stSelectbox"] label,
                [data-testid="stMultiSelect"] label,
                [data-testid="stTextInput"] label,
                [data-testid="stNumberInput"] label,
                [data-testid="stTextArea"] label {
                    color: var(--ff-text) !important;
                    font-weight: 700 !important;
                }

                div[data-baseweb="popover"] {
                    z-index: 999999 !important;
                    background: transparent !important;
                    filter: none !important;
                    backdrop-filter: none !important;
                    -webkit-backdrop-filter: none !important;
                    opacity: 1 !important;
                }

                div[data-baseweb="popover"] > div,
                div[data-baseweb="popover"] ul,
                div[data-baseweb="popover"] li,
                div[data-baseweb="menu"],
                div[role="listbox"],
                ul[role="listbox"] {
                    background: #0f172a !important;
                    color: var(--ff-text) !important;
                    border: 1px solid var(--ff-border) !important;
                    border-radius: 14px !important;
                    box-shadow: 0 18px 42px rgba(0, 0, 0, 0.55) !important;
                    filter: none !important;
                    backdrop-filter: none !important;
                    -webkit-backdrop-filter: none !important;
                    opacity: 1 !important;
                }

                div[data-baseweb="popover"] *,
                div[data-baseweb="menu"] *,
                div[role="listbox"] *,
                ul[role="listbox"] * {
                    color: var(--ff-text) !important;
                    text-shadow: none !important;
                    filter: none !important;
                    backdrop-filter: none !important;
                    -webkit-backdrop-filter: none !important;
                    opacity: 1 !important;
                    font-weight: 600 !important;
                }

                div[role="option"],
                li[role="option"],
                div[data-baseweb="menu"] li,
                ul[role="listbox"] li {
                    background: #0f172a !important;
                    color: var(--ff-text) !important;
                    border-radius: 10px !important;
                    margin: 0.12rem 0.22rem !important;
                    padding-top: 0.42rem !important;
                    padding-bottom: 0.42rem !important;
                }

                div[role="option"]:hover,
                li[role="option"]:hover,
                div[data-baseweb="menu"] li:hover,
                ul[role="listbox"] li:hover {
                    background: #1e3a5f !important;
                    color: #ffffff !important;
                }

                div[aria-selected="true"][role="option"],
                li[aria-selected="true"][role="option"] {
                    background: #1d4ed8 !important;
                    color: #ffffff !important;
                }

                /*
                ======================================================
                ALERTAS
                ======================================================
                */

                div[data-testid="stAlert"] {
                    border-radius: var(--ff-radius-md) !important;
                    border: 1px solid var(--ff-border) !important;
                    filter: none !important;
                    backdrop-filter: none !important;
                    -webkit-backdrop-filter: none !important;
                }

                /*
                ======================================================
                COMPONENTES PROPIOS
                ======================================================
                */

                .ff-module-hero {
                    display: flex;
                    align-items: stretch;
                    justify-content: space-between;
                    gap: 1rem;
                    margin: 0.25rem 0 1.35rem 0;
                    padding: 1.15rem 1.25rem;
                    border: 1px solid var(--ff-border);
                    border-radius: var(--ff-radius-lg);
                    background: #111827;
                    box-shadow: none;
                }

                .ff-module-left {
                    display: flex;
                    gap: 1rem;
                    align-items: center;
                    min-width: 0;
                }

                .ff-module-icon {
                    width: 4.2rem;
                    min-width: 4.2rem;
                    height: 4.2rem;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    border-radius: 1.35rem;
                    background: #0c4a6e;
                    border: 1px solid #38bdf8;
                    font-size: 2.05rem;
                }

                .ff-module-title {
                    font-size: clamp(2rem, 3.3vw, 3.15rem);
                    line-height: 1;
                    font-weight: 850;
                    letter-spacing: -0.045em;
                    color: var(--ff-text);
                    margin-bottom: 0.38rem;
                    text-shadow: none;
                }

                .ff-module-desc {
                    color: var(--ff-muted);
                    font-size: 0.98rem;
                    line-height: 1.45;
                    max-width: 54rem;
                    text-shadow: none;
                }

                .ff-module-right {
                    display: flex;
                    align-items: center;
                    justify-content: flex-end;
                    min-width: 14rem;
                }

                .ff-company-pill {
                    border: 1px solid #38bdf8;
                    background: #0f172a;
                    color: #e0f2fe;
                    border-radius: 999px;
                    padding: 0.55rem 0.8rem;
                    font-size: 0.82rem;
                    white-space: nowrap;
                    text-shadow: none;
                }

                .ff-sidebar-brand {
                    margin: 0.2rem 0 1rem 0;
                    padding: 1rem;
                    border-radius: 1.2rem;
                    border: 1px solid var(--ff-border);
                    background: #111827;
                    box-shadow: none;
                }

                .ff-sidebar-brand-title {
                    color: var(--ff-text);
                    font-size: 1.05rem;
                    font-weight: 800;
                    margin-bottom: 0.25rem;
                    text-shadow: none;
                }

                .ff-sidebar-brand-subtitle {
                    color: var(--ff-muted-2);
                    font-size: 0.78rem;
                    line-height: 1.35;
                    text-shadow: none;
                }

                .ff-sidebar-user {
                    margin: 0.5rem 0 0.85rem 0;
                    padding: 0.85rem;
                    border-radius: 1rem;
                    border: 1px solid var(--ff-border);
                    background: #0f172a;
                    box-shadow: none;
                }

                .ff-sidebar-user-main {
                    color: var(--ff-text);
                    font-weight: 700;
                    font-size: 0.92rem;
                    text-shadow: none;
                }

                .ff-sidebar-user-meta {
                    color: var(--ff-muted-2);
                    font-size: 0.76rem;
                    margin-top: 0.15rem;
                    text-shadow: none;
                }

                .ff-login-title {
                    text-align: center;
                    font-size: clamp(1.9rem, 4vw, 2.8rem);
                    font-weight: 850;
                    letter-spacing: -0.045em;
                    margin: 1rem 0 1.2rem 0;
                    color: var(--ff-text);
                    text-shadow: none;
                }

                @media (max-width: 760px) {
                    .ff-module-hero {
                        flex-direction: column;
                    }

                    .ff-module-right {
                        justify-content: flex-start;
                    }

                    .ff-module-icon {
                        width: 3.4rem;
                        min-width: 3.4rem;
                        height: 3.4rem;
                        font-size: 1.7rem;
                    }
                }
            </style>
            """
        ),
        unsafe_allow_html=True,
    )


def mostrar_sidebar_brand(
    titulo="Sistema Contable FF",
    subtitulo="Contabilidad, IVA, compras, ventas, bancos y auditoría en un flujo integrado.",
):
    titulo_html = escape(str(titulo))
    subtitulo_html = escape(str(subtitulo))

    st.sidebar.markdown(
        f"""
        <div class="ff-sidebar-brand">
            <div class="ff-sidebar-brand-title">{titulo_html}</div>
            <div class="ff-sidebar-brand-subtitle">{subtitulo_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def mostrar_sidebar_usuario(usuario="administrador", rol="ADMINISTRADOR"):
    usuario_html = escape(str(usuario))
    rol_html = escape(str(rol))

    st.sidebar.markdown(
        f"""
        <div class="ff-sidebar-user">
            <div class="ff-sidebar-user-main">👤 {usuario_html}</div>
            <div class="ff-sidebar-user-meta">Rol: {rol_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def mostrar_sidebar_marca(
    titulo="Sistema Contable FF",
    subtitulo="Contabilidad, IVA, compras, ventas, bancos y auditoría en un flujo integrado.",
    usuario=None,
    rol=None,
    mostrar_usuario=True,
    **kwargs,
):
    mostrar_sidebar_brand(
        titulo=titulo,
        subtitulo=subtitulo,
    )

    if mostrar_usuario and usuario is not None:
        mostrar_sidebar_usuario(
            usuario=usuario,
            rol=rol or "ADMINISTRADOR",
        )


def mostrar_sidebar_usuario_visual(usuario="administrador", rol="ADMINISTRADOR"):
    return mostrar_sidebar_usuario(
        usuario=usuario,
        rol=rol,
    )


def mostrar_encabezado_modulo(icono, titulo, descripcion="", empresa_nombre=""):
    icono_html = escape(str(icono or ""))
    titulo_html = escape(str(titulo or ""))
    descripcion_html = escape(str(descripcion or ""))
    empresa_html = escape(str(empresa_nombre or ""))

    if empresa_html:
        empresa_bloque = (
            '<div class="ff-module-right">'
            f'<div class="ff-company-pill">Empresa activa: <strong>{empresa_html}</strong></div>'
            '</div>'
        )
    else:
        empresa_bloque = ""

    html = (
        '<div class="ff-module-hero">'
        '<div class="ff-module-left">'
        f'<div class="ff-module-icon">{icono_html}</div>'
        '<div>'
        f'<div class="ff-module-title">{titulo_html}</div>'
        f'<div class="ff-module-desc">{descripcion_html}</div>'
        '</div>'
        '</div>'
        f'{empresa_bloque}'
        '</div>'
    )

    st.markdown(html, unsafe_allow_html=True)


def mostrar_encabezado_modulo_visual(icono, titulo, descripcion="", empresa_nombre=""):
    return mostrar_encabezado_modulo(
        icono=icono,
        titulo=titulo,
        descripcion=descripcion,
        empresa_nombre=empresa_nombre,
    )