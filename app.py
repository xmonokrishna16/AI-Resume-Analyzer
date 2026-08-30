import os
import json
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, login_user, login_required, logout_user, current_user

# Import AI & DB custom modules
from core.db import get_db_connection
from core.models import User
from core.parser import extract_text_from_pdf, extract_text_from_docx
from core.nlp_engine import extract_skills
from core.matcher import calculate_match
from core.roadmap import generate_roadmap

app = Flask(__name__)
app.secret_key = "super_secret_key_change_this_later"  # Required for session encryption

# Configure Upload Folder
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Configure Flask-Login
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)

# --- AUTHENTICATION ROUTES ---

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')

        if User.find_by_email(email):
            flash('Email already registered. Please log in.')
            return redirect(url_for('register'))

        hashed_password = generate_password_hash(password)
        
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO Users (name, email, password_hash) VALUES (%s, %s, %s)",
                (name, email, hashed_password)
            )
            conn.commit()
            cursor.close()
            conn.close()
            flash('Account created successfully! Please log in.')
            return redirect(url_for('login'))
        else:
            flash('Database connection failed. Please try again later.')
            return redirect(url_for('register'))
        
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.find_by_email(email)
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('home'))
        else:
            flash('Invalid email or password.')
            
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- CORE APPLICATION ROUTES ---

@app.route('/')
@login_required
def home():
    """Renders the main dashboard and fetches user analysis history."""
    conn = get_db_connection()
    history = []
    
    if conn:
        cursor = conn.cursor(dictionary=True)
        # SQL Join to get the resume filename, job title, and score for the current user
        query = """
            SELECT r.original_filename, j.job_description, a.match_score, a.analyzed_at 
            FROM Analysis a 
            JOIN Resumes r ON a.resume_id = r.id 
            JOIN Jobs j ON a.job_id = j.id 
            WHERE r.user_id = %s 
            ORDER BY a.analyzed_at DESC
        """
        cursor.execute(query, (current_user.id,))
        history = cursor.fetchall()
        cursor.close()
        conn.close()
        
    return render_template('index.html', user=current_user, history=history)

@app.route('/api/analyze', methods=['POST'])
@login_required
def analyze_resume():
    """Handles resume upload, NLP analysis, and saves results under current_user."""

    # 1. Validate file request
    if 'resume' not in request.files:
        return jsonify({"error": "No resume file uploaded."}), 400
    
    file = request.files['resume']
    job_description = request.form.get('job_desc', '')

    if file.filename == '':
        return jsonify({"error": "Empty filename."}), 400

    # 2. Save file temporarily
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    # 3. Parse document
    if filename.endswith('.pdf'):
        raw_text = extract_text_from_pdf(filepath)
    elif filename.endswith('.docx'):
        raw_text = extract_text_from_docx(filepath)
    else:
        if os.path.exists(filepath):
            os.remove(filepath)
        return jsonify({"error": "Unsupported format. Upload PDF or DOCX."}), 400

    # Clean up temporary file
    if os.path.exists(filepath):
        os.remove(filepath)

    # 4. NLP Skill Extraction
    resume_skills = extract_skills(raw_text)
    job_skills = extract_skills(job_description.lower())

    # 5. Semantic Matching & Gap Analysis
    match_score, missing_skills = calculate_match(resume_skills, job_skills)
    
    # 6. Generate Learning Roadmap
    roadmap = generate_roadmap(missing_skills)

    # 7. Save to MySQL using current_user.id
    try:
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            
            # Insert Job Record
            cursor.execute(
                "INSERT INTO Jobs (job_title, job_description) VALUES (%s, %s)", 
                ("Target Role", job_description)
            )
            job_id = cursor.lastrowid
            
            # Insert Resume Record for Logged-In User
            cursor.execute(
                "INSERT INTO Resumes (user_id, original_filename, raw_text) VALUES (%s, %s, %s)", 
                (current_user.id, filename, raw_text)
            )
            resume_id = cursor.lastrowid
            
            # Insert Analysis Result
            cursor.execute(
                "INSERT INTO Analysis (resume_id, job_id, match_score, missing_skills) VALUES (%s, %s, %s, %s)", 
                (resume_id, job_id, match_score, json.dumps(missing_skills))
            )
            
            conn.commit()
            cursor.close()
            conn.close()
    except Exception as e:
        print(f"Database save error: {e}")

    # 8. Return JSON Response
    return jsonify({
        "status": "success",
        "resume_skills_found": resume_skills,
        "job_skills_required": job_skills,
        "match_score": match_score,
        "missing_skills": missing_skills,
        "roadmap": roadmap
    })

if __name__ == '__main__':
    app.run(debug=True)