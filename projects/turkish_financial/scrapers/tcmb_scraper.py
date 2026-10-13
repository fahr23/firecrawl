import logging
import requests
from scrapers.base_scraper import BaseScraper
from database.db_manager import DatabaseManager

logger = logging.getLogger(__name__)

class TCMBScraper(BaseScraper):
    """
    Scraper for TCMB (Central Bank of the Republic of Turkey) EVDS API.
    Used for retrieving macroeconomic indicators.

    Fails closed (FA-00): without an EVDS API key, no data is fetched, no rows
    are written, and the caller gets an honest `unavailable` result — never a
    fabricated or placeholder value.
    """
    def __init__(self, db_manager: DatabaseManager, api_key: str = None):
        super().__init__(db_manager)
        self.api_key = api_key

    async def scrape(self, indicator: str, start_date: str, end_date: str) -> dict:
        """
        Scrape macroeconomic data from TCMB EVDS.

        Returns a result dict with `success: False` and `status: "unavailable"`
        when no API key is configured or the upstream call fails — zero rows are
        ever written in that case.
        """
        logger.info(f"Starting TCMB scrape for {indicator} between {start_date} and {end_date}")

        if not self.api_key:
            logger.warning("No TCMB EVDS API key configured; returning unavailable (FA-00).")
            return {
                "success": False,
                "status": "unavailable",
                "indicator": indicator,
                "records_fetched": 0,
                "records_saved": 0,
                "detail": "TCMB EVDS API key is not configured.",
            }

        headers = {"key": self.api_key}
        url = f"https://evds2.tcmb.gov.tr/service/evds/series={indicator}&startDate={start_date}&endDate={end_date}&type=json"
        results = []
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            for item in data.get("items", []):
                val = item.get(indicator)
                date_str = item.get("Tarih")
                if val and date_str:
                    # Convert DD-MM-YYYY to YYYY-MM-DD
                    parts = date_str.split("-")
                    iso_date = f"{parts[2]}-{parts[1]}-{parts[0]}"
                    try:
                        val_float = float(val)
                        results.append({
                            "indicator_code": indicator,
                            "date": iso_date,
                            "value": val_float
                        })
                    except ValueError:
                        pass
        except Exception as e:
            logger.error(f"Failed to fetch TCMB data: {e}")
            return {
                "success": False,
                "status": "unavailable",
                "indicator": indicator,
                "records_fetched": 0,
                "records_saved": 0,
                "detail": "TCMB EVDS upstream request failed.",
            }

        # Save to DB
        saved_count = 0
        if results:
            conn = self.db_manager.get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("SET search_path TO turkish_financial,public;")
                for r in results:
                    try:
                        cursor.execute("""
                            INSERT INTO tcmb_macro_data (indicator_code, date, value)
                            VALUES (%s, %s, %s)
                            ON CONFLICT (indicator_code, date)
                            DO UPDATE SET value = EXCLUDED.value, scraped_at = CURRENT_TIMESTAMP
                        """, (r["indicator_code"], r["date"], r["value"]))
                        saved_count += 1
                    except Exception as e:
                        logger.error(f"Failed to insert TCMB data: {e}")
                conn.commit()
            finally:
                self.db_manager.return_connection(conn)

        return {
            "success": True,
            "status": "ok" if saved_count else "partial",
            "indicator": indicator,
            "records_fetched": len(results),
            "records_saved": saved_count
        }
