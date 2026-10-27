#!/usr/bin/env python3
"""
SSB Group Discussion Simulator (terminal)
-----------------------------------------
* Several AI models (different providers) take different stances and discuss a topic for a set time.
* Every turn is FACT-CHECKED: claims are extracted, searched on the web, and given a verdict.
* SSB mode: polite, agree/disagree-with-reason etiquette; judge scores like a GTO (OLQs).
* --join lets YOU take part as a candidate and get coaching feedback.

Setup:
  pip install requests ddgs            # ddgs = free web search for the fact-checker
  export GROQ_API_KEY=...  GEMINI_API_KEY=...  OPENROUTER_API_KEY=...   # whichever you use

Examples:
  python gd_simulator.py "Should India have a common civil code?" --minutes 10
  python gd_simulator.py "Agniveer scheme: boon or bane?" --join --minutes 12
  python gd_simulator.py "Is nuclear energy the answer?" -s "Strongly for" -s "Against" --style debate
"""
import argparse, json, os, random, re, time
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

# ------------------------------------------------------------------ providers
# All expose an OpenAI-compatible /chat/completions API. Model names change often:
# check each provider's current free-tier list and edit below.
PROVIDERS = {
    "groq":       {"url": "https://api.groq.com/openai/v1",                         "key_env": "GROQ_API_KEY"},
    "gemini":     {"url": "https://generativelanguage.googleapis.com/v1beta/openai", "key_env": "GEMINI_API_KEY"},
    "openrouter": {"url": "https://openrouter.ai/api/v1",                            "key_env": "OPENROUTER_API_KEY"},
    "mistral":    {"url": "https://api.mistral.ai/v1",                               "key_env": "MISTRAL_API_KEY"},
    "xai":        {"url": "https://api.x.ai/v1",                                     "key_env": "XAI_API_KEY"},  # Grok (paid, per token)
    "ollama":     {"url": "http://localhost:11434/v1",                               "key_env": None},  # local, unlimited
}

# Setup: Grok (xAI) + Mistral + Ollama (local). Check each provider's current model names.
PARTICIPANTS = [
    {"name": "Grok",    "provider": "xai",     "model": "grok-4.3",           "color": "\033[96m"},  # verify at docs.x.ai
    {"name": "Mistral", "provider": "mistral", "model": "mistral-large-latest", "color": "\033[93m"},
    {"name": "Qwen",    "provider": "ollama",  "model": "qwen2.5:7b",         "color": "\033[95m"},  # ollama pull qwen2.5:7b
]
# Neutral model: generates stances, fact-checks, and judges. Using Mistral's smaller model
# keeps Grok (paid) out of the many extra fact-check calls.
NEUTRAL = {"name": "Neutral", "provider": "mistral", "model": "mistral-small-latest"}

RESET, DIM, BOLD = "\033[0m", "\033[2m", "\033[1m"
RED, GREEN, YELLOW, GREY = "\033[91m", "\033[92m", "\033[93m", "\033[90m"
HUMAN = {"name": "You", "human": True, "color": "\033[97m"}
ICON = {"VERIFIED": "✅", "PARTIAL": "⚠️ ", "UNVERIFIED": "❓", "FALSE": "❌"}


# ------------------------------------------------------------------ LLM call
def chat(p, messages, max_tokens=450, temperature=0.8):
    prov = PROVIDERS[p["provider"]]
    headers = {"Content-Type": "application/json"}
    if prov["key_env"]:
        key = os.getenv(prov["key_env"])
        if not key:
            raise RuntimeError(f"Missing env var {prov['key_env']} for {p['name']}")
        headers["Authorization"] = f"Bearer {key}"
    body = {"model": p["model"], "messages": messages,
            "max_tokens": max_tokens, "temperature": temperature}
    for attempt in range(5):                       # free tiers rate-limit: back off and retry
        try:
            r = requests.post(f"{prov['url']}/chat/completions", json=body, headers=headers, timeout=90)
            if r.status_code in (429, 500, 502, 503):
                time.sleep(2 ** attempt + random.random())
                continue
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"] or ""
            return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
        except requests.RequestException as e:
            if attempt == 4:
                raise RuntimeError(f"{p['name']} failed: {e}")
            time.sleep(2 ** attempt)
    raise RuntimeError(f"{p['name']}: rate-limited repeatedly")


def parse_json(raw, default):
    m = re.search(r"(\[.*\]|\{.*\})", raw, re.S)
    try:
        return json.loads(m.group(1)) if m else default
    except Exception:
        return default


