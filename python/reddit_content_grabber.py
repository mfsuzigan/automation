import argparse
import time
from urllib.parse import urlparse
from argparse import Namespace
from selenium.webdriver import Chrome
import hashlib
import os

import requests
import logging

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common import TimeoutException
from selenium.webdriver import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec

REDDIT_LOGIN_URL = "https://www.reddit.com/login"
REDDIT_PROFILE_URL = "https://www.reddit.com/user"
IMAGE_OUTPUT_DIR = None
VIDEO_OUTPUT_DIR = None
WEBDRIVER_RENDER_TIMEOUT_SECONDS = 5
args: Namespace
driver: Chrome
hashes = []
redgif_links = set()


def get_args():
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("--username", "-u", required=True, help="User's username")
    arg_parser.add_argument("--password", "-p", required=True, help="User's password")
    arg_parser.add_argument("--target", "-t", required=True, help="Target profile")
    arg_parser.add_argument("--output", "-o", required=True, help="Output directory")
    arg_parser.add_argument("--headless", "-hl", action="store_true", help="Headless run")

    return arg_parser.parse_args()


def wait_until_visible(locator):
    wait = WebDriverWait(driver, WEBDRIVER_RENDER_TIMEOUT_SECONDS)
    try:
        wait.until(ec.visibility_of_element_located(locator))
    except TimeoutException:
        pass


def login():
    driver.get(REDDIT_LOGIN_URL)
    driver.find_element(By.ID, "loginUsername").send_keys(args.username)
    driver.find_element(By.ID, "loginPassword").send_keys(args.password)
    driver.find_element(By.TAG_NAME, "button").click()
    wait_until_visible((By.ID, "USER_DROPDOWN_ID"))


def file_is_image(name):
    return name.endswith(('.png', '.jpg', '.jpeg', '.tiff', '.bmp', '.gif'))


def get_grid_size():
    grid = driver.find_elements(By.XPATH,
                                "//*[@id='AppRouter-main-content']/div/div/div[2]/div[3]/div[1]/div[3]/div")
    return len(grid)


def page_scroll_up():
    page_body = driver.find_element(By.TAG_NAME, "body")
    page_body.send_keys(Keys.HOME)
    logging.info("Page scrolled up")


def full_page_scroll_down():
    grid_size = get_grid_size()
    page_body = driver.find_element(By.TAG_NAME, "body")
    page_body.send_keys(Keys.END)
    wait_until_visible((By.XPATH,
                        f"//*[@id='AppRouter-main-content']/div/div/div[2]/div[3]/div[1]/div[3]/"
                        f"div[{grid_size + 1}]"))

    counter = 1

    while get_grid_size() != grid_size:
        logging.info(f"Page scrolled ({counter})")
        counter += 1
        grid_size = get_grid_size()
        page_body.send_keys(Keys.END)
        wait_until_visible((By.XPATH,
                            f"//*[@id='AppRouter-main-content']/div/div/div[2]/div[3]/div[1]/div[3]/"
                            f"div[{grid_size + 1}]"))

    logging.info("Page finished scrolling")


def get_user_content():
    driver.get(f"{REDDIT_PROFILE_URL}/{args.target}/submitted")
    full_page_scroll_down()
    elements_grid = driver.find_elements(By.XPATH,
                                         "//*[@id='AppRouter-main-content']/div/div/div[2]/div[3]/div[1]/div[3]/div")

    logging.info(f"{len(elements_grid)} posts detected for target user {args.target}")

    create_output_directories()

    page_scroll_up()
    time.sleep(2)
    easy_images = download_simple_image_posts(elements_grid)

    page_scroll_up()
    download_complex_posts([e for e in elements_grid if e not in easy_images])

    download_redgifs()


def create_output_directories():
    global IMAGE_OUTPUT_DIR
    IMAGE_OUTPUT_DIR = f"{args.output}/{args.target}/img"
    os.makedirs(IMAGE_OUTPUT_DIR, exist_ok=True)

    global VIDEO_OUTPUT_DIR
    VIDEO_OUTPUT_DIR = f"{args.output}/{args.target}/video"
    os.makedirs(VIDEO_OUTPUT_DIR, exist_ok=True)


