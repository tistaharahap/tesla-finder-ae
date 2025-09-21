import asyncio
import json
import subprocess
import time
from pathlib import Path
from typing import Optional
from datetime import datetime

import logfire
from typer import Typer

from tesla_finder_ae.nodes import search_tesla_listings, generate_consolidated_daily_tesla_digest
from tesla_finder_ae.observability import configure_logfire
from tesla_finder_ae.html_generator import generate_tesla_html_report, generate_tesla_listings_json

app = Typer(pretty_exceptions_enable=False)

# Initialize Logfire for CLI operations
configure_logfire(service_name="tesla-finder-ae-cli")
urls = [
    "https://dubai.dubizzle.com/motors/used-cars/tesla/?sorting=price_asc&year__gte=2021&year__lte=2026&regional_specs=824",
    "https://carswitch.com/uae/used-cars/search?make=tesla&minyear=2021&maxyear=2025&sort=price_low_high",
    "https://www.kavak.com/ae/preowned?year=2021,2022,2023,2024&keyword=tesla&order=lower_price&page=0",
    "https://www.dubicars.com/search?o=&did=&gen=&trg=&moc=&c=new-and-used&ul=AE&cr=AED&k=&mg=&ma=104&yf=2021&yt=&set=bu&pf=&pt=100000&emif=&emit=&kf=&kt=&eo%5B%5D=can-be-exported&eo%5B%5D=not-for-export&noi=30",
    "https://albacars.ae/buy-used-cars-uae?make=tesla&priceMax=100000",
    "https://buyanycar.com/cars?cars%3Acars%5BrefinementList%5D%5Bmake%5D%5B0%5D=TESLA&cars%3Acars%5BrefinementList%5D%5Byear%5D%5B0%5D=2021&cars%3Acars%5BrefinementList%5D%5Byear%5D%5B1%5D=2022&cars%3Acars%5BrefinementList%5D%5Byear%5D%5B2%5D=2023&cars%3Acars%5BrefinementList%5D%5Byear%5D%5B3%5D=2024&cars%3Acars%5BrefinementList%5D%5Byear%5D%5B4%5D=2025&cars%3Acars%5Brange%5D%5Bprice%5D=%3A100000",
    "https://www.automall.ae/en/used-cars-shop/?make=tesla",
    "https://www.autotraders.ae/used-cars/tesla/?st=&city=&condition=&car_make=76&car_model=&ctrim_id=&ex_color_id=&specs_id=&code=&year_min=2021&year_max=&price_min=&price_max=100000",
    "https://www.rmamotors.com/used-cars/?manufacturer%5B0%5D=Tesla&registrationYear%5Bto%5D=2025&registrationYear%5Bfrom%5D=2021&nfcSearchVersion=1.0.0",
    "https://uae.yallamotor.com/used-cars/mk_tesla/pr_less_100000/yr_2021_later",
]


def start_dev_server_and_open_browser():
    """
    Start a Python development server and open the browser
    """
    with logfire.span("Development Server Startup") as server_span:
        try:
            import http.server
            import socketserver
            import os
            from threading import Thread
            
            # Change to public directory
            public_dir = Path("public").absolute()
            if not public_dir.exists():
                raise FileNotFoundError("public/ directory not found")
            
            # Check if files exist
            index_file = public_dir / "index.html"
            json_file = public_dir / "listings.json"
            
            if not index_file.exists():
                raise FileNotFoundError("public/index.html not found")
            if not json_file.exists():
                raise FileNotFoundError("public/listings.json not found")
            
            print(f"\n🚀 Starting development server...")
            print(f"   📁 Serving from: {public_dir}")
            print(f"   🌐 URL: http://127.0.0.1:8000")
            
            def run_server():
                os.chdir(public_dir)
                with socketserver.TCPServer(("127.0.0.1", 8000), http.server.SimpleHTTPRequestHandler) as httpd:
                    print(f"   ✅ Server started successfully")
                    logfire.info("🚀 Development server started", port=8000, directory=str(public_dir))
                    httpd.serve_forever()
            
            # Start server in background thread
            server_thread = Thread(target=run_server, daemon=True)
            server_thread.start()
            
            # Give server a moment to start
            time.sleep(1)
            
            # Open browser (macOS)
            print(f"   🌐 Opening browser...")
            try:
                subprocess.run(["open", "http://127.0.0.1:8000"], check=True)
                print(f"   ✅ Browser opened successfully")
                logfire.info("🌐 Browser opened successfully", url="http://127.0.0.1:8000")
            except subprocess.CalledProcessError as e:
                print(f"   ⚠️ Could not auto-open browser: {e}")
                print(f"   🔗 Please manually open: http://127.0.0.1:8000")
                logfire.warning("⚠️ Auto browser opening failed", error=str(e))
            
            server_span.set_attributes({
                "server_started": True,
                "port": 8000,
                "directory": str(public_dir),
                "browser_opened": True,
                "url": "http://127.0.0.1:8000"
            })
            
            print(f"\n🎯 Tesla Report Ready!")
            print(f"   📊 View your Tesla market analysis at: http://127.0.0.1:8000")
            print(f"   🛑 Press Ctrl+C to stop the server")
            
            # Keep main thread alive to maintain server
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print(f"\n\n🛑 Server stopped by user")
                logfire.info("🛑 Development server stopped by user")
                
        except Exception as e:
            print(f"\n❌ Failed to start development server: {e}")
            print(f"   📁 Please check that public/index.html and public/listings.json exist")
            print(f"   🔗 You can manually open public/index.html in your browser")
            
            server_span.set_attribute("server_startup_failed", True)
            server_span.set_attribute("error", str(e))
            logfire.error("❌ Development server startup failed", error=str(e))


