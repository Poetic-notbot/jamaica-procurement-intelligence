"""
Category Intelligence Engine - Jamaica Procurement OS
18-category taxonomy with rules-based classification and confidence scoring.
Data cleaning helpers for amounts and dates.
"""
from __future__ import annotations
import re, hashlib, logging
from datetime import datetime
from typing import Tuple
logger = logging.getLogger(__name__)

CATEGORY_RULES = {
    "Construction": ["construct","build","erect","civil work","infrastructure","concrete","foundation","structural","renovation","retrofit","rehabilitation","building","fitout","fit-out","fit out"],
    "Roadworks": ["road","highway","asphalt","paving","pavement","drainage","culvert","bridge","pothole","carriageway","kerb","sidewalk","traffic","intersection","roundabout","bus bay"],
    "Medical Supplies": ["medical supply","medical equipment","surgical","diagnostic","laboratory","lab equipment","x-ray","ultrasound","mri","hospital equipment","clinical","patient care","ward","steriliz","autoclave","dental","opthalm"],
    "Pharmaceuticals": ["pharmaceutical","drug","medication","medicine","tablet","capsule","injection","vaccine","dispensary","pharmacy","reagent","chemotherapy","insulin","antibiotic"],
    "Cleaning": ["clean","janitor","janitorial","sanitation","sanitize","hygiene","pest control","fumigat","disinfect","waste collect","housekeep","laundry","linen"],
    "Security": ["security","guard","patrol","surveillance","cctv","alarm","access control","bodyguard","armed","canine","k9"],
    "ICT": ["information technology","software","hardware","computer","network","server","laptop","desktop","printer","scanner","it service","cybersecurity","cloud","database","digital","internet","broadband","fibre","fiber","ict","telecommunication","telecom"],
    "Consulting": ["consult","advisory","feasibility","study","assessment","review","audit service","technical assistance","expert","research","survey","evaluation","project management","management service","strategic plan"],
    "Marketing": ["marketing","advertis","public relation","pr service","media","branding","graphic design","print","publication","campaign","promotion","event management","photography","videograph"],
    "Maintenance": ["maintain","maintenance","repair","overhaul","preventive","corrective","upkeep","restoration","generator service","pump service","lift service","elevator"],
    "HVAC": ["hvac","air condition","aircon","air-condition","refrigerat","chiller","cooling system","ventilation","heat pump"],
    "Electrical": ["electrical","wiring","cable","switchgear","transformer","substation","solar","photovoltaic","generator install","lighting","street light","power supply"],
    "Furniture": ["furniture","chair","desk","cabinet","shelf","locker","cubicle","partition","workstation","sofa"],
    "Waste Management": ["waste management","garbage","solid waste","disposal","recycl","landfill","dumpster","skip bin","refuse","sewage","sewer"],
    "Agriculture": ["agricultur","farm","crop","livestock","irrigation","fertilizer","pesticide","seed","nursery","fishery","aquaculture","veterinary","agro"],
    "Transportation": ["transport","vehicle","bus","truck","van","fleet","ambulance","boat","vessel","ferry","aircraft","fuel supply","tyres","tires","motor vehicle"],
    "Training": ["training","workshop","seminar","capacity build","course","certification","education","staff development"],
    "Catering": ["cater","food supply","meal","canteen","refreshment","beverage","snack","lunch","dinner","breakfast provision"],
}

STRONG_SIGNAL_BOOST = 1.3
BASE_SCORE_PER_MATCH = 0.25
MAX_CONFIDENCE = 0.98

def classify_category(text):
    if not text:
        return ("Uncategorized", 0.0)
    lower = str(text).lower()
    scores = {}
    for category, keywords in CATEGORY_RULES.items():
        score = 0.0
        for kw in keywords:
            if kw in lower:
                boost = STRONG_SIGNAL_BOOST if " " in kw else 1.0
                score += BASE_SCORE_PER_MATCH * boost
        if score > 0:
            scores[category] = min(score, MAX_CONFIDENCE)
    if not scores:
        return ("Uncategorized", 0.0)
    best_cat = max(scores, key=scores.get)
    return (best_cat, round(scores[best_cat], 3))

def clean_amount(raw):
    if raw is None:
        return None
    s = re.sub(r"[^0-9.]", "", str(raw))
    if not s:
        return None
    try:
        val = float(s)
        return val if 0 < val < 1e13 else None
    except ValueError:
        return None

_DATE_FORMATS = ["%d/%m/%Y","%m/%d/%Y","%Y-%m-%d","%d-%m-%Y","%d %b %Y","%d %B %Y","%B %d, %Y","%b %d, %Y","%d/%m/%y","%m/%d/%y"]

def clean_date(raw):
    if not raw:
        return None
    s = str(raw).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None

def make_award_hash(procuring_entity, title, publication_date):
    key = str(procuring_entity or "").lower().strip() + "|" + str(title or "").lower().strip() + "|" + str(publication_date or "").strip()
    return hashlib.md5(key.encode()).hexdigest()

def make_bid_hash(reference_number, cft_title, procuring_entity):
    key = str(reference_number or "").lower().strip() + "|" + str(cft_title or "").lower().strip() + "|" + str(procuring_entity or "").lower().strip()
    return hashlib.md5(key.encode()).hexdigest()

def fmt_jmd(amount):
    if amount is None or amount == 0:
        return "N/A"
    if amount >= 1_000_000_000:
        return "JMD ${:.2f}B".format(amount / 1_000_000_000)
    if amount >= 1_000_000:
        return "JMD ${:.2f}M".format(amount / 1_000_000)
    if amount >= 1_000:
        return "JMD ${:.1f}K".format(amount / 1_000)
    return "JMD ${:,.0f}".format(amount)

CATEGORY_COLORS = {
    "Construction":"#E07B39","Roadworks":"#8B5A2B","Medical Supplies":"#2ECC71",
    "Pharmaceuticals":"#27AE60","Cleaning":"#3498DB","Security":"#E74C3C",
    "ICT":"#9B59B6","Consulting":"#F39C12","Marketing":"#1ABC9C",
    "Maintenance":"#7F8C8D","HVAC":"#16A085","Electrical":"#F1C40F",
    "Furniture":"#D35400","Waste Management":"#95A5A6","Agriculture":"#2980B9",
    "Transportation":"#C0392B","Training":"#8E44AD","Catering":"#E91E63",
    "Uncategorized":"#BDC3C7",
}
CATEGORY_LIST = list(CATEGORY_RULES.keys())
