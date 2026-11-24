import os
import json
import re
import tempfile
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, send_file
from authlib.integrations.flask_client import OAuth
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, login_user, login_required, logout_user, current_user

# Import AI & DB custom modules
from core.interview_engine import (
    generate_interview_questions,
    start_interactive_session,
    continue_interactive_session,
    evaluate_interview_session
)
from core.db import get_db_connection
from core.models import User
from core.parser import extract_text_from_pdf, extract_text_from_docx, extract_text_preserving_case
from core.nlp_engine import extract_skills, extract_education, extract_experience, check_ats_formatting, extract_contact_info
from core.matcher import calculate_match
from core.roadmap import generate_roadmap
from core.mcq_generator import generate_mcqs
from core.resume_tailor import ResumeTailoringError, normalize_tailored_resume, tailor_resume
from core.resume_export import create_docx_resume, create_pdf_resume
from core.project_defense import (
    ProjectDefenseError,
    QUESTION_CATEGORIES,
    analyze_project,
    evaluate_project,
    fetch_github_context,
    parse_github_repo_url
)
from core.project_defense_export import create_cheat_sheet_pdf, normalize_cheat_sheet
from core.outreach_kit import (
    OutreachKitError,
    OUTREACH_TONES,
    RECIPIENT_TYPES,
    generate_outreach_kit
)
from core.rejection_autopsy import (
    FAILED_ROUNDS,
    RejectionAutopsyError,
    generate_rejection_autopsy
)

app = Flask(__name__)
app.secret_key = "super_secret_key_change_this_later"  # Required for session encryption

# Configure Google OAuth
oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=os.getenv('GOOGLE_CLIENT_ID'),
    client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

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
        role = request.form.get('role', 'individual')
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        phone_whatsapp = request.form.get('phone_whatsapp')
        address = request.form.get('address')

        if User.find_by_email(email):
            flash('Email already registered. Please log in.')
            return redirect(url_for('register'))

        hashed_password = generate_password_hash(password)
        conn = get_db_connection()
        if not conn:
            flash('Database connection failed. Please try again.')
            return redirect(url_for('register'))

        try:
            cursor = conn.cursor()
            # 1. Insert Base User Record
            cursor.execute(
                """INSERT INTO Users (name, email, password_hash, role, phone_whatsapp, address)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (name, email, hashed_password, role, phone_whatsapp, address)
            )
            user_id = cursor.lastrowid

            # 2. Insert Profile Metadata based on Role
            if role == 'individual':
                education_level = request.form.get('education_level')
                institution_name = request.form.get('institution_name')
                field_of_study = request.form.get('field_of_study')
                graduation_year = request.form.get('graduation_year') or None

                cursor.execute(
                    """INSERT INTO Individual_Profiles 
                       (user_id, education_level, institution_name, field_of_study, graduation_year)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (user_id, education_level, institution_name, field_of_study, graduation_year)
                )
            elif role == 'business':
                company_name = request.form.get('company_name') or name
                business_type = request.form.get('business_type')
                website = request.form.get('website')
                company_size = request.form.get('company_size')

                cursor.execute(
                    """INSERT INTO Business_Profiles 
                       (user_id, company_name, business_type, website, company_size)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (user_id, company_name, business_type, website, company_size)
                )

            conn.commit()
            cursor.close()
            conn.close()
            flash('Account created successfully! Please log in.')
            return redirect(url_for('login'))

        except Exception as e:
            conn.rollback()
            cursor.close()
            conn.close()
            flash(f'Registration error: {str(e)}')
            return redirect(url_for('register'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.find_by_email(email)

        if user and user.password_hash and check_password_hash(user.password_hash, password):
            login_user(user)
            if user.role == 'business':
                return redirect(url_for('recruiter_dashboard'))
            # UPDATED: Redirect standard users to the new Master Dashboard
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password.')

    return render_template('login.html')

@app.route('/login/google')
def google_login():
    redirect_uri = url_for('google_callback', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route('/auth/google/callback')
def google_callback():
    token = google.authorize_access_token()
    user_info = token.get('userinfo')
    if not user_info or not user_info.get('email') or not user_info.get('email_verified'):
        flash('Google sign-in failed because a verified email was not provided.')
        return redirect(url_for('login'))

    email = user_info['email']
    name = user_info.get('name') or email.split('@')[0]

    conn = get_db_connection()
    if not conn:
        flash('Database connection failed. Please try again.')
        return redirect(url_for('login'))

    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """SELECT id, name, email, password_hash, role, phone_whatsapp, address
               FROM Users WHERE email = %s""",
            (email,)
        )
        user_data = cursor.fetchone()

        if user_data:
            user = User(
                id=user_data['id'],
                name=user_data['name'],
                email=user_data['email'],
                password_hash=user_data['password_hash'],
                role=user_data.get('role', 'individual'),
                phone_whatsapp=user_data.get('phone_whatsapp'),
                address=user_data.get('address')
            )
        else:
            cursor.execute(
                """INSERT INTO Users (name, email, password_hash, role)
                   VALUES (%s, %s, NULL, %s)""",
                (name, email, 'individual')
            )
            conn.commit()
            user = User(
                id=cursor.lastrowid,
                name=name,
                email=email,
                password_hash=None,
                role='individual'
            )
    finally:
        cursor.close()
        conn.close()

    login_user(user)
    if user.role == 'business':
        return redirect(url_for('recruiter_dashboard'))
    return redirect(url_for('dashboard'))

@app.route('/recruiter')
@login_required
def recruiter_dashboard():
    """Renders the recruiter/bulk shortlisting dashboard for business users."""
    if current_user.role != 'business':
        flash('Access restricted to recruiter/business accounts.')
        return redirect(url_for('home'))
    return render_template('recruiter.html', user=current_user)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- NEW MASTER DASHBOARD & FEATURE ROUTES ---

@app.route('/dashboard')
@login_required
def dashboard():
    """Central hub showing all available Skill Bridge AI services."""
    return render_template('dashboard.html')

@app.route('/mock-interview')
@login_required
def mock_interview():
    """Renders the mock interview generation module."""
    return render_template('mock_interview.html')

@app.route('/mcq-generator')
@login_required
def mcq_generator_view():
    """Renders the study material upload and MCQ test module."""
    return render_template('mcq_upload.html')

@app.route('/resume-tailor')
@login_required
def resume_tailor_view():
    """Renders the AI Resume Tailor workspace and recent user history."""
    tailored_history = []
    history_available = False
    history_error = None
    conn = get_db_connection()
    if not conn:
        history_error = 'Could not connect to the database. Tailoring and history are unavailable.'
    else:
        cursor = None
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """SELECT id, target_role, company_name, original_ats_score,
                          tailored_ats_score, created_at
                   FROM tailored_resumes
                   WHERE user_id = %s
                   ORDER BY created_at DESC, id DESC
                   LIMIT 8""",
                (current_user.id,)
            )
            tailored_history = cursor.fetchall()
            history_available = True
        except Exception as error:
            if getattr(error, 'errno', None) == 1146:
                history_error = 'Run resume_tailor_schema.sql in the configured MySQL database to enable saving.'
            else:
                app.logger.exception("Failed to load tailored resume history for user %s", current_user.id)
                history_error = 'Resume history is temporarily unavailable.'
        finally:
            if cursor is not None:
                cursor.close()
            conn.close()

    return render_template(
        'resume_tailor.html',
        tailored_history=tailored_history,
        history_available=history_available,
        history_error=history_error
    )

@app.route('/api/tailor-resume', methods=['POST'])
@login_required
def api_tailor_resume():
    """Creates and persists an ATS-tailored resume for the current user."""
    target_role = request.form.get('target_role', '').strip()
    company_name = request.form.get('company_name', '').strip() or None
    job_description = request.form.get('job_description', '').strip()
    input_mode = request.form.get('input_mode', 'upload')

    if not target_role or not job_description:
        return jsonify({"status": "error", "error": "Target role and job description are required."}), 400
    if len(target_role) > 150 or (company_name and len(company_name) > 150):
        return jsonify({"status": "error", "error": "Role and company names must be 150 characters or fewer."}), 400

    if input_mode == 'upload':
        resume_file = request.files.get('resume')
        if not resume_file or not resume_file.filename:
            return jsonify({"status": "error", "error": "Choose a PDF or DOCX resume to upload."}), 400

        extension = os.path.splitext(secure_filename(resume_file.filename))[1].lower()
        if extension not in ('.pdf', '.docx'):
            return jsonify({"status": "error", "error": "Upload a PDF or DOCX resume."}), 400

        file_descriptor, temporary_path = tempfile.mkstemp(
            suffix=extension,
            dir=app.config['UPLOAD_FOLDER']
        )
        os.close(file_descriptor)
        try:
            resume_file.save(temporary_path)
            source_profile = extract_text_preserving_case(temporary_path, extension)
        except Exception:
            app.logger.exception("Failed to read uploaded resume for tailoring")
            return jsonify({"status": "error", "error": "Could not read that resume. Check the file and try again."}), 400
        finally:
            if os.path.exists(temporary_path):
                os.remove(temporary_path)

        if not source_profile:
            return jsonify({"status": "error", "error": "No readable text was found in the uploaded resume."}), 400
    elif input_mode == 'manual':
        manual_profile = {
            field: request.form.get(field, '').strip()
            for field in ('name', 'contact', 'summary', 'skills', 'projects', 'experience', 'education')
        }
        if not any(manual_profile.values()):
            return jsonify({"status": "error", "error": "Enter at least one piece of resume information."}), 400
        source_profile = json.dumps(manual_profile, ensure_ascii=False)
    else:
        return jsonify({"status": "error", "error": "Choose a valid resume input method."}), 400

    try:
        tailored_result = tailor_resume(source_profile, target_role, company_name, job_description)
    except ResumeTailoringError as error:
        return jsonify({"status": "error", "error": str(error)}), 502
    except Exception:
        app.logger.exception("Gemini failed to tailor a resume for user %s", current_user.id)
        return jsonify({"status": "error", "error": "Resume tailoring is temporarily unavailable. Please try again."}), 502

    conn = get_db_connection()
    if not conn:
        return jsonify({"status": "error", "error": "Database connection failed; the tailored resume was not saved."}), 503

    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO tailored_resumes
               (user_id, target_role, company_name, original_ats_score, tailored_ats_score,
                added_keywords, tailored_content_json)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (
                current_user.id,
                target_role,
                company_name,
                tailored_result['original_ats_score'],
                tailored_result['tailored_ats_score'],
                json.dumps(tailored_result['added_keywords'], ensure_ascii=False),
                json.dumps(tailored_result['tailored_resume'], ensure_ascii=False)
            )
        )
        tailored_resume_id = cursor.lastrowid
        conn.commit()
    except Exception as error:
        conn.rollback()
        app.logger.exception("Failed to save tailored resume for user %s", current_user.id)
        message = (
            'Run resume_tailor_schema.sql in the configured MySQL database before saving resumes.'
            if getattr(error, 'errno', None) == 1146
            else 'The tailored resume could not be saved. Please try again.'
        )
        return jsonify({"status": "error", "error": message}), 500
    finally:
        if cursor is not None:
            cursor.close()
        conn.close()

    return jsonify({
        "status": "success",
        "resume_id": tailored_resume_id,
        "target_role": target_role,
        "company_name": company_name,
        **tailored_result
    })

@app.route('/api/export-tailored-resume', methods=['POST'])
@login_required
def api_export_tailored_resume():
    """Exports a user-edited tailored resume as an ATS-friendly PDF or DOCX."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"status": "error", "error": "Provide a tailored resume and export format."}), 400

    export_format = data.get('format')
    if export_format not in ('pdf', 'docx'):
        return jsonify({"status": "error", "error": "Choose PDF or DOCX export."}), 400

    try:
        tailored_resume = normalize_tailored_resume(data.get('tailored_resume'))
    except ResumeTailoringError as error:
        return jsonify({"status": "error", "error": str(error)}), 400

    header = tailored_resume['header']
    filename_base = secure_filename(header['name']) or 'tailored-resume'
    if export_format == 'pdf':
        output = create_pdf_resume(tailored_resume)
        mimetype = 'application/pdf'
    else:
        output = create_docx_resume(tailored_resume)
        mimetype = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'

    return send_file(
        output,
        mimetype=mimetype,
        as_attachment=True,
        download_name=f'{filename_base}-resume.{export_format}'
    )

@app.route('/project-defense')
@login_required
def project_defense_view():
    """Renders recent project-defense sessions for the signed-in user."""
    defense_history = []
    history_available = False
    history_error = None
    conn = get_db_connection()
    if not conn:
        history_error = 'Could not connect to the database. Defense history is unavailable.'
    else:
        cursor = None
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """SELECT id, project_name, repo_url, tech_stack, difficulty_level,
                          readiness_score, created_at
                   FROM project_defense_sessions
                   WHERE user_id = %s
                   ORDER BY created_at DESC, id DESC
                   LIMIT 8""",
                (current_user.id,)
            )
            defense_history = cursor.fetchall()
            history_available = True
        except Exception as error:
            if getattr(error, 'errno', None) == 1146:
                history_error = 'Run project_defense_schema.sql in the configured MySQL database to enable history.'
            else:
                app.logger.exception("Failed to load project-defense history for user %s", current_user.id)
                history_error = 'Project-defense history is temporarily unavailable.'
        finally:
            if cursor is not None:
                cursor.close()
            conn.close()

    return render_template(
        'project_defense.html',
        defense_history=defense_history,
        history_available=history_available,
        history_error=history_error
    )

