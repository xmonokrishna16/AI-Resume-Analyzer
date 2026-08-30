import os
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename

# Import our custom AI modules
from core.db import get_db_connection
from core.parser import extract_text_from_pdf, extract_text_from_docx
from core.nlp_engine import extract_skills
from core.matcher import calculate_match
from core.roadmap import generate_roadmap

app = Flask(__name__)

# Configure a temporary upload folder
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

@app.route('/')
def home():
    """Renders the main frontend dashboard."""
    return render_template('index.html')

@app.route('/api/analyze', methods=['POST'])
def analyze_resume():
    """Handles the resume upload, runs AI analysis, and returns JSON."""

    # 1. Validate the incoming request
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

    # 3. Parse the document
    if filename.endswith('.pdf'):
        raw_text = extract_text_from_pdf(filepath)
    elif filename.endswith('.docx'):
        raw_text = extract_text_from_docx(filepath)
    else:
        return jsonify({"error": "Unsupported file format. Please upload PDF or DOCX."}), 400

    # Clean up the temporary file immediately after reading
    os.remove(filepath)

    # 4. Run NLP Skill Extraction
    resume_skills = extract_skills(raw_text)
    job_skills = extract_skills(job_description.lower()) # Extract skills required by the job

    # 5. Run Semantic Matching & Gap Analysis
    match_score, missing_skills = calculate_match(resume_skills, job_skills)


    
    # 6. Generate Roadmap
    roadmap = generate_roadmap(missing_skills)

    # --- NEW: SAVE TO MYSQL DATABASE ---
    try:
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            
            # Insert Job
            cursor.execute(
                "INSERT INTO Jobs (job_title, job_description) VALUES (%s, %s)", 
                ("Target Role", job_description)
            )
            job_id = cursor.lastrowid
            
            # Insert Resume (Assuming user_id 1 for now until you add login)
            cursor.execute(
                "INSERT INTO Resumes (user_id, original_filename, raw_text) VALUES (%s, %s, %s)", 
                (1, filename, raw_text)
            )
            resume_id = cursor.lastrowid
            
            # Insert Analysis Result
            import json
            cursor.execute(
                "INSERT INTO Analysis (resume_id, job_id, match_score, missing_skills) VALUES (%s, %s, %s, %s)", 
                (resume_id, job_id, match_score, json.dumps(missing_skills))
            )
            
            conn.commit()
            cursor.close()
            conn.close()
            print("✅ Analysis saved to database successfully.")
    except Exception as e:
        print(f"⚠️ Database save failed: {e}")
    # -----------------------------------

    
    # 7. Return the final payload to the frontend
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