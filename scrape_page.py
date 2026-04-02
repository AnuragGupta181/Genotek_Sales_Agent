# from bs4 import BeautifulSoup
# import requests
# import os
# from urllib.parse import urljoin

# # Base URL
# base_url = "https://jocular-lamington-998d7a.netlify.app/"

# # Create output folder
# output_folder = "scraped_pages"
# os.makedirs(output_folder, exist_ok=True)

# # Fetch main page
# response = requests.get(base_url)
# soup = BeautifulSoup(response.text, "html.parser")

# # Get all links
# links = set()

# for link in soup.find_all("a"):
#     href = link.get("href")

#     if href:
#         full_url = urljoin(base_url, href)

#         # Only keep links from same site
#         if base_url in full_url:
#             links.add(full_url)

# # Add homepage itself
# links.add(base_url)

# print(f"Found {len(links)} pages")

# # Visit each page
# for url in links:
#     try:
#         print(f"Scraping: {url}")

#         res = requests.get(url)
#         page_soup = BeautifulSoup(res.text, "html.parser")

#         # Extract readable text
#         # text = page_soup.get_text(separator="\n", strip=True)
#         for tag in page_soup(["script", "style"]):
#             tag.decompose()

#         text = page_soup.get_text(separator="\n", strip=True)

#         # Create safe filename
#         filename = url.replace(base_url, "")
#         filename = filename.strip("/")

#         if filename == "":
#             filename = "home"

#         filename = filename.replace("/", "_")

#         file_path = os.path.join(output_folder, f"{filename}.txt")

#         # Save text
#         with open(file_path, "w", encoding="utf-8") as f:
#             f.write(text)

#         print(f"Saved → {file_path}")

#     except Exception as e:
#         print(f"Failed: {url}")
#         print(e)

from bs4 import BeautifulSoup
import requests

url = "https://jocular-lamington-998d7a.netlify.app/flowchart"

# Fetch page
response = requests.get(url)

# Parse HTML
soup = BeautifulSoup(response.text, "html.parser")

# Remove scripts/styles
for tag in soup(["script", "style"]):
    tag.decompose()

# Try extracting structured content
content_blocks = []

# Extract headings
for heading in soup.find_all(["h1", "h2", "h3", "h4"]):
    text = heading.get_text(strip=True)
    if text:
        content_blocks.append(text)

# Extract list items (very important for this page)
for li in soup.find_all("li"):
    text = li.get_text(strip=True)
    if text:
        content_blocks.append(text)

# Extract paragraph text
for p in soup.find_all("p"):
    text = p.get_text(strip=True)
    if text:
        content_blocks.append(text)

# Save output
with open("flowchart.txt", "w", encoding="utf-8") as f:
    for line in content_blocks:
        f.write(line + "\n")

print("Saved full flowchart content to flowchart.txt")
print(f"Extracted {len(content_blocks)} text blocks")