@app.route('/api/project-defense/analyze', methods=['POST'])
@login_required
def api_analyze_project_defense():
    """Loads public GitHub context when available and generates grill questions."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"status": "error", "error": "Provide project details as JSON."}), 400

    project_name = data.get('project_name')
    repo_url = data.get('repo_url', '')
    project_summary = data.get('project_summary', '')
    tech_stack = data.get('tech_stack', '')
    repo_url = '' if repo_url is None else repo_url
    project_summary = '' if project_summary is None else project_summary
    tech_stack = '' if tech_stack is None else tech_stack
    difficulty_level = data.get('difficulty_level')
    values = (project_name, repo_url, project_summary, tech_stack, difficulty_level)
    if any(not isinstance(value, str) for value in values):
        return jsonify({"status": "error", "error": "Project details must be text values."}), 400

    project_name = project_name.strip()
    repo_url = repo_url.strip()
    project_summary = project_summary.strip()
    tech_stack = tech_stack.strip()
    difficulty_level = difficulty_level.strip()
    if not project_name:
        return jsonify({"status": "error", "error": "Project name is required."}), 400
    if len(project_name) > 150 or len(repo_url) > 255 or len(tech_stack) > 255:
        return jsonify({"status": "error", "error": "Project name, repository URL, or tech stack is too long."}), 400
    if len(project_summary) > 12000:
        return jsonify({"status": "error", "error": "Project summary must be 12,000 characters or fewer."}), 400
    if difficulty_level not in ('Fresher', 'SDE-1', 'Senior'):
        return jsonify({"status": "error", "error": "Choose Fresher, SDE-1, or Senior as the target level."}), 400
    if not repo_url and not project_summary:
        return jsonify({"status": "error", "error": "Add a public GitHub repository URL or a project summary."}), 400

    github_context = ""
    github_languages = []
    warnings = []
    if repo_url:
        try:
            owner, repository = parse_github_repo_url(repo_url)
        except ProjectDefenseError as error:
            return jsonify({"status": "error", "error": str(error)}), 400
        repo_url = f'https://github.com/{owner}/{repository}'
        try:
            github_result = fetch_github_context(repo_url)
        except Exception:
            app.logger.exception("GitHub repository lookup failed for project defense")
            github_result = {
                "context": "",
                "languages": [],
                "warnings": ["GitHub details could not be loaded. Paste a project summary to continue."]
            }
        github_context = github_result['context']
        github_languages = github_result['languages']
        warnings = github_result['warnings']
        if not github_context and not project_summary:
            return jsonify({
                "status": "error",
                "error": warnings[0] if warnings else "Repository details were unavailable; paste a project summary to continue.",
                "warnings": warnings
            }), 422

    if not tech_stack and github_languages:
        tech_stack = ', '.join(github_languages)[:255]
    tech_stack = tech_stack or 'Not specified'
    project_context = {
        "project_name": project_name,
        "repo_url": repo_url or None,
        "tech_stack": tech_stack,
        "difficulty_level": difficulty_level
    }
    source_material = json.dumps({
        "github_repository_data": github_context,
        "user_project_summary": project_summary
    }, ensure_ascii=False)
    try:
        analysis = analyze_project(project_context, source_material)
    except ProjectDefenseError as error:
        return jsonify({"status": "error", "error": str(error)}), 502
    except Exception:
        app.logger.exception("Gemini failed to analyze project defense for user %s", current_user.id)
        return jsonify({
            "status": "error",
            "error": "Project analysis is temporarily unavailable. Please try again."
        }), 502

    complete_context = {
        **project_context,
        "detected_architecture_summary": analysis['detected_architecture_summary'],
        "potential_weaknesses": analysis['potential_weaknesses']
    }
    return jsonify({
        "status": "success",
        "project_context": complete_context,
        "detected_architecture_summary": analysis['detected_architecture_summary'],
        "potential_weaknesses": analysis['potential_weaknesses'],
        "grill_questions": analysis['grill_questions'],
        "warnings": warnings
    })

@app.route('/api/project-defense/evaluate', methods=['POST'])
@login_required
def api_evaluate_project_defense():
    """Evaluates the candidate's answers, saves the session, and returns a cheat sheet."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"status": "error", "error": "Provide project answers as JSON."}), 400

    project_context = data.get('project_context')
    raw_questions = data.get('grill_questions')
    raw_answers = data.get('answers')
    if not isinstance(project_context, dict) or not isinstance(raw_questions, list) or not isinstance(raw_answers, list):
        return jsonify({"status": "error", "error": "Project context, questions, and answers are required."}), 400
    if not 5 <= len(raw_questions) <= 7 or len(raw_answers) != len(raw_questions):
        return jsonify({"status": "error", "error": "Answer every grill question or mark it as skipped."}), 400

    try:
        normalized_questions = []
        seen_ids = set()
        for item in raw_questions:
            if not isinstance(item, dict):
                raise ProjectDefenseError("A grill question is invalid.")
            question_id = item.get('id')
            category = item.get('category')
            question = item.get('question')
            if (
                not isinstance(question_id, str)
                or not question_id
                or len(question_id) > 32
                or question_id in seen_ids
                or not isinstance(category, str)
                or category not in QUESTION_CATEGORIES
                or not isinstance(question, str)
                or not question.strip()
            ):
                raise ProjectDefenseError("A grill question is invalid.")
            seen_ids.add(question_id)
            normalized_questions.append({
                "id": question_id,
                "category": category,
                "question": question.strip()[:2000]
            })

        normalized_answers = []
        answer_ids = set()
        for item in raw_answers:
            if not isinstance(item, dict):
                raise ProjectDefenseError("A submitted answer is invalid.")
            question_id = item.get('question_id')
            answer = item.get('answer', '')
            skipped = item.get('skipped', False)
            if (
                not isinstance(question_id, str)
                or question_id not in seen_ids
                or question_id in answer_ids
                or not isinstance(answer, str)
                or len(answer) > 5000
                or not isinstance(skipped, bool)
            ):
                raise ProjectDefenseError("A submitted answer is invalid.")
            if not skipped and not answer.strip():
                raise ProjectDefenseError("Enter an answer or choose “I don't know” for each question.")
            answer_ids.add(question_id)
            normalized_answers.append({
                "question_id": question_id,
                "answer": answer.strip(),
                "skipped": skipped
            })
        if answer_ids != seen_ids:
            raise ProjectDefenseError("Answer every grill question or mark it as skipped.")

        project_name = project_context.get('project_name')
        repo_url = project_context.get('repo_url') or None
        tech_stack = project_context.get('tech_stack')
        difficulty_level = project_context.get('difficulty_level')
        if (
            not isinstance(project_name, str)
            or not project_name.strip()
            or len(project_name) > 150
            or (repo_url is not None and (not isinstance(repo_url, str) or len(repo_url) > 255))
            or not isinstance(tech_stack, str)
            or not tech_stack.strip()
            or len(tech_stack) > 255
            or difficulty_level not in ('Fresher', 'SDE-1', 'Senior')
        ):
            raise ProjectDefenseError("Project details are invalid. Return to Step 1 and try again.")
        architecture_summary = project_context.get('detected_architecture_summary', '')
        if not isinstance(architecture_summary, str) or len(architecture_summary) > 4000:
            raise ProjectDefenseError("Project analysis details are invalid. Return to Step 1 and try again.")
        safe_context = {
            "project_name": project_name.strip(),
            "repo_url": repo_url,
            "tech_stack": tech_stack.strip(),
            "difficulty_level": difficulty_level,
            "detected_architecture_summary": architecture_summary,
            "potential_weaknesses": project_context.get('potential_weaknesses', [])
        }
        if (
            not isinstance(safe_context['potential_weaknesses'], list)
            or len(safe_context['potential_weaknesses']) > 4
            or any(not isinstance(item, str) or len(item) > 1000 for item in safe_context['potential_weaknesses'])
        ):
            raise ProjectDefenseError("Project analysis details are invalid. Return to Step 1 and try again.")
    except ProjectDefenseError as error:
        return jsonify({"status": "error", "error": str(error)}), 400

    try:
        evaluation = evaluate_project(safe_context, normalized_questions, normalized_answers)
    except ProjectDefenseError as error:
        return jsonify({"status": "error", "error": str(error)}), 502
    except Exception:
        app.logger.exception("Gemini failed to evaluate project defense for user %s", current_user.id)
        return jsonify({
            "status": "error",
            "error": "Answer evaluation is temporarily unavailable. Please try again."
        }), 502

    transcript = {
        "project_context": safe_context,
        "grill_questions": normalized_questions,
        "answers": normalized_answers,
        "evaluations": evaluation['evaluations']
    }
    conn = get_db_connection()
    if not conn:
        return jsonify({
            "status": "error",
            "error": "Database connection failed; the defense session was not saved."
        }), 503

    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO project_defense_sessions
               (user_id, project_name, repo_url, tech_stack, difficulty_level, readiness_score,
                qa_transcript_json, cheat_sheet_json)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                current_user.id,
                safe_context['project_name'],
                safe_context['repo_url'],
                safe_context['tech_stack'],
                safe_context['difficulty_level'],
                evaluation['readiness_score'],
                json.dumps(transcript, ensure_ascii=False),
                json.dumps(evaluation['cheat_sheet'], ensure_ascii=False)
            )
        )
        session_id = cursor.lastrowid
        conn.commit()
    except Exception as error:
        conn.rollback()
        app.logger.exception("Failed to save project-defense session for user %s", current_user.id)
        message = (
            'Run project_defense_schema.sql in the configured MySQL database before saving sessions.'
            if getattr(error, 'errno', None) == 1146
            else 'The project-defense session could not be saved. Please try again.'
        )
        return jsonify({"status": "error", "error": message}), 500
    finally:
        if cursor is not None:
            cursor.close()
        conn.close()

    return jsonify({
        "status": "success",
        "session_id": session_id,
        "readiness_score": evaluation['readiness_score'],
        "evaluations": evaluation['evaluations'],
        "cheat_sheet": evaluation['cheat_sheet']
    })

