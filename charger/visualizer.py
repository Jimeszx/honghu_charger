"""
数据可视化模块 - 生成充电功率变化曲线图（双 Y 轴版本）。
"""

import os
import platform
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


def _get_chinese_fonts() -> list:
    """根据操作系统返回中文字体优先级列表。"""
    system = platform.system()
    if system == "Windows":
        return ["SimHei", "Microsoft YaHei", "KaiTi", "FangSong"]
    elif system == "Darwin":  # macOS
        return ["PingFang SC", "Heiti SC", "STHeiti", "Arial Unicode MS"]
    else:  # Linux
        return [
            "WenQuanYi Micro Hei", "WenQuanYi Zen Hei",
            "Noto Sans CJK SC", "Noto Sans SC",
            "Droid Sans Fallback", "AR PL UMing CN",
        ]
    # 通用回退
    return ["SimHei", "Microsoft YaHei", "WenQuanYi Micro Hei",
            "Noto Sans CJK SC", "PingFang SC", "Arial Unicode MS", "DejaVu Sans"]


def _setup_chinese_font():
    """配置 matplotlib 中文字体，自动检测系统可用字体。"""
    import matplotlib
    import matplotlib.font_manager as fm

    # 清除字体缓存（解决 .ttc 字体不被识别的问题）
    try:
        fm._load_fontmanager(try_read_cache=False)
    except Exception:
        pass

    # 按系统优先级尝试查找可用中文字体
    preferred = _get_chinese_fonts()
    available = {f.name for f in fm.fontManager.ttflist}

    # 查找第一个可用的字体
    chosen = None
    for font_name in preferred:
        if font_name in available:
            chosen = font_name
            break

    # 如果列表中的字体都不可用，尝试从系统字体目录查找 .ttc/.ttf 文件
    if not chosen:
        font_dirs = [
            "/usr/share/fonts", "/usr/local/share/fonts",
            "/usr/share/fonts/opentype/noto",
            "/usr/share/fonts/truetype/noto",
            "/usr/share/fonts/truetype/wqy",
        ]
        cjk_patterns = ["NotoSansCJK", "NotoSerifCJK", "WenQuanYi",
                        "wqy-microhei", "wqy-zenhei", "DroidSansFallback"]
        for d in font_dirs:
            if not os.path.isdir(d):
                continue
            for f in os.listdir(d):
                fl = f.lower()
                if any(p.lower() in fl for p in cjk_patterns) and (f.endswith(".ttc") or f.endswith(".ttf")):
                    font_path = os.path.join(d, f)
                    try:
                        fe = fm.FontProperties(fname=font_path)
                        chosen = fe.get_name()
                        # 注册字体文件
                        fm.fontManager.addfont(font_path)
                        break
                    except Exception:
                        continue
            if chosen:
                break

    if chosen:
        matplotlib.rcParams["font.sans-serif"] = [chosen] + [f for f in preferred if f != chosen] + ["DejaVu Sans"]
    else:
        print("错误：未找到中文字体，无法生成图表。")
        print("请先安装中文字体：")
        print("  Debian/Ubuntu: apt install fonts-noto-cjk")
        print("  CentOS/RHEL:  yum install google-noto-sans-cjk-fonts")
        print("  Arch:         pacman -S noto-fonts-cjk")
        return False

    matplotlib.rcParams["axes.unicode_minus"] = False
    return True


