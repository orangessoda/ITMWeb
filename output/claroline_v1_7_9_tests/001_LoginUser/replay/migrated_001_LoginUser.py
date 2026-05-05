from selenium import webdriver
from selenium.webdriver.common.by import By
import time
from pathlib import Path
import subprocess
from selenium.webdriver.chrome.service import Service
CHROMEDRIVER_PATH = r"D:\chromedriver\chromedriver-win64\chromedriver-win64\chromedriver.exe"
RESET_SCRIPT = str(Path('C:/Users/DELL/Downloads/Graduation_project/ITMWeb/dockers') / "claroline-dual-docker" / "reset_claroline_non_user_data.py")
subprocess.run(
    [
        "python",
        RESET_SCRIPT,
        "--target",
        "new",
        "--execute",
    ],
    check=True,
)
print("[claroline-new] database reset succeeded")
driver_options = webdriver.ChromeOptions()
driver_options.add_argument("--window-size=1920,1080")
driver = webdriver.Chrome(service=Service(CHROMEDRIVER_PATH), options=driver_options)
driver.set_window_size(1920, 1080)
driver.get("http://claroline-new.local:8089/login")
time.sleep(1)
driver.find_element(By.ID, 'username').clear()
element = driver.find_element(By.ID, 'username')
element.clear() if (element.get_attribute('type') or '').lower() != 'file' else None
element.send_keys('admin')
time.sleep(1)
driver.find_element(By.ID, "password").clear()
driver.find_element(By.ID, "password").send_keys("admin")
time.sleep(1)
driver.find_element(By.CSS_SELECTOR, 'div > div > div > form > button').click()
time.sleep(1)
driver.quit()
time.sleep(1)
