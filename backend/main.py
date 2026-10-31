from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from pathlib import Path
from typing import Optional
import sqlite3, json, uuid, hashlib, random, os, shutil, subprocess, time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
UPLOADS = DATA / "uploads"
DB = DATA / "viralsim.db"
UPLOADS.mkdir(parents=True, exist_ok=True)
MAX_BYTES = 200 * 1024 * 1024
ALLOWED = {'.mp4', '.mov', '.webm', '.m4v', '.avi'}
app = FastAPI(title="ViralSim AI API", version="0.1.0", description="Video audience simulation API. Estimates are synthetic and not platform analytics.")
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000").split(','), allow_credentials=False, allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["Content-Type"])


def connect():
    con = sqlite3.connect(DB); con.row_factory = sqlite3.Row; return con

def init_db():
    with connect() as c:
        c.executescript('''CREATE TABLE IF NOT EXISTS videos(id TEXT PRIMARY KEY, filename TEXT NOT NULL, stored_name TEXT NOT NULL, size INTEGER, duration REAL, platform TEXT, category TEXT, objective TEXT, target TEXT, status TEXT, analysis TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, video_id TEXT NOT NULL, status TEXT NOT NULL, config TEXT, report TEXT, seed INTEGER, created_at TEXT, finished_at TEXT, FOREIGN KEY(video_id) REFERENCES videos(id));''')
init_db()

PERSONAS = [
 {"id":"tech","name":"Tech Enthusiast","emoji":"◈","age":"25–34","interests":["innovation","specs","use cases"],"familiarity":"High","price":"Medium","attention":"Stays for concrete demonstrations","motivation":"Find useful differentiators","objection":"Vague claims without proof","style":"Analytical"},
 {"id":"casual","name":"Casual Scroller","emoji":"◉","age":"18–34","interests":["entertainment","quick tips","visual hooks"],"familiarity":"Low","price":"Medium","attention":"Decides quickly in opening seconds","motivation":"Instant relevance","objection":"Slow setup or confusing context","style":"Impatient"},
 {"id":"practical","name":"Practical Buyer","emoji":"▣","age":"28–44","interests":["utility","quality","reviews"],"familiarity":"Medium","price":"High","attention":"Watches when benefits are specific","motivation":"Solve a real problem","objection":"Unclear value for money","style":"Outcome-led"},
 {"id":"skeptic","name":"Skeptical Shopper","emoji":"◇","age":"25–44","interests":["evidence","comparisons","authenticity"],"familiarity":"Medium","price":"High","attention":"Looks for proof and caveats","motivation":"Reduce purchase risk","objection":"Overstated promises","style":"Evidence-seeking"},
 {"id":"trend","name":"Trend Follower","emoji":"✳","age":"18–29","interests":["creators","trends","shareable moments"],"familiarity":"Low–Medium","price":"Low","attention":"Responds to novelty and momentum","motivation":"Discover what is current","objection":"Feels dated or overly polished","style":"Social-first"},
 {"id":"budget","name":"Budget-Conscious","emoji":"⌁","age":"24–44","interests":["deals","durability","alternatives"],"familiarity":"Medium","price":"Very high","attention":"Prioritizes practical value","motivation":"Get more for less","objection":"Price without justification","style":"Value-focused"},
 {"id":"loyal","name":"Brand Loyalist","emoji":"✦","age":"25–54","interests":["brand updates","community","new releases"],"familiarity":"High","price":"Low–Medium","attention":"Watches familiar brands longer","motivation":"Stay connected to a trusted brand","objection":"Inconsistent brand promise","style":"Relationship-led"},
 {"id":"impulse","name":"Impulse Explorer","emoji":"↗","age":"18–34","interests":["visual appeal","novelty","easy wins"],"familiarity":"Low","price":"Medium","attention":"Responds to immediate payoff","motivation":"Feel an immediate desire","objection":"Too many steps to act","style":"Emotion-led"}
]

