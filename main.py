import os, sqlite3, hashlib, secrets, time, shutil
from pathlib import Path
from datetime import datetime, timedelta
from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from passlib.context import CryptContext

APP_DIR = Path(__file__).parent
DB = APP_DIR / "cpm_website.db"
UPLOADS = APP_DIR / "uploads"
UPLOADS.mkdir(exist_ok=True)
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
app = FastAPI(title="CPM MALIK")
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", secrets.token_hex(32)), https_only=False, same_site="lax")
app.mount("/static", StaticFiles(directory=APP_DIR/"static"), name="static")
templates = Jinja2Templates(directory=APP_DIR/"templates")

PLANS = {"1 Day": 200, "1 Week": 1000, "1 Month": 1800}
SERVICES = {
 "Account Management": ["Gmail Change","Password Changed","Info","Set Name","Set ID"],
 "Economy Features": ["50M Money","Custom Money","500K Coin","Custom Coin","Race Win","Race Loss"],
 "Unlock Features": ["W16 Engine Unlock","Smoke Unlock","Unlimited Fuel","No Damage","Horn Unlock","Animation Unlock","Paid House Unlock","Paid Wheels Unlock","All Levels Complete"]
}

def db():
    con=sqlite3.connect(DB); con.row_factory=sqlite3.Row; return con