@app.route('/api/project-defense/export-cheatsheet', methods=['POST'])
@login_required
def api_export_project_defense_cheatsheet():
    """Exports a validated defense cheat sheet as a printable PDF."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"status": "error", "error": "Provide a defense cheat sheet to export."}), 400

    project_name = data.get('project_name', 'Project')
    if not isinstance(project_name, str) or not project_name.strip() or len(project_name) > 150:
        return jsonify({"status": "error", "error": "Provide a valid project name."}), 400
    try:
        cheat_sheet = normalize_cheat_sheet(data.get('cheat_sheet'))
        output = create_cheat_sheet_pdf(cheat_sheet, project_name.strip())
    except ValueError as error:
        return jsonify({"status": "error", "error": str(error)}), 400
    except Exception:
        app.logger.exception("Failed to export project-defense cheat sheet for user %s", current_user.id)
        return jsonify({"status": "error", "error": "Could not generate the PDF. Please try again."}), 500

    filename_base = secure_filename(project_name) or 'project-defense'
    return send_file(
        output,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'{filename_base}-defense-cheat-sheet.pdf'
    )

@app.route('/outreach-kit')
@login_required
def outreach_kit_view():
    """Renders recent saved outreach kits for the signed-in user."""
    saved_kits = []
    history_available = False
    history_error = None
    conn = get_db_connection()
    if not conn:
        history_error = 'Could not connect to the database. Saved outreach kits are unavailable.'
    else:
        cursor = None
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """SELECT id, company_name, target_role, recipient_type, tone,
                          highlighted_project, kit_json, created_at
                   FROM outreach_kits
                   WHERE user_id = %s
                   ORDER BY created_at DESC, id DESC
                   LIMIT 12""",
                (current_user.id,)
            )
            for record in cursor.fetchall():
                try:
                    kit = record['kit_json']
                    kit = json.loads(kit) if isinstance(kit, str) else kit
                    if not isinstance(kit, dict):
                        raise ValueError("Saved outreach kit is not a JSON object.")
                except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                    app.logger.warning("Invalid outreach kit JSON in saved record %s", record.get('id'))
                    kit = None
                created_at = record.get('created_at')
                saved_kits.append({
                    "id": record['id'],
                    "company_name": record['company_name'],
                    "target_role": record['target_role'],
                    "recipient_type": record['recipient_type'],
                    "tone": record['tone'],
                    "highlighted_project": record['highlighted_project'],
                    "created_at": created_at.strftime('%b %d, %Y') if hasattr(created_at, 'strftime') else str(created_at or ''),
                    "kit": kit
                })
            history_available = True
        except Exception as error:
            if getattr(error, 'errno', None) == 1146:
                history_error = 'Run outreach_kit_schema.sql in the configured MySQL database to enable saved kits.'
            else:
                app.logger.exception("Failed to load outreach kits for user %s", current_user.id)
                history_error = 'Saved outreach kits are temporarily unavailable.'
        finally:
            if cursor is not None:
                cursor.close()
            conn.close()

    return render_template(
        'outreach_kit.html',
        saved_kits=saved_kits,
        history_available=history_available,
        history_error=history_error,
        delete_url= url_for('api_delete_outreach_kit', kit_id=0)
    )

@app.route('/api/outreach-kit/generate', methods=['POST'])
@login_required
def api_generate_outreach_kit():
    """Generates and persists a personalized outreach kit."""
    company_name = request.form.get('company_name', '').strip()
    target_role = request.form.get('target_role', '').strip()
    job_link_or_id = request.form.get('job_link_or_id', '').strip()
    recipient_name = request.form.get('recipient_name', '').strip() or '[Name]'
    recipient_type = request.form.get('recipient_type', 'Engineer / Peer').strip()
    tone = request.form.get('tone', 'Professional').strip()
    input_mode = request.form.get('input_mode', 'paste').strip()

    if not company_name or not target_role:
        return jsonify({"status": "error", "error": "Company name and target role are required."}), 400
    if len(company_name) > 150 or len(target_role) > 150:
        return jsonify({"status": "error", "error": "Company name and target role must be 150 characters or fewer."}), 400
    if len(job_link_or_id) > 500:
        return jsonify({"status": "error", "error": "Job link or ID must be 500 characters or fewer."}), 400
    if len(recipient_name) > 100:
        return jsonify({"status": "error", "error": "Recipient name must be 100 characters or fewer."}), 400
    if recipient_type not in RECIPIENT_TYPES or tone not in OUTREACH_TONES:
        return jsonify({"status": "error", "error": "Choose a valid recipient type and message tone."}), 400

    if input_mode == 'upload':
        resume_file = request.files.get('resume')
        if not resume_file or not resume_file.filename:
            return jsonify({"status": "error", "error": "Choose a PDF or DOCX resume to upload."}), 400
        extension = os.path.splitext(secure_filename(resume_file.filename))[1].lower()
        if extension not in ('.pdf', '.docx'):
            return jsonify({"status": "error", "error": "Upload a PDF or DOCX resume."}), 400
        try:
            resume_bytes = resume_file.stream.read(5 * 1024 * 1024 + 1)
        except Exception:
            app.logger.exception("Failed to read uploaded resume for outreach kit")
            return jsonify({"status": "error", "error": "Could not read that resume. Check the file and try again."}), 400
        if len(resume_bytes) > 5 * 1024 * 1024:
            return jsonify({"status": "error", "error": "Resume files must be 5 MB or smaller."}), 413

        file_descriptor, temporary_path = tempfile.mkstemp(suffix=extension, dir=app.config['UPLOAD_FOLDER'])
        os.close(file_descriptor)
        try:
            with open(temporary_path, 'wb') as temporary_file:
                temporary_file.write(resume_bytes)
            resume_text = extract_text_preserving_case(temporary_path, extension)
        except Exception:
            app.logger.exception("Failed to parse uploaded resume for outreach kit")
            return jsonify({"status": "error", "error": "Could not extract text from that resume. Check the file and try again."}), 400
        finally:
            if os.path.exists(temporary_path):
                os.remove(temporary_path)
    elif input_mode == 'paste':
        resume_text = request.form.get('resume_text', '').strip()
    else:
        return jsonify({"status": "error", "error": "Choose upload or pasted resume/project notes."}), 400

    if not resume_text:
        return jsonify({"status": "error", "error": "Provide resume or project details to personalize your outreach."}), 400
    if len(resume_text) > 18000:
        return jsonify({"status": "error", "error": "Resume or project notes must be 18,000 characters or fewer."}), 400

    try:
        kit = generate_outreach_kit(
            resume_text,
            company_name,
            target_role,
            job_link_or_id,
            recipient_name,
            recipient_type,
            tone
        )
    except OutreachKitError as error:
        return jsonify({"status": "error", "error": str(error)}), 502
    except Exception:
        app.logger.exception("Gemini failed to generate an outreach kit for user %s", current_user.id)
        return jsonify({
            "status": "error",
            "error": "Outreach-kit generation is temporarily unavailable. Please try again."
        }), 502

    conn = get_db_connection()
    if not conn:
        return jsonify({
            "status": "error",
            "error": "Database connection failed; the outreach kit was not saved."
        }), 503

    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO outreach_kits
               (user_id, company_name, target_role, recipient_type, tone, highlighted_project, kit_json)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (
                current_user.id,
                company_name,
                target_role,
                recipient_type,
                tone,
                kit['highlighted_project'],
                json.dumps(kit, ensure_ascii=False)
            )
        )
        kit_id = cursor.lastrowid
        conn.commit()
    except Exception as error:
        conn.rollback()
        app.logger.exception("Failed to save outreach kit for user %s", current_user.id)
        message = (
            'Run outreach_kit_schema.sql in the configured MySQL database before saving kits.'
            if getattr(error, 'errno', None) == 1146
            else 'The outreach kit could not be saved. Please try again.'
        )
        return jsonify({"status": "error", "error": message}), 500
    finally:
        if cursor is not None:
            cursor.close()
        conn.close()

    return jsonify({
        "status": "success",
        "kit_id": kit_id,
        "company_name": company_name,
        "target_role": target_role,
        "recipient_name": recipient_name,
        "recipient_type": recipient_type,
        "tone": tone,
        "kit": kit
    })

@app.route('/api/outreach-kit/<int:kit_id>', methods=['DELETE'])
@login_required
def api_delete_outreach_kit(kit_id):
    """Deletes only a saved outreach kit owned by the signed-in user."""
    conn = get_db_connection()
    if not conn:
        return jsonify({"status": "error", "error": "Database connection failed."}), 503

    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM outreach_kits WHERE id = %s AND user_id = %s",
            (kit_id, current_user.id)
        )
        if cursor.rowcount == 0:
            return jsonify({"status": "error", "error": "Saved outreach kit was not found."}), 404
        conn.commit()
    except Exception as error:
        conn.rollback()
        app.logger.exception("Failed to delete outreach kit %s for user %s", kit_id, current_user.id)
        message = (
            'Run outreach_kit_schema.sql in the configured MySQL database before managing kits.'
            if getattr(error, 'errno', None) == 1146
            else 'The outreach kit could not be deleted. Please try again.'
        )
        return jsonify({"status": "error", "error": message}), 500
    finally:
        if cursor is not None:
            cursor.close()
        conn.close()

    return jsonify({"status": "success", "deleted_id": kit_id})

@app.route('/rejection-autopsy')
@login_required
def rejection_autopsy_view():
    """Renders recent rejection autopsies and recurring diagnoses for the user."""
    autopsy_history = []
    recurring_patterns = []
    history_available = False
    history_error = None
    conn = get_db_connection()
    if not conn:
        history_error = 'Could not connect to the database. Recovery history is unavailable.'
    else:
        cursor = None
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """SELECT id, company_name, target_role, failed_round, primary_failure_pattern,
                          autopsy_json, completed_days_json, status, created_at
                   FROM rejection_autopsies
                   WHERE user_id = %s
                   ORDER BY created_at DESC, id DESC
                   LIMIT 20""",
                (current_user.id,)
            )
            for record in cursor.fetchall():
                try:
                    autopsy = record['autopsy_json']
                    autopsy = json.loads(autopsy) if isinstance(autopsy, str) else autopsy
                    if not isinstance(autopsy, dict):
                        raise ValueError("Saved rejection autopsy is not a JSON object.")
                except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                    app.logger.warning("Invalid rejection autopsy JSON in saved record %s", record.get('id'))
                    autopsy = None
                try:
                    completed_days = record.get('completed_days_json') or '[]'
                    completed_days = json.loads(completed_days) if isinstance(completed_days, str) else completed_days
                    if not isinstance(completed_days, list):
                        raise ValueError("Completed-day history is not a JSON array.")
                    completed_days = sorted({
                        day for day in completed_days
                        if type(day) is int and 1 <= day <= 7
                    })
                except (TypeError, ValueError, json.JSONDecodeError):
                    app.logger.warning("Invalid completed-day data in rejection autopsy %s", record.get('id'))
                    completed_days = []
                created_at = record.get('created_at')
                autopsy_history.append({
                    "id": record['id'],
                    "company_name": record['company_name'],
                    "target_role": record['target_role'],
                    "failed_round": record['failed_round'],
                    "primary_failure_pattern": record['primary_failure_pattern'] or 'Diagnosis unavailable',
                    "autopsy": autopsy,
                    "completed_days": completed_days,
                    "status": record['status'],
                    "created_at": created_at.strftime('%b %d, %Y') if hasattr(created_at, 'strftime') else str(created_at or '')
                })

            cursor.execute(
                """SELECT primary_failure_pattern, COUNT(*) AS occurrences
                   FROM rejection_autopsies
                   WHERE user_id = %s AND primary_failure_pattern IS NOT NULL
                   GROUP BY primary_failure_pattern
                   HAVING COUNT(*) > 1
                   ORDER BY occurrences DESC, primary_failure_pattern ASC
                   LIMIT 5""",
                (current_user.id,)
            )
            recurring_patterns = cursor.fetchall()
            history_available = True
        except Exception as error:
            if getattr(error, 'errno', None) == 1146:
                history_error = 'Run rejection_autopsy_schema.sql in the configured MySQL database to enable recovery history.'
            else:
                app.logger.exception("Failed to load rejection-autopsy history for user %s", current_user.id)
                history_error = 'Recovery history is temporarily unavailable.'
        finally:
            if cursor is not None:
                cursor.close()
            conn.close()

    return render_template(
        'rejection_autopsy.html',
        autopsy_history=autopsy_history,
        recurring_patterns=recurring_patterns,
        history_available=history_available,
        history_error=history_error,
        toggle_day_url=url_for('api_toggle_rejection_autopsy_day', autopsy_id=0),
        delete_url=url_for('api_delete_rejection_autopsy', autopsy_id=0)
    )

@app.route('/api/rejection-autopsy/analyze', methods=['POST'])
@login_required
def api_analyze_rejection():
    """Creates and persists an evidence-aware rejection analysis and seven-day plan."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"status": "error", "error": "Provide rejection details as JSON."}), 400

    fields = {
        "company_name": data.get("company_name"),
        "target_role": data.get("target_role"),
        "failed_round": data.get("failed_round"),
        "job_description": data.get("job_description", ""),
        "what_happened": data.get("what_happened")
    }
    if any(not isinstance(value, str) for value in fields.values()):
        return jsonify({"status": "error", "error": "Rejection details must be text values."}), 400
    fields = {name: value.strip() for name, value in fields.items()}
    if not fields["company_name"] or not fields["target_role"] or not fields["what_happened"]:
        return jsonify({
            "status": "error",
            "error": "Company, target role, and what happened are required."
        }), 400
    if (
        len(fields["company_name"]) > 150
        or len(fields["target_role"]) > 150
        or len(fields["failed_round"]) > 100
        or len(fields["job_description"]) > 12000
        or len(fields["what_happened"]) > 8000
    ):
        return jsonify({"status": "error", "error": "One or more fields exceed the allowed length."}), 400
    if fields["failed_round"] not in FAILED_ROUNDS:
        return jsonify({"status": "error", "error": "Choose a valid failed round."}), 400

    try:
        autopsy = generate_rejection_autopsy(
            fields["company_name"],
            fields["target_role"],
            fields["failed_round"],
            fields["job_description"],
            fields["what_happened"]
        )
    except RejectionAutopsyError as error:
        return jsonify({"status": "error", "error": str(error)}), 502
    except Exception:
        app.logger.exception("Gemini failed to analyze rejection for user %s", current_user.id)
        return jsonify({
            "status": "error",
            "error": "Rejection analysis is temporarily unavailable. Please try again."
        }), 502

    conn = get_db_connection()
    if not conn:
        return jsonify({
            "status": "error",
            "error": "Database connection failed; the recovery sprint was not saved."
        }), 503

    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO rejection_autopsies
               (user_id, company_name, target_role, failed_round, primary_failure_pattern,
                autopsy_json, completed_days_json, status)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                current_user.id,
                fields["company_name"],
                fields["target_role"],
                fields["failed_round"],
                autopsy["primary_failure_pattern"],
                json.dumps(autopsy, ensure_ascii=False),
                "[]",
                "In Progress"
            )
        )
        autopsy_id = cursor.lastrowid
        conn.commit()
    except Exception as error:
        conn.rollback()
        app.logger.exception("Failed to save rejection autopsy for user %s", current_user.id)
        message = (
            'Run rejection_autopsy_schema.sql in the configured MySQL database before saving recovery sprints.'
            if getattr(error, 'errno', None) == 1146
            else 'The recovery sprint could not be saved. Please try again.'
        )
        return jsonify({"status": "error", "error": message}), 500
    finally:
        if cursor is not None:
            cursor.close()
        conn.close()

    return jsonify({
        "status": "success",
        "autopsy_id": autopsy_id,
        "company_name": fields["company_name"],
        "target_role": fields["target_role"],
        "failed_round": fields["failed_round"],
        "autopsy": autopsy,
        "completed_days": [],
        "progress_percentage": 0,
        "sprint_status": "In Progress"
    })

