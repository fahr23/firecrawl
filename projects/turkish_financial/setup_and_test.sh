#!/bin/bash
# Setup and test script for devcontainer
# Installs dependencies and runs tests

set -e

echo "=========================================="
echo "🔧 Setting up Turkish Financial Data Scraper"
echo "=========================================="
echo ""

# Navigate to project directory
# Navigate to project directory (using current directory)
current_dir=$(pwd)
echo "📂 Working in: $current_dir"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔌 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "=========================================="
echo "✅ Setup complete!"
echo "=========================================="
echo ""

# Run tests
echo "🧪 Running service tests..."
echo ""
python3 test_devcontainer_services.py

echo ""
echo "=========================================="
echo "📋 Next Steps:"
echo "=========================================="
echo ""
echo "1. Start API server:"
echo "   source venv/bin/activate"
echo "   python3 api_server.py"
echo ""
echo "2. Test API:"
echo "   curl http://localhost:8000/api/v1/health"
echo ""
echo "3. Run scraper:"
echo "   python3 main.py --scraper kap --days 7"
echo ""
