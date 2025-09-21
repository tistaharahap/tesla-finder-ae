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
from jinja2 import Environment, FileSystemLoader, select_autoescape
from tesla_finder_ae.nodes import (
    TeslaConsolidatedSummary,
    parse_mileage_to_numeric,
    parse_price_to_numeric,
)


TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

_JINJA_ENV = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(["html", "xml"]),
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
                "sortingCriteria": "Mileage ↑, Price ↑, Year ↓ (balance score tie-breaker)"
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
                "imageUrl": (
                    listing.image_url
                    if listing.image_url
                    else f"https://placehold.co/400x300/1f2937/ffffff?text=Tesla+Image+{i}"
                ),
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
    """Generate the HTML report using the Jinja2 template engine."""
    with logfire.span(
        "Tesla HTML Template Generation",
        sources_count=len(consolidated_summary.source_urls)
    ) as html_span:
        if output_path is None:
            output_path = Path("public/index.html")

        timestamp = consolidated_summary.analyzed_at.strftime("%Y-%m-%d %H:%M:%S")
        context = {
            "page_title": f"Tesla Market Analysis Report - {timestamp}",
            "analyzed_at_iso": consolidated_summary.analyzed_at.isoformat(),
            "sources_count": len(consolidated_summary.source_urls),
            "source_urls": consolidated_summary.source_urls,
            "fallback_generation_label": f"Generated: {timestamp}",
        }

        template = _JINJA_ENV.get_template("report.html.j2")
        html_content = template.render(**context)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html_content, encoding="utf-8")

        html_span.set_attributes(
            {
                "html_generated": True,
                "output_path": str(output_path),
                "file_size_bytes": len(html_content),
                "template_name": "report.html.j2",
            }
        )

        logfire.info(
            "✅ Tesla HTML report generated successfully",
            output_path=str(output_path),
            file_size_bytes=len(html_content),
            template_name="report.html.j2",
        )

        return str(output_path)
