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
from core.nlp_engine import extract_skills, extract_education, extract_experience
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
    default_resume = None
    
    if conn:
        cursor = conn.cursor(dictionary=True)
        
        # Fetch History
        query = """
            SELECT a.id AS analysis_id, r.original_filename, j.job_description, a.match_score, a.analyzed_at 
            FROM Analysis a 
            JOIN Resumes r ON a.resume_id = r.id 
            JOIN Jobs j ON a.job_id = j.id 
            WHERE r.user_id = %s 
            ORDER BY a.analyzed_at DESC
        """
        cursor.execute(query, (current_user.id,))
        history = cursor.fetchall()
        
        # Fetch Default Resume Status
        cursor.execute("SELECT original_filename FROM Resumes WHERE user_id = %s AND is_default = TRUE LIMIT 1", (current_user.id,))
        default_resume = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
    return render_template('index.html', user=current_user, history=history, default_resume=default_resume)

@app.route('/api/analyze', methods=['POST'])
@login_required
def analyze_resume():
    """Handles resume upload or uses the default, runs NLP, and saves results."""
    
    file = request.files.get('resume')
    job_description = request.form.get('job_desc', '')
    save_default = request.form.get('save_default') == 'on'

    raw_text = ""
    filename = ""
    resume_id = None
    using_default = False

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # 1. Check if a new file was uploaded
    if file and file.filename != '':
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        if filename.endswith('.pdf'):
            raw_text = extract_text_from_pdf(filepath)
        elif filename.endswith('.docx'):
            raw_text = extract_text_from_docx(filepath)
        else:
            os.remove(filepath)
            return jsonify({"error": "Unsupported format. Upload PDF or DOCX."}), 400
        
        # Clean up temporary file
        os.remove(filepath)
    else:
        # 2. No file uploaded -> Look for a saved default resume
        cursor.execute("SELECT id, original_filename, raw_text FROM Resumes WHERE user_id = %s AND is_default = TRUE LIMIT 1", (current_user.id,))
        default_res = cursor.fetchone()
        
        if not default_res:
            return jsonify({"error": "No file uploaded and no default resume found."}), 400
            
        raw_text = default_res['raw_text']
        filename = default_res['original_filename']
        resume_id = default_res['id']
        using_default = True

    # 3. NLP Skill Extraction & Matching
    resume_skills = extract_skills(raw_text)
    job_skills = extract_skills(job_description.lower())
    match_score, missing_skills = calculate_match(resume_skills, job_skills)
    roadmap = generate_roadmap(missing_skills)

    # --- NEW: Extract Education & Experience ---
    education_found = extract_education(raw_text)
    experience_found = extract_experience(raw_text)

    # 4. Save to Database
    try:
        cursor.execute("INSERT INTO Jobs (job_title, job_description) VALUES (%s, %s)", ("Target Role", job_description))
        job_id = cursor.lastrowid
        
        # If we uploaded a NEW file, insert it into Resumes
        if not using_default:
            # If they checked the box, remove the default flag from their old resumes first
            if save_default:
                cursor.execute("UPDATE Resumes SET is_default = FALSE WHERE user_id = %s", (current_user.id,))
            
            cursor.execute(
                "INSERT INTO Resumes (user_id, original_filename, raw_text, is_default) VALUES (%s, %s, %s, %s)", 
                (current_user.id, filename, raw_text, save_default)
            )
            resume_id = cursor.lastrowid
            
        # Link the Analysis to whichever resume_id we used
        cursor.execute(
            "INSERT INTO Analysis (resume_id, job_id, match_score, missing_skills) VALUES (%s, %s, %s, %s)", 
            (resume_id, job_id, match_score, json.dumps(missing_skills))
        )
        conn.commit()
    except Exception as e:
        print(f"Database save error: {e}")
    finally:
        cursor.close()
        conn.close()

    # 5. Return JSON Response
    return jsonify({
        "status": "success",
        "resume_skills_found": resume_skills,
        "job_skills_required": job_skills,
        "match_score": match_score,
        "missing_skills": missing_skills,
        "roadmap": roadmap,
        "education": education_found,
        "experience": experience_found
    })
@app.route('/api/delete_history', methods=['POST'])
@login_required
def delete_history():
    """Securely deletes selected analyses after verifying user password."""
    data = request.json
    analysis_ids = data.get('analysis_ids', [])
    password = data.get('password', '')

    # 1. Verify Password
    if not check_password_hash(current_user.password_hash, password):
        return jsonify({"status": "error", "message": "Incorrect password. Deletion denied."}), 403

    if not analysis_ids:
        return jsonify({"status": "error", "message": "No records selected."}), 400

    # 2. Execute Secure Deletion
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        try:
            # Ensure the user only deletes their own records by joining the Resumes table
            format_strings = ','.join(['%s'] * len(analysis_ids))
            query = f"""
                DELETE a FROM Analysis a
                JOIN Resumes r ON a.resume_id = r.id
                WHERE a.id IN ({format_strings}) AND r.user_id = %s
            """
            # Combine the IDs and the current_user ID into a single tuple
            params = tuple(analysis_ids) + (current_user.id,)
            
            cursor.execute(query, params)
            conn.commit()
            return jsonify({"status": "success"})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500
        finally:
            cursor.close()
            conn.close()
            
    return jsonify({"status": "error", "message": "Database connection failed."}), 500

if __name__ == '__main__':
    app.run(debug=True)