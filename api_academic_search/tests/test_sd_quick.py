from firecrawl import FirecrawlApp
app = FirecrawlApp(api_url='http://localhost:3002', api_key='fc-USER_API_KEY')

# Test direct article access
url = 'https://www.sciencedirect.com/science/article/pii/S0960148124014496'
print(f"Scraping: {url}")

result = app.scrape(url, formats=['markdown', 'links'], wait_for=3000)

print(f"\nType of result: {type(result)}")
print(f"Result attributes: {[a for a in dir(result) if not a.startswith('_')]}")

if hasattr(result, 'metadata') and result.metadata:
    print(f"\nMetadata type: {type(result.metadata)}")
    print(f"Metadata attrs: {[a for a in dir(result.metadata) if not a.startswith('_')]}")
    # Try to access as attributes
    if hasattr(result.metadata, 'title'):
        print(f"Title: {result.metadata.title}")

if hasattr(result, 'links') and result.links:
    print(f"\nLinks found: {len(result.links)}")

if hasattr(result, 'markdown') and result.markdown:
    print(f"\nMarkdown length: {len(result.markdown)}")
    print("\nFirst 2000 chars of content:")
    print("-" * 50)
    print(result.markdown[:2000])
