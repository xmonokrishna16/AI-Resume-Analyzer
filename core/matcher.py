from sentence_transformers import SentenceTransformer, util

# Load the lightweight embedding model
# Note: The first time this script runs, it will download the model (approx 80MB)
model = SentenceTransformer('all-MiniLM-L6-v2')

def calculate_match(resume_skills, job_skills):
    """
    Calculates the semantic match score between resume skills and job requirements.
    Also identifies the exact missing skills.
    """
    if not resume_skills or not job_skills:
        return 0.0, []

    # 1. Convert skill lists to single strings for the embedding model
    resume_text = " ".join(resume_skills)
    job_text = " ".join(job_skills)

    # 2. Generate vector embeddings
    resume_embedding = model.encode(resume_text, convert_to_tensor=True)
    job_embedding = model.encode(job_text, convert_to_tensor=True)

    # 3. Calculate Cosine Similarity
    similarity = util.cos_sim(resume_embedding, job_embedding)
    match_score = round(similarity.item() * 100, 2)

    # 4. Find missing skills (Basic set difference)
    # This assumes both lists are already lowercase from the NLP engine
    resume_set = set(resume_skills)
    job_set = set(job_skills)
    missing_skills = list(job_set - resume_set)

    return match_score, missing_skills

# --- Quick Test Block ---
if __name__ == "__main__":
    print("Loading AI Model (this takes a few seconds)...")
    
    # 1. Simulated extracted skills from your resume
    my_resume_skills = ['python', 'flask', 'mysql', 'javascript', 'html', 'css', 'c++']
    
    # 2. Simulated job description requirements (Notice we require Django and React)
    target_job_skills = ['python', 'django', 'postgresql', 'javascript', 'react', 'aws']

    print("\nAnalyzing Match...")
    score, missing = calculate_match(my_resume_skills, target_job_skills)
    
    print(f"\n--- RESULTS ---")
    print(f"Match Score: {score}%")
    
    print("\nMissing Skills to Improve:")
    for skill in missing:
        print(f"❌ {skill}")