#!/usr/bin/env python3
"""
SSB Group Discussion Simulator - OLLAMA ONLY (free, offline, unlimited)
-----------------------------------------------------------------------
Several AI "characters" (retired officer, economist, student, ...) discuss a topic for a set time.
You choose how many characters take part. No API keys needed - everything runs on your PC.

One-time setup:
  1. Install Ollama from https://ollama.com  (it runs in the background)
  2. ollama pull qwen2.5:7b          (or a smaller one: ollama pull llama3.2:3b)
  3. pip install requests ddgs       (ddgs = free web search for the fact-checker)

Examples:
  python gd_ollama.py                                   # asks for topic + number of characters
  python gd_ollama.py "Agnipath scheme: boon or bane?" -n 4 --minutes 8
  python gd_ollama.py "Should voting be compulsory?" -n 3 --join
  python gd_ollama.py "EVs in India" --pick Arjun,Meera,Rahul
  python gd_ollama.py --list-characters
  python gd_ollama.py "Topic" -n 3 --models qwen2.5:7b,llama3.2:3b     # different model per character
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

OLLAMA = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
DEFAULT_MODEL = "qwen2.5:7b"

# ------------------------------------------------------------------ characters
CHARACTERS = [
    {"name": "Arjun",  "role": "Retired Army Major",
     "lens": "You value discipline, national security, operational readiness and lessons from real field experience."},
    {"name": "Meera",  "role": "Economist",
     "lens": "You think in budgets, incentives, costs and benefits, and long-term fiscal impact; you like data."},
    {"name": "Rahul",  "role": "College Student",
     "lens": "You speak for young people: jobs, education, aspirations and how policies feel on the ground."},
    {"name": "Dr. Iyer", "role": "Sociologist",
     "lens": "You focus on social impact, inequality, communities and unintended consequences."},
    {"name": "Farah",  "role": "Journalist",
     "lens": "You care about public interest, transparency and accountability, and ask pointed but fair questions."},
    {"name": "Kabir",  "role": "Tech Entrepreneur",
     "lens": "You favour innovation, technology and efficiency, and look for scalable practical solutions."},
    {"name": "Lakshmi", "role": "School Teacher and Parent",
     "lens": "You think about families, children's futures, ethics and values."},
    {"name": "Vikram", "role": "Civil Servant and Policy Analyst",
     "lens": "You focus on implementation, law, governance and whether a plan is actually workable."},
    {"name": "Anita",  "role": "Environmental Scientist",
     "lens": "You weigh long-term sustainability, evidence from research and impact on future generations."},
    {"name": "Samir",  "role": "Small Business Owner",
     "lens": "You speak from everyday economic reality: employment, local markets and practical hardships."},
]
COLORS = ["\033[96m", "\033[93m", "\033[92m", "\033[95m", "\033[94m", "\033[91m", "\033[36m", "\033[33m", "\033[32m", "\033[35m"]

# Starting leans guarantee real disagreement. First two are always one FOR and one AGAINST.
LEANS = [
    "You are broadly IN FAVOUR of the idea, and must back that up with facts.",
    "You are broadly AGAINST the idea, but you stay polite and fact-based.",
    "You are CONDITIONAL: you support it only with specific safeguards, which you name.",
    "You are SKEPTICAL but open to being convinced by good evidence.",
    "You prefer a MIDDLE PATH: a hybrid or phased solution.",
    "You support the GOAL but are critical of the CURRENT method.",
]

RESET, DIM, BOLD = "\033[0m", "\033[2m", "\033[1m"
GREEN, RED, YELLOW, GREY = "\033[92m", "\033[91m", "\033[93m", "\033[90m"
ICON = {"VERIFIED": "✅", "PARTIAL": "⚠️ ", "UNVERIFIED": "❓", "FALSE": "❌"}


# ------------------------------------------------------------------ Ollama
def installed_models():
    try:
        r = requests.get(f"{OLLAMA}/api/tags", timeout=5)
        r.raise_for_status()
    except requests.RequestException:
        sys.exit("Cannot reach Ollama at " + OLLAMA + ".\n"
                 "Start the Ollama app (or run `ollama serve` in another window) and try again.")
    return [m["name"] for m in r.json().get("models", [])]


def has_model(name, installed):
    return name in installed or f"{name}:latest" in installed


def llm(model, messages, max_tokens=300, temperature=0.8):
    body = {"model": model, "messages": messages, "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens}}
    try:
        r = requests.post(f"{OLLAMA}/api/chat", json=body, timeout=600)
    except requests.ConnectionError:
        raise RuntimeError("lost connection to Ollama")
    except requests.Timeout:
        raise RuntimeError(f"model '{model}' timed out (try a smaller model)")
    if r.status_code >= 400:
        raise RuntimeError(f"Ollama HTTP {r.status_code}: {r.text[:200]}")
    text = r.json().get("message", {}).get("content", "") or ""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()


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


def fact_check(model, text):
    raw = llm(model, [{"role": "user", "content":
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
    results = parse_json(llm(model, [{"role": "user", "content": prompt}], 400, 0.0), [])
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
  PARTLY AGREE, and say WHY. Example: "I respectfully disagree with Meera on cost, because ..."
- Add ONE new point with a real fact, example or logic. Do not repeat what was already said.
- Sometimes invite another person: "Rahul, what is your view?" Never dominate.
- Be solution-oriented; suggest a practical middle path when views clash."""


