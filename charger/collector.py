"""
数据采集器 - 合并原 base.py 和 requests_collector.py，去除 playwright 引用。
"""

import requests
import logging
import warnings
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, Any

# 禁用 SSL 不验证警告（该平台证书链不完整）
warnings.filterwarnings("ignore", message="Unverified HTTPS request")

logger = logging.getLogger(__name__)


@dataclass
class CollectResult:
    """采集结果数据类"""
    success: bool
    power_watts: Optional[float] = None
    energy_kwh: Optional[float] = None
    order_id: Optional[str] = None
    raw_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    collector_mode: str = "unknown"
    server_time: Optional[str] = None  # 从 API 数据计算的服务器时间

    def __str__(self):
        if self.success:
            energy_str = f" | 电量: {self.energy_kwh:.2f}度" if self.energy_kwh is not None else ""
            return f"[成功] 功率: {self.power_watts}W{energy_str} | 订单: {self.order_id or '未知'}"
        return f"[失败] {self.error_message}"


class BaseCollector(ABC):
    """采集器抽象基类"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config

    @abstractmethod
    def collect(self) -> CollectResult:
        raise NotImplementedError

    def _extract_nested_field(self, data: Dict, field_path: str) -> Any:
        """
        从嵌套字典/列表中按点号分隔的路径提取值。
        支持字典键和列表索引，例如:
          "api_objects.0.order_list.0.power" 表示 data["api_objects"][0]["order_list"][0]["power"]
        """
        keys = field_path.split(".")
        current = data
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            elif isinstance(current, list):
                try:
                    index = int(key)
                    current = current[index]
                except (ValueError, IndexError):
                    return None
            else:
                return None
        return current


class RequestsCollector(BaseCollector):
    """基于 requests 的 API 采集器"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        api_config = config.get("api", {})

        self.api_url = api_config.get("url", "")
        self.method = api_config.get("method", "POST").upper()
        self.headers = api_config.get("headers", {})
        self.body = api_config.get("body", {})
        self.power_field = api_config.get("power_field", "api_objects.0.order_list.0.power")
        self.order_id_field = api_config.get("order_id_field", None)
        self.energy_field = api_config.get("energy_field", "api_objects.0.order_list.0.energy_consumed")

        # 创建 session
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.session.verify = False  # 该平台证书链不完整，需跳过 SSL 验证

        # 验证配置
        if not self.api_url:
            logger.warning("未配置 api.url，请先运行 python main.py token")

    def collect(self) -> CollectResult:
        """执行一次 API 请求采集。"""
        if not self.api_url:
            return CollectResult(
                success=False,
                error_message="未配置 API URL，请先运行 python main.py token",
                collector_mode="requests"
            )

        try:
            logger.debug(f"正在请求: {self.method} {self.api_url}")

            if self.method == "GET":
                resp = self.session.get(self.api_url, timeout=15)
            elif self.method == "POST":
                resp = self.session.post(
                    self.api_url,
                    json=self.body if self.body else None,
                    timeout=15
                )
            else:
                return CollectResult(
                    success=False,
                    error_message=f"不支持的请求方法: {self.method}",
                    collector_mode="requests"
                )

            # 检查 HTTP 状态码
            if resp.status_code != 200:
                return CollectResult(
                    success=False,
                    error_message=f"HTTP {resp.status_code}: {resp.text[:200]}",
                    collector_mode="requests"
                )

            # 解析 JSON 响应
            try:
                data = resp.json()
            except ValueError:
                return CollectResult(
                    success=False,
                    error_message=f"响应不是有效的 JSON: {resp.text[:200]}",
                    collector_mode="requests"
                )

            logger.debug(f"API 响应: {data}")

            # 检查是否有充电订单
            order_list = data.get("api_objects", [{}])[0].get("order_list", [])
            if not order_list:
                return CollectResult(
                    success=False,
                    error_message="当前没有正在充电的订单（order_list 为空）",
                    raw_data=data,
                    collector_mode="requests"
                )

            # 提取功率值
            power_value = self._extract_nested_field(data, self.power_field)
            if power_value is None:
                return CollectResult(
                    success=False,
                    error_message=f"无法从响应中提取功率值 (路径: {self.power_field})，响应内容: {str(data)[:300]}",
                    raw_data=data,
                    collector_mode="requests"
                )

            # 尝试转换为浮点数
            try:
                power_watts = float(power_value)
            except (TypeError, ValueError):
                return CollectResult(
                    success=False,
                    error_message=f"功率值无法转换为数字: {power_value}",
                    raw_data=data,
                    collector_mode="requests"
                )

            # 提取订单ID（可选）
            order_id = None
            if self.order_id_field:
                order_id = self._extract_nested_field(data, self.order_id_field)
                if order_id:
                    order_id = str(order_id)

            # 提取已充电量（energy_consumed 单位为 Wh，除以 1000 得 kWh/度）
            energy_kwh = None
            energy_raw = self._extract_nested_field(data, self.energy_field)
            if energy_raw is not None:
                try:
                    energy_kwh = float(energy_raw) / 1000.0
                except (TypeError, ValueError):
                    pass

            # 从 API 数据计算服务器时间（begin_time + time_consumed_sec）
            server_time = None
            begin_time_str = self._extract_nested_field(data, "api_objects.0.order_list.0.begin_time")
            time_consumed = self._extract_nested_field(data, "api_objects.0.order_list.0.time_consumed_sec")
            if begin_time_str and time_consumed is not None:
                try:
                    from datetime import datetime as dt, timedelta
                    bt = dt.strptime(begin_time_str, "%Y-%m-%d %H:%M:%S")
                    server_time = (bt + timedelta(seconds=int(time_consumed))).strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    pass

            logger.debug(
                f"采集成功: {power_watts}W | {energy_kwh:.2f}度"
                if energy_kwh is not None else f"采集成功: {power_watts}W"
            )

            return CollectResult(
                success=True,
                power_watts=power_watts,
                energy_kwh=energy_kwh,
                order_id=order_id,
                raw_data=data,
                collector_mode="requests",
                server_time=server_time,
            )

        except requests.exceptions.Timeout:
            return CollectResult(
                success=False,
                error_message="请求超时（15秒）",
                collector_mode="requests"
            )
        except requests.exceptions.ConnectionError as e:
            return CollectResult(
                success=False,
                error_message=f"连接失败: {str(e)[:200]}",
                collector_mode="requests"
            )
        except Exception as e:
            logger.exception("采集过程中发生异常")
            return CollectResult(
                success=False,
                error_message=f"未知异常: {str(e)[:200]}",
                collector_mode="requests"
            )

    def test_connection(self) -> bool:
        """测试 API 连接是否正常"""
        result = self.collect()
        if result.success:
            print(f"连接测试成功！当前功率: {result.power_watts}W")
        else:
            print(f"连接测试失败: {result.error_message}")
        return result.success
