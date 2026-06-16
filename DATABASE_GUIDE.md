# CSGO饰品市场监控 - 完整技术文档

> **本文档是项目最核心的技术参考文档**
> 
> 包含：数据库Schema + 完整字段映射 + 详细说明 + 查询示例

---

## 一、完整字段映射表

### 映射格式：原始字段名 → 中文含义 → 数据库表 → 数据库字段名

---

### 1. 饰品基础信息

| 原始字段 | 中文含义 | 数据库表 | 数据库字段 | 类型 | 示例 |
|---------|---------|---------|-----------|------|------|
| `id` | CSQAQ内部ID | `items` | `id` | INTEGER | 234 |
| `name` | 饰品中文名称 | `items` | `name` | TEXT | "AWP \| 二西莫夫" |
| `market_hash_name` | Steam标准名称 | `items` | `market_hash_name` | TEXT | "AWP \| Asiimov" |
| `type_localized_name` | 武器类型 | `items` | `type` | TEXT | "步枪" |
| `rarity_localized_name` | 稀有度 | `items` | `rarity` | TEXT | "隐秘" |
| `exterior_localized_name` | 磨损度 | `items` | `exterior` | TEXT | "战痕累累" |
| `buff_id` | BUFF平台ID | `items` | `buff_id` | INTEGER | 34065 |
| `yyyp_id` | YYYP平台ID | `items` | `yyyp_id` | INTEGER | 270 |
| `statistic` | 存世量 | `daily_snapshots` | `statistic` | INTEGER | 67242 |
| `def_index` | 武器定义索引 | `items` | `def_index` | INTEGER | 9 |
| `paint_index` | 涂装索引 | `items` | `paint_index` | INTEGER | 279 |
| `min_float` | 最小磨损 | `items` | `min_float` | REAL | 0.45 |
| `max_float` | 最大磨损 | `items` | `max_float` | REAL | 1.0 |

---

### 2. BUFF平台数据

| 原始字段 | 中文含义 | 数据库表 | 数据库字段 | 类型 | 示例 |
|---------|---------|---------|-----------|------|------|
| `buff_sell_price` | BUFF售价 | `daily_snapshots` | `buff_sell_price` | REAL | 574.49 |
| `buff_buy_price` | BUFF求购价 | `daily_snapshots` | `buff_buy_price` | REAL | 571.00 |
| `buff_sell_num` | BUFF在售数 | `daily_snapshots` | `buff_sell_num` | INTEGER | 741 |
| `buff_buy_num` | BUFF求购数 | `daily_snapshots` | `buff_buy_num` | INTEGER | 104 |

---

### 3. YYYP平台数据

| 原始字段 | 中文含义 | 数据库表 | 数据库字段 | 类型 | 示例 |
|---------|---------|---------|-----------|------|------|
| `yyyp_sell_price` | YYYP售价 | `daily_snapshots` | `yyyp_sell_price` | REAL | 577.50 |
| `yyyp_buy_price` | YYYP求购价 | `daily_snapshots` | `yyyp_buy_price` | REAL | 576.00 |
| `yyyp_sell_num` | YYYP在售数 | `daily_snapshots` | `yyyp_sell_num` | INTEGER | 519 |
| `yyyp_buy_num` | YYYP求购数 | `daily_snapshots` | `yyyp_buy_num` | INTEGER | 21 |
| `yyyp_lease_num` | 可租赁数 | `daily_snapshots` | `yyyp_lease_num` | INTEGER | 171 |
| `yyyp_lease_price` | 短租价格 | `daily_snapshots` | `yyyp_lease_price` | REAL | 0.07 |
| `yyyp_lease_annual` | 短租年化% | `daily_snapshots` | `yyyp_lease_annual` | REAL | 2.33 |

---

### 4. Steam平台数据

| 原始字段 | 中文含义 | 数据库表 | 数据库字段 | 类型 | 示例 |
|---------|---------|---------|-----------|------|------|
| `steam_sell_price` | Steam售价 | `daily_snapshots` | `steam_sell_price` | REAL | 820.35 |
| `steam_buy_price` | Steam求购价 | `daily_snapshots` | `steam_buy_price` | REAL | 760.54 |

---