def system_prompt(c, topic, others):
    return f"""You are {c['name']}, a {c['role']}, taking part in a live group discussion with {', '.join(others)}.
TOPIC: {topic}

YOUR PERSPECTIVE: {c['lens']}
YOUR STARTING POSITION: {c['lean']}
Speak in your own voice, as someone with your background would, but stay polite.

RULES
1. Give concrete evidence (a statistic, law, study, historical or real example). Name source or year if you can.
2. NEVER invent numbers or sources. If unsure, say "I believe..." or leave it out.
3. A neutral FACT-CHECKER may flag claims. If YOURS is flagged, politely acknowledge and correct it.
4. If someone proves you wrong, concede that point gracefully.
5. Write ONLY your own turn: 3 to 5 sentences (60-100 words), spoken style, no bullet points, no name prefix.
6. Finish with a last line exactly like: [CONFIDENCE: NN]  (0-100, how strongly you hold your position).
{SSB_STYLE}"""


def turn_prompt(topic, transcript, name):
    recent = "\n\n".join(f"{s}: {t}" for s, t in transcript[-8:]) or \
        "(Nobody has spoken yet. You are the FIRST speaker: state your position briefly with one fact. " \
        "Do not refer to other speakers.)"
    return f"Discussion so far on '{topic}':\n\n{recent}\n\nIt is now your turn, {name}."


# ------------------------------------------------------------------ setup helpers
def choose_characters(n, picks):
    if picks:
        wanted = [p.strip().lower() for p in picks.split(",") if p.strip()]
        chosen = [c for c in CHARACTERS if c["name"].lower() in wanted]
        missing = set(wanted) - {c["name"].lower() for c in chosen}
        if missing:
            sys.exit(f"Unknown character(s): {', '.join(missing)}. Use --list-characters to see names.")
    else:
        chosen = random.sample(CHARACTERS, n)
    chosen = [dict(c) for c in chosen]
    for i, c in enumerate(chosen):
        c["lean"] = LEANS[i % len(LEANS)]
        c["color"] = COLORS[i % len(COLORS)]
    return chosen


def ask_int(prompt, lo, hi, default):
    while True:
        s = input(f"{prompt} [{lo}-{hi}, default {default}]: ").strip()
        if not s:
            return default
        if s.isdigit() and lo <= int(s) <= hi:
            return int(s)
        print(f"  Please enter a number from {lo} to {hi}.")


def human_turn(left):
    print(f"\033[97m{BOLD}YOU{RESET} {DIM}[{left // 60}:{left % 60:02d} left] "
          f"type your point + ENTER | blank = pass | /quit = end{RESET}")
    try:
        s = input("> ").strip()
    except (EOFError, KeyboardInterrupt):
        return None
    return None if s.lower() == "/quit" else s


