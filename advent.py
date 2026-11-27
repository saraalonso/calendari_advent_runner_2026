#!/usr/bin/env python3
"""Calendari d'Advent de Running 2026 - bot de Telegram (sense dependencies externes).

Ús:
  python advent.py run        # un cicle: processa comandes + envia el missatge del dia (GitHub Actions)
  python advent.py loop       # el mateix en bucle cada 30 s (PC / Raspberry / servidor local)
  python advent.py setup      # registra el menú de comandes al bot
  python advent.py simulate N # prova offline: N calendaris aleatoris verificant totes les regles
  python advent.py preview    # imprimeix un calendari d'exemple (spoiler!)

Variables d'entorn: TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, (opcional) STATE_FILE.
"""
import json
import os
import random
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Madrid")
YEAR = 2026
START, END, RACE = date(YEAR, 12, 1), date(YEAR, 12, 24), date(YEAR, 12, 31)
SEND_AT, RACE_AT = (7, 30), (7, 0)
STATE_FILE = os.environ.get("STATE_FILE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json"))

# Dies festius / cap de setmana amb llum de dia completa
HOLIDAYS = {date(YEAR, 12, d) for d in (5, 6, 7, 8, 12, 13, 19, 20)}
# Dies on poden sortir les tirades llargues. ATENCIO: amb la regla original (7, 8, 12, 13, 19, 20)
# les 4 tirades llargues NO caben (7-8, 12-13 i 19-20 són parelles consecutives => màxim 3).
# S'ha afegit el diumenge 6 (així el pont accepta 6 + 8 = 2 tirades no consecutives).
LONG_DAYS = {6, 7, 8, 12, 13, 19, 20}
LONG_85_FROM = 12  # el 8,5 km no surt abans del 12

# ----------------------------------------------------------------------------- bombo
ITEMS = {}


def _add(i, g, txt, **kw):
    ITEMS[i] = dict(id=i, g=g, txt=txt, **kw)


for _i, _t in enumerate([
    "Descans total (Avui toca sofà i recuperar energies)",
    "Descans total (Avui no es corre, deixa descansar les cames)",
    "Descans total (Dia lliure d'esport)",
    "Descans total (Recuperació completa)",
    "Descans total (Avui toca cuidar-se i dormir bé)"], 1):
    _add(_i, "A", _t, rest=True)
_add(6, "A", "15 min d'estiraments suaus (Cames, esquena i glutis)")
_add(7, "A", "20 min de mobilitat (Turmells, genolls i malucs)")
_add(8, "A", "15 min d'estiraments + automassatge als bessons i peus")
_add(9, "B", "30 min de caminata ràpida a pas alegre", walk=True)
_add(10, "B", "COMODÍ GIMNÀS", com="gym",
     equiv="30 min d'exercicis de força a casa sense pes (esquats, planxes, pont de glutis, genolls amunt) o 30 min de caminata ràpida")
_add(11, "B", "COMODÍ RUTA EN PARELLA 1", com="ruta",
     equiv="45 min de caminata ràpida sense pauses (idealment buscant alguna pujada suau)")
_add(12, "B", "COMODÍ RUTA EN PARELLA 2", com="ruta",
     equiv="45 min de caminata ràpida sense pauses (idealment buscant alguna pujada suau)")
for _i, _km, _t in [
    (13, 2, "2 km molt suaus (o alternar 2 min corrent + 1 min caminant)"),
    (14, 2, "2 km molt suaus a ritme de xerrada"),
    (15, 3, "3 km suaus (sense mirar el rellotge)"),
    (16, 3, "3 km suaus centrant-te en respirar còmode"),
    (17, 4, "4 km suaus a ritme constant"),
    (18, 4, "4 km suaus (primers 2 km lents, últims 2 km còmodes)"),
    (19, 5, "5 km suaus (gairebé mitja cursa!)"),
    (20, 5, "5 km suaus a ritme constant"),
    (21, 6, "6 km (4 km suaus + últims 2 km una mica més alegres)"),
    (22, 6, "6 km (4 km suaus + últims 2 km a ritme de cursa)"),
    (23, 7.5, "7,5 km a ritme còmode i constant"),
    (24, 8.5, "8,5 km (El gran test final abans del 31!)")]:
    _add(_i, "C", _t, km=_km, long=_km >= 6)
