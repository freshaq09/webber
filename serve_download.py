from flask import Flask, send_file, render_template_string
import os

app = Flask(__name__)

HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Website Download</title>
    <link rel="stylesheet" href="https://cdn.replit.com/agent/bootstrap-agent-dark-theme.min.css">
    <style>
        body {
            padding: 20px;
            background-color: #121212;
            color: #e0e0e0;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
        }
        .card {
            margin-top: 30px;
            margin-bottom: 30px;
            background-color: #1e1e1e;
            border: 1px solid #333;
        }
        .btn-download {
            margin-top: 20px;
        }
        .file-info {
            margin-bottom: 15px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1 class="mt-4 mb-3">Website Package Download</h1>
        
        <div class="card p-4">
            <h2>{{ filename }}</h2>
            <div class="file-info">
                <p><strong>Size:</strong> {{ size }} KB</p>
                <p><strong>Contains:</strong> HTML files, CSS, JavaScript, and assets from the website</p>
                <p><strong>Compatible with:</strong> Netlify Drop (direct upload)</p>
            </div>
            
            <p>This ZIP file contains a crawled website that's ready for deployment on Netlify.</p>
            
            <a href="/download" 
               class="btn btn-primary btn-lg btn-download">
                Download ZIP File
            </a>
        </div>
        
        <div class="card p-4 mt-4">
            <h3>Usage Instructions</h3>
            <ol>
                <li>Click the blue download button above to save the ZIP file.</li>
                <li>Go to <a href="https://app.netlify.com/drop" target="_blank">Netlify Drop</a></li>
                <li>Drag and drop the downloaded ZIP file to deploy your website</li>
            </ol>
        </div>
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    # Find the latest zip file
    zip_files = [f for f in os.listdir('.') if f.endswith('.zip')]
    if not zip_files:
        return "No ZIP files found", 404
    
    # Sort by modification time (newest first)
    zip_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    latest_zip = zip_files[0]
    
    # Calculate size
    size_kb = os.path.getsize(latest_zip) / 1024
    
    return render_template_string(HTML_TEMPLATE, 
                                 filename=latest_zip,
                                 size=f"{size_kb:.1f}")

@app.route('/download')
def download():
    # Find the latest zip file
    zip_files = [f for f in os.listdir('.') if f.endswith('.zip')]
    if not zip_files:
        return "No ZIP files found", 404
    
    # Sort by modification time (newest first)
    zip_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    latest_zip = zip_files[0]
    
    return send_file(latest_zip, as_attachment=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)