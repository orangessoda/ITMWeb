import time
from pathlib import Path
import subprocess
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
CHROMEDRIVER_PATH = r"D:\chromedriver\chromedriver-win64\chromedriver-win64\chromedriver.exe"
RESET_SCRIPT = str(Path('C:/Users/DELL/Downloads/Graduation_project/ITMWeb/dockers') / "collabtive-dual-docker" / "reset_collabtive_non_user_data.py")
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
print("[collabtive-new] database reset succeeded")
driver_options = webdriver.ChromeOptions()
driver_options.add_argument("--window-size=1920,1080")
driver = webdriver.Chrome(service=Service(CHROMEDRIVER_PATH), options=driver_options)
driver.set_window_size(1920, 1080)
driver.get("http://collabtive-new.local:8085/")
time.sleep(1)
driver.find_element(By.XPATH, '//*[@id="username"]').clear()
driver.find_element(By.XPATH, '//*[@id="username"]').send_keys("admin")
time.sleep(1)
driver.find_element(By.XPATH, '//*[@id="pass"]').clear()
driver.find_element(By.XPATH, '//*[@id="pass"]').send_keys("admin")
time.sleep(1)
driver.find_element(By.XPATH, '//*[@id="loginform"]/fieldset/div[3]').click()
time.sleep(1)
driver.find_element(By.XPATH, '//*[@id="loginform"]/fieldset/div[4]/button').click()
time.sleep(1)
driver.close()
time.sleep(1)
driver.quit()
time.sleep(1)
