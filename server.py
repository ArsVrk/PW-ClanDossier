# -*- coding: utf-8 -*-
import base64, hmac, json, os, re, sqlite3, socket, threading, urllib.request, urllib.error
from html import unescape
from html.parser import HTMLParser
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote

HERE=os.path.dirname(os.path.abspath(__file__))
DATABASE_URL=os.environ.get("DATABASE_URL", "").strip()
DB_CANDIDATES=[os.path.join(HERE,"PW_ClanDossier.sqlite3"), os.path.join(os.path.dirname(HERE),"PW_ClanDossier.sqlite3")]
DB_PATH=os.environ.get("DOSSIER_DB","")
if not DB_PATH: DB_PATH=next((p for p in DB_CANDIDATES if os.path.exists(p)), DB_CANDIDATES[0])

HOST=os.environ.get("DOSSIER_HOST","0.0.0.0")
PORT=int(os.environ.get("DOSSIER_PORT","8787"))
DOSSIER_PASSWORD=os.environ.get("DOSSIER_PASSWORD", "")
STATIC=os.path.join(HERE,"static")
CACHE=os.path.join(HERE,"cache")
ICONS=os.path.join(CACHE,"icons")
META_FILE=os.path.join(CACHE,"pwdb_items.json")
DEFAULTS_FILE=os.path.join(HERE,"scan_defaults.json")
FULL_BUFF_IDS={28,31,64,65,66,68}
def load_setting(key, fallback):
    if not DATABASE_URL:
        try:
            with open(DEFAULTS_FILE,"r",encoding="utf-8") as f: return json.load(f)
        except Exception: return fallback
    try:
        cx=db(); row=cx.execute("SELECT value_json FROM app_settings WHERE key=%s",(key,)).fetchone(); cx.close()
        return json.loads(row[0]) if row else fallback
    except Exception: return fallback
SCAN_DEFAULTS={} if DATABASE_URL else load_setting("scan_defaults", {})
DEFAULTS_LOCK=threading.Lock()
DICT_FILES={k:os.path.join(HERE,k+"_names.json") for k in ("item","stone")}
def load_dict(kind):
    try:
        with open(DICT_FILES[kind],"r",encoding="utf-8") as f:return json.load(f)
    except Exception:return {}
ITEM_NAMES=load_dict("item")
STONE_NAMES=load_dict("stone")
os.makedirs(ICONS,exist_ok=True)

def load_item_metadata():
    if not DATABASE_URL:
        try:
            with open(META_FILE,"r",encoding="utf-8") as f: return json.load(f)
        except Exception: return {}
    try:
        cx=db(); rows=cx.execute("SELECT item_id, metadata_json FROM item_metadata").fetchall(); cx.close()
        return {str(r[0]):json.loads(r[1]) for r in rows}
    except Exception: return {}
PWDB_META={} if DATABASE_URL else load_item_metadata()
META_LOCK=threading.Lock()

CLASS_NAMES={0:"Воїн",1:"Маг",2:"Шаман",3:"Друїд",4:"Перевертень",5:"Вбивця",
             6:"Лучник",7:"Жрець",8:"Страж",9:"Містик"}

class PgConnection:
    """Small compatibility wrapper so existing SQLite-style queries can use PostgreSQL."""
    def __init__(self, conn): self.conn=conn
    def execute(self, sql, params=()):
        from psycopg2.extras import DictCursor
        cur=self.conn.cursor(cursor_factory=DictCursor)
        cur.execute(sql.replace("?", "%s"), params)
        return cur
    def close(self): self.conn.close()

def db():
    if DATABASE_URL:
        import psycopg2
        return PgConnection(psycopg2.connect(DATABASE_URL, connect_timeout=10, sslmode="require"))
    cx=sqlite3.connect(DB_PATH); cx.row_factory=sqlite3.Row; return cx

def status_columns(cx):
    if DATABASE_URL: return {"status_state","status_count","status_ids_json","status_records_json"}
    return {r[1] for r in cx.execute("PRAGMA table_info(scans)").fetchall()}