def download_redgifs():
    logging.info("Downloading Redgifs content 🔴")
    counter = 0

    for link in redgif_links:
        soup = BeautifulSoup(requests.get(link).content, "html.parser")
        redgif_src = soup.find("meta", {"property": "og:video"}).attrs["content"]
        title = soup.find("title").text

        if save_file(redgif_src, title, VIDEO_OUTPUT_DIR):
            counter += 1

    logging.info(f"{counter} Redgifs files saved")


def get_redgifs_link(post):
    redgif_link_probe = post.find_elements(By.CSS_SELECTOR, "a[href*=redgifs]")

    if len(redgif_link_probe) > 0:
        return redgif_link_probe[0].get_attribute("href")

    else:
        return None


def download_complex_posts(composite_posts):
    logging.info("Downloading content from complex posts 🧠")
    count = 0

    for post in composite_posts:
        redgif_link = get_redgifs_link(post)

        if redgif_link:
            redgif_links.add(redgif_link)

        else:
            expand_button_probe = post.find_elements(By.CSS_SELECTOR,
                                                     "div[data-click-id='body'] button[aria-label='Expand content']")

            if len(expand_button_probe) > 0:
                expand_button_probe[0].click()
                time.sleep(2)
                post_image_elements = post.find_elements(By.CSS_SELECTOR, "img[src]:not([alt='']):not([src=''])")

                count += [download_image_element(image_element=i) for i in post_image_elements].count(True)

    logging.info(f"{count} files saved")


def sanitize_string(str_input):
    return "".join(c for c in str_input if c.isalnum() or c in "._- ")


def is_duplicate(image_content):
    global hashes
    image_hash = hashlib.md5(image_content).hexdigest()
    is_duplicated = hashes.__contains__(image_hash)

    if not is_duplicated:
        hashes.append(image_hash)

    return is_duplicated


def download_image_element(image_element, file_content=None, image_src=None, image_title=None):
    if not image_title:
        image_title = sanitize_string(image_element.get_attribute("alt"))

    if not image_src:
        image_src = image_element.get_attribute("src")

    return save_file(content=file_content, link=image_src, title=image_title, path=IMAGE_OUTPUT_DIR)


def save_file(link, title, path, content=None):
    name_parts = urlparse(link).path.split(".")
    name_identifier = name_parts[0].split("/")[-1]
    extension = name_parts[-1]
    local_path = f"{path}/{args.target}__{name_identifier}__{title[:30]}.{extension}"

    if not content:
        content = requests.get(link).content

    if is_duplicate(content):
        logging.info(f"Skipping duplicate file {name_identifier}")

    else:
        with open(local_path, "wb") as image_file:
            image_file.write(content)
            logging.info(f"File {local_path.split('/')[-1]} downloaded")
            return True

    return False


def download_simple_image_posts(elements_grid):
    logging.info("Downloading images from simple posts 📸")
    easy_images = []

    for element in elements_grid:
        href = element.find_element(By.TAG_NAME, "a").get_attribute("href")

        if file_is_image(href.split("/")[-1]):
            # TODO: scroll if title is null
            image_title = element.find_element(By.TAG_NAME, "h3").text
            download_image_element(image_element=element.find_element(By.TAG_NAME, "img"), image_src=href,
                                   image_title=image_title)
            easy_images.append(element)

    logging.info(f"{len(easy_images)} files saved")

    return easy_images


def main():
    logging.getLogger().setLevel(logging.INFO)
    logging.info("Starting")

    global args
    args = get_args()

    webdriver_setup()

    logging.info("Logging in")
    login()
    logging.info("Logged in")

    get_user_content()

    logging.info("Done")


def webdriver_setup():
    options = webdriver.ChromeOptions()

    if args.headless:
        options.add_argument("--headless")

    global driver
    driver = webdriver.Chrome(options=options)


if __name__ == "__main__":
    main()