# ------------------------------------------------------------------ fact-checker
def web_evidence(claim, n=4):
    """Free web search (DuckDuckGo). Returns [] if library missing or search fails."""
    if DDGS is None:
        return []
    try:
        with DDGS() as d:
            return [{"title": r.get("title", ""), "url": r.get("href", ""), "snippet": r.get("body", "")}
                    for r in d.text(claim, max_results=n)]
    except Exception:
        return []


def fact_check(text):
    """Extract up to 2 checkable claims from a turn, search the web, return verdicts."""
    raw = chat(NEUTRAL, [{"role": "user", "content":
        "Extract up to 2 specific, CHECKABLE factual claims (statistics, dates, studies, laws, named events) "
        "from the discussion turn below. Ignore opinions and general reasoning. Rewrite each as a standalone "
        "sentence. Return ONLY a JSON list of strings, or [] if none.\n\nTURN:\n" + text}], 300, 0.0)
    claims = [c for c in parse_json(raw, []) if isinstance(c, str)][:2]
    if not claims:
        return []

    blocks = []
    for i, c in enumerate(claims):
        ev = web_evidence(c)
        ev_txt = "\n".join(f"  - {e['title']} ({e['url']}): {e['snippet'][:300]}" for e in ev) \
            or "  (no web evidence available)"
        blocks.append(f"CLAIM {i}: {c}\nEVIDENCE:\n{ev_txt}")

    prompt = (
        "You are a strict fact-checker. Judge each claim against the EVIDENCE given. If there is no "
        "evidence, rely on well-established knowledge only, and never say VERIFIED for obscure figures.\n"
        "Verdicts: VERIFIED (evidence supports it), PARTIAL (roughly right but number/context off or "
        "exaggerated), UNVERIFIED (cannot confirm), FALSE (contradicted by evidence).\n"
        'Return ONLY a JSON list: [{"id":0,"verdict":"...","reason":"max 20 words","source":"url or empty"}]\n\n'
        + "\n\n".join(blocks))
    results = parse_json(chat(NEUTRAL, [{"role": "user", "content": prompt}], 500, 0.0), [])

    out = []
    for i, c in enumerate(claims):
        r = next((x for x in results if isinstance(x, dict) and x.get("id") == i), {})
        v = str(r.get("verdict", "UNVERIFIED")).upper()
        out.append({"claim": c, "verdict": v if v in ICON else "UNVERIFIED",
                    "reason": r.get("reason", ""), "source": r.get("source", "")})
    return out


# ------------------------------------------------------------------ prompts
SSB_STYLE = """
SSB GROUP DISCUSSION ETIQUETTE (a Group Testing Officer is assessing everyone):
- Be POLITE and respectful. Attack the point, never the person. No sarcasm, no raised voice, no interrupting.
- Begin by naming a previous speaker and acknowledging their point before you agree or disagree.
- Always say AGREE or DISAGREE explicitly and give the WHY. Patterns:
    "I agree with <name> on <point>, because <reason>."
    "I respectfully disagree with <name> on <point>, because <reason / evidence>."
    "I partly agree with <name>; however <reason>."
- Then add ONE NEW point backed by a fact, example or logic - never just repeat what was said.
- Sometimes bring in others politely ("<name>, what is your view on this?") and never dominate.
- Be solution-oriented: when views clash, suggest a practical middle path or action.
- Show officer-like qualities: clear reasoning, cooperation, confidence without arrogance, leadership.
- Length: 60-110 words, spoken style, no bullet points."""

DEBATE_STYLE = """
DEBATE STYLE: Be assertive but civil. Rebut a specific claim from the previous speakers, challenge
unsupported claims ("What is your evidence for X?") and call out fallacies. 80-130 words, no bullets."""


def system_prompt(p, topic, stance, others, style):
    return f"""You are {p['name']}, a participant in a live group discussion with {', '.join(others)}.
TOPIC: {topic}
YOUR STARTING STANCE: {stance}

GOAL: Convince the group through well-reasoned, factual arguments.
CORE RULES
1. Support your point with concrete evidence (statistic, study, law, historical or real-world case).
   Name the source or year when you can.
2. NEVER invent sources, numbers or quotes. If unsure, say "I believe..." or leave the claim out.
3. A neutral FACT-CHECKER may flag claims. If YOUR claim is flagged, politely acknowledge and correct it.
   If another speaker's claim is flagged, you may politely raise it.
4. If someone proves you wrong with good evidence, concede that point gracefully and refine your stance.
5. End EVERY turn with exactly: [CONFIDENCE: NN]  (0-100, how strongly you still hold your stance).
{SSB_STYLE if style == 'ssb' else DEBATE_STYLE}"""