# Paperet de seguretat (fora del bombo) per al /canvi quan no queden descansos
_add(0, "A", "Descans total (Avui prima la salut: descansa sense culpes)", rest=True)

POT0 = [i for i in ITEMS if i != 0 and not ITEMS[i].get("com")]  # 21 paperets aleatoris
COM0 = [10, 11, 12]

TAPER = {
    25: "😴 Descans total. Gaudeix de Nadal i deixa descansar el cos.",
    26: "🏃 Rodatge de 4 km molt suaus (ritme lent i còmode per baixar els àpats sense cansar-se).",
    27: "😴 Descans total i bona hidratació.",
    28: ("🏃 3 km suaus + 3 rectes: 3 km lents + 3 acceleracions curtes de 50 m sense esprintar al màxim, "
         "caminant 1 min entre cadascuna, per despertar les cames."),
    29: "🧘 15 min de mobilitat + estiraments suaus (sense córrer).",
    30: ("😴 Descans total i preparació: no facis esport. Deixa preparat el dorsal, la roba, les Adidas Trail "
         "i un sopar lleuger."),
}
RACE_MSG = (
    "🏁 DIA DE CURSA (10,5 km +150 m a les 10:00 h)\n\n"
    "1️⃣ Esmorza entre les 7:30 i les 8:00: 2 torrades de pa blanc amb melmelada/gall dindi + 1 plàtan + "
    "cafè/infusió. Evita fibra i sucs àcids. Deixa de beure aigua 45 min abans.\n"
    "2️⃣ Surt més lent del que toca els primers 3 km per no cremar-te.\n"
    "3️⃣ Camina a pas ràpid les rampes fortes si n'hi ha, per estalviar energia.\n"
    "4️⃣ Gaudeix i creua la meta! 🎉"
)

# ----------------------------------------------------------------------------- regles
NEUTRAL = (False, False, False, False, False)   # (córrer, descans total, activitat, llarga, ruta)
WILD = (False, False, True, False, True)         # dia de comodí encara per decidir


def flags(it, equiv=False):
    if equiv:
        return (False, False, True, False, False)
    run = it.get("km") is not None
    return (run, bool(it.get("rest")), run or bool(it.get("walk")) or bool(it.get("com")),
            bool(it.get("long")), it.get("com") == "ruta")


def sig_of(it):
    return (flags(it), it.get("km"))


def seq_ok(prev, f):
    run, rest, active, long_, _ = f
    p1 = prev[-1] if len(prev) >= 1 else None
    p2 = prev[-2] if len(prev) >= 2 else None
    if p1 and p2:
        if run and p1[0] and p2[0]:
            return False                       # regla 4: màx. 2 dies seguits corrent
        if p1[1] and p2[1] and (rest or not active):
            return False                       # regla 5: després de 2 descansos, activitat
    if p1 and long_ and (p1[3] or p1[4]):
        return False                           # regla 6 + (ruta llarga => l'endemà no tirada llarga)
    return True


def day_kind(d, st):
    if d in HOLIDAYS or d.weekday() >= 5:
        return "free"
    ov = st.get("light", {}).get(d.isoformat())
    if ov:
        return ov
    return {0: "night", 2: "night", 1: "dusk", 3: "dusk", 4: "friday"}[d.weekday()]


def allowed(it, d, kind):
    if it.get("com") == "ruta":
        return kind == "free"
    if it.get("com") == "gym":
        return True
    if it.get("long"):
        return kind == "free" and d.day in LONG_DAYS and (it["km"] < 8 or d.day >= LONG_85_FROM)
    km = it.get("km")
    if km is not None:
        return km <= 4 if kind == "night" else km <= 5
    return True


# ----------------------------------------------------------------------------- estat
def new_state():
    return {"offset": 0, "hist": {}, "pot": list(POT0), "com": list(COM0), "booked": {}, "light": {}, "sent": {}}


def load():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    return new_state()


def save(st):
    with open(STATE_FILE, "w", encoding="utf-8") as fh:
        json.dump(st, fh, ensure_ascii=False, indent=1, sort_keys=True)


