import urllib.request
import re

html = urllib.request.urlopen('http://localhost:8000/ui').read().decode('utf-8')
print("HTML length:", len(html))
print("Contains evidence modal:", "evidence-modal" in html)
