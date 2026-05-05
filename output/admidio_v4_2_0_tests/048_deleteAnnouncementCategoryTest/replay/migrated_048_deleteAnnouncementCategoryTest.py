import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
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
driver.find_element(By.XPATH, '//*[@id="announcements"]').click()
time.sleep(1)
driver.find_element(By.XPATH, '//*[@id="menu_item_announcement_categories"]').click()
time.sleep(1)
driver.find_element(By.XPATH, '/html/body/div[2]/div/div[2]/div/div[2]/table/tbody/tr[3]/td[6]/a[2]').click()
time.sleep(1)
driver.find_element(By.XPATH, '//*[@id="btn_yes"]').click()
time.sleep(1)
driver.close()
time.sleep(1)
driver.quit()
time.sleep(1)

