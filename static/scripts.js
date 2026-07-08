// ─── State ────────────────────────────────────────────────
let currentTab = 'paste';
let selectedFile = null;
let workEntryId = 0;

// ─── View switching ───────────────────────────────────────
function showView(name) {
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(n => {
        n.classList.toggle('active', n.dataset.view === name);
    });
    const el = document.getElementById(`view-${name}`);
    if (el) el.classList.add('active');
    if (name === 'history') loadHistory();
}

// ─── Tab switching (analyzer input) ──────────────────────
function switchTab(tab) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    document.querySelector(`.tab[data-tab="${tab}"]`).classList.add('active');
    document.getElementById(`tab-${tab}`).classList.add('active');
    currentTab = tab;
}

// ─── File handling ────────────────────────────────────────
function handleFileSelect(event) {
    const file = event.target.files[0];
    if (file) {
        selectedFile = file;
        document.getElementById('fileName').textContent = file.name;
    }
}

// ─── PDF export ───────────────────────────────────────────
function exportPDF() {
    window.print();
}

// ─── Job analysis ─────────────────────────────────────────
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
        let endpoint;

        if (currentTab === 'paste') {
            const text = document.getElementById('jobText').value;
            if (!text.trim()) throw new Error('Please paste a job description');
            formData.append('job_text', text);
            endpoint = '/api/analyze/text';
        } else if (currentTab === 'upload') {
            if (!selectedFile) throw new Error('Please select a PDF file');
            formData.append('file', selectedFile);
            endpoint = '/api/analyze/pdf';
        } else if (currentTab === 'url') {
            const url = document.getElementById('jobUrl').value;
            if (!url.trim()) throw new Error('Please enter a URL');
            formData.append('url', url);
            endpoint = '/api/analyze/url';
        }

        const response = await fetch(endpoint, { method: 'POST', body: formData });

        if (!response.ok) {
            const errData = await response.json().catch(() => ({}));
            throw new Error(_errorText(errData.detail) || 'Analysis failed');
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

// ─── Display analysis report ──────────────────────────────
function displayResults(data) {
    const results = document.getElementById('results');
    results.classList.add('active');

    const jobTitle = data.job_title && data.job_title !== 'Unknown Position'
        ? data.job_title : 'Analysis Result';
    const jobCompany = data.job_company || '';

    // Timestamp badge
    const ts = data.created_at ? _relativeTime(data.created_at) : 'Just now';
    document.getElementById('reportTimestamp').textContent = `Analysis · ${ts}`;

    // Company logo initial
    const logoEl = document.getElementById('reportLogo');
    logoEl.textContent = jobCompany ? jobCompany.trim()[0].toUpperCase() : '?';

    // Title
    document.getElementById('resultTitle').textContent = jobTitle;

    // Subtitle: Company · Seniority · Job type
    const subtitleParts = [jobCompany, data.seniority_level, data.job_type].filter(Boolean);
    document.getElementById('reportSubtitle').textContent = subtitleParts.join(' · ');

    // Meta chips (location, salary, remote)
    _buildMetaChips(data);

    // Score ring
    const score = data.qualification_score || 0;
    _animateScoreRing(score);
    const scoreNumEl = document.getElementById('scoreNumber');
    scoreNumEl.textContent = score;
    const ringTextEl = document.getElementById('scoreRingText');
    const tier = score >= 80 ? 'strong' : score >= 60 ? 'good' : 'weak';
    const tierLabel = tier === 'strong' ? 'Strong Match' : tier === 'good' ? 'Good Match' : 'Weak Match';
    scoreNumEl.className = `score-number ${tier}`;
    ringTextEl.textContent = tierLabel;
    ringTextEl.className = `score-ring-text ${tier}`;

    // Verdict banner
    const banner = document.getElementById('verdictBanner');
    const verdictText = document.getElementById('verdictText');
    const headline = document.getElementById('verdictHeadline');
    if (data.should_apply) {
        banner.className = 'verdict-banner apply';
        verdictText.textContent = 'Apply';
        headline.textContent = 'This is squarely in your lane — apply.';
    } else {
        banner.className = 'verdict-banner skip';
        verdictText.textContent = 'Skip';
        headline.textContent = 'Not the right fit right now — skip.';
    }
    document.getElementById('verdictReasoning').textContent = data.qualification_summary || '';

    // Skills chips
    _renderSkillChips('matchingSkills', data.matching_skills, 'match');
    _renderSkillChips('missingSkills', data.missing_skills, 'miss');
    document.getElementById('matchCount').textContent = (data.matching_skills || []).length;
    document.getElementById('missingCount').textContent = (data.missing_skills || []).length;
    _renderTrainingResources(data.training_resources || {});

    // Salary
    document.getElementById('salaryAssessment').textContent = data.salary_assessment || '';
    document.getElementById('salaryRec').textContent = data.salary_recommendation || '';
    _renderSalaryBar(data);

    // Flags
    _renderFlagList('greenFlags', data.green_flags || []);
    _renderFlagList('redFlags', data.red_flags || []);

    // Interview tips
    _renderInterviewTips(data.interview_tips || []);

    // Overall recommendation
    document.getElementById('overallRec').textContent = data.overall_recommendation || '';

    // Scroll to report
    results.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function _buildMetaChips(data) {
    const chips = document.getElementById('reportMetaChips');
    chips.innerHTML = '';

    const addText = (icon, text) => {
        if (!text) return;
        const c = document.createElement('span');
        c.className = 'meta-chip';
        c.innerHTML = `<i class="${icon}"></i>`;
        c.appendChild(document.createTextNode(text));
        chips.appendChild(c);
    };

    // Location — combine remote_policy + job_location
    const locationParts = [data.remote_policy, data.job_location].filter(Boolean);
    if (locationParts.length) addText('fa-solid fa-location-dot', locationParts.join(' · '));

    // Salary
    if (data.salary_range) addText('fa-solid fa-dollar-sign', data.salary_range);

    // Source URL — show hostname only as a link
    const rawUrl = data.source_url || data.job_url;
    if (rawUrl) {
        try {
            const hostname = new URL(rawUrl).hostname.replace(/^www\./, '');
            const a = document.createElement('a');
            a.className = 'meta-chip';
            a.href = rawUrl;
            a.target = '_blank';
            a.rel = 'noopener noreferrer';
            a.style.textDecoration = 'none';
            a.innerHTML = `<i class="fa-solid fa-link"></i>`;
            a.appendChild(document.createTextNode(hostname));
            chips.appendChild(a);
        } catch (_) {}
    }
}

function _animateScoreRing(score) {
    const circumference = 263.9;
    const fill = document.getElementById('scoreRingFill');
    const offset = circumference - (score / 100) * circumference;
    fill.style.strokeDashoffset = circumference; // reset
    fill.style.stroke = score >= 80 ? 'var(--green)' : score >= 60 ? 'var(--yellow)' : 'var(--red)';
    // trigger animation next frame
    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            fill.style.strokeDashoffset = offset;
        });
    });
}

