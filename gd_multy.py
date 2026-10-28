#!/usr/bin/env python3
"""
SSB Group Discussion Simulator - MULTI-MODEL (every AI model is a participant)
-------------------------------------------------------------------------------
Different AI models (Llama, Gemini, GPT-OSS, Mistral, Qwen, ...) sit in one group discussion.
Each model takes a stance on the topic and argues it politely, with facts, for a set time.
Every claim is fact-checked on the web, and a judge scores the discussion like a GTO would.

Every backend that is ready becomes one participant, named after its model:

  ollama      local, FREE and truly unlimited (runs on your PC)
  groq        free tier  (runs OpenAI's open-weight gpt-oss models)
  nvidia      free developer tier
  gemini      free tier
  mistral     free tier
  openrouter  free models (very small daily quota)
  openai      PAID ChatGPT API - optional
  xai         PAID Grok API   - optional

Set a key only for the models you want; the rest are skipped. Free tiers are rate-limited
(not unlimited), so calls are spaced out and retried. A model that keeps failing leaves the discussion.

Setup:   pip install requests ddgs
Keys (PowerShell):  $env:GROQ_API_KEY="..."   $env:GEMINI_API_KEY="..."   (see --list-backends)

Examples:
  python gd_multi.py --list-backends
  python gd_multi.py "Agnipath scheme: boon or bane?" --minutes 10
  python gd_multi.py "Should voting be compulsory?" --join
  python gd_multi.py "EVs in India" --backends groq,gemini,ollama
  python gd_multi.py "Topic" --models groq:openai/gpt-oss-120b,groq:openai/gpt-oss-20b,ollama:llama3.2:3b
  python gd_multi.py "Topic" -s "Strongly for" -s "Strongly against" -s "Conditional"
"""
import argparse, json, os, random, re, sys, time
from collections import Counter
from datetime import datetime
import requests

try:
    from ddgs import DDGS
except ImportError:
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        DDGS = None

OLLAMA_ROOT = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")

# ------------------------------------------------------------------ backends
# All speak the OpenAI-compatible /chat/completions protocol. Model names change often:
# override any default without editing code, e.g.  $env:GD_GROQ_MODEL="openai/gpt-oss-20b"
# gap = minimum seconds between calls to that backend (keeps you under free-tier limits)
BACKENDS = [
    {"id": "ollama", "url": OLLAMA_ROOT + "/v1", "key_env": None, "model": "qwen2.5:7b", "gap": 0,
     "note": "FREE, unlimited (runs on your PC)"},
    {"id": "groq", "url": "https://api.groq.com/openai/v1", "key_env": "GROQ_API_KEY",
     "model": "openai/gpt-oss-120b", "gap": 2.5, "reasoning": True, "extra": {"reasoning_effort": "low"},
     "note": "free tier, roughly 30 req/min and 1,000/day"},
    {"id": "nvidia", "url": "https://integrate.api.nvidia.com/v1", "key_env": "NVIDIA_API_KEY",
     "model": "openai/gpt-oss-20b", "gap": 1.6, "reasoning": True,
     "note": "free developer tier, roughly 40 req/min; trial use, prompts logged"},
    {"id": "gemini", "url": "https://generativelanguage.googleapis.com/v1beta/openai", "key_env": "GEMINI_API_KEY",
     "model": "gemini-2.5-flash", "gap": 4,
     "note": "free tier, rate-limited; prompts may be used by Google"},
    {"id": "mistral", "url": "https://api.mistral.ai/v1", "key_env": "MISTRAL_API_KEY",
     "model": "mistral-small-latest", "gap": 1.5,
     "note": "free mode, about 1 req/sec; prompts may train models"},
    {"id": "openrouter", "url": "https://openrouter.ai/api/v1", "key_env": "OPENROUTER_API_KEY",
     "model": "openai/gpt-oss-20b:free", "gap": 3.2, "reasoning": True,
     "note": "free models, only about 50 requests/day in total"},
    {"id": "openai", "url": "https://api.openai.com/v1", "key_env": "OPENAI_API_KEY",
     "model": "gpt-4o-mini", "gap": 0.3,
     "note": "PAID ChatGPT API (cents per discussion); verify model name"},
    {"id": "xai", "url": "https://api.x.ai/v1", "key_env": "XAI_API_KEY",
     "model": "grok-4.3", "gap": 0.5,
     "note": "PAID Grok API; verify model name with --list-models xai"},
]
# Neutral duties (fact-check, stances, verdict): first ready backend here wins.
# High-limit and free first; paid ones last so nothing is billed unless it is all you have.
JUDGE_ORDER = ["groq", "nvidia", "mistral", "gemini", "ollama", "openrouter", "openai", "xai"]

