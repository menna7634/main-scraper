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
        response = requests.get(website_url, headers=headers, timeout=5)
        response.raise_for_status()

        email_pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
        emails = re.findall(email_pattern, response.text)

        return emails[0] if emails else None
    except requests.exceptions.RequestException:
        return None

def scrape_google_maps(search_query):
    """Scrapes Google Maps search results for businesses and extracts websites/emails separately."""
    global stop_scraping, scraping_count
    stop_scraping = False  
    scraping_count = 0  

    safe_filename = f"{search_query.replace(' ', '_')}.csv"
    file_path = os.path.join(SCRAPING_DIR, safe_filename)

    results = []  

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f'https://www.google.com/maps/search/{search_query}/', wait_until="domcontentloaded")

        try:
            page.wait_for_selector("form:nth-child(2)", timeout=5000)
            page.click("form:nth-child(2)")
        except:
            pass

        scrollable_div = page.query_selector('div[role="feed"]')
        previous_count = 0
        same_count_times = 0  

        while True:
            if stop_scraping:
                print("Scraping stopped by user!")
                browser.close()
                return  

            items = page.query_selector_all('div[role="feed"] > div > div[jsaction]')
            current_count = len(items)

            if current_count == previous_count:
                same_count_times += 1  
                if same_count_times >= 10:  # Increase the number of checks before stopping
                    break
            else:
                same_count_times = 0  

            previous_count = current_count

            page.evaluate("(scrollable_div) => scrollable_div.scrollBy(0, 2000);", scrollable_div)
            time.sleep(3)  # Increase sleep time to avoid blocking

        print("No more new results found, stopping scrolling...")

        for item in items:
            if stop_scraping:
                break  

            data = {
                "Business Name": item.query_selector(".fontHeadlineSmall") and item.query_selector(".fontHeadlineSmall").text_content(),
                "Address": item.query_selector('.W4Efsd > span:last-of-type span[dir="ltr"]') and item.query_selector('.W4Efsd > span:last-of-type span[dir="ltr"]').text_content(),
                "Category": item.query_selector('.W4Efsd > span:first-child span') and item.query_selector('.W4Efsd > span:first-child span').text_content().strip(),
                "Google Maps Link": item.query_selector("a") and item.query_selector("a").get_attribute('href'),
                "Phone Number": item.query_selector('.UsdlK') and item.query_selector('.UsdlK').text_content(),
                "Rating": item.query_selector('.MW4etd') and item.query_selector('.MW4etd').text_content(),
                "Number of Reviews": item.query_selector('.UY7F9 span[dir="ltr"]') and item.query_selector('.UY7F9 span[dir="ltr"]').text_content().strip("()")
            }

            if data['Business Name']:
                results.append(data)
                scraping_count += 1  
                socketio.emit("update_count", {"count": scraping_count})  

        browser.close()

    print("Basic business details extracted. Now extracting websites and emails...")
    print("scraping count" ,scraping_count )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        pages = [context.new_page() for _ in range(min(5, len(results)))]  

        def extract_website_and_email(business, page):
            if stop_scraping:
                return

            google_maps_link = business.get("Google Maps Link")
            if google_maps_link:
                print("google maps link" , google_maps_link)
                try:
                    page.goto(google_maps_link, wait_until="domcontentloaded", timeout=7000)
                    website_element = page.query_selector('a.CsEnBe')
                    website_url = website_element.get_attribute('href') if website_element else None
                    business["Website"] = website_url
                    business["Email"] = extract_email_from_website(website_url) if website_url else None
                except:
                    business["Website"] = None
                    business["Email"] = None

        for i, business in enumerate(results):
            if stop_scraping:
                break

            page = pages[i % len(pages)]  
            extract_website_and_email(business, page)

        browser.close()

    df = pd.DataFrame(results)
    df.to_csv(file_path, index=False, encoding="utf-8-sig")

    if not stop_scraping:
        socketio.emit("scraping_done", {"filename": safe_filename})  

    print(f"Scraping completed! {scraping_count} items saved.")
    return safe_filename

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

if __name__ == "__main__":
    socketio.run(app, debug=True)
