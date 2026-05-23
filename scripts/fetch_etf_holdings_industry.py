#!/usr/bin/env python3
"""
ETF持仓行业穿透估值脚本 v1.1
功能：通过ETF重仓股→申万行业→行业PE/PB，为无分位数据的ETF估算估值

输入：
- etf_valuation_latest.json（现有估值数据，含申万行业PE/PB）
- stock_to_sw_industry.json（股票→申万行业映射）

输出：
- etf_holding_industry_valuation.json（ETF行业穿透估值数据）
"""

import akshare as ak
import pandas as pd
import json
import time
import sys
from datetime import datetime
from pathlib import Path

# 配置
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / 'data'
OUTPUT_DIR = BASE_DIR / 'output'


def load_mappings():
    """加载股票→申万行业映射和申万行业PE/PB数据"""
    # 股票→申万行业映射
    mapping_file = DATA_DIR / 'stock_to_sw_industry.json'
    if mapping_file.exists():
        with open(mapping_file) as f:
            d = json.load(f)
            stock_to_sw = d.get('mapping', {})
        print(f'已加载股票→申万行业映射(v{d.get("version","1")}): {len(stock_to_sw)}只股票')
    else:
        stock_to_sw = {}
        print('⚠️ 未找到股票→申万行业映射文件')
    
    # 申万行业PE/PB数据 - 从enricher数据中提取
    valuation_file = DATA_DIR / 'etf_valuation_latest.json'
    sw_industry_pe_pb = {}
    if valuation_file.exists():
        with open(valuation_file) as f:
            d = json.load(f)
            for etf in d.get('data', []):
                src = etf.get('pe_pb_source', '')
                if src.startswith('申万-'):
                    ind_name = src.split('-')[1].split('(')[0]
                    pe = etf.get('pe_ttm')
                    pb = etf.get('pb')
                    pe_pct = etf.get('pe_percentile')
                    pb_pct = etf.get('pb_percentile')
                    # 用行业PE/PB中位数（多只同行业ETF取平均）
                    if ind_name not in sw_industry_pe_pb:
                        sw_industry_pe_pb[ind_name] = {'pes': [], 'pbs': [], 'pe_pcts': [], 'pb_pcts': []}
                    if pe and pe > 0:
                        sw_industry_pe_pb[ind_name]['pes'].append(pe)
                    if pb and pb > 0:
                        sw_industry_pe_pb[ind_name]['pbs'].append(pb)
                    if pe_pct is not None:
                        sw_industry_pe_pb[ind_name]['pe_pcts'].append(pe_pct)
                    if pb_pct is not None:
                        sw_industry_pe_pb[ind_name]['pb_pcts'].append(pb_pct)
            
            # 取中位数
            for ind, vals in sw_industry_pe_pb.items():
                sw_industry_pe_pb[ind] = {
                    'pe': pd.Series(vals['pes']).median() if vals['pes'] else None,
                    'pb': pd.Series(vals['pbs']).median() if vals['pbs'] else None,
                    'pe_percentile': pd.Series(vals['pe_pcts']).median() if vals['pe_pcts'] else None,
                    'pb_percentile': pd.Series(vals['pb_pcts']).median() if vals['pb_pcts'] else None,
                }
        print(f'已提取申万行业PE/PB: {len(sw_industry_pe_pb)}个行业')
    
    return stock_to_sw, sw_industry_pe_pb


def get_etf_holdings(etf_code, year='2024'):
    """获取ETF的重仓股（最新季度top 10）"""
    pure_code = etf_code[2:] if etf_code.startswith(('sh', 'sz')) else etf_code
    
    try:
        df = ak.fund_portfolio_hold_em(symbol=pure_code, date=year)
        if len(df) == 0:
            return None, None
        
        # 只取最新季度
        latest_q = df['季度'].iloc[0]
        latest_holdings = df[df['季度'] == latest_q].head(10)  # 最多取10只
        
        holdings = []
        for _, row in latest_holdings.iterrows():
            weight_pct = float(row['占净值比例']) if row['占净值比例'] else 0
            holdings.append({
                'stock_code': row['股票代码'],
                'stock_name': row['股票名称'],
                'weight_pct': weight_pct,  # 百分比（如5.00=5%）
                'weight': weight_pct / 100.0,  # 小数（如0.05=5%）
            })
        
        return holdings, latest_q
    except Exception as e:
        return None, None


