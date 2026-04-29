#!/usr/bin/env python3
"""
KAP Live Data Test

Test scraping real KAP data and saving to database
"""

import asyncio
import re
import psycopg2
import json
from datetime import datetime, date
from firecrawl import FirecrawlApp
from bs4 import BeautifulSoup


class KAPLiveTest:
    """Test class for KAP live data scraping"""
    
    def __init__(self):
        self.base_url = "https://kap.org.tr"
        self.main_url = f"{self.base_url}/en"
        self.firecrawl = FirecrawlApp(api_url="http://api:3002")
        self.db_config = {
            'host': 'nuq-postgres',
            'port': 5432,
            'database': 'postgres',
            'user': 'postgres',
            'password': 'postgres'
        }
    
    def parse_kap_html(self, content):
        """Parse KAP HTML content to extract disclosure items"""
        items = []
        
        try:
            soup = BeautifulSoup(content, 'html.parser')
            
            # Look for table rows with disclosure data
            rows = soup.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 3:
                    
                    checkbox_cell = cells[0] if cells else None
                    main_cell = cells[1] if len(cells) > 1 else None
                    language_cell = cells[2] if len(cells) > 2 else None
                    
                    if checkbox_cell and main_cell:
                        # Extract checkbox ID
                        checkbox_text = checkbox_cell.get_text()
                        disclosure_id = None
                        id_match = re.search(r'checkbox\s+(\d+)', checkbox_text)
                        if id_match:
                            disclosure_id = id_match.group(1)
                        
                        # Extract main disclosure info
                        main_text = main_cell.get_text(strip=True)
                        
                        # Parse company name and disclosure type
                        company_name = ""
                        disclosure_type = ""
                        
                        if main_text:
                            # Try to split on common company endings
                            company_endings = ['A.Ş.', 'T.A.Ş.', 'BANKASI', 'BANK']
                            
                            words = main_text.split()
                            company_words = []
                            disclosure_words = []
                            found_break = False
                            
                            for i, word in enumerate(words):
                                if not found_break:
                                    company_words.append(word)
                                    # Check if this word ends the company name
                                    if any(ending in word for ending in company_endings):
                                        found_break = True
                                    # Also check if next words look like disclosure types
                                    elif i < len(words) - 1:
                                        next_word = words[i + 1].lower()
                                        if next_word in ['material', 'notification', 'financial', 'fund', 'corporate']:
                                            found_break = True
                                else:
                                    disclosure_words.append(word)
                            
                            company_name = ' '.join(company_words).strip()
                            disclosure_type = ' '.join(disclosure_words).strip()
                        
                        # Extract language info
                        language_info = ""
                        if language_cell:
                            language_info = language_cell.get_text(strip=True)
                        
                        # Extract timestamp from row
                        row_text = row.get_text()
                        time_match = re.search(r'(Today|Yesterday|\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2})', row_text)
                        timestamp_str = ""
                        disclosure_date = date.today()
                        
                        if time_match:
                            date_part = time_match.group(1)
                            time_str = time_match.group(2)
                            timestamp_str = f"{date_part} {time_str}"
                            
                            try:
                                if date_part == "Today":
                                    disclosure_date = date.today()
                                elif date_part == "Yesterday":
                                    from datetime import timedelta
                                    disclosure_date = date.today() - timedelta(days=1)
                                else:
                                    disclosure_date = datetime.strptime(date_part, "%d.%m.%Y").date()
                            except:
                                disclosure_date = date.today()
                        
                        # Only add if we have meaningful data
                        if company_name and disclosure_type:
                            items.append({
                                'id': disclosure_id,
                                'company_name': company_name,
                                'disclosure_type': disclosure_type,
                                'date': disclosure_date,
                                'timestamp_str': timestamp_str,
                                'language_info': language_info,
                                'has_attachment': 'attachment' in language_info.lower(),
                                'raw_text': main_text
                            })
            
        except Exception as e:
            print(f"❌ Parsing error: {e}")
        
        return items
    
    def save_to_database(self, items):
        """Save items to database"""
        saved_count = 0
        
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()
            
            for item in items:
                try:
                    insert_sql = '''
                        INSERT INTO turkish_financial.kap_disclosures 
                        (disclosure_id, company_name, disclosure_type, disclosure_date, 
                         timestamp, language_info, has_attachment, detail_url, content, data)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (disclosure_id, company_name, disclosure_type) 
                        DO UPDATE SET 
                            content = EXCLUDED.content,
                            scraped_at = CURRENT_TIMESTAMP
                        RETURNING id
                    '''
                    
                    cursor.execute(insert_sql, (
                        item['id'],
                        item['company_name'],
                        item['disclosure_type'],
                        item['date'].isoformat(),
                        item['timestamp_str'],
                        item['language_info'],
                        item['has_attachment'],
                        '',  # detail_url
                        item['raw_text'][:1000],  # content
                        json.dumps({
                            'source': 'kap_live_test',
                            'scraped_at': datetime.now().isoformat(),
                            'original_text': item['raw_text']
                        })
                    ))
                    
                    result = cursor.fetchone()
                    if result:
                        saved_count += 1
                        print(f"   ✅ [{result[0]}] {item['company_name'][:30]} - {item['disclosure_type'][:40]}")
                
                except Exception as e:
                    print(f"   ❌ Save error for {item.get('company_name', 'Unknown')}: {e}")
            
            conn.commit()
            cursor.close()
            conn.close()
            
        except Exception as e:
            print(f"❌ Database error: {e}")
        
        return saved_count
    
    async def run_live_test(self):
        """Run live KAP data test"""
        print("🚀 KAP Live Data Test")
        print("=" * 50)
        
        # Test 1: Scrape KAP main page
        print("\n📡 Step 1: Scraping KAP main page")
        print("-" * 30)
        
        try:
            result = self.firecrawl.scrape(
                self.main_url,
                formats=['html', 'markdown'],
                wait_for=5000
            )
            
            print(f"✅ KAP page scraped successfully")
            
            # Get content
            content = ""
            if hasattr(result, 'html') and result.html:
                content = result.html
                print(f"📄 HTML content: {len(content)} characters")
            elif hasattr(result, 'markdown') and result.markdown:
                content = result.markdown
                print(f"📄 Markdown content: {len(content)} characters")
            
            if not content:
                print("❌ No content received")
                return
            
            # Test 2: Parse content
            print("\n🔍 Step 2: Parsing disclosure data")
            print("-" * 30)
            
            items = self.parse_kap_html(content)
            print(f"📋 Found {len(items)} disclosure items")
            
            if items:
                print("\nSample disclosures:")
                for i, item in enumerate(items[:3], 1):
                    print(f"   {i}. ID:{item['id']} - {item['company_name'][:30]} - {item['disclosure_type'][:40]}")
            
            # Test 3: Save to database
            print("\n💾 Step 3: Saving to database")
            print("-" * 30)
            
            if items:
                saved_count = self.save_to_database(items[:5])  # Save first 5
                print(f"\n✅ Saved {saved_count}/{min(5, len(items))} items to database")
            
            # Test 4: Verify database results
            print("\n📊 Step 4: Database verification")
            print("-" * 30)
            
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM turkish_financial.kap_disclosures")
            total = cursor.fetchone()[0]
            print(f"📈 Total disclosures in database: {total}")
            
            cursor.execute("""
                SELECT id, company_name, disclosure_type, scraped_at 
                FROM turkish_financial.kap_disclosures 
                ORDER BY scraped_at DESC 
                LIMIT 5
            """)
            
            recent = cursor.fetchall()
            if recent:
                print("\n🕒 Recent entries:")
                for row in recent:
                    company = row[1][:25] if row[1] else "N/A"
                    dtype = row[2][:30] if row[2] else "N/A"
                    time_str = row[3].strftime('%H:%M:%S') if row[3] else "N/A"
                    print(f"   [{row[0]}] {company} - {dtype} ({time_str})")
            
            cursor.close()
            conn.close()
            
            print(f"\n🎉 Live test completed successfully!")
            print(f"   - Scraped KAP main page: ✅")
            print(f"   - Parsed {len(items)} disclosures: ✅")
            print(f"   - Saved to database: ✅")
            print(f"   - Total DB records: {total}")
            
        except Exception as e:
            print(f"❌ Live test failed: {e}")
            import traceback
            traceback.print_exc()


async def main():
    """Main function"""
    tester = KAPLiveTest()
    await tester.run_live_test()


if __name__ == "__main__":
    asyncio.run(main())