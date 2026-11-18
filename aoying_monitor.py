#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
币安带单「熬鹰资本」开仓提醒 → Bark（云端版，配合 GitHub Actions）

运行方式：
  本地单次：  python3 aoying_monitor.py
  云端：      GitHub Actions 每 5 分钟自动运行一次

去重原理：用 state.json 记录已推送过的订单指纹，
          每次运行只推「新的」订单，避免重复推送。
          state.json 由 GitHub Actions 自动 commit 回仓库。

BARK_KEY 从环境变量读取（GitHub secret），本地运行也可直接改脚本。
"""

import json
import os
import time
import urllib.parse
import urllib.request

# ==================== 配置 ====================
PORTFOLIO_ID = "5075281354358777856"          # 熬鹰资本的项目ID
BARK_KEY = os.environ.get("BARK_KEY", "t6WzKWURnimGPZcZBVekQJ")
STATE_FILE = "state.json"                      # 去重状态文件
LOOKBACK_MIN = 10                              # 回看分钟数（比调度间隔大，防漏单）
MAX_SEEN = 300                                 # 最多保留的订单指纹数
PUSH_CLOSE = True                              # True=开平仓都推，False=只推开仓
# ==============================================

API = "https://www.binance.com/bapi/futures/v1/friendly/future/copy-trade/lead-portfolio/order-history"


def fetch_orders(start_ms, end_ms):
    body = json.dumps({
        "portfolioId": PORTFOLIO_ID,
        "startTime": start_ms,
        "endTime": end_ms,
        "pageSize": 50,
    }).encode("utf-8")
    req = urllib.request.Request(API, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("clienttype", "web")
    req.add_header("lang", "zh-CN")
    req.add_header("User-Agent", "Mozilla/5.0")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def bark_push(title, content):
    url = "https://api.day.app/{}/{}/{}".format(
        BARK_KEY, urllib.parse.quote(title), urllib.parse.quote(content))
    try:
        urllib.request.urlopen(url, timeout=10)
        return True
    except Exception as e:
        print("[bark] 推送失败:", e)
        return False


def classify(side, pnl):
    is_open = abs(float(pnl or 0)) < 0.0001
    if side == "BUY":
        return "开多" if is_open else "平空"
    return "开空" if is_open else "平多"


def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"seen": []}


def save_state(s):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False)


def main():
    state = load_state()
    seen = set(state.get("seen", []))

    now_ms = int(time.time() * 1000)
    start = now_ms - LOOKBACK_MIN * 60 * 1000

    try:
        d = fetch_orders(start, now_ms)
    except Exception as e:
        print("[error] 拉取订单失败:", e)
        return

    if not d.get("success"):
        print("[warn] 接口异常:", d.get("message"))
        return

    orders = d.get("data", {}).get("list", [])
    pushed = 0

    for o in orders:
        fp = (
            o.get("orderTime"),
            o.get("symbol"),
            o.get("side"),
            o.get("executedQty"),
            o.get("avgPrice"),
        )
        if fp in seen:
            continue
        seen.add(fp)

        action = classify(o.get("side"), o.get("totalPnl"))
        if not PUSH_CLOSE and action not in ("开多", "开空"):
            continue

        content = "{} {} {} {} @ {:.2f}".format(
            o.get("symbol"), action, o.get("executedQty"),
            o.get("side"), float(o.get("avgPrice") or 0))
        print("[推送]", content)
        bark_push("熬鹰提醒", content)
        pushed += 1

    state["seen"] = list(seen)[-MAX_SEEN:]
    save_state(state)
    print("检查完成：回看 {} 分钟，新推送 {} 条".format(LOOKBACK_MIN, pushed))


if __name__ == "__main__":
    main()
