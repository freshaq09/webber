import os
import re
import time
import uuid
import logging
import zipfile
import shutil
from pathlib import Path
from urllib.parse import urlparse, urljoin, urldefrag
from collections import deque
import threading
import queue

import requests
from bs4 import BeautifulSoup
import hashlib
import random

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class WebCrawler:
    def __init__(self, start_url, task_id, socketio, throttle_delay=0.1):
        self.start_url = start_url
        self.task_id = task_id
        self.socketio = socketio
        self.throttle_delay = throttle_delay
        
        # Parse the starting URL
        self.parsed_url = urlparse(start_url)
        self.base_domain = self.parsed_url.netloc
        self.base_url = f"{self.parsed_url.scheme}://{self.base_domain}"
        
        # Create task directory
        self.task_dir = Path(f"temp/{self.task_id}")
        self.task_dir.mkdir(parents=True, exist_ok=True)
        
        # Set up tracking variables
        self.visited_urls = set()
        self.queue = deque()
        self.processed_count = 0
        self.failed_urls = []
        self.file_count = 0
        self.zip_path = None
        self.status = "initialized"
        
        # Set up tracking for downloaded resource types
        self.resources = {
            "html": 0,
            "css": 0,
            "js": 0,
            "images": 0,
            "fonts": 0,
            "other": 0
        }
        
        # Stats for the frontend
        self.stats = {
            "total_urls": 0,
            "processed_urls": 0,
            "failed_urls": 0,
            "resources": self.resources
        }
        
        # Thread-safe queue for emitting status updates
        self.message_queue = queue.Queue()
        self._stop_event = threading.Event()
        
        # Session for requests
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; WebSiteToZip/1.0; +http://websitetozip.com)'
        })
    
    def start_crawling(self):
        """Start the crawling process."""
        logger.info(f"Starting crawl for {self.start_url}")
        self.status = "crawling"
        
        # Start status update thread
        status_thread = threading.Thread(target=self._status_updater)
        status_thread.daemon = True
        status_thread.start()
        
        try:
            # Add the start URL to the queue
            self.queue.append(self.start_url)
            self.stats["total_urls"] += 1
            
            # Emit initial status
            self._queue_status_update("Started crawling", 0)
            
            # Create necessary directories
            self._create_directory_structure()
            
            # Process the queue - limit to 15 URLs to ensure timely completion
            max_urls = 15
            processed_urls = 0
            
            while self.queue and not self._stop_event.is_set() and processed_urls < max_urls:
                # Get the next URL
                current_url = self.queue.popleft()
                
                # Skip if already visited
                if current_url in self.visited_urls:
                    continue
                
                # Mark as visited
                self.visited_urls.add(current_url)
                
                # Process the URL
                self._process_url(current_url)
                
                # Update progress
                self.processed_count += 1
                self.stats["processed_urls"] = self.processed_count
                processed_urls += 1
                
                # Update progress more frequently (every 2 URLs)
                if processed_urls % 2 == 0:
                    progress = min(int((processed_urls / max_urls) * 100), 99)
                    self._queue_status_update(f"Processed {processed_urls} of {max_urls} URLs", progress)
                
                # Throttle requests with shorter delay for faster completion
                time.sleep(self.throttle_delay)
            
            # Create redirects file for Netlify
            self._create_redirects_file()
            
            # Create zip file
            self._create_zip_file()
            
            # Update status to completed
            self.status = "completed"
            self._queue_status_update("Crawling completed", 100)
            
        except Exception as e:
            logger.error(f"Crawling error: {e}")
            self.status = "failed"
            self._queue_status_update(f"Error: {str(e)}", -1)
        
        # Signal the status updater to stop
        self._stop_event.set()
    
    def _status_updater(self):
        """Thread to handle emitting status updates."""
        while not self._stop_event.is_set() or not self.message_queue.empty():
            try:
                if not self.message_queue.empty():
                    message, progress = self.message_queue.get(timeout=0.1)
                    try:
                        self.socketio.emit('status_update', {
                            'task_id': self.task_id,
                            'message': message,
                            'progress': progress,
                            'stats': self.stats
                        }, namespace='/')
                    except Exception as emit_error:
                        logger.error(f"Socket emit error: {emit_error}")
                    self.message_queue.task_done()
                else:
                    time.sleep(0.1)
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Status updater error: {e}")
                time.sleep(0.5)
    
    def _queue_status_update(self, message, progress):
        """Queue a status update to be sent."""
        try:
            self.message_queue.put((message, progress))
        except Exception as e:
            logger.error(f"Error queueing status update: {e}")
    
    def _create_directory_structure(self):
        """Create necessary directory structure for the site."""
        # Create directories for assets
        (self.task_dir / "css").mkdir(exist_ok=True)
        (self.task_dir / "js").mkdir(exist_ok=True)
        (self.task_dir / "images").mkdir(exist_ok=True)
        (self.task_dir / "fonts").mkdir(exist_ok=True)
    
    def _process_url(self, url):
        """Process a single URL: download, parse, extract links."""
        logger.debug(f"Processing URL: {url}")
        self._queue_status_update(f"Processing: {url}", 
                                 int(self.processed_count / max(1, len(self.visited_urls) + len(self.queue)) * 100))
        
        try:
            # Download the content
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            
            # Determine content type
            content_type = response.headers.get('Content-Type', '').lower()
            
            # Process based on content type
            if 'text/html' in content_type:
                self._process_html(url, response.text)
            elif 'text/css' in content_type:
                self._save_css(url, response.content)
            elif 'javascript' in content_type or 'text/js' in content_type:
                self._save_javascript(url, response.content)
            elif 'image/' in content_type:
                self._save_image(url, response.content)
            elif 'font/' in content_type or '.woff' in url or '.ttf' in url:
                self._save_font(url, response.content)
            else:
                self._save_other_resource(url, response.content)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching {url}: {e}")
            self.failed_urls.append(url)
            self.stats["failed_urls"] += 1
    
    def _process_html(self, url, html_content):
        """Process HTML content, extract links, and save the file."""
        try:
            # Parse HTML
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Get relative path for this HTML file
            relative_path = self._get_relative_path(url)
            
            # Process and update links
            self._process_links(soup, url)
            
            # Save the modified HTML
            self._save_html(relative_path, str(soup))
            
            self.resources["html"] += 1
            
        except Exception as e:
            logger.error(f"Error processing HTML {url}: {e}")
            self.failed_urls.append(url)
            self.stats["failed_urls"] += 1
    
    def _process_links(self, soup, base_url):
        """Process all links in an HTML document and update them."""
        # Process <a> links
        for a_tag in soup.find_all('a', href=True):
            self._process_a_tag(a_tag, base_url)
        
        # Process <link> tags (CSS, etc.)
        for link_tag in soup.find_all('link', href=True):
            self._process_resource_link(link_tag, 'href', base_url)
        
        # Process <script> tags
        for script_tag in soup.find_all('script', src=True):
            self._process_resource_link(script_tag, 'src', base_url)
        
        # Process <img> tags
        for img_tag in soup.find_all('img', src=True):
            self._process_resource_link(img_tag, 'src', base_url)
        
        # Process <source> tags (for <picture>, <audio>, <video>)
        for source_tag in soup.find_all('source', src=True):
            self._process_resource_link(source_tag, 'src', base_url)
        
        # Process srcset attributes
        for tag in soup.find_all(srcset=True):
            self._process_srcset(tag, base_url)
        
        # Process CSS background images in style attributes
        for tag in soup.find_all(style=True):
            self._process_inline_style(tag, base_url)
    
    def _process_a_tag(self, a_tag, base_url):
        """Process an <a> tag and update its href."""
        href = a_tag['href']
        
        # Skip empty, anchor-only, and external links
        if not href or href.startswith('#') or href.startswith('javascript:'):
            return
        
        # Create absolute URL
        absolute_url = urljoin(base_url, href)
        absolute_url, _ = urldefrag(absolute_url)
        
        # Check if the URL is from the same domain
        parsed_url = urlparse(absolute_url)
        if parsed_url.netloc != self.base_domain:
            return
        
        # Add to queue if not visited
        if absolute_url not in self.visited_urls and absolute_url not in self.queue:
            self.queue.append(absolute_url)
            self.stats["total_urls"] += 1
        
        # Update href to relative path
        a_tag['href'] = self._get_relative_link_path(absolute_url)
    
    def _process_resource_link(self, tag, attr, base_url):
        """Process a resource link (CSS, JS, images) and update its attribute."""
        resource_url = tag[attr]
        
        # Skip empty, data URLs, and absolute URLs from different domains
        if not resource_url or resource_url.startswith('data:'):
            return
        
        # Create absolute URL
        absolute_url = urljoin(base_url, resource_url)
        
        # Check if the URL is from the same domain
        parsed_url = urlparse(absolute_url)
        if parsed_url.netloc and parsed_url.netloc != self.base_domain:
            return
        
        # Add to queue if not visited
        if absolute_url not in self.visited_urls and absolute_url not in self.queue:
            self.queue.append(absolute_url)
            self.stats["total_urls"] += 1
        
        # Update attribute to relative path
        tag[attr] = self._get_relative_link_path(absolute_url)
    
    def _process_srcset(self, tag, base_url):
        """Process srcset attribute in image tags."""
        srcset = tag['srcset']
        srcset_parts = srcset.split(',')
        new_srcset_parts = []
        
        for part in srcset_parts:
            # Split into URL and size descriptor
            part = part.strip()
            if not part:
                continue
                
            url_size = part.split(' ', 1)
            url = url_size[0].strip()
            size = url_size[1] if len(url_size) > 1 else ''
            
            # Process the URL
            absolute_url = urljoin(base_url, url)
            
            # Add to queue if not visited
            if absolute_url not in self.visited_urls and absolute_url not in self.queue:
                self.queue.append(absolute_url)
                self.stats["total_urls"] += 1
            
            # Create new srcset entry
            relative_url = self._get_relative_link_path(absolute_url)
            new_srcset_parts.append(f"{relative_url} {size}".strip())
        
        # Update the srcset attribute
        tag['srcset'] = ', '.join(new_srcset_parts)
    
    def _process_inline_style(self, tag, base_url):
        """Process CSS URLs in inline style attributes."""
        style = tag['style']
        
        # Find all url(...) patterns
        for url_match in re.finditer(r'url\s*\(\s*[\'"]?([^\'")]+)[\'"]?\s*\)', style):
            resource_url = url_match.group(1)
            
            # Skip data URLs
            if resource_url.startswith('data:'):
                continue
            
            # Create absolute URL
            absolute_url = urljoin(base_url, resource_url)
            
            # Add to queue if not visited
            if absolute_url not in self.visited_urls and absolute_url not in self.queue:
                self.queue.append(absolute_url)
                self.stats["total_urls"] += 1
            
            # Update URL in style
            relative_url = self._get_relative_link_path(absolute_url)
            style = style.replace(url_match.group(1), relative_url)
        
        # Update the style attribute
        tag['style'] = style
    
    def _get_relative_path(self, url):
        """Get the relative file system path for a URL."""
        parsed_url = urlparse(url)
        
        # Handle root URL
        if parsed_url.path == '/' or not parsed_url.path:
            return 'index.html'
        
        # Remove leading and trailing slashes
        path = parsed_url.path.strip('/')
        
        # Handle file extensions
        if path.endswith('/') or '.' not in path.split('/')[-1]:
            # Directory-like URL, add index.html
            if path.endswith('/'):
                path = path + 'index.html'
            else:
                path = path + '/index.html'
        
        return path
    
    def _get_relative_link_path(self, url):
        """Get the relative link path for internal navigation."""
        parsed_url = urlparse(url)
        
        # Handle external URLs
        if parsed_url.netloc != self.base_domain:
            return url  # Keep external URLs as is
        
        # Remove query string and fragment
        path = parsed_url.path
        
        # Handle root URL
        if path == '/' or not path:
            return '/'
        
        # Handle directory-like URLs
        if path.endswith('/'):
            return path
        
        # Check file extension
        if '.' not in path.split('/')[-1]:
            # No file extension, assume it's a directory
            return path + '/'
        
        return path
    
    def _save_html(self, relative_path, content):
        """Save HTML content to file."""
        try:
            # Create directory if needed
            file_path = self.task_dir / relative_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Save the file
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            self.file_count += 1
            
        except Exception as e:
            logger.error(f"Error saving HTML file {relative_path}: {e}")
    
    def _save_css(self, url, content):
        """Save CSS content to file."""
        try:
            # Get the file name from the URL
            filename = self._get_resource_filename(url, 'css')
            file_path = self.task_dir / 'css' / filename
            
            # Save the file
            with open(file_path, 'wb') as f:
                f.write(content)
            
            self.file_count += 1
            self.resources["css"] += 1
            
        except Exception as e:
            logger.error(f"Error saving CSS file {url}: {e}")
    
    def _save_javascript(self, url, content):
        """Save JavaScript content to file."""
        try:
            # Get the file name from the URL
            filename = self._get_resource_filename(url, 'js')
            file_path = self.task_dir / 'js' / filename
            
            # Save the file
            with open(file_path, 'wb') as f:
                f.write(content)
            
            self.file_count += 1
            self.resources["js"] += 1
            
        except Exception as e:
            logger.error(f"Error saving JavaScript file {url}: {e}")
    
    def _save_image(self, url, content):
        """Save image content to file."""
        try:
            # Get the file name from the URL
            filename = self._get_resource_filename(url, 'img')
            file_path = self.task_dir / 'images' / filename
            
            # Save the file
            with open(file_path, 'wb') as f:
                f.write(content)
            
            self.file_count += 1
            self.resources["images"] += 1
            
        except Exception as e:
            logger.error(f"Error saving image file {url}: {e}")
    
    def _save_font(self, url, content):
        """Save font content to file."""
        try:
            # Get the file name from the URL
            filename = self._get_resource_filename(url, 'font')
            file_path = self.task_dir / 'fonts' / filename
            
            # Save the file
            with open(file_path, 'wb') as f:
                f.write(content)
            
            self.file_count += 1
            self.resources["fonts"] += 1
            
        except Exception as e:
            logger.error(f"Error saving font file {url}: {e}")
    
    def _save_other_resource(self, url, content):
        """Save other resource content to file."""
        try:
            # Get the file name from the URL
            relative_path = self._get_relative_path(url)
            file_path = self.task_dir / relative_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Save the file
            with open(file_path, 'wb') as f:
                f.write(content)
            
            self.file_count += 1
            self.resources["other"] += 1
            
        except Exception as e:
            logger.error(f"Error saving resource file {url}: {e}")
    
    def _get_resource_filename(self, url, resource_type):
        """Generate a filename for a resource based on its URL."""
        parsed_url = urlparse(url)
        path = parsed_url.path
        
        # Extract filename from path
        filename = path.split('/')[-1]
        
        # If no filename, generate a unique one
        if not filename:
            filename = f"{resource_type}_{str(uuid.uuid4())[:8]}"
        
        # Ensure file has appropriate extension
        extensions = {
            'css': '.css',
            'js': '.js',
            'img': '.jpg',  # Default, actual extension should come from URL
            'font': '.woff'  # Default, actual extension should come from URL
        }
        
        # Add a random number to ensure uniqueness
        random_suffix = str(random.randint(1000, 9999))
        
        # Keep original extension if present
        if '.' in filename:
            safe_filename = re.sub(r'[^a-zA-Z0-9._-]', '_', f"{filename}_{random_suffix}")
            return safe_filename[:100]  # Limit length
        else:
            safe_filename = re.sub(r'[^a-zA-Z0-9._-]', '_', f"{filename}_{random_suffix}" + extensions.get(resource_type, ''))
            return safe_filename[:100]  # Limit length
    
    def _create_redirects_file(self):
        """Create _redirects file for Netlify."""
        redirects_path = self.task_dir / '_redirects'
        
        with open(redirects_path, 'w') as f:
            # Add a basic redirect rule to handle clean URLs
            f.write("/*    /index.html   404\n")
    
    def _create_zip_file(self):
        """Create a ZIP file of the crawled content."""
        domain_name = self.base_domain.replace('.', '_')
        zip_filename = f"{domain_name}_{int(time.time())}.zip"
        self.zip_path = os.path.join("temp", zip_filename)
        
        # Make sure any previously existing file with the same name is removed
        if os.path.exists(self.zip_path):
            try:
                os.remove(self.zip_path)
            except Exception as e:
                logger.error(f"Error removing existing zip file: {e}")
        
        try:
            with zipfile.ZipFile(self.zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Add the netlify _redirects file
                redirect_path = os.path.join(self.task_dir, "_redirects")
                if os.path.exists(redirect_path):
                    zipf.write(redirect_path, "_redirects")
                
                # Add all other files from the task directory
                for root, _, files in os.walk(self.task_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, self.task_dir)
                        zipf.write(file_path, arcname)
            
            # Debug log: Show zip file was created and its size
            if os.path.exists(self.zip_path):
                size_kb = os.path.getsize(self.zip_path) / 1024
                logger.debug(f"ZIP file created: {zip_filename} ({size_kb:.1f} KB)")
                
            self._queue_status_update(f"ZIP file created: {zip_filename}", 100)
        except Exception as e:
            logger.error(f"Error creating ZIP file: {e}")
            # Create minimal zip file anyway to avoid download failures
            try:
                with zipfile.ZipFile(self.zip_path, 'w') as zipf:
                    # Create a dummy index.html 
                    dummy_path = os.path.join(self.task_dir, "index.html")
                    with open(dummy_path, 'w') as f:
                        f.write("<html><body><h1>Minimal download</h1><p>The crawl did not complete properly.</p></body></html>")
                    zipf.write(dummy_path, "index.html")
            except Exception as e2:
                logger.error(f"Error creating minimal ZIP: {e2}")
    
    def get_stats(self):
        """Get crawling statistics."""
        return self.stats
    
    def get_zip_path(self):
        """Get the path to the generated ZIP file."""
        return self.zip_path
    
    def get_preview_data(self):
        """Get data for preview of crawled content."""
        # Return information about crawled pages
        preview_data = {
            "pages": [],
            "resources": self.resources,
            "total_files": self.file_count
        }
        
        # Get a sample of HTML files for preview
        html_files = list(self.task_dir.glob('**/*.html'))
        for html_file in html_files[:10]:  # Limit to first 10 files
            try:
                with open(html_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Extract title
                title_match = re.search(r'<title>(.*?)</title>', content, re.IGNORECASE | re.DOTALL)
                title = title_match.group(1) if title_match else "No title"
                
                preview_data["pages"].append({
                    "path": str(html_file.relative_to(self.task_dir)),
                    "title": title
                })
            except Exception as e:
                logger.error(f"Error reading HTML file for preview: {e}")
        
        return preview_data
    
    def cleanup(self):
        """Clean up task files."""
        try:
            # Remove the task directory
            if self.task_dir.exists():
                shutil.rmtree(self.task_dir)
            
            # Remove ZIP file if it exists
            if self.zip_path and os.path.exists(self.zip_path):
                os.remove(self.zip_path)
            
            return True
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
            return False
