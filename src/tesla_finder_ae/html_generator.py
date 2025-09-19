"""
HTML Report Generator for Tesla Finder AE

Generates beautiful HTML reports from Tesla consolidated summaries using Tailwind CSS.
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import logfire
from tesla_finder_ae.nodes import TeslaConsolidatedSummary


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
        
        # Add all sorted listings with proper structure
        for i, listing in enumerate(consolidated_summary.all_sorted_listings, 1):
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
                "mileageZScore": round(listing.mileage_z_score, 2) if listing.mileage_z_score is not None else None
            }
            json_data["listings"].append(listing_data)
        
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
            </div>
            
            <!-- Cars Grid -->
            <div id="cars-grid" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
                <!-- Cars will be loaded here by JavaScript -->
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
        
        // Load Tesla data from JSON
        async function loadTeslaData() {{
            try {{
                document.getElementById('loading-section').classList.remove('hidden');
                document.getElementById('error-section').classList.add('hidden');
                document.getElementById('cars-section').classList.add('hidden');
                
                const response = await fetch('./listings.json');
                if (!response.ok) {{
                    throw new Error('Failed to fetch listings data');
                }}
                
                teslaData = await response.json();
                renderTeslaData();
                
                document.getElementById('loading-section').classList.add('hidden');
                document.getElementById('cars-section').classList.remove('hidden');
                
                console.log('🚗 Tesla data loaded successfully:', teslaData);
                
            }} catch (error) {{
                console.error('❌ Failed to load Tesla data:', error);
                document.getElementById('loading-section').classList.add('hidden');
                document.getElementById('error-section').classList.remove('hidden');
            }}
        }}
        
        // Render Tesla data to the page
        function renderTeslaData() {{
            const {{ metadata, listings }} = teslaData;
            
            // Update header timestamp
            document.getElementById('generation-time').innerHTML = `
                <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3a2 2 0 012-2h4a2 2 0 012 2v4m-6 9l6 6 6-6" />
                </svg>
                <span class="font-semibold">Generated: ${{new Date(metadata.generatedAt).toLocaleString()}}</span>
            `;
            
            // Update statistics
            document.getElementById('statistics-container').innerHTML = `
                <div class="text-center p-6 bg-gradient-to-r from-blue-500 to-blue-600 rounded-xl text-white">
                    <div class="text-3xl font-bold">${{metadata.sourcesAnalyzed}}</div>
                    <div class="text-blue-100">Sources Analyzed</div>
                </div>
                <div class="text-center p-6 bg-gradient-to-r from-green-500 to-green-600 rounded-xl text-white">
                    <div class="text-3xl font-bold">${{metadata.totalListings}}</div>
                    <div class="text-green-100">Total Listings</div>
                </div>
                <div class="text-center p-6 bg-gradient-to-r from-purple-500 to-purple-600 rounded-xl text-white">
                    <div class="text-3xl font-bold">${{listings.length}}</div>
                    <div class="text-purple-100">Available Cars</div>
                </div>
                <div class="text-center p-6 bg-gradient-to-r from-red-500 to-red-600 rounded-xl text-white">
                    <div class="text-2xl font-bold">${{metadata.globalPriceRange}}</div>
                    <div class="text-red-100">Price Range</div>
                </div>
            `;
            
            // Update market overview
            document.getElementById('available-models').textContent = metadata.availableModels.join(', ') || 'No models found';
            document.getElementById('available-locations').textContent = metadata.availableLocations.join(', ') || 'No locations found';
            
            // Update total listings badge
            document.getElementById('total-listings-badge').innerHTML = `
                <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                </svg>
                ${{listings.length}} Tesla Cars Found
            `;
            
            // Update footer
            document.getElementById('footer-timestamp').textContent = `Generated at ${{new Date(metadata.generatedAt).toLocaleString()}} with comprehensive market data`;
            document.getElementById('footer-sources').textContent = `Data sourced from ${{metadata.sourcesAnalyzed}} trusted automotive platforms`;
            
            // Render car listings
            renderCarListings(listings);
        }}
        
        // Generate balance score badge based on score and rating
        function getBalanceScoreBadge(score, rating) {{
            if (!score || !rating) return '<span class="text-xs text-gray-400">No score available</span>';

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
                    ${{rating}} <span class="ml-1 text-xs opacity-75">(Score: ${{score}})</span>
                </div>
            `;
        }}

        // Render individual car listings
        function renderCarListings(listings) {{
            const carsGrid = document.getElementById('cars-grid');
            
            carsGrid.innerHTML = listings.map((listing, index) => {{
                const yearText = listing.year ? `(${{listing.year}})` : '(Year Unknown)';
                const mileageText = listing.mileage || 'Mileage Unknown';
                const locationText = listing.location || 'Location Unknown';
                const imageUrl = listing.imageUrl || `https://via.placeholder.com/400x300/1f2937/ffffff?text=Tesla+Image+${{index + 1}}`;
                
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
                        <!-- Car Image -->
                        <div class="relative h-64 bg-gray-200">
                            <img src="${{imageUrl}}" 
                                 alt="${{listing.title}}"
                                 class="w-full h-full object-cover"
                                 onerror="this.src='https://via.placeholder.com/400x300/1f2937/ffffff?text=Tesla+Image+Not+Available'; this.classList.add('opacity-75');" />
                            <div class="absolute top-4 left-4 bg-black bg-opacity-75 text-white px-3 py-1 rounded-full text-sm font-semibold">
                                #${{index + 1}}
                            </div>
                        </div>
                        
                        <!-- Car Details -->
                        <div class="p-6">
                            <h3 class="text-xl font-bold text-gray-900 mb-2 line-clamp-2">${{listing.title}}</h3>
                            
                            <!-- Price Badge -->
                            <div class="mb-4">
                                <span class="inline-flex items-center px-4 py-2 bg-green-100 text-green-800 text-lg font-bold rounded-lg">
                                    ${{listing.price}}
                                </span>
                            </div>

                            <!-- Balance Score Badge -->
                            <div class="mb-4">
                                ${{getBalanceScoreBadge(listing.balanceScore, listing.balanceRating)}}
                            </div>
                            
                            <!-- Details Grid -->
                            <div class="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4 text-sm">
                                <div class="flex items-center text-gray-600">
                                    <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3a2 2 0 012-2h4a2 2 0 012 2v4m-6 9l6 6 6-6" />
                                    </svg>
                                    <span class="font-medium">Year:</span>
                                    <span class="ml-1">${{yearText}}</span>
                                </div>
                                
                                <div class="flex items-center text-gray-600">
                                    <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
                                    </svg>
                                    <span class="font-medium">Mileage:</span>
                                    <span class="ml-1">${{mileageText}}</span>
                                </div>
                                
                                <div class="flex items-center text-gray-600 md:col-span-2">
                                    <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                                    </svg>
                                    <span class="font-medium">Location:</span>
                                    <span class="ml-1">${{locationText}}</span>
                                </div>
                            </div>
                            
                            <!-- Action Button -->
                            <div class="flex justify-center">
                                ${{viewButton}}
                            </div>
                        </div>
                    </div>
                `;
            }}).join('');
        }}
        
        // Initialize page
        document.addEventListener('DOMContentLoaded', function() {{
            loadTeslaData();
        }});
        
        // Add loading state for external links
        document.addEventListener('click', function(e) {{
            if (e.target.closest('a[target="_blank"]')) {{
                const link = e.target.closest('a[target="_blank"]');
                const originalHTML = link.innerHTML;
                link.innerHTML = '<svg class="animate-spin w-4 h-4 mr-2 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path></svg>Loading...';
                setTimeout(() => {{ link.innerHTML = originalHTML; }}, 2000);
            }}
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