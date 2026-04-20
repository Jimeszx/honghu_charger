#!/usr/bin/env python3
"""
鸿鹄智充 - 充电功率数据自动采集工具
"""

import argparse
import os
import sys
import logging
import json
import uuid
import base64
import glob
import warnings
from datetime import datetime
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from charger.config import (
    BASE_URL, WXMP_APPID, TENANT_VER, DEFAULT_INTERVAL,
    OUTPUT_DIR, DB_PATH, PLOT_DIR, LOG_PATH, CONFIG_PATH,
    build_full_config, save_dynamic_config,
)

warnings.filterwarnings("ignore", message="Unverified HTTPS request")

DEFAULT_CONFIG = CONFIG_PATH


def setup_logging():
    """配置日志"""
    log_dir = os.path.dirname(LOG_PATH)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(LOG_PATH, encoding="utf-8"),
        ]
    )


# ============================================================
# token 命令
# ============================================================

def build_headers(jwt_token=None):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 NetType/WIFI MicroMessenger/7.0.20.1781(0x6700143B) WindowsWechat(0x63090a13) UnifiedPCWindowsWechat(0xf2541843) XWEB/19339 Flue",
        "Content-Type": "application/json",
        "api-client-ver": "1.3.15",
        "api-client-type": "wxmp",
        "Origin": BASE_URL,
        "Referer": f"{BASE_URL}/pages/tab_map/tab_map",
    }
    if jwt_token:
        headers["Authorization"] = f"Bearer {jwt_token}"
    return headers


def generate_oauth_url():
    redirect_uri = quote(BASE_URL, safe="")
    return (
        f"https://open.weixin.qq.com/connect/oauth2/authorize"
        f"?appid={WXMP_APPID}&redirect_uri={redirect_uri}"
        f"&response_type=code&scope=snsapi_userinfo&state=1#wechat_redirect"
    )


def exchange_code_for_jwt(code: str, tenant_no: str = "100009") -> dict:
    import requests
    url = f"{BASE_URL}/uiapi/v1/login/uni_login"
    app_guid = str(uuid.uuid4())
    body = {
        "code": code,
        "tenant_ver": TENANT_VER,
        "tenant_no": tenant_no,
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 NetType/WIFI MicroMessenger/7.0.20.1781(0x6700143B) WindowsWechat(0x63090a13) UnifiedPCWindowsWechat(0xf2541843) XWEB/19339 Flue",
        "wxmp_appid": WXMP_APPID,
        "app_guid": app_guid,
    }
    headers = build_headers()
    headers["api-client-app-guid"] = app_guid
    resp = requests.post(url, json=body, headers=headers, timeout=15, verify=False)
    return resp.json()


def extract_code_from_url(url: str) -> str:
    for part in url.split("&"):
        part = part.strip()
        if part.startswith("code="):
            return part.split("=", 1)[1]
        if "?code=" in part or "&code=" in part:
            return part.split("code=", 1)[1].split("&")[0]
    return ""


def decode_jwt(token: str) -> dict:
    try:
        parts = token.split(".")
        payload = parts[1]
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += "=" * padding
        return json.loads(base64.b64decode(payload))
    except Exception:
        return {}


def cmd_token(args):
    import requests

    print()
    print("=" * 60)
    print("鸿鹄智充 - JWT Token 获取")
    print("=" * 60)
    print()
    print("步骤 1/3：在微信中打开以下链接")
    print("-" * 60)
    print(generate_oauth_url())
    print("-" * 60)
    print()
    print("  A. 复制链接 -> 微信文件传输助手 -> 点击打开")
    print("  B. 复制链接 -> 微信 PC 版地址栏粘贴访问")
    print()

    redirected_url = input("步骤 2/3：粘贴跳转后的 URL: ").strip()
    if not redirected_url:
        print("  未输入 URL，退出。")
        return

    code = extract_code_from_url(redirected_url)
    if not code:
        if "code=" in redirected_url:
            code = redirected_url.split("code=")[1].split("&")[0].split("#")[0]
        else:
            print(f"  无法提取 code 参数：{redirected_url}")
            return

    print(f"  提取到 code: {code[:10]}...{code[-6:]}")
    print()
    print("步骤 3/3：正在换取 JWT Token...")

    try:
        # 从已有配置中读取 tenant_no（如果有）
        from charger.config import load_dynamic_config
        dynamic = load_dynamic_config(args.config)
        saved_tenant = dynamic.get("tenant_no", "100009") or "100009"

        result = exchange_code_for_jwt(code, tenant_no=saved_tenant)

        if result.get("api_code") != 0:
            print(f"  登录失败: {result.get('api_message', '未知错误')}")
            return

        api_objects = result.get("api_objects", [{}])
        if not api_objects:
            print("  响应中无数据")
            return

        user_info = api_objects[0].get("user_info", {})
        jwt_token = api_objects[0].get("JWT", "") or api_objects[0].get("token", "")

        if not jwt_token:
            print("  未找到 JWT 字段")
            return

        token_data = decode_jwt(jwt_token)
        exp = datetime.fromtimestamp(token_data.get("exp", 0))
        login_info = token_data.get("login_info", {})

        # 从 JWT 中提取 tenant_no 和 customer_no
        tenant_no = str(login_info.get("tenant_no", "100009"))
        customer_no = login_info.get("customer_no", 0)

        print()
        print("  Token 获取成功！")
        print(f"  用户: {user_info.get('nickname', '未知')} ({customer_no})")
        print(f"  过期: {exp.strftime('%Y-%m-%d %H:%M:%S')}（24小时有效）")
        print()

        # 保存到 config.yaml
        config_path = args.config
        save_dynamic_config(config_path, jwt_token=jwt_token,
                           tenant_no=tenant_no, customer_no=customer_no)
        print(f"  已保存到 {config_path}")
        print()
        print("现在可以运行: python main.py schedule")

    except requests.exceptions.ConnectionError:
        print("  连接失败，请检查网络")
    except Exception as e:
        print(f"  异常: {e}")


