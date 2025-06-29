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
import uuid

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def crawl_with_wget_sync(url):
    """
    Uses wget to crawl a website and returns the path to the ZIP file.
    This is a synchronous version that blocks until completion.
    
    Args:
        url (str): The URL to crawl
        
    Returns:
        str: Path to the ZIP file or None if failed
    """
    try:
        # First, check if wget is available
        try:
            # Check multiple possible wget locations
            wget_locations = ['wget', '/nix/store/*/bin/wget', '/usr/bin/wget', '/bin/wget']
            wget_found = False
            wget_path = None
            
            for location in wget_locations:
                try:
                    if '*' in location:
                        # Handle wildcard paths
                        import glob
                        matches = glob.glob(location)
                        for match in matches:
                            if os.path.exists(match) and os.access(match, os.X_OK):
                                wget_path = match
                                wget_found = True
                                break
                    else:
                        # Direct path check
                        result = subprocess.run(['which', location], capture_output=True, text=True)
                        if result.returncode == 0:
                            wget_path = result.stdout.strip()
                            wget_found = True
                            break
                except Exception:
                    continue
            
            if not wget_found:
                logger.error("wget is not available on this system")
                logger.error(f"Checked locations: {wget_locations}")
                logger.error(f"PATH: {os.environ.get('PATH', 'Not set')}")
                return None
            
            logger.info(f"wget found at: {wget_path}")
        except Exception as e:
            logger.error(f"Error checking wget availability: {e}")
            return None
        
        # Parse URL to get domain for ZIP file naming
        parsed_url = urllib.parse.urlparse(url)
        domain = parsed_url.netloc
        
        # Create a unique task ID and temporary directory
        task_id = str(uuid.uuid4())
        temp_dir = Path("temp") / task_id
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Starting wget crawl for {url} in {temp_dir}")
        
        # Build wget command for fast, complete website downloading
        # Find wget in Nix store or use system wget
        wget_cmd = 'wget'
        try:
            # Try to find wget in Nix store
            import glob
            nix_wget_paths = glob.glob('/nix/store/*/bin/wget')
            if nix_wget_paths:
                wget_cmd = nix_wget_paths[0]
                logger.info(f"Using Nix wget: {wget_cmd}")
            else:
                logger.info("Using system wget")
        except Exception:
            logger.info("Using system wget")
        
        cmd = [
            wget_cmd,
            '--mirror',               # Mirror the website
            '--convert-links',        # Convert links to work locally
            '--adjust-extension',     # Add extensions to files (.html)
            '--page-requisites',      # Get all assets (CSS, JS, images)
            '--no-parent',            # Don't go to parent directory
            '--directory-prefix=' + str(temp_dir),  # Output directory
            '--no-verbose',           # Reduce output verbosity
            '--timeout=30',           # Add timeout
            '--tries=3',              # Retry failed downloads
            url
        ]
        
        logger.info(f"Running wget command: {' '.join(cmd)}")
        
        # Execute wget command and wait for completion
        process = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False  # Don't raise exception on non-zero exit
        )
        
        # Log the full output for debugging
        logger.info(f"wget stdout: {process.stdout}")
        logger.info(f"wget stderr: {process.stderr}")
        logger.info(f"wget return code: {process.returncode}")
        
        # Check if wget was successful or partially successful
        # Return code 8 means some URLs couldn't be downloaded, but the core site was likely downloaded
        if process.returncode != 0 and process.returncode != 8:
            logger.error(f"wget failed with return code {process.returncode}: {process.stderr}")
            
            # Provide more specific error messages based on return codes
            if process.returncode == 1:
                error_msg = "Generic error occurred during download. The website might be unavailable or blocked."
            elif process.returncode == 2:
                error_msg = "Parse error. The URL format might be invalid."
            elif process.returncode == 3:
                error_msg = "File I/O error. Check disk space and permissions."
            elif process.returncode == 4:
                error_msg = "Network failure. Check your internet connection."
            elif process.returncode == 5:
                error_msg = "SSL verification failed. The website might have certificate issues."
            elif process.returncode == 6:
                error_msg = "Username/password authentication failed."
            elif process.returncode == 7:
                error_msg = "Protocol error. The website might not support the required protocol."
            else:
                error_msg = f"wget failed with error code {process.returncode}. Please try a different website."
            
            logger.error(f"Specific error: {error_msg}")
            return None
        elif process.returncode == 8:
            # This is a partial success - some URLs were too long or had other issues
            logger.warning(f"wget completed with partial success (code 8). Some URLs may have been skipped.")
            # Continue processing since we likely have most of the content
        
        # Find the domain directory (wget creates a directory structure)
        domain_dir = temp_dir / domain
        if not domain_dir.exists():
            # Maybe wget used a www subdomain
            www_domain_dir = temp_dir / ("www." + domain)
            if www_domain_dir.exists():
                domain_dir = www_domain_dir
        
        # If neither domain directory exists, use the output directory
        if not domain_dir.exists():
            domain_dir = temp_dir
        
        # Create _redirects file for Netlify
        redirects_path = domain_dir / "_redirects"
        with open(redirects_path, 'w') as f:
            f.write("/*    /index.html   404\n")
            
        # Create ZIP file
        timestamp = int(time.time())
        zip_filename = f"{domain.replace('.', '_')}_{timestamp}.zip"
        zip_path = str(Path(".") / zip_filename)  # Save to current directory for easy access
        
        logger.info(f"Creating ZIP file at {zip_path}")
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # If domain directory exists, archive its contents
            for root, _, files in os.walk(domain_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, domain_dir)
                    zipf.write(file_path, arcname)
        
        # Count files
        files_downloaded = sum(1 for _ in zipfile.ZipFile(zip_path, 'r').namelist())
        
        logger.info(f"Wget crawl completed for {url}")
        logger.info(f"Downloaded {files_downloaded} files")
        logger.info(f"ZIP file created at {zip_path}")
        
        # Clean up temp directory
        shutil.rmtree(temp_dir, ignore_errors=True)
        
        return zip_path
        
    except Exception as e:
        logger.error(f"Error in wget crawling: {str(e)}")
        # Log the full traceback for debugging
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        # Return None to indicate failure
        return None

# Command line interface for testing
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: fast_wget.py URL")
        sys.exit(1)
    
    url = sys.argv[1]
    
    # Start the timer
    start_time = time.time()
    
    # Call the function
    zip_path = crawl_with_wget_sync(url)
    
    # Calculate elapsed time
    elapsed_time = time.time() - start_time
    
    if zip_path and os.path.exists(zip_path):
        print(f"\nDOWNLOAD COMPLETE!")
        print(f"Downloaded and processed {url}")
        print(f"ZIP file: {zip_path} ({os.path.getsize(zip_path) / (1024*1024):.2f} MB)")
        print(f"Time taken: {elapsed_time:.2f} seconds")
    else:
        print(f"\nFAILED TO DOWNLOAD {url}")
        print(f"Check logs for errors")
        sys.exit(1)