def hist_prev(st, before):
    out, d = [], START
    while d < before:
        r = st["hist"].get(d.isoformat())
        out.append(flags(ITEMS[r["id"]], r.get("equiv")) if r else NEUTRAL)
        d = date.fromordinal(d.toordinal() + 1)
    return tuple(out[-2:])


def build_seq(st, start):
    seq, d = [], start
    while d <= END:
        b = st["booked"].get(d.isoformat())
        seq.append((d, ITEMS[b] if b else None))
        d = date.fromordinal(d.toordinal() + 1)
    return seq


_MEMO = {}
ALL_SIGS = sorted({sig_of(ITEMS[i]) for i in POT0}, key=repr)


def solve(seq, pot_ids, wild_left, prev, st, rng):
    """Cert si els paperets restants caben als dies restants complint totes les regles.
    Memoritza resultats (estat = dia, paperets que queden, comodins lliures, últims 2 dies, context)."""
    reps = {}
    counts = {s: 0 for s in ALL_SIGS}
    for i in pot_ids:
        s = sig_of(ITEMS[i])
        counts[s] += 1
        reps.setdefault(s, ITEMS[i])
    ctx = (tuple(sorted(st["booked"].items())), tuple(sorted(st.get("light", {}).items())))
    kinds = [day_kind(d, st) for d, _ in seq]
    steps = [0]
    n = len(seq)
    cap = [0] * (n + 2)                     # màx. tirades llargues no consecutives encara possibles
    for j in range(n - 1, -1, -1):
        dj, fj = seq[j]
        can = fj is None and kinds[j] == "free" and dj.day in LONG_DAYS
        cap[j] = max(cap[j + 1], (1 + cap[j + 2]) if can else 0)
    long_sigs = [s for s in ALL_SIGS if s[0][3]]

    def rec(i, prev, wl):
        if i == len(seq):
            return all(c == 0 for c in counts.values())
        if sum(counts[s] for s in long_sigs) > cap[i]:
            return False
        key = (seq[i][0].toordinal(), tuple(counts[s] for s in ALL_SIGS), wl, prev, ctx)
        if key in _MEMO:
            return _MEMO[key]
        steps[0] += 1
        if steps[0] > 400000:
            raise TimeoutError
        d, fixed = seq[i]
        res = False
        if fixed is not None:
            f = flags(fixed)
            res = seq_ok(prev, f) and rec(i + 1, (prev + (f,))[-2:], wl)
        else:
            opts = [s for s in ALL_SIGS if counts[s] and allowed(reps[s], d, kinds[i]) and seq_ok(prev, s[0])]
            rng.shuffle(opts)
            if wl > 0 and seq_ok(prev, WILD):
                opts.insert(rng.randrange(len(opts) + 1), "W")
            for s in opts:
                if s == "W":
                    res = rec(i + 1, (prev + (WILD,))[-2:], wl - 1)
                else:
                    counts[s] -= 1
                    res = rec(i + 1, (prev + (s[0],))[-2:], wl)
                    counts[s] += 1
                if res:
                    break
        _MEMO[key] = res
        return res

    try:
        return rec(0, tuple(prev), wild_left)
    except TimeoutError:
        return False


def feasible(st, start, prev, rng):
    return solve(build_seq(st, start), st["pot"], len(st["com"]), prev, st, rng)


def plan_ok(st, today, rng):
    """Comprova que, amb l'estat actual, el que queda de calendari segueix sent viable."""
    start = max(today, START)
    if start.isoformat() in st["hist"]:
        start = date.fromordinal(start.toordinal() + 1)
    return feasible(st, start, hist_prev(st, start), rng)


def draw(st, d, rng, pool=None):
    """Tria el paperet d'avui entre els permesos que no bloquegen els dies següents."""
    kind, prev = day_kind(d, st), hist_prev(st, d)
    cand = [i for i in (pool if pool is not None else st["pot"])
            if allowed(ITEMS[i], d, kind) and seq_ok(prev, flags(ITEMS[i]))]
    rng.shuffle(cand)
    cache, nxt = {}, date.fromordinal(d.toordinal() + 1)
    for i in cand:
        s = sig_of(ITEMS[i])
        if s not in cache:
            st["pot"].remove(i)
            cache[s] = feasible(st, nxt, (prev + (s[0],))[-2:], rng)
            st["pot"].append(i)
        if cache[s]:
            return i, True
    return (cand[0], False) if cand else (0, False)


