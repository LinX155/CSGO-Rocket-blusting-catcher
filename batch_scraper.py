#!/usr/bin/env python3
"""
CSQAQ 批量抓取程序 - 生产级版本
基于压力测试结果，采用最保守稳定的方案
"""

import argparse
import json
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
import sys

sys.path.insert(0, str(Path(__file__).parent))
from csqaq_scraper import CSQAQScraper
from database import CSQAQDatabase


class BatchScraper:
    """
    批量抓取器 - 基于压力测试结果的最保守方案
    
    配置原则：
    - 1线程并发（100%成功率）
    - 批次间隔 5秒
    - 每30个ID长休息 60秒
    - 失败自动重试（最多3次）
    - 重试间隔 30秒
    - 每个ID抓取时间不超过50秒
    """
    
    DEFAULT_CONFIG = {
        "max_workers": 1,
        "batch_size": 1,
        "interval_between_batches": 8,
        "long_rest_interval": 30,
        "long_rest_duration": 60,
        "extra_long_rest_interval": 90,
        "extra_long_rest_duration": 600,
        "max_retries": 5,
        "retry_delay": 30,
        "timeout_per_item": 50
    }

    id_list: List[str]
    results: List[Dict]
    run_start_time: Optional[float]
    db: CSQAQDatabase
    
    def __init__(
        self,
        id_list_file: str,
        output_dir: str = "./batch_data",
        platform: str = "YYYP",
        period: str = "day",
        config: Optional[Dict] = None,
        db_path: str = "./csgo_monitor.db"
    ):
        self.id_list_file = Path(id_list_file)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.platform = platform
        self.period = period
        self.config = {**self.DEFAULT_CONFIG, **(config or {})}
        self.db_path = db_path

        self._setup_logging()
        self.id_list = self._load_id_list()
        self.results: List[Dict] = []
        self.run_start_time: Optional[float] = None
        self.db = CSQAQDatabase(db_path=self.db_path)
        
        
    def _setup_logging(self):
        log_file = self.output_dir / f"batch_scraper_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s [%(levelname)s] %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
    def _load_id_list(self) -> List[str]:
        if not self.id_list_file.exists():
            raise FileNotFoundError(f"ID列表文件不存在: {self.id_list_file}")
        
        with open(self.id_list_file, 'r', encoding='utf-8') as f:
            ids = [line.strip() for line in f if line.strip()]
        
        self.logger.info(f"加载了 {len(ids)} 个ID")
        return ids
    
    def _fetch_single(self, goods_id: str, retry_count: int = 0) -> Dict:
        """抓取单个ID，带重试机制"""
        start_time = time.time()
        
        try:
            scraper = CSQAQScraper(
                goods_id=goods_id,
                platform=self.platform,
                period=self.period,
                output_dir=str(self.output_dir)
            )
            
            result = scraper.fetch()
            json_path, csv_path = scraper.save()

            elapsed = time.time() - start_time
            
            if result.get("kline_data") and len(result["kline_data"]) > 0:
                goods_info = result.get("goods_info", {})
                
                if goods_info:
                    try:
                        item_id = self.db.insert_or_update_item(goods_info)
                        self.db.insert_daily_snapshot(item_id, goods_info)
                        self.db.insert_kline_data(item_id, result["kline_data"])
                        self.db.log_fetch(
                            item_id=item_id,
                            status="success",
                            retry_count=retry_count,
                            elapsed_time=elapsed
                        )
                    except Exception as db_err:
                        self.logger.warning(f"ID {goods_id} 数据库存储失败（JSON/CSV已保存）: {str(db_err)[:80]}")
                
                return {
                    "id": goods_id,
                    "success": True,
                    "elapsed": elapsed,
                    "data_count": len(result["kline_data"]),
                    "goods_name": goods_info.get("name", "Unknown"),
                    "json_path": str(json_path),
                    "csv_path": str(csv_path),
                    "retry_count": retry_count,
                    "error": None
                }
            else:
                raise Exception("未获取到K线数据")
                
        except Exception as e:
            elapsed = time.time() - start_time
            
            if retry_count < self.config["max_retries"]:
                self.logger.warning(f"ID {goods_id} 抓取失败，{retry_count+1}/{self.config['max_retries']} 次重试: {str(e)[:50]}")
                time.sleep(self.config["retry_delay"])
                return self._fetch_single(goods_id, retry_count + 1)
            else:
                self.logger.error(f"ID {goods_id} 抓取失败，已达到最大重试次数: {str(e)[:50]}")
                try:
                    failed_item_id = int(goods_id) if goods_id.isdigit() else 0
                    self.db.log_fetch(
                        item_id=failed_item_id,
                        status="failed",
                        error_msg=str(e)[:500],
                        retry_count=retry_count,
                        elapsed_time=elapsed
                    )
                except Exception as db_err:
                    self.logger.warning(f"ID {goods_id} 写入失败日志失败: {str(db_err)[:80]}")
                return {
                    "id": goods_id,
                    "success": False,
                    "elapsed": elapsed,
                    "data_count": 0,
                    "goods_name": "Failed",
                    "json_path": None,
                    "csv_path": None,
                    "retry_count": retry_count,
                    "error": str(e)
                }
    
    def _process_batch(self, batch: List[str], batch_num: int, total_batches: int) -> List[Dict]:
        """处理一个批次"""
        self.logger.info(f"处理批次 {batch_num}/{total_batches} (ID: {', '.join(batch)})")
        
        batch_results = []
        
        with ThreadPoolExecutor(max_workers=self.config["max_workers"]) as executor:
            future_to_id = {
                executor.submit(self._fetch_single, goods_id): goods_id
                for goods_id in batch
            }
            
            for future in as_completed(future_to_id):
                result = future.result()
                batch_results.append(result)
                
                status = "✅" if result["success"] else "❌"
                self.logger.info(
                    f"{status} ID {result['id']}: {result['elapsed']:.2f}s "
                    f"({result['data_count']}条数据, 重试{result['retry_count']}次)"
                )
        
        return batch_results
    
    def run(self):
        """运行批量抓取"""
        start_time = time.time()
        self.run_start_time = start_time
        self.logger.info("="*70)
        self.logger.info("开始批量抓取")
        self.logger.info(f"总ID数: {len(self.id_list)}")
        self.logger.info(f"配置: {self.config}")
        self.logger.info("="*70)
        
        # 分批次处理
        batches = [
            self.id_list[i:i + self.config["batch_size"]] 
            for i in range(0, len(self.id_list), self.config["batch_size"])
        ]
        total_batches = len(batches)
        
        for i, batch in enumerate(batches, 1):
            processed_count = (i - 1) * self.config["batch_size"]
            
            if i > 1:
                # 分层休息机制
                # 第一层：每100个ID休息10分钟
                if processed_count % self.config["extra_long_rest_interval"] == 0:
                    self.logger.info(f"🛌 深度休息: 已处理 {processed_count} 个ID，休息10分钟")
                    self.logger.info(f"⏰ 预计休息结束时间: {datetime.fromtimestamp(time.time() + self.config['extra_long_rest_duration']).strftime('%H:%M:%S')}")
                    time.sleep(self.config["extra_long_rest_duration"])
                    self.logger.info("✅ 深度休息结束，继续抓取")
                
                # 第二层：每30个ID休息60秒
                elif processed_count % self.config["long_rest_interval"] == 0:
                    self.logger.info(f"☕ 常规休息: 已处理 {processed_count} 个ID，休息 {self.config['long_rest_duration']} 秒")
                    time.sleep(self.config["long_rest_duration"])
                
                # 基础批次间隔
                else:
                    time.sleep(self.config["interval_between_batches"])
            
            # 处理批次
            batch_results = self._process_batch(batch, i, total_batches)
            self.results.extend(batch_results)
            
            # 统计
            success_count = len([r for r in batch_results if r["success"]])
            self.logger.info(f"批次 {i} 完成: {success_count}/{len(batch)} 成功")
        
        # 生成报告
        self._generate_report(start_time)
        
    def _generate_report(self, start_time: float):
        """生成最终报告"""
        total_time = time.time() - start_time
        successful = [r for r in self.results if r["success"]]
        failed = [r for r in self.results if not r["success"]]
        total_ids = len(self.id_list)
        success_rate = (len(successful) / total_ids * 100) if total_ids else 0
        
        report = {
            "start_time": datetime.fromtimestamp(start_time).isoformat(),
            "end_time": datetime.now().isoformat(),
            "total_time": total_time,
            "total_ids": total_ids,
            "success_count": len(successful),
            "failed_count": len(failed),
            "success_rate": success_rate,
            "config": self.config,
            "failed_ids": [r["id"] for r in failed],
            "details": self.results
        }
        
        # 保存JSON报告
        report_path = self.output_dir / f"batch_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        # 保存失败列表（方便重试）
        if failed:
            failed_path = self.output_dir / f"failed_ids_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            with open(failed_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join([r["id"] for r in failed]))
        
        # 打印总结
        self.logger.info("="*70)
        self.logger.info("批量抓取完成")
        self.logger.info("="*70)
        self.logger.info(f"总耗时: {total_time:.2f}秒 ({total_time/60:.2f}分钟)")
        self.logger.info(f"成功: {len(successful)}/{total_ids} ({report['success_rate']:.1f}%)")
        self.logger.info(f"失败: {len(failed)}")
        
        if successful:
            avg_time = sum(r["elapsed"] for r in successful) / len(successful)
            self.logger.info(f"平均耗时: {avg_time:.2f}秒/ID")
        
        self.logger.info(f"报告保存: {report_path}")
        
        if failed:
            self.logger.warning(f"失败ID列表: {report['failed_ids']}")

    def close(self):
        if hasattr(self, "db") and self.db:
            self.db.close()


