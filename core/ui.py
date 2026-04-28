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
                    --ff-bg-0: #0b1020;
                    --ff-bg-1: #111827;
                    --ff-bg-2: #172033;
                    --ff-card: rgba(17, 24, 39, 0.84);
                    --ff-card-soft: rgba(30, 41, 59, 0.72);
                    --ff-border: rgba(148, 163, 184, 0.22);
                    --ff-border-strong: rgba(148, 163, 184, 0.34);
                    --ff-text: #f8fafc;
                    --ff-muted: #cbd5e1;
                    --ff-muted-2: #94a3b8;
                    --ff-primary: #38bdf8;
                    --ff-primary-2: #2563eb;
                    --ff-success: #22c55e;
                    --ff-warning: #f59e0b;
                    --ff-danger: #ef4444;
                    --ff-radius-lg: 22px;
                    --ff-radius-md: 16px;
                    --ff-shadow: 0 18px 55px rgba(0, 0, 0, 0.34);
                }

                .stApp {
                    background:
                        radial-gradient(circle at top left, rgba(56, 189, 248, 0.13), transparent 34rem),
                        radial-gradient(circle at top right, rgba(37, 99, 235, 0.16), transparent 34rem),
                        linear-gradient(135deg, #070b16 0%, #0f172a 48%, #111827 100%);
                    color: var(--ff-text);
                }

                section[data-testid="stSidebar"] {
                    background:
                        linear-gradient(180deg, rgba(15, 23, 42, 0.98), rgba(2, 6, 23, 0.98));
                    border-right: 1px solid var(--ff-border);
                }

                section[data-testid="stSidebar"] div[data-testid="stMarkdownContainer"] p,
                section[data-testid="stSidebar"] label,
                section[data-testid="stSidebar"] span {
                    color: var(--ff-muted);
                }

                div[data-testid="stSidebarUserContent"] {
                    padding-top: 1rem;
                }

                .block-container {
                    padding-top: 1.35rem;
                    padding-bottom: 3rem;
                    max-width: 1480px;
                }

                h1, h2, h3 {
                    letter-spacing: -0.035em;
                }

                div[data-testid="stMetric"] {
                    background: rgba(15, 23, 42, 0.70);
                    border: 1px solid var(--ff-border);
                    border-radius: var(--ff-radius-md);
                    padding: 0.85rem 1rem;
                    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.20);
                }

                div[data-testid="stMetric"] label {
                    color: var(--ff-muted-2) !important;
                    font-size: 0.82rem !important;
                }

                div[data-testid="stMetric"] div {
                    color: var(--ff-text);
                }

                div[data-testid="stDataFrame"] {
                    border: 1px solid var(--ff-border);
                    border-radius: var(--ff-radius-md);
                    overflow: hidden;
                }

                .stTabs [data-baseweb="tab-list"] {
                    gap: 0.35rem;
                    background: rgba(15, 23, 42, 0.48);
                    border: 1px solid var(--ff-border);
                    border-radius: 999px;
                    padding: 0.35rem;
                }

                .stTabs [data-baseweb="tab"] {
                    border-radius: 999px;
                    padding: 0.45rem 0.9rem;
                    color: var(--ff-muted);
                }

                .stTabs [aria-selected="true"] {
                    background: linear-gradient(135deg, rgba(56, 189, 248, 0.22), rgba(37, 99, 235, 0.20));
                    color: var(--ff-text) !important;
                    border: 1px solid rgba(56, 189, 248, 0.35);
                }

                div.stButton > button,
                div.stDownloadButton > button,
                button[kind="secondary"] {
                    border-radius: 999px !important;
                    border: 1px solid var(--ff-border-strong) !important;
                    background: rgba(15, 23, 42, 0.72) !important;
                    color: var(--ff-text) !important;
                    transition: all 0.14s ease-in-out;
                }

                div.stButton > button:hover,
                div.stDownloadButton > button:hover {
                    border-color: rgba(56, 189, 248, 0.55) !important;
                    transform: translateY(-1px);
                    box-shadow: 0 10px 24px rgba(56, 189, 248, 0.13);
                }

                div.stButton > button[kind="primary"] {
                    background: linear-gradient(135deg, #0284c7, #2563eb) !important;
                    border: 1px solid rgba(125, 211, 252, 0.35) !important;
                    color: white !important;
                    font-weight: 700 !important;
                }

                div[data-baseweb="select"] > div,
                div[data-baseweb="input"] > div,
                textarea {
                    border-radius: 14px !important;
                    border-color: rgba(148, 163, 184, 0.28) !important;
                    background: rgba(15, 23, 42, 0.72) !important;
                }

                .ff-module-hero {
                    display: flex;
                    align-items: stretch;
                    justify-content: space-between;
                    gap: 1rem;
                    margin: 0.25rem 0 1.35rem 0;
                    padding: 1.15rem 1.25rem;
                    border: 1px solid var(--ff-border);
                    border-radius: var(--ff-radius-lg);
                    background:
                        linear-gradient(135deg, rgba(15, 23, 42, 0.92), rgba(30, 41, 59, 0.70)),
                        radial-gradient(circle at top right, rgba(56, 189, 248, 0.20), transparent 22rem);
                    box-shadow: var(--ff-shadow);
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
                    background: linear-gradient(135deg, rgba(56, 189, 248, 0.18), rgba(37, 99, 235, 0.20));
                    border: 1px solid rgba(125, 211, 252, 0.26);
                    font-size: 2.05rem;
                }

                .ff-module-title {
                    font-size: clamp(2rem, 3.3vw, 3.15rem);
                    line-height: 1;
                    font-weight: 850;
                    letter-spacing: -0.055em;
                    color: var(--ff-text);
                    margin-bottom: 0.38rem;
                }

                .ff-module-desc {
                    color: var(--ff-muted);
                    font-size: 0.98rem;
                    line-height: 1.45;
                    max-width: 54rem;
                }

                .ff-module-right {
                    display: flex;
                    align-items: center;
                    justify-content: flex-end;
                    min-width: 14rem;
                }

                .ff-company-pill {
                    border: 1px solid rgba(56, 189, 248, 0.28);
                    background: rgba(14, 165, 233, 0.10);
                    color: #dff7ff;
                    border-radius: 999px;
                    padding: 0.55rem 0.8rem;
                    font-size: 0.82rem;
                    white-space: nowrap;
                }

                .ff-sidebar-brand {
                    margin: 0.2rem 0 1rem 0;
                    padding: 1rem;
                    border-radius: 1.2rem;
                    border: 1px solid var(--ff-border);
                    background:
                        linear-gradient(135deg, rgba(56, 189, 248, 0.14), rgba(37, 99, 235, 0.10)),
                        rgba(15, 23, 42, 0.68);
                }

                .ff-sidebar-brand-title {
                    color: var(--ff-text);
                    font-size: 1.05rem;
                    font-weight: 800;
                    margin-bottom: 0.25rem;
                }

                .ff-sidebar-brand-subtitle {
                    color: var(--ff-muted-2);
                    font-size: 0.78rem;
                    line-height: 1.35;
                }

                .ff-sidebar-user {
                    margin: 0.5rem 0 0.85rem 0;
                    padding: 0.85rem;
                    border-radius: 1rem;
                    border: 1px solid rgba(148, 163, 184, 0.18);
                    background: rgba(15, 23, 42, 0.58);
                }

                .ff-sidebar-user-main {
                    color: var(--ff-text);
                    font-weight: 700;
                    font-size: 0.92rem;
                }

                .ff-sidebar-user-meta {
                    color: var(--ff-muted-2);
                    font-size: 0.76rem;
                    margin-top: 0.15rem;
                }

                .ff-login-card {
                    margin-top: 8vh;
                    padding: 1.25rem;
                    border-radius: var(--ff-radius-lg);
                    border: 1px solid var(--ff-border);
                    background: rgba(15, 23, 42, 0.72);
                    box-shadow: var(--ff-shadow);
                }

                .ff-card {
                    padding: 1rem;
                    border-radius: var(--ff-radius-md);
                    border: 1px solid var(--ff-border);
                    background: var(--ff-card);
                    box-shadow: 0 14px 35px rgba(0, 0, 0, 0.18);
                }

                .ff-section-note {
                    padding: 0.85rem 1rem;
                    border-radius: 1rem;
                    border: 1px solid rgba(56, 189, 248, 0.22);
                    background: rgba(14, 165, 233, 0.08);
                    color: var(--ff-muted);
                    line-height: 1.45;
                    margin: 0.65rem 0 1rem 0;
                }

                @media (max-width: 900px) {
                    .ff-module-hero {
                        flex-direction: column;
                    }

                    .ff-module-right {
                        justify-content: flex-start;
                        min-width: unset;
                    }

                    .ff-company-pill {
                        white-space: normal;
                    }
                }
            </style>
            """
        ),
        unsafe_allow_html=True
    )


def _limpiar_html(valor):
    return escape(str(valor or ""))


def mostrar_encabezado_modulo_visual(icono, titulo, descripcion, empresa_nombre=""):
    icono_html = _limpiar_html(icono)
    titulo_html = _limpiar_html(titulo)
    descripcion_html = _limpiar_html(descripcion)
    empresa_html = _limpiar_html(empresa_nombre)

    empresa_bloque = ""

    if empresa_html:
        empresa_bloque = (
            f'<div class="ff-module-right">'
            f'<div class="ff-company-pill">Empresa activa: <strong>{empresa_html}</strong></div>'
            f'</div>'
        )

    html = f"""
    <div class="ff-module-hero">
        <div class="ff-module-left">
            <div class="ff-module-icon">{icono_html}</div>
            <div>
                <div class="ff-module-title">{titulo_html}</div>
                <div class="ff-module-desc">{descripcion_html}</div>
            </div>
        </div>
        {empresa_bloque}
    </div>
    """

    st.markdown(dedent(html).strip(), unsafe_allow_html=True)


def mostrar_sidebar_marca(usuario="", rol=""):
    usuario_html = _limpiar_html(usuario)
    rol_html = _limpiar_html(rol)

    st.sidebar.markdown(
        dedent(
            """
            <div class="ff-sidebar-brand">
                <div class="ff-sidebar-brand-title">Sistema Contable FF</div>
                <div class="ff-sidebar-brand-subtitle">
                    Contabilidad, IVA, compras, ventas, bancos y auditoría en un flujo integrado.
                </div>
            </div>
            """
        ).strip(),
        unsafe_allow_html=True
    )

    if usuario_html or rol_html:
        st.sidebar.markdown(
            dedent(
                f"""
                <div class="ff-sidebar-user">
                    <div class="ff-sidebar-user-main">👤 {usuario_html}</div>
                    <div class="ff-sidebar-user-meta">Rol: {rol_html}</div>
                </div>
                """
            ).strip(),
            unsafe_allow_html=True
        )


def mostrar_login_bienvenida():
    st.markdown(
        dedent(
            """
            <div class="ff-login-card">
                <h2 style="margin-top: 0; margin-bottom: 0.25rem;">Sistema Contable FF</h2>
                <p style="color: #cbd5e1; margin-bottom: 0;">
                    Ingresá con tu usuario y contraseña para continuar.
                </p>
            </div>
            """
        ).strip(),
        unsafe_allow_html=True
    )


def mostrar_nota_visual(texto):
    texto_html = _limpiar_html(texto)

    st.markdown(
        dedent(
            f"""
            <div class="ff-section-note">
                {texto_html}
            </div>
            """
        ).strip(),
        unsafe_allow_html=True
    )


def mostrar_tarjeta(titulo, descripcion="", icono=""):
    icono_html = _limpiar_html(icono)
    titulo_html = _limpiar_html(titulo)
    descripcion_html = _limpiar_html(descripcion)

    st.markdown(
        dedent(
            f"""
            <div class="ff-card">
                <div style="font-size: 1.55rem; margin-bottom: 0.35rem;">{icono_html}</div>
                <div style="font-weight: 800; color: #f8fafc; margin-bottom: 0.25rem;">{titulo_html}</div>
                <div style="color: #cbd5e1; font-size: 0.92rem; line-height: 1.45;">{descripcion_html}</div>
            </div>
            """
        ).strip(),
        unsafe_allow_html=True
    )