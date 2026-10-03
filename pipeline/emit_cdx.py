"""Emit a CycloneDX 1.7 ML-BOM per model (machine-learning-model component with a modelCard).

Built as plain JSON (cyclonedx-python-lib does not model modelCard/data components) and
validated against the pinned 1.7.2 schema. Escape-hatch facts go into `properties` named
`model-cards:<fact_id>`.
"""
import json, re, uuid

from .emit_common import Placement, as_list, as_text, disclosed
from .common import RAW
from .emit_spdx import SPDX_LICENSES, Unplaceable

NS = uuid.UUID('6f1d8a52-3b7e-4c1a-9e2f-6d0b5a4c3e21')  # fixed namespace -> reproducible serials
PROP = 'model-cards:'
MODALITY_FORMATS = {'text', 'image', 'audio', 'video'}


class Escaped(Exception):
    """A field exists but the value could only be written to a generic bag."""
    def __init__(self, where, reason):
        super().__init__(reason)
        self.where, self.reason = where, reason


def ref(key, local):
    return f'{key}:{re.sub(r"[^A-Za-z0-9._/-]+", "-", local)}'


def build(m, recs, facts, api):
    key = m['key']
    log = Placement('cdx', key)
    val = lambda fid: recs[fid]['value'] if disclosed(recs.get(fid)) else None
    comp = {'type': 'machine-learning-model', 'bom-ref': ref(key, 'model'), 'name': m['repo_id']}
    card = {'modelParameters': {}, 'quantitativeAnalysis': {}, 'considerations': {}, 'properties': []}
    components, deps = [comp], []
    data_comp = None

    def training_data():
        nonlocal data_comp
        if data_comp is None:
            data_comp = {'type': 'data', 'bom-ref': ref(key, 'training-data'),
                         'name': f'Training data of {m["repo_id"]} (as described in the card)',
                         'data': [{'type': 'dataset', 'name': 'training data', 'description': ''}],
                         'properties': []}
            components.append(data_comp)
            card['modelParameters'].setdefault('datasets', []).append({'ref': data_comp['bom-ref']})
        return data_comp

    def prop(target, fid, value):
        target.setdefault('properties', []).append({'name': PROP + fid, 'value': as_text(value)})

    def escape(fid, value, path):
        text = as_text(value)
        if path.startswith('components[type=data]'):
            dc = training_data()
            if 'description' in path or 'classification' in path:
                dc['data'][0]['description'] = (dc['data'][0]['description'] + f'\n{fid}: {text}').strip()
            else:
                prop(dc, fid, value)
        elif path.startswith('components[].pedigree.notes'):
            comp.setdefault('pedigree', {})['notes'] = f'{fid}: {text}'
        elif 'technicalLimitations' in path:
            card['considerations'].setdefault('technicalLimitations', []).append(f'{fid}: {text}')
        elif 'environmentalConsiderations' in path:
            prop(card['considerations'].setdefault('environmentalConsiderations', {}), fid, value)
        elif path.startswith('components[].'):
            prop(comp, fid, value)
        else:
            card['properties'].append({'name': PROP + fid, 'value': text})
        log.log(fid, 'escape_hatch', path)

    def field(fid, value, rec):
        v = as_text(value)
        mp, cons = card['modelParameters'], card['considerations']
        if fid == 'provider_name':
            comp['supplier'] = {'name': v}
            return 'supplier.name'
        if fid == 'model_name':
            return 'name'
        if fid == 'model_version':
            comp['version'] = v
            return 'version'
        if fid == 'model_authenticity':
            if not re.fullmatch(r'[0-9a-f]{40}', v):
                raise Unplaceable('not a SHA-1 hash')
            comp['hashes'] = [{'alg': 'SHA-1', 'content': v}]
            return 'hashes'
        if fid == 'license':
            ev = {e['path']: e['value'] for e in rec.get('evidence', [])}
            lic = ev.get('card:license') or v
            spdx_id = SPDX_LICENSES.get(str(lic).lower())
            if spdx_id:
                comp['licenses'] = [{'license': {'id': spdx_id}}]
            else:
                entry = {'name': ev.get('card:license_name') or str(lic)}
                link = ev.get('card:license_link')
                if link and re.match(r'https?://', link):
                    entry['url'] = link
                elif link:
                    entry['url'] = f"https://huggingface.co/{m['repo_id']}/blob/main/{link}"
                comp['licenses'] = [{'license': entry}]
            return 'licenses'
        if fid == 'additional_assets':
            raise Unplaceable('externalReferences need URLs; the stated value is prose')
        if fid == 'architecture_family':
            mp['architectureFamily'] = v
            return 'modelParameters.architectureFamily'
        if fid == 'architecture_details':
            mp['modelArchitecture'] = v
            return 'modelParameters.modelArchitecture'
        if fid in ('input_modalities', 'output_modalities'):
            items = value if isinstance(value, list) else [x.strip() for x in re.split(r',|\band\b', v) if x.strip()]
            mp['inputs' if fid.startswith('input') else 'outputs'] = [{'format': x} for x in items]
            return f"modelParameters.{'inputs' if fid.startswith('input') else 'outputs'}"
        if fid == 'task':
            mp['task'] = v
            return 'modelParameters.task'
        if fid in ('training_datasets', 'eval_datasets'):
            for name in as_list(value):
                role = 'evalset' if fid == 'eval_datasets' else 'dataset'  # same name, separate roles
                dc = {'type': 'data', 'bom-ref': ref(key, f'{role}-{name}'), 'name': as_text(name),
                      'data': [{'type': 'dataset', 'name': as_text(name)}]}
                if rec['status'] == 'structured' and fid == 'training_datasets':
                    dc['externalReferences'] = [{'type': 'distribution', 'url': f'https://huggingface.co/datasets/{name}'}]
                if fid == 'eval_datasets':
                    dc['properties'] = [{'name': PROP + 'role', 'value': 'evaluation'}]
                if not any(c['bom-ref'] == dc['bom-ref'] for c in components):
                    components.append(dc)
                    mp.setdefault('datasets', []).append({'ref': dc['bom-ref']})
            return 'modelParameters.datasets'
        if fid == 'personal_data':
            training_data()['data'][0]['sensitiveData'] = [v]
            return 'data[].sensitiveData'
        if fid in ('data_bias_measures', 'bias_fairness_evaluation'):
            cons.setdefault('fairnessAssessments', []).append({'harms': v} if fid == 'data_bias_measures' else {'benefits': '', 'harms': v})
            return 'considerations.fairnessAssessments'
        if fid == 'training_method':
            raise Unplaceable('modelParameters.approach.type is a 5-value enum; prose needs human classification')
        if fid == 'training_energy':
            raise Unplaceable('energyConsumptions require energyProviders (organization, energySource, energyProvided), not stated in cards')
        if fid == 'carbon_emissions':
            raise Unplaceable('co2CostEquivalent sits inside an energyConsumption that requires energy provider details')
        if fid in ('intended_uses', 'target_systems'):
            cons.setdefault('useCases', []).append(v)
            return 'considerations.useCases'
        if fid == 'required_software':
            lib = {'type': 'library', 'bom-ref': ref(key, 'dependency-software'), 'name': v}
            components.append(lib)
            deps.append(lib['bom-ref'])
            return 'dependencies'
        if fid == 'limitations':
            cons.setdefault('technicalLimitations', []).insert(0, v)
            return 'considerations.technicalLimitations'
        if fid == 'eval_results':
            metrics = []
            if isinstance(value, list):
                for mi in value:
                    for r in mi.get('results', []):
                        for met in r.get('metrics', []):
                            metrics.append({'type': met.get('type') or met.get('name') or 'metric',
                                            'value': str(met.get('value')),
                                            'slice': r.get('dataset', {}).get('name', '')})
            else:
                metrics.append({'type': 'reported results', 'value': v})
            card['quantitativeAnalysis']['performanceMetrics'] = metrics
            return 'quantitativeAnalysis.performanceMetrics'
        if fid == 'safety_evaluation':
            cons.setdefault('ethicalConsiderations', []).append({'name': v})
            return 'considerations.ethicalConsiderations'
        if fid == 'base_model':
            rel = val('base_model_relation')
            ancestors = []
            for b in as_list(value):
                b = as_text(b)
                anc = {'type': 'machine-learning-model', 'bom-ref': ref(key, f'ancestor-{b}'), 'name': b,
                       'externalReferences': [{'type': 'distribution', 'url': f'https://huggingface.co/{b}'}]}
                up = RAW / '_upstream' / b.replace('/', '__') / 'api.json'
                if up.exists():
                    anc['version'] = json.loads(up.read_text()).get('sha')
                ancestors.append(anc)
            ped = comp.setdefault('pedigree', {})
            ped['ancestors'] = ancestors
            return 'pedigree.ancestors'
        if fid == 'distribution_channels':
            prop(comp, fid, value)  # a URL-less list of channels cannot be an externalReference
            raise Escaped('components[].properties',
                          'externalReferences need a URL per channel; stated channels are prose')
        if fid == 'download_location':
            comp.setdefault('externalReferences', []).append({'type': 'distribution', 'url': v})
            return 'externalReferences[distribution]'
        raise NotImplementedError(fid)

    for f in facts:
        fid, rec, kind = f['id'], recs.get(f['id']), f['cdx']['kind']
        if not disclosed(rec):
            log.log(fid, 'not_disclosed')
            continue
        if kind == 'none':
            log.log(fid, 'no_field')
        elif kind == 'escape_hatch':
            escape(fid, rec['value'], f['cdx']['path'])
        else:
            try:
                log.log(fid, 'placed', field(fid, rec['value'], rec))
            except Escaped as e:
                log.log(fid, 'escape_hatch', e.where, e.reason)
            except Unplaceable as e:
                log.log(fid, 'unplaceable', f['cdx']['path'], str(e))

    if 'version' not in comp:
        comp['version'] = api['sha']
    comp['externalReferences'] = comp.get('externalReferences', []) + [
        {'type': 'model-card', 'url': f"https://huggingface.co/{m['repo_id']}"}]
    for section in ('modelParameters', 'quantitativeAnalysis', 'considerations', 'properties'):
        if not card[section]:
            del card[section]
    if data_comp is not None:
        data_comp['data'][0]['description'] = data_comp['data'][0]['description'] or 'See properties.'
        if not data_comp['properties']:
            del data_comp['properties']
    comp['modelCard'] = card
    bom = {
        'bomFormat': 'CycloneDX', 'specVersion': '1.7',
        'serialNumber': f"urn:uuid:{uuid.uuid5(NS, key + ':' + api['sha'])}", 'version': 1,
        'metadata': {'timestamp': m['retrieved_at'].replace('+00:00', 'Z'),
                     'tools': {'components': [{'type': 'application', 'name': 'model-cards pipeline'}]}},
        'components': components,
        'dependencies': [{'ref': comp['bom-ref'], 'dependsOn': deps}] + [{'ref': r} for r in deps],
    }
    return bom, log.rows
