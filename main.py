import os
import json
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import pytz
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from google import genai
from google.genai import types

try:
    from geopy.geocoders import Nominatim
    geolocator = Nominatim(user_agent="vedic_kundali_vercel_v5")
except Exception:
    geolocator = None

try:
    from timezonefinder import TimezoneFinder
    tf = TimezoneFinder()
except Exception:
    tf = None

def get_timezone_name(lat: float, lon: float) -> str:
    # Fast coordinate bounding box for India (IST)
    if 6.0 <= lat <= 37.5 and 68.0 <= lon <= 97.5:
        return "Asia/Kolkata"
    if tf is not None:
        try:
            return tf.timezone_at(lat=lat, lng=lon) or "Asia/Kolkata"
        except Exception:
            pass
    return "Asia/Kolkata"

# Optional Swiss Ephemeris import with pure-python fallback via jyotishganit
try:
    import swisseph as swe
    HAS_SWISSEPH = True
    swe.set_sid_mode(swe.SIDM_LAHIRI, 0, 0)
except ImportError:
    try:
        import pysweph as swe
        HAS_SWISSEPH = True
        swe.set_sid_mode(swe.SIDM_LAHIRI, 0, 0)
    except ImportError:
        swe = None
        HAS_SWISSEPH = False
        try:
            from jyotishganit import calculate_birth_chart
        except ImportError:
            calculate_birth_chart = None

app = FastAPI(title="Astolog — Vedic Kundali & Agentic AI Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

api_key = os.environ.get("GEMINI_API_KEY", "")
ai_client = genai.Client(api_key=api_key) if api_key else None

CHART_STORE: Dict[str, Any] = {}

ZODIAC_SIGNS = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"
]

SIGN_LORDS = {
    1: "Mars", 2: "Venus", 3: "Mercury", 4: "Moon",
    5: "Sun", 6: "Mercury", 7: "Venus", 8: "Mars",
    9: "Jupiter", 10: "Saturn", 11: "Saturn", 12: "Jupiter"
}

EXALTATION_SIGNS = {
    "Sun": 1, "Moon": 2, "Mars": 10, "Mercury": 6,
    "Jupiter": 4, "Venus": 12, "Saturn": 7, "Rahu": 2, "Ketu": 8
}

DEBILITATION_SIGNS = {
    "Sun": 7, "Moon": 8, "Mars": 4, "Mercury": 12,
    "Jupiter": 10, "Venus": 6, "Saturn": 1, "Rahu": 8, "Ketu": 2
}

OWN_SIGNS = {
    "Sun": [5], "Moon": [4], "Mars": [1, 8], "Mercury": [3, 6],
    "Jupiter": [9, 12], "Venus": [2, 7], "Saturn": [10, 11],
    "Rahu": [11], "Ketu": [8]
}

SPECIAL_ASPECTS = {
    "Sun": [7], "Moon": [7], "Mercury": [7], "Venus": [7],
    "Mars": [4, 7, 8], "Jupiter": [5, 7, 9], "Saturn": [3, 7, 10],
    "Rahu": [5, 7, 9], "Ketu": [5, 7, 9]
}

NAKSHATRAS = [
    ("Ashwini", "Ketu"), ("Bharani", "Venus"), ("Krittika", "Sun"),
    ("Rohini", "Moon"), ("Mrigashira", "Mars"), ("Ardra", "Rahu"),
    ("Punarvasu", "Jupiter"), ("Pushya", "Saturn"), ("Ashlesha", "Mercury"),
    ("Magha", "Ketu"), ("Purva Phalguni", "Venus"), ("Uttara Phalguni", "Sun"),
    ("Hasta", "Moon"), ("Chitra", "Mars"), ("Swati", "Rahu"),
    ("Vishakha", "Jupiter"), ("Anuradha", "Saturn"), ("Jyeshtha", "Mercury"),
    ("Mula", "Ketu"), ("Purva Ashadha", "Venus"), ("Uttara Ashadha", "Sun"),
    ("Shravana", "Moon"), ("Dhanishta", "Mars"), ("Shatabhisha", "Rahu"),
    ("Purva Bhadrapada", "Jupiter"), ("Uttara Bhadrapada", "Saturn"), ("Revati", "Mercury")
]

DASHA_YEARS = {
    "Ketu": 7, "Venus": 20, "Sun": 6, "Moon": 10, "Mars": 7,
    "Rahu": 18, "Jupiter": 16, "Saturn": 19, "Mercury": 17
}
DASHA_ORDER = ["Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury"]
DASHA_LEVEL_NAMES = ["Mahadasha", "Antardasha", "Pratyantardasha", "Sookshmadasha", "Prana Dasha", "Deha Dasha"]

COMBUST_ORBS = {
    "Moon": (12.0, 12.0), "Mars": (17.0, 17.0), "Mercury": (14.0, 12.0),
    "Jupiter": (11.0, 11.0), "Venus": (10.0, 8.0), "Saturn": (15.0, 15.0)
}

PLANET_SHORT = {
    "Sun": "Su", "Moon": "Mo", "Mars": "Ma", "Mercury": "Me",
    "Jupiter": "Ju", "Venus": "Ve", "Saturn": "Sa", "Rahu": "Ra", "Ketu": "Ke"
}

if HAS_SWISSEPH:
    SWE_PLANETS = {
        "Sun": swe.SUN, "Moon": swe.MOON, "Mars": swe.MARS,
        "Mercury": swe.MERCURY, "Jupiter": swe.JUPITER,
        "Venus": swe.VENUS, "Saturn": swe.SATURN, "Rahu": swe.MEAN_NODE
    }
else:
    SWE_PLANETS = {}

NATURAL_KARAKAS = {
    "Sun": "Atmakaraka (Soul, Father, Authority, Government, Vitality)",
    "Moon": "Manokaraka (Mind, Mother, Emotions, Public, Peace)",
    "Mars": "Bhratrikaraka (Courage, Younger Siblings, Land, Energy, Surgery)",
    "Mercury": "Vidya & Vanijya Karaka (Intellect, Speech, Business, Accounting)",
    "Jupiter": "Putra & Dhanakaraka (Wisdom, Children, Wealth, Husband, Dharma)",
    "Venus": "Kalatrakaraka (Spouse, Marriage, Luxury, Arts, Vehicles)",
    "Saturn": "Ayush & Karmakaraka (Longevity, Discipline, Service, Masses, Delays)",
    "Rahu": "Pitamaha Karaka (Ambition, Foreign Lands, Innovation, Obsession)",
    "Ketu": "Mokshakaraka (Detachment, Spirituality, Intuition, Liberation)"
}

