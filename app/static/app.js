// Whisper Transcriber Web UI

const API_BASE = '';

// State
let selectedFiles = [];
let ws = null;

// DOM Elements
const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const selectedFilesContainer = document.getElementById('selected-files');
const transcribeBtn = document.getElementById('transcribe-btn');
const modelSelect = document.getElementById('model-select');
const languageSelect = document.getElementById('language-select');
const jobQueue = document.getElementById('job-queue');
const themeToggle = document.getElementById('theme-toggle');
const watcherToggle = document.getElementById('watcher-toggle');
const watcherStatus = document.getElementById('watcher-status');
const watchPath = document.getElementById('watch-path');
const deviceInfo = document.getElementById('device-info');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    initDropZone();
    initWebSocket();
    loadDeviceInfo();
    loadWatcherStatus();
    pollJobs();
});

// Theme
function initTheme() {
    const saved = localStorage.getItem('theme');
    if (saved) {
        document.documentElement.setAttribute('data-theme', saved);
    } else if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
        document.documentElement.setAttribute('data-theme', 'dark');
    }

    themeToggle.addEventListener('click', () => {
        const current = document.documentElement.getAttribute('data-theme');
        const next = current === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', next);
        localStorage.setItem('theme', next);
    });
}

// Drop Zone
function initDropZone() {
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(event => {
        dropZone.addEventListener(event, e => {
            e.preventDefault();
            e.stopPropagation();
        });
    });

    ['dragenter', 'dragover'].forEach(event => {
        dropZone.addEventListener(event, () => dropZone.classList.add('dragover'));
    });

    ['dragleave', 'drop'].forEach(event => {
        dropZone.addEventListener(event, () => dropZone.classList.remove('dragover'));
    });

    dropZone.addEventListener('drop', e => {
        const files = Array.from(e.dataTransfer.files);
        addFiles(files);
    });

    fileInput.addEventListener('change', e => {
        const files = Array.from(e.target.files);
        addFiles(files);
        fileInput.value = '';
    });

    transcribeBtn.addEventListener('click', startTranscription);
}

function addFiles(files) {
    const audioFiles = files.filter(f => isAudioFile(f.name));
    selectedFiles = [...selectedFiles, ...audioFiles];
    renderSelectedFiles();
    updateTranscribeButton();
}

function removeFile(index) {
    selectedFiles.splice(index, 1);
    renderSelectedFiles();
    updateTranscribeButton();
}

function isAudioFile(filename) {
    const ext = filename.split('.').pop().toLowerCase();
    return ['mp3', 'wav', 'm4a', 'flac', 'ogg', 'wma', 'aac', 'mp4', 'webm'].includes(ext);
}

function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function renderSelectedFiles() {
    if (selectedFiles.length === 0) {
        selectedFilesContainer.innerHTML = '';
        return;
    }

    selectedFilesContainer.innerHTML = selectedFiles.map((file, index) => `
        <div class="selected-file">
            <span class="filename">${escapeHtml(file.name)}</span>
            <span class="size">${formatFileSize(file.size)}</span>
            <button class="remove-btn" onclick="removeFile(${index})">&times;</button>
        </div>
    `).join('');
}

function updateTranscribeButton() {
    transcribeBtn.disabled = selectedFiles.length === 0;
}

