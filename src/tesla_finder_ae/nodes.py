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
    top_cheapest_cars: List[TeslaListing] = Field(description="Top 20 cheapest cars sorted by price", max_items=20)
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
        - Extracting individual Tesla listings with prices, years, MILEAGE, locations, and DIRECT LISTING URLs
        - For each listing, find and extract the specific URL link that leads to the individual car's detail page
        - Pay special attention to mileage information (km, miles, odometer reading) as this is crucial for buyers
        - Identifying the most common models (Model 3, Model Y, Model S, Model X)
        - Calculating price ranges and availability trends
        - Creating a concise daily summary for a Tesla buyer

        IMPORTANT: Always include the direct URL and mileage for each individual Tesla listing.
        Mileage formats may vary (e.g., "45,000 km", "28K miles", "30,000") - extract and preserve the format.
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
    Consolidate multiple Tesla summaries into single summary with top 20 cheapest cars

    Args:
        summaries: List of individual TeslaListingSummary objects

    Returns:
        TeslaConsolidatedSummary with consolidated metadata and top 20 cheapest cars
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
                summary="No Tesla listings found from any source."
            )

        # Extract all individual listings
        with logfire.span("Extract Individual Listings") as extract_span:
            all_listings = []
            for summary in summaries:
                all_listings.extend(summary.listings)

            extract_span.set_attribute("total_individual_listings", len(all_listings))

        # Parse prices and sort by price (cheapest first)
        with logfire.span("Price Parsing and Sorting") as sort_span:
            listings_with_prices = []

            for listing in all_listings:
                parsed_price = parse_price_to_numeric(listing.price)
                listings_with_prices.append((parsed_price, listing))

            # Sort by price (ascending - cheapest first)
            # Listings with price 0 (unparseable) will be at the end
            listings_with_prices.sort(key=lambda x: (x[0] == 0, x[0]))

            # Take top 20 cheapest cars
            top_20_cheapest = [listing for price, listing in listings_with_prices[:20]]

            sort_span.set_attributes({
                "total_listings_with_prices": len(listings_with_prices),
                "top_20_selected": len(top_20_cheapest),
                "price_range_processed": f"{listings_with_prices[0][0]} - {listings_with_prices[-1][0]}" if listings_with_prices else "No listings"
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

            # Calculate global price range
            if listings_with_prices:
                cheapest_price = listings_with_prices[0][0]
                most_expensive_price = max(price for price, _ in listings_with_prices if price > 0)
                global_price_range = f"AED {cheapest_price:,.0f} - AED {most_expensive_price:,.0f}"
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

Top 20 Cheapest Tesla Models (with URLs and mileage):
{chr(10).join([f"  {i+1}. {listing.title} - {listing.price} ({listing.year or 'Unknown year'}) | {listing.mileage or 'Mileage unknown'}{f' - {listing.url}' if listing.url else ''}" for i, listing in enumerate(top_20_cheapest)])}

Available Models: {', '.join(all_models)}
Available Locations: {', '.join(all_locations)}

Analysis completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Note: Individual listing URLs and mileage information are included for comprehensive car shopping decisions."""

            summary_span.set_attribute("summary_length", len(summary_text))

        # Create consolidated summary
        consolidated = TeslaConsolidatedSummary(
            source_urls=source_urls,
            total_listings_found=total_listings_found,
            global_price_range=global_price_range,
            all_models=all_models,
            all_locations=all_locations,
            top_cheapest_cars=top_20_cheapest,
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
            top_cars_selected=len(top_20_cheapest),
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