def turn_prompt(topic, transcript, name):
    recent = "\n\n".join(f"{s}: {t}" for s, t in transcript[-9:]) or "(You are opening the discussion.)"
    return f"Discussion so far on '{topic}':\n\n{recent}\n\nIt is now your turn, {name}."


def generate_stances(topic, n):
    msg = [{"role": "user", "content":
            f"Topic: {topic}\nWrite {n} clearly distinct, defensible stances people could take (spanning for / "
            f"against / nuanced). One per line, max 15 words each, no numbering."}]
    lines = [l.strip(" -*0123456789.") for l in chat(NEUTRAL, msg, 200).splitlines() if l.strip()]
    return (lines + ["Pragmatic middle ground"] * n)[:n]


# ------------------------------------------------------------------ human turn
def human_turn(p, left):
    print(f"{p['color']}{BOLD}YOU{RESET} {DIM}[{left // 60}:{left % 60:02d} left] "
          f"type your point + ENTER | blank = pass | /quit = end{RESET}")
    try:
        s = input("> ").strip()
    except (EOFError, KeyboardInterrupt):
        return None
    return None if s.lower() == "/quit" else s


# ------------------------------------------------------------------ main loop
def available(p):
    """True if the provider's key is set (or, for Ollama, the local server is running)."""
    prov = PROVIDERS[p["provider"]]
    if prov["key_env"]:
        return bool(os.getenv(prov["key_env"]))
    try:
        requests.get(prov["url"].replace("/v1", ""), timeout=2)
        return True
    except requests.RequestException:
        return False


def run(topic, minutes, stances, delay, style, join, do_check):
    global NEUTRAL
    players, skipped = [], []
    for p in PARTICIPANTS:
        (players if available(p) else skipped).append(dict(p))
    for p in skipped:
        why = f"set {PROVIDERS[p['provider']]['key_env']}" if PROVIDERS[p["provider"]]["key_env"] \
            else "start Ollama (ollama serve)"
        print(f"{DIM}Skipping {p['name']} ({p['provider']}): {why}{RESET}")
    if not players:
        raise SystemExit("No AI models available. Set at least one API key or start Ollama - see README.")
    if not available(NEUTRAL):
        NEUTRAL = {**players[0], "name": "Neutral"}
        print(f"{DIM}Neutral model unavailable; using {players[0]['name']} for fact-check and judging.{RESET}")
    n_ai = len(players)
    stances = (stances + [None] * n_ai)[:n_ai]
    if None in stances:
        auto = generate_stances(topic, n_ai)
        stances = [s or auto[i] for i, s in enumerate(stances)]
    for p, s in zip(players, stances):
        p["stance"] = s
    if join:
        h = dict(HUMAN)
        h["stance"] = "Your own view - speak naturally, as you would before the GTO"
        players.append(h)

    mode = "SSB (polite, agree/disagree with reasons)" if style == "ssb" else "Debate"
    print(f"\n{BOLD}=== GROUP DISCUSSION ==={RESET}\nTopic : {BOLD}{topic}{RESET}")
    print(f"Time  : {minutes} min   Style: {mode}   Fact-check: {'ON' if do_check else 'OFF'}"
          f"{'' if DDGS or not do_check else '  (install `ddgs` for web evidence)'}\n")
    for p in players:
        who = "human" if p.get("human") else f"{p['provider']}/{p['model']}"
        print(f"{p['color']}{p['name']:<9}{RESET} ({who}) -> {p['stance']}")
    print()

    transcript, confidence = [], {p["name"]: [] for p in players if not p.get("human")}
    ledger = {p["name"]: Counter() for p in players}
    order = players[:]
    random.shuffle(order)
    end_time, turn = time.time() + minutes * 60, 0

    try:
        while time.time() < end_time:
            p = order[turn % len(order)]
            turn += 1
            left = max(0, int(end_time - time.time()))

            if p.get("human"):
                reply = human_turn(p, left)
                if reply is None:
                    break
                if not reply:
                    continue
                print()
            else:
                others = [o["name"] for o in players if o is not p]
                msgs = [{"role": "system", "content": system_prompt(p, topic, p["stance"], others, style)},
                        {"role": "user", "content": turn_prompt(topic, transcript, p["name"])}]
                try:
                    reply = chat(p, msgs)
                except RuntimeError as e:
                    print(f"{DIM}[{e} - skipping turn]{RESET}")
                    continue
                m = re.search(r"\[CONFIDENCE:\s*(\d+)\]", reply)
                if m:
                    confidence[p["name"]].append(int(m.group(1)))
                print(f"{p['color']}{BOLD}{p['name']}{RESET} {DIM}[{left // 60}:{left % 60:02d} left]{RESET}\n{reply}\n")

            transcript.append((p["name"], reply))

            if do_check:
                try:
                    for r in fact_check(reply):
                        ledger[p["name"]][r["verdict"]] += 1
                        col = GREEN if r["verdict"] == "VERIFIED" else RED if r["verdict"] == "FALSE" else YELLOW
                        src = f" {GREY}{r['source']}{RESET}" if r["source"] else ""
                        print(f"  {ICON[r['verdict']]} {col}{r['verdict']}{RESET} {DIM}[{p['name']}]{RESET} "
                              f"{r['claim']}\n     {DIM}{r['reason']}{RESET}{src}")
                        if r["verdict"] != "VERIFIED":      # let the group react to shaky claims
                            transcript.append(("FACT-CHECKER",
                                f"On {p['name']}'s claim \"{r['claim']}\": {r['verdict']} - {r['reason']}"))
                    print()
                except RuntimeError as e:
                    print(f"  {DIM}[fact-check skipped: {e}]{RESET}\n")

            time.sleep(delay)
    except KeyboardInterrupt:
        print("\n(stopped early)")

    result = verdict(topic, transcript, confidence, ledger, style, join)
    save_log(topic, transcript, ledger, result)


