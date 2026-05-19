"""
AlgoQuant Content Multiplier v1.0 — Standalone SaaS
One YouTube video → Reddit · LinkedIn · Instagram · TikTok · Twitter/X
Anonymous brand mode ON · Platform-native formatting · Image briefs included
Single file. Deploy: streamlit run content_multiplier.py
"""

import json, re, time, os, io, base64, textwrap, requests
from datetime import datetime, timedelta
from collections import Counter

import streamlit as st
import pandas as pd
import google.generativeai as genai

# ════════════════════════════════════════════════════════════
# SUPABASE CLIENT (Level 1 — Persistence)
# ════════════════════════════════════════════════════════════

def get_supabase():
    try:
        from supabase import create_client
        url = st.secrets.get("SUPABASE_URL", "")
        key = st.secrets.get("SUPABASE_KEY", "")
        if url and key:
            return create_client(url, key)
    except Exception:
        pass
    return None

def db_save(table: str, data: dict, user_id: str = None):
    sb = get_supabase()
    if not sb:
        if table not in st.session_state:
            st.session_state[table] = []
        if isinstance(st.session_state[table], list):
            st.session_state[table].append(data)
        return True
    try:
        if user_id:
            data['user_id'] = user_id
        data['created_at'] = datetime.utcnow().isoformat()
        sb.table(table).insert(data).execute()
        return True
    except Exception as e:
        st.warning(f"DB save failed: {e}")
        return False

def db_fetch(table: str, user_id: str = None, limit: int = 50):
    sb = get_supabase()
    if not sb:
        return st.session_state.get(table, [])
    try:
        q = sb.table(table).select("*").order("created_at", desc=True).limit(limit)
        if user_id:
            q = q.eq("user_id", user_id)
        return q.execute().data
    except Exception:
        return st.session_state.get(table, [])

# ════════════════════════════════════════════════════════════
# GOOGLE OAUTH (Level 2 — Multi-user Auth)
# ════════════════════════════════════════════════════════════

def get_google_auth_url():
    client_id = st.secrets.get("GOOGLE_CLIENT_ID", "")
    redirect  = st.secrets.get("REDIRECT_URI", "http://localhost:8501")
    if not client_id:
        return None
    scopes = "openid email profile"
    return (
        f"https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={client_id}"
        f"&redirect_uri={redirect}"
        f"&response_type=code"
        f"&scope={scopes}"
        f"&access_type=offline"
    )

def exchange_code_for_token(code: str):
    try:
        resp = requests.post("https://oauth2.googleapis.com/token", data={
            "code"         : code,
            "client_id"    : st.secrets.get("GOOGLE_CLIENT_ID",""),
            "client_secret": st.secrets.get("GOOGLE_CLIENT_SECRET",""),
            "redirect_uri" : st.secrets.get("REDIRECT_URI","http://localhost:8501"),
            "grant_type"   : "authorization_code",
        })
        return resp.json()
    except Exception:
        return None

def get_user_info(access_token: str):
    try:
        resp = requests.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        return resp.json()
    except Exception:
        return None

def is_logged_in():
    return bool(st.session_state.get('user'))

def get_user_id():
    user = st.session_state.get('user', {})
    return user.get('id', 'anonymous')

