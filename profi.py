import logging
import re
import time
import tempfile
import threading
import random
import yaml
import json
import hashlib
import shutil

import telebot
from bs4 import BeautifulSoup as bs
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

from config_logging import setup_logging

# Настройка логирования из отдельного файла конфигурации
setup_logging()
logger = logging.getLogger(__name__)


def generate_task_id(task_title: str, task_description: str, task_url: str) -> str:
    unique_str = task_title + task_description + task_url
    return hashlib.md5(unique_str.encode('utf-8')).hexdigest()


class ProfiBotScraper:
    URL_TASKS = 'https://profi.ru/backoffice/n.php'
    URL_SITE = 'https://profi.ru'

    def __init__(self,
                 login: str,
                 password: str,
                 telegram_token: str,
                 telegram_chat_id: str,
                 good_words: list,
                 bad_words: list,
                 refresh_interval: int,
                 batch_size: int,
                 scroll_pause_time: int,
                 state_file: str = "state.json"):
        self.login = login
        self.password = password
        self.token = telegram_token
        self.chat_id = telegram_chat_id
        self.bot = telebot.TeleBot(self.token)

        self.good_words = good_words
        self.bad_words = bad_words

        self.REFRESH_INTERVAL = refresh_interval
        self.BATCH_SIZE = batch_size
        self.SCROLL_PAUSE_TIME = scroll_pause_time

        self.all_tasks: list = []
        self.sent_tasks: set = set()
        self.state_file = state_file
        self.load_state()

        self.lock = threading.Lock()
        self.shutdown_flag = False  # Флаг для корректного завершения потоков

        self.temp_user_data_dir = tempfile.mkdtemp()

        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument(f'--user-data-dir={self.temp_user_data_dir}')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--headless=new')

        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Safari/605.1.15",
        ]
        chosen_user_agent = random.choice(user_agents)
        chrome_options.add_argument(f'user-agent={chosen_user_agent}')
        logger.info("Выбран User-Agent: %s", chosen_user_agent)

        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.threads = []

    def load_state(self) -> None:
        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.all_tasks = data.get('all_tasks', [])
                self.sent_tasks = set(data.get('sent_tasks', []))
            logger.info("Состояние успешно загружено из %s", self.state_file)
        except FileNotFoundError:
            logger.info("Файл состояния %s не найден, начинаем с пустого состояния", self.state_file)
        except Exception as e:
            logger.exception("Ошибка загрузки состояния: %s", e)
            self.shutdown()

    def save_state(self) -> None:
        data = {
            'all_tasks': self.all_tasks,
            'sent_tasks': list(self.sent_tasks)
        }
        try:
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info("Состояние успешно сохранено в %s", self.state_file)
        except Exception as e:
            logger.exception("Ошибка сохранения состояния: %s", e)
            self.shutdown()

    def login_to_site(self) -> None:
        try:
            self.driver.get(self.URL_TASKS)
        except TimeoutException as ex:
            logger.exception("TimeoutException при загрузке страницы авторизации: %s", ex)
            try:
                self.driver.refresh()
            except Exception as e:
                logger.exception("Ошибка при обновлении страницы авторизации: %s", e)
                self.shutdown()

        try:
            login_field = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "ui-input"))
            )
            login_field.clear()
            login_field.send_keys(self.login)

            login_fields = self.driver.find_elements(By.CLASS_NAME, "ui-input")
            if len(login_fields) > 1:
                login_fields[1].clear()
                login_fields[1].send_keys(self.password)

            button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.CLASS_NAME, "ui-button"))
            )
            button.click()
            logger.info("Клик по кнопке авторизации")
        except Exception as e:
            logger.exception("Ошибка при авторизации: %s", e)
            self.shutdown()

        time.sleep(5)

    def refresh_page(self) -> None:
        last_height = self.driver.execute_script("return document.body.scrollHeight")
        while True:
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(self.SCROLL_PAUSE_TIME)
            self.driver.execute_script("window.scrollBy(0, -300);")
            time.sleep(self.SCROLL_PAUSE_TIME / 2)
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(random.randint(self.SCROLL_PAUSE_TIME, self.SCROLL_PAUSE_TIME + 3))
            new_height = self.driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                logger.info("Конец прокрутки страницы")
                break
            last_height = new_height

    def cleanup_old_tasks(self) -> None:
        three_weeks_seconds = 21 * 86400
        current_time = time.time()
        original_count = len(self.all_tasks)
        self.all_tasks = [task for task in self.all_tasks
                          if current_time - task.get('added', current_time) < three_weeks_seconds]
        valid_ids = {task['id'] for task in self.all_tasks}
        self.sent_tasks = self.sent_tasks.intersection(valid_ids)
        removed = original_count - len(self.all_tasks)
        logger.info("Очищено старых задач: %d удалено, осталось: %d", removed, len(self.all_tasks))

    def update_all_tasks(self) -> None:
        try:
            self.driver.get(self.URL_TASKS)
        except TimeoutException as ex:
            logger.exception("TimeoutException при обновлении страницы: %s", ex)
            try:
                self.driver.refresh()
            except Exception as e:
                logger.exception("Ошибка при обновлении страницы: %s", e)
                self.shutdown()

        self.refresh_page()
        page = self.driver.page_source
        soup = bs(page, 'html.parser')
        blocks = soup.find_all(class_=re.compile('SnippetBodyStyles__Container-'))
        new_tasks = []
        with self.lock:
            existing_ids = {task['id'] for task in self.all_tasks}
            for block in blocks:
                task_key = block.find(class_=re.compile('SubjectAndPriceStyles__SubjectsText-'))
                name = block.find(class_=re.compile('SnippetBodyStyles__MainInfo-'))
                href = block.attrs.get('href', '')
                if not task_key or not name or not href:
                    continue

                my_url = self.URL_SITE + str(href)
                task_title = task_key.get_text().strip()
                task_description = name.get_text().strip()

                arr_url = ''.join(filter(lambda x: x.isdigit(), my_url))
                task_id = str(href) if len(arr_url) < 8 else arr_url[:8]

                if task_id not in existing_ids:
                    new_tasks.append({
                        'id': task_id,
                        'title': task_title,
                        'description': task_description,
                        'url': my_url,
                        'added': time.time()
                    })

            if new_tasks:
                self.all_tasks = new_tasks + self.all_tasks
                logger.info("Добавлено новых задач: %d", len(new_tasks))
            else:
                logger.info("Новых задач не найдено.")
            logger.info("Всего задач в хранилище: %d", len(self.all_tasks))
            self.cleanup_old_tasks()
            self.save_state()

    def send_batch(self) -> None:
        new_tasks = []
        with self.lock:
            for task in self.all_tasks:
                if task['id'] not in self.sent_tasks:
                    if self.word_check((task['title'], task['description'], task['url']),
                                       set(self.good_words),
                                       set(self.bad_words)):
                        new_tasks.append(task)
        if not new_tasks:
            logger.info("Нет новых задач для отправки.")
            return

        batch = new_tasks[:self.BATCH_SIZE]
        for task in batch:
            formatted_message = self.format_task_message((task['title'], task['description'], task['url']))
            if formatted_message:
                self.send_telegram_message(formatted_message)
            with self.lock:
                self.sent_tasks.add(task['id'])
            logger.info("Задача отправлена: %s", task['title'])
        logger.info("Отправлено пачкой %d задач", len(batch))
        logger.info("Всего отправлено задач: %d", len(self.sent_tasks))
        self.save_state()

    @staticmethod
    def escape_markdown(text: str) -> str:
        escape_chars = r"_*[]~`>#|{}"
        return re.sub(f"([{re.escape(escape_chars)}])", r"\\\1", text)

    @staticmethod
    def format_task_message(task_stack: tuple) -> str or None:
        task_title, task_description, task_url = task_stack
        task_title = ProfiBotScraper.escape_markdown(task_title.strip())
        task_description = ProfiBotScraper.escape_markdown(task_description.strip())

        if isinstance(task_url, str):
            url_match = re.search(r"https://profi\.ru/backoffice/n\.php\?o=\d+", task_url)
            task_url = url_match.group(0) if url_match else None
        else:
            task_url = None

        if task_url:
            return (
                f"📌 *Новое задание*\n\n"
                f"📝 *{task_title}*\n"
                f"{task_description}\n\n"
                f"🔗 [Подробнее о задании]({task_url})"
            )
        else:
            return None

    @staticmethod
    def word_check(full_text: tuple,
                   good: set,
                   bad: set) -> bool:
        for text in full_text:
            for good_word in good:
                if good_word.lower() in text.lower():
                    for bad_word in bad:
                        if bad_word.lower() in text.lower():
                            return False
                    return True
        return False

    def send_telegram_message(self, message: str) -> None:
        max_message_length = 4000
        try:
            if len(message) > max_message_length:
                parts = [message[i: i + max_message_length] for i in range(0, len(message), max_message_length)]
                for part in parts:
                    self.bot.send_message(self.chat_id, part, parse_mode="Markdown")
                    time.sleep(2)
            else:
                self.bot.send_message(self.chat_id, message, parse_mode="Markdown")
            logger.info("Сообщение отправлено в Telegram")
        except Exception as e:
            logger.exception("Ошибка при отправке сообщения в Telegram: %s", e)
            self.shutdown()

    def sending_loop(self) -> None:
        try:
            while not self.shutdown_flag:
                self.send_batch()
                sleep_duration = random.uniform(self.REFRESH_INTERVAL - 5, self.REFRESH_INTERVAL + 5)
                time.sleep(sleep_duration)
        except Exception as e:
            logger.exception("Критическая ошибка в sending_loop: %s", e)
            self.shutdown()

    def search_loop(self) -> None:
        try:
            while not self.shutdown_flag:
                sleep_time = random.randint(300, 600)
                logger.info("Поисковый процесс ожидает %d секунд", sleep_time)
                time.sleep(sleep_time)
                self.update_all_tasks()
        except Exception as e:
            logger.exception("Критическая ошибка в search_loop: %s", e)
            self.shutdown()

    def run(self) -> None:
        logger.info("Начало работы скрипта")
        self.login_to_site()
        sending_thread = threading.Thread(target=self.sending_loop, daemon=True, name="SendingThread")
        search_thread = threading.Thread(target=self.search_loop, daemon=True, name="SearchThread")
        sending_thread.start()
        search_thread.start()
        self.threads.extend([sending_thread, search_thread])
        try:
            while not self.shutdown_flag:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Получен сигнал остановки. Завершаем работу.")
            self.shutdown()
        finally:
            for t in self.threads:
                t.join(timeout=5)
            self.save_state()
            logger.info("Работа завершена.")

    def shutdown(self) -> None:
        logger.info("Начало процедуры завершения работы")
        self.shutdown_flag = True
        try:
            self.driver.quit()
        except Exception as e:
            logger.exception("Ошибка при закрытии драйвера: %s", e)
        try:
            shutil.rmtree(self.temp_user_data_dir)
        except Exception as e:
            logger.exception("Ошибка при удалении временной директории: %s", e)
        self.save_state()
        logger.info("Скрипт завершил работу корректно.")


if __name__ == '__main__':
    try:
        with open("config.yaml", "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except Exception as e:
        logger.exception("Ошибка загрузки конфигурации: %s", e)
        raise

    auth = config.get("auth", {})
    search = config.get("search", {})
    settings = config.get("settings", {})

    scraper = ProfiBotScraper(
        login=auth.get("login"),
        password=auth.get("password"),
        telegram_token=auth.get("telegram_token"),
        telegram_chat_id=auth.get("telegram_chat_id"),
        good_words=search.get("good_words", []),
        bad_words=search.get("bad_words", []),
        refresh_interval=settings.get("refresh_interval", 60),
        batch_size=settings.get("batch_size", 20),
        scroll_pause_time=settings.get("scroll_pause_time", 2)
    )
    try:
        scraper.run()
    except KeyboardInterrupt:
        scraper.shutdown()
