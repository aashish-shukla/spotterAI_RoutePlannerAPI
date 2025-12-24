import csv
from django.core.management.base import BaseCommand
from route_planner.models import FuelStation
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
import time

class Command(BaseCommand):
    help = 'Load fuel station data from CSV'

    def handle(self, *args, **kwargs):
        self.stdout.write('Loading fuel data...')
        
        # Clear existing data
        FuelStation.objects.all().delete()
        
        geolocator = Nominatim(user_agent="spotter_fuel_app")
        
        with open('fuel_data.csv', 'r') as file:
            reader = csv.DictReader(file)
            stations = []
            processed_cities = {}  # Cache city coordinates
            
            for row in reader:
                city_key = f"{row['City'].strip()}, {row['State']}"
                
                # Get coordinates
                lat, lon = processed_cities.get(city_key, (None, None))
                
                if lat is None:
                    location_str = f"{row['City']}, {row['State']}, USA"
                    try:
                        location = geolocator.geocode(location_str)
                        if location:
                            lat, lon = location.latitude, location.longitude
                            processed_cities[city_key] = (lat, lon)
                        time.sleep(1)  # Rate limiting for Nominatim
                    except (GeocoderTimedOut, GeocoderServiceError):
                        pass
                
                station = FuelStation(
                    opis_id=int(row['OPIS Truckstop ID']),
                    name=row['Truckstop Name'],
                    address=row['Address'],
                    city=row['City'].strip(),
                    state=row['State'],
                    rack_id=int(row['Rack ID']),
                    retail_price=float(row['Retail Price']),
                    latitude=lat,
                    longitude=lon
                )
                stations.append(station)
                
                if len(stations) >= 100:
                    FuelStation.objects.bulk_create(stations)
                    self.stdout.write(f'Loaded {FuelStation.objects.count()} stations...')
                    stations = []
            
            if stations:
                FuelStation.objects.bulk_create(stations)
        
        self.stdout.write(self.style.SUCCESS(f'Successfully loaded {FuelStation.objects.count()} fuel stations'))