class SimConfig(BaseModel):
    platform: str = "Instagram Reels"
    category: str = "Technology"
    objective: str = "Retention"
    audience_size: int = Field(100, ge=8, le=5000)
    rounds: int = Field(3, ge=1, le=10)
    age_range: str = "18–34"
    interests: list[str] = []
    geography: str = "Global"
    product_familiarity: str = "Mixed"
    seed: Optional[int] = None

class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1000)

class ActualPerformance(BaseModel):
    views: Optional[int] = Field(default=None, ge=0)
    average_watch_seconds: Optional[float] = Field(default=None, ge=0)
    likes: Optional[int] = Field(default=None, ge=0)
    shares: Optional[int] = Field(default=None, ge=0)
    saves: Optional[int] = Field(default=None, ge=0)
    notes: Optional[str] = Field(default=None, max_length=2000)


def now(): return datetime.now(timezone.utc).isoformat()
def rowdict(r): return dict(r) if r else None

def ffprobe(path: Path):
    exe = shutil.which('ffprobe')
    if not exe: return None
    try:
        p = subprocess.run([exe,'-v','error','-show_entries','format=duration:stream=codec_type,width,height','-of','json',str(path)],capture_output=True,text=True,timeout=20,check=True)
        raw=json.loads(p.stdout); duration=float(raw.get('format',{}).get('duration') or 0)
        video=next((s for s in raw.get('streams',[]) if s.get('codec_type')=='video'),{})
        return {"duration_seconds":round(duration,2),"width":video.get('width'),"height":video.get('height'),"metadata_source":"ffprobe"}
    except Exception: return None

def safe_json(value):
    try: return json.loads(value) if value else None
    except Exception: return None

@app.get('/api/health')
def health(): return {"status":"ok","service":"viralsim-api","time":now(),"ffmpeg_available":bool(shutil.which('ffprobe')),"llm_configured":bool(os.getenv('OPENAI_API_KEY'))}

