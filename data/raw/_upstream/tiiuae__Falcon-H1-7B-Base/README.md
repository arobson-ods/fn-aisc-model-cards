---
library_name: transformers
language:
- ar
- cs
- de
- en
- es
- fr
- hi
- it
- ja
- ko
- nl
- pl
- pt
- ro
- ru
- sv
- ur
- zh
tags:
- falcon-h1
license: other
license_name: falcon-llm-license
license_link: https://falconllm.tii.ae/falcon-terms-and-conditions.html
---

<img src="https://huggingface.co/datasets/tiiuae/documentation-images/resolve/main/falcon_mamba/falcon-h1-logo.png" alt="drawing" width="800"/>

#  Table of Contents

0. [TL;DR](#TL;DR)
1. [Model Details](#model-details)
2. [Training Details](#training-details)
3. [Usage](#usage)
4. [Evaluation](#evaluation)
5. [Citation](#citation)

# TL;DR

# Model Details

## Model Description

- **Developed by:** [https://www.tii.ae](https://www.tii.ae)
- **Model type:** Causal decoder-only
- **Architecture:** Hybrid Transformers + Mamba architecture
- **Language(s) (NLP):** English, Multilingual
- **License:** Falcon-LLM License

# Training details

For more details about the training protocol of this model, please refer to the [Falcon-H1 technical blogpost](https://falcon-lm.github.io/blog/falcon-h1/) and [Technical Report](https://arxiv.org/abs/2507.22448).

# Usage

Currently to use this model you can either rely on Hugging Face `transformers`, `vLLM` or `llama.cpp` library.

## Inference

Make sure to install the latest version of `transformers` or `vllm`, eventually install these packages from source:

```bash
pip install git+https://github.com/huggingface/transformers.git
```

For vLLM, make sure to install `vllm>=0.9.0`:

```bash
pip install "vllm>=0.9.0"
```

### 🤗 transformers

Refer to the snippet below to run H1 models using 🤗 transformers:

```python
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

model_id = "tiiuae/Falcon-H1-1B-Base"

model = AutoModelForCausalLM.from_pretrained(
  model_id,
  torch_dtype=torch.bfloat16,
  device_map="auto"
)

# Perform text generation
```

### vLLM

For vLLM, simply start a server by executing the command below:

```
# pip install vllm>=0.9.0
vllm serve tiiuae/Falcon-H1-1B-Instruct --tensor-parallel-size 2 --data-parallel-size 1
```

### `llama.cpp`

You can find all GGUF files under [our official collection](https://huggingface.co/collections/tiiuae/falcon-h1-6819f2795bc406da60fab8df)

# Evaluation

Falcon-H1 series perform very well on a variety of tasks, including reasoning tasks. 

| Tasks | Falcon-H1-7B | Qwen3-8B | Qwen2.5-7B | Gemma3-12B | Llama3.1-8B | Falcon3-7B | Falcon3-10B |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **General**  | | | | | | |
| BBH | **60.61** | 58.44 | 53.72 | 54.33 | 46.52 | 50.88 | 59.3 |
| MMLU | **77.38** | 76.63 | 74.17 | 74.23 | 65.17 | 69.98 | 73.22 |
| ARC-C | 65.19 | **67.75** | 63.91 | 67.58 | 57.68 | 62.71 | 67.49 |
| HellaSwag | 81.26 | 79.6 | 80.2 | **84.22** | 81.97 | 76.69 | 79.64 |
| Winogrande | 79.01 | 76.8 | 76.01 | **79.79** | 77.11 | 73.64 | 79.01 |
| **Math**  | | | | | | |
| GSM8k | 73.46 | 83.02 | **83.09** | 71.19 | 49.51 | 76.95 | 82.11 |
| MATH lvl5 | **34.67** | 28.85 | 22.58 | 17.22 | 6.57 | 20.09 | 25.38 |
| **Science**  | | | | | | |
| GPQA | **36.58** | 35.65 | 32.3 | 34.56 | 31.46 | 35.07 | 35.4 |
| MMLU-Pro | **48.38** | 48.25 | 43.55 | 42.72 | 32.71 | 39.23 | 42.45 |
| MMLU-stem | 77.2 | **78.53** | 71.04 | 68.51 | 55.72 | 67.71 | 70.85 |
| **Code**  | | | | | | |
| HumanEval | 67.68 | **87.8** | 57.32 | 45.12 | 39.02 | 50.0 | 51.83 |
| HumanEval+ | 63.41 | **82.32** | 48.78 | 36.59 | 31.71 | 43.29 | 44.51 |
| MBPP | **78.57** | 75.13 | 76.72 | 73.02 | 61.38 | 67.99 | 73.54 |
| MBPP+ | **67.2** | 64.02 | 63.49 | 59.79 | 51.32 | 57.14 | 61.38 |

You can check more in detail on our [our release blogpost](https://falcon-lm.github.io/blog/falcon-h1/), detailed benchmarks.

# Useful links

- View [our release blogpost](https://falcon-lm.github.io/blog/falcon-h1/).
- View [our technical report](https://arxiv.org/abs/2507.22448).
- Feel free to join [our discord server](https://discord.gg/trwMYP9PYm) if you have any questions or to interact with our researchers and developers.

# Citation

If the Falcon-H1 family of models were helpful to your work, feel free to give us a cite.

```
@article{falconh1,
    title={Falcon-H1: A Family of Hybrid-Head Language Models Redefining Efficiency and Performance},
    author={Jingwei Zuo and Maksim Velikanov and Ilyas Chahed and Younes Belkada and Dhia Eddine Rhayem and Guillaume Kunsch and Hakim Hacid and Hamza Yous and Brahim Farhat and Ibrahim Khadraoui and Mugariya Farooq and Giulia Campesan and Ruxandra Cojocaru and Yasser Djilali and Shi Hu and Iheb Chaabane and Puneesh Khanna and Mohamed El Amine Seddik and Ngoc Dung Huynh and Phuc Le Khac and Leen AlQadi and Billel Mokeddem and Mohamed Chami and Abdalgader Abubaker and Mikhail Lubinets and Kacper Piskorski and Slim Frikha},
    journal = {arXiv preprint arXiv:2507.22448},
    year={2025}
}
```