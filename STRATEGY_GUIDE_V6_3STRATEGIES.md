# 异动识别系统 V6（当前有效版 / README）

> 本文档是当前唯一有效的策略与工具说明。  
> 目标：每天识别“当天最新”是否触发异动；同时支持历史回测辅助验证。

---

## 1. 当前系统范围

当前系统由两部分组成：

1. **策略规则（3个）**：全部基于 `kline_data`（日线 OHLCV）触发
2. **识别工具**：`anomaly_detector.py`
   - `current`：只检测每个标的“最新一根日线”
   - `backtest`：按历史K线逐日回放触发情况

### 明确边界

- 核心触发只使用：`kline_data(timestamp, open, high, low, close, volume)`
- `daily_snapshots` 只用于告警补充展示，不参与触发开关
- 不提供写库功能（不写 `strategy_signals`）
- 输出为 JSON 报告

---

## 2. 数据依赖（与数据库一致）

### 2.1 必需表
- `kline_data`：核心策略计算
- `items`：读取 `item_name`
- `daily_snapshots`：辅助参数展示

### 2.2 核心触发最小字段
- `kline_data.item_id`
- `kline_data.timestamp`
- `kline_data.open`
- `kline_data.high`
- `kline_data.low`
- `kline_data.close`
- `kline_data.volume`

### 2.3 辅助展示字段（可为空）
- `turnover_number`, `rank_num`, `yyyp_lease_annual`
- `buff_sell_price`, `yyyp_sell_price`, `steam_sell_price`
- `yyyp_buy_num`, `yyyp_sell_num`
- `steam_buff_sell_conversion`, `statistic`
- `sell_price_rate_1`, `yyyp_sell_price_rate_1`, `yyyp_sell_price_rate_15`

---

## 3. 三个策略（当前有效定义）

> 规则机制：每个策略内部为 **AND**（核心条件全部满足才触发）

## 3.1 策略一：主力装盘入场监控（S1_MAIN_FORCE_ENTRY）

### 策略解释
这是“分阶段时序”策略：
1) 历史阶段先出现“量涨价平 + 多轮放量异动”；
2) 近期出现“回调到位 + 明显缩量”；
3) 当天正好命中洗盘窗口。  
只有这个顺序同时成立，才视为“庄家埋伏到位”的候选异动。

### 核心规则（5条，全部满足才触发）

> 时间测度范围（当前实现）：
> - 历史阶段：`t-33` 到 `t-3`（30根）
> - 近期阶段：`t-12` 到 `t`（用于 MA5(T-7) 与 MA5(当前)）
> - 当天判定：`t`

1. **历史阶段量涨价平（30天吸筹）**
   - 解释：历史30天里，价格要保持低波动（价平），同时量能有抬升（量涨）。
   - 公式：
     - `ret_t = (close_t - close_{t-1}) / close_{t-1}`
     - `hist_volatility_14d = std(ret_{hist,-14...-1}) <= 0.035`
     - `hist_volatility_7d = std(ret_{hist,-7...-1}) <= 0.03`
     - `hist_MA5(volume)_now > hist_MA5(volume)_{t-7}`

2. **多轮放量异动**
   - 解释：在历史阶段内要有多次2倍放量，说明不是单次脉冲噪声。
   - 公式：历史阶段统计 `volume_i / max(volume_{i-1}, 1) >= 2.0`
   - 条件：`spike_count >= 4`

3. **回调幅度到位（近期）**
   - 解释：吸筹结束后回调8%~12%，属于“洗盘中期”而不是结构破坏。
   - 公式：`decline_pct = (acc_end_price - close_now) / acc_end_price`
   - 条件：`0.08 <= decline_pct <= 0.12`

4. **近期缩量确认**
   - 解释：近期成交量要明显低于T-7阶段，体现洗盘后抛压衰减。
   - 公式：`MA5(volume)_now < MA5(volume)_{t-7} * 0.7`

5. **今天命中洗盘窗口**
   - 解释：当今天处于吸筹完成后第3~5天，才触发最终信号。
   - 公式：`3 <= bars_since_accumulation_end <= 5`

### 辅助展示参数（不参与触发）
- `turnover_number`：近期成交活跃度
- `rank_num`：热度位置
- `yyyp_lease_annual`：租赁资金背景
- `buff_sell_price / yyyp_sell_price / steam_sell_price`：多平台价格参考
- `yyyp_sell_price_rate_15`：YYYP 15日涨跌幅（中短周期趋势补充）

