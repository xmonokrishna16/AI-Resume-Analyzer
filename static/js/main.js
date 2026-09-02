document.addEventListener('DOMContentLoaded', () => {
    // --- Chart Instance (Scoped to DOMContentLoaded) ---
    let scoreChartInstance = null;

    function renderChart(score) {
        const canvas = document.getElementById('scoreChart');
        if (!canvas) return;

        const ctx = canvas.getContext('2d');
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

    // --- Form Analysis Logic ---
    const analyzeForm = document.getElementById('analyze-form');
    if (analyzeForm) {
        analyzeForm.addEventListener('submit', async (e) => {
            e.preventDefault(); // Prevent page reload

            const form = e.target;
            const formData = new FormData(form);
            const submitBtn = document.getElementById('submit-btn');
            const loadingText = document.getElementById('loading');
            const uploadSection = document.getElementById('upload-section');
            const dashboardSection = document.getElementById('dashboard-section');

            // Show loading state
            if (submitBtn) submitBtn.style.display = 'none';
            if (loadingText) loadingText.style.display = 'block';

            try {
                // Call your Flask API
                const response = await fetch('/api/analyze', {
                    method: 'POST',
                    body: formData
                });

                const data = await response.json();

                if (data.status === 'success') {
                    // Hide upload, show dashboard
                    if (uploadSection) uploadSection.style.display = 'none';
                    if (dashboardSection) dashboardSection.style.display = 'block';

                    // Render Education and Experience
                    document.getElementById('edu-text').innerText = (data.education && data.education.length > 0) ? data.education.join(', ') : 'None Detected';
                    document.getElementById('exp-text').innerText = data.experience || 'Not specified';

                    // Render ATS Health
                    const lengthStatus = document.getElementById('ats-length-status');
                    if (lengthStatus && data.ats_health) {
                        lengthStatus.innerText = data.ats_health.status;
                        lengthStatus.style.color = data.ats_health.status === 'Pass' ? '#16a34a' : '#ea580c';
                    }

                    if (data.ats_health) {
                        document.getElementById('ats-word-count').innerText = data.ats_health.word_count;
                        document.getElementById('ats-message').innerText = data.ats_health.message;
                    }

                    // Render Contact Info Badges
                    const setBadge = (id, hasItem) => {
                        const el = document.getElementById(id);
                        if (!el) return;
                        if (hasItem) {
                            el.style.backgroundColor = '#dcfce7';
                            el.style.color = '#166534';
                            // Remove "(Missing)" if it was previously appended
                            el.innerText = el.innerText.replace(' (Missing)', '');
                        } else {
                            el.style.backgroundColor = '#fee2e2';
                            el.style.color = '#991b1b';
                            if (!el.innerText.includes('(Missing)')) {
                                el.innerText += ' (Missing)';
                            }
                        }
                    };

                    if (data.contact_info) {
                        setBadge('contact-email', data.contact_info.email);
                        setBadge('contact-phone', data.contact_info.phone);
                        setBadge('contact-linkedin', data.contact_info.linkedin);
                    }

                    // 1. Render Score Chart
                    renderChart(data.match_score);
                    document.getElementById('score-text').innerText = `${data.match_score}% Match`;

                    // 2. Render Missing Skills
                    const missingList = document.getElementById('missing-skills-list');
                    if (missingList) {
                        missingList.innerHTML = '';
                        (data.missing_skills || []).forEach(skill => {
                            const li = document.createElement('li');
                            li.innerText = `❌ ${skill}`;
                            missingList.appendChild(li);
                        });
                    }

                    // 3. Render Roadmap
                    const roadmapList = document.getElementById('roadmap-list');
                    if (roadmapList) {
                        roadmapList.innerHTML = '';
                        (data.roadmap || []).forEach(step => {
                            const div = document.createElement('div');
                            div.className = 'roadmap-step';
                            div.innerHTML = `<strong>Step ${step.step}: ${step.skill}</strong><br>${step.action}`;
                            roadmapList.appendChild(div);
                        });
                    }
                } else {
                    alert("Error: " + data.error);
                    if (submitBtn) submitBtn.style.display = 'block';
                    if (loadingText) loadingText.style.display = 'none';
                }
            } catch (error) {
                console.error("Error analyzing resume:", error);
                alert("Something went wrong on the server.");
                if (submitBtn) submitBtn.style.display = 'block';
                if (loadingText) loadingText.style.display = 'none';
            }
        });
    }

    // --- PDF Export Logic ---
    const downloadPdfBtn = document.getElementById('download-pdf-btn');
    if (downloadPdfBtn) {
        downloadPdfBtn.addEventListener('click', () => {
            const dashboardElement = document.getElementById('dashboard-section');
            if (!dashboardElement) return;

            const username = downloadPdfBtn.getAttribute('data-username')
                ? downloadPdfBtn.getAttribute('data-username').replace(/\s+/g, '_')
                : 'User';

            // 1. Temporarily hide the action buttons
            const actionButtons = dashboardElement.querySelectorAll('button');
            actionButtons.forEach(btn => btn.style.display = 'none');

            // 2. Configure the PDF settings
            const opt = {
                margin: 0.5,
                filename: `${username}_AI_Resume_Report.pdf`,
                image: { type: 'jpeg', quality: 0.98 },
                html2canvas: {
                    scale: 2,
                    useCORS: true,
                    scrollY: 0  // Forces the renderer to ignore scroll position
                },
                jsPDF: { unit: 'in', format: 'letter', orientation: 'portrait' }
            };

            // 3. Generate and save the PDF, then restore the buttons
            html2pdf().set(opt).from(dashboardElement).save().then(() => {
                actionButtons.forEach(btn => btn.style.display = 'block');
            });
        });
    }

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
    if (deleteBtn && passwordModal) {
        deleteBtn.addEventListener('click', () => passwordModal.style.display = 'flex');
    }

    if (cancelDeleteBtn && passwordModal) {
        cancelDeleteBtn.addEventListener('click', () => {
            passwordModal.style.display = 'none';
            const passwordInput = document.getElementById('delete-password');
            if (passwordInput) passwordInput.value = ''; // Clear password field
        });
    }

    // Execute Deletion
    if (confirmDeleteBtn) {
        confirmDeleteBtn.addEventListener('click', async () => {
            const passwordInput = document.getElementById('delete-password');
            const password = passwordInput ? passwordInput.value : '';

            if (!password) return alert("Password is required to delete records.");

            const selectedIds = Array.from(deleteCheckboxes)
                .filter(cb => cb.checked)
                .map(cb => parseInt(cb.value));

            if (selectedIds.length === 0) return;

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

    // --- Recruiter Bulk Analysis Logic ---
    const bulkAnalyzeForm = document.getElementById('bulk-analyze-form');

    if (bulkAnalyzeForm) {
        bulkAnalyzeForm.addEventListener('submit', async (e) => {
            e.preventDefault();

            const loadingDiv = document.getElementById('bulk-loading');
            const resultsSection = document.getElementById('bulk-results-section');
            const submitBtn = document.getElementById('bulk-submit-btn');
            const tbody = document.getElementById('candidates-tbody');

            loadingDiv.style.display = 'block';
            submitBtn.disabled = true;
            resultsSection.style.display = 'none';
            tbody.innerHTML = ''; // Clear previous results

            const formData = new FormData(bulkAnalyzeForm);

            try {
                const response = await fetch('/api/bulk_analyze', {
                    method: 'POST',
                    body: formData
                });

                const data = await response.json();

                if (data.status === 'success') {
                    // Populate Table
                    data.results.forEach((candidate, index) => {
                        let badgeColor = '#64748b'; // Default Grey
                        if (candidate.category === 'High Skills & Exp') badgeColor = '#10b981'; // Green
                        else if (candidate.category === 'High Skills') badgeColor = '#3b82f6'; // Blue
                        else if (candidate.category === 'High Exp') badgeColor = '#f59e0b'; // Yellow
                        else if (candidate.category === 'Needs Upskilling') badgeColor = '#ef4444'; // Red

                        const row = `
                            <tr>
                                <td><strong>#${index + 1}</strong></td>
                                <td>${candidate.file_name}</td>
                                <td><strong>${candidate.match_score}%</strong></td>
                                <td>${candidate.experience}</td>
                                <td><span style="background: ${badgeColor}; color: white; padding: 4px 8px; border-radius: 4px; font-size: 0.85em;">${candidate.category}</span></td>
                                <td><button class="btn-secondary" style="padding: 5px 10px; margin: 0; font-size: 0.85em;">View Details</button></td>
                            </tr>
                        `;
                        tbody.innerHTML += row;
                    });

                    resultsSection.style.display = 'block';
                } else {
                    alert("Error: " + data.error);
                }
            } catch (error) {
                console.error("Bulk upload error:", error);
                alert("Something went wrong processing the resumes.");
            } finally {
                loadingDiv.style.display = 'none';
                submitBtn.disabled = false;
            }
        });
    }
    // --- CSV Export Logic for Recruiters ---
    const exportCsvBtn = document.getElementById('export-csv-btn');
    if (exportCsvBtn) {
        exportCsvBtn.addEventListener('click', () => {
            const table = document.getElementById('candidates-table');
            if (!table) return;

            let csvContent = "";
            const rows = table.querySelectorAll('tr');

            rows.forEach((row, index) => {
                const cols = row.querySelectorAll('th, td');
                const rowData = [];

                cols.forEach((col, colIndex) => {
                    // Skip the "Action" column (the last column with the button)
                    if (colIndex !== cols.length - 1) {
                        // Clean up the text: remove existing commas and newlines to prevent CSV breaking
                        let text = col.innerText.replace(/,/g, '').replace(/(\r\n|\n|\r)/gm, ' ').trim();
                        rowData.push(text);
                    }
                });

                csvContent += rowData.join(",") + "\n";
            });

            // Create a Blob and trigger the download
            const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
            const url = URL.createObjectURL(blob);
            const link = document.createElement("a");
            link.setAttribute("href", url);

            // Generate a filename with today's date
            const dateStr = new Date().toISOString().split('T')[0];
            link.setAttribute("download", `Recruiter_Shortlist_${dateStr}.csv`);

            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        });
    }


});