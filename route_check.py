import json
import os
import requests
import math
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import time
from functions import get_traffic_events, convert_to_df
from test import geocode_road_name
import sys
from loguru import logger

# Configure logger (level via env var LOG_LEVEL, default INFO)
logger.remove()
logger.add(sys.stderr, level=os.getenv("LOG_LEVEL", "INFO"), enqueue=True, backtrace=False, diagnose=False)

@dataclass
class Location:
    """Represents a geographic location with latitude and longitude."""
    lat: float
    lng: float

@dataclass
class BusRoute:
    """Represents a bus route with directions and road segments."""
    route_id: str
    directions: Dict[str, List[Location]]  # direction_name -> coordinate path
    
@dataclass
class RouteDirection:
    """Represents a specific direction of a bus route."""
    route_id: str
    direction: str
    coordinates: List[Location]

@dataclass
class TrafficEvent:
    """Represents a traffic event at a specific location."""
    event_id: str
    location: Location
    description: str

class BusRouteTrafficMatcher:
    """
    Main class for matching traffic events to bus routes.
    """
    
    def __init__(self, osrm_url: str = "http://router.project-osrm.org"):
        """
        Initialize the matcher.
        
        Args:
            osrm_url: URL for OSRM routing service (not needed for your data format)
        """
        self.osrm_url = osrm_url
        self.bus_routes = []
        self.route_directions = []  # List of individual route directions
        logger.debug("Initialized BusRouteTrafficMatcher with OSRM URL: {}", osrm_url)
        
    def load_bus_routes(self, json_file_path: str) -> None:
        """
        Load bus route data from JSON file.
        
        Expected JSON format (your format):
        {
            "600-4289": {
                "Caloundra station": [
                    [153.091325, -26.654874],  // [lng, lat]
                    [153.093219, -26.654964],
                    ...
                ],
                "Maroochydore station": [
                    [153.133391, -26.805579],
                    ...
                ]
            }
        }
        
        Where:
        - "600-4289" is the route number/ID
        - "Caloundra station" is the direction/destination 
        - Coordinates are the path taken towards that destination
        """
        logger.info("Loading bus routes from {}", json_file_path)
        try:
            with open(json_file_path, 'r') as file:
                data = json.load(file)
            for route_id, route_directions in data.items():
                directions_dict = {}
                for direction_name, coordinates in route_directions.items():
                    direction_coords = [Location(lat=coord[1], lng=coord[0]) for coord in coordinates]
                    directions_dict[direction_name] = direction_coords
                    route_direction = RouteDirection(
                        route_id=route_id,
                        direction=direction_name,
                        coordinates=direction_coords
                    )
                    self.route_directions.append(route_direction)
                route = BusRoute(route_id=route_id, directions=directions_dict)
                self.bus_routes.append(route)
                logger.debug("Loaded route {} with {} directions", route_id, len(directions_dict))
            logger.info("Loaded {} routes and {} directions", len(self.bus_routes), len(self.route_directions))
        except Exception:
            logger.exception("Error loading bus routes from {}", json_file_path)
            
    def get_road_route(self, start: Location, end: Location) -> List[Location]:
        """
        Get the actual road route between two points using OSRM.
        
        Args:
            start: Starting location
            end: Ending location
            
        Returns:
            List of locations representing the road route
        """
        try:
            url = f"{self.osrm_url}/route/v1/driving/{start.lng},{start.lat};{end.lng},{end.lat}"
            params = {
                'overview': 'full',
                'geometries': 'geojson',
                'steps': 'false'
            }
            logger.debug("Requesting OSRM route: {} with params {}", url, params)
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            if data['code'] == 'Ok' and data['routes']:
                coordinates = data['routes'][0]['geometry']['coordinates']
                logger.debug("OSRM returned route with {} points", len(coordinates))
                return [Location(lat=coord[1], lng=coord[0]) for coord in coordinates]
            else:
                logger.warning("No route found between {} and {}", start, end)
                return []
        except Exception:
            logger.exception("Error getting road route between {} and {}", start, end)
            return []
    
    def calculate_road_segments(self) -> None:
        """
        For your data format, road coordinates are already provided.
        This method validates and reports on the loaded route directions.
        """
        logger.info("Loaded {} bus routes with {} total directions", len(self.bus_routes), len(self.route_directions))
        
        for route in self.bus_routes:
            for direction_name, coordinates in route.directions.items():
                coord_count = len(coordinates)
                if coord_count > 0:
                    start = coordinates[0]
                    end = coordinates[-1]
                    logger.debug("Route {} direction '{}' has {} points from ({:.6f},{:.6f}) to ({:.6f},{:.6f})", route.route_id, direction_name, coord_count, start.lat, start.lng, end.lat, end.lng)
                else:
                    logger.warning("Route {} direction '{}' has no coordinates", route.route_id, direction_name)
    
    def haversine_distance(self, loc1: Location, loc2: Location) -> float:
        """
        Calculate the great circle distance between two points in meters.
        """
        R = 6371000  # Earth radius in meters
        
        lat1_rad = math.radians(loc1.lat)
        lat2_rad = math.radians(loc2.lat)
        delta_lat = math.radians(loc2.lat - loc1.lat)
        delta_lng = math.radians(loc2.lng - loc1.lng)
        
        a = (math.sin(delta_lat / 2) ** 2 + 
             math.cos(lat1_rad) * math.cos(lat2_rad) * 
             math.sin(delta_lng / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        
        return R * c
    
    def point_to_line_distance(self, point: Location, line_start: Location, line_end: Location) -> float:
        """
        Calculate the shortest distance from a point to a line segment.
        """
        # Convert to Cartesian coordinates for easier calculation
        def to_cartesian(loc):
            x = loc.lng * 111320 * math.cos(math.radians(loc.lat))
            y = loc.lat * 111320
            return x, y
        
        px, py = to_cartesian(point)
        ax, ay = to_cartesian(line_start)
        bx, by = to_cartesian(line_end)
        
        # Vector from A to B
        ab_x, ab_y = bx - ax, by - ay
        # Vector from A to P
        ap_x, ap_y = px - ax, py - ay
        
        # Project P onto AB
        ab_squared = ab_x * ab_x + ab_y * ab_y
        if ab_squared == 0:
            return math.sqrt((px - ax) ** 2 + (py - ay) ** 2)
        
        t = max(0, min(1, (ap_x * ab_x + ap_y * ab_y) / ab_squared))
        
        # Find the projection point
        proj_x = ax + t * ab_x
        proj_y = ay + t * ab_y
        
        # Distance from P to projection
        return math.sqrt((px - proj_x) ** 2 + (py - proj_y) ** 2)
    
    def point_on_line_segment(self, point: Location, line_start: Location, line_end: Location, tolerance_meters: float = 1.0) -> bool:
        """
        Check if a point lies on a line segment within a very small tolerance.
        Uses cross product to check collinearity and dot product to check if point is within segment bounds.
        """
        # Convert to Cartesian coordinates for precise calculation
        def to_cartesian(loc):
            x = loc.lng * 111320 * math.cos(math.radians(loc.lat))
            y = loc.lat * 111320
            return x, y
        
        px, py = to_cartesian(point)
        ax, ay = to_cartesian(line_start)
        bx, by = to_cartesian(line_end)
        
        # Vector from A to B
        ab_x, ab_y = bx - ax, by - ay
        # Vector from A to P
        ap_x, ap_y = px - ax, py - ay
        
        # Check if point is collinear with line segment using cross product
        cross_product = abs(ap_x * ab_y - ap_y * ab_x)
        line_length = math.sqrt(ab_x * ab_x + ab_y * ab_y)
        
        if line_length == 0:
            # Line segment is actually a point
            distance = math.sqrt(ap_x * ap_x + ap_y * ap_y)
            return distance <= tolerance_meters
        
        # Distance from point to line (perpendicular distance)
        distance_to_line = cross_product / line_length
        
        if distance_to_line > tolerance_meters:
            return False
        
        # Check if point is within the segment bounds using dot product
        dot_product = ap_x * ab_x + ap_y * ab_y
        if dot_product < 0 or dot_product > ab_x * ab_x + ab_y * ab_y:
            return False
        
        return True
    
    def line_segments_intersect(self, line1_start: Location, line1_end: Location, 
                               line2_start: Location, line2_end: Location) -> bool:
        """
        Check if two line segments intersect using the cross product method.
        Returns True if the segments intersect, False otherwise.
        """
        def to_cartesian(loc):
            x = loc.lng * 111320 * math.cos(math.radians(loc.lat))
            y = loc.lat * 111320
            return x, y
        
        # Convert all points to Cartesian
        x1, y1 = to_cartesian(line1_start)
        x2, y2 = to_cartesian(line1_end)
        x3, y3 = to_cartesian(line2_start)
        x4, y4 = to_cartesian(line2_end)
        
        # Calculate the direction of the four triplets
        def orientation(px, py, qx, qy, rx, ry):
            val = (qy - py) * (rx - qx) - (qx - px) * (ry - qy)
            if abs(val) < 1e-10:  # Collinear
                return 0
            return 1 if val > 0 else 2  # Clockwise or Counterclockwise
        
        # Check if point q lies on segment pr
        def on_segment(px, py, qx, qy, rx, ry):
            return (qx <= max(px, rx) and qx >= min(px, rx) and
                    qy <= max(py, ry) and qy >= min(py, ry))
        
        o1 = orientation(x1, y1, x2, y2, x3, y3)
        o2 = orientation(x1, y1, x2, y2, x4, y4)
        o3 = orientation(x3, y3, x4, y4, x1, y1)
        o4 = orientation(x3, y3, x4, y4, x2, y2)
        
        # General case
        if o1 != o2 and o3 != o4:
            return True
        
        # Special cases - collinear points
        if (o1 == 0 and on_segment(x1, y1, x3, y3, x2, y2)) or \
           (o2 == 0 and on_segment(x1, y1, x4, y4, x2, y2)) or \
           (o3 == 0 and on_segment(x3, y3, x1, y1, x4, y4)) or \
           (o4 == 0 and on_segment(x3, y3, x2, y2, x4, y4)):
            return True
        
        return False
    
    def polylines_intersect(self, polyline1: List[Location], polyline2: List[Location]) -> Tuple[bool, List[int]]:
        """
        Check if two polylines intersect at any point.
        Returns (intersects: bool, intersection_segments: List[int]) where intersection_segments
        contains the indices of polyline1 segments that intersect with polyline2.
        """
        if not polyline1 or not polyline2 or len(polyline1) < 2 or len(polyline2) < 2:
            return False, []
        
        intersecting_segments = []
        
        # Check each segment of polyline1 against each segment of polyline2
        for i in range(len(polyline1) - 1):
            for j in range(len(polyline2) - 1):
                if self.line_segments_intersect(
                    polyline1[i], polyline1[i + 1],
                    polyline2[j], polyline2[j + 1]
                ):
                    if i not in intersecting_segments:
                        intersecting_segments.append(i)
        
        return len(intersecting_segments) > 0, intersecting_segments
    
    def point_on_polyline(self, point: Location, polyline: List[Location], tolerance_meters: float = 1.0) -> Tuple[bool, Optional[int]]:
        """
        Check if a point lies on any segment of a polyline.
        Returns (is_on_polyline: bool, segment_index: Optional[int])
        """
        if not polyline or len(polyline) < 2:
            return False, None
        
        for i in range(len(polyline) - 1):
            if self.point_on_line_segment(point, polyline[i], polyline[i + 1], tolerance_meters):
                return True, i
        
        return False, None
    
    def is_traffic_event_on_route(self, event: TrafficEvent, route: BusRoute, 
                                  threshold_meters: float = 50.0) -> Dict[str, any]:
        """Legacy method not used in the DataFrame-based flow."""
        return {'is_match': False, 'segment': None, 'distance': float('inf')}
    

    
    def find_affected_routes(self, traffic_df, 
                           tolerance_meters: float = 1.0,
                           geocode_api_key: Optional[str] = None,
                           country_code: Optional[str] = 'AU') -> Dict[str, Dict[str, any]]:
        """
        Find which bus routes are affected by traffic events using precise geometric intersection.
        
        For traffic events with coordinates (polylines): Check if the event polyline intersects 
        with any bus route polyline.
        
        For traffic events with single point (geocoded): Check if the point lies on any 
        bus route polyline within a very small tolerance (default 1m for GPS accuracy).
        
        This ensures we only flag routes where the traffic event is actually ON the bus path,
        not just nearby.
        """
        results = {}
        if traffic_df is None or len(traffic_df) == 0:
            logger.info("No traffic events to process")
            return results
        logger.info("Processing {} traffic events with geometric intersection (tolerance: {}m)", len(traffic_df), tolerance_meters)
        
        for _, row in traffic_df.iterrows():
            event_id = str(row.get('ID'))
            road_name = row.get('road_name')
            locality = row.get('locality')
            description = row.get('description', '')
            coordinates = row.get('coordinates') or []
            
            event_points: List[Location] = []
            location_repr = None
            is_polyline = False
            
            # Use provided coordinates if available (list of [lng, lat])
            if isinstance(coordinates, list) and len(coordinates) > 0:
                logger.debug("Event {} has {} coordinate points; checking for polyline intersection", event_id, len(coordinates))
                for coord in coordinates:
                    try:
                        lng, lat = float(coord[0]), float(coord[1])
                        event_points.append(Location(lat=lat, lng=lng))
                    except Exception:
                        logger.debug("Skipping invalid coordinate {} for event {}", coord, event_id)
                        continue
                location_repr = f"polyline {len(event_points)} points"
                is_polyline = len(event_points) >= 2
            else:
                # Fallback to geocoding
                if geocode_api_key and road_name and locality:
                    logger.debug("Event {} missing coordinates; geocoding '{}' in '{}'", event_id, road_name, locality)
                    lat, lng = geocode_road_name(road_name, geocode_api_key, country_code=country_code, locality=locality, description=description)
                    if lat is not None and lng is not None:
                        event_points = [Location(lat=lat, lng=lng)]
                        location_repr = f"({lat:.6f}, {lng:.6f})"
                        is_polyline = False
                    else:
                        logger.warning("Geocoding failed for event {} with road '{}' and locality '{}'", event_id, road_name, locality)
                else:
                    logger.warning("Event {} has no coordinates and cannot geocode (missing key or fields)", event_id)
            
            if not event_points:
                logger.debug("Skipping event {} due to no usable location points", event_id)
                continue
            
            affected_directions = []
            
            for route_direction in self.route_directions:
                intersection_found = False
                intersection_type = None
                segment_indices = []
                
                if is_polyline:
                    # Check polyline-to-polyline intersection
                    intersects, intersecting_segments = self.polylines_intersect(event_points, route_direction.coordinates)
                    if intersects:
                        intersection_found = True
                        intersection_type = "polyline_intersection"
                        segment_indices = intersecting_segments
                        logger.debug("Event {} polyline intersects with route {} direction '{}' at segments {}", 
                                   event_id, route_direction.route_id, route_direction.direction, intersecting_segments)
                else:
                    # Check if single point lies on the route polyline
                    point = event_points[0]
                    is_on_route, segment_index = self.point_on_polyline(point, route_direction.coordinates, tolerance_meters)
                    if is_on_route:
                        intersection_found = True
                        intersection_type = "point_on_route"
                        segment_indices = [segment_index] if segment_index is not None else []
                        logger.debug("Event {} point lies on route {} direction '{}' at segment {}", 
                                   event_id, route_direction.route_id, route_direction.direction, segment_index)
                
                if intersection_found:
                    affected_directions.append({
                        'route_id': route_direction.route_id,
                        'direction': route_direction.direction,
                        'intersection_type': intersection_type,
                        'segment_indices': segment_indices,
                        'total_segments': len(route_direction.coordinates) - 1 if len(route_direction.coordinates) > 1 else 0
                    })
            
            if affected_directions:
                logger.info("Event {} intersects with {} route directions", event_id, len(affected_directions))
                results[event_id] = {
                    'location': location_repr if location_repr else 'unknown',
                    'description': description,
                    'event_type': 'polyline' if is_polyline else 'point',
                    'affected_directions': affected_directions
                }
            else:
                logger.debug("Event {} does not intersect with any route directions", event_id)
        
        return results
    
    def add_route_info_to_dataframe(self, traffic_df, affected_routes) -> None:
        """
        Add route and headsign information to the traffic DataFrame based on affected routes.
        
        Args:
            traffic_df: The traffic events DataFrame
            affected_routes: Dictionary of affected routes from find_affected_routes()
        """
        logger.info("Adding route information to {} traffic events", len(traffic_df))
        
        # Initialize new columns with None values
        traffic_df['route'] = None
        traffic_df['headsign'] = None
        
        for index, row in traffic_df.iterrows():
            event_id = str(row['ID'])
            
            if event_id in affected_routes:
                affected_directions = affected_routes[event_id]['affected_directions']
                
                # Extract unique route and headsign combinations
                route_headsign_combos = []
                for direction in affected_directions:
                    combo = f"{direction['route_id']}|{direction['direction']}"
                    if combo not in route_headsign_combos:
                        route_headsign_combos.append(combo)
                
                if route_headsign_combos:
                    # Extract routes and headsigns separately
                    raw_routes = [combo.split('|')[0] for combo in route_headsign_combos]
                    headsigns = [combo.split('|')[1] for combo in route_headsign_combos]
                    
                    # Clean route numbers by removing everything after '-' (including the '-')
                    cleaned_routes = [route.split('-')[0] for route in raw_routes]
                    
                    # Remove duplicates while preserving order
                    unique_cleaned_routes = []
                    unique_headsigns = []
                    seen_routes = set()
                    for i, route in enumerate(cleaned_routes):
                        if route not in seen_routes:
                            unique_cleaned_routes.append(route)
                            unique_headsigns.append(headsigns[i])
                            seen_routes.add(route)
                    
                    # Store as JSONB-compatible format
                    # Single values stored as strings, multiple values as arrays
                    route_value = unique_cleaned_routes[0] if len(unique_cleaned_routes) == 1 else unique_cleaned_routes
                    headsign_value = unique_headsigns[0] if len(unique_headsigns) == 1 else unique_headsigns
                    
                    traffic_df.at[index, 'route'] = route_value
                    traffic_df.at[index, 'headsign'] = headsign_value
                    
                    logger.debug("Event {} affects routes {} (cleaned from {}) with headsigns {}", 
                               event_id, unique_cleaned_routes, raw_routes, unique_headsigns)
        
        affected_count = traffic_df['route'].notna().sum()
        logger.info("Added route information to {} out of {} traffic events", affected_count, len(traffic_df))

class TrafficAPIIntegration:
    """
    Helper class for integrating with various traffic APIs.
    """
    
    @staticmethod
    def parse_traffic_events_from_api(api_response: Dict) -> List[TrafficEvent]:
        """
        Parse traffic events from API response. 
        Adapt this method based on your specific traffic API format.
        
        Example for a generic traffic API response:
        {
            "events": [
                {
                    "id": "evt_123",
                    "latitude": -27.4688,
                    "longitude": 153.0261,
                    "description": "Accident reported"
                }
            ]
        }
        """
        events = []
        for event_data in api_response.get('events', []):
            event = TrafficEvent(
                event_id=event_data['id'],
                location=Location(
                    lat=event_data['latitude'],
                    lng=event_data['longitude']
                ),
                description=event_data['description']
            )
            events.append(event)
        return events

# Enhanced example usage
def main():
    # traffic event api key
    api_key = os.getenv('api_key')
    # geocoding api key (LocationIQ)
    geocode_api_key = os.getenv('geocode_api_key')
    # Initialize the matcher
    matcher = BusRouteTrafficMatcher()
    
    # Load bus routes from your JSON file
    matcher.load_bus_routes('./data/route_data.json')  # Your actual JSON file
    
    # Process and display the route information
    logger.info("Processing bus route directions...")
    matcher.calculate_road_segments()
    
    # Traffic events
    traffic_events = get_traffic_events(api_key)
    
    ## convert the events to dataframe
    traffic_df = convert_to_df(traffic_events)
    logger.info("Received {} filtered traffic events for analysis", len(traffic_df))
    
    # Find affected route directions with precise geometric intersection
    affected_routes = matcher.find_affected_routes(
        traffic_df,
        tolerance_meters=1.0,  # Very small tolerance for GPS accuracy
        geocode_api_key=geocode_api_key,
        country_code='AU'
    )
    logger.info("Found {} events with geometric intersections on route directions", len(affected_routes))
    
    # Summary statistics
    total_events = len(traffic_df)
    affected_events = len(affected_routes)
    total_directions = len(matcher.route_directions)
    
    logger.info("Analysis complete: {} routes loaded, {} directions, {} events analyzed, {} events affecting routes", 
                len(matcher.bus_routes), total_directions, total_events, affected_events)
    
    return affected_routes

if __name__ == "__main__":
    main()