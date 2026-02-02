import requests
import json

api_key = '7e0c8c4ed4e0fb320d69074f093779d9'

print('='*60)
print('Testing ScienceDirect API...')
print('='*60)
headers = {
    'X-ELS-APIKey': api_key,
    'Accept': 'application/json'
}
url = 'https://api.elsevier.com/content/search/sciencedirect'
params = {'query': 'title-abs-key("neural networks")', 'count': 2}

try:
    response = requests.get(url, headers=headers, params=params, timeout=15)
    print(f'Status: {response.status_code}')
    print(f'X-ELS-Status: {response.headers.get("X-ELS-Status")}')
    
    if response.status_code == 200:
        data = response.json()
        results = data.get('search-results', {})
        total = results.get('opensearch:totalResults', '0')
        print(f'Total Results: {total}')
        
        entries = results.get('entry', [])
        print(f'Returned: {len(entries)} entries')
        if entries:
            print('\nFirst entry:')
            entry = entries[0]
            print(f"  Title: {entry.get('dc:title', 'N/A')}")
            print(f"  DOI: {entry.get('prism:doi', 'N/A')}")
            print(f"  Date: {entry.get('prism:coverDate', 'N/A')}")
    else:
        print(f'Error: {response.text[:300]}')
except Exception as e:
    print(f'Exception: {e}')

print('\n' + '='*60)
print('Testing Scopus API...')
print('='*60)
url2 = 'https://api.elsevier.com/content/search/scopus'
params2 = {'query': 'neural networks', 'count': 2}

try:
    response2 = requests.get(url2, headers=headers, params=params2, timeout=10)
    print(f'Status: {response2.status_code}')
    print(f'X-ELS-Status: {response2.headers.get("X-ELS-Status")}')
    
    if response2.status_code == 200:
        data2 = response2.json()
        results2 = data2.get('search-results', {})
        total2 = results2.get('opensearch:totalResults', '0')
        print(f'Total Results: {total2}')
        
        entries2 = results2.get('entry', [])
        print(f'Returned: {len(entries2)} entries')
        if entries2:
            print('\nFirst entry:')
            entry2 = entries2[0]
            print(f"  Title: {entry2.get('dc:title', 'N/A')}")
            print(f"  DOI: {entry2.get('prism:doi', 'N/A')}")
            print(f"  Date: {entry2.get('prism:coverDate', 'N/A')}")
    else:
        print(f'Error: {response2.text[:300]}')
except Exception as e:
    print(f'Exception: {e}')