def assign(st, d, item_id, equiv=False):
    if item_id in st["pot"]:
        st["pot"].remove(item_id)
    st["hist"][d.isoformat()] = {"id": item_id, "equiv": equiv}


def release(st, d):
    """Treu el paperet del dia `d` i el retorna al bombo / als comodins."""
    r = st["hist"].pop(d.isoformat(), None)
    if not r:
        return
    i = r["id"]
    if i == 0:
        return
    if ITEMS[i].get("com"):
        if i not in st["com"]:
            st["com"].append(i)
    elif i not in st["pot"]:
        st["pot"].append(i)


def ensure_day(st, d, rng=random):
    """Assegura que el dia `d` (1-24) té paperet. Retorna (registre, avís)."""
    iso, warn = d.isoformat(), ""
    if iso in st["hist"]:
        return st["hist"][iso], warn
    b = st["booked"].pop(iso, None)
    if b:
        assign(st, d, b)
    elif not st["pot"]:                               # fi de calendari: s'alliberen els comodins
        assign(st, d, st["com"].pop(0), equiv=True)
    else:
        i, ok = draw(st, d, rng)
        if not ok:
            warn = "⚠️ Amb els imprevistos d'aquests dies ja no hi caben totes les tirades llargues; he triat la millor opció possible."
        assign(st, d, i)
    return st["hist"][iso], warn


# ----------------------------------------------------------------------------- missatges
def short(i):
    t = ITEMS[i]["txt"].split(" (")[0]
    return t if len(t) <= 40 else t[:38] + "…"


def logistics(it, kind, equiv=False):
    km = it.get("km")
    if equiv:
        return ("Carrer o camí suau", "Planes") if it["com"] == "ruta" else ("A casa o carrer", "Planes")
    if it.get("com") == "ruta":
        return "Camí de muntanya/sorra (ruta en parella)", "Adidas Trail"
    if it.get("com") == "gym":
        return "Gimnàs", "Esportives"
    if it.get("long"):
        return "Camins de sorra/terra (de dia!)", "Adidas Trail"
    if km is not None:
        if kind == "free":
            return ("Camí fàcil de sorra/terra", "Adidas Trail") if km >= 5 else ("Asfalt o camí fàcil", "Planes")
        if kind == "dusk":
            return "Asfalt o camí fàcil molt proper (aprofita l'última llum)", "Planes"
        return "Asfalt amb carrers il·luminats", "Planes"
    if it.get("walk"):
        return ("Carrers il·luminats" if kind in ("night", "friday") else "Carrer o camí, com vulguis"), "Planes"
    return None, None


def pot_summary(st):
    a = sum(1 for i in st["pot"] if ITEMS[i]["g"] == "A")
    c = [i for i in st["pot"] if ITEMS[i]["g"] == "C"]
    b = sum(1 for i in st["pot"] if ITEMS[i]["g"] == "B") + len(st["com"]) + len(st["booked"])
    ll = sum(1 for i in c if ITEMS[i].get("long"))
    return (f"🎲 Queden al bombo → Descans/mobilitat: {a} · Activitat/comodins: {b} "
            f"(🃏 {len(st['com']) + len(st['booked'])}) · Running: {len(c)} (⭐ {ll})")


def day_message(st, d, warn=""):
    iso = d.isoformat()
    if d > END:
        return f"📅 {d.day} de desembre\n\n" + (RACE_MSG if d == RACE else TAPER[d.day])
    rec = st["hist"][iso]
    it, kind = ITEMS[rec["id"]], day_kind(d, st)
    n = (d - START).days + 1
    head = f"🎄 Dia {n} de 24 · {['dilluns','dimarts','dimecres','dijous','divendres','dissabte','diumenge'][d.weekday()]} {d.day} de desembre\n\n"
    if rec.get("equiv"):
        body = (f"🃏 Comodí no gastat → convertit en equivalència:\n{it['equiv']}.")
    elif it.get("com"):
        body = (f"🃏 {it['txt']}!\n(Si al final no el fas: {it['equiv']}.)")
    else:
        body = ("⭐ TIRADA LLARGA ⭐\n" if it.get("long") else "") + it["txt"] + "."
    terr, shoes = logistics(it, kind, rec.get("equiv"))
    lines = [head + body]
    if terr:
        lines.append(f"📍 Terreny: {terr}\n👟 Sabatilles: {shoes}")
    if kind == "dusk" and it.get("km"):
        lines.append("🌅 Surt a les 17:00 en punt per aprofitar la llum.")
    lines.append(pot_summary(st))
    if warn:
        lines.append(warn)
    return "\n\n".join(lines)


