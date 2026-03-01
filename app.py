"""
=====================================================================
  SimpleNotes – AI-Powered Note-Taking App  (Single File Version)
=====================================================================
  Stack : Flask, SQLAlchemy, Flask-Login, Together AI, Tailwind CSS
  Run   : python app.py
  Setup :
    1. pip install flask flask-sqlalchemy flask-login flask-bcrypt
                   flask-wtf wtforms email-validator python-dotenv
                   psycopg2-binary together
    2. Create a .env file:
         DATABASE_URL=postgresql://user:pass@localhost/simplenotes_db
         TOGETHER_API_KEY=your_key_here
         SECRET_KEY=your_secret_key
    3. python app.py   →   visit http://localhost:5000
=====================================================================
"""

import os
from datetime import datetime
from dotenv import load_dotenv

from flask import (Flask, render_template_string, redirect, url_for,
                   flash, request, jsonify, Blueprint)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (LoginManager, UserMixin, login_user, logout_user,
                         login_required, current_user)
from flask_bcrypt import Bcrypt
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, Email, Length
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()

# ─────────────────────────────────────────
#  App & Config
# ─────────────────────────────────────────
app = Flask(__name__)
app.config["SECRET_KEY"]                  = os.getenv("SECRET_KEY", "dev-secret-key")
app.config["SQLALCHEMY_DATABASE_URI"]     = os.getenv("DATABASE_URL", "sqlite:///simplenotes.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["TOGETHER_API_KEY"]            = os.getenv("TOGETHER_API_KEY", "")
app.config["WTF_CSRF_ENABLED"]            = True

db           = SQLAlchemy(app)
bcrypt       = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

# ─────────────────────────────────────────
#  Models
# ─────────────────────────────────────────
class User(db.Model, UserMixin):
    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(64))
    email         = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    notes         = db.relationship("Note", backref="author", lazy=True)

class Note(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    title      = db.Column(db.String(128))
    content    = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    tags       = db.Column(db.String(256))
    user_id    = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    is_trashed = db.Column(db.Boolean, default=False)
    mood       = db.Column(db.String(64))
    versions   = db.relationship("NoteVersion", backref="note", lazy=True,
                                 cascade="all, delete-orphan")

class NoteVersion(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    note_id    = db.Column(db.Integer, db.ForeignKey("note.id"))
    title      = db.Column(db.String(128))
    content    = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ─────────────────────────────────────────
#  Forms
# ─────────────────────────────────────────
class RegisterForm(FlaskForm):
    name     = StringField("Name",     validators=[DataRequired()])
    email    = StringField("Email",    validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=6)])
    submit   = SubmitField("Register")

class LoginForm(FlaskForm):
    email    = StringField("Email",    validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])
    submit   = SubmitField("Login")

class NoteForm(FlaskForm):
    title   = StringField("Title",   validators=[DataRequired()])
    content = TextAreaField("Content", validators=[DataRequired()])
    tags    = StringField("Tags (comma-separated)")
    submit  = SubmitField("Save Note")

# ─────────────────────────────────────────
#  AI Utility
# ─────────────────────────────────────────
def call_together_ai(prompt, model="mistralai/Mixtral-8x7B-Instruct-v0.1"):
    try:
        from together import Together
        api_key = app.config.get("TOGETHER_API_KEY")
        if not api_key:
            return "TOGETHER_API_KEY is missing."
        client = Together(api_key=api_key)
        result = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=200,
        )
        content = result.choices[0].message.content
        return content.strip() if content else "AI returned no response."
    except Exception as e:
        return f"AI failed: {e}"

