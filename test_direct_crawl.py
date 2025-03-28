import requests
import time
import os
import shutil
from urllib.parse import urlparse
import sys

# This is a simplified direct crawler test that only crawls a limited number of pages
# and returns a Netlify-ready ZIP file as quickly as possible

# Define the URL to crawl
if len(sys.argv) > 1:
    TEST_URL = sys.argv[1]
else:
    TEST_URL = "https://press-hub-news.webflow.io"

print(f"Testing direct crawling of {TEST_URL}")

# Step 1: Start a crawl job
response = requests.post('http://localhost:5000/crawl', data={
    'url': TEST_URL
})

if response.status_code != 200:
    print(f"Failed to start crawl job: {response.text}")
    exit(1)

data = response.json()
task_id = data.get('task_id')

if not task_id:
    print("No task ID returned from server")
    exit(1)

print(f"Crawl job started with task ID: {task_id}")

# Step 2: Poll for status until completed (faster polling)
max_retries = 30  # Maximum 1 minute (2 seconds per retry)
retry_count = 0
completed = False

# Wait a moment to let crawling initialize
time.sleep(2)
print("Checking crawl status...")

progress_chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
progress_idx = 0

while retry_count < max_retries:
    try:
        status_response = requests.get(f'http://localhost:5000/status/{task_id}')
        
        if status_response.status_code != 200:
            print(f"Failed to get status: {status_response.text}")
            retry_count += 1
            time.sleep(2)
            continue
            
        status_data = status_response.json()
        status = status_data.get('status')
        
        # Get crawl stats
        stats = status_data.get('crawled_urls', {})
        processed = stats.get('processed_urls', 0)
        total = stats.get('total_urls', 0)
        failed = stats.get('failed_urls', 0)
        
        if status == 'completed':
            print(f"\nCrawl job completed successfully! Processed {processed} URLs.")
            completed = True
            break
        elif status == 'failed':
            print(f"\nCrawl job failed: {status_data}")
            break
        
        # Spinning character for animation
        progress_char = progress_chars[progress_idx]
        progress_idx = (progress_idx + 1) % len(progress_chars)
        
        # Print status (overwrite previous line)
        print(f"\r{progress_char} Current status: {status}, Progress: {processed}/{total} URLs processed, Failed: {failed}", end='')
        
    except Exception as e:
        print(f"\nError checking status: {e}")
        
    retry_count += 1
    time.sleep(2)

if not completed:
    print("Crawl job did not complete in the expected time")
    exit(1)

# Step 3: Download the ZIP file
print("Downloading ZIP file...")
download_response = requests.get(f'http://localhost:5000/download/{task_id}', stream=True)

if download_response.status_code != 200:
    print(f"Failed to download ZIP file: {download_response.text}")
    exit(1)

# Create descriptive filename
domain_name = urlparse(TEST_URL).netloc.replace('.', '_')
timestamp = int(time.time())
filename = f"{domain_name}_{timestamp}.zip"

# Save the ZIP file
with open(filename, 'wb') as f:
    for chunk in download_response.iter_content(chunk_size=8192):
        f.write(chunk)

# Verify ZIP file exists and has content
if os.path.exists(filename) and os.path.getsize(filename) > 0:
    filesize = os.path.getsize(filename)
    filesize_kb = filesize / 1024
    filesize_mb = filesize_kb / 1024
    
    if filesize_mb >= 1:
        size_str = f"{filesize_mb:.2f} MB"
    else:
        size_str = f"{filesize_kb:.2f} KB"
        
    print(f"Successfully downloaded ZIP file: {filename} ({size_str})")
    print(f"\nDownload complete! The ZIP file is ready for Netlify deployment.")
    print(f"Full path: {os.path.abspath(filename)}")
    print("\nTest passed! ✓")
else:
    print(f"ZIP file download failed or file is empty: {filename}")
    exit(1)

# Clean up the task on server
try:
    cleanup_response = requests.post(f'http://localhost:5000/cleanup/{task_id}')
    if cleanup_response.status_code == 200:
        print("Server-side cleanup completed.")
except Exception as e:
    print(f"Note: Server cleanup error: {e}")