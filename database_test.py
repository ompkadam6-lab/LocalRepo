import mysql.connector import os

connection = mysql.connector.connect(
    host="mysql-2ff33ec-om2000kadam-dc6d.l.aivencloud.com",
    port=12747,
    user="avnadmin",
    "password": os.environ["AIVEN_DB_PASSWORD"],
    database="defaultdb",
    ssl_disabled=False
)

cursor = connection.cursor()

cursor.execute("SELECT * FROM site_connections")

rows = cursor.fetchall()

for row in rows:
    print(row)

cursor.close()
connection.close()