### 配置参数（config.json）

- `s1.history_window`：历史阶段窗口长度（默认30）
- `s1.history_end_offset`：历史阶段结束偏移（默认3）
- `s1.volatility_14d_max` / `s1.volatility_7d_max`：价平波动率阈值
- `s1.spike_ratio_threshold` / `s1.spike_count_min`：放量异动定义
- `s1.pullback_min` / `s1.pullback_max`：回调幅度范围
- `s1.contraction_ratio`：近期缩量比例（MA5_now < MA5_t7 * ratio）
- `s1.washout_day_min` / `s1.washout_day_max`：洗盘窗口天数

---

## 3.2 策略二：多底缩量回踩监控（S2_MULTI_BOTTOM_RETRACE）

### 策略解释
这是“横盘区间波段反弹”策略：
- 只做近1个月横盘内的支撑反弹；
- 不赌主力装盘，不赌区间突破；
- 通过“多底共识 + 缩量回踩 + 止跌阳线”提高胜率。
- 第二轮修正后，额外增加“近期拉升护栏 + 近期剧烈波动护栏”，避免把主力拉升后出货阶段误判成区间支撑反弹。

它与策略一的差异是：策略一是“主力阶段切换”逻辑，策略二是“区间支撑反弹”逻辑。

### 多底识别算法（核心）

1. **样本窗口**：最近 `N=30` 根日线（近1个月）
2. **候选底（局部低点）**：
   - `low[i] < low[i-1], low[i-2], low[i+1], low[i+2]`
3. **去重规则**：相邻候选底至少间隔 `min_sep=5`
4. **底部带过滤**：
   - 候选底价格中位数记为 `bottom_med`
   - 保留条件：`abs(low_i - bottom_med)/bottom_med <= 0.03`
5. **有效底定义**：
   - `bottom_count = 1`：单底（不触发）
   - `bottom_count >= 2`：双底及以上
   - 且有效底价差：`bottom_spread <= 0.10`

### 核心规则（5条）+ 护栏（2条，全部满足才触发）

1. **横盘环境成立**
   - 解释：仅在横盘内做反弹，不参与趋势行情。
   - 公式：`sideways_range = (max(close_30)-min(close_30))/avg(close_30)`
   - 条件：`0.10 <= sideways_range <= 0.40`

2. **多底共识有效**
   - 解释：至少双底，且底部之间价格差不能太大，才算市场共识支撑。
   - 公式：`bottom_count >= 2 and bottom_spread <= 0.10`

3. **回踩到支撑区间**
   - 解释：只在支撑区间内考虑入场，避免追到区间中上轨。
   - 公式：`0.98 <= close_now / bottom_med <= 1.05`

4. **缩量回踩成立**
   - 解释：回踩过程中缩量是抛压衰减的刚性验证。
   - 公式：`0.10 <= SMA3(volume)_now / SMA10(volume)_prev <= 0.14`

5. **止跌阳线确认**
   - 解释：支撑区内出现止跌阳线，再给交易确认。
   - 公式：`close_now > open_now and low_now >= bottom_med * 0.98`

6. **近期未发生过强拉升（护栏）**
   - 解释：如果近14根K线已经发生过明显拉升，当前更可能是冲高后的整理/出货，而不是区间下沿反弹。
   - 公式：`HHV(14) / LLV(14) <= recent_pump_ratio_14_max`

7. **近期不存在过大单日波动（护栏）**
   - 解释：如果近14根K线里出现过大阳/大阴，通常说明结构已经偏离“平稳横盘回踩”，更像主力拉升后的震荡分配。
   - 公式：`max(abs(ret_1d)) over last 14 bars <= recent_max_abs_return_14_max`

### 辅助展示参数（不参与触发）
- `yyyp_buy_num / yyyp_sell_num`：承接强弱
- `steam_buff_sell_conversion`：跨平台结构参考
- `turnover_number`：活跃度过滤
- `rank_num`：热度变化背景
- `yyyp_sell_price_rate_15`：YYYP 15日涨跌幅（结构阶段趋势补充）

### 配置参数（config.json）