# Load persistent preferences/cache only after the database adapter is defined.
if DATABASE_URL:
    SCAN_DEFAULTS=load_setting("scan_defaults", {})
    PWDB_META=load_item_metadata()

def latest_characters(q=""):
    cx=db(); cols=status_columns(cx)
    status_sql=("s.status_state,s.status_count,s.status_ids_json" if "status_state" in cols else
                "'UNKNOWN' AS status_state,NULL AS status_count,'[]' AS status_ids_json")
    rows=cx.execute(f"""
      SELECT s.id scan_id,s.wid,s.name,s.captured_at,st.json,
             st.damage_rating,st.hp_rating,st.max_hp,st.phys_min,st.phys_max,
             st.phys_def,st.attack_level,st.defense_level,st.critical,{status_sql}
      FROM scans s JOIN stats st ON st.scan_id=s.id
      WHERE s.detailed_ok=1 ORDER BY s.id DESC
    """).fetchall();cx.close()
    candidates={}
    for r in rows:
        d=dict(r);wid=int(d["wid"])
        try:ids=[int(v) for v in json.loads(d.get("status_ids_json") or "[]")]
        except Exception:ids=[]
        d["status_ids"]=ids;d["full_buff"]=FULL_BUFF_IDS.issubset(set(ids));d["status_state"]=d.get("status_state") or "UNKNOWN"
        try:st=json.loads(d.pop("json") or "{}")
        except Exception:st={}
        d.pop("status_ids_json",None);d["stats"]=st;d["class_name"]=CLASS_NAMES.get(st.get("class_id"),str(st.get("class_id","—")));d["level"]=st.get("level")
        candidates.setdefault(wid,[]).append(d)
    out=[];q=q.lower().strip()
    for wid,scans in candidates.items():
        chosen=None
        preferred=SCAN_DEFAULTS.get(str(wid))
        if preferred is not None:
            chosen=next((x for x in scans if int(x["scan_id"])==int(preferred)),None)
        if chosen is None:chosen=next((x for x in scans if x["status_state"]=="NO_REPORTED_STATUSES"),None)
        if chosen is None:chosen=next((x for x in scans if not x["full_buff"]),scans[0])
        if q and q not in (chosen["name"] or "").lower() and q not in f'{wid:08x}':continue
        out.append(chosen)
    out.sort(key=lambda x:(x.get("name") or "").lower())
    return out

