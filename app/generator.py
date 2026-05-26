import asyncio
from datetime import datetime
import json
import logging
import os
import random
import re
import time
from typing import List, Dict, Any, Optional

import httpx
from app.config import settings
from app.cache import cache

logger = logging.getLogger("generator")

# ── Constants ───────────────────────────────────────────────────
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = "meta-llama/llama-3.3-70b-instruct"
DEFAULT_INSUFFICIENT_INFO_MSG = "I don't have enough information to answer this."

# ── Trust Tiers Inside "Web" ─────────────────────────────────────
OFFICIAL_IIT_SITE = 1.0
PLACEMENT_REPORT = 0.95
FACULTY_PROFILE = 0.9
NEWS = 0.7
BLOG = 0.4
QUORA = 0.2
LLM_PRIOR = 0.3

# ── Aspect Classification & Decomposition Helpers ────────────────
NORMALIZATION_MAP = {
    "electrical": "ee",
    "computer science": "cse",
    "mechanical": "me"
}

def normalize_entity_category(entity: str, category: str) -> tuple[str, str]:
    """
    Normalizes the entity and category to resolve synonyms to the same cache namespace.
    """
    ent_lower = entity.lower().strip()
    
    # Check normalization map and synonyms
    if any(x in ent_lower for x in ["electrical", "ee"]):
        entity_norm = "IIT Mandi EE"
    elif any(x in ent_lower for x in ["computer science", "cse"]):
        entity_norm = "IIT Mandi CSE"
    elif any(x in ent_lower for x in ["mechanical", "me"]):
        entity_norm = "IIT Mandi ME"
    elif any(x in ent_lower for x in ["civil", "ce"]):
        entity_norm = "IIT Mandi CE"
    elif any(x in ent_lower for x in ["data science", "ds"]):
        entity_norm = "IIT Mandi DS"
    elif any(x in ent_lower for x in ["general", "ge"]):
        entity_norm = "IIT Mandi GE"
    else:
        entity_norm = "IIT Mandi"
        
    cat_lower = category.lower().strip()
    if any(x in cat_lower for x in ["placement", "salary", "package", "ctc", "lpa"]):
        category_norm = "placements"
    elif any(x in cat_lower for x in ["cutoff", "rank", "closing", "opening", "josaa"]):
        category_norm = "cutoffs"
    elif any(x in cat_lower for x in ["curriculum", "syllabus", "rigor", "credits"]):
        category_norm = "curriculum"
    elif any(x in cat_lower for x in ["research", "faculty", "labs"]):
        category_norm = "research"
    elif any(x in cat_lower for x in ["software", "transition", "job", "career"]):
        category_norm = "software_transition"
    elif any(x in cat_lower for x in ["campus", "life", "hostel", "mess"]):
        category_norm = "campus_life"
    else:
        category_norm = "general"
        
    return entity_norm, category_norm


def decompose_query(query: str) -> List[Dict[str, str]]:
    """
    Decomposes a user query into aspect-based subqueries.
    Uses robust regex/caching rules, and falls back to a fast LLM prompt when needed.
    """
    query_lower = query.lower().strip()
    
    # Extract branches using strict word boundaries to prevent false positives
    branches = []
    if re.search(r"\b(ee|electrical)\b", query_lower):
        branches.append("EE")
    if re.search(r"\b(cse|computer science|computer)\b", query_lower):
        branches.append("CSE")
        
    # Match ME case-sensitively or using mech/mechanical (exclude lowercase 'me' word)
    if "mechanical" in query_lower or "mech" in query_lower or re.search(r"\bME\b", query):
        branches.append("ME")
        
    if re.search(r"\bce\b|\bcivil\b", query_lower):
        branches.append("CE")
    if re.search(r"\bds\b|\bdata science\b", query_lower):
        branches.append("DS")
        
    # Deduplicate branches
    branches = list(dict.fromkeys(branches))
    
    if branches:
        sub_queries = []
        for branch in branches:
            sub_queries.extend([
                {
                    "aspect": "placements",
                    "query": f"IIT Mandi {branch} placements"
                },
                {
                    "aspect": "curriculum",
                    "query": f"IIT Mandi {branch} curriculum rigor"
                },
                {
                    "aspect": "research",
                    "query": f"IIT Mandi {branch} research areas"
                },
                {
                    "aspect": "software_transition",
                    "query": f"IIT Mandi {branch} software opportunities"
                }
            ])
        # Cap to max 4 subqueries and deduplicate
        deduped = []
        seen = set()
        for sq in sub_queries:
            sq_key = (sq["aspect"], sq["query"])
            if sq_key not in seen:
                seen.add(sq_key)
                deduped.append(sq)
        return deduped[:4]

    # For non-branch specific or complex queries, use LLM or fallback
    fallback = [
        {"aspect": "placements", "query": "IIT Mandi placements average package"},
        {"aspect": "cutoffs", "query": "IIT Mandi JoSAA cutoff ranks"},
        {"aspect": "curriculum", "query": "IIT Mandi academic curriculum rigor"},
        {"aspect": "research", "query": "IIT Mandi faculty research developments"}
    ]
    
    try:
        if "generator" in globals() and generator is not None:
            prompt = f"""Decompose the user query into 3-5 specific aspect-based subqueries to retrieve precise information.
User Query: "{query}"

Each subquery must focus on a distinct aspect (e.g. placements, curriculum, research, cutoffs, software_transition, campus_life, general).
Return the subqueries STRICTLY as a raw JSON list of objects, each with "aspect" and "query" keys. Do not output any prose or markdown backticks:
[
  {{"aspect": "placements", "query": "IIT Mandi EE placements"}}
]
"""
            messages = [
                {"role": "system", "content": "You are a precise query decomposer. Output JSON only."},
                {"role": "user", "content": prompt}
            ]
            response = generator._call_llm(messages)
            if response:
                parsed = parse_json_array(response)
                if parsed and isinstance(parsed, list):
                    # Deduplicate and cap to 4
                    seen = set()
                    deduped = []
                    for item in parsed:
                        if isinstance(item, dict) and "aspect" in item and "query" in item:
                            key = (item["aspect"], item["query"])
                            if key not in seen:
                                seen.add(key)
                                deduped.append(item)
                    return deduped[:4]
    except Exception as e:
        logger.warning("LLM query decomposition failed: %s. Using deterministic fallback.", e)
        
    return fallback[:4]


def classify_query(query: str) -> str:
    """Classifies the query into a distinct category for specialized fusion policies."""
    q_lower = query.lower()
    if any(w in q_lower for w in ["vs", "compare", "difference between", "better than"]):
        return "branch_comparison"
    if any(w in q_lower for w in ["placement", "salary", "package", "ctc", "lpa", "placed", "job", "career"]):
        return "placement_info"
    if any(w in q_lower for w in ["cutoff", "rank", "closing", "opening", "josaa", "seat", "admissions"]):
        return "cutoff_info"
    if any(w in q_lower for w in ["curriculum", "syllabus", "rigor", "math", "course", "credits", "study"]):
        return "curriculum_info"
    if any(w in q_lower for w in ["research", "projects", "faculty", "labs", "developments", "latest"]):
        return "research_and_news"
    if any(w in q_lower for w in ["higher studies", "m.tech", "phd", "research output"]):
        return "higher_studies"
    if any(w in q_lower for w in ["decide", "choose", "interest vs placement", "tradeoff"]):
        return "placement_vs_interest_tradeoff"
    if any(w in q_lower for w in ["campus", "life", "hostel", "mess", "clubs", "sports"]):
        return "campus_life"
    return "general"