# ------------------------------------------------------------------ judge
def verdict(topic, transcript, confidence, ledger, style, join):
    if len(transcript) < 2:
        return ""
    print(f"{BOLD}=== FACT-CHECK LEDGER ==={RESET}")
    for name, c in ledger.items():
        if sum(c.values()):
            print(f"  {name:<9} " + "  ".join(f"{ICON[k]}{c[k]}" for k in ICON))
    full = "\n\n".join(f"{s}: {t}" for s, t in transcript)
    led = "; ".join(f"{n}: {dict(c)}" for n, c in ledger.items())

    if style == "ssb":
        task = (
            "You are an experienced SSB Group Testing Officer. Assess EACH participant on: (1) politeness and "
            "etiquette, (2) agreeing/disagreeing WITH stated reasons, (3) quality and factual accuracy of "
            "evidence (use the fact-check ledger), (4) ability to influence and convince the group, "
            "(5) cooperation and including others, (6) officer-like qualities shown (reasoning, initiative, "
            "confidence, leadership, solution orientation). Give a score /10 for each of the six areas, plus "
            "one concrete strength and one improvement per person. Then name who would most likely be "
            "recommended and why, and summarise where consensus or disagreement remains.")
        if join:
            task += (" For participant 'You' give EXTRA coaching: 3 strengths, 3 improvements, and rewrite your "
                     "weakest contribution the way an ideal candidate would say it.")
    else:
        task = ("You are a strict debate judge. For EACH participant give /10 for persuasiveness and factual "
                "rigor, list unsupported or fabricated claims, note concessions, name the winner, and "
                "summarise the remaining disagreement.")

    prompt = (f"Topic: {topic}\n\nTranscript (includes FACT-CHECKER notes):\n{full}\n\n"
              f"Fact-check ledger: {led}\nConfidence trends: {confidence}\n\n{task}")
    print(f"\n{BOLD}=== JUDGE'S VERDICT ==={RESET}")
    try:
        out = chat(NEUTRAL, [{"role": "user", "content": prompt}], 1400, 0.3)
    except RuntimeError as e:
        out = f"(judge unavailable: {e})"
    print(out)
    print(f"\n{BOLD}Confidence trend (first -> last):{RESET}")
    for name, vals in confidence.items():
        if vals:
            print(f"  {name:<9} {vals[0]} -> {vals[-1]}  ({len(vals)} turns)")
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
    ap = argparse.ArgumentParser(description="SSB Group Discussion Simulator")
    ap.add_argument("topic")
    ap.add_argument("--minutes", type=float, default=8)
    ap.add_argument("--delay", type=float, default=2, help="seconds between turns (free-tier rate limits)")
    ap.add_argument("--style", choices=["ssb", "debate"], default="ssb")
    ap.add_argument("--join", action="store_true", help="take part yourself as a candidate")
    ap.add_argument("--no-factcheck", action="store_true")
    ap.add_argument("-s", "--stance", action="append", default=[], help="repeat once per AI participant")
    a = ap.parse_args()
    run(a.topic, a.minutes, a.stance, a.delay, a.style, a.join, not a.no_factcheck)
