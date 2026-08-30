# A simple knowledge base for your MVP. You can expand this later.
ROADMAP_DATA = {
    'react': "Learn React components, hooks (useState, useEffect), and state management.",
    'django': "Study Django ORM, function/class-based views, and URL routing.",
    'postgresql': "Learn relational database design, complex joins, and indexing.",
    'aws': "Start with AWS IAM basics, S3 for storage, and EC2 for hosting.",
    'docker': "Learn to write Dockerfiles and manage containers with Docker Compose.",
    'spring boot': "Learn Spring MVC, dependency injection, and JPA."
}

def generate_roadmap(missing_skills):
    """Generates actionable learning steps for missing skills."""
    roadmap = []
    for i, skill in enumerate(missing_skills):
        # Fetch the specific advice, or provide a default fallback
        action = ROADMAP_DATA.get(skill.lower(), f"Look up crash courses and documentation for {skill}.")
        roadmap.append({
            "step": i + 1,
            "skill": skill.capitalize(),
            "action": action
        })
    return roadmap