from flask import Flask, send_file, jsonify
import os
import glob

app = Flask(__name__)

@app.route('/api/zip-files')
def list_files():
    """List all ZIP files in the current directory."""
    try:
        # Get a list of all ZIP files in the current directory
        zip_files = glob.glob('*.zip')
        
        # Get file info
        files = []
        for zip_file in zip_files:
            size_bytes = os.path.getsize(zip_file)
            size_kb = size_bytes / 1024
            files.append({
                'name': zip_file,
                'size_bytes': size_bytes,
                'size_kb': f"{size_kb:.1f} KB",
                'date': os.path.getmtime(zip_file)
            })
        
        return jsonify({'files': files})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/download/<filename>')
def download_file(filename):
    """Download a specific ZIP file."""
    if not filename.endswith('.zip'):
        return jsonify({'error': 'Only ZIP files can be downloaded'}), 400
    
    file_path = os.path.join(os.getcwd(), filename)
    
    if os.path.exists(file_path):
        try:
            return send_file(file_path, as_attachment=True)
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    else:
        return jsonify({'error': 'File not found'}), 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)