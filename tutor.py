from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any
import chromadb
import json
import random
import re
import time
import os

# ============ GEMINI CLOUD AI ============
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
gemini_client = None
USE_GEMINI = False
GEMINI_MODEL = "gemini-2.5-flash"

try:
    if GEMINI_KEY:
        from google import genai
        gemini_client = genai.Client(api_key=GEMINI_KEY)
        USE_GEMINI = True
        print("Gemini client initialized")
    else:
        print("GEMINI_API_KEY not set")
except Exception as e:
    print(f"Gemini init failed: {e}")

_ANSWER_CACHE = {}
_CACHE_MAX = 50

# ============ STUDENT DATA ============
STUDENTS: Dict[str, Dict[str, Any]] = {}

def ensure_student(name: str):
    if not name: return None
    if name not in STUDENTS:
        STUDENTS[name] = {
            "name": name, "current_level": 0, "stars": 0, "coins": 100,
            "last_answer": None, "history": [], "last_updated": 0,
            "session_started": time.time(), "inventory": [],
            "equipped": {"body": "🐪", "hat": None, "glasses": None, "shoes": None, "accessory": None, "pet": None},
            "achievements": [], "streak": 0, "boxes_opened": 0,
            "total_coins_earned": 100, "minigame_stats": {},
        }
    return STUDENTS[name]

# ============ ITEMS ============
RARITY_WEIGHTS = {"common": 60, "rare": 25, "epic": 12, "legendary": 2.5, "mythic": 0.5}
RARITY_COLORS = {"common": "#a0a0c0", "rare": "#22c55e", "epic": "#3b82f6", "legendary": "#a855f7", "mythic": "#fbbf24"}

ITEMS = {
    "body_classic":   {"slot": "body", "emoji": "🐪", "name": "جمل كلاسيكي", "rarity": "common", "price": 0},
    "body_robot":     {"slot": "body", "emoji": "🤖", "name": "جمل روبوت", "rarity": "rare", "price": 200},
    "body_ninja":     {"slot": "body", "emoji": "🥷", "name": "جمل نينجا", "rarity": "rare", "price": 250},
    "body_rainbow":   {"slot": "body", "emoji": "🌈", "name": "جمل قوس قزح", "rarity": "epic", "price": 500},
    "body_dragon":    {"slot": "body", "emoji": "🐉", "name": "جمل تنين", "rarity": "legendary", "price": 1200},
    "body_cosmic":    {"slot": "body", "emoji": "🌌", "name": "جمل كوني", "rarity": "mythic", "price": 3000},
    "hat_cap":        {"slot": "hat", "emoji": "🧢", "name": "قبعة", "rarity": "common", "price": 0},
    "hat_chef":       {"slot": "hat", "emoji": "👨‍🍳", "name": "قبعة طباخ", "rarity": "common", "price": 80},
    "hat_pirate":     {"slot": "hat", "emoji": "🏴‍☠️", "name": "قبعة قرصان", "rarity": "rare", "price": 300},
    "hat_wizard":     {"slot": "hat", "emoji": "🧙", "name": "قبعة ساحر", "rarity": "rare", "price": 350},
    "hat_crown":      {"slot": "hat", "emoji": "👑", "name": "تاج", "rarity": "epic", "price": 700},
    "hat_astro":      {"slot": "hat", "emoji": "👨‍🚀", "name": "خوذة فضاء", "rarity": "epic", "price": 800},
    "hat_halo":       {"slot": "hat", "emoji": "😇", "name": "هالة", "rarity": "legendary", "price": 1500},
    "glasses_sun":    {"slot": "glasses", "emoji": "🕶️", "name": "نظارة شمس", "rarity": "common", "price": 60},
    "glasses_3d":     {"slot": "glasses", "emoji": "👓", "name": "نظارة 3D", "rarity": "rare", "price": 250},
    "glasses_star":   {"slot": "glasses", "emoji": "⭐", "name": "نظارة نجوم", "rarity": "epic", "price": 600},
    "shoes_sneakers": {"slot": "shoes", "emoji": "👟", "name": "حذاء رياضي", "rarity": "common", "price": 70},
    "shoes_boots":    {"slot": "shoes", "emoji": "🥾", "name": "أحذية طويلة", "rarity": "rare", "price": 200},
    "shoes_rocket":   {"slot": "shoes", "emoji": "🚀", "name": "أحذية صاروخية", "rarity": "legendary", "price": 1800},
    "acc_scarf":      {"slot": "accessory", "emoji": "🧣", "name": "وشاح", "rarity": "common", "price": 50},
    "acc_cape":       {"slot": "accessory", "emoji": "🦸", "name": "عباءة بطل", "rarity": "rare", "price": 400},
    "acc_wings":      {"slot": "accessory", "emoji": "🪽", "name": "أجنحة", "rarity": "epic", "price": 900},
    "acc_sword":      {"slot": "accessory", "emoji": "⚔️", "name": "سيف", "rarity": "epic", "price": 850},
    "pet_cat":        {"slot": "pet", "emoji": "🐱", "name": "قطة", "rarity": "common", "price": 90},
    "pet_dog":        {"slot": "pet", "emoji": "🐶", "name": "كلب", "rarity": "common", "price": 90},
    "pet_fox":        {"slot": "pet", "emoji": "🦊", "name": "ثعلب", "rarity": "rare", "price": 300},
    "pet_dragon":     {"slot": "pet", "emoji": "🐲", "name": "تنين صغير", "rarity": "epic", "price": 700},
    "pet_phoenix":    {"slot": "pet", "emoji": "🔥", "name": "طائر الفينيق", "rarity": "legendary", "price": 2000},
    "pet_star":       {"slot": "pet", "emoji": "✨", "name": "روح النجوم", "rarity": "mythic", "price": 5000},
}