COLORS = ["\033[96m", "\033[93m", "\033[92m", "\033[95m", "\033[94m", "\033[91m", "\033[36m", "\033[33m"]
FALLBACK_STANCES = [
    "Strongly IN FAVOUR of the idea.",
    "Strongly AGAINST the idea.",
    "CONDITIONAL support: only with specific safeguards, which you name.",
    "SKEPTICAL, but open to being convinced by good evidence.",
    "A MIDDLE PATH: a hybrid or phased solution.",
    "Supports the GOAL but is critical of the CURRENT method.",
]

RESET, DIM, BOLD = "\033[0m", "\033[2m", "\033[1m"
GREEN, RED, YELLOW, GREY = "\033[92m", "\033[91m", "\033[93m", "\033[90m"
ICON = {"VERIFIED": "✅", "PARTIAL": "⚠️ ", "UNVERIFIED": "❓", "FALSE": "❌"}


# ------------------------------------------------------------------ calling a model
class BackendError(RuntimeError):
    def __init__(self, msg, fatal=False):
        super().__init__(msg)
        self.fatal = fatal          # fatal = retrying will not help (bad key, unknown model...)


def default_model(b):
    return os.getenv(f"GD_{b['id'].upper()}_MODEL", b["model"])


def status(b, model=None):
    """(ready?, reason). Ollama must be running with the model installed; others need a key."""
    model = model or default_model(b)
    if b["id"] == "ollama":
        try:
            r = requests.get(OLLAMA_ROOT + "/api/tags", timeout=2)
            names = [m["name"] for m in r.json().get("models", [])]
        except (requests.RequestException, ValueError):
            return False, "Ollama not running (open the app or run `ollama serve`)"
        if model not in names and f"{model}:latest" not in names:
            return False, f"model not installed: run `ollama pull {model}`"
        return True, "ready"
    if not os.getenv(b["key_env"]):
        return False, f"set {b['key_env']}"
    return True, "ready"


_last_call = {}


def throttle(b):
    wait = _last_call.get(b["id"], 0) + b.get("gap", 0) - time.time()
    if wait > 0:
        time.sleep(wait)
    _last_call[b["id"]] = time.time()


def call(b, model, messages, max_tokens=300, temperature=0.8):
    headers = {"Content-Type": "application/json"}
    if b["key_env"]:
        key = os.getenv(b["key_env"])
        if not key:
            raise BackendError(f"missing {b['key_env']}", fatal=True)
        headers["Authorization"] = f"Bearer {key}"
    # reasoning models spend tokens "thinking" first, so they need a much bigger budget
    mt = max(max_tokens * 4, 1200) if b.get("reasoning") else max_tokens
    body = {"model": model, "messages": messages, "max_tokens": mt,
            "temperature": temperature, **b.get("extra", {})}
    timeout = 600 if b["id"] == "ollama" else 120

    for attempt in range(4):
        throttle(b)
        try:
            r = requests.post(f"{b['url']}/chat/completions", json=body, headers=headers, timeout=timeout)
        except requests.Timeout:
            raise BackendError("timed out")
        except requests.RequestException as e:
            raise BackendError(f"network error: {str(e)[:100]}")
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(min(2 ** attempt * 2, 20) + random.random())
            continue
        if r.status_code >= 400:
            low = r.text.lower()
            # adapt automatically when a model rejects a parameter
            if r.status_code == 400 and "max_tokens" in body and "max_tokens" in low:
                body["max_completion_tokens"] = body.pop("max_tokens")
                continue
            if r.status_code == 400 and "temperature" in body and "temperature" in low:
                body.pop("temperature")
                continue
            if r.status_code == 400 and "reasoning_effort" in body and "reasoning_effort" in low:
                body.pop("reasoning_effort")
                continue
            raise BackendError(f"HTTP {r.status_code} (model '{model}'): {r.text[:160]}",
                               fatal=r.status_code in (401, 403, 404))
        try:
            text = r.json()["choices"][0]["message"]["content"] or ""
        except (ValueError, KeyError, IndexError):
            raise BackendError("unexpected reply format")
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
        if not text:
            raise BackendError("empty reply (the model used its whole budget thinking)")
        return text
    raise BackendError("rate-limited (this backend's quota may be used up)")


