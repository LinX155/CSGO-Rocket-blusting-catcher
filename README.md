<div align="center">

<h1>📈 CSGO饰品K线数据抓取工具&策略监测工具</h1>
<h3>🎯 悠悠有品：@全力一击</h3>

<p><strong>无需API Token，使用浏览器自动化技术抓取CSQAQ网站的饰品K线数据</strong></p>
<p>支持单ID抓取、批量抓取、数据库存储和量化分析</p>
<p>量化策略部分与策略程序的使用参见STRATEGY_GUIDE_V6_3STRATEGIES.md</p>

</div>

---

## 功能特点

- ✅ 无需注册或API Token
- ✅ 支持任意饰品ID
- ✅ 支持多平台数据（BUFF、悠悠有品、Steam）
- ✅ 支持多周期（日线、周线、1小时、4小时）
- ✅ **SQLite数据库存储** - 高效管理历史数据
- ✅ **批量抓取** - 基于压力测试的稳定方案
- ✅ **增量存储** - K线数据智能去重
- ✅ **补抓支持** - 失败ID可重复抓取并合并数据
- ✅ 自动保存为JSON和CSV格式（备份用）
- ✅ 全自动运行，无需人工干预

## 环境要求

- Python 3.8+
- Playwright

## 安装步骤

### 1. 安装Python依赖

```bash
pip install playwright
```

### 2. 安装浏览器

```bash
python -m playwright install chromium
```

## 项目架构

```
csgo饰品市场看盘工具搭建/
├── csqaq_scraper.py           # 单ID抓取程序
├── batch_scraper.py           # 批量抓取程序（生产级）
├── database.py                # SQLite数据库管理
├── csgo_monitor.db            # SQLite数据库（自动创建）
├── README.md                  # 本文件
├── DATABASE_GUIDE.md          # 数据字段详细说明与数据库使用指南
├── stress_test_report.md      # 压力测试报告
├── batch_data/                # 批量抓取数据（自动创建） 
│   ├── *.json                 # JSON格式备份
│   ├── *.csv                  # CSV格式备份
│   ├── batch_report_*.json    # 批量抓取报告
│   ├── failed_ids_*.txt       # 失败ID列表
│   └── *.log                  # 运行日志
└── ids.txt                    # ID列表
```

## 快速开始

### 场景1：抓取单个饰品

```bash
# 抓取商品ID为234的日线数据
python csqaq_scraper.py 234

# 抓取特定ID的周线数据
python csqaq_scraper.py 234 --period week

# 抓取悠悠有品平台数据
python csqaq_scraper.py 234 --platform YYYP
```

### 场景2：批量抓取多个饰品（推荐）

```bash
# 1. 创建ID列表文件
cat > ids.txt << EOF
234
6798
14135
14140
EOF

# 2. 执行批量抓取
python batch_scraper.py ids.txt

# 3. 查看数据库
sqlite3 csgo_monitor.db "SELECT name, buff_sell_price FROM items JOIN daily_snapshots ON items.id = daily_snapshots.item_id WHERE date = date('now');"
```

## 详细使用指南

### 一、单ID抓取（csqaq_scraper.py）

适用于抓取单个或少量的饰品数据。

#### 使用方法

```bash
python csqaq_scraper.py <goods_id> [选项]
```

#### 参数说明

| 参数 | 简写 | 说明 | 默认值 |
|------|------|------|--------|
| `goods_id` | - | **必填** 饰品ID | - |
| `--platform` | `-p` | 平台: BUFF或YYYP | BUFF |
| `--period` | `-t` | 周期: day/week/hour1/hour4 | day |
| `--output` | `-o` | 输出目录 | ./data |

#### 输出文件

```
data/
├── 234_AWP_二西莫夫_20250304_102130.json   # JSON格式原始数据
└── 234_AWP_二西莫夫_20250304_102130.csv    # CSV格式（可用Excel打开）
```

#### 示例

```bash
# 抓取蝴蝶刀（假设ID为6798）
python csqaq_scraper.py 6798

# 抓取1小时线数据用于日内交易分析
python csqaq_scraper.py 234 --period hour1

# 保存到指定目录
python csqaq_scraper.py 234 --output ./my_data
```

### 二、批量抓取（batch_scraper.py）【生产级】

基于压力测试结果的最保守稳定方案，支持数据库存储。

#### 核心特性

- ✅ **基于压力测试结果**: 采用最保守稳定方案
- ✅ **数据库存储**: 自动存储到SQLite，支持查询分析
- ✅ **失败自动重试**: 最多3次重试机制
- ✅ **分层休息机制**: 
  - 每30个ID休息60秒
  - 每90个ID深度休息10分钟
