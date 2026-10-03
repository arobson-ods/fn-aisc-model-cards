"""Classify gaps and build the report tables.

Usage: uv run python -m pipeline.report
Writes out/matrix_disclosure.csv, out/matrix_schema.csv, out/gaps.csv, out/lineage.csv,
out/headline.json.

Gap cause for each (model, fact, target), first rule that matches:
  1. target has no field for the fact (kind none or escape_hatch)           -> schema
  2. fact not disclosed, target is the EU form, and none of the fact's form
     items is addressed to downstream providers (regulator-only, or the
     precise AI-Office half of a split item)                               -> audience
  3. fact not disclosed                                                    -> disclosure
  4. disclosed only in prose, and the target (SPDX / CycloneDX) has a field -> structure
Otherwise no gap. The EU form is a document, so prose satisfies it (no structure gap).
Rejected quotes count as not disclosed, flagged extraction_rejected.
"""
import json, statistics

import pandas as pd

from .common import OUT, RAW, TARGETS, load_yaml
from .emit_common import load_inputs, load_records

TARGETS_ = ('spdx', 'cdx', 'eu')
NOT_DISCLOSED = ('not_stated', 'rejected_quote', 'llm_error')


def eu_audience(fact, eu_by_id):
    """Union of audience flags over the fact's EU form items."""
    items = [eu_by_id[i] for i in (fact.get('eu') or {}).get('items', [])]
    return {k: any(it['audience'][k] for it in items) for k in ('AIO', 'NCA', 'DP')}


def target_kind(fact, target):
    if target == 'eu':
        return 'field' if fact.get('eu') else 'none'
    return fact[target]['kind']


def classify(status, kind, target, audience):
    """Return (cause, escape_hatch) or (None, False) when there is no gap."""
    if status == 'pending':
        return 'pending', False
    if kind in ('none', 'escape_hatch'):
        return 'schema', kind == 'escape_hatch'
    if status in NOT_DISCLOSED:
        if target == 'eu' and not audience.get('DP'):
            return 'audience', False
        return 'disclosure', False
    if status == 'prose' and target != 'eu':
        return 'structure', False
    return None, False


def main():
    facts, models = load_inputs()
    eu_items = load_yaml(TARGETS / 'eu_form.yaml')['items']
    eu_by_id = {i['id']: i for i in eu_items}
    placement = pd.read_csv(OUT / 'placement.csv') if (OUT / 'placement.csv').exists() else None
    recs = {m['key']: load_records(m['key']) for m in models}

    # Matrix A: disclosure
    rows = []
    for m in models:
        for f in facts:
            r = recs[m['key']][f['id']]
            rows.append(dict(model=m['key'], role=m['role'], fact_id=f['id'], group=f['group'],
                             status=r['status'], source_type=r.get('source_type')))
    long = pd.DataFrame(rows)
    long.to_csv(OUT / 'disclosure_long.csv', index=False)
    order = [f['id'] for f in facts]
    long.pivot(index='fact_id', columns='model', values='status').reindex(order)[
        [m['key'] for m in models]].to_csv(OUT / 'matrix_disclosure.csv')

    # Matrix B: schema coverage
    pd.DataFrame([dict(fact_id=f['id'], group=f['group'],
                       spdx=f['spdx']['kind'] + ('/coarse' if f['spdx'].get('fit') == 'coarse' else ''),
                       spdx_path=f['spdx'].get('path'),
                       cdx=f['cdx']['kind'] + ('/coarse' if f['cdx'].get('fit') == 'coarse' else ''),
                       cdx_path=f['cdx'].get('path'),
                       eu=target_kind(f, 'eu'),
                       eu_items=';'.join((f.get('eu') or {}).get('items', [])),
                       eu_audience=''.join(k for k, v in eu_audience(f, eu_by_id).items() if v) if f.get('eu') else '')
                  for f in facts]).to_csv(OUT / 'matrix_schema.csv', index=False)

    # Gap table
    gaps = []
    for m in models:
        for f in facts:
            r = recs[m['key']][f['id']]
            for t in TARGETS_:
                aud = eu_audience(f, eu_by_id) if t == 'eu' else {}
                cause, hatch = classify(r['status'], target_kind(f, t), t, aud)
                if cause is None:
                    continue
                note = None
                if placement is not None and t != 'eu':
                    p = placement[(placement.model == m['key']) & (placement.target == t) &
                                  (placement.fact_id == f['id'])]
                    if len(p) and p.iloc[0].outcome == 'unplaceable':
                        note = p.iloc[0].reason
                gaps.append(dict(model=m['key'], role=m['role'], fact_id=f['id'], group=f['group'],
                                 target=t, cause=cause, escape_hatch=hatch, status=r['status'],
                                 disclosed=r['status'] in ('structured', 'prose'),
                                 extraction_rejected=r['status'] == 'rejected_quote',
                                 eu_audience=''.join(k for k, v in aud.items() if v) or None,
                                 fit_note=note))
    gaps = pd.DataFrame(gaps)
    gaps.to_csv(OUT / 'gaps.csv', index=False)

    mvp = []
    for m in models:
        for f in facts:
            r = recs[m['key']][f['id']]
            pc = r.get('prose_check')
            if pc:
                mvp.append(dict(model=m['key'], fact_id=f['id'], source_type=r.get('source_type'),
                                metadata_value=json.dumps(r['value'], ensure_ascii=False),
                                prose_status=pc['status'], agreement=pc.get('agreement'),
                                prose_value=pc.get('value'),
                                prose_quotes=' [...] '.join(pc.get('quotes') or [])))
    mvp = pd.DataFrame(mvp)
    mvp.to_csv(OUT / 'metadata_vs_prose.csv', index=False)

    lineage = build_lineage(models, facts, recs)
    lineage.to_csv(OUT / 'lineage.csv', index=False)
    headline = build_headline(models, facts, recs, eu_items, gaps)
    if len(mvp):
        headline['metadata_vs_prose'] = dict(
            checked=len(mvp), agreement=mvp['agreement'].fillna('n/a').value_counts().to_dict(),
            by_source_type=mvp.groupby('source_type')['agreement'].value_counts().unstack(fill_value=0).to_dict('index'))
    (OUT / 'headline.json').write_text(json.dumps(headline, indent=1))
    print(json.dumps(headline, indent=1))
    print('\ncauses:\n', gaps.groupby(['target', 'cause']).size().unstack(fill_value=0))


