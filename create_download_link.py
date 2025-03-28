import sys
import base64
import os

def create_html_download_link(zip_filename, output_filename="download.html"):
    """
    Create an HTML file with a download link for the zip file
    """
    if not os.path.exists(zip_filename):
        print(f"Error: {zip_filename} does not exist!")
        return False
    
    size_kb = os.path.getsize(zip_filename) / 1024
    
    with open(zip_filename, 'rb') as f:
        encoded_data = base64.b64encode(f.read()).decode('utf-8')
    
    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Download Website Package</title>
    <link rel="stylesheet" href="https://cdn.replit.com/agent/bootstrap-agent-dark-theme.min.css">
    <style>
        body {{
            padding: 20px;
            background-color: #121212;
            color: #e0e0e0;
        }}
        .container {{
            max-width: 800px;
            margin: 0 auto;
        }}
        .card {{
            margin-top: 30px;
            margin-bottom: 30px;
            background-color: #1e1e1e;
            border: 1px solid #333;
        }}
        .btn-download {{
            margin-top: 20px;
        }}
        .file-info {{
            margin-bottom: 15px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1 class="mt-4 mb-3">Website Package Download</h1>
        
        <div class="card p-4">
            <h2>{zip_filename}</h2>
            <div class="file-info">
                <p><strong>Size:</strong> {size_kb:.1f} KB</p>
                <p><strong>Contains:</strong> HTML files, CSS, JavaScript, and assets from the website</p>
                <p><strong>Compatible with:</strong> Netlify Drop (direct upload)</p>
            </div>
            
            <p>This ZIP file contains a crawled website that's ready for deployment on Netlify.</p>
            
            <a href="data:application/zip;base64,{encoded_data}" 
               download="{zip_filename}" 
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
    
    with open(output_filename, 'w') as f:
        f.write(html_content)
    
    print(f"Created download page: {output_filename}")
    print(f"File size (Base64): {len(encoded_data) / 1024:.1f} KB")
    return True

if __name__ == "__main__":
    if len(sys.argv) > 1:
        zip_file = sys.argv[1]
    else:
        # Get the most recent zip file in the current directory
        zip_files = [f for f in os.listdir('.') if f.endswith('.zip')]
        if not zip_files:
            print("No zip files found in the current directory!")
            sys.exit(1)
        
        # Sort by modification time (newest first)
        zip_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        zip_file = zip_files[0]
    
    create_html_download_link(zip_file)