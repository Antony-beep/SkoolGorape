import json
from scrapling_fetcher import SkoolFetcher
from course_parser import CourseParser

fetcher = SkoolFetcher(cookies_path="hola.json", headless=True)
html = fetcher.fetch_page_html("https://www.skool.com/levantarte/calendar")
parser = CourseParser()
next_data = parser.extract_next_data(html)

if next_data:
    # Save the next_data to a file for inspection
    with open("calendar_data.json", "w", encoding="utf-8") as f:
        json.dump(next_data, f, indent=2)
    print("Calendar data saved to calendar_data.json")
else:
    print("Could not extract __NEXT_DATA__")
