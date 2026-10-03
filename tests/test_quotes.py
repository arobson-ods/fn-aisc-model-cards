from pipeline.common import quote_in_source

SRC = """## Training Data

The model was trained on **4.6 trillion** tokens from Dolma 3.
It uses a “mixture” of web and code data – see the paper.

| Benchmark | Score |
|---|---|
| MMLU | 71.2 |
"""


def test_exact():
    assert quote_in_source('trained on **4.6 trillion** tokens', SRC) == 'exact'


def test_whitespace_and_newlines():
    assert quote_in_source('tokens from Dolma 3.  It uses', SRC) == 'normalised'


def test_typographic_quotes_and_dashes():
    assert quote_in_source('a "mixture" of web and code data - see', SRC) == 'normalised'


def test_markdown_emphasis_and_table_pipes():
    assert quote_in_source('trained on 4.6 trillion tokens', SRC) == 'normalised'
    assert quote_in_source('MMLU 71.2', SRC) == 'normalised'


def test_changed_words_rejected():
    assert quote_in_source('trained on 5 trillion tokens', SRC) is None
    assert quote_in_source('trained on 4.6 trillion tokens from Dolma 4', SRC) is None


def test_empty_rejected():
    assert quote_in_source('', SRC) is None
    assert quote_in_source('   ', SRC) is None
