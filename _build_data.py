"""
Build master data.json from static-data.json + (future) API data.
Usage: python _build_data.py
Output: data.json
"""
import json
import re
from pathlib import Path

HERE = Path(__file__).parent

# 1. Load static data
static_raw = json.loads((HERE / 'static-data.json').read_text('utf-8'))
items = static_raw['items']

# 2. Add isTech flag to subsidies
tech_cats = [
    '高新技术', '研发补贴', '专精特新', '瞪羚企业', '科技人才',
    '科技金融', '知识产权', '算力补贴', '低空经济', '数据资产',
    '标准化', '人工智能', '集成电路', '生物医药', '数字经济',
    '智能制造', '新能源'
]
for item in items:
    if item['type'] == 'subsidy':
        item['isTech'] = item.get('cat', '') in tech_cats

# 3. Remove subsidy-specific fields from non-subsidy items
for item in items:
    if item['type'] != 'subsidy':
        item.pop('amount', None)
        item.pop('unit', None)
        item.pop('desc', None)
        item.pop('deadline', None)
        item.pop('org', None)
    if item['type'] != 'event':
        item.pop('month', None)
        item.pop('day', None)
        item.pop('year', None)
        item.pop('location', None)

# 4. Sort: isNew first, then by time desc
def sort_key(item):
    t = item.get('time', '') or ''
    return (0 if item.get('isNew') else 1, t if t else '')

items.sort(key=sort_key, reverse=True)

# 5. Build output
output = {
    'updated': static_raw.get('updated', ''),
    'count': len(items),
    'items': items,
    'source': 'merged',
    'note': 'Static data maintained in static-data.json',
}

# 6. Write
with open(HERE / 'data.json', 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
    f.write('\n')

print(f'✅ Built data.json: {len(items)} items')
type_counts = {}
for item in items:
    t = item['type']
    type_counts[t] = type_counts.get(t, 0) + 1
for t, c in sorted(type_counts.items()):
    print(f'  {t}: {c}')
