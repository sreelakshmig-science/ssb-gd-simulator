# SSB Group Discussion Simulator

A terminal-based group discussion simulator for practising **SSB (GTO) group discussions**: polite arguments, agreeing or disagreeing *with reasons*, and convincing others with facts.

AI participants take different positions on a topic and discuss it for a set time. Every claim can be fact-checked against the web, and a judge scores the discussion the way a Group Testing Officer would. You can also **join as a candidate** and get coaching feedback.

## Two versions

| Script | Models | Cost | Best for |
|---|---|---|---|
| `gd_ollama.py` | Local models through Ollama; AI **characters** (officer, economist, student...) | Free, offline, unlimited | Easiest start, no API keys |
| `gd_simulator.py` | Different AI providers (Groq, Gemini, OpenRouter, Mistral, xAI Grok, Ollama) | Free tiers or paid, depending on provider | Different "brains" debating each other |

Use either one, or both.

## Features

- Timed discussion that ends when the clock runs out
- **SSB mode**: contributions follow *acknowledge, agree or disagree, give the reason, add a new point*
- **Live fact-checker**: claims are searched on the web and marked ✅ VERIFIED, ⚠️ PARTIAL, ❓ UNVERIFIED or ❌ FALSE. Flagged claims go back into the discussion so others can respond
- **Join mode** (`--join`): take part yourself
- **GTO-style judge**: scores politeness, reasoning, evidence, influence, cooperation and officer-like qualities
- **Transcripts saved** to `gd_logs/`

## Requirements

