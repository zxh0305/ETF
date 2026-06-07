#!/usr/bin/env python3
"""
ETF跟踪指数映射表（扩展版）
根据ETF名称和代码，映射到对应的指数代码
覆盖：宽基 + 行业 + 主题 + 跨境ETF
"""

# 宽基指数映射
BROAD_INDEX_MAP = {
    # 沪深300
    '510300': 'sh000300',
    '159919': 'sh000300',
    '510330': 'sh000300',
    
    # 中证500
    '510500': 'sh000905',
    '159922': 'sh000905',
    '510510': 'sh000905',
    
    # 中证1000
    '512100': 'sh000852',
    '159845': 'sh000852',
    '159632': 'sh000852',
    
    # 上证50
    '510050': 'sh000016',
    '510800': 'sh000016',
    '510710': 'sh000016',
    
    # 科创50
    '588000': 'sh000688',
    '159901': 'sh000688',
    '588080': 'sh000688',
    
    # 创业板指
    '159915': 'sz399006',
    '159948': 'sz399006',
    '159949': 'sz399006',
    
    # 上证红利
    '510880': 'sh000015',
    '159905': 'sh000015',
    
    # 中证100
    '512910': 'sh000903',
    '159923': 'sh000903',
    
    # 深证100
    '159901': 'sz399850',
    '159903': 'sz399850',
}

# 行业指数映射（申万一级行业 + 中证行业指数）
INDUSTRY_INDEX_MAP = {
    # 医药生物 (关键词: 医药、医疗)
    '512010': 'sz399394',  # 医药ETF
    '159938': 'sz399394',  # 医药ETF
    '512290': 'sz399394',  # 医药ETF
    '512170': 'sz399394',  # 医疗ETF
    '159928': 'sz399394',  # 医药消费ETF
    '515950': 'sz399394',  # 医药创新ETF
    
    # 电子/芯片/半导体 (关键词: 电子、芯片、半导体)
    '159995': 'sz399395',  # 芯片ETF
    '512760': 'sz399395',  # 芯片ETF
    '512480': 'sz399395',  # 半导体ETF
    '159813': 'sz399395',  # 芯片ETF
    '516640': 'sz399395',  # 芯片ETF
    
    # 计算机/软件 (关键词: 计算机、软件、大数据)
    '512720': 'sz399396',  # 计算机ETF
    '159998': 'sz399396',  # 计算机ETF
    '516000': 'sz399396',  # 大数据ETF
    
    # 银行 (关键词: 银行)
    '512800': 'sz399986',  # 银行ETF
    '159887': 'sz399986',  # 银行ETF
    '512700': 'sz399986',  # 银行ETF
    
    # 非银金融/证券 (关键词: 证券、券商、保险)
    '512070': 'sz399975',  # 证券ETF (证券公司指数)
    '512880': 'sz399975',  # 证券ETF
    '512000': 'sz399975',  # 券商ETF
    '159993': 'sz399387',  # 券商ETF
    
    # 房地产 (关键词: 房地产、地产)
    '512200': 'sz399393',  # 房地产ETF
    '159768': 'sz399393',  # 房地产ETF
    
    # 食品饮料/消费 (关键词: 消费、食品、饮料、白酒)
    '159736': 'sz399932',  # 消费ETF
    '512690': 'sz399932',  # 酒ETF
    '159928': 'sz399932',  # 消费ETF
    '515650': 'sz399932',  # 消费ETF
    
    # 新能源/光伏/汽车 (关键词: 新能源、光伏、汽车、电动车)
    '515030': 'sz399976',  # 新能源车ETF
    '159806': 'sz399976',  # 新能源车ETF
    '515790': 'sz399952',  # 光伏ETF
    '159857': 'sz399952',  # 光伏ETF
    '516110': 'sz399395',  # 汽车ETF (电子行业包含汽车电子)
    
    # 军工 (关键词: 军工、国防)
    '512660': 'sz399967',  # 军工ETF
    '159638': 'sz399967',  # 军工ETF
    '512810': 'sz399967',  # 军工ETF
    
    # 传媒 (关键词: 传媒、文娱)
    '512980': 'sz399397',  # 传媒ETF
    '159805': 'sz399397',  # 传媒ETF
    
    # 有色金属 (关键词: 有色金属、黄金)
    '512400': 'sz399395',  # 有色金属ETF
    '159880': 'sz399395',  # 有色金属ETF
    
    # 化工 (关键词: 化工、化学)
    '516020': 'sz399394',  # 化工ETF
    '159870': 'sz399394',  # 化工ETF
}

# 主题指数映射
THEME_INDEX_MAP = {
    # 新能源汽车
    '515030': 'sz399976',  # 新能源车
    '159806': 'sz399976',
    
    # 光伏
    '515790': 'sz399952',  # 光伏产业
    '159857': 'sz399952',
    
    # 芯片半导体
    '159995': 'sz399395',  # 电子
    '512760': 'sz399395',
    
    # 军工
    '512660': 'sz399967',  # 中证军工
    '159638': 'sz399967',
}

