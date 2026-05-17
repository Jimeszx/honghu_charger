"""
定时采集调度器 - 按固定间隔循环执行数据采集。
"""

import time
import signal
import logging
from datetime import datetime
from typing import Optional, Callable

from charger.storage import ChargeDatabase
from charger.collector import CollectResult

logger = logging.getLogger(__name__)


class ChargeScheduler:
    """充电数据定时采集调度器"""

    def __init__(
        self,
        collector,
        db: ChargeDatabase,
        interval: int = 30,
        on_collect: Optional[Callable[[CollectResult], None]] = None
    ):
        """
        初始化调度器。

        Args:
            collector: 采集器实例（BaseCollector 子类）
            db: 数据库实例
            interval: 采集间隔（秒）
            on_collect: 每次采集完成后的回调函数
        """
        self.collector = collector
        self.db = db
        self.interval = interval
        self.on_collect = on_collect
        self._running = False
        self._stats = {
            "total": 0,
            "success": 0,
            "failed": 0,
            "start_time": None,
            "last_success_time": None,
        }

        # 注册信号处理（优雅退出）
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """处理 Ctrl+C 等中断信号"""
        print("\n收到中断信号，正在停止采集...")
        self._running = False

    def collect_once(self) -> CollectResult:
        """
        执行一次采集并存储到数据库。

        Returns:
            CollectResult
        """
        result = self.collector.collect()

        self._stats["total"] += 1

        if result.success:
            self._stats["success"] += 1
            self._stats["last_success_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 存储到数据库（使用服务器时间）
            record_id = self.db.insert_record(
                power_watts=result.power_watts,
                order_id=result.order_id,
                raw_data=result.raw_data,
                collector_mode=result.collector_mode,
                energy_kwh=result.energy_kwh,
                timestamp=result.server_time,
            )

            logger.info(
                f"[#{self._stats['total']}] 成功 | 功率: {result.power_watts}W"
                + (f" | {result.energy_kwh:.2f}度" if result.energy_kwh is not None else "")
                + f" | 订单: {result.order_id or '-'} | 记录ID: {record_id}"
            )
        else:
            self._stats["failed"] += 1
            logger.warning(
                f"[#{self._stats['total']}] 失败 | {result.error_message}"
            )

        # 执行回调
        if self.on_collect:
            self.on_collect(result)

        return result

    def run(self, max_iterations: Optional[int] = None):
        """
        启动定时采集循环。

        Args:
            max_iterations: 最大采集次数（None 表示无限循环）
        """
        self._running = True
        self._stats["start_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        print("=" * 60)
        print("鸿鹄智充 - 充电功率自动采集")
        print("=" * 60)
        print(f"  采集模式: {self.collector.__class__.__name__}")
        print(f"  采集间隔: {self.interval} 秒")
        print(f"  开始时间: {self._stats['start_time']}")
        if max_iterations:
            print(f"  采集次数: {max_iterations} 次后自动停止")
        else:
            print(f"  采集次数: 持续运行（按 Ctrl+C 停止）")
        print("=" * 60)
        print()

        iteration = 0
        charge_ended = False
        pending_retry = False  # 等待重试状态

        while self._running:
            if max_iterations and iteration >= max_iterations:
                print(f"\n已完成 {max_iterations} 次采集，自动停止。")
                break

            iteration += 1
            result = self.collect_once()

            if result.success:
                charge_ended = False
                pending_retry = False
            else:
                # 区分"充电结束"和"其他错误"
                msg = result.error_message or ""
                if "order_list 为空" in msg or "没有正在充电" in msg:
                    if pending_retry:
                        # 60秒后重试仍然失败，确认充电结束
                        print(f"\n充电完成，自动停止采集。")
                        # 回滚上一次失败的统计（这不是真正的采集失败）
                        self._stats["failed"] -= 1
                        self._stats["total"] -= 1
                        break
                    else:
                        # 首次遇到 order_list 为空，等待 60 秒后重试
                        pending_retry = True
                        # 等待 60 秒（每秒检查中断信号）
                        waited = 0
                        while waited < 60 and self._running:
                            sleep_chunk = min(1, 60 - waited)
                            time.sleep(sleep_chunk)
                            waited += sleep_chunk
                        continue  # 跳过正常间隔，立即重试
                elif "HTTP 401" in msg or "认证失败" in msg:
                    print(f"\nToken 已失效，请运行 python main.py token 重新获取。")
                    break

            # 等待下一次采集（每秒检查中断信号，实现即时响应）
            if self._running and (not max_iterations or iteration < max_iterations):
                next_time = datetime.now().timestamp() + self.interval
                next_str = datetime.fromtimestamp(next_time).strftime("%H:%M:%S")
                print(f"  下次采集: {next_str} (间隔 {self.interval}s)")
                waited = 0
                while waited < self.interval and self._running:
                    sleep_chunk = min(1, self.interval - waited)
                    time.sleep(sleep_chunk)
                    waited += sleep_chunk

        self._print_summary()

    def _print_summary(self):
        """打印采集统计摘要"""
        print()
        print("=" * 60)
        print("采集统计摘要")
        print("=" * 60)
        print(f"  开始时间:     {self._stats['start_time']}")
        print(f"  结束时间:     {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  总采集次数:   {self._stats['total']}")
        print(f"  成功次数:     {self._stats['success']}")
        print(f"  失败次数:     {self._stats['failed']}")
        if self._stats['total'] > 0:
            rate = self._stats['success'] / self._stats['total'] * 100
            print(f"  成功率:       {rate:.1f}%")
        print(f"  最后成功时间: {self._stats['last_success_time'] or '-'}")
        print("=" * 60)