# ─────────────────────────────────────────
#  Templates
# ─────────────────────────────────────────
BASE = """
<!DOCTYPE html>
<html lang="en" class="light">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>SimpleNotes{% block title %}{% endblock %}</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script>tailwind.config = { darkMode: 'class' }</script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css"/>
  <style>body{transition:background-color .3s,color .3s}</style>
</head>
<body class="bg-gray-50 dark:bg-gray-900 text-gray-800 dark:text-gray-100 min-h-screen flex flex-col">

<!-- Navbar -->
<nav class="bg-white dark:bg-gray-800 shadow-md px-6 py-3 flex items-center justify-between sticky top-0 z-50">
  <a href="{{ url_for('home') }}" class="text-xl font-bold text-indigo-600 dark:text-indigo-400 flex items-center gap-2">
    <i class="fa-solid fa-note-sticky"></i> SimpleNotes
  </a>
  <div class="flex items-center gap-4">
    {% if current_user.is_authenticated %}
      <a href="{{ url_for('dashboard') }}"   class="text-sm hover:text-indigo-500 transition"><i class="fa-solid fa-table-columns mr-1"></i>Dashboard</a>
      <a href="{{ url_for('note_editor') }}" class="text-sm hover:text-indigo-500 transition"><i class="fa-solid fa-plus mr-1"></i>New Note</a>
      <a href="{{ url_for('trash') }}"       class="text-sm hover:text-indigo-500 transition"><i class="fa-solid fa-trash mr-1"></i>Trash</a>
      <a href="{{ url_for('logout') }}"      class="text-sm hover:text-red-500 transition"><i class="fa-solid fa-right-from-bracket mr-1"></i>Logout</a>
      <span class="text-xs text-gray-400 hidden sm:block">Hi, {{ current_user.name }}</span>
    {% else %}
      <a href="{{ url_for('login') }}"    class="text-sm hover:text-indigo-500 transition">Login</a>
      <a href="{{ url_for('register') }}" class="bg-indigo-600 text-white text-sm px-4 py-1.5 rounded-lg hover:bg-indigo-700 transition">Register</a>
    {% endif %}
    <button onclick="toggleDark()" class="ml-2 text-gray-500 dark:text-yellow-300 hover:scale-110 transition text-lg">
      <i class="fa-solid fa-moon" id="darkIcon"></i>
    </button>
  </div>
</nav>

<!-- Flash Messages -->
<div class="max-w-4xl mx-auto w-full px-4 mt-4">
  {% with messages = get_flashed_messages(with_categories=true) %}
    {% for category, message in messages %}
      <div class="flex items-center gap-2 px-4 py-2 rounded mb-2 text-sm
        {% if category == 'success' %}bg-green-100 text-green-800 border border-green-300
        {% elif category == 'danger' %}bg-red-100 text-red-800 border border-red-300
        {% elif category == 'warning' %}bg-yellow-100 text-yellow-800 border border-yellow-300
        {% else %}bg-blue-100 text-blue-800 border border-blue-300{% endif %}">
        <i class="fa-solid fa-circle-info"></i> {{ message }}
      </div>
    {% endfor %}
  {% endwith %}
</div>

<!-- Content -->
<main class="flex-1 max-w-5xl mx-auto w-full px-4 py-6">{% block content %}{% endblock %}</main>

<footer class="text-center text-xs text-gray-400 dark:text-gray-600 py-4">
  © 2025 SimpleNotes · Built with Flask &amp; Together AI
</footer>

<script>
  function toggleDark(){
    const h=document.documentElement;
    h.classList.toggle('dark');
    const d=h.classList.contains('dark');
    localStorage.setItem('theme',d?'dark':'light');
    document.getElementById('darkIcon').className=d?'fa-solid fa-sun':'fa-solid fa-moon';
  }
  (function(){
    if(localStorage.getItem('theme')==='dark'){
      document.documentElement.classList.add('dark');
      document.getElementById('darkIcon').className='fa-solid fa-sun';
    }
  })();
</script>
{% block scripts %}{% endblock %}
</body>
</html>
"""

HOME_TMPL = BASE.replace("{% block content %}{% endblock %}", """{% block content %}
<div class="flex flex-col items-center justify-center text-center py-20 gap-6">
  <div class="text-6xl text-indigo-500 animate-bounce"><i class="fa-solid fa-note-sticky"></i></div>
  <h1 class="text-4xl font-extrabold">Welcome to <span class="text-indigo-600">SimpleNotes</span></h1>
  <p class="text-gray-500 dark:text-gray-400 max-w-lg text-lg">Your AI-powered note-taking app. Summarize, detect mood, track versions, and never lose an idea.</p>
  <div class="flex gap-4 mt-4">
    <a href="{{ url_for('register') }}" class="bg-indigo-600 text-white px-6 py-3 rounded-xl text-sm font-semibold hover:bg-indigo-700 transition shadow">Get Started</a>
    <a href="{{ url_for('login') }}"    class="border border-indigo-600 text-indigo-600 dark:text-indigo-400 px-6 py-3 rounded-xl text-sm font-semibold hover:bg-indigo-50 dark:hover:bg-gray-800 transition">Log In</a>
  </div>
  <div class="grid grid-cols-1 sm:grid-cols-3 gap-6 mt-14 w-full max-w-3xl text-left">
    <div class="bg-white dark:bg-gray-800 rounded-2xl p-5 shadow hover:shadow-md transition">
      <div class="text-3xl mb-3 text-indigo-400"><i class="fa-solid fa-wand-magic-sparkles"></i></div>
      <h3 class="font-bold mb-1">AI Summaries</h3>
      <p class="text-sm text-gray-500 dark:text-gray-400">Instantly summarize long notes using Together AI.</p>
    </div>
    <div class="bg-white dark:bg-gray-800 rounded-2xl p-5 shadow hover:shadow-md transition">
      <div class="text-3xl mb-3 text-pink-400"><i class="fa-solid fa-face-smile"></i></div>
      <h3 class="font-bold mb-1">Emotion Tags</h3>
      <p class="text-sm text-gray-500 dark:text-gray-400">Auto-detect the emotional tone of your notes.</p>
    </div>
    <div class="bg-white dark:bg-gray-800 rounded-2xl p-5 shadow hover:shadow-md transition">
      <div class="text-3xl mb-3 text-green-400"><i class="fa-solid fa-clock-rotate-left"></i></div>
      <h3 class="font-bold mb-1">Version History</h3>
      <p class="text-sm text-gray-500 dark:text-gray-400">Every edit is saved so you can always go back.</p>
    </div>
  </div>
</div>
{% endblock %}""")

