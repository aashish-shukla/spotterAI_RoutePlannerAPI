# Spotter Fuel Route Planner API

Django REST API that finds optimal fuel stops along a route based on fuel prices.

## Features
- Takes start and finish locations in the USA
- Returns route map with geometry
- Finds cost-effective fuel stops along the route
- Accounts for 500-mile vehicle range (10 MPG)
- Calculates total fuel costs
- Fast response with caching

## Setup Instructions

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run Migrations
```bash
python manage.py makemigrations
python manage.py migrate
```

### 3. Load Fuel Data
```bash
python manage.py load_fuel_data
```
Note: This will take some time as it geocodes cities. The CSV has 8000+ entries.

### 4. Run Server
```bash
python manage.py runserver
```

## API Usage

### Endpoint
```
GET /api/optimal-route/
```

### Parameters
- `start` (required): Starting location (e.g., "Los Angeles, CA")
- `finish` (required): Destination location (e.g., "New York, NY")

### Example Request
```
GET http://localhost:8000/api/optimal-route/?start=Los Angeles, CA&finish=New York, NY
```

### Example Response
```json
{
  "route": {
    "start": "Los Angeles, CA",
    "finish": "New York, NY",
    "distance_miles": 2789.45,
    "duration_hours": 40.5,
    "geometry": {
      "type": "LineString",
      "coordinates": [[...], [...]]
    }
  },
  "fuel_stops": [
    {
      "stop_number": 1,
      "station_name": "PILOT TRAVEL CENTER #92",
      "address": "I-40, EXIT 280",
      "city": "Albuquerque",
      "state": "NM",
      "price": 3.359,
      "latitude": 35.0844,
      "longitude": -106.6504,
      "gallons_purchased": 50.0,
      "cost": 167.95
    },
    ...
  ],
  "summary": {
    "total_distance_miles": 2789.45,
    "total_gallons_needed": 278.95,
    "total_fuel_cost": 936.50,
    "number_of_stops": 5,
    "average_price_per_gallon": 3.36
  }
}
```

## Technical Details

- **Routing API**: Uses OSRM (free, no API key required)
- **Geocoding**: Uses Nominatim OpenStreetMap
- **Caching**: Routes and geocoding results are cached to improve performance
- **Database**: SQLite with indexed queries
- **Algorithm**: Finds cheapest stations within 50-100 mile radius of optimal refuel points

## Performance
- First request: ~2-3 seconds (routing + station search)
- Cached requests: <500ms
- Only makes 1-2 external API calls per unique route

## Testing with Postman

1. Open Postman
2. Create GET request to: `http://localhost:8000/api/optimal-route/`
3. Add query parameters:
   - `start`: `Dallas, TX`
   - `finish`: `Chicago, IL`
4. Send request
5. View route geometry on map using the returned coordinates