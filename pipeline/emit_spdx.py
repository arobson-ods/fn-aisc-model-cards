"""Emit an SPDX 3.0.1 JSON-LD document (AI + Dataset profiles) per model.

Every extracted fact is placed according to targets/facts.yaml and the outcome logged
(see emit_common.Placement). Values come only from extracted records; where SPDX requires a
property the card does not state (releaseTime, suppliedBy), a Hub-supplied value is used and the
substitution is written into the element's comment.
"""
import json, re

from .emit_common import Placement, as_list, as_text, disclosed, parse_date, parse_energy_kwh
from .common import RAW

CONTEXT = 'https://spdx.org/rdf/3.0.1/spdx-context.jsonld'
CI = '_:creationinfo'
PROFILES = ['core', 'software', 'ai', 'dataset', 'simpleLicensing']

# HF licence ids -> SPDX licence ids (only those that differ only in case)
SPDX_LICENSES = {'apache-2.0': 'Apache-2.0', 'mit': 'MIT', 'cc-by-4.0': 'CC-BY-4.0',
                 'cc-by-nc-4.0': 'CC-BY-NC-4.0', 'bsd-3-clause': 'BSD-3-Clause',
                 'gpl-3.0': 'GPL-3.0-only', 'llama3.1': None, 'gemma': None}
# Words in a stated data modality that map one-to-one onto SPDX DatasetType values
DATASET_TYPES = {'text': 'text', 'image': 'image', 'images': 'image', 'audio': 'audio',
                 'video': 'video', 'videos': 'video', 'code': 'text'}
DATASET_FACTS = {'data_modality', 'data_provenance', 'data_acquisition', 'training_data_size',
                 'data_scope', 'knowledge_cutoff', 'data_curation', 'unsuitable_data_measures',
                 'personal_data', 'data_bias_measures'}


def decimal_text(x):
    """xsd:decimal lexical form: plain digits, no exponent, no 6-digit rounding."""
    return f'{x:.6f}'.rstrip('0').rstrip('.')


def licence_ref(s):
    return 'LicenseRef-' + re.sub(r'[^A-Za-z0-9.-]+', '-', s).strip('-')


class Doc:
    def __init__(self, key, created):
        self.key, self.graph = key, []
        self.ci = {'type': 'CreationInfo', '@id': CI, 'specVersion': '3.0.1', 'created': created,
                   'createdBy': [self.iri('agent')]}
        self.add({'type': 'SoftwareAgent', 'spdxId': self.iri('agent'),
                  'name': 'model-cards pipeline (Open Data Services Field Work)'})

    def iri(self, local):
        return f'urn:model-cards:{self.key}#{re.sub(r"[^A-Za-z0-9._-]+", "-", local)}'

    def add(self, el):
        el.setdefault('creationInfo', CI)
        self.graph.append(el)
        return el

    def rel(self, frm, rtype, to, comment=None):
        el = {'type': 'Relationship', 'spdxId': self.iri(f'rel-{len(self.graph)}'),
              'from': frm, 'relationshipType': rtype, 'to': as_list(to)}
        if comment:
            el['comment'] = comment
        return self.add(el)

    def document(self, root):
        ids = [e['spdxId'] for e in self.graph]
        doc = {'type': 'SpdxDocument', 'spdxId': self.iri('document'), 'creationInfo': CI,
               'name': f'AI BOM for {self.key} (from its model card)',
               'profileConformance': PROFILES, 'rootElement': [root], 'element': ids}
        return {'@context': CONTEXT, '@graph': [self.ci, doc] + self.graph}


