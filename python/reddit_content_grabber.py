import argparse
import requests
import logging
from selenium import webdriver
from selenium.common import TimeoutException
from selenium.webdriver import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec

REDDIT_LOGIN_URL = "https://www.reddit.com/login"
REDDIT_PROFILE_URL = "https://www.reddit.com/user"
WEBDRIVER_RENDER_TIMEOUT_SECONDS = 5


def get_args():
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("--username", "-u", required=True, help="User's username")
    arg_parser.add_argument("--password", "-p", required=True, help="User's password")
    arg_parser.add_argument("--target", "-t", required=True, help="Target profile")

    return arg_parser.parse_args()


def wait_until_visible(driver, locator):
    wait = WebDriverWait(driver, WEBDRIVER_RENDER_TIMEOUT_SECONDS)
    try:
        wait.until(ec.visibility_of_element_located(locator))
    except TimeoutException:
        pass


def login(driver, args):
    driver.get(REDDIT_LOGIN_URL)
    driver.find_element(By.ID, "loginUsername").send_keys(args.username)
    driver.find_element(By.ID, "loginPassword").send_keys(args.password)
    driver.find_element(By.TAG_NAME, "button").click()
    wait_until_visible(driver, (By.ID, "USER_DROPDOWN_ID"))


def file_is_image(name):
    return name.endswith(('.png', '.jpg', '.jpeg', '.tiff', '.bmp', '.gif'))


def get_grid_size(driver):
    grid = driver.find_elements(By.XPATH,
                                "//*[@id='AppRouter-main-content']/div/div/div[2]/div[3]/div[1]/div[3]/div")
    return len(grid)


def full_page_scroll(driver):
    grid_size = get_grid_size(driver)
    page_body = driver.find_element(By.TAG_NAME, "body")
    page_body.send_keys(Keys.END)
    wait_until_visible(driver, (By.XPATH,
                                f"//*[@id='AppRouter-main-content']/div/div/div[2]/div[3]/div[1]/div[3]/div[{grid_size + 1}]"))

    while get_grid_size(driver) != grid_size:
        logging.info("Page scrolled")
        grid_size = get_grid_size(driver)
        page_body.send_keys(Keys.END)
        wait_until_visible(driver, (By.XPATH,
                                    f"//*[@id='AppRouter-main-content']/div/div/div[2]/div[3]/div[1]/div[3]/div[{grid_size + 1}]"))


logging.info("Page finished scrolling")


def download_content(driver, args):
    driver.get(f"{REDDIT_PROFILE_URL}/{args.target}/submitted")
    full_page_scroll(driver)
    elements_grid = driver.find_elements(By.XPATH,
                                         "//*[@id='AppRouter-main-content']/div/div/div[2]/div[3]/div[1]/div[3]/div")

    for element in elements_grid:
        image_link = element.find_element(By.TAG_NAME, "a")

        if image_link:
            image_url = image_link.get_attribute("href")
            file_name = image_url.split("/")[-1]

            if file_is_image(file_name):
                with open(file_name, "wb") as image_file:
                    image_file.write(requests.get(image_url).content)
                    logging.info(f"File {image_file} downloaded")


def main():
    args = get_args()
    driver = webdriver.Chrome()
    logging.getLogger().setLevel(logging.INFO)
    login(driver, args)
    download_content(driver, args)


if __name__ == "__main__":
    main()