COIN_TABLE = {0: 0, 1: 2, 2: 5, 3: 10, 4: 15, 5: 20}

def calculate_coins(final_score, seconds_taken=40, streak=0, first_time=False):
    base = COIN_TABLE.get(int(round(final_score)), 0)
    bonus = 0
    if final_score >= 5: bonus += 10
    if seconds_taken <= 5: bonus += 5
    if streak >= 3: bonus += 25
    if first_time: bonus += 50
    return base + bonus

# ============ ACHIEVEMENTS ============
ACHIEVEMENTS = {
    "first_word":     {"name": "أول كلمة فصحى", "icon": "🌟", "condition": "أول إجابة صحيحة"},
    "hundred_coins":  {"name": "100 نقطة", "icon": "🪙", "condition": "اجمع 100 نقطة"},
    "perfect":        {"name": "5 نجوم", "icon": "⭐", "condition": "احصل على 5/5"},
    "first_box":      {"name": "أول صندوق", "icon": "🎁", "condition": "افتح أول صندوق"},
    "ten_perfect":    {"name": "10 إجابات مثالية", "icon": "🏆", "condition": "10 إجابات بدرجة 5"},
    "five_streak":    {"name": "خمس صفقات رابحة", "icon": "🔥", "condition": "5 إجابات صحيحة متتالية"},
    "three_levels":   {"name": "٣ مراحل مكتملة", "icon": "🚀", "condition": "أكمل 3 مراحل"},
    "legendary_item": {"name": "كنز أسطوري", "icon": "💎", "condition": "احصل على عنصر أسطوري"},
    "mythic_item":    {"name": "العنصر الأسطوري", "icon": "🌟", "condition": "احصل على عنصر ميثي"},
    "collector":      {"name": "جامع التحف", "icon": "🎨", "condition": "اجمع 10 عناصر"},
}

def check_achievements(student):
    unlocked = set(student.get("achievements", []))
    new = []
    history = student.get("history", [])
    if len(history) >= 1 and "first_word" not in unlocked: new.append("first_word")
    if student["coins"] >= 100 and "hundred_coins" not in unlocked: new.append("hundred_coins")
    if any(h.get("final_score", 0) >= 5 for h in history) and "perfect" not in unlocked: new.append("perfect")
    if student.get("boxes_opened", 0) >= 1 and "first_box" not in unlocked: new.append("first_box")
    if sum(1 for h in history if h.get("final_score", 0) >= 5) >= 10 and "ten_perfect" not in unlocked: new.append("ten_perfect")
    if student.get("streak", 0) >= 5 and "five_streak" not in unlocked: new.append("five_streak")
    completed_count = len(set(h.get("level", 0) for h in history if h.get("final_score", 0) >= 3))
    if completed_count >= 3 and "three_levels" not in unlocked: new.append("three_levels")
    if any(ITEMS.get(i, {}).get("rarity") == "legendary" for i in student.get("inventory", [])) and "legendary_item" not in unlocked: new.append("legendary_item")
    if any(ITEMS.get(i, {}).get("rarity") == "mythic" for i in student.get("inventory", [])) and "mythic_item" not in unlocked: new.append("mythic_item")
    if len(student.get("inventory", [])) >= 10 and "collector" not in unlocked: new.append("collector")
    for a in new: student["achievements"].append(a)
    return new

# ============ APP + CORS ============
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])

try:
    client = chromadb.PersistentClient(path="./baligh_db")
    col = client.get_or_create_collection("arabic_grammar")
    if col.count() == 0:
        for i, r in enumerate(["الفاعل مرفوع", "المفعول به منصوب"]):
            col.add(documents=[r], ids=["rule_" + str(i)])
        print("Loaded rules")
    else:
        print("Rules already loaded")
except Exception as e:
    print(f"ChromaDB failed: {e}")
    col = None

# ============ UTILS ============
def clean_arabic(text):
    if not text: return ""
    text = re.sub(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af\u0400-\u04ff]", "", text)
    text = re.sub(r"[^\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF0-9\s\.\,\!\?\:\;\(\)\-\n\r\u060C\u061F]", "", text)
    return re.sub(r"\s{2,}", " ", text).strip()

def normalize_arabic(w):
    if not w: return ""
    w = re.sub(r"[\u064B-\u065F\u0670]", "", w)
    w = w.replace("أ","ا").replace("إ","ا").replace("آ","ا").replace("ة","ه").replace("ى","ي").replace("ؤ","و").replace("ئ","ي")
    if w.startswith("ال") and len(w) > 3: w = w[2:]
    for suf in ["ها","هم","هن","كم","كن","نا","ات","ون","ين","ان","ه","ي","ك","ت"]:
        if w.endswith(suf) and len(w) > len(suf) + 2:
            w = w[:-len(suf)]; break
    return w

