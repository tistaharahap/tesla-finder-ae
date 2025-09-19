# Tesla Finder AE - Daily Tesla Digest Generator

A Pydantic AI-powered tool that fetches and summarizes Tesla listings from multiple car search websites daily, using advanced web scraping via MCP (Model Context Protocol) integration.

## Features

- **🔗 MCP Integration**: Uses Streamable HTTP MCP server for JavaScript-rendered web scraping
- **🤖 AI-Powered Analysis**: Claude-4-Sonnet agent specialized for Tesla listing extraction and summarization
- **📊 Consolidated Summary**: Single summary showing top 20 cheapest Tesla cars across all sources
- **🖱️ Clickable URLs**: Direct links to individual Tesla listings for instant access
- **🛣️ Mileage Display**: Vehicle mileage information for informed purchasing decisions
- **💰 AED Price Support**: Handles UAE Dirham pricing with intelligent parsing and sorting
- **🔄 Multi-Factor Sorting**: MongoDB-style sorting by (mileage ascending, price ascending, year descending)
- **📄 HTML Reports**: Beautiful Tailwind CSS reports with Tesla car images and interactive links
- **📈 Combined Metadata**: Aggregated price ranges, models, and locations from all sources
- **⚡ Concurrent Processing**: Parallel URL processing for efficient daily digests
- **🌐 Multi-Site Support**: Pre-configured for Dubai Dubizzle, CarSwitch, and Kavak
- **🔥 Logfire Observability**: Comprehensive tracing and spans for LLM operations, graph execution, and CLI interactions

## Architecture

Built with:
- **Pydantic AI**: Agent framework with native MCP toolset integration
- **Pydantic Graph**: State-based execution graph for reliable workflows
- **MCP Server**: `https://bhinneka-mcp.bango29.com/mcp` for web scraping with JS rendering
- **Typer**: CLI interface for daily operation

## Installation

```bash
# Set up environment
export OPENAI_API_KEY="your-openai-api-key"

# Install dependencies (handled by uv/rye)
# Dependencies include pydantic-ai[mcp] for MCP integration
```

## Usage

### CLI Commands

```bash
# Generate daily digest from all configured URLs
python -m src.tesla_finder_ae.main digest

# Save digest to JSON file
python -m src.tesla_finder_ae.main digest --output-file tesla_digest.json

# Generate beautiful HTML report with car images
python -m src.tesla_finder_ae.main digest --html-report

# Generate HTML report with custom path
python -m src.tesla_finder_ae.main digest --html-report --html-output custom_report.html

# Analyze single URL
python -m src.tesla_finder_ae.main search "https://dubai.dubizzle.com/motors/used-cars/tesla/..."

# Use custom URLs for digest
python -m src.tesla_finder_ae.main digest --custom-urls "url1,url2,url3"

# List configured URLs
python -m src.tesla_finder_ae.main urls-list
```

### Programmatic Usage

```python
from src.tesla_finder_ae.nodes import (
    search_tesla_listings,
    generate_consolidated_daily_tesla_digest
)

# Analyze single URL
summary = await search_tesla_listings("https://dubai.dubizzle.com/...")

# Generate consolidated daily digest with top 20 cheapest cars
urls = ["url1", "url2", "url3"]
consolidated = await generate_consolidated_daily_tesla_digest(urls)

# Generate HTML report
from tesla_finder_ae.html_generator import generate_tesla_html_report
html_content = generate_tesla_html_report(consolidated)
```

## Output Structure

### Consolidated Summary (New Default)
```python
class TeslaConsolidatedSummary(BaseModel):
    source_urls: List[str]              # All URLs processed
    total_listings_found: int           # Total across all sources
    global_price_range: str             # "AED 45,000 - AED 285,000"
    all_models: List[str]               # Unique models from all sources
    all_locations: List[str]            # Unique locations from all sources
    top_cheapest_cars: List[TeslaListing]  # Top 20 sorted by (mileage ASC, price ASC, year DESC)
    summary: str                        # Human-readable consolidated summary
    analyzed_at: datetime
```

