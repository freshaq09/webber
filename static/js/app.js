// Web Crawler Application JavaScript

// Global state
let currentTaskId = null;
let statusCheckInterval = null;
let socket = null;

// DOM elements
const urlForm = document.getElementById('urlForm');
const urlInput = document.getElementById('urlInput');
const crawlButton = document.getElementById('crawlButton');
const statusSection = document.getElementById('statusSection');
const progressBar = document.getElementById('crawlingProgress');
const statusMessage = document.getElementById('statusMessage');
const downloadSection = document.getElementById('downloadSection');
const downloadButton = document.getElementById('downloadButton');
const previewSection = document.getElementById('previewSection');
const previewContent = document.getElementById('previewContent');
const statsHtml = document.getElementById('statsHtml');
const statsCss = document.getElementById('statsCss');
const statsJs = document.getElementById('statsJs');
const statsImages = document.getElementById('statsImages');
const statsFonts = document.getElementById('statsFonts');
const statsOther = document.getElementById('statsOther');
const previewButton = document.getElementById('previewButton');
const initialSection = document.getElementById('initialSection');

// Initialize socket.io connection
function initializeSocket() {
    socket = io.connect(window.location.origin, {
        transports: ['polling', 'websocket'],
        reconnectionAttempts: 5,
        reconnectionDelay: 1000
    });
    
    socket.on('connect', () => {
        console.log('Connected to server');
    });
    
    socket.on('status_update', (data) => {
        console.log('Status update received:', data);
        if (data.task_id === currentTaskId) {
            updateProgress(data.message, data.progress, data.stats);
        }
    });
    
    socket.on('connect_error', (error) => {
        console.error('Connection error:', error);
        // Fallback to polling if socket connection fails
        if (currentTaskId) {
            startStatusChecking();
        }
    });
    
    socket.on('error', (error) => {
        console.error('Socket error:', error);
    });
}

// Event listeners
document.addEventListener('DOMContentLoaded', () => {
    // Initialize socket
    initializeSocket();
    
    // Form submission handler
    urlForm.addEventListener('submit', handleFormSubmit);
    
    // Download button handler
    downloadButton.addEventListener('click', handleDownload);
    
    // Preview button handler
    previewButton.addEventListener('click', handlePreview);
});

// Form submission handler
async function handleFormSubmit(event) {
    event.preventDefault();
    
    const url = urlInput.value.trim();
    if (!url) {
        showError('Please enter a valid URL');
        return;
    }
    
    // Reset UI state
    resetUI();
    
    // Show loading state
    crawlButton.disabled = true;
    crawlButton.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Starting...';
    
    try {
        const response = await fetch('/crawl', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: `url=${encodeURIComponent(url)}`
        });
        
        const data = await response.json();
        
        if (response.ok) {
            // Save the task ID
            currentTaskId = data.task_id;
            
            // Update UI to show progress section
            initialSection.classList.add('hidden');
            statusSection.classList.remove('hidden');
            
            // If socket is connected, we'll get updates through it
            // Otherwise, fall back to polling
            if (!socket.connected) {
                startStatusChecking();
            }
            
            // Update button state
            crawlButton.innerHTML = 'Crawling...';
        } else {
            showError(data.error || 'Failed to start crawling');
            crawlButton.disabled = false;
            crawlButton.innerHTML = 'Crawl Website';
        }
    } catch (error) {
        console.error('Error starting crawler:', error);
        showError('Server error. Please try again.');
        crawlButton.disabled = false;
        crawlButton.innerHTML = 'Crawl Website';
    }
}

// Start polling for status updates
function startStatusChecking() {
    // Clear any existing interval
    if (statusCheckInterval) {
        clearInterval(statusCheckInterval);
    }
    
    // Set up new interval
    statusCheckInterval = setInterval(checkStatus, 2000);
}

// Check task status via API
async function checkStatus() {
    if (!currentTaskId) return;
    
    try {
        const response = await fetch(`/status/${currentTaskId}`);
        const data = await response.json();
        
        if (response.ok) {
            // Calculate progress percentage
            let progress = Math.min(
                Math.floor((data.crawled_urls.processed_urls / Math.max(1, data.crawled_urls.total_urls)) * 100),
                99
            );
            
            // Update progress
            updateProgress(`Processing ${data.crawled_urls.processed_urls} of ${data.crawled_urls.total_urls} URLs...`, progress, data.crawled_urls);
            
            // Check if task is completed
            if (data.status === 'completed') {
                updateProgress('Crawling completed!', 100, data.crawled_urls);
                showDownloadSection();
                clearInterval(statusCheckInterval);
            }
        } else {
            console.error('Error checking status:', data.error);
        }
    } catch (error) {
        console.error('Error checking status:', error);
    }
}