# 跨境指数映射
CROSS_BORDER_INDEX_MAP = {
    # 恒生指数
    '159920': 'HSI',  # 恒生指数
    '513660': 'HSI',
    
    # 恒生科技
    '513180': 'HSTECH',  # 恒生科技
    '513130': 'HSTECH',
    
    # 标普500
    '513500': 'SPX',  # 标普500
    '513650': 'SPX',
    
    # 纳斯达克100
    '513100': 'NDX',  # 纳斯达克100
    '159941': 'NDX',
}

def get_index_code(etf_code, etf_name=''):
    """根据ETF代码获取跟踪指数代码"""
    
    # 1. 先查宽基映射
    if etf_code in BROAD_INDEX_MAP:
        return BROAD_INDEX_MAP[etf_code], 'broad'
    
    # 2. 查行业映射
    if etf_code in INDUSTRY_INDEX_MAP:
        return INDUSTRY_INDEX_MAP[etf_code], 'industry'
    
    # 3. 查主题映射
    if etf_code in THEME_INDEX_MAP:
        return THEME_INDEX_MAP[etf_code], 'theme'
    
    # 4. 查跨境映射
    if etf_code in CROSS_BORDER_INDEX_MAP:
        return CROSS_BORDER_INDEX_MAP[etf_code], 'cross_border'
    
    # 5. 根据名称智能推断
    name_lower = etf_name.lower()
    
    # 宽基指数
    if '沪深300' in etf_name or '300' in etf_name:
        return 'sh000300', 'broad_inferred'
    elif '中证500' in etf_name or '500' in etf_name:
        return 'sh000905', 'broad_inferred'
    elif '中证1000' in etf_name or '1000' in etf_name:
        return 'sh000852', 'broad_inferred'
    elif '上证50' in etf_name or '50' in etf_name:
        return 'sh000016', 'broad_inferred'
    elif '科创50' in etf_name or '科创' in etf_name:
        return 'sh000688', 'broad_inferred'
    elif '创业板' in etf_name:
        return 'sz399006', 'broad_inferred'
    elif '红利' in etf_name:
        return 'sh000015', 'broad_inferred'
    
    # 行业指数
    elif '医药' in etf_name or '医疗' in etf_name:
        return 'sz399394', 'industry_inferred'
    elif '电子' in etf_name or '芯片' in etf_name or '半导体' in etf_name:
        return 'sz399395', 'industry_inferred'
    elif '计算机' in etf_name or '软件' in etf_name:
        return 'sz399396', 'industry_inferred'
    elif '银行' in etf_name:
        return 'sz399986', 'industry_inferred'
    elif '证券' in etf_name or '券商' in etf_name:
        return 'sz399975', 'industry_inferred'
    elif '房地产' in etf_name or '地产' in etf_name:
        return 'sz399393', 'industry_inferred'
    elif '消费' in etf_name or '食品' in etf_name or '白酒' in etf_name or '酒' in etf_name:
        return 'sz399932', 'industry_inferred'
    elif '新能源' in etf_name or '光伏' in etf_name or '汽车' in etf_name:
        return 'sz399976', 'industry_inferred'
    elif '军工' in etf_name or '国防' in etf_name:
        return 'sz399967', 'industry_inferred'
    elif '传媒' in etf_name:
        return 'sz399397', 'industry_inferred'
    
    # 跨境指数
    elif '恒生' in etf_name or '港股' in etf_name:
        return 'HSI', 'cross_border_inferred'
    elif '纳指' in etf_name or '纳斯达克' in etf_name:
        return 'NDX', 'cross_border_inferred'
    elif '标普' in etf_name:
        return 'SPX', 'cross_border_inferred'
    
    return None, None

def get_all_mapped_etfs():
    """获取所有已映射的ETF"""
    all_maps = {}
    all_maps.update(BROAD_INDEX_MAP)
    all_maps.update(INDUSTRY_INDEX_MAP)
    all_maps.update(THEME_INDEX_MAP)
    all_maps.update(CROSS_BORDER_INDEX_MAP)
    return all_maps

if __name__ == '__main__':
    print("ETF跟踪指数映射表（扩展版）")
    print(f"宽基: {len(BROAD_INDEX_MAP)}只")
    print(f"行业: {len(INDUSTRY_INDEX_MAP)}只")
    print(f"主题: {len(THEME_INDEX_MAP)}只")
    print(f"跨境: {len(CROSS_BORDER_INDEX_MAP)}只")
    print(f"总计: {len(get_all_mapped_etfs())}只")
    print("\n✅ 智能推断: 根据ETF名称自动匹配指数")
    print("   覆盖率预计: 80%+")
