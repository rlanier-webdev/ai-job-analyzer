// Global variables
let currentTab = "paste";
let selectedFile = null;
let workEntryId = 0;

// Global functions for onclick handlers
function openProfileModal() {
    document.getElementById('profileModal').classList.add('active');
}

function closeProfileModal() {
    document.getElementById('profileModal').classList.remove('active');
}

function switchTab(tab) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

    const tabIdx = tab === 'paste' ? 1 : tab === 'upload' ? 2 : 3;
    document.querySelector(`.tab:nth-child(${tabIdx})`).classList.add('active');
    document.getElementById(`tab-${tab}`).classList.add('active');
    currentTab = tab;
}

function handleFileSelect(event) {
    const file = event.target.files[0];
    if (file) {
        selectedFile = file;
        document.getElementById('fileName').textContent = file.name;
    }
}

async function analyze() {
    const btn = document.getElementById('analyzeBtn');
    const loading = document.getElementById('loading');
    const error = document.getElementById('errorMessage');
    const results = document.getElementById('results');

    btn.disabled = true;
    loading.classList.add('active');
    error.classList.remove('active');
    results.classList.remove('active');

    try {
        const formData = new FormData();
        let endpoint = `/api/analyze/${currentTab}`;

        if (currentTab === 'paste') {
            const text = document.getElementById('jobText').value;
            if (!text.trim()) throw new Error('Please paste a job description');
            formData.append('job_text', text);
        } else if (currentTab === 'upload') {
            if (!selectedFile) throw new Error('Please select a PDF file');
            formData.append('file', selectedFile);
            endpoint = `/api/analyze/pdf`; // match FastAPI route
        } else if (currentTab === 'url') {
            const url = document.getElementById('jobUrl').value;
            if (!url.trim()) throw new Error('Please enter a URL');
            formData.append('url', url);
        }

        const response = await fetch(endpoint, {
            method: 'POST',
            body: formData,
        });

        if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.detail || 'Analysis failed');
        }

        const data = await response.json();
        displayResults(data);
    } catch (err) {
        error.textContent = err.message;
        error.classList.add('active');
    } finally {
        btn.disabled = false;
        loading.classList.remove('active');
    }
}

function displayResults(data) {
    document.getElementById('results').classList.add('active');

    // Header
    const title = data.job_title !== 'Unknown Position' ? `${data.job_title} @ ${data.job_company}` : 'Analysis Result';
    document.getElementById('resultTitle').textContent = title;

    // Score & Verdict
    const scoreBadge = document.getElementById('scoreBadge');
    scoreBadge.textContent = `${data.qualification_score}/100`;
    scoreBadge.className = `score-badge ${data.qualification_score >= 80 ? 'score-high' : data.qualification_score >= 60 ? 'score-mid' : 'score-low'}`;

    const verdict = document.getElementById('applyVerdict');
    verdict.textContent = data.should_apply ? 'APPLY' : 'SKIP';
    verdict.className = `verdict ${data.should_apply ? 'verdict-yes' : 'verdict-no'}`;

    // Body Sections
    document.getElementById('qualSummary').textContent = data.qualification_summary;
    document.getElementById('applyReasoning').textContent = data.apply_reasoning;
    document.getElementById('salaryAssessment').textContent = data.salary_assessment;
    document.getElementById('salaryRec').textContent = data.salary_recommendation;
    document.getElementById('overallRec').textContent = data.overall_recommendation;

    // Lists
    const listMap = {
        'matchingSkills': { items: data.matching_skills, icon: 'fas fa-check-circle', color: '#38a169' },
        'missingSkills': { items: data.missing_skills, icon: 'fas fa-times-circle', color: '#e53e3e' },
        'greenFlags': { items: data.green_flags, icon: 'fas fa-plus-circle', color: '#38a169' },
        'redFlags': { items: data.red_flags, icon: 'fas fa-exclamation-triangle', color: '#e53e3e' },
        'interviewTips': { items: data.interview_tips, icon: 'fas fa-lightbulb', color: '#4361ee' }
    };

    for (const [id, config] of Object.entries(listMap)) {
        const el = document.getElementById(id);
        if (config.items.length) {
            el.innerHTML = config.items.map(i => `<li><i class="${config.icon}" style="color: ${config.color}; margin-right: 0.5em;"></i>${i}</li>`).join('');
        } else {
            el.innerHTML = '<li><i class="fas fa-minus-circle" style="color: #666; margin-right: 0.5em;"></i>None identified</li>';
        }
    }

    results.scrollIntoView({ behavior: 'smooth' });
}

