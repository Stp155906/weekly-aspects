from skyfield.api import load, Topos
from datetime import datetime, timedelta
import json

def fetch_weekly_aspects():
    # Load planetary data
    planets = load('de421.bsp')
    earth = planets['earth']

    # Define planets
    planet_names = {
        'mercury': '1 MERCURY',
        'venus': '2 VENUS',
        'mars': '4 MARS',
        'jupiter': '5 JUPITER BARYCENTER',
        'saturn': '6 SATURN BARYCENTER',
        'uranus': '7 URANUS BARYCENTER',
        'neptune': '8 NEPTUNE BARYCENTER'
    }
    planetary_objects = {name: planets[planet_names[name]] for name in planet_names}

    # Define observer location (e.g., at the center of the Earth)
    observer = earth + Topos('0 N', '0 E')

    # Calculate the current date and the next 6 days
    start_date = datetime.utcnow()
    dates = [start_date + timedelta(days=i) for i in range(7)]

    # Aspect definitions
    aspects = [
        ('conjunction', 0, 8),
        ('opposition', 180, 8),
        ('trine', 120, 8),
        ('square', 90, 8),
        ('sextile', 60, 6),
        ('inconjunct', 150, 4),
        ('quintile', 72, 2),
        ('semi-sextile', 30, 2),
        ('semi-square', 45, 2),
        ('sesquiquadrate', 135, 2)
    ]

    def calculate_angle(pos1, pos2):
        return (pos2 - pos1).degrees % 360

    def check_aspect(angle, target_angle, tolerance):
        return abs(angle - target_angle) <= tolerance or abs(angle - target_angle + 360) <= tolerance

    weekly_aspects = []

    for date in dates:
        ts = load.timescale()
        t = ts.utc(date.year, date.month, date.day)
        aspects_for_date = []

        for name1, planet1 in planetary_objects.items():
            for name2, planet2 in planetary_objects.items():
                if name1 >= name2:  # Avoid duplicate pairs and self-comparison
                    continue
                angle = calculate_angle(observer.at(t).observe(planet1).ecliptic_position().longitude,
                                        observer.at(t).observe(planet2).ecliptic_position().longitude)
                for aspect_name, aspect_angle, tolerance in aspects:
                    if check_aspect(angle, aspect_angle, tolerance):
                        aspects_for_date.append({
                            'planet1': name1,
                            'planet2': name2,
                            'aspect': aspect_name,
                            'angle': angle
                        })

        weekly_aspects.append({
            'date': date.strftime('%Y-%m-%d'),
            'aspects': aspects_for_date
        })

    return weekly_aspects

def save_to_json(data, filename="weekview.json"):
    with open(filename, 'w') as f:
        json.dump(data, f, indent=4)

# Fetch data
aspects = fetch_weekly_aspects()

# Save the data to a JSON file
save_to_json({"weekly_aspects": aspects})

# Print the fetched data for verification
print(json.dumps({"weekly_aspects": aspects}, indent=4))