# ----------------------------------------------------------------------------- comandes
def parse_date(s):
    m = re.match(r"^(\d{1,2})(?:[/-](\d{1,2}))?$", s.strip())
    if m:
        try:
            return date(YEAR, int(m[2] or 12), int(m[1]))
        except ValueError:
            return None
    try:
        return date.fromisoformat(s.strip())
    except ValueError:
        return None


def cmd_comodi(st, today, kind_, arg, rng):
    d = parse_date(arg) if arg else max(today, START)
    if not d or not (START <= d <= END):
        return "Dia fora del calendari (1-24 de desembre). Exemple: /ruta 12"
    if d < today:
        return "Aquest dia ja ha passat."
    if kind_ == "ruta" and day_kind(d, st) != "free":
        return "Les rutes en parella només van en cap de setmana o festiu (cal llum de dia). Prova amb /ruta 12 per exemple."
    avail = [i for i in st["com"] if ITEMS[i]["com"] == kind_]
    iso = d.isoformat()
    cur = st["hist"].get(iso)
    if iso in st["booked"] or (cur and ITEMS[cur["id"]].get("com") and not cur.get("equiv")):
        return "Aquest dia ja té un comodí."
    if not avail:
        return "Ja has gastat tots els comodins d'aquest tipus."
    was_ok = plan_ok(st, today, rng)
    snap = json.dumps(st)
    cid = avail[0]
    if cur:
        release(st, d)
    st["com"].remove(cid)
    if d == today:
        assign(st, d, cid)
    else:
        st["booked"][iso] = cid
    ok = plan_ok(st, today, rng) or not was_ok
    if not ok:
        st.clear()
        st.update(json.loads(snap))
        sug = []
        for k in range((END - max(today, START)).days + 1):
            x = date.fromordinal(max(today, START).toordinal() + k)
            if x == d or x.isoformat() in st["booked"] or x.isoformat() in st["hist"] or x < today:
                continue
            if kind_ == "ruta" and day_kind(x, st) != "free":
                continue
            st["booked"][x.isoformat()] = cid
            st["com"].remove(cid)
            good = plan_ok(st, today, rng)
            st["com"].append(cid)
            del st["booked"][x.isoformat()]
            if good:
                sug.append(x)
        tail = ("Dies que sí encaixen: " + ", ".join(f"{x.day}/12" for x in sug[:8]) + "."
                if sug else "Ara mateix no hi ha cap dia que encaixi; fes servir /canvi si cal.")
        return ("Aquest comodí en aquesta data m'obligaria a trencar alguna regla "
                "(p. ex. no deixaria lloc a una tirada llarga). " + tail)
    if d == today:
        return day_message(st, d)
    return f"✅ Comodí reservat per al {d.day}/12. Aquell matí t'ho recordaré."


def cmd_canvi(st, today, rng):
    if not (START <= today <= END):
        return "El calendari només està actiu l'1-24 de desembre."
    rec, _ = ensure_day(st, today, rng)
    it = ITEMS[rec["id"]]
    if it["g"] == "A":
        return "Avui ja toca descans o mobilitat 😌 No cal canviar res."
    if it.get("com") and not rec.get("equiv"):
        return "Avui tens un comodí; ja és un dia flexible. Si no pots, fes-ne l'equivalència: " + it["equiv"] + "."
    release(st, today)
    pool = [i for i in st["pot"] if ITEMS[i]["g"] == "A"]
    i, ok = draw(st, today, rng, pool)
    assign(st, today, i)
    warn = "" if ok else "⚠️ He fet el canvi, però ara costarà encabir totes les tirades llargues; si cal, alguna tirada llarga quedarà sense fer (millor això que forçar el cos)."
    return "🔄 Fet! Avui el repte torna al bombo i et toca una cosa més suau.\n\n" + day_message(st, today, warn)


