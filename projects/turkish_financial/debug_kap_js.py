"""Debug: test JS fetch() with bypass_proxy=True (no ScraperAPI)."""
import asyncio
import logging
import json
import re

logging.basicConfig(level=logging.INFO)

from scrapers.kap_scraper import KAPScraper

async def main():
    s = KAPScraper()
    BASE_URL = 'https://www.kap.org.tr'
    full_api_url = f'{BASE_URL}/tr/api/memberDisclosureQuery'
    body = {'fromDate': '2026-06-25', 'toDate': '2026-06-29'}

    body_js = json.dumps(json.dumps(body))
    fetch_options = (
        'method:"POST",'
        'headers:{"Content-Type":"application/json","Accept":"application/json"},'
        'credentials:"same-origin",'
        f'body:{body_js}'
    )
    js_script = (
        '(async()=>{'
        'try{'
        'const ac=new AbortController();'
        "const tid=setTimeout(()=>ac.abort(new Error('fetch timeout 30s')),30000);"
        'let r;'
        'try{'
        f'r=await fetch({json.dumps(full_api_url)},{{{fetch_options},signal:ac.signal}});'
        '}finally{clearTimeout(tid);}'
        'const t=await r.text();'
        'let el=document.getElementById("__kap_api_result");'
        'if(!el){el=document.createElement("pre");el.id="__kap_api_result";'
        'document.documentElement.appendChild(el);}'
        'el.setAttribute("data-status",String(r.status));'
        'el.textContent=t;'
        '}catch(e){'
        'let el=document.getElementById("__kap_api_result");'
        'if(!el){el=document.createElement("pre");el.id="__kap_api_result";'
        'document.documentElement.appendChild(el);}'
        'el.setAttribute("data-error",e.message||String(e));'
        '}'
        '})()'
    )

    actions = [
        {'type': 'wait', 'milliseconds': 5000},
        {'type': 'executeJavascript', 'script': js_script},
        {'type': 'wait', 'milliseconds': 10000},
        {'type': 'scrape'},
    ]

    print('\n=== Testing JS fetch() WITH bypass_proxy=True (no ScraperAPI) ===')
    result = await s.scrape_with_actions(
        url=f'{BASE_URL}/tr/Bildirimler',
        actions=actions,
        formats=['rawHtml'],
        proxy='basic',
        bypass_proxy=True,
        timeout=120000,
        only_main_content=False,
    )
    print(f'success={result.get("success")}')
    data = result.get('data') or {}
    raw = data.get('rawHtml') or data.get('raw_html', '')
    print(f'rawHtml length={len(raw or "")}')

    m = re.search(r'<pre[^>]*id=["\']__kap_api_result["\'][^>]*>(.*?)</pre>', raw or '', re.DOTALL | re.IGNORECASE)
    if m:
        whole = raw[m.start():m.end()]
        content = m.group(1).strip()
        print(f'Tag: {whole[:300]}')
        print(f'Content (first 400): {content[:400]}')
    else:
        print('No __kap_api_result found')

asyncio.run(main())