def make_neutral(pool):
    """A function for fact-checking / stances / verdict that falls back across backends."""
    def neutral(messages, max_tokens=400, temperature=0.0):
        last = None
        for b in pool:
            if b.get("dead"):
                continue
            try:
                return call(b, default_model(b), messages, max_tokens, temperature)
            except BackendError as e:
                last = e
                b["fails"] = b.get("fails", 0) + 1
                print(f"  {DIM}[judge {b['id']} failed: {e}]{RESET}")
                if e.fatal or b["fails"] >= 3:
                    b["dead"] = True
        raise BackendError(f"no judge model available (last error: {last})")
    return neutral


def parse_json(raw, default):
    m = re.search(r"(\[.*\]|\{.*\})", raw, re.S)
    try:
        return json.loads(m.group(1)) if m else default
    except Exception:
        return default


# ------------------------------------------------------------------ fact-checker
def web_evidence(claim, n=4):
    if DDGS is None:
        return []
    try:
        with DDGS() as d:
            return [{"title": r.get("title", ""), "url": r.get("href", ""), "snippet": r.get("body", "")}
                    for r in d.text(claim, max_results=n)]
    except Exception:
        return []


def fact_check(llm, text):
    """llm(messages, max_tokens, temperature) -> str. Returns a list of claim verdicts."""
    raw = llm([{"role": "user", "content":
        "Extract up to 2 specific, CHECKABLE factual claims (statistics, dates, laws, named events) from the "
        "text below. Ignore opinions. Return ONLY a JSON list of strings, or [] if none.\n\nTEXT:\n" + text}],
        250, 0.0)
    claims = [c for c in parse_json(raw, []) if isinstance(c, str)][:2]
    if not claims:
        return []
    blocks = []
    for i, c in enumerate(claims):
        ev = web_evidence(c)
        ev_txt = "\n".join(f"  - {e['title']} ({e['url']}): {e['snippet'][:250]}" for e in ev) \
            or "  (no web evidence available)"
        blocks.append(f"CLAIM {i}: {c}\nEVIDENCE:\n{ev_txt}")
    prompt = ("You are a strict fact-checker. Judge each claim using the EVIDENCE. Without evidence, only "
              "accept well-known facts; otherwise answer UNVERIFIED.\n"
              "Verdicts: VERIFIED, PARTIAL (roughly right but exaggerated or numbers off), UNVERIFIED, FALSE.\n"
              'Return ONLY a JSON list: [{"id":0,"verdict":"...","reason":"max 15 words","source":"url or empty"}]\n\n'
              + "\n\n".join(blocks))
    results = parse_json(llm([{"role": "user", "content": prompt}], 400, 0.0), [])
    out = []
    for i, c in enumerate(claims):
        r = next((x for x in results if isinstance(x, dict) and x.get("id") == i), {})
        v = str(r.get("verdict", "UNVERIFIED")).upper()
        out.append({"claim": c, "verdict": v if v in ICON else "UNVERIFIED",
                    "reason": r.get("reason", ""), "source": r.get("source", "")})
    return out


