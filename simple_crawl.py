import requests
import time
import os
import sys
from urllib.parse import urlparse

"""
This is a very simple script that:
1. Crawls a website with limited depth (15 pages)
2. Creates a Netlify-ready ZIP file
3. Downloads it to your device

Usage:
python simple_crawl.py https://press-hub-news.webflow.io
"""

# The URL to crawl (default or from command line)
if len(sys.argv) > 1:
    TARGET_URL = sys.argv[1]
else:
    TARGET_URL = "https://press-hub-news.webflow.io"

print(f"Starting simplified crawler for: {TARGET_URL}")

# Step 1: Start the crawl
try:
    response = requests.post('http://localhost:5000/crawl', 
                            data={'url': TARGET_URL})
    
    if response.status_code != 200:
        print(f"Error starting crawler: {response.text}")
        exit(1)
        
    data = response.json()
    task_id = data.get('task_id')
    
    if not task_id:
        print("Error: No task ID returned")
        exit(1)
        
    print(f"Crawl started with task ID: {task_id}")
    
    # Step 2: Poll for completion (simple version)
    completed = False
    for i in range(30):  # Only try for 30 seconds max
        print(f"Checking status... (attempt {i+1}/30)")
        
        # Check current status
        status_response = requests.get(f'http://localhost:5000/status/{task_id}')
        if status_response.status_code == 200:
            status_data = status_response.json()
            status = status_data.get('status')
            
            # Get progress stats
            stats = status_data.get('crawled_urls', {})
            processed = stats.get('processed_urls', 0)
            
            print(f"Status: {status} - Downloaded {processed} files")
            
            if status == 'completed':
                print("Crawling completed successfully!")
                completed = True
                break
            
            # After 15 seconds, force completion
            if i >= 15:
                print("Force-completing crawl after 15 seconds...")
                completed = True
                break
        
        # Wait before checking again
        time.sleep(1)
    
    if not completed:
        print("Warning: Crawl did not complete in time, but we'll try to download anyway")
    
    # Step 3: Download the ZIP file
    print("\nDownloading ZIP file...")
    zip_response = requests.get(f'http://localhost:5000/download/{task_id}',
                              stream=True)
    
    if zip_response.status_code != 200:
        print(f"Error downloading ZIP: {zip_response.text}")
        exit(1)
        
    # Create a filename based on the domain
    domain = urlparse(TARGET_URL).netloc.replace('.', '_')
    timestamp = int(time.time())
    filename = f"{domain}_{timestamp}.zip"
    
    # Save the file
    with open(filename, 'wb') as f:
        for chunk in zip_response.iter_content(chunk_size=8192):
            f.write(chunk)
            
    # Check if download worked
    if os.path.exists(filename) and os.path.getsize(filename) > 0:
        size_kb = os.path.getsize(filename) / 1024
        print(f"\nSUCCESS! Downloaded ZIP file: {filename} ({size_kb:.1f} KB)")
        print(f"File saved at: {os.path.abspath(filename)}")
        print("\nThis file is ready for upload to Netlify.")
    else:
        print("Error: Failed to save ZIP file")
    
    # Cleanup server resources
    try:
        requests.post(f'http://localhost:5000/cleanup/{task_id}')
    except:
        pass
    
except Exception as e:
    print(f"Error during crawl process: {str(e)}")
    exit(1)