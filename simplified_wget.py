#!/usr/bin/env python3
import os
import sys
import subprocess
import logging
import time
import urllib.parse
import zipfile
import shutil
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def crawl_with_wget(url, task_id, output_dir):
    """
    Uses wget to crawl a website and returns statistics about the crawl.
    
    Args:
        url (str): The URL to crawl
        task_id (str): A unique ID for this crawl task
        output_dir (Path): Directory to save the crawled files
        
    Returns:
        dict: Statistics about the crawl
    """
    try:
        # Make sure output directory exists
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Parse URL to get domain for ZIP file naming
        parsed_url = urllib.parse.urlparse(url)
        domain = parsed_url.netloc
        
        # Build wget command
        cmd = [
            'wget',
            '--mirror',                 # Mirror the website
            '--convert-links',          # Convert links to work locally
            '--adjust-extension',       # Add extensions to files (.html)
            '--page-requisites',        # Get all assets (CSS, JS, images)
            '--no-parent',              # Don't go to parent directory
            '--directory-prefix=' + str(output_dir),  # Output directory
            '--no-verbose',             # Reduce output verbosity
            url
        ]
        
        logger.info(f"Starting wget crawl for {url}")
        logger.info(f"Command: {' '.join(cmd)}")
        
        # Execute wget command
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Capture output before waiting
        stdout, stderr = process.communicate()
        
        # Check if wget was successful
        if process.returncode != 0:
            logger.error(f"wget failed with return code {process.returncode}: {stderr}")
            return {
                "status": "failed",
                "error": f"wget failed with return code {process.returncode}"
            }
        
        # Count files and categorize them
        files_downloaded = 0
        resources = {
            'html': 0,
            'css': 0,
            'js': 0, 
            'images': 0,
            'fonts': 0,
            'other': 0
        }
        
        # Find the domain directory (wget creates a directory structure)
        domain_dir = output_dir / domain
        if not domain_dir.exists():
            # Maybe wget used a www subdomain
            www_domain_dir = output_dir / ("www." + domain)
            if www_domain_dir.exists():
                domain_dir = www_domain_dir
        
        # If neither domain directory exists, use the output directory
        if not domain_dir.exists():
            domain_dir = output_dir
        
        # Walk through the directory and count files
        logger.info(f"Counting files in {domain_dir}")
        for root, _, files in os.walk(domain_dir):
            for file in files:
                files_downloaded += 1
                
                # Update resource counts based on file extension
                if file.endswith('.html') or file.endswith('.htm'):
                    resources['html'] += 1
                elif file.endswith('.css'):
                    resources['css'] += 1
                elif file.endswith('.js'):
                    resources['js'] += 1
                elif any(file.endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp']):
                    resources['images'] += 1
                elif any(file.endswith(ext) for ext in ['.woff', '.woff2', '.ttf', '.eot']):
                    resources['fonts'] += 1
                else:
                    resources['other'] += 1
        
        # Create _redirects file for Netlify
        redirects_path = domain_dir / "_redirects"
        with open(redirects_path, 'w') as f:
            f.write("/*    /index.html   404\n")
            
        # Create ZIP file
        timestamp = int(time.time())
        zip_filename = f"{domain.replace('.', '_')}_{timestamp}.zip"
        zip_path = str(output_dir.parent / zip_filename)
        
        logger.info(f"Creating ZIP file at {zip_path}")
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # If domain directory exists, archive its contents
            for root, _, files in os.walk(domain_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, domain_dir)
                    zipf.write(file_path, arcname)
        
        # Create success result
        result = {
            "status": "completed",
            "zip_path": zip_path,
            "files_downloaded": files_downloaded,
            "resources": resources
        }
        
        logger.info(f"Wget crawl completed for {url}")
        logger.info(f"Downloaded {files_downloaded} files")
        logger.info(f"ZIP file created at {zip_path}")
        
        return result
        
    except Exception as e:
        logger.error(f"Error in wget crawling: {str(e)}")
        return {
            "status": "failed",
            "error": str(e)
        }

# Command line interface for testing
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: simplified_wget.py URL [OUTPUT_DIR]")
        sys.exit(1)
    
    url = sys.argv[1]
    output_dir = Path("wget_temp") if len(sys.argv) < 3 else Path(sys.argv[2])
    task_id = f"test_{int(time.time())}"
    
    result = crawl_with_wget(url, task_id, output_dir)
    print(f"\nRESULT: {result}")
    
    if result["status"] == "completed":
        print(f"\nDownloaded {result['files_downloaded']} files")
        print(f"ZIP file: {result['zip_path']} ({os.path.getsize(result['zip_path']) / (1024*1024):.2f} MB)")