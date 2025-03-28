from flask import Flask, render_template, request, send_file, make_response
import os
import time
from io import StringIO
from web_scraper import get_website_text_content

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('web_scraper.html')

@app.route('/scrape', methods=['POST'])
def scrape():
    url = request.form.get('url')
    if not url:
        return render_template('web_scraper.html', error="Please enter a URL")
    
    try:
        # Extract content using the web_scraper module
        content = get_website_text_content(url)
        
        if not content:
            return render_template('web_scraper.html', 
                                  error="No main content could be extracted from this URL. The page might be empty, protected, or not accessible.",
                                  url=url)
        
        return render_template('web_scraper.html', content=content, url=url)
    
    except Exception as e:
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
    text_file = StringIO()
    text_file.write(f"Source URL: {url}\n\n")
    text_file.write(content)
    text_file.seek(0)
    
    # Create response with file
    response = make_response(text_file.getvalue())
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    response.headers["Content-Type"] = "text/plain"
    
    return response

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)