def classify_query_rich(query: str) -> dict:
    """
    Enhanced query classifier returning type, entities, web/rerank/decomposition needs,
    and priority markdown categories for metadata boosting.
    """
    q_lower = query.lower()
    
    # 1. Detect branches / entities
    entities = []
    branch_map = {
        "cse": ["cse", "computer science", "cs"],
        "ee": ["ee", "electrical", "electronics"],
        "me": ["me", "mechanical", "mechanics"],
        "ce": ["ce", "civil"],
        "ep": ["ep", "physics", "engineering physics"],
        "dse": ["dse", "data science"],
        "mnc": ["mnc", "math", "mathematics"]
    }
    
    for branch, keywords in branch_map.items():
        if any(kw in q_lower for kw in keywords):
            entities.append(f"IIT Mandi {branch.upper()}")
            
    # 2. Categorize query type
    query_type = "general"
    priority_categories = []
    
    has_placement = any(w in q_lower for w in ["placement", "salary", "package", "ctc", "lpa", "placed", "job", "career", "recruit", "employer"])
    has_cutoff = any(w in q_lower for w in ["cutoff", "rank", "closing", "opening", "seat", "admissions", "cutoff", "cut-off"])
    has_comparison = any(w in q_lower for w in ["vs", "compare", "difference between", "better than", "or", "versus"])
    has_software_transition = any(w in q_lower for w in ["software", "coding", "programming", "swe", "sde", "it job", "it sector"]) and any(b in q_lower for b in ["civil", "mechanical", "chemical", "core", "ee", "electrical", "electronics", "ce", "me"])
    has_latest = any(w in q_lower for w in ["latest", "current", "recent", "2025", "2026", "new", "this year", "updated"])
    has_josaa = any(w in q_lower for w in ["josaa", "counselling", "counseling", "process", "round", "choice filling", "allocation"])
    has_fee = any(w in q_lower for w in ["fee", "fees", "cost", "charge", "expensive", "scholarship", "tuition"])
    has_campus = any(w in q_lower for w in ["hostel", "mess", "clubs", "sports", "life", "campus", "accommodation", "canteen", "weather"])
    
    if has_software_transition:
        query_type = "software_transition"
        priority_categories = ["branch_profile", "coding_culture"]
    elif has_comparison:
        query_type = "comparison_query"
        priority_categories = ["branch_profile", "comparison"]
    elif has_latest and has_placement:
        query_type = "latest_updates"
        priority_categories = ["placements"]
    elif has_placement:
        query_type = "placement_query"
        priority_categories = ["placements", "branch_profile"]
    elif has_cutoff:
        query_type = "cutoff_query"
        priority_categories = ["cutoffs"]
    elif has_josaa:
        query_type = "josaa_strategy"
        priority_categories = ["josaa", "cutoffs"]
    elif has_fee:
        query_type = "fee_query"
        priority_categories = ["admin", "faq"]
    elif has_campus:
        query_type = "campus_life"
        priority_categories = ["campus", "faq"]
    elif any(b in q_lower for b in ["cse", "ee", "me", "ce", "ep", "dse", "mnc", "computer science", "electrical", "mechanical", "civil", "physics", "data science"]):
        query_type = "branch_overview"
        priority_categories = ["branch_profile"]
        
    # 3. Determine pipeline needs
    needs_web = False
    if has_latest or query_type == "latest_updates":
        needs_web = True
        
    needs_rerank = False
    if query_type == "general" or len(priority_categories) == 0:
        needs_rerank = True
        
    needs_decomposition = False
    
    return {
        "type": query_type,
        "entities": entities,
        "priority_categories": priority_categories,
        "needs_web": needs_web,
        "needs_rerank": needs_rerank,
        "needs_decomposition": needs_decomposition
    }


# ── JSON Array Parser ───────────────────────────────────────────
def parse_json_array(text: str) -> list:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\n", "", text)
        text = re.sub(r"\n```$", "", text)
        text = text.strip()
        
    match = re.search(r"(\[[\s\S]*\])", text)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass
            
    objects = re.findall(r"(\{[\s\S]*?\})", text)
    parsed = []
    for obj_str in objects:
        try:
            parsed.append(json.loads(obj_str))
        except Exception:
            pass
    return parsed

# ── Deterministic Verification, Scoring & Fusion ────────────────
def verify_claim(claim: dict, current_year: Optional[int] = None) -> dict:
    """Calculates source trust tier, freshness scores, and final confidence for an atomic claim."""
    if current_year is None:
        current_year = datetime.now().year
        
    source = claim.get("source_name", "") or ""
    source_lower = source.lower()
    text = claim.get("text", claim.get("claim", "")) or ""
    claim["text"] = text  # Ensure text field is always explicitly populated
    text_lower = text.lower()
    
    # 1. Deterministic Source-Tiering Map
    TRUST = {
        "official_pdf": 1.0,
        "official_website": 0.98,
        "placement_report": 0.95,
        "faculty_profile": 0.9,
        "news": 0.7,
        "blog": 0.4,
        "reddit": 0.2,
        "llm_prior": 0.3
    }
    
    # Determine the source trust tier key
    s_type = claim.get("source_type", "")
    key = "llm_prior"
    if s_type == "Official PDF/RAG":
        key = "official_pdf"
    elif any(d in source_lower for d in ["iitmandi.ac.in", "josaa.nic.in", "gov.in", "nic.in"]):
        key = "official_website"
        claim["source_type"] = "Official Website"
    elif any(k in source_lower or k in text_lower for k in ["placement report", "cnp", "salary report", "placement statistics"]):
        key = "placement_report"
        claim["source_type"] = "Placement Report"
    elif any(k in source_lower for k in ["faculty", "profile", "scee.iitmandi"]):
        key = "faculty_profile"
        claim["source_type"] = "Faculty Profile"
    elif any(d in source_lower for d in ["indianexpress", "timesofindia", "ndtv", "thehindu", "news", "hindustantimes"]):
        key = "news"
        claim["source_type"] = "News"
    elif any(d in source_lower for d in ["shiksha", "collegedunia", "careers360", "blog", "medium"]):
        key = "blog"
        claim["source_type"] = "Blog"
    elif any(d in source_lower or d in text_lower for d in ["quora", "reddit"]):
        key = "reddit"
        claim["source_type"] = "reddit"
    else:
        # Fallback to map value if present
        for k in TRUST.keys():
            if k in s_type.lower():
                key = k
                break
                
    base_trust = TRUST.get(key, 0.3)
    
    # 2. Freshness Penalty (Deduct -0.3 if older than current_year - 2)
    years = [int(y) for y in re.findall(r"\b(20\d{2})\b", text + " " + source)]
    source_year = claim.get("source_year") or (max(years) if years else None)
    
    # Check official CnP report from July 2024 using regex
    CNP_REGEX = re.compile(r'cnp report', re.IGNORECASE)
    if CNP_REGEX.search(source_lower) and not source_year:
        source_year = 2024
        
    claim["source_year"] = source_year
    
    # Enforce [Year]: [Placement Stats] format for placement claims
    if claim.get("category") == "placement" and source_year:
        year_prefix = f"{source_year}: "
        if not text.startswith(year_prefix):
            clean_text = re.sub(r"^\b20\d{2}\b\s*:\s*", "", text)
            claim["text"] = f"{year_prefix}{clean_text}".replace("  ", " ").strip()
    
    freshness = 1.0
    confidence = base_trust
    
    if source_year:
        age = current_year - source_year
        if age > 2:
            freshness = max(0.1, 1.0 - (age * 0.15))
            confidence -= 0.3
            
    claim["freshness_score"] = freshness
    claim["confidence"] = max(0.1, round(confidence, 2))
    claim["verified"] = True
    claim["contradicts"] = []
    claim["rejected"] = False

    
    # 3. Sanity Checks (Reject impossible claims at verification time)
    val = claim.get("value")
    unit = claim.get("unit")
    if val is not None:
        try:
            val_float = float(val)
            category = claim.get("category", "")
            # placement_rate > 100
            if (unit == "%" or "placement" in category) and val_float > 100.0:
                claim["rejected"] = True
                logger.warning("Sanity Check: Rejected placement percentage %.2f (> 100%%)", val_float)
            # invalid negative metrics
            if unit in ["LPA", "rank"] and val_float <= 0.0:
                claim["rejected"] = True
                logger.warning("Sanity Check: Rejected invalid metric value %.2f for unit %s", val_float, unit)
            # cutoff_rank < 1
            if unit == "rank" and val_float < 1.0:
                claim["rejected"] = True
                logger.warning("Sanity Check: Rejected impossible cutoff rank %.2f (< 1)", val_float)
        except (ValueError, TypeError):
            pass
            
    return claim