// Update progress UI
function updateProgress(message, progress, stats) {
    // Update progress bar
    if (progress >= 0) {
        progressBar.style.width = `${progress}%`;
        progressBar.setAttribute('aria-valuenow', progress);
        
        // Show download section when complete
        if (progress === 100) {
            showDownloadSection();
            if (statusCheckInterval) {
                clearInterval(statusCheckInterval);
            }
        }
    }
    
    // Update status message
    if (message) {
        const messageItem = document.createElement('div');
        messageItem.className = 'message-item';
        messageItem.textContent = message;
        statusMessage.appendChild(messageItem);
        statusMessage.scrollTop = statusMessage.scrollHeight;
    }
    
    // Update statistics if available
    if (stats && stats.resources) {
        updateStats(stats.resources);
    }
}

// Update resource statistics
function updateStats(resources) {
    statsHtml.textContent = resources.html || 0;
    statsCss.textContent = resources.css || 0;
    statsJs.textContent = resources.js || 0;
    statsImages.textContent = resources.images || 0;
    statsFonts.textContent = resources.fonts || 0;
    statsOther.textContent = resources.other || 0;
}

// Show download section
function showDownloadSection() {
    downloadSection.classList.remove('hidden');
    previewButton.classList.remove('hidden');
    crawlButton.disabled = false;
    crawlButton.innerHTML = 'Crawl Another Website';
}

// Handle download button click
function handleDownload() {
    if (!currentTaskId) return;
    
    const downloadUrl = `/download/${currentTaskId}`;
    window.location.href = downloadUrl;
    
    // After download, schedule cleanup
    setTimeout(() => {
        fetch(`/cleanup/${currentTaskId}`, { method: 'POST' })
            .then(response => response.json())
            .then(data => console.log('Cleanup response:', data))
            .catch(error => console.error('Error during cleanup:', error));
    }, 5000);
}

// Handle preview button click
async function handlePreview() {
    if (!currentTaskId) return;
    
    try {
        previewButton.disabled = true;
        previewButton.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Loading preview...';
        
        const response = await fetch(`/preview/${currentTaskId}`);
        const data = await response.json();
        
        if (response.ok) {
            // Show preview section
            previewSection.classList.remove('hidden');
            
            // Create preview content
            let previewHtml = '<h4>Crawled Pages</h4>';
            previewHtml += '<div class="list-group">';
            
            if (data.pages && data.pages.length > 0) {
                data.pages.forEach(page => {
                    previewHtml += `<div class="list-group-item">
                        <h5 class="mb-1">${page.title}</h5>
                        <p class="mb-1">${page.path}</p>
                    </div>`;
                });
            } else {
                previewHtml += '<div class="list-group-item">No pages available for preview</div>';
            }
            
            previewHtml += '</div>';
            previewHtml += `<div class="mt-3">
                <p>Total files: <strong>${data.total_files}</strong></p>
            </div>`;
            
            previewContent.innerHTML = previewHtml;
        } else {
            showError(data.error || 'Failed to load preview');
        }
        
        previewButton.disabled = false;
        previewButton.innerHTML = 'Show Preview';
    } catch (error) {
        console.error('Error loading preview:', error);
        showError('Server error. Please try again.');
        previewButton.disabled = false;
        previewButton.innerHTML = 'Show Preview';
    }
}

// Show error message
function showError(message) {
    const errorAlert = document.createElement('div');
    errorAlert.className = 'alert alert-danger alert-dismissible fade show';
    errorAlert.role = 'alert';
    errorAlert.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;
    
    const container = document.querySelector('.container');
    container.insertBefore(errorAlert, container.firstChild);
    
    // Auto-dismiss after 5 seconds
    setTimeout(() => {
        errorAlert.classList.add('fade');
        setTimeout(() => errorAlert.remove(), 500);
    }, 5000);
}

// Reset UI state
function resetUI() {
    // Reset task ID
    currentTaskId = null;
    
    // Clear status check interval
    if (statusCheckInterval) {
        clearInterval(statusCheckInterval);
        statusCheckInterval = null;
    }
    
    // Reset progress bar
    progressBar.style.width = '0%';
    progressBar.setAttribute('aria-valuenow', 0);
    
    // Clear status messages
    statusMessage.innerHTML = '';
    
    // Hide download and preview sections
    downloadSection.classList.add('hidden');
    previewSection.classList.add('hidden');
    previewButton.classList.add('hidden');
    
    // Clear preview content
    previewContent.innerHTML = '';
    
    // Reset statistics
    updateStats({
        html: 0,
        css: 0,
        js: 0,
        images: 0,
        fonts: 0,
        other: 0
    });
}