# ------------------------------------------------------------------ prompts
SSB_STYLE = """
SSB GROUP DISCUSSION ETIQUETTE (a Group Testing Officer is watching):
- Be POLITE. Attack the point, never the person. No sarcasm, no interrupting.
- Name a previous speaker and acknowledge their point, then say clearly whether you AGREE, DISAGREE or
  PARTLY AGREE, and say WHY. Example: "I respectfully disagree with Gemini on cost, because ..."
- Add ONE new point with a real fact, example or logic. Do not repeat what was already said.
- Sometimes invite another person: "Llama, what is your view?" Never dominate.
- Be solution-oriented; suggest a practical middle path when views clash."""


def system_prompt(name, topic, stance, others):
    return f"""You are {name}, taking part as a candidate in a live SSB-style group discussion with {', '.join(others)}.
TOPIC: {topic}
YOUR STARTING STANCE: {stance}

RULES
1. Give concrete evidence (a statistic, law, study, historical or real example). Name source or year if you can.
2. NEVER invent numbers or sources. If unsure, say "I believe..." or leave it out.
3. A neutral FACT-CHECKER may flag claims. If YOURS is flagged, politely acknowledge and correct it.
4. If someone proves you wrong, concede that point gracefully and refine your stance.
5. Write ONLY your own turn: 3 to 5 sentences (60-100 words), spoken style, no bullet points, no name prefix.
6. Finish with a last line exactly like: [CONFIDENCE: NN]  (0-100, how strongly you hold your stance).
{SSB_STYLE}"""


def turn_prompt(topic, transcript, name):
    recent = "\n\n".join(f"{s}: {t}" for s, t in transcript[-8:]) or \
        "(Nobody has spoken yet. You are the FIRST speaker: state your position briefly with one fact. " \
        "Do not refer to other speakers.)"
    return f"Discussion so far on '{topic}':\n\n{recent}\n\nIt is now your turn, {name}."


def generate_stances(neutral, topic, n):
    """Topic-specific stances, first FOR and second AGAINST. Falls back to generic ones."""
    try:
        raw = neutral([{"role": "user", "content":
            f"Topic: {topic}\nWrite {n} clearly distinct, defensible stances for a group discussion on this "
            f"topic. Stance 1 must be strongly in favour, stance 2 strongly against, the rest nuanced "
            f"(conditional, skeptical, middle path). One per line, max 15 words each, no numbering."}],
            250, 0.6)
        lines = [l.strip(" -*0123456789.") for l in raw.splitlines() if l.strip()]
    except BackendError:
        lines = []
    lines = [l for l in lines if len(l) > 3][:n]
    return lines + FALLBACK_STANCES[len(lines):n] if len(lines) < n else lines


# ------------------------------------------------------------------ participants = models
def nice_name(model):
    low = model.split("/")[-1].split(":")[0].lower()
    for pat, nm in [("gpt-oss", "GPT-OSS"), ("gpt", "GPT"), ("gemini", "Gemini"), ("gemma", "Gemma"),
                    ("ministral", "Mistral"), ("mistral", "Mistral"), ("qwen", "Qwen"), ("llama", "Llama"),
                    ("grok", "Grok"), ("nemotron", "Nemotron"), ("deepseek", "DeepSeek"), ("glm", "GLM"),
                    ("phi", "Phi")]:
        if pat in low:
            return nm
    return low.split("-")[0].title() or "Model"