def estimate_etf_valuation(holdings, stock_to_sw, sw_industry_pe_pb):
    """通过行业穿透估算ETF估值"""
    if not holdings:
        return None
    
    # 映射重仓股到行业，计算行业权重
    industry_weights = {}  # 行业 → 累计权重（小数）
    mapped_weight = 0
    total_weight = sum(h['weight'] for h in holdings)
    unmapped_stocks = []
    
    for h in holdings:
        stock_code = h['stock_code']
        w = h['weight']
        industry = stock_to_sw.get(stock_code)
        
        if industry:
            industry_weights[industry] = industry_weights.get(industry, 0) + w
            mapped_weight += w
        else:
            unmapped_stocks.append(f"{h['stock_code']}({h['stock_name']})")
    
    coverage = mapped_weight / total_weight if total_weight > 0 else 0
    
    if coverage < 0.3:
        return {
            'status': 'low_coverage',
            'mapped_weight_pct': round(coverage * 100, 1),
            'unmapped_stocks': unmapped_stocks[:5],
            'message': f'持仓映射覆盖率{coverage*100:.1f}%，估值不可靠'
        }
    
    # 用行业PE/PB加权估算
    pe_sum = 0
    pb_sum = 0
    pe_pct_sum = 0
    pb_pct_sum = 0
    
    for ind, w in industry_weights.items():
        ind_data = sw_industry_pe_pb.get(ind, {})
        pe = ind_data.get('pe')
        pb = ind_data.get('pb')
        pe_pct = ind_data.get('pe_percentile')
        pb_pct = ind_data.get('pb_percentile')
        
        if pe and pe > 0:
            pe_sum += w * pe
        if pb and pb > 0:
            pb_sum += w * pb
        if pe_pct is not None:
            pe_pct_sum += w * pe_pct
        if pb_pct is not None:
            pb_pct_sum += w * pb_pct
    
    # 归一化：用mapped_weight归一化
    estimated_pe = round(pe_sum / mapped_weight, 2) if pe_sum > 0 else None
    estimated_pb = round(pb_sum / mapped_weight, 2) if pb_sum > 0 else None
    estimated_pe_pct = round(pe_pct_sum / mapped_weight, 1) if pe_pct_sum > 0 else None
    estimated_pb_pct = round(pb_pct_sum / mapped_weight, 1) if pb_pct_sum > 0 else None
    
    return {
        'status': 'success',
        'mapped_weight_pct': round(coverage * 100, 1),
        'industry_weights': {k: round(v * 100, 2) for k, v in industry_weights.items()},
        'unmapped_count': len(unmapped_stocks),
        'unmapped_stocks': unmapped_stocks[:5],
        'estimated_pe': estimated_pe,
        'estimated_pb': estimated_pb,
        'estimated_pe_percentile': estimated_pe_pct,
        'estimated_pb_percentile': estimated_pb_pct,
        'source': '行业穿透估算'
    }


def main():
    """主流程"""
    print('=' * 60)
    print('ETF持仓行业穿透估值 v1.1')
    print('=' * 60)
    
    stock_to_sw, sw_industry_pe_pb = load_mappings()
    
    # 加载现有ETF估值数据
    valuation_file = DATA_DIR / 'etf_valuation_latest.json'
    with open(valuation_file) as f:
        d = json.load(f)
        all_etfs = d.get('data', [])
    
    # 需要穿透估值的ETF：无PE分位数据
    need_penetration = [e for e in all_etfs if e.get('pe_percentile') is None]
    print(f'\n需要穿透估值的ETF: {len(need_penetration)}只')
    
    # 处理
    results = {
        'meta': {
            'generated_at': datetime.now().isoformat(),
            'version': 'v1.1',
            'source': 'ETF持仓行业穿透',
            'total_etfs': len(need_penetration),
            'stock_mapping_count': len(stock_to_sw),
            'sw_industry_count': len(sw_industry_pe_pb)
        },
        'data': []
    }
    
    success_count = 0
    low_coverage_count = 0
    failed_count = 0
    
    for i, etf in enumerate(need_penetration):
        etf_code = etf.get('code', '')
        etf_name = etf.get('name', '')
        
        if (i + 1) % 50 == 0:
            print(f'  进度: {i+1}/{len(need_penetration)} | 成功:{success_count} 低覆盖:{low_coverage_count} 失败:{failed_count}')
        
        holdings, quarter = get_etf_holdings(etf_code)
        
        if holdings:
            valuation = estimate_etf_valuation(holdings, stock_to_sw, sw_industry_pe_pb)
            
            result = {
                'code': etf_code,
                'name': etf_name,
                'original_source': etf.get('pe_pb_source'),
                'quarter': quarter,
                'holdings_count': len(holdings),
                'valuation': valuation
            }
            results['data'].append(result)
            
            if valuation['status'] == 'success':
                success_count += 1
            else:
                low_coverage_count += 1
        else:
            failed_count += 1
        
        time.sleep(0.3)
    
    # 汇总统计
    results['meta']['success_count'] = success_count
    results['meta']['low_coverage_count'] = low_coverage_count
    results['meta']['failed_count'] = failed_count
    
    # 保存
    output_file = OUTPUT_DIR / 'etf_holding_industry_valuation.json'
    with open(output_file, 'w') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f'\n{"=" * 60}')
    print('处理完成')
    print(f'{"=" * 60}')
    print(f'  成功估算: {success_count} ({success_count/len(need_penetration)*100:.1f}%)')
    print(f'  覆盖率低: {low_coverage_count}')
    print(f'  获取失败: {failed_count}')
    print(f'  输出: {output_file}')
    
    return results


if __name__ == '__main__':
    main()
