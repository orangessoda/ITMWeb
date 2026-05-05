from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import time
from selenium.webdriver.chrome.service import Service
CHROMEDRIVER_PATH = r"D:\chromedriver\chromedriver-win64\chromedriver-win64\chromedriver.exe"
driver_options = webdriver.ChromeOptions()
driver_options.add_argument("--window-size=1920,1080")
driver = webdriver.Chrome(service=Service(CHROMEDRIVER_PATH), options=driver_options)
driver.set_window_size(1920, 1080)
js = driver
driver.execute_script("document.body.style.zoom='80%'")
driver.get("http://phpmyadmin-new.local:8093/")
time.sleep(1)
driver.find_element(By.ID, "input_username").clear()
driver.find_element(By.ID, "input_username").send_keys("admin")
time.sleep(1)
driver.find_element(By.ID, "input_password").clear()
driver.find_element(By.ID, "input_password").send_keys("admin")
time.sleep(1)
driver.find_element(By.ID, "input_go").click()
time.sleep(1)
driver.find_element(By.LINK_TEXT, "test").click()
time.sleep(1)
driver.get('http://phpmyadmin-old.local:8092/tbl_operations.php?server=1&db=test&table=newtestable')
time.sleep(1)
driver.execute_script('return;')
time.sleep(1)
driver.find_element(By.TAG_NAME, "html").send_keys(Keys.END)
time.sleep(1)
driver.find_element(By.ID, "drop_tbl_anchor").click()
time.sleep(1)
driver.find_element(By.CSS_SELECTOR, ".submitOK").click()
time.sleep(1)
assert not (("newtestable" in driver.find_element(By.XPATH, "html/body").text))
time.sleep(1)
driver.quit()
time.sleep(1)