def licence_elements(d, frm, licence_rec):
    """Declared licence from the card; concluded is NOASSERTION (we make no conclusion)."""
    if disclosed(licence_rec):
        ev = {e['path']: e['value'] for e in licence_rec.get('evidence', [])}
        lic = as_text(ev.get('card:license') or licence_rec['value'])
        spdx_id = SPDX_LICENSES.get(lic.lower()) if isinstance(lic, str) else None
        name = ev.get('card:license_name')
        expr = spdx_id or licence_ref(name or lic)
        el = d.add({'type': 'simplelicensing_LicenseExpression', 'spdxId': d.iri(f'licence-{frm[-8:]}'),
                    'simplelicensing_licenseExpression': expr})
        if ev.get('card:license_link'):
            el['comment'] = f"Licence link from card: {ev['card:license_link']}"
        declared = el['spdxId']
    else:
        declared = 'expandedlicensing_NoAssertionLicense'
    d.rel(frm, 'hasDeclaredLicense', declared)
    d.rel(frm, 'hasConcludedLicense', 'expandedlicensing_NoAssertionLicense')


def stub_model(d, repo_id, what):
    """Upstream model element. Uses the one-hop cached API record when fetched."""
    api_path = RAW / '_upstream' / repo_id.replace('/', '__') / 'api.json'
    el = {'type': 'ai_AIPackage', 'spdxId': d.iri(f'model-{repo_id}'), 'name': repo_id,
          'software_primaryPurpose': 'model',
          'software_downloadLocation': f'https://huggingface.co/{repo_id}',
          'comment': f'{what} declared in the model card; details not described in this document.'}
    if api_path.exists():
        api = json.loads(api_path.read_text())
        el['software_packageVersion'] = api.get('sha')
    d.add(el)
    licence_elements(d, el['spdxId'], None)
    return el['spdxId']