def levenshtein(a, b):
    if a == b: return 0
    if len(a) < len(b): a, b = b, a
    if len(b) == 0: return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            curr.append(min(curr[j] + 1, prev[j + 1] + 1, prev[j] + (ca != cb)))
        prev = curr
    return prev[-1]

def similarity(a, b):
    if not a or not b: return 0.0
    m = max(len(a), len(b))
    return 1.0 if m == 0 else 1.0 - (levenshtein(a, b) / m)

def simple_match(el, words):
    el_n = normalize_arabic(el)
    if not el_n: return False
    for w in words:
        w_n = normalize_arabic(w)
        if not w_n: continue
        if el_n == w_n: return True
        if len(el_n) >= 3 and len(w_n) >= 3:
            if el_n[:3] == w_n[:3]: return True
            if similarity(el_n, w_n) >= 0.75: return True
        if el_n in w_n or w_n in el_n: return True
    return False

# ============ MODELS ============
class Query(BaseModel): message: str
class StudentUpdate(BaseModel):
    student_name: str = ""; level: int = 0; stars: int = 0; transcript: str = ""
    fusha_score: float = 0; match_score: float = 0; final_score: float = 0
    topic: str = ""; image: str = ""; challenge: str = "describe"
    matched: list = []; missing: list = []; praise: str = ""
    seconds_taken: int = 40; first_time: bool = False
class BuyBoxRequest(BaseModel): student_name: str = ""; box_type: str = "bronze"
class EquipRequest(BaseModel): student_name: str = ""; item_id: str = ""; slot: str = ""
class SceneReq(BaseModel): level: int = 1; avoid: list = []
class SpeakEval(BaseModel):
    image_description: str = ""
    user_transcript: str = ""
    elements: list = []
    topic: str = ""
    challenge: str = "describe"

# ============ HEALTH ============
@app.get("/health")
def health():
    return {"status":"ok","model":GEMINI_MODEL if USE_GEMINI else "fallback","provider":"gemini" if USE_GEMINI else "fallback","cors":"enabled"}

@app.get("/")
def root():
    return {"status": "ok", "service": "Baligh API", "version": "1.0"}

@app.post("/chat")
def chat(q: Query):
    try:
        if USE_GEMINI and gemini_client:
            r = gemini_client.models.generate_content(model=GEMINI_MODEL, contents=q.message)
            return {"reply": clean_arabic(r.text)}
        return {"reply": "Gemini not available"}
    except Exception as e:
        return {"reply": f"Error: {e}"}

# ============ STUDENT ============
@app.post("/student/update")
def student_update(req: StudentUpdate):
    if not req.student_name: return {"ok": False, "error": "no name"}
    student = ensure_student(req.student_name)
    now = time.time()
    student["current_level"] = req.level
    student["stars"] = req.stars
    student["last_updated"] = now
    coins_earned = calculate_coins(req.final_score, req.seconds_taken, student.get("streak", 0), req.first_time)
    student["coins"] += coins_earned
    student["total_coins_earned"] += coins_earned
    if req.final_score >= 4: student["streak"] = student.get("streak", 0) + 1
    else: student["streak"] = 0
    last = {"timestamp": now, "transcript": req.transcript, "fusha_score": req.fusha_score,
            "match_score": req.match_score, "final_score": req.final_score, "topic": req.topic,
            "image": req.image, "challenge": req.challenge, "matched": req.matched,
            "missing": req.missing, "praise": req.praise, "level": req.level, "coins_earned": coins_earned}
    student["last_answer"] = last
    student["history"].append(last)
    if len(student["history"]) > 50: student["history"] = student["history"][-50:]
    new_ach = check_achievements(student)
    return {"ok": True, "coins_earned": coins_earned, "total_coins": student["coins"],
            "streak": student["streak"],
            "new_achievements": [{"id":a, **ACHIEVEMENTS[a]} for a in new_ach]}

@app.get("/student/list")
def student_list():
    now = time.time()
    out = []
    for name, s in STUDENTS.items():
        history = s.get("history", [])
        total = len(history)
        if total > 0:
            af = sum(h["final_score"] for h in history)/total
            au = sum(h["fusha_score"] for h in history)/total
            am = sum(h["match_score"] for h in history)/total
        else: af = au = am = 0
        last_update = s.get("last_updated", 0)
        out.append({"name": name, "current_level": s.get("current_level",0),
            "stars": s.get("stars",0), "coins": s.get("coins",0),
            "total_answers": total, "avg_final": round(af,1), "avg_fusha": round(au,1), "avg_match": round(am,1),
            "is_active": bool(last_update and (now-last_update)<60),
            "seconds_ago": int(now-last_update) if last_update else -1, "last_updated": last_update})
    out.sort(key=lambda x: (not x["is_active"], -x["avg_final"]))
    return {"students": out}

