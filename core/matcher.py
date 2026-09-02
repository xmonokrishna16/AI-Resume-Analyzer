import re
from sentence_transformers import SentenceTransformer, util

# Load the model once to keep the application fast
model = SentenceTransformer('all-MiniLM-L6-v2')

def extract_years_required(job_text):
    """Extracts the minimum years of experience required from a job description."""
    pattern = r'(\d+)\+?\s*(years?|yrs?)\s*(of\s*)?experience'
    match = re.search(pattern, job_text.lower())
    if match:
        return int(match.group(1))
    return 0 # Default to 0 if entry-level or not specified

def parse_resume_years(exp_string):
    """Converts the NLP experience string back into an integer."""
    if not exp_string or "Entry Level" in exp_string or "Not Specified" in exp_string:
        return 0
    match = re.search(r'(\d+)', exp_string)
    if match:
        return int(match.group(1))
    return 0

def calculate_match(resume_skills, job_skills, resume_edu, resume_exp, job_desc):
    """
    Calculates a weighted match score based on Skills (60%), Experience (20%), and Education (20%).
    """
    # 1. Edge Case: Empty inputs
    if not job_skills:
        return 0, [], {"skills": 0, "experience": 0, "education": 0}
        
    if not resume_skills:
        return 0, job_skills, {"skills": 0, "experience": 0, "education": 0}

    # 2. Skills Match (60% Weight)
    resume_text = " ".join(resume_skills)
    job_text = " ".join(job_skills)

    resume_embedding = model.encode(resume_text, convert_to_tensor=True)
    job_embedding = model.encode(job_text, convert_to_tensor=True)

    cosine_score = util.cos_sim(resume_embedding, job_embedding).item()
    base_skill_score = max(0, min(100, int(cosine_score * 100)))
    
    missing_skills = [skill for skill in job_skills if skill.lower() not in [rs.lower() for rs in resume_skills]]

    # 3. Experience Match (20% Weight)
    job_years_req = extract_years_required(job_desc)
    res_years = parse_resume_years(resume_exp)
    
    if job_years_req == 0:
        exp_score = 100 # No experience required -> instant max score for this category
    elif res_years >= job_years_req:
        exp_score = 100 # Meets or exceeds requirements
    else:
        exp_score = int((res_years / job_years_req) * 100) # Partial credit
        
    # 4. Education Match (20% Weight)
    edu_score = 100
    job_lower = job_desc.lower()
    needs_degree = any(keyword in job_lower for keyword in ['bachelor', 'degree', 'b.tech', 'btech', 'master', 'phd', 'b.sc', 'bsc'])
    
    if needs_degree and len(resume_edu) == 0:
        edu_score = 25 # Penalty for missing required education (give 25% base so it isn't too brutal)
    elif needs_degree and len(resume_edu) > 0:
        edu_score = 100

    # 5. Calculate Final Weighted Score
    weighted_total = (base_skill_score * 0.60) + (exp_score * 0.20) + (edu_score * 0.20)
    final_score = int(weighted_total)

    breakdown = {
        "skills": int(base_skill_score * 0.60),
        "experience": int(exp_score * 0.20),
        "education": int(edu_score * 0.20)
    }

    return final_score, missing_skills, breakdown