from flask import Flask, jsonify, request
from flask_cors import CORS
import pandas as pd
import numpy as np
from datetime import datetime
import requests

app = Flask(__name__)
CORS(app)

# Load all safety data
crime_data = pd.read_csv('bangalore_crimes.csv')
lighting_data = pd.read_csv('bangalore_lighting.csv')
population_data = pd.read_csv('bangalore_population.csv')

def calculate_crime_density(lat, lon, radius=0.01):
    """Calculate crime density around a point"""
    nearby_crimes = crime_data[
        (abs(crime_data['Latitude'] - lat) < radius) &
        (abs(crime_data['Longitude'] - lon) < radius)
    ]
    return len(nearby_crimes)

def get_route_from_osrm(start_lat, start_lon, end_lat, end_lon):
    """Get route from OSRM (Open Source Routing Machine)"""
    url = f"http://router.project-osrm.org/route/v1/driving/{start_lon},{start_lat};{end_lon},{end_lat}?overview=full&geometries=geojson"
    
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if data['code'] == 'Ok':
            coordinates = data['routes'][0]['geometry']['coordinates']
            # Convert from [lon, lat] to [lat, lon]
            route = [[coord[1], coord[0]] for coord in coordinates]
            return route
        return None
    except Exception as e:
        print(f"Error getting route: {e}")
        return None

def calculate_lighting_score(lat, lon, radius=0.01):
    """Calculate average lighting score around a point (higher is better)"""
    nearby_lighting = lighting_data[
        (abs(lighting_data['Latitude'] - lat) < radius) &
        (abs(lighting_data['Longitude'] - lon) < radius)
    ]
    if len(nearby_lighting) > 0:
        return nearby_lighting['lighting_score'].mean()
    return 5.0  # Default medium lighting

def calculate_population_score(lat, lon, radius=0.01):
    """Calculate average population and traffic around a point (higher is better for safety)"""
    nearby_pop = population_data[
        (abs(population_data['Latitude'] - lat) < radius) &
        (abs(population_data['Longitude'] - lon) < radius)
    ]
    if len(nearby_pop) > 0:
        pop_score = nearby_pop['population_density'].mean() / 1000  # Normalize
        traffic_score = nearby_pop['traffic_level'].mean() / 10  # Normalize
        is_main_road = nearby_pop['is_main_road'].mean() > 0.5
        return pop_score, traffic_score, is_main_road
    return 5.0, 5.0, False

def calculate_route_safety_score(route, prefer_main_roads=False, prefer_well_lit=False, prefer_populated=False):
    """Calculate safety score for a route (lower is safer)"""
    if not route:
        return float('inf')
    
    total_danger = 0
    total_lighting = 0
    total_population = 0
    total_traffic = 0
    main_road_count = 0
    
    for lat, lon in route:
        # Crime density (bad - increases danger)
        danger = calculate_crime_density(lat, lon, radius=0.005)
        total_danger += danger
        
        # Lighting (good - decreases danger)
        lighting = calculate_lighting_score(lat, lon, radius=0.005)
        total_lighting += lighting
        
        # Population and traffic (good - decreases danger)
        pop_score, traffic_score, is_main = calculate_population_score(lat, lon, radius=0.005)
        total_population += pop_score
        total_traffic += traffic_score
        if is_main:
            main_road_count += 1
    
    # Normalize by route length
    avg_danger = total_danger / len(route)
    avg_lighting = total_lighting / len(route)
    avg_population = total_population / len(route)
    avg_traffic = total_traffic / len(route)
    main_road_ratio = main_road_count / len(route)
    
    # Calculate composite score (lower is better)
    base_score = avg_danger
    
    # Adjust based on preferences
    if prefer_main_roads:
        base_score -= main_road_ratio * 2  # Subtract points for main roads
    if prefer_well_lit:
        base_score -= (avg_lighting / 10) * 2  # Subtract points for good lighting
    if prefer_populated:
        base_score -= (avg_population / 20) * 2  # Subtract points for high population
        base_score -= (avg_traffic / 10) * 2  # Subtract points for high traffic
    
    # Ensure non-negative
    return max(0, base_score)