def login_page():
    st.markdown("""
    <div style='min-height:100vh;display:flex;align-items:center;justify-content:center;'>
    <div style='text-align:center;max-width:420px;padding:3rem;background:#111318;border:1px solid #1e2229;border-radius:20px;'>
        <div style='font-size:3rem;margin-bottom:0.5rem;'>📱</div>
        <div style='font-size:1.8rem;font-weight:700;color:#00e5a0;margin-bottom:0.25rem;'>Content Multiplier</div>
        <div style='font-size:0.82rem;color:#6b7280;margin-bottom:2rem;letter-spacing:0.08em;text-transform:uppercase;'>One Video · Five Platforms · Zero Extra Work</div>
        <div style='font-size:0.9rem;color:#9ca3af;margin-bottom:2rem;line-height:1.6;'>
            Paste your YouTube video. Get Reddit, LinkedIn, Instagram, TikTok, and Twitter posts — all platform-optimized, brand-safe, and ready to post.
        </div>
    """, unsafe_allow_html=True)

    auth_url = get_google_auth_url()
    params = st.query_params
    if "code" in params:
        with st.spinner("Signing you in..."):
            token_data = exchange_code_for_token(params["code"])
            if token_data and "access_token" in token_data:
                user_info = get_user_info(token_data["access_token"])
                if user_info:
                    st.session_state['user'] = {
                        'id'           : user_info.get('id', 'anon'),
                        'email'        : user_info.get('email', ''),
                        'name'         : user_info.get('name', 'Creator'),
                        'picture'      : user_info.get('picture', ''),
                        'access_token' : token_data.get('access_token', ''),
                    }
                    st.query_params.clear()
                    st.rerun()

    if auth_url:
        st.markdown(f"""
        <a href="{auth_url}" style='
            display:inline-block;background:#00e5a0;color:#000;
            font-weight:700;padding:0.75rem 2rem;border-radius:10px;
            text-decoration:none;font-size:0.95rem;margin-bottom:1rem;
        '>🔐 Sign in with Google</a>
        """, unsafe_allow_html=True)
    else:
        if st.button("🚀  Continue as Demo User", use_container_width=True):
            st.session_state['user'] = {
                'id': 'demo', 'email': 'demo@algoquant.studio',
                'name': 'Demo Creator', 'picture': '', 'access_token': ''
            }
            st.rerun()
        st.markdown("<div style='font-size:0.72rem;color:#6b7280;margin-top:0.5rem;'>OAuth not configured — running in demo mode</div>", unsafe_allow_html=True)

    st.markdown("</div></div>", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════
# SESSION STATE INIT
# ════════════════════════════════════════════════════════════

def init_session():
    if 'config' not in st.session_state:
        st.session_state['config'] = {
            'brand_name'     : 'AlgoQuant',
            'brand_bio'      : 'Algorithmic trading · Python · MQL5 · FTMO',
            'target_audience': 'US/EU prop firm traders, crypto quants, algo developers',
            'gemini_api_key' : '',
            'email'          : '',
        }
    try:
        if hasattr(st, 'secrets'):
            cfg = st.session_state['config']
            if 'GEMINI_API_KEY' in st.secrets and not cfg.get('gemini_api_key'):
                cfg['gemini_api_key'] = st.secrets['GEMINI_API_KEY']
    except Exception:
        pass

# ════════════════════════════════════════════════════════════
# PAGE CONFIG & CSS
# ════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="Content Multiplier",
    page_icon="📱",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
:root {
  --bg:#0a0c10;--surface:#111318;--border:#1e2229;
  --accent:#00e5a0;--accent2:#0066ff;--warn:#ff6b35;
  --text:#e8eaf0;--muted:#6b7280;
  --green:#00e5a0;--red:#ff4560;--yellow:#ffd700;
}
html,body,[data-testid="stAppViewContainer"]{background:var(--bg)!important;color:var(--text)!important;font-family:'Space Grotesk',sans-serif!important;}
[data-testid="stSidebar"]{background:var(--surface)!important;border-right:1px solid var(--border)!important;}
[data-testid="stSidebar"] *{color:var(--text)!important;}
h1,h2,h3,h4{font-family:'Space Grotesk',sans-serif!important;color:var(--text)!important;font-weight:700!important;}
.stButton>button{background:var(--accent)!important;color:#000!important;border:none!important;border-radius:8px!important;font-weight:600!important;font-family:'Space Grotesk',sans-serif!important;padding:0.5rem 1.5rem!important;transition:all 0.2s!important;}
.stButton>button:hover{transform:translateY(-1px)!important;box-shadow:0 4px 20px rgba(0,229,160,0.3)!important;}
.stTextInput>div>div>input,.stTextArea>div>div>textarea,.stSelectbox>div>div{background:var(--surface)!important;border:1px solid var(--border)!important;color:var(--text)!important;border-radius:8px!important;}
.stTabs [data-baseweb="tab-list"]{background:var(--surface)!important;border-radius:8px;}
.stTabs [data-baseweb="tab"]{color:var(--muted)!important;}
.stTabs [aria-selected="true"]{color:var(--accent)!important;}
.metric-card{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:1.25rem 1.5rem;position:relative;overflow:hidden;}
.metric-card::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:var(--accent);}
.metric-val{font-size:2rem;font-weight:700;color:var(--accent);line-height:1;margin-bottom:0.25rem;}
.metric-lbl{font-size:0.8rem;color:var(--muted);text-transform:uppercase;letter-spacing:0.08em;}
.video-card{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:1rem 1.25rem;margin-bottom:0.75rem;transition:border-color 0.2s;}
.video-card:hover{border-color:var(--accent);}
.score-badge{display:inline-block;padding:0.2rem 0.6rem;border-radius:20px;font-size:0.75rem;font-weight:600;}
.score-green{background:rgba(0,229,160,0.15);color:var(--green);}
.score-yellow{background:rgba(255,215,0,0.15);color:var(--yellow);}
.score-red{background:rgba(255,69,96,0.15);color:var(--red);}
.section-header{font-size:0.7rem;text-transform:uppercase;letter-spacing:0.12em;color:var(--muted);margin-bottom:0.75rem;margin-top:1.5rem;}
.tag{display:inline-block;background:rgba(0,102,255,0.15);color:#60a5fa;border:1px solid rgba(0,102,255,0.3);border-radius:4px;padding:0.15rem 0.5rem;font-size:0.72rem;margin:0.15rem;}
.funnel-badge{display:inline-block;padding:0.2rem 0.7rem;border-radius:20px;font-size:0.72rem;font-weight:600;background:rgba(255,107,53,0.15);color:var(--warn);}
.step-box{background:var(--surface);border:1px solid var(--border);border-left:3px solid var(--accent);border-radius:0 8px 8px 0;padding:0.75rem 1rem;margin-bottom:0.5rem;}
.script-block{background:#0d1117;border:1px solid var(--border);border-radius:8px;padding:1rem 1.25rem;font-family:'JetBrains Mono',monospace;font-size:0.82rem;color:#c9d1d9;line-height:1.7;white-space:pre-wrap;}
.divider{border:none;border-top:1px solid var(--border);margin:1.25rem 0;}
#MainMenu,footer,header{visibility:hidden;}
</style>
""", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════
# INIT + AUTH GATE
# ════════════════════════════════════════════════════════════

init_session()
has_oauth = bool(st.secrets.get("GOOGLE_CLIENT_ID", "")) if hasattr(st, 'secrets') else False

if has_oauth and not is_logged_in():
    login_page()
    st.stop()
elif not is_logged_in():
    st.session_state['user'] = {'id': 'demo', 'email': '', 'name': 'Creator', 'picture': '', 'access_token': ''}

cfg     = st.session_state['config']
user    = st.session_state.get('user', {})
user_id = user.get('id', 'demo')

# ════════════════════════════════════════════════════════════
# ENGINE — AI + PLATFORM LOGIC
# ════════════════════════════════════════════════════════════

PLATFORM_CONTEXTS = {
    'reddit': """
Reddit rules: Community r/algotrading r/quant r/CryptoCurrency r/Forex.
Tone: Technical honest peer-to-peer. Never promotional.
Format: Title + body paragraphs + code mention if relevant.
End with genuine question to drive discussion.
Never say check out my channel — say casually "posted a full breakdown video if anyone wants to go deeper".
Length: 200-400 words.
""",
    'linkedin': """
LinkedIn rules: Finance professionals investors trading firms developers.
Tone: Professional but personal. First person narrative.
Format: Hook line → 3-4 short paragraphs → lesson → question.
No code. Translate technical to business language.
Use line breaks generously. End with question.
Length: 150-250 words.
""",
    'instagram': """
Instagram rules: Young traders crypto investors aspiring quants.
Tone: Punchy inspiring real. Short sentences.
Format: Hook first line must stop scroll → 3-4 short sentences → CTA.
End with Follow for more algo content.
Add 25-30 relevant hashtags at end.
Length: 80-120 words + hashtags.
""",
    'tiktok': """
TikTok rules: Young traders crypto audience curious learners.
Tone: Fast energetic surprising. Result in first 2 seconds.
Format: Hook → show the thing → payoff → CTA to follow.
First sentence must be shocking or counterintuitive.
End with Follow for more or Part 2 coming.
Length: 80-100 words maximum.
""",
    'twitter': """
Twitter/X rules: Traders developers quants finance Twitter.
Tone: Direct confident slightly provocative.
Format: 8 tweets. Tweet 1 is hook. Tweets 2-7 are points. Tweet 8 is CTA.
Each tweet under 280 characters. Number them 1/ 2/ 3/ etc.
End with Follow for daily algo trading insights.
"""
}

def get_model():
    key = cfg.get('gemini_api_key', '')
    if not key:
        return None
    genai.configure(api_key=key)
    # ✅ Using gemini-2.0-flash (current stable fast model)
    # Note: gemini-3.1-flash-lite is not publicly available yet
    return genai.GenerativeModel('gemini-3.1-flash-lite')

def call_gemini(model, prompt, max_tokens=2000):
    for attempt in range(2):
        try:
            resp = model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=max_tokens, temperature=0.7),
                request_options={"timeout": 120}
            )
            raw = resp.text.strip()
            raw = re.sub(r'```json|```', '', raw).strip()
            o, c = raw.count('{'), raw.count('}')
            if o > c: raw += '}' * (o - c)
            return json.loads(raw)
        except Exception as e:
            if attempt == 0: time.sleep(3)
            else: raise e

def build_context():
    return f"""
Brand: {cfg.get('brand_name','AlgoQuant')}
Bio: {cfg.get('brand_bio','Algorithmic trading · Python · MQL5 · FTMO')}
Target: {cfg.get('target_audience','US/EU prop firm traders, crypto quants, algo developers')}

Brand rules — CRITICAL:
- Never reveal real name, location, or personal details
- Write as AlgoQuant brand persona only
- Lean into honest failure content — it performs best
- Never mention Morocco or any personal identifiers
- Target US and European traders primarily
"""

def ai_content_multiplier(model, title, script, platforms, ctx):
    platform_instructions = '\n'.join([f"Platform {p.upper()}:\n{PLATFORM_CONTEXTS[p]}" for p in platforms])
    platform_schema = ', '.join([f'"{p}": {{"post_text": "full post", "character_count": 0, "best_time_to_post": "day time EST", "target_community": "where to post"}}' for p in platforms])
    return call_gemini(model, f"""
You are a social media content strategist for algorithmic trading.
{ctx}

BRAND RULES — CRITICAL:
- Brand: AlgoQuant. Never reveal real name or location.
- Never mention Morocco. Write as AlgoQuant brand persona.
- Target: US and Europe traders.
- Honest failure angle performs best — lean into it.

YouTube title: {title}
Script: {script[:1500]}

Platform instructions:
{platform_instructions}

Each post must be standalone, drive YouTube traffic naturally, match platform culture.

Return ONLY valid JSON no markdown:
{{{platform_schema}}}
""", 3000)

def ai_image_brief(model, title, platform, style, ctx):
    specs = {
        'reddit'  : '1200x628px informational',
        'linkedin': '1200x627px horizontal professional clean',
        'instagram': '1080x1080px square bold colorful',
        'tiktok'  : '1080x1920px vertical dark neon',
        'twitter' : '1200x675px horizontal simple bold',
    }
    return call_gemini(model, f"""
Social media graphic designer for algorithmic trading.
{ctx}
Title: {title}
Platform: {platform}
Spec: {specs.get(platform,'')}
Style: {style}

Return ONLY valid JSON no markdown:
{{"platform":"{platform}","dimensions":"{specs.get(platform,'').split(' ')[0]}","concept":"one sentence","background":"color with hex","main_text":"max 5 words","sub_text":"3 words or null","visual_element":"describe exactly","color_palette":["#hex1","#hex2","#hex3"],"layout":"step by step","canva_steps":"numbered steps under 15 min","ai_image_prompt":"prompt for Pollinations AI","predicted_engagement":"estimate"}}
""", 800)

def generate_image(prompt_text, platform):
    try:
        encoded = requests.utils.quote(prompt_text[:500])
        w, h = ("1080","1080") if platform in ['instagram','tiktok'] else ("1280","720")
        url = f"https://image.pollinations.ai/prompt/{encoded}?width={w}&height={h}&nologo=true"
        resp = requests.get(url, timeout=30)
        if resp.status_code == 200:
            return resp.content
    except Exception:
        pass
    return None

# ════════════════════════════════════════════════════════════
# MAIN PAGE (FIXED STATE MANAGEMENT)
# ════════════════════════════════════════════════════════════

def main():
    # Initialize session state for inputs to survive refresh
    if 'cm_title' not in st.session_state: st.session_state['cm_title'] = ""
    if 'cm_script' not in st.session_state: st.session_state['cm_script'] = ""
    if 'generated_results' not in st.session_state: st.session_state['generated_results'] = None

    st.markdown("""
    <h1 style='font-size:1.8rem;margin-bottom:0.25rem;'>📱 Content Multiplier</h1>
    <p style='color:#6b7280;font-size:0.9rem;margin-bottom:0.5rem;'>One YouTube video → Reddit · LinkedIn · Instagram · TikTok · Twitter. All platform-optimized.</p>
    <div style='background:rgba(0,102,255,0.1);border:1px solid rgba(0,102,255,0.3);border-radius:8px;padding:0.6rem 1rem;margin-bottom:2rem;font-size:0.78rem;color:#60a5fa;'>
        🔒 <b>Anonymous mode ON</b> — All content uses AlgoQuant brand. No personal info revealed.
    </div>
    """, unsafe_allow_html=True)

    if not cfg.get('gemini_api_key',''):
        st.warning("⚠️  Add Gemini API key in Settings.")
        return

    section("Your YouTube Video")
    col1, col2 = st.columns([2,1])
    with col1:
        yt_title = st.text_input("Video title", value=st.session_state['cm_title'], placeholder="I Turned $10k Into $26k (Then Lost It All)", key="cm_title")
    with col2:
        recent = st.selectbox("Or pick recent", [
            "Select...",
            "I Turned $10k Into $26k (Then Lost It All) part 2",
            "3 Traps That Make Crypto Strategies Look Profitable",
            "WARNING: Your Python Backtest Is Hiding Real Losses",
            "I Backtested the Triple EMA: It's a Trap",
        ], key="cm_recent")
        if recent != "Select..." and not yt_title:
            st.session_state['cm_title'] = recent
            yt_title = recent

    yt_script = st.text_area("Paste script or description (first 500 words enough)", 
        value=st.session_state['cm_script'], height=120, placeholder="Paste from Video Factory...", key="cm_script")

    section("Select Platforms")
    col_r,col_l,col_i,col_t,col_x = st.columns(5)
    platforms = []
    platform_meta = [
        (col_r, 'reddit',    'Reddit',    'r/algotrading\nr/quant'),
        (col_l, 'linkedin',  'LinkedIn',  'Professional\nB2B'),
        (col_i, 'instagram', 'Instagram', 'Feed+Stories\nReels'),
        (col_t, 'tiktok',    'TikTok',    'Script for\nshort video'),
        (col_x, 'twitter',   'Twitter/X', '8-tweet\nthread'),
    ]
    defaults = {'reddit':True,'linkedin':True,'instagram':True,'tiktok':True,'twitter':False}
    for col, key, label, desc in platform_meta:
        with col:
            if st.checkbox(label, value=defaults[key], key=f"p_{key}"):
                platforms.append(key)
            st.markdown(f"<div style='font-size:0.68rem;color:#6b7280;'>{desc}</div>", unsafe_allow_html=True)

    col_s, col_t2 = st.columns(2)
    with col_s: style = st.selectbox("Image style", ["dark minimal","dark dramatic","green success","red warning","data clean"], key="img_style")
    with col_t2: tone = st.selectbox("Tone", ["honest failure (recommended)","technical","results","educational"], key="tone_select")

    # Main Generation Button
    if st.button(f"⚡  Generate for {len(platforms)} Platform{'s' if len(platforms)>1 else ''}", use_container_width=True, key="main_gen_btn"):
        if not yt_title.strip() or not yt_script.strip():
            st.error("Please enter a title and script first.")
        elif not platforms:
            st.warning("Select at least one platform.")
        else:
            model = get_model()
            ctx   = build_context()
            with st.spinner(f"Generating content for {', '.join(platforms)}..."):
                try:
                    # Generate content
                    results = ai_content_multiplier(model, yt_title, yt_script, platforms, ctx)
                    # Save to session state so it survives refresh
                    st.session_state['generated_results'] = results
                    st.session_state['last_platforms'] = platforms
                    st.rerun() # Force refresh to show results cleanly
                except Exception as e:
                    st.error(str(e))

    # Display Results (Loaded from Session State)
    if st.session_state.get('generated_results'):
        results = st.session_state['generated_results']
        platforms = st.session_state.get('last_platforms', [])
        
        st.markdown("<hr class='divider'>", unsafe_allow_html=True)
        st.markdown(f"<div style='background:rgba(0,229,160,0.05);border:1px solid rgba(0,229,160,0.2);border-radius:10px;padding:0.75rem 1rem;margin-bottom:1.5rem;'><span style='color:#00e5a0;font-weight:700;'>✅ Content Ready</span></div>", unsafe_allow_html=True)

        ICONS   = {'reddit':'🟠','linkedin':'🔵','instagram':'🟣','tiktok':'⚫','twitter':'🐦'}
        COLORS  = {'reddit':'#FF4500','linkedin':'#0077B5','instagram':'#E1306C','tiktok':'#00f2ea','twitter':'#1DA1F2'}

        for platform in platforms:
            data       = results.get(platform, {})
            post_text  = data.get('post_text','')
            char_count = data.get('character_count', len(post_text))
            best_time  = data.get('best_time_to_post','')
            target_c   = data.get('target_community','')
            icon       = ICONS.get(platform,'📱')
            color      = COLORS.get(platform,'#00e5a0')

            st.markdown(f"""
            <div style='background:var(--surface);border:1px solid var(--border);border-top:3px solid {color};border-radius:12px;padding:1.25rem 1.5rem;margin-bottom:0.5rem;'>
                <div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;'>
                    <div style='display:flex;align-items:center;gap:0.5rem;'>
                        <span style='font-size:1.2rem;'>{icon}</span>
                        <span style='font-size:0.9rem;font-weight:700;color:{color};text-transform:uppercase;'>{platform}</span>
                    </div>
                    <div style='font-size:0.72rem;color:#6b7280;'>📍 {target_c} · 🕐 {best_time}</div>
                </div>
            </div>""", unsafe_allow_html=True)

            st.text_area(f"{platform.title()} post — copy this", value=post_text, height=200 if platform in ['reddit','twitter'] else 150, key=f"post_{platform}", label_visibility='collapsed')

            # Image Brief Logic
            col_img, _ = st.columns([1,2])
            with col_img:
                if st.button(f"🖼️  Image Brief", key=f"img_btn_{platform}"):
                    model = get_model()
                    ctx = build_context()
                    title = st.session_state.get('cm_title', 'Trading Strategy')
                    style = st.session_state.get('img_style', 'dark minimal')
                    with st.spinner(f"Generating {platform} brief..."):
                        try:
                            ib = ai_image_brief(model, title, platform, style, ctx)
                            st.session_state[f'ib_{platform}'] = ib
                            st.rerun()
                        except Exception as e: st.error(str(e))

            # Show Brief if exists
            if f'ib_{platform}' in st.session_state:
                ib = st.session_state[f'ib_{platform}']
                c_html = ''.join([f"<span style='display:inline-block;width:18px;height:18px;border-radius:3px;background:{c};margin-right:3px;vertical-align:middle;'></span>" for c in ib.get('color_palette',[])])
                st.markdown(f"""
                <div style='background:#0d1117;border:1px solid {color};border-radius:8px;padding:1rem;margin-top:0.5rem;margin-bottom:0.75rem;'>
                    <div style='font-size:0.72rem;color:{color};font-weight:700;text-transform:uppercase;margin-bottom:8px;'>Image Brief — {platform.title()} {ib.get('dimensions','')}</div>
                    <div style='font-size:0.85rem;font-weight:600;margin-bottom:4px;'>"{ib.get('main_text','')}"</div>
                    {f"<div style='font-size:0.75rem;color:#6b7280;margin-bottom:4px;'>Sub: {ib.get('sub_text','')}</div>" if ib.get('sub_text') else ''}
                    <div style='margin-bottom:8px;'>{c_html}</div>
                    <div style='font-size:0.75rem;font-weight:600;margin-bottom:4px;'>Canva steps:</div>
                    <div style='font-size:0.72rem;color:#9ca3af;line-height:1.6;'>{ib.get('canva_steps','')}</div>
                </div>""", unsafe_allow_html=True)

                if st.button(f"🎨  Generate Image (Free AI)", key=f"gen_btn_{platform}"):
                    img_prompt = ib.get('ai_image_prompt', f"professional trading dark background {st.session_state.get('cm_title')}")
                    with st.spinner("Generating via Pollinations AI..."):
                        try:
                            encoded = requests.utils.quote(img_prompt[:500])
                            w, h = ("1080","1080") if platform in ['instagram','tiktok'] else ("1280","720")
                            url  = f"https://image.pollinations.ai/prompt/{encoded}?width={w}&height={h}&nologo=true"
                            resp = requests.get(url, timeout=30)
                            if resp.status_code == 200:
                                st.image(resp.content, caption=f"{platform.title()} — add text in Canva")
                                st.download_button(f"⬇️  Download", resp.content,
                                    file_name=f"{platform}_{datetime.now().strftime('%Y%m%d_%H%M')}.jpg",
                                    mime="image/jpeg", key=f"dl_{platform}")
                            else: st.error("Failed. Build manually in Canva using brief above.")
                        except Exception as e: st.error(str(e))

            st.markdown("<div style='margin-bottom:1.5rem;'></div>", unsafe_allow_html=True)

        # Save to DB
        db_save('content_posts', {'user_id':user_id,'title':yt_title,'platforms':json.dumps(platforms),'content':json.dumps(results),'status':'generated'}, user_id)

        # Schedule & Checklist
        st.markdown("<hr class='divider'>", unsafe_allow_html=True)
        section("Recommended Posting Schedule")
        schedule = [
            ("Monday",    "📺 YouTube",    "Upload video with full SEO tags"),
            ("Tuesday",   "🟠 Reddit",     "Post to r/algotrading — technical breakdown"),
            ("Wednesday", "🔵 LinkedIn",   "Professional narrative — best B2B day"),
            ("Thursday",  "🟣 Instagram",  "Image post — Thursday 6pm EST is peak"),
            ("Friday",    "⚫ TikTok",     "Upload short video with generated script"),
        ]
        for day, plat_, action in schedule:
            st.markdown(f"<div style='display:flex;align-items:center;gap:1rem;padding:0.5rem 0;border-bottom:1px solid var(--border);'><span style='font-size:0.78rem;font-weight:600;color:#6b7280;min-width:80px;'>{day}</span><span style='font-size:0.78rem;font-weight:600;min-width:110px;'>{plat_}</span><span style='font-size:0.78rem;color:#9ca3af;'>{action}</span></div>", unsafe_allow_html=True)

        st.markdown("""
        <div style='background:rgba(255,107,53,0.08);border:1px solid rgba(255,107,53,0.3);border-radius:10px;padding:1rem 1.25rem;margin-top:1.5rem;'>
            <div style='font-size:0.82rem;font-weight:700;color:#ff6b35;margin-bottom:8px;'>🔒 Anonymous Posting Checklist</div>
            <div style='font-size:0.75rem;color:#9ca3af;line-height:1.9;'>
                ✅ Post from algoquant.trading@gmail.com accounts only<br>
                ✅ AlgoQuant logo as profile picture on all platforms<br>
                ✅ Location blank or United States everywhere<br>
                ✅ Never mention Morocco or personal details<br>
                ✅ Bio: "Algorithmic trading · Python · MQL5 · FTMO"<br>
                ✅ Link in bio → YouTube channel only
            </div>
        </div>
        """, unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════
# LAUNCH
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":
    main()
