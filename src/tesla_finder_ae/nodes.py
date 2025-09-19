from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime

import logfire
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage
from pydantic_ai.mcp import MCPServerStreamableHTTP
from pydantic_graph import BaseNode, End, Graph, GraphRunContext

from .observability import (
    configure_logfire, 
    TeslaObservabilityMixin,
    async_tesla_operation_span
)

# MCP server configuration
tavily_mcp_url = "https://mcp.tavily.com/mcp/?tavilyApiKey=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"


# Pydantic models for structured data
class TeslaListing(BaseModel):
    """Individual Tesla listing details"""
    title: str = Field(description="Car title/model")
    price: str = Field(description="Listed price")
    year: Optional[int] = Field(description="Year of manufacture")
    mileage: Optional[str] = Field(description="Vehicle mileage")
    location: Optional[str] = Field(description="Location/dealership")
    url: Optional[str] = Field(description="Direct listing URL")
    image_url: Optional[str] = Field(description="Main car image URL")

    # Z-score based scoring fields for finding "sweet spot" listings
    price_z_score: Optional[float] = Field(default=None, description="Price Z-score (distance from mean)")
    year_z_score: Optional[float] = Field(default=None, description="Year Z-score (distance from mean)")
    mileage_z_score: Optional[float] = Field(default=None, description="Mileage Z-score (distance from mean)")
    composite_score: Optional[float] = Field(default=None, description="Composite balance score (lower = more balanced)")
    balance_rating: Optional[str] = Field(default=None, description="Human-readable balance rating")


class TeslaListingSummary(BaseModel):
    """Summary of Tesla listings from a search URL"""
    source_url: str = Field(description="Original search URL")
    total_listings: int = Field(description="Total number of listings found")
    price_range: str = Field(description="Price range summary (e.g., '$25,000 - $85,000')")
    common_models: List[str] = Field(description="Most common Tesla models found")
    locations: List[str] = Field(description="Available locations/cities")
    listings: List[TeslaListing] = Field(description="Individual listing details", max_items=10)
    summary: str = Field(description="Human-readable summary for daily digest")
    analyzed_at: datetime = Field(default_factory=datetime.now, description="Analysis timestamp")


class TeslaConsolidatedSummary(BaseModel):
    """Consolidated summary of Tesla listings from multiple sources"""
    source_urls: List[str] = Field(description="All search URLs processed")
    total_listings_found: int = Field(description="Total listings across all sources")
    global_price_range: str = Field(description="Price range across all sources")
    all_models: List[str] = Field(description="All unique Tesla models found")
    all_locations: List[str] = Field(description="All unique locations found")
    top_cheapest_cars: List[TeslaListing] = Field(description="Top 20 best balanced cars (sweet spot analysis)", max_items=20)
    all_sorted_listings: List[TeslaListing] = Field(description="All Tesla listings sorted by balance score (Z-score based sweet spot analysis)")
    summary: str = Field(description="Human-readable consolidated summary")
    analyzed_at: datetime = Field(default_factory=datetime.now, description="Analysis timestamp")


# Utility functions
def parse_price_to_numeric(price_str: str) -> float:
    """
    Parse price string to numeric value for sorting

    Handles UAE Dirham formats like: "AED 45,000", "45,000 AED", "45K AED", "درهم 45,000", etc.
    Also handles generic formats: "$45,000", "$45K", "45000", etc.
    Returns 0 for unparseable prices (they'll sort last)
    """
    if not price_str or not isinstance(price_str, str):
        return 0.0

    # Remove common prefixes and suffixes, clean up
    clean_price = (price_str.strip()
                   .replace('AED', '')
                   .replace('aed', '')
                   .replace('درهم', '')  # Arabic for Dirham
                   .replace('$', '')
                   .replace(',', '')
                   .strip()
                   .upper())

    try:
        # Handle 'K' suffix (thousands)
        if clean_price.endswith('K'):
            number_part = clean_price[:-1]
            return float(number_part) * 1000

        # Handle 'M' suffix (millions)
        elif clean_price.endswith('M'):
            number_part = clean_price[:-1]
            return float(number_part) * 1000000

        # Try direct conversion
        else:
            return float(clean_price)

    except (ValueError, TypeError):
        # Return 0 for unparseable prices (they'll sort last)
        return 0.0