# ============================================================
# verify 命令
# ============================================================

def cmd_verify(args):
    import requests

    config = build_full_config(args.config)
    headers = config["api"]["headers"]
    auth = headers.get("Authorization", "")
    jwt_token = auth.replace("Bearer ", "") if auth.startswith("Bearer ") else ""

    if not jwt_token:
        print("未找到 Token，请先运行: python main.py token")
        return

    print()
    print("鸿鹄智充 - API 验证")
    print()

    # 检查 Token
    token_data = decode_jwt(jwt_token)
    if not token_data or "exp" not in token_data:
        print("Token 解析失败")
        return

    exp = datetime.fromtimestamp(token_data["exp"])
    now = datetime.now()
    login_info = token_data.get("login_info", {})

    print(f"  用户: {login_info.get('customer_no', '?')} | 手机: {login_info.get('phone_num', '?')}")
    remaining = (exp - now).total_seconds() / 3600
    if now > exp:
        print(f"  状态: 已过期 {abs(remaining):.1f} 小时，请运行: python main.py token")
        return
    print(f"  状态: 有效（剩余 {remaining:.1f} 小时）")

    # 测试 API
    print()
    api_url = config["api"]["url"]
    body = config["api"]["body"]
    print(f"  测试 API: {api_url}")

    try:
        resp = requests.post(api_url, json=body, headers=headers, timeout=15, verify=False)
        data = resp.json()

        if resp.status_code == 200 and data.get("api_code") == 0:
            order_list = data.get("api_objects", [{}])[0].get("order_list", [])
            if not order_list:
                print("  API 正常，当前无充电订单。")
            else:
                for order in order_list:
                    print()
                    print("  --- 充电订单 ---")
                    print(f"  充电站:     {order.get('site_name', '?')}")
                    print(f"  充电桩:     {order.get('node_nickname', '?')}{order.get('port_nickname', '?')} (型号: {order.get('node_device_mpn_id', '?')})")
                    print(f"  网关:       {order.get('gw_device_no', '?')}")
                    print(f"  功率:       {order.get('power', '?')}W")
                    print(f"  电流:       {order.get('current', '?')}A")
                    print(f"  峰值功率:   {order.get('max_power', '?')}W")
                    print(f"  已充电量:   {order.get('energy_consumed', 0) / 1000:.3f} 度")
                    print(f"  已充时长:   {order.get('time_consumed', '?')} 分钟")
                    print(f"  开始时间:   {order.get('begin_time', '?')}")
                    print(f"  结束时间:   {order.get('finish_time') or '未结束'}")
                    print(f"  充电方案:   {order.get('scheme_name', '?')}")
                    print(f"  充电类型:   {order.get('charge_type', '?')}")
                    print(f"  应付金额:   {order.get('amount_due', 0) / 100:.2f} 元")
                    print(f"  订单号:     {order.get('transaction_id', '?')}")
                    print(f"  状态:       {'充电中' if order.get('charge_status') == 1 else '其他'}")
                    print()
                    # 完整 JSON（方便调试）
                    print("  --- 原始数据 ---")
                    print(f"  {json.dumps(order, ensure_ascii=False, indent=2)}")
        else:
            print(f"  API 错误: {data.get('api_message', resp.status_code)}")
    except Exception as e:
        print(f"  请求失败: {e}")


# ============================================================
# once / schedule 命令
# ============================================================

def cmd_once(args):
    from charger.collector import RequestsCollector
    from charger.storage import ChargeDatabase

    config = build_full_config(args.config)
    collector = RequestsCollector(config)

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    with ChargeDatabase(DB_PATH) as db:
        result = collector.collect()
        if result.success:
            rid = db.insert_record(
                power_watts=result.power_watts,
                order_id=result.order_id,
                raw_data=result.raw_data,
                collector_mode=result.collector_mode,
                energy_kwh=result.energy_kwh,
                timestamp=result.server_time,
            )
            energy_str = f" | {result.energy_kwh:.2f}度" if result.energy_kwh is not None else ""
            print(f"采集成功！功率: {result.power_watts}W{energy_str} | 记录ID: {rid}")
        else:
            print(f"采集失败: {result.error_message}")