- `s2.window`：横盘与多底识别窗口（默认30）
- `s2.sideways_range_min` / `s2.sideways_range_max`：横盘振幅范围
- `s2.bottom_min_sep`：底点去重最小间隔
- `s2.bottom_band_tolerance`：底部带容差
- `s2.bottom_count_min`：最小有效底数量
- `s2.bottom_spread_max`：多底价差上限
- `s2.support_ratio_min` / `s2.support_ratio_max`：回踩支撑区间
- `s2.shrink_ratio_min` / `s2.shrink_ratio_max`：缩量回踩比例区间
- `s2.rebound_low_guard`：止跌阳线低点守位比例
- `s2.recent_pump_ratio_14_max`：近14根K线高低点振幅比上限（过滤近期明显拉升后的末端结构）
- `s2.recent_max_abs_return_14_max`：近14根K线单日最大绝对涨跌幅上限（过滤近期剧烈波动/分配痕迹）

>
> 第二轮微调后，当前有效护栏为：
> - `s2.recent_pump_ratio_14_max = 1.22`
> - `s2.recent_max_abs_return_14_max = 0.10`

---

## 3.3 策略三：四倍增量预警（S3_VOLUME_4X）

### 策略解释
这是最直接的“当日量能异动”策略。按当前有效口径，先看三倍量，再过滤掉长期停滞标的的假信号。

### 核心规则（2条，全部满足才触发）

1. **三倍量触发**
   - 解释：今天量至少是昨天4倍，直接判定为显著异动。
   - 公式：`volume_now / max(volume_yesterday, 1) >= 4.0`

2. **非停滞过滤**
   - 解释：避免长期无成交标的因单次成交被误判为异动。
   - 公式：`count(volume > 0 in last_20_bars) / 20 >= 0.80`

### 辅助展示参数（不参与触发）
- `sell_price_rate_1 / yyyp_sell_price_rate_1`：放量当天涨跌方向
- `turnover_number`：成交真实性
- `statistic`：存世量背景
- 平台价格（BUFF/YYYP/Steam）：多平台确认
- `yyyp_sell_price_rate_15`：YYYP 15日涨跌幅（避免只看1日噪声）

### 配置参数（config.json）

- `s3.volume_multiple`：四倍量阈值（默认4.0）
- `s3.non_zero_window`：非停滞统计窗口（默认20）
- `s3.non_zero_min_ratio`：非零成交占比阈值（默认0.80）

---

## 4. 工具能力（anomaly_detector.py）

- 支持两种模式：`current`（检测当前）和 `backtest`（回测）
- 只输出 JSON 报告，不写库
- 告警参数统一为：`variable + explanation + value`

---

## 5. 输出规范（统一告警格式）

每个告警参数都使用三元结构：

```json
{
  "variable": "volume_ratio",
  "explanation": "今日成交量/昨日成交量",
  "value": 6.75
}
```

告警由四组组成：

1. `meta`：日期、item_id、item_name、strategy
2. `core_rule_results`：核心规则布尔值（是否满足）
3. `core_metric_values`：核心计算指标数值
4. `auxiliary_values`：辅助参数值（仅展示）

---



## 7. 工具运行说明

### 7.1 运行模式

- `current`：每个标的只计算一次（最新日线）
- `backtest`：对历史窗口逐日推进，统计历史触发

### 7.2 参数说明

| 参数 | 说明 | 默认值 |
|---|---|---|
| `--db-path` | SQLite数据库路径 | `./csgo_monitor.db` |
| `--config` | 策略参数配置文件路径 | `./config.json` |
| `--mode` | `current` 或 `backtest` | `current` |
| `--item-id` | 只跑单个item_id | 全部 |
| `--lookback-bars` | 回测模式回看K线根数 | `120` |
| `--output-dir` | 报告输出目录 | `./signals` |

### 7.3 命令行用法

```bash
# 检测当前（推荐日常使用）
python anomaly_detector.py --db-path ./csgo_monitor.db --mode current 

# 检测当前（单个标的）
python anomaly_detector.py --db-path ./csgo_monitor.db --mode current --item-id 14175 --output-dir ./signals

# 回测（最近120根）
python anomaly_detector.py --db-path ./csgo_monitor.db --mode backtest --lookback-bars 120 --output-dir ./signals

# 回测（最近90根）
python anomaly_detector.py --db-path ./csgo_monitor.db --mode backtest --lookback-bars 90 --output-dir ./signals
```

回测结果额外包含：
- `summary`：各策略触发次数
- `alerts`：历史触发明细

---



## 9. 当前状态（截至本版）

- 异动工具已可运行
- 支持：`current` + `backtest`
- 告警输出已统一为“变量名+变量解释+数值”

本文件即当前生效版本。
