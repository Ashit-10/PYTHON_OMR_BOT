import os
import time
import shutil
import subprocess
import signal
import sys
import threading
import glob
from flask import Flask, send_from_directory, render_template_string, jsonify
import logging

class FilterRequests(logging.Filter):
    def filter(self, record):
        return "GET /" not in record.getMessage() and "POST /" not in record.getMessage()

log = logging.getLogger('werkzeug')
log.setLevel(logging.INFO)
log.addFilter(FilterRequests())

# Paths
# download_folder = "test"
download_folder = "/sdcard/Download"
input_folder = "temp_input"
output_folder = "temp_output"
error_folder = "error"

# Extensions to look for
extensions = ('.jpg', '.jpeg', '.png')

# Globals
processing = False
current_filename = ""
latest_output_filename = ""
error_occurred = False

app = Flask(__name__)

# Handle Ctrl+C
def signal_handler(sig, frame):
    print("\nStopped by user.")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

def get_latest_error_image():
    error_files = glob.glob(os.path.join(error_folder, "*"))
    error_files = [f for f in error_files if f.lower().endswith(extensions)]
    if not error_files:
        return None
    return max(error_files, key=os.path.getmtime)

def move_and_process(file_path):
    global processing, current_filename, latest_output_filename, error_occurred
    filename = os.path.basename(file_path)
    current_filename = filename
    processing = True
    error_occurred = False

    os.system("mkdir -p temp_input temp_output")

    os.system("rm -rf temp_input/*")
    os.system("rm -rf temp_output/*")
    shutil.move(file_path, os.path.join(input_folder, filename))
    print(f"Moved {filename} to input folder.")

    process = subprocess.Popen(
        ["python3", "autoapp.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    stdout, stderr = process.communicate()

    if stdout:
        print("Output from autoapp.py:")
        print(stdout)

    if stderr:
        print("Error from autoapp.py:", file=sys.stderr)
        print(stderr, file=sys.stderr)
        error_occurred = True
    if "fail" in str(stdout) or "fail" in str(stderr):
        error_occurred = True

    output_files = os.listdir(output_folder)
    output_files = [f for f in output_files if f.lower().endswith(extensions)]

    if output_files:
        latest_output_filename = output_files[-1]
        print(f"Processed output: {latest_output_filename}")
    else:
        error_file = get_latest_error_image()
        if error_occurred and error_file:
            dest = os.path.join(output_folder, os.path.basename(error_file))
            shutil.copy(error_file, dest)
            latest_output_filename = os.path.basename(error_file)
            print(f"Displayed error image: {latest_output_filename}")
        else:
            latest_output_filename = ""

    if error_occurred:
        error_file = get_latest_error_image()
        if error_file:
            dest = os.path.join(output_folder, os.path.basename(error_file))
            shutil.copy(error_file, dest)
            latest_output_filename = os.path.basename(error_file)
            print(f"Displayed error image: {latest_output_filename}")
        else:
            latest_output_filename = ""

    processing = False

def watch_folder():
    print("Watching for new OMR images...")
    already_seen = set()

    while True:
        # Process answer_key*.txt files
        try:
            key_files = [f for f in os.listdir(download_folder) if f.startswith("answer_key") and f.endswith(".txt")]
            for key_file in key_files:
                key_path = os.path.join(download_folder, key_file)
                shutil.move(key_path, "answer_key.txt")
                print(f"Moved answer key: {key_path}")
        except:
            pass
        try:
            files = [f for f in os.listdir(download_folder) if f.startswith("OMR_") and f.lower().endswith(extensions)]
            for file in files:
                full_path = os.path.join(download_folder, file)
                if full_path not in already_seen:
                    move_and_process(full_path)
                    already_seen.add(full_path)
            time.sleep(1)
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(1)

@app.route('/')
def index():
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>OMR Result Viewer</title>
        <style>
            .spinner {
                margin: 40px auto;
                width: 80px;
                height: 80px;
                border: 10px solid #f3f3f3;
                border-top: 10px solid #3498db;
                border-radius: 50%;
                animation: spin 1.2s linear infinite;
            }

            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }

            #loading {
                display: none;
                text-align: center;
            }

            body {
                text-align: center;
                font-family: Arial, sans-serif;
            }

            img {
                max-width: 95%;
                margin-top: 20px;
            }
        </style>

        <script>
            function checkProcessingStatus() {
                fetch("/status")
                    .then(response => response.json())
                    .then(data => {
                        if (data.processing) {
                            document.getElementById('status').innerText = "Processing " + data.filename + "...";
                            document.getElementById('loading').style.display = "block";
                            document.getElementById('result').style.display = "none";
                        } else if (data.filename) {
                            document.getElementById('status').innerText = "";
                            document.getElementById('loading').style.display = "none";
                            document.getElementById('result').style.display = "block";
                            document.getElementById('result').src = "/temp_output/" + data.filename + "?t=" + new Date().getTime();
                        } else {
                            document.getElementById('status').innerText = "No OMR sheet processed yet.";
                            document.getElementById('loading').style.display = "none";
                            document.getElementById('result').style.display = "none";
                        }
                    });
            }

            setInterval(checkProcessingStatus, 2000);
        </script>
    </head>
    <body>
        <h1>OMR Result Viewer</h1>
        <h2 id="status">Waiting for OMR sheet...</h2>

        <div id="loading">
            <div class="spinner"></div>
            <p>Processing... Please wait</p>
        </div>

        <img id="result" style="display:none;">
    </body>
    </html>
    ''')

@app.route('/status')
def status():
    global processing, current_filename, latest_output_filename
    return jsonify({
        "processing": processing,
        "filename": current_filename if processing else latest_output_filename
    })

@app.route('/temp_output/<path:filename>')
def serve_output_file(filename):
    return send_from_directory(output_folder, filename)

if __name__ == "__main__":
    threading.Thread(target=watch_folder, daemon=True).start()
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
