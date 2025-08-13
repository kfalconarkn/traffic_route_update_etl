import requests
import json
from math import radians, sin, cos, sqrt, atan2
from groq import Groq
from dotenv import load_dotenv
import os
from pydantic import BaseModel

load_dotenv()

def find_closest_route(latitude, longitude, route_data, threshold_km=1.0):
    """
    Finds the closest bus route to a given latitude and longitude.

    Args:
        latitude (float): The latitude of the location.
        longitude (float): The longitude of the location.
        route_data (dict): A dictionary containing the bus route data.
        threshold_km (float): The maximum distance in kilometers for a route to be considered close.

    Returns:
        tuple: A tuple containing the route_id, trip_headsign, and distance of the closest route,
               or (None, None, None) if no route is within the threshold.
    """
    if latitude is None or longitude is None:
        return None, None, None
        
    min_dist = float('inf')
    closest_route = None

    for route_id, trips in route_data.items():
        for trip_headsign, coordinates in trips.items():
            for lon, lat in coordinates:
                dist = haversine(latitude, longitude, lat, lon)
                if dist < min_dist:
                    min_dist = dist
                    if min_dist < threshold_km:
                        closest_route = (route_id, trip_headsign, min_dist)

    if closest_route:
        return closest_route
    return None, None, None

def haversine(lat1, lon1, lat2, lon2):
    """
    Calculate the great circle distance in kilometers between two points
    on the earth (specified in decimal degrees).
    """
    # convert decimal degrees to radians
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])

    # haversine formula
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    r = 6371 # Radius of earth in kilometers.
    return c * r

def geocode_road_name(road_name, api_key, country_code=None, locality=None, description=None):
    query = road_name
    if locality:
        query += f", {locality}"
    if description:
        query += f", {description}"

    url = f"https://us1.locationiq.com/v1/search.php"
    params = {
        'key': api_key,
        'q': query,
        'format': 'json',
        'countrycodes': country_code
    }
    response = requests.get(url, params=params)
    data = response.json()

    # Check if the response contains valid data
    if isinstance(data, list) and data:
        location = data[0]
        # Ensure lat and lon are converted to float before returning
        return float(location['lat']), float(location['lon'])
    else:
        # Log or print the error details for debugging
        print(f"Error: {data.get('error', 'No results found')}")
        return None, None
    
    
## AI Data cleaning function 

class roadname_schema(BaseModel):
    road_name: str

def ai_clean_data(road_name: str):
    """ This Function is to clean the data from the TMR api data. output should be a structed json output.
    output required format. A roadname variable might have addtional information in the string but we only need to extract
    the first road name in the string.
    
    { 
    road_name: a single road name (string)
    } 
    """
    # load the model
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    
    response = client.chat.completions.create(
    messages=[
        {
            "role": "user",
            "content": "Extract the first road name from the following string: " + road_name,
        }
    ],
    model="moonshotai/kimi-k2-instruct",
    response_format={
        "type": "json_schema",
        "json_schema": {
            "name": "roadname_schema",
            "schema": roadname_schema.model_json_schema()
        }
    }
    )

    road_name = roadname_schema.model_validate(json.loads(response.choices[0].message.content))
 
    return road_name


if __name__ == "__main__":
    ## run  test ##

    ##extract road name from the data
    original_road_name = "Montana Road"
    road_name = ai_clean_data(original_road_name)
    print(road_name)

    ## constants ##
    api_key = 'pk.a8230f042eb2ad0a79ed1c019ca037f1'
    state = "QLD"
    country_code = "AU"

    ##input variables ##
    locality = "Mermaid beach"
    road_name = road_name.road_name
    description = ""
    ## coordinates is optional system should use traffic coordinaes if exists, if not default back to road name and get coordinates from locationiq
    coordinates = [[153.3376703, -27.9900039], [153.33808, -27.99029], [153.33815, -27.99034], [153.33816, -27.99035], [153.33818, -27.99036], [153.33823, -27.99039], [153.3382419, -27.9903951], [153.3359292, -27.9885944], [153.33593, -27.9886], [153.33598, -27.98874], [153.33602, -27.98881], [153.33606, -27.9889], [153.33616, -27.98904], [153.33622, -27.98911], [153.33628, -27.98918], [153.33632, -27.98922], [153.33637, -27.98927], [153.33641, -27.98931], [153.33648, -27.98936], [153.33658, -27.98943], [153.33693, -27.98962], [153.33717, -27.98974], [153.33744, -27.98988], [153.3376703, -27.9900039]]

    latitude, longitude = geocode_road_name(road_name, api_key, country_code=country_code, locality=locality, description=description)

    if latitude is not None and longitude is not None:
        print(f"The latitude and longitude for '{road_name}' are {latitude}, {longitude}.")
        
        # Load route data from JSON file
        with open('data/route_data.json', 'r') as f:
            route_data = json.load(f)
        
        # Find the closest route
        route_id, trip_headsign, distance = find_closest_route(latitude, longitude, route_data)
        
        if route_id and trip_headsign:
            print(f"The closest bus route is Route ID: {route_id}, Trip Headsign: {trip_headsign}.")
            print(f"Distance to route: {distance:.2f} km")
        else:
            print("No bus route found within the specified threshold.")
    else:
        print(f"Could not find the latitude and longitude for '{road_name}'.")