def cmd_llum(st, today, args, rng):
    if not args or args[0].lower() not in ("si", "sí", "no"):
        return "Ús: /llum si (avui tinc llum de dia) o /llum no (arribo de nit). Opcionalment amb data: /llum no 9"
    d = parse_date(args[1]) if len(args) > 1 else today
    if not d or not (START <= d <= END) or d < today:
        return "Data no vàlida."
    if day_kind(d, {}) == "free":
        return "Aquest dia és festiu o cap de setmana: ja tens llum completa."
    new = "dusk" if args[0].lower() in ("si", "sí") else "night"
    was_ok = plan_ok(st, today, rng)
    old = st["light"].get(d.isoformat())
    st["light"][d.isoformat()] = new
    iso = d.isoformat()
    cur = st["hist"].get(iso)
    if cur and (ITEMS[cur["id"]].get("com") is None or cur.get("equiv")) and \
            not allowed(ITEMS[cur["id"]], d, new) and not cur.get("equiv"):
        release(st, d)
        i, ok = draw(st, d, rng)
        assign(st, d, i)
        return "💡 Entès, canvio el repte d'avui:\n\n" + day_message(st, d)
    if was_ok and not plan_ok(st, today, rng):
        if old:
            st["light"][iso] = old
        else:
            st["light"].pop(iso, None)
        return "Aquest canvi de llum trencaria el pla de tirades llargues. L'he ignorat."
    return f"💡 Anotat: el {d.day}/12 tindràs {'llum de dia' if new == 'dusk' else 'només llum artificial'}."


def cmd_estat(st, today):
    wd = ["dl", "dt", "dc", "dj", "dv", "ds", "dg"]
    done, trail, d = [], 0.0, START
    while d <= min(today, END):
        r = st["hist"].get(d.isoformat())
        if r:
            it = ITEMS[r["id"]]
            mark = "✔" if d < today else "⏳"
            done.append(f"{mark} {d.day}/12 {wd[d.weekday()]}: {short(r['id']) if not r.get('equiv') else 'Equivalència comodí'}")
            if d < today and it.get("km") and logistics(it, day_kind(d, st))[1] == "Adidas Trail":
                trail += it["km"]
        d = date.fromordinal(d.toordinal() + 1)
    pend = sorted(st["pot"], key=lambda i: (ITEMS[i]["g"], ITEMS[i].get("km") or 0))
    com = [short(i) for i in st["com"]] + [f"{short(i)} (reservat {k[8:]}/12)" for k, i in st["booked"].items()]
    return ("📊 ESTAT\n\n" + ("\n".join(done) or "Encara no ha començat.") +
            f"\n\n👟 Km acumulats amb Adidas Trail (dies ja passats): {trail:g} km (objectiu 25-30)"
            f"\n\n🎲 Pendent al bombo ({len(st['pot'])}):\n" + "\n".join("· " + short(i) for i in pend) +
            ("\n\n🃏 Comodins:\n" + "\n".join("· " + c for c in com) if com else "\n\n🃏 Comodins: cap"))


HELP = ("🎄 Calendari d'Advent de Running\n\n/estat · resum i bombo\n/ruta [dia] · comodí de ruta en parella\n"
        "/gimnas [dia] · comodí de gimnàs\n/canvi o /fatiga · canvia el repte d'avui per un descans\n"
        "/llum si|no [dia] · llum de dia (teletreball) o nit (oficina)\n\nEl missatge arriba cada matí a les 7:30.")


def handle(st, text, now, rng=random):
    parts = text.strip().split()
    cmd = parts[0].lower().split("@")[0]
    args, today = parts[1:], now.date()
    if cmd in ("/start", "/ajuda", "/help"):
        return HELP
    if cmd == "/estat":
        return cmd_estat(st, today)
    if cmd in ("/ruta", "/gimnas"):
        return cmd_comodi(st, today, "ruta" if cmd == "/ruta" else "gym", args[0] if args else None, rng)
    if cmd in ("/canvi", "/fatiga"):
        return cmd_canvi(st, today, rng)
    if cmd == "/llum":
        return cmd_llum(st, today, args, rng)
    return None


