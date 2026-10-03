from pipeline.extract import pass1, pass2, resolve

API = {
    'id': 'org/model-7b', 'sha': 'a' * 40, 'author': 'org', 'pipeline_tag': 'image-text-to-text',
    'safetensors': {'total': 7_000_000_000},
    'tags': ['base_model:org/base-7b', 'base_model:finetune:org/base-7b', 'gguf', 'license:mit'],
    'model-index': [{'name': 'm', 'results': [{'dataset': {'name': 'MMLU'},
                                               'metrics': [{'type': 'accuracy', 'value': 71.2}]}]}],
}
CARD = {'license': 'other', 'license_name': 'org-licence', 'license_link': 'LICENSE',
        'datasets': ['org/data'], 'base_model': 'org/base-7b'}
CONFIG = {'text_config': {'max_position_embeddings': 32768}, 'transformers_version': '4.57.0'}
SRC = dict(api_url='https://huggingface.co/api/models/org/model-7b', config_url='https://x/config.json',
           readme_url='https://x/README.md', retrieved_at='2026-09-30T00:00:00+00:00')
CTX = dict(key='m', api=API, card=CARD, config=CONFIG, src=SRC,
           readme='## Training\nThe model was trained on 2T tokens.\n')


def fact(fid, *structured):
    return {'id': fid, 'hf': {'structured': list(structured)}}


def test_card_api_config_sources():
    assert resolve('card:license', CTX)[:2] == ('other', 'card_metadata')
    assert resolve('api:safetensors.total', CTX)[:2] == (7_000_000_000, 'hub_api')
    assert resolve('config:max_position_embeddings|text_config.max_position_embeddings', CTX)[:3] == (
        32768, 'repo_config', 'config:text_config.max_position_embeddings')
    assert resolve('config:transformers_version', CTX)[0] == 'transformers 4.57.0'
    assert resolve('card:co2_eq_emissions', CTX) is None


def test_tags_and_derived():
    assert resolve('tags:gguf', CTX)[0] == ['gguf']
    assert resolve('derived:pipeline_input_modalities', CTX)[0] == ['text', 'image']
    assert resolve('derived:pipeline_output_modalities', CTX)[0] == ['text']
    assert resolve('derived:model_index_datasets', CTX)[0] == ['MMLU']
    assert resolve('derived:base_model_relation_tags', CTX)[0] == ['finetune']
    assert resolve('derived:hub_url', CTX)[0] == 'https://huggingface.co/org/model-7b'


def test_pass1_keeps_all_hits_as_evidence():
    r = pass1(fact('license', 'card:license', 'card:license_name', 'card:license_link'), CTX)
    assert r['status'] == 'structured' and r['value'] == 'org-licence (other)'
    assert [e['value'] for e in r['evidence']] == ['other', 'org-licence', 'LICENSE']


def test_pass1_miss():
    assert pass1(fact('release_date'), CTX) is None


def test_pass2_quote_verification():
    f = {'id': 'training_data_size'}
    ok = pass2(f, CTX, {'answer': dict(status='stated', value='2T tokens', section='Training',
                                       quotes=['The model was trained on 2T tokens.', '## Training'])})
    assert ok['status'] == 'prose' and ok['quote_check'] == 'exact'
    bad = pass2(f, CTX, {'answer': dict(status='stated', value='3T tokens', section='Training',
                                        quotes=['## Training', 'The model was trained on 3T tokens.'])})
    assert bad['status'] == 'rejected_quote'  # one bad quote rejects the value
    assert bad['failed_quotes'] == ['The model was trained on 3T tokens.']
    assert pass2(f, CTX, {'answer': dict(status='stated', value='x', section='', quotes=[])})['status'] == 'rejected_quote'
    none = pass2(f, CTX, {'answer': dict(status='not_stated', value='', quotes=[], section='')})
    assert none['status'] == 'not_stated'