@app.post('/api/videos/upload')
async def upload_video(file: UploadFile = File(...)):
    suffix=Path(file.filename or '').suffix.lower()
    if suffix not in ALLOWED: raise HTTPException(415, f"Unsupported video type. Allowed: {', '.join(sorted(ALLOWED))}")
    vid=str(uuid.uuid4()); stored=f"{vid}{suffix}"; dest=UPLOADS/stored; total=0; header=bytearray()
    try:
        with dest.open('wb') as out:
            while True:
                chunk=await file.read(1024*1024)
                if not chunk: break
                total+=len(chunk)
                if len(header)<32: header.extend(chunk[:32-len(header)])
                if total>MAX_BYTES: raise HTTPException(413,'Video exceeds the 200 MB upload limit.')
                out.write(chunk)
        if total==0: raise HTTPException(400,'The uploaded file is empty.')
        valid_signature = (b'ftyp' in bytes(header[:16]) if suffix in {'.mp4','.mov','.m4v'} else (bytes(header).startswith(b'\x1a\x45\xdf\xa3') if suffix=='.webm' else (bytes(header).startswith(b'RIFF') and b'AVI ' in bytes(header[:16])) if suffix=='.avi' else False))
        if not valid_signature: raise HTTPException(415,'The file signature does not match a supported video container.')
        metadata=ffprobe(dest) or {"duration_seconds":None,"width":None,"height":None,"metadata_source":"unavailable; install ffmpeg for metadata extraction"}
        with connect() as c:
            c.execute('INSERT INTO videos VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(vid,Path(file.filename).name,stored,total,metadata.get('duration_seconds'),None,None,None,None,'uploaded',json.dumps(metadata),now()))
        return {"id":vid,"filename":Path(file.filename).name,"size_bytes":total,"status":"uploaded","metadata":metadata,"notice":"Video stored locally. Analysis extracts available technical metadata; semantic scene, audio and transcript analysis requires configured media/AI providers."}
    except Exception:
        dest.unlink(missing_ok=True); raise
    finally: await file.close()

@app.get('/api/videos')
def list_videos():
    with connect() as c: rows=c.execute('SELECT id,filename,size,duration,platform,category,objective,status,created_at FROM videos ORDER BY created_at DESC').fetchall()
    return {"videos":[dict(r) for r in rows]}

@app.get('/api/videos/{video_id}')
def get_video(video_id:str):
    with connect() as c: r=c.execute('SELECT * FROM videos WHERE id=?',(video_id,)).fetchone()
    if not r: raise HTTPException(404,'Video not found')
    d=dict(r); d['analysis']=safe_json(d.get('analysis')); d.pop('stored_name',None); return d

@app.post('/api/videos/{video_id}/analyze')
def analyze_video(video_id:str):
    with connect() as c: r=c.execute('SELECT * FROM videos WHERE id=?',(video_id,)).fetchone()
    if not r: raise HTTPException(404,'Video not found')
    duration=r['duration'] or 24.0
    # Timeline is explicitly heuristic unless a configured multimodal provider supplies grounded timestamps.
    marks=[(0.0,'Opening hook','First impression and immediate relevance'),(min(3.0,duration*.15),'Problem introduction','Context and problem clarity'),(min(7.0,duration*.32),'Product reveal','Product visibility and novelty'),(min(12.0,duration*.52),'Demonstration','Evidence, use and pacing'),(min(18.0,duration*.76),'Benefits','Value proposition and differentiation'),(max(0.0,duration-3.0),'Call to action','Closing instruction and next step')]
    timeline=[]
    for sec,title,desc in marks:
        if not timeline or sec>timeline[-1]['seconds']:
            timeline.append({"seconds":round(sec,2),"timestamp":f"{int(sec//60):02d}:{int(sec%60):02d}","title":title,"description":desc,"source":"heuristic placeholder; not visually verified"})
    analysis={"duration_seconds":r['duration'],"metadata":safe_json(r['analysis']),"timeline":timeline,"signals":{"semantic_scene_detection":"not configured","speech_transcription":"not configured","on_screen_text":"not configured","product_visibility":"not configured","hook_quality":"requires video understanding model"},"status":"metadata_ready","limitations":["Scene labels are provisional timeline anchors, not detected scenes.","No audio, transcript, frames, or product visibility claims are inferred without a configured media-analysis pipeline."]}
    with connect() as c: c.execute('UPDATE videos SET status=?,analysis=? WHERE id=?',('analyzed',json.dumps(analysis),video_id))
    return {"video_id":video_id,"status":"analyzed","analysis":analysis}

@app.get('/api/personas')
def personas(): return {"personas":PERSONAS}

def run_simulation(run_id, video_id, config):
    try:
        with connect() as c:
            c.execute('UPDATE runs SET status=? WHERE id=?',('running',run_id))
            video=c.execute('SELECT * FROM videos WHERE id=?',(video_id,)).fetchone()
        duration=float(video['duration'] or 24)
        seed=config.get('seed') or int(hashlib.sha256(f"{video_id}:{json.dumps(config,sort_keys=True)}".encode()).hexdigest()[:8],16)
        rng=random.Random(seed)
        n=config.get('audience_size',100); rounds=config.get('rounds',3)
        category=(config.get('category') or video['category'] or 'Technology').lower()
        objective=config.get('objective','Retention')
        cat_bonus=0.025 if category in ('technology','tech','beauty','fashion','food') else 0
        hook=rng.uniform(.48,.82)+cat_bonus
        if duration>35: hook-=min(.14,(duration-35)/220)
        retention=[]
        for i in range(11):
            t=duration*i/10 if duration else i
            decay=(i/10)*(0.34+rng.uniform(-.045,.045))
            retention.append({"seconds":round(t,1),"timestamp":f"{int(t//60):02d}:{int(t%60):02d}","retention":round(max(.08,min(.98,hook-decay)),3)})
        cohorts=[]
        per=[]
        weighted=[]
        for idx,p in enumerate(PERSONAS):
            base=max(.12,min(.93,hook + rng.uniform(-.15,.15) + (0.04 if p['id'] in ('tech','practical') and category in ('technology','tech') else 0)))
            completion=max(.04,min(.84,base-(.24 if duration>20 else .13)+rng.uniform(-.06,.06)))
            skip=max(.04,min(.75,1-base+rng.uniform(-.05,.05)))
            weight=n//len(PERSONAS)+(1 if idx<n%len(PERSONAS) else 0)
            cohort={"persona_id":p['id'],"persona":p['name'],"count":weight,"retention":round(base,3),"completion":round(completion,3),"skip":round(skip,3),"interest":round(max(.1,min(.95,base+rng.uniform(-.08,.08))),3),"reaction":rng.choice(["The opening feels relevant, but show the payoff sooner.","The demonstration helps make the value concrete.","I need stronger evidence before I believe the claim.","Clear visual storytelling makes this easy to follow.","The next step could be more specific."]),"reasoning_basis":"Synthetic persona preference and configured category; not observed human feedback."}
            cohorts.append(cohort)
            per.append({"persona_id":p['id'],"persona":p['name'],"count":weight,"action_probabilities":{"continue":round(base,3),"skip":round(skip,3),"finish":round(completion,3),"like":round(max(.03,base*.38+rng.uniform(-.04,.04)),3),"save":round(max(.02,base*.22+rng.uniform(-.03,.03)),3),"share":round(max(.01,base*.16+rng.uniform(-.025,.025)),3),"comment":round(max(.01,base*.12+rng.uniform(-.02,.02)),3),"profile_visit":round(max(.01,base*.14+rng.uniform(-.025,.025)),3)},"reaction":cohort['reaction'],"reasoning_basis":cohort['reasoning_basis']})
            weighted.append((base,weight))
        retention_avg=sum(v*w for v,w in weighted)/max(1,sum(w for _,w in weighted))
        completion_avg=sum(x['completion']*x['count'] for x in cohorts)/max(1,n)
        skip_avg=sum(x['skip']*x['count'] for x in cohorts)/max(1,n)
        eng={"likes":round(max(.01,retention_avg*.32+rng.uniform(-.025,.025)),3),"saves":round(max(.01,retention_avg*.2+rng.uniform(-.02,.02)),3),"shares":round(max(.01,retention_avg*.14+rng.uniform(-.02,.02)),3),"comments":round(max(.01,retention_avg*.11+rng.uniform(-.02,.02)),3),"profile_visits":round(max(.01,retention_avg*.13+rng.uniform(-.02,.02)),3)}
        recs=[{"priority":"high","timestamp":"00:00","issue":"Opening-hook strength is not verified","suggestion":"Test a cut that shows the product payoff or a specific problem in the first 1–3 seconds.","audience":"Casual Scroller, Impulse Explorer","impact":None,"basis":"General creative hypothesis; not derived from detected frames."},{"priority":"high","timestamp":f"{int(duration*.45//60):02d}:{int(duration*.45%60):02d}","issue":"Mid-video value clarity needs validation","suggestion":"Bring the clearest benefit and a visible proof point forward; remove setup that does not advance the demonstration.","audience":"Practical Buyer, Skeptical Shopper","impact":None,"basis":"General creative hypothesis; not derived from transcript or scene detection."},{"priority":"medium","timestamp":f"{int(max(0,duration-3)//60):02d}:{int(max(0,duration-3)%60):02d}","issue":"Call-to-action clarity is unverified","suggestion":"Close with one concrete next step and a reason to take it now.","audience":"Practical Buyer, Budget-Conscious Customer","impact":None,"basis":"General creative hypothesis; not derived from detected on-screen text."}]
        report={"run_id":run_id,"video_id":video_id,"status":"completed","mode":"heuristic_synthetic_estimate","is_demo_or_heuristic":True,"notice":"These are uncalibrated synthetic estimates from a transparent heuristic, not predictions validated against real viewers or platform algorithms.","config":config,"seed":seed,"model_version":"viralsim-heuristic-0.1","summary":{"estimated_retention":round(retention_avg,3),"estimated_completion_probability":round(completion_avg,3),"estimated_skip_probability":round(skip_avg,3),"audience_size":n,"rounds":rounds,"objective":objective},"retention_curve":retention,"engagement_probabilities":eng,"cohorts":cohorts,"persona_responses":per,"recommendations":recs,"distribution":{"model":"simplified hypothetical cohort expansion","platform_algorithm_replica":False,"cohorts":[{"name":"Initial target audience","relative_response":round(retention_avg,3)},{"name":"Adjacent interest audience","relative_response":round(max(.05,retention_avg-.09),3)},{"name":"Broad discovery audience","relative_response":round(max(.05,retention_avg-.18),3)}]},"uncertainty":{"available":False,"reason":"No calibration dataset or statistical sampling model is configured; no confidence interval is asserted."},"provenance":{"analysis":"metadata only unless external video-analysis services are configured","simulation":"seeded heuristic cohort estimates","actual_performance":"not supplied"}}
        with connect() as c: c.execute('UPDATE runs SET status=?,report=?,finished_at=? WHERE id=?',('completed',json.dumps(report),now(),run_id))
    except Exception as e:
        with connect() as c: c.execute('UPDATE runs SET status=?,report=?,finished_at=? WHERE id=?',('failed',json.dumps({"error":"Simulation failed","detail":str(e)[:300]}),now(),run_id))

@app.post('/api/videos/{video_id}/simulate')
def simulate(video_id:str, config:SimConfig, background_tasks:BackgroundTasks):
    with connect() as c:
        v=c.execute('SELECT id FROM videos WHERE id=?',(video_id,)).fetchone()
        if not v: raise HTTPException(404,'Video not found')
        # prevent accidental duplicate active runs for identical config
        existing=c.execute("SELECT id FROM runs WHERE video_id=? AND status IN ('queued','running') AND config=?",(video_id,config.model_dump_json())).fetchone()
        if existing: return {"run_id":existing['id'],"status":"already_in_progress"}
        rid=str(uuid.uuid4()); seed=config.seed
        c.execute('INSERT INTO runs VALUES(?,?,?,?,?,?,?,?)',(rid,video_id,'queued',config.model_dump_json(),None,seed,now(),None))
    background_tasks.add_task(run_simulation,rid,video_id,config.model_dump())
    return {"run_id":rid,"video_id":video_id,"status":"queued","poll_url":f"/api/runs/{rid}","notice":"This deployment uses a transparent heuristic simulation; no external LLM is invoked."}

@app.get('/api/runs')
def list_runs():
    with connect() as c: rows=c.execute('SELECT r.id,r.video_id,r.status,r.created_at,r.finished_at,v.filename FROM runs r JOIN videos v ON v.id=r.video_id ORDER BY r.created_at DESC').fetchall()
    return {"runs":[dict(r) for r in rows]}

@app.get('/api/runs/{run_id}')
def get_run(run_id:str):
    with connect() as c: r=c.execute('SELECT * FROM runs WHERE id=?',(run_id,)).fetchone()
    if not r: raise HTTPException(404,'Run not found')
    d=dict(r); d['config']=safe_json(d['config']); d['report']=safe_json(d['report']); return d

@app.get('/api/runs/{run_id}/report')
def get_report(run_id:str):
    with connect() as c: r=c.execute('SELECT status,report FROM runs WHERE id=?',(run_id,)).fetchone()
    if not r: raise HTTPException(404,'Run not found')
    if r['status']!='completed': raise HTTPException(409,f"Report is not ready; run status is {r['status']}.")
    return safe_json(r['report'])

@app.post('/api/videos/{video_id}/actual-performance')
def save_actual(video_id:str, body:ActualPerformance):
    with connect() as c:
        v=c.execute('SELECT id,analysis FROM videos WHERE id=?',(video_id,)).fetchone()
        if not v: raise HTTPException(404,'Video not found')
        analysis=safe_json(v['analysis']) or {}
        # Keep observed data separate from predictions; append to metadata record.
        analysis['actual_performance_submissions']=analysis.get('actual_performance_submissions',[])+[{**body.model_dump(),'submitted_at':now(),'source':'user-provided; not independently verified'}]
        c.execute('UPDATE videos SET analysis=? WHERE id=?',(json.dumps(analysis),video_id))
    return {"status":"saved","notice":"Actual outcomes are stored separately from synthetic estimates. Calibration is not automatic in this version."}

@app.post('/api/runs/{run_id}/ask')
def ask_report(run_id:str, body:ChatRequest):
    with connect() as c: r=c.execute('SELECT report FROM runs WHERE id=? AND status=?',(run_id,'completed')).fetchone()
    if not r: raise HTTPException(404,'Completed report not found')
    report=safe_json(r['report']); q=body.question.lower()
    if any(x in q for x in ('skip','casual','drop','opening','hook')):
        chosen=next((x for x in report['cohorts'] if x['persona_id']=='casual'),None)
        answer=f"The heuristic report estimates the Casual Scroller cohort at {chosen['skip']:.0%} skip probability and {chosen['retention']:.0%} retention. The opening itself was not analyzed frame-by-frame, so this is a cohort-level heuristic—not evidence of a measured drop at a specific timestamp. Consider testing a version that reveals the product or payoff earlier." if chosen else 'No cohort detail is available.'
    elif any(x in q for x in ('tech','enthusiast','audience','segment','cohort')):
        answer='Compare the cohort table for estimated retention, completion and skip probabilities. These differences are generated from persona priors and a seeded heuristic; they do not establish how real tech enthusiasts or other groups will behave.'
    elif any(x in q for x in ('timestamp','time','second','when')):
        answer='The timeline anchors in this run are provisional because no configured frame/audio understanding model detected actual scene boundaries. Use them as places to investigate, not verified moments of attention loss.'
    else:
        answer=f"The report estimates {report['summary']['estimated_retention']:.0%} audience retention and {report['summary']['estimated_completion_probability']:.0%} completion probability for the configured synthetic cohort. The result is uncalibrated. A useful next experiment is to change one creative variable, run both versions with comparable settings, and validate the direction using consented real analytics."
    return {"answer":answer,"grounded_in_run":run_id,"mode":"report-grounded heuristic response","limitations":["No external LLM is configured.","Estimates are not validated human responses."]}

@app.post('/api/compare')
def compare_runs(payload: dict):
    a,b=payload.get('run_a'),payload.get('run_b')
    if not a or not b: raise HTTPException(400,'Provide run_a and run_b IDs')
    with connect() as c: rows=c.execute('SELECT id,report FROM runs WHERE id IN (?,?) AND status=?',(a,b,'completed')).fetchall()
    reports={r['id']:safe_json(r['report']) for r in rows}
    if a not in reports or b not in reports: raise HTTPException(404,'Both completed reports must exist')
    ra,rb=reports[a],reports[b]
    return {"run_a":ra,"run_b":rb,"delta":{"retention":round(rb['summary']['estimated_retention']-ra['summary']['estimated_retention'],3),"completion":round(rb['summary']['estimated_completion_probability']-ra['summary']['estimated_completion_probability'],3),"skip":round(rb['summary']['estimated_skip_probability']-ra['summary']['estimated_skip_probability'],3)},"notice":"Directional comparison of heuristic estimates only; use controlled real-world tests before publishing conclusions."}

app.mount('/', StaticFiles(directory=ROOT/'frontend', html=True), name='frontend')