### 5. 涨跌幅数据

| 原始字段 | 中文含义 | 数据库表 | 数据库字段 | 类型 | 示例 |
|---------|---------|---------|-----------|------|------|
| `sell_price_rate_1` | 1天涨跌% | `daily_snapshots` | `sell_price_rate_1` | REAL | -0.31 |
| `sell_price_rate_7` | 7天涨跌% | `daily_snapshots` | `sell_price_rate_7` | REAL | 0.11 |
| `sell_price_rate_30` | 30天涨跌% | `daily_snapshots` | `sell_price_rate_30` | REAL | 4.55 |
| `yyyp_sell_price_rate_1` | YYYP 1天涨跌% | `daily_snapshots` | `yyyp_sell_price_rate_1` | REAL | 0.44 |
| `yyyp_sell_price_rate_7` | YYYP 7天涨跌% | `daily_snapshots` | `yyyp_sell_price_rate_7` | REAL | 2.23 |
| `yyyp_sell_price_rate_15` | YYYP 15天涨跌% | `daily_snapshots` | `yyyp_sell_price_rate_15` | REAL | 3.87 |

---

### 6. 市场热度数据

| 原始字段 | 中文含义 | 数据库表 | 数据库字段 | 类型 | 示例 |
|---------|---------|---------|-----------|------|------|
| `rank_num` | 热门排名 | `daily_snapshots` | `rank_num` | INTEGER | 1585 |
| `rank_num_change` | 排名变化 | `daily_snapshots` | `rank_num_change` | INTEGER | 297 |
| `turnover_number` | 近期成交数 | `daily_snapshots` | `turnover_number` | INTEGER | 28 |
| `turnover_avg_price` | 近期成交均价 | `daily_snapshots` | `turnover_avg_price` | REAL | 90.71 |

---

### 7. 挂刀比例数据

| 原始字段 | 中文含义 | 数据库表 | 数据库字段 | 类型 | 示例 |
|---------|---------|---------|-----------|------|------|
| `steam_buff_sell_conversion` | Steam卖/BUFF卖 | `daily_snapshots` | `steam_buff_sell_conversion` | REAL | 0.70 |
| `buff_steam_sell_conversion` | BUFF卖/Steam卖 | `daily_snapshots` | `buff_steam_sell_conversion` | REAL | 0.81 |

---

### 8. K线数据

| 原始字段 | 中文含义 | 数据库表 | 数据库字段 | 类型 | 示例 |
|---------|---------|---------|-----------|------|------|
| `t` | 时间戳 | `kline_data` | `timestamp` | INTEGER | 1746720000000 |
| `o` | 开盘价 | `kline_data` | `open` | REAL | 545.0 |
| `c` | 收盘价 | `kline_data` | `close` | REAL | 539.0 |
| `h` | 最高价 | `kline_data` | `high` | REAL | 545.0 |
| `l` | 最低价 | `kline_data` | `low` | REAL | 538.5 |
| `v` | 成交量 | `kline_data` | `volume` | INTEGER | 28 |

---

## 二、数据表结构

### 1. items表