def build_participants(only, models_spec, max_n):
    by_id = {b["id"]: dict(b) for b in BACKENDS}          # one shared dict per backend
    if models_spec:
        specs = []
        for item in models_spec.split(","):
            bid, _, model = item.strip().partition(":")
            if bid not in by_id:
                sys.exit(f"Unknown backend '{bid}'. Choose from: {', '.join(by_id)}")
            specs.append((bid, model or None, True))
    else:
        specs = [(b["id"], None, bool(only)) for b in BACKENDS if not only or b["id"] in only]

    parts, seen = [], set()
    for bid, model, loud in specs:
        b = by_id[bid]
        model = model or default_model(b)
        if (bid, model) in seen:
            continue
        seen.add((bid, model))
        ok, why = status(b, model)
        if not ok:
            if loud or bid != "ollama":
                print(f"{DIM}Skipping {bid}/{model}: {why}{RESET}")
            continue
        parts.append({"backend": b, "model": model, "name": nice_name(model), "fails": 0})

    if max_n and len(parts) > max_n:
        parts = random.sample(parts, max_n)
    # make names unique: two GPT-OSS models become GPT-OSS-120b / GPT-OSS-20b (or -groq / -nvidia),
    # and a number is added only if names still collide
    for attempt in range(2):
        count = Counter(p["name"] for p in parts)
        for p in [x for x in parts if count[x["name"]] > 1]:
            if attempt == 0:
                size = re.search(r"(\d+(?:\.\d+)?[bB])\b", p["model"])
                p["name"] += f"-{size.group(1)}" if size else f"-{p['backend']['id']}"
            else:
                p["name"] += f"-{parts.index(p) + 1}"
    for i, p in enumerate(parts):
        p["color"] = COLORS[i % len(COLORS)]
    return parts, by_id


def ask_topic():
    return input("Discussion topic: ").strip()


def human_turn(left):
    print(f"\033[97m{BOLD}YOU{RESET} {DIM}[{left // 60}:{left % 60:02d} left] "
          f"type your point + ENTER | blank = pass | /quit = end{RESET}")
    try:
        s = input("> ").strip()
    except (EOFError, KeyboardInterrupt):
        return None
    return None if s.lower() == "/quit" else s


def list_backends():
    rows = [(b, *status(b)) for b in BACKENDS]
    w = max(len(why) for _, ok, why in rows) + 2
    print(f"\n{BOLD}{'ID':<11}{'MODEL':<26}{'STATUS':<{w}}COST / LIMITS{RESET}")
    for b, ok, why in rows:
        col = GREEN if ok else YELLOW
        print(f"{b['id']:<11}{default_model(b):<26}{col}{why:<{w}}{RESET}{b['note']}")
    print(f"\n{DIM}Every ready row becomes one participant in the discussion. Limits change; check each "
          f"provider.\nOverride a model with e.g. $env:GD_GROQ_MODEL=\"openai/gpt-oss-20b\" or use --models.{RESET}\n")


def list_models(bid):
    b = next((x for x in BACKENDS if x["id"] == bid), None)
    if not b:
        sys.exit(f"Unknown backend. Choose from: {', '.join(x['id'] for x in BACKENDS)}")
    headers = {}
    if b["key_env"]:
        if not os.getenv(b["key_env"]):
            sys.exit(f"Set {b['key_env']} first.")
        headers["Authorization"] = f"Bearer {os.getenv(b['key_env'])}"
    r = requests.get(b["url"] + "/models", headers=headers, timeout=30)
    if r.status_code >= 400:
        sys.exit(f"HTTP {r.status_code}: {r.text[:300]}")
    for m in r.json().get("data", []):
        print(m.get("id"))