// Transcription
async function startTranscription() {
    if (selectedFiles.length === 0) return;

    const model = modelSelect.value;
    const language = languageSelect.value;
    const formats = Array.from(document.querySelectorAll('input[name="format"]:checked'))
        .map(cb => cb.value)
        .join(',');

    transcribeBtn.disabled = true;
    transcribeBtn.textContent = 'Uploading...';

    try {
        for (const file of selectedFiles) {
            const formData = new FormData();
            formData.append('file', file);

            const params = new URLSearchParams({
                model,
                output_formats: formats
            });
            if (language) {
                params.append('language', language);
            }

            const response = await fetch(`${API_BASE}/api/transcribe?${params}`, {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                throw new Error(`Upload failed: ${response.statusText}`);
            }
        }

        selectedFiles = [];
        renderSelectedFiles();
        refreshJobs();
    } catch (error) {
        console.error('Transcription error:', error);
        alert('Error: ' + error.message);
    } finally {
        transcribeBtn.disabled = false;
        transcribeBtn.textContent = 'Start Transcription';
        updateTranscribeButton();
    }
}

// Jobs
async function refreshJobs() {
    try {
        const response = await fetch(`${API_BASE}/api/jobs`);
        const data = await response.json();
        renderJobs(data.jobs);
    } catch (error) {
        console.error('Error fetching jobs:', error);
    }
}

function pollJobs() {
    refreshJobs();
    setInterval(refreshJobs, 1000);  // Poll every second for smoother progress updates
}

// Track simulated progress for jobs
const simulatedProgress = {};

function renderJobs(jobs) {
    if (!jobs || jobs.length === 0) {
        jobQueue.innerHTML = '<p class="empty-state">No transcription jobs yet</p>';
        return;
    }

    // Sort by created_at descending
    jobs.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));

    jobQueue.innerHTML = jobs.map(job => {
        const icon = getStatusIcon(job.status);

        // Simulate gradual progress for processing jobs
        let displayProgress = job.progress;
        if (job.status === 'processing') {
            if (!simulatedProgress[job.id]) {
                simulatedProgress[job.id] = { value: 0.05, startTime: Date.now() };
            }
            const sim = simulatedProgress[job.id];
            const elapsed = (Date.now() - sim.startTime) / 1000;
            // Slowly increase to ~90% over time (asymptotic approach)
            sim.value = Math.min(0.9, 0.05 + (0.85 * (1 - Math.exp(-elapsed / 60))));
            displayProgress = Math.max(job.progress, sim.value);
        } else {
            delete simulatedProgress[job.id];
            if (job.status === 'completed') displayProgress = 1;
        }

        const progress = job.status === 'processing' ? `
            <div class="job-progress">
                <div class="progress-bar">
                    <div class="progress-fill" style="width: ${displayProgress * 100}%"></div>
                </div>
                <div class="progress-text">${Math.round(displayProgress * 100)}%</div>
            </div>
        ` : '';

        const actions = job.status === 'completed' ? `
            <div class="job-actions">
                ${job.output_formats.map(fmt => `
                    <button class="download-btn" onclick="downloadResult('${job.id}', '${fmt}')">${fmt.toUpperCase()}</button>
                `).join('')}
            </div>
        ` : job.status === 'failed' ? `
            <div class="job-actions">
                <button class="delete-btn" onclick="deleteJob('${job.id}')">Delete</button>
            </div>
        ` : '';

        return `
            <div class="job-item">
                <div class="job-icon ${job.status}">${icon}</div>
                <div class="job-info">
                    <div class="job-filename">${escapeHtml(job.filename)}</div>
                    <div class="job-status">${job.message || job.status}</div>
                </div>
                ${progress}
                ${actions}
            </div>
        `;
    }).join('');
}

function getStatusIcon(status) {
    switch (status) {
        case 'completed': return '&#10003;';
        case 'processing': return '&#8635;';
        case 'pending': return '&#9675;';
        case 'failed': return '&#10007;';
        default: return '&#8226;';
    }
}

async function downloadResult(jobId, format) {
    window.open(`${API_BASE}/api/jobs/${jobId}/download/${format}`, '_blank');
}

async function deleteJob(jobId) {
    try {
        await fetch(`${API_BASE}/api/jobs/${jobId}`, { method: 'DELETE' });
        refreshJobs();
    } catch (error) {
        console.error('Error deleting job:', error);
    }
}

// WebSocket
function initWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

    ws.onmessage = (event) => {
        const job = JSON.parse(event.data);
        updateJobInQueue(job);
    };

    ws.onclose = () => {
        setTimeout(initWebSocket, 3000);
    };

    ws.onerror = () => {
        ws.close();
    };
}

function updateJobInQueue(job) {
    // Refresh the full list for simplicity
    refreshJobs();
}

// Watcher
async function loadWatcherStatus() {
    try {
        const response = await fetch(`${API_BASE}/api/watch/status`);
        const data = await response.json();
        updateWatcherUI(data.active, data.path);
    } catch (error) {
        console.error('Error loading watcher status:', error);
    }
}

function updateWatcherUI(active, path) {
    if (active) {
        watcherStatus.textContent = 'ON';
        watcherStatus.classList.remove('off');
        watcherStatus.classList.add('on');
        watcherToggle.textContent = 'Disable';
    } else {
        watcherStatus.textContent = 'OFF';
        watcherStatus.classList.remove('on');
        watcherStatus.classList.add('off');
        watcherToggle.textContent = 'Enable';
    }
    if (path) {
        watchPath.textContent = path;
    }
}

watcherToggle.addEventListener('click', async () => {
    const isOn = watcherStatus.classList.contains('on');
    const endpoint = isOn ? '/api/watch/stop' : '/api/watch/start';

    try {
        const response = await fetch(`${API_BASE}${endpoint}`, { method: 'POST' });
        const data = await response.json();
        updateWatcherUI(!isOn, data.path);
    } catch (error) {
        console.error('Error toggling watcher:', error);
    }
});

// Device Info
async function loadDeviceInfo() {
    try {
        const response = await fetch(`${API_BASE}/api/device`);
        const data = await response.json();
        deviceInfo.textContent = `Device: ${data.device.toUpperCase()}`;
    } catch (error) {
        console.error('Error loading device info:', error);
    }
}

// Utils
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
