"""
iPhone 17 Pro 買取価格スクレイパー
対象: 買取商店 / 買取wiki / 買取ルデヤ
"""

import requests
from bs4 import BeautifulSoup
import json
import re
import time
from datetime import datetime, timezone, timedelta

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

JST = timezone(timedelta(hours=9))


def clean_price(text: str) -> int | None:
    """'196,000円' → 196000"""
    if not text:
        return None
    digits = re.sub(r"[^\d]", "", text)
    val = int(digits) if digits else None
    # 明らかに変な値を除外（1万円未満 or 500万円超）
    if val and (val < 10000 or val > 5000000):
        return None
    return val


def fetch(url: str) -> BeautifulSoup | None:
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        res.raise_for_status()
        res.encoding = res.apparent_encoding
        return BeautifulSoup(res.text, "html.parser")
    except Exception as e:
        print(f"  FETCH ERROR {url}: {e}")
        return None


# ──────────────────────────────────────────────
#  買取商店  https://iphone-shoten.com/kaitori
# ──────────────────────────────────────────────
def scrape_shoten() -> dict:
    print("[買取商店] スクレイプ中...")
    soup = fetch("https://iphone-shoten.com/kaitori")
    result = {"256GB": None, "512GB": None, "error": None}

    if soup is None:
        result["error"] = "取得失敗"
        return result

    # iPhone 17 Pro セクションを探す（アンカー #iphone17pro 付近）
    # ページテキスト全体から "17 Pro" の価格行を探す
    text = soup.get_text("\n")
    lines = text.splitlines()

    # 256GB / 512GB の価格を正規表現で探す
    for i, line in enumerate(lines):
        if "17 Pro" not in line and "iPhone17Pro" not in line.replace(" ", ""):
            continue
        # 前後30行を結合して検索
        block = "\n".join(lines[max(0, i-2):i+30])

        for cap in ["256", "512"]:
            if cap not in block:
                continue
            key = f"{cap}GB"
            if result[key] is not None:
                continue
            # 価格パターンを探す
            prices = re.findall(r"[\d,]{6,9}円?", block)
            for p in prices:
                val = clean_price(p)
                if val:
                    result[key] = val
                    break

    if result["256GB"] is None and result["512GB"] is None:
        # フォールバック: ページ内の全価格から推測
        all_prices = re.findall(r"([\d,]{6,9})円", text)
        vals = sorted([clean_price(p) for p in all_prices if clean_price(p)], reverse=True)
        if len(vals) >= 2:
            result["error"] = "構造変更の可能性あり（推定値）"

    print(f"  256GB: {result['256GB']}, 512GB: {result['512GB']}")
    return result


# ──────────────────────────────────────────────
#  買取wiki  https://iphonekaitori.tokyo
# ──────────────────────────────────────────────
WIKI_URLS = {
    "256GB": [
        "https://iphonekaitori.tokyo/purchase/iPhone-17-Pro-256GB-silver",
        "https://iphonekaitori.tokyo/purchase/iPhone-17-Pro-256GB-black",
        "https://iphonekaitori.tokyo/purchase/iPhone-17-Pro-256GB",
    ],
    "512GB": [
        "https://iphonekaitori.tokyo/purchase/iPhone-17-Pro-512GB-Silver",
        "https://iphonekaitori.tokyo/purchase/iPhone-17-Pro-512GB-black",
        "https://iphonekaitori.tokyo/purchase/iPhone-17-Pro-512GB",
    ],
}


def scrape_wiki() -> dict:
    print("[買取wiki] スクレイプ中...")
    result = {"256GB": None, "512GB": None, "error": None}

    for cap, urls in WIKI_URLS.items():
        for url in urls:
            soup = fetch(url)
            if soup is None:
                continue

            text = soup.get_text("\n")

            # "買取価格: 195000円" パターン
            m = re.search(r"買取価格[：:]\s*([\d,]+)\s*円", text)
            if m:
                val = clean_price(m.group(1))
                if val:
                    result[cap] = val
                    print(f"  {cap}: {val} ({url})")
                    break

            # フォールバック: ページ内最大価格
            if result[cap] is None:
                prices = re.findall(r"([\d,]{6,9})円", text)
                vals = [clean_price(p) for p in prices if clean_price(p)]
                if vals:
                    result[cap] = max(vals)
                    print(f"  {cap}: {result[cap]} (フォールバック)")
                    break

            time.sleep(0.5)

    if result["256GB"] is None and result["512GB"] is None:
        result["error"] = "取得失敗"
    return result


# ──────────────────────────────────────────────
#  買取ルデヤ  https://kaitori-rudeya.com
# ──────────────────────────────────────────────
def scrape_rudeya() -> dict:
    print("[買取ルデヤ] スクレイプ中...")
    url = "https://kaitori-rudeya.com/category/detail/219/"
    result = {"256GB": None, "512GB": None, "error": None}

    soup = fetch(url)
    if soup is None:
        result["error"] = "取得失敗"
        return result

    # 商品カードを探す（a タグ + テキストに "17 Pro" を含む）
    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True)
        if "17 Pro" not in text and "iPhone17Pro" not in text.replace(" ", ""):
            continue

        for cap in ["256", "512"]:
            key = f"{cap}GB"
            if cap not in text:
                continue
            if result[key] is not None:
                continue

            # このカード要素の親を少し広げて価格を探す
            parent = a.parent
            for _ in range(4):
                if parent is None:
                    break
                price_text = parent.get_text("\n")
                prices = re.findall(r"([\d,]{6,9})円", price_text)
                vals = [clean_price(p) for p in prices if clean_price(p)]
                if vals:
                    result[key] = max(vals)
                    break
                parent = parent.parent

    # フォールバック: ページ全体から "256GB" "512GB" 付近の価格を探す
    if result["256GB"] is None or result["512GB"] is None:
        text = soup.get_text("\n")
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if "17 Pro" not in line:
                continue
            block = "\n".join(lines[max(0, i-1):i+10])
            for cap in ["256", "512"]:
                key = f"{cap}GB"
                if result[key] is not None:
                    continue
                if cap not in block:
                    continue
                prices = re.findall(r"([\d,]{6,9})円?", block)
                vals = [clean_price(p) for p in prices if clean_price(p)]
                if vals:
                    result[key] = max(vals)

    print(f"  256GB: {result['256GB']}, 512GB: {result['512GB']}")
    return result


# ──────────────────────────────────────────────
#  メイン
# ──────────────────────────────────────────────
def main():
    print(f"=== スクレイプ開始 {datetime.now(JST).strftime('%Y-%m-%d %H:%M')} ===\n")

    stores = {
        "shoten": {
            "name": "買取商店",
            "url": "https://iphone-shoten.com/kaitori",
            **scrape_shoten(),
        },
        "wiki": {
            "name": "買取wiki",
            "url": "https://iphonekaitori.tokyo",
            **scrape_wiki(),
        },
        "rudeya": {
            "name": "買取ルデヤ",
            "url": "https://kaitori-rudeya.com/category/detail/219/",
            **scrape_rudeya(),
        },
    }

    output = {
        "updated_at": datetime.now(JST).strftime("%Y-%m-%d %H:%M"),
        "stores": stores,
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n=== 保存完了: data.json ===")
    for k, v in stores.items():
        print(f"  {v['name']:10s}  256GB: {v['256GB']}  512GB: {v['512GB']}")


if __name__ == "__main__":
    main()
