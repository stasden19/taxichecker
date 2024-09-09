import json
import psycopg2
import requests
import urllib
from headers_taxi import header_1, header_2, header_3
from bs4 import BeautifulSoup
import base64
import io
import cv2
import numpy as np
import easyocr
import warnings
import sys
import time
from flask import Flask, request, jsonify, Response

warnings.filterwarnings('ignore')


def main(plate):
    plate_url = urllib.parse.quote_plus(plate.lower())
    url_1 = f'https://sicmt.ru/fgis-taksi?type=car&filters%5BregNumTS%5D={plate_url}&filters%5BlicenseNumber%5D='
    response = requests.get(url_1, headers=header_1, verify=False)
    soup = BeautifulSoup(response.text, 'html.parser')
    cookie = response.headers['set-cookie'].split(';')[0]
    cookie_text = cookie.split('=')
    cid = soup.find_all('input', id='cid')[0]['value']
    photo = soup.find('div', class_='captcha-img').img['src'].split()[1]
    image_stream = io.BytesIO(base64.decodebytes(bytes(photo, "utf-8")))
    file_bytes = np.asarray(bytearray(image_stream.read()), dtype=np.uint8)
    img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
    min_p = (0, 170, 0)
    max_p = (255, 255, 255)
    img_g = cv2.inRange(img, min_p, max_p)
    reader = easyocr.Reader(['ru'], gpu=True, verbose=False)
    result = reader.readtext(img_g, detail=0, blocklist='\n', paragraph=True,
                             allowlist='йцукенгшщзхъфывапролджэячсмитьбю1234567890')
    captha = ''.join(result).lower().replace(' ', '')
    cookie = {
        cookie_text[0]: cookie_text[1]
    }
    data_2 = {
        'action': 'check_captcha',
        'id': f'{cid}',
        'val': f'{captha}',
        'let': '7'
    }
    response_2 = requests.post('https://sicmt.ru/wp-content/ajax.php', data=data_2, headers=header_2, verify=False,
                               cookies=cookie)
    if response_2.text == '"false"':
        table = main(plate)
        # print('Error captcha')
        return table
    cookie_3 = cookie
    url_3 = (f'https://sicmt.ru//fgis-taksi?type=car&filters%5BregNumTS%5D={plate_url}&filters%5BlicenseNumber%5D'
             f'=&captcha={urllib.parse.quote_plus(captha)}&cid={cid}')
    response_3 = requests.get(url_3, headers=header_3, cookies=cookie_3, verify=False)
    response_3_soup = BeautifulSoup(response_3.text, 'html.parser')
    try:
        table = response_3_soup.find_all('div', class_='sic-fgis_resultTable')[0].find_all('table')[0]
        return table
    except:
        print('Нет информации')
        return 'Нет информации'


app = Flask(__name__)


@app.route('/', methods=['POST'])
def handle_json_array():

    if request.is_json:
        conn = psycopg2.connect(host='localhost', dbname='nomerogram', port=5432, user='postgres')
        cur = conn.cursor()
        json_array: list = request.get_json()
        if isinstance(json_array, str):
            json_array = [json_array]
        for plate in json_array:
            print(plate.rstrip('\n'))
            table1 = main(plate.lower().rstrip('\n'))
            try:
                soup1 = BeautifulSoup(str(table1))
                rows = soup1.find_all('tr')
                # Итерируемся по строкам, начиная со второй (первая - заголовок)
                for row in rows[1:]:
                    # Находим все ячейки в строке
                    cells = row.find_all('td')

                    # Извлекаем данные из ячеек
                    region = cells[0].find('a').text.strip()
                    record_number = cells[1].find('a').text.strip()
                    record_date = cells[2].find('a').text.strip()
                    vehicle_number = cells[3].find('a').text.strip()
                    vehicle_brand = cells[4].find('a').text.strip()
                    vehicle_model = cells[5].find('a').text.strip()
                    status = cells[6].text.strip()

                    # Выводим данные
                    plate_json = {
                        "Region": region,
                        "Record_number": record_number,
                        "Record_date": record_date,
                        "Vehicle_number": vehicle_number,
                        "Vehicle_brand": vehicle_brand,
                        "Vehicle_model": vehicle_model,
                        "Status": status
                    }
                    # cur.execute("""
                    #             CREATE TABLE IF NOT EXISTS vehicle_records (
                    #                 Record_date DATE,
                    #                 Record_number VARCHAR(50),
                    #                 Region VARCHAR(255),
                    #                 Status VARCHAR(255),
                    #                 Vehicle_brand VARCHAR(255),
                    #                 Vehicle_model VARCHAR(255),
                    #                 Vehicle_number VARCHAR(50)
                    #             );
                    #         """)

                    # Преобразование даты в формат YYYY-MM-DD
                    plate_json['Record_date'] = plate_json['Record_date'].replace('.', '-')

                    # Вставка данных в таблицу
                    cur.execute("""
                                SELECT 1
                                FROM vehicle_records
                                WHERE Record_date = %(Record_date)s
                                AND Record_number = %(Record_number)s
                                AND Region = %(Region)s
                                AND Status = %(Status)s
                                AND Vehicle_brand = %(Vehicle_brand)s
                                AND Vehicle_model = %(Vehicle_model)s
                                AND Vehicle_number = %(Vehicle_number)s;
                            """, plate_json)

                    if cur.fetchone() is None:
                        # Вставка данных в таблицу, если запись не существует
                        cur.execute("""
                                    INSERT INTO vehicle_records (Record_date, Record_number, Region, Status, Vehicle_brand, Vehicle_model, Vehicle_number)
                                    VALUES (%(Record_date)s, %(Record_number)s, %(Region)s, %(Status)s, %(Vehicle_brand)s, %(Vehicle_model)s, %(Vehicle_number)s);
                                """, plate_json)
                    return jsonify(plate_json)
            except Exception as e:
                print(e)
        return "0", 200


if __name__ == '__main__':
    app.run(debug=False, port=5002)