### Example CLI Output
```
🎯 TESLA MARKET SUMMARY - UAE DIRHAM (AED)
==========================================================================================
📅 Analysis Date: 2024-01-15 14:30:22
🔗 Sources Analyzed: 3 URLs
🏷️  Total Listings Found: 47
💰 Global Price Range: AED 85,000 - AED 285,000
🚙 Available Models: Model 3, Model S, Model X, Model Y
📍 Available Locations: Dubai, Abu Dhabi, Sharjah

🏆 TOP 20 TESLA CARS (SORTED BY MILEAGE):
------------------------------------------------------------------------------------------
   1. Tesla Model 3 Standard Range Plus   -   AED 85,000 (2021) | 45,000 km - Dubai
      🔗 https://dubai.dubizzle.com/motors/used-cars/tesla/model-3/2024/tesla-model-3-standard

   2. Tesla Model Y Long Range            -  AED 125,000 (2022) | 28K miles - Abu Dhabi
      🔗 https://carswitch.com/uae/used-cars/tesla-model-y-long-range-2022

   3. Tesla Model S Plaid                 -  AED 285,000 (2023) | Mileage unknown - Sharjah
      🔗 https://www.kavak.com/ae/preowned/tesla-model-s-plaid-2023

   4. Tesla Model 3 Performance           -  AED 155,000 (2021) | 35,000 km - Dubai
      🔗 https://dubai.dubizzle.com/motors/tesla-model-3-performance-2021

   5. Tesla Model Y Standard Range        -  AED 165,000 (2022) | 22,500 km - Abu Dhabi
      🔗 https://carswitch.com/uae/used-cars/tesla-model-y-standard-2022
   ...
   [Showing top 20 cheapest Tesla cars with full details]

📋 DETAILED ANALYSIS:
------------------------------------------------------------
Tesla Market Analysis Summary with individual listing URLs and mileage information...
```

## Pre-configured URLs

1. **Dubai Dubizzle**: Tesla listings 2021-2026, sorted by price ascending
2. **CarSwitch UAE**: Tesla search 2021-2025, price low to high
3. **Kavak UAE**: Tesla pre-owned 2021-2024, lowest price first

## HTML Report Generation

### Beautiful Tesla Car Listings with Images

The HTML report feature generates gorgeous, responsive web pages featuring Tesla car listings with:

**Visual Features**:
- **Tesla Car Images**: Main photo for each listing with automatic fallback for missing images
- **Tailwind CSS Styling**: Modern, responsive design that works on all devices  
- **Tesla-themed Design**: Red and dark gray color scheme matching Tesla branding
- **Interactive Elements**: Clickable "View Listing" buttons and smooth hover effects

**Content Organization**:
- **Market Statistics**: Overview cards showing sources, total listings, price ranges
- **Sorted Car Grid**: Responsive grid layout showing cars sorted by (mileage, price, year)
- **Detailed Car Cards**: Each car displays title, price badge, year, mileage, location, and image
- **Direct Links**: Clickable buttons to view original Tesla listings

**Technical Implementation**:
- **Single HTML File**: All CSS/JS embedded, loads from CDNs (Tailwind CSS)
- **Mobile-First Design**: Responsive breakpoints for phones, tablets, desktops
- **Fast Loading**: Optimized images with placeholder fallbacks
- **Accessibility**: Semantic HTML, ARIA labels, keyboard navigation

**Usage Examples**:
```bash
# Generate HTML report in public/tesla_digest.html
python -m src.tesla_finder_ae.main digest --html-report

# Custom HTML output location  
python -m src.tesla_finder_ae.main digest --html-report --html-output reports/tesla_cars.html

# Combined JSON + HTML output
python -m src.tesla_finder_ae.main digest --output-file data.json --html-report
```