def build(m, recs, facts, api):
    key = m['key']
    d = Doc(key, m['retrieved_at'].replace('+00:00', 'Z'))
    log = Placement('spdx', key)
    fact_by_id = {f['id']: f for f in facts}
    val = lambda fid: recs[fid]['value'] if disclosed(recs.get(fid)) else None
    comments, info_training, hyper = [], [], []

    # supplier (required by the AI profile)
    provider = val('provider_name')
    org = d.add({'type': 'Organization', 'spdxId': d.iri('supplier'),
                 'name': as_text(provider) if provider else api['author']})
    if not provider:
        org['comment'] = 'Provider not stated in the card; this is the Hugging Face account name.'

    pkg = d.add({'type': 'ai_AIPackage', 'spdxId': d.iri('model'), 'name': m['repo_id'],
                 'software_primaryPurpose': 'model', 'suppliedBy': org['spdxId']})
    pid = pkg['spdxId']
    ds = None  # aggregate training-data package, created on demand

    def dataset():
        nonlocal ds
        if ds is None:
            ds = d.add({'type': 'dataset_DatasetPackage', 'spdxId': d.iri('training-data'),
                        'name': f'Training data of {m["repo_id"]} (as described in the card)',
                        'software_primaryPurpose': 'data', 'dataset_datasetType': ['noAssertion']})
            d.rel(pid, 'trainedOn', ds['spdxId'])
        return ds

    def escape(fid, value, path):
        text = f'{fid}: {as_text(value)}'
        if 'ai_hyperparameter' in path:
            hyper.append({'type': 'DictionaryEntry', 'key': fid, 'value': as_text(value)})
        elif 'ai_informationAboutTraining' in path:
            info_training.append(text)
        elif path.startswith('dataset_') or fid in DATASET_FACTS:
            ds_ = dataset()
            ds_['comment'] = (ds_.get('comment', '') + '\n' + text).strip()
        elif 'ai_domain' in path:
            pkg.setdefault('ai_domain', []).extend(as_list(value) if isinstance(value, list) else [as_text(value)])
        elif 'ai_limitation' in path:
            pkg['ai_limitation'] = (pkg.get('ai_limitation', '') + '\n' + text).strip()
        else:
            comments.append(text)
        log.log(fid, 'escape_hatch', path)

    def field(fid, value, rec):
        """Place a value into its defined SPDX field. Returns the location, or raises
        Unplaceable with a reason."""
        v = as_text(value)
        if fid == 'provider_name':
            return 'suppliedBy -> Organization.name'  # already used above
        if fid == 'model_name':
            return 'name'
        if fid == 'model_version':
            pkg['software_packageVersion'] = v
            return 'software_packageVersion'
        if fid == 'model_authenticity':
            if not re.fullmatch(r'[0-9a-f]{40}', v):
                raise Unplaceable('not a SHA-1 hash')
            pkg['verifiedUsing'] = [{'type': 'Hash', 'algorithm': 'sha1', 'hashValue': v,
                                     'comment': 'Hugging Face repository commit (git SHA-1).'}]
            return 'verifiedUsing'
        if fid == 'release_date':
            iso = parse_date(v)
            if not iso:
                raise Unplaceable(f'date not in a parseable form: {v!r}')
            pkg['releaseTime'] = iso
            return 'releaseTime'
        if fid == 'license':
            return 'hasDeclaredLicense'  # placed by licence_elements
        if fid == 'architecture_family':
            pkg['ai_typeOfModel'] = [as_text(x) for x in as_list(value)]
            return 'ai_typeOfModel'
        if fid == 'max_input_size':
            hyper.append({'type': 'DictionaryEntry', 'key': 'contextLength', 'value': v})
            return 'ai_hyperparameter[contextLength]'
        if fid == 'hyperparameters':
            hyper.append({'type': 'DictionaryEntry', 'key': 'trainingHyperparameters', 'value': v})
            return 'ai_hyperparameter'
        if fid == 'training_datasets':
            for name in as_list(value):
                el = d.add({'type': 'dataset_DatasetPackage', 'spdxId': d.iri(f'dataset-{name}'),
                            'name': as_text(name), 'software_primaryPurpose': 'data',
                            'dataset_datasetType': ['noAssertion']})
                if rec['status'] == 'structured':
                    el['software_downloadLocation'] = f'https://huggingface.co/datasets/{name}'
                d.rel(pid, 'trainedOn', el['spdxId'])
            return 'Relationship(trainedOn)'
        if fid == 'eval_datasets':
            for name in as_list(value):
                el = d.add({'type': 'dataset_DatasetPackage', 'spdxId': d.iri(f'evalset-{name}'),
                            'name': as_text(name), 'software_primaryPurpose': 'data',
                            'dataset_datasetType': ['noAssertion']})
                d.rel(pid, 'testedOn', el['spdxId'])
            return 'Relationship(testedOn)'
        if fid == 'data_modality':
            words = set(re.findall(r'[a-z]+', v.lower()))
            types = sorted({DATASET_TYPES[w] for w in words if w in DATASET_TYPES})
            if not types:
                raise Unplaceable(f'no DatasetType value matches {v!r}')
            dataset()['dataset_datasetType'] = types
            return 'dataset_datasetType'
        if fid in ('data_provenance', 'data_acquisition'):
            ds_ = dataset()
            ds_['dataset_dataCollectionProcess'] = (ds_.get('dataset_dataCollectionProcess', '') + '\n' + v).strip()
            return 'dataset_dataCollectionProcess'
        if fid == 'data_curation':
            dataset().setdefault('dataset_dataPreprocessing', []).append(v)
            return 'dataset_dataPreprocessing'
        if fid == 'data_bias_measures':
            dataset().setdefault('dataset_knownBias', []).append(v)
            return 'dataset_knownBias'
        if fid == 'personal_data':
            raise Unplaceable('dataset_hasSensitivePersonalInformation is a yes/no/noAssertion enum; prose needs human classification')
        if fid == 'training_method':
            info_training.insert(0, v)
            return 'ai_informationAboutTraining'
        if fid in ('intended_uses', 'out_of_scope_uses', 'target_systems'):
            label = {'intended_uses': 'Intended uses', 'out_of_scope_uses': 'Out of scope',
                     'target_systems': 'Target systems'}[fid]
            pkg['ai_informationAboutApplication'] = (pkg.get('ai_informationAboutApplication', '') + f'\n{label}: {v}').strip()
            return 'ai_informationAboutApplication'
        if fid == 'limitations':
            pkg['ai_limitation'] = (v + '\n' + pkg.get('ai_limitation', '')).strip()
            return 'ai_limitation'
        if fid == 'training_energy':
            kwh = parse_energy_kwh(v)
            if kwh is None:
                raise Unplaceable(f'no energy quantity with a unit in {v!r}')
            pkg['ai_energyConsumption'] = {'type': 'ai_EnergyConsumption', 'ai_trainingEnergyConsumption': [
                {'type': 'ai_EnergyConsumptionDescription', 'ai_energyQuantity': decimal_text(kwh),
                 'ai_energyUnit': 'kilowattHour'}]}
            return 'ai_energyConsumption.ai_trainingEnergyConsumption'
        if fid == 'eval_results':
            entries = []
            if isinstance(value, list):  # model-index
                for mi in value:
                    for r in mi.get('results', []):
                        for met in r.get('metrics', []):
                            name = f"{r.get('dataset', {}).get('name', '?')} {met.get('type') or met.get('name', '')}".strip()
                            entries.append({'type': 'DictionaryEntry', 'key': name, 'value': str(met.get('value'))})
            else:
                entries.append({'type': 'DictionaryEntry', 'key': 'reportedResults', 'value': v})
            pkg['ai_metric'] = entries
            return 'ai_metric'
        if fid in ('safety_evaluation', 'autonomy'):
            prop = {'safety_evaluation': 'ai_safetyRiskAssessment', 'autonomy': 'ai_autonomyType'}[fid]
            raise Unplaceable(f'{prop} is an enum; prose needs human classification')
        if fid == 'explainability':
            pkg['ai_modelExplainability'] = [v]
            return 'ai_modelExplainability'
        if fid == 'standards_compliance':
            pkg['ai_standardCompliance'] = [v]
            return 'ai_standardCompliance'
        if fid == 'base_model':
            ids = [stub_model(d, as_text(b), 'Base model') for b in as_list(value)]
            rel = val('base_model_relation')
            d.rel(pid, 'descendantOf', ids,
                  comment=f'Relation declared: {as_text(rel)}' if rel else None)
            return 'Relationship(descendantOf)'
        if fid == 'required_software':
            sw = d.add({'type': 'software_Package', 'spdxId': d.iri('dependency-software'), 'name': v,
                        'software_primaryPurpose': 'library'})
            d.rel(pid, 'dependsOn', sw['spdxId'])
            return 'Relationship(dependsOn)'
        if fid in ('distribution_channels', 'download_location'):
            if fid == 'download_location':
                pkg['software_downloadLocation'] = v
                return 'software_downloadLocation'
            pkg.setdefault('externalRef', []).append(
                {'type': 'ExternalRef', 'externalRefType': 'other', 'comment': f'Distribution channels: {v}'})
            return 'externalRef'
        raise NotImplementedError(fid)

    for f in facts:
        fid, rec, kind = f['id'], recs.get(f['id']), f['spdx']['kind']
        if not disclosed(rec):
            log.log(fid, 'not_disclosed')
            continue
        if kind == 'none':
            log.log(fid, 'no_field')
        elif kind == 'escape_hatch':
            escape(fid, rec['value'], f['spdx']['path'])
        else:
            try:
                log.log(fid, 'placed', field(fid, rec['value'], rec))
            except Unplaceable as e:
                log.log(fid, 'unplaceable', f['spdx']['path'], str(e))

    # required properties the card may not supply
    if 'software_packageVersion' not in pkg:
        pkg['software_packageVersion'] = api['sha']
    if 'software_downloadLocation' not in pkg:
        pkg['software_downloadLocation'] = f"https://huggingface.co/{m['repo_id']}"
    if 'releaseTime' not in pkg:
        pkg['releaseTime'] = api['createdAt'].split('.')[0] + 'Z'
        comments.insert(0, 'releaseTime: release date not stated in the card; Hugging Face repo creation time used.')
    if hyper:
        pkg['ai_hyperparameter'] = hyper
    if info_training:
        pkg['ai_informationAboutTraining'] = '\n'.join(info_training)
    if comments:
        pkg['comment'] = '\n'.join(comments)
    licence_elements(d, pid, recs.get('license'))
    return d.document(pid), log.rows


class Unplaceable(Exception):
    pass
