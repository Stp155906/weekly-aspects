from skyfield.api import load, Topos
from datetime import datetime, timedelta
import json

# Load planetary data
planets = load('de421.bsp')

# Define planets with their correct names from the kernel
planet_names = {
    'mercury': 'mercury',
    'venus': 'venus',
    'mars': 'mars',
    'jupiter': 'jupiter barycenter',
    'saturn': 'saturn barycenter',
    'uranus': 'uranus barycenter',
    'neptune': 'neptune barycenter'
}
planetary_objects = {name: planets[planet_names[name]] for name in planet_names}

# Define observer location (e.g., at the center of the Earth)
earth = planets['earth']
observer = earth + Topos(latitude_degrees=0, longitude_degrees=0)

# Function to calculate aspects
def calculate_aspects(date):
    ts = load.timescale()
    t = ts.utc(date.year, date.month, date.day)
    positions = {name: observer.at(t).observe(planet).apparent().ecliptic_latlon()[1].degrees for name, planet in planetary_objects.items()}
    
    aspects = []
    aspect_angles = {
        "conjunction": 0,
        "opposition": 180,
        "trine": 120,
        "square": 90,
        "sextile": 60,
        "quincunx": 150,
        "quintile": 72,
        "semi-sextile": 30,
        "semi-square": 45,
        "sesquiquadrate": 135
    }
    aspect_tolerance = 8  # Degrees of tolerance for aspects
    
    for planet1, lon1 in positions.items():
        for planet2, lon2 in positions.items():
            if planet1 != planet2:
                angle = abs(lon1 - lon2)
                for aspect, aspect_angle in aspect_angles.items():
                    if abs(angle - aspect_angle) <= aspect_tolerance or abs((angle + 360) - aspect_angle) <= aspect_tolerance:
                        aspects.append({
                            "planet1": planet1,
                            "planet2": planet2,
                            "aspect": aspect,
                            "angle": angle
                        })
    return aspects

# Function to fetch aspects for the current week
def fetch_weekly_aspects(start_date, days=7):
    weekly_aspects = []
    for i in range(days):
        date = start_date + timedelta(days=i)
        aspects = calculate_aspects(date)
        weekly_aspects.append({
            "date": date.strftime('%Y-%m-%d'),
            "aspects": aspects
        })
    return weekly_aspects

# Fetch data starting from today
start_date = datetime.now()
weekly_aspects = fetch_weekly_aspects(start_date)

# Save the data to a JSON file
def save_to_json(data, filename="weekly_aspects.json"):
    with open(filename, 'w') as f:
        json.dump(data, f, indent=4)

save_to_json({"weekly_aspects": weekly_aspects})

# Print the fetched data for verification
print(json.dumps({"weekly_aspects": weekly_aspects}, indent=4))