REGISTER_TMPL = BASE.replace("{% block content %}{% endblock %}", """{% block content %}
<div class="max-w-md mx-auto mt-10 bg-white dark:bg-gray-800 rounded-2xl shadow-lg p-8">
  <h2 class="text-2xl font-bold mb-6 text-center text-indigo-600 dark:text-indigo-400"><i class="fa-solid fa-user-plus mr-2"></i>Create Account</h2>
  <form method="POST" novalidate>
    {{ form.hidden_tag() }}
    <div class="mb-4">
      {{ form.name.label(class="block text-sm font-medium mb-1") }}
      {{ form.name(class="w-full border dark:border-gray-600 rounded-lg px-3 py-2 bg-gray-50 dark:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-400", placeholder="Your name") }}
      {% for e in form.name.errors %}<p class="text-red-500 text-xs mt-1">{{ e }}</p>{% endfor %}
    </div>
    <div class="mb-4">
      {{ form.email.label(class="block text-sm font-medium mb-1") }}
      {{ form.email(class="w-full border dark:border-gray-600 rounded-lg px-3 py-2 bg-gray-50 dark:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-400", placeholder="you@email.com") }}
      {% for e in form.email.errors %}<p class="text-red-500 text-xs mt-1">{{ e }}</p>{% endfor %}
    </div>
    <div class="mb-6">
      {{ form.password.label(class="block text-sm font-medium mb-1") }}
      {{ form.password(class="w-full border dark:border-gray-600 rounded-lg px-3 py-2 bg-gray-50 dark:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-400", placeholder="Min. 6 characters") }}
      {% for e in form.password.errors %}<p class="text-red-500 text-xs mt-1">{{ e }}</p>{% endfor %}
    </div>
    {{ form.submit(class="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-2 rounded-lg transition") }}
  </form>
  <p class="text-center text-sm mt-4 text-gray-500 dark:text-gray-400">Already have an account? <a href="{{ url_for('login') }}" class="text-indigo-500 hover:underline">Log in</a></p>
</div>
{% endblock %}""")

LOGIN_TMPL = BASE.replace("{% block content %}{% endblock %}", """{% block content %}
<div class="max-w-md mx-auto mt-10 bg-white dark:bg-gray-800 rounded-2xl shadow-lg p-8">
  <h2 class="text-2xl font-bold mb-6 text-center text-indigo-600 dark:text-indigo-400"><i class="fa-solid fa-right-to-bracket mr-2"></i>Login</h2>
  <form method="POST" novalidate>
    {{ form.hidden_tag() }}
    <div class="mb-4">
      {{ form.email.label(class="block text-sm font-medium mb-1") }}
      {{ form.email(class="w-full border dark:border-gray-600 rounded-lg px-3 py-2 bg-gray-50 dark:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-400", placeholder="you@email.com") }}
      {% for e in form.email.errors %}<p class="text-red-500 text-xs mt-1">{{ e }}</p>{% endfor %}
    </div>
    <div class="mb-6">
      {{ form.password.label(class="block text-sm font-medium mb-1") }}
      {{ form.password(class="w-full border dark:border-gray-600 rounded-lg px-3 py-2 bg-gray-50 dark:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-400", placeholder="Password") }}
      {% for e in form.password.errors %}<p class="text-red-500 text-xs mt-1">{{ e }}</p>{% endfor %}
    </div>
    {{ form.submit(class="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-2 rounded-lg transition") }}
  </form>
  <p class="text-center text-sm mt-4 text-gray-500 dark:text-gray-400">Don't have an account? <a href="{{ url_for('register') }}" class="text-indigo-500 hover:underline">Register</a></p>
</div>
{% endblock %}""")

