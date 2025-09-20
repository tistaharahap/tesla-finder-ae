"""
HTML Report Generator for Tesla Finder AE

Generates beautiful HTML reports from Tesla consolidated summaries using Tailwind CSS.
"""
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Optional
from urllib.parse import urlparse

import logfire
from tesla_finder_ae.nodes import (
    TeslaConsolidatedSummary,
    parse_mileage_to_numeric,
    parse_price_to_numeric,
)


def generate_tesla_listings_json(
    consolidated_summary: TeslaConsolidatedSummary,
    output_path: Optional[Path] = None
) -> str:
    """
    Generate JSON data file for Tesla listings
    
    Args:
        consolidated_summary: Tesla market analysis results
        output_path: Optional path to save JSON file (defaults to public/listings.json)
    
    Returns:
        Path to the generated JSON file as string
    """
    with logfire.span(
        "Tesla JSON Data Generation",
        total_listings=len(consolidated_summary.all_sorted_listings),
        sources_count=len(consolidated_summary.source_urls)
    ) as json_span:
        
        # Set default output path
        if output_path is None:
            output_path = Path("public/listings.json")
        
        # Generate JSON structure optimized for frontend consumption
        json_data = {
            "metadata": {
                "generatedAt": consolidated_summary.analyzed_at.isoformat(),
                "totalListings": consolidated_summary.total_listings_found,
                "sourcesAnalyzed": len(consolidated_summary.source_urls),
                "globalPriceRange": consolidated_summary.global_price_range,
                "availableModels": consolidated_summary.all_models,
                "availableLocations": consolidated_summary.all_locations,
                "sourceUrls": consolidated_summary.source_urls,
                "sortingCriteria": "Balance Score ASC (Z-score based sweet spot analysis)"
            },
            "listings": []
        }

        # Aggregate helpers for enhanced reporting
        source_stats = defaultdict(lambda: {"count": 0, "prices": [], "mileages": []})
        model_counts = {model: 0 for model in consolidated_summary.all_models}
        model_counts["Other"] = 0
        valid_prices_for_range = []
        valid_mileages_for_range = []
        search_models = sorted(consolidated_summary.all_models, key=len, reverse=True)

        # Add all sorted listings with proper structure
        for i, listing in enumerate(consolidated_summary.all_sorted_listings, 1):
            numeric_price = parse_price_to_numeric(listing.price)
            price_numeric = numeric_price if numeric_price > 0 else None

            mileage_numeric = (
                parse_mileage_to_numeric(listing.mileage)
                if listing.mileage is not None
                else None
            )
            if mileage_numeric is not None and mileage_numeric >= 999_999:
                mileage_numeric = None

            source_domain = "unattributed"
            if listing.url:
                parsed_url = urlparse(listing.url)
                source_domain = parsed_url.netloc.lower() or "unattributed"
                if source_domain.startswith("www."):
                    source_domain = source_domain[4:]

            title_lower = listing.title.lower()
            matched_model = next(
                (model for model in search_models if model.lower() in title_lower),
                None,
            )
            model_key = matched_model if matched_model else "Other"
            model_counts[model_key] += 1

            source_entry = source_stats[source_domain]
            source_entry["count"] += 1
            if price_numeric is not None:
                source_entry["prices"].append(price_numeric)
                valid_prices_for_range.append(price_numeric)
            if mileage_numeric is not None:
                source_entry["mileages"].append(mileage_numeric)
                valid_mileages_for_range.append(mileage_numeric)

            listing_data = {
                "id": i,
                "title": listing.title,
                "price": listing.price,
                "year": listing.year,
                "mileage": listing.mileage,
                "location": listing.location,
                "url": listing.url,
                "imageUrl": listing.image_url if listing.image_url else f"https://via.placeholder.com/400x300/1f2937/ffffff?text=Tesla+Image+{i}",
                # Z-score based scoring information
                "balanceScore": round(listing.composite_score, 2) if listing.composite_score is not None else None,
                "balanceRating": listing.balance_rating,
                "priceZScore": round(listing.price_z_score, 2) if listing.price_z_score is not None else None,
                "yearZScore": round(listing.year_z_score, 2) if listing.year_z_score is not None else None,
                "mileageZScore": round(listing.mileage_z_score, 2) if listing.mileage_z_score is not None else None,
                "priceNumeric": price_numeric,
                "mileageNumeric": mileage_numeric,
                "source": source_domain,
                "modelLabel": model_key,
                "hasImage": bool(listing.image_url),
            }
            json_data["listings"].append(listing_data)

        # Derive aggregate statistics for enhanced client visualizations
        price_stats = {
            "min": round(min(valid_prices_for_range)) if valid_prices_for_range else None,
            "max": round(max(valid_prices_for_range)) if valid_prices_for_range else None,
            "average": round(mean(valid_prices_for_range)) if valid_prices_for_range else None,
        }

        mileage_stats = {
            "min": round(min(valid_mileages_for_range)) if valid_mileages_for_range else None,
            "max": round(max(valid_mileages_for_range)) if valid_mileages_for_range else None,
            "average": round(mean(valid_mileages_for_range)) if valid_mileages_for_range else None,
        }

        model_distribution = [
            {"model": model, "count": count}
            for model, count in model_counts.items()
            if count > 0 or model == "Other"
        ]

        source_breakdown = []
        for source, stats in source_stats.items():
            prices = stats["prices"]
            mileages = stats["mileages"]
            source_breakdown.append(
                {
                    "source": source,
                    "listingCount": stats["count"],
                    "averagePrice": round(mean(prices)) if prices else None,
                    "medianPrice": round(median(prices)) if prices else None,
                    "minPrice": round(min(prices)) if prices else None,
                    "maxPrice": round(max(prices)) if prices else None,
                    "averageMileage": round(mean(mileages)) if mileages else None,
                }
            )

        source_breakdown.sort(key=lambda entry: entry["listingCount"], reverse=True)

        json_data["metadata"].update(
            {
                "priceStats": price_stats,
                "mileageStats": mileage_stats,
                "modelDistribution": model_distribution,
                "sourceBreakdown": source_breakdown,
            }
        )

        # Convert to JSON string
        json_content = json.dumps(json_data, indent=2, ensure_ascii=False)
        
        # Save JSON file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(json_content)
        
        json_span.set_attributes({
            "json_generated": True,
            "output_path": str(output_path),
            "file_size_bytes": len(json_content),
            "listings_count": len(consolidated_summary.all_sorted_listings),
            "metadata_included": True
        })
        
        logfire.info(
            "✅ Tesla JSON data generated successfully",
            output_path=str(output_path),
            file_size_bytes=len(json_content),
            listings_count=len(consolidated_summary.all_sorted_listings)
        )
        
        return str(output_path)


