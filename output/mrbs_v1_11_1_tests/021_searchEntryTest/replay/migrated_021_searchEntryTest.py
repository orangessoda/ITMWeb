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
driver.find_element(By.XPATH, '//*[@id="form_nav"]/input[5]').click()
time.sleep(1)
driver.find_element(By.XPATH, '/html/body/div[2]/div[2]/div/div[2]/div/span[6]').click()
time.sleep(1)
driver.find_element(By.XPATH, '//*[@id="header_search"]/input[9]').clear()
driver.find_element(By.XPATH, '//*[@id="header_search"]/input[9]').send_keys("test")
time.sleep(1)
driver.find_element(By.XPATH, '//*[@id="header_search"]/input[9]').clear()
driver.find_element(By.XPATH, '//*[@id="header_search"]/input[9]').send_keys(Keys.ENTER)
time.sleep(1)
driver.close()
time.sleep(1)
driver.quit()
time.sleep(1)
