#!/usr/bin/env python3
"""
============================================================
  Online Examination & Grading System
  Single-file Flask + SQLite application
  Run:  pip install flask werkzeug && python app.py
============================================================
"""

import os, json, sqlite3, traceback
from datetime import datetime
from functools import wraps
from flask import (Flask, render_template_string, request, redirect,
                   url_for, session, flash, jsonify, g)
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "examSys#Secret!2025"
DATABASE = "exam_system.db"

# ─────────────────────────────────────────────
#  DATABASE HELPERS
# ─────────────────────────────────────────────
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop("db", None)
    if db: db.close()

def query(sql, args=(), one=False):
    cur = get_db().execute(sql, args)
    rv  = cur.fetchall()
    return (rv[0] if rv else None) if one else rv

def execute(sql, args=()):
    db  = get_db()
    cur = db.execute(sql, args)
    db.commit()
    return cur.lastrowid

def init_db():
    db = sqlite3.connect(DATABASE)
    db.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id       INTEGER PRIMARY KEY AUTOINCREMENT,
        name     TEXT    NOT NULL,
        email    TEXT    NOT NULL UNIQUE,
        password TEXT    NOT NULL,
        role     TEXT    NOT NULL DEFAULT 'student'
    );
    CREATE TABLE IF NOT EXISTS courses (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        course_name TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS exams (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        course_id     INTEGER NOT NULL,
        teacher_id    INTEGER NOT NULL,
        title         TEXT    NOT NULL,
        timer_minutes INTEGER NOT NULL DEFAULT 30,
        FOREIGN KEY(course_id)  REFERENCES courses(id),
        FOREIGN KEY(teacher_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS questions (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        exam_id        INTEGER NOT NULL,
        question_text  TEXT    NOT NULL,
        type           TEXT    NOT NULL,
        choices        TEXT,
        correct_answer TEXT,
        FOREIGN KEY(exam_id) REFERENCES exams(id)
    );
    CREATE TABLE IF NOT EXISTS student_answers (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id  INTEGER NOT NULL,
        exam_id     INTEGER NOT NULL,
        question_id INTEGER NOT NULL,
        answer      TEXT,
        FOREIGN KEY(student_id)  REFERENCES users(id),
        FOREIGN KEY(exam_id)     REFERENCES exams(id),
        FOREIGN KEY(question_id) REFERENCES questions(id)
    );
    CREATE TABLE IF NOT EXISTS results (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        exam_id    INTEGER NOT NULL,
        score      INTEGER NOT NULL DEFAULT 0,
        percentage REAL    NOT NULL DEFAULT 0,
        taken_at   TEXT    NOT NULL,
        FOREIGN KEY(student_id) REFERENCES users(id),
        FOREIGN KEY(exam_id)    REFERENCES exams(id)
    );
    """)
    # default admin
    cur = db.execute("SELECT id FROM users WHERE role='admin' LIMIT 1")
    if not cur.fetchone():
        db.execute("INSERT INTO users (name,email,password,role) VALUES (?,?,?,?)",
                   ("Administrator","admin@exam.com",
                    generate_password_hash("admin123"),"admin"))
    db.commit()
    db.close()

# ─────────────────────────────────────────────
#  AUTH DECORATORS
# ─────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def dec(*a,**kw):
        if "user_id" not in session:
            flash("Please login first.","warning")
            return redirect(url_for("login"))
        return f(*a,**kw)
    return dec

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def dec(*a,**kw):
            if session.get("role") not in roles:
                flash("Access denied.","danger")
                return redirect(url_for("dashboard"))
            return f(*a,**kw)
        return login_required(dec)
    return decorator

# ─────────────────────────────────────────────
#  SHARED CSS + JS (injected into every page)
# ─────────────────────────────────────────────
GLOBAL_STYLE = """
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&family=Space+Grotesk:wght@400;500;600;700&display=swap');

*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --navy:#0a1628;--navy2:#0f2044;--navy3:#162b55;
  --green:#00c896;--green2:#00a87e;--green3:#00f5b8;
  --text:#e8f0fe;--text2:#9ab0d0;--text3:#5a7499;
  --card:#111e35;--card2:#162240;--border:#1e3258;
  --red:#ff4d6d;--yellow:#ffd166;
  --radius:14px;--shadow:0 8px 32px rgba(0,0,0,.45);
  --trans:all .25s cubic-bezier(.4,0,.2,1);
}
html{scroll-behavior:smooth}
body{font-family:'DM Sans',sans-serif;background:var(--navy);color:var(--text);min-height:100vh;display:flex;flex-direction:column}

/* SCROLLBAR */
::-webkit-scrollbar{width:6px}
::-webkit-scrollbar-track{background:var(--navy2)}
::-webkit-scrollbar-thumb{background:var(--navy3);border-radius:99px}

/* ANIMATIONS */
@keyframes fadeIn{from{opacity:0;transform:translateY(18px)}to{opacity:1;transform:translateY(0)}}
@keyframes slideIn{from{opacity:0;transform:translateX(-24px)}to{opacity:1;transform:translateX(0)}}
@keyframes pulse{0%,100%{box-shadow:0 0 0 0 rgba(0,200,150,.35)}50%{box-shadow:0 0 0 10px rgba(0,200,150,0)}}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes shimmer{0%{background-position:-200% 0}100%{background-position:200% 0}}
@keyframes countDown{from{stroke-dashoffset:0}to{stroke-dashoffset:251}}

.anim-fade{animation:fadeIn .5s ease both}
.anim-slide{animation:slideIn .4s ease both}

/* LAYOUT */
.app-wrapper{display:flex;min-height:100vh}
.sidebar{width:260px;min-height:100vh;background:var(--navy2);border-right:1px solid var(--border);display:flex;flex-direction:column;position:sticky;top:0;height:100vh;overflow-y:auto;transition:var(--trans)}
.sidebar-logo{padding:28px 24px 20px;border-bottom:1px solid var(--border)}
.sidebar-logo h2{font-family:'Space Grotesk',sans-serif;font-size:1.2rem;color:var(--green);letter-spacing:-.5px}
.sidebar-logo span{font-size:.78rem;color:var(--text3)}
.sidebar-nav{padding:16px 12px;flex:1}
.sidebar-nav a{display:flex;align-items:center;gap:12px;padding:12px 14px;border-radius:10px;color:var(--text2);text-decoration:none;font-size:.9rem;font-weight:500;transition:var(--trans);margin-bottom:4px}
.sidebar-nav a:hover,.sidebar-nav a.active{background:var(--navy3);color:var(--text)}
.sidebar-nav a svg{flex-shrink:0;opacity:.7}
.sidebar-nav a:hover svg,.sidebar-nav a.active svg{opacity:1;stroke:var(--green)}
.sidebar-nav a.active{color:var(--green)}
.sidebar-footer{padding:16px 20px;border-top:1px solid var(--border);font-size:.82rem;color:var(--text3)}
.sidebar-footer strong{color:var(--text2);display:block}

.main-content{flex:1;padding:32px;overflow-x:hidden}
.page-header{margin-bottom:28px;animation:fadeIn .4s ease}
.page-header h1{font-family:'Space Grotesk',sans-serif;font-size:1.75rem;font-weight:700;letter-spacing:-.5px}
.page-header p{color:var(--text2);margin-top:4px;font-size:.95rem}

/* CARDS */
.cards-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:18px;margin-bottom:28px}
.stat-card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:22px;transition:var(--trans);animation:fadeIn .5s ease both}
.stat-card:hover{transform:translateY(-3px);border-color:var(--green);box-shadow:var(--shadow)}
.stat-card .icon{width:44px;height:44px;border-radius:10px;display:flex;align-items:center;justify-content:center;margin-bottom:14px;background:rgba(0,200,150,.1)}
.stat-card .icon svg{stroke:var(--green)}
.stat-card h3{font-size:2rem;font-weight:700;font-family:'Space Grotesk',sans-serif}
.stat-card p{color:var(--text2);font-size:.85rem;margin-top:4px}

/* TABLES */
.table-wrap{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden;animation:fadeIn .5s ease both}
table{width:100%;border-collapse:collapse}
thead{background:var(--card2)}
th{padding:14px 18px;text-align:left;font-size:.8rem;text-transform:uppercase;letter-spacing:.8px;color:var(--text3);font-weight:600}
td{padding:14px 18px;border-top:1px solid var(--border);font-size:.9rem;color:var(--text2);transition:var(--trans)}
tr:hover td{background:rgba(255,255,255,.02);color:var(--text)}
td .badge{display:inline-block;padding:3px 10px;border-radius:99px;font-size:.75rem;font-weight:600}
.badge-admin{background:rgba(255,77,109,.15);color:var(--red)}
.badge-teacher{background:rgba(255,209,102,.15);color:var(--yellow)}
.badge-student{background:rgba(0,200,150,.15);color:var(--green)}