- Python 3.9 or newer
- For `gd_ollama.py`: [Ollama](https://ollama.com)
- For `gd_simulator.py`: at least one API key, and/or Ollama

## Installation

```powershell
git clone https://github.com/<your-username>/ssb-gd-simulator.git
cd ssb-gd-simulator

python -m venv .venv
```

Activate the virtual environment:

| System | Command |
|---|---|
| Windows (PowerShell) | `.venv\Scripts\Activate.ps1` |
| macOS / Linux | `source .venv/bin/activate` |

Windows may block the activation script. If so, run this once in that window, then activate again:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Install the packages:
```powershell
pip install -r requirements.txt
```

---

## Option A: Ollama only (`gd_ollama.py`)

No API keys, no limits, runs on your PC.

### 1. Set up Ollama (once)
Install Ollama from ollama.com, then download a model:
```powershell
ollama pull qwen2.5:7b        # better quality, about 4-5 GB
ollama pull llama3.2:3b       # smaller and faster for low-RAM laptops
```
If you later see a connection error, start the server with `ollama serve` in another window.

### 2. Run
```powershell
# Asks for the topic and the number of characters
python gd_ollama.py

# Everything on the command line
python gd_ollama.py "Agnipath scheme: boon or bane?" -n 4 --minutes 8

# Join as a candidate
python gd_ollama.py "Should voting be compulsory?" -n 3 --join

# Choose specific characters
python gd_ollama.py "EVs in India" --pick Arjun,Meera,Rahul

# Smaller model, or a mix of models across characters
python gd_ollama.py "Topic" -n 3 --model llama3.2:3b
python gd_ollama.py "Topic" -n 3 --models qwen2.5:7b,llama3.2:3b

# Show all characters
python gd_ollama.py --list-characters
```

### Characters (2 to 10)

| Name | Role |
|---|---|
| Arjun | Retired Army Major |
| Meera | Economist |
| Rahul | College Student |
| Dr. Iyer | Sociologist |
| Farah | Journalist |
| Kabir | Tech Entrepreneur |
| Lakshmi | School Teacher and Parent |
| Vikram | Civil Servant and Policy Analyst |
| Anita | Environmental Scientist |
| Samir | Small Business Owner |

Each character is given a starting position (in favour, against, conditional, skeptical, middle path, or supports the goal but not the method). The first two always take opposite sides, so there is real disagreement.

### Options

| Option | Meaning | Default |
|---|---|---|
| `-n`, `--characters` | Number of AI characters | asks you |
| `--pick` | Choose characters by name | random |
| `--minutes` | Discussion length | 8 |
| `--delay` | Seconds between turns | 1 |
| `--join` | Take part yourself | off |
| `--no-factcheck` | Skip fact-checking | off |
| `--model` | Ollama model | `qwen2.5:7b` |
| `--models` | Comma-separated models, rotated across characters | none |
| `--list-characters` | Print the characters and exit | |

**Tips:** local models are slower than cloud ones (10 to 60 seconds per turn), so use 10 minutes or more. With a 7B model, 3 to 5 characters works well. The fact-checker uses the same local model, so treat its verdicts as a rough filter.

---

## Option B: Multiple providers (`gd_simulator.py`)

### 1. Get API keys
Set keys only for the providers you use. The script **skips any model whose key is missing** and tells you which ones.

| Provider | Variable | Where to get a key | Cost |
|---|---|---|---|
| Groq (Llama) | `GROQ_API_KEY` | console.groq.com | Free tier |
| Google Gemini | `GEMINI_API_KEY` | aistudio.google.com | Free tier |
| OpenRouter | `OPENROUTER_API_KEY` | openrouter.ai | Some free models |
| Mistral | `MISTRAL_API_KEY` | console.mistral.ai | Free tier |
| xAI (Grok) | `XAI_API_KEY` | console.x.ai | Paid, per token |
| Ollama | none | ollama.com | Free |

Groq (with a Q) hosts Llama and other open models. Grok (with a K) is xAI's model. They are different companies.

### 2. Set the keys in your terminal
**Windows (PowerShell)**
```powershell
$env:GROQ_API_KEY="your_key"
$env:MISTRAL_API_KEY="your_key"
```
**macOS / Linux**
```bash
export GROQ_API_KEY="your_key"
export MISTRAL_API_KEY="your_key"
```
Keys last only for that terminal window, so set them again in a new one. Never put keys in files you push to GitHub.

### 3. Choose your models
Open `gd_simulator.py` and edit the `PARTICIPANTS` list near the top, and the `NEUTRAL` line below it. `NEUTRAL` is the model that generates stances, fact-checks and judges, so give it a provider you have a key for (or Ollama). If it is unavailable, the script falls back to one of your participants.

To see the exact model names your key can use:
```powershell
python gd_simulator.py --list-models xai
python gd_simulator.py --list-models mistral
python gd_simulator.py --list-models ollama
```
Model names change often, so if you get "model not found", pick a current one from that list.

### 4. Run
```powershell
python gd_simulator.py "Agnipath scheme: boon or bane?" --minutes 8
python gd_simulator.py "Agnipath scheme: boon or bane?" --join --minutes 12 --delay 3
python gd_simulator.py "EVs in India" -s "Strongly for" -s "Against" -s "Cautious"
python gd_simulator.py "Is AI a threat?" --style debate
python gd_simulator.py "Any topic" --no-factcheck
```

### Options

| Option | Meaning | Default |
|---|---|---|
| `--minutes` | Discussion length | 8 |
| `--delay` | Seconds between turns (helps with rate limits) | 2 |
| `--style` | `ssb` (polite) or `debate` (assertive) | `ssb` |
| `--join` | Take part yourself | off |
| `--no-factcheck` | Skip fact-checking | off |
| `-s`, `--stance` | Stance for each AI, repeatable (one per AI that runs) | auto-generated |
| `--list-models PROVIDER` | List model names for a provider and exit | |

---

## Playing in join mode

When it is your turn, type your point and press ENTER. A blank line passes your turn and `/quit` ends the session. A good contribution follows this pattern:

1. **Acknowledge** a speaker by name
2. **Agree or disagree** clearly
3. **Give the reason**, ideally with a fact
4. **Add one new point** or ask someone a question

> "I respectfully disagree with Meera on cost, because the training period is only 6 months in many cases. Rahul, what is your view on how the scheme affects young people?"

At the end, the judge scores everyone and coaches you with strengths, improvements and a rewrite of your weakest point.

## How the fact-checker works

1. The model extracts up to two checkable claims from each turn.
2. Each claim is searched on the web (DuckDuckGo through `ddgs`).
3. The model compares the claim with the results and gives a verdict, a reason and a source.
4. Anything not verified is added to the discussion so others can politely challenge it.

It is a useful filter, not a final authority. Open the source links for facts that matter.

## Project structure

```
ssb-gd-simulator/
├── gd_ollama.py       # Ollama-only version with characters
├── gd_simulator.py    # multi-provider version
├── requirements.txt
├── README.md
├── .gitignore
└── gd_logs/           # created automatically, ignored by git
```

## Troubleshooting

| Problem | Fix |
|---|---|
| `source` is not recognized (Windows) | Use `.venv\Scripts\Activate.ps1`. `source` is for macOS/Linux |
| "running scripts is disabled" | Run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` first |
| `Skipping X: set ..._API_KEY` | Normal. Set that key, or ignore it and use the other models |
| `KeyError: 'xai'` (or another provider) | Your `PROVIDERS` list is missing that entry. Use the latest `gd_simulator.py` |
| `unrecognized arguments: --list-models` | You are running an old copy of the script. Replace it and confirm with `Select-String -Path .\gd_simulator.py -Pattern "list-models"` |
| `400 Bad Request` | Usually a wrong model name. Run `--list-models <provider>` and update `PARTICIPANTS` |
| 401 / 403 | Wrong key, or no credit on a paid provider such as xAI |
| 429 / rate-limit errors | Increase `--delay`, use fewer cloud models, or use Ollama |
| "Cannot reach Ollama" | Open the Ollama app or run `ollama serve` |
| "Model ... is not installed" | Run `ollama pull <model>` |
| Fact-check shows "no web evidence" | `pip install ddgs` and check your internet connection |
| Edits to the script have no effect | You may be editing a different copy. Run `Get-Location` and `dir` to see which folder you are in |

## Git: pushing your changes

```powershell
git add .
git commit -m "Describe your change"
git push
```

If `git remote add origin` says the remote already exists, update its URL instead:
```powershell
git remote set-url origin https://github.com/<your-username>/ssb-gd-simulator.git
```

## Disclaimer

This is an unofficial practice tool and is not affiliated with the SSB or the Indian Armed Forces. AI models can make mistakes and fact-check results are not guaranteed, so verify facts yourself.

## License

MIT (add a `LICENSE` file when creating the repo on GitHub).
