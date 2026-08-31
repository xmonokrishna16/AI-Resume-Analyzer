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

// --- PDF Export Logic ---
document.getElementById('download-pdf-btn').addEventListener('click', () => {
    const dashboardElement = document.getElementById('dashboard-section');
    const button = document.getElementById('download-pdf-btn');
    const username = button.getAttribute('data-username').replace(/\s+/g, '_');

    // 1. Temporarily hide the action buttons
    const actionButtons = dashboardElement.querySelectorAll('button');
    actionButtons.forEach(btn => btn.style.display = 'none');

    // 2. Configure the PDF settings (with scrollY fix)
    const opt = {
        margin: 0.5,
        filename: `${username}_AI_Resume_Report.pdf`,
        image: { type: 'jpeg', quality: 0.98 },
        html2canvas: {
            scale: 2,
            useCORS: true,
            scrollY: 0  // <--- Forces the renderer to ignore your scroll position
        },
        jsPDF: { unit: 'in', format: 'letter', orientation: 'portrait' }
    };

    // 3. Generate and save the PDF, then restore the buttons
    html2pdf().set(opt).from(dashboardElement).save().then(() => {
        actionButtons.forEach(btn => btn.style.display = 'block');
    });
});

// --- Secure Deletion Logic ---
const selectAllCheckbox = document.getElementById('select-all');
const deleteCheckboxes = document.querySelectorAll('.delete-checkbox');
const deleteBtn = document.getElementById('delete-selected-btn');
const passwordModal = document.getElementById('password-modal');
const cancelDeleteBtn = document.getElementById('cancel-delete-btn');
const confirmDeleteBtn = document.getElementById('confirm-delete-btn');

// Show/Hide Delete Button based on selections
function toggleDeleteButton() {
    const anyChecked = Array.from(deleteCheckboxes).some(cb => cb.checked);
    if (deleteBtn) deleteBtn.style.display = anyChecked ? 'inline-block' : 'none';
}

if (selectAllCheckbox) {
    selectAllCheckbox.addEventListener('change', (e) => {
        deleteCheckboxes.forEach(cb => cb.checked = e.target.checked);
        toggleDeleteButton();
    });
}

deleteCheckboxes.forEach(cb => cb.addEventListener('change', toggleDeleteButton));

// Modal Controls
if (deleteBtn) {
    deleteBtn.addEventListener('click', () => passwordModal.style.display = 'flex');
}

if (cancelDeleteBtn) {
    cancelDeleteBtn.addEventListener('click', () => {
        passwordModal.style.display = 'none';
        document.getElementById('delete-password').value = ''; // Clear password field
    });
}

// Execute Deletion
if (confirmDeleteBtn) {
    confirmDeleteBtn.addEventListener('click', async () => {
        const password = document.getElementById('delete-password').value;
        if (!password) return alert("Password is required to delete records.");

        const selectedIds = Array.from(deleteCheckboxes)
            .filter(cb => cb.checked)
            .map(cb => parseInt(cb.value));

        try {
            const response = await fetch('/api/delete_history', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ analysis_ids: selectedIds, password: password })
            });

            const data = await response.json();
            if (data.status === 'success') {
                location.reload(); // Refresh to show updated table
            } else {
                alert(data.message); // Show password error
            }
        } catch (error) {
            console.error("Deletion error:", error);
            alert("Something went wrong processing your request.");
        }
    });
}