function _renderSkillChips(containerId, skills, type) {
    const el = document.getElementById(containerId);
    if (!skills || skills.length === 0) {
        el.innerHTML = '<span class="skill-chip ' + type + '" style="opacity:.5">None identified</span>';
        return;
    }
    el.innerHTML = skills.map(s =>
        `<span class="skill-chip ${type}">${_esc(s)}</span>`
    ).join('');
}

function _renderTrainingResources(resources) {
    const wrap = document.getElementById('trainingResources');
    const list = document.getElementById('trainingList');
    const entries = Object.entries(resources);
    if (!entries.length) {
        wrap.style.display = 'none';
        return;
    }
    wrap.style.display = 'block';
    list.innerHTML = entries.map(([skill, resource]) => {
        const safeResource = typeof resource === 'string'
            ? resource
            : (resource?.url || resource?.name || resource?.title || String(resource));
        const isUrl = safeResource.startsWith('http');
        const resourceHTML = isUrl
            ? `<a href="${_esc(safeResource)}" target="_blank" rel="noopener noreferrer">${_esc(safeResource)}</a>`
            : _esc(safeResource);
        return `<li class="training-item">
            <span class="training-skill">${_esc(skill)}</span>
            <span class="training-resource">${resourceHTML}</span>
        </li>`;
    }).join('');
}

function _renderFlagList(containerId, flags) {
    const el = document.getElementById(containerId);
    if (!flags.length) {
        el.innerHTML = '<li style="opacity:.5;font-size:.8rem">None identified</li>';
        return;
    }
    el.innerHTML = flags.map(f => `<li>${_esc(f)}</li>`).join('');
}