def generate_alternative_routes(start_lat, start_lon, end_lat, end_lon, num_routes=5, 
                                 prefer_main_roads=False, prefer_well_lit=False, prefer_populated=False):
    """Generate multiple alternative routes using waypoints"""
    routes = []
    
    # Direct route
    direct_route = get_route_from_osrm(start_lat, start_lon, end_lat, end_lon)
    if direct_route:
        safety_score = calculate_route_safety_score(direct_route, prefer_main_roads, prefer_well_lit, prefer_populated)
        routes.append({
            'route': direct_route,
            'safety_score': safety_score,
            'type': 'direct'
        })
    
    # Generate alternative routes with intermediate waypoints
    lat_diff = end_lat - start_lat
    lon_diff = end_lon - start_lon
    
    # Alternative 1: Slight northward detour
    mid_lat1 = start_lat + lat_diff * 0.5 + 0.01
    mid_lon1 = start_lon + lon_diff * 0.5
    
    route1_part1 = get_route_from_osrm(start_lat, start_lon, mid_lat1, mid_lon1)
    route1_part2 = get_route_from_osrm(mid_lat1, mid_lon1, end_lat, end_lon)
    
    if route1_part1 and route1_part2:
        alt_route1 = route1_part1 + route1_part2
        safety_score1 = calculate_route_safety_score(alt_route1, prefer_main_roads, prefer_well_lit, prefer_populated)
        routes.append({
            'route': alt_route1,
            'safety_score': safety_score1,
            'type': 'alternative_1'
        })
    
    # Alternative 2: Slight southward detour
    mid_lat2 = start_lat + lat_diff * 0.5 - 0.01
    mid_lon2 = start_lon + lon_diff * 0.5
    
    route2_part1 = get_route_from_osrm(start_lat, start_lon, mid_lat2, mid_lon2)
    route2_part2 = get_route_from_osrm(mid_lat2, mid_lon2, end_lat, end_lon)
    
    if route2_part1 and route2_part2:
        alt_route2 = route2_part1 + route2_part2
        safety_score2 = calculate_route_safety_score(alt_route2, prefer_main_roads, prefer_well_lit, prefer_populated)
        routes.append({
            'route': alt_route2,
            'safety_score': safety_score2,
            'type': 'alternative_2'
        })
    
    # Alternative 3: Eastward detour
    mid_lat3 = start_lat + lat_diff * 0.5
    mid_lon3 = start_lon + lon_diff * 0.5 + 0.01
    
    route3_part1 = get_route_from_osrm(start_lat, start_lon, mid_lat3, mid_lon3)
    route3_part2 = get_route_from_osrm(mid_lat3, mid_lon3, end_lat, end_lon)
    
    if route3_part1 and route3_part2:
        alt_route3 = route3_part1 + route3_part2
        safety_score3 = calculate_route_safety_score(alt_route3, prefer_main_roads, prefer_well_lit, prefer_populated)
        routes.append({
            'route': alt_route3,
            'safety_score': safety_score3,
            'type': 'alternative_3'
        })
    
    # Alternative 4: Westward detour
    mid_lat4 = start_lat + lat_diff * 0.5
    mid_lon4 = start_lon + lon_diff * 0.5 - 0.01
    
    route4_part1 = get_route_from_osrm(start_lat, start_lon, mid_lat4, mid_lon4)
    route4_part2 = get_route_from_osrm(mid_lat4, mid_lon4, end_lat, end_lon)
    
    if route4_part1 and route4_part2:
        alt_route4 = route4_part1 + route4_part2
        safety_score4 = calculate_route_safety_score(alt_route4, prefer_main_roads, prefer_well_lit, prefer_populated)
        routes.append({
            'route': alt_route4,
            'safety_score': safety_score4,
            'type': 'alternative_4'
        })
    
    # Sort by safety score
    routes.sort(key=lambda x: x['safety_score'])
    
    return routes[:num_routes]

@app.route('/api/crime-heatmap', methods=['GET'])
def get_crime_heatmap():
    """Return crime data for heatmap"""
    heatmap_data = crime_data[['Latitude', 'Longitude']].values.tolist()
    return jsonify({
        'success': True,
        'data': heatmap_data,
        'total_crimes': len(crime_data)
    })

@app.route('/api/lighting-heatmap', methods=['GET'])
def get_lighting_heatmap():
    """Return lighting data for heatmap"""
    # Include lighting score as weight for better visualization
    heatmap_data = lighting_data[['Latitude', 'Longitude', 'lighting_score']].values.tolist()
    return jsonify({
        'success': True,
        'data': heatmap_data,
        'total_locations': len(lighting_data)
    })

@app.route('/api/population-heatmap', methods=['GET'])
def get_population_heatmap():
    """Return population density data for heatmap"""
    # Include population density as weight for better visualization
    heatmap_data = population_data[['Latitude', 'Longitude', 'population_density']].values.tolist()
    return jsonify({
        'success': True,
        'data': heatmap_data,
        'total_locations': len(population_data)
    })

@app.route('/api/route', methods=['POST'])
def get_routes():
    """Generate multiple routes avoiding high-crime areas"""
    data = request.json
    start_lat = data.get('start_lat')
    start_lon = data.get('start_lon')
    end_lat = data.get('end_lat')
    end_lon = data.get('end_lon')
    
    # Get preferences
    prefer_main_roads = data.get('prefer_main_roads', False)
    prefer_well_lit = data.get('prefer_well_lit', False)
    prefer_populated = data.get('prefer_populated', False)
    
    if not all([start_lat, start_lon, end_lat, end_lon]):
        return jsonify({'success': False, 'error': 'Missing coordinates'}), 400
    
    # Generate alternative routes with preferences
    routes = generate_alternative_routes(start_lat, start_lon, end_lat, end_lon, 
                                         num_routes=5,
                                         prefer_main_roads=prefer_main_roads,
                                         prefer_well_lit=prefer_well_lit,
                                         prefer_populated=prefer_populated)
    
    if not routes:
        return jsonify({'success': False, 'error': 'Could not generate routes'}), 500
    
    return jsonify({
        'success': True,
        'routes': routes,
        'message': f'Generated {len(routes)} routes. Lower safety score is safer.'
    })

@app.route('/api/rate-route', methods=['POST'])
def rate_route():
    """Store route rating from user"""
    data = request.json
    route_id = data.get('route_id')  # Could be a hash of start/end/type
    rating = data.get('rating')  # 1-5 stars
    feedback = data.get('feedback', '')
    
    # In a real app, store this in a database
    # For now, we'll just acknowledge it
    print(f"Route {route_id} rated: {rating} stars - {feedback}")
    
    return jsonify({
        'success': True,
        'message': 'Thank you for your feedback! This helps us improve route recommendations.'
    })

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'success': True,
        'message': 'Backend is running',
        'crimes_loaded': len(crime_data)
    })

if __name__ == '__main__':
    print("Starting Bangalore Safe Route Backend...")
    print(f"Loaded {len(crime_data)} crime records")
    app.run(debug=True, host='0.0.0.0', port=5000)