class ChargeVisualizer:
    """充电数据可视化"""

    def __init__(self, db, output_dir: str = "./output/plots/", interactive: bool = False):
        """
        初始化可视化器。

        Args:
            db: ChargeDatabase 实例
            output_dir: 图表输出目录
            interactive: 是否使用交互式后端（用于 --show 显示窗口）
        """
        self.db = db
        self.output_dir = output_dir

        if not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        # 后端必须在 import pyplot 之前设置
        if interactive:
            import matplotlib
            matplotlib.use("TkAgg")

    def plot_power_curve(
        self,
        order_id: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        title: Optional[str] = None,
        output_filename: Optional[str] = None,
        show: bool = False
    ) -> str:
        """
        绘制充电功率变化曲线。

        Args:
            order_id: 按订单ID筛选
            start_time: 起始时间
            end_time: 结束时间
            title: 图表标题（自动生成如果为空）
            output_filename: 输出文件名（自动生成如果为空）
            show: 是否显示图表窗口

        Returns:
            生成的图表文件路径
        """
        try:
            import matplotlib.pyplot as plt
            import matplotlib.dates as mdates
        except ImportError:
            logger.error("需要安装 matplotlib: pip install matplotlib")
            return ""

        # 查询数据
        records = self.db.query_records(
            order_id=order_id,
            start_time=start_time,
            end_time=end_time,
            limit=100000
        )

        if not records:
            logger.warning("没有可绘制的数据")
            print("没有找到匹配的充电记录数据")
            return ""

        # 提取数据
        timestamps = []
        powers = []
        energies = []
        for r in records:
            ts = datetime.strptime(r["timestamp"], "%Y-%m-%d %H:%M:%S")
            timestamps.append(ts)
            powers.append(r["power_watts"])
            energies.append(r.get("energy_kwh"))

        # 设置中文字体
        if not _setup_chinese_font():
            return ""

        # 创建图表（双 Y 轴：功率 + 电量）
        fig, ax1 = plt.subplots(figsize=(14, 6))
        ax2 = ax1.twinx()

        # 绘制功率曲线（左 Y 轴）
        ax1.plot(timestamps, powers, color="#2196F3", linewidth=1.5, alpha=0.8, label="充电功率")
        ax1.fill_between(timestamps, powers, alpha=0.15, color="#2196F3")
        ax1.set_ylabel("功率 (W)", fontsize=12, color="#2196F3")
        ax1.tick_params(axis="y", labelcolor="#2196F3")

        # 绘制电量曲线（右 Y 轴）
        valid_energies = [(t, e) for t, e in zip(timestamps, energies) if e is not None]
        if valid_energies:
            e_times, e_vals = zip(*valid_energies)
            ax2.plot(e_times, e_vals, color="#FF9800", linewidth=2, linestyle="--", label="已充电量", zorder=2)
            ax2.set_ylabel("电量 (度/kWh)", fontsize=12, color="#FF9800")
            ax2.tick_params(axis="y", labelcolor="#FF9800")

        # 标记最大值和最小值
        if powers:
            max_power = max(powers)
            # 谷值排除 0 值（充电未开始或数据异常）
            valid_powers = [p for p in powers if p > 0]
            min_power = min(valid_powers) if valid_powers else 0
            avg_power = sum(powers) / len(powers)

            max_idx = powers.index(max_power)
            min_idx = powers.index(min_power) if min_power in powers else 0

            ax1.scatter([timestamps[max_idx]], [max_power], color="#F44336", s=80, zorder=5, label=f"峰值: {max_power:.0f}W")
            ax1.scatter([timestamps[min_idx]], [min_power], color="#4CAF50", s=80, zorder=5, label=f"谷值: {min_power:.0f}W")

            # 添加平均线
            ax1.axhline(y=avg_power, color="#9C27B0", linestyle="--", alpha=0.7, label=f"平均: {avg_power:.0f}W")

        # 设置标题和标签
        if not title:
            if order_id:
                title = f"充电功率 & 电量变化曲线 (订单: {order_id})"
            else:
                title = "充电功率 & 电量变化曲线"

        time_range = f"{timestamps[0].strftime('%m/%d %H:%M')} — {timestamps[-1].strftime('%m/%d %H:%M')}"
        ax1.set_title(f"{title}\n{time_range}", fontsize=14, fontweight="bold")
        ax1.set_xlabel("时间", fontsize=12)

        # 设置时间轴格式
        ax1.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        ax1.xaxis.set_major_locator(mdates.AutoDateLocator())
        fig.autofmt_xdate()

        # 添加网格
        ax1.grid(True, alpha=0.3, linestyle="--")

        # 合并两个轴的图例（放在 ax2 上，因为 ax2 始终在 ax1 之上）
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax2.legend(lines1 + lines2, labels1 + labels2, loc="upper right", fontsize=10,
                   framealpha=0.5)

        # 添加统计信息文本框
        final_energy = energies[-1] if energies and energies[-1] is not None else None
        stats_text = (
            f"数据点: {len(powers)}\n"
            f"采集时长: {(timestamps[-1] - timestamps[0]).total_seconds() / 60:.1f} 分钟\n"
            f"平均功率: {avg_power:.0f}W\n"
            f"峰值功率: {max_power:.0f}W\n"
            f"谷值功率: {min_power:.0f}W"
        )
        if final_energy is not None:
            stats_text += f"\n最终电量: {final_energy:.2f}度"

        ax2.text(
            0.02, 0.98, stats_text,
            transform=ax2.transAxes, fontsize=9,
            verticalalignment="top",
            bbox=dict(boxstyle="round,pad=0.5", facecolor="wheat", alpha=0.5)
        )

        plt.tight_layout()

        # 保存图表
        if not output_filename:
            output_filename = f"power_curve_{datetime.now().strftime('%Y%m%d')}.png"

        output_path = str(Path(self.output_dir) / output_filename)
        plt.savefig(output_path, dpi=330, bbox_inches="tight")
        logger.info(f"图表已保存到: {output_path}")

        if show:
            plt.show()
        else:
            plt.close()

        return output_path

    def plot_session_comparison(self, show: bool = False) -> str:
        """
        绘制多次充电会话的对比图。

        Args:
            show: 是否显示图表窗口

        Returns:
            生成的图表文件路径
        """
        try:
            import matplotlib.pyplot as plt
            import matplotlib.dates as mdates
        except ImportError:
            logger.error("需要安装 matplotlib")
            return ""

        sessions = self.db.get_sessions_summary()
        if not sessions or len(sessions) < 2:
            print("至少需要 2 次充电会话才能生成对比图")
            return ""

        # 设置中文字体
        if not _setup_chinese_font():
            return ""

        fig, axes = plt.subplots(1, 2, figsize=(14, 6))

        # 左图：各会话的峰值/平均/谷值功率对比
        labels = []
        max_powers = []
        avg_powers = []
        min_powers = []

        for s in sessions:
            short_id = s["order_id"][:8] if s["order_id"] else "?"
            labels.append(short_id)
            max_powers.append(s["max_power"])
            avg_powers.append(s["avg_power"])
            min_powers.append(s["min_power"])

        x = range(len(labels))
        width = 0.25

        axes[0].bar([i - width for i in x], max_powers, width, label="峰值", color="#F44336", alpha=0.8)
        axes[0].bar(x, avg_powers, width, label="平均", color="#FF9800", alpha=0.8)
        axes[0].bar([i + width for i in x], min_powers, width, label="谷值", color="#4CAF50", alpha=0.8)

        axes[0].set_xlabel("充电会话")
        axes[0].set_ylabel("功率 (W)")
        axes[0].set_title("各次充电功率对比")
        axes[0].set_xticks(list(x))
        axes[0].set_xticklabels(labels, rotation=45, ha="right")
        axes[0].legend()
        axes[0].grid(True, alpha=0.3, axis="y")

        # 右图：各会话的采集数据点数
        record_counts = [s["total_records"] for s in sessions]
        axes[1].bar(labels, record_counts, color="#2196F3", alpha=0.8)
        axes[1].set_xlabel("充电会话")
        axes[1].set_ylabel("采集数据点数")
        axes[1].set_title("各次充电数据采集量")
        axes[1].tick_params(axis="x", rotation=45)
        axes[1].grid(True, alpha=0.3, axis="y")

        plt.suptitle("充电会话对比分析", fontsize=14, fontweight="bold")
        plt.tight_layout()

        output_path = str(Path(self.output_dir) / f"session_comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
        plt.savefig(output_path, dpi=330, bbox_inches="tight")

        if show:
            plt.show()
        else:
            plt.close()

        return output_path