def character(wid, requested_scan_id=None):
    cx=db()
    cols=status_columns(cx)
    has_status="status_state" in cols
    if has_status:
        hist_sql="s.status_state,s.status_count,s.status_ids_json,s.status_records_json"
    else:
        hist_sql="'UNKNOWN' AS status_state,NULL AS status_count,'[]' AS status_ids_json,'[]' AS status_records_json"
    raw_hist=cx.execute(f"""
      SELECT s.id,s.wid,s.name,s.captured_at,st.json,st.damage_rating,st.hp_rating,st.max_hp,
             st.max_mp,st.critical,st.attack_level,st.defense_level,{hist_sql}
      FROM scans s JOIN stats st ON st.scan_id=s.id
      WHERE s.wid=? AND s.detailed_ok=1 ORDER BY s.id DESC LIMIT 100
    """,(wid,)).fetchall()
    if not raw_hist:
        cx.close(); return None
    history=[]
    for rr in raw_hist:
        h=dict(rr)
        try: ids=[int(v) for v in json.loads(h.get("status_ids_json") or "[]")]
        except Exception: ids=[]
        h["status_ids"]=ids
        h["full_buff"]=FULL_BUFF_IDS.issubset(set(ids))
        h["status_state"]=h.get("status_state") or "UNKNOWN"
        h.pop("status_ids_json",None);h.pop("status_records_json",None);h.pop("json",None)
        history.append(h)
    available={int(h["id"]):h for h in history}
    preferred=SCAN_DEFAULTS.get(str(int(wid)))
    default_id=None
    try:
        if preferred is not None and int(preferred) in available: default_id=int(preferred)
    except (ValueError,TypeError): pass
    if default_id is None:
        # By default, prefer the newest scan without the complete NPC buff set.
        default_id=next((int(h["id"]) for h in history if h["status_state"]=="NO_REPORTED_STATUSES"),None)
        if default_id is None:default_id=next((int(h["id"]) for h in history if not h["full_buff"]),int(history[0]["id"]))
    selected_id=default_id
    try:
        if requested_scan_id is not None and int(requested_scan_id) in available:
            selected_id=int(requested_scan_id)
    except (ValueError,TypeError): pass
    selected=available[selected_id]
    sr=cx.execute("""
      SELECT s.id scan_id,s.wid,s.name,s.captured_at,st.json,s.status_state,s.status_count,
             s.status_ids_json,s.status_records_json
      FROM scans s JOIN stats st ON st.scan_id=s.id
      WHERE s.id=? AND s.wid=? AND s.detailed_ok=1
    """ if has_status else """
      SELECT s.id scan_id,s.wid,s.name,s.captured_at,st.json,
             'UNKNOWN' AS status_state,NULL AS status_count,'[]' AS status_ids_json,'[]' AS status_records_json
      FROM scans s JOIN stats st ON st.scan_id=s.id
      WHERE s.id=? AND s.wid=? AND s.detailed_ok=1
    """,(selected_id,wid)).fetchone()
    if not sr:
        cx.close();return None
    d=dict(sr); st=json.loads(d.pop("json") or "{}")
    try:d["status_ids"]=[int(v) for v in json.loads(d.pop("status_ids_json") or "[]")]
    except Exception:d["status_ids"]=[]
    try:d["status_records"]=json.loads(d.pop("status_records_json") or "[]")
    except Exception:d["status_records"]=[]
    d["status_state"]=d.get("status_state") or "UNKNOWN"
    d["full_buff"]=FULL_BUFF_IDS.issubset(set(d["status_ids"]))
    d["stats"]=st
    eq=[dict(x) for x in cx.execute("""
      SELECT slot,template_id,runtime_class,refine,sockets_json,properties_json
      FROM equipment WHERE scan_id=? ORDER BY slot
    """,(selected_id,)).fetchall()]
    cx.close()
    for x in eq:
        try:x["sockets"]=json.loads(x.pop("sockets_json") or "[]")
        except Exception:x["sockets"]=[]
        try:x["properties"]=json.loads(x.pop("properties_json") or "[]")
        except Exception:x["properties"]=[]
        meta=PWDB_META.get(str(x["template_id"]),{})
        x["pwdb_name"]=meta.get("name")
    d["equipment"]=eq
    d["history"]=[dict(h, is_default=(int(h["id"])==int(default_id))) for h in history]
    d["selected_scan_id"]=selected_id
    d["default_scan_id"]=default_id
    d["class_name"]=CLASS_NAMES.get(st.get("class_id"),str(st.get("class_id","—")))
    return d

