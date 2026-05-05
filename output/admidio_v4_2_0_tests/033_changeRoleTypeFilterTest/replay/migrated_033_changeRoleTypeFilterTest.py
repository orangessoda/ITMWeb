import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import Select
CHROMEDRIVER_PATH = r"D:\chromedriver\chromedriver-win64\chromedriver-win64\chromedriver.exe"
driver_options = webdriver.ChromeOptions()
driver_options.add_argument("--window-size=1920,1080")
driver = webdriver.Chrome(service=Service(CHROMEDRIVER_PATH), options=driver_options)
driver.set_window_size(1920, 1080)
driver.get("http://admidio-new.local:8083/modules/overview.php")
time.sleep(1)
driver.find_element(By.XPATH, '//*[@id="plg_usr_login_name"]').clear()
driver.find_element(By.XPATH, '//*[@id="plg_usr_login_name"]').send_keys("admin")
time.sleep(1)
driver.find_element(By.XPATH, '//*[@id="plg_usr_password"]').clear()
driver.find_element(By.XPATH, '//*[@id="plg_usr_password"]').send_keys("admin")
time.sleep(1)
driver.find_element(By.ID, 'plg_btn_login').click()
time.sleep(1)
driver.find_element(By.XPATH, '//*[@id="groups-roles"]').click()
time.sleep(1)
driver.find_element(By.XPATH, '//*[@id="role_type"]').click()
time.sleep(1)
driver.find_element(By.XPATH, '//*[@id="role_type"]/option[2]').click()
time.sleep(1)
driver.find_element(By.XPATH, '//*[@id="role_type"]').click()
time.sleep(1)
driver.find_element(By.XPATH, '//*[@id="role_type"]/option[3]').click()
time.sleep(1)
driver.get('http://admidio-new.local:8083/modules/groups-roles/groups_roles.php?show=card&cat_uuid=0&role_type=0')
time.sleep(1)
driver.get('http://admidio-new.local:8083/modules/groups-roles/groups_roles.php?show=card&cat_uuid=0&role_type=2')
time.sleep(1)
driver.close()
time.sleep(1)
driver.quit()
time.sleep(1)