DASHBOARD_TMPL = BASE.replace("{% block content %}{% endblock %}", """{% block content %}
<div class="flex items-center justify-between mb-6">
  <h1 class="text-2xl font-bold">My Notes</h1>
  <a href="{{ url_for('note_editor') }}" class="bg-indigo-600 hover:bg-indigo-700 text-white text-sm px-4 py-2 rounded-xl shadow transition">
    <i class="fa-solid fa-plus mr-1"></i> New Note
  </a>
</div>
<form method="GET" class="flex flex-col sm:flex-row gap-2 mb-6">
  <input type="text" name="q"   value="{{ search_query }}" placeholder="Search notes..."
    class="flex-1 border dark:border-gray-600 rounded-lg px-4 py-2 bg-white dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-indigo-400 text-sm"/>
  <input type="text" name="tag" value="{{ tag_filter }}"   placeholder="Filter by tag..."
    class="w-full sm:w-44 border dark:border-gray-600 rounded-lg px-4 py-2 bg-white dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-indigo-400 text-sm"/>
  <button type="submit" class="bg-indigo-500 hover:bg-indigo-600 text-white px-4 py-2 rounded-lg text-sm transition">
    <i class="fa-solid fa-magnifying-glass"></i>
  </button>
  {% if search_query or tag_filter %}
  <a href="{{ url_for('dashboard') }}" class="text-sm text-gray-400 hover:text-red-400 flex items-center gap-1 px-2">
    <i class="fa-solid fa-xmark"></i> Clear
  </a>
  {% endif %}
</form>
{% if notes %}
<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
  {% for note in notes %}
  <div class="bg-white dark:bg-gray-800 rounded-2xl shadow hover:shadow-md transition p-5 flex flex-col gap-3 group">
    <div class="flex items-start justify-between gap-2">
      <a href="{{ url_for('note_view', note_id=note.id) }}" class="font-semibold text-gray-800 dark:text-white hover:text-indigo-500 transition line-clamp-1 text-base">{{ note.title or "Untitled" }}</a>
      {% if note.mood %}<span class="text-xs bg-indigo-100 dark:bg-indigo-900 text-indigo-600 dark:text-indigo-300 px-2 py-0.5 rounded-full whitespace-nowrap">{{ note.mood }}</span>{% endif %}
    </div>
    <p class="text-sm text-gray-500 dark:text-gray-400 line-clamp-3">{{ note.content }}</p>
    {% if note.tags %}
    <div class="flex flex-wrap gap-1">
      {% for tag in note.tags.split(',') %}
      <a href="{{ url_for('dashboard', tag=tag.strip()) }}" class="text-xs bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 px-2 py-0.5 rounded-full hover:bg-indigo-100 transition">#{{ tag.strip() }}</a>
      {% endfor %}
    </div>
    {% endif %}
    <div class="flex items-center justify-between mt-auto pt-2 border-t border-gray-100 dark:border-gray-700">
      <span class="text-xs text-gray-400">{{ note.updated_at.strftime('%d %b %Y') }}</span>
      <div class="flex gap-3 opacity-0 group-hover:opacity-100 transition">
        <a href="{{ url_for('note_editor', note_id=note.id) }}" class="text-blue-400 hover:text-blue-600 text-sm"><i class="fa-solid fa-pen"></i></a>
        <form method="POST" action="{{ url_for('delete_note', note_id=note.id) }}" onsubmit="return confirm('Move to trash?')">
          <button type="submit" class="text-red-400 hover:text-red-600 text-sm"><i class="fa-solid fa-trash"></i></button>
        </form>
      </div>
    </div>
  </div>
  {% endfor %}
</div>
{% else %}
<div class="text-center py-24 text-gray-400 dark:text-gray-600">
  <i class="fa-regular fa-file-lines text-5xl mb-4 block"></i>
  <p class="text-lg">No notes found.</p>
  <a href="{{ url_for('note_editor') }}" class="text-indigo-500 hover:underline text-sm mt-2 inline-block">Create your first note →</a>
</div>
{% endif %}
{% endblock %}""")