@app.get("/student/details/{name}")
def student_details(name: str):
    if name not in STUDENTS: return {"error": "not found"}
    s = STUDENTS[name]
    history = s.get("history", [])
    total = len(history)
    if total > 0:
        af = sum(h["final_score"] for h in history)/total
        au = sum(h["fusha_score"] for h in history)/total
        am = sum(h["match_score"] for h in history)/total
    else: af = au = am = 0
    weak = {}
    for h in history:
        for m in h.get("missing", []): weak[m] = weak.get(m,0) + 1
    weak_list = [{"word":w,"count":c} for w,c in sorted(weak.items(), key=lambda x:-x[1])[:5]]
    now = time.time()
    last_update = s.get("last_updated", 0)
    return {"name": name, "current_level": s.get("current_level",0), "stars": s.get("stars",0),
        "coins": s.get("coins",0), "inventory": s.get("inventory",[]),
        "equipped": s.get("equipped",{}),
        "achievements": [{"id":a, **ACHIEVEMENTS[a]} for a in s.get("achievements",[]) if a in ACHIEVEMENTS],
        "boxes_opened": s.get("boxes_opened",0), "minigame_stats": s.get("minigame_stats",{}),
        "last_answer": s.get("last_answer"), "history": history[-10:], "weak_areas": weak_list,
        "stats": {"total_answers": total, "avg_fusha": round(au,1), "avg_match": round(am,1), "avg_final": round(af,1)},
        "is_active": bool(last_update and (now-last_update)<60), "last_updated": last_update}

@app.post("/student/reset")
def student_reset():
    STUDENTS.clear()
    return {"ok": True}

# ============ SHOP ============
BOX_TYPES = {
    "bronze": {"price": 100, "guaranteed_rarity": None, "extra": 0},
    "silver": {"price": 300, "guaranteed_rarity": "rare", "extra": 1},
    "gold":   {"price": 800, "guaranteed_rarity": "epic", "extra": 2},
}

def roll_rarity(min_rarity=None):
    rarities = list(RARITY_WEIGHTS.keys())
    weights = list(RARITY_WEIGHTS.values())
    if min_rarity:
        idx = rarities.index(min_rarity)
        for i in range(idx): weights[i] = 0
        total = sum(weights)
        if total == 0: return min_rarity
        weights = [w/total for w in weights]
    else:
        total = sum(weights)
        weights = [w/total for w in weights]
    return random.choices(rarities, weights=weights, k=1)[0]

def pick_random_item(min_rarity=None):
    pool = [i for i,d in ITEMS.items() if min_rarity is None or list(RARITY_WEIGHTS.keys()).index(d["rarity"]) >= list(RARITY_WEIGHTS.keys()).index(min_rarity)]
    return random.choice(pool if pool else list(ITEMS.keys()))

@app.post("/shop/buy")
def shop_buy(req: BuyBoxRequest):
    if req.student_name not in STUDENTS: return {"ok": False, "error": "student not found"}
    if req.box_type not in BOX_TYPES: return {"ok": False, "error": "invalid box"}
    student = STUDENTS[req.student_name]
    box = BOX_TYPES[req.box_type]
    if student["coins"] < box["price"]:
        return {"ok": False, "error": "not enough coins", "needed": box["price"]-student["coins"]}
    student["coins"] -= box["price"]
    student["boxes_opened"] = student.get("boxes_opened",0) + 1
    items_won = []
    if box["guaranteed_rarity"]:
        iid = pick_random_item(box["guaranteed_rarity"]); items_won.append(iid)
        if iid not in student["inventory"]: student["inventory"].append(iid)
    for _ in range(box["extra"]):
        rarity = roll_rarity()
        iid = pick_random_item(rarity); items_won.append(iid)
        if iid not in student["inventory"]: student["inventory"].append(iid)
    if not items_won:
        rarity = roll_rarity()
        iid = pick_random_item(rarity); items_won.append(iid)
        if iid not in student["inventory"]: student["inventory"].append(iid)
    new_ach = check_achievements(student)
    return {"ok": True, "items": [{"id":i, **ITEMS[i]} for i in items_won],
            "coins_left": student["coins"],
            "new_achievements": [{"id":a, **ACHIEVEMENTS[a]} for a in new_ach]}

@app.get("/inventory/{name}")
def get_inventory(name: str):
    if name not in STUDENTS: return {"error": "not found"}
    s = STUDENTS[name]
    return {"coins": s["coins"],
        "inventory": [{"id":i, **ITEMS[i]} for i in s.get("inventory",[]) if i in ITEMS],
        "all_items": [{"id":i, **d, "owned": i in s.get("inventory",[])} for i,d in ITEMS.items()],
        "equipped": s.get("equipped",{})}

@app.post("/inventory/equip")
def equip_item(req: EquipRequest):
    if req.student_name not in STUDENTS: return {"ok": False, "error": "not found"}
    student = STUDENTS[req.student_name]
    if req.item_id not in student["inventory"]: return {"ok": False, "error": "not owned"}
    item = ITEMS.get(req.item_id)
    if not item: return {"ok": False}
    student["equipped"][item["slot"]] = item["emoji"]
    student["equipped"][item["slot"]+"_id"] = req.item_id
    return {"ok": True, "equipped": student["equipped"]}

@app.post("/inventory/unequip")
def unequip_item(req: EquipRequest):
    if req.student_name not in STUDENTS: return {"ok": False}
    student = STUDENTS[req.student_name]
    item = ITEMS.get(req.item_id)
    if not item: return {"ok": False}
    student["equipped"][item["slot"]] = None
    student["equipped"][item["slot"]+"_id"] = None
    return {"ok": True, "equipped": student["equipped"]}

