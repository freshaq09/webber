import requests
import time
import json
import os

print("Starting crawler test for https://press-hub-news.webflow.io")

# Step 1: Start a crawl job
response = requests.post('http://localhost:5000/crawl', data={
    'url': 'https://press-hub-news.webflow.io'
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

# Step 2: Poll for status until completed
max_retries = 60  # Maximum 5 minutes (5 seconds per retry)
retry_count = 0
completed = False

print("Will poll for status updates")
print("Waiting for crawl job to complete...")

while retry_count < max_retries:
    try:
        status_response = requests.get(f'http://localhost:5000/status/{task_id}')
        
        if status_response.status_code != 200:
            print(f"Failed to get status: {status_response.text}")
            retry_count += 1
            time.sleep(5)
            continue
            
        status_data = status_response.json()
        status = status_data.get('status')
        
        if status == 'completed':
            print("Crawl job completed successfully")
            completed = True
            break
        elif status == 'failed':
            print(f"Crawl job failed: {status_data}")
            break
            
        # Get and display crawl stats
        stats = status_data.get('crawled_urls', {})
        processed = stats.get('processed_urls', 0)
        total = stats.get('total_urls', 0)
        failed = stats.get('failed_urls', 0)
        
        print(f"Current status: {status}, Progress: {processed}/{total} URLs processed, Failed: {failed}")
        
    except Exception as e:
        print(f"Error checking status: {e}")
        
    retry_count += 1
    time.sleep(5)

if not completed:
    print("Crawl job did not complete in the expected time")
    exit(1)

# Step 3: Download the ZIP file
print("Attempting to download ZIP file...")
download_response = requests.get(f'http://localhost:5000/download/{task_id}', stream=True)

if download_response.status_code != 200:
    print(f"Failed to download ZIP file: {download_response.text}")
    exit(1)

# Save the ZIP file
filename = 'crawled_site.zip'
with open(filename, 'wb') as f:
    for chunk in download_response.iter_content(chunk_size=8192):
        f.write(chunk)

# Verify ZIP file exists and has content
if os.path.exists(filename) and os.path.getsize(filename) > 0:
    print(f"Successfully downloaded ZIP file: {filename} ({os.path.getsize(filename)} bytes)")
    print("Test passed!")
else:
    print(f"ZIP file download failed or file is empty: {filename}")
    exit(1)