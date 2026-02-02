#!/bin/bash
# Quick setup script for Turkish Financial Data Scraper in DevContainer

set -e

echo "🚀 Setting up Turkish Financial Data Scraper in DevContainer..."

# Get the script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Step 1: Install Python dependencies
echo "📦 Installing Python dependencies..."
pip install -r requirements.txt

# Step 2: Create logs directory
echo "📁 Creating logs directory..."
mkdir -p logs

# Step 3: Check if .env exists, if not create from example
if [ ! -f .env ]; then
    echo "⚙️  Creating .env file from .env.example..."
    cp .env.example .env
    
    # Update .env with devcontainer-specific settings
    echo ""
    echo "📝 Updating .env with devcontainer settings..."
    
    # Use nuq-postgres as host
    sed -i 's/DB_HOST=localhost/DB_HOST=nuq-postgres/' .env
    
    # Use postgres defaults
    sed -i 's/DB_PORT=5432/DB_PORT=5432/' .env
    sed -i 's/DB_NAME=backtofuture/DB_NAME=backtofuture/' .env
    sed -i 's/DB_USER=backtofuture/DB_USER=postgres/' .env
    sed -i 's/DB_PASSWORD=back2future/DB_PASSWORD=postgres/' .env
    
    # Add schema if not present
    if ! grep -q "DB_SCHEMA" .env; then
        echo "" >> .env
        echo "# Database schema (isolates project tables)" >> .env
        echo "DB_SCHEMA=turkish_financial" >> .env
    fi
    
    # Add Firecrawl base URL for local API
    if ! grep -q "FIRECRAWL_BASE_URL" .env; then
        echo "" >> .env
        echo "# Use local Firecrawl API in devcontainer" >> .env
        echo "FIRECRAWL_BASE_URL=http://api:3002" >> .env
    fi
    
    echo "✅ .env file created and configured"
    echo ""
    echo "⚠️  IMPORTANT: Please edit .env and add your FIRECRAWL_API_KEY if needed"
    echo "   Or keep FIRECRAWL_BASE_URL=http://api:3002 for local Firecrawl API"
else
    echo "✅ .env file already exists, skipping..."
fi

# Step 4: Check database connection
echo ""
echo "🔍 Checking database connection..."
if python3 -c "
import psycopg2
import os
from dotenv import load_dotenv
load_dotenv()

try:
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST', 'nuq-postgres'),
        port=int(os.getenv('DB_PORT', '5432')),
        database=os.getenv('DB_NAME', 'postgres'),
        user=os.getenv('DB_USER', 'postgres'),
        password=os.getenv('DB_PASSWORD', 'postgres')
    )
    conn.close()
    print('✅ Database connection successful!')
except Exception as e:
    print(f'❌ Database connection failed: {e}')
    print('')
    print('💡 You may need to create the database:')
    print('   psql -h nuq-postgres -U postgres -d postgres -c \"CREATE DATABASE backtofuture;\"')
    exit(1)
" 2>/dev/null; then
    echo "✅ Database is accessible"
else
    echo "⚠️  Database connection check failed. You may need to create the database."
    echo "   Run: psql -h nuq-postgres -U postgres -d postgres -c \"CREATE DATABASE backtofuture;\""
fi

# Step 5: Test Python imports
echo ""
echo "🧪 Testing Python imports..."
if python3 -c "
try:
    from database.db_manager import DatabaseManager
    from scrapers.kap_scraper import KAPScraper
    from config import config
    print('✅ All imports successful!')
except ImportError as e:
    print(f'❌ Import error: {e}')
    exit(1)
" 2>/dev/null; then
    echo "✅ Python imports working correctly"
else
    echo "❌ Python import test failed"
    exit 1
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "📚 Next steps:"
echo "   1. Review and edit .env file if needed"
echo "   2. Create database if it doesn't exist:"
echo "      psql -h nuq-postgres -U postgres -d postgres -c \"CREATE DATABASE backtofuture;\""
echo "   3. Start the API server:"
echo "      python api_server.py"
echo "   4. Or run CLI commands:"
echo "      python main.py --scraper kap --days 7"
echo ""
echo "📖 See SETUP_DEVCONTAINER.md for detailed instructions"