@app.get("/shop/catalog")
def shop_catalog():
    return {"items": [{"id":i, **d} for i,d in ITEMS.items()],
            "boxes": [{"id":k, **v} for k,v in BOX_TYPES.items()],
            "rarity_colors": RARITY_COLORS}

@app.get("/achievements/{name}")
def get_achievements(name: str):
    if name not in STUDENTS: return {"error": "not found"}
    s = STUDENTS[name]
    unlocked = set(s.get("achievements", []))
    return {"achievements": [{"id":a, **d, "unlocked": a in unlocked} for a,d in ACHIEVEMENTS.items()]}

# ============================================================
# ============ SCENES — MATCHING YOUR IMAGES ============
# ============================================================

SCENES = [
    # ===== LEVEL 1 (Easy) — Market, Beach, Zoo, Kitchen =====
    {"id":"market1","img":"images/market1.jpg","topic":"سُوق خُضَار","difficulty":1,"challenge":"describe",
     "elements":["خُضَار","سُوق","بَائِع","أَلْوَان","طَعَام"],
     "camel":"صِفْ مَا تَرَاه فِي السُّوق!"},
    {"id":"market2","img":"images/market2.jpg","topic":"سُوق خُضَار","difficulty":1,"challenge":"describe",
     "elements":["خُضَار","أَلْوَان","طَعَام","سُوق","بَائِع"],
     "camel":"السُّوق مَلِيء بِالأَلْوَان! صِفْ."},
    {"id":"beach1","img":"images/beach1.jpg","topic":"شَاطِئ","difficulty":1,"challenge":"describe",
     "elements":["شَمْس","بَحْر","رَمْل","سَمَاء","مَاء"],
     "camel":"يَوْم مُشْمِس فِي الشَّاطِئ. صِفْ مَا تَرَاه."},
    {"id":"beach2","img":"images/beach2.jpg","topic":"شَاطِئ","difficulty":1,"challenge":"describe",
     "elements":["شَاطِئ","أَشْجَار","شَمْس","بَحْر","سَمَاء"],
     "camel":"شَاطِئ جَمِيل! صِفْ الصُّورَة."},
    {"id":"zoo1","img":"images/zoo1.jpg","topic":"بَانْدَا","difficulty":2,"challenge":"question",
     "question":"مَاذَا يَأْكُل البَانْدَا؟",
     "elements":["بَانْدَا","يَأْكُل","خَيْزَرَان","أَخْضَر"],
     "camel":"هَذَا حَيَوَان البَانْدَا. مَاذَا يَأْكُل؟"},
    {"id":"zoo2","img":"images/zoo2.jpg","topic":"حَيَوَانَات","difficulty":2,"challenge":"describe",
     "elements":["زَرَافَة","حِمَار وَحْشِي","حَيَوَان","طَوِيل","خُطُوط"],
     "camel":"مَا هَذِهِ الحَيَوَانَات؟"},
    {"id":"kitchen1","img":"images/kitchen1.jpg","topic":"مَطْبَخ","difficulty":2,"challenge":"describe",
     "elements":["مَطْبَخ","طَبْخ","طَاهِي","طَعَام","قِدْر"],
     "camel":"شَخْصَان يَطْبُخَان. صِفْ مَا تَرَاه."},
    {"id":"kitchen2","img":"images/kitchen2.jpg","topic":"طَاهِي","difficulty":2,"challenge":"describe",
     "elements":["طَاهِي","يَطْبُخ","مَطْبَخ","طَعَام"],
     "camel":"مَنْ هَذَا الَّذِي يَطْبُخ؟"},

    # ===== LEVEL 3 (Medium) — School, Library, Farm, Bakery =====
    {"id":"school1","img":"images/school1.jpg","topic":"فَصْل","difficulty":3,"challenge":"describe",
     "elements":["فَصْل","طَاوِلَات","كَرَاسِي","سَبُّورَة","هَادِئ"],
     "camel":"فَصْل فَارِغ. صِفْ مَا تَرَاه."},
    {"id":"school2","img":"images/school2.jpg","topic":"مَدْرَسَة","difficulty":3,"challenge":"describe",
     "elements":["كُتُب","أَقْلَام","تُفَّاحَة","مَكْتَب"],
     "camel":"مَاذَا عَلَى المَكْتَب؟"},
    {"id":"library1","img":"images/library1.jpg","topic":"مَكْتَبَة","difficulty":3,"challenge":"describe",
     "elements":["مَكْتَبَة","كُتُب","رُفُوف","قِرَاءَة"],
     "camel":"المَكْتَبَة. صِفْ مَا تَرَاه."},
    {"id":"library2","img":"images/library2.jpg","topic":"مَكْتَبَة","difficulty":3,"challenge":"describe",
     "elements":["كُتُب","مَكْتَبَة","رُفُوف","كَثِير"],
     "camel":"كُتُب كَثِيرَة! صِفْ."},
    {"id":"farm1","img":"images/farm1.jpg","topic":"مَزْرَعَة","difficulty":3,"challenge":"describe",
     "elements":["بَقَرَة","حَقْل","عُشْب","مَزْرَعَة"],
     "camel":"بَقَرَة فِي الحَقْل. صِفْ."},
    {"id":"farm2","img":"images/farm2.jpg","topic":"مَزْرَعَة","difficulty":3,"challenge":"describe",
     "elements":["نَبَاتَات","حَقْل","زَرْع","أَخْضَر"],
     "camel":"نَبَاتَات فِي الحَقْل. صِفْ."},
    {"id":"bakery1","img":"images/bakery1.jpg","topic":"مَخْبَز","difficulty":3,"challenge":"describe",
     "elements":["خُبْز","مَخْبَز","طَعَام","مُخَبَّزَات"],
     "camel":"خُبْز طَازَج! صِفْ."},
    {"id":"bakery2","img":"images/bakery2.jpg","topic":"مَخْبَز","difficulty":3,"challenge":"describe",
     "elements":["خُبْز","أَنْوَاع","مَحَل","مُخَبَّزَات"],
     "camel":"أَنْوَاع الخُبْز. صِفْ."},

    # ===== LEVEL 4 (Harder) — Mosque, Train, Football, Forest =====
    {"id":"mosque1","img":"images/mosque1.jpg","topic":"مَسْجِد","difficulty":4,"challenge":"describe",
     "elements":["مَسْجِد","قُبَّة","مِئْذَنَة","بِنَاء"],
     "camel":"مَسْجِد جَمِيل. صِفْ مَا تَرَاه."},
    {"id":"mosque2","img":"images/mosque2.jpg","topic":"قُرْآن","difficulty":4,"challenge":"describe",
     "elements":["قُرْآن","مُصْحَف","كِتَاب","قِرَاءَة"],
     "camel":"هَذَا القُرْآن الكَرِيم. صِفْ."},
    {"id":"train1","img":"images/train1.jpg","topic":"قِطَار","difficulty":4,"challenge":"describe",
     "elements":["قِطَار","سِكَّة","يَسِير","حَدِيد"],
     "camel":"القِطَار يُسَافِر. صِفْ."},
    {"id":"train2","img":"images/train2.jpg","topic":"قِطَار","difficulty":4,"challenge":"describe",
     "elements":["قِطَار","مَحَطَّة","يَتَوَقَّف","سِكَّة"],
     "camel":"القِطَار يَتَوَقَّف. صِفْ."},
    {"id":"football1","img":"images/football1.jpg","topic":"كُرَة قَدَم","difficulty":4,"challenge":"describe",
     "elements":["كُرَة","مَلْعَب","لَاعِبَان","يَلْعَبُون"],
     "camel":"لَاعِبَان يَلْعَبَان كُرَة القَدَم. صِفْ."},
    {"id":"football2","img":"images/football2.jpg","topic":"كُرَة قَدَم","difficulty":4,"challenge":"describe",
     "elements":["كُرَة","لَاعِب","مَلْعَب","وَحِيد"],
     "camel":"لَاعِب وَاحِد. صِفْ."},
    {"id":"forest1","img":"images/forest1.jpg","topic":"غَابَة","difficulty":4,"challenge":"describe",
     "elements":["غَابَة","أَشْجَار","أَخْضَر","طَبِيعَة"],
     "camel":"الغَابَة. صِفْ مَا تَرَاه."},
    {"id":"forest2","img":"images/forest2.jpg","topic":"غَابَة","difficulty":4,"challenge":"describe",
     "elements":["غَابَة","أَشْجَار","أَوْرَاق","طَبِيعَة"],
     "camel":"الغَابَة الكَبِيرَة. صِفْ."},

    # ===== LEVEL 5 (Advanced) — Park, Sunset, Hospital, Museum =====
    {"id":"park1","img":"images/park1.jpg","topic":"مَلَاهِي","difficulty":5,"challenge":"describe",
     "elements":["أَطْفَال","مَلَاهِي","مَرْجِيحَة","يَلْعَبُون"],
     "camel":"الأَطْفَال يَلْعَبُون فِي المَلَاهِي. صِفْ."},
    {"id":"park2","img":"images/park2.jpg","topic":"قَلْعَة","difficulty":5,"challenge":"describe",
     "elements":["قَلْعَة","بِنَاء","بُرْج","كَبِير"],
     "camel":"هَذِهِ قَلْعَة! صِفْ مَا تَرَاه."},
    {"id":"sunset1","img":"images/sunset1.jpg","topic":"جِبَال وَغُيُوم","difficulty":5,"challenge":"describe",
     "elements":["جِبَال","غُيُوم","سَمَاء","أَلْوَان"],
     "camel":"جِبَال وَغُيُوم. صِفْ."},
    {"id":"sunset2","img":"images/sunset2.jpg","topic":"غُرُوب","difficulty":5,"challenge":"describe",
     "elements":["غُرُوب","بَحْر","شَمْس","مَاء"],
     "camel":"الغُرُوب عَلَى البَحْر. صِفْ."},
    {"id":"hospital1","img":"images/hospital1.jpg","topic":"مُسْتَشْفَى","difficulty":5,"challenge":"describe",
     "elements":["مُسْتَشْفَى","اِسْتِقْبَال","طَبِيب","مَكْتَب"],
     "camel":"اِسْتِقْبَال المُسْتَشْفَى. صِفْ."},
    {"id":"hospital2","img":"images/hospital2.jpg","topic":"مُسْتَشْفَى","difficulty":5,"challenge":"describe",
     "elements":["مُسْتَشْفَى","أَسِرَّة","غُرْفَة","مَرِيض"],
     "camel":"أَسِرَّة المُسْتَشْفَى. صِفْ."},
    {"id":"museum1","img":"images/museum1.jpg","topic":"مَتْحَف","difficulty":5,"challenge":"describe",
     "elements":["مَتْحَف","صُوَر","جِدَار","فَنّ"],
     "camel":"صُوَر عَلَى الحَائِط. صِفْ."},
    {"id":"museum2","img":"images/museum2.jpg","topic":"مَتْحَف","difficulty":5,"challenge":"describe",
     "elements":["مَتْحَف","صُوَر","غُرْفَة","فَنّ"],
     "camel":"غُرْفَة الصُّوَر. صِفْ."},

    # ===== LEVEL 6 (Expert) — Mountain, Rain, Airport, Book Fair =====
    {"id":"mountain1","img":"images/mountain1.jpg","topic":"جَبَل","difficulty":6,"challenge":"describe",
     "elements":["جَبَل","قِمَم","حِجَارَة","سَمَاء"],
     "camel":"الجَبَل مُرْتَفِع. صِفْ."},
    {"id":"rain1","img":"images/rain1.jpg","topic":"مَطَر","difficulty":6,"challenge":"describe",
     "elements":["مَطَر","سَمَاء","غُيُوم","مَاء"],
     "camel":"إِنَّهَا تُمْطِر! صِفْ."},
    {"id":"rain2","img":"images/rain2.jpg","topic":"مَطَر","difficulty":6,"challenge":"describe",
     "elements":["مَطَر","قَطَرَات","مَاء","سَمَاء"],
     "camel":"قَطَرَات المَطَر. صِفْ."},
    {"id":"airport1","img":"images/airport1.jpg","topic":"طَائِرَة","difficulty":6,"challenge":"describe",
     "elements":["طَائِرَة","جَنَاح","سَفَر","سَمَاء"],
     "camel":"جَنَاح الطَّائِرَة. صِفْ."},
    {"id":"airport2","img":"images/airport2.jpg","topic":"طَائِرَة","difficulty":6,"challenge":"describe",
     "elements":["طَائِرَة","مَطَار","سَفَر","كَبِير"],
     "camel":"الطَّائِرَة فِي المَطَار. صِفْ."},
    {"id":"bookfair1","img":"images/bookfair1.jpg","topic":"مَعْرِض كِتَاب","difficulty":6,"challenge":"describe",
     "elements":["كُتُب","مَعْرِض","قِرَاءَة"],
     "camel":"الكُتُب! صِفْ."},
    {"id":"bookfair2","img":"images/bookfair2.jpg","topic":"مَعْرِض كِتَاب","difficulty":6,"challenge":"describe",
     "elements":["كُتُب","مَعْرِض","رُفُوف"],
     "camel":"مَعْرِض الكِتَاب. صِفْ."},
]