# ------------------------------------------------------------------ main loop
def run(topic, n, picks, minutes, delay, join, do_check, models, judge_model):
    chars = choose_characters(n, picks)
    for i, c in enumerate(chars):
        c["model"] = models[i % len(models)]

    print(f"\n{BOLD}=== GROUP DISCUSSION (Ollama only) ==={RESET}\nTopic : {BOLD}{topic}{RESET}")
    print(f"Time  : {minutes} min   Characters: {len(chars)}{' + you' if join else ''}   "
          f"Fact-check: {'ON' if do_check else 'OFF'}"
          f"{'' if DDGS or not do_check else '  (pip install ddgs for web evidence)'}\n")
    for c in chars:
        print(f"{c['color']}{c['name']:<9}{RESET} {c['role']} [{c['model']}]\n{'':<10}{DIM}{c['lean']}{RESET}")
    if join:
        print(f"\033[97m{'You':<9}{RESET} Candidate - speak your own view")
    print()

    players = chars + ([{"name": "You", "human": True, "color": "\033[97m"}] if join else [])
    transcript, confidence = [], {c["name"]: [] for c in chars}
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
                reply = human_turn(left)
                if reply is None:
                    break
                if not reply:
                    continue
                print()
            else:
                others = [o["name"] for o in players if o is not p]
                msgs = [{"role": "system", "content": system_prompt(p, topic, others)},
                        {"role": "user", "content": turn_prompt(topic, transcript, p["name"])}]
                print(f"{DIM}{p['name']} is thinking...{RESET}", end="\r", flush=True)
                try:
                    reply = llm(p["model"], msgs)
                except RuntimeError as e:
                    print(f"{DIM}[{e} - skipping turn]{RESET}")
                    continue
                reply = re.sub(rf"^\s*{re.escape(p['name'])}\s*[:\-]\s*", "", reply)   # strip "Name:" prefix
                m = re.search(r"\[CONFIDENCE:\s*(\d+)\]", reply)
                if m:
                    confidence[p["name"]].append(int(m.group(1)))
                print(" " * 40, end="\r")
                print(f"{p['color']}{BOLD}{p['name']}{RESET} {DIM}({p['role']}) "
                      f"[{left // 60}:{left % 60:02d} left]{RESET}\n{reply}\n")

            transcript.append((p["name"], reply))

            if do_check:
                try:
                    for r in fact_check(judge_model, reply):
                        ledger[p["name"]][r["verdict"]] += 1
                        col = GREEN if r["verdict"] == "VERIFIED" else RED if r["verdict"] == "FALSE" else YELLOW
                        src = f" {GREY}{r['source']}{RESET}" if r["source"] else ""
                        print(f"  {ICON[r['verdict']]} {col}{r['verdict']}{RESET} {DIM}[{p['name']}]{RESET} "
                              f"{r['claim']}\n     {DIM}{r['reason']}{RESET}{src}")
                        if r["verdict"] != "VERIFIED":
                            transcript.append(("FACT-CHECKER",
                                f"On {p['name']}'s claim \"{r['claim']}\": {r['verdict']} - {r['reason']}"))
                    print()
                except RuntimeError as e:
                    print(f"  {DIM}[fact-check skipped: {e}]{RESET}\n")
            time.sleep(delay)
    except KeyboardInterrupt:
        print("\n(stopped early)")

    result = verdict(topic, transcript, confidence, ledger, join, judge_model)
    save_log(topic, transcript, ledger, result)


def verdict(topic, transcript, confidence, ledger, join, judge_model):
    if len(transcript) < 2:
        return ""
    print(f"{BOLD}=== FACT-CHECK LEDGER ==={RESET}")
    for name, c in ledger.items():
        if sum(c.values()):
            print(f"  {name:<9} " + "  ".join(f"{ICON[k]}{c[k]}" for k in ICON))
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
    print(f"\n{BOLD}=== JUDGE'S VERDICT ==={RESET}\n{DIM}(judging, this can take a minute on a local model...){RESET}")
    try:
        out = llm(judge_model, [{"role": "user", "content": prompt}], 1200, 0.3)
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
    ap = argparse.ArgumentParser(description="SSB GD Simulator - Ollama only")
    ap.add_argument("topic", nargs="?")
    ap.add_argument("-n", "--characters", type=int, help=f"number of AI characters (2-{len(CHARACTERS)})")
    ap.add_argument("--pick", help="choose characters by name, e.g. Arjun,Meera,Rahul")
    ap.add_argument("--minutes", type=float, default=8)
    ap.add_argument("--delay", type=float, default=1, help="seconds between turns")
    ap.add_argument("--join", action="store_true", help="take part yourself as a candidate")
    ap.add_argument("--no-factcheck", action="store_true")
    ap.add_argument("--model", default=DEFAULT_MODEL, help=f"Ollama model (default {DEFAULT_MODEL})")
    ap.add_argument("--models", help="comma-separated models, rotated across characters")
    ap.add_argument("--list-characters", action="store_true")
    a = ap.parse_args()

    if a.list_characters:
        for c in CHARACTERS:
            print(f"{c['name']:<9} {c['role']:<34} {c['lens']}")
        raise SystemExit

    topic = a.topic or input("Discussion topic: ").strip()
    if not topic:
        sys.exit("A topic is required.")
    if a.pick:
        n = len([p for p in a.pick.split(",") if p.strip()])
    else:
        n = a.characters or ask_int("How many AI characters?", 2, len(CHARACTERS), 3)
    if not 2 <= n <= len(CHARACTERS):
        sys.exit(f"Choose between 2 and {len(CHARACTERS)} characters.")

    models = [m.strip() for m in (a.models or a.model).split(",") if m.strip()]
    have = installed_models()
    for m in models:
        if not has_model(m, have):
            sys.exit(f"Model '{m}' is not installed.\nRun:  ollama pull {m}\n"
                     f"Installed: {', '.join(have) or 'none'}")
    run(topic, n, a.pick, a.minutes, a.delay, a.join, not a.no_factcheck, models, models[0])
