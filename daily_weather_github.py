"""
每日天气推送 - GitHub Actions 版
环境变量：
  WEBHOOK_URL = 钉钉群机器人 Webhook 地址
  CITY        = 城市名（默认淄博）
"""

import os
import logging
import requests

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s")
logger = logging.getLogger("daily-weather")

CITY = os.getenv("CITY", "淄博")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")


def get_weather() -> str:
    """获取天气信息"""
    try:
        r = requests.get(
            "https://restapi.amap.com/v3/weather/weatherInfo",
            params={
                "key": "a3c6ef0b9f79b7b7b7b7b7b7b7b7b7b7",
                "city": CITY,
                "extensions": "all"
            },
            timeout=10
        )
        data = r.json()
        if data.get("status") == "1" and data.get("count", "0") != "0":
            forecast = data["forecasts"][0]
            today = forecast["casts"][0]
            return (
                f"## 🌤 **{CITY} 天气预报**\n"
                f"> 📅 **日期：**{today['date']}\n"
                f"> ☀️ **白天：**{today['dayweather']}  {today['daytemp']}℃  {today['daywind']}\n"
                f"> 🌙 **夜间：**{today['nightweather']}  {today['nighttemp']}℃  {today['nightwind']}\n\n"
                f"🦐 小虾米祝您今天有个好心情！"
            )
    except Exception as e:
        logger.warning(f"高德天气失败: {e}")

    # 备用方案
    try:
        r = requests.get(f"https://wttr.in/{CITY}?format=%C+%t+%w&lang=zh", timeout=10)
        return (
            f"## 🌤 **{CITY} 今日天气**\n\n"
            f"> {r.text.strip()}\n\n"
            f"🦐 小虾米祝您今天有个好心情！"
        )
    except Exception as e:
        logger.warning(f"备用天气失败: {e}")
        return (
            f"## 🌤 **{CITY} 今日天气**\n\n"
            f"抱歉，天气服务暂不可用～\n\n"
            f"🦐 小虾米"
        )


def send_to_group(content: str):
    payload = {
        "msgtype": "markdown",
        "markdown": {
            "title": "早安天气 ☀️",
            "text": content
        }
    }
    r = requests.post(WEBHOOK_URL, json=payload, timeout=10)
    data = r.json()
    if data.get("errcode") == 0:
        logger.info("✅ 发送成功")
    else:
        logger.error(f"❌ 发送失败: {data}")


def main():
    if not WEBHOOK_URL:
        logger.error("❌ 未设置 WEBHOOK_URL 环境变量")
        return

    msg = get_weather()
    logger.info(f"天气:\n{msg}")
    send_to_group(msg)


if __name__ == "__main__":
    main()