def parse_mileage_to_numeric(mileage_str: str) -> float:
    """
    Parse mileage string to numeric value for sorting (in kilometers)

    Handles formats like: "45,000 km", "28K miles", "30,000", "Mileage unknown", etc.
    Converts miles to km (multiply by 1.6)
    Returns 999999 for unparseable mileage (they'll sort last)
    """
    if not mileage_str or not isinstance(mileage_str, str):
        return 999999.0

    # Clean up the string
    clean_mileage = mileage_str.strip().replace(',', '').upper()

    # Check if it's unknown/unavailable
    if any(word in clean_mileage.lower() for word in ['unknown', 'unavailable', 'n/a', 'na', 'not available']):
        return 999999.0

    try:
        is_miles = False

        # Check for miles indicators
        if any(word in clean_mileage.lower() for word in ['mile', 'mi']):
            is_miles = True
            clean_mileage = re.sub(r'\b(miles?|mi)\b', '', clean_mileage, flags=re.IGNORECASE).strip()

        # Remove km indicators
        clean_mileage = re.sub(r'\b(km|kilometers?|kilometres?)\b', '', clean_mileage, flags=re.IGNORECASE).strip()

        # Handle 'K' suffix (thousands)
        if clean_mileage.endswith('K'):
            number_part = clean_mileage[:-1]
            value = float(number_part) * 1000
        else:
            value = float(clean_mileage)

        # Convert miles to km
        if is_miles:
            value *= 1.6

        return value

    except (ValueError, TypeError):
        # Return high number for unparseable mileage (they'll sort last)
        return 999999.0


def calculate_z_scores_and_composite_score(listings: List[TeslaListing]) -> List[TeslaListing]:
    """
    Calculate Z-scores for price, year, and mileage, then compute composite balance scores.
    Updates listings in-place with scoring information.

    Args:
        listings: List of TeslaListing objects to score

    Returns:
        Updated list of listings with scoring fields populated
    """
    import statistics
    import math

    if not listings or len(listings) < 2:
        # Not enough data for meaningful statistics
        for listing in listings:
            listing.price_z_score = 0.0
            listing.year_z_score = 0.0
            listing.mileage_z_score = 0.0
            listing.composite_score = 0.0
            listing.balance_rating = "Insufficient Data"
        return listings

    # Extract numeric values for statistics
    prices = []
    years = []
    mileages = []

    for listing in listings:
        # Parse price
        price = parse_price_to_numeric(listing.price)
        if price > 0:  # Exclude invalid prices
            prices.append(price)

        # Parse year
        if listing.year and listing.year > 2000:  # Reasonable year range
            years.append(listing.year)

        # Parse mileage
        mileage = parse_mileage_to_numeric(listing.mileage or "")
        if mileage < 999999:  # Exclude invalid mileage
            mileages.append(mileage)

    # Calculate statistics (need at least 2 valid values)
    price_mean = statistics.mean(prices) if len(prices) >= 2 else 0
    price_stdev = statistics.stdev(prices) if len(prices) >= 2 else 1

    year_mean = statistics.mean(years) if len(years) >= 2 else 0
    year_stdev = statistics.stdev(years) if len(years) >= 2 else 1

    mileage_mean = statistics.mean(mileages) if len(mileages) >= 2 else 0
    mileage_stdev = statistics.stdev(mileages) if len(mileages) >= 2 else 1

    # Calculate Z-scores for each listing
    for listing in listings:
        # Price Z-score
        price = parse_price_to_numeric(listing.price)
        if price > 0 and price_stdev > 0:
            listing.price_z_score = (price - price_mean) / price_stdev
        else:
            listing.price_z_score = 0.0

        # Year Z-score
        if listing.year and listing.year > 2000 and year_stdev > 0:
            listing.year_z_score = (listing.year - year_mean) / year_stdev
        else:
            listing.year_z_score = 0.0

        # Mileage Z-score
        mileage = parse_mileage_to_numeric(listing.mileage or "")
        if mileage < 999999 and mileage_stdev > 0:
            listing.mileage_z_score = (mileage - mileage_mean) / mileage_stdev
        else:
            listing.mileage_z_score = 0.0

        # Composite score (Euclidean distance from center across all dimensions)
        # Lower score = closer to statistical center = more balanced listing
        listing.composite_score = math.sqrt(
            (listing.price_z_score ** 2) +
            (listing.year_z_score ** 2) +
            (listing.mileage_z_score ** 2)
        )

        # Generate human-readable balance rating
        if listing.composite_score <= 0.5:
            listing.balance_rating = "Excellent Balance"
        elif listing.composite_score <= 1.0:
            listing.balance_rating = "Good Balance"
        elif listing.composite_score <= 1.5:
            listing.balance_rating = "Moderate Balance"
        else:
            listing.balance_rating = "Poor Balance"

    return listings