**Sample HTML Output Structure**:
- **Header**: Tesla Market Analysis title with generation timestamp
- **Statistics Bar**: 4 key metrics cards (sources, listings, featured cars, price range)  
- **Market Overview**: Available models and locations summary
- **Car Grid**: Responsive grid of Tesla car cards with images and details
- **Footer**: Generation info and data source attribution

## Sorting Algorithm

### Multi-Factor Sorting (MongoDB-style)

The consolidated summary uses intelligent multi-factor sorting to prioritize Tesla listings:

**Sorting Criteria** (in order of priority):
1. **Mileage (Ascending)**: Lowest mileage cars first
2. **Price (Ascending)**: Among same-mileage cars, cheapest first  
3. **Year (Descending)**: Among same mileage and price, newer models first

**Example Sorting Behavior**:
```
Input: 
- AED 50,000, 2020, 30,000 km
- AED 50,000, 2022, 15,000 km  
- AED 40,000, 2019, 45,000 km
- AED 80,000, 2023, 5,000 km

Output:
1. AED 80,000, 2023, 5,000 km   (lowest mileage wins)
2. AED 40,000, 2019, 45,000 km  (same mileage, cheapest price)
3. AED 50,000, 2022, 15,000 km  (same mileage, higher price, newer year)
4. AED 50,000, 2020, 30,000 km  (higher mileage)
```

**Price Parsing**: Handles "AED 45,000", "65K AED", "Call for price"  
**Mileage Parsing**: Supports "45,000 km", "28K miles" (auto-converts to km)  
**Year Extraction**: From `year` field or extracted from listing titles

## Implementation Details

### Graph Node Architecture
- **`FetchAndSummarizeTesla`**: Single node that handles both web scraping and AI summarization
- **`TeslaSearchState`**: Session state management with message history
- **Lazy Loading**: Agent creation deferred until runtime to avoid API key requirements during import

### MCP Integration
- Uses `MCPServerStreamableHTTP` for proper Pydantic AI MCP client integration
- JavaScript rendering enabled for dynamic content extraction
- Automatic tool selection by the AI agent for optimal scraping strategy

### Error Handling
- Graceful failure handling for individual URLs
- Exception isolation in concurrent processing
- Detailed error reporting with source URL identification

## Observability with Logfire

### Comprehensive Tracing & Spans

The application includes full **Pydantic AI + Logfire** integration providing visibility into:

**🤖 LLM Operations**:
- Agent creation and configuration  
- Tool calls and responses
- Model requests/responses with token usage
- Error handling and retries
- MCP server interactions

**📊 Graph Execution**:
- Node-level spans with timing
- State management tracking
- Concurrent operation coordination
- Success/failure metrics

**⚙️ CLI Operations**:
- Command execution traces
- Batch processing metrics
- File I/O operations
- User interaction logging

### Trace Examples

```bash
# All operations automatically traced
python -m src.tesla_finder_ae.main digest

# Logfire console output shows:
16:42:20.714 🔥 Logfire configured for Tesla Finder AE
16:42:20.718 🚀 Tesla Finder AE CLI Starting  
16:42:20.719 📊 Starting Tesla batch processing
16:42:22.156 🎯 Tesla analysis completed
16:42:22.891 ✅ Tesla batch processing completed
```

### Local Development

Logfire runs in **development mode** by default:
- Console output enabled
- No cloud authentication required  
- Local trace collection
- Full instrumentation active

### Production Setup

For production monitoring:
1. Run `logfire auth` to authenticate
2. Set `TESLA_FINDER_ENV=production`
3. Configure cloud trace shipping
4. Set up dashboards and alerts

## Daily Workflow

Perfect for automation with full observability:
1. Run `digest` command daily via cron with full tracing
2. Monitor execution health via Logfire dashboards
3. Track performance trends and success rates
4. Get alerts on failures or performance degradation
5. Analyze Tesla market trends through structured logs