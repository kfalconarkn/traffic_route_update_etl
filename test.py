import pandas as pd
import requests

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
        return location['lat'], location['lon']
    else:
        # Log or print the error details for debugging
        print(f"Error: {data.get('error', 'No results found')}")
        return None, None

api_key = 'pk.a8230f042eb2ad0a79ed1c019ca037f1'
road_name = "Pacific Motorway"
state = "QLD"
country_code = "AU"
locality = "Pimpama"
description = "Exit 49"

latitude, longitude = geocode_road_name(road_name, api_key, country_code=country_code, locality=locality, description=description)

if latitude and longitude:
    print(f"The latitude and longitude for '{road_name}' are {latitude}, {longitude}.")
else:
    print(f"Could not find the latitude and longitude for '{road_name}'.")