def init():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE, password TEXT, role TEXT DEFAULT 'customer', banned INTEGER DEFAULT 0, created TEXT);
        CREATE TABLE IF NOT EXISTS payments(id INTEGER PRIMARY KEY, user_id INTEGER, plan TEXT, amount INTEGER, proof TEXT, status TEXT DEFAULT 'pending', created TEXT);
        CREATE TABLE IF NOT EXISTS subscriptions(id INTEGER PRIMARY KEY, user_id INTEGER, plan TEXT, expires TEXT, active INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY, user_id INTEGER, service TEXT, details TEXT, status TEXT DEFAULT 'pending', created TEXT);
        CREATE TABLE IF NOT EXISTS notices(id INTEGER PRIMARY KEY, user_id INTEGER, message TEXT, created TEXT, seen INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS service_flags(service TEXT PRIMARY KEY, enabled INTEGER DEFAULT 1);
        """)
        for cat, items in SERVICES.items():
            for s in items: c.execute("INSERT OR IGNORE INTO service_flags(service,enabled) VALUES(?,1)",(s,))
        admin=os.getenv("ADMIN_USERNAME","admin").strip()
        pw=os.getenv("ADMIN_PASSWORD","")
        if pw and not c.execute("SELECT id FROM users WHERE username=?",(admin,)).fetchone():
            c.execute("INSERT INTO users(username,password,role,created) VALUES(?,?,?,?)",(admin,pwd.hash(pw),"admin",datetime.utcnow().isoformat()))
init()

def current(request):
    uid=request.session.get("uid")
    if not uid: return None
    with db() as c: return c.execute("SELECT * FROM users WHERE id=?",(uid,)).fetchone()
def page(request, name, **ctx):
    user=current(request)
    return templates.TemplateResponse(name, {"request":request,"user":user,"plans":PLANS,"services":SERVICES,**ctx})
def notice(uid,msg):
    with db() as c: c.execute("INSERT INTO notices(user_id,message,created) VALUES(?,?,?)",(uid,msg,datetime.utcnow().isoformat()))
def redirect(path): return RedirectResponse(path,status_code=303)

@app.get("/",response_class=HTMLResponse)
def home(request:Request):
    u=current(request)
    return redirect("/dashboard" if u else "/login")
@app.get("/register",response_class=HTMLResponse)
def register_page(request:Request): return page(request,"register.html")
@app.post("/register")
def register(username:str=Form(...),password:str=Form(...)):
    username=username.strip()
    if len(username)<3 or len(password)<8: raise HTTPException(400,"Username 3+ characters; password 8+ characters.")
    try:
        with db() as c: c.execute("INSERT INTO users(username,password,created) VALUES(?,?,?)",(username,pwd.hash(password),datetime.utcnow().isoformat()))
    except sqlite3.IntegrityError: raise HTTPException(400,"Username already exists.")
    return redirect("/login")
@app.get("/login",response_class=HTMLResponse)
def login_page(request:Request): return page(request,"login.html")
@app.post("/login")
def login(request:Request,username:str=Form(...),password:str=Form(...)):
    with db() as c: u=c.execute("SELECT * FROM users WHERE username=?",(username.strip(),)).fetchone()
    if not u or not pwd.verify(password,u["password"]) or u["banned"]: raise HTTPException(401,"Login details incorrect or account disabled.")
    request.session["uid"]=u["id"]
    return redirect("/dashboard")
@app.get("/logout")
def logout(request:Request): request.session.clear(); return redirect("/login")
@app.get("/dashboard",response_class=HTMLResponse)
def dashboard(request:Request):
    u=current(request)
    if not u:return redirect("/login")
    with db() as c:
        sub=c.execute("SELECT * FROM subscriptions WHERE user_id=? AND active=1 AND expires>? ORDER BY id DESC LIMIT 1",(u["id"],datetime.utcnow().isoformat())).fetchone()
        orders=c.execute("SELECT * FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 10",(u["id"],)).fetchall()
        pays=c.execute("SELECT * FROM payments WHERE user_id=? ORDER BY id DESC LIMIT 5",(u["id"],)).fetchall()
        notes=c.execute("SELECT * FROM notices WHERE user_id=? ORDER BY id DESC LIMIT 10",(u["id"],)).fetchall()
    if u["role"]=="admin": return redirect("/admin")
    return page(request,"dashboard.html",sub=sub,orders=orders,pays=pays,notes=notes)
@app.get("/payment",response_class=HTMLResponse)
def payment_page(request:Request):
    if not current(request):return redirect("/login")
    return page(request,"payment.html")
@app.post("/payment")
async def payment(request:Request,plan:str=Form(...),proof:UploadFile=File(...)):
    u=current(request)
    if not u:return redirect("/login")
    if plan not in PLANS: raise HTTPException(400,"Invalid plan")
    if proof.content_type not in ("image/png","image/jpeg","image/webp"): raise HTTPException(400,"Upload a JPG, PNG or WEBP screenshot.")
    if proof.size and proof.size>5*1024*1024: raise HTTPException(400,"Maximum upload size is 5 MB.")
    ext={"image/png":".png","image/jpeg":".jpg","image/webp":".webp"}[proof.content_type]
    name=f"payment_{u['id']}_{int(time.time())}{ext}"
    with (UPLOADS/name).open("wb") as f: shutil.copyfileobj(proof.file,f)
    with db() as c: c.execute("INSERT INTO payments(user_id,plan,amount,proof,created) VALUES(?,?,?,?,?)",(u["id"],plan,PLANS[plan],name,datetime.utcnow().isoformat()))
    notice(u["id"],"Payment screenshot submitted. Admin approval is pending.")
    return redirect("/dashboard")
@app.post("/order")
def order(request:Request,service:str=Form(...),details:str=Form("")):
    u=current(request)
    if not u:return redirect("/login")
    valid=[s for a in SERVICES.values() for s in a]
    with db() as c:
        sub=c.execute("SELECT id FROM subscriptions WHERE user_id=? AND active=1 AND expires>? LIMIT 1",(u["id"],datetime.utcnow().isoformat())).fetchone()
        enabled=c.execute("SELECT enabled FROM service_flags WHERE service=?",(service,)).fetchone()
        if service not in valid or not enabled or not enabled["enabled"]: raise HTTPException(400,"Service unavailable.")
        if not sub: raise HTTPException(403,"Active subscription required.")
        c.execute("INSERT INTO orders(user_id,service,details,created) VALUES(?,?,?,?)",(u["id"],service,details[:1000],datetime.utcnow().isoformat()))
    notice(u["id"],f"Order for {service} submitted. Waiting for admin/API processing.")
    return redirect("/dashboard")
@app.get("/admin",response_class=HTMLResponse)
def admin(request:Request):
    u=current(request)
    if not u:return redirect("/login")
    if u["role"]!="admin":raise HTTPException(403,"Admin only")
    with db() as c:
        users=c.execute("SELECT id,username,role,banned,created FROM users ORDER BY id DESC").fetchall()
        payments=c.execute("SELECT p.*,u.username FROM payments p JOIN users u ON u.id=p.user_id ORDER BY p.id DESC").fetchall()
        orders=c.execute("SELECT o.*,u.username FROM orders o JOIN users u ON u.id=o.user_id ORDER BY o.id DESC").fetchall()
        flags=c.execute("SELECT * FROM service_flags ORDER BY service").fetchall()
    return page(request,"admin.html",users=users,payments=payments,orders=orders,flags=flags)
@app.post("/admin/payment/{pid}/{action}")
def payment_action(request:Request,pid:int,action:str):
    u=current(request)
    if not u or u["role"]!="admin":raise HTTPException(403)
    with db() as c:
        p=c.execute("SELECT * FROM payments WHERE id=?",(pid,)).fetchone()
        if not p:raise HTTPException(404)
        if action=="approve":
            days={"1 Day":1,"1 Week":7,"1 Month":30}[p["plan"]]
            expires=(datetime.utcnow()+timedelta(days=days)).isoformat()
            c.execute("UPDATE payments SET status='approved' WHERE id=?",(pid,))
            c.execute("UPDATE subscriptions SET active=0 WHERE user_id=?",(p["user_id"],))
            c.execute("INSERT INTO subscriptions(user_id,plan,expires) VALUES(?,?,?)",(p["user_id"],p["plan"],expires))
            notice(p["user_id"],f"Payment approved. {p['plan']} access activated.")
        elif action=="reject":
            c.execute("UPDATE payments SET status='rejected' WHERE id=?",(pid,))
            notice(p["user_id"],"Payment rejected. Please contact admin.")
        else:raise HTTPException(400)
    return redirect("/admin")
@app.post("/admin/order/{oid}/{action}")
def order_action(request:Request,oid:int,action:str):
    u=current(request)
    if not u or u["role"]!="admin":raise HTTPException(403)
    if action not in ("complete","reject","processing"):raise HTTPException(400)
    status={"complete":"completed","reject":"rejected","processing":"processing"}[action]
    with db() as c:
        o=c.execute("SELECT * FROM orders WHERE id=?",(oid,)).fetchone()
        if not o:raise HTTPException(404)
        c.execute("UPDATE orders SET status=? WHERE id=?",(status,oid))
        notice(o["user_id"],f"Your {o['service']} order status: {status}.")
    return redirect("/admin")
@app.post("/admin/service")
def service_toggle(request:Request,service:str=Form(...),enabled:int=Form(...)):
    u=current(request)
    if not u or u["role"]!="admin":raise HTTPException(403)
    with db() as c:c.execute("UPDATE service_flags SET enabled=? WHERE service=?",(enabled,service))
    return redirect("/admin")
@app.post("/admin/user/{uid}/ban")
def ban_user(request:Request,uid:int):
    u=current(request)
    if not u or u["role"]!="admin":raise HTTPException(403)
    with db() as c:c.execute("UPDATE users SET banned=1 WHERE id=? AND role!='admin'",(uid,))
    return redirect("/admin")
@app.get("/uploads/{name}")
def get_upload(name:str,request:Request):
    u=current(request)
    if not u or u["role"]!="admin":raise HTTPException(403)
    from fastapi.responses import FileResponse
    p=UPLOADS/name
    if not p.exists():raise HTTPException(404)
    return FileResponse(p)
