import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
CHROMEDRIVER_PATH = r"D:\chromedriver\chromedriver-win64\chromedriver-win64\chromedriver.exe"
driver_options = webdriver.ChromeOptions()
driver_options.add_argument("--window-size=1920,1080")
driver = webdriver.Chrome(service=Service(CHROMEDRIVER_PATH), options=driver_options)
driver.set_window_size(1920, 1080)
driver.get("http://mrbs-new.local:8095/admin.php")
time.sleep(1)
driver.find_element(By.XPATH, '//*[@id="username"]').clear()
driver.find_element(By.XPATH, '//*[@id="username"]').send_keys("admin")
time.sleep(1)
driver.find_element(By.XPATH, '//*[@id="password"]').clear()
driver.find_element(By.XPATH, '//*[@id="password"]').send_keys("admin")
time.sleep(1)
driver.find_element(By.XPATH, '//*[@id="logon"]/fieldset[2]/div/input').click()
time.sleep(1)
driver.find_element(By.XPATH, '/html/body/header/nav/nav[1]/nav[1]/a[4]').click()
time.sleep(1)
driver.find_element(By.XPATH, '//*[@id="rooms_table_filter"]/label/input').clear()
driver.find_element(By.XPATH, '//*[@id="rooms_table_filter"]/label/input').send_keys("test room")
time.sleep(1)
driver.find_element(By.XPATH, '//*[@id="rooms_table_filter"]/label/input').clear()
driver.find_element(By.XPATH, '//*[@id="rooms_table_filter"]/label/input').send_keys(Keys.ENTER)
time.sleep(1)
driver.close()
time.sleep(1)
driver.quit()
time.sleep(1)