NOTE_EDITOR_TMPL = BASE.replace("{% block content %}{% endblock %}", """{% block content %}
<div class="max-w-3xl mx-auto">
  <div class="flex items-center justify-between mb-5">
    <h1 class="text-xl font-bold">{{ "Edit Note" if note else "New Note" }}</h1>
    <span id="autosaveStatus" class="text-xs text-gray-400 italic"></span>
  </div>
  <form method="POST" id="noteForm" novalidate>
    {{ form.hidden_tag() }}
    <input type="hidden" id="noteId" value="{{ note.id if note else '' }}"/>
    <div class="mb-4">
      {{ form.title.label(class="block text-sm font-medium mb-1") }}
      {{ form.title(id="titleInput", class="w-full border dark:border-gray-600 rounded-lg px-4 py-2.5 bg-white dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-indigo-400 text-base", placeholder="Note title...") }}
      {% for e in form.title.errors %}<p class="text-red-500 text-xs mt-1">{{ e }}</p>{% endfor %}
    </div>
    <div class="mb-4">
      {{ form.content.label(class="block text-sm font-medium mb-1") }}
      {{ form.content(id="contentInput", class="w-full border dark:border-gray-600 rounded-lg px-4 py-2.5 bg-white dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-indigo-400 text-sm min-h-[240px] resize-y", placeholder="Write your note here...") }}
      {% for e in form.content.errors %}<p class="text-red-500 text-xs mt-1">{{ e }}</p>{% endfor %}
    </div>
    <div class="mb-4">
      {{ form.tags.label(class="block text-sm font-medium mb-1") }}
      {{ form.tags(id="tagsInput", class="w-full border dark:border-gray-600 rounded-lg px-4 py-2.5 bg-white dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-indigo-400 text-sm", placeholder="e.g. work, ideas, personal") }}
    </div>
    <div class="flex flex-wrap gap-2 mb-5">
      <button type="button" onclick="aiSummarize()" class="bg-purple-100 dark:bg-purple-900 text-purple-700 dark:text-purple-300 hover:bg-purple-200 text-xs px-4 py-2 rounded-lg transition font-medium"><i class="fa-solid fa-wand-magic-sparkles mr-1"></i> Summarize</button>
      <button type="button" onclick="aiTitle()"     class="bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-300 hover:bg-blue-200 text-xs px-4 py-2 rounded-lg transition font-medium"><i class="fa-solid fa-heading mr-1"></i> Generate Title</button>
      <button type="button" onclick="aiKeywords()"  class="bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-300 hover:bg-green-200 text-xs px-4 py-2 rounded-lg transition font-medium"><i class="fa-solid fa-tags mr-1"></i> Extract Keywords</button>
    </div>
    <div id="aiBox" class="hidden mb-5 bg-indigo-50 dark:bg-gray-700 border border-indigo-200 dark:border-gray-600 rounded-xl p-4 text-sm">
      <div class="flex items-center justify-between mb-2">
        <span class="font-semibold text-indigo-600 dark:text-indigo-400" id="aiBoxLabel">AI Output</span>
        <button type="button" onclick="document.getElementById('aiBox').classList.add('hidden')" class="text-gray-400 hover:text-red-400 text-xs">✕</button>
      </div>
      <p id="aiBoxContent" class="leading-relaxed text-gray-700 dark:text-gray-200"></p>
    </div>
    <div class="flex gap-3">
      {{ form.submit(class="bg-indigo-600 hover:bg-indigo-700 text-white font-semibold px-6 py-2.5 rounded-xl transition shadow") }}
      <a href="{{ url_for('dashboard') }}" class="border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 px-6 py-2.5 rounded-xl hover:bg-gray-100 dark:hover:bg-gray-700 transition text-sm font-medium">Cancel</a>
      {% if note %}
      <a href="{{ url_for('note_view', note_id=note.id) }}" class="ml-auto text-sm text-blue-500 hover:underline self-center"><i class="fa-solid fa-clock-rotate-left mr-1"></i>View History</a>
      {% endif %}
    </div>
  </form>
</div>
{% endblock %}
{% block scripts %}
<script>
  let autosaveTimer, currentNoteId = document.getElementById('noteId').value || null;
  function scheduleAutosave(){
    clearTimeout(autosaveTimer);
    document.getElementById('autosaveStatus').textContent='Unsaved changes...';
    autosaveTimer=setTimeout(doAutosave,3000);
  }
  async function doAutosave(){
    const title=document.getElementById('titleInput').value;
    const content=document.getElementById('contentInput').value;
    const tags=document.getElementById('tagsInput').value;
    if(!title&&!content)return;
    const res=await fetch('/note/autosave',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({note_id:currentNoteId,title,content,tags})});
    const data=await res.json();
    if(data.note_id){currentNoteId=data.note_id;document.getElementById('noteId').value=currentNoteId;}
    document.getElementById('autosaveStatus').textContent='✓ Autosaved';
    setTimeout(()=>document.getElementById('autosaveStatus').textContent='',3000);
  }
  document.getElementById('titleInput').addEventListener('input',scheduleAutosave);
  document.getElementById('contentInput').addEventListener('input',scheduleAutosave);
  document.getElementById('tagsInput').addEventListener('input',scheduleAutosave);
  async function callAI(endpoint,label){
    const content=document.getElementById('contentInput').value;
    if(!content.trim()){alert('Please write some content first.');return;}
    document.getElementById('aiBoxLabel').textContent=label+' (loading...)';
    document.getElementById('aiBoxContent').textContent='';
    document.getElementById('aiBox').classList.remove('hidden');
    const form=new FormData();form.append('content',content);
    const res=await fetch(endpoint,{method:'POST',body:form});
    const data=await res.json();
    document.getElementById('aiBoxLabel').textContent=label;
    document.getElementById('aiBoxContent').textContent=Object.values(data)[0]||'No response.';
  }
  function aiSummarize(){callAI('/ai/summarize','✨ Summary');}
  function aiTitle(){callAI('/ai/title','📝 Suggested Title');}
  function aiKeywords(){callAI('/ai/keywords','🏷️ Keywords');}
</script>
{% endblock %}""")

