from __future__ import annotations

from pathlib import Path
from typing import Dict, List


class Settings:
    """
    StructFi centralized backend configuration.

    This file is intentionally simple and import-safe.
    Other services import `settings` directly, so all values are plain Python
    constants and dictionaries. No database, no environment dependency, and no
    startup side effects except creating required data folders.
    """

    # ------------------------------------------------------------------
    # Application identity
    # ------------------------------------------------------------------

    APP_NAME = "StructFi Simulator"
    APP_VERSION = "0.2.0-demo"
    PROJECT_NAME = "StructFi"
    PROJECT_FULL_NAME = "Low-Cost Enterprise Wi-Fi System Prototype"
    PROJECT_MODE = "graduation_demo"

    # ------------------------------------------------------------------
    # Paths
    # ------------------------------------------------------------------

    BASE_DIR = Path(__file__).resolve().parent.parent.parent
    DATA_DIR = BASE_DIR / "data"

    UPLOADS_DIR = DATA_DIR / "uploads"
    PARSED_DIR = DATA_DIR / "parsed"
    GENERATED_DIR = DATA_DIR / "generated"
    RUNTIME_DIR = DATA_DIR / "runtime"
    RENDERED_DIR = DATA_DIR / "rendered"
    REPORTS_DIR = DATA_DIR / "reports"
    META_DIR = DATA_DIR / "meta"

    REQUIRED_DIRS = [
        DATA_DIR,
        UPLOADS_DIR,
        PARSED_DIR,
        GENERATED_DIR,
        RUNTIME_DIR,
        RENDERED_DIR,
        REPORTS_DIR,
        META_DIR,
    ]

    # ------------------------------------------------------------------
    # Backend/API configuration
    # ------------------------------------------------------------------

    API_HOST = "0.0.0.0"
    API_PORT = 8000

    # Cloud backend used by Streamlit Cloud and the mobile app.
    API_BASE_URL = "https://structfi.onrender.com"

    # Local dashboard defaults. Streamlit Cloud should use st.secrets["API_URL"].
    DASHBOARD_HOST = "127.0.0.1"
    DASHBOARD_PORT = 8501
    DASHBOARD_URL = f"http://{DASHBOARD_HOST}:{DASHBOARD_PORT}"

    # Keep permissive for demo because:
    # - Streamlit Cloud calls the API
    # - Mobile app calls the API
    # - Local dashboard may still call the API
    CORS_ALLOWED_ORIGINS = ["*"]

    REQUEST_TIMEOUT_SECONDS = 120

    # ------------------------------------------------------------------
    # Centralized router / controller configuration
    # ------------------------------------------------------------------

    CENTRAL_ROUTER = {
        "name": "StructFi Central Controller",
        "role": "centralized_router_controller",
        "model": "prototype_router_or_laptop_controller",
        "management_ip": "192.168.10.1",
        "management_vlan": 10,
        "controller_subnet": "192.168.10.0/24",
        "internet_uplink": "wan0",
        "lan_interface": "lan0",
        "node_management_port": 1883,
        "api_port": API_PORT,
        "dashboard_port": DASHBOARD_PORT,
        "dhcp_enabled": True,
        "dns_forwarder_enabled": True,
        "nat_enabled": True,
        "firewall_enabled": True,
        "radius_enabled": True,
        "telemetry_poll_interval_seconds": 5,
        "config_sync_interval_seconds": 15,
        "public_api_url": API_BASE_URL,
        "description": (
            "Prototype centralized controller for managing simulated ESP32-S3 Wi-Fi nodes, "
            "VLAN profiles, telemetry, alerts, and AI recommendations."
        ),
    }

    # ------------------------------------------------------------------
    # Wireless / node defaults
    # ------------------------------------------------------------------

    DEFAULT_TX_POWER = 18
    DEFAULT_TX_POWER_DBM = 18
    MIN_TX_POWER_DBM = 8
    MAX_TX_POWER_DBM = 20

    DEFAULT_CHANNELS_24GHZ = [1, 6, 11]
    DEFAULT_CHANNELS_5GHZ = [36, 40, 44, 48, 149, 153, 157, 161]

    DEFAULT_BAND = "5GHz"
    FALLBACK_BAND = "2.4GHz"
    DEFAULT_WIFI_STANDARD = "IEEE 802.11ax/ac simulated"

    DEFAULT_NODE_CAPACITY_MBPS = 110.0
    DEFAULT_MAX_CLIENTS_PER_NODE = 18
    CORRIDOR_MAX_CLIENTS_PER_NODE = 28

    DEFAULT_NOISE_FLOOR_DBM = -92.0
    MIN_ACCEPTABLE_RSSI_DBM = -72.0
    TARGET_RSSI_DBM = -62.0
    EXCELLENT_RSSI_DBM = -50.0

    DEFAULT_SNR_GOOD_DB = 25.0
    DEFAULT_SNR_WARNING_DB = 18.0
    DEFAULT_SNR_CRITICAL_DB = 12.0

    ROAMING_80211R_ENABLED = True
    TARGET_HANDOVER_LATENCY_MS = 100.0

    NODE_FIRMWARE_VERSION = "node-fw-1.0-demo"
    NODE_IP_BASE = "192.168.10."
    NODE_IP_START = 101

    ESP32_NODE_PROFILE = {
        "device_family": "ESP32-S3",
        "role": "low_cost_wifi_node_prototype",
        "expected_power_watts_idle": 3.2,
        "expected_power_watts_peak": 7.8,
        "enclosure": "hidden_vertical_in_wall_corner_enclosure",
        "limitations": [
            "Not enterprise-grade AP hardware",
            "Limited client capacity compared with commercial access points",
            "Best used as prototype/simulation node for monitoring and concept demonstration",
        ],
    }

    # ------------------------------------------------------------------
    # VLAN / SSID profiles
    # ------------------------------------------------------------------

    DEFAULT_MANAGEMENT_VLAN = 10
    DEFAULT_STAFF_VLAN = 20
    DEFAULT_GUEST_VLAN = 30
    DEFAULT_IOT_VLAN = 40

    VLAN_PROFILES = [
        {
            "vlan_id": DEFAULT_MANAGEMENT_VLAN,
            "name": "Management",
            "zone_role": "management",
            "zone": "management",
            "subnet": "192.168.10.0/24",
            "gateway": "192.168.10.1",
            "dhcp_enabled": True,
            "description": "Controller, admins, monitoring, and privileged devices.",
        },
        {
            "vlan_id": DEFAULT_STAFF_VLAN,
            "name": "Staff",
            "zone_role": "staff",
            "zone": "staff",
            "subnet": "192.168.20.0/24",
            "gateway": "192.168.20.1",
            "dhcp_enabled": True,
            "description": "Internal staff users and trusted devices.",
        },
        {
            "vlan_id": DEFAULT_GUEST_VLAN,
            "name": "Guest",
            "zone_role": "guest",
            "zone": "guest",
            "subnet": "192.168.30.0/24",
            "gateway": "192.168.30.1",
            "dhcp_enabled": True,
            "description": "Internet-only isolated guest users.",
        },
        {
            "vlan_id": DEFAULT_IOT_VLAN,
            "name": "IoT",
            "zone_role": "iot",
            "zone": "iot",
            "subnet": "192.168.40.0/24",
            "gateway": "192.168.40.1",
            "dhcp_enabled": True,
            "description": "Optional IoT / sensor network for prototype expansion.",
        },
    ]

    SSID_PROFILES = [
        {
            "ssid_name": "StructFi-Enterprise",
            "ssid": "StructFi-Enterprise",
            "security_mode": "WPA3-Enterprise",
            "security": "WPA3-Enterprise",
            "vlan_id": DEFAULT_STAFF_VLAN,
            "radius_enabled": True,
            "fast_roaming_enabled": True,
            "roaming_80211r": True,
            "max_clients_per_node": DEFAULT_MAX_CLIENTS_PER_NODE,
        },
        {
            "ssid_name": "StructFi-Management",
            "ssid": "StructFi-Management",
            "security_mode": "WPA3-Enterprise",
            "security": "WPA3-Enterprise",
            "vlan_id": DEFAULT_MANAGEMENT_VLAN,
            "radius_enabled": True,
            "fast_roaming_enabled": True,
            "roaming_80211r": True,
            "hidden": True,
            "max_clients_per_node": 8,
        },
        {
            "ssid_name": "StructFi-Guest",
            "ssid": "StructFi-Guest",
            "security_mode": "Open",
            "security": "Captive Portal / Isolated VLAN",
            "vlan_id": DEFAULT_GUEST_VLAN,
            "radius_enabled": False,
            "fast_roaming_enabled": False,
            "client_isolation": True,
            "max_clients_per_node": DEFAULT_MAX_CLIENTS_PER_NODE,
        },
    ]

    RADIUS_PROFILE = {
        "enabled": True,
        "auth_mode": "WPA3-Enterprise",
        "server_ip": "192.168.10.10",
        "port": 1812,
        "accounting_port": 1813,
        "accounting_enabled": True,
        "shared_secret_label": "demo-secret-not-for-production",
        "description": "Prototype RADIUS profile for enterprise authentication demonstration.",
    }

    ACCESS_POLICIES = [
        {
            "id": 1,
            "source_role": "guest",
            "target_zone": "internet",
            "action": "allow",
            "description": "Guests may access the internet only.",
        },
        {
            "id": 2,
            "source_role": "guest",
            "target_zone": "staff",
            "action": "deny",
            "description": "Guests are isolated from staff devices.",
        },
        {
            "id": 3,
            "source_role": "guest",
            "target_zone": "management",
            "action": "deny",
            "description": "Guests cannot access management VLAN.",
        },
        {
            "id": 4,
            "source_role": "guest",
            "target_zone": "controller",
            "action": "deny",
            "description": "Guests cannot access the controller.",
        },
        {
            "id": 5,
            "source_role": "staff",
            "target_zone": "internet",
            "action": "allow",
            "description": "Staff may access the internet.",
        },
        {
            "id": 6,
            "source_role": "staff",
            "target_zone": "staff",
            "action": "allow",
            "description": "Staff may access staff resources.",
        },
        {
            "id": 7,
            "source_role": "staff",
            "target_zone": "management",
            "action": "deny",
            "description": "Staff cannot access management VLAN by default.",
        },
        {
            "id": 8,
            "source_role": "staff",
            "target_zone": "controller",
            "action": "deny",
            "description": "Staff cannot access controller admin interfaces.",
        },
        {
            "id": 9,
            "source_role": "management",
            "target_zone": "internet",
            "action": "allow",
            "description": "Management users may access internet.",
        },
        {
            "id": 10,
            "source_role": "management",
            "target_zone": "staff",
            "action": "allow",
            "description": "Management users may access staff resources.",
        },
        {
            "id": 11,
            "source_role": "management",
            "target_zone": "management",
            "action": "allow",
            "description": "Management users may access management VLAN.",
        },
        {
            "id": 12,
            "source_role": "management",
            "target_zone": "controller",
            "action": "allow",
            "description": "Management users may administer the controller.",
        },
    ]

    # ------------------------------------------------------------------
    # AI thresholds and scoring
    # ------------------------------------------------------------------

    AI_THRESHOLDS = {
        "rssi_warning_dbm": -72.0,
        "rssi_critical_dbm": -80.0,
        "snr_warning_db": 18.0,
        "snr_critical_db": 12.0,
        "retry_warning_pct": 15.0,
        "retry_critical_pct": 25.0,
        "packet_loss_warning_pct": 5.0,
        "packet_loss_critical_pct": 12.0,
        "latency_warning_ms": 80.0,
        "latency_critical_ms": 140.0,
        "node_load_warning": 6,
        "node_load_critical": 10,
        "temperature_warning_c": 55.0,
        "temperature_critical_c": 70.0,
        "anomaly_warning_score": 25.0,
        "anomaly_critical_score": 60.0,
        "min_recommendation_confidence": 0.60,
    }

    AI_RECOMMENDATION_POLICY = {
        "prefer_low_cost_actions": True,
        "allow_add_node_recommendation": True,
        "allow_tx_power_adjustment": True,
        "allow_channel_change": True,
        "allow_reposition_recommendation": True,
        "explain_limitations": True,
        "demo_focused": True,
    }

    # ------------------------------------------------------------------
    # IDS thresholds and rule catalog
    # ------------------------------------------------------------------

    IDS_THRESHOLDS = {
        "weak_signal_rssi_dbm": -76.0,
        "critical_signal_rssi_dbm": -84.0,
        "low_snr_db": 16.0,
        "high_retry_rate_pct": 18.0,
        "critical_retry_rate_pct": 30.0,
        "packet_loss_pct": 8.0,
        "critical_packet_loss_pct": 15.0,
        "high_latency_ms": 100.0,
        "critical_latency_ms": 180.0,
        "rapid_roaming_events": 3,
        "node_overload_clients": 8,
        "node_critical_clients": 12,
        "temperature_warning_c": 55.0,
        "temperature_critical_c": 70.0,
    }

    IDS_RULES = [
        {
            "id": "IDS-001",
            "name": "Guest isolation violation",
            "category": "segmentation_violation",
            "severity": "critical",
            "description": "Guest client attempted to access management/controller resources.",
        },
        {
            "id": "IDS-002",
            "name": "Weak client signal",
            "category": "weak_signal",
            "severity": "warning",
            "description": "Client RSSI dropped below acceptable threshold.",
        },
        {
            "id": "IDS-003",
            "name": "High retry rate",
            "category": "high_retries",
            "severity": "warning",
            "description": "Wireless retry rate indicates interference or poor link quality.",
        },
        {
            "id": "IDS-004",
            "name": "Packet loss detected",
            "category": "packet_loss",
            "severity": "warning",
            "description": "Packet loss exceeded demo threshold.",
        },
        {
            "id": "IDS-005",
            "name": "Node failure",
            "category": "node_failure",
            "severity": "critical",
            "description": "Node is offline or severely degraded.",
        },
        {
            "id": "IDS-006",
            "name": "Interference risk",
            "category": "interference",
            "severity": "warning",
            "description": "Retry/latency/SNR pattern suggests RF interference.",
        },
        {
            "id": "IDS-007",
            "name": "Thermal enclosure risk",
            "category": "anomaly",
            "severity": "warning",
            "description": "Node temperature suggests enclosure ventilation issue.",
        },
    ]

    # ------------------------------------------------------------------
    # Simulation defaults
    # ------------------------------------------------------------------

    SIMULATION = {
        "step_seconds": 5,
        "client_speed_min": 0.18,
        "client_speed_max": 0.55,
        "default_clients_per_room_min": 1,
        "default_clients_per_room_max": 6,
        "enable_roaming": True,
        "enable_controller_decisions": True,
        "enable_ai": True,
        "enable_ids": True,
        "telemetry_history_limit": 500,
        "auto_apply_latest_plan_if_empty": True,
    }

    ROOM_CLIENT_DENSITY = {
        "office": 2,
        "meeting": 5,
        "open_area": 6,
        "reception": 3,
        "corridor": 1,
        "server_room": 1,
        "service": 1,
        "storage": 1,
        "kitchen": 1,
        "bathroom": 1,
        "unknown": 1,
    }

    # ------------------------------------------------------------------
    # Rendering defaults
    # ------------------------------------------------------------------

    RENDERING = {
        "dpi_rooms": 175,
        "dpi_plan": 175,
        "dpi_heatmap": 170,
        "figure_width": 12.8,
        "min_figure_height": 5.5,
        "max_figure_height": 9.2,
        "heatmap_grid_x": 220,
        "heatmap_alpha": 0.78,
    }

    # ------------------------------------------------------------------
    # Mobile app integration defaults
    # ------------------------------------------------------------------

    MOBILE_API = {
        "base_url": API_BASE_URL,
        "base_url_android_emulator": API_BASE_URL,
        "base_url_ios_simulator": API_BASE_URL,
        "base_url_physical_device_note": "Use deployed backend URL for the demo.",
        "refresh_interval_seconds": 5,
        "screens": [
            "Dashboard",
            "CAD Images",
            "Nodes",
            "Clients",
            "Alerts",
            "AI Recommendations",
            "Management",
        ],
    }

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    @classmethod
    def ensure_directories(cls) -> None:
        for directory in cls.REQUIRED_DIRS:
            directory.mkdir(parents=True, exist_ok=True)

    @classmethod
    def get_vlan_by_role(cls, role: str) -> Dict:
        for vlan in cls.VLAN_PROFILES:
            if vlan.get("zone_role") == role or vlan.get("zone") == role:
                return vlan
        return cls.VLAN_PROFILES[1]

    @classmethod
    def get_policy_action(cls, source_role: str, target_zone: str) -> str:
        for policy in cls.ACCESS_POLICIES:
            if policy["source_role"] == source_role and policy["target_zone"] == target_zone:
                return policy["action"]
        return "deny"

    @classmethod
    def get_channel_for_index(cls, index: int, band: str = "5GHz") -> int:
        channels = cls.DEFAULT_CHANNELS_5GHZ if band == "5GHz" else cls.DEFAULT_CHANNELS_24GHZ
        return channels[index % len(channels)]


settings = Settings()
settings.ensure_directories()