@app.route('/api/rejection-autopsy/<int:autopsy_id>/toggle-day', methods=['POST'])
@login_required
def api_toggle_rejection_autopsy_day(autopsy_id):
    """Toggles a day atomically for an autopsy owned by the signed-in user."""
    data = request.get_json(silent=True)
    day = data.get("day") if isinstance(data, dict) else None
    if type(day) is not int or not 1 <= day <= 7:
        return jsonify({"status": "error", "error": "Choose a sprint day from 1 to 7."}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({"status": "error", "error": "Database connection failed."}), 503

    cursor = None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """SELECT completed_days_json
               FROM rejection_autopsies
               WHERE id = %s AND user_id = %s
               FOR UPDATE""",
            (autopsy_id, current_user.id)
        )
        record = cursor.fetchone()
        if not record:
            return jsonify({"status": "error", "error": "Saved recovery sprint was not found."}), 404
        try:
            completed_days = record.get("completed_days_json") or "[]"
            completed_days = json.loads(completed_days) if isinstance(completed_days, str) else completed_days
            if not isinstance(completed_days, list) or any(
                type(item) is not int or not 1 <= item <= 7 for item in completed_days
            ):
                raise ValueError("Completed-day data is invalid.")
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise ValueError("Saved sprint progress is invalid. Contact support before changing it.") from error

        completed_days = set(completed_days)
        if day in completed_days:
            completed_days.remove(day)
        else:
            completed_days.add(day)
        completed_days = sorted(completed_days)
        status = "Completed" if len(completed_days) == 7 else "In Progress"
        cursor.execute(
            """UPDATE rejection_autopsies
               SET completed_days_json = %s, status = %s
               WHERE id = %s AND user_id = %s""",
            (json.dumps(completed_days), status, autopsy_id, current_user.id)
        )
        conn.commit()
    except ValueError as error:
        conn.rollback()
        return jsonify({"status": "error", "error": str(error)}), 500
    except Exception as error:
        conn.rollback()
        app.logger.exception("Failed to update rejection autopsy %s for user %s", autopsy_id, current_user.id)
        message = (
            'Run rejection_autopsy_schema.sql in the configured MySQL database before updating sprint progress.'
            if getattr(error, 'errno', None) == 1146
            else 'Sprint progress could not be updated. Please try again.'
        )
        return jsonify({"status": "error", "error": message}), 500
    finally:
        if cursor is not None:
            cursor.close()
        conn.close()

    return jsonify({
        "status": "success",
        "autopsy_id": autopsy_id,
        "day": day,
        "completed_days": completed_days,
        "completed_count": len(completed_days),
        "progress_percentage": round(len(completed_days) / 7 * 100),
        "status_label": status
    })