function _renderInterviewTips(tips) {
    const el = document.getElementById('interviewTips');
    if (!tips.length) {
        el.innerHTML = '<li class="tip-item"><div class="tip-desc" style="opacity:.5">No tips available</div></li>';
        return;
    }
    el.innerHTML = tips.map((tip, i) => {
        // Tips may be full sentences — split on first "." or ":" for a title/desc split
        const colonIdx = tip.indexOf(':');
        let titleText = '';
        let descText = tip;
        if (colonIdx > 0 && colonIdx < 60) {
            titleText = tip.slice(0, colonIdx).trim();
            descText = tip.slice(colonIdx + 1).trim();
        }
        return `<li class="tip-item">
            <div class="tip-number">${i + 1}</div>
            <div>
                ${titleText ? `<div class="tip-title">${_esc(titleText)}</div>` : ''}
                <div class="tip-desc">${_esc(descText)}</div>
            </div>
        </li>`;
    }).join('');
}

function _renderSalaryBar(data) {
    const rangeLabel = document.getElementById('salaryRangeLabel');
    const barFill = document.getElementById('salaryBarFill');
    const marker = document.getElementById('salaryTargetMarker');

    // Try to show the job salary range as the label
    const rangeText = data.salary_range || '';
    rangeLabel.textContent = rangeText || '—';

    // Parse min salary from profile and job range for bar positioning
    // We'll animate fill to represent match quality (score-based fallback)
    const fill = Math.min(100, Math.max(5, data.qualification_score || 50));
    barFill.style.width = fill + '%';

    // Position target marker if we can parse numbers
    const nums = rangeText.match(/\d[\d,]*/g);
    if (nums && nums.length >= 2 && data.min_salary) {
        const low = parseInt(nums[0].replace(/,/g, ''));
        const high = parseInt(nums[nums.length - 1].replace(/,/g, ''));
        const target = data.min_salary;
        if (target >= low && target <= high) {
            const pct = ((target - low) / (high - low)) * 100;
            marker.style.display = 'flex';
            marker.style.left = pct + '%';
        } else {
            marker.style.display = 'none';
        }
    } else {
        marker.style.display = 'none';
    }
}

// ─── Job search ───────────────────────────────────────────
async function searchJobs() {
    const btn = document.getElementById('searchBtn');
    const loading = document.getElementById('searchLoading');
    const errorEl = document.getElementById('searchError');
    const resultsEl = document.getElementById('searchResults');

    btn.disabled = true;
    loading.classList.add('active');
    errorEl.classList.remove('active');
    resultsEl.style.display = 'none';

    try {
        const response = await fetch('/api/search', { method: 'POST' });
        if (!response.ok) {
            let message = 'Search failed';
            try {
                const err = await response.json();
                message = err.detail || message;
            } catch {
                message = `Search failed (${response.status})`;
            }
            throw new Error(message);
        }
        const data = await response.json();
        displayJobList(data);
    } catch (err) {
        errorEl.textContent = err.message;
        errorEl.classList.add('active');
    } finally {
        btn.disabled = false;
        loading.classList.remove('active');
    }
}

function displayJobList(data) {
    const resultsEl = document.getElementById('searchResults');
    const listEl = document.getElementById('jobList');

    document.getElementById('searchQueryUsed').textContent =
        `Search query: "${data.query_used}" — ${data.jobs.length} result(s)`;

    listEl.innerHTML = '';

    data.jobs.forEach(job => {
        const scoreClass = job.score != null
            ? (job.score >= 80 ? 'score-high' : job.score >= 60 ? 'score-mid' : 'score-low')
            : 'score-unscored';
        const scoreLabel = job.score != null ? `${job.score}/100` : 'Unscored';

        const verdictHTML = job.should_apply === true
            ? '<span class="verdict-pill verdict-yes">APPLY</span>'
            : job.should_apply === false
            ? '<span class="verdict-pill verdict-no">SKIP</span>'
            : '';

        const card = document.createElement('div');
        card.className = 'job-card';
        card.innerHTML = `
            <div class="job-card-header">
                <div>
                    <div class="job-card-title"></div>
                    <div class="job-card-meta"></div>
                    ${job.salary ? '<div class="job-card-salary"></div>' : ''}
                </div>
                <span class="score-pill ${scoreClass}">${_esc(scoreLabel)}</span>
            </div>
            ${job.summary ? '<p class="job-card-summary"></p>' : ''}
            <div class="job-card-footer">
                ${verdictHTML}
                <a href="" target="_blank" rel="noopener noreferrer" class="btn btn-outline btn-small">
                    <i class="fa-solid fa-arrow-up-right-from-square"></i> View Posting
                </a>
                <button class="btn btn-outline btn-small js-full-analysis">
                    <i class="fa-solid fa-wand-magic-sparkles"></i> Full Analysis
                </button>
            </div>`;

        card.querySelector('.job-card-title').textContent = job.title;
        card.querySelector('.job-card-meta').textContent = `${job.company} · ${job.location}`;
        if (job.salary) card.querySelector('.job-card-salary').textContent = job.salary;
        if (job.summary) card.querySelector('.job-card-summary').textContent = job.summary;
        card.querySelector('a').href = job.url;
        card.querySelector('.js-full-analysis').addEventListener('click', () => analyzeFromSearch(job.url));

        listEl.appendChild(card);
    });

    resultsEl.style.display = 'block';
    resultsEl.scrollIntoView({ behavior: 'smooth' });
}