def fuse_and_arbitrate_claims(claims: List[Dict[str, Any]], query: str, current_year: int = 2026) -> List[Dict[str, Any]]:
    """Applies age-based RAG overrides, contradiction tracking, validates metrics, and filters brochure noise."""
    valid_claims = []
    query_lower = query.lower()
    
    # Check if brochure is explicitly asked
    wants_brochure = any(kw in query_lower for kw in ["hostel", "mess", "canteen", "wifi", "campus", "classroom", "greenery", "building"])
    
    # 1. Filter out rejected, brochure noise, and check average vs highest packages
    for c in claims:
        if not c.get("verified", False) or c.get("rejected", False):
            continue
            
        text = c.get("text", "") or ""
        text_lower = text.lower()
        
        # Brochure Filter: Automatically remove low-decision-value claims unless explicitly asked
        if not wants_brochure:
            brochure_keywords = ["classroom", "canteen", "greenery", "hostel wifi", "mess food", "campus beauty", "scenic", "mountains", "dormitory", "beautiful campus"]
            if any(kw in text_lower for kw in brochure_keywords):
                logger.info("Brochure Filter: Removing low-decision brochure claim: %s", text)
                continue
                
        valid_claims.append(c)

    # Sanity Check: average package > highest package for same entity and year
    packages = {}
    for c in list(valid_claims):
        if c.get("category") == "placement" and c.get("unit") == "LPA" and c.get("value") is not None:
            ent = c.get("entity", "").upper()
            yr = c.get("source_year")
            try:
                val = float(c["value"])
                text_low = c.get("text", "").lower()
                if ent and yr:
                    key = (ent, yr)
                    if key not in packages:
                        packages[key] = {"avg": None, "highest": None, "avg_claim": None, "highest_claim": None}
                    
                    if any(x in text_low for x in ["highest", "maximum", "max"]):
                        packages[key]["highest"] = val
                        packages[key]["highest_claim"] = c
                    elif any(x in text_low for x in ["average", "avg", "mean", "median"]):
                        packages[key]["avg"] = val
                        packages[key]["avg_claim"] = c
            except (ValueError, TypeError):
                pass

    for key, pk in packages.items():
        if pk["avg"] is not None and pk["highest"] is not None:
            if pk["avg"] > pk["highest"]:
                logger.warning("Sanity Check: Average package %.2f > highest package %.2f for %s in %s. Rejecting conflicting average claim.", pk["avg"], pk["highest"], key[0], key[1])
                avg_claim = pk["avg_claim"]
                if avg_claim in valid_claims:
                    valid_claims.remove(avg_claim)
        
    # 2. Group RAG and Web claims
    rag_claims = [c for c in valid_claims if c.get("origin") == "rag"]
    web_claims = [c for c in valid_claims if c.get("origin") == "web"]
    
    # Check if we have placements from official CnP Report using case-insensitive regex
    CNP_REGEX = re.compile(r'cnp report', re.IGNORECASE)
    cnp_placements = [c for c in rag_claims if c.get("category") == "placement" and CNP_REGEX.search(c.get("source_name", ""))]
    
    if cnp_placements:
        logger.info("Only preferring official CnP Report for placement data. Discarding other placement sources.")
        # Discard non-CnP placement claims in both RAG and Web
        rag_claims = [c for c in rag_claims if c.get("category") != "placement" or CNP_REGEX.search(c.get("source_name", ""))]
        web_claims = [c for c in web_claims if c.get("category") != "placement" or CNP_REGEX.search(c.get("source_name", ""))]

    
    # 3. Fresh RAG Arbitration Policy
    # Official categories
    OFFICIAL_CATEGORIES = {
        "placements",
        "cutoffs",
        "branch_stats",
        "curriculum",
        "placement",
        "cutoff"
    }
    
    # Index fresh RAG claims by (entity, category)
    # A RAG claim is "fresh" if source_year >= 2024
    fresh_rag_by_ent_cat = {}
    for rc in rag_claims:
        cat = rc.get("category", "general")
        ent = rc.get("entity", "").upper()
        yr = rc.get("source_year")
        
        if yr and yr >= (current_year - 2): # >= 2024
            key = (ent, cat)
            fresh_rag_by_ent_cat[key] = True

    fused_claims = list(rag_claims)
    
    # Arbitration filter on Web claims
    for wc in web_claims:
        cat = wc.get("category", "general")
        ent = wc.get("entity", "").upper()
        
        # If category is official and we have fresh RAG data, DISCARD web claim entirely!
        if cat in OFFICIAL_CATEGORIES:
            if (ent, cat) in fresh_rag_by_ent_cat:
                logger.info("Arbitration: Discarded conflicting Web claim because fresh RAG exists for %s:%s. Claim: %s", ent, cat, wc.get("text"))
                continue
            else:
                wc["text"] = f"[Web-Sourced (RAG Absent/Stale)] {wc.get('text', '')}"
                fused_claims.append(wc)
        else:
            # Fuse/Merge other categories (research, faculty, latest developments, campus life)
            fused_claims.append(wc)
            
    # 4. Contradiction Tracking
    for i, c1 in enumerate(fused_claims):
        for j, c2 in enumerate(fused_claims):
            if i != j:
                ent1 = c1.get("entity", "").upper()
                ent2 = c2.get("entity", "").upper()
                cat1 = c1.get("category")
                cat2 = c2.get("category")
                yr1 = c1.get("source_year")
                yr2 = c2.get("source_year")
                
                # Must be same entity, same category, same year
                if ent1 == ent2 and cat1 == cat2 and yr1 == yr2 and yr1 is not None:
                    val1 = c1.get("value")
                    val2 = c2.get("value")
                    unit1 = c1.get("unit")
                    unit2 = c2.get("unit")
                    
                    if val1 is not None and val2 is not None and unit1 and unit1 == unit2:
                        try:
                            f1 = float(val1)
                            f2 = float(val2)
                            # numeric difference > 5%
                            if abs(f1 - f2) > 0.05 * max(f1, f2):
                                if c2["claim_id"] not in c1["contradicts"]:
                                    c1["contradicts"].append(c2["claim_id"])
                                if c1["claim_id"] not in c2["contradicts"]:
                                    c2["contradicts"].append(c1["claim_id"])
                        except ValueError:
                            pass
                            
    # 5. Deduplicate by clean lower-case text
    unique_fused = []
    seen_texts = set()
    for c in fused_claims:
        norm = re.sub(r"[^\w\s]", "", c.get("text", "").lower())
        if norm in seen_texts:
            continue
        seen_texts.add(norm)
        unique_fused.append(c)
        
    return unique_fused

# ── Cross-IIT guards ─────────────────────────────────────────────
_OTHER_IIT_PATTERN = re.compile(
    r'iit\s*(?:bombay|delhi|madras|kanpur|kharagpur|roorkee|guwahati|hyderabad|'
    r'indore|varanasi|bhu|patna|ropar|jodhpur|gandhinagar|bhubaneswar|tirupati|'
    r'palakkad|dharwad|jammu|bhilai|goa|ism)',
    re.IGNORECASE
)
_IIT_MANDI_PATTERN = re.compile(r'iit\s*mandi', re.IGNORECASE)


# ── Concurrency & Key Management Safeguards ─────────────────────
SEMAPHORE = asyncio.Semaphore(5)


class GeminiKeyManager:
    """
    Manages active Gemini API keys with thread/async-safe asyncio.Lock,
    instant key rotation on 429, and jittered cooldown intervals.
    """
    def __init__(self, primary: str, secondary: str, third: str):
        self.keys = []
        if primary and primary != "your_gemini_api_key_here":
            self.keys.append({"label": "Primary", "key": primary, "cooldown_until": 0.0})
        if secondary and secondary != "your_gemini_second_api_key_here":
            self.keys.append({"label": "Secondary", "key": secondary, "cooldown_until": 0.0})
        if third and third != "your_gemini_third_api_key_here":
            self.keys.append({"label": "Third", "key": third, "cooldown_until": 0.0})
        self._current_idx = 0
        self._lock = asyncio.Lock()

    async def get_available_key(self) -> Optional[dict]:
        """
        Returns the first key that is not under active cooldown.
        If all keys are on cooldown, returns the key that will become available soonest.
        """
        async with self._lock:
            if not self.keys:
                return None
            now = time.time()
            n_keys = len(self.keys)
            
            # 1. Try to find a key that is not on cooldown
            for i in range(n_keys):
                idx = (self._current_idx + i) % n_keys
                key_info = self.keys[idx]
                if key_info["cooldown_until"] < now:
                    self._current_idx = idx
                    return key_info
            
            # 2. If all are on cooldown, select the one with the smallest cooldown_until
            least_cooldown_key = min(self.keys, key=lambda k: k["cooldown_until"])
            logger.warning(
                "All Gemini API keys are currently on cooldown! Selecting the least cooled down key: %s (remaining cooldown: %.1fs)", 
                least_cooldown_key["label"], 
                least_cooldown_key["cooldown_until"] - now
            )
            return least_cooldown_key

    async def handle_429(self, key_label: str):
        """Puts a key on jittered cooldown (120s + jitter) and rotates to the next index."""
        async with self._lock:
            now = time.time()
            cooldown_duration = 120.0 + random.randint(0, 30)
            for key_info in self.keys:
                if key_info["label"] == key_label:
                    key_info["cooldown_until"] = now + cooldown_duration
                    logger.warning("Gemini Key %s put on jittered cooldown for %.1f seconds due to 429.", key_label, cooldown_duration)
            if self.keys:
                self._current_idx = (self._current_idx + 1) % len(self.keys)