# ----------------------------------------------------------------------------- Telegram
def tg(method, **params):
    token = os.environ["TELEGRAM_TOKEN"]
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/{method}",
                                 data=urllib.parse.urlencode(params).encode())
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.load(r)


def say(text):
    tg("sendMessage", chat_id=os.environ["TELEGRAM_CHAT_ID"], text=text)


def process_updates(st, now):
    chat = str(os.environ["TELEGRAM_CHAT_ID"])
    for u in tg("getUpdates", offset=st["offset"], timeout=0).get("result", []):
        st["offset"] = u["update_id"] + 1
        m = u.get("message") or {}
        if str(m.get("chat", {}).get("id")) != chat or not m.get("text", "").startswith("/"):
            continue
        reply = handle(st, m["text"], now)
        if reply:
            say(reply)
        save(st)


def tick(st, now):
    d = now.date()
    if not (START <= d <= RACE):
        return
    iso, at = d.isoformat(), (RACE_AT if d == RACE else SEND_AT)
    if st["sent"].get(iso) or (now.hour, now.minute) < at:
        return
    warn = ""
    if d <= END:
        _, warn = ensure_day(st, d)
    say(day_message(st, d, warn))
    st["sent"][iso] = True


def run_once():
    st, now = load(), datetime.now(TZ)
    process_updates(st, now)
    tick(st, now)
    save(st)


# ----------------------------------------------------------------------------- simulació / prova
def simulate_one(seed, joker_prob=0.0):
    rng = random.Random(seed)
    st, rows = new_state(), []
    d = START
    while d <= END:
        if joker_prob and rng.random() < joker_prob and st["com"]:
            kind_ = rng.choice(["ruta", "gym"])
            now = datetime(YEAR, 12, d.day, 7, 30, tzinfo=TZ)
            ensure_day(st, d, rng)
            cmd_comodi(st, d, kind_, None, rng)
        ensure_day(st, d, rng)
        rows.append((d, st["hist"][d.isoformat()]))
        d = date.fromordinal(d.toordinal() + 1)
    return st, rows


def check(rows, st):
    errs, prev = [], ()
    for d, r in rows:
        it = ITEMS[r["id"]]
        f = flags(it, r.get("equiv"))
        if not seq_ok(prev, f):
            errs.append(f"{d}: ruptura de seqüència")
        if not r.get("equiv") and not allowed(it, d, day_kind(d, {})):
            errs.append(f"{d}: {short(r['id'])} no permès en aquest dia")
        prev = (prev + (f,))[-2:]
    return errs


def simulate(n):
    bad = unplaced = 0
    for s in range(n):
        st, rows = simulate_one(s, joker_prob=0.15 if s % 2 else 0.0)
        errs = check(rows, st)
        if st["pot"]:
            unplaced += 1
        if errs:
            bad += 1
            print("seed", s, errs[:3])
    print(f"{n} calendaris · amb errors de regles: {bad} · amb paperets sense col·locar: {unplaced}")


def preview():
    st, rows = simulate_one(random.randrange(10**6))
    for d, r in rows:
        print(f"{d.day:>2}/12 {['dl','dt','dc','dj','dv','ds','dg'][d.weekday()]}  {ITEMS[r['id']]['txt'] if not r.get('equiv') else '[equiv] '+ITEMS[r['id']]['equiv']}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    if cmd == "run":
        run_once()
    elif cmd == "loop":
        while True:
            try:
                run_once()
            except Exception as e:  # noqa
                print("error:", e, file=sys.stderr)
            time.sleep(30)
    elif cmd == "setup":
        tg("setMyCommands", commands=json.dumps([
            {"command": "estat", "description": "Resum i què queda al bombo"},
            {"command": "ruta", "description": "Activa un comodí de ruta en parella"},
            {"command": "gimnas", "description": "Activa el comodí de gimnàs"},
            {"command": "canvi", "description": "Canvia el repte d'avui per un descans"},
            {"command": "fatiga", "description": "Igual que /canvi"},
            {"command": "llum", "description": "/llum si|no: llum de dia o nit avui"}]))
        print("Comandes registrades.")
    elif cmd == "simulate":
        simulate(int(sys.argv[2]) if len(sys.argv) > 2 else 200)
    elif cmd == "preview":
        preview()
    else:
        print(__doc__)