# State management for the graph
@dataclass
class TeslaSearchState:
    url: str
    summary_agent_messages: List[ModelMessage] = field(default_factory=list)


# Lazy-loaded MCP server and agent creation
def get_tesla_summary_agent() -> Agent:
    """Create Tesla summary agent with MCP integration (lazy-loaded)"""
    mcp_server = MCPServerStreamableHTTP(tavily_mcp_url)
    
    return Agent(
        "anthropic:claude-4-sonnet-20250514",
        output_type=TeslaListingSummary,
        toolsets=[mcp_server],  # MCP server provides web scraping tools
        system_prompt='''
        You are a Tesla car shopping assistant. Use the available web scraping tools to fetch Tesla search results
        and extract structured information about available Tesla vehicles.

        Focus on:
        - Fetching the provided URL using available tools with JavaScript rendering enabled
        - Extracting individual Tesla listings with prices, years, MILEAGE, locations, DIRECT LISTING URLs, and MAIN CAR IMAGES
        - For each listing, find and extract the specific URL link that leads to the individual car's detail page
        - Extract the main/primary image URL for each Tesla car listing (usually the first or featured image)
        - Pay special attention to mileage information (km, miles, odometer reading) as this is crucial for buyers
        - Identifying the most common models (Model 3, Model Y, Model S, Model X)
        - Calculating price ranges and availability trends
        - Creating a concise daily summary for a Tesla buyer

        IMPORTANT: Always include the direct URL, mileage, and main image URL for each individual Tesla listing.
        Mileage formats may vary (e.g., "45,000 km", "28K miles", "30,000") - extract and preserve the format.
        For images, extract the main/primary car photo URL (typically the first image shown in the listing).
        Be precise with data extraction and provide actionable insights for car shopping decisions.
        '''
    )


# Graph nodes
@dataclass
class FetchAndSummarizeTesla(BaseNode[TeslaSearchState, None, TeslaListingSummary], TeslaObservabilityMixin):
    """Fetches and summarizes Tesla listings using Pydantic AI with MCP tools"""
    
    async def run(
        self, 
        ctx: GraphRunContext[TeslaSearchState]
    ) -> End[TeslaListingSummary]:
        """Fetch URL and generate structured summary using MCP tools"""
        
        url = ctx.state.url
        
        # Log the start of processing
        self.log_url_processing_start(url, "fetch_and_summarize")
        
        with logfire.span(
            "Tesla Graph Node Execution",
            url=url,
            operation="fetch_and_summarize",
            node_type="FetchAndSummarizeTesla"
        ) as node_span:
            
            try:
                # Prepare prompt that instructs the agent to use MCP tools for fetching
                with logfire.span("Prompt Preparation") as prompt_span:
                    prompt = f"""
                    Please fetch and analyze Tesla search results from: {url}
                    
                    Use the available web scraping tools to:
                    1. Fetch the URL with JavaScript rendering enabled
                    2. Extract Tesla listing information from the rendered content
                    3. Structure the data according to the TeslaListingSummary format
                    
                    The URL to analyze: {url}
                    """
                    prompt_span.set_attribute("prompt_length", len(prompt))
                    prompt_span.set_attribute("url", url)
                
                # Get the agent and run it - Logfire will automatically trace the AI operations
                with logfire.span("Tesla Agent Creation and Execution") as agent_span:
                    agent = get_tesla_summary_agent()
                    agent_span.set_attribute("agent_model", "anthropic:claude-4-sonnet-20250514")
                    agent_span.set_attribute("has_mcp_toolset", True)
                    
                    # The agent.run call will be automatically instrumented by Logfire
                    # This will create spans for:
                    # - MCP tool calls
                    # - LLM requests/responses  
                    # - Token usage
                    # - Tool execution times
                    result = await agent.run(
                        prompt,
                        message_history=ctx.state.summary_agent_messages,
                    )
                
                # Update message history for context in future runs
                with logfire.span("Message History Update") as history_span:
                    new_messages = result.new_messages()
                    ctx.state.summary_agent_messages.extend(new_messages)
                    history_span.set_attribute("new_message_count", len(new_messages))
                    history_span.set_attribute("total_message_count", len(ctx.state.summary_agent_messages))
                
                # Process and validate the result
                with logfire.span("Result Processing") as result_span:
                    summary = result.output
                    summary.source_url = url
                    
                    # Log structured metrics about the analysis
                    metrics = {
                        "total_listings": summary.total_listings,
                        "price_range": summary.price_range,
                        "common_models_count": len(summary.common_models),
                        "locations_count": len(summary.locations),
                        "individual_listings_count": len(summary.listings)
                    }
                    
                    result_span.set_attributes(metrics)
                    node_span.set_attributes(metrics)
                    node_span.set_attribute("success", True)
                
                # Log successful completion
                self.log_url_processing_success(url, "fetch_and_summarize", metrics)
                
                # Log the summary as structured data for easy querying
                logfire.info(
                    "🎯 Tesla analysis completed",
                    summary=summary,
                    url=url,
                    metrics=metrics
                )
                
                return End(summary)
                
            except Exception as e:
                # Log the error with full context
                self.log_url_processing_error(url, "fetch_and_summarize", e)
                node_span.set_attribute("success", False)
                node_span.set_attribute("error_type", type(e).__name__)
                node_span.set_attribute("error_message", str(e))
                raise