@app.command()
def digest(
    output_file: Optional[Path] = None,
    custom_urls: Optional[str] = None,
    html_report: bool = False
):
    """
    Generate daily Tesla digest from configured URLs or custom URLs.
    
    Args:
        output_file: Optional JSON file to save the digest results
        custom_urls: Comma-separated list of custom URLs to analyze
        html_report: Generate HTML report in public/ (creates index.html + listings.json) and start dev server
    """
    start_time = time.time()
    
    with logfire.span(
        "CLI Tesla Digest Command",
        command="digest",
        has_custom_urls=custom_urls is not None,
        has_output_file=output_file is not None,
        html_report_requested=html_report
    ) as cli_span:
        
        # Use custom URLs if provided, otherwise use default URLs
        target_urls = urls
        if custom_urls:
            target_urls = [url.strip() for url in custom_urls.split(',')]
            logfire.info("📝 Using custom URLs for digest", custom_urls=target_urls)
        else:
            logfire.info("📋 Using default configured URLs", default_urls=target_urls)
        
        cli_span.set_attribute("target_url_count", len(target_urls))
        cli_span.set_attribute("target_urls", target_urls)
        
        print(f"🚗 Generating Tesla digest from {len(target_urls)} URLs...")
        logfire.info("🚀 Starting Tesla digest generation via CLI", url_count=len(target_urls))
        
        # Run consolidated digest generation with tracing
        with logfire.span("Async Consolidated Digest Execution") as async_span:
            consolidated_summary = asyncio.run(generate_consolidated_daily_tesla_digest(target_urls))
            async_span.set_attribute("consolidated_summary_created", True)

        if not consolidated_summary or not consolidated_summary.top_cheapest_cars:
            print("❌ No Tesla listings found. Check URLs and network connection.")
            logfire.error("❌ No Tesla listings found from digest command")
            cli_span.set_attribute("success", False)
            return

        print(f"✅ Generated consolidated summary with {len(consolidated_summary.top_cheapest_cars)} cheapest cars")
        logfire.info("✅ Consolidated digest generation completed",
                    top_cars_count=len(consolidated_summary.top_cheapest_cars),
                    total_listings=consolidated_summary.total_listings_found)

        # Display consolidated summary with structured logging
        with logfire.span("Consolidated Summary Display") as display_span:
            print(f"\n🎯 TESLA MARKET SUMMARY - UAE DIRHAM (AED)")
            print(f"{'='*60}")
            print(f"📅 Analysis Date: {consolidated_summary.analyzed_at.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"🔗 Sources Analyzed: {len(consolidated_summary.source_urls)} URLs")
            print(f"🏷️  Total Listings Found: {consolidated_summary.total_listings_found}")
            print(f"💰 Global Price Range: {consolidated_summary.global_price_range}")
            print(f"🚙 Available Models: {', '.join(consolidated_summary.all_models)}")
            print(f"📍 Available Locations: {', '.join(consolidated_summary.all_locations)}")

            print(f"\n🏆 TOP 20 CHEAPEST TESLA CARS:")
            print(f"{'-'*90}")
            for i, listing in enumerate(consolidated_summary.top_cheapest_cars, 1):
                year_info = f"({listing.year})" if listing.year else "(Year unknown)"
                mileage_info = f" | {listing.mileage}" if listing.mileage else " | Mileage unknown"
                location_info = f" - {listing.location}" if listing.location else ""

                # Display listing with mileage and other details
                print(f"  {i:2d}. {listing.title:35} - {listing.price:>12} {year_info}{mileage_info}{location_info}")

                # Show clickable URL if available
                if listing.url:
                    print(f"      🔗 {listing.url}")
                else:
                    print(f"      🔗 No direct URL available")
                print()  # Add blank line for better readability

            print(f"\n📋 DETAILED ANALYSIS:")
            print(f"{'-'*60}")
            print(consolidated_summary.summary)

            # Log consolidated summary as structured data
            logfire.info(
                "📊 Displayed consolidated Tesla summary",
                total_listings=consolidated_summary.total_listings_found,
                price_range=consolidated_summary.global_price_range,
                models_found=consolidated_summary.all_models,
                locations_found=consolidated_summary.all_locations,
                top_cars_count=len(consolidated_summary.top_cheapest_cars)
            )

            display_span.set_attributes({
                "total_listings": consolidated_summary.total_listings_found,
                "sources_count": len(consolidated_summary.source_urls),
                "top_cars_displayed": len(consolidated_summary.top_cheapest_cars),
                "models_count": len(consolidated_summary.all_models),
                "locations_count": len(consolidated_summary.all_locations)
            })
        
        # Save to JSON file if requested
        if output_file:
            with logfire.span("JSON File Output", output_path=str(output_file)) as file_span:
                output_data = consolidated_summary.model_dump()
                with open(output_file, 'w') as f:
                    json.dump(output_data, f, indent=2, default=str)
                print(f"\n💾 Consolidated summary saved to {output_file}")

                file_span.set_attribute("file_saved", True)
                file_span.set_attribute("file_size_bytes", output_file.stat().st_size if output_file.exists() else 0)
                logfire.info("💾 Consolidated digest results saved to file", output_file=str(output_file))
        
        # Generate HTML report if requested
        if html_report:
            with logfire.span("HTML Report Generation") as html_span:
                try:
                    # Generate both HTML template and JSON data
                    html_path = Path("public/index.html")
                    json_path = Path("public/listings.json")
                    
                    html_content = generate_tesla_html_report(consolidated_summary, html_path)
                    json_content = generate_tesla_listings_json(consolidated_summary, json_path)
                    
                    print(f"\n🌐 Tesla HTML report generated successfully!")
                    print(f"   📄 Static HTML: {html_path}")
                    print(f"   📊 JSON Data: {json_path}")
                    print(f"   🚗 {len(consolidated_summary.all_sorted_listings)} Tesla cars with images and details")
                    
                    html_span.set_attributes({
                        "html_generated": True,
                        "json_generated": True,
                        "html_path": str(html_path),
                        "json_path": str(json_path),
                        "cars_with_images": sum(1 for car in consolidated_summary.all_sorted_listings if car.image_url),
                        "total_cars": len(consolidated_summary.all_sorted_listings),
                        "xhr_enabled": True
                    })
                    
                    logfire.info("🌐 Tesla HTML+JSON report generated successfully", 
                               html_path=str(html_path), 
                               json_path=str(json_path),
                               total_listings=len(consolidated_summary.all_sorted_listings))
                    
                    # Start development server and open browser
                    start_dev_server_and_open_browser()
                    
                except Exception as e:
                    print(f"\n❌ Failed to generate HTML report: {e}")
                    html_span.set_attribute("html_generation_failed", True)
                    html_span.set_attribute("error", str(e))
                    logfire.error("❌ HTML report generation failed", error=str(e))
        
        # Calculate and log final metrics
        execution_time = time.time() - start_time
        cli_span.set_attributes({
            "success": True,
            "execution_time_seconds": execution_time,
            "consolidated_summary_generated": True,
            "total_listings_found": consolidated_summary.total_listings_found,
            "top_cars_selected": len(consolidated_summary.top_cheapest_cars),
            "file_saved": output_file is not None,
            "html_report_generated": html_report
        })

        logfire.info(
            "🎯 Tesla consolidated digest CLI command completed",
            execution_time_seconds=execution_time,
            total_listings_found=consolidated_summary.total_listings_found,
            top_cars_selected=len(consolidated_summary.top_cheapest_cars),
            target_urls=len(target_urls),
            sources_processed=len(consolidated_summary.source_urls)
        )


@app.command()  
def search(
    url: str,
    output_file: Optional[Path] = None
):
    """
    Search a single Tesla URL and get structured results.
    
    Args:
        url: Tesla search URL to analyze
        output_file: Optional JSON file to save results
    """
    start_time = time.time()
    
    with logfire.span(
        "CLI Tesla Search Command",
        command="search",
        url=url,
        has_output_file=output_file is not None
    ) as cli_span:
        
        print(f"🔍 Searching Tesla listings from: {url}")
        logfire.info("🔍 Starting Tesla single URL search via CLI", url=url)
        
        try:
            # Run async search with tracing
            with logfire.span("Async Search Execution") as async_span:
                summary = asyncio.run(search_tesla_listings(url))
                async_span.set_attribute("search_completed", True)
                async_span.set_attribute("listings_found", summary.total_listings)
            
            print(f"✅ Analysis complete!")
            print(f"📅 Analyzed: {summary.analyzed_at.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"🏷️  Total listings: {summary.total_listings}")
            print(f"💰 Price range: {summary.price_range}")
            print(f"🚙 Common models: {', '.join(summary.common_models)}")
            print(f"📍 Locations: {', '.join(summary.locations)}")
            print(f"📝 Summary: {summary.summary}")
            
            # Log the complete summary as structured data
            logfire.info(
                "✅ Tesla search analysis completed",
                url=url,
                total_listings=summary.total_listings,
                price_range=summary.price_range,
                common_models=summary.common_models,
                locations=summary.locations,
                summary_text=summary.summary
            )
            
            if summary.listings:
                print(f"\n🚗 Individual listings:")
                with logfire.span("Individual Listings Display") as listings_span:
                    for i, listing in enumerate(summary.listings, 1):
                        print(f"  {i}. {listing.title}")
                        print(f"     💰 {listing.price} | 📅 {listing.year} | 🛣️  {listing.mileage}")
                        if listing.location:
                            print(f"     📍 {listing.location}")
                        if listing.url:
                            print(f"     🔗 {listing.url}")
                        print()
                        
                        # Log each listing for detailed analysis
                        logfire.debug(
                            f"🚗 Tesla listing {i}",
                            listing_index=i,
                            title=listing.title,
                            price=listing.price,
                            year=listing.year,
                            mileage=listing.mileage,
                            location=listing.location
                        )
                    
                    listings_span.set_attribute("listings_displayed", len(summary.listings))
            
            # Save to file if requested
            if output_file:
                with logfire.span("File Output", output_path=str(output_file)) as file_span:
                    with open(output_file, 'w') as f:
                        json.dump(summary.model_dump(), f, indent=2, default=str)
                    print(f"💾 Results saved to {output_file}")
                    
                    file_span.set_attribute("file_saved", True)
                    file_span.set_attribute("file_size_bytes", output_file.stat().st_size if output_file.exists() else 0)
                    logfire.info("💾 Search results saved to file", output_file=str(output_file))
            
            # Set successful completion attributes
            execution_time = time.time() - start_time
            cli_span.set_attributes({
                "success": True,
                "execution_time_seconds": execution_time,
                "listings_found": summary.total_listings,
                "file_saved": output_file is not None
            })
            
            logfire.info(
                "🎯 Tesla search CLI command completed successfully",
                execution_time_seconds=execution_time,
                url=url,
                listings_found=summary.total_listings
            )
                
        except Exception as e:
            print(f"❌ Error analyzing URL: {e}")
            
            # Log the error with full context
            cli_span.set_attribute("success", False)
            cli_span.set_attribute("error_type", type(e).__name__)
            cli_span.set_attribute("error_message", str(e))
            
            logfire.error(
                "❌ Tesla search CLI command failed",
                url=url,
                error_type=type(e).__name__,
                error_message=str(e),
                execution_time_seconds=time.time() - start_time
            )
            raise


@app.command()
def urls_list():
    """List all configured Tesla search URLs."""
    with logfire.span("CLI URLs List Command") as cli_span:
        print("🔗 Configured Tesla search URLs:")
        for i, url in enumerate(urls, 1):
            print(f"  {i}. {url}")
        
        cli_span.set_attribute("urls_displayed", len(urls))
        logfire.info("📋 Listed configured Tesla URLs", url_count=len(urls), urls=urls)


@app.command()
def main():
    """Default command - shows help."""
    with logfire.span("CLI Main Command") as cli_span:
        print("🚗 Tesla Finder AE - Daily Tesla Digest Generator")
        print("\nAvailable commands:")
        print("  digest    - Generate daily digest from all configured URLs")
        print("  search    - Analyze a single Tesla search URL")
        print("  urls-list - List configured URLs")
        print("\nUse --help with any command for more details.")
        
        cli_span.set_attribute("help_displayed", True)
        logfire.info("ℹ️ Tesla Finder CLI help displayed")


if __name__ == "__main__":
    # Log application startup
    logfire.info(
        "🚀 Tesla Finder AE CLI Starting",
        timestamp=datetime.now().isoformat(),
        configured_urls=len(urls),
        logfire_enabled=True
    )
    
    try:
        app()
    except KeyboardInterrupt:
        logfire.info("⏹️ Tesla Finder AE CLI stopped by user")
    except Exception as e:
        logfire.error(
            "💥 Tesla Finder AE CLI crashed",
            error_type=type(e).__name__,
            error_message=str(e)
        )
        raise


if __name__ == "__main__":
    app()
