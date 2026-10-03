"""Shared helpers for the three emitters: loading extracted records and logging placement."""
import datetime as dt
import json, re

from .common import EXTRACTED, ROOT, TARGETS, load_yaml

DISCLOSED = ('structured', 'prose')


def load_inputs():
    facts = load_yaml(TARGETS / 'facts.yaml')['facts']
    models = load_yaml(ROOT / 'models.yaml')['models']
    return facts, models


def load_records(key):
    return {r['fact_id']: r for r in json.loads((EXTRACTED / f'{key}.json').read_text())}


def disclosed(rec):
    return rec is not None and rec['status'] in DISCLOSED and rec.get('value') not in (None, '', [])


def as_text(v):
    if isinstance(v, str):
        return v
    if isinstance(v, list) and all(isinstance(x, str) for x in v):
        return ', '.join(v)
    return json.dumps(v, ensure_ascii=False)


def as_list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


class Placement:
    """Per-target log of where each fact went. outcome is one of:
    placed          value written into a defined field (kind field)
    escape_hatch    value written into a generic bag (kind escape_hatch)
    no_field        stated but the target has nowhere to put it (kind none)
    unplaceable     field exists but the value can't be written without human judgment
                    (e.g. prose into an enum); reason says why
    not_disclosed   nothing to place (not stated / rejected / pending)
    """

    def __init__(self, target, model):
        self.target, self.model, self.rows = target, model, []

    def log(self, fact_id, outcome, where=None, reason=None):
        self.rows.append(dict(model=self.model, target=self.target, fact_id=fact_id,
                              outcome=outcome, where=where, reason=reason))


def parse_date(text):
    """ISO date from a stated date string, or None. Only unambiguous formats."""
    if not isinstance(text, str):
        return None
    t = text.strip()
    for fmt in ('%Y-%m-%d', '%B %d, %Y', '%d %B %Y', '%b %d, %Y', '%B %Y', '%b %Y', '%Y-%m'):
        try:
            return dt.datetime.strptime(t, fmt).strftime('%Y-%m-%dT00:00:00Z')
        except ValueError:
            pass
    m = re.search(r'\b(\d{4}-\d{2}-\d{2})\b', t)
    return m.group(1) + 'T00:00:00Z' if m else None


ENERGY = re.compile(r'([\d.,]+)\s*(?:x\s*10\^?(\d+)\s*)?(MWh|kWh|GWh|megawatt[- ]hours?|kilowatt[- ]hours?)', re.I)


def parse_energy_kwh(text):
    """Energy in kWh from a stated value like '1.2 MWh', or None."""
    if not isinstance(text, str):
        return None
    m = ENERGY.search(text)
    if not m:
        return None
    try:
        q = float(m.group(1).replace(',', ''))
    except ValueError:
        return None
    if m.group(2):
        q *= 10 ** int(m.group(2))
    unit = m.group(3).lower()
    return q * (1000 if unit.startswith(('mwh', 'megawatt')) else 1_000_000 if unit.startswith('gwh') else 1)
