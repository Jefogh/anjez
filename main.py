# -*- coding: utf-8 -*-
import os
import sys
import threading
import time
import base64
import io
import random
import requests
import urllib3
import numpy as np

# مكتبات دعم اللغة العربية
try:
    import arabic_reshaper
    from bidi.algorithm import get_display
except ImportError:
    print("خطأ: يرجى تثبيت مكتبات اللغة العربية أولاً عبر الأمر:")
    print("pip install arabic-reshaper python-bidi")
    exit()

from PIL import Image, ImageOps

# مكتبات Kivy
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.uix.progressbar import ProgressBar
from kivy.uix.popup import Popup
from kivy.uix.image import Image as KivyImage
from kivy.core.image import Image as CoreImage
from kivy.clock import Clock
from kivy.core.text import LabelBase, DEFAULT_FONT
from kivy.graphics import Color, RoundedRectangle


# ---------------------------------------------------------
# دالة ذكية لمعرفة المسار الحالي للملفات (ضرورية جداً لعمل الـ APK)
def get_resource_path(filename):
    base_path = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base_path, filename)


# إعداد خط اللغة العربية
FONT_PATH = get_resource_path("arial.ttf")
if os.path.exists(FONT_PATH):
    LabelBase.register(DEFAULT_FONT, FONT_PATH)
else:
    print(f"تنبيه: ملف الخط '{FONT_PATH}' غير موجود. قد تظهر الحروف العربية كمربعات.")

# مسار نموذج الذكاء الاصطناعي (تأكد من عدم وجود مسافات في الاسم)
ONNX_MODEL_PATH = get_resource_path("holako_bag.onnx")

# رابط السيرفر الخاص بك على بايثون أني وير (استبدل yourusername باسم حسابك)
PYTHONANYWHERE_URL = "https://hosalin.pythonanywhere.com/status"
# ---------------------------------------------------------

try:
    import onnxruntime as ort
except ImportError:
    print("خطأ: مكتبة onnxruntime غير مثبتة.")
    exit()

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

CHARSET = '0123456789abcdefghijklmnopqrstuvwxyz'
CHAR2IDX = {c: i for i, c in enumerate(CHARSET)}
IDX2CHAR = {i: c for c, i in CHAR2IDX.items()}
NUM_CLASSES = len(CHARSET)
NUM_POS = 5


def ar(text):
    """
    دالة لمعالجة الحروف العربية المتقطعة والمعكوسة.
    """
    try:
        reshaped_text = arabic_reshaper.reshape(str(text))
        bidi_text = get_display(reshaped_text)
        return bidi_text
    except Exception:
        return text


def preprocess_for_model_numpy(pil_image):
    img_resized = pil_image.resize((224, 224), Image.Resampling.BILINEAR)
    img_rgb = img_resized.convert("L").convert("RGB")
    arr = np.array(img_rgb, dtype=np.float32) / 255.0
    arr = np.transpose(arr, (2, 0, 1))
    arr = (arr - 0.5) / 0.5
    input_tensor = np.expand_dims(arr, axis=0)
    return input_tensor


def pil_to_kivy_texture(pil_image):
    data = io.BytesIO()
    pil_image.save(data, format='png')
    data.seek(0)
    im = CoreImage(io.BytesIO(data.read()), ext='png')
    return im.texture


