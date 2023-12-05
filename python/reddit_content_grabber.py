import argparse
import time
from urllib.parse import urlparse
from urllib.parse import parse_qs
from argparse import Namespace
from requests import RequestException
from selenium.webdriver import Chrome
import hashlib
import os

import requests
import logging

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common import TimeoutException, NoSuchElementException, ElementNotInteractableException, \
    ElementClickInterceptedException
from selenium.webdriver import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec

REDDIT_LOGIN_URL = "https://www.reddit.com/login"
REDDIT_PROFILE_URL = "https://www.reddit.com/user"
REDDIT_SUB_URL = "https://www.reddit.com/r"
IMAGE_OUTPUT_DIR = None
VIDEO_OUTPUT_DIR = None
WEBDRIVER_RENDER_TIMEOUT_SECONDS = 5
TIME_SLEEP_SECONDS = 5
args: Namespace
driver: Chrome
hashes = []
redgif_links = set()


def get_args():
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("--username", "-u", required=True, help="User's username")
    arg_parser.add_argument("--password", "-p", required=True, help="User's password")
    arg_parser.add_argument("--target", "-t", required=False, help="Target profile")
    arg_parser.add_argument("--sub", "-s", required=False, help="Target subreddit")
    arg_parser.add_argument("--output", "-o", required=True, help="Output directory")
    arg_parser.add_argument("--headless", "-hl", action="store_true", help="Headless run")
    arg_parser.add_argument("--only-videos", "-v", action="store_true", help="Download only videos")
    arg_parser.add_argument("--max-files", "-m", required=False, help="Maximum number of files to download")

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


def file_is_downloadable(name):
    name = name.split("?")[0]

    if args.only_videos:
        return name.endswith('.gif')

    else:
        return name.endswith(('.png', '.jpg', '.jpeg', '.tiff', '.bmp', '.gif'))


def file_is_type(name, extension):
    name = name.split("?")[0]
    return name.endswith(extension)


def file_is_image(extension):
    return extension.lower() in ['png', 'jpg', 'jpeg', 'tiff', 'bmp', 'gif']


def get_grid_size():
    grid = driver.find_elements(By.XPATH,
                                "//*[@id='AppRouter-main-content']/div/div/div[2]/div[3]/div[1]/div[3]/div")
    return len(grid)


def page_scroll(key):
    page_body = driver.find_element(By.TAG_NAME, "body")
    page_body.send_keys(key)
    direction = "down" if key == Keys.PAGE_DOWN else "up"
    logging.info(f"Page scrolled {direction}")


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
    create_output_directories()
    inspected_elements = []
    grid_elements_xpath = "//*[@id='AppRouter-main-content']/div/div/div[2]/div[3]/div[1]/div[3]/div"
    grid_elements = driver.find_elements(By.XPATH, grid_elements_xpath)

    while len(inspected_elements) != len(grid_elements):
        elements_to_inspect = [e for e in grid_elements if e not in inspected_elements]
        download_from_simple_posts(elements_to_inspect)
        inspected_elements.extend(elements_to_inspect)
        grid_elements = driver.find_elements(By.XPATH, grid_elements_xpath)


def create_output_directories():
    base_output_dir = args.target if args.target else args.sub
    base_output_dir = f"{args.output}/{base_output_dir}"

    global IMAGE_OUTPUT_DIR
    IMAGE_OUTPUT_DIR = f"{base_output_dir}/img"
    os.makedirs(IMAGE_OUTPUT_DIR, exist_ok=True)

    global VIDEO_OUTPUT_DIR
    VIDEO_OUTPUT_DIR = f"{base_output_dir}/video"
    os.makedirs(VIDEO_OUTPUT_DIR, exist_ok=True)


def safe_request_content(url):
    try:
        return requests.get(url).content

    except RequestException:
        logging.error(f"Error downloading {url}")
        return ""


def download_from_inspectable_file(link, title=None, user=None):
    soup = BeautifulSoup(safe_request_content(link), "html.parser")
    src = None

    for type_ in ["og:video", "og:image:url"]:
        if soup.find("meta", {"property": type_}):
            src = soup.find("meta", {"property": type_})

    if not src:
        return False

    if not title and soup.find("title"):
        title = soup.find("title").text

    else:
        title = "UNTITLED by UNKNOWN"

    if not user:
        user = title.split("by ")[1].split(" |")[0]

    return save_file(link=src.attrs["content"], title=title, user=user)


def download_redgifs():
    logging.info("Downloading Redgifs content 🔴")
    counter = 0

    for link in redgif_links:
        soup = BeautifulSoup(safe_request_content(link), "html.parser")
        redgif_src = soup.find("meta", {"property": "og:video"}).attrs["content"]
        title = soup.find("title").text
        user = title.split("by ")[1].split(" |")[0]

        if save_file(link=redgif_src, title=title, user=user):
            counter += 1

    logging.info(f"{counter} Redgifs files saved")


def get_redgifs_link(post):
    redgif_link_probe = post.find_elements(By.CSS_SELECTOR, "a[href*=redgifs]")

    if len(redgif_link_probe) > 0:
        return redgif_link_probe[0].get_attribute("href")

    else:
        return None


def toggle_complex_post_details(expand_button):
    successful = False

    while not successful:
        try:
            expand_button.click()
            successful = True

        except (ElementClickInterceptedException, ElementNotInteractableException):
            logging.warning("Error expanding complex post details, retrying...")
            page_scroll(Keys.PAGE_UP)
            time.sleep(TIME_SLEEP_SECONDS)