def scenes_for_level(lvl):
    d = min(6, max(1, lvl))
    matching = [s for s in SCENES if s["difficulty"] == d]
    return matching if matching else SCENES

@app.post("/speak/scene")
def speak_scene(req: SceneReq):
    pool = scenes_for_level(req.level)
    avail = [s for s in pool if s["id"] not in req.avoid] or pool
    scene = random.choice(avail)
    return {"id":scene["id"],"image":scene["img"],"topic":scene["topic"],
        "elements":scene["elements"],"challenge":scene.get("challenge","describe"),
        "camel":scene.get("camel","صِفْ مَا تَرَاه!"),
        "question":scene.get("question",""),"start":scene.get("start","")}

# ============ EVALUATION ============
def check_match(answer, elements):
    words = re.findall(r"[\u0600-\u06FF]+", answer)
    matched, missing = [], []
    for el in elements:
        (matched if simple_match(el, words) else missing).append(el)
    total = max(1, len(elements)); mc = len(matched)
    if mc == 0: s = 0
    elif mc == total: s = 5
    elif mc >= 3: s = 4
    elif mc >= 2: s = 3
    else: s = 2
    return {"score": s, "matched": matched, "missing": missing, "matched_count": mc, "total": total}

EGYPTIAN = {"مش","مافيش","ايوه","كده","ده","دي","عشان","لسه","دلوقتي","خالص","أوي","قوي","عايز","فين","ايه","بتاع","زي","كمان","حاجة"}
LEVANTINE = {"شو","ليش","بدي","هلق","هيك","هون","منيح","كتير","وين","شلون"}
GULF = {"وين","شلون","شنو","وايد","زين","أبي","ابغى","مو","ايش","وش","كذا","الحين","هسه"}
MAGHREBI = {"بزاف","شحال","فاش","واخا","دابا","كيفاش","علاش","ديال","بغيت","مزيان","واش","غادي"}
DIALECT = EGYPTIAN | LEVANTINE | GULF | MAGHREBI
FOREIGN = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af\u0400-\u04ff\u0041-\u005a\u0061-\u007a]")