@app.route('/api/rejection-autopsy/<int:autopsy_id>', methods=['DELETE'])
@login_required
def api_delete_rejection_autopsy(autopsy_id):
    """Deletes only a rejection autopsy owned by the signed-in user."""
    conn = get_db_connection()
    if not conn:
        return jsonify({"status": "error", "error": "Database connection failed."}), 503

    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM rejection_autopsies WHERE id = %s AND user_id = %s",
            (autopsy_id, current_user.id)
        )
        if cursor.rowcount == 0:
            return jsonify({"status": "error", "error": "Saved recovery sprint was not found."}), 404
        conn.commit()
    except Exception as error:
        conn.rollback()
        app.logger.exception("Failed to delete rejection autopsy %s for user %s", autopsy_id, current_user.id)
        message = (
            'Run rejection_autopsy_schema.sql in the configured MySQL database before managing recovery sprints.'
            if getattr(error, 'errno', None) == 1146
            else 'The recovery sprint could not be deleted. Please try again.'
        )
        return jsonify({"status": "error", "error": message}), 500
    finally:
        if cursor is not None:
            cursor.close()
        conn.close()

    return jsonify({"status": "success", "deleted_id": autopsy_id})

@app.route('/analytics')
@app.route('/progress-analytics')
@login_required
def analytics_view():
    """Renders consolidated career-readiness analytics for the signed-in user."""
    conn = get_db_connection()
    if not conn:
        return render_template(
            'analytics.html',
            analytics_error='Could not connect to the analytics database. Please check the database connection.'
        ), 503

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """SELECT a.id, j.job_title AS target_role, a.match_score AS ats_score,
                      a.missing_skills, a.analyzed_at AS created_at
               FROM analysis a
               JOIN resumes r ON r.id = a.resume_id
               JOIN jobs j ON j.id = a.job_id
               WHERE r.user_id = %s
               ORDER BY a.analyzed_at ASC, a.id ASC""",
            (current_user.id,)
        )
        resume_records = cursor.fetchall()

        cursor.execute(
            """SELECT id, category, questions_answered, total_questions, overall_score,
                      status, feedback_summary, created_at
               FROM interview_sessions
               WHERE user_id = %s
               ORDER BY created_at ASC, id ASC""",
            (current_user.id,)
        )
        interview_records = cursor.fetchall()

        cursor.execute(
            """SELECT id, test_title AS topic_name, score, total_questions,
                      percentage AS score_percentage, created_at
               FROM mcq_tests
               WHERE user_id = %s
               ORDER BY created_at ASC, id ASC""",
            (current_user.id,)
        )
        mcq_records = cursor.fetchall()

        tailored_resume_count = 0
        average_tailor_score_boost = None
        tailor_summary_available = True
        try:
            cursor.execute(
                """SELECT COUNT(*) AS tailored_count,
                          AVG(tailored_ats_score - original_ats_score) AS average_score_boost
                   FROM tailored_resumes
                   WHERE user_id = %s""",
                (current_user.id,)
            )
            tailored_summary = cursor.fetchone() or {}
            tailored_resume_count = tailored_summary.get('tailored_count', 0)
            average_tailor_score_boost = tailored_summary.get('average_score_boost')
            if average_tailor_score_boost is not None:
                average_tailor_score_boost = round(float(average_tailor_score_boost), 2)
        except Exception as error:
            if getattr(error, 'errno', None) != 1146:
                raise
            app.logger.warning("Resume Tailor summary is unavailable until its schema is installed.")
            tailor_summary_available = False

        project_defense_count = 0
        average_defense_readiness = None
        project_defense_summary_available = True
        try:
            cursor.execute(
                """SELECT COUNT(*) AS defense_count,
                          AVG(readiness_score) AS average_readiness
                   FROM project_defense_sessions
                   WHERE user_id = %s""",
                (current_user.id,)
            )
            defense_summary = cursor.fetchone() or {}
            project_defense_count = defense_summary.get('defense_count', 0)
            average_defense_readiness = defense_summary.get('average_readiness')
            if average_defense_readiness is not None:
                average_defense_readiness = round(float(average_defense_readiness), 2)
        except Exception as error:
            if getattr(error, 'errno', None) != 1146:
                raise
            app.logger.warning("Project-defense summary is unavailable until its schema is installed.")
            project_defense_summary_available = False

        outreach_kit_count = 0
        outreach_kit_summary_available = True
        try:
            cursor.execute(
                """SELECT COUNT(*) AS outreach_kit_count
                   FROM outreach_kits
                   WHERE user_id = %s""",
                (current_user.id,)
            )
            outreach_summary = cursor.fetchone() or {}
            outreach_kit_count = outreach_summary.get('outreach_kit_count', 0)
        except Exception as error:
            if getattr(error, 'errno', None) != 1146:
                raise
            app.logger.warning("Outreach-kit summary is unavailable until its schema is installed.")
            outreach_kit_summary_available = False

        completed_recovery_sprint_count = 0
        most_common_failure_pattern = None
        rejection_autopsy_summary_available = True
        try:
            cursor.execute(
                """SELECT COUNT(*) AS completed_sprint_count
                   FROM rejection_autopsies
                   WHERE user_id = %s AND status = 'Completed'""",
                (current_user.id,)
            )
            recovery_summary = cursor.fetchone() or {}
            completed_recovery_sprint_count = recovery_summary.get('completed_sprint_count', 0)
            cursor.execute(
                """SELECT primary_failure_pattern, COUNT(*) AS occurrences
                   FROM rejection_autopsies
                   WHERE user_id = %s AND primary_failure_pattern IS NOT NULL
                   GROUP BY primary_failure_pattern
                   ORDER BY occurrences DESC, primary_failure_pattern ASC
                   LIMIT 1""",
                (current_user.id,)
            )
            common_pattern = cursor.fetchone()
            if common_pattern:
                most_common_failure_pattern = common_pattern.get('primary_failure_pattern')
        except Exception as error:
            if getattr(error, 'errno', None) != 1146:
                raise
            app.logger.warning("Rejection-autopsy summary is unavailable until its schema is installed.")
            rejection_autopsy_summary_available = False

        cursor.close()
    except Exception as error:
        app.logger.exception("Failed to load analytics for user %s", current_user.id)
        analytics_error = (
            'The analytics schema is incomplete. Run analytics_schema.sql in the configured MySQL database.'
            if getattr(error, 'errno', None) == 1146
            else 'Analytics data is temporarily unavailable. Please try again later.'
        )
        return render_template(
            'analytics.html',
            analytics_error=analytics_error
        ), 503
    finally:
        conn.close()

    previous_resume_score = None
    for record in resume_records:
        score = float(record['ats_score']) if record['ats_score'] is not None else None
        record['ats_score'] = round(score, 2) if score is not None else None
        if record['missing_skills']:
            try:
                missing_skills = json.loads(record['missing_skills'])
                record['missing_keywords_count'] = len(missing_skills) if isinstance(missing_skills, list) else 0
            except (TypeError, json.JSONDecodeError):
                app.logger.warning("Invalid missing_skills JSON in analysis %s", record['id'])
                record['missing_keywords_count'] = 0
        else:
            record['missing_keywords_count'] = 0
        record['target_role'] = record['target_role'] or 'Unspecified role'
        record['score_change'] = (
            round(record['ats_score'] - previous_resume_score, 2)
            if record['ats_score'] is not None and previous_resume_score is not None
            else None
        )
        if record['ats_score'] is not None:
            previous_resume_score = record['ats_score']

    category_labels = {
        'technical': 'Technical',
        'dsa': 'DSA',
        'hr': 'HR',
        'mixed': 'Mixed',
        'subjective': 'Subjective',
        'personality': 'Behavioral / HR'
    }
    for record in interview_records:
        record['overall_score'] = (
            round(float(record['overall_score']), 2)
            if record['overall_score'] is not None else None
        )
        category = (record['category'] or 'mixed').lower()
        record['category'] = category_labels.get(category, category.replace('_', ' ').title())

    for record in mcq_records:
        record['score_percentage'] = (
            round(float(record['score_percentage']), 2)
            if record['score_percentage'] is not None else None
        )
        record['topic_name'] = record['topic_name'] or 'Study Material Assessment'

    resume_scores = [record['ats_score'] for record in resume_records if record['ats_score'] is not None]
    interview_scores = [
        record['overall_score'] for record in interview_records
        if record['status'] == 'Completed' and record['overall_score'] is not None
    ]
    mcq_scores = [record['score_percentage'] for record in mcq_records if record['score_percentage'] is not None]
    resume_delta = round(resume_scores[-1] - resume_scores[0], 2) if len(resume_scores) > 1 else None
    mcq_delta = round(mcq_scores[-1] - mcq_scores[0], 2) if len(mcq_scores) > 1 else None
    average_interview_score = round(sum(interview_scores) / len(interview_scores), 2) if interview_scores else None
    average_mcq_accuracy = round(sum(mcq_scores) / len(mcq_scores), 2) if mcq_scores else None

    readiness_components = []
    if resume_scores:
        readiness_components.append((resume_scores[-1], 0.40))
    if average_interview_score is not None:
        readiness_components.append((average_interview_score, 0.35))
    if mcq_scores:
        readiness_components.append((mcq_scores[-1], 0.25))
    readiness_weight = sum(weight for _, weight in readiness_components)
    readiness_score = (
        round(sum(score * weight for score, weight in readiness_components) / readiness_weight, 2)
        if readiness_weight else None
    )

    timeline_events = []
    for record in resume_records:
        if record['ats_score'] is not None:
            timeline_events.append((record['created_at'], 'resume', record['ats_score']))
    for record in interview_records:
        if record['status'] == 'Completed' and record['overall_score'] is not None:
            timeline_events.append((record['created_at'], 'interview', record['overall_score']))
    for record in mcq_records:
        if record['score_percentage'] is not None:
            timeline_events.append((record['created_at'], 'mcq', record['score_percentage']))
    timeline_events.sort(key=lambda event: event[0])

    topic_scores = {}
    for record in mcq_records:
        if record['score_percentage'] is not None:
            topic_scores.setdefault(record['topic_name'], []).append(record['score_percentage'])
    topic_labels = sorted(topic_scores)
    topic_averages = [
        round(sum(topic_scores[topic]) / len(topic_scores[topic]), 2)
        for topic in topic_labels
    ]

    return render_template(
        'analytics.html',
        resume_records=resume_records,
        interview_records=interview_records,
        mcq_records=mcq_records,
        readiness_score=readiness_score,
        latest_resume_score=resume_scores[-1] if resume_scores else None,
        resume_delta=resume_delta,
        completed_interviews=sum(record['status'] == 'Completed' for record in interview_records),
        in_progress_interviews=sum(record['status'] == 'In Progress' for record in interview_records),
        average_interview_score=average_interview_score,
        average_mcq_accuracy=average_mcq_accuracy,
        mcq_delta=mcq_delta,
        timeline_labels=[
            event[0].strftime('%b %d') if hasattr(event[0], 'strftime') else str(event[0])
            for event in timeline_events
        ],
        resume_chart_scores=[event[2] if event[1] == 'resume' else None for event in timeline_events],
        interview_chart_scores=[event[2] if event[1] == 'interview' else None for event in timeline_events],
        mcq_chart_scores=[event[2] if event[1] == 'mcq' else None for event in timeline_events],
        topic_labels=topic_labels,
        topic_averages=topic_averages,
        tailored_resume_count=tailored_resume_count,
        average_tailor_score_boost=average_tailor_score_boost,
        tailor_summary_available=tailor_summary_available,
        project_defense_count=project_defense_count,
        average_defense_readiness=average_defense_readiness,
        project_defense_summary_available=project_defense_summary_available,
        outreach_kit_count=outreach_kit_count,
        outreach_kit_summary_available=outreach_kit_summary_available,
        completed_recovery_sprint_count=completed_recovery_sprint_count,
        most_common_failure_pattern=most_common_failure_pattern,
        rejection_autopsy_summary_available=rejection_autopsy_summary_available
    )

