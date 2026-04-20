# 鸿鹄智充 - 充电功率数据自动采集工具

> 本项目由 [TRAE SOLO](https://solo.trae.ai/) 协助完成。

由于鸿鹄智充公众号内无法查看充电功率随时间变化的曲线，也无法获取更详细的充电数据统计，因此开发了此项目，通过自动化采集充电过程中的功率和电量数据，生成可视化图表，帮助用户更好地了解充电情况。

通过 Python 脚本自动获取微信公众号"鸿鹄智充"中电动车实时充电功率和电量数据，生成变化曲线图。

## 快速开始

```bash
# 1. 创建虚拟环境
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# 2. 安装依赖
pip install -r requirements.txt

# 3. 获取 Token（每天充电前运行一次）
python main.py token

# 4. 开始采集
python main.py schedule
```

## 命令

| 命令 | 说明 |
|------|------|
| `python main.py token` | 获取 JWT Token（微信中打开链接 → 粘贴跳转 URL） |
| `python main.py verify` | 验证 API 连接和 Token 有效性 |
| `python main.py once` | 单次采集 |
| `python main.py schedule` | 持续采集（默认 5 分钟间隔） |
| `python main.py schedule -i 60` | 自定义采集间隔（秒） |
| `python main.py plot` | 生成功率/电量变化曲线图 |
| `python main.py clean` | 清理数据库、日志和图表 |
| `python main.py status` | 查看采集状态 |

运行 `python main.py -h` 可查看完整的命令用法和参数说明。

## 目录结构

```
honghu_charger/
├── main.py              # 唯一入口
├── charger/             # 核心代码
├── docs/                # 文档
│   └── capture_guide.md # 抓包指南（记录 API 逆向分析过程，仅供学习参考）
└── output/              # 输出（配置、数据库、日志、图表）
    ├── config.yaml      # 动态配置（由 token 命令自动管理）
    ├── data/            # charge_data.db, collector.log
    └── plots/           # *.png 图表
```

## 注意事项

- **Token 有效期 24 小时**，过期后重新运行 `python main.py token`
- **数据更新频率约 5 分钟**，默认采集间隔已设为 300 秒
- **config.yaml 不需要手动编辑**，`token` 命令会自动创建和更新
