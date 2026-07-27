#!/usr/bin/env python3
"""
痛点扫描器 — 从论坛和社交媒体中发现用户痛点

用法:
    python3 pain-scanner.py --platform xiaohongshu --keyword "求推荐" --count 20
    python3 pain-scanner.py --platform v2ex --keyword "有没有" --count 10
    python3 pain-scanner.py --interactive

依赖: pip3 install requests beautifulsoup4
"""

import argparse
import re
import json
import sys
from datetime import datetime
from urllib.parse import quote, urlparse
import time

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("请先安装依赖: pip3 install requests beautifulsoup4")
    sys.exit(1)

# ============================================================
# 痛点关键词词典（含否定/需求/抱怨模式）
# ============================================================

PAIN_KEYWORDS_CN = [
    # 直接痛点
    "求推荐", "有没有.*工具", "受不了", "太麻烦了", "有没有办法",
    "怎么解决", "忍了很久", "好烦", "崩溃", "太难用了",
    # 需求表达
    "要是有.*就好了", "希望能", "什么时候能有", "为什么没有",
    # 对比抱怨
    "还不如", "比不上", "竟然不能", "居然没有",
    # 效率相关
    "浪费时间", "效率太低", "花了很多时间", "每次都要",
    "手动.*麻烦", "重复.*操作",
]

PAIN_KEYWORDS_EN = [
    "I wish there was", "Is there a tool for", "Is there a way to",
    "so annoying", "so frustrating", "why is there no",
    "there should be", "hate it when", "waste of time",
    "every time I have to", "looking for a better",
    "anyone know a tool", "recommend me a",
]

# ============================================================
# 平台配置
# ============================================================

PLATFORMS = {
    "v2ex": {
        "name": "V2EX",
        "base_url": "https://www.v2ex.com",
        "search_url": "https://www.v2ex.com/search?q={keyword}",
        "selectors": {
            "item": ".item",
            "title": ".topic-link",
            "link": ".topic-link",
            "replies": ".count_livid",
        },
    },
    "xiaohongshu": {
        "name": "小红书",
        "note": "小红书需要登录 Cookie 才能抓取，建议使用手动搜索",
    },
    "zhihu": {
        "name": "知乎",
        "base_url": "https://www.zhihu.com",
        "search_url": "https://www.zhihu.com/search?type=content&q={keyword}",
    },
    "reddit": {
        "name": "Reddit",
        "search_url": "https://www.reddit.com/search/?q={keyword}&sort=comments",
    },
}


def pain_score(text):
    """对文本进行痛点强度评分 (0-100)"""
    score = 0
    
    # 强情绪词
    strong = ["崩溃", "受不了", "忍了很久", "太麻烦了", "好烦", "要疯了",
              "frustrating", "hate", "terrible", "awful", "ridiculous"]
    for w in strong:
        if w in text.lower():
            score += 20
    
    # 付出代价（时间/金钱）
    cost = ["花了.*小时", "浪费.*时间", "花了.*钱", "贵", "不值",
            "waste of time", "cost.*money", "overpriced"]
    for w in cost:
        if re.search(w, text.lower()):
            score += 15
    
    # 反复模式
    repeat = ["每次都要", "每天都要", "反复", "一直", "总是",
              "every time", "always have to", "constantly"]
    for w in repeat:
        if re.search(w, text.lower()):
            score += 15
    
    # 对比抱怨（有期望但被辜负）
    compare = ["还不如", "比不上", "竟然不能", "居然没有",
               "wish.*could", "should be able to", "why can't"]
    for w in compare:
        if re.search(w, text.lower()):
            score += 10
    
    return min(score, 100)


def extract_pain_points(text, max_length=300):
    """从文本中提取痛点关键句"""
    points = []
    sentences = re.split(r'[。！？.!?\n]', text)
    for s in sentences:
        s = s.strip()
        if len(s) > 10 and len(s) < max_length:
            for kw in PAIN_KEYWORDS_CN + PAIN_KEYWORDS_EN:
                if kw.replace(".*", "") in s.lower():
                    if s not in points:
                        points.append(s)
                    break
    return points


def scan_v2ex(keyword, count=20):
    """扫描 V2EX 搜索"""
    results = []
    url = PLATFORMS["v2ex"]["search_url"].format(keyword=quote(keyword))
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.encoding = 'utf-8'
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        for item in soup.select(".item")[:count]:
            title_el = item.select_one(".topic-link")
            if not title_el:
                continue
            
            title = title_el.get_text(strip=True)
            link = PLATFORMS["v2ex"]["base_url"] + title_el.get("href", "")
            replies_el = item.select_one(".count_livid")
            replies = int(replies_el.get_text(strip=True)) if replies_el else 0
            
            score = pain_score(title)
            
            results.append({
                "platform": "v2ex",
                "title": title,
                "url": link,
                "replies": replies,
                "pain_score": score,
                "scanned_at": datetime.now().isoformat(),
            })
    except Exception as e:
        print(f"  ⚠️ V2EX 扫描出错: {e}")
    
    return results


