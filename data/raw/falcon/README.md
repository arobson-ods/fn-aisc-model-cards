---
base_model:
- tiiuae/Falcon-H1-7B-Base
language:
- en
library_name: transformers
pipeline_tag: text-generation
license: other
license_name: falcon-llm-license
license_link: https://falconllm.tii.ae/falcon-terms-and-conditions.html
tags:
- falcon-h1r
---

<img src="https://huggingface.co/datasets/tiiuae/reasoning-images/resolve/main/falcon-h1r-logo.png" alt="drawing" width="800"/>

# Falcon-H1R-7B

This repository presents **Falcon-H1R-7B**, a reasoning-specialized model introduced in the paper [Falcon-H1R: Pushing the Reasoning Frontiers with a Hybrid Model for Efficient Test-Time Scaling](https://huggingface.co/papers/2601.02346). 

Built on top of [Falcon-H1-7B-Base](https://huggingface.co/tiiuae/Falcon-H1-7B-Base), it was trained via cold-start supervised fine-tuning with long reasoning traces and further enhanced by scaling RL with GRPO. The model demonstrates outstanding performance across various benchmark evaluations, including mathematics, programming, instruction following, and general logic.

## Model Description

- **Developed by:** [Technology Innovation Institute](https://www.tii.ae)
- **Model type:** Causal decoder-only
- **Architecture:** Hybrid (Transformers + Mamba2) architecture
- **Language(s):** English, Multilingual
- **License:** [Falcon-LLM License](https://falconllm.tii.ae/falcon-terms-and-conditions.html)

## Training details

For more details about the training protocol of this model, please refer to the [Falcon-H1R technical blogpost](https://falcon-lm.github.io/blog/falcon-h1r-7b) and [Technical Report](https://github.com/tiiuae/falcon-h1r/blob/main/tech_report.pdf).

# Usage

Currently to use this model, you can either rely on Hugging Face `transformers`, `vLLM` or `SGLang` library.

## Inference

Make sure to install the latest version of `transformers` or `vLLM` or `SGLang`.

```bash
pip install transformers
pip install mamba-ssm[causal-conv1d]
```

For vLLM, make sure to install `vllm=0.11.0`:

```bash
pip install "vllm>=0.11.0"
```

## Sampling Parameters

We recommend using a **temperature** of **0.6** and **top-p** as **0.95** with max new tokens up to 65536.
For supported frameworks, you can adjust the repetition_penalty and presence_penalty parameters to reduce endless repetitions.
For reasoning tasks with continuous batching and requiring higher max new tokens, we recommend to use TP=2.

## 🤗 Transformers

Refer to the snippet below to run H1R models using 🤗 transformers. 
Model will generate think content wrapped in a `<think>...</think>` block, followed by the final response.

<details>
<summary> Click to expand </summary>
  
```python
from transformers import AutoTokenizer, AutoModelForCausalLM
model_id = "tiiuae/Falcon-H1R-7B"
tokenizer = AutoTokenizer.from_pretrained(model_id)
model = AutoModelForCausalLM.from_pretrained(model_id, device_map="auto", dtype="auto")

messages = [
    {"role": "user", "content": "What is the derivative of x^2?"},
]
inputs = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True, return_tensors="pt")

outputs = model.generate(
    inputs.to(model.device),
    max_new_tokens=65536,
    temperature=0.6,
    top_p=0.95,
    do_sample=True,
)
print(tokenizer.decode(outputs[0]))
```
</details>

## vLLM

For vLLM, simply start a server by executing the command below:

<details>
<summary> Click to expand </summary>
<br>
  
```python
vllm serve tiiuae/Falcon-H1R-7B \
  --tensor-parallel-size 1 \
  --data-parallel-size 1 \
  --reasoning-parser deepseek_r1
```  
<br>
Additional flags:

* You can reduce `--max-model-len` to preserve memory. Default value is `262144` which is quite large but not necessary for most scenarios.
* For function calling, append `--enable-auto-tool-choice` and `--tool-call-parser hermes` to the vllm serve command.


vLLM client execution code:
```python
from openai import OpenAI
import json

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="EMPTY",
)

completion = client.chat.completions.create(
    model="tiiuae/Falcon-H1R-7B",
    messages=[
        {"role": "user", "content": "If the product of two numbers is 360 and their GCD is 6, what is their LCM?"},
    ],
    temperature=0.6,
    top_p=0.95,
    max_tokens=65536
)

msg = completion.choices[0].message

print(json.dumps({
    "reasoning": msg.reasoning_content,
    "answer": msg.content
}, indent=2))
```
</details>

## SGLang

For SGLang, simply start a server by executing the command below:

<details>
<summary> Click to expand </summary>
<br>

```python
python -m sglang.launch_server \
  --model tiiuae/Falcon-H1R-7B \
  --tensor-parallel-size 1 \
  --reasoning-parser deepseek-r1
```
<br>

SGLang client execution code:
```python
from openai import OpenAI
import json

client = OpenAI(
    base_url="http://localhost:30000/v1",
    api_key="EMPTY",
)

completion = client.chat.completions.create(
    model="tiiuae/Falcon-H1R-7B",
    messages=[
        {"role": "user", "content": "How many solutions in integers satisfy ∣x∣+∣y∣=20?"},
    ],
    max_tokens=65536,
    temperature=0.6,
    top_p=0.95,
)

msg = completion.choices[0].message

print(json.dumps({
    "reasoning": msg.reasoning_content,
    "answer": msg.content
}, indent=2))
```
</details>
<br>

# Evaluation

Falcon-H1R achieves state of art results in reasoning benchmarks. 

<table border="1" style="width: 100%; text-align: center; border-collapse: collapse;">
    <colgroup>
        <col style="width: 6%;">
        <col style="width: 6%;">
        <col style="background-color: rgba(80, 15, 213, 0.5); width: 5%;">  
        <col style="width: 5%;">
        <col style="width: 5%;">
        <col style="width: 5%;">
        <col style="width: 5%;">
        <col style="width: 5%;">
        <col style="width: 5%;">
        <col style="width: 5%;">
    </colgroup>
    <thead>
        <tr>
            <th>Category</th>
            <th>Benchmark</th>
            <th>Falcon-H1R-7B</th>  
            <th>Qwen3-8B</th>
            <th>DeepSeek-R1-0528-Qwen3-8B</th>
            <th>Phi-4-Reasoning-Plus-14B</th>
            <th>Apriel-1.5-15b-Thinker</th>
            <th>GPT-OSS-20B</th>
            <th>Qwen3-32B</th>
            <th>Nemotron-H-47B-Reasoning</th>
        </tr>
    </thead>
    <tbody>
        <tr>
            <td rowspan="5">MATH</td>
            <td>AIME24</td>
            <td><b>88.1</b></td>
            <td>77.9</td>
            <td>83.3</td>
            <td>77.2</td>
            <td>86.2</td>
            <td>83.3</td>
            <td>79.4</td>
            <td>64.6</td>
        </tr>
        <tr>
            <td>AIME25</td>
            <td>83.1</td>
            <td>65.8</td>
            <td>75.8</td>
            <td>71.2</td>
            <td>80.0</td>
            <td><b>84.4</b></td>
            <td>71.0</td>
            <td>51.4</td>
        </tr>
        <tr>
            <td>HMMT25</td>
            <td><b>64.9</b></td>
            <td>41.0</td>
            <td>54.3</td>
            <td>47.7</td>
            <td>61.0</td>
            <td>64.8</td>
            <td>49.8</td>
            <td>34.2</td>
        </tr>
        <tr>
            <td>AMO-BENCH</td>
            <td><b>36.3</b></td>
            <td>14.1</td>
            <td>23.3</td>
            <td>15.0</td>
            <td>22.2</td>
            <td>26.0</td>
            <td>21.3</td>
            <td>7.0</td>
        </tr>
        <tr>
            <td>MATH500</td>
            <td><b>97.4</b></td>
            <td>97.4</td>
            <td>96.8</td>
            <td>95.4</td>
            <td>97.2</td>
            <td>94.8</td>
            <td>96.8</td>
            <td>91.4</td>
        </tr>
        <tr>
            <td rowspan="2">Code</td>
            <td>LCBv5-v6</td>
            <td>68.6</td>
            <td>53.0</td>
            <td>57.2</td>
            <td>53.1</td>
            <td>53.0</td>
            <td><b>72.0</b></td>
            <td>61.0</td>
            <td>47.4</td>
        </tr>
        <tr>
            <td>SciCode (sub/main)</td>
            <td>28.3 / 3.9</td>
            <td>28.3 / 6.7</td>
            <td>22.2 / 2.6</td>
            <td>29.8 / 7.2</td>
            <td>31.9 / 8.2</td>
            <td>34.9 / 6.2</td>
            <td>36.4 / 9.2</td>
            <td>26.1 / 4.6</td>
        </tr>
        <tr>
            <td rowspan="4">General</td>
            <td>GPQA-D</td>
            <td>61.3</td>
            <td>61.2</td>
            <td>61.4</td>
            <td><b>67.9</b></td>
            <td>68.2</td>
            <td>61.2</td>
            <td>67.3</td>
            <td>56.8</td>
        </tr>
        <tr>
            <td>MMLU-Pro</td>
            <td>72.1</td>
            <td>63.5</td>
            <td>69.1</td>
            <td><b>79.2</b></td>
            <td>76.5</td>
            <td>75.6</td>
            <td>73.9</td>
            <td>78.6</td>
        </tr>
        <tr>
            <td>HLE</td>
            <td>11.1</td>
            <td>4.2</td>
            <td>5.6</td>
            <td>5.9</td>
            <td>12.0</td>
            <td>9.8</td>
            <td>8.3</td>
            <td>4.4</td>
        </tr>
        <tr>
            <td>IFBench</td>
            <td>53.4</td>
            <td>35.3</td>
            <td>29.2</td>
            <td>51.7</td>
            <td>55.8</td>
            <td>69.4</td>
            <td>35.4</td>
            <td>34.3</td>
        </tr>
        <tr>
            <td rowspan="2">Agentic Workflows</td>
            <td>𝜏²-Bench Telecom</td>
            <td>25.4</td>
            <td>27.8</td>
            <td></td>
            <td></td>
            <td>68.4</td>
            <td>60.2</td>
            <td>29.8</td>
            <td>11.4</td>
        </tr>
        <tr>
            <td>Terminal-Bench Hard</td>
            <td>4.9</td>
            <td>2.1</td>
            <td>1.4</td>
            <td>2.1</td>
            <td>9.9</td>
            <td>9.9</td>
            <td>2.8</td>
            <td>1.4</td>
        </tr>      
    </tbody>
</table>

TTS represents test time scaling results on few of the benchmarks that we evaluated via [DeepConf](https://github.com/facebookresearch/deepconf). Note that AMO-Bench* is limited to the parser-verifiable subset which comprises 39 problems.

<table border="1" style="width: 100%; text-align: center; border-collapse: collapse;">
    <colgroup>
        <col style="width: 6%;">
        <col style="background-color: rgba(80, 15, 213, 0.5); width: 5%;">
        <col style="width: 5%;">
        <col style="width: 5%;">
        <col style="width: 5%;">
        <col style="width: 5%;">
        <col style="width: 5%;">
    </colgroup>
    <thead>
        <tr>
            <th>Benchmark</th>
            <th>Falcon-H1R-7B</th>
            <th>Qwen3-8B</th>
            <th>DeepSeek-R1-0528-Qwen3-8B</th>
            <th>Nemotron-H-8B</th>
            <th>Phi-4-Reasoning-Plus-14B</th>
            <th>Qwen3-32B</th>
        </tr>
    </thead>
    <tbody>
        <tr>
            <td>AIME24</td>
            <td><b>96.7</b></td>
            <td>80.0</td>
            <td>90.0</td>
            <td>53.3</td>
            <td>86.7</td>
            <td>86.7</td>
        </tr>
        <tr>
            <td>AIME25</td>
            <td><b>96.7</b></td>
            <td>80.0</td>
            <td>82.8</td>
            <td>43.3</td>
            <td>83.3</td>
            <td>86.7</td>
        </tr>
        <tr>
            <td>GPQA-D</td>
            <td>70.2</td>
            <td>60.9</td>
            <td>59.9</td>
            <td>61.1</td>
            <td><b>73.2</b></td>
            <td>70.1</td>
        </tr>
        <tr>
            <td>AMO-Bench*</td>
            <td><b>35.9</b></td>
            <td>15.4</td>
            <td>25.6</td>
            <td>7.7</td>
            <td>20.5</td>
            <td>28.2</td>
        </tr>
    </tbody>
</table>

# Useful links

- View [our release blogpost](https://falcon-lm.github.io/blog/falcon-h1r-7b).
- View [our technical report](https://huggingface.co/papers/2601.02346).
- Feel free to join [our discord server](https://discord.gg/Cbek57PrZE) if you have any questions or to interact with our researchers and developers.

# Citation

If the Falcon-H1R family of reasoning models is helpful to your work, feel free to give us a cite.

```
@misc{falcon-h1r,
      title={Falcon-H1R: Pushing the Reasoning Frontiers with a Hybrid Model for Efficient Test-Time Scaling}, 
      author={Falcon LLM Team and Iheb Chaabane and Puneesh Khanna and Suhail Mohmad and Slim Frikha and Shi Hu and Abdalgader Abubaker and Reda Alami and Mikhail Lubinets and Mohamed El Amine Seddik and Hakim Hacid},
      year={2026},
      eprint={2601.02346},
      archivePrefix={arXiv},
      primaryClass={cs.AI},
      url={https://arxiv.org/abs/2601.02346}, 
}
```