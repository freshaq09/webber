import sys
import os
import time
import urllib.parse
import logging
import requests
from bs4 import BeautifulSoup
import zipfile
import shutil

# Set up basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Get URL from command line or use default
if len(sys.argv) > 1:
    url = sys.argv[1]
else:
    url = "https://press-hub-news.webflow.io"

# Get max pages from command line or use default
if len(sys.argv) > 2:
    max_pages = int(sys.argv[2])
else:
    max_pages = 15  # Default limit to 15 pages

# Parse domain information
domain_info = urllib.parse.urlparse(url)
base_domain = domain_info.netloc
base_url = f"{domain_info.scheme}://{domain_info.netloc}"

# Create a temporary directory for this download
timestamp = int(time.time())
temp_dir = f"quick_download_{timestamp}"
os.makedirs(temp_dir, exist_ok=True)

# Create nested directories
for subdir in ["css", "js", "images", "fonts"]:
    os.makedirs(os.path.join(temp_dir, subdir), exist_ok=True)

# Track processed URLs
processed_urls = set()
urls_to_process = [url]
processed_count = 0

print(f"Starting quick download of {url}")
print(f"Will download up to {max_pages} pages")

# Process URLs
session = requests.Session()

# Start processing pages
while urls_to_process and processed_count < max_pages:
    current_url = urls_to_process.pop(0)
    
    # Skip if already processed
    if current_url in processed_urls:
        continue
    
    processed_urls.add(current_url)
    processed_count += 1
    
    print(f"Processing {processed_count}/{max_pages}: {current_url}")
    
    try:
        # Get page content
        response = session.get(current_url, timeout=10)
        if response.status_code != 200:
            logging.warning(f"Failed to get {current_url}: {response.status_code}")
            continue
        
        # Parse HTML content
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Determine file path for this page
        url_path = urllib.parse.urlparse(current_url).path
        if not url_path or url_path == '/':
            page_file = "index.html"
        else:
            # Remove leading/trailing slashes
            path = url_path.strip('/')
            # Handle directory-like URLs
            if not path.endswith('.html') and not '.' in path.split('/')[-1]:
                if '/' in path:
                    dir_path = os.path.join(temp_dir, os.path.dirname(path))
                    os.makedirs(dir_path, exist_ok=True)
                    page_file = os.path.join(path, "index.html")
                else:
                    os.makedirs(os.path.join(temp_dir, path), exist_ok=True)
                    page_file = os.path.join(path, "index.html")
            else:
                page_file = path
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(os.path.join(temp_dir, page_file)), exist_ok=True)
        
        # Save the HTML file
        with open(os.path.join(temp_dir, page_file), 'w', encoding='utf-8') as f:
            f.write(response.text)
        
        # Extract links to other pages on the same domain
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            if href.startswith('/') or href.startswith(base_url):
                # Create absolute URL
                if href.startswith('/'):
                    absolute_url = urllib.parse.urljoin(base_url, href)
                else:
                    absolute_url = href
                
                # Check if it's from the same domain
                if urllib.parse.urlparse(absolute_url).netloc == base_domain:
                    # Remove fragments
                    absolute_url = absolute_url.split('#')[0]
                    # Skip processed and queued URLs
                    if absolute_url not in processed_urls and absolute_url not in urls_to_process:
                        urls_to_process.append(absolute_url)
    
    except Exception as e:
        logging.error(f"Error processing {current_url}: {str(e)}")
    
    # Short delay to be respectful
    time.sleep(0.1)

# Create _redirects file for Netlify
with open(os.path.join(temp_dir, "_redirects"), 'w') as f:
    f.write("/*    /index.html   404\n")

# Create a ZIP file
zip_filename = f"{base_domain.replace('.', '_')}_{timestamp}.zip"
with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
    for root, _, files in os.walk(temp_dir):
        for file in files:
            file_path = os.path.join(root, file)
            arcname = os.path.relpath(file_path, temp_dir)
            zipf.write(file_path, arcname)

# Clean up temporary directory
shutil.rmtree(temp_dir)

# Show completion
print(f"\nDOWNLOAD COMPLETE!")
print(f"Downloaded {processed_count} pages from {url}")
print(f"ZIP file: {zip_filename} ({os.path.getsize(zip_filename) / 1024:.1f} KB)")
print(f"This file is ready for upload to Netlify.")