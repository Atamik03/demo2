"""Verified table rows from plant documents; ratings are not alarm setpoints."""
import json
import re
from pathlib import Path

CATALOG = json.loads(Path(__file__).with_name('passport_data.json').read_text(encoding='utf-8'))


def normalize_tag(value):
    return re.sub(r'[-\s]', '', value.upper().translate(str.maketrans({'H':'Н','T':'Т','X':'Х','A':'А','B':'В','K':'К'})))


def match_passports(node):
    text = node.name.upper().translate(str.maketrans({'H':'Н','T':'Т','X':'Х'}))
    # Explicit slash ranges, e.g. Х-4/1-3, denote three separate units.
    text = re.sub(r'([ТХ]-?\d+)/([1-9]\d*)-([1-9]\d*)',
      lambda m: ', '.join(f'{m[1]}/{i}' for i in range(int(m[2]),int(m[3])+1))
      if 0 <= int(m[3])-int(m[2]) <= 20 else m[0], text)
    pattern = r'[НТХ]-?\d+(?:-?[А-ЯA-Z])?(?:/\d+)?'
    tags = re.findall(pattern, text)
    records = [CATALOG[normalize_tag(tag)] for tag in dict.fromkeys(tags)
               if normalize_tag(tag) in CATALOG and CATALOG[normalize_tag(tag)]['type'] == node.type]
    residue = re.sub(pattern, '', text)
    complete = bool(tags) and len(records) == len(set(tags)) and not re.sub(r'[\s,.()]', '', residue)
    return records, complete


def passport_rows(node):
    records, complete = match_passports(node)
    return {'records': records, 'complete': complete}
