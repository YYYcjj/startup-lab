#!/usr/bin/env python3
"""
专利查重辅助工具 — 查询已有专利，避免重复发明

用法:
    python3 patent-check.py --query "基于 NLP 的自动记账方法"
    python3 patent-check.py --query "智能家居 自然语言 自动化" --source google
    python3 patent-check.py --file patent-brief.md

依赖: pip3 install requests
"""

import argparse
import json
import re
import sys
from datetime import datetime
from urllib.parse import quote

try:
    import requests
except ImportError:
    print("请先安装依赖: pip3 install requests")
    sys.exit(1)


# ============================================================
# Google Patents API（非官方，基于网页搜索）
# ============================================================

def search_google_patents(query, count=20):
    """通过 Google Patents 搜索"""
    url = "https://patents.google.com/"
    params = {
        "q": query,
        "num": count,
        "language": "ZH",
    }
    
    # 使用 Google Patents 的 JSON API
    api_url = f"https://patents.google.com/patents/search?q={quote(query)}&num={count}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
    }
    
    try:
        resp = requests.get(api_url, headers=headers, timeout=15)
        data = resp.json()
        
        results = []
        for item in data.get("results", [])[:count]:
            patent = item.get("patent", {})
            results.append({
                "id": patent.get("patentNumber", ""),
                "title": patent.get("title", ""),
                "assignee": patent.get("assignee", ""),
                "date": patent.get("publicationDate", ""),
                "abstract": (patent.get("abstract", "") or "")[:300],
                "url": f"https://patents.google.com/patent/{patent.get('patentNumber', '')}",
            })
        return results
    except Exception as e:
        print(f"⚠️ Google Patents 查询出错: {e}")
        return []


def search_cn_patents(query, count=20):
    """通过中国专利公布公告系统搜索（简化版）"""
    url = "http://epub.sipo.gov.cn/advancedSearch"
    print(f"🔍 中国专利检索请访问: {url}")
    print(f"   搜索关键词: {query}")
    print("   （中国专利系统需要手动查询，建议同时使用 Google Patents）")
    return []


def search_soopat(query, count=20):
    """通过 SooPAT 搜索"""
    url = f"http://www.soopat.com/Home/Result?SearchWord={quote(query)}"
    print(f"🔍 SooPAT 搜索: {url}")
    return []


def analyze_overlap(query, results):
    """分析搜索结果与查询的相关度"""
    if not results:
        return {"risk_level": "unknown", "overlapping_patents": []}
    
    query_terms = set(re.findall(r'[\u4e00-\u9fff\w]+', query.lower()))
    overlapping = []
    
    for r in results:
        title_terms = set(re.findall(r'[\u4e00-\u9fff\w]+', 
                                     r.get("title", "").lower()))
        abstract = r.get("abstract", "").lower()
        abstract_terms = set(re.findall(r'[\u4e00-\u9fff\w]+', abstract))
        
        # 计算关键词重叠度
        title_overlap = len(query_terms & title_terms) / max(len(query_terms), 1)
        abstract_overlap = len(query_terms & abstract_terms) / max(len(query_terms), 1)
        total_overlap = max(title_overlap, abstract_overlap * 0.7)
        
        if total_overlap > 0.3:
            overlapping.append({
                **r,
                "overlap_score": round(total_overlap * 100, 1),
            })
    
    overlapping.sort(key=lambda x: x.get("overlap_score", 0), reverse=True)
    
    # 风险评估
    if overlapping and overlapping[0].get("overlap_score", 0) > 70:
        risk = "🔴 高风险 — 存在高度相似的专利，建议调整技术方案"
    elif overlapping and overlapping[0].get("overlap_score", 0) > 40:
        risk = "🟠 中风险 — 存在部分重叠，需要差异化设计"
    elif overlapping:
        risk = "🟡 低风险 — 有一些相关专利，但重叠度不高"
    else:
        risk = "🟢 低风险 — 未发现明显重叠的专利"
    
    return {
        "risk_level": risk,
        "overlapping_patents": overlapping[:10],
        "total_patents_searched": len(results),
    }


def check_from_file(filepath):
    """从专利交底书文件中提取查询关键词"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 提取发明名称
        name_match = re.search(r'发明名称.*?\n.*?([^\n]+)', content)
        name = name_match.group(1).strip() if name_match else ""
        
        # 提取技术领域
        field_match = re.search(r'技术领域.*?\n.*?([^\n]+)', content)
        field = field_match.group(1).strip() if field_match else ""
        
        query = name or field or filepath
        print(f"📄 从 {filepath} 提取查询: {query}")
        return query
    except Exception as e:
        print(f"⚠️ 文件读取失败: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(
        description="专利查重辅助工具"
    )
    parser.add_argument("--query", "-q", type=str, help="搜索关键词")
    parser.add_argument("--file", "-f", type=str, help="从专利交底书文件提取关键词")
    parser.add_argument("--source", choices=["google", "cn", "all"], 
                        default="google", help="专利数据源")
    parser.add_argument("--count", "-n", type=int, default=20, help="结果数量")
    parser.add_argument("--output", "-o", type=str, help="输出 JSON 文件")
    
    args = parser.parse_args()
    
    if args.file:
        query = check_from_file(args.file)
        if not query:
            sys.exit(1)
    elif args.query:
        query = args.query
    else:
        print("请指定 --query 或 --file")
        sys.exit(1)
    
    print(f"\n{'='*60}")
    print(f"  🔍 专利查重: {query}")
    print(f"{'='*60}\n")
    
    all_results = []
    
    if args.source in ("google", "all"):
        print("📡 查询 Google Patents...")
        results = search_google_patents(query, args.count)
        all_results.extend(results)
        print(f"   找到 {len(results)} 条相关专利")
    
    if args.source in ("cn", "all"):
        search_cn_patents(query, args.count)
    
    if args.source in ("all"):
        search_soopat(query, args.count)
    
    # 分析重叠度
    analysis = analyze_overlap(query, all_results)
    
    print(f"\n{'='*60}")
    print(f"  📊 分析报告")
    print(f"{'='*60}\n")
    print(f"风险评估: {analysis['risk_level']}\n")
    
    if analysis["overlapping_patents"]:
        print("⚠️ 需要关注的专利:\n")
        for i, p in enumerate(analysis["overlapping_patents"][:5]):
            print(f"  {i+1}. [{p.get('overlap_score',0):.0f}%] {p.get('title','')}")
            print(f"     申请号: {p.get('id','')}")
            print(f"     申请人: {p.get('assignee','')}")
            print(f"     日期: {p.get('date','')}")
            print(f"     摘要: {p.get('abstract','')[:150]}...")
            print(f"     链接: {p.get('url','')}\n")
    
    print(f"📝 建议:")
    if "🔴" in analysis["risk_level"]:
        print("  1. 仔细阅读高度重叠专利的权利要求书")
        print("  2. 寻找可以差异化的技术点")
        print("  3. 考虑从属权利要求绕过策略")
    elif "🟠" in analysis["risk_level"]:
        print("  1. 在交底书中明确与现有专利的技术区别")
        print("  2. 强调你的创新点带来的独特技术效果")
    else:
        print("  1. 继续推进专利设计")
        print("  2. 在正式申请前进行专业检索")
    
    # 输出
    output = {
        "query": query,
        "search_time": datetime.now().isoformat(),
        "total_results": len(all_results),
        "analysis": analysis,
        "all_results": all_results,
    }
    
    outfile = args.output or f"patent-check-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    with open(outfile, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 完整报告已保存到 {outfile}")


if __name__ == "__main__":
    main()
