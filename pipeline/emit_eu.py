"""Fill the EU Model Documentation Form (as parsed in targets/eu_form.yaml) per model.

There is no official machine-readable schema for the form, so the output is our own YAML/CSV:
one entry per form item, carrying the item's audience flags and the facts that answer it.
"""
from .emit_common import Placement, as_text, disclosed


def build(m, recs, facts, eu_items):
    log = Placement('eu', m['key'])
    by_item = {}
    for f in facts:
        for item in (f.get('eu') or {}).get('items', []):
            by_item.setdefault(item, []).append(f['id'])
    items = []
    for it in eu_items:
        answers = []
        for fid in by_item.get(it['id'], []):
            r = recs.get(fid)
            if disclosed(r):
                answers.append(dict(fact_id=fid, status=r['status'], value=as_text(r['value']),
                                    quote=r.get('quote'), source_url=r.get('source_url'),
                                    source_type=r.get('source_type')))
                pc = r.get('prose_check') or {}
                if pc.get('status') == 'prose' and pc.get('agreement') in ('adds', 'conflicts'):
                    # the card text says more than, or differs from, its metadata: show both
                    answers.append(dict(fact_id=fid, status=f"prose_{pc['agreement']}", value=pc['value'],
                                        quote=' [...] '.join(pc['quotes']), source_url=r.get('source_url'),
                                        source_type='card'))
        items.append(dict(id=it['id'], section=it['section'], item=it['item'],
                          audience=it['audience'], precision=it.get('precision'),
                          status='answered' if answers else 'not_stated', answers=answers))
    for f in facts:
        r = recs.get(f['id'])
        if not disclosed(r):
            log.log(f['id'], 'not_disclosed')
        elif f.get('eu'):
            log.log(f['id'], 'placed', ', '.join(f['eu']['items']))
        else:
            log.log(f['id'], 'no_field')
    doc = dict(model=m['key'], repo_id=m['repo_id'], retrieved_at=m['retrieved_at'],
               note='Unofficial fill of the EU GPAI Code of Practice Model Documentation Form from the '
                    'public model card. No official machine-readable schema exists. This is a '
                    'yardstick, not a compliance assessment.',
               items=items)
    return doc, log.rows
