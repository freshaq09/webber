from flask import Flask, send_file, render_template
import os
import glob

app = Flask(__name__)

@app.route('/')
def index():
    # Get a list of all ZIP files in the current directory
    zip_files = glob.glob('*.zip')
    # Sort by modification time (newest first)
    zip_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    
    # Create a list of file information
    files = []
    for zip_file in zip_files:
        size_kb = os.path.getsize(zip_file) / 1024
        files.append({
            'name': zip_file,
            'size': f"{size_kb:.1f} KB",
            'date': os.path.getmtime(zip_file)
        })
    
    return render_template('download.html', files=files)

@app.route('/download/<filename>')
def download(filename):
    # Check if the file exists
    if os.path.exists(filename):
        return send_file(filename, as_attachment=True)
    else:
        return "File not found", 404

if __name__ == '__main__':
    # Ensure templates directory exists
    os.makedirs('templates', exist_ok=True)
    
    # Create a simple template for the download page if it doesn't exist
    template_path = 'templates/download.html'
    if not os.path.exists(template_path):
        with open(template_path, 'w') as f:
            f.write('''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Website Crawler - Downloads</title>
    <link rel="stylesheet" href="https://cdn.replit.com/agent/bootstrap-agent-dark-theme.min.css">
    <style>
        body {
            padding: 20px;
        }
        .file-card {
            margin-bottom: 15px;
            padding: 15px;
            border-radius: 5px;
        }
        .download-btn {
            margin-top: 10px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1 class="mt-4 mb-4">Website Crawler - Available Downloads</h1>
        
        {% if files %}
            <div class="row">
                {% for file in files %}
                    <div class="col-md-6">
                        <div class="card file-card bg-dark">
                            <div class="card-body">
                                <h5 class="card-title">{{ file.name }}</h5>
                                <p class="card-text">Size: {{ file.size }}</p>
                                <a href="/download/{{ file.name }}" class="btn btn-primary download-btn">Download</a>
                            </div>
                        </div>
                    </div>
                {% endfor %}
            </div>
        {% else %}
            <div class="alert alert-info">
                No ZIP files available for download.
            </div>
            <p>Use the quick_download.py script to create website downloads:</p>
            <pre class="bg-dark p-3 rounded">python quick_download.py https://your-website-url.com</pre>
        {% endif %}
    </div>
</body>
</html>''')
    
    app.run(host='0.0.0.0', port=8000)