def expressible(facts, fid):
    f = next(x for x in facts if x['id'] == fid)
    return {t: target_kind(f, t) for t in TARGETS_}


def build_lineage(models, facts, recs):
    can = {fid: expressible(facts, fid) for fid in
           ('base_model', 'base_model_relation', 'training_datasets', 'eval_datasets')}
    chains_path = RAW / '_upstream' / 'chains.json'
    chains = json.loads(chains_path.read_text()) if chains_path.exists() else {}
    rows = []
    for m in models:
        r = recs[m['key']]
        base = r['base_model']
        if m['role'] != 'lineage' and base['status'] not in ('structured', 'prose'):
            continue
        chain = chains.get(m['key'], [])
        with_data = [n for n in chain if n.get('datasets')]
        roots = [n['repo_id'] for n in chain if not n.get('base_model') and not n.get('stopped')]
        row = dict(model=m['key'], role=m['role'], repo_id=m['repo_id'],
                   declared_relation=m.get('relation'),
                   base_model=json.dumps(base['value']), base_model_status=base['status'],
                   relation=json.dumps(r['base_model_relation']['value']),
                   relation_status=r['base_model_relation']['status'],
                   training_datasets_status=r['training_datasets']['status'],
                   eval_datasets_status=r['eval_datasets']['status'],
                   chain=' <- '.join([m['repo_id']] + [n['repo_id'] for n in chain]),
                   chain_hops=max((n['depth'] for n in chain), default=0),
                   chain_roots=';'.join(roots),
                   upstream_cards_declaring_datasets=';'.join(f"{n['repo_id']} (hop {n['depth']})" for n in with_data),
                   chain_reaches_declared_data=bool(with_data) or r['training_datasets']['status'] == 'structured',
                   upstream_gated=';'.join(n['repo_id'] for n in chain if n.get('gated')))
        for fid, kinds in can.items():
            for t, k in kinds.items():
                row[f'{t}_can_express_{fid}'] = k
        rows.append(row)
    return pd.DataFrame(rows)


def build_headline(models, facts, recs, eu_items, gaps):
    eu_ids = {i['id'] for i in eu_items}
    eu_facts = [f for f in facts if f.get('eu')]
    per_model = {}
    for m in models:
        r = recs[m['key']]
        disclosed = [f for f in facts if r[f['id']]['status'] in ('structured', 'prose')]
        structured = [f for f in disclosed if r[f['id']]['status'] == 'structured']
        card_md = [f for f in structured if r[f['id']].get('source_type') == 'card_metadata']
        answered = {i for f in eu_facts if r[f['id']]['status'] in ('structured', 'prose')
                    for i in f['eu']['items']}
        per_model[m['key']] = dict(
            eu_items_answered=len(answered & eu_ids), eu_items=len(eu_ids),
            eu_item_share=round(len(answered & eu_ids) / len(eu_ids), 3),
            eu_fact_share=round(sum(r[f['id']]['status'] in ('structured', 'prose') for f in eu_facts) / len(eu_facts), 3),
            facts_disclosed=len(disclosed), facts=len(facts),
            machine_readable_share=round(len(structured) / len(disclosed), 3) if disclosed else None,
            card_metadata_share=round(len(card_md) / len(disclosed), 3) if disclosed else None,
            pending=sum(r[f['id']]['status'] == 'pending' for f in facts),
            rejected_quotes=sum(r[f['id']]['status'] == 'rejected_quote' for f in facts))
    med = lambda k: statistics.median(v[k] for v in per_model.values() if v[k] is not None)
    control = next(m['key'] for m in models if m['role'] == 'control')
    cg = gaps[(gaps.model == control) & (gaps.cause == 'schema') & (gaps.disclosed)]
    spot = OUT / 'spotcheck_summary.json'
    auto = OUT / 'autocheck_summary.json'
    return dict(
        median_eu_item_share_public=med('eu_item_share'),
        median_eu_fact_share_public=med('eu_fact_share'),
        median_machine_readable_share_of_disclosed=med('machine_readable_share'),
        median_card_metadata_share_of_disclosed=med('card_metadata_share'),
        control_model=control,
        control_disclosed_facts_without_field={t: sorted(cg[cg.target == t].fact_id) for t in ('spdx', 'cdx', 'eu')},
        schema_gap_facts={t: int(sum(target_kind(f, t) != 'field' for f in facts)) for t in TARGETS_},
        spotcheck=json.loads(spot.read_text()) if spot.exists() else 'full human spot-check not done',
        autocheck=json.loads(auto.read_text()) if auto.exists() else 'not run',
        pending_records=sum(v['pending'] for v in per_model.values()),
        per_model=per_model)


if __name__ == '__main__':
    main()