HUMAN_ARCHETYPES = {
    "Sun": {
        "archetype": "The Sovereign King & Father Figure",
        "human_role": "Represents authority figures, father, bosses, government officials, and your own inner leadership and self-respect.",
        "life_manifestation": "When activated, people in power notice you, responsibilities increase, and your pride or independence is tested."
    },
    "Moon": {
        "archetype": "The Nurturing Mother & Caregiver",
        "human_role": "Represents mother, maternal figures, emotional confidants, home environment, and public receptivity.",
        "life_manifestation": "Brings emotional sensitivity, domestic changes, travel, and deep bonding with caregivers or the public."
    },
    "Mars": {
        "archetype": "The Warrior, Sibling & Engineer",
        "human_role": "Represents brothers, competitors, athletes, police/military, surgeons, and your own fighting spirit.",
        "life_manifestation": "Drives decisive action, property matters, competition, and courage to confront obstacles head-on."
    },
    "Mercury": {
        "archetype": "The Scholar, Merchant & Communicator",
        "human_role": "Represents students, friends, writers, analysts, traders, maternal uncles, and witty advisors.",
        "life_manifestation": "Activates contracts, learning, negotiations, calculations, and problem-solving through intellect."
    },
    "Jupiter": {
        "archetype": "The Guru, Mentor & Wise Counselor",
        "human_role": "Represents teachers, gurus, judges, elders, children, and ethical guides who protect you.",
        "life_manifestation": "Expands wisdom, financial grace, higher learning, family blessings, and dharmic opportunities."
    },
    "Venus": {
        "archetype": "The Partner, Artist & Diplomat",
        "human_role": "Represents spouse/romantic partner, artists, luxury providers, diplomats, and harmonious allies.",
        "life_manifestation": "Highlights relationships, marriage, comforts, creative expression, vehicles, and social grace."
    },
    "Saturn": {
        "archetype": "The Strict Taskmaster, Elder & Worker",
        "human_role": "Represents elderly mentors, laborers, employees, judges of karma, and those who demand accountability.",
        "life_manifestation": "Requires patience, structured hard work, long-term endurance, and realistic restructuring of duties."
    },
    "Rahu": {
        "archetype": "The Foreign Maverick & Strategist",
        "human_role": "Represents unconventional outsiders, foreign contacts, tech disruptors, and ambitious risk-takers.",
        "life_manifestation": "Triggers sudden breakthroughs, foreign connections, intense desires, and breaking traditional boundaries."
    },
    "Ketu": {
        "archetype": "The Mystic Ascetic & Silent Observer",
        "human_role": "Represents spiritual seekers, healers, researchers, and karmic figures from the past who detach you from illusion.",
        "life_manifestation": "Brings sudden closures, spiritual insight, deep research, and release from material attachments."
    }
}

