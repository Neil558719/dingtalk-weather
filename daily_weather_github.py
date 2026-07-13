"""
每日天气推送 - GitHub Actions 版 v2 🦐
===================================
三大防护：自动重试 + 多源备用 + 本地缓存
环境变量：
  WEBHOOK_URL = 钉钉群机器人 Webhook 地址
  CITY        = 城市名（默认淄博）
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s")
logger = logging.getLogger("daily-weather")

CITY = os.getenv("CITY", "淄博")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
AMAP_KEY = "7e89297c445e7e1918ffa324c3ee67c8"
# 淄博经纬度（Open-Meteo 使用）
CITY_LAT = 36.78
CITY_LON = 118.05

# GitHub Actions 缓存目录（workflow 目录下）
BACKUP_DIR = Path(os.getenv("RUNNER_TEMP", ".")) / "weather_backup"
BACKUP_FILE = BACKUP_DIR / "weather_backup.json"

BJT = timezone(timedelta(hours=8))


# ──────────── 数据源 1：高德天气 ────────────
def fetch_amap(retries=3) -> str | None:
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(
                "https://restapi.amap.com/v3/weather/weatherInfo",
                params={"key": AMAP_KEY, "city": CITY, "extensions": "all"},
                timeout=10,
            )
            data = r.json()
            if data.get("status") == "1" and data.get("count", "0") != "0":
                today = data["forecasts"][0]["casts"][0]
                return (
                    f"## 🌤 **{CITY} 天气预报**\n"
                    f"> 📅 **日期：**{today['date']}\n"
                    f"> ☀️ **白天：**{today['dayweather']}  {today['daytemp']}℃  {today['daywind']}\n"
                    f"> 🌙 **夜间：**{today['nightweather']}  {today['nighttemp']}℃  {today['nightwind']}\n\n"
                    f"🦐 小虾米祝您今天有个好心情！"
                )
            logger.warning(f"高德返回异常: {data}")
        except Exception as e:
            if attempt < retries:
                wait = 2 ** (attempt - 1)
                logger.warning(f"高德第{attempt}次失败({e})，{wait}s后重试…")
                time.sleep(wait)
            else:
                logger.warning(f"高德{retries}次均失败: {e}")
    return None


# ──────────── 数据源 2：Open-Meteo ────────────
def fetch_openmeteo(retries=2) -> str | None:
    """Open-Meteo - 完全免费，无需 API Key"""
    wmo_codes = {
        0: "晴天", 1: "少云", 2: "多云", 3: "阴天",
        45: "雾", 48: "雾凇",
        51: "小毛毛雨", 53: "毛毛雨", 55: "大毛毛雨",
        56: "冻毛毛雨", 57: "冻毛毛雨",
        61: "小雨", 63: "中雨", 65: "大雨",
        66: "冻雨", 67: "冻雨",
        71: "小雪", 73: "中雪", 75: "大雪",
        77: "雪粒",
        80: "阵雨", 81: "中阵雨", 82: "大阵雨",
        85: "小阵雪", 86: "大阵雪",
        95: "雷暴", 96: "雷暴+冰雹", 99: "强雷暴+冰雹",
    }
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": CITY_LAT,
                    "longitude": CITY_LON,
                    "daily": "weathercode,temperature_2m_max,temperature_2m_min,precipitation_sum,windspeed_10m_max",
                    "timezone": "Asia/Shanghai",
                    "forecast_days": 1,
                },
                timeout=10,
            )
            data = r.json()
            daily = data.get("daily", {})
            if daily.get("time"):
                today_date = daily["time"][0]
                wmo = daily.get("weathercode", [None])[0]
                weather_cn = wmo_codes.get(wmo, f"代码{wmo}")
                t_max = daily["temperature_2m_max"][0]
                t_min = daily["temperature_2m_min"][0]
                precip = daily.get("precipitation_sum", [0])[0]
                wind = daily.get("windspeed_10m_max", [0])[0]
                return (
                    f"## 🌤 **{CITY} 天气预报**\n"
                    f"> 📅 **日期：**{today_date}\n"
                    f"> ☀️ **白天：**{weather_cn}  {t_max}℃  降水{precip}mm\n"
                    f"> 🌙 **夜间：**最低 {t_min}℃  风力 {wind}km/h\n\n"
                    f"🦐 小虾米祝您今天有个好心情！"
                )
        except Exception as e:
            if attempt < retries:
                wait = 2 ** (attempt - 1)
                logger.warning(f"Open-Meteo第{attempt}次失败({e})，{wait}s后重试…")
                time.sleep(wait)
            else:
                logger.warning(f"Open-Meteo{retries}次均失败: {e}")
    return None


# ──────────── 数据源 3：wttr.in ────────────
def fetch_wttr(retries=2) -> str | None:
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(
                f"https://wttr.in/{CITY}?format=%C+%t+%w&lang=zh", timeout=10
            )
            text = r.text.strip()
            if text and not text.startswith("Unknown"):
                return (
                    f"## 🌤 **{CITY} 今日天气**\n\n"
                    f"> {text}\n\n"
                    f"🦐 小虾米祝您今天有个好心情！"
                )
        except Exception as e:
            if attempt < retries:
                wait = 2 ** (attempt - 1)
                logger.warning(f"wttr.in第{attempt}次失败({e})，{wait}s后重试…")
                time.sleep(wait)
            else:
                logger.warning(f"wttr.in{retries}次均失败: {e}")
    return None


# ──────────── 本地缓存 ────────────
def save_backup(text: str):
    try:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        now = datetime.now(BJT).isoformat()
        data = {"date": now, "city": CITY, "content": text}
        BACKUP_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("💾 天气已缓存到本地")
    except Exception as e:
        logger.warning(f"缓存写入失败: {e}")


def load_backup() -> str | None:
    try:
        if not BACKUP_FILE.exists():
            logger.warning("⚠️ 无本地缓存可用")
            return None
        data = json.loads(BACKUP_FILE.read_text(encoding="utf-8"))
        cached_time = datetime.fromisoformat(data["date"])
        age_hours = (datetime.now(BJT) - cached_time).total_seconds() / 3600

        if age_hours > 48:
            logger.warning(f"⚠️ 缓存已过期({age_hours:.0f}小时前)，丢弃")
            return None

        note = "⚠️ 天气服务暂不可用，以下为上次缓存数据"
        if age_hours > 24:
            note = f"⚠️ 数据已缓存{age_hours:.0f}小时，仅供参考"
        elif age_hours > 1:
            note = f"⚠️ 以下为{age_hours:.0f}小时前的缓存数据"

        result = f"{note}\n\n{data['content']}"
        logger.info(f"📂 使用本地缓存（{age_hours:.0f}小时前）")
        return result
    except Exception as e:
        logger.warning(f"缓存读取失败: {e}")
    return None


# ──────────── 主流程 ────────────
def get_weather() -> str:
    sources = [
        ("高德地图", fetch_amap),
        ("Open-Meteo", fetch_openmeteo),
        ("wttr.in", fetch_wttr),
    ]

    for name, fetcher in sources:
        logger.info(f"📡 尝试数据源: {name}")
        result = fetcher()
        if result:
            save_backup(result)
            return result
        logger.warning(f"❌ {name} 不可用，切换下一源")

    logger.error("⚠️ 所有天气数据源均不可用，尝试本地缓存")
    backup = load_backup()
    if backup:
        return backup

    return (
        f"## 🌤 **{CITY} 今日天气**\n\n"
        f"抱歉，天气服务和本地缓存均不可用～\n\n"
        f"🦐 小虾米"
    )


def send_to_group(content: str):
    payload = {
        "msgtype": "markdown",
        "markdown": {"title": "早安天气 ☀️", "text": content},
    }
    for attempt in range(1, 4):
        try:
            r = requests.post(WEBHOOK_URL, json=payload, timeout=10)
            data = r.json()
            if data.get("errcode") == 0:
                logger.info("✅ 钉钉推送成功！")
                return
            logger.warning(f"钉钉返回异常: {data}")
        except Exception as e:
            if attempt < 3:
                logger.warning(f"钉钉推送第{attempt}次失败({e})，重试…")
                time.sleep(2)
            else:
                logger.error(f"❌ 钉钉推送3次均失败: {e}")


def main():
    if not WEBHOOK_URL:
        logger.error("❌ 未设置 WEBHOOK_URL 环境变量")
        return

    logger.info(f"🌤 开始每日天气推送 - {CITY}")
    msg = get_weather()
    logger.info(f"\n{msg}")
    send_to_group(msg)
    logger.info("🎉 推送完成！")


if __name__ == "__main__":
    main()