def has_foreign(t): return bool(FOREIGN.search(t))

def py_fusha(answer, words, challenge):
    if not words: return 0, "لم تتحدث"
    if has_foreign(answer): return 0, "استخدم لغة أخرى"
    wc = len(words)
    if challenge in ("question","complete"):
        if wc < 1: return 2, "تحدث أكثر"
    else:
        if wc < 2: return 2, "تحدث أكثر"
    dialect = [w for w in words if normalize_arabic(w) in DIALECT or w in DIALECT]
    dc = len(dialect); ratio = dc/wc if wc>0 else 0
    if dc == 0: return None, ""
    if dc >= 2: return 1, "استخدمت العامية"
    if wc <= 4 or ratio >= 0.25: return 2, "استخدمت العامية"
    return 3, "كلمة عامية"

def ai_fusha(answer, topic, challenge):
    cache_key = (answer.strip(), topic, challenge)
    if cache_key in _ANSWER_CACHE: return _ANSWER_CACHE[cache_key]
    if not (USE_GEMINI and gemini_client):
        return 4, "فصحى جيدة"
    sp = "أنت مُصحّح لغة عربية فصحى للأطفال. 1) الفصحى = MSA 2) العامية = خصم 3) كلمات أجنبية = 0 4) التشكيل لا يغير التقييم 5) كن عادلاً للأطفال"
    task = f"قيّم وصف الطفل.\nالموضوع: {topic}\nالوصف: {answer}\n5=غني 4=جيد 3=بسيط 2=مزيج 1=عامية 0=ليست عربية"
    prompt = sp + "\n\n" + task + '\n\nأعد JSON: {"score":4,"comment":"تعليق"}'
    try:
        r = gemini_client.models.generate_content(model=GEMINI_MODEL, contents=prompt,
            config={"temperature":0.1,"max_output_tokens":200,"response_mime_type":"application/json"})
        text = r.text.strip()
        text = re.sub(r"```(?:json)?", "", text).strip()
        s = text.find("{"); e = text.rfind("}") + 1
        data = json.loads(text[s:e])
        score = max(0, min(5, int(data.get("score",4))))
        comment = clean_arabic(str(data.get("comment",""))) or ("فصحى جيدة" if score>=4 else "حاول بالفصحى")
        result = (score, comment)
        if len(_ANSWER_CACHE) >= _CACHE_MAX: _ANSWER_CACHE.pop(next(iter(_ANSWER_CACHE)))
        _ANSWER_CACHE[cache_key] = result
        return result
    except Exception as e:
        print(f"Gemini failed: {e}")
        return 4, "فصحى جيدة"