def centralize_at_element(element):
    driver.execute_script("arguments[0].scrollIntoView(true);", element)


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
                logging.info("Inspecting complex post details")
                toggle_complex_post_details(expand_button_probe[0])

                # centralize_at_element(expand_button_probe[0])
                # page_scroll(Keys.UP)
                time.sleep(2)

                post_image_elements = post.find_elements(By.CSS_SELECTOR, "img[src]:not([alt='']):not([src=''])")

                if len(post_image_elements) >= 5:
                    next_button_probe = post.find_elements(By.CSS_SELECTOR, "a[title='Next']")

                    while len(next_button_probe) > 0:
                        next_button_probe[0].click()
                        next_button_probe = post.find_elements(By.CSS_SELECTOR, "a[title='Next']")

                    post_image_elements = post.find_elements(By.CSS_SELECTOR, "img[src]:not([alt='']):not([src=''])")

                author = get_post_author(post)

                count += [download_image_element(image_element=i, user=author) for i in post_image_elements].count(True)
                toggle_complex_post_details(expand_button_probe[0])

    logging.info(f"{count} files saved")


def get_post_author(post):
    try:
        return post.find_element(By.CSS_SELECTOR, "a[data-testid='post_author_link']").text.replace("u/", "")

    except NoSuchElementException:
        return "UNKNOWN"


def sanitize_string(str_input):
    return "".join(c for c in str_input if c.isalnum() or c in "._- ")


def is_duplicate(image_content):
    global hashes
    image_hash = hashlib.md5(image_content).hexdigest()
    is_duplicated = hashes.__contains__(image_hash)

    if not is_duplicated:
        hashes.append(image_hash)

    return is_duplicated


def download_image_element(image_element, user, file_content=None, image_src=None, image_title=None):
    if not image_title:
        image_title = image_element.get_attribute("alt")

    if not image_src:
        image_src = image_element.get_attribute("src")

    return (file_is_downloadable(image_src.split("/")[-1]) and
            save_file(content=file_content, link=image_src, title=image_title, user=user))


def save_file(link, user, title, content=None):
    parsed_link = urlparse(link)
    name_parts = parsed_link.path.split(".")
    name_identifier = name_parts[0].split("/")[-1]
    format_probe = parse_qs(parsed_link.query)

    if "format" in format_probe.keys():
        extension = format_probe["format"][0]

    else:
        extension = name_parts[-1]

    path = IMAGE_OUTPUT_DIR if file_is_image(extension) else VIDEO_OUTPUT_DIR
    local_path = f"{path}/{user}__{name_identifier}__{sanitize_string(title[:30])}.{extension}"
    content: bytes

    if os.path.exists(local_path):
        logging.info(f"Skipping existing file {local_path}")

    else:
        if not content:
            content = safe_request_content(link)

        if content:
            if is_duplicate(content):
                logging.info(f"Skipping duplicate file {name_identifier}")

            else:
                with open(local_path, "wb") as image_file:
                    image_file.write(content)
                    logging.info(f"File {local_path.split('/')[-1]} downloaded")
                    return True

    return False


def download_from_simple_posts(elements_grid):
    logging.info("Downloading content from simple posts 📸")
    easy_posts = []
    counter = 0

    for element in elements_grid:
        centralize_at_element(element)
        href_probe = element.find_elements(By.TAG_NAME, "a")
        image_title_probe = element.find_elements(By.TAG_NAME, "h3")
        author = get_post_author(element)

        if len(href_probe) > 0 and len(image_title_probe) > 0:
            src = href_probe[0].get_attribute("href")
            image_title = image_title_probe[0].text
            success = False

            if file_is_type(src, "gifv"):
                success = download_from_inspectable_file(src, image_title, author)

            elif len(element.find_elements(By.CSS_SELECTOR, "a[href*=redgifs]")) > 0:
                success = download_from_inspectable_file(src)

            elif file_is_downloadable(src.split("/")[-1]):
                success = download_image_element(image_element=element.find_element(By.TAG_NAME, "img"),
                                                 image_src=src,
                                                 image_title=image_title, user=author)

            else:
                download_complex_posts([element])

            if success:
                counter += 1

        else:
            download_complex_posts([element])

        easy_posts.append(element)

    logging.info(f"{counter} files saved")

    return easy_posts


def get_subreddit_content():
    driver.get(f"{REDDIT_SUB_URL}/{args.sub}/")
    posts_xpath = "//*[@id='AppRouter-main-content']/div/div/div[2]/div[4]/div[1]/div[5]/div"
    elements_grid = driver.find_elements(By.XPATH, posts_xpath)
    downloaded_elements = []
    create_output_directories()
    max_files = -1

    if args.max_files:
        max_files = int(args.max_files)

    while max_files < 0 or len(downloaded_elements) <= max_files:
        download_from_simple_posts(elements_grid)
        # full_page_scroll_down()
        downloaded_elements.extend(elements_grid)
        elements_grid = [e for e in driver.find_elements(By.XPATH, posts_xpath) if e not in downloaded_elements]

    # page_scroll_up()
    # time.sleep(TIME_SLEEP_SECONDS)
    # download_complex_posts([e for e in elements_grid if e not in easy_images])
    #
    # download_redgifs()


def main():
    logging.getLogger().setLevel(logging.INFO)
    logging.info("Starting")

    global args
    args = get_args()

    webdriver_setup()

    logging.info("Logging in")
    login()
    logging.info("Logged in")

    if args.target:
        get_user_content()

    elif args.sub:
        get_subreddit_content()

    else:
        logging.error("Either a target user or subreddit is required")

    logging.info("Done")


def webdriver_setup():
    options = webdriver.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument('--disable-dev-shm-usage')

    if args.headless:
        options.add_argument("--headless")

    global driver
    driver = webdriver.Chrome(options=options)


if __name__ == "__main__":
    main()
