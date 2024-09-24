import requests
import pandas as pd
import json
import pytz
from datetime import datetime
import os
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

## API CALL
def get_traffic_events(api_key):
    url = "https://api.qldtraffic.qld.gov.au/v2/events"
    params = {"apikey": api_key}
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()  
    except requests.exceptions.HTTPError as http_err:
        logger.error(f"HTTP error occurred: {http_err}")
        return None
    except requests.exceptions.RequestException as req_err:
        logger.error(f"Request error occurred: {req_err}")
        return None
    
    data = response.json()
    return data

## COMVERT TO PANDAS DF
def convert_to_df(response):
    events = response['features']
    data = []
    for event in events:
        event_data = event['properties']
        coordinates = []  # Initialize coordinates as an empty list
        # Extracting line strings from geometries for coordinates
        geometry = event['geometry']
        if geometry['type'] == 'MultiLineString':
            for line_string in geometry['coordinates']:
                coordinates.extend(line_string)  # Correct usage of extend with a list
        elif geometry['type'] == 'LineString':
            coordinates.extend(geometry['coordinates'])  # Correct usage of extend with a list
        row = {
            "ID": event_data['id'],
            "event_type": event_data['event_type'],
            "event_subtype": event_data.get('event_subtype', ''),
            "event_due_to": event_data.get('event_due_to', ''),
            "direction": event_data['impact']['direction'],
            "towards": event_data['impact']['towards'],
            "impact_type": event_data['impact']['impact_type'],
            "impact_subtype": event_data['impact']['impact_subtype'],
            "duration_start": event_data['duration']['start'],
            "event_priority": event_data['event_priority'],
            "description": event_data.get('description', ''),
            "advice": event_data.get('advice', ''),
            "last_updated": event_data['last_updated'],
            "information": event_data.get('information', ''),
            "road_name": event_data['road_summary']['road_name'],
            "locality": event_data['road_summary']['locality'],
            "postcode": event_data['road_summary']['postcode'],
            "local_government_area": event_data['road_summary']['local_government_area'],
            "district": event_data['road_summary']['district'],
            "coordinates": coordinates  # Now coordinates is correctly formatted as a list
        }
        data.append(row)
    df = pd.DataFrame(data)

    # Parse the datetime columns directly without specifying a format
     # Convert to datetime without specifying the format, allowing pandas to infer it
    df['duration_start'] = pd.to_datetime(df['duration_start'], utc=True, errors='coerce')
    df['last_updated'] = pd.to_datetime(df['last_updated'], utc=True, errors='coerce')

    # Convert to the desired timezone
    df['duration_start'] = df['duration_start'].dt.tz_convert('Australia/Brisbane')
    df['last_updated'] = df['last_updated'].dt.tz_convert('Australia/Brisbane')

    # Now, format these datetime columns as strings in the format YYYY-MM-DD HH:MM:SS
    df['duration_start'] = df['duration_start'].dt.strftime('%Y-%m-%d %H:%M:%S')
    df['last_updated'] = df['last_updated'].dt.strftime('%Y-%m-%d %H:%M:%S')


    # Filter out other regions
    filter_df = df[df['local_government_area'].isin(['Gold Coast City', 'Sunshine Coast Regional', 'Noosa Shire'])]
    logger.info(f"Number activate traffic events on network {len(filter_df)}")
    return filter_df


## UPLOAD TO SUPABASE

def upload_to_db(df, table_name, supabase_key, supabase_url):
    headers = {
        'apikey': supabase_key,
        'Authorization': f'Bearer {supabase_key}',
        'Content-Type': 'application/json',
        'Prefer': 'return=representation'
    }

    data = df.to_dict(orient='records')
    endpoint = f"{supabase_url}/rest/v1/{table_name}"

    # Get existing IDs from Supabase table
    try:
        response = requests.get(endpoint, headers=headers)
        response.raise_for_status()  # This will raise an HTTPError for bad responses
        existing_data = response.json()

        if not isinstance(existing_data, list):
            logger.error(f"Unexpected response format: {existing_data}")
            return

        # Create a dictionary to store IDs as keys for fast lookup
        id_lookup = {str(item.get('ID')): item for item in existing_data if item.get('ID')}
        df_ids = set(df['ID'].astype(str).tolist())

        # Iterate through existing IDs in Supabase
        for supabase_id, item in id_lookup.items():
            # Check if the ID is not in the DataFrame's ID set and if the 'resolved' value is empty or null
            if supabase_id not in df_ids and (not item.get('resolved') or item.get('resolved').strip() == ''):
                # If the conditions are met, update the 'resolved' column with the current date and time
                resolved_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')  # Today's date in YYYY-MM-DD HH:MM:SS format
                update_data = {'resolved': resolved_date}  # Data to update
                update_endpoint = f"{supabase_url}/rest/v1/{table_name}?ID=eq.{supabase_id}"
                logger.info(f"Updating 'resolved' for ID {supabase_id}")
                update_response = requests.patch(update_endpoint, headers=headers, data=json.dumps(update_data))
                if update_response.status_code != 200:
                    logger.error(f"Error updating 'resolved' for ID {supabase_id}: {update_response.text}")
                else:
                    logger.info(f"Successfully updated 'resolved' for ID {supabase_id}. resolved: {resolved_date}")

        # Iterate through rows in the DataFrame for insertion or update record
        for item in data:
            item_id = item['ID']
            if item_id in id_lookup:
                # If the ID exists, update the corresponding row
                update_endpoint = f"{supabase_url}/rest/v1/{table_name}?ID=eq.{item_id}"
                print(f"Updating data with ID {item_id} at endpoint: {update_endpoint}")
                update_response = requests.patch(update_endpoint, headers=headers, data=json.dumps([item]))
                if update_response.status_code != 200:
                    logger.error(f"Error updating db with ID {item_id}: {update_response.text}")
                else:
                    logger.info(f"Successfully updated db with ID {item_id}.")
            else:
                # If the ID is new, append the row to the database
                print(f"Inserting new data with ID {item_id} at endpoint: {endpoint}")
                response = requests.post(endpoint, headers=headers, data=json.dumps([item]))
                if response.status_code != 201:
                    logger.error(f"Error inserting data with ID {item_id}: {response.text}")
                else:
                    logger.info(f"Successfully inserted data with ID {item_id}.")

    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching existing data: {e}")
        logger.error(f"Response content: {response.text}")
        return