# --- CORE APPLICATION ROUTES (Existing Analyzer) ---

@app.route('/resume-analyzer')
@login_required
def home():
    """Renders the resume analyzer module and fetches analysis history."""
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
        
    # Still rendering index.html for the specific resume analyzer view
    return render_template('index.html', user=current_user, history=history, default_resume=default_resume)

@app.route('/api/analyze', methods=['POST'])
@login_required
def analyze_resume():
    """Handles resume upload or uses the default, runs NLP, and saves results."""
    
    file = request.files.get('resume')
    job_description = request.form.get('job_desc', '')
    target_role = request.form.get('target_role', '').strip() or 'Target Role'
    save_default = request.form.get('save_default') == 'on'

    raw_text = ""
    filename = ""
    resume_id = None
    using_default = False

    conn = get_db_connection()
    if not conn:
        return jsonify({"status": "error", "error": "Database connection failed."}), 503
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

    # --- Extract Education & Experience ---
    education_found = extract_education(raw_text)
    experience_found = extract_experience(raw_text)
    
    # --- Call the weighted matcher ---
    resume_skills = extract_skills(raw_text)
    job_skills = extract_skills(job_description.lower())
    match_score, missing_skills, breakdown = calculate_match(resume_skills, job_skills, education_found, experience_found, job_description)
    roadmap = generate_roadmap(missing_skills)

    # --- ATS Formatting & Contact Checks ---
    ats_health = check_ats_formatting(raw_text)
    contact_info = extract_contact_info(raw_text)

    # 4. Save to Database
    try:
        cursor.execute(
            "INSERT INTO Jobs (job_title, job_description) VALUES (%s, %s)",
            (target_role, job_description)
        )
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
    except Exception:
        conn.rollback()
        app.logger.exception("Database save error while analyzing resume")
        return jsonify({"status": "error", "error": "Unable to save resume analysis."}), 500
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
        "experience": experience_found,
        "ats_health": ats_health,
        "contact_info": contact_info
    })

