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
time.sleep(1)
driver.find_element(By.XPATH, '//*[@id="plg_usr_login_name"]').clear()
driver.find_element(By.XPATH, '//*[@id="plg_usr_login_name"]').send_keys("admin")
time.sleep(1)
driver.find_element(By.XPATH, '//*[@id="plg_usr_password"]').clear()
driver.find_element(By.XPATH, '//*[@id="plg_usr_password"]').send_keys("admin")
time.sleep(1)
driver.find_element(By.ID, 'plg_btn_login').click()
time.sleep(1)
driver.find_element(By.XPATH, '//*[@id="messages"]').click()
time.sleep(1)
driver.find_element(By.CSS_SELECTOR, 'thead > tr > th > div > span').click()
time.sleep(1)
driver.find_element(By.CSS_SELECTOR, 'thead > tr > th > div > span').click()
time.sleep(1)
driver.find_element(By.CSS_SELECTOR, 'thead > tr > th > div > span').click()
time.sleep(1)
driver.find_element(By.CSS_SELECTOR, 'thead > tr > th > div > span').click()
time.sleep(1)
Select(driver.find_element(By.ID, 'dt-length-0')).select_by_visible_text('25')
time.sleep(1)
Select(driver.find_element(By.ID, 'dt-length-0')).select_by_visible_text('25')
time.sleep(1)
driver.find_element(By.ID, 'dt-search-0').clear()
element = driver.find_element(By.ID, 'dt-search-0')
element.clear() if (element.get_attribute('type') or '').lower() != 'file' else None
element.send_keys('test')
time.sleep(1)
driver.close()
time.sleep(1)
driver.quit()
time.sleep(1)