# Create the Tesla search graph (simplified with single node)
tesla_search_graph = Graph(
    nodes=[FetchAndSummarizeTesla],
    state_type=TeslaSearchState
)


# Convenience function to run Tesla search
@async_tesla_operation_span("single_url_search")
async def search_tesla_listings(url: str) -> TeslaListingSummary:
    """
    Convenience function to fetch and summarize Tesla listings from a URL
    
    Args:
        url: Tesla search results URL
        
    Returns:
        TeslaListingSummary with structured listing data
    """
    with logfire.span("Tesla Single URL Search", url=url) as search_span:
        # Initialize Logfire if not already configured
        try:
            logfire.info("🔥 Logfire status check")
        except:
            configure_logfire()
        
        logfire.info("🚗 Starting single Tesla URL search", url=url)
        
        state = TeslaSearchState(url=url)
        search_span.set_attribute("state_initialized", True)
        
        with logfire.span("Graph Execution") as graph_span:
            result = await tesla_search_graph.run(FetchAndSummarizeTesla(), state=state)
            graph_span.set_attribute("graph_completed", True)
            graph_span.set_attribute("result_type", type(result.output).__name__)
        
        search_span.set_attribute("search_completed", True)
        logfire.info("✅ Single Tesla URL search completed", url=url)
        
        return result.output


