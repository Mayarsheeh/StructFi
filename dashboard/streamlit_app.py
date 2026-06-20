import os
import json
import time
import html

import requests
import streamlit as st
import matplotlib.pyplot as plt
import matplotlib.patches as patches

LOCAL_DEFAULT_API_URL = "http://127.0.0.1:8000"


def resolve_api_url() -> str:
    """
    Resolve the backend API URL safely for local development.

    Priority:
    1. Streamlit secrets: API_URL, when secrets.toml exists
    2. Environment variables: STRUCTFI_API_URL or API_URL
    3. Local FastAPI backend: http://127.0.0.1:8000

    This prevents StreamlitSecretNotFoundError when running locally without
    a .streamlit/secrets.toml file.
    """
    api_url = None

    try:
        api_url = st.secrets.get("API_URL")
    except Exception:
        api_url = None

    api_url = api_url or os.getenv("STRUCTFI_API_URL") or os.getenv("API_URL") or LOCAL_DEFAULT_API_URL
    return str(api_url).rstrip("/")


API_URL = resolve_api_url()

st.set_page_config(
    page_title="StructiFi",
    page_icon="S",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    :root {
        --sf-bg: #f5f5f7;
        --sf-card: rgba(255, 255, 255, 0.82);
        --sf-card-solid: #ffffff;
        --sf-text: #1d1d1f;
        --sf-muted: #6e6e73;
        --sf-border: rgba(0, 0, 0, 0.08);
        --sf-blue: #007aff;
        --sf-blue-dark: #005ecb;
        --sf-green: #34c759;
        --sf-orange: #ff9f0a;
        --sf-red: #ff3b30;
        --sf-shadow: 0 18px 45px rgba(0, 0, 0, 0.08);
        --sf-shadow-soft: 0 10px 28px rgba(0, 0, 0, 0.06);
    }

    .stApp {
        background:
            radial-gradient(circle at 12% 8%, rgba(0, 122, 255, 0.14), transparent 32%),
            radial-gradient(circle at 88% 0%, rgba(52, 199, 89, 0.10), transparent 30%),
            linear-gradient(180deg, #fbfbfd 0%, #f5f5f7 44%, #eef1f5 100%);
        color: var(--sf-text);
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Segoe UI", sans-serif;
    }

    .block-container {
        max-width: 1760px;
        padding-top: 1.05rem;
        padding-bottom: 1.4rem;
    }

    .hero {
        position: relative;
        overflow: hidden;
        background:
            linear-gradient(135deg, rgba(255,255,255,0.94) 0%, rgba(247,249,252,0.86) 56%, rgba(232,241,255,0.88) 100%);
        color: var(--sf-text);
        border-radius: 34px;
        padding: 34px 36px;
        margin-bottom: 18px;
        border: 1px solid rgba(255,255,255,0.85);
        box-shadow: var(--sf-shadow);
        backdrop-filter: blur(24px);
    }

    .hero::after {
        content: "";
        position: absolute;
        right: -110px;
        top: -120px;
        width: 320px;
        height: 320px;
        background: radial-gradient(circle, rgba(0,122,255,0.25), transparent 62%);
        pointer-events: none;
    }

    .hero h1 {
        margin: 0;
        font-size: 3.05rem;
        font-weight: 800;
        letter-spacing: -1.8px;
        line-height: 1.02;
    }

    .hero p {
        margin-top: 12px;
        max-width: 820px;
        color: var(--sf-muted);
        font-size: 1.04rem;
        line-height: 1.55;
    }

    .hero .workflow-pill {
        display: inline-flex;
        gap: 8px;
        flex-wrap: wrap;
        align-items: center;
        margin-top: 18px;
        padding: 8px 12px;
        border-radius: 999px;
        background: rgba(255,255,255,0.78);
        border: 1px solid var(--sf-border);
        color: #3a3a3c;
        font-size: 0.86rem;
        font-weight: 700;
        box-shadow: 0 8px 18px rgba(0,0,0,0.05);
    }

    .card, .export-card, .room-card, .node-card {
        background: var(--sf-card);
        color: var(--sf-text);
        border-radius: 28px;
        padding: 20px;
        border: 1px solid rgba(255,255,255,0.82);
        box-shadow: var(--sf-shadow-soft);
        backdrop-filter: blur(22px);
        margin-bottom: 14px;
    }

    .card {
        min-height: 126px;
    }

    .card.metric-critical {
        border: 1px solid rgba(255, 59, 48, 0.24);
        background: linear-gradient(145deg, rgba(255,255,255,0.94), rgba(255,241,240,0.86));
        box-shadow: 0 16px 34px rgba(255,59,48,0.10);
    }

    .card.metric-live {
        border: 1px solid rgba(52, 199, 89, 0.22);
        background: linear-gradient(145deg, rgba(255,255,255,0.94), rgba(239,253,244,0.86));
    }

    .metric-title {
        font-size: 0.84rem;
        color: var(--sf-muted);
        margin-bottom: 12px;
        font-weight: 700;
        letter-spacing: 0.1px;
    }

    .metric-value {
        font-size: 2.18rem;
        font-weight: 800;
        color: var(--sf-text);
        line-height: 1.05;
        letter-spacing: -1px;
        word-break: break-word;
        overflow-wrap: anywhere;
    }

    .section-title {
        font-size: 1.35rem;
        font-weight: 800;
        color: var(--sf-text);
        margin: 18px 0 12px;
        letter-spacing: -0.45px;
    }

    .status-strip {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 12px;
        margin: 14px 0 2px;
    }

    .status-tile {
        background: rgba(255,255,255,0.76);
        border: 1px solid var(--sf-border);
        border-radius: 22px;
        padding: 15px 16px;
        box-shadow: var(--sf-shadow-soft);
    }

    .status-tile b {
        display: block;
        color: var(--sf-text);
        font-size: 1.5rem;
        line-height: 1;
        letter-spacing: -0.8px;
    }

    .status-tile span {
        display: block;
        margin-top: 7px;
        color: var(--sf-muted);
        font-size: 0.82rem;
        font-weight: 800;
    }

    .status-tile.critical {
        border-color: rgba(255, 59, 48, 0.25);
        background: linear-gradient(145deg, rgba(255,255,255,0.94), rgba(255,241,240,0.90));
    }

    .status-tile.warning {
        border-color: rgba(255, 159, 10, 0.25);
        background: linear-gradient(145deg, rgba(255,255,255,0.94), rgba(255,248,235,0.90));
    }

    .critical-banner {
        margin: 14px 0 4px;
        padding: 16px 18px;
        border-radius: 24px;
        color: #7f1d1d;
        background: linear-gradient(135deg, rgba(255,235,235,0.96), rgba(255,247,237,0.92));
        border: 1px solid rgba(255,59,48,0.24);
        box-shadow: 0 14px 34px rgba(255,59,48,0.10);
        font-weight: 800;
    }

    .alert-card {
        border-radius: 22px;
        padding: 16px 18px;
        margin-bottom: 12px;
        border: 1px solid var(--sf-border);
        background: rgba(255,255,255,0.78);
        box-shadow: 0 8px 22px rgba(0,0,0,0.05);
    }

    .alert-card.alert-critical {
        border-color: rgba(255, 59, 48, 0.28);
        background: linear-gradient(145deg, rgba(255,255,255,0.96), rgba(255,241,240,0.92));
    }

    .alert-card.alert-warning {
        border-color: rgba(255, 159, 10, 0.28);
        background: linear-gradient(145deg, rgba(255,255,255,0.96), rgba(255,248,235,0.92));
    }

    .alert-title {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 7px;
        color: var(--sf-text);
        font-weight: 900;
    }

    .alert-meta {
        margin-top: 10px;
        color: var(--sf-muted);
        font-size: 0.82rem;
        font-weight: 750;
    }

    .severity-chip {
        display: inline-block;
        padding: 5px 9px;
        border-radius: 999px;
        font-size: 0.72rem;
        letter-spacing: 0.2px;
        font-weight: 900;
    }

    .severity-critical {
        color: #b42318;
        background: rgba(255,59,48,0.14);
        border: 1px solid rgba(255,59,48,0.20);
    }

    .severity-warning {
        color: #a36200;
        background: rgba(255,159,10,0.16);
        border: 1px solid rgba(255,159,10,0.22);
    }

    .severity-info {
        color: #005ecb;
        background: rgba(0,122,255,0.12);
        border: 1px solid rgba(0,122,255,0.18);
    }

    .subtle {
        color: var(--sf-muted);
        font-size: 0.95rem;
    }

    .room-card {
        background: rgba(255,255,255,0.72);
        border-radius: 22px;
        padding: 16px 18px;
        color: #1d1d1f;
        border: 1px solid var(--sf-border);
    }

    .node-card {
        background: linear-gradient(145deg, rgba(255,255,255,0.94) 0%, rgba(238,246,255,0.86) 100%);
        border: 1px solid rgba(0,122,255,0.18);
        color: var(--sf-text);
    }

    .status-pill {
        display: inline-block;
        padding: 7px 13px;
        border-radius: 999px;
        font-size: 0.8rem;
        font-weight: 800;
        letter-spacing: 0.1px;
    }

    .status-ok {
        background: rgba(52, 199, 89, 0.14);
        color: #168a3d;
        border: 1px solid rgba(52,199,89,0.18);
    }

    .status-warn {
        background: rgba(255, 159, 10, 0.16);
        color: #a36200;
        border: 1px solid rgba(255,159,10,0.18);
    }

    .status-bad {
        background: rgba(255, 59, 48, 0.14);
        color: #c92a22;
        border: 1px solid rgba(255,59,48,0.18);
    }

    section[data-testid="stSidebar"] {
        background: rgba(255,255,255,0.72);
        border-right: 1px solid rgba(0,0,0,0.08);
        backdrop-filter: blur(26px);
    }

    section[data-testid="stSidebar"] * {
        color: var(--sf-text);
    }

    .stButton > button {
        border-radius: 999px;
        font-weight: 800;
        min-height: 44px;
        background: linear-gradient(180deg, #0a84ff 0%, #007aff 100%);
        color: white !important;
        border: 1px solid rgba(0,122,255,0.28);
        box-shadow: 0 8px 20px rgba(0,122,255,0.20);
        transition: all 0.16s ease;
    }

    .stButton > button:hover {
        transform: translateY(-1px);
        background: linear-gradient(180deg, #2795ff 0%, #007aff 100%);
        border: 1px solid rgba(0,122,255,0.45);
    }

    .stDownloadButton > button,
    .stLinkButton > a {
        border-radius: 999px !important;
        font-weight: 800 !important;
        min-height: 42px !important;
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background: rgba(255,255,255,0.64);
        padding: 8px;
        border-radius: 18px;
        border: 1px solid rgba(0,0,0,0.06);
        box-shadow: 0 6px 18px rgba(0,0,0,0.04);
    }

    .stTabs [data-baseweb="tab"] {
        background-color: transparent;
        color: #3a3a3c;
        border-radius: 14px;
        padding: 10px 16px;
        font-weight: 800;
    }

    .stTabs [aria-selected="true"] {
        background-color: white !important;
        color: #007aff !important;
        box-shadow: 0 5px 14px rgba(0,0,0,0.08);
    }

    div[data-testid="stMetric"] {
        background: rgba(255,255,255,0.70);
        border: 1px solid rgba(0,0,0,0.06);
        border-radius: 20px;
        padding: 12px 14px;
        box-shadow: 0 5px 16px rgba(0,0,0,0.04);
    }

    div[data-testid="stMetricLabel"] {
        color: var(--sf-muted);
    }

    div[data-testid="stMetricValue"] {
        color: var(--sf-text);
        font-weight: 800;
    }

    .stAlert {
        border-radius: 22px;
    }

    img {
        border-radius: 22px;
        box-shadow: 0 12px 34px rgba(0,0,0,0.08);
    }

    pre, code {
        border-radius: 18px !important;
    }

    @media (max-width: 980px) {
        .status-strip {
            grid-template-columns: repeat(2, minmax(0, 1fr));
        }

        .hero h1 {
            font-size: 2.2rem;
        }
    }

    @media (max-width: 640px) {
        .status-strip {
            grid-template-columns: 1fr;
        }
    }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<style>
    :root {
        --sf-page: #f7f9fc;
        --sf-panel: rgba(255,255,255,0.88);
        --sf-ink: #0f172a;
        --sf-soft: #64748b;
        --sf-line: rgba(15,23,42,0.08);
        --sf-brand: #0a84ff;
        --sf-brand-2: #2563eb;
        --sf-ok: #16a34a;
        --sf-warn: #f59e0b;
        --sf-danger: #dc2626;
        --sf-shadow-lg: 0 28px 80px rgba(15,23,42,0.12);
        --sf-shadow-md: 0 16px 42px rgba(15,23,42,0.09);
    }

    @keyframes sfFadeUp {
        from { opacity: 0; transform: translateY(14px); }
        to { opacity: 1; transform: translateY(0); }
    }

    @keyframes sfGlow {
        0%, 100% { box-shadow: 0 0 0 0 rgba(10,132,255,0.18); }
        50% { box-shadow: 0 0 0 10px rgba(10,132,255,0); }
    }

    @keyframes sfScan {
        0% { transform: translateX(-120%); opacity: 0; }
        20% { opacity: 1; }
        100% { transform: translateX(120%); opacity: 0; }
    }

    .stApp {
        background:
            linear-gradient(115deg, rgba(10,132,255,0.08), transparent 28%),
            linear-gradient(250deg, rgba(22,163,74,0.06), transparent 26%),
            linear-gradient(180deg, #fbfdff 0%, #f7f9fc 48%, #eef3f9 100%);
    }

    header[data-testid="stHeader"] {
        background: rgba(255,255,255,0.58);
        backdrop-filter: blur(18px);
        border-bottom: 1px solid rgba(15,23,42,0.06);
    }

    .block-container {
        max-width: 1500px;
        padding-top: 1.35rem;
        padding-left: 2rem;
        padding-right: 2rem;
    }

    .hero {
        display: grid;
        grid-template-columns: minmax(0, 1.18fr) minmax(300px, 0.82fr);
        gap: 28px;
        align-items: stretch;
        padding: 28px;
        margin-bottom: 16px;
        border-radius: 28px;
        background:
            linear-gradient(135deg, rgba(255,255,255,0.96), rgba(244,248,255,0.88)),
            radial-gradient(circle at 88% 18%, rgba(10,132,255,0.18), transparent 35%);
        border: 1px solid rgba(255,255,255,0.92);
        box-shadow: var(--sf-shadow-lg);
        animation: sfFadeUp .55s ease both;
    }

    .hero::after {
        display: none;
    }

    .hero-kicker {
        display: inline-flex;
        width: fit-content;
        align-items: center;
        gap: 8px;
        padding: 7px 11px;
        border-radius: 999px;
        color: #0f3f8c;
        background: rgba(10,132,255,0.10);
        border: 1px solid rgba(10,132,255,0.14);
        font-size: 0.78rem;
        font-weight: 900;
        letter-spacing: 0.2px;
        text-transform: uppercase;
    }

    .live-dot {
        width: 8px;
        height: 8px;
        border-radius: 999px;
        background: var(--sf-ok);
        animation: sfGlow 2.4s ease infinite;
    }

    .hero h1 {
        margin-top: 18px;
        max-width: 900px;
        font-size: clamp(2.35rem, 4vw, 4.8rem);
        letter-spacing: -2.4px;
        color: var(--sf-ink);
    }

    .hero p {
        max-width: 760px;
        color: var(--sf-soft);
        font-size: 1.02rem;
        line-height: 1.6;
    }

    .hero .workflow-pill {
        background: rgba(255,255,255,0.78);
        border: 1px solid rgba(15,23,42,0.08);
        box-shadow: 0 10px 24px rgba(15,23,42,0.07);
    }

    .hero-visual {
        position: relative;
        min-height: 250px;
        overflow: hidden;
        border-radius: 24px;
        border: 1px solid rgba(15,23,42,0.08);
        background:
            linear-gradient(135deg, rgba(15,23,42,0.94), rgba(30,64,175,0.86)),
            radial-gradient(circle at 80% 0%, rgba(96,165,250,0.38), transparent 38%);
        color: white;
        padding: 22px;
    }

    .hero-visual::before {
        content: "";
        position: absolute;
        inset: 18px;
        border-radius: 18px;
        border: 1px solid rgba(255,255,255,0.12);
        background:
            linear-gradient(rgba(255,255,255,0.06) 1px, transparent 1px),
            linear-gradient(90deg, rgba(255,255,255,0.06) 1px, transparent 1px);
        background-size: 34px 34px;
        opacity: 0.8;
    }

    .hero-visual::after {
        content: "";
        position: absolute;
        top: 36px;
        bottom: 36px;
        width: 120px;
        background: linear-gradient(90deg, transparent, rgba(255,255,255,0.17), transparent);
        animation: sfScan 4.4s ease-in-out infinite;
    }

    .visual-node {
        position: absolute;
        width: 74px;
        height: 74px;
        border-radius: 22px;
        background: rgba(255,255,255,0.13);
        border: 1px solid rgba(255,255,255,0.18);
        backdrop-filter: blur(12px);
        display: grid;
        place-items: center;
        font-weight: 950;
        z-index: 2;
    }

    .visual-node.main {
        right: 38px;
        top: 38px;
        background: rgba(10,132,255,0.40);
    }

    .visual-node.secondary {
        left: 38px;
        bottom: 42px;
    }

    .visual-stat {
        position: absolute;
        left: 24px;
        top: 24px;
        z-index: 2;
        color: rgba(255,255,255,0.74);
        font-size: 0.8rem;
        font-weight: 800;
    }

    .visual-stat b {
        display: block;
        margin-top: 7px;
        color: #fff;
        font-size: 2.25rem;
        letter-spacing: -1px;
    }

    .command-shell {
        padding: 18px;
        border-radius: 28px;
        background: rgba(255,255,255,0.82);
        border: 1px solid rgba(255,255,255,0.92);
        box-shadow: var(--sf-shadow-md);
        backdrop-filter: blur(22px);
        margin: 12px 0 18px;
        animation: sfFadeUp .65s ease both;
    }

    .command-head {
        display: flex;
        justify-content: space-between;
        gap: 12px;
        align-items: center;
        margin-bottom: 14px;
    }

    .command-title {
        font-size: 1.03rem;
        font-weight: 950;
        color: var(--sf-ink);
        letter-spacing: -0.3px;
    }

    .command-caption {
        color: var(--sf-soft);
        font-size: 0.84rem;
        font-weight: 750;
    }

    .command-section {
        min-height: 100%;
        padding: 15px;
        border-radius: 22px;
        border: 1px solid rgba(15,23,42,0.07);
        background: linear-gradient(180deg, rgba(255,255,255,0.78), rgba(248,251,255,0.72));
    }

    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 22px;
        border: 1px solid rgba(15,23,42,0.07);
        background: linear-gradient(180deg, rgba(255,255,255,0.82), rgba(248,251,255,0.74));
        box-shadow: 0 12px 28px rgba(15,23,42,0.06);
        transition: transform .18s ease, box-shadow .18s ease;
    }

    div[data-testid="stVerticalBlockBorderWrapper"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 20px 42px rgba(15,23,42,0.10);
    }

    .command-section-title {
        margin-bottom: 10px;
        color: var(--sf-ink);
        font-weight: 950;
        font-size: 0.9rem;
        letter-spacing: -0.1px;
    }

    .stButton > button {
        min-height: 42px;
        border-radius: 13px;
        color: #fff !important;
        background: linear-gradient(180deg, #0a84ff 0%, #006ee6 100%);
        border: 1px solid rgba(10,132,255,0.32);
        box-shadow: 0 9px 20px rgba(10,132,255,0.20);
        transition: transform .18s ease, box-shadow .18s ease, border .18s ease;
    }

    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 16px 28px rgba(10,132,255,0.24);
    }

    .stButton > button:active {
        transform: translateY(0) scale(.99);
    }

    .stFileUploader section {
        border-radius: 18px;
        border: 1px dashed rgba(10,132,255,0.28);
        background: rgba(10,132,255,0.035);
    }

    .card, .export-card, .room-card, .node-card, div[data-testid="stMetric"], .status-tile {
        animation: sfFadeUp .55s ease both;
        transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease;
    }

    .card:hover, .export-card:hover, .room-card:hover, .node-card:hover, .status-tile:hover {
        transform: translateY(-3px);
        box-shadow: 0 22px 52px rgba(15,23,42,0.11);
    }

    .card {
        min-height: 118px;
        padding: 22px;
        border-radius: 24px;
    }

    .metric-value {
        font-size: clamp(1.9rem, 2.6vw, 2.75rem);
    }

    .status-strip {
        grid-template-columns: repeat(4, minmax(0, 1fr));
        margin-top: 6px;
        margin-bottom: 16px;
    }

    .status-tile {
        border-radius: 20px;
        padding: 16px 18px;
    }

    .stTabs [data-baseweb="tab-list"] {
        position: sticky;
        top: 58px;
        z-index: 20;
        border-radius: 18px;
        background: rgba(255,255,255,0.84);
        backdrop-filter: blur(20px);
    }

    .stTabs [data-baseweb="tab"] {
        min-height: 42px;
        border-radius: 13px;
    }

    .stTabs [aria-selected="true"] {
        color: white !important;
        background: linear-gradient(180deg, #0a84ff, #006ee6) !important;
        box-shadow: 0 10px 24px rgba(10,132,255,0.20);
    }

    section[data-testid="stSidebar"] {
        background:
            linear-gradient(180deg, rgba(255,255,255,0.92), rgba(241,246,252,0.92));
        border-right: 1px solid rgba(15,23,42,0.08);
    }

    .sidebar-status {
        padding: 14px;
        border-radius: 18px;
        background: rgba(255,255,255,0.74);
        border: 1px solid rgba(15,23,42,0.08);
        box-shadow: 0 10px 24px rgba(15,23,42,0.06);
        margin: 10px 0 18px;
    }

    .sidebar-status b {
        display: block;
        color: var(--sf-ink);
        font-size: 0.86rem;
        margin-bottom: 6px;
    }

    .sidebar-status span {
        color: var(--sf-soft);
        font-size: 0.76rem;
        overflow-wrap: anywhere;
        font-weight: 750;
    }

    @media (max-width: 1100px) {
        .hero {
            grid-template-columns: 1fr;
        }

        .hero-visual {
            min-height: 210px;
        }
    }
</style>
""", unsafe_allow_html=True)


def safe_get_json(url, default=None):
    try:
        r = requests.get(url, timeout=20)
        if r.headers.get("content-type", "").startswith("application/json"):
            data = r.json()
        else:
            data = {"detail": r.text}
        if not r.ok:
            return data
        return data
    except Exception as e:
        return {"detail": str(e)} if default is None else default


def safe_post_json(url, payload=None, files=None, default=None):
    try:
        if files is not None:
            r = requests.post(url, files=files, timeout=120)
        else:
            r = requests.post(url, json=payload, timeout=120)

        if r.headers.get("content-type", "").startswith("application/json"):
            data = r.json()
        else:
            data = {"detail": r.text}

        if not r.ok:
            return data
        return data
    except Exception as e:
        return {"detail": str(e)} if default is None else default


def upload_cad(file_obj):
    files = {
        "file": (file_obj.name, file_obj.getvalue(), file_obj.type or "application/octet-stream")
    }
    return safe_post_json(f"{API_URL}/cad/upload", files=files, default={})


def extract_rooms():
    return safe_post_json(f"{API_URL}/cad/extract-rooms", default={})


def plan_nodes():
    return safe_post_json(f"{API_URL}/cad/plan-nodes", default={})


def render_plan():
    return safe_post_json(f"{API_URL}/cad/render-plan", default={})


def render_heatmap():
    return safe_post_json(f"{API_URL}/cad/render-heatmap", default={})


def render_extracted_rooms_image():
    return safe_post_json(f"{API_URL}/cad/render-extract-rooms", default={})


def apply_plan_to_simulation():
    return safe_post_json(f"{API_URL}/simulation/apply-cad-plan", default={})


def next_step():
    return safe_post_json(f"{API_URL}/simulation/step", default={})


def reset_simulation():
    return safe_post_json(f"{API_URL}/simulation/reset", default={})


def full_project_reset():
    return safe_post_json(f"{API_URL}/cad/reset", default={})


def get_latest_cad():
    return safe_get_json(f"{API_URL}/cad/latest", {"cad": None}).get("cad")


def get_latest_rooms():
    data = safe_get_json(f"{API_URL}/cad/latest-rooms", {"rooms_result": None})
    return data.get("rooms_result")


def get_latest_plan():
    data = safe_get_json(f"{API_URL}/cad/latest-plan", {"plan_result": None})
    return data.get("plan_result")


def get_ai_summary():
    return safe_get_json(f"{API_URL}/ai/summary", {"health_summary": {}, "recommendations": []})


def get_sim_state():
    return safe_get_json(f"{API_URL}/simulation/state", {
        "simulation_source": "unknown",
        "building": None,
        "node_plan": [],
        "node_runtime": [],
        "clients": [],
        "events": [],
        "controller_state": {"decisions": []},
        "security_state": {"alerts": [], "access_matrix": []},
        "ai_output": {"health_summary": {}, "recommendations": []},
        "planning_summary": {}
    })


def get_rendered_url(file_name):
    return f"{API_URL}/cad/rendered/{file_name}"


def _html(value) -> str:
    if value is None:
        return ""
    return html.escape(str(value))


def _alert_severity(alert) -> str:
    if not isinstance(alert, dict):
        return "info"
    severity = str(alert.get("severity", "info")).lower()
    return severity if severity in ["critical", "warning", "info"] else "info"


def _count_alerts_by_severity(alerts):
    counts = {"critical": 0, "warning": 0, "info": 0}

    for alert in alerts or []:
        severity = _alert_severity(alert)
        counts[severity] = counts.get(severity, 0) + 1

    return counts


def _render_alert_card(alert):
    if not isinstance(alert, dict):
        return

    severity = _alert_severity(alert)
    css_class = f"alert-{severity}"
    chip_class = f"severity-{severity}"
    title = _html(alert.get("title", "Untitled alert"))
    description = _html(alert.get("description", ""))
    category = _html(alert.get("category", "unknown"))
    node_id = _html(alert.get("node_id", "-"))
    client_id = _html(alert.get("client_id", "-"))
    recommendation = _html(alert.get("recommendation", ""))

    recommendation_html = ""
    if recommendation:
        recommendation_html = f"<div class='alert-meta'>Recommendation: {recommendation}</div>"

    st.markdown(f"""
    <div class="alert-card {css_class}">
        <div class="alert-title">
            <span class="severity-chip {chip_class}">{severity.upper()}</span>
            <span>{title}</span>
        </div>
        <div class="subtle">{description}</div>
        <div class="alert-meta">
            Category: {category} &nbsp; | &nbsp; Node: {node_id} &nbsp; | &nbsp; Client: {client_id}
        </div>
        {recommendation_html}
    </div>
    """, unsafe_allow_html=True)




def _dashboard_plan_nodes(plan):
    if not isinstance(plan, dict):
        return []

    for key in ["node_plan", "nodes", "planned_nodes", "node_plans"]:
        value = plan.get(key)
        if isinstance(value, list):
            return value

    result = plan.get("result")
    if isinstance(result, dict):
        for key in ["node_plan", "nodes", "planned_nodes", "node_plans"]:
            value = result.get(key)
            if isinstance(value, list):
                return value

    data = plan.get("data")
    if isinstance(data, dict):
        for key in ["node_plan", "nodes", "planned_nodes", "node_plans"]:
            value = data.get(key)
            if isinstance(value, list):
                return value

    return []


def _dashboard_summary_value(summary, keys, default=0):
    if not isinstance(summary, dict):
        return default

    for key in keys:
        value = summary.get(key)
        if value is not None:
            return value

    return default


def _dashboard_metric_number(value, default=0):
    try:
        if value is None:
            return default
        number = float(value)
        if number.is_integer():
            return int(number)
        return round(number, 2)
    except Exception:
        return value if value not in [None, ""] else default


def _dashboard_table_safe_rows(rows):
    safe_rows = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        safe_row = {}
        for key, value in row.items():
            if value is None:
                safe_row[key] = "-"
            elif isinstance(value, (dict, list, tuple)):
                safe_row[key] = json.dumps(value, ensure_ascii=False)
            else:
                safe_row[key] = str(value)
        safe_rows.append(safe_row)
    return safe_rows


def _dashboard_build_client_profile_rows(clients):
    rows = []
    for client in clients or []:
        if not isinstance(client, dict):
            continue
        rows.append({
            "Client": client.get("name", "-"),
            "Type": client.get("client_type", client.get("role", "-")),
            "Role": client.get("role", "-"),
            "Traffic": client.get("traffic_profile", "-"),
            "SSID": client.get("ssid", "-"),
            "VLAN": client.get("vlan_id", "-"),
            "Priority": client.get("qos_priority", "-"),
            "Required Mbps": client.get("required_bandwidth_mbps", "-"),
            "Max Latency ms": client.get("max_latency_ms", "-"),
            "Loss Tolerance %": client.get("packet_loss_tolerance_pct", "-"),
            "Mobility": client.get("mobility_pattern", "-"),
            "Speed m/s": client.get("speed", "-"),
            "Connected Node": client.get("connected_node", "-"),
            "Throughput Mbps": client.get("current_throughput_mbps", "-"),
            "Latency ms": client.get("current_latency_ms", "-"),
            "Loss %": client.get("current_packet_loss_pct", "-"),
            "QoS State": client.get("qos_state", "not_evaluated"),
            "Roaming": client.get("roaming_count", 0),
        })
    return rows


def _dashboard_qos_badge(qos_state):
    state = str(qos_state or "not_evaluated").lower()
    if state == "ok":
        return '<span class="status-pill status-ok">QoS OK</span>'
    if state == "warning":
        return '<span class="status-pill status-warn">QoS Warning</span>'
    if state == "violated":
        return '<span class="status-pill status-bad">QoS Violated</span>'
    return '<span class="status-pill status-warn">QoS Pending</span>'

def get_excel_export_url():
    return f"{API_URL}/export/excel"


def get_pdf_export_url():
    return f"{API_URL}/export/pdf"


def node_color(node):
    status = node.get("status", "active")
    if status in ["down", "offline"]:
        return "red"
    if status == "degraded":
        return "orange"
    return "green"


def role_color(role):
    if role == "management":
        return "purple"
    if role == "guest":
        return "brown"
    return "deepskyblue"


def render_status_badge(text):
    t = str(text).lower()
    if t in ["stable", "active", "ok", "healthy", "online"]:
        css = "status-ok"
    elif t in ["warning", "degraded", "medium"]:
        css = "status-warn"
    else:
        css = "status-bad"
    st.markdown(f'<span class="status-pill {css}">{text}</span>', unsafe_allow_html=True)


def render_interactive_plan(building_data, display_sim_state):
    """
    Interactive Simulation Overlay.

    This view is allowed to show nodes and clients.
    It uses the real CAD walls so it visually matches the AI Planning render,
    but it is separate from the Extracted Rooms view.
    """
    if not building_data:
        st.info("No building model available to draw.")
        return

    rooms = building_data.get("rooms", []) or []
    walls = building_data.get("walls", []) or []
    bounds = building_data.get("bounds", {}) or {}
    clients = display_sim_state.get("clients", []) or []

    if not rooms and not walls:
        st.info("No CAD building data available to draw.")
        return

    min_x = float(bounds.get("min_x", min([r.get("x", 0.0) for r in rooms], default=0.0)))
    min_y = float(bounds.get("min_y", min([r.get("y", 0.0) for r in rooms], default=0.0)))
    max_x = float(bounds.get("max_x", max([r.get("x", 0.0) + r.get("width", 0.0) for r in rooms], default=10.0)))
    max_y = float(bounds.get("max_y", max([r.get("y", 0.0) + r.get("height", 0.0) for r in rooms], default=10.0)))

    width = max(max_x - min_x, 1.0)
    height = max(max_y - min_y, 1.0)
    aspect = width / max(height, 1e-9)

    fig_w = 13.2
    fig_h = max(5.8, min(9.5, fig_w / max(aspect, 0.55)))

    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.set_facecolor("white")

    _draw_dashboard_room_fills(ax, rooms)
    _draw_dashboard_cad_walls(ax, walls)
    _draw_dashboard_room_outlines_and_labels(ax, rooms)
    _draw_dashboard_planned_nodes(ax, display_sim_state)
    _draw_dashboard_clients(ax, clients)

    pad_x = max(width * 0.025, 0.25)
    pad_y = max(height * 0.025, 0.25)

    ax.set_xlim(min_x - pad_x, max_x + pad_x)
    ax.set_ylim(min_y - pad_y, max_y + pad_y)
    ax.set_aspect("equal", adjustable="box")
    ax.set_title("Interactive CAD Simulation Overlay", fontsize=9)
    ax.grid(True, linewidth=0.25, alpha=0.18)

    st.pyplot(fig, clear_figure=True)


def render_extracted_rooms_overlay(building_data):
    """
    Extracted Rooms preview.

    Important rule:
    This view must never draw nodes, beam arcs, clients, heatmap, or planning output.
    It is only for validating extracted rooms, corridors, labels, and CAD walls.
    """
    if not building_data:
        st.info("No extracted room model available to draw.")
        return

    rooms = building_data.get("rooms", []) or []
    walls = building_data.get("walls", []) or []
    bounds = building_data.get("bounds", {}) or {}

    if not rooms and not walls:
        st.info("No extracted rooms available to draw.")
        return

    min_x = float(bounds.get("min_x", min([r.get("x", 0.0) for r in rooms], default=0.0)))
    min_y = float(bounds.get("min_y", min([r.get("y", 0.0) for r in rooms], default=0.0)))
    max_x = float(bounds.get("max_x", max([r.get("x", 0.0) + r.get("width", 0.0) for r in rooms], default=10.0)))
    max_y = float(bounds.get("max_y", max([r.get("y", 0.0) + r.get("height", 0.0) for r in rooms], default=10.0)))

    width = max(max_x - min_x, 1.0)
    height = max(max_y - min_y, 1.0)
    aspect = width / max(height, 1e-9)

    fig_w = 13.2
    fig_h = max(5.8, min(9.5, fig_w / max(aspect, 0.55)))

    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.set_facecolor("white")

    _draw_dashboard_room_fills(ax, rooms)
    _draw_dashboard_cad_walls(ax, walls)
    _draw_dashboard_room_outlines_and_labels(ax, rooms)

    pad_x = max(width * 0.025, 0.25)
    pad_y = max(height * 0.025, 0.25)

    ax.set_xlim(min_x - pad_x, max_x + pad_x)
    ax.set_ylim(min_y - pad_y, max_y + pad_y)
    ax.set_aspect("equal", adjustable="box")
    ax.set_title("Extracted Rooms - CAD Wall Overlay", fontsize=9)
    ax.grid(True, linewidth=0.25, alpha=0.18)

    st.pyplot(fig, clear_figure=True)


def _draw_dashboard_room_fills(ax, rooms):
    for room in rooms:
        room_type = str(room.get("room_type", "unknown")).lower()
        pts = _dashboard_polygon_points(room.get("polygon", []) or [])

        alpha = 0.075
        if room_type == "corridor":
            alpha = 0.13
        elif room_type in ["bathroom", "service", "storage"]:
            alpha = 0.095

        if len(pts) >= 3:
            patch = patches.Polygon(
                pts,
                closed=True,
                facecolor=_dashboard_room_fill(room_type),
                edgecolor="none",
                alpha=alpha,
                zorder=2,
            )
            ax.add_patch(patch)
        else:
            x = float(room.get("x", 0.0))
            y = float(room.get("y", 0.0))
            w = float(room.get("width", 0.0))
            h = float(room.get("height", 0.0))
            rect = patches.Rectangle(
                (x, y),
                w,
                h,
                facecolor=_dashboard_room_fill(room_type),
                edgecolor="none",
                alpha=alpha,
                zorder=2,
            )
            ax.add_patch(rect)


def _draw_dashboard_cad_walls(ax, walls):
    for wall in walls:
        try:
            x1 = float(wall.get("x1", 0.0))
            y1 = float(wall.get("y1", 0.0))
            x2 = float(wall.get("x2", 0.0))
            y2 = float(wall.get("y2", 0.0))
        except Exception:
            continue

        if ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5 < 0.01:
            continue

        layer = str(wall.get("layer", "")).lower()
        lw = 1.45
        if "healed" in layer:
            lw = 1.0
        if "door" in layer or "window" in layer:
            lw = 0.85

        ax.plot(
            [x1, x2],
            [y1, y2],
            color="#111111",
            linewidth=lw,
            solid_capstyle="round",
            zorder=30,
        )


def _draw_dashboard_room_outlines_and_labels(ax, rooms):
    placed_labels = []

    for room in sorted(rooms, key=lambda r: float(r.get("area", 0.0) or 0.0), reverse=True):
        room_type = str(room.get("room_type", "unknown")).lower()
        pts = _dashboard_polygon_points(room.get("polygon", []) or [])

        if len(pts) >= 3:
            outline = patches.Polygon(
                pts,
                closed=True,
                facecolor="none",
                edgecolor=_dashboard_room_edge(room_type),
                linewidth=0.65,
                alpha=0.42,
                zorder=35,
            )
            ax.add_patch(outline)

        cx = float(room.get("center_x", room.get("x", 0.0)) or 0.0)
        cy = float(room.get("center_y", room.get("y", 0.0)) or 0.0)

        if _dashboard_label_collides(cx, cy, placed_labels, threshold=0.34):
            continue

        placed_labels.append((cx, cy))

        name = str(room.get("label_text") or room.get("name") or "room")
        zone = str(room.get("zone", "unknown"))
        expected = room.get("expected_clients", 0)
        label = _dashboard_short_room_label(name, room_type, zone, expected)

        ax.text(
            cx,
            cy,
            label,
            ha="center",
            va="center",
            fontsize=5.6,
            color="#202020",
            zorder=55,
            bbox=dict(
                boxstyle="round,pad=0.12",
                facecolor="white",
                edgecolor="none",
                alpha=0.70,
            ),
        )


def _draw_dashboard_planned_nodes(ax, sim_state):
    planned_nodes = _dashboard_get_planned_nodes(sim_state)

    for idx, node in enumerate(planned_nodes, start=1):
        x = _dashboard_node_x(node)
        y = _dashboard_node_y(node)

        if x is None or y is None:
            continue

        node_id = node.get("node_id") or node.get("id") or idx
        display_id = _dashboard_short_node_id(node_id, idx)
        room_id = node.get("room_id", "")
        tx_power = node.get("tx_power_dbm", node.get("tx_power", ""))

        direction = float(
            node.get(
                "beam_direction_deg",
                node.get(
                    "antenna_direction_deg",
                    node.get("direction_deg", 0.0),
                ),
            )
            or 0.0
        )
        beamwidth = float(
            node.get(
                "beamwidth_deg",
                node.get(
                    "beam_width_deg",
                    node.get("antenna_beamwidth", 80.0),
                ),
            )
            or 80.0
        )

        ax.scatter(
            [x],
            [y],
            s=96,
            marker="o",
            color="#0B3D91",
            edgecolors="white",
            linewidths=1.25,
            zorder=80,
        )
        ax.text(
            x,
            y,
            "N",
            color="white",
            fontsize=6.2,
            ha="center",
            va="center",
            fontweight="bold",
            zorder=85,
        )

        _dashboard_draw_beam_arcs(ax, x, y, direction, beamwidth)

        label = f"Node {display_id}"
        if room_id != "":
            label += f"\nR{room_id}"
        if tx_power != "":
            label += f"\n{tx_power} dBm"

        ax.text(
            x + 0.12,
            y + 0.12,
            label,
            fontsize=5.0,
            color="#0B1F3A",
            ha="left",
            va="bottom",
            zorder=86,
            bbox=dict(
                boxstyle="round,pad=0.12",
                facecolor="white",
                edgecolor="#C8D3E5",
                alpha=0.84,
            ),
        )


def _draw_dashboard_clients(ax, clients):
    for client in clients:
        try:
            cx = float(client["x"])
            cy = float(client["y"])
        except Exception:
            continue

        ax.scatter(
            [cx],
            [cy],
            marker="o",
            s=36,
            color=role_color(client.get("role", "staff")),
            edgecolors="white",
            linewidths=0.6,
            alpha=0.70,
            zorder=70,
        )


def _dashboard_get_planned_nodes(sim_state):
    nodes = sim_state.get("node_plan", []) or []
    if nodes:
        return nodes

    try:
        if latest_plan:
            for key in ["node_plan", "nodes", "planned_nodes", "node_plans"]:
                value = latest_plan.get(key)
                if isinstance(value, list) and value:
                    return value
    except Exception:
        pass

    runtime_nodes = sim_state.get("node_runtime", []) or []
    if runtime_nodes:
        return runtime_nodes

    return []


def _dashboard_polygon_points(polygon):
    pts = []
    for p in polygon:
        try:
            if isinstance(p, dict):
                pts.append((float(p.get("x", 0.0)), float(p.get("y", 0.0))))
            else:
                x = getattr(p, "x", None)
                y = getattr(p, "y", None)
                if x is not None and y is not None:
                    pts.append((float(x), float(y)))
        except Exception:
            continue
    return pts


def _dashboard_node_x(node):
    for key in ["x", "node_x", "placement_x", "center_x"]:
        if key in node:
            try:
                return float(node[key])
            except Exception:
                pass

    pos = node.get("position")
    if isinstance(pos, dict) and "x" in pos:
        try:
            return float(pos["x"])
        except Exception:
            pass

    placement = node.get("placement")
    if isinstance(placement, dict) and "x" in placement:
        try:
            return float(placement["x"])
        except Exception:
            pass

    return None


def _dashboard_node_y(node):
    for key in ["y", "node_y", "placement_y", "center_y"]:
        if key in node:
            try:
                return float(node[key])
            except Exception:
                pass

    pos = node.get("position")
    if isinstance(pos, dict) and "y" in pos:
        try:
            return float(pos["y"])
        except Exception:
            pass

    placement = node.get("placement")
    if isinstance(placement, dict) and "y" in placement:
        try:
            return float(placement["y"])
        except Exception:
            pass

    return None


def _dashboard_draw_beam_arcs(ax, x, y, direction, beamwidth):
    start = direction - beamwidth / 2.0
    end = direction + beamwidth / 2.0

    for radius, lw, alpha in [
        (0.55, 1.0, 0.85),
        (0.90, 1.0, 0.70),
        (1.25, 1.0, 0.55),
    ]:
        arc = patches.Arc(
            (x, y),
            width=radius * 2,
            height=radius * 2,
            angle=0,
            theta1=start,
            theta2=end,
            linewidth=lw,
            color="#1464C0",
            alpha=alpha,
            zorder=78,
        )
        ax.add_patch(arc)


def _dashboard_short_node_id(raw_id, idx):
    text = str(raw_id)
    if text.startswith("SF-N"):
        text = text.replace("SF-N", "N")
    if len(text) > 8:
        return f"N{idx}"
    if text.upper().startswith("N"):
        return text.upper()
    return f"N{text}"


def _dashboard_short_room_label(name, room_type, zone, expected):
    clean = str(name).replace("_", " ").strip()
    if len(clean) > 18:
        clean = clean[:16] + "..."
    return f"{clean}\n[{zone}]\n{room_type}\nExp {expected}"


def _dashboard_label_collides(x, y, placed, threshold):
    for px, py in placed:
        if ((x - px) ** 2 + (y - py) ** 2) ** 0.5 < threshold:
            return True
    return False


def _dashboard_room_fill(room_type):
    return {
        "corridor": "#F6C85F",
        "bathroom": "#9DD9D2",
        "service": "#BFC7D5",
        "storage": "#BFC7D5",
        "server_room": "#FF9F80",
        "meeting": "#90CAF9",
        "reception": "#C5E1A5",
        "open_area": "#D7BDE2",
        "office": "#A7C7E7",
        "kitchen": "#FAD7A0",
    }.get(room_type, "#D6EAF8")


def _dashboard_room_edge(room_type):
    return {
        "corridor": "#B7791F",
        "bathroom": "#278A86",
        "service": "#5D6D7E",
        "storage": "#5D6D7E",
        "server_room": "#C0392B",
        "meeting": "#2471A3",
        "reception": "#558B2F",
        "open_area": "#7D3C98",
        "office": "#2E86C1",
        "kitchen": "#B9770E",
    }.get(room_type, "#2874A6")

if "extracted_img" not in st.session_state:
    st.session_state.extracted_img = None

if "plan_img" not in st.session_state:
    st.session_state.plan_img = None

if "heatmap_img" not in st.session_state:
    st.session_state.heatmap_img = None

if "simulation_runtime_active" not in st.session_state:
    st.session_state.simulation_runtime_active = False

if "auto_simulation_enabled" not in st.session_state:
    st.session_state.auto_simulation_enabled = False

if "auto_simulation_interval" not in st.session_state:
    st.session_state.auto_simulation_interval = 1.0


def _reset_visual_runtime_state() -> None:
    st.session_state.extracted_img = None
    st.session_state.plan_img = None
    st.session_state.heatmap_img = None
    st.session_state.simulation_runtime_active = False
    st.session_state.auto_simulation_enabled = False


def _handle_upload_cad(file_obj) -> None:
    if file_obj is None:
        st.warning("Choose a DXF or DWG file first.")
        return

    result = upload_cad(file_obj)
    if result.get("cad"):
        _reset_visual_runtime_state()
        st.success("CAD file uploaded successfully.")
        st.rerun()

    st.error(result.get("detail", "CAD upload failed."))


def _handle_extract_rooms() -> None:
    result = extract_rooms()
    if result.get("result"):
        rendered = render_extracted_rooms_image()
        if rendered.get("image"):
            st.session_state.extracted_img = rendered["image"]
        else:
            st.session_state.extracted_img = {
                "file_name": "cad_extract_rooms.png",
                "url": "/cad/rendered/cad_extract_rooms.png",
                "kind": "extract_rooms",
            }
        st.session_state.simulation_runtime_active = False
        st.session_state.auto_simulation_enabled = False
        st.success("Rooms extracted.")
        st.rerun()

    st.error(result.get("detail", "Extraction failed."))


def _handle_ai_planning() -> None:
    result = plan_nodes()
    if result.get("result"):
        st.session_state.simulation_runtime_active = False
        st.session_state.auto_simulation_enabled = False
        st.success("AI planning completed.")
        st.rerun()

    st.error(result.get("detail", "Planning failed."))


def _handle_render_plan() -> None:
    result = render_plan()
    if result.get("image"):
        st.session_state.plan_img = result["image"]
        st.success("Plan image rendered.")
        st.rerun()

    st.error(result.get("detail", "Render failed."))


def _handle_render_heatmap() -> None:
    result = render_heatmap()
    if result.get("image"):
        st.session_state.heatmap_img = result["image"]
        st.success("Heatmap rendered.")
        st.rerun()

    st.error(result.get("detail", "Heatmap failed."))


def _handle_apply_plan_to_simulation() -> None:
    result = apply_plan_to_simulation()
    if result.get("state"):
        st.session_state.simulation_runtime_active = True
        st.success("CAD plan applied to simulation.")
        st.rerun()

    st.error(result.get("detail", "Apply failed."))


def _handle_next_simulation_step() -> None:
    if not st.session_state.get("simulation_runtime_active", False):
        st.warning("Apply the CAD plan before advancing runtime steps.")
        return

    result = next_step()
    if result.get("step") is not None:
        st.success("Simulation advanced.")
        st.rerun()

    st.error(result.get("detail", "Step failed."))


def _handle_reset_simulation() -> None:
    result = reset_simulation()
    if result.get("state"):
        st.session_state.simulation_runtime_active = False
        st.session_state.auto_simulation_enabled = False
        st.success("Simulation runtime reset.")
        st.rerun()

    st.error(result.get("detail", "Reset failed."))


def _handle_full_project_reset() -> None:
    result = full_project_reset()
    if result.get("state") or result.get("message"):
        _reset_visual_runtime_state()
        st.success("Full project reset completed.")
        st.rerun()

    st.error(result.get("detail", "Full reset failed."))


latest_cad = get_latest_cad()
latest_rooms = get_latest_rooms()
latest_plan = get_latest_plan()
ai_summary = get_ai_summary()
sim_state = get_sim_state()

building_data = sim_state.get("building")
if not building_data and latest_rooms:
    building_data = latest_rooms

plan_nodes_list = _dashboard_plan_nodes(latest_plan)
node_runtime_raw = sim_state.get("node_runtime", []) or []
simulation_is_active = bool(node_runtime_raw)
st.session_state.simulation_runtime_active = simulation_is_active
security_state = sim_state.get("security_state", {}) or {}

if simulation_is_active:
    node_runtime = node_runtime_raw
    clients = sim_state.get("clients", []) or []
    alerts = security_state.get("alerts", []) or []
    ai_output = sim_state.get("ai_output", ai_summary) or {}
else:
    node_runtime = []
    clients = []
    alerts = []
    ai_output = ai_summary or {"health_summary": {}, "recommendations": []}

health = ai_output.get("health_summary", {}) or {}
recommendations = ai_output.get("recommendations", []) or []
controller_state = sim_state.get("controller_state", {}) or {}
decisions = (controller_state.get("decisions", []) or []) if simulation_is_active else []
runtime_events = (sim_state.get("events", []) or []) if simulation_is_active else []
summary = latest_plan.get("summary", {}) if latest_plan else {}
alert_counts = _count_alerts_by_severity(alerts)
critical_alerts_count = alert_counts.get("critical", 0)
warning_alerts_count = alert_counts.get("warning", 0)
info_alerts_count = alert_counts.get("info", 0)

display_sim_state = dict(sim_state or {})
if not simulation_is_active:
    display_sim_state["clients"] = []
    display_sim_state["node_runtime"] = []
    display_sim_state["events"] = []
    display_sim_state["controller_state"] = {"decisions": []}
    display_sim_state["security_state"] = {"alerts": [], "access_matrix": []}

extracted_rooms_count = len(latest_rooms.get("rooms", [])) if latest_rooms else 0
suggested_nodes_count = 0
if latest_plan:
    suggested_nodes_count = latest_plan.get("nodes_count")
    if suggested_nodes_count is None:
        suggested_nodes_count = len(plan_nodes_list)
suggested_nodes_count = _dashboard_metric_number(suggested_nodes_count, 0)
placement = _dashboard_metric_number(
    _dashboard_summary_value(
        summary,
        ["placement_score", "coverage_score", "avg_coverage_percent", "overall_score", "nodes_planned"],
        0,
    ),
    0,
)

st.markdown("""
<style>
    section[data-testid="stSidebar"] {
        display: none !important;
    }

    .block-container {
        max-width: 1480px;
        padding: 1rem 1.3rem 1.8rem;
    }

    div[data-testid="stHorizontalBlock"] {
        gap: 1rem;
        flex-wrap: wrap;
        align-items: stretch;
    }

    div[data-testid="column"] {
        min-width: min(100%, 250px);
        flex: 1 1 250px !important;
    }

    .sf-topbar {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 16px;
        margin: 2px 0 16px;
        padding: 12px 14px;
        border: 1px solid rgba(15,23,42,0.08);
        border-radius: 22px;
        background: rgba(255,255,255,0.76);
        box-shadow: 0 12px 34px rgba(15,23,42,0.07);
        backdrop-filter: blur(22px);
    }

    .sf-brand {
        display: flex;
        align-items: center;
        gap: 11px;
        min-width: 0;
    }

    .sf-mark {
        width: 38px;
        height: 38px;
        border-radius: 13px;
        display: grid;
        place-items: center;
        color: white;
        font-weight: 950;
        background: linear-gradient(135deg, #0a84ff, #1d4ed8);
        box-shadow: 0 12px 24px rgba(37,99,235,0.25);
    }

    .sf-brand-title {
        color: #0f172a;
        font-size: 1rem;
        font-weight: 950;
        line-height: 1.05;
    }

    .sf-brand-sub {
        color: #64748b;
        font-size: 0.76rem;
        font-weight: 800;
        margin-top: 2px;
    }

    .sf-top-pills {
        display: flex;
        justify-content: flex-end;
        gap: 8px;
        flex-wrap: wrap;
    }

    .sf-pill {
        display: inline-flex;
        align-items: center;
        gap: 7px;
        padding: 8px 10px;
        border-radius: 999px;
        background: rgba(248,250,252,0.88);
        border: 1px solid rgba(15,23,42,0.08);
        color: #334155;
        font-size: 0.78rem;
        font-weight: 900;
        white-space: nowrap;
    }

    .sf-dot {
        width: 8px;
        height: 8px;
        border-radius: 99px;
        background: #16a34a;
        box-shadow: 0 0 0 6px rgba(22,163,74,0.10);
    }

    .sf-dot.warn {
        background: #f59e0b;
        box-shadow: 0 0 0 6px rgba(245,158,11,0.12);
    }

    .sf-hero-pro {
        position: relative;
        overflow: hidden;
        display: grid;
        grid-template-columns: minmax(0, 1.25fr) minmax(280px, 0.75fr);
        gap: 22px;
        align-items: stretch;
        padding: clamp(18px, 2.4vw, 28px);
        border-radius: 32px;
        background:
            linear-gradient(135deg, rgba(255,255,255,0.96), rgba(242,247,255,0.90)),
            radial-gradient(circle at 90% 10%, rgba(10,132,255,0.20), transparent 34%);
        border: 1px solid rgba(255,255,255,0.92);
        box-shadow: 0 28px 80px rgba(15,23,42,0.12);
        animation: sfFadeUp .42s ease both;
    }

    .sf-eyebrow {
        width: fit-content;
        padding: 8px 12px;
        border-radius: 999px;
        background: rgba(10,132,255,0.10);
        color: #0758bf;
        border: 1px solid rgba(10,132,255,0.16);
        font-size: 0.76rem;
        font-weight: 950;
        letter-spacing: 0.2px;
        text-transform: uppercase;
    }

    .sf-hero-pro h1 {
        margin: 13px 0 9px;
        color: #0f172a;
        max-width: 820px;
        font-size: clamp(2.35rem, 4.4vw, 4.55rem);
        line-height: 0.94;
        letter-spacing: -3px;
        font-weight: 950;
    }

    .sf-hero-pro p {
        max-width: 640px;
        color: #64748b;
        font-size: 0.98rem;
        line-height: 1.48;
        font-weight: 760;
    }

    .sf-mini-map {
        position: relative;
        min-height: 220px;
        border-radius: 26px;
        overflow: hidden;
        color: white;
        background:
            linear-gradient(135deg, rgba(15,23,42,0.96), rgba(30,64,175,0.88)),
            radial-gradient(circle at 82% 8%, rgba(96,165,250,0.35), transparent 35%);
        border: 1px solid rgba(15,23,42,0.10);
    }

    .sf-mini-map::before {
        content: "";
        position: absolute;
        inset: 18px;
        border-radius: 20px;
        border: 1px solid rgba(255,255,255,0.13);
        background:
            linear-gradient(rgba(255,255,255,0.06) 1px, transparent 1px),
            linear-gradient(90deg, rgba(255,255,255,0.06) 1px, transparent 1px);
        background-size: 32px 32px;
    }

    .sf-mini-map::after {
        content: "";
        position: absolute;
        top: 24px;
        bottom: 24px;
        width: 120px;
        background: linear-gradient(90deg, transparent, rgba(255,255,255,0.18), transparent);
        animation: sfScan 4.2s ease-in-out infinite;
    }

    .sf-map-stat {
        position: absolute;
        z-index: 2;
        left: 24px;
        top: 24px;
        color: rgba(255,255,255,0.72);
        font-size: 0.78rem;
        font-weight: 900;
    }

    .sf-map-stat b {
        display: block;
        margin-top: 6px;
        color: #fff;
        font-size: 2.6rem;
        letter-spacing: -1.4px;
    }

    .sf-map-chip {
        position: absolute;
        z-index: 2;
        right: 22px;
        bottom: 22px;
        padding: 10px 12px;
        border-radius: 16px;
        background: rgba(255,255,255,0.12);
        border: 1px solid rgba(255,255,255,0.16);
        backdrop-filter: blur(14px);
        font-size: 0.8rem;
        font-weight: 900;
    }

    .sf-node {
        position: absolute;
        z-index: 2;
        width: 64px;
        height: 64px;
        display: grid;
        place-items: center;
        border-radius: 20px;
        background: rgba(255,255,255,0.13);
        border: 1px solid rgba(255,255,255,0.20);
        backdrop-filter: blur(16px);
        color: #fff;
        font-weight: 950;
    }

    .sf-node.a { right: 32px; top: 32px; background: rgba(10,132,255,0.42); }
    .sf-node.b { left: 36px; bottom: 36px; }

    .sf-kpi-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(158px, 1fr));
        gap: 12px;
        margin: 14px 0;
    }

    .sf-kpi {
        min-height: 102px;
        padding: 16px;
        border-radius: 22px;
        background: rgba(255,255,255,0.82);
        border: 1px solid rgba(255,255,255,0.92);
        box-shadow: 0 18px 44px rgba(15,23,42,0.08);
        transition: transform .18s ease, box-shadow .18s ease;
    }

    .sf-kpi:hover {
        transform: translateY(-4px);
        box-shadow: 0 26px 58px rgba(15,23,42,0.12);
    }

    .sf-kpi.danger {
        background: linear-gradient(145deg, rgba(255,255,255,0.92), rgba(255,241,240,0.94));
        border-color: rgba(220,38,38,0.20);
    }

    .sf-kpi.live {
        background: linear-gradient(145deg, rgba(255,255,255,0.92), rgba(240,253,244,0.94));
        border-color: rgba(22,163,74,0.18);
    }

    .sf-kpi span {
        display: block;
        color: #64748b;
        font-size: 0.78rem;
        font-weight: 950;
        text-transform: uppercase;
        letter-spacing: 0.28px;
    }

    .sf-kpi b {
        display: block;
        margin-top: 12px;
        color: #0f172a;
        font-size: clamp(1.8rem, 3.2vw, 2.65rem);
        line-height: 0.95;
        letter-spacing: -1.4px;
    }

    .sf-kpi small {
        display: block;
        margin-top: 8px;
        color: #64748b;
        font-size: 0.78rem;
        font-weight: 800;
    }

    .sf-section-head {
        display: flex;
        justify-content: space-between;
        align-items: end;
        gap: 16px;
        margin: 18px 0 10px;
    }

    .sf-section-head h2 {
        margin: 0;
        color: #0f172a;
        font-size: 1.25rem;
        letter-spacing: -0.6px;
    }

    .sf-section-head p {
        margin: 4px 0 0;
        color: #64748b;
        font-size: 0.84rem;
        font-weight: 750;
    }

    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 24px !important;
        border: 1px solid rgba(15,23,42,0.08) !important;
        background: rgba(255,255,255,0.82) !important;
        box-shadow: 0 16px 42px rgba(15,23,42,0.08) !important;
        backdrop-filter: blur(20px);
    }

    .command-section-title {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 12px;
        color: #0f172a;
        font-size: 0.92rem;
        font-weight: 950;
        letter-spacing: -0.1px;
    }

    .command-section-title::before {
        content: "";
        width: 9px;
        height: 9px;
        border-radius: 999px;
        background: #0a84ff;
        box-shadow: 0 0 0 6px rgba(10,132,255,0.10);
    }

    .stButton > button,
    .stLinkButton > a {
        border-radius: 14px !important;
        min-height: 43px !important;
        font-weight: 950 !important;
        letter-spacing: -0.1px !important;
    }

    .stButton > button {
        background: linear-gradient(180deg, #0f8cff, #006ee6) !important;
        color: #fff !important;
        border: 1px solid rgba(10,132,255,0.30) !important;
        box-shadow: 0 12px 24px rgba(10,132,255,0.20) !important;
    }

    .stLinkButton > a {
        background: #0f172a !important;
        color: #fff !important;
        border: 1px solid rgba(15,23,42,0.18) !important;
    }

    .stTabs [data-baseweb="tab-list"] {
        top: 8px !important;
        border-radius: 20px !important;
        padding: 8px !important;
        background: rgba(255,255,255,0.88) !important;
        border: 1px solid rgba(15,23,42,0.08) !important;
        box-shadow: 0 16px 42px rgba(15,23,42,0.08) !important;
    }

    .stTabs [aria-selected="true"] {
        background: #0f172a !important;
        color: #fff !important;
    }

    @media (max-width: 880px) {
        .sf-topbar,
        .sf-section-head {
            align-items: flex-start;
            flex-direction: column;
        }

        .sf-hero-pro {
            grid-template-columns: 1fr;
        }

        .sf-mini-map {
            min-height: 210px;
        }

        .sf-hero-pro h1 {
            letter-spacing: -1.6px;
        }
    }

    .sf-hero-pro {
        display: block;
        padding: 18px 20px;
        border-radius: 24px;
        margin-bottom: 12px;
    }

    .sf-hero-pro h1 {
        margin: 10px 0 6px;
        font-size: clamp(2rem, 3.4vw, 3.4rem);
        letter-spacing: -2px;
    }

    .sf-hero-pro p {
        max-width: 760px;
        margin-bottom: 0;
    }

    .sf-mini-map {
        display: none !important;
    }

    .sf-kpi-grid {
        grid-template-columns: repeat(auto-fit, minmax(145px, 1fr));
        gap: 10px;
        margin: 10px 0 12px;
    }

    .sf-kpi {
        min-height: 88px;
        padding: 14px 15px;
        border-radius: 18px;
    }

    .sf-kpi b {
        margin-top: 8px;
        font-size: clamp(1.55rem, 2.5vw, 2.25rem);
    }

    .sf-kpi small {
        display: none;
    }

    .sf-control-title {
        margin: 12px 0 8px;
        color: #0f172a;
        font-size: 1rem;
        font-weight: 950;
        letter-spacing: -0.35px;
    }

    .sf-control-hint {
        margin-top: -4px;
        margin-bottom: 8px;
        color: #64748b;
        font-size: 0.8rem;
        font-weight: 800;
    }

    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 20px !important;
        box-shadow: 0 14px 34px rgba(15,23,42,0.07) !important;
    }

    .stButton > button,
    .stLinkButton > a {
        min-height: 46px !important;
    }
</style>
""", unsafe_allow_html=True)

cad_source_label = _html(latest_cad.get("source_format", "NONE") if latest_cad else "NONE")
simulation_label = "Live" if simulation_is_active else "Standby"
simulation_dot_class = "" if simulation_is_active else "warn"
alert_kpi_class = "danger" if critical_alerts_count else ""
client_kpi_class = "live" if simulation_is_active else ""
st.markdown(f"""
<div class="sf-topbar">
    <div class="sf-brand">
        <div class="sf-mark">S</div>
        <div>
            <div class="sf-brand-title">StructFi Digital Twin</div>
            <div class="sf-brand-sub">CAD + AI planning + live network simulation</div>
        </div>
    </div>
    <div class="sf-top-pills">
        <div class="sf-pill"><span class="sf-dot {simulation_dot_class}"></span>{simulation_label}</div>
        <div class="sf-pill">Step {sim_state.get("step", 0)}</div>
        <div class="sf-pill">Render API</div>
    </div>
</div>

<div class="sf-hero-pro">
    <div>
        <div class="sf-eyebrow">Live Network Lab</div>
        <h1>StructFi Control Center</h1>
        <p>CAD planning, RF views, live simulation, IDS, and reports in one control surface.</p>
    </div>
</div>

<div class="sf-kpi-grid">
    <div class="sf-kpi"><span>CAD</span><b>{cad_source_label}</b><small>Source</small></div>
    <div class="sf-kpi"><span>Rooms</span><b>{extracted_rooms_count}</b><small>Extracted</small></div>
    <div class="sf-kpi"><span>Nodes</span><b>{suggested_nodes_count}</b><small>AI plan</small></div>
    <div class="sf-kpi"><span>Score</span><b>{placement}</b><small>Placement</small></div>
    <div class="sf-kpi {client_kpi_class}"><span>Clients</span><b>{len(clients)}</b><small>Live</small></div>
    <div class="sf-kpi {alert_kpi_class}"><span>Alerts</span><b>{len(alerts)}</b><small>{critical_alerts_count} critical</small></div>
</div>

<div class="sf-control-title">Controls</div>
<div class="sf-control-hint">Upload once, then run the actions from left to right.</div>
""", unsafe_allow_html=True)

with st.container(border=True):
    source_col, actions_col, runtime_col = st.columns([1.15, 2.45, 1.55])

    with source_col:
        st.markdown('<div class="command-section-title">Source</div>', unsafe_allow_html=True)
        uploaded_cad = st.file_uploader(
            "DXF / DWG",
            type=["dxf", "dwg"],
            key="cad_upload_main",
        )
        if st.button("Upload", use_container_width=True, key="action_upload_cad"):
            _handle_upload_cad(uploaded_cad)

    with actions_col:
        st.markdown('<div class="command-section-title">Build & Visualize</div>', unsafe_allow_html=True)
        action_cols = st.columns(4)
        with action_cols[0]:
            if st.button("Extract", use_container_width=True, key="action_extract_rooms"):
                _handle_extract_rooms()
        with action_cols[1]:
            if st.button("AI Plan", use_container_width=True, key="action_ai_plan"):
                _handle_ai_planning()
        with action_cols[2]:
            if st.button("Preview", use_container_width=True, key="action_render_plan"):
                _handle_render_plan()
        with action_cols[3]:
            if st.button("Heatmap", use_container_width=True, key="action_heatmap"):
                _handle_render_heatmap()

        export_cols = st.columns(4)
        with export_cols[0]:
            if st.button("Apply", use_container_width=True, key="action_apply_sim"):
                _handle_apply_plan_to_simulation()
        with export_cols[1]:
            if st.button("Step", use_container_width=True, key="action_next_step"):
                _handle_next_simulation_step()
        with export_cols[2]:
            st.link_button("Excel", get_excel_export_url(), use_container_width=True)
        with export_cols[3]:
            st.link_button("PDF", get_pdf_export_url(), use_container_width=True)

    with runtime_col:
        st.markdown('<div class="command-section-title">Runtime</div>', unsafe_allow_html=True)
        st.session_state.auto_simulation_enabled = st.checkbox(
            "Auto",
            value=bool(st.session_state.get("auto_simulation_enabled", False)),
            help="Advance one simulation step repeatedly.",
        )
        st.session_state.auto_simulation_interval = st.slider(
            "Interval",
            min_value=0.5,
            max_value=3.0,
            value=float(st.session_state.get("auto_simulation_interval", 1.0)),
            step=0.5,
        )
        reset_a, reset_b = st.columns(2)
        with reset_a:
            if st.button("Reset", use_container_width=True, key="action_reset_runtime"):
                _handle_reset_simulation()
        with reset_b:
            if st.button("Full", use_container_width=True, key="action_full_reset"):
                _handle_full_project_reset()

if simulation_is_active and critical_alerts_count:
    st.markdown("""
    <div class="critical-banner">
        Critical IDS activity detected. Review the alert feed before continuing the runtime scenario.
    </div>
    """, unsafe_allow_html=True)

workflow_tabs = st.tabs([
    "1. Workflow",
    "2. Live Simulation",
    "3. AI & IDS",
    "4. Rooms & Nodes",
    "5. Backend / Export",
])

# -------------------------------------------------------------------
# 1. Workflow
# -------------------------------------------------------------------
with workflow_tabs[0]:
    st.markdown('<div class="section-title">Workflow</div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="export-card">
        <div class="subtle">Source -> Build -> Runtime -> Output</div>
    </div>
    """, unsafe_allow_html=True)

    extract_col, plan_col = st.columns([1, 1])
    with extract_col:
        st.markdown('<div class="section-title">Extracted Rooms Preview</div>', unsafe_allow_html=True)
        st.caption("Rooms, corridors, labels, and CAD walls only. No nodes in this view.")
        if st.session_state.extracted_img:
            st.image(get_rendered_url(st.session_state.extracted_img["file_name"]), use_container_width=True)
        elif latest_rooms and latest_rooms.get("rooms"):
            st.image(get_rendered_url("cad_extract_rooms.png"), use_container_width=True)
        else:
            st.info("Run Extract.")

    with plan_col:
        st.markdown('<div class="section-title">AI Planning Preview</div>', unsafe_allow_html=True)
        st.caption("Planned nodes, directional beams, room labels, and CAD walls.")
        if st.session_state.plan_img:
            st.image(get_rendered_url(st.session_state.plan_img["file_name"]), use_container_width=True)
        else:
            st.info("Run AI Plan, then Preview.")

    st.markdown('<div class="section-title">Unified RF Heatmap</div>', unsafe_allow_html=True)
    if st.session_state.heatmap_img:
        st.image(get_rendered_url(st.session_state.heatmap_img["file_name"]), use_container_width=True)
    else:
        st.info("Run Heatmap.")

# -------------------------------------------------------------------
# 2. Live Simulation
# -------------------------------------------------------------------
with workflow_tabs[1]:
    top_left, top_right = st.columns([1.35, 1])

    with top_left:
        st.markdown('<div class="section-title">Interactive Simulation Overlay</div>', unsafe_allow_html=True)
        render_interactive_plan(building_data, display_sim_state)

    with top_right:
        st.markdown('<div class="section-title">Simulation Runtime</div>', unsafe_allow_html=True)
        st.markdown('<div class="export-card">', unsafe_allow_html=True)
        st.metric("Simulation Source", sim_state.get("simulation_source", "unknown"))
        st.metric("Step", sim_state.get("step", 0))
        st.metric("Runtime Nodes", len(node_runtime))
        st.metric("Clients", len(clients))
        st.metric("Telemetry Points", len(sim_state.get("telemetry_history", []) or []) if simulation_is_active else 0)
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="section-title">Runtime Nodes</div>', unsafe_allow_html=True)
    if not node_runtime:
        st.info("Apply CAD Plan to Simulation to populate live node runtime.")
    else:
        for node in node_runtime:
            radio = node.get("radio", {}) or {}
            env = node.get("environment", {}) or {}
            st.markdown(f"""
            <div class="room-card">
                <b>{node.get("name", "Node")}</b><br>
                Status: {node.get("status", "unknown")}<br>
                Room: {node.get("room_name", "-")}<br>
                Channel: {radio.get("current_channel", "-")} | TX: {radio.get("tx_power_dbm", "-")} dBm<br>
                Load: {node.get("current_load", 0)} | Connected Clients: {node.get("connected_clients", 0)}<br>
                RSSI Avg: {radio.get("rssi_avg", 0)} dBm | SNR Avg: {radio.get("snr_avg", 0)} dB<br>
                Throughput: {radio.get("throughput_mbps", 0)} Mbps | Retry: {radio.get("retry_rate_pct", 0)}% | Packet Loss: {radio.get("packet_loss_pct", 0)}%<br>
                Latency: {radio.get("latency_ms", 0)} ms | Temp: {env.get("temperature_c", 0)} C | Humidity: {env.get("humidity_pct", 0)}%
            </div>
            """, unsafe_allow_html=True)

    st.markdown('<div class="section-title">Live Clients / Traffic Profiles</div>', unsafe_allow_html=True)
    if not clients:
        st.info("No clients yet. Apply the CAD plan to simulation.")
    else:
        client_rows = _dashboard_build_client_profile_rows(clients)
        if client_rows:
            st.dataframe(_dashboard_table_safe_rows(client_rows), width="stretch", hide_index=True)

        client_cols = st.columns(2)
        for i, client in enumerate(clients):
            with client_cols[i % 2]:
                qos_badge = _dashboard_qos_badge(client.get("qos_state", "not_evaluated"))
                st.markdown(f"""
                <div class="room-card">
                    <b>{client.get("name", "Client")}</b> {qos_badge}<br>
                    Type: {client.get("client_type", client.get("role", "staff"))} | Role: {client.get("role", "staff")}<br>
                    Traffic: {client.get("traffic_profile", "-")} | Priority: {client.get("qos_priority", "-")}<br>
                    SSID: {client.get("ssid", "-")} | VLAN: {client.get("vlan_id", "-")}<br>
                    Required: {client.get("required_bandwidth_mbps", "-")} Mbps | Max Latency: {client.get("max_latency_ms", "-")} ms | Loss Tol.: {client.get("packet_loss_tolerance_pct", "-")}%<br>
                    Mobility: {client.get("mobility_pattern", "-")} | Speed: {client.get("speed", 0)} m/s<br>
                    Position: ({round(float(client.get("x", 0)), 2)}, {round(float(client.get("y", 0)), 2)})<br>
                    Connected Node: {client.get("connected_node", "-")}<br>
                    RSSI: {client.get("current_rssi", "-")} dBm | SNR: {client.get("current_snr", "-")} dB<br>
                    Throughput: {client.get("current_throughput_mbps", 0)} Mbps | Latency: {client.get("current_latency_ms", 0)} ms | Loss: {client.get("current_packet_loss_pct", 0)}%<br>
                    Roaming: {client.get("roaming_count", 0)} | Last Handover: {client.get("handover_latency_ms", 0)} ms / {client.get("last_handover_status", "none")}
                </div>
                """, unsafe_allow_html=True)

    st.markdown('<div class="section-title">Recent Simulation Events / Handover Timeline</div>', unsafe_allow_html=True)
    if not runtime_events:
        st.info("No runtime events yet. Apply the CAD plan and advance simulation steps to observe movement, handover, and QoS behavior.")
    else:
        for event in list(runtime_events)[-8:][::-1]:
            metadata = event.get("metadata", {}) if isinstance(event, dict) else {}
            extra = ""
            if isinstance(metadata, dict) and metadata:
                handover_latency = metadata.get("handover_latency_ms")
                speed = metadata.get("client_speed_mps")
                status = metadata.get("status")
                if handover_latency is not None:
                    extra += f"<br>Handover Latency: {handover_latency} ms"
                if speed is not None:
                    extra += f" | Speed: {speed} m/s"
                if status is not None:
                    extra += f" | Status: {status}"
            st.markdown(f"""
            <div class="room-card">
                <b>{str(event.get('type', 'event')).upper()}</b> - {event.get('severity', 'info')}<br>
                {event.get('message', '')}{extra}
            </div>
            """, unsafe_allow_html=True)

# -------------------------------------------------------------------
# 3. AI & IDS
# -------------------------------------------------------------------
with workflow_tabs[2]:
    st.markdown('<div class="section-title">AI Runtime Status</div>', unsafe_allow_html=True)
    ai_cols = st.columns(5)
    with ai_cols[0]:
        st.markdown("**Status**")
        render_status_badge(health.get("status", "stable"))
    with ai_cols[1]:
        st.metric("Anomaly Score", health.get("anomaly_score", 0))
    with ai_cols[2]:
        st.metric("Critical", critical_alerts_count)
    with ai_cols[3]:
        st.metric("Warnings", warning_alerts_count)
    with ai_cols[4]:
        st.metric("High Load Nodes", health.get("high_load_nodes", 0))

    rec_col, alert_col = st.columns([1, 1])
    with rec_col:
        st.markdown('<div class="section-title">AI Recommendations</div>', unsafe_allow_html=True)
        if not recommendations:
            st.info("No recommendations yet.")
        else:
            for rec in recommendations:
                st.markdown(f"""
                <div class="room-card">
                    <b>{str(rec.get("type", "observation")).upper()}</b><br>
                    {rec.get("message", "")}<br>
                    Confidence: {rec.get("confidence", 0)}
                </div>
                """, unsafe_allow_html=True)

    with alert_col:
        st.markdown('<div class="section-title">Security / IDS Alerts</div>', unsafe_allow_html=True)
        if not alerts:
            st.info("No security alerts.")
        else:
            sorted_alerts = sorted(
                alerts,
                key=lambda item: {"critical": 0, "warning": 1, "info": 2}.get(_alert_severity(item), 3),
            )
            for alert in sorted_alerts:
                _render_alert_card(alert)

    st.markdown('<div class="section-title">Controller Decisions</div>', unsafe_allow_html=True)
    if not decisions:
        st.info("No controller decisions yet.")
    else:
        for d in decisions:
            st.markdown(f"""
            <div class="room-card">
                <b>{d.get("action", "none")}</b><br>
                Node: {d.get("node_id", "-")}<br>
                Value: {d.get("value", "")}<br>
                Reason: {d.get("reason", "")}
            </div>
            """, unsafe_allow_html=True)

# -------------------------------------------------------------------
# 4. Rooms & Nodes
# -------------------------------------------------------------------
with workflow_tabs[3]:
    rooms_col, nodes_col = st.columns([1, 1])

    with rooms_col:
        st.markdown('<div class="section-title">Extracted Rooms Inventory</div>', unsafe_allow_html=True)
        if latest_rooms and latest_rooms.get("rooms"):
            for room in latest_rooms.get("rooms", []):
                st.markdown(f"""
                <div class="room-card">
                    <b>{room.get("name", "Room")}</b><br>
                    Type: {room.get("room_type", "unknown")} | Zone: {room.get("zone", "unknown")} | Floor: {room.get("floor", "unknown")}<br>
                    Size: {round(float(room.get("width", 0)), 2)} x {round(float(room.get("height", 0)), 2)} | Area: {round(float(room.get("area", 0)), 2)}<br>
                    Expected Clients: {room.get("expected_clients", 0)} | Traffic: {room.get("traffic_profile", "medium")}<br>
                    Confidence: {room.get("confidence", 0)}
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No extracted rooms yet.")

    with nodes_col:
        st.markdown('<div class="section-title">Suggested Nodes Inventory</div>', unsafe_allow_html=True)
        if plan_nodes_list:
            for node in plan_nodes_list:
                coverage = node.get("coverage", {}) or {}
                capacity = node.get("capacity", {}) or {}
                coverage_metrics = node.get("coverage_metrics", {}) or {}
                capacity_metrics = node.get("capacity_metrics", {}) or {}
                telemetry = node.get("telemetry", {}) or {}
                node_name = node.get("name") or node.get("node_id") or f"Node {node.get('id', '-') }"
                coverage_score = coverage.get("room_coverage_score", coverage_metrics.get("coverage_percent", 0))
                projected_clients = capacity.get("projected_clients", capacity_metrics.get("expected_clients", 0))
                projected_capacity = capacity.get("projected_capacity_mbps", capacity_metrics.get("effective_capacity_mbps", 0))
                tx_power = node.get("tx_power", node.get("tx_power_dbm", telemetry.get("tx_power_dbm", 0)))
                st.markdown(f"""
                <div class="node-card">
                    <b>{node_name}</b><br>
                    Room: {node.get("room_name", "-")} | Role: {node.get("node_role", "room_node")}<br>
                    Position: ({round(float(node.get("x", 0)), 2)}, {round(float(node.get("y", 0)), 2)})<br>
                    TX: {tx_power} dBm | Channel: {node.get("channel", 0)}<br>
                    Beam: {node.get("beam_direction_deg", node.get("antenna_direction", "omni"))}<br>
                    Coverage: {coverage_score} | Clients: {projected_clients} | Capacity: {projected_capacity} Mbps<br>
                    Placement Score: {node.get("placement_score", 0)}
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No planned nodes yet.")

# -------------------------------------------------------------------
# 5. Backend / Export
# -------------------------------------------------------------------
with workflow_tabs[4]:
    st.markdown('<div class="section-title">Backend & Mobile Readiness</div>', unsafe_allow_html=True)
    st.markdown(f"""
    <div class="export-card">
        <b>Backend base URL</b><br>
        <span class="subtle">{API_URL}</span><br><br>
        <b>Mobile-ready endpoints</b><br>
        <span class="subtle">/mobile/bootstrap, /mobile/dashboard, /mobile/images, /mobile/nodes, /mobile/clients, /mobile/alerts, /mobile/simulation, /mobile/reports</span><br><br>
        <b>Router / Security endpoints</b><br>
        <span class="subtle">/router/config, /network/vlans, /network/ssids, /security/policies, /ids/rules</span>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="section-title">CAD / Planning JSON</div>', unsafe_allow_html=True)
    info_col, json_col = st.columns([0.8, 1.2])
    with info_col:
        if latest_cad:
            st.markdown(f"""
            <div class="room-card">
                <b>CAD Info</b><br>
                Source: {latest_cad.get("source_file_name", "-")}<br>
                Format: {latest_cad.get("source_format", "-")}<br>
                Converted: {latest_cad.get("converted", False)}<br>
                Working DXF: {latest_cad.get("working_dxf_file_name", "-")}
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info("No CAD file uploaded yet.")

    with json_col:
        with st.expander("Show latest plan JSON", expanded=False):
            st.json(latest_plan or {})
        with st.expander("Show simulation state JSON", expanded=False):
            st.json(sim_state or {})

    st.markdown('<div class="section-title">Export Center</div>', unsafe_allow_html=True)
    export_a, export_b = st.columns(2)
    with export_a:
        st.link_button("Download Excel Report", get_excel_export_url(), use_container_width=True)
    with export_b:
        st.link_button("Download PDF Report", get_pdf_export_url(), use_container_width=True)

# Auto real-time playback. This runs after rendering the current frame so the
# user can see each tick before the page refreshes.
if simulation_is_active and st.session_state.get("auto_simulation_enabled", False):
    time.sleep(float(st.session_state.get("auto_simulation_interval", 1.0)))
    auto_result = next_step()
    if auto_result.get("step") is not None:
        st.rerun()
    else:
        st.session_state.auto_simulation_enabled = False
        st.warning(auto_result.get("detail", "Auto simulation stopped because the backend did not advance."))