# ------------------------------------------------------------------ main loop
def run(topic, minutes, delay, join, do_check, only, models_spec, max_n, stances, judge_pref):
    parts, by_id = build_participants(only, models_spec, max_n)
    if not parts:
        sys.exit("\nNo AI models are ready. Install Ollama and pull a model, or set at least one API key.\n"
                 "Run  python gd_multi.py --list-backends  to see what each one needs.")
    if len(parts) + (1 if join else 0) < 2:
        sys.exit("\nOnly one AI model is ready, so there is nobody to discuss with.\n"
                 "Add another API key (or start Ollama), or use --join to discuss with this model yourself.")

    used = {p["backend"]["id"] for p in parts}
    pref = ([judge_pref] if judge_pref else []) + JUDGE_ORDER
    pool = []
    for k in pref:
        b = by_id.get(k)
        if b and b not in pool and (k in used or (k == judge_pref and status(b)[0])):
            pool.append(b)
    neutral = make_neutral(pool)

    stances = list(stances or [])[:len(parts)]
    if len(stances) < len(parts):
        auto = generate_stances(neutral, topic, len(parts))
        stances += auto[len(stances):len(parts)]
    for p, s in zip(parts, stances):
        p["stance"] = s

    print(f"\n{BOLD}=== GROUP DISCUSSION ==={RESET}\nTopic : {BOLD}{topic}{RESET}")
    print(f"Time  : {minutes} min   AI models: {len(parts)}{' + you' if join else ''}   "
          f"Fact-check: {'ON' if do_check else 'OFF'}   Judge: {pool[0]['id']}"
          f"{'' if DDGS or not do_check else '  (pip install ddgs for web evidence)'}\n")
    for p in parts:
        print(f"{p['color']}{p['name']:<14}{RESET}{DIM}{p['backend']['id']}/{p['model']}{RESET}\n"
              f"{'':<14}{p['stance']}")
    if join:
        print(f"\033[97m{'You':<14}{RESET}{DIM}human candidate{RESET}\n{'':<14}Your own view")
    print()

    players = parts + ([{"name": "You", "human": True, "color": "\033[97m"}] if join else [])
    transcript, confidence = [], {p["name"]: [] for p in parts}
    ledger = {p["name"]: Counter() for p in players}
    order = players[:]
    random.shuffle(order)
    end_time, turn = time.time() + minutes * 60, 0

    try:
        while time.time() < end_time:
            active = [p for p in order if not p.get("out")]
            if not any(not p.get("human") for p in active):
                print(f"{RED}No AI models are left in the discussion. Stopping.{RESET}")
                break
            p = order[turn % len(order)]
            turn += 1
            if p.get("out"):
                continue
            left = max(0, int(end_time - time.time()))

            if p.get("human"):
                reply = human_turn(left)
                if reply is None:
                    break
                if not reply:
                    continue
                print()
            else:
                others = [o["name"] for o in players if o is not p and not o.get("out")]
                msgs = [{"role": "system", "content": system_prompt(p["name"], topic, p["stance"], others)},
                        {"role": "user", "content": turn_prompt(topic, transcript, p["name"])}]
                print(f"{DIM}{p['name']} is thinking...{RESET}", end="\r", flush=True)
                try:
                    reply = call(p["backend"], p["model"], msgs)
                    p["fails"] = 0
                except BackendError as e:
                    p["fails"] += 1
                    print(f"{' ' * 40}\r  {DIM}[{p['name']} ({p['backend']['id']}) failed: {e}]{RESET}")
                    if e.fatal or p["fails"] >= 3:
                        p["out"] = True
                        print(f"  {DIM}[{p['name']} has left the discussion]{RESET}")
                    continue
                reply = re.sub(rf"^\s*{re.escape(p['name'])}\s*[:\-]\s*", "", reply)
                m = re.search(r"\[CONFIDENCE:\s*(\d+)\]", reply)
                if m:
                    confidence[p["name"]].append(int(m.group(1)))
                print(" " * 40, end="\r")
                print(f"{p['color']}{BOLD}{p['name']}{RESET} "
                      f"{DIM}[{p['backend']['id']}/{p['model']}] [{left // 60}:{left % 60:02d} left]{RESET}\n{reply}\n")

            transcript.append((p["name"], reply))

            if do_check:
                try:
                    for r in fact_check(neutral, reply):
                        ledger[p["name"]][r["verdict"]] += 1
                        col = GREEN if r["verdict"] == "VERIFIED" else RED if r["verdict"] == "FALSE" else YELLOW
                        src = f" {GREY}{r['source']}{RESET}" if r["source"] else ""
                        print(f"  {ICON[r['verdict']]} {col}{r['verdict']}{RESET} {DIM}[{p['name']}]{RESET} "
                              f"{r['claim']}\n     {DIM}{r['reason']}{RESET}{src}")
                        if r["verdict"] != "VERIFIED":
                            transcript.append(("FACT-CHECKER",
                                f"On {p['name']}'s claim \"{r['claim']}\": {r['verdict']} - {r['reason']}"))
                    print()
                except BackendError as e:
                    print(f"  {DIM}[fact-check skipped: {e}]{RESET}\n")
            time.sleep(delay)
    except KeyboardInterrupt:
        print("\n(stopped early)")

    result = verdict(topic, transcript, confidence, ledger, join, neutral)
    save_log(topic, transcript, ledger, result)


