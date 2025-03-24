import os
import time
import re
import requests
import pandas as pd
from flask import Flask, render_template, request, send_from_directory, jsonify
from flask_socketio import SocketIO
from playwright.sync_api import sync_playwright  

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

SCRAPING_DIR = "Results"
os.makedirs(SCRAPING_DIR, exist_ok=True)

stop_scraping = False  
scraping_count = 0  

def extract_email_from_website(website_url):
    """Extracts an email address from a website's HTML content."""
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(website_url, headers=headers, timeout=10)
        response.raise_for_status()

        email_pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
        emails = re.findall(email_pattern, response.text)

        return emails[0] if emails else None
    except requests.exceptions.RequestException:
        return None

def scrape_google_maps(search_query):
    """Scrapes Google Maps search results for businesses."""
    global stop_scraping, scraping_count
    stop_scraping = False  
    scraping_count = 0  

    safe_filename = f"{search_query.replace(' ', '_')}.csv"
    file_path = os.path.join(SCRAPING_DIR, safe_filename)

    # Start Playwright session
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True) 
        page = browser.new_page()
        page.goto(f'https://www.google.com/maps/search/{search_query}/')

        try:
            page.wait_for_selector("form:nth-child(2)", timeout=5000)
            page.click("form:nth-child(2)")
        except Exception:
            pass

        scrollable_div = page.query_selector('div[role="feed"]')

        for _ in range(15):  # Scrolling 15 times
            if stop_scraping:
                print("Scraping stopped by user!")
                browser.close()
                return  
            page.evaluate("""(scrollable_div) => {
                scrollable_div.scrollBy(0, 1000);
            }""", scrollable_div)
            time.sleep(1)

        items = page.query_selector_all('div[role="feed"] > div > div[jsaction]')

        results = []
        for index, item in enumerate(items):
            if stop_scraping:
                print("Scraping interrupted, stopping...")
                break  

            data = {}
            try:
                data['Business Name'] = item.query_selector(".fontHeadlineSmall").text_content()
            except:
                data['Business Name'] = None

            try:
                data['Address'] = item.query_selector('.W4Efsd > span:last-of-type span[dir="ltr"]').text_content()
            except:
                data['Address'] = None

            try:
                category_element = item.query_selector('.W4Efsd > span:first-child span')
                data['Category'] = category_element.text_content().strip() if category_element else None
            except:
                data['Category'] = None

            try:
                data['Google Maps Link'] = item.query_selector("a").get_attribute('href')
            except:
                data['Google Maps Link'] = None

            try:
                website_element = item.query_selector('a.lcr4fd.S9kvJb')
                website_url = website_element.get_attribute('href')
                if website_url:
                    data['Website'] = website_url
                    data["Email"] = extract_email_from_website(website_url)
                else:
                    data['Website'] = None
                    data['Email'] = None 
            except:
                data['Website'] = None
                data['Email'] = None

            try:
                data['Phone Number'] = item.query_selector('.UsdlK').text_content()
            except:
                data['Phone Number'] = None

            try:
                data['Rating'] = item.query_selector('.MW4etd').text_content()
            except:
                data['Rating'] = None

            try:
                num_reviews_element = item.query_selector('.UY7F9 span[dir="ltr"]')
                data['Number of Reviews'] = num_reviews_element.text_content().strip("()") 
            except:
                data['Number of Reviews'] = None

            if data['Business Name']:
                results.append(data)
                scraping_count += 1  
                socketio.emit("update_count", {"count": scraping_count})  # Emit updated count to client

        df = pd.DataFrame(results)
        df.to_csv(file_path, index=False, encoding="utf-8-sig")

        browser.close()

    if not stop_scraping:
        socketio.emit("scraping_done", {"filename": safe_filename})  # Emit event when scraping is done

    print(f"Scraping completed! {scraping_count} items saved.")
    return safe_filename

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/start_scraping", methods=["POST"])
def start_scraping():
    search_query = request.form.get("query")
    socketio.start_background_task(scrape_google_maps, search_query)
    return jsonify({"message": "Scraping started!"})

@app.route("/stop_scraping", methods=["POST"])
def stop_scraping_func():
    global stop_scraping
    stop_scraping = True
    return jsonify({"message": "Scraping stopping in progress..."})

@app.route("/download/<filename>")
def download(filename):
    return send_from_directory(SCRAPING_DIR, filename, as_attachment=True)

if __name__ == "__main__":
    socketio.run(app, debug=True)