def generate_tesla_html_report(
    consolidated_summary: TeslaConsolidatedSummary,
    output_path: Optional[Path] = None
) -> str:
    """
    Generate static HTML template that loads Tesla data via XHR
    
    Args:
        consolidated_summary: Tesla market analysis results (used for metadata only)
        output_path: Optional path to save HTML file (defaults to public/index.html)
    
    Returns:
        Path to the generated HTML file as string
    """
    with logfire.span(
        "Tesla HTML Template Generation",
        sources_count=len(consolidated_summary.source_urls)
    ) as html_span:
        
        # Set default output path
        if output_path is None:
            output_path = Path("public/index.html")
        
        # Generate timestamp for report
        timestamp = consolidated_summary.analyzed_at.strftime('%Y-%m-%d %H:%M:%S')
        
        # Generate complete static HTML template with XHR loading
        html_content = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Tesla Market Analysis Report - {timestamp}</title>
    
    <!-- Tailwind CSS from CDN -->
    <script src="https://cdn.tailwindcss.com"></script>
    <!-- Chart.js for data visualizations -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    
    <!-- Custom Tesla-themed configuration -->
    <script>
        tailwind.config = {{
            theme: {{
                extend: {{
                    colors: {{
                        'tesla-red': '#dc2626',
                        'tesla-dark': '#1f2937',
                        'tesla-light': '#f8fafc'
                    }}
                }}
            }}
        }}
    </script>
    
    <!-- Additional styles -->
    <style>
        .line-clamp-2 {{
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }}
        
        .loading-spinner {{
            animation: spin 1s linear infinite;
        }}

        @keyframes spin {{
            from {{ transform: rotate(0deg); }}
            to {{ transform: rotate(360deg); }}
        }}

        .filter-label {{
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}

        .filter-help {{
            font-size: 0.75rem;
        }}

        .chart-container {{
            position: relative;
            height: 18rem;
        }}
    </style>
</head>
<body class="bg-gray-50 min-h-screen">
    <!-- Header Section -->
    <header class="bg-tesla-dark text-white py-8">
        <div class="container mx-auto px-4">
            <div class="text-center">
                <h1 class="text-4xl md:text-6xl font-bold mb-2">🚗 Tesla Market Analysis</h1>
                <p class="text-xl md:text-2xl text-gray-300">UAE Dirham (AED) Pricing Report</p>
                <div id="generation-time" class="mt-4 inline-flex items-center px-4 py-2 bg-tesla-red rounded-full">
                    <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3a2 2 0 012-2h4a2 2 0 012 2v4m-6 9l6 6 6-6" />
                    </svg>
                    <span class="font-semibold">Loading...</span>
                </div>
            </div>
        </div>
    </header>

    <!-- Filter & Sort Controls -->
    <section class="py-6 bg-tesla-light">
        <div class="container mx-auto px-4">
            <div class="bg-white rounded-xl shadow-lg p-6">
                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                    <div>
                        <p class="filter-label text-gray-500 font-semibold mb-2">Model</p>
                        <select id="model-filter" class="w-full px-3 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-tesla-red transition" disabled>
                            <option selected>Loading models...</option>
                        </select>
                    </div>
                    <div>
                        <p class="filter-label text-gray-500 font-semibold mb-2">Price Range (AED)</p>
                        <div class="flex items-center space-x-3">
                            <input id="price-min" type="number" class="w-full px-3 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-tesla-red transition" placeholder="Min" disabled>
                            <span class="text-gray-400">to</span>
                            <input id="price-max" type="number" class="w-full px-3 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-tesla-red transition" placeholder="Max" disabled>
                        </div>
                        <p class="filter-help text-gray-500 mt-2">Active: <span id="price-range-display" class="font-medium">Loading...</span></p>
                    </div>
                    <div>
                        <p class="filter-label text-gray-500 font-semibold mb-2">Mileage</p>
                        <select id="mileage-filter" class="w-full px-3 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-tesla-red transition" disabled>
                            <option selected>Loading mileage...</option>
                        </select>
                    </div>
                    <div>
                        <p class="filter-label text-gray-500 font-semibold mb-2">Sort</p>
                        <div class="flex flex-col space-y-3">
                            <div class="flex space-x-3">
                                <select id="sort-key" class="w-full px-3 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-tesla-red transition" disabled>
                                    <option selected>Loading options...</option>
                                </select>
                                <button id="sort-order" data-direction="asc" class="px-3 py-2 bg-tesla-dark text-white rounded-lg flex items-center justify-center space-x-2 disabled:opacity-50" disabled>
                                    <span id="sort-order-icon">⬆️</span>
                                </button>
                            </div>
                            <button id="reset-filters" class="px-3 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-100 transition disabled:opacity-50" disabled>
                                Reset filters
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </section>
    
    <!-- Statistics Section -->
    <section class="py-12 bg-white">
        <div class="container mx-auto px-4">
            <div id="statistics-container" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                <!-- Loading placeholders -->
                <div class="text-center p-6 bg-gradient-to-r from-gray-400 to-gray-500 rounded-xl text-white animate-pulse">
                    <div class="text-3xl font-bold">...</div>
                    <div class="text-gray-100">Loading...</div>
                </div>
                <div class="text-center p-6 bg-gradient-to-r from-gray-400 to-gray-500 rounded-xl text-white animate-pulse">
                    <div class="text-3xl font-bold">...</div>
                    <div class="text-gray-100">Loading...</div>
                </div>
                <div class="text-center p-6 bg-gradient-to-r from-gray-400 to-gray-500 rounded-xl text-white animate-pulse">
                    <div class="text-3xl font-bold">...</div>
                    <div class="text-gray-100">Loading...</div>
                </div>
                <div class="text-center p-6 bg-gradient-to-r from-gray-400 to-gray-500 rounded-xl text-white animate-pulse">
                    <div class="text-2xl font-bold">...</div>
                    <div class="text-gray-100">Loading...</div>
                </div>
            </div>
        </div>
    </section>
    
    <!-- Market Overview -->
    <section class="py-8 bg-gray-100">
        <div class="container mx-auto px-4">
            <div id="market-overview" class="grid grid-cols-1 lg:grid-cols-2 gap-8">
                <div class="bg-white p-6 rounded-xl shadow-lg">
                    <h3 class="text-xl font-bold text-gray-900 mb-4 flex items-center">
                        <svg class="w-6 h-6 mr-2 text-tesla-red" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                        </svg>
                        Available Models
                    </h3>
                    <p id="available-models" class="text-gray-700 leading-relaxed">Loading models...</p>
                </div>
                
                <div class="bg-white p-6 rounded-xl shadow-lg">
                    <h3 class="text-xl font-bold text-gray-900 mb-4 flex items-center">
                        <svg class="w-6 h-6 mr-2 text-tesla-red" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                        </svg>
                        Available Locations
                    </h3>
                    <p id="available-locations" class="text-gray-700 leading-relaxed">Loading locations...</p>
                </div>
            </div>
        </div>
    </section>

    <!-- Source Insights Section -->
    <section class="py-10 bg-white">
        <div class="container mx-auto px-4">
            <div class="flex items-center justify-between mb-6">
                <h3 class="text-2xl font-bold text-gray-900">Source Performance Overview</h3>
                <p class="text-sm text-gray-500">Breakdown by listing origin with price and mileage signals.</p>
            </div>
            <div id="source-breakdown" class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
                <div class="p-6 bg-gradient-to-r from-gray-400 to-gray-500 rounded-xl text-white animate-pulse">
                    <div class="text-lg font-semibold">Loading source metrics...</div>
                </div>
            </div>
        </div>
    </section>

    <!-- Loading State -->
    <div id="loading-section" class="py-12 text-center">
        <div class="container mx-auto px-4">
            <div class="loading-spinner w-12 h-12 border-4 border-tesla-red border-t-transparent rounded-full mx-auto mb-4"></div>
            <p class="text-lg text-gray-600">Loading Tesla listings...</p>
        </div>
    </div>
    
    <!-- Error State -->
    <div id="error-section" class="py-12 text-center hidden">
        <div class="container mx-auto px-4">
            <div class="text-red-500 text-6xl mb-4">⚠️</div>
            <h3 class="text-2xl font-bold text-gray-900 mb-4">Failed to Load Tesla Data</h3>
            <p class="text-gray-600 mb-4">There was an error loading the Tesla listings data.</p>
            <button onclick="loadTeslaData()" class="px-6 py-3 bg-tesla-red text-white rounded-lg hover:bg-red-700 transition-colors">
                Try Again
            </button>
        </div>
    </div>
    
    <!-- Main Cars Section -->
    <section id="cars-section" class="py-12 hidden">
        <div class="container mx-auto px-4">
            <div class="text-center mb-12">
                <h2 class="text-3xl md:text-4xl font-bold text-gray-900 mb-4">
                    🎯 Tesla Sweet Spot Analysis (Balance Score Sorting)
                </h2>
                <p class="text-lg text-gray-600 max-w-3xl mx-auto">
                    Complete Tesla market overview using Z-score analysis to find cars closest to the statistical sweet spot.
                    Cars with better balance scores represent optimal combinations of price, year, and mileage - avoiding extremes in any category.
                </p>
                <div class="mt-4">
                    <span id="total-listings-badge" class="inline-flex items-center px-4 py-2 bg-tesla-red text-white rounded-full font-semibold">
                        Loading listings count...
                    </span>
                </div>
                <div class="mt-3">
                    <p id="filter-summary" class="text-sm text-gray-500">Loading filters...</p>
                </div>
            </div>
            
            <!-- Cars Grid -->
            <div id="cars-grid" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
                <!-- Cars will be loaded here by JavaScript -->
            </div>
            <div id="cars-empty-state" class="hidden text-center py-12">
                <div class="max-w-xl mx-auto bg-white border border-dashed border-gray-300 rounded-xl p-8">
                    <div class="text-5xl mb-4">🤔</div>
                    <h3 class="text-xl font-semibold text-gray-900 mb-2">No listings match your filters</h3>
                    <p class="text-gray-600 mb-4">Try widening the price or mileage range, or reset the filters to view all available Tesla listings.</p>
                    <button id="empty-reset" class="px-4 py-2 bg-tesla-dark text-white rounded-lg hover:bg-black transition">
                        Reset filters
                    </button>
                </div>
            </div>
        </div>
    </section>

    <!-- Analytics Section -->
    <section id="analytics-section" class="py-12 bg-gray-100 hidden">
        <div class="container mx-auto px-4">
            <div class="text-center mb-10">
                <h2 class="text-3xl font-bold text-gray-900 mb-2">Market Analytics</h2>
                <p class="text-gray-600 max-w-2xl mx-auto">Visualize price distribution and model availability across the filtered dataset.</p>
            </div>
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-8">
                <div class="bg-white rounded-xl shadow-lg p-6">
                    <div class="flex items-center justify-between mb-4">
                        <h3 class="text-xl font-semibold text-gray-900">Price Distribution</h3>
                        <span class="text-sm text-gray-500" id="price-chart-summary">Loading...</span>
                    </div>
                    <div class="chart-container">
                        <canvas id="price-distribution-chart"></canvas>
                        <div id="price-chart-empty" class="absolute inset-0 flex items-center justify-center text-gray-400 text-sm hidden">
                            No price data available for charting.
                        </div>
                    </div>
                </div>
                <div class="bg-white rounded-xl shadow-lg p-6">
                    <div class="flex items-center justify-between mb-4">
                        <h3 class="text-xl font-semibold text-gray-900">Model Mix</h3>
                        <span class="text-sm text-gray-500" id="model-chart-summary">Loading...</span>
                    </div>
                    <div class="chart-container">
                        <canvas id="model-distribution-chart"></canvas>
                        <div id="model-chart-empty" class="absolute inset-0 flex items-center justify-center text-gray-400 text-sm hidden">
                            Model data will appear once listings load.
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </section>
    
    <!-- Footer -->
    <footer class="bg-tesla-dark text-white py-8">
        <div class="container mx-auto px-4 text-center">
            <p class="text-lg mb-2">⚡ Tesla Finder AE - AI-Powered Tesla Market Analysis</p>
            <p id="footer-timestamp" class="text-gray-400">Loading timestamp...</p>
            <div class="mt-4 text-sm text-gray-500">
                <p id="footer-sources">Loading source information...</p>
            </div>
        </div>
    </footer>
    
    <!-- JavaScript for data loading and rendering -->
    <script>
        let teslaData = null;
        let filteredListings = [];
        let filtersInitialized = false;
        const state = {{
            filters: {{
                model: 'all',
                price: {{ min: null, max: null }},
                mileage: 'all'
            }},
            sort: {{ key: 'balanceScore', direction: 'asc' }},
            defaults: null
        }};
        const charts = {{ price: null, model: null }};
        const palette = ['#dc2626', '#1f2937', '#2563eb', '#f97316', '#16a34a', '#9333ea', '#0ea5e9'];

        async function loadTeslaData() {{
            try {{
                const response = await fetch('listings.json', {{ cache: 'no-store' }});
                if (!response.ok) {{
                    throw new Error(`Failed to fetch listings.json: ${{response.status}}`);
                }}
                teslaData = await response.json();
                renderTeslaData();
            }} catch (error) {{
                console.error('Failed to load Tesla data', error);
                document.getElementById('loading-section').classList.add('hidden');
                const errorSection = document.getElementById('error-section');
                errorSection.classList.remove('hidden');
                errorSection.querySelector('p.text-gray-600').textContent = 'There was an error loading Tesla listings. Please refresh and try again.';
            }}
        }}

        function renderTeslaData() {{
            if (!teslaData) {{
                return;
            }}

            const {{ metadata, listings }} = teslaData;

            document.getElementById('generation-time').innerHTML = `
                <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3a2 2 0 012-2h4a2 2 0 012 2v4m-6 9l6 6 6-6" />
                </svg>
                <span class="font-semibold">Generated: ${{new Date(metadata.generatedAt).toLocaleString()}}</span>
            `;

            renderStatistics(listings);
            renderMarketOverview(metadata);

            document.getElementById('footer-timestamp').textContent = `Generated at ${{new Date(metadata.generatedAt).toLocaleString()}} with comprehensive market data`;
            document.getElementById('footer-sources').textContent = `Data sourced from ${{metadata.sourcesAnalyzed}} trusted automotive platforms`;

            document.getElementById('loading-section').classList.add('hidden');
            document.getElementById('error-section').classList.add('hidden');
            document.getElementById('cars-section').classList.remove('hidden');
            document.getElementById('analytics-section').classList.remove('hidden');

            initializeFilters();
            applyFiltersAndSort();
        }}

        function initializeFilters() {{
            if (filtersInitialized || !teslaData) {{
                return;
            }}

            const {{ metadata }} = teslaData;
            const modelFilter = document.getElementById('model-filter');
            const priceMinInput = document.getElementById('price-min');
            const priceMaxInput = document.getElementById('price-max');
            const mileageFilter = document.getElementById('mileage-filter');
            const sortKeySelect = document.getElementById('sort-key');
            const sortOrderButton = document.getElementById('sort-order');
            const resetButton = document.getElementById('reset-filters');
            const emptyResetButton = document.getElementById('empty-reset');

            const priceMin = metadata.priceStats?.min ?? 0;
            const priceMax = metadata.priceStats?.max ?? 0;

            state.filters.model = 'all';
            state.filters.price = {{ min: priceMin, max: priceMax }};
            state.filters.mileage = 'all';
            state.sort = {{ key: 'balanceScore', direction: 'asc' }};
            state.defaults = {{
                model: 'all',
                price: {{ min: priceMin, max: priceMax }},
                mileage: 'all',
                sort: {{ key: 'balanceScore', direction: 'asc' }}
            }};

            modelFilter.innerHTML = '<option value="all">All models</option>' +
                metadata.availableModels.map(model => `<option value="${{model}}">${{model}}</option>`).join('');
            modelFilter.disabled = false;

            priceMinInput.value = priceMin ? Math.round(priceMin) : '';
            priceMaxInput.value = priceMax ? Math.round(priceMax) : '';
            priceMinInput.disabled = false;
            priceMaxInput.disabled = false;
            updatePriceRangeDisplay();

            mileageFilter.innerHTML = `
                <option value="all">Any mileage</option>
                <option value="low">Under 50,000 km</option>
                <option value="mid">50,000 - 100,000 km</option>
                <option value="high">Over 100,000 km</option>
                <option value="unknown">Mileage unknown</option>
            `;
            mileageFilter.value = 'all';
            mileageFilter.disabled = false;

            sortKeySelect.innerHTML = `
                <option value="balanceScore">Balance score (best value)</option>
                <option value="price">Price</option>
                <option value="year">Year</option>
                <option value="mileage">Mileage</option>
                <option value="title">Title</option>
            `;
            sortKeySelect.value = 'balanceScore';
            sortKeySelect.disabled = false;

            sortOrderButton.dataset.direction = 'asc';
            document.getElementById('sort-order-icon').textContent = '⬆️';
            sortOrderButton.disabled = false;

            resetButton.disabled = false;
            if (emptyResetButton) {{
                emptyResetButton.disabled = false;
            }}

            modelFilter.addEventListener('change', event => {{
                state.filters.model = event.target.value;
                applyFiltersAndSort();
            }});

            function handlePriceInputChange() {{
                const minValue = Number(priceMinInput.value || priceMin);
                const maxValue = Number(priceMaxInput.value || priceMax);
                state.filters.price.min = Math.min(minValue, maxValue);
                state.filters.price.max = Math.max(minValue, maxValue);
                updatePriceRangeDisplay();
                applyFiltersAndSort();
            }}

            priceMinInput.addEventListener('input', handlePriceInputChange);
            priceMaxInput.addEventListener('input', handlePriceInputChange);

            mileageFilter.addEventListener('change', event => {{
                state.filters.mileage = event.target.value;
                applyFiltersAndSort();
            }});

            sortKeySelect.addEventListener('change', event => {{
                state.sort.key = event.target.value;
                applyFiltersAndSort();
            }});

            sortOrderButton.addEventListener('click', () => {{
                state.sort.direction = state.sort.direction === 'asc' ? 'desc' : 'asc';
                sortOrderButton.dataset.direction = state.sort.direction;
                document.getElementById('sort-order-icon').textContent = state.sort.direction === 'asc' ? '⬆️' : '⬇️';
                applyFiltersAndSort();
            }});

            resetButton.addEventListener('click', () => {{
                resetFilters();
            }});

            if (emptyResetButton) {{
                emptyResetButton.addEventListener('click', () => {{
                    resetFilters();
                }});
            }}

            filtersInitialized = true;
        }}

        function resetFilters() {{
            const {{ defaults }} = state;
            if (!defaults) {{
                return;
            }}

            state.filters.model = defaults.model;
            state.filters.price = {{ ...defaults.price }};
            state.filters.mileage = defaults.mileage;
            state.sort = {{ ...defaults.sort }};

            document.getElementById('model-filter').value = defaults.model;
            document.getElementById('price-min').value = defaults.price.min ? Math.round(defaults.price.min) : '';
            document.getElementById('price-max').value = defaults.price.max ? Math.round(defaults.price.max) : '';
            document.getElementById('mileage-filter').value = defaults.mileage;
            document.getElementById('sort-key').value = defaults.sort.key;
            const sortOrderButton = document.getElementById('sort-order');
            sortOrderButton.dataset.direction = defaults.sort.direction;
            document.getElementById('sort-order-icon').textContent = defaults.sort.direction === 'asc' ? '⬆️' : '⬇️';

            updatePriceRangeDisplay();
            applyFiltersAndSort();
        }}

        function updatePriceRangeDisplay() {{
            const display = document.getElementById('price-range-display');
            const minValue = state.filters.price.min;
            const maxValue = state.filters.price.max;
            if (!minValue && !maxValue) {{
                display.textContent = 'All prices';
                return;
            }}
            const minText = minValue ? formatCurrency(minValue) : 'Min';
            const maxText = maxValue ? formatCurrency(maxValue) : 'Max';
            display.textContent = `${{minText}} → ${{maxText}}`;
        }}

        function applyFiltersAndSort() {{
            if (!teslaData) {{
                return;
            }}

            const filtered = filterListings(teslaData.listings);
            filteredListings = sortListings(filtered);

            renderCarListings(filteredListings);
            renderStatistics(filteredListings);
            renderSourceBreakdown(filteredListings);
            renderFilterSummary(filteredListings);
            updateCharts(filteredListings);
        }}

        function filterListings(listings) {{
            const {{ model, price, mileage }} = state.filters;
            return listings.filter(listing => {{
                if (model !== 'all' && listing.modelLabel !== model) {{
                    return false;
                }}

                if (typeof price.min === 'number' && price.min > 0 && typeof listing.priceNumeric === 'number' && listing.priceNumeric < price.min) {{
                    return false;
                }}
                if (typeof price.max === 'number' && price.max > 0 && typeof listing.priceNumeric === 'number' && listing.priceNumeric > price.max) {{
                    return false;
                }}

                const mileageValue = listing.mileageNumeric;
                if (mileage === 'low' && (typeof mileageValue !== 'number' || mileageValue > 50000)) {{
                    return false;
                }}
                if (mileage === 'mid' && (typeof mileageValue !== 'number' || mileageValue < 50000 || mileageValue > 100000)) {{
                    return false;
                }}
                if (mileage === 'high' && (typeof mileageValue !== 'number' || mileageValue <= 100000)) {{
                    return false;
                }}
                if (mileage === 'unknown' && typeof mileageValue === 'number') {{
                    return false;
                }}

                return true;
            }});
        }}

        function sortListings(listings) {{
            const direction = state.sort.direction === 'asc' ? 1 : -1;
            const key = state.sort.key;
            const sorted = [...listings];

            sorted.sort((a, b) => {{
                const valueA = extractSortValue(a, key);
                const valueB = extractSortValue(b, key);

                if (valueA === valueB) {{
                    return secondarySort(a, b, direction);
                }}

                if (valueA === null || valueA === undefined) {{
                    return 1;
                }}
                if (valueB === null || valueB === undefined) {{
                    return -1;
                }}

                if (valueA > valueB) {{
                    return direction;
                }}
                if (valueA < valueB) {{
                    return -direction;
                }}

                return secondarySort(a, b, direction);
            }});

            return sorted;
        }}

        function extractSortValue(listing, key) {{
            switch (key) {{
                case 'price':
                    return typeof listing.priceNumeric === 'number' ? listing.priceNumeric : null;
                case 'year':
                    return listing.year ?? null;
                case 'mileage':
                    return typeof listing.mileageNumeric === 'number' ? listing.mileageNumeric : null;
                case 'title':
                    return listing.title?.toLowerCase() ?? null;
                case 'balanceScore':
                default:
                    return typeof listing.balanceScore === 'number' ? listing.balanceScore : null;
            }}
        }}

        function secondarySort(a, b, direction) {{
            const priceA = typeof a.priceNumeric === 'number' ? a.priceNumeric : Number.POSITIVE_INFINITY;
            const priceB = typeof b.priceNumeric === 'number' ? b.priceNumeric : Number.POSITIVE_INFINITY;
            if (priceA === priceB) {{
                return 0;
            }}
            return priceA > priceB ? direction : -direction;
        }}

        function renderStatistics(listings) {{
            const container = document.getElementById('statistics-container');
            const metadata = teslaData?.metadata ?? {{}};
            const priceRange = getPriceRange(listings);
            const availableCount = listings.length;

            container.innerHTML = `
                <div class="text-center p-6 bg-gradient-to-r from-blue-500 to-blue-600 rounded-xl text-white">
                    <div class="text-3xl font-bold">${{metadata.sourcesAnalyzed ?? 0}}</div>
                    <div class="text-blue-100">Sources Analyzed</div>
                </div>
                <div class="text-center p-6 bg-gradient-to-r from-green-500 to-green-600 rounded-xl text-white">
                    <div class="text-3xl font-bold">${{metadata.totalListings ?? 0}}</div>
                    <div class="text-green-100">Total Listings</div>
                </div>
                <div class="text-center p-6 bg-gradient-to-r from-purple-500 to-purple-600 rounded-xl text-white">
                    <div class="text-3xl font-bold">${{availableCount}}</div>
                    <div class="text-purple-100">Listings Displayed</div>
                </div>
                <div class="text-center p-6 bg-gradient-to-r from-red-500 to-red-600 rounded-xl text-white">
                    <div class="text-2xl font-bold">${{priceRange}}</div>
                    <div class="text-red-100">Price Range</div>
                </div>
            `;
        }}

        function renderMarketOverview(metadata) {{
            const models = metadata.modelDistribution?.filter(entry => entry.model !== 'Other' || entry.count > 0) ?? [];
            const modelText = models.length
                ? models.map(entry => `${{entry.model}} (${{entry.count}})`).join(', ')
                : metadata.availableModels.join(', ');
            document.getElementById('available-models').textContent = modelText || 'No models found';
            document.getElementById('available-locations').textContent = metadata.availableLocations.join(', ') || 'No locations found';
        }}

        function renderSourceBreakdown(listings) {{
            const container = document.getElementById('source-breakdown');
            const breakdown = aggregateSources(listings);

            if (!breakdown.length) {{
                container.innerHTML = `
                    <div class="p-6 border border-dashed border-gray-300 rounded-xl text-center text-gray-500">
                        Source metrics will appear once listings are available.
                    </div>
                `;
                return;
            }}

            container.innerHTML = breakdown.map(entry => `
                <div class="bg-white rounded-xl shadow-lg p-6">
                    <div class="flex items-center justify-between mb-4">
                        <h4 class="text-lg font-semibold text-gray-900">${{entry.source}}</h4>
                        <span class="text-sm text-gray-500">${{entry.listingCount}} listings</span>
                    </div>
                    <div class="space-y-2 text-sm text-gray-600">
                        <div class="flex items-center justify-between">
                            <span>Median price</span>
                            <span class="font-semibold">${{entry.medianPrice ? formatCurrency(entry.medianPrice) : 'N/A'}}</span>
                        </div>
                        <div class="flex items-center justify-between">
                            <span>Price range</span>
                            <span class="font-semibold">${{formatPriceBand(entry.minPrice, entry.maxPrice)}}</span>
                        </div>
                        <div class="flex items-center justify-between">
                            <span>Avg. mileage</span>
                            <span class="font-semibold">${{entry.averageMileage ? formatMileage(entry.averageMileage) : 'N/A'}}</span>
                        </div>
                    </div>
                </div>
            `).join('');
        }}

        function aggregateSources(listings) {{
            const map = new Map();
            listings.forEach(listing => {{
                const source = listing.source || 'unattributed';
                if (!map.has(source)) {{
                    map.set(source, {{ source, listingCount: 0, prices: [], mileages: [] }});
                }}
                const entry = map.get(source);
                entry.listingCount += 1;
                if (typeof listing.priceNumeric === 'number') {{
                    entry.prices.push(listing.priceNumeric);
                }}
                if (typeof listing.mileageNumeric === 'number') {{
                    entry.mileages.push(listing.mileageNumeric);
                }}
            }});

            return Array.from(map.values()).map(entry => {{
                const prices = entry.prices;
                const mileages = entry.mileages;
                prices.sort((a, b) => a - b);
                return {{
                    source: entry.source,
                    listingCount: entry.listingCount,
                    medianPrice: prices.length ? prices[Math.floor(prices.length / 2)] : null,
                    minPrice: prices.length ? prices[0] : null,
                    maxPrice: prices.length ? prices[prices.length - 1] : null,
                    averageMileage: mileages.length ? mileages.reduce((sum, value) => sum + value, 0) / mileages.length : null
                }};
            }}).sort((a, b) => b.listingCount - a.listingCount);
        }}

        function renderCarListings(listings) {{
            const carsGrid = document.getElementById('cars-grid');
            const emptyState = document.getElementById('cars-empty-state');
            const totalBadge = document.getElementById('total-listings-badge');
            const totalAvailable = teslaData?.listings?.length ?? listings.length;

            if (!listings.length) {{
                carsGrid.innerHTML = '';
                emptyState.classList.remove('hidden');
                totalBadge.innerHTML = `
                    <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3a2 2 0 012-2h4a2 2 0 012 2v4m-6 9l6 6 6-6" />
                    </svg>
                    Showing 0 of ${{totalAvailable}} Tesla listings
                `;
                return;
            }}

            emptyState.classList.add('hidden');
            totalBadge.innerHTML = `
                <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3a2 2 0 012-2h4a2 2 0 012 2v4m-6 9l6 6 6-6" />
                </svg>
                Showing ${{listings.length}} of ${{totalAvailable}} Tesla listings
            `;

            carsGrid.innerHTML = listings.map((listing, index) => {{
                const yearText = listing.year ? `(${{listing.year}})` : '(Year Unknown)';
                const mileageText = listing.mileage || 'Mileage Unknown';
                const locationText = listing.location || 'Location Unknown';
                const imageUrl = listing.imageUrl || `https://via.placeholder.com/400x300/1f2937/ffffff?text=Tesla+Image+${{index + 1}}`;
                const modelBadge = listing.modelLabel && listing.modelLabel !== 'Other'
                    ? `<span class="inline-flex items-center px-3 py-1 bg-tesla-dark text-white text-xs font-semibold rounded-full">${{listing.modelLabel}}</span>`
                    : '';

                const viewButton = listing.url ? `
                    <a href="${{listing.url}}" target="_blank" 
                       class="inline-flex items-center px-4 py-2 bg-red-600 hover:bg-red-700 text-white text-sm font-medium rounded-lg transition-colors duration-200">
                        <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                        </svg>
                        View Listing
                    </a>
                ` : `
                    <button disabled class="inline-flex items-center px-4 py-2 bg-gray-400 text-white text-sm font-medium rounded-lg cursor-not-allowed">
                        <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728L5.636 5.636m12.728 12.728L18.364 5.636" />
                        </svg>
                        No URL Available
                    </button>
                `;

                return `
                    <div class="bg-white rounded-xl shadow-lg overflow-hidden hover:shadow-xl transition-shadow duration-300">
                        <div class="relative h-64 bg-gray-200">
                            <img src="${{imageUrl}}"
                                 alt="${{listing.title}}"
                                 class="w-full h-full object-cover"
                                 loading="lazy"
                                 onerror="this.src='https://via.placeholder.com/400x300/1f2937/ffffff?text=Tesla+Image+Not+Available'; this.classList.add('opacity-75');" />
                            <div class="absolute top-4 left-4 bg-black bg-opacity-75 text-white px-3 py-1 rounded-full text-sm font-semibold">
                                #${{index + 1}}
                            </div>
                        </div>

                        <div class="p-6 space-y-4">
                            <div class="flex items-start justify-between">
                                <h3 class="text-xl font-bold text-gray-900 line-clamp-2">${{listing.title}}</h3>
                                ${{modelBadge}}
                            </div>

                            <div class="flex items-center space-x-3">
                                <span class="inline-flex items-center px-4 py-2 bg-green-100 text-green-800 text-lg font-bold rounded-lg">
                                    ${{listing.price}}
                                </span>
                                ${{getBalanceScoreBadge(listing.balanceScore, listing.balanceRating)}}
                            </div>

                            <div class="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm text-gray-600">
                                <div class="flex items-center">
                                    <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3a2 2 0 012-2h4a2 2 0 012 2v4m-6 9l6 6 6-6" />
                                    </svg>
                                    <span class="font-medium">Year:</span>
                                    <span class="ml-1">${{yearText}}</span>
                                </div>
                                <div class="flex items-center">
                                    <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
                                    </svg>
                                    <span class="font-medium">Mileage:</span>
                                    <span class="ml-1">${{mileageText}}</span>
                                </div>
                                <div class="flex items-center md:col-span-2">
                                    <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                                    </svg>
                                    <span class="font-medium">Location:</span>
                                    <span class="ml-1">${{locationText}}</span>
                                </div>
                                <div class="flex items-center md:col-span-2 text-gray-500 text-xs">
                                    <svg class="w-3 h-3 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 8h10M7 12h4m1 8l-4-4H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-3l-4 4z" />
                                    </svg>
                                    Source: ${{listing.source || 'unattributed'}}
                                </div>
                            </div>

                            <div class="flex justify-center">
                                ${{viewButton}}
                            </div>
                        </div>
                    </div>
                `;
            }}).join('');
        }}

        function renderFilterSummary(listings) {{
            const summaryEl = document.getElementById('filter-summary');
            const parts = [];
            const defaults = state.defaults;

            if (state.filters.model !== defaults?.model) {{
                parts.push(`Model: ${{state.filters.model}}`);
            }}

            const priceChanged = defaults && (
                (state.filters.price.min && state.filters.price.min !== defaults.price.min) ||
                (state.filters.price.max && state.filters.price.max !== defaults.price.max)
            );
            if (priceChanged) {{
                parts.push(`Price ${{formatCurrency(state.filters.price.min)}} → ${{formatCurrency(state.filters.price.max)}}`);
            }}

            if (state.filters.mileage !== defaults?.mileage) {{
                const labels = {{
                    low: 'Under 50k km',
                    mid: '50k-100k km',
                    high: '100k+ km',
                    unknown: 'Mileage unknown'
                }};
                parts.push(`Mileage: ${{labels[state.filters.mileage] ?? state.filters.mileage}}`);
            }}

            if (state.sort.key !== defaults?.sort.key || state.sort.direction !== defaults?.sort.direction) {{
                parts.push(`Sorted by ${{state.sort.key}} (${{state.sort.direction}})`);
            }}

            const activeSummary = parts.length ? parts.join(' • ') : 'No filters applied';
            summaryEl.textContent = `${{activeSummary}} — ${{listings.length}} matching listings`;
        }}

        function updateCharts(listings) {{
            const analyticsSection = document.getElementById('analytics-section');
            if (!listings.length) {{
                analyticsSection.classList.add('hidden');
                toggleChartEmptyState('price', true);
                toggleChartEmptyState('model', true);
                return;
            }}
            analyticsSection.classList.remove('hidden');

            const priceData = buildPriceBands(listings);
            const modelData = buildModelDistribution(listings);

            toggleChartEmptyState('price', !priceData.data.length);
            toggleChartEmptyState('model', !modelData.data.length);

            updateChartInstance('price', priceData.labels, priceData.data, {{
                label: 'Listings',
                backgroundColor: palette[0],
                borderColor: palette[0],
                type: 'bar'
            }});
            document.getElementById('price-chart-summary').textContent = priceData.summary;

            updateChartInstance('model', modelData.labels, modelData.data, {{
                label: 'Share',
                backgroundColor: modelData.labels.map((_, index) => palette[index % palette.length]),
                type: 'doughnut'
            }});
            document.getElementById('model-chart-summary').textContent = modelData.summary;
        }}

        function updateChartInstance(type, labels, data, options) {{
            const canvas = document.getElementById(`${{type}}-distribution-chart`);
            if (!canvas) {{
                return;
            }}

            const existing = charts[type];
            if (existing) {{
                existing.data.labels = labels;
                existing.data.datasets[0].data = data;
                if (Array.isArray(options.backgroundColor)) {{
                    existing.data.datasets[0].backgroundColor = options.backgroundColor;
                }}
                existing.update();
                return;
            }}

            const config = type === 'price'
                ? {{
                    type: 'bar',
                    data: {{
                        labels,
                        datasets: [{{
                            label: options.label,
                            data,
                            backgroundColor: options.backgroundColor,
                            borderRadius: 8
                        }}]
                    }},
                    options: {{
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {{
                            y: {{
                                ticks: {{
                                    callback: value => formatCurrency(Number(value))
                                }}
                            }}
                        }},
                        plugins: {{
                            legend: {{ display: false }}
                        }}
                    }}
                }}
                : {{
                    type: 'doughnut',
                    data: {{
                        labels,
                        datasets: [{{
                            label: options.label,
                            data,
                            backgroundColor: options.backgroundColor,
                            borderWidth: 0
                        }}]
                    }},
                    options: {{
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {{
                            legend: {{
                                position: 'bottom'
                            }}
                        }}
                    }}
                }};

            charts[type] = new Chart(canvas.getContext('2d'), config);
        }}

        function toggleChartEmptyState(type, isEmpty) {{
            const emptyElement = document.getElementById(`${{type}}-chart-empty`);
            if (!emptyElement) {{
                return;
            }}
            emptyElement.classList.toggle('hidden', !isEmpty);
        }}

        function buildPriceBands(listings) {{
            const validPrices = listings
                .map(listing => listing.priceNumeric)
                .filter(value => typeof value === 'number' && value > 0);
            if (!validPrices.length) {{
                return {{ labels: [], data: [], summary: 'No price data available' }};
            }}
            const min = Math.min(...validPrices);
            const max = Math.max(...validPrices);
            if (min === max) {{
                return {{
                    labels: [formatCurrency(min)],
                    data: [validPrices.length],
                    summary: `All listings around ${{formatCurrency(min)}}`
                }};
            }}
            const bucketCount = Math.min(6, Math.max(3, Math.ceil(validPrices.length / 8)));
            const bucketSize = Math.max(1, Math.ceil((max - min) / bucketCount));
            const labels = [];
            const data = new Array(bucketCount).fill(0);
            for (let i = 0; i < bucketCount; i += 1) {{
                const start = min + i * bucketSize;
                const end = i === bucketCount - 1 ? max : start + bucketSize;
                labels.push(`${{formatCurrency(start)}} – ${{formatCurrency(end)}}`);
            }}
            validPrices.forEach(price => {{
                const bucketIndex = Math.min(labels.length - 1, Math.floor((price - min) / bucketSize));
                data[bucketIndex] += 1;
            }});
            return {{
                labels,
                data,
                summary: `${{validPrices.length}} listings across ${{labels.length}} price bands`
            }};
        }}

        function buildModelDistribution(listings) {{
            const counts = new Map();
            listings.forEach(listing => {{
                const key = listing.modelLabel || 'Other';
                counts.set(key, (counts.get(key) || 0) + 1);
            }});
            const labels = Array.from(counts.keys());
            const data = Array.from(counts.values());
            const summary = labels.length
                ? `${{labels.length}} models represented`
                : 'No model data available';
            return {{ labels, data, summary }};
        }}

        function getPriceRange(listings) {{
            const values = listings
                .map(listing => listing.priceNumeric)
                .filter(value => typeof value === 'number' && value > 0);
            if (!values.length) {{
                return 'N/A';
            }}
            const min = Math.min(...values);
            const max = Math.max(...values);
            if (min === max) {{
                return formatCurrency(min);
            }}
            return `${{formatCurrency(min)}} – ${{formatCurrency(max)}}`;
        }}

        function formatCurrency(value) {{
            if (typeof value !== 'number' || Number.isNaN(value)) {{
                return 'N/A';
            }}
            return `AED ${{Math.round(value).toLocaleString('en-US')}}`;
        }}

        function formatPriceBand(min, max) {{
            if (typeof min !== 'number' && typeof max !== 'number') {{
                return 'N/A';
            }}
            if (typeof min !== 'number') {{
                return formatCurrency(max);
            }}
            if (typeof max !== 'number') {{
                return formatCurrency(min);
            }}
            if (min === max) {{
                return formatCurrency(min);
            }}
            return `${{formatCurrency(min)}} – ${{formatCurrency(max)}}`;
        }}

        function formatMileage(value) {{
            if (typeof value !== 'number' || Number.isNaN(value)) {{
                return 'N/A';
            }}
            return `${{Math.round(value).toLocaleString('en-US')}} km`;
        }}

        function getBalanceScoreBadge(score, rating) {{
            if (typeof score !== 'number' || !rating) {{
                return '<span class="text-xs text-gray-400">No score available</span>';
            }}

            let badgeClass = '';
            let icon = '';

            if (score <= 0.5) {{
                badgeClass = 'bg-green-100 text-green-800 border border-green-200';
                icon = '<svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>';
            }} else if (score <= 1.0) {{
                badgeClass = 'bg-blue-100 text-blue-800 border border-blue-200';
                icon = '<svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>';
            }} else if (score <= 1.5) {{
                badgeClass = 'bg-yellow-100 text-yellow-800 border border-yellow-200';
                icon = '<svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L3.732 16.5c-.77.833.192 2.5 1.732 2.5z"/></svg>';
            }} else {{
                badgeClass = 'bg-red-100 text-red-800 border border-red-200';
                icon = '<svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>';
            }}

            return `
                <div class="inline-flex items-center px-3 py-1 ${{badgeClass}} rounded-full text-sm font-medium">
                    ${{icon}}
                    ${{rating}} <span class="ml-1 text-xs opacity-75">(Score: ${{score.toFixed(2)}})</span>
                </div>
            `;
        }}

        document.addEventListener('DOMContentLoaded', () => {{
            loadTeslaData();
        }});

        document.addEventListener('click', event => {{
            const link = event.target.closest('a[target="_blank"]');
            if (!link) {{
                return;
            }}
            const originalHTML = link.innerHTML;
            link.innerHTML = '<svg class="animate-spin w-4 h-4 mr-2 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path></svg>Loading...';
            setTimeout(() => {{
                link.innerHTML = originalHTML;
            }}, 2000);
        }});

        console.log('🚗 Tesla Finder AE HTML Template Loaded Successfully');

    </script>
</body>
</html>'''
        
        # Save HTML file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        html_span.set_attributes({
            "html_template_generated": True,
            "output_path": str(output_path),
            "file_size_bytes": len(html_content),
            "uses_xhr": True,
            "static_template": True
        })
        
        logfire.info(
            "✅ Tesla static HTML template generated successfully",
            output_path=str(output_path),
            file_size_bytes=len(html_content),
            template_type="static_with_xhr"
        )
        
        return str(output_path)