@app.route('/api/delete_history', methods=['POST'])
@login_required
def delete_history():
    """Securely deletes selected analyses after verifying user password."""
    data = request.json
    analysis_ids = data.get('analysis_ids', [])
    password = data.get('password', '')

    # 1. Verify Password
    if not current_user.password_hash or not check_password_hash(current_user.password_hash, password):
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

@app.route('/api/bulk_analyze', methods=['POST'])
@login_required
def bulk_analyze():
    """Handles bulk resume uploads for recruiters and saves the campaign."""
    if current_user.role != 'business':
        return jsonify({"error": "Unauthorized access. Recruiter account required."}), 403

    files = request.files.getlist('resumes')
    campaign_title = request.form.get('campaign_title', 'Untitled Campaign')
    job_description = request.form.get('job_desc', '')
    min_experience = int(request.form.get('min_experience', 0))

    if not files or not job_description:
        return jsonify({"error": "Missing files or job description."}), 400

    job_skills = extract_skills(job_description.lower())
    results = []

    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed."}), 500
        
    cursor = conn.cursor(dictionary=True)

    try:
        # 1. Create the Campaign Record
        cursor.execute(
            "INSERT INTO Bulk_Job_Campaigns (business_id, campaign_title, job_description, min_experience_years) VALUES (%s, %s, %s, %s)",
            (current_user.id, campaign_title, job_description, min_experience)
        )
        campaign_id = cursor.lastrowid

        # 2. Process Each Resume
        for file in files:
            if file.filename == '':
                continue
            
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            # Extract Text
            raw_text = ""
            if filename.endswith('.pdf'):
                raw_text = extract_text_from_pdf(filepath)
            elif filename.endswith('.docx'):
                raw_text = extract_text_from_docx(filepath)
            
            if os.path.exists(filepath):
                os.remove(filepath)

            if not raw_text:
                continue

            # Analyze Text
            resume_skills = extract_skills(raw_text)
            resume_edu = extract_education(raw_text) 
            resume_exp_text = extract_experience(raw_text) 
            
            # Parse numerical experience for logic
            exp_match = re.search(r'(\d+)', resume_exp_text)
            exp_years = int(exp_match.group(1)) if exp_match else 0

            # --- Call the weighted matcher ---
            match_score, missing_skills, breakdown = calculate_match(resume_skills, job_skills, resume_edu, resume_exp_text, job_description)
            
            # 3. Categorization Logic
            if match_score >= 70 and exp_years >= min_experience:
                category = 'High Skills & Exp'
            elif match_score >= 70:
                category = 'High Skills'
            elif exp_years >= min_experience:
                category = 'High Exp'
            else:
                category = 'Needs Upskilling'

            # 4. Save Candidate to Database
            cursor.execute(
                """INSERT INTO Bulk_Candidates 
                   (campaign_id, file_name, match_score, extracted_experience, matched_skills, missing_skills, category_tag) 
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (campaign_id, filename, match_score, exp_years, json.dumps(resume_skills), json.dumps(missing_skills), category)
            )

            results.append({
                "file_name": filename,
                "match_score": match_score,
                "experience": f"{exp_years} Years",
                "category": category
            })

        conn.commit()
    except Exception as e:
        print("Bulk processing error:", e)
        conn.rollback()
        return jsonify({"error": "Failed to process bulk analysis."}), 500
    finally:
        cursor.close()
        conn.close()

    # Sort results highest score first
    results.sort(key=lambda x: x['match_score'], reverse=True)

    return jsonify({"status": "success", "results": results})

@app.route('/api/generate_mcq', methods=['POST'])
@login_required
def api_generate_mcq():
    """Handles document upload, extracts text, and triggers AI MCQ generation."""
    
    file = request.files.get('study_material')
    question_count = int(request.form.get('question_count', 20))
    
    if not file or file.filename == '':
        return jsonify({"status": "error", "error": "No file selected."}), 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    raw_text = ""
    try:
        if filename.endswith('.pdf'):
            raw_text = extract_text_from_pdf(filepath)
        elif filename.endswith('.docx'):
            raw_text = extract_text_from_docx(filepath)
        else:
            os.remove(filepath)
            return jsonify({"status": "error", "error": "Unsupported format. Upload PDF or DOCX."}), 400
    except Exception as e:
        os.remove(filepath)
        return jsonify({"status": "error", "error": f"Failed to parse document: {str(e)}"}), 500
        
    # Clean up file after extracting text
    if os.path.exists(filepath):
        os.remove(filepath)
        
    if not raw_text.strip():
        return jsonify({"status": "error", "error": "Could not extract text from the document."}), 400

    # Call the AI Generator
    generated_questions = generate_mcqs(raw_text, question_count)
    
    if not generated_questions:
        return jsonify({"status": "error", "error": "AI failed to generate questions. Please try again."}), 500

    # For now, we return the questions to the frontend.
    # In the next step, we will save this to the database and render the exam UI.
    return jsonify({
        "status": "success",
        "questions": generated_questions
    })

@app.route('/api/save_mcq_result', methods=['POST'])
@login_required
def save_mcq_result():
    """Stores user MCQ test performance for analytics."""
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"status": "error", "message": "Invalid test data."}), 400
    total_questions = data.get('total_questions', 0)
    score = data.get('score', 0)
    topic_name = data.get('topic_name') or data.get('title') or 'Study Material Assessment'

    if type(total_questions) is not int or total_questions <= 0:
        return jsonify({"status": "error", "message": "Invalid test data."}), 400
    if type(score) is not int or score < 0 or score > total_questions:
        return jsonify({"status": "error", "message": "Invalid test score."}), 400
    if not isinstance(topic_name, str):
        return jsonify({"status": "error", "message": "Invalid test topic."}), 400
    topic_name = topic_name.strip()[:255] or 'Study Material Assessment'

    percentage = round((score / total_questions) * 100, 2)

    conn = get_db_connection()
    if not conn:
        return jsonify({"status": "error", "message": "Database connection failed."}), 500

    try:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO mcq_tests (user_id, test_title, total_questions, score, percentage)
               VALUES (%s, %s, %s, %s, %s)""",
            (current_user.id, topic_name, total_questions, score, percentage)
        )
        conn.commit()
        return jsonify({"status": "success", "percentage": percentage})
    except Exception as e:
        print("Database error saving MCQ score:", e)
        conn.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/generate_interview_list', methods=['POST'])