NOTE_VIEW_TMPL = BASE.replace("{% block content %}{% endblock %}", """{% block content %}
<div class="max-w-3xl mx-auto">
  <div class="flex items-start justify-between mb-4 gap-4">
    <div>
      <h1 class="text-2xl font-bold text-gray-800 dark:text-white">{{ note.title or "Untitled" }}</h1>
      <p class="text-xs text-gray-400 mt-1">Created {{ note.created_at.strftime('%d %b %Y, %I:%M %p') }} · Updated {{ note.updated_at.strftime('%d %b %Y, %I:%M %p') }}</p>
    </div>
    <div class="flex gap-2 flex-shrink-0">
      <a href="{{ url_for('note_editor', note_id=note.id) }}" class="bg-blue-500 hover:bg-blue-600 text-white text-sm px-4 py-2 rounded-lg transition"><i class="fa-solid fa-pen mr-1"></i> Edit</a>
      <form method="POST" action="{{ url_for('delete_note', note_id=note.id) }}" onsubmit="return confirm('Move to trash?')">
        <button class="bg-red-100 dark:bg-red-900 hover:bg-red-200 text-red-600 dark:text-red-300 text-sm px-4 py-2 rounded-lg transition"><i class="fa-solid fa-trash mr-1"></i> Trash</button>
      </form>
    </div>
  </div>
  <div class="flex flex-wrap gap-2 mb-5">
    {% if note.mood %}<span class="bg-indigo-100 dark:bg-indigo-900 text-indigo-600 dark:text-indigo-300 text-xs px-3 py-1 rounded-full font-medium"><i class="fa-solid fa-face-smile mr-1"></i>{{ note.mood }}</span>{% endif %}
    {% if note.tags %}{% for tag in note.tags.split(',') %}<a href="{{ url_for('dashboard', tag=tag.strip()) }}" class="bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 text-xs px-3 py-1 rounded-full hover:bg-indigo-100 transition">#{{ tag.strip() }}</a>{% endfor %}{% endif %}
  </div>
  <div class="bg-white dark:bg-gray-800 rounded-2xl shadow p-6 mb-6 text-sm leading-relaxed whitespace-pre-wrap text-gray-700 dark:text-gray-200">{{ note.content }}</div>
  {% if note.versions %}
  <div class="mt-6">
    <h2 class="font-semibold text-sm text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-3"><i class="fa-solid fa-clock-rotate-left mr-1"></i> Version History ({{ note.versions|length }})</h2>
    <div class="space-y-3">
      {% for v in note.versions|sort(attribute='created_at', reverse=True) %}
      <details class="bg-white dark:bg-gray-800 rounded-xl shadow px-4 py-3 cursor-pointer">
        <summary class="flex justify-between items-center text-sm">
          <span class="font-medium">{{ v.title or "Untitled" }}</span>
          <span class="text-xs text-gray-400">{{ v.created_at.strftime('%d %b %Y, %I:%M %p') }}</span>
        </summary>
        <p class="mt-3 text-sm text-gray-600 dark:text-gray-400 whitespace-pre-wrap leading-relaxed border-t dark:border-gray-700 pt-3">{{ v.content }}</p>
      </details>
      {% endfor %}
    </div>
  </div>
  {% endif %}
  <a href="{{ url_for('dashboard') }}" class="text-sm text-indigo-500 hover:underline mt-6 inline-block">← Back to Dashboard</a>
</div>
{% endblock %}""")

