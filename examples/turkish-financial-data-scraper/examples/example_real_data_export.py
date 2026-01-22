"""
Example: Export real KAP data from database to files
Shows all the data that was scraped and saved to database
"""
import asyncio
import logging
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from database.db_manager import DatabaseManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def export_kap_reports_to_files(output_dir="/root/kap_export"):
    """
    Export all real KAP reports from database to files
    Shows where the actual data is stored
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    db = DatabaseManager()
    conn = db.get_connection()
    cur = conn.cursor()
    
    # Get all KAP reports
    cur.execute("""
        SELECT id, company_code, company_name, report_type, report_date, 
               title, summary, data, scraped_at
        FROM kap_reports 
        ORDER BY scraped_at DESC
    """)
    
    reports = cur.fetchall()
    logger.info(f"Found {len(reports)} KAP reports in database")
    
    # Export to JSON file
    json_path = Path(output_dir) / "kap_reports.json"
    data_export = []
    
    for report in reports:
        report_dict = {
            "id": report[0],
            "company_code": report[1],
            "company_name": report[2],
            "report_type": report[3],
            "report_date": str(report[4]) if report[4] else None,
            "title": report[5],
            "summary": report[6],
            "scraped_at": str(report[8]),
        }
        
        # Add data if available
        if report[7]:
            if isinstance(report[7], dict):
                report_dict["data"] = report[7]
            else:
                report_dict["data_text"] = str(report[7])[:200]  # Preview
        
        data_export.append(report_dict)
    
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data_export, f, indent=2, ensure_ascii=False, default=str)
    
    logger.info(f"Exported {len(data_export)} reports to {json_path}")
    
    # Create summary file
    summary_path = Path(output_dir) / "summary.txt"
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("KAP Reports Database Export Summary\n")
        f.write("=" * 50 + "\n\n")
        f.write(f"Total reports: {len(reports)}\n")
        f.write(f"Export date: {Path.cwd()}\n")
        f.write(f"Export location: {output_dir}\n\n")
        
        f.write("Companies in database:\n")
        cur.execute("SELECT DISTINCT company_code, company_name FROM kap_reports ORDER BY company_code")
        for code, name in cur.fetchall():
            f.write(f"  - {code}: {name}\n")
    
    logger.info(f"Created summary at {summary_path}")
    
    # Create CSV export
    csv_path = Path(output_dir) / "kap_reports.csv"
    with open(csv_path, "w", encoding="utf-8") as f:
        # Header
        f.write("ID,Company Code,Company Name,Report Type,Report Date,Title,Summary,Scraped At\n")
        
        # Data
        for report in reports:
            company_code = (report[1] or "").replace(",", ";")
            company_name = (report[2] or "").replace(",", ";")
            title = (report[5] or "").replace(",", ";")
            summary = (report[6] or "").replace(",", ";")[:100]
            
            f.write(f"{report[0]},{company_code},{company_name},{report[3] or ''},"
                   f"{report[4] or ''},{title},{summary},{report[8]}\n")
    
    logger.info(f"Created CSV export at {csv_path}")
    
    # Show file sizes
    logger.info("\nExported files:")
    for path in [json_path, summary_path, csv_path]:
        if path.exists():
            size = path.stat().st_size
            logger.info(f"  {path.name}: {size:,} bytes")
    
    cur.close()
    db.return_connection(conn)
    
    return {
        "success": True,
        "total_reports": len(reports),
        "export_dir": output_dir,
        "files": {
            "json": str(json_path),
            "csv": str(csv_path),
            "summary": str(summary_path)
        }
    }


def show_database_status():
    """Show all data in database"""
    db = DatabaseManager()
    conn = db.get_connection()
    cur = conn.cursor()
    
    # List all tables and their row counts
    cur.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema='public'
        ORDER BY table_name
    """)
    
    tables = [t[0] for t in cur.fetchall()]
    
    logger.info("\n" + "="*60)
    logger.info("DATABASE STATUS")
    logger.info("="*60)
    logger.info(f"Database: firecrawl (PostgreSQL)\n")
    logger.info("Tables and record counts:")
    
    for table in tables:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        count = cur.fetchone()[0]
        logger.info(f"  {table:40s}: {count:>6,} records")
    
    logger.info("="*60 + "\n")
    
    cur.close()
    db.return_connection(conn)


if __name__ == "__main__":
    # Show database status
    show_database_status()
    
    # Export real KAP data to files
    logger.info("Exporting real KAP reports to files...\n")
    result = export_kap_reports_to_files(output_dir="/root/kap_export")
    
    if result['success']:
        logger.info(f"\n✓ Export complete!")
        logger.info(f"  Total reports exported: {result['total_reports']}")
        logger.info(f"  Export directory: {result['export_dir']}")
        logger.info(f"\nYou can find the data here:")
        for name, path in result['files'].items():
            logger.info(f"  {name.upper()}: {path}")
