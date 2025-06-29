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
import secrets
from functools import wraps

import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, jsonify, send_file, session, redirect, url_for, flash, make_response
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit

from models import db, User, ApiKey
from crawler import WebCrawler

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "default_secret_key")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///app.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,
    "pool_recycle": 300,
}

# Initialize extensions
db.init_app(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'

# Create database tables
with app.app_context():
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# API key decorator for API routes
def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Get the API key from header or query string
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        
        if not api_key:
            return jsonify({"error": "API key is required"}), 401
            
        # Find the key in the database
        key_record = ApiKey.query.filter_by(key=api_key).first()
        if not key_record:
            return jsonify({"error": "Invalid API key"}), 401
            
        # Update last used timestamp
        key_record.mark_used()
        
        # Add the user to the request context
        request.user = key_record.user
        return f(*args, **kwargs)
    return decorated_function

# Create a directory for temporary storage if it doesn't exist
temp_dir = Path("temp")
temp_dir.mkdir(exist_ok=True)

# Store active crawling tasks
active_tasks = {}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/direct_download')
def direct_download():
    """Provide direct download of the latest ZIP file."""
    try:
        # Find the most recent zip file in the root directory
        zip_files = [f for f in os.listdir('.') if f.endswith('.zip')]
        if not zip_files:
            return jsonify({"error": "No ZIP files available"}), 404
        
        # Sort by modification time, newest first
        zip_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        latest_zip = zip_files[0]
        
        return send_file(latest_zip, as_attachment=True)
    except Exception as e:
        logger.error(f"Direct download error: {e}")
        return jsonify({"error": f"Error providing direct download: {str(e)}"}), 500

@app.route('/fast_wget', methods=['POST'])
def fast_wget():
    """
    Direct wget crawl route that immediately returns the ZIP file.
    This is a synchronous endpoint that will block until the download is complete.
    """
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
    
    try:
        # Import and use the fast_wget module
        from fast_wget import crawl_with_wget_sync
        
        # Show a message to the user
        logger.info(f"Starting fast wget download for {url}")
        
        # Call the wget function (this will block until download is complete)
        logger.debug(f"Calling crawl_with_wget_sync({url})")
        zip_path = crawl_with_wget_sync(url)
        logger.debug(f"crawl_with_wget_sync returned zip_path: {zip_path}")
        
        if not zip_path:
            logger.error("crawl_with_wget_sync returned None")
            return jsonify({"error": "Failed to download website with wget. The website might be unavailable, blocked, or have certificate issues. Please try a different website."}), 500
            
        if not os.path.exists(zip_path):
            logger.error(f"Generated ZIP file does not exist at path: {zip_path}")
            return jsonify({"error": f"Failed to download website with wget. ZIP file not found at {zip_path}."}), 500
        
        # Log success
        logger.info(f"Successfully downloaded website. ZIP file at: {zip_path}")
        
        # Return the ZIP file directly
        return send_file(zip_path, as_attachment=True, download_name=os.path.basename(zip_path))
    
    except Exception as e:
        # Log the error with full traceback
        import traceback
        logger.error(f"Fast wget error: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({"error": f"Error downloading with wget: {str(e)}"}), 500

@app.route('/scraper')
def scraper():
    return render_template('web_scraper.html')

@app.route('/scrape', methods=['POST'])
def scrape():
    url = request.form.get('url')
    if not url:
        return render_template('web_scraper.html', error="Please enter a URL")
    
    try:
        # Import web_scraper here to avoid circular imports
        from web_scraper import get_website_text_content
        
        # Extract content using the web_scraper module
        content = get_website_text_content(url)
        
        if not content:
            return render_template('web_scraper.html', 
                                  error="No main content could be extracted from this URL. The page might be empty, protected, or not accessible.",
                                  url=url)
        
        return render_template('web_scraper.html', content=content, url=url)
    
    except Exception as e:
        logger.error(f"Error extracting content: {str(e)}")
        return render_template('web_scraper.html', 
                              error=f"Error extracting content: {str(e)}",
                              url=url)

@app.route('/download_text', methods=['POST'])
def download_text():
    url = request.form.get('url', '')
    content = request.form.get('content', '')
    
    if not content:
        return render_template('web_scraper.html', error="No content to download")
    
    # Generate filename from URL
    filename = url.replace('https://', '').replace('http://', '')
    filename = filename.replace('/', '_').replace('.', '_')
    filename = f"{filename}_{int(time.time())}.txt"
    
    # Create text file in memory
    text_file = io.StringIO()
    text_file.write(f"Source URL: {url}\n\n")
    text_file.write(content)
    text_file.seek(0)
    
    # Create response with file
    response = make_response(text_file.getvalue())
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    response.headers["Content-Type"] = "text/plain"
    
    return response

@app.route('/crawl', methods=['POST'])
def crawl():
    """Start a website crawling process."""
    url = request.form.get('url')
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    
    # Check if wget mode is selected
    use_wget = request.form.get('use_wget') == 'true'
    
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
    
    if use_wget:
        # Create a thread to run wget crawling
        def wget_crawler():
            try:
                # Send initial status
                logger.info(f"Starting wget crawling for {url}")
                socketio.emit('status_update', {
                    'task_id': task_id,
                    'message': f"Starting wget download for {url}",
                    'progress': 10,
                    'stats': {'resources': {'html': 0, 'css': 0, 'js': 0, 'images': 0, 'fonts': 0, 'other': 0}}
                })
                
                # Prepare task directory
                task_dir = temp_dir / task_id
                
                # Use our simplified_wget module
                from simplified_wget import crawl_with_wget
                
                # Send status update
                socketio.emit('status_update', {
                    'task_id': task_id,
                    'message': f"Downloading website with wget...",
                    'progress': 30,
                    'stats': {'resources': {'html': 0, 'css': 0, 'js': 0, 'images': 0, 'fonts': 0, 'other': 0}}
                })
                
                # Start crawling
                result = crawl_with_wget(url, task_id, task_dir)
                
                if result["status"] == "completed":
                    # Store task completion info
                    active_tasks[task_id] = {
                        "status": "completed",
                        "start_time": time.time(),
                        "url": url,
                        "zip_path": result["zip_path"],
                        "files_downloaded": result["files_downloaded"],
                        "resources": result["resources"],
                        "wget_mode": True
                    }
                    
                    # Emit completion status
                    socketio.emit('status_update', {
                        'task_id': task_id,
                        'message': f"Crawling completed! Downloaded {result['files_downloaded']} files.",
                        'progress': 100,
                        'stats': {'resources': result["resources"]}
                    })
                    
                    logger.info(f"Wget crawling completed for {url}")
                else:
                    # Handle error
                    active_tasks[task_id] = {
                        "status": "failed",
                        "start_time": time.time(),
                        "url": url,
                        "error": result.get("error", "Unknown error"),
                        "wget_mode": True
                    }
                    
                    socketio.emit('status_update', {
                        'task_id': task_id,
                        'message': f"Error: {result.get('error', 'Unknown error')}",
                        'progress': -1
                    })
                    
                    logger.error(f"Wget crawling failed for {url}: {result.get('error', 'Unknown error')}")
                
            except Exception as e:
                logger.error(f"Error in wget crawling: {str(e)}")
                active_tasks[task_id] = {
                    "status": "failed",
                    "start_time": time.time(),
                    "url": url,
                    "error": str(e),
                    "wget_mode": True
                }
                socketio.emit('status_update', {
                    'task_id': task_id,
                    'message': f"Error: {str(e)}",
                    'progress': -1
                })
        
        # Start wget crawling in a thread
        active_tasks[task_id] = {
            "status": "starting",
            "start_time": time.time(),
            "url": url,
            "wget_mode": True
        }
        thread = threading.Thread(target=wget_crawler)
        thread.daemon = True
        thread.start()
    else:
        # Initialize crawler with faster throttle using the original Python method
        crawler = WebCrawler(url, task_id, socketio, throttle_delay=0.01)
        active_tasks[task_id] = {
            "crawler": crawler,
            "status": "starting",
            "start_time": time.time(),
            "url": url,
            "wget_mode": False
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
    # so the download can be attempted (for non-wget tasks only)
    if not task.get("wget_mode", False) and time.time() - task["start_time"] > 30 and task["status"] != "failed":
        task["status"] = "completed"
    
    # Handle wget vs non-wget tasks differently
    if task.get("wget_mode", False):
        # For wget mode tasks
        stats = {
            "processed_urls": task.get("files_downloaded", 0),
            "total_urls": task.get("files_downloaded", 0) + 10,  # Add buffer for incomplete downloads
            "resources": task.get("resources", {
                "html": 0, "css": 0, "js": 0, "images": 0, "fonts": 0, "other": 0
            })
        }
        
        return jsonify({
            "status": task["status"],
            "url": task["url"],
            "duration": time.time() - task["start_time"],
            "crawled_urls": stats
        })
    else:
        # For original Python crawler tasks
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
        # Handle wget vs non-wget tasks differently
        if task.get("wget_mode", False):
            # For wget mode tasks
            zip_path = task.get("zip_path")
            if not zip_path or not os.path.exists(zip_path):
                return jsonify({"error": "ZIP file not found"}), 404
            
            filename = os.path.basename(zip_path)
            return send_file(zip_path, download_name=filename, as_attachment=True)
        else:
            # For original Python crawler tasks
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
        # Handle wget vs non-wget tasks differently
        if task.get("wget_mode", False):
            # For wget mode tasks, create a basic preview
            task_dir = temp_dir / task_id
            
            # Find HTML files for preview
            pages = []
            total_files = 0
            
            # Handle different directory structures
            domain_dir = task_dir / urlparse(task["url"]).netloc
            search_dir = domain_dir if domain_dir.exists() else task_dir
            
            # Walk through the directory and count files
            for root, _, files in os.walk(search_dir):
                total_files += len(files)
                
                # Only include HTML files in the preview
                for file in files:
                    if file.endswith('.html') or file.endswith('.htm'):
                        file_path = os.path.join(root, file)
                        rel_path = os.path.relpath(file_path, search_dir)
                        
                        # Try to extract title
                        title = rel_path
                        try:
                            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                                content = f.read()
                                soup = BeautifulSoup(content, 'html.parser')
                                title_tag = soup.find('title')
                                if title_tag and title_tag.text:
                                    title = title_tag.text.strip()
                        except Exception:
                            pass  # Just use the filename if we can't extract title
                        
                        pages.append({
                            'title': title,
                            'path': rel_path
                        })
                        
                        # Limit to 20 pages for preview
                        if len(pages) >= 20:
                            break
            
            preview_data = {
                'pages': pages,
                'total_files': total_files
            }
            return jsonify(preview_data)
        else:
            # For original Python crawler tasks
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
        
        # Different cleanup for wget vs non-wget tasks
        if task.get("wget_mode", False):
            # For wget mode tasks, just remove the task directory
            task_dir = temp_dir / task_id
            if task_dir.exists():
                import shutil
                shutil.rmtree(task_dir, ignore_errors=True)
        elif "crawler" in task:
            # For original Python crawler tasks
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

# Authentication routes
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        name = request.form.get('name')
        
        # Validate input
        if not email or not password or not name:
            flash('All fields are required', 'danger')
            return render_template('register.html')
        
        try:
            # Check if user already exists
            existing_user = User.query.filter_by(email=email).first()
            if existing_user:
                flash('Email already registered', 'danger')
                return render_template('register.html')
            
            # Create new user
            user = User(email=email, name=name)
            user.set_password(password)
            
            # Add to database
            db.session.add(user)
            db.session.commit()
            
            # Generate initial API key
            api_key = ApiKey(
                user_id=user.id,
                key=secrets.token_urlsafe(32),
                name="Default Key"
            )
            db.session.add(api_key)
            db.session.commit()
            
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Registration error: {str(e)}")
            flash(f'Error during registration. Please try again later.', 'danger')
            return render_template('register.html')
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        # Validate input
        if not email or not password:
            flash('Email and password are required', 'danger')
            return render_template('login.html')
        
        # Find user
        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            flash('Invalid email or password', 'danger')
            return render_template('login.html')
        
        # Log in user
        login_user(user)
        next_page = request.args.get('next', url_for('dashboard'))
        return redirect(next_page)
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    """User dashboard for managing API keys"""
    api_keys = current_user.api_keys
    return render_template('dashboard.html', api_keys=api_keys)

@app.route('/api_keys/create', methods=['POST'])
@login_required
def create_api_key():
    """Create a new API key for the current user"""
    name = request.form.get('name', 'New Key')
    api_key = current_user.generate_api_key(name)
    flash(f'API key "{name}" created successfully', 'success')
    return redirect(url_for('dashboard'))

@app.route('/api_keys/delete/<int:key_id>', methods=['POST'])
@login_required
def delete_api_key(key_id):
    """Delete an API key"""
    api_key = ApiKey.query.get_or_404(key_id)
    
    # Ensure the key belongs to the current user
    if api_key.user_id != current_user.id:
        flash('Access denied', 'danger')
        return redirect(url_for('dashboard'))
    
    key_name = api_key.name
    db.session.delete(api_key)
    db.session.commit()
    
    flash(f'API key "{key_name}" deleted successfully', 'success')
    return redirect(url_for('dashboard'))

# API documentation
@app.route('/api/docs')
def api_docs():
    """API documentation page"""
    return render_template('api_docs.html')

# API endpoints
@app.route('/api/v1/fast_wget', methods=['POST'])
@require_api_key
def api_fast_wget():
    """API endpoint for fast wget download"""
    url = request.json.get('url')
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
    
    try:
        # Import and use the fast_wget module
        from fast_wget import crawl_with_wget_sync
        
        # Show a message to the user
        logger.info(f"API: Starting fast wget download for {url}")
        
        # Call the wget function (this will block until download is complete)
        logger.debug(f"API: Calling crawl_with_wget_sync({url})")
        zip_path = crawl_with_wget_sync(url)
        logger.debug(f"API: crawl_with_wget_sync returned zip_path: {zip_path}")
        
        if not zip_path:
            logger.error("API: crawl_with_wget_sync returned None")
            return jsonify({"error": "Failed to download website with wget. The website might be unavailable, blocked, or have certificate issues. Please try a different website."}), 500
            
        if not os.path.exists(zip_path):
            logger.error(f"API: Generated ZIP file does not exist at path: {zip_path}")
            return jsonify({"error": f"Failed to download website with wget. ZIP file not found at {zip_path}."}), 500
        
        # Log success
        logger.info(f"API: Successfully downloaded website. ZIP file at: {zip_path}")
        
        # Return the ZIP file directly
        return send_file(zip_path, as_attachment=True, download_name=os.path.basename(zip_path))
    
    except Exception as e:
        # Log the error with full traceback
        import traceback
        logger.error(f"API fast wget error: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({"error": f"Error downloading with wget: {str(e)}"}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5050))
    socketio.run(app, debug=True, host='0.0.0.0', port=port)