def cmd_schedule(args):
    from charger.collector import RequestsCollector
    from charger.storage import ChargeDatabase
    from charger.scheduler import ChargeScheduler

    config = build_full_config(args.config)
    collector = RequestsCollector(config)
    interval = args.interval or DEFAULT_INTERVAL

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    with ChargeDatabase(DB_PATH) as db:
        scheduler = ChargeScheduler(collector=collector, db=db, interval=interval)
        scheduler.run()


# ============================================================
# plot 命令
# ============================================================

def cmd_plot(args):
    from charger.storage import ChargeDatabase
    from charger.visualizer import ChargeVisualizer

    if not os.path.exists(DB_PATH):
        print("数据库不存在，请先采集数据。")
        return

    os.makedirs(PLOT_DIR, exist_ok=True)

    with ChargeDatabase(DB_PATH) as db:
        viz = ChargeVisualizer(db, PLOT_DIR, interactive=args.show)
        viz.plot_power_curve(order_id=args.order_id, show=args.show)
        sessions = db.get_sessions_summary()
        if len(sessions) >= 2:
            viz.plot_session_comparison(show=args.show)


# ============================================================
# clean 命令
# ============================================================

def cmd_clean(args):
    files = []
    for path in [DB_PATH, LOG_PATH]:
        if os.path.exists(path):
            files.append(path)
    for pattern in [os.path.join(PLOT_DIR, "*.png"), os.path.join(OUTPUT_DIR, "data", "*.csv")]:
        files.extend(glob.glob(pattern))

    if not files:
        print("没有需要清理的文件。")
        return

    print("将删除以下文件：")
    for f in files:
        print(f"  - {f}")
    if input("\n确认清理？(y/n): ").strip().lower() != "y":
        print("已取消。")
        return

    for f in files:
        os.remove(f)
        print(f"  已删除: {f}")
    print(f"\n清理完成，共删除 {len(files)} 个文件。")


# ============================================================
# status 命令
# ============================================================

def cmd_status(args):
    from charger.storage import ChargeDatabase

    if not os.path.exists(DB_PATH):
        print("数据库不存在，暂无采集记录。")
        return

    with ChargeDatabase(DB_PATH) as db:
        latest = db.get_latest_record()
        sessions = db.get_sessions_summary()

        print("=" * 50)
        print("采集状态")
        print("=" * 50)
        if latest:
            print(f"  最新时间: {latest['timestamp']}")
            print(f"  最新功率: {latest['power_watts']}W")
        else:
            print("  暂无采集记录")

        print(f"\n  充电会话: {len(sessions)}")
        for s in sessions[:5]:
            oid = s['order_id'][:12] if s['order_id'] else '?'
            print(f"    {oid}... | 峰值: {s['max_power']:.0f}W | 平均: {s['avg_power']:.0f}W | {s['total_records']}条")
        print("=" * 50)


# ============================================================
# 主入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="鸿鹄智充 - 充电功率数据自动采集工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python main.py token          # 获取 JWT Token（每天充电前运行一次）
  python main.py verify         # 验证 API 连接
  python main.py once           # 单次采集
  python main.py schedule       # 持续采集（默认5分钟间隔）
  python main.py schedule -i 60 # 自定义间隔
  python main.py plot           # 生成图表
  python main.py clean          # 清理数据
  python main.py status         # 查看状态
        """
    )
    parser.add_argument(
        "command",
        choices=["token", "verify", "once", "schedule", "plot", "clean", "status"],
    )
    parser.add_argument(
        "--config", "-c",
        default=DEFAULT_CONFIG,
        help="配置文件路径（默认: output/config.yaml）"
    )
    parser.add_argument(
        "--interval", "-i",
        type=int,
        default=None,
        help="采集间隔秒数，仅 schedule 命令有效（默认: 300）"
    )
    parser.add_argument(
        "--order-id", "-o",
        default=None,
        help="按订单ID筛选数据，仅 plot 命令有效"
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="显示图表窗口，仅 plot 命令有效（默认保存为文件）"
    )

    def _error(msg):
        print(f"\n错误: {msg}\n请运行 python main.py --help 查看帮助\n")
        sys.exit(2)
    parser.error = _error

    args = parser.parse_args()

    if args.command == "token":
        cmd_token(args)
        return

    if args.command == "clean":
        cmd_clean(args)
        return

    # 需要配置文件的命令
    if not os.path.exists(args.config):
        print(f"未找到 {args.config}，请先运行: python main.py token")
        return

    if args.command in ("verify",):
        cmd_verify(args)
        return

    setup_logging()

    commands = {"once": cmd_once, "schedule": cmd_schedule, "plot": cmd_plot, "status": cmd_status}
    cmd_func = commands.get(args.command)
    if cmd_func:
        cmd_func(args)


if __name__ == "__main__":
    main()