function analyzeFromSearch(url) {
    showView('analyzer');
    switchTab('url');
    document.getElementById('jobUrl').value = url;
    document.getElementById('analyzerInputCard').scrollIntoView({ behavior: 'smooth' });
}

// ─── Resume upload ────────────────────────────────────────
async function handleResumeUpload(event) {
    const file = event.target.files[0];
    if (!file) return;

    const status = document.getElementById('profileStatus');
    status.textContent = 'Processing Resume...';
    status.className = 'profile-status';

    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch('/api/profile/upload-resume', { method: 'POST', body: formData });
        if (!response.ok) throw new Error('Failed to parse resume');
        const newProfile = await response.json();
        updateProfileUI(newProfile);
        alert('Profile updated successfully from resume!');
    } catch (err) {
        alert('Error: ' + err.message);
        status.textContent = 'Upload Failed';
    }
}

// ─── Profile UI ───────────────────────────────────────────
function updateProfileUI(profile) {
    document.getElementById('profileStatus').textContent = `Loaded: ${profile.name}`;
    document.getElementById('profileStatus').classList.add('loaded');
    document.getElementById('profileNameDisplay').textContent = profile.name || 'Not loaded';
    document.getElementById('profileTitleDisplay').textContent = profile.title || '—';
    // Update avatar initials
    const initials = (profile.name || '?').split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase();
    document.getElementById('profileAvatar').textContent = initials;

    document.getElementById('pName').value = profile.name || '';
    document.getElementById('pTitle').value = profile.title || '';
    document.getElementById('pYears').value = profile.years_experience || 0;
    document.getElementById('pSkills').value = (profile.skills || []).join(', ');
    document.getElementById('pEducation').value = (profile.education || []).join(', ');
    document.getElementById('pLocations').value = (profile.preferred_locations || []).join(', ');
    document.getElementById('pRemote').value = profile.remote_preference || 'flexible';
    document.getElementById('pSalary').value = profile.min_salary || '';
    document.getElementById('pSummary').value = profile.summary || '';
    loadWorkHistory(profile.work_history);
}

// ─── Work history ─────────────────────────────────────────
function addWorkEntry(data = {}) {
    const container = document.getElementById('workHistoryEntries');
    const id = workEntryId++;
    const entry = document.createElement('div');
    entry.className = 'work-entry';
    entry.id = `work-entry-${id}`;
    entry.innerHTML = `
        <button type="button" class="remove-btn" onclick="removeWorkEntry(${id})">
            <i class="fas fa-times"></i>
        </button>
        <div class="form-row">
            <div class="form-group"><label>Title</label><input type="text" class="work-title" value="${_esc(data.title || '')}"></div>
            <div class="form-group"><label>Company</label><input type="text" class="work-company" value="${_esc(data.company || '')}"></div>
        </div>
        <div class="form-group"><label>Description</label><textarea class="work-description" rows="2">${_esc(data.description || '')}</textarea></div>
    `;
    container.appendChild(entry);
}

function removeWorkEntry(id) {
    const el = document.getElementById(`work-entry-${id}`);
    if (el) el.remove();
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
    workEntryId = 0;
    (history || []).forEach(addWorkEntry);
}