@app.post("/speak/evaluate")
def speak_evaluate(req: SpeakEval):
    answer = req.user_transcript or ""
    elements = req.elements or []
    topic = req.topic or req.image_description or ""
    challenge = req.challenge or "describe"
    words = re.findall(r"[\u0600-\u06FF]+", answer)
    py_s, py_r = py_fusha(answer, words, challenge)
    if py_s is not None: fs, fc = py_s, py_r
    else: fs, fc = ai_fusha(answer, topic, challenge)
    mr = check_match(answer, elements)
    ms = mr["score"]
    final = round(fs*0.7 + ms*0.3, 1)
    if mr["matched_count"] == 0: mc = "لم تذكر عناصر"
    elif mr["matched_count"] == mr["total"]: mc = "ذكرت كل العناصر! 🌟"
    else: mc = f"ذكرت {mr['matched_count']} من {mr['total']}"
    pct = final/5*100
    if pct>=90: g,gd = 6,"ممتاز! 🌟"
    elif pct>=75: g,gd = 5,"جيد جداً! ⭐"
    elif pct>=60: g,gd = 4,"جيد 👍"
    elif pct>=40: g,gd = 3,"مقبول 📖"
    elif pct>=20: g,gd = 2,"يحتاج تحسين 📝"
    else: g,gd = 1,"واصل 💪"
    if final>=4.5: praise,rec,ov = "رائع! 🏆","استمر!","ممتاز"
    elif final>=3.5:
        praise = "أحسنت! 👏"
        rec = "أضف: " + "، ".join(mr["missing"][:2]) if mr["missing"] else "استمر!"
        ov = "جيد جداً"
    elif final>=2.5: praise,rec,ov = "بداية جيدة 👍","اذكر المزيد","واصل"
    else:
        praise = "لا تستسلم 💪"
        rec = "صف: " + "، ".join(mr["missing"][:3]) if mr["missing"] else "تحدث أكثر"
        ov = "حاول مرة أخرى"
    return {"fusha_score":fs,"match_score":ms,"final_score":final,
        "fusha_comment":fc,"match_comment":mc,"matched":mr["matched"],"missing":mr["missing"],
        "matched_count":mr["matched_count"],"total_elements":mr["total"],
        "grade":g,"grade_desc":gd,"praise":praise,"recommendation":rec,"overall":ov}

@app.on_event("startup")
def warmup():
    print("=" * 50)
    print("CORS: enabled")
    print(f"Gemini: {'ready' if USE_GEMINI else 'fallback mode'}")
    print("Baligh API is starting...")
    print("=" * 50)