/* BUTTONS */
.btn{display:inline-flex;align-items:center;gap:8px;padding:10px 20px;border-radius:10px;font-size:.88rem;font-weight:600;cursor:pointer;border:none;transition:var(--trans);text-decoration:none;font-family:'DM Sans',sans-serif}
.btn-primary{background:var(--green);color:#fff}
.btn-primary:hover{background:var(--green2);transform:translateY(-1px);box-shadow:0 4px 20px rgba(0,200,150,.35)}
.btn-danger{background:rgba(255,77,109,.15);color:var(--red);border:1px solid rgba(255,77,109,.3)}
.btn-danger:hover{background:var(--red);color:#fff}
.btn-secondary{background:var(--card2);color:var(--text2);border:1px solid var(--border)}
.btn-secondary:hover{background:var(--navy3);color:var(--text)}
.btn-sm{padding:7px 14px;font-size:.8rem;border-radius:8px}
.btn-warning{background:rgba(255,209,102,.15);color:var(--yellow);border:1px solid rgba(255,209,102,.3)}
.btn-warning:hover{background:var(--yellow);color:#000}

/* FORMS */
.form-card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:28px;animation:fadeIn .5s ease both;max-width:680px}
.form-group{margin-bottom:20px}
.form-group label{display:block;margin-bottom:8px;font-size:.87rem;font-weight:600;color:var(--text2)}
.form-group input,.form-group select,.form-group textarea{width:100%;padding:12px 16px;background:var(--navy2);border:1px solid var(--border);border-radius:10px;color:var(--text);font-size:.92rem;font-family:'DM Sans',sans-serif;transition:var(--trans);outline:none}
.form-group input:focus,.form-group select:focus,.form-group textarea:focus{border-color:var(--green);box-shadow:0 0 0 3px rgba(0,200,150,.12)}
.form-group select option{background:var(--navy2)}
.form-group textarea{min-height:90px;resize:vertical}
.form-hint{font-size:.78rem;color:var(--text3);margin-top:5px}

/* ALERTS */
.alert{padding:13px 18px;border-radius:10px;margin-bottom:20px;font-size:.9rem;animation:fadeIn .3s ease;display:flex;align-items:center;gap:10px}
.alert-success{background:rgba(0,200,150,.12);border:1px solid rgba(0,200,150,.3);color:var(--green)}
.alert-danger{background:rgba(255,77,109,.12);border:1px solid rgba(255,77,109,.3);color:var(--red)}
.alert-warning{background:rgba(255,209,102,.12);border:1px solid rgba(255,209,102,.3);color:var(--yellow)}
.alert-info{background:rgba(10,22,40,.5);border:1px solid var(--border);color:var(--text2)}

/* SECTION TITLE */
.section-title{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px}
.section-title h2{font-family:'Space Grotesk',sans-serif;font-size:1.1rem;font-weight:600}

/* LOGIN PAGE */
.auth-page{min-height:100vh;display:flex;align-items:center;justify-content:center;background:var(--navy);background-image:radial-gradient(ellipse at 20% 50%,rgba(0,200,150,.07) 0%,transparent 60%),radial-gradient(ellipse at 80% 20%,rgba(10,100,200,.08) 0%,transparent 60%)}
.auth-card{background:var(--card);border:1px solid var(--border);border-radius:20px;padding:40px;width:100%;max-width:420px;box-shadow:var(--shadow);animation:fadeIn .6s ease}
.auth-card h1{font-family:'Space Grotesk',sans-serif;font-size:1.6rem;font-weight:700;margin-bottom:6px}
.auth-card p.sub{color:var(--text3);margin-bottom:28px;font-size:.9rem}
.auth-card .logo{display:flex;align-items:center;gap:10px;margin-bottom:28px}
.auth-card .logo-icon{width:40px;height:40px;background:linear-gradient(135deg,var(--green),var(--navy3));border-radius:10px;display:flex;align-items:center;justify-content:center}

/* EXAM TAKING */
.exam-header{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:20px 24px;margin-bottom:24px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:16px;z-index:100;backdrop-filter:blur(10px)}
.timer-ring{position:relative;width:64px;height:64px}
.timer-ring svg{transform:rotate(-90deg)}
.timer-ring circle{fill:none;stroke:var(--border);stroke-width:4}
.timer-ring .progress{stroke:var(--green);stroke-width:4;stroke-linecap:round;stroke-dasharray:251;transition:stroke-dashoffset 1s linear,stroke .3s}
.timer-text{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:.8rem;font-weight:700;font-family:'Space Grotesk',sans-serif}
.question-card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:24px;margin-bottom:18px;transition:var(--trans);animation:fadeIn .4s ease both}
.question-card:hover{border-color:rgba(0,200,150,.3)}
.question-num{font-size:.78rem;font-weight:700;color:var(--green);text-transform:uppercase;letter-spacing:1px;margin-bottom:10px}
.question-text{font-size:1rem;font-weight:500;margin-bottom:16px;line-height:1.6}
.choices label{display:flex;align-items:flex-start;gap:12px;padding:11px 14px;border-radius:8px;cursor:pointer;transition:var(--trans);border:1px solid transparent;margin-bottom:8px;font-size:.9rem}
.choices label:hover{background:var(--card2);border-color:var(--border)}
.choices input[type=radio],.choices input[type=checkbox]{accent-color:var(--green);width:16px;height:16px;flex-shrink:0;margin-top:2px}
.choices input:checked + span{color:var(--green)}
.choices label:has(input:checked){background:rgba(0,200,150,.08);border-color:rgba(0,200,150,.3)}
.essay-area{width:100%;min-height:110px;background:var(--navy2);border:1px solid var(--border);border-radius:10px;padding:12px;color:var(--text);font-family:'DM Sans',sans-serif;resize:vertical;font-size:.92rem}
.essay-area:focus{border-color:var(--green);outline:none;box-shadow:0 0 0 3px rgba(0,200,150,.12)}

/* RESULT */
.result-circle{width:150px;height:150px;border-radius:50%;border:6px solid var(--green);display:flex;flex-direction:column;align-items:center;justify-content:center;margin:0 auto 24px;animation:pulse 2s infinite;background:rgba(0,200,150,.05)}
.result-circle .score{font-size:2.4rem;font-weight:700;font-family:'Space Grotesk',sans-serif;color:var(--green)}
.result-circle .label{font-size:.8rem;color:var(--text3)}

/* PROGRESS BAR */
.progress-wrap{background:var(--navy3);border-radius:99px;height:8px;overflow:hidden}
.progress-bar{height:100%;border-radius:99px;background:linear-gradient(90deg,var(--green),var(--green3));transition:width .6s ease}

/* ERROR PAGE */
.error-page{min-height:100vh;display:flex;align-items:center;justify-content:center;background:var(--navy);background-image:radial-gradient(ellipse at 20% 50%,rgba(255,77,109,.05) 0%,transparent 60%),radial-gradient(ellipse at 80% 20%,rgba(10,100,200,.06) 0%,transparent 60%)}
.error-card{background:var(--card);border:1px solid var(--border);border-radius:20px;padding:48px 40px;width:100%;max-width:520px;box-shadow:var(--shadow);animation:fadeIn .6s ease;text-align:center}
.error-code{font-family:'Space Grotesk',sans-serif;font-size:5rem;font-weight:700;line-height:1;margin-bottom:8px}
.error-title{font-family:'Space Grotesk',sans-serif;font-size:1.4rem;font-weight:600;margin-bottom:12px}
.error-desc{color:var(--text3);font-size:.95rem;line-height:1.6;margin-bottom:28px}
.error-actions{display:flex;gap:12px;justify-content:center;flex-wrap:wrap}

/* MOBILE */
@media(max-width:768px){
  .app-wrapper{flex-direction:column}
  .sidebar{width:100%;min-height:auto;height:auto;position:relative;flex-direction:row;flex-wrap:wrap;padding:12px}
  .sidebar-logo{padding:8px 12px;border-bottom:none;border-right:1px solid var(--border)}
  .sidebar-nav{display:flex;flex-wrap:wrap;padding:0;gap:4px;align-items:center}
  .sidebar-nav a{padding:8px 12px;font-size:.82rem}
  .sidebar-footer{display:none}
  .main-content{padding:18px}
  .cards-grid{grid-template-columns:1fr 1fr}
  .exam-header{flex-direction:column;gap:12px;position:relative;top:0}
}
@media(max-width:480px){
  .cards-grid{grid-template-columns:1fr}
  .form-card{padding:20px}
  .auth-card{padding:28px 20px}
  .error-card{padding:32px 20px}
  .error-code{font-size:3.5rem}
}
"""

# ─────────────────────────────────────────────
#  ERROR PAGE RENDERER
# ─────────────────────────────────────────────
def render_error_page(code, title, description, icon_color="var(--red)", show_login=False):
    """Render a styled standalone error page (no sidebar)."""
    back_btn = f'<a href="{url_for("dashboard")}" class="btn btn-secondary">Go to Dashboard</a>' \
               if "user_id" in session else \
               f'<a href="{url_for("login")}" class="btn btn-secondary">Go to Login</a>'
    login_btn = f'<a href="{url_for("login")}" class="btn btn-primary">Login</a>' if show_login else ""
    home_btn  = f'<a href="javascript:history.back()" class="btn btn-secondary">Go Back</a>'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Error {code} &mdash; ExamSys</title>
<style>{GLOBAL_STYLE}</style>
</head>
<body>
<div class="error-page">
  <div class="error-card">
    <div class="error-code" style="color:{icon_color}">{code}</div>
    <h1 class="error-title">{title}</h1>
    <p class="error-desc">{description}</p>
    <div class="error-actions">
      {home_btn}
      {back_btn}
      {login_btn}
    </div>
    <p style="margin-top:24px;font-size:.78rem;color:var(--text3)">&#9670; ExamSys &mdash; Examination Platform</p>
  </div>
</div>
</body></html>"""
    return html

# ─────────────────────────────────────────────
#  ERROR HANDLERS
# ─────────────────────────────────────────────

@app.errorhandler(400)
def bad_request(e):
    """400 Bad Request — malformed request syntax or invalid parameters."""
    html = render_error_page(
        code=400,
        title="Bad Request",
        description="The server could not understand your request due to invalid syntax or missing parameters. "
                    "Please check your input and try again.",
        icon_color="var(--yellow)"
    )
    return html, 400


@app.errorhandler(401)
def unauthorized(e):
    """401 Unauthorized — authentication required."""
    html = render_error_page(
        code=401,
        title="Unauthorized",
        description="You need to be logged in to access this page. "
                    "Please sign in with your credentials to continue.",
        icon_color="var(--yellow)",
        show_login=True
    )
    return html, 401


@app.errorhandler(403)
def forbidden(e):
    """403 Forbidden — authenticated but not allowed."""
    html = render_error_page(
        code=403,
        title="Access Forbidden",
        description="You don't have permission to access this page. "
                    "If you believe this is a mistake, please contact your administrator.",
        icon_color="var(--red)"
    )
    return html, 403


@app.errorhandler(404)
def not_found(e):
    """404 Not Found — page or resource does not exist."""
    html = render_error_page(
        code=404,
        title="Page Not Found",
        description=f"The page <code style='background:var(--navy2);padding:2px 8px;border-radius:6px;"
                    f"font-size:.88rem;color:var(--green)'>{request.path}</code> does not exist. "
                    f"It may have been moved, deleted, or you may have mistyped the URL.",
        icon_color="var(--text2)"
    )
    return html, 404


@app.errorhandler(405)
def method_not_allowed(e):
    """405 Method Not Allowed — wrong HTTP verb used."""
    html = render_error_page(
        code=405,
        title="Method Not Allowed",
        description=f"The <strong>{request.method}</strong> method is not allowed for this endpoint. "
                    f"Please use the correct HTTP method or navigate via the application.",
        icon_color="var(--yellow)"
    )
    return html, 405


@app.errorhandler(408)
def request_timeout(e):
    """408 Request Timeout — client took too long to send the request."""
    html = render_error_page(
        code=408,
        title="Request Timeout",
        description="Your request took too long to reach the server and timed out. "
                    "This can happen with a slow connection. Please try again.",
        icon_color="var(--yellow)"
    )
    return html, 408


@app.errorhandler(409)
def conflict(e):
    """409 Conflict — e.g. duplicate email registration."""
    html = render_error_page(
        code=409,
        title="Conflict",
        description="Your request could not be completed because it conflicts with existing data "
                    "(for example, a duplicate email address). Please go back and try different values.",
        icon_color="var(--yellow)"
    )
    return html, 409


@app.errorhandler(410)
def gone(e):
    """410 Gone — resource has been permanently removed."""
    html = render_error_page(
        code=410,
        title="Gone",
        description="The resource you are looking for has been permanently removed "
                    "and is no longer available on this server.",
        icon_color="var(--text3)"
    )
    return html, 410


@app.errorhandler(413)
def payload_too_large(e):
    """413 Payload Too Large — uploaded file or request body exceeds limit."""
    html = render_error_page(
        code=413,
        title="Payload Too Large",
        description="The data you submitted is too large for the server to process. "
                    "Please reduce the size of your input or file and try again.",
        icon_color="var(--yellow)"
    )
    return html, 413


@app.errorhandler(422)
def unprocessable_entity(e):
    """422 Unprocessable Entity — request well-formed but semantically incorrect."""
    html = render_error_page(
        code=422,
        title="Unprocessable Request",
        description="The server understood your request but could not process the data you sent. "
                    "Please check your input fields for errors and try again.",
        icon_color="var(--yellow)"
    )
    return html, 422


@app.errorhandler(429)
def too_many_requests(e):
    """429 Too Many Requests — rate limit exceeded."""
    html = render_error_page(
        code=429,
        title="Too Many Requests",
        description="You have sent too many requests in a short period of time. "
                    "Please wait a moment and try again.",
        icon_color="var(--yellow)"
    )
    return html, 429


@app.errorhandler(500)
def internal_server_error(e):
    """500 Internal Server Error — unhandled exception on the server."""
    # Log the full traceback to console for debugging
    app.logger.error("500 Internal Server Error: %s\n%s", str(e), traceback.format_exc())
    html = render_error_page(
        code=500,
        title="Internal Server Error",
        description="Something went wrong on our end. The server encountered an unexpected condition "
                    "and could not complete your request. Our team has been notified. "
                    "Please try again in a few moments.",
        icon_color="var(--red)"
    )
    return html, 500


@app.errorhandler(502)
def bad_gateway(e):
    """502 Bad Gateway — upstream server returned an invalid response."""
    html = render_error_page(
        code=502,
        title="Bad Gateway",
        description="The server received an invalid response from an upstream server. "
                    "This is usually a temporary issue. Please try again shortly.",
        icon_color="var(--red)"
    )
    return html, 502


@app.errorhandler(503)
def service_unavailable(e):
    """503 Service Unavailable — server is overloaded or down for maintenance."""
    html = render_error_page(
        code=503,
        title="Service Unavailable",
        description="The server is currently unable to handle your request due to temporary overload "
                    "or scheduled maintenance. Please try again in a few minutes.",
        icon_color="var(--red)"
    )
    return html, 503


@app.errorhandler(504)
def gateway_timeout(e):
    """504 Gateway Timeout — upstream server did not respond in time."""
    html = render_error_page(
        code=504,
        title="Gateway Timeout",
        description="The server did not receive a timely response from an upstream server. "
                    "This is usually temporary. Please try again in a moment.",
        icon_color="var(--red)"
    )
    return html, 504


@app.errorhandler(Exception)
def handle_unexpected_error(e):
    """Catch-all handler for any unhandled Python exception."""
    app.logger.error("Unhandled Exception: %s\n%s", str(e), traceback.format_exc())

    # If it's already an HTTP exception (e.g. raised by abort()), re-use its code
    code = getattr(e, "code", 500)
    if isinstance(code, int) and 400 <= code < 600:
        return internal_server_error(e) if code == 500 else render_error_page(
            code=code,
            title="An Error Occurred",
            description=f"An unexpected error occurred: {str(e)}. "
                        "Please go back or return to the dashboard.",
            icon_color="var(--red)"
        ), code

    html = render_error_page(
        code=500,
        title="Unexpected Error",
        description="An unexpected error occurred while processing your request. "
                    "Please try again or contact support if the problem persists.",
        icon_color="var(--red)"
    )
    return html, 500


# ─────────────────────────────────────────────
#  BASE LAYOUT
# ─────────────────────────────────────────────
def base_layout(content, active=""):
    role = session.get("role","")
    name = session.get("name","")
    nav_links = ""

    if role == "admin":
        nav_links = f"""
        <a href="{url_for('admin_dashboard')}" class="{'active' if active=='dashboard' else ''}">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>Dashboard</a>
        <a href="{url_for('admin_courses')}" class="{'active' if active=='courses' else ''}">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>Courses</a>
        <a href="{url_for('admin_users')}" class="{'active' if active=='users' else ''}">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>Users</a>
        """
    elif role == "teacher":
        nav_links = f"""
        <a href="{url_for('teacher_dashboard')}" class="{'active' if active=='dashboard' else ''}">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>Dashboard</a>
        <a href="{url_for('create_exam')}" class="{'active' if active=='create_exam' else ''}">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/></svg>Create Exam</a>
        <a href="{url_for('teacher_exams')}" class="{'active' if active=='exams' else ''}">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>My Exams</a>
        """
    elif role == "student":
        nav_links = f"""
        <a href="{url_for('student_dashboard')}" class="{'active' if active=='dashboard' else ''}">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>Dashboard</a>
        <a href="{url_for('available_exams')}" class="{'active' if active=='exams' else ''}">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>Take Exam</a>
        <a href="{url_for('my_results')}" class="{'active' if active=='results' else ''}">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>My Results</a>
        """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ExamSys &mdash; Online Examination System</title>
<style>{GLOBAL_STYLE}</style>
</head>
<body>
<div class="app-wrapper">
  <aside class="sidebar">
    <div class="sidebar-logo">
      <h2>&#9670; ExamSys</h2>
      <span>Examination Platform</span>
    </div>
    <nav class="sidebar-nav">
      {nav_links}
      <a href="{url_for('logout')}" style="margin-top:auto;color:var(--red)">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>Logout</a>
    </nav>
    <div class="sidebar-footer">
      <strong>{name}</strong>
      <span style="text-transform:capitalize">{role}</span>
    </div>
  </aside>
  <main class="main-content">
    {_flashes()}
    {content}
  </main>
</div>
</body></html>"""

def _flashes():
    msgs = ""
    for cat, msg in get_flashed_messages(with_categories=True):
        icon = "✓" if cat=="success" else ("✕" if cat=="danger" else "!")
        msgs += f'<div class="alert alert-{cat}">{icon} {msg}</div>'
    return msgs

from flask import get_flashed_messages

# ─────────────────────────────────────────────
#  AUTH ROUTES
# ─────────────────────────────────────────────
@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    role = session.get("role")
    if role == "admin":    return redirect(url_for("admin_dashboard"))
    if role == "teacher":  return redirect(url_for("teacher_dashboard"))
    return redirect(url_for("student_dashboard"))

@app.route("/login", methods=["GET","POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    error = ""
    if request.method == "POST":
        email = request.form.get("email","").strip()
        pw    = request.form.get("password","")
        user  = query("SELECT * FROM users WHERE email=?", [email], one=True)
        if user and check_password_hash(user["password"], pw):
            session["user_id"] = user["id"]
            session["name"]    = user["name"]
            session["role"]    = user["role"]
            return redirect(url_for("dashboard"))
        error = "Invalid email or password."
    html = f"""
    <div class="auth-page">
      <div class="auth-card">
        <div class="logo">
          <div class="logo-icon"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg></div>
          <span style="font-family:'Space Grotesk',sans-serif;font-weight:700;font-size:1.1rem;color:var(--green)">ExamSys</span>
        </div>
        <h1>Welcome back</h1>
        <p class="sub">Sign in to your account to continue</p>
        {"<div class='alert alert-danger'>✕ "+error+"</div>" if error else ""}
        <form method="POST">
          <div class="form-group"><label>Email Address</label>
            <input type="email" name="email" placeholder="you@example.com" required></div>
          <div class="form-group"><label>Password</label>
            <input type="password" name="password" placeholder="••••••••" required></div>
          <button class="btn btn-primary" style="width:100%;justify-content:center;padding:13px" type="submit">Sign In</button>
        </form>
        <p style="text-align:center;margin-top:20px;font-size:.88rem;color:var(--text3)">
          No account? <a href="{url_for('register')}" style="color:var(--green);text-decoration:none">Register here</a></p>
        <p style="text-align:center;margin-top:8px;font-size:.78rem;color:var(--text3)"> </p>
      </div>
    </div>"""
    return render_template_string(f"<!DOCTYPE html><html><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Login &mdash; ExamSys</title><style>{GLOBAL_STYLE}</style></head><body>{html}</body></html>")

@app.route("/register", methods=["GET","POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    error = ""
    if request.method == "POST":
        name  = request.form.get("name","").strip()
        email = request.form.get("email","").strip()
        pw    = request.form.get("password","")
        role  = request.form.get("role","student")
        if role not in ("student","teacher"): role = "student"
        if not name or not email or not pw:
            error = "All fields are required."
        elif query("SELECT id FROM users WHERE email=?", [email], one=True):
            error = "Email already registered."
        else:
            execute("INSERT INTO users(name,email,password,role) VALUES(?,?,?,?)",
                    [name, email, generate_password_hash(pw), role])
            flash("Account created! Please login.","success")
            return redirect(url_for("login"))
    html = f"""
    <div class="auth-page">
      <div class="auth-card">
        <div class="logo">
          <div class="logo-icon"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg></div>
          <span style="font-family:'Space Grotesk',sans-serif;font-weight:700;font-size:1.1rem;color:var(--green)">ExamSys</span>
        </div>
        <h1>Create Account</h1>
        <p class="sub">Join the examination platform</p>
        {"<div class='alert alert-danger'>✕ "+error+"</div>" if error else ""}
        <form method="POST">
          <div class="form-group"><label>Full Name</label>
            <input type="text" name="name" placeholder="John Doe" required></div>
          <div class="form-group"><label>Email Address</label>
            <input type="email" name="email" placeholder="you@example.com" required></div>
          <div class="form-group"><label>Password</label>
            <input type="password" name="password" placeholder="Min. 6 characters" required></div>
          <div class="form-group"><label>Register As</label>
            <select name="role">
              <option value="student">Student</option>
              <option value="teacher">Teacher</option>
            </select></div>
          <button class="btn btn-primary" style="width:100%;justify-content:center;padding:13px" type="submit">Create Account</button>
        </form>
        <p style="text-align:center;margin-top:20px;font-size:.88rem;color:var(--text3)">
          Have an account? <a href="{url_for('login')}" style="color:var(--green);text-decoration:none">Sign in</a></p>
      </div>
    </div>"""
    return render_template_string(f"<!DOCTYPE html><html><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Register &mdash; ExamSys</title><style>{GLOBAL_STYLE}</style></head><body>{html}</body></html>")

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.","info")
    return redirect(url_for("login"))

# ─────────────────────────────────────────────
#  ADMIN ROUTES
# ─────────────────────────────────────────────
@app.route("/admin")
@role_required("admin")
def admin_dashboard():
    total_users    = query("SELECT COUNT(*) c FROM users WHERE role!='admin'",one=True)["c"]
    total_students = query("SELECT COUNT(*) c FROM users WHERE role='student'",one=True)["c"]
    total_teachers = query("SELECT COUNT(*) c FROM users WHERE role='teacher'",one=True)["c"]
    total_courses  = query("SELECT COUNT(*) c FROM courses",one=True)["c"]
    total_exams    = query("SELECT COUNT(*) c FROM exams",one=True)["c"]
    total_results  = query("SELECT COUNT(*) c FROM results",one=True)["c"]
    recent = query("""SELECT u.name,u.email,u.role,r.score,r.percentage,
                             e.title,r.taken_at FROM results r
                      JOIN users u ON u.id=r.student_id
                      JOIN exams e ON e.id=r.exam_id
                      ORDER BY r.id DESC LIMIT 8""")
    rows = ""
    for r in recent:
        pct = round(r["percentage"],1)
        color = "var(--green)" if pct>=75 else ("var(--yellow)" if pct>=50 else "var(--red)")
        rows += f"""<tr>
          <td>{r['name']}</td><td style="color:var(--text3)">{r['email']}</td>
          <td>{r['title']}</td>
          <td><span style="color:{color};font-weight:700">{r['score']}</span></td>
          <td><span style="color:{color}">{pct}%</span></td>
          <td style="color:var(--text3);font-size:.82rem">{r['taken_at'][:16]}</td>
        </tr>"""
    content = f"""
    <div class="page-header"><h1>Admin Dashboard</h1><p>Overview of the entire examination system</p></div>
    <div class="cards-grid">
      <div class="stat-card" style="animation-delay:.05s"><div class="icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg></div><h3>{total_users}</h3><p>Total Users</p></div>
      <div class="stat-card" style="animation-delay:.1s"><div class="icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="8" r="7"/><polyline points="8.21 13.89 7 23 12 20 17 23 15.79 13.88"/></svg></div><h3>{total_students}</h3><p>Students</p></div>
      <div class="stat-card" style="animation-delay:.15s"><div class="icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg></div><h3>{total_teachers}</h3><p>Teachers</p></div>
      <div class="stat-card" style="animation-delay:.2s"><div class="icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg></div><h3>{total_courses}</h3><p>Courses</p></div>
      <div class="stat-card" style="animation-delay:.25s"><div class="icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg></div><h3>{total_exams}</h3><p>Exams Created</p></div>
      <div class="stat-card" style="animation-delay:.3s"><div class="icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg></div><h3>{total_results}</h3><p>Exams Taken</p></div>
    </div>
    <div class="section-title"><h2>Recent Exam Submissions</h2></div>
    <div class="table-wrap">
      <table><thead><tr><th>Student</th><th>Email</th><th>Exam</th><th>Score</th><th>%</th><th>Date</th></tr></thead>
      <tbody>{"".join(rows) if rows else "<tr><td colspan='6' style='text-align:center;color:var(--text3);padding:30px'>No submissions yet</td></tr>"}</tbody></table>
    </div>"""
    return render_template_string(base_layout(content,"dashboard"))

@app.route("/admin/courses", methods=["GET","POST"])
@role_required("admin")
def admin_courses():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "add":
            name = request.form.get("course_name","").strip()
            if name:
                execute("INSERT INTO courses(course_name) VALUES(?)",[name])
                flash(f'Course "{name}" added.','success')
        elif action == "edit":
            cid  = request.form.get("course_id")
            name = request.form.get("course_name","").strip()
            if cid and name:
                execute("UPDATE courses SET course_name=? WHERE id=?",[name,cid])
                flash("Course updated.","success")
        elif action == "delete":
            cid = request.form.get("course_id")
            execute("DELETE FROM courses WHERE id=?",[cid])
            flash("Course deleted.","danger")
        return redirect(url_for("admin_courses"))
    courses = query("SELECT * FROM courses ORDER BY id DESC")
    rows = ""
    for c in courses:
        rows += f"""<tr>
          <td>{c['id']}</td><td>{c['course_name']}</td>
          <td>
            <form method="POST" style="display:inline;margin-right:6px" onsubmit="return promptEdit(this,'{c['course_name']}')">
              <input type="hidden" name="action" value="edit">
              <input type="hidden" name="course_id" value="{c['id']}">
              <input type="hidden" name="course_name" id="en_{c['id']}">
              <button class="btn btn-warning btn-sm" type="submit">Edit</button>
            </form>
            <form method="POST" style="display:inline" onsubmit="return confirm('Delete this course?')">
              <input type="hidden" name="action" value="delete">
              <input type="hidden" name="course_id" value="{c['id']}">
              <button class="btn btn-danger btn-sm" type="submit">Delete</button>
            </form>
          </td></tr>"""
    content = f"""
    <div class="page-header"><h1>Manage Courses</h1><p>Add, edit, or remove courses</p></div>
    <div class="form-card" style="margin-bottom:28px;max-width:460px">
      <div class="section-title"><h2>Add New Course</h2></div>
      <form method="POST">
        <input type="hidden" name="action" value="add">
        <div class="form-group"><label>Course Name</label>
          <input type="text" name="course_name" placeholder="e.g. Introduction to Python" required></div>
        <button class="btn btn-primary" type="submit">Add Course</button>
      </form>
    </div>
    <div class="section-title"><h2>All Courses</h2></div>
    <div class="table-wrap">
      <table><thead><tr><th>#</th><th>Course Name</th><th>Actions</th></tr></thead>
      <tbody>{"".join(rows) if rows else "<tr><td colspan='3' style='text-align:center;color:var(--text3);padding:30px'>No courses yet</td></tr>"}</tbody></table>
    </div>
    <script>
    function promptEdit(form,current){{
      var v=prompt("Edit course name:",current);
      if(!v||!v.trim())return false;
      form.querySelector('[id^="en_"]').value=v.trim();
      return true;
    }}
    </script>"""
    return render_template_string(base_layout(content,"courses"))

@app.route("/admin/users")
@role_required("admin")
def admin_users():
    users = query("SELECT * FROM users WHERE role!='admin' ORDER BY role,name")
    rows = ""
    for u in users:
        badge = f'<span class="badge badge-{u["role"]}">{u["role"].capitalize()}</span>'
        rows += f"""<tr>
          <td>{u['id']}</td><td>{u['name']}</td>
          <td style="color:var(--text3)">{u['email']}</td>
          <td>{badge}</td>
          <td>
            <form method="POST" action="{url_for('admin_delete_user',uid=u['id'])}" onsubmit="return confirm('Delete user {u['name']}?')">
              <button class="btn btn-danger btn-sm" type="submit">Delete</button>
            </form>
          </td></tr>"""
    content = f"""
    <div class="page-header"><h1>Manage Users</h1><p>View and manage all registered users</p></div>
    <div class="table-wrap">
      <table><thead><tr><th>#</th><th>Name</th><th>Email</th><th>Role</th><th>Action</th></tr></thead>
      <tbody>{"".join(rows) if rows else "<tr><td colspan='5' style='text-align:center;color:var(--text3);padding:30px'>No users found</td></tr>"}</tbody></table>
    </div>"""
    return render_template_string(base_layout(content,"users"))

@app.route("/admin/users/delete/<int:uid>", methods=["POST"])
@role_required("admin")
def admin_delete_user(uid):
    execute("DELETE FROM student_answers WHERE student_id=?",[uid])
    execute("DELETE FROM results WHERE student_id=?",[uid])
    execute("DELETE FROM users WHERE id=?",[uid])
    flash("User deleted.","danger")
    return redirect(url_for("admin_users"))

# ─────────────────────────────────────────────
#  TEACHER ROUTES
# ─────────────────────────────────────────────
@app.route("/teacher")
@role_required("teacher")
def teacher_dashboard():
    tid = session["user_id"]
    total_exams = query("SELECT COUNT(*) c FROM exams WHERE teacher_id=?", [tid], one=True)["c"]
    total_q     = query("""SELECT COUNT(*) c FROM questions q
                           JOIN exams e ON e.id=q.exam_id WHERE e.teacher_id=?""",[tid],one=True)["c"]
    total_taken = query("""SELECT COUNT(*) c FROM results r
                           JOIN exams e ON e.id=r.exam_id WHERE e.teacher_id=?""",[tid],one=True)["c"]
    exams = query("""SELECT e.*,c.course_name,
                     (SELECT COUNT(*) FROM questions WHERE exam_id=e.id) qc,
                     (SELECT COUNT(*) FROM results WHERE exam_id=e.id) rc
                     FROM exams e JOIN courses c ON c.id=e.course_id
                     WHERE e.teacher_id=? ORDER BY e.id DESC LIMIT 6""",[tid])
    rows = "".join(f"""<tr>
      <td>{e['title']}</td><td>{e['course_name']}</td>
      <td style="color:var(--text2)">{e['timer_minutes']} min</td>
      <td><span class="badge badge-student">{e['qc']} Q</span></td>
      <td>{e['rc']}</td>
      <td>
        <a href="{url_for('view_exam',eid=e['id'])}" class="btn btn-secondary btn-sm">View</a>
        <a href="{url_for('edit_exam',eid=e['id'])}" class="btn btn-warning btn-sm">Edit</a>
      </td></tr>""" for e in exams)
    content = f"""
    <div class="page-header"><h1>Teacher Dashboard</h1><p>Manage your exams and track student performance</p></div>
    <div class="cards-grid">
      <div class="stat-card"><div class="icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg></div><h3>{total_exams}</h3><p>Exams Created</p></div>
      <div class="stat-card" style="animation-delay:.1s"><div class="icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/></svg></div><h3>{total_q}</h3><p>Questions</p></div>
      <div class="stat-card" style="animation-delay:.2s"><div class="icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/></svg></div><h3>{total_taken}</h3><p>Student Attempts</p></div>
    </div>
    <div class="section-title"><h2>Recent Exams</h2>
      <a href="{url_for('create_exam')}" class="btn btn-primary btn-sm">+ Create Exam</a>
    </div>
    <div class="table-wrap">
      <table><thead><tr><th>Title</th><th>Course</th><th>Timer</th><th>Questions</th><th>Attempts</th><th>Actions</th></tr></thead>
      <tbody>{"".join(rows) if rows else "<tr><td colspan='6' style='text-align:center;color:var(--text3);padding:30px'>No exams created yet</td></tr>"}</tbody></table>
    </div>"""
    return render_template_string(base_layout(content,"dashboard"))

@app.route("/teacher/exams")
@role_required("teacher")
def teacher_exams():
    tid = session["user_id"]
    exams = query("""SELECT e.*,c.course_name,
                     (SELECT COUNT(*) FROM questions WHERE exam_id=e.id) qc,
                     (SELECT COUNT(*) FROM results WHERE exam_id=e.id) rc
                     FROM exams e JOIN courses c ON c.id=e.course_id
                     WHERE e.teacher_id=? ORDER BY e.id DESC""",[tid])
    rows = "".join(f"""<tr>
      <td>{e['title']}</td><td>{e['course_name']}</td>
      <td>{e['timer_minutes']} min</td>
      <td><span class="badge badge-student">{e['qc']}</span></td>
      <td>{e['rc']}</td>
      <td>
        <a href="{url_for('view_exam',eid=e['id'])}" class="btn btn-secondary btn-sm">View</a>
        <a href="{url_for('edit_exam',eid=e['id'])}" class="btn btn-warning btn-sm">Edit</a>
        <a href="{url_for('exam_results',eid=e['id'])}" class="btn btn-primary btn-sm">Results</a>
        <form method="POST" action="{url_for('delete_exam',eid=e['id'])}" style="display:inline" onsubmit="return confirm('Delete exam?')">
          <button class="btn btn-danger btn-sm" type="submit">Delete</button>
        </form>
      </td></tr>""" for e in exams)
    content = f"""
    <div class="page-header"><h1>My Exams</h1><p>All exams you have created</p></div>
    <div class="section-title"><h2></h2><a href="{url_for('create_exam')}" class="btn btn-primary">+ Create New Exam</a></div>
    <div class="table-wrap">
      <table><thead><tr><th>Title</th><th>Course</th><th>Timer</th><th>Questions</th><th>Attempts</th><th>Actions</th></tr></thead>
      <tbody>{"".join(rows) if rows else "<tr><td colspan='6' style='text-align:center;color:var(--text3);padding:30px'>No exams yet. Create one!</td></tr>"}</tbody></table>
    </div>"""
    return render_template_string(base_layout(content,"exams"))

@app.route("/teacher/exam/create", methods=["GET","POST"])
@role_required("teacher")
def create_exam():
    courses = query("SELECT * FROM courses ORDER BY course_name")
    if not courses:
        flash("No courses available. Ask admin to add courses first.","warning")
        return redirect(url_for("teacher_dashboard"))
    if request.method == "POST":
        title   = request.form.get("title","").strip()
        cid     = request.form.get("course_id")
        timer   = request.form.get("timer_minutes","30")
        if not title or not cid:
            flash("Title and course are required.","danger")
            return redirect(url_for("create_exam"))
        eid = execute("INSERT INTO exams(course_id,teacher_id,title,timer_minutes) VALUES(?,?,?,?)",
                      [cid, session["user_id"], title, timer])
        # process questions
        qtypes   = request.form.getlist("q_type[]")
        qtexts   = request.form.getlist("q_text[]")
        qcorrect = request.form.getlist("q_correct[]")
        for i, (qt, qtext, qcorr) in enumerate(zip(qtypes, qtexts, qcorrect)):
            if not qtext.strip(): continue
            choices = None
            if qt == "mcq":
                opts = []
                for letter in "ABCDEFGH":
                    v = request.form.get(f"q_choice_{i}_{letter}","").strip()
                    if v: opts.append(f"{letter}:{v}")
                choices = "|".join(opts)
            execute("INSERT INTO questions(exam_id,question_text,type,choices,correct_answer) VALUES(?,?,?,?,?)",
                    [eid, qtext.strip(), qt, choices, qcorr.strip()])
        flash(f'Exam "{title}" created successfully! ✓',"success")
        return redirect(url_for("teacher_exams"))

    opts_html = "\n".join(f'<option value="{c["id"]}">{c["course_name"]}</option>' for c in courses)
    content = f"""
    <div class="page-header"><h1>Create Exam</h1><p>Build a new examination for your students</p></div>
    <div class="form-card" style="max-width:760px">
      <form method="POST" id="examForm">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
          <div class="form-group"><label>Exam Title</label>
            <input type="text" name="title" placeholder="e.g. Midterm Exam" required></div>
          <div class="form-group"><label>Course</label>
            <select name="course_id" required>{opts_html}</select></div>
        </div>
        <div class="form-group" style="max-width:200px"><label>Timer (minutes)</label>
          <input type="number" name="timer_minutes" value="30" min="1" max="300" required></div>

        <div style="margin:24px 0 16px;padding-top:20px;border-top:1px solid var(--border)">
          <div class="section-title"><h2>Questions</h2>
            <button type="button" class="btn btn-primary btn-sm" onclick="addQuestion()">+ Add Question</button>
          </div>
          <div id="questions-container"></div>
        </div>
        <button class="btn btn-primary" type="submit" style="padding:13px 32px">Create Exam</button>
      </form>
    </div>
    <script>
    var qCount=0;
    function addQuestion(){{
      var i=qCount++;
      var div=document.createElement('div');
      div.className='question-card';
      div.id='q_'+i;
      div.innerHTML=`
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
          <span class="question-num">Question ${{i+1}}</span>
          <button type="button" onclick="document.getElementById('q_${{i}}').remove()" style="background:none;border:none;color:var(--red);cursor:pointer;font-size:1.2rem">&times;</button>
        </div>
        <div class="form-group"><label>Question Type</label>
          <select name="q_type[]" onchange="typeChange(this,${{i}})">
            <option value="mcq">Multiple Choice (A–H)</option>
            <option value="tf">True / False</option>
            <option value="essay">Essay</option>
          </select></div>
        <div class="form-group"><label>Question Text</label>
          <textarea name="q_text[]" placeholder="Enter your question here..." required></textarea></div>
        <div id="choices_${{i}}">
          ${{mcqChoices(i)}}
        </div>
        <div class="form-group"><label>Correct Answer <span style="color:var(--text3);font-weight:400">(leave blank for essay)</span></label>
          <input type="text" name="q_correct[]" placeholder="e.g. A or True"></div>`;
      document.getElementById('questions-container').appendChild(div);
    }}
    function mcqChoices(i){{
      var html='<div class="form-group"><label>Answer Options (fill in at least 2)</label><div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">';
      ['A','B','C','D','E','F','G','H'].forEach(function(l){{
        html+=`<div style="display:flex;align-items:center;gap:8px">
          <span style="color:var(--green);font-weight:700;width:14px">${{l}}</span>
          <input type="text" name="q_choice_${{i}}_${{l}}" placeholder="Option ${{l}}" style="flex:1;padding:8px 12px;background:var(--navy2);border:1px solid var(--border);border-radius:8px;color:var(--text);font-size:.88rem">
        </div>`;
      }});
      html+='</div></div>';
      return html;
    }}
    function tfChoices(){{
      return '<div class="form-group" style="color:var(--text3);font-size:.88rem">Correct answer: type <strong style=color:var(--green)>True</strong> or <strong style=color:var(--green)>False</strong></div>';
    }}
    function typeChange(sel,i){{
      var box=document.getElementById('choices_'+i);
      if(sel.value==='mcq') box.innerHTML=mcqChoices(i);
      else if(sel.value==='tf') box.innerHTML=tfChoices();
      else box.innerHTML='<div class="form-group" style="color:var(--text3);font-size:.88rem">Essay: students type their answer. Leave correct answer blank; review manually.</div>';
    }}
    addQuestion();
    </script>"""
    return render_template_string(base_layout(content,"create_exam"))

@app.route("/teacher/exam/<int:eid>")
@role_required("teacher")
def view_exam(eid):
    exam = query("SELECT e.*,c.course_name FROM exams e JOIN courses c ON c.id=e.course_id WHERE e.id=? AND e.teacher_id=?",
                 [eid,session["user_id"]],one=True)
    if not exam: flash("Exam not found.","danger"); return redirect(url_for("teacher_exams"))
    questions = query("SELECT * FROM questions WHERE exam_id=? ORDER BY id",[eid])
    q_html = ""
    for i,q in enumerate(questions):
        type_badge = {"mcq":"Multiple Choice","tf":"True/False","essay":"Essay"}.get(q["type"],q["type"])
        choices_html = ""
        if q["type"] == "mcq" and q["choices"]:
            for opt in q["choices"].split("|"):
                if ":" in opt:
                    letter, text = opt.split(":",1)
                    is_correct = letter.strip() == (q["correct_answer"] or "").strip()
                    choices_html += f'<div style="padding:5px 0;color:{"var(--green)" if is_correct else "var(--text2)"};font-size:.88rem">{"✓ " if is_correct else ""}<strong>{letter}</strong>. {text}</div>'
        elif q["type"] == "tf":
            choices_html = f'<div style="color:var(--green);font-size:.88rem">✓ Correct: {q["correct_answer"]}</div>'
        else:
            choices_html = '<div style="color:var(--text3);font-size:.88rem"><em>Essay — manual review</em></div>'
        q_html += f"""<div class="question-card">
          <div style="display:flex;justify-content:space-between;align-items:flex-start">
            <span class="question-num">Question {i+1}</span>
            <span class="badge badge-{'student' if q['type']=='essay' else 'teacher'}">{type_badge}</span>
          </div>
          <p class="question-text">{q['question_text']}</p>
          {choices_html}
        </div>"""
    content = f"""
    <div class="page-header">
      <h1>{exam['title']}</h1>
      <p>{exam['course_name']} &bull; {exam['timer_minutes']} min &bull; {len(questions)} questions</p>
    </div>
    <div style="display:flex;gap:10px;margin-bottom:24px">
      <a href="{url_for('edit_exam',eid=eid)}" class="btn btn-warning">Edit Exam</a>
      <a href="{url_for('exam_results',eid=eid)}" class="btn btn-primary">View Results</a>
      <a href="{url_for('teacher_exams')}" class="btn btn-secondary">Back</a>
    </div>
    {q_html if q_html else '<div class="alert alert-info">No questions added yet.</div>'}"""
    return render_template_string(base_layout(content,"exams"))

@app.route("/teacher/exam/<int:eid>/edit", methods=["GET","POST"])
@role_required("teacher")
def edit_exam(eid):
    exam = query("SELECT * FROM exams WHERE id=? AND teacher_id=?",[eid,session["user_id"]],one=True)
    if not exam: flash("Exam not found.","danger"); return redirect(url_for("teacher_exams"))
    if request.method == "POST":
        title = request.form.get("title","").strip()
        timer = request.form.get("timer_minutes","30")
        cid   = request.form.get("course_id")
        execute("UPDATE exams SET title=?,timer_minutes=?,course_id=? WHERE id=?",[title,timer,cid,eid])
        flash("Exam updated.","success")
        return redirect(url_for("view_exam",eid=eid))
    courses = query("SELECT * FROM courses ORDER BY course_name")
    opts = "\n".join(f'<option value="{c["id"]}" {"selected" if c["id"]==exam["course_id"] else ""}>{c["course_name"]}</option>' for c in courses)
    content = f"""
    <div class="page-header"><h1>Edit Exam</h1></div>
    <div class="form-card">
      <form method="POST">
        <div class="form-group"><label>Title</label>
          <input type="text" name="title" value="{exam['title']}" required></div>
        <div class="form-group"><label>Course</label>
          <select name="course_id">{opts}</select></div>
        <div class="form-group"><label>Timer (minutes)</label>
          <input type="number" name="timer_minutes" value="{exam['timer_minutes']}" min="1" required></div>
        <div style="display:flex;gap:10px">
          <button class="btn btn-primary" type="submit">Save Changes</button>
          <a href="{url_for('view_exam',eid=eid)}" class="btn btn-secondary">Cancel</a>
        </div>
      </form>
    </div>"""
    return render_template_string(base_layout(content,"exams"))

@app.route("/teacher/exam/<int:eid>/delete", methods=["POST"])
@role_required("teacher")
def delete_exam(eid):
    exam = query("SELECT * FROM exams WHERE id=? AND teacher_id=?",[eid,session["user_id"]],one=True)
    if exam:
        execute("DELETE FROM student_answers WHERE exam_id=?",[eid])
        execute("DELETE FROM results WHERE exam_id=?",[eid])
        execute("DELETE FROM questions WHERE exam_id=?",[eid])
        execute("DELETE FROM exams WHERE id=?",[eid])
        flash("Exam deleted.","danger")
    return redirect(url_for("teacher_exams"))

@app.route("/teacher/exam/<int:eid>/results")
@role_required("teacher")
def exam_results(eid):
    exam = query("SELECT e.*,c.course_name FROM exams e JOIN courses c ON c.id=e.course_id WHERE e.id=? AND e.teacher_id=?",
                 [eid,session["user_id"]],one=True)
    if not exam: flash("Exam not found.","danger"); return redirect(url_for("teacher_exams"))
    results = query("""SELECT r.*,u.name,u.email FROM results r
                       JOIN users u ON u.id=r.student_id
                       WHERE r.exam_id=? ORDER BY r.percentage DESC""",[eid])
    rows = ""
    for r in results:
        pct   = round(r["percentage"],1)
        color = "var(--green)" if pct>=75 else ("var(--yellow)" if pct>=50 else "var(--red)")
        grade = "A" if pct>=90 else ("B" if pct>=75 else ("C" if pct>=60 else ("D" if pct>=50 else "F")))
        rows += f"""<tr>
          <td>{r['name']}</td><td style="color:var(--text3)">{r['email']}</td>
          <td style="color:var(--green);font-weight:700">{r['score']}</td>
          <td><div style="display:flex;align-items:center;gap:10px;min-width:140px">
            <div class="progress-wrap" style="flex:1"><div class="progress-bar" style="width:{pct}%"></div></div>
            <span style="color:{color};font-weight:700;font-size:.88rem">{pct}%</span>
          </div></td>
          <td><span style="color:{color};font-weight:700">{grade}</span></td>
          <td style="color:var(--text3);font-size:.82rem">{r['taken_at'][:16]}</td>
        </tr>"""
    # essay answers
    essays = query("""SELECT sa.answer,u.name,q.question_text FROM student_answers sa
                      JOIN questions q ON q.id=sa.question_id
                      JOIN users u ON u.id=sa.student_id
                      WHERE q.exam_id=? AND q.type='essay' ORDER BY u.name""",[eid])
    essay_html = ""
    if essays:
        essay_html = '<div class="section-title" style="margin-top:28px"><h2>Essay Answers (for review)</h2></div>'
        for e in essays:
            essay_html += f"""<div class="question-card" style="margin-bottom:12px">
              <p style="font-size:.8rem;color:var(--text3);margin-bottom:6px"><strong style="color:var(--text2)">{e['name']}</strong></p>
              <p style="font-size:.88rem;color:var(--text2);margin-bottom:8px"><em>{e['question_text']}</em></p>
              <p style="font-size:.92rem">{e['answer'] or '<em style="color:var(--text3)">No answer provided</em>'}</p>
            </div>"""
    content = f"""
    <div class="page-header"><h1>Results: {exam['title']}</h1><p>{exam['course_name']}</p></div>
    <div class="section-title"><h2>Student Scores</h2></div>
    <div class="table-wrap">
      <table><thead><tr><th>Student</th><th>Email</th><th>Score</th><th>Percentage</th><th>Grade</th><th>Date</th></tr></thead>
      <tbody>{"".join(rows) if rows else "<tr><td colspan='6' style='text-align:center;color:var(--text3);padding:30px'>No attempts yet</td></tr>"}</tbody></table>
    </div>
    {essay_html}"""
    return render_template_string(base_layout(content,"exams"))

# ─────────────────────────────────────────────
#  STUDENT ROUTES
# ─────────────────────────────────────────────
@app.route("/student")
@role_required("student")
def student_dashboard():
    sid = session["user_id"]
    taken   = query("SELECT COUNT(*) c FROM results WHERE student_id=?",[sid],one=True)["c"]
    avg_pct = query("SELECT AVG(percentage) a FROM results WHERE student_id=?",[sid],one=True)["a"] or 0
    results = query("""SELECT r.*,e.title,c.course_name FROM results r
                       JOIN exams e ON e.id=r.exam_id
                       JOIN courses c ON c.id=e.course_id
                       WHERE r.student_id=? ORDER BY r.id DESC LIMIT 8""",[sid])
    rows = ""
    for r in results:
        pct   = round(r["percentage"],1)
        color = "var(--green)" if pct>=75 else ("var(--yellow)" if pct>=50 else "var(--red)")
        grade = "A" if pct>=90 else ("B" if pct>=75 else ("C" if pct>=60 else ("D" if pct>=50 else "F")))
        rows += f"""<tr>
          <td>{r['title']}</td><td>{r['course_name']}</td>
          <td style="color:var(--green);font-weight:700">{r['score']}</td>
          <td><span style="color:{color};font-weight:700">{pct}%</span></td>
          <td><span style="color:{color}">{grade}</span></td>
          <td style="color:var(--text3);font-size:.82rem">{r['taken_at'][:16]}</td>
        </tr>"""
    content = f"""
    <div class="page-header"><h1>Student Dashboard</h1><p>Track your exams and performance</p></div>
    <div class="cards-grid">
      <div class="stat-card"><div class="icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg></div><h3>{taken}</h3><p>Exams Taken</p></div>
      <div class="stat-card" style="animation-delay:.1s"><div class="icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg></div><h3>{round(avg_pct,1)}%</h3><p>Average Score</p></div>
    </div>
    <div class="section-title"><h2>Recent Results</h2>
      <a href="{url_for('available_exams')}" class="btn btn-primary btn-sm">Take Exam</a>
    </div>
    <div class="table-wrap">
      <table><thead><tr><th>Exam</th><th>Course</th><th>Score</th><th>%</th><th>Grade</th><th>Date</th></tr></thead>
      <tbody>{"".join(rows) if rows else "<tr><td colspan='6' style='text-align:center;color:var(--text3);padding:30px'>No exams taken yet. <a href='"+url_for('available_exams')+"' style='color:var(--green)'>Start one!</a></td></tr>"}</tbody></table>
    </div>"""
    return render_template_string(base_layout(content,"dashboard"))

@app.route("/student/exams")
@role_required("student")
def available_exams():
    sid  = session["user_id"]
    taken_ids = [r["exam_id"] for r in query("SELECT exam_id FROM results WHERE student_id=?",[sid])]
    exams = query("""SELECT e.*,c.course_name,u.name teacher_name,
                     (SELECT COUNT(*) FROM questions WHERE exam_id=e.id) qc
                     FROM exams e JOIN courses c ON c.id=e.course_id
                     JOIN users u ON u.id=e.teacher_id
                     ORDER BY e.id DESC""")
    cards = ""
    for e in exams:
        done = e["id"] in taken_ids
        btn  = f'<span class="badge badge-teacher" style="padding:8px 16px">Completed</span>' if done else \
               f'<a href="{url_for("take_exam",eid=e["id"])}" class="btn btn-primary btn-sm">Start Exam</a>'
        cards += f"""<div class="stat-card" style="padding:20px;animation-delay:{exams.index(e)*0.05}s">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:12px">
            <span class="badge badge-student">{e['course_name']}</span>
            {"<span style='color:var(--green);font-size:.8rem'>✓ Done</span>" if done else ""}
          </div>
          <h3 style="font-size:1rem;margin-bottom:6px;font-family:'Space Grotesk',sans-serif">{e['title']}</h3>
          <p style="font-size:.82rem;color:var(--text3);margin-bottom:14px">
            By {e['teacher_name']} &bull; {e['qc']} questions &bull; {e['timer_minutes']} min
          </p>
          {btn}
        </div>"""
    content = f"""
    <div class="page-header"><h1>Available Exams</h1><p>Select an exam to start</p></div>
    <div class="cards-grid" style="grid-template-columns:repeat(auto-fill,minmax(260px,1fr))">
      {"".join(cards) if cards else "<p style='color:var(--text3)'>No exams available yet.</p>"}
    </div>"""
    return render_template_string(base_layout(content,"exams"))

@app.route("/student/exam/<int:eid>/take", methods=["GET","POST"])
@role_required("student")
def take_exam(eid):
    sid  = session["user_id"]
    exam = query("SELECT e.*,c.course_name FROM exams e JOIN courses c ON c.id=e.course_id WHERE e.id=?",[eid],one=True)
    if not exam: flash("Exam not found.","danger"); return redirect(url_for("available_exams"))
    already = query("SELECT id FROM results WHERE student_id=? AND exam_id=?",[sid,eid],one=True)
    if already: flash("You have already taken this exam.","warning"); return redirect(url_for("available_exams"))
    questions = query("SELECT * FROM questions WHERE exam_id=? ORDER BY id",[eid])
    if not questions: flash("This exam has no questions yet.","warning"); return redirect(url_for("available_exams"))

    if request.method == "POST":
        score   = 0
        total_gradable = 0
        for q in questions:
            ans = request.form.get(f"q_{q['id']}","").strip()
            execute("INSERT INTO student_answers(student_id,exam_id,question_id,answer) VALUES(?,?,?,?)",
                    [sid, eid, q["id"], ans])
            if q["type"] != "essay":
                total_gradable += 1
                if ans.strip().upper() == (q["correct_answer"] or "").strip().upper():
                    score += 1
        total_q = len(questions)
        pct = (score / total_gradable * 100) if total_gradable else 0
        execute("INSERT INTO results(student_id,exam_id,score,percentage,taken_at) VALUES(?,?,?,?,?)",
                [sid, eid, score, pct, datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
        return redirect(url_for("exam_result",eid=eid))

    # Build exam HTML
    q_html = ""
    for i, q in enumerate(questions):
        choices_html = ""
        if q["type"] == "mcq" and q["choices"]:
            choices_html = '<div class="choices">'
            for opt in q["choices"].split("|"):
                if ":" in opt:
                    letter, text = opt.split(":",1)
                    choices_html += f'<label><input type="radio" name="q_{q["id"]}" value="{letter.strip()}"><span>{letter.strip()}. {text}</span></label>'
            choices_html += '</div>'
        elif q["type"] == "tf":
            choices_html = f"""<div class="choices">
              <label><input type="radio" name="q_{q['id']}" value="True"><span>True</span></label>
              <label><input type="radio" name="q_{q['id']}" value="False"><span>False</span></label>
            </div>"""
        else:
            choices_html = f'<textarea class="essay-area" name="q_{q["id"]}" placeholder="Write your answer here..."></textarea>'
        q_html += f"""<div class="question-card" style="animation-delay:{i*0.05}s">
          <div class="question-num">Question {i+1} of {len(questions)}</div>
          <p class="question-text">{q['question_text']}</p>
          {choices_html}
        </div>"""

    total_sec = exam["timer_minutes"] * 60
    content = f"""
    <div class="exam-header">
      <div>
        <h2 style="font-family:'Space Grotesk',sans-serif;font-size:1.1rem">{exam['title']}</h2>
        <p style="font-size:.82rem;color:var(--text3)">{exam['course_name']} &bull; {len(questions)} questions</p>
      </div>
      <div style="display:flex;align-items:center;gap:16px">
        <div class="timer-ring">
          <svg width="64" height="64" viewBox="0 0 90 90">
            <circle cx="45" cy="45" r="40"/>
            <circle class="progress" cx="45" cy="45" r="40" id="timerRing" stroke-dashoffset="0"/>
          </svg>
          <div class="timer-text" id="timerText">{exam['timer_minutes']}:00</div>
        </div>
        <button onclick="submitExam()" class="btn btn-primary">Submit</button>
      </div>
    </div>
    <form method="POST" id="examForm">
      {q_html}
      <div style="display:flex;justify-content:center;margin-top:24px">
        <button type="button" onclick="submitExam()" class="btn btn-primary" style="padding:14px 48px;font-size:1rem">
          Submit Exam</button>
      </div>
    </form>
    <script>
    var total={total_sec},remaining={total_sec};
    var ring=document.getElementById('timerRing');
    var txt=document.getElementById('timerText');
    function fmt(s){{var m=Math.floor(s/60),sec=s%60;return m+':'+(sec<10?'0':'')+sec;}}
    function tick(){{
      remaining--;
      if(remaining<=0){{submitExam();return;}}
      var pct=1-(remaining/total);
      ring.style.strokeDashoffset=(251*pct).toFixed(2);
      txt.textContent=fmt(remaining);
      if(remaining<=60){{ring.style.stroke='var(--red)';txt.style.color='var(--red)';}}
      else if(remaining<=180){{ring.style.stroke='var(--yellow)';}}
    }}
    var timer=setInterval(tick,1000);
    function submitExam(){{clearInterval(timer);document.getElementById('examForm').submit();}}
    </script>"""
    return render_template_string(base_layout(content,"exams"))

@app.route("/student/exam/<int:eid>/result")
@role_required("student")
def exam_result(eid):
    sid    = session["user_id"]
    result = query("SELECT r.*,e.title,c.course_name FROM results r JOIN exams e ON e.id=r.exam_id JOIN courses c ON c.id=e.course_id WHERE r.exam_id=? AND r.student_id=?",
                   [eid,sid],one=True)
    if not result: flash("Result not found.","danger"); return redirect(url_for("student_dashboard"))
    pct   = round(result["percentage"],1)
    grade = "A" if pct>=90 else ("B" if pct>=75 else ("C" if pct>=60 else ("D" if pct>=50 else "F")))
    color = "var(--green)" if pct>=75 else ("var(--yellow)" if pct>=50 else "var(--red)")
    msg   = "Excellent work! 🎉" if pct>=90 else ("Great job! 👍" if pct>=75 else ("Good effort! 💪" if pct>=50 else "Keep studying! 📚"))
    questions = query("SELECT q.*,sa.answer FROM questions q LEFT JOIN student_answers sa ON sa.question_id=q.id AND sa.student_id=? WHERE q.exam_id=? ORDER BY q.id",[sid,eid])
    review_html = ""
    for i,q in enumerate(questions):
        ans = q["answer"] or ""
        if q["type"] == "essay":
            review_html += f"""<div class="question-card">
              <div class="question-num">Q{i+1} &mdash; Essay</div>
              <p class="question-text">{q['question_text']}</p>
              <p style="color:var(--text2);font-size:.9rem;background:var(--navy2);padding:10px;border-radius:8px">{ans or '<em style="color:var(--text3)">No answer given</em>'}</p>
              <p style="color:var(--text3);font-size:.8rem;margin-top:8px">Awaiting teacher review</p>
            </div>"""
        else:
            correct = (q["correct_answer"] or "").strip().upper()
            given   = ans.strip().upper()
            ok      = given == correct
            review_html += f"""<div class="question-card" style="border-color:{'rgba(0,200,150,.3)' if ok else 'rgba(255,77,109,.25)'}">
              <div style="display:flex;justify-content:space-between">
                <div class="question-num">Q{i+1}</div>
                <span style="font-size:.85rem;color:{'var(--green)' if ok else 'var(--red)'}">{'✓ Correct' if ok else '✕ Incorrect'}</span>
              </div>
              <p class="question-text">{q['question_text']}</p>
              <p style="font-size:.88rem">Your answer: <strong style="color:{'var(--green)' if ok else 'var(--red)'}">{ans or '—'}</strong></p>
              {"" if ok else f"<p style='font-size:.88rem;margin-top:4px'>Correct answer: <strong style='color:var(--green)'>{q['correct_answer']}</strong></p>"}
            </div>"""

    content = f"""
    <div class="page-header"><h1>Exam Result</h1><p>{result['title']} &mdash; {result['course_name']}</p></div>
    <div style="text-align:center;margin-bottom:32px;animation:fadeIn .6s ease">
      <div class="result-circle" style="border-color:{color}">
        <span class="score" style="color:{color}">{pct}%</span>
        <span class="label">Score</span>
      </div>
      <h2 style="font-family:'Space Grotesk',sans-serif;margin-bottom:8px">{msg}</h2>
      <p style="color:var(--text2)">Grade: <strong style="color:{color};font-size:1.2rem">{grade}</strong> &nbsp;&bull;&nbsp; Raw score: <strong>{result['score']}</strong></p>
      <div style="margin-top:20px;display:flex;gap:12px;justify-content:center">
        <a href="{url_for('available_exams')}" class="btn btn-secondary">Take Another Exam</a>
        <a href="{url_for('my_results')}" class="btn btn-primary">All My Results</a>
      </div>
    </div>
    <div class="section-title"><h2>Answer Review</h2></div>
    {review_html}"""
    return render_template_string(base_layout(content,"results"))

@app.route("/student/results")
@role_required("student")
def my_results():
    sid = session["user_id"]
    results = query("""SELECT r.*,e.title,c.course_name FROM results r
                       JOIN exams e ON e.id=r.exam_id
                       JOIN courses c ON c.id=e.course_id
                       WHERE r.student_id=? ORDER BY r.id DESC""",[sid])
    rows = ""
    for r in results:
        pct   = round(r["percentage"],1)
        color = "var(--green)" if pct>=75 else ("var(--yellow)" if pct>=50 else "var(--red)")
        grade = "A" if pct>=90 else ("B" if pct>=75 else ("C" if pct>=60 else ("D" if pct>=50 else "F")))
        rows += f"""<tr>
          <td>{r['title']}</td><td>{r['course_name']}</td>
          <td style="color:var(--green);font-weight:700">{r['score']}</td>
          <td>
            <div style="display:flex;align-items:center;gap:10px;min-width:140px">
              <div class="progress-wrap" style="flex:1"><div class="progress-bar" style="width:{pct}%"></div></div>
              <span style="color:{color};font-weight:700;font-size:.88rem">{pct}%</span>
            </div>
          </td>
          <td><span style="color:{color};font-weight:700">{grade}</span></td>
          <td style="color:var(--text3);font-size:.82rem">{r['taken_at'][:16]}</td>
          <td><a href="{url_for('exam_result',eid=r['exam_id'])}" class="btn btn-secondary btn-sm">Review</a></td>
        </tr>"""
    content = f"""
    <div class="page-header"><h1>My Results</h1><p>All your exam history and scores</p></div>
    <div class="table-wrap">
      <table><thead><tr><th>Exam</th><th>Course</th><th>Score</th><th>Percentage</th><th>Grade</th><th>Date</th><th></th></tr></thead>
      <tbody>{"".join(rows) if rows else "<tr><td colspan='7' style='text-align:center;color:var(--text3);padding:30px'>No exams taken yet.</td></tr>"}</tbody></table>
    </div>"""
    return render_template_string(base_layout(content,"results"))

# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    init_db()
    print("="*55)
    print("  ExamSys Online Examination System")
    print("  http://127.0.0.1:5000")
    print("="*55)
    app.run(debug=True, port=5000)