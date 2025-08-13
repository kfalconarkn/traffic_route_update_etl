import os
import time
import logging
import sys
from functions import get_traffic_events, convert_to_df, upload_to_db
from route_check import BusRouteTrafficMatcher
from dotenv import load_dotenv
from loguru import logger

# Load environment variables
load_dotenv()

supabase_url = os.getenv('supabase_url')
supabase_key = os.getenv('supabase_key')
table_name = os.getenv('table_name') or 'traffic_events'
api_key = os.getenv('api_key')
geocode_api_key = os.getenv('geocode_api_key')

# Configure Loguru logger
logger.remove()  # Remove default handler
logger.add(sys.stderr, level=os.getenv("LOG_LEVEL", "INFO"), enqueue=True, backtrace=False, diagnose=False)

# Suppress HTTP request logs from various libraries
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("supabase").setLevel(logging.WARNING)

# Initialize the bus route matcher once at startup
matcher = BusRouteTrafficMatcher()
try:
    matcher.load_bus_routes('./data/route_data.json')
    matcher.calculate_road_segments()
    logger.info("Bus route matcher initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize bus route matcher: {e}")
    matcher = None

def upload_traffic_events():
    try:
        # Validate environment variables before proceeding
        missing_vars = [
            name for name, value in [
                ('supabase_url', supabase_url),
                ('supabase_key', supabase_key),
                ('table_name', table_name),
                ('api_key', api_key),
            ] if not value
        ]

        if missing_vars:
            logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
            return

        logger.info("Starting API call...")
        # Make API call
        data = get_traffic_events(api_key)
        logger.info("API call completed")
        
        if not data or 'features' not in data:
            logger.warning("No data returned from API or unexpected response format. Skipping this cycle.")
            return

        logger.info("Converting data to DataFrame...")
        # Convert JSON to DataFrame
        df = convert_to_df(data)
        logger.info("Data conversion complete")
        
        # Check for bus route intersections if matcher is available
        if matcher is not None:
            logger.info("Checking traffic events against bus routes...")
            try:
                affected_routes = matcher.find_affected_routes(
                    df,
                    tolerance_meters=1.0,
                    geocode_api_key=geocode_api_key,
                    country_code='AU'
                )
                
                # Add route information to DataFrame
                matcher.add_route_info_to_dataframe(df, affected_routes)
                logger.info("Route intersection analysis complete")
                
            except Exception as e:
                logger.error(f"Error during route intersection analysis: {e}")
                # Continue with upload even if route analysis fails
        else:
            logger.warning("Bus route matcher not available, skipping route analysis")
        
        logger.info("Uploading data to database...")
        # Upload to database
        upload_to_db(df, table_name, supabase_key, supabase_url)
        logger.info('Data upload complete')
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")

if __name__ == "__main__":
    # Single execution for GitHub Actions (triggered by Google Cloud Scheduler)
    logger.info("Starting traffic monitoring single execution...")
    upload_traffic_events()
    logger.info("Traffic monitoring execution completed successfully")




