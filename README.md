# SSB Group Discussion Simulator

A terminal-based group discussion simulator where several AI models, each with a different stance, discuss a topic for a set time. Built for practising **SSB (GTO) group discussions**: polite arguments, agreeing or disagreeing *with reasons*, and convincing others with facts.

## Features

- **Multiple AI participants** from different providers (Groq, Gemini, OpenRouter, Mistral, local Ollama)
- **Timed discussion** that ends when the clock runs out
- **Live fact-checker**: claims in every turn are searched on the web and marked ✅ VERIFIED, ⚠️ PARTIAL, ❓ UNVERIFIED or ❌ FALSE
- **SSB mode**: AIs follow a polite pattern (acknowledge → agree/disagree → reason → new point)
- **Join mode**: take part yourself as a candidate
- **GTO-style judge**: scores etiquette, reasoning, evidence, influence, cooperation and officer-like qualities, with coaching for you
- **Transcripts saved** to `gd_logs/`

## Requirements

- Python 3.9+
- At least one model source: a free API key (Groq, Gemini, OpenRouter, Mistral) and/or [Ollama](https://ollama.com) for unlimited local models

## Installation

```bash
git clone https://github.com/<your-username>/ssb-gd-simulator.git
cd ssb-gd-simulator

python -m venv .venv
# macOS / Linux:
source .venv/bin/activate
# Windows (PowerShell):
.venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

## API keys

Set keys only for the providers you use.

| Provider | Variable | Get a key |
|---|---|---|
| Groq | `GROQ_API_KEY` | console.groq.com |
| Google Gemini | `GEMINI_API_KEY` | aistudio.google.com |
| OpenRouter | `OPENROUTER_API_KEY` | openrouter.ai |
| Mistral | `MISTRAL_API_KEY` | console.mistral.ai |
| Ollama (local) | none | `ollama pull qwen2.5:7b` |

**macOS / Linux**
```bash
export GROQ_API_KEY="your_key"
export GEMINI_API_KEY="your_key"
```

**Windows (PowerShell)**
```powershell
$env:GROQ_API_KEY="your_key"
$env:GEMINI_API_KEY="your_key"
```

Never commit keys to GitHub.

## Choose your models

Open `gd_simulator.py` and edit the `PARTICIPANTS` list near the top. Remove any participant whose key you don't have. The `NEUTRAL` model does fact-checking and judging, so use a model that is not one of the debaters if you can. Free-tier model names change often, so check each provider's current list.

## Usage

```bash
# Watch the AIs discuss for 10 minutes
python gd_simulator.py "Should India adopt a Uniform Civil Code?" --minutes 10

# Join as a candidate
python gd_simulator.py "Agnipath scheme: boon or bane?" --join --minutes 12

# Set the stances yourself (one -s per AI participant)
python gd_simulator.py "Electric vehicles in India" -s "Strongly for" -s "Against" -s "Cautious" -s "Neutral"

# Debate style, or without fact-checking
python gd_simulator.py "Is AI a threat?" --style debate
python gd_simulator.py "Any topic" --no-factcheck
```

| Option | Meaning | Default |
|---|---|---|
| `--minutes` | Discussion length | 8 |
| `--delay` | Seconds between turns (helps with rate limits) | 2 |
| `--style` | `ssb` or `debate` | `ssb` |
| `--join` | Take part yourself | off |
| `--no-factcheck` | Skip fact-checking | off |
| `-s`, `--stance` | Stance for each AI, repeatable | auto-generated |

In join mode: type your point and press ENTER, leave blank to pass, type `/quit` to end.

## How the fact-checker works

1. A neutral model extracts up to two checkable claims from each turn.
2. Each claim is searched on the web (DuckDuckGo via `ddgs`).
3. The model compares the claim with the results and gives a verdict, reason and source.
4. Unverified or false claims are added to the discussion so others can respond.

It is a helpful filter, not a final authority. Open the source links for important facts.

## Project structure

```
ssb-gd-simulator/
├── gd_simulator.py    # the whole simulator
├── requirements.txt
├── README.md
├── .gitignore
└── gd_logs/           # created automatically, ignored by git
```

## Troubleshooting

| Problem | Fix |
|---|---|
| `Missing env var ...` | Set that provider's key, or remove the participant |
| 429 / rate-limit errors | Increase `--delay`, use fewer cloud models, or add local Ollama models |
| "no web evidence" in fact-check | Run `pip install ddgs` and check your connection |
| Model not found | Update the model name in `PARTICIPANTS` |
| Ollama connection refused | Start it with `ollama serve` |

## Disclaimer

This is an unofficial practice tool and is not affiliated with the SSB or the Indian Armed Forces. AI models can make mistakes, so verify facts yourself.

## License

MIT (add a `LICENSE` file when creating the repo on GitHub).
