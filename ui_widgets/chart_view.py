from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTextEdit, QLineEdit
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QTextCursor

class MervisChatWindow(QWidget):
    message_sent = pyqtSignal(str) 

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Mervis Chat")
        self.setGeometry(1450, 100, 400, 600)
        self.setStyleSheet("background-color: #F0F8FF;")

        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)

        title = QLabel("Talk with Mervis")
        title.setStyleSheet("font-weight: bold; font-size: 12pt; color: #2C3E50; margin-bottom: 5px;")
        layout.addWidget(title)

        self.chat_log = QTextEdit()
        self.chat_log.setReadOnly(True)
        self.chat_log.setStyleSheet("background-color: white; border: 1px solid #BDC3C7; font-family: 'Malgun Gothic'; font-size: 10pt;")
        layout.addWidget(self.chat_log)

        self.input_field = QLineEdit()
        self.input_field.setStyleSheet("background-color: white; padding: 8px; border: 1px solid #BDC3C7;")
        self.input_field.returnPressed.connect(self.send_message)
        layout.addWidget(self.input_field)

        self.setLayout(layout)

    def send_message(self):
        text = self.input_field.text()
        if not text: return
        
        self.append_user_message(text)
        self.input_field.clear()
        
        self.message_sent.emit(text)

    def append_user_message(self, text):
        self.chat_log.append(f"<div style='margin: 5px;'><b style='color:#2980B9;'>User:</b> {text}</div>")
        self.scroll_to_bottom()

    def append_bot_message(self, text):
        self.chat_log.append(f"<div style='margin: 5px; background-color:#ECF0F1; padding:5px; border-radius:5px;'><b style='color:#E67E22;'>Mervis:</b> {text}</div>")
        self.scroll_to_bottom()

    def scroll_to_bottom(self):
        cursor = self.chat_log.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.chat_log.setTextCursor(cursor)