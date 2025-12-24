from django.http import JsonResponse, HttpResponse
from django.views import View
from django.core.cache import cache
from django.db import models
from .models import FuelStation
import requests
import math
import json

class IgnoreUnknownView(View):
    def get(self, request, *args, **kwargs):
        return HttpResponse(status=204)  
    
    def post(self, request, *args, **kwargs):
        return HttpResponse(status=204)

class OptimalRouteView(View):
    
    VEHICLE_RANGE = 500  # miles
    MPG = 10  # miles per gallon
    TANK_CAPACITY = VEHICLE_RANGE / MPG  # 50 gallons
    
    def get(self, request):
        start = request.GET.get('start')
        finish = request.GET.get('finish')
        
        if not start or not finish:
            return JsonResponse({
                'error': 'Please provide both start and finish locations'
            }, status=400)
        
        try:
            # Get coordinates for start and finish
            start_coords = self.geocode(start)
            finish_coords = self.geocode(finish)
            
            if not start_coords or not finish_coords:
                return JsonResponse({
                    'error': 'Could not geocode one or both locations'
                }, status=400)
            
            # Get route from OSRM
            route_data = self.get_route(start_coords, finish_coords)
            
            if not route_data:
                return JsonResponse({
                    'error': 'Could not find route between locations'
                }, status=400)
            
            # Get all stations once for reuse
            all_stations = list(FuelStation.objects.filter(
                latitude__isnull=False,
                longitude__isnull=False
            ).values('id', 'name', 'address', 'city', 'state', 'retail_price', 'latitude', 'longitude'))
            
            # Find optimal fuel stops
            fuel_stops = self.find_optimal_fuel_stops(
                route_data['coordinates'],
                route_data['distance'],
                all_stations
            )
            
            total_distance = route_data['distance']
            total_gallons = total_distance / self.MPG
            
            if fuel_stops:
                # Cost of all refills made during trip
                refill_cost = sum(stop['cost'] for stop in fuel_stops)
                
                # Add cost of initial tank (assume filled at start location)
                start_point = route_data['coordinates'][0]
                nearby_start_stations = self.find_nearby_stations(
                    start_point, 
                    all_stations,
                    search_radius=50
                )
                
                if not nearby_start_stations:
                    # Expand search if no stations found
                    nearby_start_stations = self.find_nearby_stations(
                        start_point,
                        all_stations,
                        search_radius=100
                    )
                
                if nearby_start_stations:
                    cheapest_start = min(nearby_start_stations, key=lambda x: x['retail_price'])
                    initial_fill_cost = self.TANK_CAPACITY * float(cheapest_start['retail_price'])
                    initial_station_info = {
                        'stop_number': 0,
                        'station_name': cheapest_start['name'],
                        'address': cheapest_start['address'],
                        'city': cheapest_start['city'],
                        'state': cheapest_start['state'],
                        'price': float(cheapest_start['retail_price']),
                        'latitude': cheapest_start['latitude'],
                        'longitude': cheapest_start['longitude'],
                        'gallons_purchased': self.TANK_CAPACITY,
                        'cost': round(initial_fill_cost, 2),
                        'note': 'Initial fill-up before starting journey'
                    }
                    # Insert at beginning of fuel stops
                    fuel_stops.insert(0, initial_station_info)
                    # Renumber stops
                    for idx, stop in enumerate(fuel_stops[1:], start=1):
                        stop['stop_number'] = idx
                else:
                    # Use average if no nearby station
                    avg_price = FuelStation.objects.aggregate(
                        avg_price=models.Avg('retail_price')
                    )['avg_price'] or 3.50
                    initial_fill_cost = self.TANK_CAPACITY * float(avg_price)
                
                total_cost = refill_cost + initial_fill_cost
            else:
                # Trip under 500 miles - only need initial tank (or partial)
                # Find cheapest station near start
                start_point = route_data['coordinates'][0]
                nearby_start_stations = self.find_nearby_stations(
                    start_point,
                    all_stations,
                    search_radius=50
                )
                
                if not nearby_start_stations:
                    nearby_start_stations = self.find_nearby_stations(
                        start_point,
                        all_stations,
                        search_radius=100
                    )
                
                if nearby_start_stations:
                    cheapest_start = min(nearby_start_stations, key=lambda x: x['retail_price'])
                    total_cost = total_gallons * float(cheapest_start['retail_price'])
                else:
                    avg_price = FuelStation.objects.aggregate(
                        avg_price=models.Avg('retail_price')
                    )['avg_price'] or 3.50
                    total_cost = total_gallons * float(avg_price)
            
            response_data = {
                'route': {
                    'start': start,
                    'finish': finish,
                    'distance_miles': round(total_distance, 2),
                    'duration_hours': round(route_data['duration'] / 3600, 2),
                    'geometry': route_data['geometry']
                },
                'fuel_stops': fuel_stops,
                'summary': {
                    'total_distance_miles': round(total_distance, 2),
                    'total_gallons_needed': round(total_gallons, 2),
                    'total_fuel_cost': round(total_cost, 2),
                    'number_of_stops': len(fuel_stops),
                    'average_price_per_gallon': round(total_cost / total_gallons, 2) if total_gallons > 0 else 0
                }
            }
            
            # Add note for short trips
            if len(fuel_stops) == 0:
                response_data['summary']['note'] = 'No fuel stops needed - vehicle can reach destination on single tank'
            elif len(fuel_stops) == 1 and fuel_stops[0].get('note'):
                response_data['summary']['note'] = 'Only initial fill-up needed - no refueling stops required'
            
            return JsonResponse(response_data)
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return JsonResponse({
                'error': f'An error occurred: {str(e)}'
            }, status=500)
    
    def geocode(self, location):
        """Geocode location using Nominatim"""
        cache_key = f'geocode_{location}'
        cached = cache.get(cache_key)
        if cached:
            return cached
        
        try:
            url = "https://nominatim.openstreetmap.org/search"
            params = {
                'q': location + ', USA',
                'format': 'json',
                'limit': 1
            }
            headers = {'User-Agent': 'SpotterFuelApp/1.0'}
            
            response = requests.get(url, params=params, headers=headers, timeout=10)
            data = response.json()
            
            if data:
                coords = (float(data[0]['lon']), float(data[0]['lat']))
                cache.set(cache_key, coords, 86400)  # Cache for 24 hours
                return coords
        except:
            pass
        
        return None
    
    def get_route(self, start_coords, finish_coords):
        """Get route from OSRM"""
        cache_key = f'route_{start_coords}_{finish_coords}'
        cached = cache.get(cache_key)
        if cached:
            return cached
        
        try:
            # Using OSRM (completely free, no API key needed)
            url = f"http://router.project-osrm.org/route/v1/driving/{start_coords[0]},{start_coords[1]};{finish_coords[0]},{finish_coords[1]}"
            params = {
                'overview': 'full',
                'geometries': 'geojson',
                'steps': 'true'
            }
            
            response = requests.get(url, params=params, timeout=30)
            data = response.json()
            
            if data.get('code') == 'Ok' and data.get('routes'):
                route = data['routes'][0]
                
                # Convert meters to miles
                distance_miles = route['distance'] * 0.000621371
                
                route_data = {
                    'distance': distance_miles,
                    'duration': route['duration'],
                    'geometry': route['geometry'],
                    'coordinates': route['geometry']['coordinates']
                }
                
                cache.set(cache_key, route_data, 3600)  # Cache for 1 hour
                return route_data
        except Exception as e:
            print(f"Route error: {e}")
        
        return None
    
    def find_optimal_fuel_stops(self, route_coords, total_distance, stations):
        """Find optimal fuel stops along the route"""
        
        fuel_stops = []
        
        # Calculate number of stops needed (excluding initial fill)
        num_stops_needed = math.ceil(total_distance / self.VEHICLE_RANGE) - 1
        
        if num_stops_needed <= 0:
            return []  # No stops needed
        
        # For each fuel stop needed
        for i in range(1, num_stops_needed + 1):
            # Target distance for this stop
            target_distance = (i * total_distance) / (num_stops_needed + 1)
            
            # Find point on route near target distance
            target_point = self.get_point_at_distance(route_coords, target_distance, total_distance)
            
            if not target_point:
                continue
            
            # Find nearby stations within search radius
            nearby_stations = self.find_nearby_stations(
                target_point,
                stations,
                search_radius=50  # miles
            )
            
            if not nearby_stations:
                # Expand search if no stations found
                nearby_stations = self.find_nearby_stations(
                    target_point,
                    stations,
                    search_radius=100
                )
            
            if nearby_stations:
                # Sort by price and pick cheapest
                cheapest = min(nearby_stations, key=lambda x: x['retail_price'])
                
                # Calculate gallons needed
                gallons_to_purchase = self.TANK_CAPACITY
                
                fuel_stops.append({
                    'stop_number': len(fuel_stops) + 1,
                    'station_name': cheapest['name'],
                    'address': cheapest['address'],
                    'city': cheapest['city'],
                    'state': cheapest['state'],
                    'price': float(cheapest['retail_price']),
                    'latitude': cheapest['latitude'],
                    'longitude': cheapest['longitude'],
                    'gallons_purchased': gallons_to_purchase,
                    'cost': round(gallons_to_purchase * float(cheapest['retail_price']), 2)
                })
        
        return fuel_stops
    
    def get_point_at_distance(self, coords, target_distance, total_distance):
        """Get coordinates at a specific distance along the route"""
        # Simple approximation: find point at proportional position
        target_ratio = target_distance / total_distance
        target_idx = int(len(coords) * target_ratio)
        
        if target_idx < len(coords):
            return coords[target_idx]
        return None
    
    def find_nearby_stations(self, point, stations, search_radius=50):
        """Find stations within radius of a point"""
        nearby = []
        
        for station in stations:
            distance = self.haversine_distance(
                point[1], point[0],
                station['latitude'], station['longitude']
            )
            
            if distance <= search_radius:
                station['distance_from_route'] = distance
                nearby.append(station)
        
        return nearby
    
    def haversine_distance(self, lat1, lon1, lat2, lon2):
        """Calculate distance between two points in miles"""
        R = 3959  # Earth's radius in miles
        
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        
        return R * c