TRASH_TMPL = BASE.replace("{% block content %}{% endblock %}", """{% block content %}
<div class="flex items-center justify-between mb-6">
  <h1 class="text-2xl font-bold flex items-center gap-2"><i class="fa-solid fa-trash text-red-400"></i> Trash</h1>
  <a href="{{ url_for('dashboard') }}" class="text-sm text-indigo-500 hover:underline">← Dashboard</a>
</div>
{% if notes %}
<div class="space-y-4">
  {% for note in notes %}
  <div class="bg-white dark:bg-gray-800 rounded-2xl shadow p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
    <div class="flex-1 min-w-0">
      <p class="font-semibold text-gray-800 dark:text-white truncate">{{ note.title or "Untitled" }}</p>
      <p class="text-xs text-gray-400 mt-0.5">Deleted {{ note.updated_at.strftime('%d %b %Y') }}</p>
      <p class="text-sm text-gray-500 dark:text-gray-400 line-clamp-2 mt-1">{{ note.content }}</p>
    </div>
    <div class="flex gap-2 flex-shrink-0">
      <form method="POST" action="{{ url_for('restore_note', note_id=note.id) }}">
        <button class="bg-green-100 dark:bg-green-900 hover:bg-green-200 text-green-700 dark:text-green-300 text-sm px-4 py-2 rounded-lg transition font-medium"><i class="fa-solid fa-rotate-left mr-1"></i> Restore</button>
      </form>
      <form method="POST" action="{{ url_for('trash_delete', note_id=note.id) }}" onsubmit="return confirm('Permanently delete? This cannot be undone.')">
        <button class="bg-red-100 dark:bg-red-900 hover:bg-red-200 text-red-600 dark:text-red-300 text-sm px-4 py-2 rounded-lg transition font-medium"><i class="fa-solid fa-xmark mr-1"></i> Delete Forever</button>
      </form>
    </div>
  </div>
  {% endfor %}
</div>
{% else %}
<div class="text-center py-24 text-gray-400 dark:text-gray-600">
  <i class="fa-solid fa-trash-can text-5xl mb-4 block"></i>
  <p class="text-lg">Trash is empty.</p>
  <a href="{{ url_for('dashboard') }}" class="text-indigo-500 hover:underline text-sm mt-2 inline-block">Back to notes</a>
</div>
{% endif %}
{% endblock %}""")

# ─────────────────────────────────────────
#  Routes
# ─────────────────────────────────────────
@app.route("/")
def home():
    return render_template_string(HOME_TMPL)

@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    form = RegisterForm()
    if form.validate_on_submit():
        if User.query.filter_by(email=form.email.data.lower()).first():
            flash("Email already registered.", "warning")
            return redirect(url_for("login"))
        user = User(
            name=form.name.data,
            email=form.email.data.lower(),
            password_hash=generate_password_hash(form.password.data)
        )
        db.session.add(user)
        db.session.commit()
        flash("Account created! You can now log in.", "success")
        return redirect(url_for("login"))
    return render_template_string(REGISTER_TMPL, form=form)

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower()).first()
        if user and check_password_hash(user.password_hash, form.password.data):
            login_user(user)
            flash("Logged in successfully.", "success")
            return redirect(url_for("dashboard"))
        flash("Invalid email or password.", "danger")
    return render_template_string(LOGIN_TMPL, form=form)

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have logged out.", "info")
    return redirect(url_for("home"))

@app.route("/dashboard")
@login_required
def dashboard():
    tag_filter   = request.args.get("tag", "")
    search_query = request.args.get("q", "")
    notes = Note.query.filter_by(user_id=current_user.id, is_trashed=False)
    if tag_filter:
        notes = notes.filter(Note.tags.ilike(f"%{tag_filter}%"))
    if search_query:
        notes = notes.filter(
            (Note.title.ilike(f"%{search_query}%")) |
            (Note.content.ilike(f"%{search_query}%"))
        )
    notes = notes.order_by(Note.updated_at.desc()).all()
    return render_template_string(DASHBOARD_TMPL, notes=notes,
                                  tag_filter=tag_filter, search_query=search_query)

