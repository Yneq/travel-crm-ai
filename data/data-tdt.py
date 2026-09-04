import json
import os
import re

import mysql.connector

with open('data/taipei-attractions.json', 'r', encoding='utf-8') as att:
    data = json.load(att)

db = mysql.connector.connect(
    user=os.getenv('DB_USER', 'root'),
    host=os.getenv('RDS_HOST', 'localhost'),
    password=os.getenv('RDS_PASSWORD'),
    database=os.getenv('DB_NAME', 'tdt')
)
cursor = db.cursor()

def filter_img(img_urls):
    urls = re.findall(r'https?://[^\s]+?\.(?:jpg|png|JPG|PNG)', img_urls)

    filtered_urls = []
    for url in urls:
        filtered_urls.append(url)
    return filtered_urls

for item in data['result']['results']:
    name = item['name']
    category = item['CAT']
    description = item['description']
    address = item['address']
    transport = item['direction']
    mrt = item['MRT']
    lat = item['latitude']
    lng = item['longitude']
    images = json.dumps(filter_img(item['file']))

    print(f"Processing item: {name}")
    print(f"Images before filtering: {item['file']}")
    print(f"Filtered images: {images}")

    cursor.execute("INSERT INTO attractions(name, category, description, address, transport, mrt, lat, lng, images) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)", (name, category, description, address, transport, mrt, lat, lng, images))

db.commit()
cursor.close()
db.close()

