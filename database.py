#!/usr/bin/env python3
"""
CSQAQ 数据库管理模块
负责SQLite数据库的初始化和数据操作
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class CSQAQDatabase:
    """CSQAQ数据库管理类"""
    
    def __init__(self, db_path: str = "./csgo_monitor.db"):
        self.db_path = Path(db_path)
        self.conn = None
        self._connect()
        self._init_tables()
    
    def _connect(self):
        """连接数据库"""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        logger.info(f"数据库连接成功: {self.db_path}")
    
    def _init_tables(self):
        """初始化数据表"""
        cursor = self.conn.cursor()
        
        # 1. 饰品基本信息表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                market_hash_name TEXT,
                rarity TEXT,
                type TEXT,
                exterior TEXT,
                buff_id INTEGER,
                yyyp_id INTEGER,
                def_index INTEGER,
                paint_index INTEGER,
                min_float REAL,
                max_float REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 2. 每日截面数据表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                date DATE NOT NULL,
                fetch_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                -- BUFF平台
                buff_sell_price REAL,
                buff_buy_price REAL,
                buff_sell_num INTEGER,
                buff_buy_num INTEGER,
                -- 悠悠有品
                yyyp_sell_price REAL,
                yyyp_buy_price REAL,
                yyyp_sell_num INTEGER,
                yyyp_buy_num INTEGER,
                yyyp_lease_price REAL,
                yyyp_lease_annual REAL,
                -- Steam
                steam_sell_price REAL,
                steam_buy_price REAL,
                -- 涨跌幅 (BUFF平台)
                sell_price_rate_1 REAL,
                sell_price_rate_7 REAL,
                sell_price_rate_30 REAL,
                sell_price_rate_90 REAL,
                sell_price_rate_180 REAL,
                sell_price_rate_365 REAL,
                -- 涨跌幅 (YYYP平台)
                yyyp_sell_price_rate_1 REAL,
                yyyp_sell_price_rate_7 REAL,
                yyyp_sell_price_rate_15 REAL,
                yyyp_sell_price_rate_30 REAL,
                yyyp_sell_price_rate_90 REAL,
                yyyp_sell_price_rate_180 REAL,
                yyyp_sell_price_rate_365 REAL,
                -- 其他指标
                statistic INTEGER,  -- 存世量
                rank_num INTEGER,
                turnover_number INTEGER,
                turnover_avg_price REAL,
                -- 挂刀比例
                steam_buff_sell_conversion REAL,
                buff_steam_sell_conversion REAL,
                -- 元数据
                raw_data TEXT,  -- 原始goods_info JSON
                UNIQUE(item_id, date),
                FOREIGN KEY (item_id) REFERENCES items(id)
            )
        """)
        
        # 3. K线数据表（增量存储，不重复）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS kline_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                timestamp INTEGER NOT NULL,  -- 毫秒时间戳
                open REAL,
                close REAL,
                high REAL,
                low REAL,
                volume INTEGER,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(item_id, timestamp),
                FOREIGN KEY (item_id) REFERENCES items(id)
            )
        """)
        
        # 4. 监控策略结果表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS strategy_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                date DATE NOT NULL,
                strategy_name TEXT NOT NULL,
                signal_score REAL,
                signal_type TEXT,  -- 'strong_buy', 'buy', 'watch', 'sell'
                reason TEXT,
                indicators TEXT,  -- JSON格式存储触发时的各项指标
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(item_id, date, strategy_name),
                FOREIGN KEY (item_id) REFERENCES items(id)
            )
        """)
        
        # 5. 抓取日志表（用于追踪每次运行）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fetch_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id TEXT,  -- 批次ID，用于关联
                item_id INTEGER,
                status TEXT,  -- 'success', 'failed'
                error_msg TEXT,
                retry_count INTEGER DEFAULT 0,
                elapsed_time REAL,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (item_id) REFERENCES items(id)
            )
        """)
        
        # 创建索引优化查询
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_snapshots_date 
            ON daily_snapshots(date)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_snapshots_item_date 
            ON daily_snapshots(item_id, date)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_kline_item_time 
            ON kline_data(item_id, timestamp)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_signals_date 
            ON strategy_signals(date)
        """)

        cursor.execute("PRAGMA table_info(daily_snapshots)")
        daily_columns = {row[1] for row in cursor.fetchall()}
        if 'yyyp_sell_price_rate_15' not in daily_columns:
            cursor.execute("ALTER TABLE daily_snapshots ADD COLUMN yyyp_sell_price_rate_15 REAL")
        
        self.conn.commit()
        logger.info("数据库表初始化完成")
    
    def insert_or_update_item(self, goods_info: Dict) -> int:
        """
        插入或更新饰品基本信息
        返回item_id
        """
        cursor = self.conn.cursor()
        
        item_id = goods_info.get('id')
        
        cursor.execute("""
            INSERT INTO items (
                id, name, market_hash_name, rarity, type, exterior,
                buff_id, yyyp_id, def_index, paint_index, min_float, max_float,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                market_hash_name = excluded.market_hash_name,
                rarity = excluded.rarity,
                type = excluded.type,
                exterior = excluded.exterior,
                buff_id = excluded.buff_id,
                yyyp_id = excluded.yyyp_id,
                def_index = excluded.def_index,
                paint_index = excluded.paint_index,
                min_float = excluded.min_float,
                max_float = excluded.max_float,
                updated_at = excluded.updated_at
        """, (
            item_id,
            goods_info.get('name'),
            goods_info.get('market_hash_name'),
            goods_info.get('rarity_localized_name'),
            goods_info.get('type_localized_name'),
            goods_info.get('exterior_localized_name'),
            goods_info.get('buff_id'),
            goods_info.get('yyyp_id'),
            goods_info.get('def_index'),
            goods_info.get('paint_index'),
            goods_info.get('min_float'),
            goods_info.get('max_float'),
            datetime.now().isoformat()
        ))
        
        self.conn.commit()
        return item_id
    
    def insert_daily_snapshot(self, item_id: int, goods_info: Dict):
        """
        插入每日截面数据
        使用INSERT OR REPLACE处理补抓场景
        """
        cursor = self.conn.cursor()
        today = datetime.now().strftime('%Y-%m-%d')
        
        cursor.execute("""
            INSERT INTO daily_snapshots (
                item_id, date, fetch_time,
                buff_sell_price, buff_buy_price, buff_sell_num, buff_buy_num,
                yyyp_sell_price, yyyp_buy_price, yyyp_sell_num, yyyp_buy_num,
                yyyp_lease_price, yyyp_lease_annual,
                steam_sell_price, steam_buy_price,
                sell_price_rate_1, sell_price_rate_7, sell_price_rate_30,
                sell_price_rate_90, sell_price_rate_180, sell_price_rate_365,
                yyyp_sell_price_rate_1, yyyp_sell_price_rate_7, yyyp_sell_price_rate_15, yyyp_sell_price_rate_30,
                yyyp_sell_price_rate_90, yyyp_sell_price_rate_180, yyyp_sell_price_rate_365,
                statistic, rank_num, turnover_number, turnover_avg_price,
                steam_buff_sell_conversion, buff_steam_sell_conversion,
                raw_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(item_id, date) DO UPDATE SET
                fetch_time = excluded.fetch_time,
                buff_sell_price = excluded.buff_sell_price,
                buff_buy_price = excluded.buff_buy_price,
                buff_sell_num = excluded.buff_sell_num,
                buff_buy_num = excluded.buff_buy_num,
                yyyp_sell_price = excluded.yyyp_sell_price,
                yyyp_buy_price = excluded.yyyp_buy_price,
                yyyp_sell_num = excluded.yyyp_sell_num,
                yyyp_buy_num = excluded.yyyp_buy_num,
                yyyp_lease_price = excluded.yyyp_lease_price,
                yyyp_lease_annual = excluded.yyyp_lease_annual,
                steam_sell_price = excluded.steam_sell_price,
                steam_buy_price = excluded.steam_buy_price,
                sell_price_rate_1 = excluded.sell_price_rate_1,
                sell_price_rate_7 = excluded.sell_price_rate_7,
                sell_price_rate_30 = excluded.sell_price_rate_30,
                sell_price_rate_90 = excluded.sell_price_rate_90,
                sell_price_rate_180 = excluded.sell_price_rate_180,
                sell_price_rate_365 = excluded.sell_price_rate_365,
                yyyp_sell_price_rate_1 = excluded.yyyp_sell_price_rate_1,
                yyyp_sell_price_rate_7 = excluded.yyyp_sell_price_rate_7,
                yyyp_sell_price_rate_15 = excluded.yyyp_sell_price_rate_15,
                yyyp_sell_price_rate_30 = excluded.yyyp_sell_price_rate_30,
                yyyp_sell_price_rate_90 = excluded.yyyp_sell_price_rate_90,
                yyyp_sell_price_rate_180 = excluded.yyyp_sell_price_rate_180,
                yyyp_sell_price_rate_365 = excluded.yyyp_sell_price_rate_365,
                statistic = excluded.statistic,
                rank_num = excluded.rank_num,
                turnover_number = excluded.turnover_number,
                turnover_avg_price = excluded.turnover_avg_price,
                steam_buff_sell_conversion = excluded.steam_buff_sell_conversion,
                buff_steam_sell_conversion = excluded.buff_steam_sell_conversion,
                raw_data = excluded.raw_data
        """, (
            item_id, today, datetime.now().isoformat(),
            goods_info.get('buff_sell_price'),
            goods_info.get('buff_buy_price'),
            goods_info.get('buff_sell_num'),
            goods_info.get('buff_buy_num'),
            goods_info.get('yyyp_sell_price'),
            goods_info.get('yyyp_buy_price'),
            goods_info.get('yyyp_sell_num'),
            goods_info.get('yyyp_buy_num'),
            goods_info.get('yyyp_lease_price'),
            goods_info.get('yyyp_lease_annual'),
            goods_info.get('steam_sell_price'),
            goods_info.get('steam_buy_price'),
            goods_info.get('sell_price_rate_1'),
            goods_info.get('sell_price_rate_7'),
            goods_info.get('sell_price_rate_30'),
            goods_info.get('sell_price_rate_90'),
            goods_info.get('sell_price_rate_180'),
            goods_info.get('sell_price_rate_365'),
            goods_info.get('yyyp_sell_price_rate_1'),
            goods_info.get('yyyp_sell_price_rate_7'),
            goods_info.get('yyyp_sell_price_rate_15'),
            goods_info.get('yyyp_sell_price_rate_30'),
            goods_info.get('yyyp_sell_price_rate_90'),
            goods_info.get('yyyp_sell_price_rate_180'),
            goods_info.get('yyyp_sell_price_rate_365'),
            goods_info.get('statistic'),
            goods_info.get('rank_num'),
            goods_info.get('turnover_number'),
            goods_info.get('turnover_avg_price'),
            goods_info.get('steam_buff_sell_conversion'),
            goods_info.get('buff_steam_sell_conversion'),
            json.dumps(goods_info, ensure_ascii=False)
        ))
        
        self.conn.commit()
    
    def insert_kline_data(self, item_id: int, kline_list: List[Dict]):
        """
        插入K线数据（增量）
        使用INSERT OR IGNORE避免重复
        """
        if not kline_list:
            return
        
        cursor = self.conn.cursor()
        
        # 批量插入，忽略重复
        cursor.executemany("""
            INSERT OR IGNORE INTO kline_data 
            (item_id, timestamp, open, close, high, low, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, [
            (
                item_id,
                int(k.get('t')),
                k.get('o'),
                k.get('c'),
                k.get('h'),
                k.get('l'),
                k.get('v')
            )
            for k in kline_list
        ])
        
        self.conn.commit()
        inserted = cursor.rowcount
        logger.debug(f"K线数据入库: item_id={item_id}, 新增{inserted}条")
    
    def log_fetch(self, item_id: int, status: str, error_msg: str = None,
                  retry_count: int = 0, elapsed_time: float = 0):
        """记录抓取日志"""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO fetch_logs 
            (item_id, status, error_msg, retry_count, elapsed_time)
            VALUES (?, ?, ?, ?, ?)
        """, (item_id, status, error_msg, retry_count, elapsed_time))
        self.conn.commit()
    
    def get_item_history(self, item_id: int, days: int = 30) -> List[Dict]:
        """获取饰品历史数据"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM daily_snapshots
            WHERE item_id = ? AND date >= date('now', '-{} days')
            ORDER BY date DESC
        """.format(days), (item_id,))
        
        return [dict(row) for row in cursor.fetchall()]
    
    def get_all_items(self) -> List[Dict]:
        """获取所有饰品列表"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM items ORDER BY id")
        return [dict(row) for row in cursor.fetchall()]
    
    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
            logger.info("数据库连接已关闭")
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
