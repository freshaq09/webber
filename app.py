import os
import logging
import json
import re
import time
from urllib.parse import urlparse, urljoin
import zipfile
import io
import uuid
from pathlib import Path
import threading
import queue

import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, jsonify, send_file, session
from flask_socketio import SocketIO, emit

from crawler import WebCrawler

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "default_secret_key")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Create a directory for temporary storage if it doesn't exist
temp_dir = Path("temp")
temp_dir.mkdir(exist_ok=True)

# Store active crawling tasks
active_tasks = {}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/crawl', methods=['POST'])
def crawl():
    """Start a website crawling process."""
    url = request.form.get('url')
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    
    # Validate URL
    if not re.match(r'^https?://', url):
        url = 'http://' + url
    
    try:
        parsed_url = urlparse(url)
        if not parsed_url.netloc:
            return jsonify({"error": "Invalid URL"}), 400
    except Exception as e:
        logger.error(f"URL parsing error: {e}")
        return jsonify({"error": f"Invalid URL: {str(e)}"}), 400
    
    # Generate a task ID
    task_id = str(uuid.uuid4())
    session['task_id'] = task_id
    
    # Initialize crawler with faster throttle
    crawler = WebCrawler(url, task_id, socketio, throttle_delay=0.01)
    active_tasks[task_id] = {
        "crawler": crawler,
        "status": "starting",
        "start_time": time.time(),
        "url": url
    }
    
    # Start crawling in a separate thread
    thread = threading.Thread(target=crawler.start_crawling)
    thread.daemon = True
    thread.start()
    
    return jsonify({"task_id": task_id, "status": "started"})

@app.route('/status/<task_id>')
def status(task_id):
    """Get the status of a crawling task."""
    if task_id not in active_tasks:
        return jsonify({"error": "Task not found"}), 404
    
    task = active_tasks[task_id]
    
    # If task has been running for over 30 seconds, mark it as completed
    # so the download can be attempted
    if time.time() - task["start_time"] > 30 and task["status"] != "failed":
        task["status"] = "completed"
        
    return jsonify({
        "status": task["status"],
        "url": task["url"],
        "duration": time.time() - task["start_time"],
        "crawled_urls": task["crawler"].get_stats()
    })

@app.route('/download/<task_id>')
def download(task_id):
    """Download the ZIP file for a completed task."""
    if task_id not in active_tasks:
        return jsonify({"error": "Task not found"}), 404
    
    task = active_tasks[task_id]
    if task["status"] != "completed":
        return jsonify({"error": "Task not yet completed"}), 400
    
    try:
        zip_path = task["crawler"].get_zip_path()
        if not zip_path or not os.path.exists(zip_path):
            return jsonify({"error": "ZIP file not found"}), 404
        
        filename = os.path.basename(zip_path)
        return send_file(zip_path, download_name=filename, as_attachment=True)
    except Exception as e:
        logger.error(f"Download error: {e}")
        return jsonify({"error": f"Error downloading ZIP: {str(e)}"}), 500

@app.route('/preview/<task_id>')
def preview(task_id):
    """Show a preview of crawled content."""
    if task_id not in active_tasks:
        return jsonify({"error": "Task not found"}), 404
    
    task = active_tasks[task_id]
    if task["status"] not in ["completed", "processing"]:
        return jsonify({"error": "No content available for preview"}), 400
    
    try:
        preview_data = task["crawler"].get_preview_data()
        return jsonify(preview_data)
    except Exception as e:
        logger.error(f"Preview error: {e}")
        return jsonify({"error": f"Error generating preview: {str(e)}"}), 500

@app.route('/cleanup/<task_id>', methods=['POST'])
def cleanup(task_id):
    """Clean up completed task data."""
    if task_id not in active_tasks:
        return jsonify({"error": "Task not found"}), 404
    
    try:
        # Clean up task files
        task = active_tasks[task_id]
        if "crawler" in task:
            task["crawler"].cleanup()
        
        # Remove from active tasks
        del active_tasks[task_id]
        return jsonify({"status": "cleaned"})
    except Exception as e:
        logger.error(f"Cleanup error: {e}")
        return jsonify({"error": f"Error during cleanup: {str(e)}"}), 500

@socketio.on('connect')
def handle_connect():
    logger.info('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    logger.info('Client disconnected')

@app.errorhandler(404)
def page_not_found(e):
    return render_template('index.html'), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Server error occurred"}), 500
