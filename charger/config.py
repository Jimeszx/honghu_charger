"""
配置模块 - 固定值硬编码，动态值从 config.yaml 读取。
"""

import os

import yaml


# 固定配置（不会变）
BASE_URL = "https://m1.cdzypt.net"
WXMP_APPID = "wxab5a30e2e6ef5797"
TENANT_VER = "1"

API_URL = f"{BASE_URL}/uiapi/cdzcomm_v1/cdzcomm/cdzcomm_get_charging_or_waitpay_order"
POWER_FIELD = "api_objects.0.order_list.0.power"
ENERGY_FIELD = "api_objects.0.order_list.0.energy_consumed"
ORDER_ID_FIELD = "api_objects.0.order_list.0.transaction_id"

from pathlib import Path

DEFAULT_INTERVAL = 300  # 默认采集间隔 5 分钟（平台数据更新频率）

OUTPUT_DIR = "./output"
DB_PATH = str(Path(OUTPUT_DIR) / "data" / "charge_data.db")
PLOT_DIR = str(Path(OUTPUT_DIR) / "plots")
LOG_PATH = str(Path(OUTPUT_DIR) / "data" / "collector.log")

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 NetType/WIFI MicroMessenger/7.0.20.1781(0x6700143B) WindowsWechat(0x63090a13) UnifiedPCWindowsWechat(0xf2541843) XWEB/19339 Flue",
    "Content-Type": "application/json",
    "api-client-ver": "1.3.15",
    "api-client-type": "wxmp",
    "Origin": BASE_URL,
    "Referer": f"{BASE_URL}/pages/tab_map/tab_map",
}


CONFIG_PATH = str(Path(OUTPUT_DIR) / "config.yaml")


def load_dynamic_config(config_path: str = None) -> dict:
    """
    加载动态配置（JWT Token、tenant_no、customer_no）。
    如果文件不存在则返回空字典。
    """
    if config_path is None:
        config_path = CONFIG_PATH
    if not os.path.exists(config_path):
        return {}

    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    return {
        "jwt_token": data.get("Authorization", "").replace("Bearer ", "").strip(),
        "tenant_no": str(data.get("tenant_no", "")),
        "customer_no": data.get("customer_no", 0),
    }


def build_full_config(config_path: str = None) -> dict:
    """
    构建完整的配置字典，合并固定值和动态值。
    供 collector、scheduler 等模块使用。
    """
    if config_path is None:
        config_path = CONFIG_PATH
    dynamic = load_dynamic_config(config_path)

    headers = dict(DEFAULT_HEADERS)
    jwt = dynamic.get("jwt_token", "")
    if jwt:
        headers["Authorization"] = f"Bearer {jwt}"

    return {
        "api": {
            "url": API_URL,
            "method": "POST",
            "body": {
                "tenant_no": dynamic.get("tenant_no", ""),
                "customer_no": dynamic.get("customer_no", 0),
            },
            "headers": headers,
            "power_field": POWER_FIELD,
            "energy_field": ENERGY_FIELD,
            "order_id_field": ORDER_ID_FIELD,
        },
        "output_dir": OUTPUT_DIR,
        "collect_interval": DEFAULT_INTERVAL,
        "logging": {
            "level": "INFO",
            "file": LOG_PATH,
        },
    }


def save_dynamic_config(config_path: str, jwt_token: str = None,
                        tenant_no: str = None, customer_no=None):
    """保存动态配置到 config.yaml（保留注释）"""
    import re

    # 读取已有内容
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read()
    else:
        content = (
            "# 鸿鹄智充 - 配置文件\n"
            "# 由 python main.py token 命令自动创建和更新\n"
            "# 不需要手动修改此文件\n"
            "\n"
            'Authorization: "Bearer "\n'
            "tenant_no: \"\"\n"
            "customer_no: 0\n"
        )

    # 用正则替换值，保留注释和格式
    if jwt_token:
        content = re.sub(
            r'^Authorization:\s*".*?"',
            f'Authorization: "Bearer {jwt_token}"',
            content, flags=re.MULTILINE
        )
    if tenant_no:
        content = re.sub(
            r'^tenant_no:\s*.*',
            f'tenant_no: "{tenant_no}"',
            content, flags=re.MULTILINE
        )
    if customer_no is not None:
        content = re.sub(
            r'^customer_no:\s*.*',
            f'customer_no: {customer_no}',
            content, flags=re.MULTILINE
        )

    with open(config_path, "w", encoding="utf-8") as f:
        f.write(content)