@login_required
def api_generate_interview_list():
    """Handles Mode 1: Static List Generation"""
    file = request.files.get('resume')
    job_desc = request.form.get('job_desc', '')
    category = request.form.get('category', 'mixed')
    question_count = int(request.form.get('question_count', 5))
    
    if not file: return jsonify({"error": "No resume uploaded."}), 400
    
    # Secure and read file (reusing your existing logic)
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    raw_text = extract_text_from_pdf(filepath) if filename.endswith('.pdf') else extract_text_from_docx(filepath)
    os.remove(filepath)

    result = generate_interview_questions(raw_text, job_desc, question_count, category)
    if not result: return jsonify({"error": "Generation failed."}), 500

    conn = get_db_connection()
    if not conn:
        return jsonify({"status": "error", "error": "Database connection failed."}), 503

    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO mock_interviews (user_id, session_mode, category, job_description, session_data) VALUES (%s, %s, %s, %s, %s)",
            (current_user.id, 'list', category, job_desc[:500], json.dumps(result))
        )
        source_id = cursor.lastrowid
        cursor.execute(
            """INSERT INTO interview_sessions
               (source_interview_id, user_id, category, questions_answered, total_questions,
                overall_score, status, feedback_summary)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                source_id, current_user.id, category, 0, len(result), None, 'Completed',
                'Practice questions generated. No candidate answers were collected, so this session is not scored.'
            )
        )
        conn.commit()
    except Exception:
        conn.rollback()
        app.logger.exception("Failed to save generated interview session")
        return jsonify({"status": "error", "error": "Unable to save interview session."}), 500
    finally:
        if cursor is not None:
            cursor.close()
        conn.close()

    return jsonify({"status": "success", "questions": result, "session_id": source_id})


@app.route('/api/start_interactive_interview', methods=['POST'])
@login_required
def api_start_interactive_interview():
    """Handles Mode 2: Chat Initialization"""
    file = request.files.get('resume')
    job_desc = request.form.get('job_desc', '')
    category = request.form.get('category', 'mixed')
    
    if not file: return jsonify({"error": "No resume uploaded."}), 400
    
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    raw_text = extract_text_from_pdf(filepath) if filename.endswith('.pdf') else extract_text_from_docx(filepath)
    os.remove(filepath)

    first_msg, history, sys_inst = start_interactive_session(raw_text, job_desc, category)
    if not first_msg: return jsonify({"error": "Failed to start chat."}), 500

    session_data = {
        "system_instruction": sys_inst,
        "history": history
    }

    conn = get_db_connection()
    if not conn:
        return jsonify({"status": "error", "error": "Database connection failed."}), 503

    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO mock_interviews (user_id, session_mode, category, job_description, session_data) VALUES (%s, %s, %s, %s, %s)",
            (current_user.id, 'interactive', category, job_desc[:500], json.dumps(session_data))
        )
        session_id = cursor.lastrowid
        cursor.execute(
            """INSERT INTO interview_sessions
               (source_interview_id, user_id, category, questions_answered, total_questions,
                overall_score, status)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (session_id, current_user.id, category, 0, 1, None, 'In Progress')
        )
        conn.commit()
    except Exception:
        conn.rollback()
        app.logger.exception("Failed to save interactive interview session")
        return jsonify({"status": "error", "error": "Unable to save interview session."}), 500
    finally:
        if cursor is not None:
            cursor.close()
        conn.close()

    return jsonify({"status": "success", "first_message": first_msg, "session_id": session_id})


@app.route('/api/send_chat_message', methods=['POST'])
@login_required
def api_send_chat_message():
    """Handles Mode 2: Ongoing Chat Messaging"""
    data = request.json
    session_id = data.get('session_id')
    user_message = data.get('message')

    if not session_id or not user_message:
        return jsonify({"error": "Session ID and message are required."}), 400

    conn = get_db_connection()
    if not conn: 
        return jsonify({"error": "Database error"}), 500
    
    cursor = None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT session_data FROM mock_interviews WHERE id = %s AND user_id = %s", 
            (session_id, current_user.id)
        )
        record = cursor.fetchone()
        
        if not record:
            return jsonify({"error": "Session not found."}), 404

        session_data = json.loads(record['session_data'])
        sys_inst = session_data['system_instruction']
        history = session_data['history']

        ai_reply, updated_history = continue_interactive_session(sys_inst, history, user_message)
        
        if not ai_reply:
            return jsonify({"error": "AI failed to respond."}), 500

        # Update DB with new history
        session_data['history'] = updated_history
        cursor.execute(
            "UPDATE mock_interviews SET session_data = %s WHERE id = %s", 
            (json.dumps(session_data), session_id)
        )
        answered_count = sum(
            1 for message in updated_history
            if message.get('role') == 'user'
            and not 'Introduce yourself briefly as the AI interviewer' in ' '.join(message.get('parts', []))
        )
        questions_asked = sum(1 for message in updated_history if message.get('role') == 'model')
        cursor.execute(
            """UPDATE interview_sessions
               SET questions_answered = %s, total_questions = %s
               WHERE source_interview_id = %s AND user_id = %s AND status = 'In Progress'""",
            (answered_count, max(questions_asked, answered_count), session_id, current_user.id)
        )
        conn.commit()

        return jsonify({"status": "success", "reply": ai_reply})
        
    except Exception as e:
        print(f"Chat route error: {e}")
        return jsonify({"error": "An internal server error occurred."}), 500
    finally:
        if cursor is not None:
            cursor.close()
        conn.close()

@app.route('/api/complete_interview', methods=['POST'])
@login_required
def api_complete_interview():
    """Completes an interactive session and saves its AI score and feedback."""
    data = request.get_json(silent=True) or {}
    try:
        session_id = int(data.get('session_id'))
    except (TypeError, ValueError):
        return jsonify({"status": "error", "error": "A valid session ID is required."}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({"status": "error", "error": "Database connection failed."}), 503

    cursor = None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """SELECT m.session_data
               FROM mock_interviews m
               JOIN interview_sessions s ON s.source_interview_id = m.id
               WHERE m.id = %s AND m.user_id = %s
                 AND s.user_id = %s AND s.status = 'In Progress'""",
            (session_id, current_user.id, current_user.id)
        )
        record = cursor.fetchone()
        if not record:
            return jsonify({"status": "error", "error": "Active interview session not found."}), 404

        session_data = json.loads(record['session_data'])
        history = session_data.get('history', [])
        answered_count = sum(
            1 for message in history
            if message.get('role') == 'user'
            and not 'Introduce yourself briefly as the AI interviewer' in ' '.join(message.get('parts', []))
        )
        total_questions = max(
            sum(1 for message in history if message.get('role') == 'model'),
            answered_count
        )
        evaluation = evaluate_interview_session(history) if answered_count else None
        score = evaluation['overall_score'] if evaluation else None
        feedback_summary = (
            evaluation['feedback_summary'] if evaluation
            else 'No answers were submitted, so this session has no performance score.'
        )

        cursor.execute(
            """UPDATE interview_sessions
               SET questions_answered = %s, total_questions = %s, overall_score = %s,
                   status = 'Completed', feedback_summary = %s
               WHERE source_interview_id = %s AND user_id = %s AND status = 'In Progress'""",
            (
                answered_count, total_questions, score, feedback_summary,
                session_id, current_user.id
            )
        )
        conn.commit()
        return jsonify({
            "status": "success",
            "questions_answered": answered_count,
            "total_questions": total_questions,
            "overall_score": score,
            "feedback_summary": feedback_summary
        })
    except Exception:
        conn.rollback()
        app.logger.exception("Failed to complete interview session %s", session_id)
        return jsonify({"status": "error", "error": "Unable to complete interview session."}), 502
    finally:
        if cursor is not None:
            cursor.close()
        conn.close()


if __name__ == '__main__':
    app.run(debug=True)