// ─── History ──────────────────────────────────────────────
async function loadHistory() {
    const listEl = document.getElementById('historyList');
    const emptyEl = document.getElementById('historyEmpty');

    try {
        const response = await fetch('/api/history');
        if (!response.ok) throw new Error('Failed to load history');
        const entries = await response.json();

        // Remove existing cards (keep the empty state element)
        listEl.querySelectorAll('.history-card').forEach(c => c.remove());

        if (entries.length === 0) {
            emptyEl.style.display = 'flex';
            return;
        }

        emptyEl.style.display = 'none';

        entries.forEach(entry => {
            const scoreClass = entry.score >= 80 ? 'score-high' : entry.score >= 60 ? 'score-mid' : 'score-low';
            const verdictHTML = entry.should_apply
                ? '<span class="verdict-pill verdict-yes">APPLY</span>'
                : '<span class="verdict-pill verdict-no">SKIP</span>';
            const date = new Date(entry.created_at).toLocaleDateString('en-US', {
                month: 'short', day: 'numeric', year: 'numeric',
                hour: '2-digit', minute: '2-digit'
            });
            const title = entry.job_title || 'Unknown Position';
            const company = entry.job_company || '';

            const card = document.createElement('div');
            card.className = 'history-card';
            card.innerHTML = `
                <div class="history-card-left">
                    <span class="score-pill ${scoreClass}">${entry.score}/100</span>
                    <div class="history-card-info">
                        <div class="history-card-title"></div>
                        <div class="history-card-meta"></div>
                    </div>
                </div>
                <div class="history-card-right">
                    ${verdictHTML}
                    <button class="btn btn-outline btn-small js-view-report">
                        View Report <i class="fa-solid fa-arrow-right"></i>
                    </button>
                </div>`;

            card.querySelector('.history-card-title').textContent =
                company ? `${title} @ ${company}` : title;
            card.querySelector('.history-card-meta').textContent = date;
            card.querySelector('.js-view-report').addEventListener('click', () => openHistoryEntry(entry.id));

            listEl.appendChild(card);
        });
    } catch (err) {
        console.error('History load error:', err);
    }
}

async function openHistoryEntry(id) {
    try {
        const response = await fetch(`/api/history/${id}`);
        if (!response.ok) throw new Error('Failed to load entry');
        const data = await response.json();
        showView('analyzer');
        displayResults(data);
    } catch (err) {
        alert('Could not load this analysis: ' + err.message);
    }
}

// ─── Utility ──────────────────────────────────────────────
function _relativeTime(isoString) {
    const diff = Date.now() - new Date(isoString).getTime();
    const mins = Math.floor(diff / 60000);
    const hours = Math.floor(mins / 60);
    const days = Math.floor(hours / 24);
    if (mins < 1)  return 'Just now';
    if (mins < 60) return `${mins} minute${mins !== 1 ? 's' : ''} ago`;
    if (hours < 24) return `${hours} hour${hours !== 1 ? 's' : ''} ago`;
    return `${days} day${days !== 1 ? 's' : ''} ago`;
}

function _esc(str) {
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

// Coerce a FastAPI error `detail` into a readable string. For 422 responses
// `detail` is a list of error objects, which would otherwise render as
// "[object Object]" in the error banner.
function _errorText(detail) {
    if (!detail) return '';
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
        return detail.map(d => d?.msg || JSON.stringify(d)).join('; ');
    }
    return detail.msg || JSON.stringify(detail);
}

// ─── Init ─────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function () {
    // Drag-and-drop on upload zone
    const dropZone = document.getElementById('dropZone');
    if (dropZone) {
        dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('dragover'); });
        dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
        dropZone.addEventListener('drop', e => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
            const file = e.dataTransfer.files[0];
            if (file && file.type === 'application/pdf') {
                selectedFile = file;
                document.getElementById('fileName').textContent = file.name;
            }
        });
    }

    // Profile form submit
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

        try {
            const response = await fetch('/api/profile', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(profile),
            });
            if (response.ok) {
                const saved = await response.json();
                updateProfileUI(saved);
                // Flash success
                const btn = document.querySelector('#profileForm .btn-primary');
                const orig = btn.innerHTML;
                btn.innerHTML = '<i class="fa-solid fa-check"></i> Saved!';
                setTimeout(() => { btn.innerHTML = orig; }, 2000);
            }
        } catch (err) {
            console.error('Profile save failed:', err);
        }
    });

    // Load profile on startup
    (async function loadProfile() {
        try {
            const response = await fetch('/api/profile');
            if (response.ok) {
                const profileData = await response.json();
                updateProfileUI(profileData);
            }
        } catch (_) {
            // No profile yet — that's fine
        }
    })();
});