```sql
CREATE TABLE items (
    id INTEGER PRIMARY KEY,              -- 原始: id
    name TEXT,                            -- 原始: name
    market_hash_name TEXT,                -- 原始: market_hash_name
    rarity TEXT,                          -- 原始: rarity_localized_name
    type TEXT,                            -- 原始: type_localized_name
    exterior TEXT,                        -- 原始: exterior_localized_name
    buff_id INTEGER,                      -- 原始: buff_id
    yyyp_id INTEGER,                      -- 原始: yyyp_id
    def_index INTEGER,                    -- 原始: def_index
    paint_index INTEGER,                  -- 原始: paint_index
    min_float REAL,                       -- 原始: min_float
    max_float REAL,                       -- 原始: max_float
    img TEXT,                             -- 原始: img
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

### 2. daily_snapshots表

```sql
CREATE TABLE daily_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER,
    date DATE,
    fetch_time TIMESTAMP,
    
    -- BUFF价格
    buff_sell_price REAL,                 -- 原始: buff_sell_price
    buff_buy_price REAL,                  -- 原始: buff_buy_price
    buff_sell_num INTEGER,                -- 原始: buff_sell_num
    buff_buy_num INTEGER,                 -- 原始: buff_buy_num
    
    -- YYYP价格
    yyyp_sell_price REAL,                 -- 原始: yyyp_sell_price
    yyyp_buy_price REAL,                  -- 原始: yyyp_buy_price
    yyyp_sell_num INTEGER,                -- 原始: yyyp_sell_num
    yyyp_buy_num INTEGER,                 -- 原始: yyyp_buy_num
    
    -- Steam价格
    steam_sell_price REAL,                -- 原始: steam_sell_price
    steam_buy_price REAL,                 -- 原始: steam_buy_price
    
    -- YYYP租赁
    yyyp_lease_num INTEGER,               -- 原始: yyyp_lease_num
    yyyp_lease_price REAL,                -- 原始: yyyp_lease_price
    yyyp_lease_annual REAL,               -- 原始: yyyp_lease_annual
    
    -- 涨跌幅
    sell_price_rate_1 REAL,               -- 原始: sell_price_rate_1
    sell_price_rate_7 REAL,               -- 原始: sell_price_rate_7
    sell_price_rate_30 REAL,              -- 原始: sell_price_rate_30
    yyyp_sell_price_rate_1 REAL,          -- 原始: yyyp_sell_price_rate_1
    yyyp_sell_price_rate_7 REAL,          -- 原始: yyyp_sell_price_rate_7
    yyyp_sell_price_rate_15 REAL,         -- 原始: yyyp_sell_price_rate_15
    
    -- 市场数据
    statistic INTEGER,                    -- 原始: statistic
    rank_num INTEGER,                     -- 原始: rank_num
    rank_num_change INTEGER,              -- 原始: rank_num_change
    turnover_number INTEGER,              -- 原始: turnover_number
    turnover_avg_price REAL,              -- 原始: turnover_avg_price
    
    -- 挂刀比例
    steam_buff_sell_conversion REAL,      -- 原始: steam_buff_sell_conversion
    buff_steam_sell_conversion REAL,      -- 原始: buff_steam_sell_conversion
    
    raw_data TEXT,
    
    UNIQUE(item_id, date),
    FOREIGN KEY (item_id) REFERENCES items(id)
);
```

### 3. kline_data表

```sql
CREATE TABLE kline_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER,
    timestamp INTEGER,                    -- 原始: t
    open REAL,                            -- 原始: o
    close REAL,                           -- 原始: c
    high REAL,                            -- 原始: h
    low REAL,                             -- 原始: l
    volume INTEGER,                       -- 原始: v
    fetched_at TIMESTAMP,
    
    UNIQUE(item_id, timestamp),
    FOREIGN KEY (item_id) REFERENCES items(id)
);
```

---

## 三、常用查询

### 查看今日数据（多平台对比）

```sql
SELECT 
    i.name,
    s.buff_sell_price,
    s.yyyp_sell_price,
    s.steam_sell_price,
    s.statistic,
    s.rank_num_change,
    s.yyyp_lease_annual
FROM daily_snapshots s
JOIN items i ON i.id = s.item_id
WHERE s.date = date('now');
```

### 获取K线数据（策略计算）

```sql
SELECT timestamp, open, close, high, low, volume
FROM kline_data
WHERE item_id = 234
ORDER BY timestamp DESC
LIMIT 60;
```

### 平台价差套利查询

```sql
SELECT 
    i.name,
    s.buff_sell_price,
    s.yyyp_sell_price,
    ROUND((s.yyyp_sell_price - s.buff_sell_price) / s.buff_sell_price * 100, 2) as diff_pct
FROM daily_snapshots s
JOIN items i ON i.id = s.item_id
WHERE s.date = date('now')
  AND ABS(s.yyyp_sell_price - s.buff_sell_price) / s.buff_sell_price > 0.05;
```

---

## 四、数据维护

### 备份
```bash
sqlite3 csgo_monitor.db ".backup 'backup.db'"
```

### 清理日志
```bash
sqlite3 csgo_monitor.db "DELETE FROM fetch_logs WHERE fetched_at < date('now', '-30 days');"
```

---

**文档版本**: V1.0 完整技术文档  
**最后更新**: 2025-03-04