@app.route("/note/new",           methods=["GET", "POST"])
@app.route("/note/edit/<int:note_id>", methods=["GET", "POST"])
@login_required
def note_editor(note_id=None):
    note = None
    if note_id:
        note = Note.query.filter_by(id=note_id, user_id=current_user.id).first_or_404()
        form = NoteForm(obj=note)
    else:
        form = NoteForm()
    if form.validate_on_submit():
        if note is None:
            note = Note(title=form.title.data, content=form.content.data,
                        tags=form.tags.data, user_id=current_user.id)
            db.session.add(note)
        else:
            db.session.add(NoteVersion(note_id=note.id, title=note.title,
                                       content=note.content, created_at=note.updated_at))
            note.title   = form.title.data
            note.content = form.content.data
            note.tags    = form.tags.data
        db.session.commit()
        flash("Note saved successfully!", "success")
        return redirect(url_for("dashboard"))
    return render_template_string(NOTE_EDITOR_TMPL, form=form, note=note)

@app.route("/note/autosave", methods=["POST"])
@login_required
def autosave():
    data    = request.get_json()
    note_id = data.get("note_id")
    title   = data.get("title", "")
    content = data.get("content", "")
    tags    = data.get("tags", "")
    if note_id:
        note = Note.query.filter_by(id=note_id, user_id=current_user.id).first()
        if note:
            db.session.add(NoteVersion(note_id=note.id, title=note.title,
                                       content=note.content, created_at=note.updated_at))
            note.title = title; note.content = content; note.tags = tags
            db.session.commit()
            return jsonify({"status": "updated", "note_id": note.id})
    else:
        note = Note(title=title, content=content, tags=tags, user_id=current_user.id)
        db.session.add(note); db.session.commit()
        return jsonify({"status": "created", "note_id": note.id})
    return jsonify({"status": "error"}), 400

@app.route("/note/<int:note_id>")
@login_required
def note_view(note_id):
    note = Note.query.filter_by(id=note_id, user_id=current_user.id, is_trashed=False).first_or_404()
    return render_template_string(NOTE_VIEW_TMPL, note=note)

@app.route("/note/delete/<int:note_id>", methods=["POST"])
@login_required
def delete_note(note_id):
    note = Note.query.filter_by(id=note_id, user_id=current_user.id).first_or_404()
    note.is_trashed = True
    db.session.commit()
    flash("Note moved to Trash.", "info")
    return redirect(url_for("dashboard"))

@app.route("/trash")
@login_required
def trash():
    notes = Note.query.filter_by(user_id=current_user.id, is_trashed=True)\
                      .order_by(Note.updated_at.desc()).all()
    return render_template_string(TRASH_TMPL, notes=notes)

@app.route("/trash/restore/<int:note_id>", methods=["POST"])
@login_required
def restore_note(note_id):
    note = Note.query.filter_by(id=note_id, user_id=current_user.id, is_trashed=True).first_or_404()
    note.is_trashed = False
    db.session.commit()
    flash("Note restored.", "success")
    return redirect(url_for("trash"))

@app.route("/trash/delete/<int:note_id>", methods=["POST"])
@login_required
def trash_delete(note_id):
    note = Note.query.filter_by(id=note_id, user_id=current_user.id, is_trashed=True).first_or_404()
    NoteVersion.query.filter_by(note_id=note.id).delete()
    db.session.delete(note)
    db.session.commit()
    flash("Note permanently deleted.", "danger")
    return redirect(url_for("trash"))

@app.route("/ai/summarize", methods=["POST"])
@login_required
def ai_summarize():
    content = request.form.get("content", "")
    if not content.strip(): return jsonify({"summary": ""})
    return jsonify({"summary": call_together_ai(f"Summarize this note:\n\n{content}")})

@app.route("/ai/title", methods=["POST"])
@login_required
def ai_title():
    content = request.form.get("content", "")
    if not content.strip(): return jsonify({"title": ""})
    return jsonify({"title": call_together_ai(f"Generate a concise title for this note:\n\n{content}")})

@app.route("/ai/keywords", methods=["POST"])
@login_required
def ai_keywords():
    content = request.form.get("content", "")
    if not content.strip(): return jsonify({"keywords": ""})
    return jsonify({"keywords": call_together_ai(f"Extract keywords from this note:\n\n{content}")})

# ─────────────────────────────────────────
#  Entry Point
# ─────────────────────────────────────────
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        print("✅ Database tables created.")
    app.run(debug=True)
