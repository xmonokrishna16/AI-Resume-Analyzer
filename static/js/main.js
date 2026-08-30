document.getElementById('analyze-form').addEventListener('submit', async (e) => {
    e.preventDefault(); // Prevent page reload

    const form = e.target;
    const formData = new FormData(form);
    const submitBtn = document.getElementById('submit-btn');
    const loadingText = document.getElementById('loading');
    const uploadSection = document.getElementById('upload-section');
    const dashboardSection = document.getElementById('dashboard-section');

    // Show loading state
    submitBtn.style.display = 'none';
    loadingText.style.display = 'block';

    try {
        // Call your Flask API
        const response = await fetch('/api/analyze', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (data.status === 'success') {
            // Hide upload, show dashboard
            uploadSection.style.display = 'none';
            dashboardSection.style.display = 'block';

            // Render Education and Experience
            document.getElementById('edu-text').innerText = data.education.length > 0 ? data.education.join(', ') : 'None Detected';
            document.getElementById('exp-text').innerText = data.experience;

            // 1. Render Score Chart
            renderChart(data.match_score);
            document.getElementById('score-text').innerText = `${data.match_score}% Match`;

            // 2. Render Missing Skills
            const missingList = document.getElementById('missing-skills-list');
            missingList.innerHTML = '';
            data.missing_skills.forEach(skill => {
                const li = document.createElement('li');
                li.innerText = `❌ ${skill}`;
                missingList.appendChild(li);
            });

            // 3. Render Roadmap
            const roadmapList = document.getElementById('roadmap-list');
            roadmapList.innerHTML = '';
            data.roadmap.forEach(step => {
                const div = document.createElement('div');
                div.className = 'roadmap-step';
                div.innerHTML = `<strong>Step ${step.step}: ${step.skill}</strong><br>${step.action}`;
                roadmapList.appendChild(div);
            });
        } else {
            alert("Error: " + data.error);
            submitBtn.style.display = 'block';
            loadingText.style.display = 'none';
        }
    } catch (error) {
        console.error("Error analyzing resume:", error);
        alert("Something went wrong on the server.");
        submitBtn.style.display = 'block';
        loadingText.style.display = 'none';
    }
});

let scoreChartInstance = null;
function renderChart(score) {
    const ctx = document.getElementById('scoreChart').getContext('2d');
    if (scoreChartInstance) scoreChartInstance.destroy();

    scoreChartInstance = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Match', 'Gap'],
            datasets: [{
                data: [score, 100 - score],
                backgroundColor: ['#22c55e', '#e2e8f0'],
                borderWidth: 0
            }]
        },
        options: { cutout: '80%', responsive: true }
    });
}