# Batch processing for multiple URLs (daily digest)
@async_tesla_operation_span("daily_digest_batch")
async def generate_daily_tesla_digest(urls: List[str]) -> List[TeslaListingSummary]:
    """
    Generate daily digest from multiple Tesla search URLs
    
    Args:
        urls: List of Tesla search URLs to process
        
    Returns:
        List of TeslaListingSummary objects
    """
    # Initialize Logfire if not already configured
    try:
        logfire.info("🔥 Logfire status check")
    except:
        configure_logfire()
    
    start_time = time.time()
    
    with logfire.span(
        "Tesla Daily Digest Generation", 
        url_count=len(urls),
        urls=urls
    ) as digest_span:
        
        # Log batch processing start using mixin
        mixin = TeslaObservabilityMixin()
        mixin.log_batch_processing_start(urls)
        
        summaries = []
        
        with logfire.span("Concurrent Task Creation") as task_span:
            # Process URLs concurrently for efficiency
            tasks = []
            for i, url in enumerate(urls):
                with logfire.span(f"Task Creation {i+1}", url=url) as creation_span:
                    state = TeslaSearchState(url=url)
                    task = tesla_search_graph.run(FetchAndSummarizeTesla(), state=state)
                    tasks.append(task)
                    creation_span.set_attribute("task_created", True)
            
            task_span.set_attribute("total_tasks_created", len(tasks))
        
        with logfire.span("Concurrent Execution") as execution_span:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            execution_span.set_attribute("total_results", len(results))
        
        # Process results and track success/failure rates
        successful_count = 0
        failed_count = 0
        
        with logfire.span("Result Processing") as processing_span:
            for i, result in enumerate(results):
                url = urls[i]
                
                if isinstance(result, Exception):
                    failed_count += 1
                    logfire.error(
                        "❌ Failed to process Tesla URL in batch",
                        url=url,
                        error_type=type(result).__name__,
                        error_message=str(result),
                        batch_index=i
                    )
                    print(f"Failed to process URL {url}: {result}")
                else:
                    successful_count += 1
                    summaries.append(result.output)
                    logfire.debug(
                        "✅ Successfully processed Tesla URL in batch",
                        url=url,
                        batch_index=i,
                        listings_found=result.output.total_listings
                    )
            
            processing_span.set_attributes({
                "successful_urls": successful_count,
                "failed_urls": failed_count,
                "success_rate": successful_count / len(urls) if urls else 0,
                "total_summaries": len(summaries)
            })
        
        # Calculate processing time
        processing_time = time.time() - start_time
        
        # Set final span attributes
        digest_span.set_attributes({
            "processing_time_seconds": processing_time,
            "successful_urls": successful_count,
            "failed_urls": failed_count,
            "success_rate": successful_count / len(urls) if urls else 0
        })
        
        # Log batch completion
        mixin.log_batch_processing_complete(
            len(urls), successful_count, failed_count, processing_time
        )
        
        # Log aggregated metrics from all summaries
        if summaries:
            total_listings = sum(s.total_listings for s in summaries)
            all_models = set()
            all_locations = set()
            
            for summary in summaries:
                all_models.update(summary.common_models)
                all_locations.update(summary.locations)
            
            logfire.info(
                "📊 Tesla Daily Digest Summary",
                total_urls_processed=len(urls),
                successful_analyses=successful_count,
                total_tesla_listings_found=total_listings,
                unique_models_found=list(all_models),
                unique_locations_found=list(all_locations),
                processing_time_seconds=processing_time,
                average_listings_per_url=total_listings / successful_count if successful_count > 0 else 0
            )
    
    return summaries


