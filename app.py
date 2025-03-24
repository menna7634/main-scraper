import os
from flask import Flask, jsonify, render_template, request, send_file, redirect, send_from_directory, url_for, session
from scraper import scrape_google_maps

app = Flask(__name__)

SCRAPING_DIR = "Results"
os.makedirs(SCRAPING_DIR, exist_ok=True)
is_scraping = False
@app.route("/", methods=["GET", "POST"])
def index():   
    csv_path = None
    if request.method == "POST":
        search_query = request.form.get("query")
        if search_query:
            csv_path = scrape_google_maps(search_query)
    return render_template("index.html", csv_path=csv_path)


@app.route("/download/<filename>")
def download(filename):
    file_path = os.path.join(SCRAPING_DIR, filename)
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    return jsonify({"error": "File not found"}), 404




@app.route('/logo.png')
def serve_logo():
    return send_from_directory('templates', 'logo.png')


if __name__ == "__main__":
 port = int(os.environ.get("PORT", 8080))
 app.run(host="0.0.0.0", port=port)