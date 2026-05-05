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
driver.find_element(By.XPATH, '//*[@id="documents-files"]').click()
time.sleep(1)
driver.find_element(By.LINK_TEXT, 'test').click()
time.sleep(1)
driver.find_element(By.XPATH, '//*[@id="menu_item_documents_permissions"]').click()
time.sleep(1)
Select(driver.find_element(By.ID, 'adm_roles_upload_right')).select_by_visible_text('General')
time.sleep(1)
element = driver.find_element(By.CSS_SELECTOR, 'span > span > span > span > textarea')
element.clear() if (element.get_attribute('type') or '').lower() != 'file' else None
element.send_keys('General\n')
element = driver.find_element(By.CSS_SELECTOR, 'span > span > span > span > textarea')
element.clear() if (element.get_attribute('type') or '').lower() != 'file' else None
element.send_keys('Teams\n')
element = driver.find_element(By.CSS_SELECTOR, 'span > span > span > span > textarea')
element.clear() if (element.get_attribute('type') or '').lower() != 'file' else None
element.send_keys('Courses\n')
driver.find_element(By.ID, 'adm_button_save').click()
time.sleep(1)
driver.find_element(By.XPATH, '//*[@id="adm_roles_upload_right_group"]/div/span/span[1]/span/ul/li/input').click()
time.sleep(1)
driver.find_element(By.XPATH, '/html/body/span/span/span/ul/li[2]/ul/li[1]').click()
time.sleep(1)
driver.find_element(By.XPATH, '//*[@id="adm_roles_upload_right_group"]/div/span/span[1]/span/ul/li/input').click()
time.sleep(1)
driver.find_element(By.XPATH, '/html/body/span/span/span/ul/li[3]/ul/li[1]').click()
time.sleep(1)
driver.find_element(By.XPATH, '//*[@id="btn_save"]').click()
time.sleep(1)
driver.close()
time.sleep(1)
driver.quit()
time.sleep(1)