class CaptchaApp(App):
    def build(self):
        self.accounts = {}
        self.current_captcha = None
        self.session = None

        if not os.path.exists(ONNX_MODEL_PATH):
            print(ar("خطأ فادح: ملف نموذج ONNX غير موجود."))
        else:
            try:
                self.session = ort.InferenceSession(ONNX_MODEL_PATH, providers=['CPUExecutionProvider'])
            except Exception as e:
                print(ar("خطأ في تحميل النموذج:") + f" {e}")

        self.main_layout = BoxLayout(orientation='vertical', padding=10, spacing=10)

        welcome_text = ar("مرحباً! قم بإضافة حساب للبدء.")
        self.notification_label = Label(
            text=f"[color=3399ff]{welcome_text}[/color]",
            markup=True, size_hint_y=None, height=40, font_size=16
        )
        self.main_layout.add_widget(self.notification_label)

        self.btn_add = Button(text=ar("إضافة حساب"), size_hint_y=None, height=50, font_size=18)
        self.btn_add.bind(on_press=self.add_account_popup)
        self.main_layout.add_widget(self.btn_add)
        self.btn_add.disabled = True  # يتم التعطيل حتى يتحقق من السيرفر

        self.scroll_view = ScrollView()
        self.accounts_frame = BoxLayout(orientation='vertical', size_hint_y=None, spacing=15)
        self.accounts_frame.bind(minimum_height=self.accounts_frame.setter('height'))
        self.scroll_view.add_widget(self.accounts_frame)
        self.main_layout.add_widget(self.scroll_view)

        self.captcha_layout = BoxLayout(orientation='vertical', size_hint_y=None, height=160, spacing=5)
        self.main_layout.add_widget(self.captcha_layout)

        self.speed_label = Label(text=ar("المعالجة الأولية: - | التنبؤ: -"), size_hint_y=None, height=30, font_size=14)
        self.main_layout.add_widget(self.speed_label)

        return self.main_layout

    def on_start(self):
        # فحص التفعيل فور تشغيل الواجهة
        self.show_server_checking_popup()

    def show_server_checking_popup(self):
        content = BoxLayout(orientation='vertical', padding=20, spacing=10)
        self.server_status_label = Label(text=ar("جارٍ الاتصال بسيرفر التحكم والتحقق من الصلاحية..."), font_size=14)
        content.add_widget(self.server_status_label)

        self.server_popup = Popup(
            title=ar("نظام الحماية والتفعيل"),
            content=content,
            size_hint=(0.85, 0.35),
            auto_dismiss=False,
            title_align='right'
        )
        self.server_popup.open()

        threading.Thread(target=self.verify_server_backend, daemon=True).start()

    def verify_server_backend(self):
        try:
            response = requests.get(PYTHONANYWHERE_URL, timeout=6, verify=False)
            if response.status_code == 200 and "ENABLED" in response.text:
                Clock.schedule_once(self.server_check_success)
            else:
                Clock.schedule_once(lambda dt: self.server_check_failed("السيرفر مغلق أو غير مصرح لك بالتشغيل حالياً."))
        except Exception:
            Clock.schedule_once(lambda dt: self.server_check_failed("فشل الاتصال! تأكد من الإنترنت أو حالة السيرفر."))

    def server_check_success(self, dt):
        self.server_popup.dismiss()
        self.btn_add.disabled = False
        self.update_notification("تم التحقق من السيرفر بنجاح، البرنامج جاهز للعمل.", "green")

    def server_check_failed(self, error_msg):
        self.server_status_label.text = ar(error_msg)
        self.update_notification("تنبيه أمني: التطبيق موقوف حالياً.", "red")

    def update_notification(self, message, color="black"):
        colors_hex = {
            "black": "ffffff", "blue": "3399ff", "red": "ff3333",
            "green": "33cc33", "orange": "ff9933", "cyan": "33ffff", "grey": "aaaaaa"
        }
        hex_code = colors_hex.get(color, "ffffff")
        formatted_text = f"[color={hex_code}]{ar(message)}[/color]"

        def _update(dt):
            self.notification_label.text = formatted_text

        Clock.schedule_once(_update)
        print(f"[{time.strftime('%H:%M:%S')}] [{color.upper()}] {message}")

    def generate_user_agent(self):
        ua_list = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Linux; Android 13; SM-S908B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.6312.105 Mobile Safari/537.36",
        ]
        return random.choice(ua_list)

    def create_session(self, user_agent):
        headers = {
            "User-Agent": user_agent,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "ar,en-US;q=0.9,en;q=0.8",
            "Content-Type": "application/json",
            "Origin": "https://ecsc.gov.sy",
            "Referer": "https://ecsc.gov.sy/",
            "Connection": "keep-alive",
        }
        session = requests.Session()
        session.headers.update(headers)
        session.verify = False
        return session

    def add_account_popup(self, instance):
        content = BoxLayout(orientation='vertical', spacing=10, padding=10)
        user_input = TextInput(hint_text="Username", multiline=False, halign='left', font_size=16)
        pass_input = TextInput(hint_text="Password", password=True, multiline=False, halign='left', font_size=16)

        btn_layout = BoxLayout(size_hint_y=None, height=50, spacing=10)
        btn_login = Button(text=ar("تسجيل الدخول"))
        btn_cancel = Button(text=ar("إلغاء"))

        btn_layout.add_widget(btn_cancel)
        btn_layout.add_widget(btn_login)
        content.add_widget(user_input)
        content.add_widget(pass_input)
        content.add_widget(btn_layout)

        popup = Popup(title=ar("إضافة حساب جديد"), content=content, size_hint=(0.9, 0.45), title_align='right')
        btn_cancel.bind(on_press=popup.dismiss)

        def do_login(btn_instance):
            u = user_input.text.strip()
            p = pass_input.text.strip()
            if u and p:
                popup.dismiss()
                threading.Thread(target=self.add_account_thread, args=(u, p), daemon=True).start()

        btn_login.bind(on_press=do_login)
        popup.open()

    def add_account_thread(self, user, pwd):
        if user in self.accounts:
            self.update_notification(f"الحساب '{user}' موجود بالفعل.", "orange")
            return

        session = self.create_session(self.generate_user_agent())
        if not self.login(user, pwd, session):
            return

        self.accounts[user] = {"password": pwd, "session": session}
        proc_ids_data = self.fetch_process_ids(session, user)
        if proc_ids_data is not None:
            Clock.schedule_once(lambda dt: self._create_account_ui(user, proc_ids_data))
        else:
            if user in self.accounts:
                del self.accounts[user]

    def login(self, username, password, session, retries=2):
        url = "https://api.ecsc.gov.sy:8443/secure/auth/login"
        payload = {"username": username, "password": password}
        login_headers = {'Referer': 'https://ecsc.gov.sy/login'}

        for attempt in range(retries):
            try:
                self.update_notification(f"[{username}] محاولة الدخول ({attempt + 1}/{retries})...", "grey")
                r = session.post(url, json=payload, headers=login_headers, timeout=(10, 20))
                if r.status_code == 200:
                    self.update_notification(f"[{username}] تم تسجيل الدخول بنجاح.", "green")
                    return True
                elif r.status_code == 401:
                    self.update_notification(f"[{username}] فشل: بيانات الاعتماد غير صحيحة.", "red")
                    return False
                else:
                    self.update_notification(f"[{username}] فشل تسجيل الدخول ({r.status_code}).", "red")
                    if 500 <= r.status_code < 600 and attempt < retries - 1:
                        continue
                    else:
                        return False
            except requests.exceptions.RequestException:
                self.update_notification(f"[{username}] خطأ شبكة أثناء تسجيل الدخول.", "red")
                if attempt < retries - 1:
                    continue
                else:
                    return False
            except Exception as e:
                self.update_notification(f"[{username}] خطأ غير متوقع: {e}", "red")
                return False
        return False

    def fetch_process_ids(self, session, username):
        url = "https://api.ecsc.gov.sy:8443/dbm/db/execute"
        payload = {"ALIAS": "OPkUVkYsyq", "P_USERNAME": "WebSite", "P_PAGE_INDEX": 0, "P_PAGE_SIZE": 100}
        headers = {"Alias": "OPkUVkYsyq", "Referer": "https://ecsc.gov.sy/requests"}
        try:
            r = session.post(url, json=payload, headers=headers, timeout=(10, 20))
            if r.status_code == 200:
                return r.json().get("P_RESULT", [])
            else:
                self.update_notification(f"[{username}] فشل جلب العمليات ({r.status_code}).", "red")
                return None
        except Exception:
            self.update_notification(f"[{username}] خطأ أثناء جلب العمليات.", "red")
            return None

    def _create_account_ui(self, user, processes_data):
        acc_box = BoxLayout(orientation='vertical', size_hint_y=None, spacing=8, padding=10)
        acc_box.bind(minimum_height=acc_box.setter('height'))

        with acc_box.canvas.before:
            Color(0.18, 0.18, 0.18, 1)
            acc_box.bg_rect = RoundedRectangle(radius=[10])

        def update_rect(instance, value):
            instance.bg_rect.pos = instance.pos
            instance.bg_rect.size = instance.size

        acc_box.bind(pos=update_rect, size=update_rect)

        header_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=35)
        lbl = Label(text=ar(f"الحساب: {user}"), size_hint_x=1, font_size=16, color=(1, 0.8, 0.2, 1), bold=True)
        header_layout.add_widget(lbl)
        acc_box.add_widget(header_layout)

        divider = BoxLayout(size_hint_y=None, height=2)
        with divider.canvas.before:
            Color(0.4, 0.4, 0.4, 1)
            divider.rect = RoundedRectangle(radius=[1])

        def update_div(inst, val):
            inst.rect.pos = inst.pos
            inst.rect.size = inst.size

        divider.bind(pos=update_div, size=update_div)
        acc_box.add_widget(divider)

        if not processes_data:
            acc_box.add_widget(
                Label(text=ar("لا توجد عمليات متاحة حالياً."), size_hint_y=None, height=30, color=(0.6, 0.6, 0.6, 1)))
        else:
            for proc in processes_data:
                pid = proc.get("PROCESS_ID")
                name = ar(proc.get("ZCENTER_NAME", f"عملية {pid}"))
                if pid is None:
                    continue

                row = BoxLayout(orientation='horizontal', size_hint_y=None, height=45, spacing=10)
                pbar = ProgressBar(max=100, size_hint_x=0.3)
                pbar.opacity = 0

                btn = Button(text=str(name), size_hint_x=0.7, background_color=(0.2, 0.6, 0.8, 1))
                btn.bind(on_press=lambda instance, u=user, p=pid, pb=pbar, b=btn: threading.Thread(
                    target=self._handle_captcha_request, args=(u, p, pb, b), daemon=True).start())

                row.add_widget(pbar)
                row.add_widget(btn)
                acc_box.add_widget(row)

        self.accounts_frame.add_widget(acc_box)

    def _handle_captcha_request(self, user, pid, prog_bar, clicked_btn):
        Clock.schedule_once(lambda dt: setattr(prog_bar, 'opacity', 1))

        self.update_notification(f"[{user}] جارٍ طلب كابتشا للعملية '{pid}'...", "grey")
        captcha_data = None
        try:
            if user not in self.accounts or 'session' not in self.accounts[user]:
                raise ValueError("معلومات الجلسة غير موجودة.")
            session = self.accounts[user]["session"]
            captcha_data = self.get_captcha(session, pid, user)
        except Exception:
            self.update_notification(f"[{user}] خطأ فادح أثناء طلب الكابتشا.", "red")
        finally:
            Clock.schedule_once(lambda dt: setattr(prog_bar, 'opacity', 0))

        if captcha_data:
            self.update_notification(f"[{user}] كابتشا جديدة مستلمة. يتم معالجتها...", "cyan")
            self.current_captcha = (user, pid)
            threading.Thread(target=self.show_and_process_captcha, args=(captcha_data, user, pid), daemon=True).start()

    def get_captcha(self, session, pid, user):
        url = f"https://api.ecsc.gov.sy:8443/captcha/get/{pid}"
        try:
            r = session.get(url, timeout=(15, 30))
            if r.status_code == 200:
                captcha_info = r.json()
                if "file" in captcha_info and captcha_info["file"]:
                    self.update_notification(f"[{user}] تم جلب الكابتشا بنجاح.", "green")
                    return captcha_info["file"]
                else:
                    self.update_notification(f"[{user}] استجابة الكابتشا فارغة.", "orange")
                    return None
            elif r.status_code in (401, 403):
                self.update_notification(f"[{user}] خطأ صلاحية. سيتم إعادة الدخول.", "orange")
                if self.accounts[user].get("password"):
                    self.login(user, self.accounts[user]["password"], session)
                return None
            else:
                self.update_notification(f"[{user}] خطأ سيرفر عند طلب الكابتشا ({r.status_code}).", "red")
                return None
        except Exception:
            self.update_notification(f"[{user}] خطأ شبكة عند طلب الكابتشا.", "red")
            return None

    def predict_captcha(self, pil_image):
        start_preprocess = time.time()
        try:
            input_tensor = preprocess_for_model_numpy(pil_image)
        except Exception:
            return "preprocess_err", 0, 0
        end_preprocess = time.time()

        start_predict = time.time()
        predicted_text = "error"
        if self.session:
            try:
                input_name = self.session.get_inputs()[0].name
                ort_outs = self.session.run(None, {input_name: input_tensor})[0]
                expected_elements = NUM_POS * NUM_CLASSES
                ort_outs_trimmed = ort_outs[:, :expected_elements]
                ort_outs_reshaped = ort_outs_trimmed.reshape(1, NUM_POS, NUM_CLASSES)
                predicted_indices = np.argmax(ort_outs_reshaped, axis=2)[0]
                predicted_text = ''.join(IDX2CHAR[i] for i in predicted_indices if i in IDX2CHAR)
            except Exception:
                predicted_text = "predict_err"
        end_predict = time.time()
        return predicted_text, (end_preprocess - start_preprocess) * 1000, (end_predict - start_predict) * 1000

    def show_and_process_captcha(self, base64_data, task_user, task_pid):
        try:
            b64 = base64_data.split(",", 1)[1] if "," in base64_data else base64_data
            raw = base64.b64decode(b64)
            pil = Image.open(io.BytesIO(raw))

            frames = []
            try:
                pil.seek(0)
                while True:
                    frames.append(np.array(pil.convert("RGB"), dtype=np.float32))
                    pil.seek(pil.tell() + 1)
            except EOFError:
                pass

            stack = np.stack(frames, axis=0)
            summed_clipped = np.clip(np.sum(stack, axis=0) / np.sum(stack, axis=0).max() * 255.0, 0, 255).astype(
                np.uint8)
            gray_pil = Image.fromarray(summed_clipped).convert("L")
            auto = ImageOps.autocontrast(gray_pil, cutoff=1)
            equalized = ImageOps.equalize(auto)
            binary = equalized.point(lambda p: 255 if p > 128 else 0)

            predicted_solution, pre_ms, pred_ms = self.predict_captcha(binary)

            if self.current_captcha != (task_user, task_pid):
                return

            self.update_notification(f"[{task_user}] النص المتوقع: {predicted_solution}", "blue")
            Clock.schedule_once(lambda dt: self.update_captcha_ui(binary, predicted_solution, pre_ms, pred_ms))

            if predicted_solution not in ["error", "preprocess_err", "predict_err"]:
                threading.Thread(target=self.submit_captcha_solution, args=(task_user, task_pid, predicted_solution),
                                 daemon=True).start()

        except Exception:
            self.update_notification(f"[{task_user}] خطأ أثناء معالجة الصورة.", "red")

    def update_captcha_ui(self, binary_img, solution, pre_ms, pred_ms):
        self.speed_label.text = ar(f"معالجة أولية: {pre_ms:.1f} ms | التنبؤ: {pred_ms:.1f} ms")
        self.captcha_layout.clear_widgets()

        display_image = binary_img.resize((180, 70), Image.Resampling.LANCZOS)
        texture = pil_to_kivy_texture(display_image)

        img_widget = KivyImage(texture=texture, size_hint=(None, None), size=(180, 70), pos_hint={'center_x': 0.5})
        lbl_widget = Label(text=ar(f"الحل المتوقع: {solution}"), size_hint_y=None, height=40, font_size=18, bold=True)

        self.captcha_layout.add_widget(img_widget)
        self.captcha_layout.add_widget(lbl_widget)

    def submit_captcha_solution(self, task_user, task_pid, solution):
        if task_user not in self.accounts or "session" not in self.accounts[task_user]: return
        session = self.accounts[task_user]["session"]
        url = f"https://api.ecsc.gov.sy:8443/rs/reserve?id={task_pid}&captcha={solution}"

        try:
            r = session.get(url, timeout=(10, 45))
            response_text = r.text

            if r.status_code == 200:
                # إذا كان الرد 200 وكان النص فارغاً تماماً أو به كلمات نجاح يتم التثبيت
                if response_text.strip() == "" or "نجاح" in response_text or "success" in response_text.lower() or "تم الحجز" in response_text:
                    self.update_notification(f"[{task_user}] نجاح! تم الحجز وتثبيت المعاملة بنجاح.", "green")
                elif "خطأ" in response_text or "incorrect" in response_text.lower() or "failed" in response_text.lower():
                    self.update_notification(f"[{task_user}] فشل: حل خاطئ أو العملية مغلقة.", "orange")
                else:
                    self.update_notification(f"[{task_user}] تم الإرسال. نص الرد: {response_text[:30]}", "blue")
            else:
                self.update_notification(f"[{task_user}] فشل في الحجز (الحالة: {r.status_code}).", "red")
        except Exception:
            self.update_notification(f"[{task_user}] خطأ شبكة أثناء الإرسال.", "red")


if __name__ == "__main__":
    CaptchaApp().run()