def fetch_pwdb_name(item_id):
    """Fetch only the display name from the PWDatabase page; do not parse item properties."""
    key=str(int(item_id))
    with META_LOCK:
        cached=PWDB_META.get(key)
        if cached and cached.get("name"):
            return {"id":int(key),"name":cached["name"]}
        local=ITEM_NAMES.get(key) or STONE_NAMES.get(key)
        if local:
            return {"id":int(key),"name":local}
    url=f"https://www.pwdatabase.com/ru/items/{key}"
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 PW-Clan-Dossier/0.4"})
    with urllib.request.urlopen(req,timeout=8) as r:
        html_text=r.read().decode("utf-8","ignore")
    m=re.search(r"<title>\s*Perfect World Item Database\s*-\s*(.*?)\s*</title>",html_text,re.I|re.S)
    name=unescape(re.sub(r"<[^>]+>","",m.group(1))).strip() if m else None
    if not name:
        m=re.search(r"<h1[^>]*>(.*?)</h1>",html_text,re.I|re.S)
        name=unescape(re.sub(r"<[^>]+>","",m.group(1))).strip() if m else f"ID {key}"
    name=ITEM_NAMES.get(key) or STONE_NAMES.get(key) or name
    with META_LOCK:
        old=PWDB_META.get(key,{})
        # Preserve already-cached full metadata if it exists; otherwise cache only the name.
        meta=dict(old)
        meta.update({"name":name,"url":url,"icon":f"https://www.pwdatabase.com/images/icons/generalm/{key}.png"})
        meta.setdefault("details",[])
        meta.setdefault("details_fetched",False)
        PWDB_META[key]=meta
        if DATABASE_URL:
            cx=db(); cx.execute("INSERT INTO item_metadata(item_id,metadata_json,updated_at) VALUES(?,?,now()) ON CONFLICT(item_id) DO UPDATE SET metadata_json=EXCLUDED.metadata_json,updated_at=now()",(key,json.dumps(meta,ensure_ascii=False))); cx.conn.commit(); cx.close()
        else:
            with open(META_FILE,"w",encoding="utf-8") as f:json.dump(PWDB_META,f,ensure_ascii=False,indent=2)
    return {"id":int(key),"name":name}

def get_icon(item_id):
    item_id=int(item_id); path=os.path.join(ICONS,f"{item_id}.png")
    if os.path.exists(path) and os.path.getsize(path)>20:return path
    url=f"https://www.pwdatabase.com/images/icons/generalm/{item_id}.png"
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0","Referer":f"https://www.pwdatabase.com/ru/items/{item_id}"})
    with urllib.request.urlopen(req,timeout=8) as r:data=r.read()
    if len(data)>20:
        with open(path,"wb") as f:f.write(data)
        return path
    raise FileNotFoundError(item_id)

