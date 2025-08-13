import requests
import pandas as pd
from datetime import datetime
from supabase import create_client, Client
from loguru import logger
import sys
import os

# Configure Loguru logger
logger.remove()  # Remove default handler
logger.add(sys.stderr, level=os.getenv("LOG_LEVEL", "INFO"), enqueue=True, backtrace=False, diagnose=False)

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
    """Upload DataFrame rows to Supabase using upsert on the ID column.

    Also marks any previously-unresolved rows as resolved when their ID is
    no longer present in the latest DataFrame.
    """

    supabase: Client = create_client(supabase_url, supabase_key)

    # Convert DataFrame to list of dicts for JSON upsert
    records = df.to_dict(orient='records')

    # Fetch existing IDs and resolved state to determine which should be marked resolved
    try:
        select_resp = supabase.table(table_name).select("ID,resolved").execute()
        existing_items = getattr(select_resp, "data", None)
        if existing_items is None:
            # Fallback if SDK returns a dict-like structure
            existing_items = select_resp.get("data", []) if isinstance(select_resp, dict) else []

        existing_lookup = {
            str(item.get("ID")): item
            for item in existing_items
            if item.get("ID") is not None
        }
        df_ids = set(str(r["ID"]) for r in records if "ID" in r)

        ids_to_resolve = [
            existing_id
            for existing_id, item in existing_lookup.items()
            if existing_id not in df_ids and (not item.get("resolved") or str(item.get("resolved")).strip() == "")
        ]
    except Exception as e:
        logger.error(f"Error fetching existing data: {e}")
        existing_lookup = {}
        ids_to_resolve = []

    # Perform upsert in chunks to avoid large payloads
    try:
        chunk_size = 500
        for start_index in range(0, len(records), chunk_size):
            chunk = records[start_index : start_index + chunk_size]
            if not chunk:
                continue
            logger.info(f"Upserting {len(chunk)} rows into {table_name}")
            supabase.table(table_name).upsert(chunk, on_conflict="ID").execute()
        logger.info("Upsert complete")
    except Exception as e:
        logger.error(f"Error during upsert: {e}")
        return

    # Mark missing IDs as resolved (only those previously unresolved)
    if ids_to_resolve:
        try:
            resolved_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            logger.info(f"Marking {len(ids_to_resolve)} rows as resolved")
            supabase.table(table_name).update({"resolved": resolved_date}).in_("ID", ids_to_resolve).execute()
            logger.info("Resolved update complete")
        except Exception as e:
            logger.error(f"Error updating resolved status: {e}")

    return

