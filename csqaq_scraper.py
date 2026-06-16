#!/usr/bin/env python3
"""
CSGO饰品K线数据抓取工具
使用Playwright浏览器自动化方案，无需API Token
"""

import json
import csv
import argparse
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


class CSQAQScraper:
    def __init__(self, goods_id, platform="YYYP", period="day", output_dir="./data"):
        """
        初始化抓取器
        
        Args:
            goods_id: 饰品ID (从csqaq.com/goods/xxx 中获取)
            platform: 平台 - BUFF(网易BUFF) 或 YYYP(悠悠有品)
            period: 周期 - day(日线), week(周线), hour1(1小时), hour4(4小时)
            output_dir: 数据保存目录
        """
        self.goods_id = str(goods_id)
        self.platform = platform
        self.period = period
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        self.result = {
            "goods_info": None,
            "kline_data": [],
            "fetch_time": None,
            "params": {
                "goods_id": goods_id,
                "platform": platform,
                "period": period
            }
        }
        self._kline_max_timestamp = 0
    
    def fetch(self):
        """执行数据抓取"""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            page.route("**/proxies/api/v1/info/simple/chartAll", self._rewrite_chartall_request)
            
            page.on("response", self._handle_response)
            
            print(f"正在抓取商品 ID={self.goods_id} ...")
            page.goto(f"https://csqaq.com/goods/{self.goods_id}", wait_until="networkidle")
            page.wait_for_timeout(2000)
            
            print("点击K线图按钮...")
            kline_btn = page.locator('button:has-text("K线")').first
            if kline_btn.is_visible():
                self._click_and_wait_chart_response(page, kline_btn, 12000)

            self._select_platform_source(page)
            
            period_map = {
                "day": "日线",
                "week": "周线",
                "hour1": "1小时",
                "hour4": "4小时"
            }
            period_text = period_map.get(self.period, "日线")
            print(f"选择周期: {period_text}...")
            
            period_btn = page.locator(f'text={period_text}').first
            if period_btn.is_visible():
                self._click_and_wait_chart_response(page, period_btn, 12000)
            
            browser.close()
        
        self.result["fetch_time"] = datetime.now().isoformat()
        return self.result

    def _rewrite_chartall_request(self, route):
        request = route.request
        payload = request.post_data or ""
        try:
            body = json.loads(payload) if payload else {}
        except Exception:
            body = {}

        target_plat = 2 if self.platform == "YYYP" else 1
        period_map = {
            "day": "1day",
            "week": "7day",
            "hour1": "1hour",
            "hour4": "4hour"
        }

        body["good_id"] = int(self.goods_id)
        body["plat"] = target_plat
        body["periods"] = period_map.get(self.period, "1day")

        route.continue_(post_data=json.dumps(body), headers={**request.headers, "content-type": "application/json"})

    def _select_platform_source(self, page):
        target_labels = ["悠悠有品", "有品"] if self.platform == "YYYP" else ["BUFF", "网易BUFF"]
        last_error = None

        for label in target_labels:
            candidate_locators = [
                page.locator(f'button:has-text("{label}")').first,
                page.locator(f'[role="tab"]:has-text("{label}")').first,
                page.locator(f'text={label}').first,
            ]

            for locator in candidate_locators:
                try:
                    if locator.count() > 0 and locator.is_visible():
                        self._click_and_wait_chart_response(page, locator, 8000)
                        print(f"已选择数据源: {label}")
                        return True
                except Exception as err:
                    last_error = err

        print(f"未显式切换数据源，继续使用页面当前默认源（目标: {self.platform}）")
        if last_error:
            print(f"数据源切换最后一次尝试报错: {str(last_error)[:120]}")
        return False

    def _click_and_wait_chart_response(self, page, locator, timeout_ms=10000):
        try:
            with page.expect_response(
                lambda response: "simple/chartAll" in response.url and response.status == 200,
                timeout=timeout_ms,
            ):
                locator.click()
            page.wait_for_timeout(1000)
            return True
        except PlaywrightTimeoutError:
            page.wait_for_timeout(1200)
            return False
    
    def _handle_response(self, response):
        """处理API响应"""
        if response.status != 200:
            return
        
        try:
            data = response.json()
            if data.get("code") != 200:
                return
            
            url = response.url
            
            if f"good?id={self.goods_id}" in url:
                self.result["goods_info"] = data.get("data", {}).get("goods_info", {})
            
            elif "simple/chartAll" in url:
                chart_data = data.get("data", [])
                if chart_data:
                    incoming_max_ts = self._get_max_kline_timestamp(chart_data)
                    if (
                        not self.result["kline_data"]
                        or incoming_max_ts > self._kline_max_timestamp
                    ):
                        self.result["kline_data"] = chart_data
                        self._kline_max_timestamp = incoming_max_ts
                    
        except Exception:
            pass

    def _get_max_kline_timestamp(self, chart_data):
        max_ts = 0
        for item in chart_data:
            if not isinstance(item, dict):
                continue
            ts = item.get('t')
            if ts is None:
                continue
            try:
                ts_int = int(ts)
            except (TypeError, ValueError):
                continue
            if ts_int > max_ts:
                max_ts = ts_int
        return max_ts
    
    def save(self):
        """保存数据到文件"""
        goods_name = self.result["goods_info"].get("name", "unknown") if self.result["goods_info"] else "unknown"
        safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in goods_name)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_filename = f"{self.goods_id}_{safe_name}_{timestamp}"
        
        json_path = self.output_dir / f"{base_filename}.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(self.result, f, ensure_ascii=False, indent=2)
        
        csv_path = self.output_dir / f"{base_filename}.csv"
        if self.result["kline_data"]:
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['timestamp', 'datetime', 'open', 'close', 'high', 'low', 'volume'])
                for item in self.result["kline_data"]:
                    ts = int(item.get('t', 0)) / 1000
                    dt = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
                    writer.writerow([
                        item.get('t'),
                        dt,
                        item.get('o'),
                        item.get('c'),
                        item.get('h'),
                        item.get('l'),
                        item.get('v')
                    ])
        
        return json_path, csv_path
    
    def print_summary(self):
        """打印数据摘要"""
        goods = self.result.get("goods_info", {})
        klines = self.result.get("kline_data", [])
        
        print("\n" + "="*60)
        print("📊 数据抓取完成")
        print("="*60)
        
        if goods:
            print(f"\n🏷️ 商品: {goods.get('name', 'N/A')}")
            print(f"💰 BUFF售价: ¥{goods.get('buff_sell_price', 'N/A')}")
            print(f"📦 在售: {goods.get('buff_sell_num', 'N/A')} 件")
        
        print(f"\n📈 K线数据: {len(klines)} 条")
        
        if klines:
            from datetime import datetime
            timestamps = [int(k['t']) for k in klines]
            start = datetime.fromtimestamp(min(timestamps)/1000).strftime('%Y-%m-%d')
            end = datetime.fromtimestamp(max(timestamps)/1000).strftime('%Y-%m-%d')
            closes = [k['c'] for k in klines]
            print(f"📅 时间范围: {start} ~ {end}")
            print(f"📊 价格区间: ¥{min(closes)} ~ ¥{max(closes)}")
            print(f"💵 最新价格: ¥{closes[-1]}")
        
        print("="*60)


def main():
    parser = argparse.ArgumentParser(description='CSGO饰品K线数据抓取工具')
    parser.add_argument('goods_id', type=str, help='饰品ID (从csqaq.com/goods/xxx中获取)')
    parser.add_argument('--platform', '-p', type=str, default='YYYP', 
                       choices=['BUFF', 'YYYP'], help='平台: BUFF(网易BUFF) 或 YYYP(悠悠有品)')
    parser.add_argument('--period', '-t', type=str, default='day',
                       choices=['day', 'week', 'hour1', 'hour4'],
                       help='周期: day(日线), week(周线), hour1(1小时), hour4(4小时)')
    parser.add_argument('--output', '-o', type=str, default='./data',
                       help='数据保存目录 (默认: ./data)')
    
    args = parser.parse_args()
    
    scraper = CSQAQScraper(
        goods_id=args.goods_id,
        platform=args.platform,
        period=args.period,
        output_dir=args.output
    )
    
    scraper.fetch()
    json_path, csv_path = scraper.save()
    scraper.print_summary()
    
    print(f"\n✅ 文件已保存:")
    print(f"   JSON: {json_path}")
    print(f"   CSV:  {csv_path}")


if __name__ == "__main__":
    main()