class H(BaseHTTPRequestHandler):
    def log_message(self,fmt,*args): pass
    def authorized(self):
        # Optional HTTP Basic Auth for a private trial through a tunnel.
        # Local use stays password-free unless DOSSIER_PASSWORD is set.
        if not DOSSIER_PASSWORD:
            return True
        header=self.headers.get("Authorization", "")
        try:
            scheme, token=header.split(" ",1)
            if scheme.lower() != "basic": raise ValueError("not basic auth")
            userpass=base64.b64decode(token,validate=True).decode("utf-8")
            username,password=userpass.split(":",1)
        except Exception:
            username=password=""
        if username == "officer" and hmac.compare_digest(password, DOSSIER_PASSWORD):
            return True
        try:
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="Chorna Rada", charset="UTF-8"')
            self.send_header("Content-Length", "0")
            self.end_headers()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, TimeoutError):
            pass
        return False
    def handle(self):
        # A browser refresh/hover-away can cancel an in-flight request. That is normal,
        # so don't dump a traceback for a client that has already disconnected.
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, TimeoutError):
            pass
    def send_json(self,obj,status=200):
        b=json.dumps(obj,ensure_ascii=False).encode()
        try:
            self.send_response(status);self.send_header("Content-Type","application/json; charset=utf-8")
            self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, TimeoutError):
            return
    def send_file(self,path,ctype,cache="public, max-age=86400"):
        try:
            with open(path,"rb") as f:b=f.read()
        except: self.send_error(404);return
        try:
            self.send_response(200);self.send_header("Content-Type",ctype)
            self.send_header("Cache-Control",cache)
            self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, TimeoutError):
            return
    def do_GET(self):
        u=urlparse(self.path); p=u.path
        if p=="/healthz": return self.send_json({"ok":True,"service":"pw-clan-dossier"})
        if not self.authorized(): return
        if p=="/":return self.send_file(os.path.join(STATIC,"index.html"),"text/html; charset=utf-8","no-cache, no-store, must-revalidate")
        if p=="/app.js":return self.send_file(os.path.join(STATIC,"app.js"),"text/javascript; charset=utf-8","no-cache, no-store, must-revalidate")
        if p=="/style.css":return self.send_file(os.path.join(STATIC,"style.css"),"text/css; charset=utf-8","no-cache, no-store, must-revalidate")
        if p=="/slot.svg":return self.send_file(os.path.join(STATIC,"slot.svg"),"image/svg+xml")
        if p=="/item_names.json":return self.send_file(os.path.join(HERE,"item_names.json"),"application/json; charset=utf-8")
        if p=="/stone_names.json":return self.send_file(os.path.join(HERE,"stone_names.json"),"application/json; charset=utf-8")
        if p=="/api/characters":
            q=parse_qs(u.query).get("q",[""])[0];return self.send_json(latest_characters(q))
        m=re.fullmatch(r"/api/character/(\d+)",p)
        if m:
            scan_id=parse_qs(u.query).get("scan_id",[None])[0]
            x=character(int(m.group(1)),scan_id);return self.send_json(x,200 if x else 404)
        m=re.fullmatch(r"/api/pwdb-name/(\d+)",p)
        if m:
            try:return self.send_json(fetch_pwdb_name(int(m.group(1))))
            except Exception as e:return self.send_json({"id":int(m.group(1)),"name":ITEM_NAMES.get(m.group(1)) or STONE_NAMES.get(m.group(1)) or f"ID {m.group(1)}","error":str(e)},200)
        m=re.fullmatch(r"/icon/(\d+)\.png",p)
        if m:
            try:return self.send_file(get_icon(int(m.group(1))),"image/png")
            except:return self.send_file(os.path.join(STATIC,"slot.svg"),"image/svg+xml")
        self.send_error(404)

    def do_POST(self):
        if not self.authorized(): return
        u=urlparse(self.path)
        if u.path!="/api/default-scan":
            self.send_error(404);return
        try:
            length=min(int(self.headers.get("Content-Length","0")),10000)
            payload=json.loads(self.rfile.read(length).decode("utf-8"))
            wid=int(payload["wid"]);scan_id=int(payload["scan_id"])
            # Only allow a scan that actually belongs to this character and has detailed stats.
            cx=db();row=cx.execute("SELECT wid FROM scans WHERE id=? AND detailed_ok=1",(scan_id,)).fetchone();cx.close()
            if not row or int(row[0])!=wid:
                return self.send_json({"ok":False,"error":"scan does not belong to character"},400)
            with DEFAULTS_LOCK:
                SCAN_DEFAULTS[str(wid)]=scan_id
                if DATABASE_URL:
                    cx=db(); cx.execute("INSERT INTO app_settings(key,value_json,updated_at) VALUES(?,?,now()) ON CONFLICT(key) DO UPDATE SET value_json=EXCLUDED.value_json,updated_at=now()",("scan_defaults",json.dumps(SCAN_DEFAULTS,ensure_ascii=False))); cx.conn.commit(); cx.close()
                else:
                    tmp=DEFAULTS_FILE+".tmp"
                    with open(tmp,"w",encoding="utf-8") as f:json.dump(SCAN_DEFAULTS,f,ensure_ascii=False,indent=2)
                    os.replace(tmp,DEFAULTS_FILE)
            return self.send_json({"ok":True,"wid":wid,"scan_id":scan_id})
        except Exception as e:
            return self.send_json({"ok":False,"error":str(e)},400)

def local_ip():
    try:
        s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.connect(("8.8.8.8",80))
        ip=s.getsockname()[0];s.close();return ip
    except:return "127.0.0.1"

if __name__=="__main__":
    if DATABASE_URL and not DOSSIER_PASSWORD:
        print("ERROR: set DOSSIER_PASSWORD for a private hosted deployment.")
        raise SystemExit(2)
    if not DATABASE_URL and not os.path.exists(DB_PATH):
        print("НЕ ЗНАЙДЕНО БАЗУ:",DB_PATH); raise SystemExit(1)
    print("PW Clan Dossier")
    print("DB:", "Supabase PostgreSQL" if DATABASE_URL else DB_PATH)
    print(f"Listening on port {PORT}")
    ThreadingHTTPServer((HOST,PORT),H).serve_forever()