- ✅ **补抓支持**: 重复抓取自动更新数据
- ✅ **完整日志**: 记录每个ID的抓取状态
- ✅ **增量存储**: K线数据自动去重

#### 使用方法

```bash
python batch_scraper.py <id_file> [选项]
```

#### 参数说明

| 参数 | 简写 | 默认值 | 说明 |
|------|------|--------|------|
| `id_file` | - | - | **必填** ID列表文件路径 |
| `--output` | `-o` | ./batch_data | 输出目录（JSON/CSV备份） |
| `--platform` | `-p` | BUFF | 平台: BUFF 或 YYYP |
| `--period` | `-t` | day | 周期: day/week/hour1/hour4 |
| `--workers` | - | 1 | 并发线程数 |
| `--batch-size` | - | 1 | 每批次ID数量 |
| `--interval` | - | 5 | 批次间隔秒数 |

#### ID列表文件格式

创建文本文件，每行一个ID：

```
234
6798
14135
14140
14151
...
```

#### 完整工作流程

```bash
# 1. 准备ID列表
cat > my_ids.txt << EOF
234
6798
14135
14140
14151
EOF

# 2. 执行批量抓取
python batch_scraper.py ids.txt 

# 3. 查看结果
# - 数据库: csgo_monitor.db
# - 报告: batch_data/batch_report_*.json
# - 日志: batch_data/*.log

# 4. 如有失败，补抓
python batch_scraper.py batch_data/failed_ids_*.txt -o ./retry_data
```

#### 性能参考

当前配置（单线程，分层休息）：
- 单次抓取：约13秒
- 批次间隔：8秒
- 每30个ID休息：60秒
- 每90个ID深度休息：10分钟
- **400个ID预计耗时：约3小时分钟**

### 三、数据库存储（SQLite）

批量抓取程序会自动将数据存储到SQLite数据库，便于查询和分析。

#### 数据库表结构

**1. items - 饰品基本信息表**
```sql
id, name, market_hash_name, rarity, type, exterior
buff_id, yyyp_id, created_at, updated_at
```

**2. daily_snapshots - 每日截面数据表**
```sql
id, item_id, date, fetch_time
buff_sell_price, buff_buy_price, buff_sell_num, buff_buy_num
yyyp_sell_price, yyyp_buy_price, yyyp_sell_num
sell_price_rate_1, sell_price_rate_7, sell_price_rate_30
statistic, rank_num, turnover_number
raw_data  -- 原始JSON数据
```

**3. kline_data - K线数据表（增量存储）**
```sql
id, item_id, timestamp, open, close, high, low, volume
```

**4. fetch_logs - 抓取日志表**
```sql
id, item_id, status, error_msg, retry_count, elapsed_time, fetched_at
```

#### 常用查询示例

```python
import sqlite3
import pandas as pd

conn = sqlite3.connect('csgo_monitor.db')

# 查询今日所有饰品价格
df = pd.read_sql_query("""
    SELECT i.name, s.buff_sell_price, s.sell_price_rate_7, s.statistic
    FROM daily_snapshots s
    JOIN items i ON i.id = s.item_id
    WHERE s.date = date('now')
    ORDER BY s.buff_sell_price DESC
""", conn)

# 查询某饰品历史趋势
df = pd.read_sql_query("""
    SELECT date, buff_sell_price, buff_sell_num, sell_price_rate_7
    FROM daily_snapshots
    WHERE item_id = 234
    ORDER BY date DESC
    LIMIT 30
""", conn)

# 找出涨幅异常的品（近7天涨幅>10%）
df = pd.read_sql_query("""
    SELECT i.name, s.buff_sell_price, s.sell_price_rate_7
    FROM daily_snapshots s
    JOIN items i ON i.id = s.item_id
    WHERE s.date = date('now')
      AND s.sell_price_rate_7 > 10
    ORDER BY s.sell_price_rate_7 DESC
""", conn)
```

详细的数据库使用指南请查看 [DATABASE_GUIDE.md](./DATABASE_GUIDE.md)

## 数据字段说明

抓取的数据包含以下主要字段：

### 基础信息
| 字段 | 说明 | 示例 |
|------|------|------|
| `id` | CSQAQ内部饰品ID | 234 |
| `name` | 饰品中文名称 | AWP \| 二西莫夫 (战痕累累) |
| `market_hash_name` | Steam市场标准名称 | AWP \| Asiimov (Battle-Scarred) |
| `rarity_localized_name` | 稀有度 | 隐秘 |
| `type_localized_name` | 武器类型 | 步枪 |
| `exterior_localized_name` | 磨损度 | 战痕累累 |
| `statistic` | 存世量 | 67242 |