# Consolidation function for single summary with top 20 cheapest cars
@async_tesla_operation_span("consolidate_summaries")
async def consolidate_tesla_summaries(summaries: List[TeslaListingSummary]) -> TeslaConsolidatedSummary:
    """
    Consolidate multiple Tesla summaries into single summary with top 20 "sweet spot" cars using Z-score analysis

    Args:
        summaries: List of individual TeslaListingSummary objects

    Returns:
        TeslaConsolidatedSummary with consolidated metadata and top 20 cars sorted by balance score (sweet spot analysis)
    """
    with logfire.span(
        "Tesla Summary Consolidation",
        summary_count=len(summaries)
    ) as consolidation_span:

        if not summaries:
            return TeslaConsolidatedSummary(
                source_urls=[],
                total_listings_found=0,
                global_price_range="No listings found",
                all_models=[],
                all_locations=[],
                top_cheapest_cars=[],
                all_sorted_listings=[],
                summary="No Tesla listings found from any source."
            )

        # Extract all individual listings
        with logfire.span("Extract Individual Listings") as extract_span:
            all_listings = []
            for summary in summaries:
                all_listings.extend(summary.listings)

            extract_span.set_attribute("total_individual_listings", len(all_listings))

        # Calculate Z-scores and sort by composite balance score (sweet spot sorting)
        with logfire.span("Z-Score Calculation and Balance Sorting") as sort_span:
            # Calculate Z-scores and composite scores for all listings
            scored_listings = calculate_z_scores_and_composite_score(all_listings)

            # Sort by composite score (ascending) - lower scores mean better balance
            # Secondary sort by price for ties
            scored_listings.sort(key=lambda listing: (
                listing.composite_score if listing.composite_score is not None else 999,
                parse_price_to_numeric(listing.price)
            ))

            # Take top 20 cars with best balance scores
            top_20_sorted = scored_listings[:20]

            # Get ALL sorted listings for HTML report
            all_sorted_listings = scored_listings

            sort_span.set_attributes({
                "total_listings_processed": len(scored_listings),
                "top_20_selected": len(top_20_sorted),
                "sorting_criteria": "composite_balance_score_asc (Z-score based)",
                "best_balance_score": top_20_sorted[0].composite_score if top_20_sorted else None,
                "worst_balance_score": scored_listings[-1].composite_score if scored_listings else None,
                "scoring_method": "euclidean_distance_from_statistical_center"
            })

        # Aggregate metadata
        with logfire.span("Metadata Aggregation") as metadata_span:
            source_urls = [summary.source_url for summary in summaries]
            total_listings_found = sum(summary.total_listings for summary in summaries)

            # Collect all models and locations
            all_models_set = set()
            all_locations_set = set()

            for summary in summaries:
                all_models_set.update(summary.common_models)
                all_locations_set.update(summary.locations)

            all_models = sorted(list(all_models_set))
            all_locations = sorted(list(all_locations_set))

            # Calculate global price range from scored listings
            if scored_listings:
                prices = [parse_price_to_numeric(listing.price) for listing in scored_listings]
                valid_prices = [price for price in prices if price > 0]
                if valid_prices:
                    cheapest_price = min(valid_prices)
                    most_expensive_price = max(valid_prices)
                    global_price_range = f"AED {cheapest_price:,.0f} - AED {most_expensive_price:,.0f}"
                else:
                    global_price_range = "No valid prices found"
            else:
                global_price_range = "No valid prices found"

            metadata_span.set_attributes({
                "unique_models": len(all_models),
                "unique_locations": len(all_locations),
                "total_listings_found": total_listings_found,
                "global_price_range": global_price_range
            })

        # Generate consolidated summary text
        with logfire.span("Summary Generation") as summary_span:
            summary_text = f"""Tesla Market Analysis Summary:

Found {total_listings_found} Tesla listings across {len(source_urls)} sources.
Price range: {global_price_range}

Top 20 "Sweet Spot" Tesla Models (sorted by balance score - closest to statistical center):
{chr(10).join([f"  {i+1}. {listing.title} - {listing.price} ({listing.year or 'Unknown year'}) | {listing.mileage or 'Mileage unknown'} | Balance: {listing.balance_rating} (Score: {listing.composite_score:.2f}){f' - {listing.url}' if listing.url else ''}" for i, listing in enumerate(top_20_sorted)])}

Available Models: {', '.join(all_models)}
Available Locations: {', '.join(all_locations)}

Analysis completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Note: Cars are sorted using Z-score analysis to find the optimal balance between price, year, and mileage. Lower balance scores indicate better overall value positioning."""

            summary_span.set_attribute("summary_length", len(summary_text))

        # Create consolidated summary
        consolidated = TeslaConsolidatedSummary(
            source_urls=source_urls,
            total_listings_found=total_listings_found,
            global_price_range=global_price_range,
            all_models=all_models,
            all_locations=all_locations,
            top_cheapest_cars=top_20_sorted,
            all_sorted_listings=all_sorted_listings,
            summary=summary_text
        )

        consolidation_span.set_attributes({
            "consolidation_successful": True,
            "final_top_cars_count": len(consolidated.top_cheapest_cars),
            "final_models_count": len(consolidated.all_models),
            "final_locations_count": len(consolidated.all_locations)
        })

        logfire.info(
            "🎯 Tesla summaries consolidated successfully",
            source_count=len(summaries),
            total_listings=total_listings_found,
            top_cars_selected=len(top_20_sorted),
            price_range=global_price_range
        )

        return consolidated


# Enhanced daily digest that returns consolidated summary
@async_tesla_operation_span("generate_consolidated_daily_digest")
async def generate_consolidated_daily_tesla_digest(urls: List[str]) -> TeslaConsolidatedSummary:
    """
    Generate consolidated daily Tesla digest with top 20 cheapest cars from multiple URLs

    Args:
        urls: List of Tesla search URLs to process

    Returns:
        TeslaConsolidatedSummary with top 20 cheapest cars and combined metadata
    """
    with logfire.span(
        "Tesla Consolidated Daily Digest",
        url_count=len(urls)
    ) as digest_span:

        logfire.info("🚗 Starting consolidated Tesla daily digest", url_count=len(urls), urls=urls)

        # Get individual summaries first
        summaries = await generate_daily_tesla_digest(urls)
        digest_span.set_attribute("individual_summaries_count", len(summaries))

        # Consolidate into single summary
        consolidated = await consolidate_tesla_summaries(summaries)

        digest_span.set_attributes({
            "consolidated_summary_created": True,
            "top_cars_count": len(consolidated.top_cheapest_cars),
            "total_listings": consolidated.total_listings_found
        })

        logfire.info("✅ Consolidated Tesla daily digest completed",
                    top_cars=len(consolidated.top_cheapest_cars),
                    total_listings=consolidated.total_listings_found)

        return consolidated