def get_query_entities(query: str) -> List[str]:
    """
    Extracts unique program/branch entities from the query using strict word boundaries.
    """
    query_lower = query.lower().strip()
    branches = []
    
    # EE
    if re.search(r"\b(ee|electrical)\b", query_lower):
        branches.append("EE")
    # CSE
    if re.search(r"\b(cse|computer science|computer)\b", query_lower):
        branches.append("CSE")
        
    # ME - match mechanical/mech or case-sensitive ME (exclude standard lowercase "me")
    if "mechanical" in query_lower or "mech" in query_lower or re.search(r"\bME\b", query):
        branches.append("ME")
        
    # CE
    if re.search(r"\bce\b|\bcivil\b", query_lower):
        branches.append("CE")
    # DS
    if re.search(r"\bds\b|\bdata science\b", query_lower):
        branches.append("DS")
        
    # Deduplicate branches preserving order
    branches = list(dict.fromkeys(branches))
    
    entities = []
    if branches:
        for b in branches:
            entities.append(f"IIT Mandi {b}")
    else:
        entities.append("IIT Mandi")
        
    return entities


def compress_claims(claims: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Deduplicates, confidence-gates (>= 0.4), and merges highly similar claims 
    to reduce prompt token load before Groq synthesis.
    """
    if not claims:
        return []
        
    # 1. Filter out low-confidence and placeholder claims
    valid_claims = []
    for c in claims:
        claim_text = c.get("claim", c.get("text", "")) or ""
        if claim_text == "__EMPTY__" or not claim_text.strip():
            continue
        if float(c.get("confidence", 0.5)) < 0.4:
            continue
        valid_claims.append(c)

    # 2. Strict text deduplication
    seen_texts = set()
    unique_claims = []
    for c in valid_claims:
        claim_text = c.get("text", c.get("claim", "")) or ""
        text_norm = re.sub(r"[^\w\s]", "", claim_text.lower()).strip()
        if text_norm not in seen_texts:
            seen_texts.add(text_norm)
            unique_claims.append(c)

    # 3. Deduplicate claims with identical numeric values on the same category/entity/year
    merged_claims = []
    for c in unique_claims:
        ent = c.get("entity", "").upper()
        cat = c.get("category", "")
        yr = c.get("source_year")
        val = c.get("value")
        
        duplicate = False
        for existing in merged_claims:
            if (existing.get("entity", "").upper() == ent and 
                existing.get("category", "") == cat and 
                existing.get("source_year") == yr and 
                existing.get("value") == val and val is not None):
                duplicate = True
                break
                
        if not duplicate:
            merged_claims.append(c)
            
    return merged_claims


class RAGGenerator:

    """
    RAG answer generator with modular Query Classification, independent Claim Extraction,
    Python Verification, Claims Caching, Fusion Arbitration, and Groq Synthesis.
    """

    def __init__(self):
        # Read API Keys and URLs
        self.gemini_api_key = (
            os.getenv("GEMINI_API_KEY") or
            getattr(settings, "gemini_api_key", None) or
            ""
        ).strip()
        self.gemini_second_api_key = (
            os.getenv("GEMINI_SECOND_API_KEY") or
            getattr(settings, "gemini_second_api_key", None) or
            ""
        ).strip()
        self.gemini_third_api_key = (
            os.getenv("GEMINI_THIRD_API_KEY") or
            getattr(settings, "gemini_third_api_key", None) or
            ""
        ).strip()
        self.gemini_api_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

        self.groq_api_key = (
            os.getenv("GROQ_API_KEY") or
            getattr(settings, "groq_api_key", None) or
            ""
        ).strip()
        self.groq_model = (
            os.getenv("GROQ_MODEL") or
            getattr(settings, "groq_model", "llama-3.3-70b-versatile")
        ).strip()
        self.groq_api_url = (
            os.getenv("GROQ_API_URL") or
            getattr(settings, "groq_api_url", "https://api.groq.com/openai/v1/chat/completions")
        ).strip()

        self.openrouter_api_key = (
            os.getenv("OPENROUTER_API_KEY") or
            getattr(settings, "openrouter_api_key", None) or
            ""
        ).strip()
        self.openrouter_model = (
            os.getenv("OPENROUTER_MODEL") or
            getattr(settings, "openrouter_model", "meta-llama/llama-3.3-70b-instruct")
        ).strip()
        self.openrouter_api_url = (
            os.getenv("OPENROUTER_API_URL") or
            getattr(settings, "openrouter_api_url", "https://openrouter.ai/api/v1/chat/completions")
        ).strip()

        self.deepseek_api_key = (
            os.getenv("DEEPSEEK_API_KEY") or
            getattr(settings, "deepseek_api_key", None) or
            ""
        ).strip()
        self.deepseek_model = getattr(settings, "deepseek_model", "deepseek-chat")
        self.deepseek_api_url = getattr(settings, "deepseek_api_url", "https://api.deepseek.com/v1/chat/completions")

        self.nvidia_api_key = (
            os.getenv("NVIDIA_API_KEY") or
            getattr(settings, "nvidia_api_key", None) or
            ""
        ).strip()
        self.nvidia_model = getattr(settings, "nvidia_model", "meta/llama-3.3-70b-instruct")
        self.nvidia_api_url = getattr(settings, "nvidia_api_url", "https://integrate.api.nvidia.com/v1/chat/completions")

        self.hf_api_key = (
            os.getenv("HF_API_KEY") or
            os.getenv("HF_TOKEN") or
            getattr(settings, "hf_api_key", None) or
            ""
        ).strip()
        self.hf_model = getattr(settings, "hf_model", "meta-llama/Llama-3.3-70B-Instruct")
        self.hf_api_url = getattr(settings, "hf_api_url", "https://router.huggingface.co/v1/chat/completions")

        self.key_manager = GeminiKeyManager(
            self.gemini_api_key,
            self.gemini_second_api_key,
            self.gemini_third_api_key
        )
        self._cache_lock = asyncio.Lock()
        self._groq_fail_count = 0
        self._groq_bypass_until = 0.0

    def _call_llm(self, messages: list) -> Optional[str]:
        """Core LLM call handler with Groq primary and multiple fallbacks (Gemini, OpenRouter, DeepSeek, Nvidia, Hugging Face)."""
        # 1. Groq (Primary)
        now = time.time()
        if self.groq_api_key and self.groq_api_key != "your_groq_api_key_here":
            if now < self._groq_bypass_until:
                logger.warning("Groq is currently bypassed (under 429 cooldown). Skipping to Gemini fallback.")
            else:
                headers = {
                    "Authorization": f"Bearer {self.groq_api_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": self.groq_model,
                    "messages": messages,
                    "temperature": 0.1,
                    "max_tokens": 1500
                }
                try:
                    with httpx.Client(timeout=8.0) as client:
                        response = client.post(self.groq_api_url, headers=headers, json=payload)
                        if response.status_code == 429:
                            self._groq_bypass_until = now + 60
                            logger.critical("Groq API hit 429 rate limit. Bypassing Groq for 60 seconds!")
                            response.raise_for_status()
                        response.raise_for_status()
                        res_data = response.json()
                        choices = res_data.get("choices", [])
                        if choices:
                            return choices[0].get("message", {}).get("content", "").strip()
                except Exception as e:
                    logger.warning("Groq call failed in generator: %s. Trying fallbacks...", e)

        # 2. Gemini 2.5 Flash (Fallback 1 - High reliability & rate limit)
        try:
            active_key = None
            if self.key_manager.keys:
                for k in self.key_manager.keys:
                    if k["cooldown_until"] < now:
                        active_key = k
                        break
                if not active_key:
                    active_key = self.key_manager.keys[0]
            if active_key:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={active_key['key']}"
                prompt_parts = []
                for msg in messages:
                    if msg["role"] in ["system", "user"]:
                        prompt_parts.append(msg["content"])
                combined_prompt = "\n\n".join(prompt_parts)
                
                payload = {
                    "contents": [{
                        "parts": [{"text": combined_prompt}]
                    }],
                    "generationConfig": {
                        "temperature": 0.1,
                        "maxOutputTokens": 1500,
                        "thinkingConfig": {
                            "thinkingBudget": 0
                        }
                    }
                }
                with httpx.Client(timeout=15.0) as client:
                    response = client.post(url, json=payload)
                    if response.status_code == 429:
                        active_key["cooldown_until"] = now + 120.0
                        logger.warning("Gemini Key %s rate limited (429 status). Putting on cooldown for 120s.", active_key["label"])
                        response.raise_for_status()
                    response.raise_for_status()
                    res_data = response.json()
                    candidates = res_data.get("candidates", [])
                    if candidates:
                        content = candidates[0].get("content", {})
                        parts = content.get("parts", [])
                        if parts:
                            return parts[0].get("text", "").strip()
        except Exception as e:
            if hasattr(e, "response") and e.response is not None and e.response.status_code == 429:
                active_key["cooldown_until"] = now + 120.0
                logger.warning("Gemini Key %s rate limited (HTTPStatusError 429). Putting on cooldown for 120s.", active_key["label"])
            logger.warning("Gemini synthesis fallback failed: %s. Trying OpenRouter fallback...", e)

        # 2. OpenRouter (Fallback 1)
        if self.openrouter_api_key and self.openrouter_api_key != "your_openrouter_api_key_here":
            headers = {
                "Authorization": f"Bearer {self.openrouter_api_key}",
                "HTTP-Referer": "https://huggingface.co/spaces",
                "X-Title": "IIT Mandi Chatbot",
                "Content-Type": "application/json"
            }
            payload = {
                "model": self.openrouter_model,
                "messages": messages,
                "temperature": 0.1,
                "max_tokens": 1500
            }
            try:
                with httpx.Client(timeout=10.0) as client:
                    response = client.post(self.openrouter_api_url, headers=headers, json=payload)
                    response.raise_for_status()
                    res_data = response.json()
                    choices = res_data.get("choices", [])
                    if choices:
                        return choices[0].get("message", {}).get("content", "").strip()
            except Exception as e:
                logger.warning("OpenRouter call failed in generator: %s. Trying DeepSeek fallback...", e)

        # 3. DeepSeek (Fallback 2)
        if self.deepseek_api_key and self.deepseek_api_key != "your_deepseek_api_key_here":
            headers = {
                "Authorization": f"Bearer {self.deepseek_api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": self.deepseek_model,
                "messages": messages,
                "temperature": 0.1,
                "max_tokens": 1500
            }
            try:
                with httpx.Client(timeout=10.0) as client:
                    response = client.post(self.deepseek_api_url, headers=headers, json=payload)
                    response.raise_for_status()
                    res_data = response.json()
                    choices = res_data.get("choices", [])
                    if choices:
                        return choices[0].get("message", {}).get("content", "").strip()
            except Exception as e:
                logger.warning("DeepSeek call failed in generator: %s. Trying Nvidia fallback...", e)

        # 4. Nvidia (Fallback 3)
        if self.nvidia_api_key and self.nvidia_api_key != "your_nvidia_api_key_here":
            headers = {
                "Authorization": f"Bearer {self.nvidia_api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": self.nvidia_model,
                "messages": messages,
                "temperature": 0.1,
                "max_tokens": 1500
            }
            try:
                with httpx.Client(timeout=10.0) as client:
                    response = client.post(self.nvidia_api_url, headers=headers, json=payload)
                    response.raise_for_status()
                    res_data = response.json()
                    choices = res_data.get("choices", [])
                    if choices:
                        return choices[0].get("message", {}).get("content", "").strip()
            except Exception as e:
                logger.warning("Nvidia call failed in generator: %s. Trying Hugging Face fallback...", e)

        # 5. Hugging Face Inference API / Serverless (Fallback 4)
        if self.hf_api_key and self.hf_api_key != "your_hf_api_key_here":
            headers = {
                "Authorization": f"Bearer {self.hf_api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": self.hf_model,
                "messages": messages,
                "temperature": 0.1,
                "max_tokens": 1500
            }
            try:
                with httpx.Client(timeout=10.0) as client:
                    response = client.post(self.hf_api_url, headers=headers, json=payload)
                    response.raise_for_status()
                    res_data = response.json()
                    choices = res_data.get("choices", [])
                    if choices:
                        return choices[0].get("message", {}).get("content", "").strip()
            except Exception as e:
                logger.critical("Hugging Face API call failed in generator: %s", e)
        return None

    async def extract_rag_claims(self, confident_chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """RAG Claims Extractor: Uses Groq to extract atomic factual claims from local verified documents ONLY."""
        if not confident_chunks:
            return []

        context_parts = []
        for i, chunk in enumerate(confident_chunks, 1):
            source = chunk.get("metadata", {}).get("source", "unknown")
            text = chunk.get("text", "").strip()
            context_parts.append(f"[Document {i} | Source: {source}]:\n{text}")
        context_text = "\n\n".join(context_parts)

        prompt = f"""You are a precise data extractor. Extract atomic factual claims from the following official local documents.
Each claim must represent a single, atomic, verifiable metric or statement. Do not combine multiple facts into one sentence. 
Do not hallucinate or add any info outside the provided documents.

Return the findings STRICTLY as a raw JSON list of objects in the format below. Do not add markdown backticks or other text:
[
  {{
    "text": "Exact atomic statement (e.g., EE B.Tech requires a minimum of 160 credits)",
    "category": "placement|cutoff|curriculum|research_and_news|campus_life|career_decision|higher_studies|placement_vs_interest_tradeoff|general",
    "entity": "EE|CSE|ME|IIT Mandi",
    "value": 160.0,      // Parsed float value if applicable
    "unit": "LPA|%|rank|None",    // Unit of measurement or 'None'
    "source_name": "Source label of the document (e.g. from '[Document X | Source: Y]')"
  }}
]

Documents:
{context_text}
"""
        messages = [
            {"role": "system", "content": "You are a factual JSON data extractor. Output JSON only."},
            {"role": "user", "content": prompt}
        ]

        answer = await asyncio.to_thread(self._call_llm, messages)
        if not answer:
            return []

        claims = parse_json_array(answer)
        for idx, c in enumerate(claims):
            c["claim_id"] = f"claim_rag_{idx}_{int(time.time())}"
            c["source_type"] = "Official PDF/RAG"
            c["origin"] = "rag"
        return claims


    async def extract_web_claims(self, query: str) -> List[Dict[str, Any]]:
        """Web Claims Extractor: Uses Gemini 2.5 Flash with search grounding to fetch and extract web claims."""
        system_instruction = (
            "You are a JOSAA counseling intelligence agent. Actively use Google Search to retrieve "
            "the latest, fresh facts and statistics about branches and programs at IIT Mandi from the web. "
            "Extract atomic factual claims and return them STRICTLY as a raw JSON list of objects. "
            "Never write introductory prose, markdown blocks, or conversations. Return ONLY the JSON array in this format:\n"
            "[\n"
            "  {\n"
            "    \"text\": \"Factual claim description (e.g. EE placement rate was 95% in 2023 or CSE average was 25 LPA)\",\n"
            "    \"category\": \"placement|cutoff|curriculum|research_and_news|campus_life|career_decision|higher_studies|placement_vs_interest_tradeoff|general\",\n"
            "    \"entity\": \"EE|CSE|ME|IIT Mandi\",\n"
            "    \"value\": 95.0,  // Parsed float or null\n"
            "    \"unit\": \"%|LPA|rank|None\",  // Unit of the float or 'None'\n"
            "    \"source_name\": \"Specific URL or domain\"\n"
            "  }\n"
            "]"
        )
        
        payload = {
            "systemInstruction": {
                "parts": [{"text": system_instruction}]
            },
            "contents": [{
                "parts": [{"text": f"Search the web and extract atomic factual claims for: {query}"}]
            }],
            "tools": [{"google_search": {}}],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 1500,
                "thinkingConfig": {
                    "thinkingBudget": 0
                }
            }
        }
        
        # Get maximum attempts matching configured keys
        max_attempts = len(self.key_manager.keys)
        if max_attempts == 0:
            logger.info("No Gemini API keys configured. Skipping Gemini web search.")
            return []
            
        for attempt in range(max_attempts):
            key_info = await self.key_manager.get_available_key()
            if not key_info:
                logger.warning("No Gemini API keys available.")
                break
                
            key_label = key_info["label"]
            api_key = key_info["key"]
            url = f"{self.gemini_api_url}?key={api_key}"
            
            logger.info("Attempting Gemini web search using %s API key...", key_label)
            
            try:
                async with httpx.AsyncClient(timeout=25.0) as client:
                    async with SEMAPHORE:
                        response = await client.post(url, json=payload)
                        
                    if response.status_code in [429, 500, 502, 503, 504]:
                        logger.warning("%s Gemini API returned %d. Rotating key immediately.", key_label, response.status_code)
                        await self.key_manager.handle_429(key_label)
                        continue  # Rotate immediately next loop iteration
                        
                    response.raise_for_status()
                    data = response.json()
                    
                    candidates = data.get("candidates", [])
                    if candidates:
                        # Extract search grounding metadata URLs
                        grounding = candidates[0].get("groundingMetadata", {})
                        chunks = grounding.get("groundingChunks", [])
                        urls = [ch.get("web", {}).get("uri") for ch in chunks if ch.get("web", {}).get("uri")]
                        source_url = urls[0] if urls else "https://www.iitmandi.ac.in"

                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            text = parts[0].get("text", "").strip()
                            claims = parse_json_array(text)
                            
                            for idx, c in enumerate(claims):
                                c["claim_id"] = f"claim_web_{idx}_{int(time.time())}"
                                c["source_type"] = "Web Search"
                                c["origin"] = "web"
                                c["source_url"] = source_url
                                if "source_name" not in c or not c["source_name"]:
                                    c["source_name"] = "Gemini Google Search"
                            logger.info("Successfully extracted %d claims from %s Gemini Web Search with source URL: %s", len(claims), key_label, source_url)
                            return claims
                    break  # Exit on success or no candidates
            except httpx.HTTPStatusError as hse:
                if hse.response.status_code in [429, 500, 502, 503, 504]:
                    logger.warning("%s Gemini API HTTP status error %d. Rotating key immediately.", key_label, hse.response.status_code)
                    await self.key_manager.handle_429(key_label)
                    continue
                logger.error("HTTP status error during %s Gemini search: %s", key_label, hse)
                break
            except Exception as e:
                logger.warning("Failed to fetch %s Gemini structured web claims: %s", key_label, e)
                break
        
        return []

    async def extract_web_claims_for_entity(self, entity: str) -> List[Dict[str, Any]]:
        """
        Unified Entity-Level Retrieval: Fetches web claims covering placements,
        curriculum, research, and software opportunities in a single comprehensive call.
        """
        entity_short = entity.replace("IIT Mandi", "").strip()
        if not entity_short:
            query_str = "IIT Mandi overall B.Tech placements statistics packages, academic curriculum rigor, campus facilities hostels student life, and latest news developments"
        else:
            query_str = f"IIT Mandi {entity_short} B.Tech placements statistics packages, academic curriculum rigor, faculty research areas, and software IT sector transition opportunities"
            
        logger.info("Triggering unified entity web search for %s: '%s'", entity, query_str)
        claims = await self.extract_web_claims(query_str)
        return claims

    def _chunks_to_claims(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Converts chunks directly to structured claims format without an LLM call."""
        claims = []
        for i, chunk in enumerate(chunks):
            meta = chunk.get("metadata", {})
            source = meta.get("source", "unknown")
            text = chunk.get("text", "").strip()
            
            clean_text = text
            if clean_text.startswith("Title:"):
                parts = clean_text.split("\n\n", 1)
                if len(parts) > 1:
                    clean_text = parts[1]
                    
            category = meta.get("category", "general")
            entity = meta.get("entity", "IIT Mandi")
            
            year = 2026
            if "last_verified" in meta:
                try:
                    year = int(meta["last_verified"])
                except:
                    pass
            else:
                year_match = re.search(r"\b(202\d)\b", clean_text)
                if year_match:
                    year = int(year_match.group(1))
                elif "2023" in source:
                    year = 2023
                elif "2024" in source:
                    year = 2024
                    
            claims.append({
                "claim_id": f"claim_rag_{i}_{int(time.time())}",
                "text": clean_text,
                "category": category,
                "entity": entity,
                "source_name": source,
                "source_type": "Official PDF/RAG",
                "source_year": year,
                "confidence": float(chunk.get("confidence_score", 0.9)),
                "origin": "rag"
            })
        return claims

    def _verify_claims_locally(self, fused_claims: List[Dict[str, Any]]) -> dict:
        """
        Verify claims locally for sanity and consistency.
        Returns a dict containing 'contradictions' (list) and 'uncertainties' (list).
        """
        contradictions = []
        uncertainties = []
        
        for c in fused_claims:
            text = c.get("text", "").lower()
            source = c.get("source_name", "unknown")
            year = c.get("source_year")
            
            if year and year < 2024:
                uncertainties.append(
                    f"Claim from {source} mentions data from year {year}, which is outdated (prior to 2024)."
                )
                
            pct_matches = re.findall(r"\b(\d+(?:\.\d+)?)\s*%", text)
            for pct_str in pct_matches:
                try:
                    pct = float(pct_str)
                    if pct > 100.0:
                        contradictions.append(
                            f"Anomalous placement rate of {pct}% (>100%) in claim: '{c.get('text')}' (Source: {source})"
                        )
                except:
                    pass
                    
        by_group = {}
        for c in fused_claims:
            entity = c.get("entity", "general").upper()
            category = c.get("category", "general")
            year = c.get("source_year", 2026)
            key = (entity, category, year)
            if key not in by_group:
                by_group[key] = []
            by_group[key].append(c)
            
        for key, group in by_group.items():
            entity, category, year = key
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    c1 = group[i]
                    c2 = group[j]
                    
                    if c1.get("origin") == c2.get("origin"):
                        continue
                        
                    t1 = c1.get("text", "").lower()
                    t2 = c2.get("text", "").lower()
                    
                    num1_match = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:lpa|%)", t1)
                    num2_match = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:lpa|%)", t2)
                    
                    if num1_match and num2_match:
                        try:
                            v1 = float(num1_match.group(1))
                            v2 = float(num2_match.group(1))
                            if max(v1, v2) > 0:
                                diff = abs(v1 - v2) / max(v1, v2)
                                if diff > 0.20:
                                    contradictions.append(
                                        f"Conflict > 20% on {entity} {category} ({year}): "
                                        f"Local/RAG claim says '{c1.get('text')}' (Source: {c1.get('source_name')}) "
                                        f"while Web/Gemini claim says '{c2.get('text')}' (Source: {c2.get('source_name')})"
                                    )
                                    if "contradicts" not in c1: c1["contradicts"] = []
                                    if "contradicts" not in c2: c2["contradicts"] = []
                                    if c2.get("claim_id") not in c1["contradicts"]:
                                        c1["contradicts"].append(c2.get("claim_id"))
                                    if c1.get("claim_id") not in c2["contradicts"]:
                                        c2["contradicts"].append(c1.get("claim_id"))
                        except:
                            pass
                            
        return {
            "contradictions": list(set(contradictions)),
            "uncertainties": list(set(uncertainties))
        }

    async def generate_answer(self, query: str, confident_chunks: List[Dict[str, Any]], history: List[Dict[str, str]] = None, query_info: dict = None) -> Dict[str, Any]:
        """
        Generate a structured response for the query using independent claim extraction,
        verification, fusion arbitration, semantic caching, and Groq synthesis.
        """
        query_stripped = query.strip()
        if not query_info:
            query_info = classify_query_rich(query_stripped)
        query_class = query_info["type"]
        
        # ── Step 0: New Program Refusals ────────────────────────────────
        NEW_BRANCH_KEYWORDS = {
            "quantum science", "quantum technology",
            "agriculture engineering", "agricultural engineering",
            "chemical engineering and data analytics", "chemical engineering & data analytics",
            "chemical engineering with data analytics"
        }
        if any(kw in query_stripped.lower() for kw in NEW_BRANCH_KEYWORDS):
            has_confident_chunks = False
            if confident_chunks:
                max_confidence = max(c["confidence_score"] for c in confident_chunks)
                if max_confidence >= 0.4:
                    has_confident_chunks = True
            
            if not has_confident_chunks:
                logger.info("Deterministic refusal triggered for new branch query: %s", query_stripped)
                return {
                    "answer": (
                        "This is a newly introduced program at IIT Mandi. "
                        "Detailed information is not yet available in my knowledge base. "
                        "Please check iitmandi.ac.in or ask at the academic section."
                    ),
                    "sources": [],
                    "confidence": 0.0
                }

        # ── Step 1: Cross-IIT Guard ──────────────────────────────────────
        mentions_other_iit = bool(_OTHER_IIT_PATTERN.search(query_stripped))
        mentions_mandi = bool(_IIT_MANDI_PATTERN.search(query_stripped))

        if mentions_other_iit and not mentions_mandi:
            logger.info("Cross-IIT guard: query is about another IIT only. Returning refusal.")
            return {
                "answer": (
                    "I only have detailed data for IIT Mandi. "
                    "For information about other IITs, please check josaa.nic.in "
                    "or the respective institute's website."
                ),
                "sources": [],
                "confidence": 0.0
            }

        # ── Step 2: Aspect-Based Retrieval & Claim Extraction ────────────
        # A. Extract RAG Claims
        skip_rag_llm = query_class in ["branch_overview", "comparison_query", "software_transition"]
        if skip_rag_llm:
            logger.info("Strong-match query type '%s' detected. Bypassing RAG dynamic LLM claim extraction.", query_class)
            rag_claims = self._chunks_to_claims(confident_chunks)
        else:
            rag_claims = await self.extract_rag_claims(confident_chunks)
            
        for rc in rag_claims:
            verify_claim(rc)

        # B. Async Web-Cache-Lookup & Unified Gemini Web Searching
        web_claims = []
        cache_hits = 0
        gemini_calls = 0
        degraded_mode = False
        
        needs_web = query_info.get("needs_web", False)
        if needs_web:
            entities = get_query_entities(query_stripped)
            entities_to_fetch = []
            
            from app.web_cache import WebCache
            web_cache = WebCache()
            
            for ent in entities:
                cached_res = web_cache.get(ent)
                if cached_res is not None:
                    cache_hits += 1
                    claims = cached_res.get("extracted_claims", [])
                    if claims:
                        for c in claims:
                            c["origin"] = "web"
                            verify_claim(c)
                            web_claims.append(c)
                    logger.info("Web cache HIT for entity: '%s' (%d claims)", ent, len(claims))
                else:
                    entities_to_fetch.append(ent)
                    
            if entities_to_fetch:
                now = time.time()
                active_keys = [k for k in self.key_manager.keys if k["cooldown_until"] < now]
                if not active_keys and self.key_manager.keys:
                    logger.warning("Degraded Mode Triggered: All Gemini keys are currently cooling down!")
                    degraded_mode = True
                else:
                    try:
                        tasks = [self.extract_web_claims_for_entity(ent) for ent in entities_to_fetch]
                        gemini_calls += len(entities_to_fetch)
                        
                        fetched_results = await asyncio.wait_for(
                            asyncio.gather(*tasks),
                            timeout=15.0
                        )
                        
                        for ent, claims in zip(entities_to_fetch, fetched_results):
                            if claims:
                                verified_fresh = []
                                for c in claims:
                                    c["origin"] = "web"
                                    norm_ent, norm_cat = normalize_entity_category(ent, c.get("category", "general"))
                                    c["entity"] = norm_ent
                                    c["category"] = norm_cat
                                    verify_claim(c)
                                    if not c.get("rejected", False):
                                        verified_fresh.append({
                                            "entity": c["entity"],
                                            "category": c["category"],
                                            "claim": c.get("claim", c.get("text", "")),
                                            "source_url": c.get("source_url"),
                                            "source_name": c.get("source_name", "Gemini Web Search"),
                                            "source_type": c.get("source_type", "Web Search"),
                                            "source_year": c.get("source_year"),
                                            "confidence": float(c.get("confidence", 0.5)),
                                            "origin": "web"
                                        })
                                web_cache.set(ent, "", extracted_claims=verified_fresh, entity=ent, query_type=query_info["type"])
                                for c in verified_fresh:
                                    verify_claim(c)
                                    web_claims.append(c)
                            else:
                                web_cache.set(ent, "", extracted_claims=[], entity=ent, query_type=query_info["type"])
                    except asyncio.TimeoutError:
                        logger.error("Gemini web search timed out. Falling back to Degraded Mode.")
                        degraded_mode = True
                    except Exception as e:
                        logger.error("Gemini web search encountered exception: %s. Falling back to Degraded Mode.", e)
                        degraded_mode = True
        else:
            logger.info("Skipping Gemini web search (query does not need web enrichment)")

        # C. Claim Compression Layer
        compressed_web = compress_claims(web_claims)
        all_claims = rag_claims + compressed_web

        # ── Step 3: Claim Fusion & Arbitration ────────────────────────────
        fused_claims = fuse_and_arbitrate_claims(all_claims, query_stripped)
        
        # ── Local Fact & Discrepancy Verification ──────────────────────────
        verification_results = self._verify_claims_locally(fused_claims)
        
        degraded_prefix = ""
        if degraded_mode:
            degraded_prefix = "\n\n> [!WARNING]\n> *Latest web enrichment is temporarily unavailable; serving official verified documents only.*\n\n"

        avg_confidence = sum(c.get("confidence", 0.5) for c in fused_claims) / len(fused_claims) if fused_claims else 0.0

        contradiction_list = verification_results["contradictions"]
        seen_contr = set()
        for c in fused_claims:
            if c.get("contradicts"):
                for contr_id in c["contradicts"]:
                    c2 = next((x for x in fused_claims if x.get("claim_id") == contr_id), None)
                    if c2:
                        pair = tuple(sorted([c["claim_id"], c2["claim_id"]]))
                        if pair not in seen_contr:
                            seen_contr.add(pair)
                            contradiction_list.append(
                                f"Numeric discrepancy > 5% on {c.get('entity')} {c.get('category')} ({c.get('source_year')}): "
                                f"Claim '{c.get('text')}' (Source: {c.get('source_name')}, Conf: {c.get('confidence')}) "
                                f"contradicts Claim '{c2.get('text')}' (Source: {c2.get('source_name')}, Conf: {c2.get('confidence')})"
                            )
        
        uncertainties_list = verification_results["uncertainties"]
        
        contradictions_context = "\n".join(f"- {item}" for item in contradiction_list) if contradiction_list else "None detected."
        uncertainties_context = "\n".join(f"- {item}" for item in uncertainties_list) if uncertainties_list else "None detected."

        claims_context = ""
        for idx, c in enumerate(fused_claims, 1):
            source = c.get("source_name", "unknown")
            text = c.get("text", "")
            conf = c.get("confidence", 0.5)
            contr = c.get("contradicts", [])
            contr_note = f" (CONTRADICTS: {', '.join(contr)})" if contr else ""
            claims_context += f"[Claim {idx} | Source: {source} | Confidence: {conf:.2f}{contr_note}]: {text}\n"

        self._last_telemetry = {
            "rag_claims": len(rag_claims),
            "web_cache_hits": cache_hits,
            "gemini_calls": gemini_calls,
            "discarded_claims": len(all_claims) - len(fused_claims),
            "contradictions": len(contradiction_list)
        }

        # ── Step 4: Groq Weighted Response Generation ──────────────
        SYSTEM_PROMPT = """You are an expert, highly rigorous JOSAA admissions counselor who speaks like an honest IIT senior. Provide realistic, factual, and deeply structured, decision-oriented analytical advice on engineering branches. Avoid brochure-style descriptions and generic AI summary text.

CRITICAL RULES:
- **Strict Factuality**: Use ONLY the facts provided in the fused claims. Do NOT fabricate or invent placement figures, cutoffs, recruiter names, branch comparisons, or institute parameters.
- **Prose Ban & Bullet Reasoning**: Replace prose-heavy counselor talk (e.g. "choice depends on student interests") with dense, claim-grounded bulleted reasoning and short analytical statements. Limit narrative glue and filler.
- **Banned Danger Phrases**: NEVER use the phrases: "it can be inferred", "likely", "probably", "suggests", "appears to", unless there is an explicit claim directly specifying that exact inference or outcome in the prompt.
- **Audited Year Requirement**: Every placement stat MUST strictly prefix the calendar year in the format `[Year]: [Placement Stats]` (e.g. "2024: EE Median CTC is ₹14 LPA" or "2024: EE Placement Rate is 61.66%"). If the calendar year is missing, you MUST print exactly: "Branch-wise audited placement year unavailable." and avoid comparative conclusions.
- **Fact vs Interpretation Separation**: In every section, keep facts and interpretations strictly separated. Clearly prefix fact statements with "FACT:" and interpretive deductions with "INTERPRETATION:".
- **Table Parsing Alignment**: Structure all facts perfectly.
- **NO CITATIONS OR SOURCE DISCLOSURES**: NEVER reveal any source names, document paths, database filenames (such as "branch_comparison.md"), search URLs, or document indexes anywhere in your response. Present all information seamlessly as your own direct counselor knowledge.

VOCABULARY CONSTRAINTS:
- **Banned GPT-Style Filler**: DO NOT use: "strong foundation", "industry connection", "versatile degree", "highly competitive", "comprehensive curriculum", "well-rounded education", "diverse opportunities", "cutting-edge".
- **Approved Realistic Alternatives**:
  - Instead of "strong foundation", use "sustained math-heavy coursework" or "rigorous theoretical grounding".
  - Instead of "industry connection", use "partial software placement access" or "direct core placement channels".
  - Instead of "versatile degree", use "flexible electives with core constraints" or "broad hardware-software overlap".
  - Instead of "highly competitive", use "lower placement stability during hiring downturns" or "demanding relative grading curves".
  - Instead of "easy software transition", use "software transition requires independent DSA/CP preparation".

ACADEMIC REALISM & TOUGH SUBJECTS:
- Avoid repeating the obvious (e.g. NEVER write "EE has electrical subjects" or "CSE has computer courses").
- Instead, use concrete academic realism by mentioning actual difficult coursework subjects that students face when discussing branch rigor:
  - For Electrical Engineering (EE): Signals & Systems, Control Systems, Electromagnetic Theory, VLSI electives, DSP, Embedded systems.
  - For Mechanical Engineering (ME): Thermodynamics, Fluid Mechanics, Solid Mechanics, Kinematics & Dynamics of Machines, FEA electives.
  - For Computer Science / Data Science / MnC (CSE/DSE/MnC): Data Structures & Algorithms, Discrete Mathematics, Computer Architecture, Operating Systems, Abstract Algebra, Stochastic Processes.

MANDATORY INTERPRETATION STRUCTURE:
- Every single bullet point prefixed with "INTERPRETATION:" in Section 3 and Section 5 MUST explain:
  1. WHY the statistic or fact matters to the student’s career/decision.
  2. WHAT caused the trend (e.g., specific curriculum constraints, local grading curves, or macroeconomic hiring downturns).
  3. HOW it compares to nearby branches (specifically contrasting with CSE, EE, or ME at IIT Mandi).
  4. WHAT tradeoff the student accepts (e.g. high academic load, limited software job access, intense competition for core roles, or relative grading pressure).

Your response MUST contain the following 5 mandatory sections:

### 1. Verified Institute-Specific Facts
- Separate RAG-derived immutable facts from any interpretation.
- Use the prefix `FACT:` for all factual claims (e.g. placement percentages, packages, ranks).
- Create a neat Markdown comparison table if comparing branches. All placement stats must strictly prefix the year. If year is missing, print "Branch-wise audited placement year unavailable."

### 2. Latest Web-Enriched Developments
- Use the prefix `FACT:` for web developments.
- Do not add speculative interpretations. If no web claims are present, list "No fresh web developments are supported by current claims."

### 3. Grounded Interpretation
- Analyze academic rigor, software transition difficulty (Easy/Moderate/Difficult) and branch flexibility.
- Use the prefix `INTERPRETATION:` for any logical analytical inferences. Apply the "WHY, WHAT, HOW, Tradeoff" structure for each bullet point.
- Never exceed the allowed inferences or use danger phrases.

### 4. Honest Uncertainty
- You MUST separate contradictions from data incompleteness.
- Under sub-heading `#### Discrepancies and Contradictions`, list any numeric discrepancies > 5% detected.
- Under sub-heading `#### Data Incompleteness`, list missing years, gaps in branch statistics, or absent research stats. Do not conflate these two types of uncertainty.

### 5. Final Recommendation
- Provide dense, grounded bullet reasoning. Lay out which paths fit each branch choice best with minimal narrative glue.
- Use the prefix `INTERPRETATION:` for counseling guidelines, applying the "WHY, WHAT, HOW, Tradeoff" structure for each bullet point.
"""

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]
        if history:
            messages.extend(history)

        allowed_inferences_content = ""
        if query_class in ["branch_overview", "comparison_query", "placement_query", "software_transition", "cutoff_query", "josaa_strategy", "general"]:
            allowed_inferences_content = """--- ALLOWED INFERENCES (USE BULLET REASONING ONLY) ---
- EE offers stronger software optionality than ME due to hardware-software co-design overlap (using courses like Signals & Systems, Control Systems, VLSI electives, Embedded systems) and sustained math-heavy coursework, but academic difficulty is very high.
- CSE has the most streamlined software placement access because of direct programming/DSA overlap, abstract coursework (Discrete Mathematics, Operating Systems), and high placement statistics.
- Software transition from core/non-CS branches (like ME, CE, EP) requires intensive independent DSA/CP preparation and accepts a lower placement stability during hiring downturns.
- Mechanical Engineering offers deep core engineering paths but has limited direct core placement channels, forcing a tradeoff where students must prepare independently for SDE roles or GATE/PSU options.
- Data Science (DSE) and Mathematics & Computing (MnC) have specialized curricula tailored for high-end analytics, machine learning, and quantitative finance, but MnC accepts high academic difficulty due to abstract algebra and stochastic mathematics.

--- FORBIDDEN TOPICS (NO EXTRAPOLATION) ---
- Do not invent or extrapolate recruiter presence or specific company visits.
- Do not fabricate placement packages, rates, or cutoffs.
- Do not use danger phrases: "it can be inferred", "likely", "probably", "suggests", "appears to".
- Do not convert absence of evidence (e.g. missing years or absent stats) into negative conclusions."""
        else:
            allowed_inferences_content = """--- FORBIDDEN TOPICS (NO EXTRAPOLATION) ---
- Do not invent or extrapolate recruiter presence or specific company visits.
- Do not fabricate placement packages, rates, or cutoffs.
- Do not use danger phrases: "it can be inferred", "likely", "probably", "suggests", "appears to".
- Do not convert absence of evidence (e.g. missing years or absent stats) into negative conclusions."""

        zero_claims_guidance = ""
        if not fused_claims:
            zero_claims_guidance = """
--- ZERO/EMPTY CLAIMS INSTRUCTION (CRITICAL REQUIREMENT) ---
There are currently NO factual claims available in the FUSED STRUCTURED CLAIMS source of truth.
You MUST still generate a complete structured answer with the EXACT 5 mandatory sections. Do NOT return any generic refusals or short answers.
Customize the output to target the specific query subject. Follow this format strictly:
- Under Section "### 1. Verified Institute-Specific Facts", you must output:
  * FACT: IIT Mandi was established in 2009.
  * FACT: No specific information is provided about the requested query subject in the given claims.
- Under Section "### 2. Latest Web-Enriched Developments", you must output:
  * FACT: No fresh web developments are supported by current claims regarding the query subject.
- Under Section "### 3. Grounded Interpretation", explain honestly that the absence of specific claims makes a detailed analytical comparison or evaluation challenging. Keep interpretations prefixed with "INTERPRETATION:".
- Under Section "### 4. Honest Uncertainty", you must output:
  #### Discrepancies and Contradictions
  * No discrepancies or contradictions detected in the provided claims.
  #### Data Incompleteness
  * Missing specific details for the requested query subject.
- Under Section "### 5. Final Recommendation", provide professional bulleted guidelines advising the user to consult official JoSAA portals, prefixed with "INTERPRETATION:".
"""

        prompt_content = f"""--- FUSED STRUCTURED CLAIMS (Source of Truth) ---
{claims_context}

--- DETECTED CONTRADICTIONS & DISCREPANCIES ---
{contradictions_context}

--- DATA INCOMPLETENESS & STALENESS UNCERTAINTIES ---
{uncertainties_context}

{allowed_inferences_content}
{zero_claims_guidance}

Question: {query_stripped}
Query Class: {query_class}

Answer:"""
        messages.append({"role": "user", "content": prompt_content})

        # Stage Timeout Budget (GROQ_TIMEOUT = 30.0 seconds)
        try:
            answer = await asyncio.wait_for(
                asyncio.to_thread(self._call_llm, messages),
                timeout=55.0
            )
        except asyncio.TimeoutError:
            raise RuntimeError("Response generation timed out (budget 55.0s exceeded).")
        except Exception as e:
            raise RuntimeError(f"Failed to generate answer from Groq: {e}")

        if not answer:
            logger.error("All LLM fallbacks exhausted. Returning degraded response.")
            return {
                "answer": (
                    "I'm temporarily unable to generate a response as all AI backends are under high load. "
                    "Please try again in a few minutes. For urgent queries, visit iitmandi.ac.in."
                ),
                "sources": [],
                "confidence": 0.0
            }

        # ── Step 5: Build Sources Output List ───────────────────────────
        sources = []
        seen_src = set()
        src_idx = 1
        for c in fused_claims:
            src_name = c.get("source_name", "unknown")
            if src_name not in seen_src:
                seen_src.add(src_name)
                sources.append({
                    "index": src_idx,
                    "source": src_name,
                    "confidence": float(c.get("confidence", 0.5))
                })
                src_idx += 1

        return {
            "answer": degraded_prefix + answer,
            "sources": sources,
            "confidence": float(avg_confidence)
        }


# Singleton instance
generator = RAGGenerator()


# Direct function export
async def generate_answer(query: str, confident_chunks: List[Dict[str, Any]], history: List[Dict[str, str]] = None, query_info: dict = None) -> Dict[str, Any]:
    """Generates an answer using the singleton generator."""
    return await generator.generate_answer(query, confident_chunks, history, query_info)