### BUFF平台数据
| 字段 | 说明 | 示例 |
|------|------|------|
| `buff_sell_price` | 最低售价(元) | 574.49 |
| `buff_buy_price` | 最高求购价(元) | 571.00 |
| `buff_sell_num` | 在售数量 | 741 |
| `buff_buy_num` | 求购数量 | 104 |

### 涨跌幅数据
| 字段 | 说明 | 示例 |
|------|------|------|
| `sell_price_rate_7` | 7天涨跌幅(%) | 0.11 |
| `sell_price_rate_30` | 30天涨跌幅(%) | 4.55 |
| `sell_price_rate_90` | 90天涨跌幅(%) | 9.63 |

完整的数据字段说明请查看 [data_fields_guide.md](./data_fields_guide.md)

## 补抓机制

当批量抓取出现失败时，程序会自动生成失败ID列表，支持补抓：

```bash
# 第一次抓取
python batch_scraper.py ids.txt -o ./batch_data

# 自动生成的失败列表
ls batch_data/failed_ids_*.txt

# 补抓失败的ID
python batch_scraper.py batch_data/failed_ids_20250304_102130.txt -o ./retry_data

# 数据自动合并到数据库（更新已有记录）
```

**数据合并规则**：
- `items` 表：INSERT OR UPDATE（更新基础信息）
- `daily_snapshots` 表：INSERT OR REPLACE（替换当日数据）
- `kline_data` 表：INSERT OR IGNORE（避免重复）
- `fetch_logs` 表：INSERT（新增日志记录）

## 压力测试结果

详细的性能测试结果请查看 [stress_test_report.md](./stress_test_report.md)

### 核心结论

| 指标 | 数值 |
|------|------|
| 单次抓取耗时 | 12-13秒 |
| 最小抓取间隔 | 0秒可行，建议1-2秒 |
| 最大多开数量 | 3线程（成功率90%） |
| 推荐多开数量 | 2线程（成功率100%） |
| 每小时抓取量 | 270-540个ID |

## 如何获取饰品ID

1. 打开 https://csqaq.com
2. 搜索你想要的饰品（如"蝴蝶刀"）
3. 进入饰品详情页
4. 查看URL中的数字，例如：`csqaq.com/goods/234` 中的 `234`

## 常见问题

### Q: 程序需要多久运行一次？
A: 数据每天更新一次即可。建议每天定时运行抓取最新数据。

### Q: 会被网站封禁吗？
A: 本工具使用浏览器自动化技术，模拟真实用户行为。已加入分层休息机制降低风险：
- 批次间隔5秒
- 每30个ID休息60秒
- 每90个ID深度休息10分钟
- 不要同时运行多个抓取任务

### Q: 数据库文件会很大吗？
A: 不会。采用增量存储策略：
- K线数据自动去重
- 每日截面数据只保留最新
- 100个ID运行一年约100-200MB

### Q: 支持哪些饰品？
A: 支持CSQAQ网站上所有的CSGO/CS2饰品。

### Q: 抓取的数据有多长历史？
A: 每次抓取返回约150条K线数据，约5个月左右的历史。数据库存储可以累积历史。

## 数据备份

```bash
# 备份SQLite数据库
cp csgo_monitor.db csgo_monitor_backup_$(date +%Y%m%d).db

# 或使用SQLite命令备份
sqlite3 csgo_monitor.db ".backup 'csgo_monitor_backup.db'"
```

## 开发计划

- [x] 单ID抓取
- [x] 批量抓取
- [x] SQLite数据库存储
- [x] 补抓机制
- [x] 分层休息保护
- [ ] 量化策略模块
- [ ] 实时监控告警
- [ ] Web可视化界面

## 免责声明

本工具仅供学习研究使用，请勿用于商业用途。使用本工具所产生的法律责任由使用者自行承担。

## 更新日志

- 2025-03-04: 初始版本，支持单ID抓取
- 2025-03-04: 新增批量抓取程序，基于压力测试结果优化
- 2025-03-04: 新增SQLite数据库存储，支持增量存储和补抓
- 2025-03-04: 新增分层休息机制（30个/90个ID）
- 2025-03-04: 新增数据字段说明文档

## License

MIT License

---

**提示**: 详细的数据库使用指南请查看 [DATABASE_GUIDE.md](./DATABASE_GUIDE.md)，数据字段说明请查看 [data_fields_guide.md](./data_fields_guide.md)。