function addWorkEntry(data = {}) {
    const container = document.getElementById('workHistoryEntries');
    const id = workEntryId++;
    const entry = document.createElement('div');
    entry.className = 'work-entry';
    entry.id = `work-entry-${id}`;
    entry.innerHTML = `
        <button type="button" class="remove-btn" onclick="removeWorkEntry(${id})"><i class="fas fa-times"></i></button>
        <div class="form-row">
            <div class="form-group"><label>Title</label><input type="text" class="work-title" value="${data.title || ''}"></div>
            <div class="form-group"><label>Company</label><input type="text" class="work-company" value="${data.company || ''}"></div>
        </div>
        <div class="form-group"><label>Description</label><textarea class="work-description" rows="2">${data.description || ''}</textarea></div>
    `;
    container.appendChild(entry);
}

function removeWorkEntry(id) {
    document.getElementById(`work-entry-${id}`).remove();
}

function getWorkHistory() {
    return Array.from(document.querySelectorAll('.work-entry')).map(entry => ({
        title: entry.querySelector('.work-title').value,
        company: entry.querySelector('.work-company').value,
        description: entry.querySelector('.work-description').value
    })).filter(e => e.title);
}

function loadWorkHistory(history) {
    const container = document.getElementById('workHistoryEntries');
    container.innerHTML = '';
    (history || []).forEach(addWorkEntry);
}

document.addEventListener('DOMContentLoaded', function() {
    // --- NEW: RESUME AUTO-FILL ---
    async function handleResumeUpload(event) {
      const file = event.target.files[0];
      if (!file) return;

      const status = document.getElementById("profileStatus");
      status.textContent = "Processing Resume...";
      status.className = "profile-status";

      const formData = new FormData();
      formData.append("file", file);

      try {
        const response = await fetch("/api/profile/upload-resume", {
          method: "POST",
          body: formData,
        });

        if (!response.ok) throw new Error("Failed to parse resume");

        const newProfile = await response.json();
        updateProfileUI(newProfile);
        alert("Profile updated successfully from resume!");
      } catch (err) {
        alert("Error: " + err.message);
        status.textContent = "Upload Failed";
      }
    }

    function updateProfileUI(profile) {
      document.getElementById("profileStatus").textContent =
        `Loaded: ${profile.name}`;
      document.getElementById("profileStatus").classList.add("loaded");

      // Fill form fields
      document.getElementById("pName").value = profile.name || "";
      document.getElementById("pTitle").value = profile.title || "";
      document.getElementById("pYears").value = profile.years_experience || 0;
      document.getElementById("pSkills").value = (profile.skills || []).join(
        ", ",
      );
      document.getElementById("pEducation").value = (
        profile.education || []
      ).join(", ");
      document.getElementById("pLocations").value = (
        profile.preferred_locations || []
      ).join(", ");
      document.getElementById("pRemote").value =
        profile.remote_preference || "flexible";
      document.getElementById("pSalary").value = profile.min_salary || "";
      document.getElementById("pSummary").value = profile.summary || "";
      loadWorkHistory(profile.work_history);
    }

    async function loadProfile() {
      try {
        const response = await fetch("/api/profile");
        if (response.ok) {
          const profileData = await response.json();
          updateProfileUI(profileData);
        }
      } catch (err) {
        console.log("Init: No profile found");
      }
    }

    // Set up form submission
    document.getElementById('profileForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        const profile = {
            name: document.getElementById('pName').value,
            title: document.getElementById('pTitle').value,
            years_experience: parseInt(document.getElementById('pYears').value) || 0,
            skills: document.getElementById('pSkills').value.split(',').map(s => s.trim()).filter(Boolean),
            education: document.getElementById('pEducation').value.split(',').map(s => s.trim()).filter(Boolean),
            preferred_locations: document.getElementById('pLocations').value.split(',').map(s => s.trim()).filter(Boolean),
            remote_preference: document.getElementById('pRemote').value,
            min_salary: parseInt(document.getElementById('pSalary').value) || null,
            summary: document.getElementById('pSummary').value,
            work_history: getWorkHistory(),
        };

        const response = await fetch('/api/profile', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(profile),
        });

        if (response.ok) {
            closeProfileModal();
            loadProfile();
        }
    });

    loadProfile();
})