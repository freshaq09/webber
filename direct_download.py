import requests
import time
import os
import sys
from urllib.parse import urlparse

"""
This is a simplified version of the website crawler that focuses on:
1. Grabbing and downloading a specified website
2. Creating a Netlify-ready ZIP file
3. Showing progress during the crawl

Just run this script with a URL to crawl:
python direct_download.py https://press-hub-news.webflow.io
"""

# Get URL from command line or use default
if len(sys.argv) > 1:
    WEBSITE_URL = sys.argv[1]
else:
    WEBSITE_URL = "https://press-hub-news.webflow.io"

# Validate URL
if not WEBSITE_URL.startswith(('http://', 'https://')):
    WEBSITE_URL = 'https://' + WEBSITE_URL

print(f"Starting website download process for: {WEBSITE_URL}")

# Start the crawl
response = requests.post('http://localhost:5000/crawl', data={
    'url': WEBSITE_URL
})

if response.status_code != 200:
    print(f"Error starting crawl: {response.text}")
    exit(1)

data = response.json()
task_id = data.get('task_id')

if not task_id:
    print("No task ID returned from server")
    exit(1)

print(f"Crawler started with task ID: {task_id}")
print("Downloading website content...")

# Animation characters for progress indicator
spinner = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
progress_idx = 0

# Poll for status (with shorter timeout)
max_tries = 60
try_count = 0
completed = False

while try_count < max_tries:
    try:
        response = requests.get(f'http://localhost:5000/status/{task_id}')
        if response.status_code == 200:
            status_data = response.json()
            status = status_data.get('status')
            
            stats = status_data.get('crawled_urls', {})
            processed = stats.get('processed_urls', 0)
            total = stats.get('total_urls', 0)
            failed = stats.get('failed_urls', 0)
            
            # Progress animation
            progress_char = spinner[progress_idx]
            progress_idx = (progress_idx + 1) % len(spinner)
            
            if status == 'completed':
                print(f"\nCrawl completed! Downloaded {processed} files.")
                completed = True
                break
                
            # Print progress (overwrite line)
            print(f"\r{progress_char} Status: {status.capitalize()} - Downloaded {processed} of {total} files (Failed: {failed})", end='')
        
        else:
            print(f"\nError checking status: {response.text}")
    
    except Exception as e:
        print(f"\nError: {e}")
    
    try_count += 1
    time.sleep(0.5)

if not completed:
    print("\nCrawl did not complete in the allocated time.")
    print("You can still try to download the partial result.")

print("\nPreparing ZIP file...")

# Download the ZIP
download_response = requests.get(f'http://localhost:5000/download/{task_id}', stream=True)

if download_response.status_code != 200:
    print(f"Error downloading ZIP: {download_response.text}")
    exit(1)

# Create a descriptive filename
domain = urlparse(WEBSITE_URL).netloc.replace('.', '_')
timestamp = int(time.time())
filename = f"{domain}_{timestamp}.zip"

# Save the file with progress indicator
print(f"Saving as: {filename}")
file_size = 0
with open(filename, 'wb') as f:
    for i, chunk in enumerate(download_response.iter_content(chunk_size=8192)):
        f.write(chunk)
        file_size += len(chunk)
        if i % 20 == 0:  # Show progress every 20 chunks
            print(f"\rDownloading: {file_size / 1024:.1f} KB", end='')

# Verify file
if os.path.exists(filename) and os.path.getsize(filename) > 0:
    final_size = os.path.getsize(filename) / 1024  # Size in KB
    
    print(f"\n\nDownload complete!")
    print(f"File saved: {os.path.abspath(filename)}")
    print(f"Size: {final_size:.1f} KB")
    print("\nThis ZIP file is ready for direct upload to Netlify.")
    print("Just drag and drop it to https://app.netlify.com/drop")
else:
    print("\nError: Downloaded file is empty or not found.")

# Clean up the server resources
try:
    requests.post(f'http://localhost:5000/cleanup/{task_id}')
except:
    pass  # Ignore cleanup errors