def scan_reddit(keyword, count=20):
    """扫描 Reddit 搜索"""
    results = []
    search_url = f"https://www.reddit.com/search.json?q={quote(keyword)}&sort=comments&limit={count}"
    
    headers = {
        "User-Agent": "python:startup-lab-pain-scanner:v0.1 (by /u/example)"
    }
    
    try:
        resp = requests.get(search_url, headers=headers, timeout=10)
        data = resp.json()
        
        for post in data.get("data", {}).get("children", [])[:count]:
            p = post["data"]
            title = p.get("title", "")
            text = p.get("selftext", "")
            full_text = title + " " + text
            score = pain_score(full_text)
            pain_points = extract_pain_points(full_text)
            
            results.append({
                "platform": "reddit",
                "subreddit": p.get("subreddit_name_prefixed", ""),
                "title": title,
                "url": f"https://reddit.com{p.get('permalink', '')}",
                "comments": p.get("num_comments", 0),
                "upvotes": p.get("score", 0),
                "pain_score": score,
                "pain_points": pain_points,
                "scanned_at": datetime.now().isoformat(),
            })
    except Exception as e:
        print(f"  ⚠️ Reddit 扫描出错: {e}")
    
    return results


def interactive_mode():
    """交互模式：手动输入痛点"""
    print("\n" + "=" * 50)
    print("  🔍 痛点发现 - 交互模式")
    print("=" * 50)
    print("\n从你的日常中挖掘痛点。回答以下问题：\n")
    
    questions = [
        ("今天有什么事让你感到烦躁或浪费时间？", ""),
        ("有没有一件事你每周/每天都要手动重复做？", ""),
        ("有没有你想做但因为缺工具而放弃的事？", ""),
        ("有没有一个流程你需要切换 3 个以上工具/App？", ""),
        ("最近有没有买了一个工具/App但发现不好用的？", ""),
    ]
    
    answers = []
    for q, _ in questions:
        ans = input(f"Q: {q}\nA: ").strip()
        if ans:
            answers.append({"question": q, "answer": ans})
    
    print("\n" + "=" * 50)
    print("  📊 分析结果")
    print("=" * 50)
    
    for a in answers:
        score = pain_score(a["answer"])
        bar = "█" * (score // 5) + "░" * (20 - score // 5)
        print(f"\n痛点强度: [{bar}] {score}/100")
        print(f"描述: {a['answer'][:100]}")
    
    # 保存
    filename = f"pain-scan-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(answers, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 已保存到 {filename}")
    
    return answers


def main():
    parser = argparse.ArgumentParser(
        description="痛点扫描器 - 从论坛和社交媒体发现用户痛点"
    )
    parser.add_argument("--platform", choices=["v2ex", "reddit", "all"],
                        help="扫描平台")
    parser.add_argument("--keyword", type=str, help="搜索关键词")
    parser.add_argument("--count", type=int, default=20, help="结果数量")
    parser.add_argument("--interactive", "-i", action="store_true",
                        help="交互模式（手动记录日常痛点）")
    parser.add_argument("--output", "-o", type=str, help="输出 JSON 文件路径")
    
    args = parser.parse_args()
    
    if args.interactive:
        interactive_mode()
        return
    
    if not args.keyword:
        # 默认：扫描常用痛点关键词
        print("未指定关键词，使用默认痛点词典扫描...\n")
        all_results = []
        for kw in ["求推荐 工具", "有没有 软件", "效率 太低", "自动 化 工具"]:
            print(f"🔍 搜索: {kw}")
            if args.platform in ("v2ex", "all") or not args.platform:
                results = scan_v2ex(kw, args.count // 4)
                all_results.extend(results)
                print(f"  V2EX: {len(results)} 条")
            time.sleep(1)
    else:
        all_results = []
        if args.platform in ("v2ex", "all") or not args.platform:
            all_results.extend(scan_v2ex(args.keyword, args.count))
        if args.platform in ("reddit", "all") or not args.platform:
            all_results.extend(scan_reddit(args.keyword, args.count))
    
    # 按痛点评分排序
    all_results.sort(key=lambda x: x.get("pain_score", 0), reverse=True)
    
    print(f"\n{'='*60}")
    print(f"  📊 扫描结果 (共 {len(all_results)} 条)")
    print(f"{'='*60}\n")
    
    for i, r in enumerate(all_results[:20]):
        score = r.get("pain_score", 0)
        emoji = "🔴" if score > 70 else "🟠" if score > 40 else "🟡"
        print(f"{i+1:2d}. {emoji} [{score:3d}] {r.get('title','')[:80]}")
        if r.get("pain_points"):
            for p in r["pain_points"][:2]:
                print(f"     └ {p[:100]}")
    
    # 输出文件
    if args.output or not args.interactive:
        outfile = args.output or f"pain-results-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        with open(outfile, 'w', encoding='utf-8') as f:
            json.dump(all_results, f, ensure_ascii=False, indent=2)
        print(f"\n✅ 完整结果已保存到 {outfile}")


if __name__ == "__main__":
    main()