def verdict(topic, transcript, confidence, ledger, join, neutral):
    if len(transcript) < 2:
        return ""
    print(f"{BOLD}=== FACT-CHECK LEDGER ==={RESET}")
    for name, c in ledger.items():
        if sum(c.values()):
            print(f"  {name:<14} " + "  ".join(f"{ICON[k]}{c[k]}" for k in ICON))
    full = "\n\n".join(f"{s}: {t}" for s, t in transcript)
    led = "; ".join(f"{n}: {dict(c)}" for n, c in ledger.items())
    task = ("You are an experienced SSB Group Testing Officer. For EACH participant give a score out of 10 for: "
            "politeness, agreeing/disagreeing WITH reasons, factual accuracy (use the ledger), ability to "
            "convince, cooperation, and officer-like qualities. Add one strength and one improvement per "
            "person. Then say who did best and summarise where agreement or disagreement remains. Be concise.")
    if join:
        task += (" For 'You' give extra coaching: 3 strengths, 3 improvements, and rewrite your weakest "
                 "contribution the way an ideal candidate would say it.")
    prompt = (f"Topic: {topic}\n\nTranscript (includes FACT-CHECKER notes):\n{full}\n\n"
              f"Fact-check ledger: {led}\n\n{task}")
    print(f"\n{BOLD}=== JUDGE'S VERDICT ==={RESET}\n{DIM}(judging...){RESET}")
    try:
        out = neutral([{"role": "user", "content": prompt}], 1200, 0.3)
    except BackendError as e:
        out = f"(judge unavailable: {e})"
    print(out)
    print(f"\n{BOLD}Confidence trend (first -> last):{RESET}")
    for name, vals in confidence.items():
        if vals:
            print(f"  {name:<14} {vals[0]} -> {vals[-1]}  ({len(vals)} turns)")
    return out


def save_log(topic, transcript, ledger, result):
    os.makedirs("gd_logs", exist_ok=True)
    path = os.path.join("gd_logs", datetime.now().strftime("gd_%Y%m%d_%H%M%S.md"))
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# GD: {topic}\n\n")
        for s, t in transcript:
            f.write(f"**{s}:** {t}\n\n")
        f.write("## Fact-check ledger\n" + "\n".join(f"- {n}: {dict(c)}" for n, c in ledger.items()))
        f.write(f"\n\n## Verdict\n{result}\n")
    print(f"\n{DIM}Saved transcript -> {path}{RESET}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="SSB GD Simulator - every AI model is a participant")
    ap.add_argument("topic", nargs="?")
    ap.add_argument("--backends", help="only use these backends, e.g. groq,gemini,ollama")
    ap.add_argument("--models", help="exact participants as backend:model, comma-separated, "
                                      "e.g. groq:openai/gpt-oss-120b,ollama:llama3.2:3b")
    ap.add_argument("-n", "--max-models", type=int, help="use at most this many AI models")
    ap.add_argument("-s", "--stance", action="append", default=[],
                    help="stance for each AI, repeatable, in the order shown at startup")
    ap.add_argument("--judge", help="backend for fact-check and verdict (default: best free one)")
    ap.add_argument("--minutes", type=float, default=8)
    ap.add_argument("--delay", type=float, default=1, help="extra seconds between turns")
    ap.add_argument("--join", action="store_true", help="take part yourself as a candidate")
    ap.add_argument("--no-factcheck", action="store_true")
    ap.add_argument("--list-backends", action="store_true", help="show which models are ready")
    ap.add_argument("--list-models", metavar="BACKEND", help="list model names offered by a backend")
    a = ap.parse_args()

    if a.list_backends:
        list_backends()
        raise SystemExit
    if a.list_models:
        list_models(a.list_models)
        raise SystemExit

    topic = a.topic or ask_topic()
    if not topic:
        sys.exit("A topic is required.")
    only = [x.strip() for x in a.backends.split(",")] if a.backends else None
    run(topic, a.minutes, a.delay, a.join, not a.no_factcheck, only, a.models, a.max_models, a.stance, a.judge)
