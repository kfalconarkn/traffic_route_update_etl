import os
import time
import logging
from functions import get_traffic_events, convert_to_df, upload_to_db
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

supabase_url = os.getenv('supabase_url')
supabase_key = os.getenv('supabase_key')
table_name = os.getenv('table_name')
api_key = os.getenv('api_key')

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def upload_traffic_events():
    try:
        logger.info("Starting API call...")
        # Make API call
        data = get_traffic_events(api_key)
        logger.info("API call completed")
        
        logger.info("Converting data to DataFrame...")
        # Convert JSON to DataFrame
        df = convert_to_df(data)
        logger.info("Data conversion complete")
        
        logger.info("Uploading data to database...")
        # Upload to database
        upload_to_db(df, table_name, supabase_key, supabase_url)
        logger.info('Data upload complete')
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")

if __name__ == "__main__":
    while True:
        upload_traffic_events()
        logger.info("Waiting for the next 15 minutes")
        time.sleep(15 * 60)  # Sleep for 15 minutes