def main():
    parser = argparse.ArgumentParser(
        description='CSQAQ 批量抓取程序 - 生产级版本',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 基础用法
  python batch_scraper.py ids.txt
  
  # 指定输出目录
  python batch_scraper.py ids.txt -o ./my_data
  
  # 抓取悠悠有品数据
  python batch_scraper.py ids.txt -p YYYP
  
  # 抓取周线数据
  python batch_scraper.py ids.txt -t week
  
  # 自定义配置
  python batch_scraper.py ids.txt --workers 2 --batch-size 2 --interval 3

ID列表文件格式:
  每行一个ID，例如:
  234
  6798
  14135
  14140
        """
    )
    
    parser.add_argument('id_file', type=str, help='ID列表文件路径 (每行一个ID)')
    parser.add_argument('-o', '--output', type=str, default='./batch_data',
                       help='输出目录 (默认: ./batch_data)')
    parser.add_argument('-p', '--platform', type=str, default='YYYP',
                       choices=['BUFF', 'YYYP'],
                       help='平台: BUFF(网易BUFF) 或 YYYP(悠悠有品) (默认: YYYP)')
    parser.add_argument('-t', '--period', type=str, default='day',
                       choices=['day', 'week', 'hour1', 'hour4'],
                       help='周期: day/week/hour1/hour4 (默认: day)')
    
    # 高级配置
    parser.add_argument('--workers', type=int, default=1,
                       help='并发线程数 (默认: 1, 基于测试结果的最保守方案)')
    parser.add_argument('--batch-size', type=int, default=1,
                       help='每批次ID数量 (默认: 1)')
    parser.add_argument('--interval', type=int, default=8,
                       help='批次间隔秒数 (默认: 8)')
    parser.add_argument('--rest-interval', type=int, default=30,
                       help='长休息触发间隔 (每N个ID后休息) (默认: 30)')
    parser.add_argument('--rest-duration', type=int, default=60,
                       help='长休息时间秒数 (默认: 60)')
    parser.add_argument('--max-retries', type=int, default=5,
                       help='最大重试次数 (默认: 5)')
    parser.add_argument('--retry-delay', type=int, default=30,
                       help='重试间隔秒数 (默认: 30)')
    
    args = parser.parse_args()
    
    # 构建配置
    config = {
        "max_workers": args.workers,
        "batch_size": args.batch_size,
        "interval_between_batches": args.interval,
        "long_rest_interval": args.rest_interval,
        "long_rest_duration": args.rest_duration,
        "max_retries": args.max_retries,
        "retry_delay": args.retry_delay
    }
    
    # 运行
    scraper = BatchScraper(
        id_list_file=args.id_file,
        output_dir=args.output,
        platform=args.platform,
        period=args.period,
        config=config
    )
    
    try:
        scraper.run()
    except KeyboardInterrupt:
        print("\n\n用户中断，正在保存当前进度...")
        report_start = scraper.run_start_time if scraper.run_start_time else time.time()
        scraper._generate_report(report_start)
        print("已保存报告")
    finally:
        scraper.close()


if __name__ == "__main__":
    main()