def sanitize_for_json(obj: Any) -> Any:
    """Recursively converts NumPy scalars and non-serializable objects into native Python types."""
    if isinstance(obj, dict):
        return {str(k): sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [sanitize_for_json(x) for x in obj]
    elif hasattr(obj, "item"):
        return obj.item()
    return obj

class BirthInput(BaseModel):
    name: str
    dob: str
    tob: str
    place: str

class DashaExpandRequest(BaseModel):
    parent_lord: str
    start_iso: str
    end_iso: str
    level: int

# Alias for backward compatibility
DashaSublevelsRequest = DashaExpandRequest

class TransitRequest(BaseModel):
    transit_date: str  # YYYY-MM-DD
    transit_time: str  # HH:MM (24-hour IST)
    natal_meta: Optional[dict] = None
    session_id: Optional[str] = None

class AgentQuery(BaseModel):
    question: str
    context_data: Optional[dict] = None
    session_id: Optional[str] = None

def get_nakshatra_info(abs_deg: float):
    abs_deg = abs_deg % 360.0
    nak_span = 360.0 / 27.0
    nak_idx = int(abs_deg // nak_span)
    rem_deg = abs_deg - (nak_idx * nak_span)
    pada = int(rem_deg // (nak_span / 4.0)) + 1
    name, lord = NAKSHATRAS[nak_idx]
    return nak_idx + 1, name, lord, pada

def angular_distance(deg1: float, deg2: float) -> float:
    diff = abs((deg1 % 360.0) - (deg2 % 360.0))
    return min(diff, 360.0 - diff)

def check_combustion(planet_name: str, planet_deg: float, sun_deg: float, is_retro: bool) -> bool:
    if planet_name not in COMBUST_ORBS:
        return False
    direct_orb, retro_orb = COMBUST_ORBS[planet_name]
    orb = retro_orb if is_retro else direct_orb
    return angular_distance(planet_deg, sun_deg) <= orb

def compute_varga_sign(abs_deg: float, varga_num: int) -> int:
    abs_deg = abs_deg % 360.0
    sign_idx = int(abs_deg // 30.0)
    deg_in_sign = abs_deg % 30.0
    part_size = 30.0 / varga_num
    part_idx = int(deg_in_sign // part_size)

    if varga_num == 1: res_idx = sign_idx
    elif varga_num == 2:
        is_odd = (sign_idx % 2 == 0)
        res_idx = (4 if deg_in_sign < 15.0 else 3) if is_odd else (3 if deg_in_sign < 15.0 else 4)
    elif varga_num == 3: res_idx = (sign_idx + part_idx * 4) % 12
    elif varga_num == 4: res_idx = (sign_idx + part_idx * 3) % 12
    elif varga_num == 7:
        start = sign_idx if (sign_idx % 2 == 0) else (sign_idx + 6) % 12
        res_idx = (start + part_idx) % 12
    elif varga_num == 9:
        nav_starts = {0: 0, 1: 9, 2: 6, 3: 3}
        res_idx = (nav_starts[sign_idx % 4] + part_idx) % 12
    elif varga_num == 10:
        start = sign_idx if (sign_idx % 2 == 0) else (sign_idx + 8) % 12
        res_idx = (start + part_idx) % 12
    elif varga_num == 12: res_idx = (sign_idx + part_idx) % 12
    elif varga_num == 16:
        starts = {0: 0, 1: 4, 2: 8}
        res_idx = (starts[sign_idx % 3] + part_idx) % 12
    elif varga_num == 20:
        starts = {0: 0, 1: 8, 2: 4}
        res_idx = (starts[sign_idx % 3] + part_idx) % 12
    elif varga_num == 24:
        start = 4 if (sign_idx % 2 == 0) else 3
        res_idx = (start + part_idx) % 12
    elif varga_num == 27:
        starts = {0: 0, 1: 3, 2: 6, 3: 9}
        res_idx = (starts[sign_idx % 4] + part_idx) % 12
    elif varga_num == 30:
        is_odd = (sign_idx % 2 == 0)
        if is_odd:
            res_idx = 0 if deg_in_sign < 5 else (10 if deg_in_sign < 10 else (8 if deg_in_sign < 18 else (2 if deg_in_sign < 25 else 6)))
        else:
            res_idx = 1 if deg_in_sign < 5 else (5 if deg_in_sign < 12 else (11 if deg_in_sign < 20 else (9 if deg_in_sign < 25 else 7)))
    elif varga_num == 40:
        start = 0 if (sign_idx % 2 == 0) else 6
        res_idx = (start + part_idx) % 12
    elif varga_num == 45:
        starts = {0: 0, 1: 4, 2: 8}
        res_idx = (starts[sign_idx % 3] + part_idx) % 12
    elif varga_num == 60: res_idx = (sign_idx + part_idx) % 12
    else: res_idx = (sign_idx * varga_num + part_idx) % 12
    return res_idx + 1

def calculate_sidereal_snapshot(utc_dt: datetime, lat: float, lon: float) -> dict:
    if HAS_SWISSEPH:
        hour_float = utc_dt.hour + (utc_dt.minute / 60.0) + (utc_dt.second / 3600.0)
        jd_ut = swe.julday(utc_dt.year, utc_dt.month, utc_dt.day, hour_float)
        flags = swe.FLG_SWIEPH | swe.FLG_SIDEREAL | swe.FLG_SPEED

        ayanamsa = swe.get_ayanamsa_ut(jd_ut)
        _, ascmc = swe.houses(jd_ut, lat, lon, b'P')
        asc_abs_deg = (ascmc[0] - ayanamsa) % 360.0
        asc_sign = int(asc_abs_deg // 30.0) + 1

        raw_planets = {}
        for pname, pid in SWE_PLANETS.items():
            res, _ = swe.calc_ut(jd_ut, pid, flags)
            lon_deg = res[0] % 360.0
            speed = res[3]
            is_retro = (speed < 0) if pname != "Rahu" else True
            raw_planets[pname] = {"abs_deg": lon_deg, "is_retro": is_retro}

        ketu_deg = (raw_planets["Rahu"]["abs_deg"] + 180.0) % 360.0
        raw_planets["Ketu"] = {"abs_deg": ketu_deg, "is_retro": True}

        return {"asc_abs_deg": asc_abs_deg, "asc_sign": asc_sign, "raw_planets": raw_planets}
    else:
        # High-precision fallback via jyotishganit / pure Python skyfield
        naive_dt = utc_dt.replace(tzinfo=None)
        chart = calculate_birth_chart(birth_date=naive_dt, latitude=lat, longitude=lon, timezone_offset=0.0)
        h1 = chart.d1_chart.houses[0]
        asc_sign = ZODIAC_SIGNS.index(h1.sign) + 1
        asc_abs_deg = ((asc_sign - 1) * 30.0) + float(getattr(h1, 'sign_degrees', 0.0))

        raw_planets = {}
        for h in chart.d1_chart.houses:
            for p in h.occupants:
                pname = p.celestial_body
                s_idx = ZODIAC_SIGNS.index(p.sign)
                deg = float(getattr(p, 'sign_degrees', 0.0))
                abs_deg = (s_idx * 30.0) + deg
                raw_planets[pname] = {
                    "abs_deg": abs_deg,
                    "is_retro": getattr(p, "motion_type", "") == "retrograde"
                }

        return {
            "asc_abs_deg": asc_abs_deg,
            "asc_sign": asc_sign,
            "raw_planets": raw_planets
        }

def evaluate_planet_dignity(pname: str, sign_num: int, is_combust: bool, is_vargottama: bool, is_retro: bool):
    reasons = []
    score = 0
    if EXALTATION_SIGNS.get(pname) == sign_num:
        score += 3
        reasons.append("Exalted")
    if sign_num in OWN_SIGNS.get(pname, []):
        score += 2
        reasons.append("Own Sign")
    if is_vargottama:
        score += 2
        reasons.append("Vargottama (#)")
    if DEBILITATION_SIGNS.get(pname) == sign_num:
        score -= 3
        reasons.append("Debilitated")
    if is_combust:
        score -= 2
        reasons.append("Combust (^)")
    if is_retro and pname not in ["Rahu", "Ketu"]:
        reasons.append("Retrograde (*)")

    status = "Good" if score > 0 else ("Weak" if score < 0 else "Neutral")
    if not reasons:
        reasons.append("Balanced dignity")
    return status, score, ", ".join(reasons)

def build_planetary_classification(asc_sign: int, d1_planets: List[dict], active_dasha_lords: List[str]) -> List[dict]:
    """
    Computes Parashari classification for each of the 9 Grahas:
    Karaka (Natural + Jaimini Chara), Yogakaraka, Functional Benefic/Malefic, Badhaka, Maraka,
    and 'Planets as per you' human role calibrated to current running Dasha.
    """
    house_to_lord = {}
    lord_to_houses = {p: [] for p in PLANET_SHORT.keys()}
    for h in range(1, 13):
        s_num = ((asc_sign - 1 + (h - 1)) % 12) + 1
        lord = SIGN_LORDS[s_num]
        house_to_lord[h] = lord
        lord_to_houses[lord].append(h)

    lagna_mod = (asc_sign - 1) % 3  # 0=Movable, 1=Fixed, 2=Dual
    badhaka_house = 11 if lagna_mod == 0 else (9 if lagna_mod == 1 else 7)
    badhaka_planet = house_to_lord[badhaka_house]

    maraka_planets = {house_to_lord[2], house_to_lord[7]}

    seven_planets = [p for p in d1_planets if p["planet"] not in ["Rahu", "Ketu"]]
    sorted_by_deg = sorted(seven_planets, key=lambda x: x["degree"], reverse=True)
    chara_names = ["Atmakaraka (AK)", "Amatyakaraka (AmK)", "Bhratrikaraka (BK)", "Matrikaraka (MK)", "Putrakaraka (PK)", "Gnatikaraka (GK)", "Darakaraka (DK)"]
    chara_map = {sorted_by_deg[idx]["planet"]: chara_names[idx] for idx in range(len(sorted_by_deg))}

    planet_lookup = {p["planet"]: p for p in d1_planets}
    classifications = []

    for pname in ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"]:
        pinfo = planet_lookup.get(pname, {})
        owned = lord_to_houses[pname]
        has_kendra = any(h in [1, 4, 7, 10] for h in owned)
        has_trikona = any(h in [1, 5, 9] for h in owned)
        has_dusthana = any(h in [6, 8, 12] for h in owned)

        is_yogakaraka = (has_kendra and has_trikona and pname not in ["Rahu", "Ketu"])
        is_func_benefic = is_yogakaraka or (has_trikona and not has_dusthana) or (pname in ["Jupiter", "Venus"] and not has_dusthana) or (pname == house_to_lord[1])
        is_badhaka = (pname == badhaka_planet)
        is_maraka = (pname in maraka_planets)

        if is_yogakaraka:
            func_status = "Yes (Yogakaraka)"
        elif is_func_benefic:
            func_status = "Yes (Benefic)"
        elif has_dusthana:
            func_status = "Functional Malefic"
        else:
            func_status = "Neutral / Mixed"

        chara_tag = f" | Chara: {chara_map[pname]}" if pname in chara_map else ""
        karaka_desc = f"{NATURAL_KARAKAS[pname]}{chara_tag}"

        dasha_levels_active = []
        level_labels = ["Mahadasha", "Antardasha", "Pratyantardasha", "Sookshmadasha"]
        for idx, d_lord in enumerate(active_dasha_lords[:4]):
            if d_lord == pname:
                dasha_levels_active.append(level_labels[idx])

        dasha_status = f"ACTIVE IN: {', '.join(dasha_levels_active)}" if dasha_levels_active else "Background Influence (Not current MD–SD lord)"
        arch = HUMAN_ARCHETYPES[pname]

        house_str = f"House {pinfo.get('house', '?')} ({pinfo.get('sign_name', '')})"
        nak_str = f"{pinfo.get('nakshatra', '')} (Lord: {pinfo.get('nakshatra_lord', '')})"
        dignity_str = pinfo.get('dignity_reason', 'Normal')

        personalized_note = (
            f"In your chart, {pname} sits in {house_str} in {nak_str} with {dignity_str} dignity. "
            f"{'Because it is currently running in your ' + ', '.join(dasha_levels_active) + ', this human archetype is actively shaping your daily interactions and decisions right now.' if dasha_levels_active else 'It operates through your natal house affairs and awakens whenever transits or sub-dashas connect to it.'}"
        )

        classifications.append({
            "planet": pname,
            "short": pinfo.get("short", pname[:2]),
            "owned_houses": ", ".join([f"H{h}" for h in owned]) if owned else "Nodes (No own sign)",
            "karaka": karaka_desc,
            "yogakaraka": "YES ★" if is_yogakaraka else "No",
            "functional_benefic": func_status,
            "badhaka": f"YES (H{badhaka_house} Lord)" if is_badhaka else "No",
            "maraka": "YES (H2/H7 Lord)" if is_maraka else "No",
            "archetype_title": arch["archetype"],
            "human_role": arch["human_role"],
            "life_manifestation": arch["life_manifestation"],
            "dasha_status": dasha_status,
            "is_dasha_active": len(dasha_levels_active) > 0,
            "personalized_note": personalized_note,
            "house_and_nak": f"{house_str} | {pinfo.get('nakshatra', '')}"
        })

    return classifications

def build_varga_chart_and_insights(
    snapshot: dict,
    varga_num: int,
    d9_signs: Dict[str, int],
    active_dasha_4: List[str],  # [MD, AD, PD, SD]
    transit_signs: Dict[str, int],
    override_asc_sign: int = None
):
    asc_sign = override_asc_sign if override_asc_sign else compute_varga_sign(snapshot["asc_abs_deg"], varga_num)
    sun_abs_deg = snapshot["raw_planets"]["Sun"]["abs_deg"]

    chart_planets = {}
    for pname, pdata in snapshot["raw_planets"].items():
        abs_deg = pdata["abs_deg"]
        v_sign = compute_varga_sign(abs_deg, varga_num)
        house_num = ((v_sign - asc_sign) % 12) + 1
        deg_in_sign = round(abs_deg % 30.0, 2)
        is_retro = pdata["is_retro"]
        is_combust = check_combustion(pname, abs_deg, sun_abs_deg, is_retro)
        is_varg = (compute_varga_sign(abs_deg, 1) == d9_signs.get(pname))
        nak_num, nak_name, nak_lord, pada = get_nakshatra_info(abs_deg)
        dignity_status, dignity_score, dignity_reason = evaluate_planet_dignity(
            pname, v_sign, is_combust, is_varg, is_retro
        )

        chart_planets[pname] = {
            "planet": pname,
            "short": PLANET_SHORT[pname],
            "degree": deg_in_sign,
            "abs_degree": round(abs_deg, 4),
            "sign_num": v_sign,
            "sign_name": ZODIAC_SIGNS[v_sign - 1],
            "house": house_num,
            "house_lord": SIGN_LORDS[v_sign],
            "nakshatra_num": nak_num,
            "nakshatra": f"{nak_name} (P{pada})",
            "nakshatra_lord": nak_lord,
            "is_retrograde": is_retro,
            "is_combust": is_combust,
            "is_vargottama": is_varg,
            "dignity_status": dignity_status,
            "dignity_score": dignity_score,
            "dignity_reason": dignity_reason
        }

    houses_data = {}
    for h in range(1, 13):
        sign_num = ((asc_sign - 1 + (h - 1)) % 12) + 1
        cusp_abs_deg = ((sign_num - 1) * 30.0) + 15.0
        house_nak_num, _, _, _ = get_nakshatra_info(cusp_abs_deg)

        occupants_list = []
        for pname, pinfo in chart_planets.items():
            if pinfo["house"] == h:
                occupants_list.append({
                    "name": pname,
                    "short": pinfo["short"],
                    "deg": f"{int(round(pinfo['degree']))}°",
                    "retro": "*" if pinfo["is_retrograde"] else "",
                    "combust": "^" if pinfo["is_combust"] else "",
                    "vargottama": "#" if pinfo["is_vargottama"] else ""
                })

        houses_data[h] = {
            "house_num": h,
            "sign_num": sign_num,
            "sign_name": ZODIAC_SIGNS[sign_num - 1],
            "house_lord": SIGN_LORDS[sign_num],
            "nak_num": house_nak_num,
            "planets": occupants_list
        }

    trikona_lords = {SIGN_LORDS[((asc_sign - 1 + offset) % 12) + 1] for offset in [0, 4, 8]}
    kendra_lords = {SIGN_LORDS[((asc_sign - 1 + offset) % 12) + 1] for offset in [0, 3, 6, 9]}
    dusthana_lords = {SIGN_LORDS[((asc_sign - 1 + offset) % 12) + 1] for offset in [5, 7, 11]}

    md_lord = active_dasha_4[0] if len(active_dasha_4) > 0 else "Sun"
    ad_lord = active_dasha_4[1] if len(active_dasha_4) > 1 else "Moon"
    pd_lord = active_dasha_4[2] if len(active_dasha_4) > 2 else "Mars"
    sd_lord = active_dasha_4[3] if len(active_dasha_4) > 3 else "Jupiter"

    insights = {}
    for target_house in range(1, 13):
        h_info = houses_data[target_house]
        house_lord = h_info["house_lord"]
        occupants = [p["name"] for p in h_info["planets"]]
        target_sign = h_info["sign_num"]

        aspecting_planets = []
        for pname, pinfo in chart_planets.items():
            from_h = pinfo["house"]
            for asp in SPECIAL_ASPECTS.get(pname, [7]):
                if ((from_h - 1 + asp - 1) % 12) + 1 == target_house:
                    aspecting_planets.append({
                        "planet": pname,
                        "from_house": from_h,
                        "aspect_type": f"{asp}th Aspect",
                        "nakshatra": pinfo["nakshatra"],
                        "nakshatra_lord": pinfo["nakshatra_lord"],
                        "dignity": pinfo["dignity_status"],
                        "reason": pinfo["dignity_reason"]
                    })

        # Occupant details including Nakshatra & Nakshatra Lord
        occupant_details = []
        for occ in occupants:
            oi = chart_planets[occ]
            occupant_details.append(f"{occ} in {oi['nakshatra']} (Nak Lord: {oi['nakshatra_lord']}, {oi['dignity_reason']})")

        involved = list(dict.fromkeys(occupants + [house_lord] + [a["planet"] for a in aspecting_planets]))
        good_planets, weak_planets = [], []
        for pname in involved:
            pinfo = chart_planets[pname]
            roles = []
            if pname in occupants: roles.append("Occupant")
            if pname == house_lord: roles.append("House Lord")
            if any(a["planet"] == pname for a in aspecting_planets): roles.append("Aspecting")
            role_label = "/".join(roles)

            is_func_benefic = (pname in trikona_lords) or (pname in kendra_lords and pname not in dusthana_lords)
            detail_str = f"{pname} ({role_label} | Nak: {pinfo['nakshatra']} -> {pinfo['nakshatra_lord']} | {pinfo['dignity_reason']})"
            if pinfo["dignity_status"] == "Good" or (pinfo["dignity_status"] == "Neutral" and is_func_benefic):
                good_planets.append(detail_str)
            elif pinfo["dignity_status"] == "Weak" or (pname in dusthana_lords and pname not in trikona_lords):
                weak_planets.append(detail_str)
            else:
                good_planets.append(detail_str)

        # --- UNBIASED ALGORITHMIC CALCULATION (Planets + Nakshatras + Live Transits + MD/AD/PD/SD) ---
        net_delta = 0.0

        # 1. House Lord & its Nakshatra Lord
        lord_info = chart_planets[house_lord]
        lord_nak_lord_info = chart_planets.get(lord_info["nakshatra_lord"], lord_info)
        lord_rel = ((lord_info["house"] - target_house) % 12) + 1
        if lord_rel in [1, 4, 5, 7, 9, 10, 11]: net_delta += 5.5
        elif lord_rel in [6, 8, 12]: net_delta -= 6.5
        net_delta += (lord_info["dignity_score"] * 1.8) + (lord_nak_lord_info["dignity_score"] * 1.0)

        # 2. Occupying & Aspecting Planets + their Nakshatra Lords
        for occ in occupants:
            oi = chart_planets[occ]
            nak_l_score = chart_planets.get(oi["nakshatra_lord"], {}).get("dignity_score", 0)
            if occ in trikona_lords or occ in ["Jupiter", "Venus"]:
                net_delta += 4.0 + oi["dignity_score"] + (nak_l_score * 0.5)
            elif occ in dusthana_lords or occ in ["Saturn", "Mars", "Rahu", "Ketu"]:
                net_delta -= 4.0 - oi["dignity_score"] - (nak_l_score * 0.5)

        for asp in aspecting_planets:
            ap = asp["planet"]
            if ap in trikona_lords or ap in ["Jupiter", "Venus"]: net_delta += 3.0
            elif ap in dusthana_lords or ap in ["Saturn", "Mars", "Rahu"]: net_delta -= 3.0

        # 3. 4-Level Active Dasha Synthesis (Mahadasha -> Antardasha -> Pratyantardasha -> Sookshmadasha)
        dasha_weights = [(md_lord, 10.0), (ad_lord, 7.0), (pd_lord, 4.5), (sd_lord, 3.0)]
        dasha_breakdown_notes = []

        for idx, (d_planet, weight) in enumerate(dasha_weights):
            lvl_tag = ["MD", "AD", "PD", "SD"][idx]
            dp = chart_planets.get(d_planet)
            if not dp:
                continue
            dp_nak_lord = dp["nakshatra_lord"]
            dp_transit_sign = transit_signs.get(d_planet, dp["sign_num"])
            dp_transit_house_from_target = ((dp_transit_sign - target_sign) % 12) + 1
            natal_rel_from_target = ((dp["house"] - target_house) % 12) + 1

            step_score = 0.0
            if d_planet == house_lord or natal_rel_from_target in [1, 5, 9, 10, 11]:
                step_score += weight
                relation_desc = f"favorable {natal_rel_from_target}th from House {target_house}"
            elif natal_rel_from_target in [2, 4, 7]:
                step_score += weight * 0.45
                relation_desc = f"supportive {natal_rel_from_target}th from House {target_house}"
            elif natal_rel_from_target in [6, 8, 12]:
                step_score -= weight
                relation_desc = f"challenging {natal_rel_from_target}th (Dusthana) from House {target_house}"
            else:
                relation_desc = f"neutral {natal_rel_from_target}th from House {target_house}"

            # Nakshatra lord modifier
            if dp_nak_lord in chart_planets:
                step_score += chart_planets[dp_nak_lord]["dignity_score"] * 1.2
            # Live transit modifier of this Dasha lord relative to target house
            if dp_transit_house_from_target in [1, 5, 9, 10, 11]:
                step_score += 1.8
            elif dp_transit_house_from_target in [6, 8, 12]:
                step_score -= 1.8

            net_delta += step_score
            dasha_breakdown_notes.append(
                f"{lvl_tag} ({d_planet}): Natal House {dp['house']} ({relation_desc}), Nakshatra {dp['nakshatra']} (Lord: {dp_nak_lord}), currently transiting {ZODIAC_SIGNS[dp_transit_sign - 1]} ({dp_transit_house_from_target}th from H{target_house})."
            )

        # 4. Major Gochar (Transit) Jupiter & Saturn over this house
        transiting_here = [p for p, s in transit_signs.items() if s == target_sign]
        if "Jupiter" in transiting_here: net_delta += 4.5
        if "Saturn" in transiting_here: net_delta -= 3.5

        green_pct = max(8, min(92, int(round(50.0 + net_delta))))
        red_pct = 100 - green_pct

        insights[target_house] = {
            "house_num": target_house,
            "sign_num": h_info["sign_num"],
            "sign_name": h_info["sign_name"],
            "house_lord": house_lord,
            "lord_nakshatra": f"{lord_info['nakshatra']} (Lord: {lord_info['nakshatra_lord']})",
            "occupants": occupants,
            "occupant_details": occupant_details,
            "aspects": aspecting_planets,
            "aspecting_planets": aspecting_planets,
            "good_planets": good_planets,
            "weak_planets": weak_planets,
            "transiting_planets": transiting_here,
            "active_dasha_4": f"{md_lord} MD / {ad_lord} AD / {pd_lord} PD / {sd_lord} SD",
            "dasha_breakdown": dasha_breakdown_notes,
            "green_pct": green_pct,
            "red_pct": red_pct
        }

    return houses_data, list(chart_planets.values()), insights

def compute_sub_dashas(parent_lord: str, parent_start: datetime, parent_end: datetime, target_level: int, clip_start: datetime = None) -> List[dict]:
    total_span = parent_end - parent_start
    start_idx = DASHA_ORDER.index(parent_lord)
    cursor = parent_start
    sub_periods = []
    fmt = "%Y-%m-%d %H:%M:%S" if target_level >= 4 else "%Y-%m-%d"

    for j in range(9):
        sub_lord = DASHA_ORDER[(start_idx + j) % 9]
        fraction = DASHA_YEARS[sub_lord] / 120.0
        sub_end = cursor + (total_span * fraction)

        if clip_start is None or sub_end > clip_start:
            effective_start = max(cursor, clip_start) if clip_start else cursor
            sub_periods.append({
                "level": target_level,
                "level_name": DASHA_LEVEL_NAMES[target_level - 1],
                "lord": sub_lord,
                "start": effective_start.strftime(fmt),
                "end": sub_end.strftime(fmt),
                "start_iso": effective_start.isoformat(),
                "end_iso": sub_end.isoformat(),
                "has_children": target_level < 6
            })
        cursor = sub_end

    return sub_periods

def calculate_vimshottari_dasha(moon_abs_deg: float, birth_dt: datetime) -> List[dict]:
    nak_span = 360.0 / 27.0
    nak_idx = int((moon_abs_deg % 360.0) // nak_span)
    deg_traversed = (moon_abs_deg % 360.0) - (nak_idx * nak_span)
    fraction_remaining = 1.0 - (deg_traversed / nak_span)

    _, start_lord = NAKSHATRAS[nak_idx]
    start_order_idx = DASHA_ORDER.index(start_lord)

    dashas = []
    current_date = birth_dt

    for i in range(9):
        maha_lord = DASHA_ORDER[(start_order_idx + i) % 9]
        total_maha_years = DASHA_YEARS[maha_lord]
        full_duration = timedelta(days=total_maha_years * 365.2425)
        effective_duration = full_duration * fraction_remaining if i == 0 else full_duration
        maha_end = current_date + effective_duration
        theoretical_start = maha_end - full_duration
        antars = compute_sub_dashas(maha_lord, theoretical_start, maha_end, target_level=2, clip_start=current_date)

        dashas.append({
            "level": 1,
            "level_name": "Mahadasha",
            "lord": maha_lord,
            "mahadasha": maha_lord,
            "start": current_date.strftime("%Y-%m-%d"),
            "end": maha_end.strftime("%Y-%m-%d"),
            "start_iso": current_date.isoformat(),
            "end_iso": maha_end.isoformat(),
            "theoretical_start_iso": theoretical_start.isoformat(),
            "has_children": True,
            "antardashas": antars
        })
        current_date = maha_end

    return dashas

def build_active_dasha_chain(mahadashas: List[dict], target_dt: datetime) -> List[dict]:
    target_dt_naive = target_dt.replace(tzinfo=None) if getattr(target_dt, 'tzinfo', None) else target_dt
    chain = []
    current_periods = mahadashas

    for level in range(1, 7):
        active_node = None
        for p in current_periods:
            p_start = datetime.fromisoformat(p["start_iso"])
            p_end = datetime.fromisoformat(p["end_iso"])
            if p_start <= target_dt_naive <= p_end:
                active_node = p
                p["is_active_now"] = True
                break

        if not active_node and current_periods:
            active_node = current_periods[0]
            active_node["is_active_now"] = True

        chain.append({
            "level": level,
            "level_name": DASHA_LEVEL_NAMES[level - 1],
            "active_lord": active_node["lord"],
            "periods": current_periods
        })

        if level == 6:
            break

        if level == 1:
            parent_start = datetime.fromisoformat(active_node["theoretical_start_iso"])
            parent_end = datetime.fromisoformat(active_node["end_iso"])
            clip = datetime.fromisoformat(active_node["start_iso"])
            current_periods = compute_sub_dashas(active_node["lord"], parent_start, parent_end, 2, clip_start=clip)
        else:
            parent_start = datetime.fromisoformat(active_node["start_iso"])
            parent_end = datetime.fromisoformat(active_node["end_iso"])
            current_periods = compute_sub_dashas(active_node["lord"], parent_start, parent_end, level + 1)

    return chain

@app.get("/")
@app.get("/index")
@app.get("/index.html")
@app.get("/index-5")
@app.get("/index-5.html")
def serve_frontend():
    for f in ["index.html", "index-5.html"]:
        if os.path.exists(f):
            return FileResponse(f)
    return FileResponse("index.html")

# Instant zero-network lookup for major Indian cities
INDIA_CITIES = {
    "patna": (25.5941, 85.1376, "Patna, Bihar, India"),
    "new delhi": (28.6139, 77.2090, "New Delhi, Delhi, India"),
    "delhi": (28.7041, 77.1025, "Delhi, India"),
    "mumbai": (19.0760, 72.8777, "Mumbai, Maharashtra, India"),
    "pune": (18.5204, 73.8567, "Pune, Maharashtra, India"),
    "kolkata": (22.5726, 88.3639, "Kolkata, West Bengal, India"),
    "bengaluru": (12.9716, 77.5946, "Bengaluru, Karnataka, India"),
    "bangalore": (12.9716, 77.5946, "Bengaluru, Karnataka, India"),
    "chennai": (13.0827, 80.2707, "Chennai, Tamil Nadu, India"),
    "hyderabad": (17.3850, 78.4867, "Hyderabad, Telangana, India"),
    "guwahati": (26.1445, 91.7362, "Guwahati, Assam, India"),
    "silchar": (24.8333, 92.7789, "Silchar, Assam, India"),
    "varanasi": (25.3176, 82.9739, "Varanasi, Uttar Pradesh, India"),
    "lucknow": (26.8467, 80.9462, "Lucknow, Uttar Pradesh, India"),
    "jaipur": (26.9124, 75.7873, "Jaipur, Rajasthan, India"),
    "ahmedabad": (23.0225, 72.5714, "Ahmedabad, Gujarat, India"),
    "ranchi": (23.3441, 85.3096, "Ranchi, Jharkhand, India"),
    "bhopal": (23.2599, 77.4126, "Bhopal, Madhya Pradesh, India"),
    "chandigarh": (30.7333, 76.7794, "Chandigarh, India"),
    "bhubaneswar": (20.2961, 85.8245, "Bhubaneswar, Odisha, India"),
}

def resolve_place_coordinates(place_str: str):
    cleaned = place_str.strip().lower()
    city_key = cleaned.split(",")[0].strip()
    if city_key in INDIA_CITIES:
        return INDIA_CITIES[city_key]

    # Fallback 1: Open-Meteo Geocoding API (Fast, free, never blocks Vercel/AWS IPs)
    try:
        q = urllib.parse.quote(city_key)
        url = f"https://geocoding-api.open-meteo.com/v1/search?name={q}&count=1&language=en&format=json"
        req = urllib.request.Request(url, headers={"User-Agent": "AstologApp/1.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            if payload.get("results"):
                r = payload["results"][0]
                full_name = f"{r.get('name')}, {r.get('admin1', '')}, {r.get('country', '')}".replace(", ,", ",")
                return float(r["latitude"]), float(r["longitude"]), full_name
    except Exception:
        pass

    # Fallback 2: Geopy Nominatim
    if geolocator is not None:
        try:
            loc = geolocator.geocode(place_str, timeout=6)
            if loc:
                return loc.latitude, loc.longitude, loc.address
        except Exception:
            pass

    return None

@app.post("/api/kundali")
@app.post("/kundali")
def generate_kundali(data: BirthInput):
    try:
        coords = resolve_place_coordinates(data.place)
        if not coords:
            raise HTTPException(status_code=400, detail=f"Could not resolve coordinates for '{data.place}'.")
        lat, lon, resolved_address = coords
        tz_name = get_timezone_name(lat, lon)
        local_tz = pytz.timezone(tz_name)

        naive_dt = datetime.strptime(f"{data.dob} {data.tob}", "%Y-%m-%d %H:%M")
        local_dt = local_tz.localize(naive_dt)
        utc_dt = local_dt.astimezone(pytz.utc)

        natal_snap = calculate_sidereal_snapshot(utc_dt, lat, lon)
        moon_abs_deg = natal_snap["raw_planets"]["Moon"]["abs_deg"]
        natal_moon_sign = int(moon_abs_deg // 30.0) + 1
        _, moon_nak_name, _, moon_pada = get_nakshatra_info(moon_abs_deg)

        dasha_timeline = calculate_vimshottari_dasha(moon_abs_deg, naive_dt)
        now_local = datetime.now(local_tz).replace(tzinfo=None)
        active_dasha_chain = build_active_dasha_chain(dasha_timeline, now_local)

        # Extract active MD, AD, PD, SD lords (up to Sookshma Dasha)
        active_dasha_4 = [c["active_lord"] for c in active_dasha_chain[:4]]

        now_utc = datetime.now(pytz.utc)
        delhi_snap = calculate_sidereal_snapshot(now_utc, 28.6139, 77.2090)
        transit_signs = {p: int(info["abs_deg"] // 30.0) + 1 for p, info in delhi_snap["raw_planets"].items()}

        d9_signs = {p: compute_varga_sign(info["abs_deg"], 9) for p, info in natal_snap["raw_planets"].items()}

        varga_list = [1, 9, 2, 3, 4, 7, 10, 12, 16, 20, 24, 27, 30, 40, 45, 60]
        all_vargas, all_chart_insights, d1_planet_table = {}, {}, []

        for v in varga_list:
            key = f"D{v}"
            v_chart, v_planets, v_insights = build_varga_chart_and_insights(
                natal_snap, v, d9_signs, active_dasha_4, transit_signs
            )
            all_vargas[key] = v_chart
            all_chart_insights[key] = v_insights
            if v == 1:
                d1_planet_table = v_planets

        d1_asc_sign = natal_snap["asc_sign"]
        planet_classifications = build_planetary_classification(d1_asc_sign, d1_planet_table, active_dasha_4)

        delhi_transit_chart, delhi_transit_table, delhi_transit_insights = build_varga_chart_and_insights(
            delhi_snap, 1, d9_signs, active_dasha_4, transit_signs
        )
        asc_transit_chart, _, asc_transit_insights = build_varga_chart_and_insights(
            delhi_snap, 1, d9_signs, active_dasha_4, transit_signs, override_asc_sign=d1_asc_sign
        )
        moon_transit_chart, _, moon_transit_insights = build_varga_chart_and_insights(
            delhi_snap, 1, d9_signs, active_dasha_4, transit_signs, override_asc_sign=natal_moon_sign
        )

        all_chart_insights["TRANSIT_DELHI"] = delhi_transit_insights
        all_chart_insights["TRANSIT_ASC"] = asc_transit_insights
        all_chart_insights["TRANSIT_MOON"] = moon_transit_insights

        ist_tz = pytz.timezone("Asia/Kolkata")
        now_ist = datetime.now(ist_tz)

        sookshma_summary = f"{active_dasha_4[0]} MD / {active_dasha_4[1]} AD / {active_dasha_4[2]} PD / {active_dasha_4[3]} SD"

        payload = {
            "profile": {
                "name": data.name,
                "dob": data.dob,
                "tob": data.tob,
                "place": resolved_address,
                "timezone": tz_name,
                "ascendant": f"{ZODIAC_SIGNS[d1_asc_sign - 1]} (Lord: {SIGN_LORDS[d1_asc_sign]})",
                "moon_sign": f"{ZODIAC_SIGNS[natal_moon_sign - 1]} (Lord: {SIGN_LORDS[natal_moon_sign]}) — {moon_nak_name} P{moon_pada}",
                "running_dasha": sookshma_summary,
                "current_dasha": sookshma_summary
            },
            "charts": all_vargas,
            "chart_insights": all_chart_insights,
            "house_insights": all_chart_insights.get("D1", {}),
            "planet_table": d1_planet_table,
            "planet_classifications": planet_classifications,
            "planets_page": {"table": planet_classifications},
            "transit": {
                "timestamp": now_ist.strftime("%Y-%m-%d %H:%M IST"),
                "delhi_asc": f"{ZODIAC_SIGNS[delhi_snap['asc_sign'] - 1]} (New Delhi Lagna)",
                "delhi_chart": delhi_transit_chart,
                "chart": asc_transit_chart,
                "asc_chart": asc_transit_chart,
                "moon_chart": moon_transit_chart,
                "moon_transit_chart": moon_transit_chart,
                "table": delhi_transit_table
            },
            "dasha": dasha_timeline,
            "active_dasha_chain": active_dasha_chain,
            "dasha_chain": active_dasha_chain
        }

        payload["natal_meta"] = {
            "d1_asc_sign": d1_asc_sign,
            "natal_moon_sign": natal_moon_sign,
            "d9_signs": d9_signs,
            "active_dasha_4": active_dasha_4
        }

        CHART_STORE[data.name.lower()] = payload
        return payload
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {str(e)} | {traceback.format_exc().splitlines()[-1]}")

@app.post("/api/dasha-sublevels")
@app.post("/dasha-sublevels")
def expand_dasha_level(req: DashaExpandRequest):
    if req.level < 1 or req.level >= 6:
        raise HTTPException(status_code=400, detail="Deha Dasha (Level 6) is the deepest level.")
    start_dt = datetime.fromisoformat(req.start_iso)
    end_dt = datetime.fromisoformat(req.end_iso)
    next_level = req.level + 1
    children = compute_sub_dashas(req.parent_lord, start_dt, end_dt, next_level)

    now_dt = datetime.now()
    for p in children:
        p_start = datetime.fromisoformat(p["start_iso"])
        p_end = datetime.fromisoformat(p["end_iso"])
        if p_start <= now_dt <= p_end:
            p["is_active_now"] = True
            break

    return {"level": next_level, "level_name": DASHA_LEVEL_NAMES[next_level - 1], "periods": children}

@app.post("/api/transit")
@app.post("/transit")
def calculate_custom_transit(req: TransitRequest):
    meta = req.natal_meta
    if not meta and req.session_id:
        stored = CHART_STORE.get(req.session_id.lower(), {})
        meta = stored.get("natal_meta")

    if not meta:
        raise HTTPException(
            status_code=400,
            detail="Missing natal metadata. Please generate Kundali first."
        )

    try:
        naive_target = datetime.strptime(f"{req.transit_date} {req.transit_time}", "%Y-%m-%d %H:%M")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date or time format. Expected YYYY-MM-DD and HH:MM.")

    ist_tz = pytz.timezone("Asia/Kolkata")
    ist_target = ist_tz.localize(naive_target)
    utc_target = ist_target.astimezone(pytz.utc)

    delhi_snap = calculate_sidereal_snapshot(utc_target, 28.6139, 77.2090)
    transit_signs = {p: int(info["abs_deg"] // 30.0) + 1 for p, info in delhi_snap["raw_planets"].items()}

    delhi_chart, delhi_table, delhi_insights = build_varga_chart_and_insights(
        delhi_snap, 1, meta.get("d9_signs", {}), meta.get("active_dasha_4", ["Sun", "Moon", "Mars", "Jupiter"]), transit_signs
    )
    asc_chart, _, asc_insights = build_varga_chart_and_insights(
        delhi_snap, 1, meta.get("d9_signs", {}), meta.get("active_dasha_4", ["Sun", "Moon", "Mars", "Jupiter"]), transit_signs,
        override_asc_sign=meta.get("d1_asc_sign", 1)
    )
    moon_chart, _, moon_insights = build_varga_chart_and_insights(
        delhi_snap, 1, meta.get("d9_signs", {}), meta.get("active_dasha_4", ["Sun", "Moon", "Mars", "Jupiter"]), transit_signs,
        override_asc_sign=meta.get("natal_moon_sign", 1)
    )

    return {
        "timestamp": ist_target.strftime("%Y-%m-%d %H:%M IST"),
        "delhi_asc": f"{ZODIAC_SIGNS[delhi_snap['asc_sign'] - 1]} (New Delhi Lagna)",
        "delhi_chart": delhi_chart,
        "chart": asc_chart,
        "asc_chart": asc_chart,
        "moon_chart": moon_chart,
        "moon_transit_chart": moon_chart,
        "insights": {
            "TRANSIT_DELHI": delhi_insights,
            "TRANSIT_ASC": asc_insights,
            "TRANSIT_MOON": moon_insights
        },
        "table": delhi_table
    }

@app.post("/api/ask-astrologer")
@app.post("/ask-astrologer")
def ask_agentic_astrologer(req: AgentQuery):
    stored = req.context_data
    if not stored and req.session_id:
        stored = CHART_STORE.get(req.session_id.lower())

    if not stored:
        raise HTTPException(status_code=400, detail="Please generate the Kundali first.")

    def inspect_chart_house(chart_name: str, house_number: int) -> dict:
        house_dict = stored.get("chart_insights", {}).get(chart_name.upper(), {})
        data = house_dict.get(str(house_number)) or house_dict.get(int(house_number), {})
        return sanitize_for_json(data)

    def get_planets_and_dasha() -> dict:
        return sanitize_for_json({
            "profile": stored.get("profile", {}),
            "classifications": stored.get("planet_classifications", [])
        })

    client = ai_client
    if client is None:
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise HTTPException(
                status_code=500,
                detail="GEMINI_API_KEY environment variable is not configured."
            )
        client = genai.Client(api_key=key)

    models_to_try = [
        os.environ.get("GEMINI_MODEL"),
        "gemini-2.5-flash",
        "gemini-1.5-flash",
        "gemini-2.0-flash",
        "gemini-3.5-flash",
        "gemini-3.8-flash"
    ]
    seen = set()
    candidate_models = [m for m in models_to_try if m and not (m in seen or seen.add(m))]

    system_instruction = (
        "You are an expert Parashari Vedic Astrologer. "
        "Always check Nakshatras, live transits, Sookshma Dasha, and Yogakaraka/Badhaka/Maraka roles before answering."
    )

    last_error = None
    for model_name in candidate_models:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=req.question,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    tools=[inspect_chart_house, get_planets_and_dasha],
                    temperature=0.3,
                ),
            )
            return {"analysis": response.text}
        except Exception as e:
            last_error = e
            continue

    raise HTTPException(status_code=500, detail=f"AI Astrologer model error: {str(last_error)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
